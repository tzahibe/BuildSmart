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

from app.vertical_slice.band_embedding import _linear_orders
from app.vertical_slice.band_pipeline import _legal
from app.vertical_slice.band_sizing import CellSpec, _height_bounds
from app.vertical_slice.doors import ALLOWED_ENTRANCE_ROLES, ENTRANCE_DOOR_WIDTH_M
from app.vertical_slice.envelope import Envelope
from app.vertical_slice.exact.cells import CIRC, PUBLIC, STACKABLE, CellLayout, split
from app.vertical_slice.exact.milp_cells import HALL_MIN_WIDTH_M, _insets
from app.vertical_slice.exact.milp_oracle import FOYER_MAX_DEPTH_TO_WIDTH, FOYER_MIN_NET_M
from app.vertical_slice.exact.stacks import STACK_MAX_TARGET_M2, _tier
from app.vertical_slice.exact.screens import cells_selection
from app.vertical_slice.exposure_policy import REQUIRED_EXTERIOR_ROLES
from app.vertical_slice.geometry_core.model import UNIT_M, ProgramRole, m_to_u

#: zones that may occupy two consecutive rows (a hub two rows deep, a living room across two
#: bands) — `cells.moves` extends exactly these roles
SPANNING_ROLES = CIRC | PUBLIC
ROW_COUNTS = (2, 3, 4)
TOL_M2 = 0.01
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

    def w_min(self) -> float:
        """The least net width over the admissible heights (the sum of the cell's demands is
        decreasing then increasing in h: evaluate the ends and the crossing)."""
        lo, hi = self.net_h_range()
        pts = {lo, hi}
        cross = math.sqrt(max(self.area_lo_u2 * self.aspect, 1.0))
        if lo < cross < hi:
            pts.add(cross)
        return min(self.w_min_at(float(h)) for h in pts)


def _one_bounds(zi, z: str, r0: int, r1: int, iw: int, ih: int, h_cap: int) -> CellBounds:
    u2 = UNIT_M * UNIT_M
    c = CellSpec(z, r0, 0, 0, zi.min_area_m2, zi.max_area_m2, zi.min_short_side_m, zi.max_aspect_ratio, iw, ih)
    lo, hi = _height_bounds(c, TOL_M2, h_cap)
    role = getattr(zi, "role", None)
    w_floor, strip_cap, deeper = 0, 0.0, False
    if role in CIRC and r0 == 0:
        w_floor = max(w_floor, 3 * m_to_u(ENTRANCE_DOOR_WIDTH_M) - iw)
    if role in CIRC and r1 > r0:
        w_floor = max(w_floor, m_to_u(HALL_MIN_WIDTH_M))
    if role in CIRC and r0 == 0 and r1 == r0:
        f = m_to_u(FOYER_MIN_NET_M)
        w_floor = max(w_floor, f)
        strip_cap = float(FOYER_MAX_DEPTH_TO_WIDTH)
        lo = max(lo, ih + f)
        a_hi = (zi.max_area_m2 + TOL_M2) / u2
        hi = min(hi, ih + int(math.floor(math.sqrt(strip_cap * a_hi) + 1e-9)))
        if role is ProgramRole.CIRCULATION:
            deeper = True
            lo = max(lo, ih + w_floor + 1)
            hi = min(hi, ih + int(math.floor(a_hi / max(w_floor, 1) + 1e-9)))
    return CellBounds(z, lo, hi, iw, ih, m_to_u(zi.min_short_side_m),
                      zi.min_area_m2 / u2, (zi.max_area_m2 + TOL_M2) / u2, float(zi.max_aspect_ratio),
                      w_floor, strip_cap, deeper)


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

def precheck(layout: CellLayout, zones: dict, envelope: Envelope, *, frame=None, bounds=None) -> str | None:
    """The cheap feasibility question per row, before any MILP. None when nothing refuses; else
    the reason. A RELAXATION of `milp_cells`: a layout this refuses has no sizing at all.

    * every single-row cell admits some depth, and the cells of a row admit a common one;
    * the rows' minimum depths fit the usable depth; a spanning cell's rows can reach its range;
    * per row, the sum of its cells' least gross widths fits the widest cross-section among the
      depths the row can lie at (its top is at least the rows above it at their minimum depths,
      at most the usable depth minus the rows below at theirs)."""
    frame = frame or depth_frame(envelope)
    if frame is None:
        return "the envelope splits inside the usable depth window"
    y_start, h_cap, segments = frame
    R = layout.n_rows
    bounds = bounds or cell_bounds(layout, zones, h_cap)
    hL, hU = [1] * R, [h_cap] * R
    for z in layout.zones:
        b = bounds[z]
        if b.lo_h > b.hi_h:
            return f"{z}: no admissible depth"
        r0, r1 = layout.span(z)
        if r0 == r1:
            hL[r0] = max(hL[r0], b.lo_h); hU[r0] = min(hU[r0], b.hi_h)
    for r in range(R):
        if hL[r] > hU[r]:
            return f"row {r}: its cells have no common depth"
    if sum(hL) > h_cap:
        return f"the rows' minimum depths ({sum(hL)} u) exceed the usable depth ({h_cap} u)"
    for z in layout.zones:
        r0, r1 = layout.span(z)
        if r1 > r0:
            b = bounds[z]
            if sum(hL[r0:r1 + 1]) > b.hi_h or sum(hU[r0:r1 + 1]) < b.lo_h:
                return f"{z}: its rows cannot reach its depth range"
    for r, row in enumerate(layout.rows):
        need = sum(bounds[z].w_min() + bounds[z].iw for z in row)
        top_min = y_start + sum(hL[:r])
        bottom_max = y_start + h_cap - sum(hL[r + 1:])
        avail = max((R_ - L_ for (y0, y1, L_, R_) in segments if y0 < bottom_max and y1 > top_min), default=0)
        if need > avail + 1e-9:
            return f"row {r}: its cells need {need:.0f} u of width, the envelope offers {avail} u there"
    return None


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


def _comparable(pairs: list[tuple[int, int]]) -> bool:
    """Cross-row contacts along one seam must form a staircase: no two pairs crossing."""
    for (i, j), (i2, j2) in itertools.combinations(pairs, 2):
        if (i < i2 and j > j2) or (i > i2 and j < j2):
            return False
    return True


def generate(zones: dict, required, access, wet_rooms, envelope: Envelope, *, arrival: str | None,
             orient_tag: str = "H", row_counts=ROW_COUNTS, max_layouts: int = 200,
             node_limit: int = 20_000, orders_per_labeling: int = 16, orders_per_row: int = 40,
             deadline: float | None = None, stacks: bool = True):
    """Yield `CellLayout`s that pass `layout_rejections` and `precheck`, deterministically: row
    counts in order, labelings in DFS order from the hub, orders row by row. Every layout yielded
    claims `SCREENS`; the pre-check has been applied in the oracle's frame (`envelope` is already
    the transposed one for orient_tag "V")."""
    frame = depth_frame(envelope)
    if frame is None:
        return
    y_start, h_cap, _segments = frame
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
    # single-row depth bounds per zone, position-independent (partition insets: the loosest the
    # sizer can assign a middle cell; exterior/RC insets only widen them, so this is a relaxation)
    lo_single: dict[str, int] = {}
    u2 = UNIT_M * UNIT_M
    for z, zi in zones.items():
        c = CellSpec(z, 0, 0, 0, zi.min_area_m2, zi.max_area_m2, zi.min_short_side_m, zi.max_aspect_ratio, 2, 2)
        lo_single[z] = _height_bounds(c, TOL_M2, h_cap)[0]
    nodes = 0
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
                opts += [(r, r + 1) for r in range(R - 1)]
            for iv in opts:
                if any(not _touching(iv, n) for n in nbrs):
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
            # end, at most two per row; depth: the rows' minimum depths fit
            ends_needed = [0] * R
            for z, (r0, r1) in f.items():
                for r in range(r0, r1 + 1):
                    same = sum(1 for w in adj[z] if w in f and f[w][0] <= r <= f[w][1])
                    if same > 2:
                        return False
                if z in must_exterior and r0 > 0 and r1 < R - 1:
                    for r in range(r0, r1 + 1):
                        ends_needed[r] += 1
            if any(n > 2 for n in ends_needed):
                return False
            hL = [1] * R
            for z, (r0, r1) in f.items():
                if r0 == r1:
                    hL[r0] = max(hL[r0], lo_single[z])
            return sum(hL) <= h_cap

        def rec(i: int):
            nonlocal nodes
            if emitted >= max_layouts or out_of_time():
                return
            nodes += 1
            if nodes > node_limit:
                return
            if i == len(order):
                if all(any(r0 <= r <= r1 for (r0, r1) in f.values()) for r in range(R)):
                    rows = tuple(tuple(z for z in order if f[z][0] <= r <= f[z][1]) for r in range(R))
                    lay = CellLayout(rows)
                    relaxed = cell_bounds(lay, zones, h_cap, insets={z: (2, 2) for z in zones})
                    if precheck(lay, zones, envelope, frame=frame, bounds=relaxed) is None:
                        yield from orders_of(dict(f))
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
                for k, o in enumerate(_linear_orders(sorted(members[r]), es)):
                    if given >= orders_per_row or (k & 255 == 255 and out_of_time()):
                        return
                    if any(z in must_end and z not in (o[0], o[-1]) for z in o):
                        continue
                    if orient_tag == "V" and arrival in o and o[0] != arrival:
                        continue
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
            if layout_rejections(lay, zones, wet_rooms, access, arrival=arrival, orient_tag=orient_tag):
                continue
            if precheck(lay, zones, envelope, frame=frame) is not None:
                continue
            emitted += 1
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
