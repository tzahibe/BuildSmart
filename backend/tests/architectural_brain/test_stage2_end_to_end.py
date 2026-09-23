"""Issue #134 — Stage 2 (B/2) AC-1: one representative brief, carried the whole way.

`stage2.pipeline.run_milestone_1()` is the single documented command: donor -> intent -> seed ->
repair -> non-guillotine geometry -> validators -> preservation report, reproducibly, with no
arguments (the donor path and brief are both fixed module constants).
"""
from __future__ import annotations

from app.vertical_slice.stage2 import pipeline
from app.vertical_slice.stage2.contract import RealizedZone, RealizerRefusal


def test_run_milestone_1_is_reproducible_with_no_arguments():
    run_a = pipeline.run_milestone_1()
    run_b = pipeline.run_milestone_1()
    assert run_a.ok and run_b.ok
    assert set(run_a.realized.rects) == set(run_b.realized.rects)
    assert run_a.realized.report.ok and run_b.realized.report.ok


def test_pipeline_produces_every_stage_donor_through_preservation():
    run = pipeline.run_milestone_1()
    assert run.ok, run.refusal
    # donor
    assert run.donor.plan_id == "47"
    assert len(run.donor.rooms) == 10
    # intent — one RoomProportion per donor room, unconditionally (Required Behaviour 1)
    assert len(run.intent.room_proportions) == len(run.donor.rooms)
    # seed — the donor's own carried partition, BEFORE repair
    assert run.repair.seed.frame == "DONOR_PLAN_IMAGE_FRAME_METERS"
    assert set(run.repair.seed.donor_room_ids()) == {"BEDROOM_0", "LIVING_0", "LIVING_1",
                                                       "KITCHEN_0", "BATHROOM_1"}
    # repair — every step is logged with a reason (Required Behaviour 2)
    assert len(run.repair.steps) >= 5
    assert all(step.reason for step in run.repair.steps)
    # non-guillotine geometry — realized through stage2.realizer, never the guillotine engine
    assert run.realized is not None
    assert run.refusal is None
    # validators — the SAME chain, real checks ran
    check_ids = {c.check_id for c in run.realized.report.checks}
    assert {"C17", "C29", "C5", "C13", "C24"}.issubset(check_ids)
    assert run.realized.report.ok
    # room identity chain — every donor room accounted for (Required Behaviour 1/6)
    assert run.chain_problems == ()
    for zone in run.chain.realized_zones:
        assert isinstance(zone, RealizedZone)
    # preservation report — every fact class measured
    fact_class_names = {f.fact_class for f in run.preservation.fact_classes}
    assert {"adjacency", "access", "placement", "room_proportions",
            "footprint_relationships"}.issubset(fact_class_names)


def test_realizer_refusal_type_is_the_contract_type_not_a_local_one():
    """`Stage2Run.refusal`, when set, must be `stage2.contract.RealizerRefusal` — the sealed
    Stage 2 refusal contract (Issue #133), never a `stage2.realizer`-local stand-in."""
    run = pipeline.run_milestone_1()
    if run.refusal is not None:
        assert isinstance(run.refusal, RealizerRefusal)
