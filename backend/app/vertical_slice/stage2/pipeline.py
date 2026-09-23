"""Stage 2 (B/2), Issue #134 — the one end-to-end run: donor -> intent -> seed -> repair ->
non-guillotine geometry -> validators -> preservation report.

`run_milestone_1()` is the single documented command AC-1 asks for — reproducible with no
arguments, always the same donor (`tests/spikes/fixtures/geometry_shapes/plans/47.json`) and the
same brief (`BRIEF_PROGRAM` below). `STAGE2_END_TO_END_ENABLED` gates nothing: no existing caller
(`app.demo.*`, `app.vertical_slice.pipeline`, `app.vertical_slice.general_pipeline`) imports
`app.vertical_slice.stage2` at all, so the frozen 432-context regression corpus is unaffected by
construction (AC-6) regardless of this flag's value.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from ..constraints import derive_safe_room_constraint
from ..geometry_core.model import Rect, m_to_u
from ..spec import PlotSpec, ProgramSpec, WetRoomRequirement
from ..spec import ENSUITE_HOST_MASTER, WetRoomKind
from .contract import RealizerRefusal, RoomIdentityChain, verify_chain_completeness
from .donor import DonorPlan, load_donor_plan
from .intent import build_realization_intent
from .preservation import PreservationReport, measure_preservation
from .realizer import RealizedLayout, realize_layout
from .repair import RepairPlan, repair_donor_to_brief

#: Off by default — the same disclosure/kill-switch precedent as `STAGE2_CONTRACT_ENABLED`/
#: `STAGE2_REALIZER_ENABLED`. Nothing in `app/` outside `app.vertical_slice.stage2` imports this
#: package, so the value of this flag changes no production behaviour either way (AC-6).
STAGE2_END_TO_END_ENABLED = False

_HERE = os.path.dirname(__file__)
DONOR_PLAN_PATH = os.path.normpath(os.path.join(
    _HERE, "..", "..", "..", "tests", "spikes", "fixtures", "geometry_shapes", "plans", "47.json"))

#: The ONE representative brief (Required Behaviour 1) — distinct from the POC's own three
#: benchmark briefs (Issues #109/#110/#111), which this Issue is explicitly not to run. 1 bedroom
#: (exercises BEDROOM_COUNT_ADJUST against the donor's own 3) with 1 ENSUITE wet room mapped onto
#: the donor's own real ensuite-shaped access edge (see `repair.py`'s own reasoning).
#:
#: safe_room=False is itself a repair-driven finding, not an arbitrary omission:
#: `repair.py`'s own module docstring documents a row-topology limit discovered EMPIRICALLY while
#: building this repair — the realizer's `RowWing` supports at most ONE gated-PRIVATE-room arm per
#: connected row (a bedroom, its own ensuite sharing that SAME arm) — never two, so a SAFE_ROOM
#: cannot be added alongside a bedroom here. `test_stage2_wet_rooms_and_safe_room.py` proves
#: SAFE_ROOM's own C4/RC_SAFE_ROOM wiring on a smaller scenario with no competing bedroom. See the
#: milestone report's own decision section for the full finding.
BRIEF_PROGRAM = ProgramSpec(
    bedrooms=1,
    safe_room=False,
    wet_rooms=1,
    wet_room_kinds=(
        WetRoomRequirement(WetRoomKind.ENSUITE, host=ENSUITE_HOST_MASTER),
    ),
)

#: Comfortably larger than the repaired row envelope — sized so Required Behaviour 2's "fit the
#: seed to the buildable region" step is a real, passing check, not a formality; see the report's
#: own envelope numbers for exactly how much margin this leaves.
BRIEF_PLOT = PlotSpec(width_m=40.0, depth_m=8.0, front_setback_m=1.5, side_setback_m=2.0,
                       rear_setback_m=1.5)


@dataclass(frozen=True)
class Stage2Run:
    donor: DonorPlan
    intent: object
    repair: RepairPlan
    realized: RealizedLayout | None
    refusal: RealizerRefusal | None
    chain: RoomIdentityChain | None
    chain_problems: tuple[str, ...]
    preservation: PreservationReport | None

    @property
    def ok(self) -> bool:
        return self.realized is not None


def run_milestone_1(donor_path: str = DONOR_PLAN_PATH, program: ProgramSpec = BRIEF_PROGRAM,
                     plot: PlotSpec = BRIEF_PLOT) -> Stage2Run:
    """The single documented command AC-1 asks for. Every step's output is on the returned
    `Stage2Run` — nothing is hidden inside a log line."""
    donor = load_donor_plan(donor_path)
    intent = build_realization_intent(donor, concept_id=f"stage2-milestone-1:{donor.plan_id}")
    plan = repair_donor_to_brief(donor, program)

    buildable_w, buildable_h = plot.buildable_size_m()
    buildable = Rect(0, 0, m_to_u(buildable_w), m_to_u(buildable_h))
    safe_room_constraint = derive_safe_room_constraint(program.safe_room)

    result = realize_layout(plan.realizer_input, buildable=buildable,
                             safe_room_constraint=safe_room_constraint)

    if isinstance(result, RealizerRefusal):
        return Stage2Run(donor=donor, intent=intent, repair=plan, realized=None, refusal=result,
                          chain=None, chain_problems=(), preservation=None)

    from .contract import RealizedZone
    # HALL_1 is realized as a notch-carve GROUP (Required Behaviour 3's `ShapeGroupIntent`): its
    # own zone_id never appears in `result.rects` (only its sub-cells, e.g. "HALL_1__c0", do) — it
    # appears in `result.groups` instead (see `realizer._displayed_rows`/`groups_out`, keyed by
    # the group's own `big.zone_id`). Every other zone is an ordinary row slot, keyed directly.
    realized_zones = tuple(
        RealizedZone(zone_id=zp.zone_id, repaired_cell_ids=(f"repaired__{zp.zone_id}",),
                     donor_room_ids=(zp.donor_room_id,) if zp.donor_room_id else ())
        for zp in plan.zones
        if zp.zone_id in result.rects or zp.zone_id in result.groups
    )
    chain = RoomIdentityChain(lineage=plan.lineage, intent=intent, seed=plan.seed,
                               repaired_cells=plan.repaired_cells, realized_zones=realized_zones)
    chain_problems = verify_chain_completeness(chain)
    preservation = measure_preservation(intent, result, chain)

    return Stage2Run(donor=donor, intent=intent, repair=plan, realized=result, refusal=None,
                      chain=chain, chain_problems=chain_problems, preservation=preservation)
