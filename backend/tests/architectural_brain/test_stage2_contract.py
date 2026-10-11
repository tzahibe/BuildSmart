"""Issue #133 — Stage 2 (A/2): the shared contract every later Stage 2 child implements.

AC-1: the contract module defines the six required type groups.
AC-2: the full chain (donor room id -> intent fact -> seed cell -> repaired cell -> realized zone)
builds for one REAL retrieved plan (a genuine ResPlan fixture, CC BY 4.0, already used by the
non-rectangular geometry investigation's own corpus — `tests/spikes/fixtures/geometry_shapes/
plans/47.json`), and every donor room the brief contains is reachable at every link, with
dropped/added/merged/split rooms explicitly classified rather than missing.
"""
from __future__ import annotations

import json
import os

import pytest

from app.vertical_slice.stage2 import contract as c

_FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "spikes", "fixtures", "geometry_shapes", "plans", "47.json")


def _load_donor_plan() -> dict:
    with open(_FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)["plan_reference"]


# --------------------------------------------------------------------------------- AC-1: the types

def test_donor_room_identity_types_exist():
    assert c.DonorRoomId is str
    event = c.RoomLineageEvent(
        kind=c.RoomLineageKind.CARRIED, donor_room_ids=("LIVING_0",), result_ids=("LIVING_0",),
        stage="seeding", reason="unchanged")
    lineage = c.RoomLineage(donor_room_ids=("LIVING_0",), events=(event,))
    assert lineage.unaccounted_donor_ids() == ()


def test_seed_geometry_type_exists():
    cell = c.SeedCell(cell_id="seed__LIVING_0", donor_room_id="LIVING_0",
                      polygon_m=((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)))
    seed = c.SeedGeometry(source_plan_id="47", frame=c.DONOR_PLAN_FRAME, cells=(cell,), adjacency=())
    assert seed.donor_room_ids() == ("LIVING_0",)


def test_realization_intent_type_matches_poc_109_shape():
    proportion = c.RoomProportion(room_id="LIVING_0", room_type="LIVING", aspect_ratio=1.2,
                                  area_share_of_type=1.0)
    intent = c.RealizationIntent(
        schema_version="1.0", source_plan_id="47", concept_id="concept-1",
        adjacency_edges=(), access_edges=(), exterior_exposure=(), relative_placement=(),
        public_private_clusters=c.Clusters(public=("LIVING_0",), private=()),
        circulation_nodes=(), wet_core_groups=(), room_proportions=(proportion,),
        entrance_relationship=c.EntranceRelationship(room_id="LIVING_0", side="W"),
        footprint_relationships=c.FootprintRelationships(10.0, 8.0, 1.25, 0.9))
    assert intent.donor_room_ids() == ("LIVING_0",)


def test_realizer_input_and_refusal_types_exist():
    zone = c.ZoneIntent(zone_id="LIVING", role=c.ProgramRole.LIVING, donor_room_id="LIVING_0",
                        target_area_m2=24.0, min_area_m2=14.0, max_area_m2=30.0)
    row = c.RowWing(wing_id="w0", width_m=5.0, height_m=5.0, slots=("LIVING",),
                    zones={"LIVING": zone}, groups={})
    layout = c.RealizerInput(name="test", wings=(row,), wet_rooms=())
    assert layout.zone_ids() == ("LIVING",)
    assert c.validate_realizer_input(layout) == ()

    refusal = c.RealizerRefusal(reason="AREA_INFEASIBLE", detail="no room for it")
    assert refusal.reason == "AREA_INFEASIBLE"
    with pytest.raises(ValueError):
        c.RealizerRefusal(reason="")


def test_wet_room_and_safe_room_vocabulary_is_referenced_not_redefined():
    # THIS module does not redefine ResolvedWetRoom or ProgramRole — it references the same types
    # `wet_rooms.py`/`geometry_core.model` already own, so a realizer input can carry the real
    # authoritative wet-room roster end to end.
    from app.vertical_slice.geometry_core.model import ProgramRole as ProdProgramRole
    from app.vertical_slice.wet_rooms import ResolvedWetRoom as ProdResolvedWetRoom

    assert c.ProgramRole is ProdProgramRole
    assert c.ResolvedWetRoom is ProdResolvedWetRoom


def test_room_identity_chain_types_exist():
    repaired = c.RepairedCell(cell_id="repaired__LIVING_0", seed_cell_id="seed__LIVING_0",
                              donor_room_id="LIVING_0")
    zone = c.RealizedZone(zone_id="LIVING_0", repaired_cell_ids=("repaired__LIVING_0",),
                          donor_room_ids=("LIVING_0",))
    assert repaired.donor_room_id == "LIVING_0"
    assert zone.donor_room_ids == ("LIVING_0",)


# ---------------------------------------------------------------- AC-2: the full chain, real plan

def _build_chain_for_47() -> c.RoomIdentityChain:
    ref = _load_donor_plan()
    rooms = ref["rooms"]
    room_ids = [r["id"] for r in rooms]
    assert set(room_ids) == {
        "LIVING_0", "LIVING_1", "KITCHEN_0", "BEDROOM_0", "BEDROOM_1", "BEDROOM_2",
        "TOILET_0", "BATHROOM_0", "BATHROOM_1", "STORAGE_0",
    }, "fixture 47.json's own room roster changed — update this test's scenario"

    # --- RealizationIntent: one RoomProportion per donor room, unconditionally (mirrors POC #109's
    # own `_room_proportions`, which reads every `reference.rooms` regardless of what adaptation
    # later does to them).
    proportions = tuple(
        c.RoomProportion(room_id=r["id"], room_type=r["type"], aspect_ratio=None,
                         area_share_of_type=1.0)
        for r in rooms
    )
    intent = c.RealizationIntent(
        schema_version="1.0", source_plan_id=ref["plan_id"], concept_id="47-concept",
        adjacency_edges=tuple(c.AdjacencyFact(e["room_a"], e["room_b"])
                              for e in ref["adjacency_edges"]),
        access_edges=(), exterior_exposure=(), relative_placement=(),
        public_private_clusters=c.Clusters(public=(), private=()),
        circulation_nodes=(), wet_core_groups=(), room_proportions=proportions,
        entrance_relationship=c.EntranceRelationship(
            room_id=ref["entrance"]["room_id"], side=ref["entrance"]["side"]),
        footprint_relationships=c.FootprintRelationships(10.0, 8.0, 1.25, 0.9),
    )

    # --- SeedGeometry: every donor room EXCEPT the one adaptation drops (STORAGE_0 — dropped at the
    # "adaptation" stage, which precedes "seeding"; a dropped room never reaches a seed cell at all).
    seed_cells = tuple(
        c.SeedCell(cell_id=f"seed__{r['id']}", donor_room_id=r["id"],
                  polygon_m=tuple(tuple(p) for p in r["polygon"]))
        for r in rooms if r["id"] != "STORAGE_0"
    )
    seed = c.SeedGeometry(source_plan_id=str(ref["plan_id"]), frame=c.DONOR_PLAN_FRAME,
                          cells=seed_cells, adjacency=())

    # --- Repaired cells: CARRIED rooms 1:1; the two bathrooms MERGE into one wet core's own two
    # cells; BEDROOM_2 SPLITs into a bedroom + a closet cell; a brand-new SAFE_ROOM is ADDED with no
    # seed cell at all (the donor plan has none).
    carried_ids = ("LIVING_0", "LIVING_1", "KITCHEN_0", "BEDROOM_0", "BEDROOM_1", "TOILET_0")
    repaired_cells = [
        c.RepairedCell(cell_id=f"repaired__{rid}", seed_cell_id=f"seed__{rid}", donor_room_id=rid)
        for rid in carried_ids
    ]
    repaired_cells += [
        c.RepairedCell(cell_id="repaired__BATHROOM_0", seed_cell_id="seed__BATHROOM_0",
                       donor_room_id="BATHROOM_0"),
        c.RepairedCell(cell_id="repaired__BATHROOM_1", seed_cell_id="seed__BATHROOM_1",
                       donor_room_id="BATHROOM_1"),
        c.RepairedCell(cell_id="repaired__BEDROOM_2_main", seed_cell_id="seed__BEDROOM_2",
                       donor_room_id="BEDROOM_2"),
        c.RepairedCell(cell_id="repaired__BEDROOM_2_closet", seed_cell_id="seed__BEDROOM_2",
                       donor_room_id="BEDROOM_2"),
        c.RepairedCell(cell_id="repaired__SAFE_ROOM", seed_cell_id=None, donor_room_id=None),
    ]

    # --- Realized zones: CARRIED rooms 1:1; BATHROOM_0+BATHROOM_1 -> one WET_CORE zone; BEDROOM_2's
    # two repaired cells -> two separate realized zones; SAFE_ROOM has no donor room at all.
    realized_zones = [
        c.RealizedZone(zone_id=rid, repaired_cell_ids=(f"repaired__{rid}",), donor_room_ids=(rid,))
        for rid in carried_ids
    ]
    realized_zones += [
        c.RealizedZone(zone_id="WET_CORE", repaired_cell_ids=("repaired__BATHROOM_0",
                                                               "repaired__BATHROOM_1"),
                       donor_room_ids=("BATHROOM_0", "BATHROOM_1")),
        c.RealizedZone(zone_id="BEDROOM_2", repaired_cell_ids=("repaired__BEDROOM_2_main",),
                       donor_room_ids=("BEDROOM_2",)),
        c.RealizedZone(zone_id="BEDROOM_2_CLOSET", repaired_cell_ids=("repaired__BEDROOM_2_closet",),
                       donor_room_ids=("BEDROOM_2",)),
        c.RealizedZone(zone_id="SAFE_ROOM", repaired_cell_ids=("repaired__SAFE_ROOM",),
                       donor_room_ids=()),
    ]

    # --- Lineage: every one of the 10 donor rooms named in exactly one classifying event.
    events = (
        c.RoomLineageEvent(kind=c.RoomLineageKind.CARRIED, donor_room_ids=carried_ids,
                           result_ids=carried_ids, stage="seeding",
                           reason="unchanged donor partition, no adaptation"),
        c.RoomLineageEvent(kind=c.RoomLineageKind.MERGED,
                           donor_room_ids=("BATHROOM_0", "BATHROOM_1"),
                           result_ids=("repaired__BATHROOM_0", "repaired__BATHROOM_1"),
                           stage="repair",
                           reason="two small bathrooms combined into one shared wet core"),
        c.RoomLineageEvent(kind=c.RoomLineageKind.SPLIT, donor_room_ids=("BEDROOM_2",),
                           result_ids=("repaired__BEDROOM_2_main", "repaired__BEDROOM_2_closet"),
                           stage="repair", reason="bedroom split into a bedroom and a closet cell"),
        c.RoomLineageEvent(kind=c.RoomLineageKind.DROPPED, donor_room_ids=("STORAGE_0",),
                           result_ids=(), stage="adaptation",
                           reason="brief's programme has no STORAGE room type"),
        c.RoomLineageEvent(kind=c.RoomLineageKind.ADDED, donor_room_ids=(),
                           result_ids=("repaired__SAFE_ROOM",), stage="adaptation",
                           reason="brief requires SAFE_ROOM; donor plan has none"),
    )
    lineage = c.RoomLineage(donor_room_ids=tuple(room_ids), events=events)

    return c.RoomIdentityChain(lineage=lineage, intent=intent, seed=seed,
                               repaired_cells=tuple(repaired_cells),
                               realized_zones=tuple(realized_zones))


def test_chain_is_complete_for_a_real_retrieved_plan():
    chain = _build_chain_for_47()

    assert chain.lineage.unaccounted_donor_ids() == (), (
        "every donor room from the real retrieved plan must be named by some lineage event")
    assert c.verify_chain_completeness(chain) == ()


def test_carried_rooms_are_fully_reachable_at_every_link():
    chain = _build_chain_for_47()
    trace = c.trace_donor_room(chain, "LIVING_0")
    assert trace.has_intent_fact
    assert trace.fully_reachable
    assert trace.lineage_kinds == (c.RoomLineageKind.CARRIED,)


def test_merged_rooms_each_remain_individually_traceable():
    chain = _build_chain_for_47()
    for donor_id in ("BATHROOM_0", "BATHROOM_1"):
        trace = c.trace_donor_room(chain, donor_id)
        assert trace.fully_reachable
        assert trace.realized_zone_ids == ("WET_CORE",)
        assert c.RoomLineageKind.MERGED in trace.lineage_kinds


def test_split_room_reaches_two_realized_zones():
    chain = _build_chain_for_47()
    trace = c.trace_donor_room(chain, "BEDROOM_2")
    assert trace.fully_reachable
    assert set(trace.realized_zone_ids) == {"BEDROOM_2", "BEDROOM_2_CLOSET"}
    assert c.RoomLineageKind.SPLIT in trace.lineage_kinds


def test_dropped_room_is_explicitly_classified_not_missing():
    chain = _build_chain_for_47()
    trace = c.trace_donor_room(chain, "STORAGE_0")
    assert trace.has_intent_fact, "the intent still states the fact — only realization drops it"
    assert not trace.fully_reachable
    assert trace.seed_cell_ids == ()
    assert trace.repaired_cell_ids == ()
    assert trace.realized_zone_ids == ()
    assert trace.lineage_kinds == (c.RoomLineageKind.DROPPED,)


def test_added_room_has_no_donor_counterpart_but_is_realized():
    chain = _build_chain_for_47()
    safe_room = next(z for z in chain.realized_zones if z.zone_id == "SAFE_ROOM")
    assert safe_room.donor_room_ids == ()
    safe_repaired = next(rc for rc in chain.repaired_cells if rc.cell_id == "repaired__SAFE_ROOM")
    assert safe_repaired.seed_cell_id is None
    assert safe_repaired.donor_room_id is None


def test_an_unclassified_missing_room_is_caught_not_silently_accepted():
    """The invariant is not vacuous: removing the DROPPED event (as if a future stage forgot to
    record it) must make both `unaccounted_donor_ids` and `verify_chain_completeness` non-empty."""
    chain = _build_chain_for_47()
    broken_events = tuple(e for e in chain.lineage.events if e.kind != c.RoomLineageKind.DROPPED)
    broken_lineage = c.RoomLineage(donor_room_ids=chain.lineage.donor_room_ids, events=broken_events)
    broken_chain = c.RoomIdentityChain(lineage=broken_lineage, intent=chain.intent, seed=chain.seed,
                                       repaired_cells=chain.repaired_cells,
                                       realized_zones=chain.realized_zones)

    assert broken_lineage.unaccounted_donor_ids() == ("STORAGE_0",)
    problems = c.verify_chain_completeness(broken_chain)
    assert len(problems) == 1
    assert "STORAGE_0" in problems[0]


# ------------------------------------------------------------------- lineage event validation

@pytest.mark.parametrize("kwargs, match", [
    (dict(kind=c.RoomLineageKind.ADDED, donor_room_ids=("X",), result_ids=("Y",), stage="repair",
         reason="r"), "ADDED must not name a donor_room_id"),
    (dict(kind=c.RoomLineageKind.DROPPED, donor_room_ids=("X",), result_ids=("Y",), stage="repair",
         reason="r"), "DROPPED must not name a result_id"),
    (dict(kind=c.RoomLineageKind.CARRIED, donor_room_ids=("X",), result_ids=("Y",), stage="repair",
         reason="r"), "CARRIED must name the SAME id"),
    (dict(kind=c.RoomLineageKind.MERGED, donor_room_ids=("X",), result_ids=("Y",), stage="lunch",
         reason="r"), "not one of"),
])
def test_room_lineage_event_rejects_inconsistent_classification(kwargs, match):
    with pytest.raises(ValueError, match=match):
        c.RoomLineageEvent(**kwargs)
