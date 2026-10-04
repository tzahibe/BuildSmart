"""Issue #142I — the deterministic pre-realization proposal critic (detection) and the clearly labelled
minimal-repair experiment, measured on the frozen briefs. Harness code; nothing here is production."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vertical_slice"))

from app.ai_harness.topology_poc.proposal_critic import criticize, from_fixture  # noqa: E402
from app.ai_harness.topology_poc.proposal_repair import repair  # noqa: E402
from app.ai_harness.topology_poc.critic_142i import _pipeline_input  # noqa: E402
from app.vertical_slice.band_pipeline import PipelineSuccess, run_band_pipeline  # noqa: E402

from frozen_briefs import load_fixture, zones_of  # noqa: E402

FX = load_fixture()["briefs"]
PASSING = ("B01", "B04", "B05", "B08", "B11", "B13", "B18")
EXPECTED_HARD = {
    "B06": {"EXPOSURE_INFEASIBLE"},
    "B07": {"ACCESS_SPATIAL_CONTRADICTION", "WET_ROOM_MULTIPLE_ENTRANTS", "WET_ROOM_ENTRY_POLICY"},
    "B09": {"ACCESS_SPATIAL_CONTRADICTION", "WET_ROOM_MULTIPLE_ENTRANTS", "WET_ROOM_ENTRY_POLICY"},
    "B12": {"EXPOSURE_INFEASIBLE"},
    "B17": {"ACCESS_SPATIAL_CONTRADICTION"},
    "B20": {"WET_ROOM_MULTIPLE_ENTRANTS", "WET_ROOM_ENTRY_POLICY"},
}
REPAIRED_PASS = ("B06", "B07", "B09", "B12")


def _proposal(bid):
    return from_fixture(bid, FX[bid], zones_of(FX[bid]))


@pytest.mark.parametrize("bid", PASSING)
def test_critic_has_no_hard_finding_on_a_passing_brief(bid):
    rep = criticize(_proposal(bid))
    assert rep.hard == [], rep.hard_codes


@pytest.mark.parametrize("bid,codes", sorted(EXPECTED_HARD.items()))
def test_critic_detects_every_failing_brief_before_geometry(bid, codes):
    rep = criticize(_proposal(bid))
    assert set(rep.hard_codes) == codes, rep.hard_codes
    assert rep.seconds < 5.0


def test_critic_is_deterministic():
    a, b = criticize(_proposal("B07")), criticize(_proposal("B07"))
    assert [(f.code, f.subjects, f.detail) for f in a.findings] == [(f.code, f.subjects, f.detail) for f in b.findings]


@pytest.mark.parametrize("bid", REPAIRED_PASS)
def test_minimal_repair_is_recorded_intent_preserving_and_then_passes_production(bid):
    p = _proposal(bid)
    r = repair(p)
    assert r.repairs and r.unrepaired == [], (r.repairs, r.unrepaired)
    # no room invented, no role changed, no door added that the proposal did not ask for
    assert r.proposal.roles == p.roles
    assert {frozenset(e) for e in r.proposal.access} <= {frozenset(e) for e in p.access} | {
        frozenset(x.changed.split("->")) for x in r.repairs if x.rule == "R3_REROUTE_ACCESS"}
    assert r.proposal.spatial <= p.spatial            # contacts are only ever demoted, never invented
    for x in r.repairs:
        assert x.rule and x.original and x.changed and x.reason
    res = run_band_pipeline(_pipeline_input(bid, r.proposal, FX[bid]["footprint_m"]))
    assert isinstance(res, PipelineSuccess), res
    n = len([e for e in r.proposal.access if e[0] != "ENTRANCE"])
    assert res.access_preserved == f"{n}/{n}"


@pytest.mark.parametrize("bid", ("B17", "B20"))
def test_repair_reports_honestly_when_the_consistent_proposal_still_does_not_realize(bid):
    r = repair(_proposal(bid))
    assert r.unrepaired == []                           # the proposal IS consistent after repair ...
    res = run_band_pipeline(_pipeline_input(bid, r.proposal, FX[bid]["footprint_m"]))
    assert not isinstance(res, PipelineSuccess)         # ... but the band family within the bound has no sizable layout
    assert res.code in ("SIZING_INFEASIBLE", "NO_ENTRANCE")
