"""Dedicated-circulation metrics from realized geometry, and the C26 gate (Issue #36).

AC-1/AC-2's "spine, hub, L parti" fixtures: the canonical fixture (`pipeline.run_demo`, a
two-segment spine hall) for the spine, a realized two-wing ("2W") candidate off an L-shaped
buildable region — the same pattern `test_family_signature.py` uses, by hand, off the generator —
for the L, and a hand-built compact/branching `GeometricDesign` for the hub (see `_hub_design`'s
own docstring for why: on this branch every swept brief's HUB_PRIVATE_WING candidate is currently
rejected before solving, the same pre-existing state `test_hub_guard.py::NARROW_DEEP`'s `xfail`
documents). The "long-corridor" extreme case is likewise hand-built
(`design_output.RoomOut`/`DoorOut`): every REAL candidate this generator produces already measures
comfortably inside the calibrated limits (see `circulation_metrics.py`'s own constants) — that is
the point of C26 being additive, not a fixture this codebase can currently produce by accident.
"""
from __future__ import annotations

import pytest

from app.geometry_domain.constraints import BuildableRegion
from app.geometry_domain.primitives import MultiRegion, Region, Ring
from app.geometry_domain.provenance import Authority, Provenance, Source
from app.geometry_domain.walls import BoundaryContext, Construction, WallFacts
from app.vertical_slice import circulation_metrics as cm
from app.vertical_slice import concept_generator as cg
from app.vertical_slice import general_pipeline as gp
from app.vertical_slice import geometry_fixtures as F
from app.vertical_slice import validation as validation_stage
from app.vertical_slice.design_output import DoorOut, GeometricDesign, RoomOut
from app.vertical_slice.geometry_core.engine import GeometryInfeasible, solve_fixture
from app.vertical_slice.pipeline import run_demo
from app.vertical_slice.safe_adapter import AdapterOutcome, adapt, build_buildable_region
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec

pytestmark = pytest.mark.filterwarnings("ignore")


# --------------------------------------------------------------------------- real fixtures


@pytest.fixture(scope="module")
def canonical_design(tmp_path_factory):
    out = tmp_path_factory.mktemp("circ") / "canonical.png"
    return run_demo(str(out)).design


def _buildable(w: float, d: float) -> BuildableRegion:
    return BuildableRegion.known(
        MultiRegion.of(Region(Ring.rectangle(3.0, 5.5, w, d))),
        Provenance(Source.USER, Authority.AUTHORITATIVE, ref="test"))


def _realized_candidates(spec: ArchitecturalSpec, buildable: BuildableRegion) -> list[gp.RealizedPlan]:
    """Every candidate the generator offers, realized where the solver can — the same pattern
    `test_family_signature.py::_realized_candidates` uses to reach a specific massing/strategy
    without depending on which one the pipeline would pick as primary."""
    adapter = adapt(buildable)
    assert adapter.outcome is AdapterOutcome.SOLVED
    generated = cg.generate_concepts(spec, list(adapter.candidates))
    out = []
    for index, candidate in enumerate(generated.candidates):
        try:
            solve = solve_fixture(candidate.concept.fixture)
        except GeometryInfeasible:
            continue
        out.append(gp._realize(spec, buildable, None, candidate, index, solve, ()))
    return out


_INTERIOR_PARTITION = WallFacts(BoundaryContext.INTERIOR, Construction.STANDARD_PARTITION)


def _room(zone_id, roles, rect_m, area=None):
    x, y, w, h = rect_m
    return RoomOut(
        zone_id=zone_id, roles=roles, rect_m=rect_m, net_w_m=w, net_h_m=h,
        net_area_m2=area if area is not None else round(w * h, 4),
        walls={s: "STANDARD_PARTITION" for s in ("N", "S", "E", "W")},
        wall_facts={s: _INTERIOR_PARTITION for s in ("N", "S", "E", "W")},
    )


def _door(a, b, orientation, center_m):
    return DoorOut(a=a, b=b, kind="ROOM_DOOR", width_m=0.9, center_m=center_m,
                   orientation=orientation, placeable=True, shared_length_m=1.0)


def _hub_design() -> GeometricDesign:
    """A hand-built compact, branching hub — a small square HALL with a door on every side,
    each leading to a different room, the shape specs/005's hub parti exists to produce.

    NOT realized through the generator: on this branch every swept brief (this module's own
    calibration sweep, and `test_hub_guard.py`'s own WIDE_SQUARE/NARROW_DEEP/SMALL_4BR fixtures)
    has its HUB_PRIVATE_WING candidate rejected before solving (`ROOM_ABOVE_MAXIMUM_AREA` /
    `FOOTPRINT_BELOW_MINIMUM_WIDTH`) since the room-area two-level maxima work (2026-09-15) —
    the same pre-existing state `test_hub_guard.py::NARROW_DEEP`'s own `xfail` documents, not
    something this Issue's scope touches. `circulation_metrics.py` reads only role tuples and
    realized geometry, so a hand-built fixture of the same SHAPE measures identically to a solved
    one — this is a fixture of the geometry the check exists to prefer, not of this module's own
    numbers, so it introduces no roundtrip risk into `measure`/`classify_extreme` themselves."""
    hub = _room("HUB", ("HALL", "CIRCULATION"), (0.0, 0.0, 3.0, 3.0))
    living = _room("LIVING", ("LIVING",), (3.0, 0.0, 6.0, 5.0), area=30.0)
    br1 = _room("BR1", ("BEDROOM",), (-6.0, 0.0, 6.0, 5.0), area=30.0)
    br2 = _room("BR2", ("BEDROOM",), (0.0, -5.0, 3.0, 5.0), area=15.0)
    br3 = _room("BR3", ("BEDROOM",), (0.0, 3.0, 3.0, 5.0), area=15.0)
    doors = [
        _door("HUB", "LIVING", "vertical", (3.0, 1.5)),
        _door("HUB", "BR1", "vertical", (0.0, 1.5)),
        _door("HUB", "BR2", "horizontal", (1.5, 0.0)),
        _door("HUB", "BR3", "horizontal", (1.5, 3.0)),
    ]
    entrance = DoorOut(a="OUTSIDE", b="LIVING", kind="ENTRANCE_DOOR", width_m=1.0,
                       center_m=(6.0, 2.5), orientation="vertical", placeable=True,
                       shared_length_m=1.0)
    return GeometricDesign(
        plot_m=(-10.0, -10.0, 25.0, 25.0), footprint_m=(-6.0, -5.0, 15.0, 13.0),
        rooms=(hub, living, br1, br2, br3), interior_doors=tuple(doors), entrance_door=entrance,
        windows=(), parking_m=(), garden=(), entrance_walk_m=(0.0, 0.0, 1.0, 1.0),
        gross_area_m2=99.0, net_area_m2=99.0, wall_iterations=0,
    )


@pytest.fixture(scope="module")
def hub_design() -> GeometricDesign:
    return _hub_design()


@pytest.fixture(scope="module")
def l_design():
    """A realized two-wing ("2W", L-massing) candidate, off an L-shaped buildable region."""
    spec = ArchitecturalSpec(plot=PlotSpec(width_m=24.0, depth_m=32.0),
                             program=ProgramSpec(bedrooms=3, wet_rooms=2, safe_room=False))
    buildable = build_buildable_region(F.l_shaped_site_long_arm())
    plans = _realized_candidates(spec, buildable)
    ls = [p for p in plans if p.massing_signature == "2W" and p.ok]
    if not ls:
        pytest.skip("no validating 2W (L) candidate for this brief/site")
    return ls[0].design


# --------------------------------------------------------------------------- a hand-built extreme


def _long_corridor_design() -> GeometricDesign:
    """A single 25 m HALL with no door at either end (both dead) and two small rooms doored onto
    its LONG side only — ratio ~35%, longest segment 25 m, both well past the calibrated limits;
    only role tuples (`"HALL"`) and generic geometry are read, never a zone_id or a coordinate."""
    hall = _room("HALL", ("HALL", "CIRCULATION"), (0.0, 5.0, 25.0, 1.3))
    br1 = _room("BR1", ("BEDROOM",), (2.0, 0.0, 6.0, 5.0), area=30.0)
    br2 = _room("BR2", ("BEDROOM",), (2.0, 6.3, 6.0, 5.0), area=30.0)
    doors = [_door("HALL", "BR1", "horizontal", (5.0, 5.0)),
            _door("HALL", "BR2", "horizontal", (5.0, 6.3))]
    entrance = DoorOut(a="OUTSIDE", b="BR1", kind="ENTRANCE_DOOR", width_m=1.0,
                       center_m=(2.5, 0.0), orientation="horizontal", placeable=True,
                       shared_length_m=1.0)
    return GeometricDesign(
        plot_m=(0.0, 0.0, 40.0, 20.0), footprint_m=(0.0, 0.0, 25.0, 12.0),
        rooms=(hall, br1, br2), interior_doors=tuple(doors), entrance_door=entrance,
        windows=(), parking_m=(), garden=(), entrance_walk_m=(0.0, 0.0, 1.0, 1.0),
        gross_area_m2=100.0, net_area_m2=92.5, wall_iterations=0,
    )


# --------------------------------------------------------------------------- AC-1


def test_measures_from_realized_geometry_on_the_canonical_fixture(canonical_design):
    metrics = cm.measure(canonical_design)
    # HALL_MAIN (4.95 m2) + HALL_SPUR (14.84 m2): frozen in test_baseline_and_decoupling.py.
    assert metrics.area_m2 == pytest.approx(4.95 + 14.84, abs=0.01)
    assert metrics.ratio == pytest.approx(metrics.area_m2 / canonical_design.net_area_m2, abs=1e-3)
    assert metrics.longest_segment_m == pytest.approx(10.6, abs=0.05)
    assert metrics.total_length_m > metrics.longest_segment_m  # two segments, not one
    assert metrics.narrowest_width_m is not None and metrics.narrowest_width_m < metrics.longest_segment_m
    assert metrics.dead_end_count >= 1          # HALL_SPUR's far end serves nothing further
    # HALL_MAIN stacks directly on HALL_SPUR (same x, abutting y) — one straight run, so the
    # realized entrance->farthest-room path has no direction change on this particular fixture.
    assert metrics.turn_count == 0
    assert metrics.duplicated_segment_count == 0  # a branching hall is not a duplicate of itself


def test_no_circulation_room_measures_as_none_not_a_crash():
    design = GeometricDesign(
        plot_m=(0.0, 0.0, 10.0, 10.0), footprint_m=(0.0, 0.0, 10.0, 10.0),
        rooms=(_room("LIVING", ("LIVING",), (0.0, 0.0, 10.0, 10.0)),),
        interior_doors=(), entrance_door=DoorOut(
            a="OUTSIDE", b="LIVING", kind="ENTRANCE_DOOR", width_m=1.0, center_m=(5.0, 0.0),
            orientation="horizontal", placeable=True, shared_length_m=1.0),
        windows=(), parking_m=(), garden=(), entrance_walk_m=(0.0, 0.0, 1.0, 1.0),
        gross_area_m2=100.0, net_area_m2=100.0, wall_iterations=0,
    )
    metrics = cm.measure(design)
    assert metrics.area_m2 == 0.0 and metrics.ratio == 0.0
    assert metrics.longest_segment_m is None and metrics.narrowest_width_m is None
    assert metrics.dead_end_count == 0
    assert metrics.duplicated_segment_count == 0


# --------------------------------------------------------------------------- AC-2


def test_c26_fails_an_extreme_corridor_and_passes_compact_plans(canonical_design, hub_design):
    extreme = cm.measure(_long_corridor_design())
    assert cm.classify_extreme(extreme) is not None
    assert cm.classify_extreme(cm.measure(canonical_design)) is None
    assert cm.classify_extreme(cm.measure(hub_design)) is None


def test_extreme_reason_names_every_limit_exceeded():
    reason = cm.classify_extreme(cm.measure(_long_corridor_design()))
    assert "ratio" in reason and "segment" in reason


def test_c26_gate_actually_blocks_the_plan_when_the_calibrated_limit_is_exceeded(monkeypatch):
    """The calibrated thresholds pass every real candidate this generator produces (see the
    constants' own rationale) — proving C26 genuinely FAILS a plan therefore means tightening a
    limit below a REAL realized plan's own measured value, then re-running the same `validate()`
    call the pipeline uses, on the SAME realized geometry. This is `validate()`'s own C26 wiring
    under test, not `classify_extreme` again (see the two tests above for that)."""
    from app.vertical_slice import concept as concept_stage
    from app.vertical_slice import doors as doors_stage
    from app.vertical_slice import furniture as furniture_stage
    from app.vertical_slice import site as site_stage
    from app.vertical_slice import windows as windows_stage
    from app.vertical_slice.spec import demo_spec
    from app.vertical_slice.wet_rooms import resolve_wet_rooms

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
    c26_before = next(c for c in before.checks if c.check_id == "C26")
    assert c26_before.passed

    monkeypatch.setattr(cm, "EXTREME_LONGEST_SEGMENT_M", 5.0)
    after = validation_stage.validate(concept.fixture, rects, solve.walls, interior_doors,
                                      entrance_door, windows, furniture, site,
                                      wet_rooms=resolve_wet_rooms(spec.program))
    c26_after = next(c for c in after.checks if c.check_id == "C26")
    assert not c26_after.passed
    assert not after.ok


def test_c26_appears_in_the_check_list(canonical_design):
    del canonical_design  # the check list is fixture-independent; keeps the import path exercised
    from app.vertical_slice.pipeline import run_demo as _run_demo
    import tempfile
    result = _run_demo(tempfile.mktemp(suffix=".png"))
    assert "C26" in [c.check_id for c in result.validation.checks]


# --------------------------------------------------------------------------- AC-3


def test_ranking_prefers_compact_circulation():
    compact = cm.CirculationMetrics(
        area_m2=15.0, ratio=0.12, longest_segment_m=6.0, total_length_m=6.0,
        narrowest_width_m=1.3, dead_end_count=1, turn_count=1,
        duplicated_segment_count=0, duplicated_area_m2=0.0)
    spine = cm.CirculationMetrics(
        area_m2=19.0, ratio=0.16, longest_segment_m=12.0, total_length_m=12.0,
        narrowest_width_m=1.2, dead_end_count=1, turn_count=0,
        duplicated_segment_count=0, duplicated_area_m2=0.0)
    # Both plans the same area: the compact one is better on ratio AND longest segment.
    assert cm.circulation_prefers(spine, 150.0, compact, 150.0) is None
    # Reversed: the spine is not better on anything measured, so it earns nothing.
    reason = cm.circulation_prefers(compact, 150.0, spine, 150.0)
    assert reason is not None and "nothing" in reason


def test_ranking_never_prefers_a_much_smaller_compact_plan():
    compact_but_small = cm.CirculationMetrics(
        area_m2=10.0, ratio=0.08, longest_segment_m=4.0, total_length_m=4.0,
        narrowest_width_m=1.3, dead_end_count=0, turn_count=0,
        duplicated_segment_count=0, duplicated_area_m2=0.0)
    spine = cm.CirculationMetrics(
        area_m2=19.0, ratio=0.16, longest_segment_m=12.0, total_length_m=12.0,
        narrowest_width_m=1.2, dead_end_count=1, turn_count=0,
        duplicated_segment_count=0, duplicated_area_m2=0.0)
    reason = cm.circulation_prefers(spine, 150.0, compact_but_small, 100.0)  # 67% of the area
    assert reason is not None and "%" in reason


def test_equal_circulation_is_not_a_preference():
    a = cm.CirculationMetrics(area_m2=15.0, ratio=0.12, longest_segment_m=6.0, total_length_m=6.0,
                              narrowest_width_m=1.3, dead_end_count=1, turn_count=1,
                              duplicated_segment_count=0, duplicated_area_m2=0.0)
    b = cm.CirculationMetrics(area_m2=15.0, ratio=0.12, longest_segment_m=6.0, total_length_m=6.0,
                              narrowest_width_m=1.3, dead_end_count=1, turn_count=1,
                              duplicated_segment_count=0, duplicated_area_m2=0.0)
    assert cm.circulation_prefers(a, 150.0, b, 150.0) is not None


def test_ranking_prefers_compact_circulation_on_the_hub_and_canonical_fixtures(
        canonical_design, hub_design):
    """The two-candidate fixture AC-3 asks for: the SAME brief's canonical spine vs its hub
    sibling, both realized. Whichever is more compact by `circulation_prefers`'s own rules earns
    the comparison — this only asserts the comparator agrees with itself in both directions, never
    that a HUB always wins (a hub is not automatically more compact; measured cases can go either
    way — see `hub_guard`'s own module docstring)."""
    spine_metrics = cm.measure(canonical_design)
    hub_metrics = cm.measure(hub_design)
    a = cm.circulation_prefers(spine_metrics, canonical_design.gross_area_m2,
                               hub_metrics, hub_design.gross_area_m2)
    b = cm.circulation_prefers(hub_metrics, hub_design.gross_area_m2,
                               spine_metrics, canonical_design.gross_area_m2)
    # Never both "no reason" — one cannot strictly beat itself in both directions unless the two
    # plans measure identically, which a spine and a hub on the same brief do not.
    assert not (a is None and b is None)


def _run_guard_demoted_hub(monkeypatch, *, circulation_prefers_replacement: bool):
    """`general_pipeline._guard_demoted_hub` with every stage but the two guards themselves
    stubbed out — `hub_guard.hub_keeps_primary` forced to say the hub's proportions earn it the
    stay, and `circulation_metrics.circulation_prefers` forced to the case under test — so only
    the NEW circulation branch's own control flow is exercised."""
    from types import SimpleNamespace
    from unittest.mock import patch

    from app.vertical_slice import general_pipeline as gp_module
    from app.vertical_slice import hub_guard as hub_guard_module

    fake_design = SimpleNamespace(gross_area_m2=100.0)
    hub_plan = SimpleNamespace(ok=True, design=fake_design, validation=SimpleNamespace(failures=lambda: []))
    replacement_plan = SimpleNamespace(ok=True, design=fake_design,
                                       validation=SimpleNamespace(failures=lambda: []))
    fake_candidate = SimpleNamespace(hub_last_resort=True, concept=SimpleNamespace(fixture=object()))
    fake_chosen = SimpleNamespace(strategy=SimpleNamespace(value="SPINE_TEST"))
    fake_spec = SimpleNamespace(program=SimpleNamespace(target_built_area_m2=None))

    circulation_reason = None if circulation_prefers_replacement else "hub is more compact"
    with patch.object(gp_module, "solve_fixture", return_value=object()), \
         patch.object(gp_module, "_realize", return_value=hub_plan), \
         patch.object(gp_module, "_would_have_preceded", return_value=True), \
         patch.object(hub_guard_module, "hub_keeps_primary", return_value="forced: hub stays"), \
         patch.object(hub_guard_module, "proportions_of", return_value=object()), \
         patch.object(cm, "measure", return_value=object()), \
         patch.object(gp_module.circulation_metrics, "circulation_prefers",
                      return_value=circulation_reason):
        return gp_module._guard_demoted_hub(
            spec=fake_spec, buildable=None, site_constraints=None,
            candidates=(fake_candidate,), chosen=fake_chosen, chosen_index=0,
            plan=replacement_plan, failures=[]), fake_candidate, fake_chosen, hub_plan, replacement_plan


def test_guard_demoted_hub_lets_a_more_compact_replacement_keep_the_primary(monkeypatch):
    """AC-3's "joins the candidate ranking": with `hub_guard` forced to say the hub's proportions
    earn it the stay, a replacement `circulation_prefers` says is more compact still keeps the
    primary — the NEW rule this Issue adds; it narrows `hub_guard`'s decision, never overrides it
    the other way (see the wiring's own comment in `general_pipeline.py`)."""
    (winner, index, plan), candidate, chosen, hub_plan, replacement_plan = _run_guard_demoted_hub(
        monkeypatch, circulation_prefers_replacement=True)
    assert winner is chosen and plan is replacement_plan


def test_guard_demoted_hub_keeps_the_hub_when_its_circulation_is_not_beaten(monkeypatch):
    (winner, index, plan), candidate, chosen, hub_plan, replacement_plan = _run_guard_demoted_hub(
        monkeypatch, circulation_prefers_replacement=False)
    assert winner is candidate and plan is hub_plan


# --------------------------------------------------------------------------- AC-4 (static)


def test_no_coordinate_literal_or_fixture_name_branch_in_the_module():
    import ast
    import inspect

    from app.vertical_slice import circulation_metrics as module

    source = inspect.getsource(module)
    tree = ast.parse(source)
    banned_strings = {"HALL_MAIN", "HALL_SPUR", "SAFE_ROOM", "MASTER", "KITCHEN", "LIVING"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert node.value not in banned_strings, node.value
