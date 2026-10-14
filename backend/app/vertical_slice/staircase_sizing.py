"""Exact sizing of a band layout INSIDE AN ORTHOGONAL ENVELOPE — formulation A of ADR-001 (#197).

`band_sizing.solve_band_layout` sizes an ordered band layout so that every band spans ONE shared
width (`_layout_cells`: "0 is the shared left edge ... then node W (shared right edge)"). That is
the single line that makes every brain plan a rectangle. This module keeps everything else that
solver does — the per-cell NET width intervals, the required-contact overlap constraints, the
door-width contacts, the height branch-and-bound over a difference-constraint system solved by
Bellman–Ford — and gives each band ITS OWN start and end node, bounded by the envelope's
horizontal extent at that band's depth. The building becomes a staircase of bands: every
horizontally-convex orthogonal polygon (rectangle, L, T, Z, stepped, offset wings, U opening east or
west) can come out, and WHICH one comes out is decided by the rooms' own bounds, the contacts and
the envelope — never by a template.

What it does not do, by declaration (ADR-001 §4.A): a band whose depth range meets the envelope in
more than one interval (a court, a U opening north/south) is refused as `BAND_GAP`, naming the
band. That is formulation A's limit, reported as such.

Insets. `band_sizing` knows a cell's north/south sides are exterior only on the first/last band;
in a staircase ANY band's edge may be exterior where the neighbouring band does not cover it, and
that is only known after widths are chosen. The conservative rule used here is the heavier
EXTERIOR inset on every north/south side (a safe room's own sides stay RC). Net dimensions are
therefore UNDER-estimated, never over: a cell that sizes here cannot fail its minimum bounds in the
unchanged validator C3 downstream, and a maximum is checked again by C3 on the real walls.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

from .band_sizing import (DEFAULT_NODE_LIMIT, CellSpec, _bellman_ford_from, _height_bounds,
                          _prefix_interval, _width_interval)
from .envelope import Envelope
from .geometry_core.model import UNIT_M, ProgramRole, Rect, WallType, inset_u, m_to_u

#: Alignment is decided inside `choose()` and is not part of the height relaxation that prunes
#: the branch-and-bound, so a layout that cannot be aligned would otherwise burn the whole node
#: budget bisecting boxes whose relaxation stays feasible. After this many failed width choices
#: the solve stops and reports ALIGNMENT_UNSAT — explicitly not a proof — so a caller trying
#: many embedder candidates moves on in tens of milliseconds, not seconds.
MAX_CHOOSE_FAILURES = 40
#: Height vectors evaluated exactly before the branch-and-bound starts (each ~0.3 ms).
ENUMERATION_BUDGET = 160
#: Rounds of alternating height/width projection before the enumeration starts.
ALTERNATION_ROUNDS = 16
#: Exact LPs the aligned placement may spend per height vector before giving up on it.
ALIGNED_LP_BUDGET = 120

#: Diagnostics only: when set to a list, `choose()` appends one line per decision it makes.
_TRACE: list | None = None


def _t(msg: str) -> None:
    if _TRACE is not None:
        _TRACE.append(msg)


@dataclass(frozen=True)
class StaircaseSizing:
    status: str                                     # FEASIBLE | INFEASIBLE | UNKNOWN | BAND_GAP
    row_h_u: tuple[int, ...] = ()
    #: per band: (start_x, boundary_1, ..., end_x) in units from the envelope's west edge
    band_x_u: tuple[tuple[int, ...], ...] = ()
    nodes: int = 0
    detail: str = ""
    #: where the building's top edge sits below the envelope's street edge (an entry court)
    y_start_u: int = 0

    def rects(self, bands) -> dict[str, Rect]:
        """Every zone's centerline rectangle, y from the envelope's street edge."""
        out: dict[str, Rect] = {}
        y = self.y_start_u
        for r, band in enumerate(bands):
            xs = self.band_x_u[r]
            for i, zid in enumerate(band):
                out[zid] = Rect(xs[i], y, xs[i + 1] - xs[i], self.row_h_u[r])
            y += self.row_h_u[r]
        return out

    def band_rects(self, bands) -> tuple[Rect, ...]:
        """One rectangle per band — the realized footprint is their union."""
        out, y = [], self.y_start_u
        for r, _band in enumerate(bands):
            xs = self.band_x_u[r]
            out.append(Rect(xs[0], y, xs[-1] - xs[0], self.row_h_u[r]))
            y += self.row_h_u[r]
        return tuple(out)


def _cells_and_nodes(bands, zones, sides: dict[str, dict[str, WallType]] | None = None,
                     ) -> tuple[list[CellSpec], list[list[int]], int]:
    """Cells over PER-BAND nodes: node 0 is the global origin (the envelope's west edge, x = 0);
    band b owns nodes s_b .. s_b + k_b, the first being its own start and the last its own end.
    Nothing is shared between bands except the origin, which is the whole point.

    `sides` is each cell's wall type per side ("N"/"S"/"E"/"W") read off a PREVIOUS solution's
    real touching; on the first round it is unknown and the heavier EXTERIOR inset is assumed on
    every north/south side. The solve repeats with the real sides until they stop changing — the
    same fixed-point discipline `band_sizing.solve_band_layout` applies to RC sides — because a
    staircase makes "is this side exterior" depend on the widths being solved."""
    next_id = 1
    band_nodes: list[list[int]] = []
    for band in bands:
        k = len(band)
        band_nodes.append([next_id + i for i in range(k + 1)])
        next_id += k + 1
    ext, part, rcu = inset_u(WallType.EXTERIOR), inset_u(WallType.PARTITION), inset_u(WallType.RC_SAFE_ROOM)
    cells: list[CellSpec] = []
    for r, band in enumerate(bands):
        for i, zid in enumerate(band):
            z = zones[zid]
            safe = getattr(z, "role", None) is ProgramRole.SAFE_ROOM
            known = (sides or {}).get(zid)
            if known is not None:
                iw = inset_u(known["W"]) + inset_u(known["E"])
                ih = inset_u(known["N"]) + inset_u(known["S"])
            else:
                iw = ((rcu if safe else (ext if i == 0 else part))
                      + (rcu if safe else (ext if i == len(band) - 1 else part)))
                ih = (rcu if safe else ext) * 2        # first round: conservative, see docstring
            cells.append(CellSpec(zid, r, band_nodes[r][i], band_nodes[r][i + 1], z.min_area_m2,
                                  z.max_area_m2, z.min_short_side_m, z.max_aspect_ratio, iw, ih))
    return cells, band_nodes, next_id


def sides_from_rects(rects: dict[str, Rect], zones) -> dict[str, dict[str, WallType]]:
    """Each cell's real wall type per side from the realized touching — the rule
    `rectilinear_realizer.realize_cells` applies (RC > EXTERIOR > PARTITION)."""
    safe = {z for z, zi in zones.items() if getattr(zi, "role", None) is ProgramRole.SAFE_ROOM}
    out: dict[str, dict[str, WallType]] = {}
    for z, r in rects.items():
        touch = {"N": [], "S": [], "E": [], "W": []}
        for o, q in rects.items():
            if o == z or r.shared_edge_len_u(q) <= 0:
                continue
            if q.y2 == r.y:
                touch["N"].append(o)
            elif q.y == r.y2:
                touch["S"].append(o)
            elif q.x2 == r.x:
                touch["W"].append(o)
            elif q.x == r.x2:
                touch["E"].append(o)
        out[z] = {}
        for side, others in touch.items():
            if z in safe or any(o in safe for o in others):
                out[z][side] = WallType.RC_SAFE_ROOM
            elif others:
                out[z][side] = WallType.PARTITION
            else:
                out[z][side] = WallType.EXTERIOR
    return out


def _system(cells, bands, band_nodes, N, required, h, hU, tol_m2, min_contact_u, extents):
    """Difference constraints `x[v] - x[u] <= c` as (u, v, c), for heights in [h, hU]."""
    cons: list[tuple[int, int, int]] = []
    for cell in cells:
        lo, hi = _width_interval(cell, h[cell.r], (hU or h)[cell.r], tol_m2)
        if lo > hi:
            return None
        cons.append((cell.c0, cell.c1, hi))
        cons.append((cell.c1, cell.c0, -lo))
    by_zone = {cell.zone_id: cell for cell in cells}
    for a, b in required:
        ca, cb = by_zone[a], by_zone[b]
        if ca.r == cb.r:
            if abs(ca.c0 - cb.c0) != 1:
                return None                            # same band but not consecutive: no shared wall
            continue                                   # consecutive in one band: touching by construction
        if abs(ca.r - cb.r) != 1:
            return None
        need = max(1, (min_contact_u or {}).get(frozenset((a, b)), 1))
        cons.append((cb.c1, ca.c0, -need))
        cons.append((ca.c1, cb.c0, -need))
    # consecutive bands must overlap by at least one unit: the building is one connected piece
    for r in range(len(bands) - 1):
        s0, e0 = band_nodes[r][0], band_nodes[r][-1]
        s1, e1 = band_nodes[r + 1][0], band_nodes[r + 1][-1]
        # (u, v, c) means x[v] - x[u] <= c, as in `band_sizing._layout_system`:
        cons.append((e0, s1, -1))                      # x[s1] - x[e0] <= -1  ->  band r+1 starts before band r ends
        cons.append((e1, s0, -1))                      # x[s0] - x[e1] <= -1  ->  band r starts before band r+1 ends
    # the envelope: each band inside its own horizontal extent
    for r in range(len(bands)):
        L, R = extents[r]
        s, e = band_nodes[r][0], band_nodes[r][-1]
        cons.append((s, 0, -L))                        # x[s] >= L  ->  x[0] - x[s] <= -L
        cons.append((0, e, R))                         # x[e] <= R
    return cons



def _aligned_candidates(iv: tuple[int, int], target: int, above: list[int] | None,
                        want_start: bool) -> list[int]:
    """Feasible values in `iv` for a band endpoint, nearest the target first, that do not land
    strictly inside a cell of the band above: any boundary of that band, or any value outside its
    extent. With no band above, simply the clamped target."""
    lo, hi = iv
    if above is None:
        return [max(lo, min(hi, target))]
    a_lo, a_hi = above[0], above[-1]
    allowed = [b for b in above if lo <= b <= hi]
    # outside the band above: a start left of it / an end right of it, plus any value that is not
    # strictly inside (a start at or beyond its end, an end at or before its start)
    if want_start:
        allowed += [v for v in (lo, min(hi, a_lo)) if lo <= v <= hi and v <= a_lo]
        allowed += [v for v in (max(lo, a_hi), hi) if lo <= v <= hi and v >= a_hi]
    else:
        allowed += [v for v in (max(lo, a_hi), hi) if lo <= v <= hi and v >= a_hi]
        allowed += [v for v in (lo, min(hi, a_lo)) if lo <= v <= hi and v <= a_lo]
    allowed = sorted(set(allowed), key=lambda v: (abs(v - target), v))
    return allowed


def solve_staircase_layout(bands, zones, required, envelope: Envelope, *, tol_m2: float = 0.01,
                           node_limit: int = DEFAULT_NODE_LIMIT,
                           min_contact_u: dict | None = None, align: bool = True,
                           seed: tuple[int, ...] | None = None) -> StaircaseSizing:
    """Size `bands` (top-to-bottom tuples of zone ids, the street at the top) inside `envelope`.

    Solved to a FIXED POINT over wall insets (at most 4 rounds): the first round assumes the
    heavier exterior inset on every north/south side; each later round uses the wall types the
    previous solution actually produces, so the net dimensions the unchanged validator C3 will
    measure are the ones that were sized."""
    if not envelope.is_orthogonal:
        return StaircaseSizing("INFEASIBLE", detail="the envelope is not an orthogonal polygon")
    sides = None
    res = StaircaseSizing("INFEASIBLE")
    first = StaircaseSizing("INFEASIBLE")
    for _round in range(4):
        res = _solve_once(bands, zones, required, envelope, tol_m2=tol_m2, node_limit=node_limit,
                          min_contact_u=min_contact_u, sides=sides, seed=seed, align=align)
        if _round == 0:
            first = res
        if res.status != "FEASIBLE":
            # a later round that cannot re-solve under the real insets reports the FIRST round's
            # geometry as the honest answer: it sized under conservative insets, so every minimum
            # still holds; what it cannot promise is a maximum, which C3 re-checks on real walls
            return first if first.status == "FEASIBLE" and _round > 0 else res
        real = sides_from_rects(res.rects(bands), zones)
        if real == sides:
            return res
        sides, seed = real, res.row_h_u
    return res


def _solve_once(bands, zones, required, envelope: Envelope, *, tol_m2, node_limit, min_contact_u,
                sides, seed: tuple[int, ...] | None = None, align: bool = True) -> StaircaseSizing:
    cells, band_nodes, N = _cells_and_nodes(bands, zones, sides)
    R = len(bands)
    req = [tuple(e) for e in required]
    by_zone = {c.zone_id: c for c in cells}
    hmin = [0] * R
    for pair, need in (min_contact_u or {}).items():
        a, b = tuple(pair)
        if need > 1 and a in by_zone and b in by_zone and by_zone[a].r == by_zone[b].r:
            hmin[by_zone[a].r] = max(hmin[by_zone[a].r], need)
    # Bands are contiguous from the street edge, so under formulation A the building must END
    # before the first depth at which the envelope splits (a court, a U opening north/south):
    # a band spanning that depth would meet the envelope in two intervals. Exact for this family —
    # a layout cannot start below a court, because band 0 starts at y = 0 — and decided here
    # rather than discovered by exhausting the search budget.
    # A split window that begins AT the street edge is an entry court or a street-side notch: the
    # building starts below it (its own street wall is then its top edge — `resolve_entrance`
    # reads the building's bounding box, not the envelope's). The first split window AFTER the
    # start caps the depth, as before. Shape-free: both facts come from the envelope's own
    # cross-sections.
    windows = envelope.split_depth_windows_u()
    y_start = 0
    while windows and windows[0][0] <= y_start:
        y_start = windows[0][1]
        windows = windows[1:]
    h_cap = envelope.depth_u - y_start
    if windows:
        h_cap = min(h_cap, windows[0][0] - y_start)
    hL0, hU0 = list(hmin), [h_cap] * R
    for cell in cells:
        lo, hi = _height_bounds(cell, tol_m2, h_cap)
        hL0[cell.r] = max(hL0[cell.r], lo); hU0[cell.r] = min(hU0[cell.r], hi)
    if any(hL0[r] > hU0[r] for r in range(R)):
        return StaircaseSizing("INFEASIBLE", detail="a band's cells have no common feasible depth")
    if windows and sum(hL0) > h_cap:
        y0, y1 = windows[0]
        return StaircaseSizing("BAND_GAP", detail=(
            f"the envelope splits into more than one interval from depth {y0 * UNIT_M:.2f} m to "
            f"{y1 * UNIT_M:.2f} m and the bands need at least {sum(hL0) * UNIT_M:.2f} m of depth from "
            f"the street edge, so one band would meet the envelope in two intervals — formulation A "
            f"sizes one interval per band (ADR-001 §4.A)"))
    total = sum(z.target_area_m2 for z in zones.values()) or 1.0
    row_tot = [sum(zones[z].target_area_m2 for z in band) for band in bands]
    # The height estimate aims the building at ITS OWN programme area over the envelope's width —
    # not at a square of that area (`band_sizing`'s sqrt estimate), which on a 12 x 18 m envelope
    # stopped the search 3.5 m short of the depth and delivered 69–79 % of the request on the
    # rectangle control. Exact for a rectangle; a conservative start for a stepped envelope.
    top_ext = envelope.extent_u(0, 1)
    W_top = (top_ext[0][1] - top_ext[0][0]) if len(top_ext) == 1 else envelope.width_u
    H_est = min(h_cap, max(1, int(round(total / (UNIT_M * UNIT_M) / max(W_top, 1)))))   # m² -> units²
    h_est = [H_est * rt / total for rt in row_tot]
    _t(f"bounds hL0={hL0} hU0={hU0} h_est={[round(x,1) for x in h_est]} h_cap={h_cap} hmin={hmin} sides={'real' if sides else 'conservative'}")

    def extents_for(hL, hU):
        """Each band's conservative [L, R] over every depth it could occupy in this box, or the
        band index whose extent is split (formulation A's declared limit)."""
        out, y_lo, y_hi = [], y_start, y_start
        for r in range(R):
            y_hi += hU[r]
            ivs = envelope.extent_u(y_lo, y_hi)
            if len(ivs) != 1:
                return None, r, ivs
            out.append(ivs[0])
            y_lo += hL[r]
        return out, None, None

    def feasible_box(hL, hU):
        ext, bad, _ = extents_for(hL, hU)
        if ext is None:
            return False
        cons = _system(cells, bands, band_nodes, N, req, hL, hU, tol_m2, min_contact_u, ext)
        return cons is not None and _bellman_ford_from(N - 1, cons, 0) is not None

    def choose(h):
        ext, bad, _ = extents_for(h, h)
        if ext is None:
            _t(f"choose h={h}: split extent at band {bad}"); return None
        cons = _system(cells, bands, band_nodes, N, req, h, None, tol_m2, min_contact_u, ext)
        if cons is None or _bellman_ford_from(N - 1, cons, 0) is None:
            _t(f"choose h={h}: width system infeasible at fixed heights"); return None
        _t(f"choose h={h} ext={ext}")
        budget = [ALIGNED_LP_BUDGET]

        def place(r: int, fixed: list, P: list, prev_bounds: list[int] | None,
                  prev_start: int | None, prev_width: float | None):
            """Bands top to bottom; returns P or None. Exact LP at every decision; backtracks."""
            if r == R:
                return P if _bellman_ford_from(N - 1, cons + fixed, 0) is not None else None
            L, Rr = ext[r]
            w_target = row_tot[r] / (UNIT_M * UNIT_M) / max(h[r], 1)
            if prev_width is not None:
                w_target = max(w_target, prev_width)
            w_target = min(w_target, Rr - L)
            start_t = L if prev_start is None else max(L, min(prev_start, Rr - w_target))
            above = prev_bounds if align else None
            s_node, e_node = band_nodes[r][0], band_nodes[r][-1]
            ids = [cell for cell in cells if cell.r == r]
            iv = _prefix_interval(N - 1, cons + fixed, s_node)
            if iv is None or iv[0] > iv[1]:
                return None
            for val in _aligned_candidates(iv, int(round(start_t)), above, want_start=True):
                trial = fixed + [(0, s_node, val), (s_node, 0, -val)]
                ive = _prefix_interval(N - 1, cons + trial, e_node)
                if ive is None or ive[0] > ive[1]:
                    continue
                for ev in _aligned_candidates(ive, int(round(val + w_target)), above, want_start=False):
                    attempt = trial + [(0, e_node, ev), (e_node, 0, -ev)]
                    forced = sorted(b for b in ((above[0], above[-1]) if above else ()) if val < b < ev)
                    # which interior boundary carries each forced value: enumerate assignments
                    n_int = len(ids) - 1
                    if len(forced) > n_int:
                        continue
                    import itertools
                    options = [()] if not forced else [c for c in itertools.combinations(range(n_int), len(forced))]
                    for slots in options:
                        budget[0] -= 1
                        if budget[0] < 0:
                            return None
                        at = {slot: forced[i] for i, slot in enumerate(slots)}
                        a2 = list(attempt)
                        P2 = list(P)
                        P2[s_node], P2[e_node] = val, ev
                        span, cum, ok = float(ev - val), float(val), True
                        for k, cell in enumerate(ids[:-1]):
                            cum += zones[cell.zone_id].target_area_m2 / row_tot[r] * span
                            ivc = _prefix_interval(N - 1, cons + a2, cell.c1)
                            if ivc is None or ivc[0] > ivc[1]:
                                ok = False; break
                            v = at.get(k, max(ivc[0], min(ivc[1], int(round(cum)))))
                            if not (ivc[0] <= v <= ivc[1]):
                                ok = False; break
                            a2 += [(0, cell.c1, v), (cell.c1, 0, -v)]; P2[cell.c1] = v
                        if not ok:
                            continue
                        bounds = [P2[i] for i in band_nodes[r]]
                        res = place(r + 1, a2, P2, bounds, val, float(ev - val))
                        if res is not None:
                            return res
            return None

        P = place(0, [], [0] * N, None, None, None)
        if P is None:
            _t(f"  no aligned placement within the LP budget"); return None
        fixed = []
        if _bellman_ford_from(N - 1, cons + fixed, 0) is None:
            _t(f"  final system infeasible with P={P}"); return None
        _t(f"  OK P={P}")
        return P

    def point_in_box(hL, hU):
        h = [max(hL[r], min(hU[r], int(round(h_est[r])))) for r in range(R)]
        return None if sum(h) > h_cap else h

    def finish(h, P, nodes):
        band_x = tuple(tuple(P[i] for i in band_nodes[r]) for r in range(R))
        return StaircaseSizing("FEASIBLE", tuple(h), band_x, nodes, y_start_u=y_start)

    t0 = time.monotonic()
    nodes = 0
    aligned_failures = 0
    gap: tuple | None = None
    # ALTERNATING EXACT PROJECTIONS FIRST (the Gate-2 pivot, #197). Heights and widths are coupled
    # through each cell's area, and sampling heights blindly misses the thin feasible set an L's
    # leg leaves. At FIXED widths each band's feasible height interval is exact (area bounds over
    # the cell's width, short side, aspect, door heights); at FIXED heights the width system is
    # exact (`choose`). Alternate from an envelope-aware seed — a band's area over the envelope's
    # width AT ITS DEPTH, which is what makes an L's leg bands taller. A hit is exact; a miss
    # falls through to the enumeration and the branch-and-bound.
    ext_inset = inset_u(WallType.EXTERIOR)
    cells_by_band = [[c for c in cells if c.r == r] for r in range(R)]

    def seed_heights() -> list[int]:
        h, y = [], y_start
        for r in range(R):
            ivs = envelope.extent_u(y, y + max(1, hL0[r]))
            W = (ivs[0][1] - ivs[0][0]) if len(ivs) == 1 else envelope.width_u
            est = int(round(row_tot[r] / (UNIT_M * UNIT_M) / max(W, 1)))
            hr = max(hL0[r], min(hU0[r], est))
            h.append(hr); y += hr
        return h

    def project_heights(h: list[int]) -> list[int] | None:
        """Each band's exact height interval at the widths its cells would get inside the band's
        extent at the current depths; the nearest value to the current height; None if a band
        has no interval at all at any width (then nothing here helps)."""
        ext, bad, _ivs = extents_for(h, h)
        if ext is None:
            return None
        out = []
        prev_w: float | None = None
        for r in range(R):
            L, Rr = ext[r]
            W = min(Rr - L, max(row_tot[r] / (UNIT_M * UNIT_M) / max(h[r], 1), prev_w or 0))
            W = max(W, 1.0)
            lo_r, hi_r = hL0[r], hU0[r]
            for c in cells_by_band[r]:
                z = zones[c.zone_id]
                w_net = max(1.0, W * z.target_area_m2 / row_tot[r] - c.inset_w_u)
                a_lo, a_hi = c.min_area_m2 / (UNIT_M * UNIT_M), c.max_area_m2 / (UNIT_M * UNIT_M)
                lo_c = max(math.ceil(a_lo / w_net), m_to_u(c.min_short_m), math.ceil(w_net / c.max_aspect))
                hi_c = min(math.floor(a_hi / w_net), math.floor(w_net * c.max_aspect))
                lo_r, hi_r = max(lo_r, lo_c + c.inset_h_u), min(hi_r, hi_c + c.inset_h_u)
            if lo_r > hi_r:
                mid = (lo_r + hi_r) // 2                  # nudge toward the conflict, keep iterating
                lo_r = hi_r = max(hL0[r], min(hU0[r], mid))
            out.append(max(lo_r, min(hi_r, h[r])))
            prev_w = W
        if sum(out) > h_cap:                              # scale the slack down, never below minimums
            excess = sum(out) - h_cap
            for r in sorted(range(R), key=lambda i: -(out[i] - hL0[i])):
                take = min(excess, out[r] - hL0[r]); out[r] -= take; excess -= take
            if excess > 0:
                return None
        return out

    h = seed_heights()
    for _it in range(ALTERNATION_ROUNDS):
        if sum(h) <= h_cap:
            nodes += 1
            P = choose(h)
            if P is not None:
                return finish(h, P, nodes)
        nxt = project_heights(h)
        if nxt is None or nxt == h:
            break
        h = nxt

    # bounded enumeration next — see module notes on why the B&B relaxation is weak here
    import itertools
    base = seed if (seed is not None and all(hL0[r] <= seed[r] <= hU0[r] for r in range(R))) \
        else list(h)
    steps = (0, -4, 4, -8, 8, -14, 14, -22, 22)
    tried = 0
    for deltas in itertools.product(steps, repeat=R):
        if tried >= ENUMERATION_BUDGET:
            break
        h = [base[r] + deltas[r] for r in range(R)]
        if any(h[r] < hL0[r] or h[r] > hU0[r] for r in range(R)) or sum(h) > h_cap:
            continue
        tried += 1
        nodes += 1
        P = choose(h)
        if P is not None:
            return finish(h, P, nodes)
    stack = [(hL0, hU0)]
    if seed is not None and all(hL0[r] <= seed[r] <= hU0[r] for r in range(R)):
        stack.append((list(seed), list(seed)))        # tried first: the previous round's heights
    while stack:
        hL, hU = stack.pop()
        nodes += 1
        if nodes > node_limit:
            return StaircaseSizing("UNKNOWN", nodes=nodes, detail=f"node budget exhausted ({node_limit} nodes)")
        if sum(hL) > h_cap:
            continue
        ext, bad, ivs = extents_for(hL, hU)
        if ext is None:
            # the tightest placement of the offending band inside this box: its earliest start
            # at its minimum height. Split there too means every placement in the box is split.
            y0 = y_start + sum(hL[:bad])
            tight = envelope.extent_u(y0, y0 + max(1, hL[bad]))
            if hL == hU or len(tight) != 1:
                gap = (bad, ivs)
                continue
            # a split extent over a WIDE box may close at a narrower one; keep bisecting
            if hL != hU:
                r = max(range(R), key=lambda i: (hU[i] - hL[i], -i))
                mid = (hL[r] + hU[r]) // 2
                stack.append((list(hL), hU[:r] + [mid] + hU[r + 1:]))
                stack.append((hL[:r] + [mid + 1] + hL[r + 1:], list(hU)))
            continue
        if not feasible_box(hL, hU):
            continue
        h = point_in_box(hL, hU)
        if h is not None:
            P = choose(h)
            if P is not None:
                return finish(h, P, nodes)
            aligned_failures += 1
            if aligned_failures >= MAX_CHOOSE_FAILURES:
                note = ""
                if windows:
                    y0, _y1 = windows[0]
                    note = (f"; the search was confined to the {h_cap * UNIT_M:.2f} m of depth above "
                            f"the envelope's split at {y0 * UNIT_M:.2f} m (formulation A, ADR-001 §4.A)")
                return StaircaseSizing("ALIGNMENT_UNSAT", nodes=nodes,
                                       detail=f"{aligned_failures} feasible height vectors had no width "
                                              f"choice whose steps land on cell boundaries of the "
                                              f"neighbouring band — not a proof of infeasibility{note}")
        if hL == hU:
            continue
        r = max(range(R), key=lambda i: (hU[i] - hL[i], -i))
        mid = (hL[r] + hU[r]) // 2
        lower = (list(hL), hU[:r] + [mid] + hU[r + 1:])
        upper = (hL[:r] + [mid + 1] + hL[r + 1:], list(hU))
        if h_est[r] > mid + 0.5:
            stack.append(lower); stack.append(upper)
        else:
            stack.append(upper); stack.append(lower)
    if aligned_failures:
        return StaircaseSizing("ALIGNMENT_UNSAT", nodes=nodes,
                               detail=f"{aligned_failures} feasible height vector(s) had widths but no "
                                      f"step landing on a cell boundary of the band above — not a "
                                      f"proof of infeasibility (the alignment choice is a snap)")
    if windows:
        # a complete INFEASIBLE under the capped depth is a statement about the split, not about
        # the programme: the depth beyond the split is there, formulation A just cannot use it
        y0, y1 = windows[0]
        return StaircaseSizing("BAND_GAP", nodes=nodes, detail=(
            f"no sizing fits in the {h_cap * UNIT_M:.2f} m of depth above the envelope's split at "
            f"{y0 * UNIT_M:.2f} m (complete search, {nodes} nodes); formulation A sizes one interval "
            f"per band and cannot use the depth beyond the split (ADR-001 §4.A)"))
    if gap is not None:
        bad, ivs = gap
        return StaircaseSizing("BAND_GAP", nodes=nodes,
                               detail=f"band {bad} ({'/'.join(bands[bad])}) meets the envelope in "
                                      f"{len(ivs)} intervals at its depth — formulation A sizes one "
                                      f"interval per band (ADR-001 §4.A)")
    return StaircaseSizing("INFEASIBLE", nodes=nodes,
                           detail=f"no band heights and widths satisfy every bound, contact and the "
                                  f"envelope ({nodes} nodes, complete)")
