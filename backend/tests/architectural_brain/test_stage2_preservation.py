"""Issue #134 — Stage 2 (B/2) AC-4: no lost fact carries GUILLOTINE_IMPOSSIBLE, and no lost fact
carries DONOR_ROOM_NOT_REALIZED for a donor room the brief still contains.

`stage2.preservation` has no `GUILLOTINE_IMPOSSIBLE` reason at all (Required Behaviour 3: Stage 2
never calls the guillotine engine) — a lost fact whose realized geometry disagrees with the donor
uses `NOT_HONOURED` instead. `DONOR_ROOM_NOT_REALIZED` is legitimate ONLY for a donor room
`repair.py`'s own `RoomLineage` explicitly DROPPED (a room the brief's programme does not carry) —
never for BEDROOM_0/BATHROOM_1, the two donor rooms the milestone-1 brief actually keeps (as MASTER
and BATH_1).
"""
from __future__ import annotations

from app.vertical_slice.stage2 import pipeline
from app.vertical_slice.stage2.contract import RoomLineageKind

_BRIEF_KEPT_DONOR_ROOM_IDS = {"BEDROOM_0", "BATHROOM_1", "LIVING_0", "LIVING_1", "KITCHEN_0"}


def test_no_lost_fact_carries_guillotine_impossible():
    run = pipeline.run_milestone_1()
    assert run.ok, run.refusal
    for fact_class in run.preservation.fact_classes:
        for lost in fact_class.lost:
            assert lost.reason != "GUILLOTINE_IMPOSSIBLE", (
                f"{fact_class.fact_class}: {lost.detail} carries GUILLOTINE_IMPOSSIBLE — Stage 2 "
                "never calls the guillotine engine")


def test_donor_room_not_realized_never_names_a_room_the_brief_still_contains():
    run = pipeline.run_milestone_1()
    assert run.ok, run.refusal
    dropped_donor_ids = {
        donor_id
        for event in run.repair.lineage.events
        if event.kind is RoomLineageKind.DROPPED
        for donor_id in event.donor_room_ids
    }
    # Every donor room the brief still contains must have been explicitly CARRIED, never DROPPED.
    assert _BRIEF_KEPT_DONOR_ROOM_IDS.isdisjoint(dropped_donor_ids)

    # Every DONOR_ROOM_NOT_REALIZED lost fact names at least one donor room -- a compound fact
    # (e.g. an adjacency edge) can name TWO donor rooms, one dropped and one kept, so this checks
    # that a genuinely dropped id explains the loss, never that no kept id's own string appears
    # anywhere in the detail (a kept id can be a SUBSTRING of an unrelated dropped pair's detail).
    for fact_class in run.preservation.fact_classes:
        for lost in fact_class.lost:
            if lost.reason != "DONOR_ROOM_NOT_REALIZED":
                continue
            explained_by_a_drop = any(rid in lost.detail for rid in dropped_donor_ids)
            assert explained_by_a_drop, (
                f"{fact_class.fact_class}: {lost.detail} is DONOR_ROOM_NOT_REALIZED but names no "
                f"donor room the lineage actually dropped")


def test_every_dropped_donor_room_is_explicitly_classified_not_merely_missing():
    """Required Behaviour 1's own invariant: `RoomLineage.unaccounted_donor_ids()` must be empty —
    every one of the donor's 10 rooms is CARRIED, DROPPED, or (had one existed) MERGED/SPLIT,
    never silently absent."""
    run = pipeline.run_milestone_1()
    assert run.ok, run.refusal
    assert run.repair.lineage.unaccounted_donor_ids() == ()
    assert run.chain_problems == ()
