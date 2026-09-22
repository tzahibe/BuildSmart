"""Verifies Issue #95 AC-3: adaptation records >= 1 semantic operation per adapted concept,
changes room-area ratios non-uniformly (no global scaling), and rejects an unadaptable reference
with a reason on a synthetic case.
"""
from __future__ import annotations

from tests.architectural_brain.benchmark_briefs import BENCHMARK_BRIEFS, BENCHMARK_SITE, load_fixture_corpus

from spikes.architectural_brain.adaptation import AdaptedConcept, Rejection, adapt, room_area_ratios
from spikes.architectural_brain.brief import Brief
from spikes.architectural_brain.plan_reference import Room
from spikes.architectural_brain.retrieval import retrieve
from spikes.architectural_brain.synthesis import ConceptSpec, synthesize

from app.vertical_slice.spec import PlotSpec, ProgramSpec, WetRoomKind, WetRoomRequirement


def test_every_adapted_concept_records_at_least_one_semantic_operation():
    corpus = load_fixture_corpus()
    for brief in BENCHMARK_BRIEFS:
        references = retrieve(brief, BENCHMARK_SITE, corpus, k=8)
        for concept in synthesize(brief, references):
            result = adapt(concept, brief, BENCHMARK_SITE)
            assert isinstance(result, (AdaptedConcept, Rejection))
            if isinstance(result, AdaptedConcept):
                assert len(result.adaptations) >= 1
                for a in result.adaptations:
                    assert a.kind and a.before and a.after and a.reason


def test_room_area_ratios_change_non_uniformly_no_global_scaling():
    corpus = load_fixture_corpus()
    brief = BENCHMARK_BRIEFS[0]
    references = retrieve(brief, BENCHMARK_SITE, corpus, k=8)
    candidates = synthesize(brief, references)

    concept = result = None
    for c in candidates:
        r = adapt(c, brief, BENCHMARK_SITE)
        if isinstance(r, AdaptedConcept):
            concept, result = c, r
            break
    assert result is not None, "expected at least one candidate to adapt successfully, not reject"

    ratios = room_area_ratios(result, concept)
    assert len(ratios) >= 2, "need at least 2 room types present in both baseline and adapted"
    distinct_ratios = {round(r, 6) for r in ratios.values()}
    assert len(distinct_ratios) > 1, (
        f"all room-type ratios are equal ({ratios}) -- this is a global scale, not a semantic "
        f"per-room adaptation"
    )


def _minimal_concept(circulation_class: str, zoning: str, wet_core_strategy: str,
                     baseline_rooms: tuple[Room, ...], wet_room_kinds: tuple[str, ...] = (),
                     bedrooms: int = 3, wet_rooms: int = 2, safe_room: bool = True) -> ConceptSpec:
    return ConceptSpec(
        concept_id="synthetic-test-concept",
        circulation_class=circulation_class,
        zoning=zoning,
        wet_core_strategy=wet_core_strategy,
        entrance_relationship="TO_LIVING",
        bedroom_grouping_share=1.0,
        references=(),
        bedrooms=bedrooms,
        safe_room=safe_room,
        wet_rooms=wet_rooms,
        wet_room_kinds=wet_room_kinds,
        stories=1,
        baseline_rooms=baseline_rooms,
    )


def _one_room(room_id: str, room_type: str, area: float) -> Room:
    return Room(
        id=room_id, type=room_type,
        polygon=((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
        area_m2=area, width_m=1.0, depth_m=1.0,
        exterior_exposure=(), exposure_known=False,
    )


def test_rejects_when_the_site_has_no_room_for_the_brief_authoritative_rooms():
    """Synthetic case: a brief demanding 5 bedrooms + a safe room, on a tiny site whose buildable
    area after setbacks cannot possibly fit them -- adapt() must reject with a stated reason
    rather than silently returning an infeasible plan."""
    concept = _minimal_concept(
        circulation_class="FRONT_BAND", zoning="PUBLIC_FRONT_PRIVATE_REAR", wet_core_strategy="DISPERSED",
        baseline_rooms=(_one_room("LIVING_0", "LIVING", 20.0), _one_room("BEDROOM_0", "BEDROOM", 12.0)),
        bedrooms=5, wet_rooms=3, safe_room=True,
    )
    brief = Brief(program=ProgramSpec(bedrooms=5, safe_room=True, wet_rooms=3))
    tiny_site = PlotSpec(width_m=6.0, depth_m=6.0, front_setback_m=2.0, side_setback_m=1.5, rear_setback_m=2.0)

    result = adapt(concept, brief, tiny_site)
    assert isinstance(result, Rejection)
    assert result.concept_id == "synthetic-test-concept"
    assert "insufficient buildable area" in result.reason


def test_rejects_when_the_wet_core_is_unreachable_for_an_ensuite_request():
    """Synthetic case: brief requires an ensuite, but the donor concept has zero measured wet
    rooms (wet_core_strategy=UNKNOWN) -- there is no placement to adapt an ensuite relationship
    from, so adapt() must reject with a stated reason."""
    concept = _minimal_concept(
        circulation_class="OTHER", zoning="PUBLIC_PRIVATE_WINGS", wet_core_strategy="UNKNOWN",
        baseline_rooms=(_one_room("LIVING_0", "LIVING", 20.0), _one_room("BEDROOM_0", "BEDROOM", 12.0)),
    )
    brief = Brief(program=ProgramSpec(
        bedrooms=3, safe_room=True, wet_rooms=2,
        wet_room_kinds=(WetRoomRequirement(kind=WetRoomKind.ENSUITE, host="MASTER_BEDROOM"),),
    ))
    generous_site = PlotSpec(width_m=30.0, depth_m=30.0)

    result = adapt(concept, brief, generous_site)
    assert isinstance(result, Rejection)
    assert "wet core unreachable" in result.reason
