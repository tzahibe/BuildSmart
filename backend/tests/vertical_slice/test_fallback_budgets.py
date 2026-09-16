"""Fallback classes keep their own budgets, and over_preferred attempts stop at the hard capacity.

The measured defect (failure log, 2026-09-15, `2BR/3wet closed 16 x 18, 288 m² asked`): the
per-strategy fallback budget was ONE shared `wanted`, and three over_preferred plans at 268/259/250
m² — found first, refused by Geometry Core later — filled it, so the 223/217/211 m² shrunk plans
that solve were never offered and the brief got a 130 m² house (C21 had delivered 217).
"""
from __future__ import annotations

from collections import Counter

import pytest

from app.geometry_domain.primitives import Region, Ring
from app.vertical_slice import concept_generator as cg
from app.vertical_slice import geometry_fixtures as F
from app.vertical_slice.concept_generator import (
    ConceptStrategy,
    _MAX_PROPORTIONS_PER_STRATEGY,
    _absorbable_over_preferred,
    build_room_program,
    generate_concepts,
    program_capacity_gross_m2,
)
from app.vertical_slice.general_pipeline import run_general
from app.vertical_slice.geometry_core.model import ProgramRole
from app.vertical_slice.safe_adapter import adapt
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec

PROGRAM = ProgramSpec(bedrooms=2, safe_room=True, wet_rooms=3, open_plan_living=False,
                      parking_spaces=0, target_built_area_m2=288.0)
PLOT = (23.0, 28.5)


def _buildable():
    return F._known(Region(Ring.rectangle(3.5, 5.0, 16.0, 18.0)))


def _spec() -> ArchitecturalSpec:
    return ArchitecturalSpec(plot=PlotSpec(*PLOT), program=PROGRAM)


def _candidates(monkeypatch=None, *, prune: bool = True):
    if not prune:
        monkeypatch.setattr(cg, "_absorbable_over_preferred", lambda rooms, gross: True)
    result = generate_concepts(_spec(), list(adapt(_buildable()).candidates))
    return [c for c in result.candidates
            if c.strategy is ConceptStrategy.SPINE_PUBLIC_PRIVATE
            and cg.FREE_TWIN_RATIONALE not in c.rationale]


def _classes(cands) -> Counter:
    return Counter((c.repartitioned, c.shrunk, c.over_preferred) for c in cands)


def test_shrunk_candidates_survive_beside_over_preferred_ones(monkeypatch):
    """With pruning off, the oversized over_preferred plans exist AND the 223/217/211 shrunk plans
    are still there — each class has its own budget."""
    cands = _candidates(monkeypatch, prune=False)
    shrunk_only = sorted(round(c.used_area_m2, 1) for c in cands if c.shrunk and not c.over_preferred)
    over = sorted(round(c.used_area_m2, 1) for c in cands if c.over_preferred)
    assert over, "the oversized over_preferred plans are produced when pruning is off"
    assert max(over) > 240.0
    assert shrunk_only == [211.0, 217.5, 223.3], shrunk_only


def test_fallback_classes_do_not_consume_each_others_budget(monkeypatch):
    cands = _candidates(monkeypatch, prune=False)
    classes = _classes(cands)
    assert len([k for k in classes if k != (False, False, False)]) >= 2, classes
    for flags, n in classes.items():
        assert n <= _MAX_PROPORTIONS_PER_STRATEGY, (flags, n)
    # the shrunk-only class is full even though the over_preferred class is populated too
    assert classes[(False, True, False)] == _MAX_PROPORTIONS_PER_STRATEGY


def test_the_217_candidate_solves_and_is_delivered():
    result = run_general(_buildable(), plot_size_m=PLOT, program=PROGRAM, fast_path=True)
    assert result.design is not None, result.metrics.rejection_reasons
    assert result.validation.ok, [(c.check_id, c.detail) for c in result.validation.failures()]
    assert result.design.gross_area_m2 >= 217.0 - 0.5, result.design.gross_area_m2
    assert result.concept.shrunk and not result.concept.over_preferred


def test_pruning_never_removes_a_candidate_at_or_below_hard_capacity(monkeypatch):
    rooms = build_room_program(_spec())
    hard = program_capacity_gross_m2(rooms, hard=True)
    with_pruning = {(round(c.used_area_m2, 1), c.repartitioned, c.shrunk, c.over_preferred)
                    for c in _candidates()}
    without = {(round(c.used_area_m2, 1), c.repartitioned, c.shrunk, c.over_preferred)
               for c in _candidates(monkeypatch, prune=False)}
    kept = {k for k in without if k[0] <= hard + 1e-6}
    assert kept <= with_pruning, kept - with_pruning
    assert all(k[0] > hard for k in without - with_pruning), "only over-hard-capacity plans are pruned"


def test_absorbable_boundary_uses_the_hard_capacity_of_the_rooms():
    rooms = build_room_program(_spec())
    hard = program_capacity_gross_m2(rooms, hard=True)
    preferred = program_capacity_gross_m2(rooms)
    assert hard >= preferred
    assert _absorbable_over_preferred(rooms, hard)          # at the ceiling: kept
    assert _absorbable_over_preferred(rooms, preferred)     # below it: kept
    assert not _absorbable_over_preferred(rooms, hard + 1.0)
    # a FLEX zone is not a room: it does not raise the ceiling the rooms can absorb
    flex = cg.ProgramRoom("FLEX", ProgramRole.FLEX, cg.ZoneGroup.PUBLIC, cg.ROOM_TEMPLATES[ProgramRole.FLEX])
    assert program_capacity_gross_m2([*rooms, flex], hard=True) == pytest.approx(hard)


# ------------------------------------------------------------------ reason-aware fallback gating

from app.vertical_slice.concept_generator import (  # noqa: E402
    PlanFailure, RejectionReason, _FallbackAsks, _row_depths, _shape_failure,
)


def _room(role: ProgramRole, zone_id: str | None = None):
    return cg.ProgramRoom(zone_id or role.value, role, cg.ZoneGroup.PRIVATE, cg.ROOM_TEMPLATES[role])


def test_a_fallback_class_runs_only_when_it_adds_a_mechanism_some_failure_asked_for():
    none = _FallbackAsks()
    assert not none.worth(True, False, set()) and not none.worth(False, True, set()) and not none.worth(True, True, set())
    deficit = none.plus(PlanFailure(RejectionReason.COLUMN_DEPTH_EXCEEDED, "", deficit_fixable=True))
    assert deficit.worth(True, False, set()) and not deficit.worth(False, True, set())
    # shrunk+hard with hard inert IS the shrunk attempt: worth it only where that was not tried
    assert deficit.worth(True, True, set()) and not deficit.worth(True, True, {(True, False)})
    both = deficit.plus(PlanFailure(RejectionReason.ROOM_ABOVE_MAXIMUM_AREA, "", hard_fixable=True))
    assert both.worth(True, False, set()) and both.worth(False, True, {(True, False)}) and both.worth(True, True, {(True, False), (False, True)})
    assert _FallbackAsks.of(PlanFailure(RejectionReason.ROOM_SHAPE_INFEASIBLE, "")).shape
    assert _FallbackAsks.of(None) == none


def test_wants_over_a_column_whose_floors_fit_ask_for_shrinking_and_floors_over_do_not():
    bed = _room(ProgramRole.BEDROOM, "B1"); bed2 = _room(ProgramRole.BEDROOM, "B2")
    rows = [[bed], [bed2]]
    # wants (14 m2 each at 4 m net width = 3.5 m rows) overflow 6 m, floors (2.8 m each) fit
    _, failure = _row_depths(rows, {"B1": 14.0, "B2": 14.0}, 4.0, 6.0)
    assert failure is not None and failure.reason is RejectionReason.COLUMN_DEPTH_EXCEEDED
    assert failure.deficit_fixable
    # floors alone overflow 5 m: shrinking cannot help
    _, failure = _row_depths(rows, {"B1": 14.0, "B2": 14.0}, 4.0, 5.0)
    assert failure is not None and failure.reason is RejectionReason.COLUMN_DEPTH_EXCEEDED
    assert not failure.deficit_fixable


def test_a_preferred_maximum_asks_for_hard_only_where_there_is_headroom():
    living = _room(ProgramRole.LIVING)          # 46 preferred, 50 hard
    f = _shape_failure(living, 8.0, 6.0, "west column", False)   # 48 m2: over preferred, under hard
    assert f is not None and f.reason is RejectionReason.ROOM_ABOVE_MAXIMUM_AREA and f.hard_fixable
    f = _shape_failure(living, 8.0, 6.0, "west column", True)    # judged against hard: passes
    assert f is None
    no_headroom = next(r for r in cg.ROOM_TEMPLATES if cg.ROOM_TEMPLATES[r].hard_max == cg.ROOM_TEMPLATES[r].max_area_m2 and r not in (ProgramRole.FLEX, ProgramRole.HALL))
    room = _room(no_headroom)
    side = (room.template.max_area_m2 + 1.0) ** 0.5          # square, one m2 over the maximum
    f = _shape_failure(room, side, side, "column", False)
    assert f is not None and f.reason is RejectionReason.ROOM_ABOVE_MAXIMUM_AREA and not f.hard_fixable


def test_no_fallback_attempt_runs_without_a_failure_that_asked_for_its_mechanism(monkeypatch):
    """Recorded over a real brief: every fallback attempt at a proportion follows a failure there
    that asked for one of its mechanisms (`deficit_fixable` / `hard_fixable`), every
    re-partitioned one a shape refusal."""
    log: list[tuple[tuple[float, float], dict, object]] = []
    real = cg.plan_layout

    def recording(rooms, west, east, hall_ids, tw, th, corridor=None, **kw):
        result = real(rooms, west, east, hall_ids, tw, th, corridor, **kw)
        log.append(((round(tw, 2), round(th, 2)), kw, result[1] if result[0] is None else None))
        return result

    monkeypatch.setattr(cg, "plan_layout", recording)
    generate_concepts(_spec(), list(adapt(_buildable()).candidates))
    assert any(kw.get("allow_deficit") for _, kw, _ in log), "the brief must exercise fallbacks"
    seen: dict[tuple[float, float], _FallbackAsks] = {}
    for proportion, kw, failure in log:
        asks = seen.get(proportion, _FallbackAsks())
        if kw.get("allow_deficit") or kw.get("allow_hard"):
            assert (kw.get("allow_deficit") and asks.deficit) or (kw.get("allow_hard") and asks.hard), (proportion, kw)
        if kw.get("fallback") is not None:
            assert asks.shape, (proportion, kw)
        if failure is not None:
            seen[proportion] = asks.plus(failure)
        elif proportion not in seen:
            seen[proportion] = asks


def test_a_floor_past_preferred_asks_for_hard_even_without_headroom():
    """The hard pass skips the early floor check and clamps the row to its ceiling instead, so it
    can plan a safe room (hard maximum == preferred) that the preferred pass refused at its floor:
    5.6 m wide, its 2.4 m short side plus the RC allowance is 14.6 m2 against 14. Measured: the
    oracle over the failure log found this the one way a skipped shrunk+hard attempt planned."""
    safe = _room(ProgramRole.SAFE_ROOM); bath = _room(ProgramRole.BATHROOM, "BATH_2")
    rows = [[safe], [bath]]
    _, failure = _row_depths(rows, {"SAFE_ROOM": 10.5, "BATH_2": 6.8}, 5.6, 5.1)
    assert failure is not None and failure.reason is RejectionReason.ROOM_ABOVE_MAXIMUM_AREA
    assert "SAFE_ROOM" in failure.detail and failure.hard_fixable
    depths, failure = _row_depths(rows, {"SAFE_ROOM": 10.5, "BATH_2": 6.8}, 5.6, 5.1, allow_hard=True)
    assert failure is None and depths is not None
