"""R1 (#242) — a POST-RUN, NON-SCORED diagnostic: is fragmenting a room the blocker, independent of
how the harness happens to cut it?

C9 (furniture envelope), C20 (template aspect) and C19/C8 (exterior, daylight) run on every CELL as
if it were a room — the group checks do not replace them. So a room that is not a rectangle becomes
two or more cells, each judged as a room. This asks, for each non-rectangular room of the converted
plans and OPTIMISTICALLY (gross dimensions, no wall insets, nothing about neighbours or the
exterior): does ANY partition of the room into rectangles exist in which every rectangle passes
C20's aspect bound and C9's envelope? If none does, no wing choice, cut order or cell refinement can
carry that room under the unchanged per-cell checks; the verdict does not depend on this harness's
cutting rule. Exhaustive over the room's own coordinate grid (small), memoised.
"""
from __future__ import annotations

from functools import lru_cache

from shapely.geometry import Polygon, box

from app.vertical_slice.concept_generator import ROOM_TEMPLATES
from app.vertical_slice.geometry_core.model import MIN_FURNITURE_ENVELOPE_M, ProgramRole


def _rect_ok(role: ProgramRole, w: float, h: float) -> bool:
    if role in (ProgramRole.HALL, ProgramRole.CIRCULATION):
        return True                                   # C20/C21 exempt circulation, C9 has no envelope for it
    t = ROOM_TEMPLATES[role]
    if max(w, h) / max(min(w, h), 1e-6) > t.max_aspect_ratio + 1e-6:
        return False
    env = MIN_FURNITURE_ENVELOPE_M.get(role)
    if env is None:
        return True
    ew, ed = env
    return (ew <= w + 1e-6 and ed <= h + 1e-6) or (ew <= h + 1e-6 and ed <= w + 1e-6)


def partition_exists(poly: Polygon, role: ProgramRole) -> bool:
    xs = sorted({round(x, 4) for x, _ in poly.exterior.coords})
    ys = sorted({round(y, 4) for _, y in poly.exterior.coords})
    nx, ny = len(xs) - 1, len(ys) - 1
    occupied = [[poly.buffer(1e-7).covers(box(xs[i] + 1e-6, ys[j] + 1e-6, xs[i + 1] - 1e-6, ys[j + 1] - 1e-6))
                 for i in range(nx)] for j in range(ny)]
    full = frozenset((i, j) for j in range(ny) for i in range(nx) if occupied[j][i])

    @lru_cache(maxsize=None)
    def solve(covered: frozenset) -> bool:
        todo = sorted(full - covered, key=lambda c: (c[1], c[0]))
        if not todo:
            return True
        i, j = todo[0]
        w = 1
        while i + w <= nx and (i + w - 1, j) in full and (i + w - 1, j) not in covered:
            h = 1
            while j + h <= ny and all((i + k, j + h - 1) in full and (i + k, j + h - 1) not in covered
                                      for k in range(w)):
                if _rect_ok(role, xs[i + w] - xs[i], ys[j + h] - ys[j]):
                    new = covered | frozenset((i + k, j + m) for k in range(w) for m in range(h))
                    if solve(new):
                        return True
                h += 1
            w += 1
        return False

    return solve(frozenset())
