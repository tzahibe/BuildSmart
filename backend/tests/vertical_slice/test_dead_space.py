"""Dead-space / residual-pocket detection INSIDE zones (Issue #43).

Fixture convention mirrors `test_circulation_metrics.py`: hand-built `GeometricDesign` objects for
the shapes this codebase cannot currently produce by accident (a genuinely abandoned corridor
stub, an undersized sliver room — every REAL candidate this generator produces stays well inside
the calibrated `DEAD_SPACE_STUB_HARD_LIMIT_M`, see `docs/DEAD_SPACE_SWEEP.md`), and the real
pipeline/generator output for "what does this measure on an ordinary plan".

AC-1's own "nothing on the canonical fixtures" is proven against a fully-served, no-dead-end hand
built hall (this module's own `_no_dead_space_design`) — NOT `pipeline.run_demo()`'s own frozen
baseline, which (correctly, and by design) DOES measure a small non-zero STUB today: its HALL_SPUR
leg has exactly the one tolerated dead end `circulation_metrics.dead_end_count`'s own docstring
already documents as architecturally normal for a spine parti, now sized as data instead of merely
counted as a boolean. That real baseline is instead used for AC-2 ("passes the canonical
fixtures") — the correctness claim `dead_space_sweep.py`'s own full-corpus run actually supports:
C32 passes on it (1.05 m, well under the 2.0 m hard limit), never that it measures zero.
"""
from __future__ import annotations

import tempfile

import pytest

from app.vertical_slice import dead_space as ds
from app.vertical_slice import validation as validation_stage
from app.vertical_slice.design_output import DoorOut, GeometricDesign, RoomOut
from app.vertical_slice.geometry_core.engine import solve_fixture
from app.vertical_slice.pipeline import run_demo
from app.vertical_slice.spec import demo_spec
from app.vertical_slice import concept as concept_stage
from app.vertical_slice import doors as doors_stage
from app.vertical_slice import furniture as furniture_stage
from app.vertical_slice import site as site_stage
from app.vertical_slice import windows as windows_stage
from app.vertical_slice.wet_rooms import resolve_wet_rooms

pytestmark = pytest.mark.filterwarnings("ignore")


# --------------------------------------------------------------------------- fixtures


_INTERIOR = {"N": "STANDARD_PARTITION", "S": "STANDARD_PARTITION",
            "E": "STANDARD_PARTITION", "W": "STANDARD_PARTITION"}


def _wall_facts():
    from app.geometry_domain.walls import BoundaryContext, Construction, WallFacts
    partition = WallFacts(BoundaryContext.INTERIOR, Construction.STANDARD_PARTITION)
    return {s: partition for s in ("N", "S", "E", "W")}


def _room(zone_id, roles, rect_m, area=None):
    x, y, w, h = rect_m
    return RoomOut(
        zone_id=zone_id, roles=roles, rect_m=rect_m, net_w_m=w, net_h_m=h,
        net_area_m2=area if area is not None else round(w * h, 4),
        walls=dict(_INTERIOR), wall_facts=_wall_facts(),
    )


def _door(a, b, orientation, center_m, width_m=0.9, hinge_m=None, swing_deg=0.0):
    return DoorOut(a=a, b=b, kind="ROOM_DOOR", width_m=width_m, center_m=center_m,
                   orientation=orientation, placeable=True, shared_length_m=1.0,
                   hinge_m=hinge_m if hinge_m is not None else center_m, swing_deg=swing_deg)


def _entrance(b, center_m=(0.0, 0.0), orientation="horizontal"):
    return DoorOut(a="OUTSIDE", b=b, kind="ENTRANCE_DOOR", width_m=1.0, center_m=center_m,
                   orientation=orientation, placeable=True, shared_length_m=1.0,
                   hinge_m=center_m, swing_deg=0.0)


def _design(rooms, doors, entrance, footprint=(0.0, 0.0, 20.0, 20.0)) -> GeometricDesign:
    total = sum(r.net_area_m2 for r in rooms)
    return GeometricDesign(
        plot_m=(0.0, 0.0, 30.0, 30.0), footprint_m=footprint, rooms=tuple(rooms),
        interior_doors=tuple(doors), entrance_door=entrance, windows=(), parking_m=(), garden=(),
        entrance_walk_m=(0.0, 0.0, 1.0, 1.0), gross_area_m2=total, net_area_m2=total,
        wall_iterations=0,
    )


def _corridor_stub_design() -> GeometricDesign:
    """A 6 m HALL with its only branch door 1.0 m from the W end: the W end (1.0 m of unserved
    corridor) stays under every plausible threshold, but the E end — 5.0 m of corridor past the
    last door — is exactly the shape STUB exists to catch, well past
    `DEAD_SPACE_STUB_HARD_LIMIT_M` regardless of exactly how that constant is calibrated."""
    hall = _room("HALL", ("HALL", "CIRCULATION"), (0.0, 0.0, 6.0, 1.3))
    living = _room("LIVING", ("LIVING",), (0.0, 1.3, 4.0, 5.0), area=20.0)
    door = _door("HALL", "LIVING", "horizontal", (1.0, 1.3))
    entrance = _entrance("LIVING", center_m=(2.0, 6.3))
    return _design([hall, living], [door], entrance)


def _sliver_design() -> GeometricDesign:
    """A STORAGE room realized at a 0.6 m net short side — well under
    `SLIVER_MIN_USABLE_WIDTH_M` (0.9 m, itself below every real `ROOM_TEMPLATES` minimum, so this
    shape never occurs on a C3-compliant room in production; see that constant's own docstring)."""
    storage = _room("STORAGE", ("STORAGE",), (0.0, 0.0, 0.6, 3.0))
    living = _room("LIVING", ("LIVING",), (0.6, 0.0, 6.0, 5.0), area=30.0)
    door = _door("STORAGE", "LIVING", "vertical", (0.6, 1.5))
    entrance = _entrance("LIVING", center_m=(3.6, 0.0))
    return _design([storage, living], [door], entrance)


def _no_dead_space_design() -> GeometricDesign:
    """A HALL fully served at both ends (a door at each end) and no other region — the "nothing
    to find" fixture AC-1 asks for: a clean transition space, not a defect."""
    hall = _room("HALL", ("HALL", "CIRCULATION"), (0.0, 0.0, 6.0, 1.3))
    living = _room("LIVING", ("LIVING",), (0.0, 1.3, 4.0, 5.0), area=20.0)
    study = _room("STUDY", ("STUDY",), (0.0, -5.0, 4.0, 5.0), area=18.0)
    door_a = _door("HALL", "LIVING", "vertical", (0.0, 0.65))
    door_b = _door("HALL", "STUDY", "vertical", (6.0, 0.65))
    entrance = _entrance("LIVING", center_m=(2.0, 6.3))
    return _design([hall, living, study], [door_a, door_b], entrance)


def _transition_hall_within_budget_design() -> GeometricDesign:
    """An open, ordinary transition hall — target-sized (11 m2, within
    `ROOM_TEMPLATES[HALL]`'s own target/hard-max band) and served at both ends — the shape AC-1
    explicitly asks NOT to be flagged as OVERSIZED_HALL or STUB."""
    hall = _room("HALL", ("HALL", "CIRCULATION"), (0.0, 0.0, 5.5, 2.0), area=11.0)
    living = _room("LIVING", ("LIVING",), (0.0, 2.0, 5.0, 6.0), area=30.0)
    study = _room("STUDY", ("STUDY",), (0.0, -5.0, 5.5, 5.0), area=18.0)
    door_a = _door("HALL", "LIVING", "vertical", (0.0, 1.0))
    door_b = _door("HALL", "STUDY", "vertical", (5.5, 1.0))
    entrance = _entrance("LIVING", center_m=(2.5, 8.0))
    return _design([hall, living, study], [door_a, door_b], entrance)


def _corner_notch_design() -> GeometricDesign:
    """A door whose realized hinge sits exactly at a room's own corner — the CORNER shape, built
    deliberately (real generator doors virtually never hinge exactly at a corner; the full-corpus
    sweep found this once in 394 PLANNED contexts — `docs/DEAD_SPACE_SWEEP.md`). A second door
    serves HALL's own W end so this fixture measures CORNER alone, not also a STUB."""
    hall = _room("HALL", ("HALL", "CIRCULATION"), (0.0, 0.0, 3.0, 3.0))
    living = _room("LIVING", ("LIVING",), (3.0, 0.0, 6.0, 5.0), area=30.0)
    study = _room("STUDY", ("STUDY",), (-4.0, 0.0, 4.0, 4.0), area=16.0)
    corner_door = _door("HALL", "LIVING", "vertical", (3.0, 1.5), width_m=0.9, hinge_m=(3.0, 0.0))
    end_door = _door("HALL", "STUDY", "vertical", (0.0, 1.5))
    entrance = _entrance("LIVING", center_m=(6.0, 2.5))
    return _design([hall, living, study], [corner_door, end_door], entrance)


def _no_corner_design() -> GeometricDesign:
    """The SAME shape, the swing door hinged at the ordinary mid-wall position `doors.py` actually
    computes — CORNER must not fire here."""
    hall = _room("HALL", ("HALL", "CIRCULATION"), (0.0, 0.0, 3.0, 3.0))
    living = _room("LIVING", ("LIVING",), (3.0, 0.0, 6.0, 5.0), area=30.0)
    study = _room("STUDY", ("STUDY",), (-4.0, 0.0, 4.0, 4.0), area=16.0)
    mid_door = _door("HALL", "LIVING", "vertical", (3.0, 1.5), width_m=0.9, hinge_m=(3.0, 1.05))
    end_door = _door("HALL", "STUDY", "vertical", (0.0, 1.5))
    entrance = _entrance("LIVING", center_m=(6.0, 2.5))
    return _design([hall, living, study], [mid_door, end_door], entrance)


def _oversized_hall_design() -> GeometricDesign:
    """A HALL realized at 35 m2 — 5 m2 past `ROOM_TEMPLATES[HALL].hard_max` (30 m2)."""
    hall = _room("HALL", ("HALL", "CIRCULATION"), (0.0, 0.0, 7.0, 5.0), area=35.0)
    living = _room("LIVING", ("LIVING",), (0.0, 5.0, 6.0, 6.0), area=30.0)
    study = _room("STUDY", ("STUDY",), (0.0, -5.0, 7.0, 5.0), area=18.0)
    door_a = _door("HALL", "LIVING", "vertical", (0.0, 2.5))
    door_b = _door("HALL", "STUDY", "vertical", (7.0, 2.5))
    entrance = _entrance("LIVING", center_m=(3.0, 11.0))
    return _design([hall, living, study], [door_a, door_b], entrance)


@pytest.fixture(scope="module")
def canonical_design():
    out = tempfile.mktemp(suffix=".png")
    return run_demo(out).design


# --------------------------------------------------------------------------- AC-1


def test_finds_stub_and_sliver_not_transition_hall(canonical_design):
    stub = ds.measure(_corridor_stub_design())
    stub_regions = [r for r in stub.regions if r.kind == "STUB"]
    assert stub_regions
    # Both HALL ends are unserved: the W end (1.0 m, under any plausible threshold) and the E end
    # (5.0 m, the genuine stub this fixture exists to prove) — the longer one is what matters.
    worst = max(stub_regions, key=lambda r: r.length_m)
    assert worst.length_m == pytest.approx(5.0, abs=0.05)
    assert worst.accessible is False
    assert worst.zone_id == "HALL" and worst.role == "HALL"

    sliver = ds.measure(_sliver_design())
    sliver_kinds = [r.kind for r in sliver.regions]
    assert "SLIVER" in sliver_kinds
    sliver_region = next(r for r in sliver.regions if r.kind == "SLIVER")
    assert sliver_region.zone_id == "STORAGE"

    # A clean, fully-served design: nothing found at all.
    clean = ds.measure(_no_dead_space_design())
    assert clean.regions == () and clean.dead_space_m2 == 0.0

    # An open transition hall within its own template budget, both ends served: not flagged.
    transition = ds.measure(_transition_hall_within_budget_design())
    assert transition.regions == () and transition.dead_space_m2 == 0.0


def test_sliver_never_fires_on_a_c3_compliant_room():
    """`SLIVER_MIN_USABLE_WIDTH_M` sits below every `ROOM_TEMPLATES` minimum on purpose — proven
    directly against the template table, not merely "no corpus context happened to trip it"."""
    from app.vertical_slice.concept_generator import ROOM_TEMPLATES
    from app.vertical_slice.geometry_core.model import ProgramRole

    for role, template in ROOM_TEMPLATES.items():
        if role in (ProgramRole.HALL, ProgramRole.CIRCULATION):
            continue
        assert template.min_short_side_m >= ds.SLIVER_MIN_USABLE_WIDTH_M, role


def test_corner_notch_fires_only_when_the_hinge_is_at_a_corner():
    corner = ds.measure(_corner_notch_design())
    # The hinge (3.0, 0.0) sits at the shared corner of BOTH rooms the door connects (HALL's own
    # SE corner and LIVING's own SW corner) — a notch is real on each side of that corner.
    assert corner.regions and all(r.kind == "CORNER" for r in corner.regions)
    assert corner.regions[0].area_m2 == pytest.approx(0.9 ** 2 * (1 - 3.14159265 / 4), abs=0.01)

    clean = ds.measure(_no_corner_design())
    assert clean.regions == ()


def test_oversized_hall_only_counts_the_excess_past_budget():
    result = ds.measure(_oversized_hall_design())
    assert [r.kind for r in result.regions] == ["OVERSIZED_HALL"]
    region = result.regions[0]
    assert region.area_m2 == pytest.approx(5.0, abs=0.01)   # 35 - 30, not the whole 35
    assert region.accessible is True


def test_canonical_fixture_stays_under_the_c32_hard_limit(canonical_design):
    """`pipeline.run_demo()`'s own frozen baseline DOES measure a small, real STUB (its HALL_SPUR
    leg's own tolerated dead end, `docs/DEAD_SPACE_SWEEP.md`) — this is the correctness claim that
    fact supports: it stays well under the hard limit, never that nothing was measured."""
    metrics = ds.measure(canonical_design)
    for region in metrics.regions:
        if region.kind == "STUB":
            assert region.length_m < ds.DEAD_SPACE_STUB_HARD_LIMIT_M


def test_no_region_kind_or_zone_literal_hardcoded_for_a_specific_fixture():
    """Sanity: `measure` reasons only off role tuples and realized geometry, so it produces the
    SAME kind of finding on two structurally-identical designs with different zone ids."""
    renamed = _design(
        [_room("CORR", ("CIRCULATION",), (0.0, 0.0, 6.0, 1.3)),
         _room("ROOM_A", ("LIVING",), (0.0, 1.3, 4.0, 5.0), area=20.0)],
        [_door("CORR", "ROOM_A", "horizontal", (1.0, 1.3))],
        _entrance("ROOM_A", center_m=(2.0, 6.3)),
    )
    result = ds.measure(renamed)
    assert any(r.kind == "STUB" for r in result.regions)


# --------------------------------------------------------------------------- AC-2


def test_c32_fails_stub_fixture_and_passes_canonical(canonical_design):
    stub_defect = ds.classify_hard(ds.measure(_corridor_stub_design()))
    assert stub_defect is not None and "5.00" in stub_defect

    assert ds.classify_hard(ds.measure(canonical_design)) is None
    assert ds.classify_hard(ds.measure(_no_dead_space_design())) is None
    assert ds.classify_hard(ds.measure(_transition_hall_within_budget_design())) is None
    # SLIVER/CORNER/OVERSIZED_HALL never gate C32 — only STUB does.
    assert ds.classify_hard(ds.measure(_sliver_design())) is None
    assert ds.classify_hard(ds.measure(_corner_notch_design())) is None
    assert ds.classify_hard(ds.measure(_oversized_hall_design())) is None


def test_c32_appears_in_the_check_list(canonical_design):
    del canonical_design
    result = run_demo(tempfile.mktemp(suffix=".png"))
    assert "C32" in [c.check_id for c in result.validation.checks]


def test_c32_gate_actually_blocks_the_plan_when_the_calibrated_limit_is_tightened(monkeypatch):
    """The calibrated threshold passes every real candidate this generator produces (see the
    constant's own rationale, `docs/DEAD_SPACE_SWEEP.md`) — proving C32 genuinely FAILS a plan
    therefore means tightening the limit below a REAL realized plan's own measured value, then
    re-running the same `validate()` call the pipeline uses, on the SAME realized geometry — the
    same discipline `test_circulation_metrics.py`'s own C26 gate test uses."""
    spec = demo_spec()
    concept = concept_stage.build_concept(spec)
    solve = solve_fixture(concept.fixture)
    entrance_local_x = (solve.rects[concept.entrance_zone_id].x
                        + solve.rects[concept.entrance_zone_id].w // 2)
    site = site_stage.build_site_plan(spec, concept.footprint_width_m, concept.footprint_depth_m,
                                      entrance_local_x)
    rects = site_stage.translate_rects(solve.rects, site.footprint_offset_u)
    interior_doors = doors_stage.generate_interior_doors(concept.fixture, rects)
    entrance_door = doors_stage.build_entrance_door(site.entrance, site.footprint)
    windows = windows_stage.generate_windows(concept.fixture, rects, site.footprint)
    furniture = furniture_stage.check_furniture_feasibility(concept.fixture, rects, solve.walls)

    before = validation_stage.validate(concept.fixture, rects, solve.walls, interior_doors,
                                       entrance_door, windows, furniture, site,
                                       wet_rooms=resolve_wet_rooms(spec.program))
    c32_before = next(c for c in before.checks if c.check_id == "C32")
    assert c32_before.passed

    monkeypatch.setattr(ds, "DEAD_SPACE_STUB_HARD_LIMIT_M", 0.1)
    after = validation_stage.validate(concept.fixture, rects, solve.walls, interior_doors,
                                      entrance_door, windows, furniture, site,
                                      wet_rooms=resolve_wet_rooms(spec.program))
    c32_after = next(c for c in after.checks if c.check_id == "C32")
    assert not c32_after.passed
    assert not after.ok


# --------------------------------------------------------------------------- QualityOut.metrics


def test_quality_out_metrics_reports_measured_dead_space():
    from app.demo import service as svc
    from tests.vertical_slice.test_hub_guard import WIDE_SQUARE, _project

    result = svc.generate_demo_design(_project(WIDE_SQUARE))
    metrics = result.design.quality.metrics
    assert metrics is not None
    assert hasattr(metrics, "dead_space_m2") and hasattr(metrics, "dead_space_share")
    assert metrics.dead_space_m2 >= 0.0
    assert 0.0 <= metrics.dead_space_share <= 1.0


# --------------------------------------------------------------------------- the ranking term


def test_ranking_prefers_less_dead_space():
    less = ds.DeadSpaceMetrics(regions=(), dead_space_m2=1.0, dead_space_share=0.01)
    more = ds.DeadSpaceMetrics(regions=(), dead_space_m2=3.0, dead_space_share=0.03)
    assert ds.dead_space_prefers(more, less) is None
    reason = ds.dead_space_prefers(less, more)
    assert reason is not None and "not less" in reason


def test_ranking_equal_dead_space_is_not_a_preference():
    a = ds.DeadSpaceMetrics(regions=(), dead_space_m2=1.0, dead_space_share=0.01)
    b = ds.DeadSpaceMetrics(regions=(), dead_space_m2=1.0, dead_space_share=0.01)
    assert ds.dead_space_prefers(a, b) is not None
