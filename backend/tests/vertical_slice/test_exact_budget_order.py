"""#216 — the shared budget must not let ONE solve starve the candidates queued behind it.

`run_exact_pipeline` bounds a whole request with one wall-clock `deadline` and the runner divides
it per parti. Before #216 a solve was handed `max(1.0, min(10.0, deadline - now))`: on B11 the top
parti's share was 1.9 s, so the first candidate's V rung was allowed the entire share, spent 1.79 s
of it, returned UNKNOWN, and the NEXT candidate — the one whose H orientation sizes successfully —
was never reached. 65 solves, 64 INFEASIBLE, 1 UNKNOWN.

This machine is shared with other agents and #207 proved a seconds-based clause is invalid under
contention, so nothing here asserts a duration. The assertions are on the solve ORDER, on the
LIMIT each solve is handed (pure arithmetic), and on WHICH solves are reached when a hard one
consumes everything it is allowed — with the budget fixed by the test, never by wall-clock luck.
"""
from __future__ import annotations

import time

import pytest

from app.vertical_slice.band_pipeline import PipelineDiagnosis
from app.vertical_slice.brain import exact_pipeline as ep

pytest.importorskip("scipy")

#: the share production leaves the top parti on B11, read off `trace-b11-band.log` (#207's trace):
#: "production leaves 6 s of the 30 s request budget, the top parti's share is 1.9 s".
B11_SHARE_S = 1.9


# --------------------------------------------------------------- the bound itself, no clock at all

def test_no_single_solve_may_be_given_more_than_a_bounded_fraction_of_what_is_left():
    for remaining in (0.5, 1.0, 1.9, 6.0, 12.0, 30.0, 120.0, 1e6):
        got = ep.solve_time_limit(remaining)
        assert got <= max(ep.MIN_SOLVE_S, ep.SOLVE_BUDGET_FRACTION * remaining) + 1e-9, remaining
        assert got <= ep.SOLVE_CEILING_S, remaining
        assert got >= ep.MIN_SOLVE_S, remaining


#: a candidate's orientation walks the four-rung widening ladder, so at least that many hard solves
#: have to fit inside a share before the NEXT candidate's H can be reached at all.
LADDER_RUNGS = 4


def test_the_bound_leaves_room_behind_every_hard_solve_instead_of_truncating():
    """The property that matters: a hard solve cannot consume the share. On B11's own 1.9 s share,
    six consecutive solves that each spend every second they are handed still leave budget — where
    the pre-#216 formula left none after the first."""
    remaining = B11_SHARE_S
    for i in range(LADDER_RUNGS + 2):
        remaining -= ep.solve_time_limit(remaining)
        assert remaining > 0, f"solve {i} spent the whole remaining share"
    old_remaining = B11_SHARE_S - max(1.0, min(10.0, B11_SHARE_S))
    assert old_remaining <= 0


def test_the_old_formula_is_the_defect_this_bound_replaces():
    """Recorded for the record: the pre-#216 formula hands a 1.9 s share away in one solve."""
    old = max(1.0, min(10.0, B11_SHARE_S))
    assert old >= B11_SHARE_S                     # one solve, the whole share
    assert ep.solve_time_limit(B11_SHARE_S) < B11_SHARE_S


# ----------------------------------------------------------------------- a recording fake oracle

class _Recorder:
    """Replaces the three exact oracles. Records (family, candidate key, street, limit) per solve.

    `hard` solves consume every second they were handed and come back UNKNOWN — the B11 V rung.
    Everything else is INFEASIBLE at once, as 64 of B11's 65 solves were (0.00-0.03 s each).
    """

    def __init__(self, hard=lambda street, n: False):
        self.hard = hard
        self.log: list[tuple[str, str, str, float]] = []

    def _solve(self, family, key, street, limit_s):
        self.log.append((family, key, street, limit_s))
        if self.hard(street, len(self.log)):
            time.sleep(limit_s)
            return _Result("UNKNOWN")
        return _Result("INFEASIBLE")

    def install(self, monkeypatch):
        from app.vertical_slice.exact import milp_cells, milp_oracle

        def band(bands, *a, street="N", time_limit_s=10.0, **k):
            return self._solve("band", _key(bands), street, time_limit_s)

        def spine(layout, *a, street="N", time_limit_s=10.0, **k):
            return self._solve("spine", repr(layout)[:120], street, time_limit_s)

        def cells(lay, *a, street="N", time_limit_s=10.0, **k):
            return self._solve("cells", repr(lay)[:120], street, time_limit_s)

        monkeypatch.setattr(milp_oracle, "milp_placement", band)
        monkeypatch.setattr(milp_oracle, "milp_spine_placement", spine)
        monkeypatch.setattr(milp_cells, "cells_placement", cells)
        return self

    def candidates(self, family=None, street=None):
        """The candidate keys that got a solve, in the order they first did."""
        out = []
        for f, k, s, _ in self.log:
            if (family in (None, f)) and (street in (None, s)) and k not in out:
                out.append(k)
        return out


class _Result:
    def __init__(self, status):
        self.status = status

    def as_sizing(self):                                          # never reached: never FEASIBLE
        raise AssertionError("the fake oracle never returns FEASIBLE")


def _key(bands) -> str:
    return repr(bands)[:160]


# ------------------------------------------------------- B11's own parti, with a FIXED share

@pytest.fixture(scope="module")
def b11_call():
    """B11's top-ranked parti exactly as the runner hands it to the exact sizer: the real
    `PipelineInput` and the real keyword arguments, captured from a real `run_brain` pass whose
    exact sizer is stubbed out. Only `deadline` is replaced below — by the test, not by the clock."""
    from tests.vertical_slice.test_brain import _spec_and_footprint
    from app.vertical_slice.brain.runner import run_brain

    captured: list[tuple] = []

    def capture(inp, **kw):
        captured.append((inp, kw))
        return PipelineDiagnosis("NO_EXACT_PLAN", "SIZING", "captured by test_exact_budget_order")

    real = ep.run_exact_pipeline
    ep.run_exact_pipeline = capture
    try:
        spec, fp = _spec_and_footprint("B11")
        run_brain(spec, fp, brief="B11", sizer="exact", families=("band",))
    finally:
        ep.run_exact_pipeline = real
    assert captured, "the runner never called the exact sizer for B11"
    return captured[0]


def _replay(b11_call, monkeypatch, *, share_s, hard):
    inp, kw = b11_call
    rec = _Recorder(hard=hard).install(monkeypatch)
    kw = {k: v for k, v in kw.items() if k != "deadline"}
    ep.run_exact_pipeline(inp, deadline=time.monotonic() + share_s, **kw)
    return rec


def test_b11_h_is_sized_before_v_for_every_candidate(b11_call, monkeypatch):
    """The order was never the bug: every family's orientation loop is nested inside its candidate
    loop and walks `(("H", env), ("V", transposed))`, so a candidate's H precedes its own V. This
    pins that, with a budget big enough that nothing is cut off."""
    rec = _replay(b11_call, monkeypatch, share_s=30.0, hard=lambda street, n: False)
    assert rec.log, "no solve was recorded"
    seen_v: set[str] = set()
    for i, (family, key, street, _limit) in enumerate(rec.log):
        if street == "W":
            seen_v.add(key)
        else:
            assert key not in seen_v, f"solve {i}: H of {key} came after its own V"
    assert "N" in {s for _, _, s, _ in rec.log} and "W" in {s for _, _, s, _ in rec.log}


def test_b11_reaches_a_second_candidates_h_with_the_share_production_leaves(b11_call, monkeypatch):
    """The regression itself. Every V solve is hard — it spends all it is given and returns UNKNOWN,
    as B11's V rung did. With the share production actually leaves (1.9 s), more than one
    candidate's H orientation must still be reached."""
    rec = _replay(b11_call, monkeypatch, share_s=B11_SHARE_S, hard=lambda street, n: street == "W")
    reached = rec.candidates(street="N")
    assert len(reached) >= 2, f"only {len(reached)} candidate(s) reached H: {rec.log}"


def test_b11_the_old_formula_starved_the_second_candidate(b11_call, monkeypatch):
    """The same replay with the pre-#216 limit: the first candidate's first hard V solve is handed
    the whole 1.9 s share, so no second candidate is ever reached. This is the defect, pinned so a
    future change to `solve_time_limit` cannot quietly reintroduce it."""
    monkeypatch.setattr(ep, "solve_time_limit", lambda rest: max(1.0, min(10.0, rest)))
    rec = _replay(b11_call, monkeypatch, share_s=B11_SHARE_S, hard=lambda street, n: street == "W")
    assert len(rec.candidates(street="N")) == 1, rec.log


def test_no_solve_is_given_more_than_the_bound_in_a_real_pipeline_run(b11_call, monkeypatch):
    """Whatever the families do, every limit the pipeline hands an oracle respects the bound."""
    rec = _replay(b11_call, monkeypatch, share_s=B11_SHARE_S, hard=lambda street, n: street == "W")
    ceiling = max(ep.MIN_SOLVE_S, ep.SOLVE_BUDGET_FRACTION * B11_SHARE_S) + 1e-9
    for family, key, street, limit in rec.log:
        assert limit <= ceiling, f"{family}/{street} was given {limit} s of a {B11_SHARE_S} s share"


def test_every_family_goes_through_the_one_bound(b11_call, monkeypatch):
    """Shape- and family-agnostic: band, spine, stack and cells all call the same `time_left()`,
    so none of them can be handed more than the bound."""
    inp, kw = b11_call
    rec = _Recorder(hard=lambda street, n: street == "W").install(monkeypatch)
    kw = {k: v for k, v in kw.items() if k not in ("deadline", "families")}
    ep.run_exact_pipeline(inp, deadline=time.monotonic() + B11_SHARE_S,
                          families=ep.ALL_FAMILIES, **kw)
    ceiling = max(ep.MIN_SOLVE_S, ep.SOLVE_BUDGET_FRACTION * B11_SHARE_S) + 1e-9
    assert rec.log
    for family, key, street, limit in rec.log:
        assert limit <= ceiling, f"{family} was given {limit} s"
