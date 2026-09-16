"""The building footprint as a LIST of rectangles — one per wing — and the few facts read off it.

Every stage after Geometry Core used to take the footprint as one `Rect`: the site stage drew
the garden around it, the door stage put the entrance on its street wall, exposure was "touches
its edge", C2 measured against its area, the renderer drew it. That is true of a one-wing house
and false of an L, and it is the same assumption an upper level with its own outline would hit.
This module is the generalisation, done once: the footprint is `tuple[Rect, ...]`, the wings
never overlap, and the old single rectangle survives as the BOUNDING BOX — still what a
placement, a frame or a "the building line" question wants, and byte-identical to the old value
when there is one wing.

Two things are deliberately not here: any notion of which wing is "primary" (the generator's
business) and any polygon type — Geometry Core consumes rectangles, the adapter emits rectangles,
and every operation below is exact integer-grid rectangle arithmetic.
"""
from __future__ import annotations

from .geometry_core.model import Rect

Wings = tuple[Rect, ...]


def bounding_box(wings: Wings) -> Rect:
    """The smallest rectangle containing every wing. For one wing, that wing."""
    if not wings:
        raise ValueError("a footprint has at least one wing")
    x = min(w.x for w in wings)
    y = min(w.y for w in wings)
    x2 = max(w.x2 for w in wings)
    y2 = max(w.y2 for w in wings)
    return Rect(x, y, x2 - x, y2 - y)


def area_u(wings: Wings) -> int:
    """Σ wing areas in grid units² — the wings never overlap, so the sum is the footprint's area."""
    return sum(w.w * w.h for w in wings)


def wing_of(wings: Wings, rect: Rect) -> Rect:
    """The wing a room lies in. A room is always inside exactly one wing (the slicing tree tiles
    the wing); a rect inside none is a defect and says so rather than picking the nearest."""
    for wing in wings:
        if wing.x <= rect.x and rect.x2 <= wing.x2 and wing.y <= rect.y and rect.y2 <= wing.y2:
            return wing
    raise ValueError(f"{rect} lies in no wing of {wings}")


def wing_on_street_line(wings: Wings, x_u: int, y_u: int) -> Rect | None:
    """The wing whose street-side (y = min) wall holds the point `(x_u, y_u)`, or None."""
    for wing in wings:
        if wing.y == y_u and wing.x <= x_u <= wing.x2:
            return wing
    return None


def subtract(minuend: Rect, rects: Wings) -> Wings:
    """`minuend` minus every rectangle in `rects`, as a tuple of disjoint rectangles.

    Exact on the grid: the minuend is cut along every x and y edge the subtracted rectangles
    introduce, each cell is kept iff no rectangle covers it, and kept cells are merged along rows.
    Deterministic (rows top to bottom, cells left to right), which is what lets a garden region
    list stay stable between runs.
    """
    xs = sorted({minuend.x, minuend.x2} | {v for r in rects for v in (r.x, r.x2)
                                              if minuend.x < v < minuend.x2})
    ys = sorted({minuend.y, minuend.y2} | {v for r in rects for v in (r.y, r.y2)
                                              if minuend.y < v < minuend.y2})
    out: list[Rect] = []
    for y0, y1 in zip(ys, ys[1:]):
        run_start: int | None = None
        for x0, x1 in zip(xs, xs[1:]):
            cell = Rect(x0, y0, x1 - x0, y1 - y0)
            covered = any(r.overlap_area_u(cell) == cell.w * cell.h for r in rects)
            if not covered and run_start is None:
                run_start = x0
            if covered and run_start is not None:
                out.append(Rect(run_start, y0, x0 - run_start, y1 - y0))
                run_start = None
        if run_start is not None:
            out.append(Rect(run_start, y0, xs[-1] - run_start, y1 - y0))
    return tuple(out)


def remainder_within_bbox(wings: Wings) -> Wings:
    """The bounding box minus the wings — the crook of an L, the notch of a T. Empty for one wing."""
    if len(wings) == 1:
        return ()
    return subtract(bounding_box(wings), wings)


def covers(cover: Wings, target: Rect) -> bool:
    """Whether the union of `cover` contains `target` entirely."""
    return not subtract(target, cover)
