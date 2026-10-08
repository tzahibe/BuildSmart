"""How trivially separable the delivered plans are (#186).

`docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md` §3.2 measured the REAL corpus: 0 of 19
professional plans are guillotine-separable. This measures the same property on what BuildSmart
actually delivers, from the same JSON the decision probe wrote — plus the finer statistic that
makes the difference visible: how many straight full-span cut lines each plan admits at the top
level, and the maximum recursion depth at which a cut always exists.

    PYTHONPATH=backend python -m app.ai_harness.arch_direction.separability <decisions.json>
"""
from __future__ import annotations

import json
import sys

_TOL = 0.02


def _rects(rooms):
    return [(r["id"], r["x"], r["y"], r["x"] + r["gw"], r["y"] + r["gd"]) for r in rooms]


def _full_cuts(rects) -> tuple[list[float], list[float]]:
    """Every x (then y) at which a straight line crosses the whole group without cutting a rect."""
    xs, ys = [], []
    x0 = min(r[1] for r in rects); x1 = max(r[3] for r in rects)
    y0 = min(r[2] for r in rects); y1 = max(r[4] for r in rects)
    for c in sorted({r[1] for r in rects} | {r[3] for r in rects}):
        if c <= x0 + _TOL or c >= x1 - _TOL:
            continue
        if all(r[3] <= c + _TOL or r[1] >= c - _TOL for r in rects):
            xs.append(round(c, 2))
    for c in sorted({r[2] for r in rects} | {r[4] for r in rects}):
        if c <= y0 + _TOL or c >= y1 - _TOL:
            continue
        if all(r[4] <= c + _TOL or r[2] >= c - _TOL for r in rects):
            ys.append(round(c, 2))
    return xs, ys


def separable(rects) -> bool:
    if len(rects) <= 1:
        return True
    xs, ys = _full_cuts(rects)
    for c in xs:
        a = [r for r in rects if r[3] <= c + _TOL]
        b = [r for r in rects if r[1] >= c - _TOL]
        if a and b and len(a) + len(b) == len(rects) and separable(a) and separable(b):
            return True
    for c in ys:
        a = [r for r in rects if r[4] <= c + _TOL]
        b = [r for r in rects if r[2] >= c - _TOL]
        if a and b and len(a) + len(b) == len(rects) and separable(a) and separable(b):
            return True
    return False


def main(path: str) -> None:
    data = json.load(open(path))
    print(f"{'brief':6} {'rooms':5} {'full x-cuts':11} {'full y-cuts':11} {'guillotine':10}")
    for row in data:
        plan = row.get("plan")
        if not plan:
            continue
        rooms = [{"id": r["id"], "x": r["x"], "y": r["y"],
                  "gw": r["gross_width_m"], "gd": r["gross_depth_m"]}
                 for r in plan["rooms"]]
        rects = _rects(rooms)
        xs, ys = _full_cuts(rects)
        print(f"{row['brief']:6} {len(rects):<5} {len(xs):<11} {len(ys):<11} {str(separable(rects)):10}")


if __name__ == "__main__":
    main(sys.argv[1])
