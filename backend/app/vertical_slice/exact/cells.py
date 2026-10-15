"""Cross-band cells (#200, owner directive 2026-10-14): ONE spatial representation for the band
family, the spine, the stack and a public room two bands deep —

    Cell = row interval x column interval.

A layout is a grid of ROWS (depth bands, top to bottom); each row is a left-to-right sequence of
zone ids, and a zone that appears in several consecutive rows SPANS them (one rectangle, its
column shared by every row it is in). A band layout is the special case where every zone is in
exactly one row; a spine is a circulation zone present in a run of rows; a stack is a row split in
two sub-rows where every other zone spans both and the two stacked zones take one sub-row each;
a living room two bands deep is a public zone present in two rows. Nothing names a shape.

Facts the layout keeps structurally (the sizer keeps the metric ones — overlaps, areas, insets):
  * a zone's rows are contiguous;
  * C22, one wall type per side: a spanning zone is first in ALL its rows or in none, and last in
    all or in none (its west/east wall is then partition everywhere or exterior everywhere);
  * every required contact is POSSIBLE: the two zones are sequence-neighbours in some row, or their
    row intervals are adjacent (the sizer then holds the x-overlap to the door's width).

Layouts are produced by MOVES on the band family's own candidates (`from_bands` + `moves`) — the
band embedding stays the exact, complete source of row sequences; a move changes depth, not order.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

from app.vertical_slice.geometry_core.model import ProgramRole

CIRC = frozenset({ProgramRole.HALL, ProgramRole.CIRCULATION})
PUBLIC = frozenset({ProgramRole.LIVING, ProgramRole.DINING, ProgramRole.KITCHEN})
#: zones a stack may hold (`stacks.py`'s tiers, minus the big public room)
STACKABLE = frozenset({ProgramRole.BATHROOM, ProgramRole.TOILET, ProgramRole.STORAGE, ProgramRole.KITCHEN,
                       ProgramRole.DINING, ProgramRole.BEDROOM, ProgramRole.MASTER_BEDROOM})


@dataclass(frozen=True)
class CellLayout:
    rows: tuple[tuple[str, ...], ...]

    @property
    def n_rows(self) -> int:
        return len(self.rows)

    def span(self, zone_id: str) -> tuple[int, int]:
        rs = [r for r, row in enumerate(self.rows) if zone_id in row]
        return rs[0], rs[-1]

    @property
    def zones(self) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for row in self.rows:
            for z in row:
                seen.setdefault(z, None)
        return tuple(seen)

    @property
    def spanning(self) -> tuple[str, ...]:
        return tuple(z for z in self.zones if self.span(z)[0] != self.span(z)[1])

    def problems(self) -> list[str]:
        out = []
        for z in self.zones:
            rs = [r for r, row in enumerate(self.rows) if z in row]
            if rs != list(range(rs[0], rs[-1] + 1)):
                out.append(f"{z}: rows {rs} are not contiguous")
            if any(row.count(z) > 1 for row in self.rows):
                out.append(f"{z}: twice in one row")
            firsts = {self.rows[r][0] == z for r in rs}
            lasts = {self.rows[r][-1] == z for r in rs}
            if len(firsts) > 1 or len(lasts) > 1:
                out.append(f"{z}: at a row's end in some of its rows only (C22)")
        if any(not row for row in self.rows):
            out.append("an empty row")
        return out

    def possible_contacts(self) -> set[frozenset]:
        out: set[frozenset] = set()
        for row in self.rows:
            for a, b in itertools.pairwise(row):
                out.add(frozenset((a, b)))
        spans = {z: self.span(z) for z in self.zones}
        for a, b in itertools.combinations(self.zones, 2):
            (a0, a1), (b0, b1) = spans[a], spans[b]
            if a1 + 1 == b0 or b1 + 1 == a0:
                out.add(frozenset((a, b)))
        return out

    def admits(self, required) -> bool:
        poss = self.possible_contacts()
        return all(frozenset(e) in poss for e in required)


def from_bands(bands) -> CellLayout:
    return CellLayout(tuple(tuple(b) for b in bands))


# ------------------------------------------------------------------------------------- moves

def extend(layout: CellLayout, zone_id: str, into_row: int, position: int) -> CellLayout | None:
    """`zone_id` also occupies `into_row` (the row just above or below its span), inserted at
    `position` in that row's sequence. None when the result breaks a structural fact."""
    r0, r1 = layout.span(zone_id)
    if into_row not in (r0 - 1, r1 + 1) or not (0 <= into_row < layout.n_rows):
        return None
    row = list(layout.rows[into_row])
    if zone_id in row or not (0 <= position <= len(row)):
        return None
    row.insert(position, zone_id)
    rows = list(layout.rows); rows[into_row] = tuple(row)
    out = CellLayout(tuple(rows))
    return out if not out.problems() else None


def split(layout: CellLayout, r: int, top: str, bottom: str) -> CellLayout | None:
    """Row `r` becomes two sub-rows: `top` keeps the upper one, `bottom` the lower one, in the one
    column the two shared (they must be sequence-neighbours in row r and in no other row); every
    other zone of row r spans both. The stack of `stacks.py`, as a cell layout."""
    row = layout.rows[r]
    if top not in row or bottom not in row or abs(row.index(top) - row.index(bottom)) != 1:
        return None
    if layout.span(top) != (r, r) or layout.span(bottom) != (r, r):
        return None
    i = min(row.index(top), row.index(bottom))
    upper = row[:i] + (top,) + row[i + 2:]
    lower = row[:i] + (bottom,) + row[i + 2:]
    rows = list(layout.rows); rows[r:r + 1] = [upper, lower]
    out = CellLayout(tuple(rows))
    return out if not out.problems() else None


def moves(layout: CellLayout, zones: dict, required, *, max_out: int = 60) -> list[CellLayout]:
    """Every single move from `layout` that keeps the required contacts possible: a circulation
    or public zone extended one row up or down at every position, and every stack of two
    sequence-neighbouring stackable zones. Deduplicated; `layout` itself is not included."""
    req = [tuple(e) for e in required]
    out: list[CellLayout] = []
    seen = {layout.rows}

    def keep(cand):
        if cand is not None and cand.rows not in seen and cand.admits(req):
            seen.add(cand.rows); out.append(cand)

    for z in layout.zones:
        role = getattr(zones.get(z), "role", None)
        if role not in CIRC and role not in PUBLIC:
            continue
        r0, r1 = layout.span(z)
        for into in (r0 - 1, r1 + 1):
            if not (0 <= into < layout.n_rows):
                continue
            for pos in range(len(layout.rows[into]) + 1):
                keep(extend(layout, z, into, pos))
                if len(out) >= max_out:
                    return out
    for r, row in enumerate(layout.rows):
        for a, b in itertools.pairwise(row):
            if getattr(zones.get(a), "role", None) in STACKABLE and getattr(zones.get(b), "role", None) in STACKABLE:
                keep(split(layout, r, a, b)); keep(split(layout, r, b, a))
                if len(out) >= max_out:
                    return out
    return out


# ------------------------------------------------------------------- generators by duplication

def duplicated_layouts(zones: dict, edges, zone_id: str, *, max_partitions: int = 24,
                       max_candidates: int = 60, embed=None) -> list[CellLayout]:
    """Layouts in which `zone_id` spans TWO rows, found with the band embedding itself: the zone
    is split into a top copy and a bottom copy joined by an edge, its contacts partitioned between
    the copies, `embed_band` run on that programme, and every candidate that places the copies in
    consecutive rows becomes a `CellLayout` with the one zone spanning both. Partitions are
    enumerated from the most plausible (the circulation and public neighbours above, the private
    ones below) and bounded; each resulting layout is checked for the structural facts."""
    from dataclasses import replace

    from app.vertical_slice.band_embedding import BandEmbedding
    from app.vertical_slice.band_embedding import embed_band as _embed
    embed = embed or _embed
    edges = [tuple(e) for e in edges]
    nbrs = sorted({b if a == zone_id else a for a, b in edges if zone_id in (a, b)})
    if not nbrs:
        return []
    others = [e for e in edges if zone_id not in e]
    top_id, bot_id = zone_id + "#top", zone_id + "#bot"
    zi = zones[zone_id]
    half = replace(zi, zone_id=top_id, target_area_m2=zi.target_area_m2 / 2, min_area_m2=zi.min_area_m2 / 2,
                   max_area_m2=zi.max_area_m2 / 2, max_aspect_ratio=max(zi.max_aspect_ratio, 4.0))

    def plausibility(n):
        role = getattr(zones[n], "role", None)
        return 0 if role in CIRC or role in PUBLIC else 1

    ranked = sorted(nbrs, key=plausibility)
    partitions = []
    for mask in itertools.product((0, 1), repeat=len(ranked)):
        top = [n for n, m in zip(ranked, mask) if m == 0]
        bot = [n for n, m in zip(ranked, mask) if m == 1]
        if not top or not bot:
            continue
        # most plausible first: public/circulation on one side, private on the other
        score = sum(plausibility(n) == 0 for n in bot) + sum(plausibility(n) == 1 for n in top)
        partitions.append((score, mask, top, bot))
    partitions.sort(key=lambda t: (t[0], t[1]))
    out, seen = [], set()
    for _, _, top, bot in partitions[:max_partitions]:
        z2 = {z: v for z, v in zones.items() if z != zone_id}
        z2[top_id] = half; z2[bot_id] = replace(half, zone_id=bot_id)
        e2 = others + [(top_id, bot_id)] + [(top_id, n) for n in top] + [(bot_id, n) for n in bot]
        emb = embed(z2, e2, max_candidates=max_candidates)
        if not isinstance(emb, BandEmbedding):
            continue
        for cand in emb.candidates:
            rows = [list(b) for b in cand.bands]
            rt = next((r for r, row in enumerate(rows) if top_id in row), None)
            rb = next((r for r, row in enumerate(rows) if bot_id in row), None)
            if rt is None or rb is None or rb != rt + 1:
                continue
            rows[rt][rows[rt].index(top_id)] = zone_id
            rows[rb][rows[rb].index(bot_id)] = zone_id
            lay = CellLayout(tuple(tuple(r) for r in rows))
            if lay.rows in seen or lay.problems() or not lay.admits(edges):
                continue
            seen.add(lay.rows); out.append(lay)
            if len(out) >= max_candidates:
                return out
    return out
