"""Verifies Issue #109 AC-1: ``RealizationIntent`` is built from a fixture ``PlanReference`` +
``ConceptSpec``, every field populated or explicitly UNKNOWN, round-trips through JSON, and never
invents a fact the reference does not carry -- checked against the committed 20-plan fixture set
(``backend/tests/architectural_brain/fixtures/plans/*.json``).

AC-2 (``test_two_donors_for_one_brief_realize_to_different_layouts``) needs ``realize.py`` -- the
ConceptSpec -> Geometry Core compiler from Issue #96 -- which exists only on the unmerged branch
``agent/96-poc-architectural-brain-c-3-realization`` and is not present on this Issue's base
branch. That test is intentionally NOT included here; see the work report for #109.
"""
from __future__ import annotations

import json
import os
from dataclasses import replace

import pytest
from shapely.geometry import Polygon

from spikes.architectural_brain.brief import Brief
from spikes.architectural_brain.patterns import PRIVATE_TYPES, PUBLIC_TYPES, WET_TYPES, derive_pattern
from spikes.architectural_brain.plan_reference import PlanReference, UNKNOWN
from spikes.architectural_brain.realization_intent import RealizationIntent, intent_from
from spikes.architectural_brain.synthesis import ConceptReference, ConceptSpec

from app.vertical_slice.spec import ProgramSpec

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "plans")


def _fixture_ids() -> list[str]:
    return sorted(name[:-5] for name in os.listdir(FIXTURES_DIR) if name.endswith(".json"))


def _load_reference(plan_id: str) -> PlanReference:
    with open(os.path.join(FIXTURES_DIR, f"{plan_id}.json")) as f:
        raw = json.load(f)
    return PlanReference.from_dict(raw["plan_reference"])


def _concept_and_brief_for(ref: PlanReference) -> tuple[ConceptSpec, Brief]:
    """A ConceptSpec/Brief pair whose authoritative fields agree with each other and with `ref`'s
    own room counts -- exactly what `synthesize()` would have produced with `ref` as the primary
    donor, built directly here so this test exercises `intent_from` in isolation."""
    pattern = derive_pattern(ref)
    bedrooms = sum(1 for r in ref.rooms if r.type in ("BEDROOM", "MASTER_BEDROOM"))
    wet_rooms = sum(1 for r in ref.rooms if r.type in WET_TYPES)
    safe_room = any(r.type == "SAFE_ROOM" for r in ref.rooms)

    program = ProgramSpec(bedrooms=bedrooms, safe_room=safe_room, wet_rooms=wet_rooms, wet_room_kinds=())
    brief = Brief(program=program, stories=1)

    concept = ConceptSpec(
        concept_id=f"concept-{ref.plan_id}",
        circulation_class=pattern.circulation_class,
        zoning=pattern.zoning,
        wet_core_strategy=pattern.wet_core_strategy,
        entrance_relationship=pattern.entrance_relationship,
        bedroom_grouping_share=pattern.bedroom_grouping,
        references=(ConceptReference(plan_id=ref.plan_id, pattern_used="circulation_class", why="test fixture"),),
        bedrooms=bedrooms,
        safe_room=safe_room,
        wet_rooms=wet_rooms,
        wet_room_kinds=(),
        stories=1,
        baseline_rooms=ref.rooms,
    )
    return concept, brief


@pytest.mark.parametrize("plan_id", _fixture_ids())
def test_intent_is_built_from_the_reference_and_never_invents_facts(plan_id):
    ref = _load_reference(plan_id)
    concept, brief = _concept_and_brief_for(ref)

    intent = intent_from(ref, concept, brief)

    # Round-trips through JSON exactly.
    assert RealizationIntent.from_json(intent.to_json()).to_dict() == intent.to_dict()

    # Identity carried, never invented.
    assert intent.source_plan_id == ref.plan_id
    assert intent.concept_id == concept.concept_id

    # adjacency_edges / access_edges are EXACTLY the reference's own edges -- no more, no fewer.
    ref_adjacency = {(e.room_a, e.room_b) for e in ref.adjacency_edges}
    intent_adjacency = {(e.room_a, e.room_b) for e in intent.adjacency_edges}
    assert intent_adjacency == ref_adjacency

    ref_access = {(e.room_a, e.room_b, e.kind) for e in ref.access_edges}
    intent_access = {(e.room_a, e.room_b, e.kind) for e in intent.access_edges}
    assert intent_access == ref_access

    # exterior_exposure: one fact per room, honest UNKNOWN (known=False, sides=()) preserved when
    # the reference itself has no measured exposure for that room, otherwise the exact sides.
    exposure_by_id = {f.room_id: f for f in intent.exterior_exposure}
    assert set(exposure_by_id) == {r.id for r in ref.rooms}
    for room in ref.rooms:
        fact = exposure_by_id[room.id]
        assert fact.known == room.exposure_known
        if room.exposure_known:
            assert fact.sides == room.exterior_exposure
        else:
            assert fact.sides == ()

    # relative_placement: one fact per room, and only ever UNKNOWN when the room's own centroid
    # sits on the splitting axis -- never missing, never invented for a room absent from `ref`.
    placement_ids = {p.room_id for p in intent.relative_placement}
    assert placement_ids == {r.id for r in ref.rooms}
    for placement in intent.relative_placement:
        assert placement.primary_axis in ("FRONT", "REAR", "ABOVE", "BELOW", UNKNOWN)
        assert placement.secondary_axis in ("LEFT", "RIGHT", "ABOVE", "BELOW", UNKNOWN)

    # public_private_clusters: exactly the PUBLIC_TYPES / PRIVATE_TYPES room ids from `ref`.
    assert set(intent.public_private_clusters.public) == {r.id for r in ref.rooms if r.type in PUBLIC_TYPES}
    assert set(intent.public_private_clusters.private) == {r.id for r in ref.rooms if r.type in PRIVATE_TYPES}

    # wet_core_groups: the union of every group is exactly the reference's own WET_TYPES rooms,
    # and the groups are pairwise disjoint (never inventing a room id, never double-counting one).
    wet_ids_in_ref = {r.id for r in ref.rooms if r.type in WET_TYPES}
    all_grouped = [rid for group in intent.wet_core_groups for rid in group]
    assert set(all_grouped) == wet_ids_in_ref
    assert len(all_grouped) == len(set(all_grouped))

    # circulation_nodes: exactly the reference's own CIRCULATION rooms, "serves" only ever names
    # rooms the reference's own access_edges actually connect it to.
    circulation_ids = {r.id for r in ref.rooms if r.type == "CIRCULATION"}
    assert {n.room_id for n in intent.circulation_nodes} == circulation_ids
    access_neighbours: dict[str, set[str]] = {}
    for e in ref.access_edges:
        access_neighbours.setdefault(e.room_a, set()).add(e.room_b)
        access_neighbours.setdefault(e.room_b, set()).add(e.room_a)
    for node in intent.circulation_nodes:
        assert set(node.serves) == access_neighbours.get(node.room_id, set())

    # entrance_relationship: copied verbatim, both UNKNOWN together exactly when `ref` says so.
    assert intent.entrance_relationship.room_id == ref.entrance.room_id
    assert intent.entrance_relationship.side == ref.entrance.side

    # room_proportions: one entry per baseline room, ids preserved exactly, every share positive.
    assert {p.room_id for p in intent.room_proportions} == {r.id for r in ref.rooms}
    for prop in intent.room_proportions:
        assert prop.area_share_of_type > 0
        if prop.aspect_ratio is not None:
            assert prop.aspect_ratio > 0

    # footprint_relationships: recomputed independently here from `ref.footprint` and must match
    # exactly -- proves this is measured from the reference, not fabricated.
    poly = Polygon(ref.footprint)
    minx, miny, maxx, maxy = poly.bounds
    assert intent.footprint_relationships.width_m == pytest.approx(maxx - minx, abs=1e-6)
    assert intent.footprint_relationships.depth_m == pytest.approx(maxy - miny, abs=1e-6)


def test_intent_from_rejects_a_reference_that_does_not_carry_the_concepts_baseline_rooms():
    ref = _load_reference(_fixture_ids()[0])
    concept, brief = _concept_and_brief_for(ref)
    ghost_room = concept.baseline_rooms[0]
    concept_with_ghost = replace(
        concept, baseline_rooms=concept.baseline_rooms + (replace(ghost_room, id="GHOST_ROOM_999"),))

    with pytest.raises(ValueError):
        intent_from(ref, concept_with_ghost, brief)


def test_intent_from_rejects_a_brief_that_disagrees_with_the_concepts_authoritative_fields():
    ref = _load_reference(_fixture_ids()[0])
    concept, brief = _concept_and_brief_for(ref)
    mismatched_brief = Brief(program=ProgramSpec(bedrooms=brief.program.bedrooms + 1,
                                                 safe_room=brief.program.safe_room,
                                                 wet_rooms=brief.program.wet_rooms),
                             stories=brief.stories)

    with pytest.raises(ValueError):
        intent_from(ref, concept, mismatched_brief)


def test_relative_placement_falls_back_to_geometry_only_labels_when_entrance_is_unknown():
    """No FRONT/REAR is ever claimed when the reference's own entrance side is UNKNOWN."""
    for plan_id in _fixture_ids():
        ref = _load_reference(plan_id)
        if ref.entrance.side != UNKNOWN:
            continue
        concept, brief = _concept_and_brief_for(ref)
        intent = intent_from(ref, concept, brief)
        for placement in intent.relative_placement:
            assert placement.primary_axis in ("ABOVE", "BELOW", UNKNOWN)
            assert placement.secondary_axis in ("LEFT", "RIGHT", UNKNOWN)
        return
    pytest.skip("no fixture with entrance.side == UNKNOWN in this corpus")
