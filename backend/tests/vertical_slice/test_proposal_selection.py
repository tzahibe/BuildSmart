"""Issue #142J — production proposal critic + critic-first selection.

critic -> keep clean -> score -> select -> realizer. A HARD-invalid proposal never beats a clean one on
score; all-invalid yields a typed NO_VALID_PROPOSAL with every finding; wet-room kinds come from the
brief; nothing is repaired; UNKNOWN stays distinct from proven INFEASIBLE; everything is deterministic.
"""
from __future__ import annotations

from app.vertical_slice.geometry_core.model import ProgramRole
from app.vertical_slice.proposal_critic import Proposal, assign_wet_room_kinds, criticize
from app.vertical_slice.proposal_selection import NoValidProposal, ProposalSelection, select_proposal
from app.vertical_slice.rectilinear_realizer import ZoneIntent
from app.vertical_slice.spec import ENSUITE_HOST_MASTER, WetRoomKind, WetRoomOrigin, WetRoomRequirement


def _zi(zid, role, target, lo, hi, short=2.4, aspect=2.5):
    return ZoneIntent(zid, role, target, lo, hi, short, aspect)


ROLES = {"LIVING": ProgramRole.LIVING, "KITCHEN": ProgramRole.KITCHEN, "HALL": ProgramRole.HALL,
         "MASTER": ProgramRole.MASTER_BEDROOM, "BEDROOM_1": ProgramRole.BEDROOM,
         "BATHROOM_1": ProgramRole.BATHROOM, "BATHROOM_2": ProgramRole.BATHROOM}
ZONES = {"LIVING": _zi("LIVING", ProgramRole.LIVING, 26.0, 16.0, 46.0, 3.0), "KITCHEN": _zi("KITCHEN", ProgramRole.KITCHEN, 13.0, 9.0, 26.0, 2.4),
         "HALL": _zi("HALL", ProgramRole.HALL, 7.0, 5.0, 12.0, 1.2, 4.0), "MASTER": _zi("MASTER", ProgramRole.MASTER_BEDROOM, 15.0, 12.0, 20.0, 3.0),
         "BEDROOM_1": _zi("BEDROOM_1", ProgramRole.BEDROOM, 12.0, 9.0, 14.0, 2.6),
         "BATHROOM_1": _zi("BATHROOM_1", ProgramRole.BATHROOM, 5.0, 3.5, 7.0, 1.6), "BATHROOM_2": _zi("BATHROOM_2", ProgramRole.BATHROOM, 5.0, 3.5, 7.0, 1.6)}
KINDS = (WetRoomRequirement(WetRoomKind.ENSUITE, ENSUITE_HOST_MASTER, origin=WetRoomOrigin.COUNT_DERIVED),
         WetRoomRequirement(WetRoomKind.SHARED_BATHROOM, origin=WetRoomOrigin.COUNT_DERIVED))
FOOTPRINT = (13.0, 11.0)


def _p(name, spatial, access, kinds=KINDS):
    return Proposal(name, ROLES, frozenset(frozenset(e) for e in spatial), tuple(access), ZONES, kinds)


# a consistent proposal: hall hub, master ensuite, shared bathroom off the hall
GOOD_SPATIAL = [("LIVING", "KITCHEN"), ("LIVING", "HALL"), ("KITCHEN", "HALL"), ("HALL", "MASTER"), ("HALL", "BEDROOM_1"),
                ("HALL", "BATHROOM_2"), ("MASTER", "BATHROOM_1"), ("BEDROOM_1", "BATHROOM_2")]
GOOD_ACCESS = [("ENTRANCE", "LIVING"), ("LIVING", "KITCHEN"), ("LIVING", "HALL"), ("HALL", "MASTER"), ("HALL", "BEDROOM_1"),
               ("HALL", "BATHROOM_2"), ("MASTER", "BATHROOM_1")]
GOOD = _p("good", GOOD_SPATIAL, GOOD_ACCESS)
# the same house with a two-door bathroom (BEDROOM_1 + HALL) and a door without a wall (LIVING -> BEDROOM_1)
BAD = _p("bad", GOOD_SPATIAL, GOOD_ACCESS + [("BEDROOM_1", "BATHROOM_2"), ("LIVING", "BEDROOM_1")])


def test_clean_proposal_has_no_hard_findings_and_brief_kinds_are_assigned():
    rep = criticize(GOOD)
    assert rep.clean, rep.hard_codes
    kinds = {w.zone_id: (w.kind, w.host_zone) for w in rep.wet_rooms}
    assert kinds == {"BATHROOM_1": (WetRoomKind.ENSUITE, "MASTER"), "BATHROOM_2": (WetRoomKind.SHARED_BATHROOM, None)}


def test_two_door_bathroom_and_wall_less_door_are_hard():
    rep = criticize(BAD)
    assert "WET_ROOM_MULTIPLE_ENTRANTS" in rep.hard_codes
    assert "ILLEGAL_ACCESS_PAIR" in rep.hard_codes          # LIVING -> BEDROOM is not a legal door pair either
    assert any(f.code == "ACCESS_WITHOUT_CONTACT" for f in rep.findings)


def test_hard_invalid_never_beats_clean_on_score():
    sel = select_proposal([BAD, GOOD], score=lambda p: 10.0 if p.name == "bad" else 1.0, footprint_m=FOOTPRINT)
    assert isinstance(sel, ProposalSelection), sel
    assert sel.proposal.name == "good" and sel.index == 1 and sel.clean_rank == 0
    assert [v.eligible for v in sel.verdicts] == [False, True]
    assert sel.verdicts[0].score is None                   # never scored: not eligible
    assert sel.pipeline.realized.report.ok


def test_all_invalid_is_a_typed_no_valid_proposal_with_findings_and_nothing_repaired():
    sel = select_proposal([BAD, BAD], score=lambda p: 1.0, footprint_m=FOOTPRINT)
    assert isinstance(sel, NoValidProposal)
    assert sel.code == "NO_VALID_PROPOSAL" and len(sel.verdicts) == 2
    assert all("WET_ROOM_MULTIPLE_ENTRANTS" in v.report.hard_codes for v in sel.verdicts)
    assert "WET_ROOM_MULTIPLE_ENTRANTS" in sel.detail


def test_brief_is_the_source_of_truth_for_specified_kinds():
    # the brief SPECIFIES a master ensuite; the proposal gives the ensuite to BEDROOM_1 instead
    spatial = [("LIVING", "KITCHEN"), ("LIVING", "HALL"), ("KITCHEN", "HALL"), ("HALL", "MASTER"), ("HALL", "BEDROOM_1"),
               ("HALL", "BATHROOM_2"), ("BEDROOM_1", "BATHROOM_1"), ("MASTER", "BATHROOM_2")]
    access = [("ENTRANCE", "LIVING"), ("LIVING", "KITCHEN"), ("LIVING", "HALL"), ("HALL", "MASTER"), ("HALL", "BEDROOM_1"),
              ("HALL", "BATHROOM_2"), ("BEDROOM_1", "BATHROOM_1")]
    specified = (WetRoomRequirement(WetRoomKind.ENSUITE, ENSUITE_HOST_MASTER, origin=WetRoomOrigin.EXPLICIT),
                 WetRoomRequirement(WetRoomKind.SHARED_BATHROOM, origin=WetRoomOrigin.EXPLICIT))
    rep = criticize(_p("swap", spatial, access, specified))
    assert "WET_ROOM_KIND_MISSING" in rep.hard_codes
    # the same proposal against COUNT-DERIVED defaults: the proposal's reading is adopted, a WARN records the difference
    rep2 = criticize(_p("swap", spatial, access, KINDS))
    assert rep2.clean, rep2.hard_codes
    assert any(f.code == "WET_ROOM_KIND_DIFFERS_FROM_DEFAULT" for f in rep2.findings)
    kinds = {w.zone_id: (w.kind, w.host_zone, w.specified) for w in rep2.wet_rooms}
    assert kinds["BATHROOM_1"] == (WetRoomKind.ENSUITE, "BEDROOM_1", False)


def test_more_wet_rooms_than_the_brief_counted_is_hard():
    one_kind = (WetRoomRequirement(WetRoomKind.SHARED_BATHROOM, origin=WetRoomOrigin.EXPLICIT),)
    rep = criticize(_p("count", GOOD_SPATIAL, GOOD_ACCESS, one_kind))
    assert "WET_ROOM_COUNT_MISMATCH" in rep.hard_codes


def test_selection_is_deterministic():
    a = select_proposal([BAD, GOOD, GOOD], score=lambda p: 1.0, footprint_m=FOOTPRINT)
    b = select_proposal([BAD, GOOD, GOOD], score=lambda p: 1.0, footprint_m=FOOTPRINT)
    assert isinstance(a, ProposalSelection) and a.index == b.index == 1       # equal scores: lowest index wins
    assert {k: (r.x, r.y, r.w, r.h) for k, r in a.pipeline.realized.rects.items()} == \
           {k: (r.x, r.y, r.w, r.h) for k, r in b.pipeline.realized.rects.items()}
