"""Stage 10 — Renderer.

Draws one `GeometricDesign` to a PNG floor plan: plot + garden + parking + entrance walk,
room outlines colored by wall type (exterior/partition/RC/open), interior doors as gaps with a
swing arc, windows as blue wall segments, room labels with net area. This is a top-down line
drawing for legibility, not a photorealistic render.

DECOUPLED FROM THE SOLVER (report §11, task §9). This module imports nothing from
`geometry_core` — no `Rect`, no grid units, no `u_to_m`. It consumes the contract in metres and
nothing else. The invariant is enforced by a test, not by convention:

    tests/vertical_slice/test_renderer_decoupling.py

That matters because the renderer must not need to know whether a design came from the
rectangular Geometry Core, a future polygon solver, or a CAD engine.
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Arc, Rectangle

from .design_output import DoorOut, GeometricDesign, WindowOut

_WALL_COLOR = {
    "EXTERIOR": "#1a1a1a",
    "PARTITION": "#888888",
    "RC_SAFE_ROOM": "#b03a2e",
    "OPEN": None,  # not drawn
}
_WALL_WIDTH = {"EXTERIOR": 2.4, "PARTITION": 1.0, "RC_SAFE_ROOM": 3.2, "OPEN": 0}


def _draw_room_walls(ax, room) -> None:
    x, y, w, h = room.rect_m
    edges = {
        "N": ((x, y), (x + w, y)),
        "S": ((x, y + h), (x + w, y + h)),
        "W": ((x, y), (x, y + h)),
        "E": ((x + w, y), (x + w, y + h)),
    }
    for side, (p0, p1) in edges.items():
        wtype = room.walls[side]
        color = _WALL_COLOR[wtype]
        if color is None:
            continue
        ax.plot([p0[0], p1[0]], [p0[1], p1[1]], color=color, linewidth=_WALL_WIDTH[wtype],
                solid_capstyle="butt", zorder=3)


def _draw_door(ax, door: DoorOut, color="#ffffff") -> None:
    cx_m, cy_m = door.center_m
    half = door.width_m / 2
    if door.orientation == "vertical":
        ax.plot([cx_m, cx_m], [cy_m - half, cy_m + half], color=color, linewidth=3.0, zorder=4)
        ax.add_patch(Arc((cx_m, cy_m - half), door.width_m * 2, door.width_m * 2,
                          angle=0, theta1=0, theta2=90, color="#4a90d9", linewidth=0.8, zorder=4))
    else:
        ax.plot([cx_m - half, cx_m + half], [cy_m, cy_m], color=color, linewidth=3.0, zorder=4)
        ax.add_patch(Arc((cx_m - half, cy_m), door.width_m * 2, door.width_m * 2,
                          angle=0, theta1=0, theta2=90, color="#4a90d9", linewidth=0.8, zorder=4))


def _draw_window(ax, window: WindowOut) -> None:
    cx, cy = window.center_m
    half = window.width_m / 2
    if window.side in ("N", "S"):
        ax.plot([cx - half, cx + half], [cy, cy], color="#2f7fd6", linewidth=3.2, zorder=5)
    else:
        ax.plot([cx, cx], [cy - half, cy + half], color="#2f7fd6", linewidth=3.2, zorder=5)


def render(design: GeometricDesign, out_path: str, title: str = "Private House V1 — first vertical slice") -> str:
    fig, ax = plt.subplots(figsize=(10, 11))

    px, py, pw, ph = design.plot_m
    ax.add_patch(Rectangle((px, py), pw, ph, facecolor="#f4f6f2", edgecolor="#bbbbbb", linewidth=1.0, zorder=0))

    for region in design.garden:
        for (rx, ry, rw, rh) in region.rects_m:
            ax.add_patch(Rectangle((rx, ry), rw, rh, facecolor="#d9ead3", edgecolor="none", zorder=1))

    for (x, y, w, h) in design.parking_m:
        ax.add_patch(Rectangle((x, y), w, h, facecolor="#d9d9d9", edgecolor="#888888",
                                hatch="////", linewidth=0.8, zorder=2))
        ax.text(x + w / 2, y + h / 2, "P", ha="center", va="center", fontsize=9, color="#555555", zorder=2)

    wx, wy, ww, wh = design.entrance_walk_m
    ax.add_patch(Rectangle((wx, wy), ww, wh, facecolor="#e8d9b5", edgecolor="none", zorder=2))

    fx, fy, fw, fh = design.footprint_m
    ax.add_patch(Rectangle((fx, fy), fw, fh, facecolor="#ffffff", edgecolor="none", zorder=2))

    for room in design.rooms:
        x, y, w, h = room.rect_m
        _draw_room_walls(ax, room)
        label = room.zone_id.replace("_", " ")
        ax.text(x + w / 2, y + h / 2, f"{label}\n{room.net_area_m2:.1f} m²",
                ha="center", va="center", fontsize=7.5, color="#222222", zorder=4)

    for door in design.interior_doors:
        _draw_door(ax, door)
    _draw_door(ax, design.entrance_door, color="#1a1a1a")

    for window in design.windows:
        if window.width_m > 0:
            _draw_window(ax, window)

    ax.set_xlim(px - 1, px + pw + 1)
    ax.set_ylim(py + ph + 1, py - 1)  # y grows away from the street; keep street at the top
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(
        f"{title}\ngross {design.gross_area_m2:.1f} m² · net {design.net_area_m2:.1f} m² · "
        f"wall re-solve: {design.wall_iterations} iteration(s)",
        fontsize=11,
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return out_path
