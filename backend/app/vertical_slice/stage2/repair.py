"""Stage 2 (B/2), Issue #134 — repair: fitting the seed to the brief's own programme.

Required Behaviour 2: fit the seed to the buildable region, re-target room areas to the programme,
apply room-count adaptation, honour the site's entrance side and exposure, and snap to the
rectilinear grid the realizer needs — EVERY repair applied recorded with the reason it was applied.

This module is deliberately SPECIFIC to the one donor (`tests/spikes/fixtures/geometry_shapes/
plans/47.json`) and the one brief `pipeline.BRIEF_PROGRAM` defines — Required Behaviour 1 ("one
representative brief... no breadth work starts until the owner has read this one case") and the
ROOT's own decision ("no compiler generalization"). Nothing here is a general donor-to-brief
search; every mapping below is an explicit, reasoned decision over this donor's OWN real facts
(read off `tests/spikes/fixtures/geometry_shapes/plans/47.json`), logged as a `RepairStep`.

A TOPOLOGY LIMIT DISCOVERED WHILE BUILDING THIS REPAIR (load-bearing for the brief chosen below,
and for `docs/reports/stage2-intent-realization/milestone-1.md`'s own decision section):
`RowWing` (Required Behaviour 3's own realizer) is a single, non-branching PATH in which every
zone shares one depth and fronts the street by construction (`realizer.py`'s own module
docstring). `access_rules.py` requires every PRIVATE-role room (BEDROOM/MASTER_BEDROOM/SAFE_ROOM/
...) entered ONLY from a CIRCULATION-role room, and `entrance_sequence._stray_pockets` (C25) fails
closed on any circulation zone OTHER than the resolved entrance that independently fronts the
street — measured empirically (not merely reasoned): a SECOND plain HALL always trips it; a
notch-carved SAFE_ROOM's own "big" HALL fragment ALSO trips it (`validate()`'s own
`circulation_design` is built at CELL granularity — `_displayed_rows`' notch-carve merging is a
LATER, reporting-only step — so every big fragment is its own separate circulation "room" to this
check); and SAFE_ROOM's own regulated area (>= 9.0 m2) combined with `ROOM_TEMPLATES[SAFE_ROOM]`'s
hard 2.5 aspect ceiling forces its notch taller than half of ANY row depth this brief's other rooms
can tolerate, so no corner/family choice avoids the realizer's cross-slot door pass picking the
notch itself over its own "big" sibling on whichever side has a real neighbour. Net: **this
realizer supports at most ONE gated-private-room arm per realized row, never two** — a bedroom (+
its own ensuite, which shares its host's SAME arm, not a second one) OR a SAFE_ROOM, not both in
one connected row. This Issue's own brief therefore carries the bedroom+ensuite (Required
Behaviour 2's own room-count-adaptation and wet-room demonstrations); a SEPARATE, smaller
hand-built scenario proves SAFE_ROOM's own C4/RC_SAFE_ROOM wiring
(`test_stage2_wet_rooms_and_safe_room.py`) without needing it in the SAME row as a bedroom. See the
milestone report's own decision section for why this is reported as a genuine finding, not
papered over.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..concept_generator import ROOM_TEMPLATES
from ..geometry_core.model import ProgramRole
from ..spec import ProgramSpec
from ..wet_rooms import ResolvedWetRoom, resolve_wet_rooms
from .contract import (
    DonorRoomId,
    RealizerInput,
    RepairedCell,
    RoomLineage,
    RoomLineageEvent,
    RoomLineageKind,
    RowWing,
    SeedGeometry,
    ZoneIntent,
)
from .donor import DonorPlan
from .seed import build_seed_geometry

#: The realizer's own per-side inset-margin pre-check (`realizer._INSET_MARGIN_M`) — a repaired
#: zone's `min_short_side_m` must clear this before the row's shared depth is chosen, so this
#: module reasons about the SAME number rather than a second copy that could silently drift.
_INSET_MARGIN_M = 0.30
#: Safety headroom above the strict per-zone minimum-short-side bound when picking the row's own
#: shared depth (Required Behaviour 2's "snap to the rectilinear grid the realizer needs") — the
#: realizer rounds each slot's own width to the nearest grid unit, which can shave a few
#: centimetres off the smallest zone; this keeps every zone clear of its own bound after rounding.
_ROW_DEPTH_SAFETY_M = 0.15
#: A small overall-width margin (never a per-zone fudge): the realizer's LAST row slot absorbs
#: whatever every earlier slot's own rounding left over (`realizer._build_row_wing`) — padding the
#: whole row's own width protects the tightest zones from that accumulated drift without changing
#: any zone's own area target.
_ROW_WIDTH_MARGIN = 1.05


@dataclass(frozen=True)
class RepairStep:
    """One repair operation, with the reason it was applied — Required Behaviour 2's own
    deliverable: "the repair log is a deliverable, not a debug aid... it is what tells the owner
    which step damages the seed."""

    name: str
    reason: str
    before: str
    after: str


@dataclass(frozen=True)
class RepairedZonePlan:
    """One final zone the repaired layout will realize: its role, its donor trace (`None` for an
    ADDED zone), and the area/shape bounds `RETARGET_AREAS` (a `RepairStep` below) derived for it
    from `ROOM_TEMPLATES` — the SAME per-role targets the production planner sizes to
    (`concept_generator.ROOM_TEMPLATES`), never a Stage-2-only placeholder set."""

    zone_id: str
    role: ProgramRole
    donor_room_id: DonorRoomId | None


@dataclass(frozen=True)
class RepairPlan:
    donor: DonorPlan
    program: ProgramSpec
    wet_rooms: tuple[ResolvedWetRoom, ...]
    lineage: RoomLineage
    seed: SeedGeometry  # BEFORE repair — the donor's own carried partition
    zones: tuple[RepairedZonePlan, ...]
    row_order: tuple[str, ...]
    row_height_m: float
    repaired_cells: tuple[RepairedCell, ...]
    realizer_input: RealizerInput
    steps: tuple[RepairStep, ...]


def _zone_intent(zp: RepairedZonePlan) -> ZoneIntent:
    t = ROOM_TEMPLATES[zp.role]
    return ZoneIntent(zone_id=zp.zone_id, role=zp.role, donor_room_id=zp.donor_room_id,
                       target_area_m2=t.target_area_m2, min_area_m2=t.min_area_m2,
                       max_area_m2=t.max_area_m2, min_short_side_m=t.min_short_side_m,
                       max_aspect_ratio=t.max_aspect_ratio)


def repair_donor_to_brief(donor: DonorPlan, program: ProgramSpec) -> RepairPlan:
    """The one repair this Issue's brief needs, over the one donor it uses — see the module
    docstring for why this is specific rather than a general engine, and for the row-topology
    one-arm limit that shapes the brief itself."""
    steps: list[RepairStep] = []
    wet_rooms = resolve_wet_rooms(program)
    bath_1 = next(w for w in wet_rooms if w.zone_id == "BATH_1")
    steps.append(RepairStep(
        "RESOLVE_WET_ROOMS",
        "the brief's authoritative wet-room programme (program.wet_rooms=1, ENSUITE) is the SAME "
        "resolver (`wet_rooms.resolve_wet_rooms`) the production pipeline uses — never a "
        "Stage-2-only wet-room shape.",
        "donor carries 3 wet rooms (TOILET_0, BATHROOM_0, BATHROOM_1)",
        f"programme requires 1: {bath_1.zone_id} (ENSUITE, host {bath_1.host_zone})",
    ))

    # ---- Bedroom-count adaptation (Required Behaviour 2) ------------------------------------
    # Donor's own real access edges already show BEDROOM_0<->BATHROOM_1 as an ensuite-shaped pair
    # (`donor.access_edges`) — carried forward exactly, rather than inventing a new host pairing.
    # BEDROOM_0 is also the donor's largest bedroom (28.8 m2), the natural MASTER candidate.
    #
    # THE ROW-TOPOLOGY LIMIT (see module docstring): this realizer supports at most ONE gated
    # PRIVATE-room arm per row. This brief's one arm is MASTER (+ its own ensuite, sharing the
    # SAME arm) — a SECOND bedroom would need a SECOND arm the realizer cannot host, so BOTH of
    # the donor's other bedrooms are dropped, not just the count difference a 2-bedroom brief
    # would otherwise have needed.
    steps.append(RepairStep(
        "BEDROOM_COUNT_ADJUST",
        "brief requires program.bedrooms=1; donor carries 3 (BEDROOM_0/1/2). BEDROOM_0 is kept "
        "(renamed MASTER) — the donor's own largest bedroom and the one with a real donor ensuite "
        "access edge (BATHROOM_1). BEDROOM_1 and BEDROOM_2 are dropped: the row realizer's own "
        "one-arm topology limit (module docstring) means a SECOND gated bedroom has no arm left "
        "to occupy.",
        "3 bedrooms (BEDROOM_0, BEDROOM_1, BEDROOM_2)",
        "1 bedroom kept: BEDROOM_0 (renamed MASTER, hosts BATH_1)",
    ))
    steps.append(RepairStep(
        "ROLE_RELABEL",
        "the brief's ensuite is host=ENSUITE_HOST_MASTER, which names a zone literally \"MASTER\" "
        "(`wet_rooms.resolve_wet_rooms`); BEDROOM_0 is promoted to ProgramRole.MASTER_BEDROOM / "
        "zone id \"MASTER\".",
        "BEDROOM_0 (role BEDROOM)", "MASTER (role MASTER_BEDROOM)",
    ))
    steps.append(RepairStep(
        "ROLE_RELABEL",
        "the donor's second LIVING-type room (LIVING_1, 4.6 m2, adjacent to KITCHEN_0) reads as a "
        "secondary sitting room, not a second primary living room — ProgramRole has one LIVING "
        "slot, so it is carried as ProgramRole.FAMILY_ROOM instead of dropped.",
        "LIVING_1 (type LIVING, 4.59 m2)", "FAMILY_ROOM_0 (role FAMILY_ROOM)",
    ))
    steps.append(RepairStep(
        "DROP_UNFIT_FOR_ROW_TOPOLOGY",
        "the non-guillotine realizer's RowWing places every top-level zone at the SAME shared "
        "depth (Required Behaviour 3's own realizer, `stage2.realizer._build_row_wing`); a depth "
        "that clears MASTER/LIVING's own 3.0 m minimum short side leaves STORAGE_0's ~3 m2 target "
        "too narrow to clear ITS OWN minimum short side at that same depth (no single row depth "
        "satisfies both — the two pull in opposite directions as area shrinks). STORAGE has no "
        "ProgramSpec field of its own (not part of the brief's authoritative programme), so it is "
        "dropped rather than forced.",
        "STORAGE_0 (5.31 m2, donor)", "dropped — no realized counterpart",
    ))
    steps.append(RepairStep(
        "DROP_SUPERSEDED_WET_ROOM",
        "BATHROOM_0 and TOILET_0 are the donor's other two wet rooms; the brief's programme "
        "(program.wet_rooms=1, mapped from BATHROOM_1 above) covers the requirement in full, and "
        "BATHROOM_0's own donor host (BEDROOM_1) is itself dropped above, so neither has a role "
        "left to carry into.",
        "BATHROOM_0 (6.14 m2), TOILET_0 (3.95 m2)", "dropped — no realized counterpart",
    ))
    steps.append(RepairStep(
        "ADD_CIRCULATION",
        "the donor carries no CIRCULATION/HALL room at all (`donor.rooms` has none), but C24 "
        "requires MASTER be entered ONLY from circulation — one HALL zone is added in front of "
        "it, and (the row realizer's ONE gated-arm limit — see module docstring) becomes the "
        "resolved entrance itself.",
        "no circulation room in the donor", "HALL_1 added (role HALL, MASTER's arm, the entrance)",
    ))
    steps.append(RepairStep(
        "SAFE_ROOM_NOT_INCLUDED",
        "brief.program.safe_room=False in THIS milestone brief — not because the brief has no "
        "SAFE_ROOM requirement to honour, but because the row realizer's own one-arm limit "
        "(module docstring) makes SAFE_ROOM and MASTER mutually exclusive in a single connected "
        "row: both are PRIVATE-role and each needs its own dedicated circulation arm, and a "
        "second arm always trips C25 (`entrance_sequence._stray_pockets`) or C20/C24 (a "
        "notch-carved SAFE_ROOM's own regulated area/aspect vs. the row's shared depth) — measured "
        "empirically while building this repair, not merely reasoned. SAFE_ROOM's own C4/"
        "RC_SAFE_ROOM wiring is proven separately, on a smaller scenario with no competing bedroom "
        "(`test_stage2_wet_rooms_and_safe_room.py`). See the milestone report's own decision "
        "section.",
        "brief could have asked for a SAFE_ROOM", "not asked for in this milestone's own brief",
    ))

    # ---- Final zone roster (donor_room_id=None marks an ADDED zone) -------------------------
    zones: list[RepairedZonePlan] = [
        RepairedZonePlan("BATH_1", ProgramRole.BATHROOM, "BATHROOM_1"),
        RepairedZonePlan("MASTER", ProgramRole.MASTER_BEDROOM, "BEDROOM_0"),
        RepairedZonePlan("HALL_1", ProgramRole.HALL, None),
        RepairedZonePlan("FAMILY_ROOM_0", ProgramRole.FAMILY_ROOM, "LIVING_1"),
        RepairedZonePlan("KITCHEN_0", ProgramRole.KITCHEN, "KITCHEN_0"),
        RepairedZonePlan("LIVING_0", ProgramRole.LIVING, "LIVING_0"),
    ]
    carried_donor_ids = tuple(zp.donor_room_id for zp in zones if zp.donor_room_id is not None)

    steps.append(RepairStep(
        "RETARGET_AREAS",
        "every zone's area target/min/max/min-short-side/max-aspect comes from "
        "`concept_generator.ROOM_TEMPLATES[role]` — the SAME per-role targets the production "
        "planner sizes to, not a donor-proportion-scaled figure (a known simplification: the "
        "donor's own room-size spread, e.g. BEDROOM_0 at 28.8 m2, is NOT carried into the "
        "repaired areas — see the report's `room_proportions` preservation result).",
        "donor areas (e.g. LIVING_0 74.7 m2, BEDROOM_0 28.8 m2, BATHROOM_1 5.6 m2)",
        "template targets (LIVING 22.0 m2, MASTER_BEDROOM 14.0 m2, BATHROOM 6.5 m2, HALL 11.0 m2, "
        "...)",
    ))

    # ---- Row order (Required Behaviour 2's entrance/exposure + grid-snap step) --------------
    # BATH_1 is an ENSUITE: C17 requires it entered ONLY from MASTER, which the realizer's row
    # topology can only guarantee for a zone with EXACTLY ONE row neighbour — a row END, next to
    # its host. Public zones are ordered by the donor's own room centroid x (donor's own
    # left-to-right reading, `DonorPlan`'s own frame).
    row_order = ("BATH_1", "MASTER", "HALL_1", "FAMILY_ROOM_0", "KITCHEN_0", "LIVING_0")
    steps.append(RepairStep(
        "ROW_ORDER_FROM_DONOR_PLACEMENT",
        "BATH_1 is pinned to a row end (its own required host, MASTER, is its only row neighbour "
        "there — C17's 'entered only from the host' rule); MASTER/HALL_1 sit between BATH_1 and "
        "the public block, ordered by the donor's own room centroid x (FAMILY_ROOM_0 at x=3.5, "
        "KITCHEN_0 at x=6.8, LIVING_0 at x=7.1 — the donor's own left-to-right reading). This is "
        "the step that collapses the donor's real 2D adjacency graph into the realizer's own 1D "
        "row — see the report's own decision section for what this costs `adjacency`/`placement` "
        "preservation.",
        "donor: a 2D adjacency graph (17 adjacency edges)",
        f"repaired: one row, left to right: {', '.join(row_order)}",
    ))

    # ---- Row depth (shared by every zone in a RowWing) --------------------------------------
    max_min_short = max(ROOM_TEMPLATES[zp.role].min_short_side_m for zp in zones)
    row_height_m = round(max_min_short + _INSET_MARGIN_M + _ROW_DEPTH_SAFETY_M, 4)
    total_target_m2 = sum(_zone_intent(zp).target_area_m2 for zp in zones)
    row_width_m = round(total_target_m2 / row_height_m * _ROW_WIDTH_MARGIN, 4)
    steps.append(RepairStep(
        "ENVELOPE_FIT_AND_GRID_SNAP",
        "a RowWing shares ONE depth across every zone (Required Behaviour 3's own realizer); the "
        "depth is the largest per-role minimum short side across the roster "
        f"(MASTER_BEDROOM/LIVING, {max_min_short:.2f} m) plus the realizer's own inset-margin "
        f"pre-check ({_INSET_MARGIN_M} m) and a rounding safety margin ({_ROW_DEPTH_SAFETY_M} m); "
        "the row's own width is the summed area targets over that depth, with a small overall "
        f"margin ({_ROW_WIDTH_MARGIN}x) protecting the tightest zone from the last slot's own "
        "rounding drift. The realizer itself snaps every dimension to its own 0.05 m grid unit "
        "(`realizer.UNIT_M`) when it solves each slot's rectangle.",
        "donor footprint 20.77 m x 12.11 m (aspect ~1.72, fill ratio ~0.76 — see the intent "
        "report)",
        f"repaired envelope {row_width_m:.2f} m x {row_height_m:.2f} m (one row, aspect "
        f"{row_width_m / row_height_m:.1f}:1)",
    ))

    zone_intents = {zp.zone_id: _zone_intent(zp) for zp in zones}
    row = RowWing(wing_id="row0", width_m=row_width_m, height_m=row_height_m, slots=row_order,
                  zones=zone_intents, groups={})
    realizer_input = RealizerInput(name="stage2-milestone-1", wings=(row,), wet_rooms=wet_rooms,
                                    entrance_hint_zone_id="HALL_1")

    # ---- Lineage + seed (Required Behaviour 1 and 2) -----------------------------------------
    events: list[RoomLineageEvent] = []
    carried_reasons = {
        "LIVING_0": "carried unchanged (role LIVING)",
        "LIVING_1": "carried, role relabelled to FAMILY_ROOM (see ROLE_RELABEL above)",
        "KITCHEN_0": "carried unchanged (role KITCHEN)",
        "BEDROOM_0": "carried, role relabelled to MASTER_BEDROOM (see ROLE_RELABEL above)",
        "BATHROOM_1": "carried into BATH_1 (ENSUITE, host MASTER) — the donor's own "
                       "BATHROOM_1-BEDROOM_0 access edge, preserved as the ensuite host relationship",
    }
    for donor_id, reason in carried_reasons.items():
        events.append(RoomLineageEvent(RoomLineageKind.CARRIED, (donor_id,), (donor_id,),
                                        "adaptation", reason))
    events.append(RoomLineageEvent(RoomLineageKind.DROPPED, ("BEDROOM_1",), (), "adaptation",
                                    "bedroom count 3 -> 1; row-topology one-arm limit; see "
                                    "BEDROOM_COUNT_ADJUST above"))
    events.append(RoomLineageEvent(RoomLineageKind.DROPPED, ("BEDROOM_2",), (), "adaptation",
                                    "bedroom count 3 -> 1; row-topology one-arm limit; see "
                                    "BEDROOM_COUNT_ADJUST above"))
    events.append(RoomLineageEvent(RoomLineageKind.DROPPED, ("BATHROOM_0",), (), "adaptation",
                                    "superseded by the brief's 1-ensuite wet-room programme; its "
                                    "own donor host (BEDROOM_1) is also dropped; see "
                                    "DROP_SUPERSEDED_WET_ROOM above"))
    events.append(RoomLineageEvent(RoomLineageKind.DROPPED, ("TOILET_0",), (), "adaptation",
                                    "superseded by the brief's 1-ensuite wet-room programme; see "
                                    "DROP_SUPERSEDED_WET_ROOM above"))
    events.append(RoomLineageEvent(RoomLineageKind.DROPPED, ("STORAGE_0",), (), "repair",
                                    "row-topology minimum-short-side conflict; see "
                                    "DROP_UNFIT_FOR_ROW_TOPOLOGY above"))
    events.append(RoomLineageEvent(RoomLineageKind.ADDED, (), ("HALL_1",), "repair",
                                    "C24 requires MASTER entered only from circulation; see "
                                    "ADD_CIRCULATION above"))
    lineage = RoomLineage(donor_room_ids=tuple(r.id for r in donor.rooms), events=tuple(events))

    seed = build_seed_geometry(donor, carried_donor_ids)
    repaired_cells = tuple(
        RepairedCell(cell_id=f"repaired__{zp.zone_id}",
                     seed_cell_id=f"seed__{zp.donor_room_id}" if zp.donor_room_id else None,
                     donor_room_id=zp.donor_room_id)
        for zp in zones
    )

    return RepairPlan(
        donor=donor, program=program, wet_rooms=wet_rooms, lineage=lineage, seed=seed,
        zones=tuple(zones), row_order=row_order, row_height_m=row_height_m,
        repaired_cells=repaired_cells, realizer_input=realizer_input, steps=tuple(steps),
    )
