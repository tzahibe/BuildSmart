"""Issue #142E — exact per-cell band sizing and the canonical NET semantics of the grid gate.

The drift tests pin the domain decision: ZoneIntent/ZoneSpec/ROOM_TEMPLATES bounds are NET, so the
sizing solver and `_build_grid_wing`'s gate must both measure a room the way validator C3 does
(after the wall insets the realizer assigns), never gross-vs-net.
"""
from __future__ import annotations

import pytest

from app.vertical_slice import rectilinear_realizer as rr
from app.vertical_slice.band_sizing import cell_insets_u, cells_from_rows, solve_band_sizing
from app.vertical_slice.geometry_core.model import ProgramRole, UNIT_M, WallType, inset_u
from app.vertical_slice.rectilinear_realizer import (
    GridCell,
    GridWing,
    RealizationIntent,
    RealizedLayout,
    Refusal,
    ZoneIntent,
    realize_layout,
)


def _zi(zid, role, target, lo, hi, short=2.4, aspect=2.5):
    return ZoneIntent(zid, role, target, lo, hi, short, aspect)


def _net_dims(rect_w_u, rect_h_u, r, c0, c1, R, C):
    iw, ih = cell_insets_u(r, c0, c1, R, C)
    return (rect_w_u - iw) * UNIT_M, (rect_h_u - ih) * UNIT_M


# --------------------------------------------------------------------------- solver

def test_solution_satisfies_every_cell_on_net_dimensions():
    zones = {"A": _zi("A", ProgramRole.LIVING, 20.0, 16.0, 30.0, 3.0), "B": _zi("B", ProgramRole.KITCHEN, 12.0, 9.0, 16.0, 2.4),
             "H": _zi("H", ProgramRole.HALL, 8.0, 5.0, 14.0, 1.2), "C": _zi("C", ProgramRole.BEDROOM, 12.0, 9.0, 14.0, 2.6),
             "D": _zi("D", ProgramRole.BEDROOM, 12.0, 9.0, 14.0, 2.6)}
    rows = (( ("A", 2), ("B", 1)), (("H", 3),), (("C", 1), ("D", 2)))
    res = solve_band_sizing(rows, 3, zones, w_max_m=14.0, h_max_m=14.0)
    assert res.status == "FEASIBLE", res
    R, C = 3, 3
    for cell in cells_from_rows(rows, 3, zones):
        w_u = sum(res.col_w_u[cell.c0:cell.c1]); h_u = res.row_h_u[cell.r]
        nw, nh = _net_dims(w_u, h_u, cell.r, cell.c0, cell.c1, R, C)
        z = zones[cell.zone_id]
        assert z.min_area_m2 - 0.01 <= nw * nh <= z.max_area_m2 + 0.01, (cell.zone_id, nw, nh)
        assert min(nw, nh) >= z.min_short_side_m - 1e-9
        assert max(nw, nh) <= z.max_aspect_ratio * min(nw, nh) + 1e-9
    assert sum(res.col_w_u) * UNIT_M <= 14.0 and sum(res.row_h_u) * UNIT_M <= 14.0


def test_exact_envelope_mode_tiles_exactly():
    zones = {"A": _zi("A", ProgramRole.LIVING, 20.0, 14.0, 30.0, 3.0), "B": _zi("B", ProgramRole.KITCHEN, 12.0, 8.0, 18.0, 2.4),
             "C": _zi("C", ProgramRole.BEDROOM, 12.0, 8.0, 18.0, 2.6), "D": _zi("D", ProgramRole.BEDROOM, 12.0, 8.0, 18.0, 2.6)}
    rows = ((("A", 1), ("B", 1)), (("C", 1), ("D", 1)))
    res = solve_band_sizing(rows, 2, zones, w_max_m=9.0, h_max_m=9.0, w_exact_m=9.0, h_exact_m=9.0)
    assert res.status == "FEASIBLE"
    assert sum(res.col_w_u) == 180 and sum(res.row_h_u) == 180


def test_infeasible_is_a_proof_and_unknown_is_honest():
    # a full-width bathroom band caps the wing width below what the bedroom band needs
    zones = {"BA": _zi("BA", ProgramRole.BATHROOM, 6.0, 4.5, 12.0, 1.6), "B1": _zi("B1", ProgramRole.BEDROOM, 12.0, 9.0, 14.0, 2.6),
             "B2": _zi("B2", ProgramRole.BEDROOM, 12.0, 9.0, 14.0, 2.6), "M": _zi("M", ProgramRole.MASTER_BEDROOM, 14.0, 11.0, 20.0, 3.0)}
    rows = ((("BA", 3),), (("B1", 1), ("B2", 1), ("M", 1)))
    res = solve_band_sizing(rows, 3, zones, w_max_m=20.0, h_max_m=20.0)
    assert res.status == "INFEASIBLE"
    res2 = solve_band_sizing(rows, 3, zones, w_max_m=20.0, h_max_m=20.0, node_limit=0)
    assert res2.status in ("INFEASIBLE", "UNKNOWN")   # a root certificate may still decide it


def test_solver_is_deterministic():
    zones = {"A": _zi("A", ProgramRole.LIVING, 20.0, 16.0, 30.0, 3.0), "B": _zi("B", ProgramRole.KITCHEN, 12.0, 9.0, 16.0, 2.4),
             "H": _zi("H", ProgramRole.HALL, 8.0, 5.0, 14.0, 1.2), "C": _zi("C", ProgramRole.BEDROOM, 12.0, 9.0, 14.0, 2.6)}
    rows = ((("A", 1), ("B", 1)), (("H", 2),), (("C", 2),))
    a = solve_band_sizing(rows, 2, zones, w_max_m=14.0, h_max_m=14.0)
    b = solve_band_sizing(rows, 2, zones, w_max_m=14.0, h_max_m=14.0)
    assert (a.row_h_u, a.col_w_u) == (b.row_h_u, b.col_w_u)


# --------------------------------------------------------------------------- net/gross drift

def test_grid_gate_measures_net_not_gross():
    """A room whose GROSS area meets the minimum but whose NET area does not must be refused
    (the #142D false-acceptance defect), and a room whose NET area is inside the bounds must pass
    even if its gross area exceeds the maximum (the false-rejection defect)."""
    # single cell wing: all four sides EXTERIOR -> insets 0.15 m per side
    ext = inset_u(WallType.EXTERIOR) * UNIT_M
    # gross 4.0 x 4.0 = 16.0 ; net (4.0-0.3)^2 = 13.69
    z_min16 = {"A": _zi("A", ProgramRole.LIVING, 16.0, 16.0, 40.0, 3.0, 2.5)}
    wing = GridWing("W", 4.0, 4.0, 1, ((GridCell("A", 1),),), z_min16)
    out = rr._build_grid_wing(wing, (0, 0))
    assert isinstance(out, Refusal) and out.constraint in ("AREA_INFEASIBLE", "GRID_INFEASIBLE"), out
    # net bound satisfied although gross exceeds max: max 13.7, gross 16.0, net 13.69
    z_max = {"A": _zi("A", ProgramRole.LIVING, 13.0, 9.0, 13.7, 3.0, 2.5)}
    wing2 = GridWing("W", 4.0, 4.0, 1, ((GridCell("A", 1),),), z_max)
    out2 = rr._build_grid_wing(wing2, (0, 0))
    assert not isinstance(out2, Refusal), out2
    assert abs((4.0 - 2 * ext) ** 2 - 13.69) < 1e-6


def test_rank1_fallback_flag_restores_the_old_solver(monkeypatch):
    zones = {"A": _zi("A", ProgramRole.LIVING, 20.0, 12.0, 30.0, 3.0), "B": _zi("B", ProgramRole.KITCHEN, 12.0, 8.0, 18.0, 2.4),
             "C": _zi("C", ProgramRole.BEDROOM, 12.0, 8.0, 18.0, 2.6), "D": _zi("D", ProgramRole.BEDROOM, 12.0, 8.0, 18.0, 2.6)}
    wing = GridWing("W", 9.0, 9.0, 2, ((GridCell("A", 1), GridCell("B", 1)), (GridCell("C", 1), GridCell("D", 1))), zones)
    monkeypatch.setattr(rr, "GRID_SIZING_RANK1_FALLBACK", True)
    out = rr._solve_grid(wing)
    assert not isinstance(out, Refusal)
    row_h, col_w = out
    assert sum(row_h) == 180 and sum(col_w) == 180


def test_envelope_as_bound_lets_the_solver_choose_the_wing_size():
    zones = {"A": _zi("A", ProgramRole.LIVING, 20.0, 16.0, 30.0, 3.0), "B": _zi("B", ProgramRole.KITCHEN, 12.0, 9.0, 16.0, 2.4),
             "H": _zi("H", ProgramRole.HALL, 8.0, 5.0, 14.0, 1.2), "C": _zi("C", ProgramRole.BEDROOM, 12.0, 9.0, 14.0, 2.6),
             "D": _zi("D", ProgramRole.BEDROOM, 12.0, 9.0, 14.0, 2.6)}
    rows = ((GridCell("A", 2), GridCell("B", 1)), (GridCell("H", 3),), (GridCell("C", 1), GridCell("D", 2)))
    wing = GridWing("W", 20.0, 20.0, 3, rows, zones, envelope_is_bound=True)
    out = rr._build_grid_wing(wing, (40, 40))
    assert not isinstance(out, Refusal), out
    assert out.size[0] <= 400 and out.size[1] <= 400
    assert out.size != (400, 400)
