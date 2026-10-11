"""Issue #142G — SAFE_ROOM RC walls in the rectilinear realizer (GridWing path).

C4 (unchanged) requires every side of a SAFE_ROOM zone to be RC_SAFE_ROOM and its NET area (after
the 0.15 m RC insets) to meet the regulated minimum. The realizer now types walls with the Geometry
Core's precedence OPEN > RC_SAFE_ROOM > EXTERIOR > PARTITION, derived from the realized rects: the
safe room's own four sides, and every neighbour side that shares a boundary with it. The sizing and
the grid gate measure net with the same insets, so a plan that passes the gate passes C4's net check.
"""
from __future__ import annotations

from app.vertical_slice import rectilinear_realizer as rr
from app.vertical_slice.band_sizing import rc_sides_from_rows, solve_band_layout
from app.vertical_slice.geometry_core.engine import net_rect_m
from app.vertical_slice.geometry_core.model import ProgramRole, Side, WallType
from app.vertical_slice.rectilinear_realizer import (
    GridCell,
    GridWing,
    RealizationIntent,
    RealizedLayout,
    ZoneIntent,
    realize_layout,
)


def _zi(zid, role, target, lo, hi, short=2.4, aspect=2.5):
    return ZoneIntent(zid, role, target, lo, hi, short, aspect)


ZONES = {
    "LIVING": _zi("LIVING", ProgramRole.LIVING, 26.0, 16.0, 46.0, 3.0),
    "KITCHEN": _zi("KITCHEN", ProgramRole.KITCHEN, 13.0, 9.0, 26.0, 2.4),
    "HALL": _zi("HALL", ProgramRole.HALL, 7.0, 5.0, 12.0, 1.2),
    "BEDROOM_1": _zi("BEDROOM_1", ProgramRole.BEDROOM, 12.0, 9.0, 14.0, 2.6),
    "BEDROOM_2": _zi("BEDROOM_2", ProgramRole.BEDROOM, 12.0, 9.0, 14.0, 2.6),
    "SAFE_ROOM": _zi("SAFE_ROOM", ProgramRole.SAFE_ROOM, 10.5, 9.0, 14.0, 2.4),
}
#: street band: LIVING + KITCHEN; middle: HALL + BEDROOM_1; bottom: SAFE_ROOM + BEDROOM_2 (safe room on
#: the envelope, touching HALL above and BEDROOM_2 beside it — so RC sides appear on N/S and W/E neighbours)
BANDS = (("LIVING", "KITCHEN"), ("HALL", "BEDROOM_1"), ("SAFE_ROOM", "BEDROOM_2"))
EDGES = [("LIVING", "KITCHEN"), ("LIVING", "HALL"), ("KITCHEN", "HALL"), ("HALL", "BEDROOM_1"),
         ("HALL", "SAFE_ROOM"), ("HALL", "BEDROOM_2"), ("SAFE_ROOM", "BEDROOM_2")]


def _realize():
    sz = solve_band_layout(BANDS, ZONES, EDGES, w_max_m=14.0, h_max_m=14.0)
    assert sz.status == "FEASIBLE", sz
    W, H = round(sum(sz.col_w_u) * 0.05, 2), round(sum(sz.row_h_u) * 0.05, 2)
    wing = GridWing("T", W, H, sz.n_cols, tuple(tuple(GridCell(z, s) for z, s in r) for r in sz.rows), ZONES)
    return realize_layout(RealizationIntent(name="T", wings=(wing,)))


def test_safe_room_walls_are_rc_on_all_sides_and_c4_passes():
    res = _realize()
    assert isinstance(res, RealizedLayout), res
    sides = {s: res.walls[("SAFE_ROOM", s)] for s in Side}
    assert all(v is WallType.RC_SAFE_ROOM for v in sides.values()), sides
    c4 = next(c for c in res.report.checks if c.check_id == "C4")
    assert c4.passed, c4.detail
    assert res.report.ok


def test_neighbour_sides_facing_the_safe_room_are_rc_and_nothing_else():
    res = _realize()
    assert isinstance(res, RealizedLayout), res
    rects, walls = res.rects, res.walls
    safe = rects["SAFE_ROOM"]
    for zid, rect in rects.items():
        if zid == "SAFE_ROOM":
            continue
        for s in Side:
            touches_safe = rect.shared_edge_len_u(safe) > 0 and rr._side_between(rect, safe) == s
            if touches_safe:
                assert walls[(zid, s)] is WallType.RC_SAFE_ROOM, (zid, s)
            else:
                assert walls[(zid, s)] is not WallType.RC_SAFE_ROOM, (zid, s)
    # the safe room's exterior side is still a safe-room wall (precedence RC > EXTERIOR)
    assert walls[("SAFE_ROOM", Side.S)] is WallType.RC_SAFE_ROOM


def test_safe_room_still_has_a_real_door_and_a_window():
    res = _realize()
    assert isinstance(res, RealizedLayout), res
    doors = [d for d in res.interior_doors if "SAFE_ROOM" in (d.a, d.b) and d.placeable]
    assert doors, "a safe room must still be entered through a real door"
    assert any(w.zone_id == "SAFE_ROOM" and w.placeable for w in res.windows)
    for cid in ("C5", "C24", "C8", "C19", "C33"):
        chk = next(c for c in res.report.checks if c.check_id == cid)
        assert chk.passed, (cid, chk.detail)


def test_sizing_and_gate_use_rc_insets(monkeypatch):
    """A safe room sized to exactly its net minimum with PARTITION insets would fall below the
    minimum with RC insets; the solver sizes it with RC insets, so the realized net area honours C4."""
    res = _realize()
    assert isinstance(res, RealizedLayout), res
    _, _, net = net_rect_m("SAFE_ROOM", res.rects["SAFE_ROOM"], res.walls)
    assert net >= ZONES["SAFE_ROOM"].min_area_m2 - 1e-6
    # gate: the ORIGINAL rank-1 solver knows nothing of RC insets; with it, an interior safe room
    # whose gross cell meets the minimum only with PARTITION insets must be refused by the gate
    # (net 2.9 x 3.0 = 8.7 m2 under RC insets vs 9.3 m2 under partition insets, minimum 9.0)
    z = {"A": _zi("A", ProgramRole.BEDROOM, 10.0, 5.0, 20.0, 1.0), "SAFE_ROOM": _zi("SAFE_ROOM", ProgramRole.SAFE_ROOM, 10.0, 9.0, 14.0, 2.4),
         "B": _zi("B", ProgramRole.BEDROOM, 10.0, 5.0, 20.0, 1.0)}
    wing = GridWing("G", 9.6, 3.3, 3, ((GridCell("A", 1), GridCell("SAFE_ROOM", 1), GridCell("B", 1)),), z)
    monkeypatch.setattr(rr, "GRID_SIZING_RANK1_FALLBACK", True)
    out = rr._build_grid_wing(wing, (0, 0))
    assert isinstance(out, rr.Refusal) and out.constraint == "AREA_INFEASIBLE", out
    assert "SAFE_ROOM" in out.detail


def test_rc_assignment_is_deterministic():
    a, b = _realize(), _realize()
    assert isinstance(a, RealizedLayout) and isinstance(b, RealizedLayout)
    assert a.walls == b.walls
    assert {k: (r.x, r.y, r.w, r.h) for k, r in a.rects.items()} == {k: (r.x, r.y, r.w, r.h) for k, r in b.rects.items()}


def test_rc_sides_from_rows_matches_contacts():
    rows = ((("LIVING", 2), ("KITCHEN", 1)), (("HALL", 2), ("BEDROOM_1", 1)), (("SAFE_ROOM", 1), ("BEDROOM_2", 2)))
    rc = rc_sides_from_rows(rows, 3, ZONES)
    assert rc["SAFE_ROOM"] == frozenset({"N", "S", "E", "W"})
    assert rc["BEDROOM_2"] == frozenset({"W"})
    assert rc["HALL"] == frozenset({"S"})
    assert rc["BEDROOM_1"] == frozenset() and rc["LIVING"] == frozenset() and rc["KITCHEN"] == frozenset()
