"""A screen-aware, bound-aware layout generator for the exact path (#208 — row 2 of the path to
execution, the #200 limit).

What #200 measured on the frozen six: of the cross-band layouts its enumerators produced, about
55 % failed production's SELECTION screens (no arrival room on the street, a foyer that does not
front it, a buried bedroom) because the enumerators did not know the screens, and about 45 % were
infeasible in the sizer because the programme's rooms do not fit the row structure inside the
envelope — the room bounds bind, alignment never binds alone. And the band embedder's plausibility
order ranks the few feasible layouts of an L or a court deep in its list (F2: 39 of 1920).

This module enumerates `CellLayout`s (`exact/cells.py`: rows of zone ids, a zone in consecutive
rows spans them — band, spine, stack and two-row rooms are all instances) the other way round:

  * the SCREENS are applied while the layout is being built, not after — the parti's arrival room
    is put in the street row; for a foyer parti the hall is kept off the street (else the hall
    outranks the foyer for the door and the foyer is a blind stub, #205's remaining C25s); a
    REQUIRED-exposure room or the safe room in a middle row must be at the row's end, so a middle
    row holds at most two; every direct-access pair is a possible, legal door; every room is
    reachable from the arrival room through legal required contacts;
  * the ROOM BOUNDS are applied per row before any MILP (`precheck`): every cell's admissible
    depth range (`band_sizing._height_bounds` — net short side, area, aspect, with the insets the
    unified sizer will use, and the oracle's entrance / foyer bounds on a fronting circulation
    cell), the rows' minimum depths against the usable depth, and per row the sum of the cells'
    minimum gross widths against the widest cross-section the row can reach at the depths its
    position allows. A relaxation of the sizer's own constraints, so it never refuses a layout the
    sizer would accept (test), and it costs microseconds;
  * the SEARCH goes where the embedder's order does not: every row count from 2 to 4, every
    zone-to-row assignment that keeps the required contacts possible (the hall and the public
    rooms may span two rows), in a deterministic DFS from the hub outward, bounded by a node
    budget and a deadline rather than by a plausibility rank.

Nothing here names a shape (owner, 2026-10-13): the envelope enters only as its cross-section per
depth. The layouts feed the existing `run_exact_pipeline` as the family "generator" — sized by
`milp_cells.cells_placement`, realized by `realize_cells`, judged by the unchanged validators and
the brain's preference — OFF in the preview until the day-3 gate says otherwise.
"""
from __future__ import annotations

import itertools
import math
import time
from dataclasses import dataclass

from app.vertical_slice.band_pipeline import _legal
from app.vertical_slice.band_sizing import CellSpec, _height_bounds
from app.vertical_slice.doors import ALLOWED_ENTRANCE_ROLES, ENTRANCE_DOOR_WIDTH_M
from app.vertical_slice.envelope import Envelope
from app.vertical_slice.exact.cells import CIRC, PUBLIC, STACKABLE, CellLayout, split
from app.vertical_slice.exact.milp_cells import HALL_MIN_WIDTH_M, _insets
from app.vertical_slice.exact.milp_oracle import FOYER_MAX_DEPTH_TO_WIDTH, FOYER_MIN_NET_M, _height_grid
from app.vertical_slice.exact.stacks import STACK_MAX_TARGET_M2, _tier
from app.vertical_slice.exact.screens import cells_selection
from app.vertical_slice.exposure_policy import REQUIRED_EXTERIOR_ROLES
from app.vertical_slice.geometry_core.model import UNIT_M, ProgramRole, m_to_u

#: zones that may occupy consecutive rows: a public room across two bands (`cells.moves` extends
#: exactly these roles), and a hub hall down a run of up to `HALL_MAX_SPAN` rows — the spine: a
#: hall with a dozen required neighbours cannot be one row's cell in a narrow frame (its cover of
#: the neighbours in the adjacent row exceeds the row), it has to run along several
SPANNING_ROLES = CIRC | PUBLIC
HALL_MAX_SPAN = 4
#: row counts searched when the caller names none: from 2 up to what the usable depth admits at
#: `MIN_ROW_DEPTH_M` per row, capped — a strip across the street (the V frame of a 24 x 9.5 m
#: site) needs five or six rows of two or three rooms, a 4-band layout with a stack is five
ROW_COUNTS = None
MAX_ROWS = 6
MIN_ROW_DEPTH_M = 2.0
TYPICAL_ROW_DEPTH_M = 4.0
TOL_M2 = 0.01
#: the height grid the pre-check walks — the unified sizer's own `k` (`exact_pipeline.CELLS_K`)
PRECHECK_K = 6
#: the screens a generated layout claims to pass, in the order they are asked
SCREENS = ("arrival_fronts_street", "foyer_holds_the_door", "entrance_feasible", "foyer_fronts_street",
           "exposure_ok", "access_contact_ok", "reachable_from_entrance")


# ------------------------------------------------------------------------------ the depth frame

def depth_frame(envelope: Envelope):
    """(y_start, h_cap, segments) exactly as `milp_cells` derives them: the first contiguous depth
    window whose cross-section is one interval, and per depth segment inside it the interval
    (y0, y1, L, R) in units. None when the envelope splits inside the window (BAND_GAP there)."""
    windows = envelope.split_depth_windows_u()
    y_start = 0
    while windows and windows[0][0] <= y_start:
        y_start = windows[0][1]; windows = windows[1:]
    h_cap = envelope.depth_u - y_start
    if windows:
        h_cap = min(h_cap, windows[0][0] - y_start)
    _, miny, _, _ = envelope.polygon.bounds
    step_ys = sorted({y_start, y_start + h_cap} | {m_to_u(vy - miny) for _, vy in envelope.vertices_m
                                                    if y_start < m_to_u(vy - miny) < y_start + h_cap})
    segments = []
    for y0, y1 in itertools.pairwise(step_ys):
        ivs = envelope.extent_u(y0, y1)
        if len(ivs) != 1:
            return None
        segments.append((y0, y1, ivs[0][0], ivs[0][1]))
    return y_start, h_cap, segments


# ------------------------------------------------------------------------------- cell bounds

@dataclass(frozen=True)
class CellBounds:
    """What the unified sizer will demand of one cell, read off the layout and the zone: the
    gross height range (units) and, at a net height, the net width range (units)."""
    zone_id: str
    lo_h: int
    hi_h: int
    iw: int
    ih: int
    min_short_u: int
    area_lo_u2: float
    area_hi_u2: float
    aspect: float
    w_floor_u: int = 0          # entrance / foyer: unconditional net width floor
    strip_cap: float = 0.0      # foyer: net height <= strip_cap x net width (0 = none)
    deeper_than_wide: bool = False
    #: the foyer group's own depth window (gross units) — a CONSTRAINT in the sizer, not a grid
    #: bound: the row's height grid is spanned by `lo_h`/`hi_h` alone, exactly as `milp_cells`
    #: spans it, and a grid height outside this window simply admits no width for the cell
    foyer_lo_h: int = 0
    foyer_hi_h: int = 10 ** 9

    def net_h_range(self) -> tuple[int, int]:
        return self.lo_h - self.ih, self.hi_h - self.ih

    def w_min_at(self, h_net: float) -> float:
        w = max(self.min_short_u, self.area_lo_u2 / h_net, h_net / self.aspect, self.w_floor_u)
        if self.strip_cap:
            w = max(w, h_net / self.strip_cap)
        return w

    def w_max_at(self, h_net: float) -> float:
        w = min(self.area_hi_u2 / h_net, self.aspect * h_net)
        if self.deeper_than_wide:
            w = min(w, h_net - 1)
        return w

    def w_min(self, lo_h: int | None = None, hi_h: int | None = None) -> float:
        """The least net width over the gross depths [lo_h, hi_h] (default: the cell's own range):
        the demand falls with depth (area) then rises (aspect), so the ends and the crossing."""
        lo = max(self.lo_h, self.foyer_lo_h) if lo_h is None else max(lo_h, self.lo_h, self.foyer_lo_h)
        hi = min(self.hi_h, self.foyer_hi_h) if hi_h is None else min(hi_h, self.hi_h, self.foyer_hi_h)
        lo_n, hi_n = max(1, lo - self.ih), max(1, hi - self.ih)
        if hi_n < lo_n:
            return float("inf")
        pts = {float(lo_n), float(hi_n)}
        cross = math.sqrt(max(self.area_lo_u2 * self.aspect, 1.0))
        if lo_n < cross < hi_n:
            pts.add(cross)
        return min(self.w_min_at(h) for h in pts)


def _one_bounds(zi, z: str, r0: int, r1: int, iw: int, ih: int, h_cap: int) -> CellBounds:
    u2 = UNIT_M * UNIT_M
    c = CellSpec(z, r0, 0, 0, zi.min_area_m2, zi.max_area_m2, zi.min_short_side_m, zi.max_aspect_ratio, iw, ih)
    lo, hi = _height_bounds(c, TOL_M2, h_cap)
    role = getattr(zi, "role", None)
    w_floor, strip_cap, deeper = 0, 0.0, False
    f_lo, f_hi = 0, 10 ** 9
    if role in CIRC and r0 == 0:
        w_floor = max(w_floor, 3 * m_to_u(ENTRANCE_DOOR_WIDTH_M) - iw)
    if role in CIRC and r1 > r0:
        w_floor = max(w_floor, m_to_u(HALL_MIN_WIDTH_M))
    if role in CIRC and r0 == 0 and r1 == r0:
        f = m_to_u(FOYER_MIN_NET_M)
        w_floor = max(w_floor, f)
        strip_cap = float(FOYER_MAX_DEPTH_TO_WIDTH)
        f_lo = max(f_lo, ih + f)
        a_hi = (zi.max_area_m2 + TOL_M2) / u2
        f_hi = min(f_hi, ih + int(math.floor(math.sqrt(strip_cap * a_hi) + 1e-9)))
        if role is ProgramRole.CIRCULATION:
            deeper = True
            f_lo = max(f_lo, ih + w_floor + 1)
            f_hi = min(f_hi, ih + int(math.floor(a_hi / max(w_floor, 1) + 1e-9)))
    return CellBounds(z, lo, hi, iw, ih, m_to_u(zi.min_short_side_m),
                      zi.min_area_m2 / u2, (zi.max_area_m2 + TOL_M2) / u2, float(zi.max_aspect_ratio),
                      w_floor, strip_cap, deeper, f_lo, f_hi)


def cell_bounds(layout: CellLayout, zones: dict, h_cap: int, insets: dict | None = None) -> dict[str, CellBounds]:
    """Per cell, the sizer's own bounds with the insets `milp_cells._insets` assigns the layout
    (exterior where a cell is first/last in its row or in the street/back row, partition
    elsewhere, RC for the safe room): `_height_bounds` for the depth range, the oracle's entrance
    rule (a fronting circulation cell is three door widths wide) and the "foyer" group (#205) on
    the single-row circulation cell in row 0, `HALL_MIN_WIDTH_M` on a circulation cell spanning
    rows. Every number is what the MILP will enforce, nothing stricter. `insets` overrides the
    layout's own (the enumerator passes partition insets everywhere — a relaxation — to refuse a
    zone-to-row assignment before any order of it is enumerated)."""
    insets = insets or _insets(layout, zones, None)
    out = {}
    for z in layout.zones:
        r0, r1 = layout.span(z)
        iw, ih = insets[z]
        out[z] = _one_bounds(zones[z], z, r0, r1, iw, ih, h_cap)
    return out


# --------------------------------------------------------------------------- the pre-check

def precheck(layout: CellLayout, zones: dict, envelope: Envelope, *, frame=None, bounds=None,
             k: int = PRECHECK_K, required=(), min_contact_u: dict | None = None,
             ordered: bool = True) -> str | None:
    """The cheap feasibility question per row, before any MILP. None when nothing refuses; else
    the reason. A RELAXATION of `milp_cells` (its "cells" and "envelope" groups, without the
    contacts, the alignment and the x-positions): a layout this refuses has no sizing at all.

    The sizer chooses every row's depth from the k-point grid `_height_grid` spans between the
    row's cells' common depth range; a cell's net width at that depth must lie between what its
    short side, minimum area and aspect demand and what its maximum area and aspect allow (plus
    the oracle's entrance/foyer bounds on a fronting circulation cell); a spanning cell's depth is
    the sum of its rows'. This walks the same grids: for every combination of row depths that fits
    the usable depth, every row's cells get their least gross widths at that depth and the sum is
    held to the width the envelope offers at every depth the row covers (the intersection of the
    cross-sections it overlaps — the sizer's own step rule). One combination that fits is enough.
    With `required` (and `min_contact_u`, `band_sizing.contact_requirements`), the sizer's contact
    rule is relaxed in too: two sequence-neighbours' shared wall is the depth of the rows they
    share, so those rows' depths sum to at least the door's need; and a cell whose required
    neighbours in the adjacent row are n_1..n_k (consecutive there — the staircase) reaches from
    `need` inside n_1 to `need` inside n_k, so it is at least the interior neighbours' least
    widths plus two needs wide — which its own area and aspect must allow at that depth. With
    `ordered=False` (a zone-to-row assignment whose orders are not chosen yet) the same two facts
    hold order-free: required pairs sharing a row WILL be sequence-neighbours there (the row's
    induced required graph is a linear forest), and of k neighbours in the adjacent row at least
    the k - 2 narrowest lie between the two ends.
    Costs microseconds to a few milliseconds (k^rows combinations, pruned row by row)."""
    frame = frame or depth_frame(envelope)
    if frame is None:
        return "the envelope splits inside the usable depth window"
    y_start, h_cap, segments = frame
    R = layout.n_rows
    bounds = bounds or cell_bounds(layout, zones, h_cap)
    span = {z: layout.span(z) for z in layout.zones}
    hL, hU = [1] * R, [h_cap] * R
    for z in layout.zones:
        b = bounds[z]
        if b.lo_h > b.hi_h:
            return f"{z}: no admissible depth"
        r0, r1 = span[z]
        if r0 == r1:
            hL[r0] = max(hL[r0], b.lo_h); hU[r0] = min(hU[r0], b.hi_h)
    for r in range(R):
        if hL[r] > hU[r]:
            return f"row {r}: its cells have no common depth"
    if sum(hL) > h_cap:
        return f"the rows' minimum depths ({sum(hL)} u) exceed the usable depth ({h_cap} u)"
    grids = [_height_grid(hL[r], hU[r], k) for r in range(R)]
    singles = [[z for z in row if span[z] == (r, r)] for r, row in enumerate(layout.rows)]
    spanning = [z for z in layout.zones if span[z][1] > span[z][0]]

    def need(z: str, H: int) -> float | None:
        """The least gross width of cell `z` at gross depth `H`, or None when no integer width
        satisfies its bounds there (the sizer's boundaries are integer grid units)."""
        b = bounds[z]
        hn = H - b.ih
        if hn < 1 or H < b.foyer_lo_h or H > b.foyer_hi_h:
            return None
        lo = math.ceil(b.w_min_at(float(hn)) - 1e-9)
        hi = math.floor(b.w_max_at(float(hn)) + 1e-9)
        return None if lo > hi else float(lo + b.iw)

    # per row, the admissible grid depths with the single-row cells' summed least widths
    options: list[list[tuple[int, float]]] = []
    for r in range(R):
        opts = []
        for H in grids[r]:
            tot = 0.0
            for z in singles[r]:
                n = need(z, H)
                if n is None:
                    break
                tot += n
            else:
                opts.append((H, tot))
        if not opts:
            return f"row {r}: no grid depth admits every cell"
        options.append(opts)

    def avail(y0: int, y1: int) -> float:
        touched = [(L_, R_) for (s0, s1, L_, R_) in segments if s0 < y1 and s1 > y0]
        if not touched:
            return 0.0
        return float(min(R_ for _, R_ in touched) - max(L_ for L_, _ in touched))

    min_rest = [sum(hL[r:]) for r in range(R + 1)]
    heights: list[int] = []
    reason = [f"no combination of row depths fits the rows' widths inside the envelope"]
    # the contact rule, relaxed: same-row pairs -> shared rows' depth; cross-row -> interior cover
    req = [tuple(e) for e in required]
    pos = [{z: i for i, z in enumerate(row)} for row in layout.rows]
    same_row: list[tuple[list[int], int]] = []
    cover: dict[str, list[tuple[int, list[str], int]]] = {z: [] for z in layout.zones}
    req_set = {frozenset(e) for e in req}
    for a, b in req:
        need_u = max(1, (min_contact_u or {}).get(frozenset((a, b)), 1))
        shared = [r for r in range(R) if a in pos[r] and b in pos[r] and (not ordered or abs(pos[r][a] - pos[r][b]) == 1)]
        if shared:
            same_row.append((shared, need_u))
    for z in layout.zones:
        r0, r1 = span[z]
        for rr in (r0 - 1, r1 + 1):
            if not (0 <= rr < R) or z in pos[rr]:
                continue
            nbrs = sorted((n for n in layout.rows[rr] if frozenset((z, n)) in req_set and n not in pos[r0]),
                          key=lambda n: pos[rr][n])
            if len(nbrs) >= 2:
                interior = layout.rows[rr][pos[rr][nbrs[0]] + 1:pos[rr][nbrs[-1]]] if ordered else nbrs
                needs = sorted(max(1, (min_contact_u or {}).get(frozenset((z, n)), 1)) for n in nbrs)
                cover[z].append((rr, list(interior), needs[0] + needs[1], ordered))

    def h_of(z: str) -> int:
        r0, r1 = span[z]
        return sum(heights[r0:r1 + 1])

    def walk(r: int, y: int) -> bool:
        if r == R:
            for z in spanning:
                b = bounds[z]
                Ht = h_of(z)
                if Ht < b.lo_h or Ht > b.hi_h or need(z, Ht) is None:
                    return False
            for shared, need_u in same_row:
                if sum(heights[rr] for rr in shared) < need_u:
                    return False
            ys = [y_start]
            for H in heights:
                ys.append(ys[-1] + H)
            # every cell's gross width floor: its own least width, raised by what it must cover
            wl = {z: need(z, h_of(z)) for z in layout.zones}
            for z, covers in cover.items():
                for _rr, interior, ends, is_ordered in covers:
                    inner = [wl[n] for n in interior] if is_ordered else sorted(wl[n] for n in interior)[:-2]
                    must = sum(inner) + ends
                    if must > wl[z]:
                        b = bounds[z]
                        if must - b.iw > math.floor(b.w_max_at(float(h_of(z) - b.ih)) + 1e-9):
                            return False
                        wl[z] = float(must)
            for rr in range(R):
                tot = sum(wl[z] for z in layout.rows[rr])
                if tot > avail(ys[rr], ys[rr + 1]) + 1e-9:
                    return False
            return True
        for H, tot in options[r]:
            if y + H + min_rest[r + 1] > y_start + h_cap:
                continue
            if tot > avail(y, y + H) + 1e-9:
                continue
            heights.append(H)
            if walk(r + 1, y + H):
                return True
            heights.pop()
        return False

    return None if walk(0, y_start) else reason[0]


# ------------------------------------------------------------------------------- the screens

def _fronting(layout: CellLayout, orient_tag: str) -> set[str]:
    return set(layout.rows[0]) if orient_tag == "H" else {row[0] for row in layout.rows}


def layout_rejections(layout: CellLayout, zones: dict, wet_rooms, access, *, arrival: str | None,
                      orient_tag: str = "H") -> list[str]:
    """Production's SELECTION questions asked of a cell layout (`cells_selection`: an arrival room
    fronts the street, a foyer fronts it, REQUIRED-exposure rooms and the safe room are exterior),
    plus the rest of `placement_flags`' HARD flags read off the layout — every direct-access pair
    is a possible contact and a legal door pair (`band_pipeline._legal`: the access-rules table and
    the wet-room entry policy); every room is reachable from the arrival room through legal
    required contacts — and the two facts about the front door the sizer and `resolve_entrance`
    will apply: the parti's own arrival room fronts the street, and when it is a foyer (role
    CIRCULATION) no hall fronts it, because a hall outranks a foyer for the door
    (`ENTRANCE_ZONE_PRIORITY`) and the foyer would be left a blind stub beside the entrance (C25)."""
    role = lambda z: getattr(zones[z], "role", None)
    failed = []
    fronting = _fronting(layout, orient_tag)
    if arrival is not None and arrival in zones:
        if arrival not in fronting:
            failed.append("arrival_fronts_street")
        if role(arrival) is ProgramRole.CIRCULATION and any(role(z) is ProgramRole.HALL for z in fronting):
            failed.append("foyer_holds_the_door")
    failed.extend(cells_selection(layout, zones, orient_tag))
    roles = {z: role(z) for z in layout.zones}
    wet = {w.zone_id: w for w in wet_rooms}
    poss = layout.possible_contacts()
    pairs = [(a, b) for a, b in access if a in roles and b in roles and a != b]
    if any(frozenset(e) not in poss or not _legal(roles, wet, *e) for e in pairs):
        failed.append("access_contact_ok")
    starts = [z for z in layout.zones if roles[z] in ALLOWED_ENTRANCE_ROLES and z in fronting]
    if starts:
        start = arrival if arrival in starts else sorted(starts)[0]
        reach = {start}; stack = [start]
        legal = [e for e in poss if _legal(roles, wet, *tuple(e))]
        while stack:
            x = stack.pop()
            for e in legal:
                if x in e:
                    y = next(iter(e - {x}))
                    if y not in reach:
                        reach.add(y); stack.append(y)
        if len(reach) != len(layout.zones):
            failed.append("reachable_from_entrance")
    return failed


# ---------------------------------------------------------------------------- the enumerator

def _order(zones: dict, adj: dict) -> list[str]:
    hub = max(zones, key=lambda r: (len(adj[r]), r))
    out, seen, queue = [], {hub}, [hub]
    while queue:
        v = queue.pop(0); out.append(v)
        for w in sorted(adj[v], key=lambda r: (-len(adj[r]), r)):
            if w not in seen:
                seen.add(w); queue.append(w)
    for v in sorted(zones, key=lambda r: (-len(adj[r]), r)):
        if v not in seen:
            seen.add(v); out.append(v)
    return out


def _touching(a: tuple[int, int], b: tuple[int, int]) -> bool:
    """Two row intervals that can share a wall: they overlap (sequence neighbours in a row) or
    are adjacent (an x-overlap across the rows' seam)."""
    (a0, a1), (b0, b1) = a, b
    return (a0 <= b1 and b0 <= a1) or a1 + 1 == b0 or b1 + 1 == a0


def _units(members: list[str], es: frozenset) -> list[tuple[str, ...]] | None:
    """The paths of the row's induced required graph (a linear forest), as `_linear_orders`
    derives them; None when a room has three required neighbours in the row or a cycle exists."""
    inner = {e for e in es if e <= set(members)}
    deg = {m: 0 for m in members}
    adj = {m: [] for m in members}
    for e in inner:
        a, b = tuple(e)
        deg[a] += 1; deg[b] += 1
        adj[a].append(b); adj[b].append(a)
    if any(d > 2 for d in deg.values()):
        return None
    seen: set = set()
    paths = []
    for m in sorted(members):
        if m in seen:
            continue
        comp, stack = [], [m]
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x); comp.append(x)
            stack.extend(adj[x])
        ends = [x for x in comp if deg[x] <= 1]
        if len(comp) > 1 and len(ends) != 2:
            return None
        if len(comp) == 1:
            paths.append((m,)); continue
        start = sorted(ends)[0]
        path, prev, cur = [start], None, start
        while True:
            nxt = [y for y in adj[cur] if y != prev]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            path.append(cur)
        paths.append(tuple(path))
    return paths


def _row_orders(members: list[str], es: frozenset, must_end: set, anchor: dict | None, *, first=None,
                middle_perms: int = 6):
    """Orders of a row: its path units concatenated, built WITH the end constraints — a unit that
    holds a must-end room is placed first or last with that room outward — and the middle units
    ordered by `anchor` (a room -> position hint from the row above, so the staircase with it is
    met early) with a few permutations around that order. `first` pins one room to position 0
    (the arrival room across the street). Lazy and deterministic."""
    units = _units(members, es)
    if units is None:
        return
    ends_in = {u: [z for z in dict.fromkeys((u[0], u[-1])) if z in must_end] for u in units}
    if any(z in must_end and z not in (u[0], u[-1]) for u in units for z in u):
        return
    if sum(len(v) for v in ends_in.values()) > 2 or (first is not None and sum(len(ends_in[u]) for u in units if first not in u) > 1):
        return

    def oriented(u, outward_at_start: str | None, outward_at_end: str | None):
        """The orientations of `u` whose first/last room is the one asked for."""
        for seq in ((u, tuple(reversed(u))) if len(u) > 1 else (u,)):
            if outward_at_start is not None and seq[0] != outward_at_start:
                continue
            if outward_at_end is not None and seq[-1] != outward_at_end:
                continue
            yield seq

    def key(u):
        if anchor:
            hints = [anchor[z] for z in u if z in anchor]
            if hints:
                return (0, sum(hints) / len(hints), u)
        return (1, 0.0, u)

    seen: set = set()
    n = len(units)
    if n == 1:
        u = units[0]
        for seq in oriented(u, first, None):
            if all(z in (seq[0], seq[-1]) for z in ends_in[u]) and (seq[0] not in must_end or True):
                yield seq
        return
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            uf, ul = units[i], units[j]
            middle = sorted((u for k, u in enumerate(units) if k not in (i, j)), key=key)
            # every must-end room must be outward: in uf's first position or ul's last
            if any(ends_in[u] for u in middle):
                continue
            for sf in oriented(uf, first, None):
                if any(z != sf[0] for z in ends_in[uf]) or (first is not None and sf[0] != first):
                    continue
                for sl in oriented(ul, None, None):
                    if any(z != sl[-1] for z in ends_in[ul]):
                        continue
                    perms = [middle]
                    for perm in itertools.permutations(middle):
                        if len(perms) >= middle_perms:
                            break
                        if list(perm) != middle:
                            perms.append(list(perm))
                    for mid in perms:
                        for bits in range(1 << len(mid)):
                            seq = list(sf)
                            for k, u in enumerate(mid):
                                seq.extend(reversed(u) if (bits >> k) & 1 and len(u) > 1 else u)
                            seq.extend(sl)
                            t = tuple(seq)
                            if t not in seen:
                                seen.add(t)
                                yield t


def _comparable(pairs: list[tuple[int, int]]) -> bool:
    """Cross-row contacts along one seam must form a staircase: no two pairs crossing."""
    for (i, j), (i2, j2) in itertools.combinations(pairs, 2):
        if (i < i2 and j > j2) or (i > i2 and j < j2):
            return False
    return True


def generate(zones: dict, required, access, wet_rooms, envelope: Envelope, *, arrival: str | None,
             orient_tag: str = "H", row_counts=None, max_layouts: int = 200,
             node_limit: int = 20_000, orders_per_labeling: int = 16, orders_per_row: int = 40,
             deadline: float | None = None, stacks: bool = True, min_contact_u: dict | None = None,
             stats: dict | None = None):
    """Yield `CellLayout`s that pass `layout_rejections` and `precheck`, deterministically: row
    counts in order, labelings in DFS order from the hub, orders row by row. Every layout yielded
    claims `SCREENS`; the pre-check has been applied in the oracle's frame (`envelope` is already
    the transposed one for orient_tag "V")."""
    frame = depth_frame(envelope)
    if frame is None:
        return
    y_start, h_cap, _segments = frame
    widest = max(R_ - L_ for (_y0, _y1, L_, R_) in _segments)
    req = [tuple(e) for e in required]
    es = frozenset(frozenset(e) for e in req)
    adj: dict[str, set[str]] = {z: set() for z in zones}
    for a, b in req:
        adj[a].add(b); adj[b].add(a)
    order = _order(zones, adj)
    role = lambda z: getattr(zones[z], "role", None)
    must_exterior = {z for z in zones if role(z) in REQUIRED_EXTERIOR_ROLES or role(z) is ProgramRole.SAFE_ROOM}
    halls = [z for z in zones if role(z) is ProgramRole.HALL]
    foyer_parti = arrival is not None and arrival in zones and role(arrival) is ProgramRole.CIRCULATION
    # interchangeable rooms (four bedrooms off the hall: same role, bounds and required
    # neighbours) are assigned in non-decreasing row order — one representative per permutation
    twin_of: dict[str, str] = {}
    signature = lambda z: (role(z), zones[z].min_area_m2, zones[z].max_area_m2, zones[z].min_short_side_m,
                           zones[z].max_aspect_ratio, frozenset(adj[z]))
    for z in order:
        for w in order:
            if w == z:
                break
            if signature(w) == signature(z) and w not in twin_of.values():
                twin_of[z] = w
                break
    # every room's narrowest gross width (single row, at its deepest): the capacity bound below
    narrowest = {}
    for z in zones:
        b = _one_bounds(zones[z], z, 1, 1, 2, 2, h_cap)
        narrowest[z] = min(b.w_min() + b.iw, float(widest))
    # single-row depth bounds per zone, position-independent (partition insets: the loosest the
    # sizer can assign a middle cell; exterior/RC insets only widen them, so this is a relaxation)
    relaxed: dict[tuple[str, bool, bool], CellBounds] = {}

    def rb(z: str, fronting: bool, spanning: bool) -> CellBounds:
        key = (z, fronting, spanning)
        if key not in relaxed:
            relaxed[key] = _one_bounds(zones[z], z, 0 if fronting else 1, (1 if fronting else 2) if spanning else (0 if fronting else 1), 2, 2, h_cap)
        return relaxed[key]

    widest = max(R_ - L_ for (_y0, _y1, L_, R_) in _segments)
    if row_counts is None:
        # the most plausible row count first — the programme's area over the frame's width at a
        # typical row depth — then outward from it, so a strip across the street (six rows of two
        # or three rooms) is not reached only after the budgets of 2, 3, 4 and 5 rows are spent
        most = max(2, min(MAX_ROWS, h_cap // m_to_u(MIN_ROW_DEPTH_M)))
        total_m2 = sum(zi.target_area_m2 for zi in zones.values())
        guess = round(total_m2 / max(widest * UNIT_M * TYPICAL_ROW_DEPTH_M, 1.0))
        guess = max(2, min(most, guess))
        row_counts = tuple(sorted(range(2, most + 1), key=lambda r: (abs(r - guess), r)))
    stats = stats if stats is not None else {}
    stats.update({"nodes": 0, "labelings": 0, "labelings_refused": 0, "layouts": 0, "screened_out": 0,
                  "prechecked_out": 0, "emitted": 0, "row_counts": row_counts, "sample_labelings": [],
                  "refusals": {}, "sample_refused": []})
    emitted = 0
    seen: set = set()

    def out_of_time() -> bool:
        return deadline is not None and time.monotonic() > deadline

    for R in row_counts:
        if emitted >= max_layouts or out_of_time():
            return
        f: dict[str, tuple[int, int]] = {}

        def choices(v: str):
            nbrs = [f[w] for w in adj[v] if w in f]
            opts = [(r, r) for r in range(R)]
            if role(v) in SPANNING_ROLES and not (foyer_parti and v == arrival):
                longest = HALL_MAX_SPAN if role(v) is ProgramRole.HALL else 2
                opts += [(r, r + d) for d in range(1, longest) for r in range(R - d)]
            for iv in opts:
                if any(not _touching(iv, n) for n in nbrs):
                    continue
                if v in twin_of and twin_of[v] in f and iv < f[twin_of[v]]:
                    continue
                if orient_tag == "H":
                    if v == arrival and iv[0] != 0:
                        continue
                    if foyer_parti and v in halls and iv[0] == 0:
                        continue
                yield iv

        def consistent() -> bool:
            # same-row required neighbours: at most two per zone per row (a row's induced required
            # graph is a linear forest); exposure: a middle-row REQUIRED-exposure room must be a row
            # end, at most two per row; depth: the rows' minimum depths fit; width: at the row's
            # largest common depth (where every cell is narrowest) the cells assigned so far must
            # fit the widest cross-section — a relaxation that prunes most dead assignments early
            ends_needed = [0] * R
            members = [[] for _ in range(R)]
            for z, (r0, r1) in f.items():
                for r in range(r0, r1 + 1):
                    members[r].append(z)
                    same = sum(1 for w in adj[z] if w in f and f[w][0] <= r <= f[w][1])
                    if same > 2:
                        return False
                if z in must_exterior and r0 > 0 and r1 < R - 1:
                    for r in range(r0, r1 + 1):
                        ends_needed[r] += 1
            if any(n > 2 for n in ends_needed):
                return False
            # a row's induced required graph must be a linear forest (no cycle: a triangle of a
            # hub and two chained bedrooms has no consecutive order)
            if any(len(m) >= 3 and _units(m, es) is None for m in members):
                return False
            hL, hU = [1] * R, [h_cap] * R
            for z, (r0, r1) in f.items():
                if r0 == r1:
                    b = rb(z, r0 == 0, False)
                    hL[r0] = max(hL[r0], b.lo_h); hU[r0] = min(hU[r0], b.hi_h)
            if any(hL[r] > hU[r] for r in range(R)) or sum(hL) > h_cap:
                return False
            room_left = [0.0] * R
            for r in range(R):
                tot = 0.0
                for z, (r0, r1) in f.items():
                    if r0 == r == r1:
                        b = rb(z, r0 == 0, False)
                        tot += b.w_min(hL[r], hU[r]) + b.iw
                    elif r0 <= r <= r1:
                        b = rb(z, r0 == 0, True)
                        tot += b.w_min(sum(hL[r0:r1 + 1]), sum(hU[r0:r1 + 1])) + b.iw
                if tot > widest + 1e-9:
                    return False
                room_left[r] = widest - tot
            # what is not assigned yet must still fit somewhere: its narrowest widths against the
            # rows' remaining width
            unassigned = sum(narrowest[z] for z in zones if z not in f)
            return unassigned <= sum(room_left) + 1e-9

        nodes = 0

        def rec(i: int):
            nonlocal nodes
            if emitted >= max_layouts or out_of_time():
                return
            nodes += 1
            stats["nodes"] += 1
            if nodes > node_limit:
                return
            if i == len(order):
                if all(any(r0 <= r <= r1 for (r0, r1) in f.values()) for r in range(R)):
                    stats["labelings"] += 1
                    rows = tuple(tuple(z for z in order if f[z][0] <= r <= f[z][1]) for r in range(R))
                    lay = CellLayout(rows)
                    loose = cell_bounds(lay, zones, h_cap, insets={z: (2, 2) for z in zones})
                    why = precheck(lay, zones, envelope, frame=frame, bounds=loose, required=req,
                                   min_contact_u=min_contact_u, ordered=False)
                    if why is None:
                        if len(stats["sample_labelings"]) < 3:
                            stats["sample_labelings"].append(rows)
                        yield from orders_of(dict(f))
                    else:
                        stats["labelings_refused"] += 1
                        key = why.split(":")[0] if why.startswith("row") else why[:60]
                        stats["refusals"][key] = stats["refusals"].get(key, 0) + 1
                        if len(stats["sample_refused"]) < 3:
                            stats["sample_refused"].append((rows, why))
                return
            v = order[i]
            for iv in choices(v):
                f[v] = iv
                if consistent():
                    yield from rec(i + 1)
                del f[v]
                if emitted >= max_layouts or nodes > node_limit or out_of_time():
                    return

        def orders_of(lab: dict[str, tuple[int, int]]):
            members = [[z for z in order if lab[z][0] <= r <= lab[z][1]] for r in range(R)]
            must_end = {z for z in must_exterior if lab[z][0] > 0 and lab[z][1] < R - 1}
            got = 0

            def row_options(r: int, prev: tuple[str, ...] | None):
                given = 0
                anchor = None
                if prev is not None:
                    pos_prev = {z: k for k, z in enumerate(prev)}
                    anchor = {}
                    for z in members[r]:
                        hints = [pos_prev[w] for w in adj[z] if w in pos_prev] + ([pos_prev[z]] if z in pos_prev else [])
                        if hints:
                            anchor[z] = sum(hints) / len(hints)
                pin = arrival if (orient_tag == "V" and arrival in members[r]) else None
                for k, o in enumerate(_row_orders(members[r], es, must_end & set(members[r]), anchor, first=pin)):
                    if given >= orders_per_row or (k & 255 == 255 and out_of_time()):
                        return
                    if prev is not None:
                        # C22 for a zone in both rows: first in both or neither, last in both or neither
                        ok = True
                        for z in o:
                            if z in prev and ((prev[0] == z) != (o[0] == z) or (prev[-1] == z) != (o[-1] == z)):
                                ok = False; break
                        if not ok:
                            continue
                        # the seam's contacts form a staircase (zones in both rows are fixed points)
                        pos_p = {z: k for k, z in enumerate(prev)}; pos_o = {z: k for k, z in enumerate(o)}
                        pairs = [(pos_p[z], pos_o[z]) for z in o if z in pos_p]
                        for a in prev:
                            if a in pos_o:
                                continue
                            for b in o:
                                if b not in pos_p and frozenset((a, b)) in es:
                                    pairs.append((pos_p[a], pos_o[b]))
                        if not _comparable(pairs):
                            continue
                    given += 1
                    yield o

            def rows_rec(r: int, rows: tuple):
                nonlocal got
                if got >= orders_per_labeling or out_of_time():
                    return
                if r == R:
                    yield rows
                    got += 1
                    return
                for o in row_options(r, rows[-1] if rows else None):
                    yield from rows_rec(r + 1, rows + (o,))
                    if got >= orders_per_labeling or out_of_time():
                        return

            for rows in rows_rec(0, ()):
                lay = CellLayout(rows)
                if lay.rows in seen or lay.problems() or not lay.admits(req):
                    continue
                seen.add(lay.rows)
                yield lay
                if stacks:
                    for cand in _stacked(lay, zones):
                        if cand.rows not in seen and not cand.problems() and cand.admits(req):
                            seen.add(cand.rows)
                            yield cand

        for lay in rec(0):
            stats["layouts"] += 1
            if layout_rejections(lay, zones, wet_rooms, access, arrival=arrival, orient_tag=orient_tag):
                stats["screened_out"] += 1
                continue
            if precheck(lay, zones, envelope, frame=frame, required=req, min_contact_u=min_contact_u) is not None:
                stats["prechecked_out"] += 1
                continue
            emitted += 1
            stats["emitted"] = emitted
            yield lay
            if emitted >= max_layouts:
                return


def _stacked(layout: CellLayout, zones: dict):
    """The stacks of `layout`: every pair of sequence-neighbouring stackable rooms of one tier
    (`stacks.propose_stacks`' rule: wet with wet, public with public, bedroom with bedroom, each
    small enough) in a single row, split into two sub-rows (`cells.split`), both orders — the
    wet-room form that won the L in #200."""
    def stackable(z):
        zi = zones.get(z)
        return getattr(zi, "role", None) in STACKABLE and zi.target_area_m2 <= STACK_MAX_TARGET_M2
    for r, row in enumerate(layout.rows):
        for a, b in itertools.pairwise(row):
            if stackable(a) and stackable(b) and _tier(zones[a].role) == _tier(zones[b].role):
                for top, bottom in ((a, b), (b, a)):
                    cand = split(layout, r, top, bottom)
                    if cand is not None:
                        yield cand


__all__ = ["CellBounds", "SCREENS", "cell_bounds", "depth_frame", "generate", "layout_rejections", "precheck"]
