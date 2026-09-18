"""C19/C8 — exposure policy decoupled from window fit (Issue #19).

A hand-built 3x3-style grid (a left column, a right column, and a middle column split into
three rows) is used instead of `solve_fixture`/the row-fixture helper `test_access_rules.py`
uses: a single row always keeps every zone on the N/S envelope (the row spans the full depth),
so it cannot produce a genuinely INTERIOR room — the exact defect C19 exists to catch. Here the
middle row of the middle column (`CENTER`) touches none of the four wing edges.
"""
from __future__ import annotations

from app.vertical_slice import site as site_stage
from app.vertical_slice.doors import Door
from app.vertical_slice.geometry_adapter import envelope_sides
from app.vertical_slice.geometry_core.model import (
    ConnectionKind,
    Cut,
    DesiredAccessTopology,
    Fixture,
    Leaf,
    ProgramRole,
    Rect,
    Side,
    Split,
    WallType,
    Wing,
    ZoneSpec,
    m_to_u,
)
from app.vertical_slice.site import SitePlan
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec
from app.vertical_slice.validation import validate
from app.vertical_slice.windows import generate_windows
from app.vertical_slice.pipeline import run_demo

_GRID_LEG_M = 3.0
_LOOSE = dict(net_area_min_m2=1.0, net_area_target_m2=9.0, net_area_max_m2=99.0,
             min_short_side_m=0.1, max_aspect_ratio=99.0)


def _grid_fixture(center_roles: tuple[ProgramRole, ...]) -> tuple[Fixture, dict[str, Rect], Rect]:
    """A|TOP/CENTER/BOTTOM|C, each leg `_GRID_LEG_M` — see module docstring."""
    leg_u = m_to_u(_GRID_LEG_M)
    rects = {
        "A": Rect(0, 0, leg_u, 3 * leg_u),
        "TOP": Rect(leg_u, 0, leg_u, leg_u),
        "CENTER": Rect(leg_u, leg_u, leg_u, leg_u),
        "BOTTOM": Rect(leg_u, 2 * leg_u, leg_u, leg_u),
        "C": Rect(2 * leg_u, 0, leg_u, 3 * leg_u),
    }
    footprint = Rect(0, 0, 3 * leg_u, 3 * leg_u)
    tree = Split(Cut.V, Leaf("A"),
                Split(Cut.V,
                      Split(Cut.H, Leaf("TOP"), Split(Cut.H, Leaf("CENTER"), Leaf("BOTTOM"), None), None),
                      Leaf("C"), None),
                None)
    wing = Wing("W", 0, 0, footprint.w, footprint.h, tree)
    specs = (
        ZoneSpec("A", (ProgramRole.STORAGE,), **_LOOSE),
        ZoneSpec("TOP", (ProgramRole.STORAGE,), **_LOOSE),
        ZoneSpec("CENTER", center_roles, **_LOOSE),
        ZoneSpec("BOTTOM", (ProgramRole.STORAGE,), **_LOOSE),
        ZoneSpec("C", (ProgramRole.STORAGE,), **_LOOSE),
    )
    fixture = Fixture("GRID", (wing,), specs, DesiredAccessTopology(()))
    return fixture, rects, footprint


def _validate_grid(center_roles: tuple[ProgramRole, ...]):
    fixture, rects, footprint = _grid_fixture(center_roles)
    walls = {
        (zone_id, side): (WallType.EXTERIOR if side in envelope_sides(rect, footprint)
                          else WallType.PARTITION)
        for zone_id, rect in rects.items() for side in Side
    }
    windows = generate_windows(fixture, rects, footprint)
    spec = ArchitecturalSpec(plot=PlotSpec(30.0, 30.0), program=ProgramSpec())
    plot = Rect(0, 0, m_to_u(30.0), m_to_u(30.0))
    entrance = site_stage.build_entrance(footprint, footprint.x + footprint.w // 2)
    site = SitePlan(plot, footprint, (footprint.x, footprint.y), (), entrance,
                    site_stage.classify_garden(spec, plot, footprint, ()))
    dummy_entrance_door = Door("OUTSIDE", "A", ConnectionKind.DOOR, 1.0, (0, 0), "horizontal",
                               False, 0.0)
    return validate(fixture, rects, walls, [], dummy_entrance_door, windows, [], site,
                    skip_site_checks=True)


def _check(report, check_id: str):
    return next(c for c in report.checks if c.check_id == check_id)


def test_c19_fails_on_interior_bedroom_and_passes_on_canonical_fixtures(tmp_path):
    report = _validate_grid((ProgramRole.BEDROOM,))
    c19 = _check(report, "C19")
    assert not c19.passed
    assert "CENTER" in c19.detail

    result = run_demo(str(tmp_path / "canonical.svg"))
    c19_canonical = _check(result.validation, "C19")
    assert c19_canonical.passed, c19_canonical.detail


def test_c8_still_fails_when_the_exterior_wall_is_too_short():
    """`A` is BEDROOM here, a 0.6 x 0.6 m corner room: it has two real exterior walls (west and
    north — C19 passes) but each is only 0.6 m long, short of `WINDOW_MIN_WIDTH_M` (0.9 m) — no
    side of `A` can take a window, so C8 fails while C19 passes for the same room."""
    leg_u = m_to_u(_GRID_LEG_M)
    narrow_u = m_to_u(0.6)
    rects = {
        "A": Rect(0, 0, narrow_u, narrow_u),
        "REST": Rect(narrow_u, 0, leg_u * 3 - narrow_u, leg_u),
    }
    footprint = Rect(0, 0, leg_u * 3, leg_u)
    tree = Split(Cut.V, Leaf("A"), Leaf("REST"), None)
    wing = Wing("W", 0, 0, footprint.w, footprint.h, tree)
    specs = (
        ZoneSpec("A", (ProgramRole.BEDROOM,), **_LOOSE),
        ZoneSpec("REST", (ProgramRole.STORAGE,), **_LOOSE),
    )
    fixture = Fixture("SHORTWALL", (wing,), specs, DesiredAccessTopology(()))
    walls = {
        (zone_id, side): (WallType.EXTERIOR if side in envelope_sides(rect, footprint)
                          else WallType.PARTITION)
        for zone_id, rect in rects.items() for side in Side
    }
    windows = generate_windows(fixture, rects, footprint)
    spec = ArchitecturalSpec(plot=PlotSpec(30.0, 30.0), program=ProgramSpec())
    plot = Rect(0, 0, m_to_u(30.0), m_to_u(30.0))
    entrance = site_stage.build_entrance(footprint, footprint.x + footprint.w // 2)
    site = SitePlan(plot, footprint, (footprint.x, footprint.y), (), entrance,
                    site_stage.classify_garden(spec, plot, footprint, ()))
    dummy_entrance_door = Door("OUTSIDE", "A", ConnectionKind.DOOR, 1.0, (0, 0), "horizontal",
                               False, 0.0)
    report = validate(fixture, rects, walls, [], dummy_entrance_door, windows, [], site,
                      skip_site_checks=True)
    c19 = _check(report, "C19")
    c8 = _check(report, "C8")
    assert c19.passed, c19.detail
    assert not c8.passed
    assert "A" in c8.detail


def test_family_room_and_study_get_windows():
    for role in (ProgramRole.FAMILY_ROOM, ProgramRole.STUDY):
        report = _validate_grid((role,))
        c19 = _check(report, "C19")
        assert not c19.passed and "CENTER" in c19.detail, (role, c19.detail)

        fixture, rects, footprint = _grid_fixture((role,))
        # Move CENTER's role onto an exterior leg (`A`, full west envelope) instead, so the same
        # role's window can actually be placed.
        exterior_fixture = Fixture("GRID_EXT", fixture.wings,
                                   tuple(ZoneSpec(z.zone_id, (role,) if z.zone_id == "A" else z.roles,
                                                  **_LOOSE) for z in fixture.zones),
                                   DesiredAccessTopology(()))
        windows = generate_windows(exterior_fixture, rects, footprint)
        window = next(w for w in windows if w.zone_id == "A")
        assert window.placeable, window
        assert window.width_m > 0
