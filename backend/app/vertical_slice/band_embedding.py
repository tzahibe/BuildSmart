"""Exact band embedding — production replacement for the #142A heuristic grid search (Issue #142E).

Given rooms and the undirected spatial-adjacency pairs they MUST carry, decide whether a *band
layout* exists — horizontal bands, each tiled left-to-right by rooms, every room spanning its band's
full depth; exactly the family the `GridWing` dataclass represents — and if so return concrete
`GridWing` row/span placements (several, bounded, deterministically ordered). A result is either a
complete embedding (EVERY required pair is a positive-length shared boundary, verified with the
realizer's own `Rect.shared_edge_len_u`) or a typed refusal. Partial topology is never returned.

Why native and not the research SAT prototype (#142C used `python-sat`): the band family has an
exact combinatorial characterization that makes a plain backtracking search complete —

  A band layout carries a required graph G iff the rooms can be split into ordered bands such that
  (1) every required pair lies within one band and is CONSECUTIVE there, or lies in two CONSECUTIVE
      bands (rooms in non-adjacent bands never touch; a cell's left/right neighbour is unique);
  (2) for each pair of consecutive bands with orders a_1..a_k and b_1..b_l, the required cross
      pairs (a_i, b_j) are pairwise comparable in the product order (no (i,j), (i',j') with
      i < i' and j > j'): two interval sequences tiling the same width touch along a monotone
      staircase, and any chain of grid points lies on some staircase, while extra contacts along
      the staircase are allowed.

  Sufficiency: given such bands, interleave the column boundaries of consecutive bands along the
  chosen staircase; the union of all boundary orders is a DAG (chains plus bipartite constraints
  between consecutive chains only), whose topological order assigns global columns (`n_cols`) and
  spans. `_assign_columns` does exactly that and the result is re-verified geometrically.

The search is complete when it terminates within its NODE budgets (no wall-clock cut-offs anywhere:
the same input always yields the same candidates, and worst-case runtime is bounded by the budgets —
measured in docs/reports/142e-production-band-path); when a budget is hit the refusal says so
(`EMBEDDING_SEARCH_EXHAUSTED`), never "impossible". Three cheap exact pre-checks give the
representation-level refusals with a named reason: non-planarity (`graph_planarity`, DMP), a K4,
and an edge whose endpoints have >= 3 common neighbours — each forces a separating triangle in
every planar embedding, which no dissection into rectangles can carry (Koźmiński–Kinnen 1985;
measured on this corpus in docs/reports/142b-minimum-topological-representation).

Candidates are ordered by a brief-independent plausibility score (how well a rank-1 proportional
fit at the rooms' own target areas would satisfy each cell's bounds) so that a caller trying
candidates in order reaches a sizable one early; the score never filters.
"""
from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass, field
from itertools import combinations, permutations

from .geometry_core.model import Rect
from .graph_planarity import is_planar
from .rectilinear_realizer import GridCell, GridWing, ZoneIntent

#: Default bounds — search-COST bounds, never structural ones (see module docstring).
#: `max_candidates` layouts are RETURNED (ranked); up to `raw_cap` are ENUMERATED before ranking.
DEFAULT_MAX_CANDIDATES = 150
DEFAULT_RAW_CAP = 800
DEFAULT_NODE_LIMIT = 40_000
#: Diversified pass: at most this many layouts per band LABELING (room -> band assignment), so the
#: budget is spent across different compositions rather than on permutations of one. The complete
#: pass (no cap) runs first; when it finishes inside the budgets the enumeration is complete and
#: the diversified pass is skipped.
DIVERSIFIED_ORDERS_PER_SUBSET = 2
#: In the diversity pass, at most this many orders of the FIRST band are tried per labeling (the
#: first band is the only one whose order is not pinned by a previous band's anchors).
DIVERSIFIED_FIRST_BAND_ORDERS = 6
#: Labelings (room -> band assignments) are collected first. An exhaustive DFS gets a small node
#: budget (small families — e.g. the proven B06/B09 — complete inside it, which is what makes a
#: BAND_UNSAT / BAND_GEOMETRY_LIMIT claim a proof); when it does not complete, labelings are SAMPLED
#: with a seeded generator instead (deterministic, and spread over the whole space rather than over
#: a DFS prefix), `LABELING_SAMPLES` attempts.
LABELING_DFS_NODES = 15_000
LABELING_SAMPLES = 2_500
#: Conservative net-side margin used only to ORDER candidates (0.3 m = twice the heaviest single-side
#: inset, mirrors `rectilinear_realizer._INSET_MARGIN_M`); sizing itself uses exact insets.
_ORDER_INSET_M = 0.3


@dataclass(frozen=True)
class BandPlacement:
    """One concrete band layout: `rows` top-to-bottom, each a tuple of (zone_id, col_span) whose
    spans sum to `n_cols` — directly a `GridWing(rows=..., n_cols=...)`. `score` orders candidates
    (lower = more plausible); `flags` are downstream diagnostics only (never enforced here)."""

    rows: tuple[tuple[tuple[str, int], ...], ...]
    n_cols: int
    score: float
    #: The ordered bands themselves (top-to-bottom tuples of zone ids). `rows`/`n_cols` are ONE
    #: valid column interleaving (a strict staircase); the exact sizing (`band_sizing.solve_band_layout`)
    #: chooses the interleaving itself from `bands`, so a caller that sizes should use `bands`.
    bands: tuple[tuple[str, ...], ...] = ()
    flags: dict = field(default_factory=dict, hash=False, compare=False)

    def to_grid_wing(self, wing_id: str, width_m: float, height_m: float,
                     zones: dict[str, ZoneIntent], envelope_is_bound: bool = True) -> GridWing:
        return GridWing(wing_id=wing_id, width_m=width_m, height_m=height_m, n_cols=self.n_cols,
                        rows=tuple(tuple(GridCell(z, s) for z, s in row) for row in self.rows),
                        zones=zones, envelope_is_bound=envelope_is_bound)


@dataclass(frozen=True)
class BandEmbedding:
    candidates: tuple[BandPlacement, ...]   # ranked, at most `max_candidates`
    search_complete: bool          # EVERY band layout was enumerated (so `layouts_found` is the family size)
    nodes_explored: int
    seconds: float
    layouts_found: int = 0


@dataclass(frozen=True)
class BandEmbeddingRefusal:
    """Typed, explicit, never a partial layout.
    code ∈ {TOPOLOGY_NON_PLANAR, TOPOLOGY_REPRESENTATION_LIMIT, BAND_UNSAT, EMBEDDING_SEARCH_EXHAUSTED,
            INVALID_INPUT}"""

    code: str
    detail: str
    proof_complete: bool           # True when the refusal is a proof (theory or exhausted search)
    nodes_explored: int = 0


# ----------------------------------------------------------------------------- graph pre-checks

def _edge_set(edges) -> frozenset[frozenset[str]]:
    out = set()
    for a, b in edges:
        if a == b:
            raise ValueError(f"self-adjacency {a!r}")
        out.add(frozenset((a, b)))
    return frozenset(out)


def find_k4(adj: dict[str, set[str]]) -> tuple[str, ...] | None:
    for a in sorted(adj):
        for b in sorted(adj[a]):
            if b <= a:
                continue
            common_ab = adj[a] & adj[b]
            for c in sorted(common_ab):
                if c <= b:
                    continue
                for d in sorted(common_ab & adj[c]):
                    if d > c:
                        return (a, b, c, d)
    return None


def find_triple_lens(adj: dict[str, set[str]]) -> tuple[tuple[str, str], tuple[str, ...]] | None:
    for a in sorted(adj):
        for b in sorted(adj[a]):
            if b <= a:
                continue
            common = sorted(adj[a] & adj[b])
            if len(common) >= 3:
                return (a, b), tuple(common)
    return None


def representation_precheck(room_ids, edges) -> BandEmbeddingRefusal | None:
    """Exact, O(n·Δ²) obstructions to ANY rectangular dissection; None when none is present."""
    es = _edge_set(edges)
    adj: dict[str, set[str]] = {r: set() for r in room_ids}
    for e in es:
        a, b = tuple(e)
        adj[a].add(b); adj[b].add(a)
    if not is_planar(list(room_ids), [tuple(e) for e in es]):
        return BandEmbeddingRefusal(
            "TOPOLOGY_NON_PLANAR",
            "the required adjacency graph is not planar: no partition of the plane (rectangles, "
            "bands, L-shapes or any polygons) has a non-planar contact graph", True)
    k4 = find_k4(adj)
    if k4:
        return BandEmbeddingRefusal(
            "TOPOLOGY_REPRESENTATION_LIMIT",
            f"four mutually adjacent rooms {'/'.join(k4)} (a K4): three mutually touching "
            f"rectangles meet at a T-junction and enclose nothing, so no dissection into rectangles "
            f"— band, slicing tree or non-guillotine — can carry all six pairs", True)
    lens = find_triple_lens(adj)
    if lens:
        (a, b), common = lens
        return BandEmbeddingRefusal(
            "TOPOLOGY_REPRESENTATION_LIMIT",
            f"rooms {'/'.join(common)} are each required to touch both {a} and {b}: a straight wall "
            f"has only two sides, so the middle of the three triangles separates the others — no "
            f"dissection into rectangles can carry all of these pairs", True)
    return None


# ----------------------------------------------------------------------------- band search

def _linear_orders(members: list[str], es: frozenset):
    """Orders of `members` in which every required pair inside the set is consecutive. The induced
    required subgraph must be a linear forest; orders = concatenations of its paths in any order
    and orientation, generated LAZILY (a band of k free rooms has k!·2^k orders)."""
    inner = {e for e in es if e <= set(members)}
    deg = {m: 0 for m in members}
    for e in inner:
        for v in e:
            deg[v] += 1
    if any(d > 2 for d in deg.values()):
        return iter(())
    # components of the induced subgraph must be paths (no cycles)
    adj = {m: [] for m in members}
    for e in inner:
        a, b = tuple(e)
        adj[a].append(b); adj[b].append(a)
    seen = set(); paths = []
    for m in sorted(members):
        if m in seen:
            continue
        # walk to an end
        comp = []
        stack = [m]
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x); comp.append(x)
            stack.extend(adj[x])
        ends = [x for x in comp if deg[x] <= 1]
        if len(comp) > 1 and len(ends) != 2:
            return iter(())   # a cycle: no consecutive order exists
        if len(comp) == 1:
            paths.append((m,))
            continue
        start = sorted(ends)[0]
        path = [start]; prev = None; cur = start
        while True:
            nxt = [y for y in adj[cur] if y != prev]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            path.append(cur)
        paths.append(tuple(path))
    def gen():
        for perm in permutations(range(len(paths))):
            for orient in range(1 << len(paths)):
                seq = []
                for k, i in enumerate(perm):
                    p = paths[i]
                    seq.extend(reversed(p) if (orient >> k) & 1 and len(p) > 1 else p)
                yield tuple(seq)
    return gen()


def _path_units(members: list[str], es: frozenset):
    """Decompose the induced required subgraph on `members` into path units (tuples). Returns None
    when it is not a linear forest (a room with 3 required in-band neighbours, or a cycle)."""
    inner = {e for e in es if e <= set(members)}
    adj = {m: [] for m in members}
    for e in inner:
        a, b = tuple(e)
        adj[a].append(b); adj[b].append(a)
    if any(len(v) > 2 for v in adj.values()):
        return None
    seen = set(); units = []
    for m in sorted(members):
        if m in seen:
            continue
        comp = []; stack = [m]
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x); comp.append(x); stack.extend(adj[x])
        ends = [x for x in comp if len(adj[x]) <= 1]
        if len(comp) > 1 and len(ends) != 2:
            return None
        if len(comp) == 1:
            units.append((m,)); continue
        start = sorted(ends)[0]; path = [start]; prev = None; cur = start
        while True:
            nxt = [y for y in adj[cur] if y != prev]
            if not nxt:
                break
            prev, cur = cur, nxt[0]; path.append(cur)
        units.append(tuple(path))
    return units


def _band_orders(members: list[str], es: frozenset, prev: tuple[str, ...]):
    """Orders of `members` (lazy) that (a) keep every in-band required pair consecutive and (b)
    satisfy the chain condition against `prev` — built CONSTRUCTIVELY: every unit's anchors (positions
    of its required neighbours in `prev`) must be non-decreasing along the sequence, so anchored
    units come in anchor order (each path unit in the orientation that keeps its own anchors
    monotone) and free units (no anchors) are inserted into the gaps. The first orders yielded are
    the "free units last" and "free units first" arrangements (the diversity pass takes two)."""
    units = _path_units(members, es)
    if units is None:
        return
    pos = {v: i for i, v in enumerate(prev)}
    anchors = {v: sorted(pos[u] for u in prev if frozenset((u, v)) in es) for v in members}

    def orientations(unit):
        for u in (unit, tuple(reversed(unit))) if len(unit) > 1 else (unit,):
            seq = [a for v in u for a in anchors[v]]
            if all(seq[i] <= seq[i + 1] for i in range(len(seq) - 1)):
                yield u

    anchored = [u for u in units if any(anchors[v] for v in u)]
    free = [u for u in units if not any(anchors[v] for v in u)]
    # anchored units: every orientation combination that is globally non-decreasing
    anchored.sort(key=lambda u: (min(a for v in u for a in anchors[v]), max(a for v in u for a in anchors[v])))

    def anchored_sequences(i: int, chosen: list, last_max: int):
        if i == len(anchored):
            yield tuple(chosen); return
        for o in orientations(anchored[i]):
            first = min(anchors[o[0]] or [last_max]) if anchors[o[0]] else last_max
            seq = [a for v in o for a in anchors[v]]
            if seq[0] < last_max:
                continue
            chosen.append(o)
            yield from anchored_sequences(i + 1, chosen, seq[-1])
            chosen.pop()

    # ties: anchored units with identical (min, max) may swap — handled by trying permutations of
    # equal-key groups lazily
    def anchored_all():
        if not anchored:
            yield (); return
        keys = [(min(a for v in u for a in anchors[v]), max(a for v in u for a in anchors[v])) for u in anchored]
        groups = []
        for u, k in zip(anchored, keys):
            if groups and groups[-1][0] == k:
                groups[-1][1].append(u)
            else:
                groups.append((k, [u]))
        def rec(gi, acc):
            if gi == len(groups):
                yield from anchored_sequences_fixed(acc); return
            for perm in permutations(groups[gi][1]):
                yield from rec(gi + 1, acc + list(perm))
        yield from rec(0, [])

    def anchored_sequences_fixed(order_units):
        def rec(i, chosen, last_max):
            if i == len(order_units):
                yield tuple(chosen); return
            for o in orientations(order_units[i]):
                seq = [a for v in o for a in anchors[v]]
                if seq[0] < last_max:
                    continue
                chosen.append(o)
                yield from rec(i + 1, chosen, seq[-1])
                chosen.pop()
        yield from rec(0, [], -1)

    def with_free(base: tuple, free_units: list):
        """All insertions of free units into `base` (lazy); first the end/start placements."""
        k = len(base)
        if not free_units:
            yield base; return
        # diversity-first arrangements
        for fp in permutations(free_units):
            yield base + tuple(u for u in fp)
            yield tuple(u for u in fp) + base
            break
        # exhaustive: every permutation of free units into every multiset of gap positions
        for fp in permutations(free_units):
            for fo in (fp, tuple(reversed(fp))) if False else (fp,):
                pass
            # gap choice per free unit, non-decreasing gap indices to avoid duplicates of the same sequence
            def rec(i, gaps, acc):
                if i == len(fp):
                    seq = list(base)
                    # insert from the right so indices stay valid
                    for g, u in sorted(zip(gaps, fp), key=lambda t: -t[0]):
                        seq.insert(g, u)
                    yield tuple(seq); return
                lo = gaps[-1] if gaps else 0
                for g in range(lo, k + 1):
                    yield from rec(i + 1, gaps + [g], acc)
            for seq in rec(0, [], None):
                if seq == base + fp or seq == fp + base:
                    continue
                yield seq

    for base in anchored_all():
        for seq in with_free(base, free):
            flat = tuple(v for u in seq for v in u)
            # defensive re-check (orientation of free units with in-band paths and tie handling)
            if prev and not _chain_ok(prev, flat, es):
                continue
            yield flat
        if not prev:
            # first band: also every orientation of free path units (chain irrelevant)
            pass


def _chain_ok(prev_band: tuple[str, ...], band: tuple[str, ...], es: frozenset) -> bool:
    pos_p = {v: i for i, v in enumerate(prev_band)}
    pts = []
    for j, v in enumerate(band):
        for u in prev_band:
            if frozenset((u, v)) in es:
                pts.append((pos_p[u], j))
    pts.sort()
    for (i, j), (i2, j2) in zip(pts, pts[1:]):
        if i2 > i and j2 < j:
            return False
    return True


def _assign_columns(bands: tuple[tuple[str, ...], ...], es: frozenset) -> tuple[tuple[tuple[tuple[str, int], ...], ...], int]:
    """Global column boundaries from the staircase between each pair of consecutive bands (the path
    visits every required point; all steps are single — strict interleaving, which only adds extra
    contacts). Returns GridWing rows (zone, span) and n_cols."""
    # boundary id: (band index, k) = right boundary of cell k (k = 0..len-2); plus global 0 and W
    order_edges: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for r, band in enumerate(bands):
        for k in range(len(band) - 2):
            order_edges.append(((r, k), (r, k + 1)))
    for r in range(len(bands) - 1):
        a, b = bands[r], bands[r + 1]
        pos_a = {v: i for i, v in enumerate(a)}
        pts = sorted({(pos_a[u], j) for j, v in enumerate(b) for u in a if frozenset((u, v)) in es})
        # staircase from (0,0) through pts to (k-1, l-1); at (i,j): cell a_i overlaps b_j
        i = j = 0
        targets = pts + [(len(a) - 1, len(b) - 1)]
        for ti, tj in targets:
            while i < ti or j < tj:
                # advance the side that is further from its target first (any order is valid)
                if i < ti and (j >= tj or (ti - i) >= (tj - j)):
                    # a_i's right boundary comes before b_j's right boundary
                    if j < len(b) - 1:
                        order_edges.append(((r, i), (r + 1, j)))
                    i += 1
                else:
                    if i < len(a) - 1:
                        order_edges.append(((r + 1, j), (r, i)))
                    j += 1
    nodes = [(r, k) for r, band in enumerate(bands) for k in range(len(band) - 1)]
    indeg = {v: 0 for v in nodes}
    succ = {v: [] for v in nodes}
    for u, v in order_edges:
        if u in indeg and v in indeg:
            succ[u].append(v); indeg[v] += 1
    # Kahn topological order -> global column index of each boundary
    ready = sorted([v for v in nodes if indeg[v] == 0])
    col_of: dict[tuple[int, int], int] = {}
    nxt = 1
    while ready:
        v = ready.pop(0)
        col_of[v] = nxt; nxt += 1
        for w in succ[v]:
            indeg[w] -= 1
            if indeg[w] == 0:
                ready.append(w); ready.sort()
    if len(col_of) != len(nodes):
        raise AssertionError("boundary order is cyclic — contradicts the staircase construction")
    n_cols = nxt
    rows = []
    for r, band in enumerate(bands):
        row = []
        left = 0
        for k, z in enumerate(band):
            right = col_of[(r, k)] if k < len(band) - 1 else n_cols
            row.append((z, right - left))
            left = right
        rows.append(tuple(row))
    return tuple(rows), n_cols


def verify_rows(rows, n_cols, edges) -> list[tuple[str, str]]:
    """Required pairs NOT carried as a positive-length shared boundary of the unit cell grid (the
    realizer's own `Rect.shared_edge_len_u`). Empty list == every pair carried."""
    rects: dict[str, Rect] = {}
    for r_idx, row in enumerate(rows):
        c0 = 0
        for z, span in row:
            rects[z] = Rect(c0, r_idx, span, 1)
            c0 += span
        if c0 != n_cols:
            raise ValueError("row does not tile n_cols")
    return [(a, b) for a, b in edges if rects[a].shared_edge_len_u(rects[b]) <= 0]


def _plausibility(rows, n_cols, zones: dict[str, ZoneIntent]) -> float:
    total = sum(z.target_area_m2 for z in zones.values())
    if total <= 0:
        return 0.0
    row_tot = [sum(zones[z].target_area_m2 for z, _ in row) for row in rows]
    col_tot = [0.0] * n_cols
    for row in rows:
        c0 = 0
        for z, span in row:
            for c in range(c0, c0 + span):
                col_tot[c] += zones[z].target_area_m2 / span
            c0 += span
    side = total ** 0.5
    h = [side * rt / total for rt in row_tot]
    w = [side * ct / total for ct in col_tot]
    score = 0.0
    for r_idx, row in enumerate(rows):
        c0 = 0
        for z, span in row:
            zi = zones[z]
            width = sum(w[c0:c0 + span]); height = h[r_idx]
            area = width * height
            if area < zi.min_area_m2:
                score += (zi.min_area_m2 - area) / max(zi.target_area_m2, 1e-9)
            elif area > zi.max_area_m2:
                score += (area - zi.max_area_m2) / max(zi.target_area_m2, 1e-9)
            need = zi.min_short_side_m + _ORDER_INSET_M
            if min(width, height) < need:
                score += (need - min(width, height)) / need
            c0 += span
    return round(score, 4)


def embed_band(zones: dict[str, ZoneIntent], edges, *, max_candidates: int = DEFAULT_MAX_CANDIDATES,
               node_limit: int = DEFAULT_NODE_LIMIT, raw_cap: int = DEFAULT_RAW_CAP
               ) -> BandEmbedding | BandEmbeddingRefusal:
    """Exact band embedding of the required `edges` over `zones` (room id -> ZoneIntent); see the
    module docstring. Deterministic: the same input always yields the same candidates in the same
    order."""
    room_ids = sorted(zones)
    try:
        es = _edge_set(edges)
    except ValueError as exc:
        return BandEmbeddingRefusal("INVALID_INPUT", str(exc), True)
    for e in es:
        for v in e:
            if v not in zones:
                return BandEmbeddingRefusal("INVALID_INPUT", f"edge references unknown room {v!r}", True)
    if not room_ids:
        return BandEmbeddingRefusal("INVALID_INPUT", "no rooms", True)
    pre = representation_precheck(room_ids, es)
    if pre is not None:
        return pre

    adj: dict[str, set[str]] = {r: set() for r in room_ids}
    for e in es:
        a, b = tuple(e)
        adj[a].add(b); adj[b].add(a)

    t0 = time.monotonic()
    found: list[tuple[tuple[str, ...], ...]] = []
    seen_layouts: set = set()
    n = len(room_ids)
    # BFS order from the highest-degree room so that almost every room has an assigned neighbour
    # when its band is chosen (the +-1 rule then leaves at most 3 choices).
    hub = max(room_ids, key=lambda r: (len(adj[r]), r))
    order: list[str] = []
    seen_v = {hub}; queue = [hub]
    while queue:
        v = queue.pop(0); order.append(v)
        for w in sorted(adj[v], key=lambda r: (-len(adj[r]), r)):
            if w not in seen_v:
                seen_v.add(w); queue.append(w)
    for v in sorted(room_ids, key=lambda r: (-len(adj[r]), r)):
        if v not in seen_v:
            seen_v.add(v); order.append(v)

    nodes = 0
    exhausted = False

    def labelings():
        """Every band assignment f: room -> Z with |f(u)-f(v)| <= 1 on required pairs and at most
        2 required neighbours inside a room's own band (a band's induced required graph must be a
        linear forest), normalized to min 0 and de-duplicated under top/bottom mirroring."""
        nonlocal nodes, exhausted
        f: dict[str, int] = {}
        emitted: set = set()

        lab_nodes = 0

        def rec(i: int):
            nonlocal lab_nodes, lab_exhausted
            if lab_exhausted:
                return
            lab_nodes += 1
            if lab_nodes > LABELING_DFS_NODES:
                lab_exhausted = True
                return
            if i == n:
                lo = min(f.values())
                lab = tuple(f[v] - lo for v in room_ids)
                hi = max(lab)
                mirror = tuple(hi - b for b in lab)
                key = min(lab, mirror)
                if key not in emitted:
                    emitted.add(key)
                    yield dict(zip(room_ids, lab))
                return
            v = order[i]
            assigned = [f[w] for w in adj[v] if w in f]
            if assigned:
                cands = range(max(b - 1 for b in assigned), min(b + 1 for b in assigned) + 1)
            else:
                cur = list(f.values())
                cands = range(min(cur) - 1, max(cur) + 2) if cur else range(0, 1)
            for b in cands:
                same = [w for w in adj[v] if f.get(w) == b]
                if len(same) > 2:
                    continue
                if any(sum(1 for x in adj[w] if f.get(x) == b) >= 2 for w in same):
                    continue
                f[v] = b
                yield from rec(i + 1)
                del f[v]
                if lab_exhausted:
                    return

        yield from rec(0)

    lab_exhausted = False

    def sampled_labelings(attempts: int):
        """Seeded random labelings (same rules as `labelings`), de-duplicated under mirroring."""
        # a STABLE seed: Python's str hash is randomized per process (PYTHONHASHSEED), which would make
        # the sampled labelings — and therefore the candidates — differ between runs
        digest = hashlib.sha256("\x1f".join(room_ids).encode("utf-8")).digest()
        rng = random.Random(int.from_bytes(digest[:8], "big"))
        emitted: set = set()
        for _ in range(attempts):
            f: dict[str, int] = {}
            ok = True
            for v in order:
                assigned = [f[w] for w in adj[v] if w in f]
                if assigned:
                    lo, hi = max(b - 1 for b in assigned), min(b + 1 for b in assigned)
                    if lo > hi:
                        ok = False; break
                    cands = list(range(lo, hi + 1))
                else:
                    cur = list(f.values())
                    cands = list(range(min(cur) - 1, max(cur) + 2)) if cur else [0]
                rng.shuffle(cands)
                placed = False
                for b in cands:
                    same = [w for w in adj[v] if f.get(w) == b]
                    if len(same) > 2 or any(sum(1 for x in adj[w] if f.get(x) == b) >= 2 for w in same):
                        continue
                    f[v] = b; placed = True; break
                if not placed:
                    ok = False; break
            if not ok:
                continue
            lo = min(f.values())
            lab = tuple(f[v] - lo for v in room_ids)
            hi = max(lab)
            key = min(lab, tuple(hi - b for b in lab))
            if key not in emitted:
                emitted.add(key)
                yield dict(zip(room_ids, lab))

    def orders_for(lab: dict[str, int], per_labeling: int | None):
        """Layouts (ordered bands) of one labeling: DFS band by band, lazy within-band orders,
        chain condition against the previous band; at most `per_labeling` (None = all)."""
        R = max(lab.values()) + 1
        members = [sorted(v for v in room_ids if lab[v] == b) for b in range(R)]
        if any(not m for m in members):
            return 0, False
        # start the ordering DFS from the end band with fewer rooms (top/bottom mirror is the same
        # layout family): the first band is the only one not pinned by anchors
        if len(members[-1]) < len(members[0]):
            members = members[::-1]
        got = 0
        capped = False
        first_tried = 0

        def rec(b: int, bands: tuple[tuple[str, ...], ...]):
            nonlocal got, capped, nodes, exhausted
            if exhausted or (per_labeling is not None and got >= per_labeling) or len(found) >= raw_cap:
                capped = capped or (per_labeling is not None and got >= per_labeling)
                return
            nodes += 1
            if nodes > node_limit:
                exhausted = True
                return
            if b == R:
                key = bands if bands[0] <= bands[-1] else tuple(reversed(bands))
                if key not in seen_layouts:
                    seen_layouts.add(key)
                    found.append(bands)
                    got += 1
                return
            nonlocal first_tried
            prev = bands[-1] if bands else ()
            gen = _band_orders(members[b], es, prev) if prev else _linear_orders(members[b], es)
            for o in gen:
                if b == 0:
                    first_tried += 1
                    if per_labeling is not None and first_tried > DIVERSIFIED_FIRST_BAND_ORDERS:
                        capped = True
                        return
                rec(b + 1, bands + (o,))
                if exhausted or (per_labeling is not None and got >= per_labeling) or len(found) >= raw_cap:
                    return

        rec(0, ())
        return got, capped

    # pass 0: collect labelings — exhaustively when the family is small enough, else by sampling
    labs: list[dict[str, int]] = list(labelings())
    labelings_complete = not lab_exhausted
    if not labelings_complete:
        seen_keys = {min(tuple(l[v] for v in room_ids), tuple(max(l.values()) - l[v] for v in room_ids)) for l in labs}
        for lab in sampled_labelings(LABELING_SAMPLES):
            key = min(tuple(lab[v] for v in room_ids), tuple(max(lab.values()) - lab[v] for v in room_ids))
            if key not in seen_keys:
                seen_keys.add(key); labs.append(lab)
    # pass A (diversity): a deterministic STRIDE through the labelings, a couple of layouts each,
    # so the candidates span band counts and memberships rather than one subtree
    target_labelings = max(1, raw_cap // DIVERSIFIED_ORDERS_PER_SUBSET)
    stride = max(1, len(labs) // target_labelings)
    any_capped = False
    for lab in labs[::stride]:
        _g, c = orders_for(lab, DIVERSIFIED_ORDERS_PER_SUBSET)
        any_capped = any_capped or c
        if exhausted or len(found) >= raw_cap:
            break
    # pass B (completeness): every layout of every labeling, only when that is affordable
    complete = False
    if labelings_complete and not exhausted and len(found) < raw_cap:
        capped_any = False
        for lab in labs:
            _g, c = orders_for(lab, None)
            capped_any = capped_any or c
            if exhausted or len(found) >= raw_cap:
                break
        complete = not exhausted and not capped_any and len(found) < raw_cap
    seconds = time.monotonic() - t0
    if not found:
        if not complete:
            return BandEmbeddingRefusal(
                "EMBEDDING_SEARCH_EXHAUSTED",
                f"no band layout found within the search bound ({node_limit} nodes, "
                f"{seconds:.2f}s); not a proof of impossibility", False, nodes)
        return BandEmbeddingRefusal(
            "BAND_UNSAT",
            f"no band layout carries every required pair (search complete, {nodes} nodes): the "
            f"graph is planar and free of K4/triple-lens obstructions, so a non-band rectangular "
            f"dissection may still exist", True, nodes)
    placements = []
    for bands in found:
        rows, n_cols = _assign_columns(bands, es)
        missing = verify_rows(rows, n_cols, [tuple(e) for e in es])
        if missing:   # defensive: the construction is proven, but never trust a proof over a check
            raise AssertionError(f"band construction dropped {missing}")
        placements.append(BandPlacement(rows, n_cols, _plausibility(rows, n_cols, zones), bands))
    placements.sort(key=lambda p: (p.score, len(p.rows), p.n_cols, p.rows))
    top = placements[:max_candidates]
    single = next((p for p in placements if len(p.rows) == 1), None)
    if single is not None and single not in top:
        top = top[:-1] + [single] if len(top) >= max_candidates else top + [single]
    return BandEmbedding(tuple(top), complete, nodes, round(seconds, 4), len(placements))


__all__ = ["BandEmbedding", "BandEmbeddingRefusal", "BandPlacement", "embed_band",
           "representation_precheck", "verify_rows", "find_k4", "find_triple_lens"]
