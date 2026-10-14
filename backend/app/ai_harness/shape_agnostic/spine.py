"""Path B of ADR-001 / GATE-3 (#197): a cell that spans several bands — the vertical spine.

The band family's gap, stated precisely: every cell spans exactly its band's depth, so no room can
touch the street band AND the interior bands. The hub hall therefore sits in a middle band (no
entrance) and middle cells of middle bands have no exterior wall (no exposure). A SPINE closes
both: one circulation cell runs down through a contiguous run of bands — the SPINE SECTION — and
each of those bands splits into a LEFT part (cells ordered from the envelope inward), the spine,
and a RIGHT part (ordered from the spine outward). Plain full-width bands may sit ABOVE the section
(at the street: a public band the front door opens into) and BELOW it (at the back). Rooms stay
rectangles; nothing downstream changes; nothing here names a shape.

Facts the layout honours, each one a downstream rule read off the realizer, never a new rule:
  * every room the intent connects to the spine is innermost on its side, or sits in the plain band
    adjacent to the section (it then touches the spine's end; the sizer holds the overlap);
  * C22 (one wall type per side): the spine's east wall is abutted by a right part in EVERY band
    of the section or in none — so an occupied left and right side run the same number of bands;
  * the front door (`doors.resolve_entrance`): the street band holds an allowed arrival room with a
    full door width of wall each side of the door. A spine that fronts the street is that room —
    HALL outranks LIVING there — so it must be three door widths wide; otherwise the plain street
    band must hold an allowed arrival room.

The embedding REUSES `band_embedding.embed_band`: on each side component separately (its rows are
stacked, one block per component, so a side with k rooms off the spine has k rows — the one
packing the innermost rule allows), and on the top/bottom groups as full-width bands.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

from app.vertical_slice.band_embedding import BandEmbedding, embed_band
from app.vertical_slice.doors import ALLOWED_ENTRANCE_ROLES
from app.vertical_slice.geometry_core.model import ProgramRole

CIRC = {ProgramRole.HALL, ProgramRole.CIRCULATION}
PLAIN = ()   # type: tuple


@dataclass(frozen=True)
class SpineLayout:
    spine: str
    #: the spine section, top to bottom: (left cells from the envelope inward, right cells from the spine outward)
    bands: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]
    #: plain full-width bands above the section (street side) and below it, each left to right
    top: tuple[tuple[str, ...], ...] = ()
    bottom: tuple[tuple[str, ...], ...] = ()

    @property
    def cells(self) -> tuple[str, ...]:
        out = [self.spine]
        for b in self.top:
            out.extend(b)
        for left, right in self.bands:
            out.extend(left); out.extend(right)
        for b in self.bottom:
            out.extend(b)
        return tuple(out)

    @property
    def section(self) -> tuple[int, int]:
        """Row indices [a, b) of the spine section among all rows (top rows first)."""
        a = len(self.top)
        return a, a + len(self.bands)

    @property
    def n_rows(self) -> int:
        return len(self.top) + len(self.bands) + len(self.bottom)

    def row_of(self, zone_id: str) -> int:
        for r, b in enumerate(self.top):
            if zone_id in b:
                return r
        a = len(self.top)
        for r, (left, right) in enumerate(self.bands):
            if zone_id in left or zone_id in right:
                return a + r
        a += len(self.bands)
        for r, b in enumerate(self.bottom):
            if zone_id in b:
                return a + r
        raise KeyError(zone_id)


def choose_spine(zones: dict, edges) -> str | None:
    """The circulation node of highest degree — the hub. None when there is no circulation."""
    deg: dict[str, int] = {}
    for a, b in edges:
        deg[a] = deg.get(a, 0) + 1; deg[b] = deg.get(b, 0) + 1
    circ = [z for z, zi in zones.items() if zi.role in CIRC]
    if not circ:
        return None
    return max(circ, key=lambda z: (deg.get(z, 0), z))


def _components(nodes, edges) -> list[set[str]]:
    adj: dict[str, set[str]] = {n: set() for n in nodes}
    for a, b in edges:
        if a in adj and b in adj:
            adj[a].add(b); adj[b].add(a)
    seen, comps = set(), []
    for n in nodes:
        if n in seen:
            continue
        stack, comp = [n], set()
        while stack:
            x = stack.pop()
            if x in comp:
                continue
            comp.add(x); stack.extend(adj[x] - comp)
        seen |= comp; comps.append(comp)
    return comps


def _side_blocks(comp: set[str], zones: dict, inner, spine_nbrs: set[str], *, max_side_candidates: int,
                 inward_last: bool) -> list[tuple[tuple[str, ...], ...]]:
    """One side component's row blocks: `embed_band` on the component alone, keeping the candidates
    whose spine neighbours are all innermost (the row's last cell when the side is read from the
    envelope inward, its first when read from the spine outward)."""
    zs = {z: zones[z] for z in comp}
    es = [(a, b) for a, b in inner if a in zs and b in zs]
    emb = embed_band(zs, es, max_candidates=max_side_candidates)
    if not isinstance(emb, BandEmbedding):
        return []
    need = comp & spine_nbrs
    out = []
    for cand in emb.candidates:
        rows = tuple(tuple(b) for b in cand.bands)
        inner_cells = {row[-1] if inward_last else row[0] for row in rows}
        if need <= inner_cells:
            out.append(rows)
        else:
            # the same rows mirrored: the innermost end is a convention of the side, not of embed_band
            rows_m = tuple(tuple(reversed(row)) for row in rows)
            inner_m = {row[-1] if inward_last else row[0] for row in rows_m}
            if need <= inner_m:
                out.append(rows_m)
    return out


def _plain_group(comps: list[set[str]], zones: dict, inner, spine_nbrs: set[str], *, adjacent_last: bool,
                 max_side_candidates: int) -> list[tuple[tuple[str, ...], ...]]:
    """Full-width bands for the components above (adjacent band LAST) or below (adjacent band
    FIRST) the spine section: `embed_band` over the group, keeping candidates whose spine
    neighbours all sit in the band that touches the section. Both band orders are tried."""
    group = set().union(*comps) if comps else set()
    if not group:
        return [()]
    zs = {z: zones[z] for z in group}
    es = [(a, b) for a, b in inner if a in zs and b in zs]
    emb = embed_band(zs, es, max_candidates=max_side_candidates)
    if not isinstance(emb, BandEmbedding):
        return []
    need = group & spine_nbrs
    out, seen = [], set()
    for cand in emb.candidates:
        for rows in (tuple(tuple(b) for b in cand.bands), tuple(tuple(b) for b in reversed(cand.bands))):
            adj = set(rows[-1] if adjacent_last else rows[0])
            if need <= adj and rows not in seen:
                seen.add(rows); out.append(rows)
    return out


def _has_arrival_room(cells, zones: dict) -> bool:
    return any(getattr(zones[z], "role", None) in ALLOWED_ENTRANCE_ROLES for z in cells)


def embed_spine(zones: dict, edges, spine: str, *, max_candidates: int = 40,
                max_side_candidates: int = 30, uniform_sides: bool = True,
                max_orders: int = 24, max_plain_components: int = 2) -> list[SpineLayout]:
    """Every spine layout found (bounded), most plausible first. Empty when the contact graph
    cannot be split around the spine, or no side embeds."""
    edges = [tuple(e) for e in edges]
    others = [z for z in zones if z != spine]
    spine_nbrs = {b if a == spine else a for a, b in edges if spine in (a, b)}
    inner = [(a, b) for a, b in edges if spine not in (a, b)]
    comps = _components(others, inner)
    # every component must reach the spine (the whole graph is connected around it)
    if any(not (c & spine_nbrs) for c in comps):
        return []
    out: list[SpineLayout] = []
    seen: set = set()
    blocks_cache: dict = {}

    def blocks(ci: int, inward_last: bool):
        key = (ci, inward_last)
        if key not in blocks_cache:
            blocks_cache[key] = _side_blocks(comps[ci], zones, inner, spine_nbrs,
                                             max_side_candidates=max_side_candidates, inward_last=inward_last)
        return blocks_cache[key]

    # assign whole components to LEFT / RIGHT / TOP / BOTTOM; the assignments with the fewest rows
    # (balanced sides, few plain bands) come first — a side with k components is k rows deep
    def est(assignment):
        L = sum(1 for s in assignment if s == 0); Rr = sum(1 for s in assignment if s == 1)
        T = sum(1 for s in assignment if s == 2); B = sum(1 for s in assignment if s == 3)
        return (max(L, Rr) + (1 if T else 0) + (1 if B else 0), abs(L - Rr), T + B)
    # a plain band exists for the street room (and at most a companion) — the sides are where a
    # spine puts its rooms, and `embed_band` over a large plain group is the whole-programme
    # embedding again (F4: 4^9 assignments x that = ten minutes); so |top|, |bottom| <= 2 components
    assignments = [a for a in itertools.product((0, 1, 2, 3), repeat=len(comps))
                   if (any(s == 0 for s in a) or any(s == 1 for s in a))           # a spine needs a side
                   and sum(1 for s in a if s == 2) <= max_plain_components
                   and sum(1 for s in a if s == 3) <= max_plain_components]
    assignments.sort(key=lambda a: (est(a), a))
    plain_cache: dict = {}

    def plain(idx: list[int], adjacent_last: bool):
        key = (frozenset(idx), adjacent_last)
        if key not in plain_cache:
            plain_cache[key] = _plain_group([comps[i] for i in idx], zones, inner, spine_nbrs,
                                            adjacent_last=adjacent_last, max_side_candidates=max_side_candidates)
        return plain_cache[key]

    for assignment in assignments:
        L = [i for i, s in enumerate(assignment) if s == 0]
        Rr = [i for i, s in enumerate(assignment) if s == 1]
        T = [i for i, s in enumerate(assignment) if s == 2]
        B = [i for i, s in enumerate(assignment) if s == 3]
        mirror = tuple({0: 1, 1: 0}.get(s, s) for s in assignment)
        if L and Rr and tuple(assignment) > mirror:
            continue                                        # the mirror image is enumerated already
        tops = plain(T, True)
        bottoms = plain(B, False)
        if not tops or not bottoms:
            continue
        # a side's rows: one block per component, stacked, over a bounded set of orders
        def side_rows(idx: list[int], inward_last: bool):
            if not idx:
                return [()]
            per = [blocks(i, inward_last) for i in idx]
            if any(not p for p in per):
                return []
            rows_out = []
            for order in itertools.islice(itertools.permutations(range(len(idx))), max_orders):
                for choice in itertools.product(*(per[i] for i in order)):
                    rows_out.append(tuple(itertools.chain.from_iterable(choice)))
                    if len(rows_out) >= max_side_candidates:
                        return rows_out
            return rows_out
        lefts = side_rows(L, inward_last=True)
        rights = side_rows(Rr, inward_last=False)
        for top in tops:
            if top and not _has_arrival_room(top[0], zones):
                continue                                    # the street band must hold the arrival room
            for lb in lefts:
                for rb in rights:
                    if uniform_sides and lb and rb and len(lb) != len(rb):
                        continue                            # C22: the spine's side walls are each one wall type
                    n = max(len(lb), len(rb))
                    bands = tuple((lb[r] if r < len(lb) else (), rb[r] if r < len(rb) else ()) for r in range(n))
                    if any(not l and not rr for l, rr in bands):
                        continue
                    for bottom in bottoms:
                        layout = SpineLayout(spine, bands, top, bottom)
                        key = (bands, top, bottom)
                        if key in seen:
                            continue
                        seen.add(key)
                        out.append(layout)
                        if len(out) >= max_candidates:
                            return _ordered(out)
    return _ordered(out)


def _ordered(layouts: list[SpineLayout]) -> list[SpineLayout]:
    """Fewest rows first (a shallower house for the same rooms), then the balanced sides."""
    def key(lay):
        lefts = sum(1 for l, _ in lay.bands if l); rights = sum(1 for _, r in lay.bands if r)
        return (lay.n_rows, abs(lefts - rights), len(lay.top) + len(lay.bottom))
    return sorted(layouts, key=key)
