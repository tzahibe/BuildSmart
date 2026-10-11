"""Disposable analysis library (not production code): exact SAT decision procedures for
"can this required adjacency graph be carried by representation family X", plus graph diagnostics.

Families (nested):
  L0  GridWing-as-searched : the exact slot structures graph_embedding.py enumerates
                             (balanced row lengths, spans 1,1,...,remainder), exact assignment.
  L1  Band layout          : the full GridWing dataclass — rooms partitioned into horizontal
                             bands, every room spans its band's full height (== depth-2 slicing
                             H-then-V with globally aligned columns; equals ANY band layout).
                             Tested in both orientations (rows or columns as bands).
  L2  Slicing (guillotine) : any recursive guillotine dissection (the Geometry Core's family).
  L3  Rectangular          : any rectangular dissection (non-guillotine allowed) == subgraph of
                             a rectangular dual.
  L4  k L-shaped rooms     : rectangular dissection where k chosen rooms may be an L (union of 2
                             rectangles sharing an aligned edge); the rest stay rectangles.

All SAT models tile an N x N unit grid (N = #pieces suffices: a dissection with p rectangles has at
most p+1 distinct coordinates per axis), require every required edge to be a positive-length
shared boundary, and ALLOW extra contacts (touching without a door is not a violation).
"""
from __future__ import annotations

import itertools
import json
import time
from dataclasses import dataclass, field

import networkx as nx
from pysat.solvers import Cadical153


# ----------------------------------------------------------------------------- graph diagnostics

def diagnostics(nodes: list[str], edges: list[tuple[str, str]]) -> dict:
    G = nx.Graph()
    G.add_nodes_from(nodes)
    G.add_edges_from(edges)
    n, m = G.number_of_nodes(), G.number_of_edges()
    deg = dict(G.degree())
    planar, _ = nx.check_planarity(G)
    k4s = [tuple(sorted(c)) for c in nx.enumerate_all_cliques(G) if len(c) == 4]
    tri = [tuple(sorted(c)) for c in nx.enumerate_all_cliques(G) if len(c) == 3]
    # edge whose endpoints have >= 3 common neighbours ("triple lens"): forces a separating
    # triangle in every planar embedding -> no rectangular dual even with extra adjacencies.
    lens3 = []
    for a, b in G.edges():
        common = sorted(set(G[a]) & set(G[b]))
        if len(common) >= 3:
            lens3.append(((a, b), common))
    cyc_rank = m - n + nx.number_connected_components(G)
    return {
        "n": n, "m": m, "density": round(2 * m / (n * (n - 1)), 3) if n > 1 else 0.0,
        "degree": deg, "max_degree": max(deg.values()) if deg else 0,
        "degree_hist": dict(sorted(((d, list(deg.values()).count(d)) for d in set(deg.values())))),
        "planar": planar, "triangles": tri, "k4": k4s, "lens3": lens3,
        "cycle_rank": cyc_rank, "connected": nx.is_connected(G) if n else True,
        "rect_dual_edge_bound_3n_minus_7": 3 * n - 7, "exceeds_3n7": m > 3 * n - 7,
        "articulation_points": sorted(nx.articulation_points(G)) if n else [],
    }


# ----------------------------------------------------------------------------- L0: slot structures

def row_lengths_for(n: int, n_rows: int) -> tuple[int, ...]:
    base, rem = divmod(n, n_rows)
    return tuple([base + 1] * rem + [base] * (n_rows - rem))


def slot_positions(row_lengths, n_cols):
    slots = []
    for r_idx, row_len in enumerate(row_lengths):
        for i in range(row_len):
            span = 1 if i < row_len - 1 else n_cols - (row_len - 1)
            slots.append((r_idx, i, span))
    return slots


def slot_adjacency(slots):
    adj = set()
    by_row: dict[int, list[int]] = {}
    for idx, (r, _c0, _span) in enumerate(slots):
        by_row.setdefault(r, []).append(idx)
    for idxs in by_row.values():
        for a, b in zip(idxs, idxs[1:]):
            adj.add(frozenset((a, b)))
    rows = sorted(by_row)
    for ra, rb in zip(rows, rows[1:]):
        for ia in by_row[ra]:
            _, c0a, spana = slots[ia]
            for ib in by_row[rb]:
                _, c0b, spanb = slots[ib]
                if c0a < c0b + spanb and c0b < c0a + spana:
                    adj.add(frozenset((ia, ib)))
    return frozenset(adj)


def exact_slot_embedding(nodes, edges, slot_adj, n_slots):
    """Exact (SAT) room->slot assignment carrying every edge, or None. Subgraph embedding."""
    idx = {v: i for i, v in enumerate(nodes)}
    n = len(nodes)
    var = lambda v, s: 1 + idx[v] * n_slots + s  # noqa: E731
    s = Cadical153()
    for v in nodes:
        s.add_clause([var(v, t) for t in range(n_slots)])
        for t1, t2 in itertools.combinations(range(n_slots), 2):
            s.add_clause([-var(v, t1), -var(v, t2)])
    for t in range(n_slots):
        for v1, v2 in itertools.combinations(nodes, 2):
            s.add_clause([-var(v1, t), -var(v2, t)])
    for a, b in edges:
        for t1 in range(n_slots):
            for t2 in range(n_slots):
                if t1 == t2 or frozenset((t1, t2)) in slot_adj:
                    continue
                s.add_clause([-var(a, t1), -var(b, t2)])
    ok = s.solve()
    model = None
    if ok:
        pos = set(l for l in s.get_model() if l > 0)
        model = {}
        for v in nodes:
            for t in range(n_slots):
                if var(v, t) in pos:
                    model[t] = v
    s.delete()
    return model


def l0_exact(nodes, edges, max_rows=None):
    """For every slot structure the production search enumerates (and beyond 6 rows if asked),
    the EXACT answer: embeddable or not."""
    n = len(nodes)
    out = {}
    for n_rows in range(1, (max_rows or n) + 1):
        rl = row_lengths_for(n, n_rows)
        n_cols = max(rl)
        slots = slot_positions(rl, n_cols)
        sadj = slot_adjacency(slots)
        model = exact_slot_embedding(nodes, edges, sadj, len(slots))
        out[n_rows] = {"row_lengths": rl, "n_cols": n_cols, "embeddable": model is not None,
                       "assignment": model}
    return out


# ----------------------------------------------------------------------------- grid-tiling SAT

@dataclass
class Piece:
    pid: str        # piece id (room id, or room id + "#2" for an L's second rectangle)
    room: str       # owning room


class TilingModel:
    """Rooms (or room pieces) as rectangles tiling an N x N unit grid."""

    def __init__(self, pieces: list[Piece], W: int, H: int):
        self.pieces = pieces
        self.W, self.H = W, H
        self.N = max(W, H)
        self.nv = 0
        self.clauses: list[list[int]] = []
        P = len(pieces)
        rx, ry = range(W), range(H)
        # order-encoding: Lx[p][i] = x0_p <= i ; Rx[p][i] = x1_p >= i+1  (covers column i iff both)
        self.Lx = [[self.new() for _ in rx] for _ in range(P)]
        self.Rx = [[self.new() for _ in rx] for _ in range(P)]
        self.Ly = [[self.new() for _ in ry] for _ in range(P)]
        self.Ry = [[self.new() for _ in ry] for _ in range(P)]
        self.colcov = [[self.new() for _ in rx] for _ in range(P)]
        self.rowcov = [[self.new() for _ in ry] for _ in range(P)]
        self.cov = [[[self.new() for _ in ry] for _ in rx] for _ in range(P)]
        for p in range(P):
            for i in range(W - 1):
                self.add([-self.Lx[p][i], self.Lx[p][i + 1]])
                self.add([-self.Rx[p][i + 1], self.Rx[p][i]])
            for j in range(H - 1):
                self.add([-self.Ly[p][j], self.Ly[p][j + 1]])
                self.add([-self.Ry[p][j + 1], self.Ry[p][j]])
            for i in rx:
                self.iff_and(self.colcov[p][i], [self.Lx[p][i], self.Rx[p][i]])
            for j in ry:
                self.iff_and(self.rowcov[p][j], [self.Ly[p][j], self.Ry[p][j]])
            for i in rx:
                for j in ry:
                    self.iff_and(self.cov[p][i][j], [self.colcov[p][i], self.rowcov[p][j]])
            # non-empty
            self.add([self.colcov[p][i] for i in rx])
            self.add([self.rowcov[p][j] for j in ry])
        # every cell exactly one piece
        for i in rx:
            for j in ry:
                self.add([self.cov[p][i][j] for p in range(P)])
                for p1, p2 in itertools.combinations(range(P), 2):
                    self.add([-self.cov[p1][i][j], -self.cov[p2][i][j]])
        self.pid_index = {pc.pid: k for k, pc in enumerate(pieces)}
        self.room_pieces: dict[str, list[int]] = {}
        for k, pc in enumerate(pieces):
            self.room_pieces.setdefault(pc.room, []).append(k)

    def new(self) -> int:
        self.nv += 1
        return self.nv

    def add(self, clause):
        self.clauses.append(list(clause))

    def iff_and(self, y, xs):
        for x in xs:
            self.add([-y, x])
        self.add([y] + [-x for x in xs])

    def contact_atoms(self, p: int, q: int) -> list[int]:
        """Aux literals each implying 'piece p and piece q share a unit cell boundary'."""
        W, H = self.W, self.H
        atoms = []
        for i in range(W):
            for j in range(H):
                if i + 1 < W:
                    for a, b in ((p, q), (q, p)):
                        t = self.new()
                        self.add([-t, self.cov[a][i][j]])
                        self.add([-t, self.cov[b][i + 1][j]])
                        atoms.append(t)
                if j + 1 < H:
                    for a, b in ((p, q), (q, p)):
                        t = self.new()
                        self.add([-t, self.cov[a][i][j]])
                        self.add([-t, self.cov[b][i][j + 1]])
                        atoms.append(t)
        return atoms

    def require_room_contact(self, u: str, v: str):
        atoms = []
        for p in self.room_pieces[u]:
            for q in self.room_pieces[v]:
                atoms += self.contact_atoms(p, q)
        self.add(atoms)

    def require_band_layout(self, axis: str = "y"):
        """Every piece's extent along `axis` is exactly one band (no band cut strictly inside a
        piece; every piece boundary is a band cut)."""
        N = self.H if axis == "y" else self.W
        cov = self.rowcov if axis == "y" else self.colcov
        bcut = [None] + [self.new() for _ in range(1, N)]
        for p in range(len(self.pieces)):
            for j in range(1, N):
                # starts at j  -> cut ; ends at j -> cut ; spans across j -> no cut
                self.add([-cov[p][j], cov[p][j - 1], bcut[j]])
                self.add([-cov[p][j - 1], cov[p][j], bcut[j]])
                self.add([-cov[p][j - 1], -cov[p][j], -bcut[j]])

    def require_guillotine(self):
        """The whole grid admits a recursive guillotine decomposition w.r.t. the piece tiling."""
        W, H = self.W, self.H
        P = len(self.pieces)
        # cross_x[i][j]: the same piece covers (i-1,j) and (i,j)  (a vertical cut at i is blocked in row j)
        cross_x = {}
        cross_y = {}
        for i in range(1, W):
            for j in range(H):
                c = self.new()
                sx = []
                for p in range(P):
                    t = self.new()
                    self.iff_and(t, [self.cov[p][i - 1][j], self.cov[p][i][j]])
                    sx.append(t)
                # c <-> OR sx
                for t in sx:
                    self.add([-t, c])
                self.add([-c] + sx)
                cross_x[(i, j)] = c
        for j in range(1, H):
            for i in range(W):
                c = self.new()
                sy = []
                for p in range(P):
                    t = self.new()
                    self.iff_and(t, [self.cov[p][i][j - 1], self.cov[p][i][j]])
                    sy.append(t)
                for t in sy:
                    self.add([-t, c])
                self.add([-c] + sy)
                cross_y[(i, j)] = c
        g: dict[tuple, int] = {}
        for i0 in range(W):
            for i1 in range(i0 + 1, W + 1):
                for j0 in range(H):
                    for j1 in range(j0 + 1, H + 1):
                        g[(i0, i1, j0, j1)] = self.new()
        for (i0, i1, j0, j1), gv in g.items():
            options = []
            # single piece covers the region (corners suffice by rectangularity)
            for p in range(P):
                t = self.new()
                self.add([-t, self.Lx[p][i0]])
                self.add([-t, self.Rx[p][i1 - 1]])
                self.add([-t, self.Ly[p][j0]])
                self.add([-t, self.Ry[p][j1 - 1]])
                options.append(t)
            for i in range(i0 + 1, i1):
                t = self.new()
                for j in range(j0, j1):
                    self.add([-t, -cross_x[(i, j)]])
                self.add([-t, g[(i0, i, j0, j1)]])
                self.add([-t, g[(i, i1, j0, j1)]])
                options.append(t)
            for j in range(j0 + 1, j1):
                t = self.new()
                for i in range(i0, i1):
                    self.add([-t, -cross_y[(i, j)]])
                self.add([-t, g[(i0, i1, j0, j)]])
                self.add([-t, g[(i0, i1, j, j1)]])
                options.append(t)
            self.add([-gv] + options)
        self.add([g[(0, W, 0, H)]])

    def require_L_union(self, p: int, q: int):
        """Pieces p and q (same room) touch and share one aligned extreme -> union is an L
        (or, degenerately, a rectangle)."""
        self.add(self.contact_atoms(p, q))
        eqs = []
        for arr in (self.Lx, self.Rx, self.Ly, self.Ry):
            e = self.new()
            for i in range(len(arr[p])):
                # e -> (arr[p][i] <-> arr[q][i])
                self.add([-e, -arr[p][i], arr[q][i]])
                self.add([-e, arr[p][i], -arr[q][i]])
            eqs.append(e)
        self.add(eqs)

    def solve(self, conf_budget: int | None = None):
        s = Cadical153(bootstrap_with=self.clauses)
        t0 = time.time()
        if conf_budget:
            s.conf_budget(conf_budget)
            ok = s.solve_limited()
        else:
            ok = s.solve()
        dt = time.time() - t0
        rects = None
        if ok:
            pos = set(l for l in s.get_model() if l > 0)
            rects = {}
            for k, pc in enumerate(self.pieces):
                xs = [i for i in range(self.W) if self.colcov[k][i] in pos]
                ys = [j for j in range(self.H) if self.rowcov[k][j] in pos]
                rects[pc.pid] = (min(xs), max(xs) + 1, min(ys), max(ys) + 1)
        s.delete()
        return ok, rects, dt, len(self.clauses), self.nv


def compress(rects: dict) -> dict:
    """Remove unused coordinates so the picture is compact (topology preserved)."""
    xs = sorted(set(v for r in rects.values() for v in (r[0], r[1])))
    ys = sorted(set(v for r in rects.values() for v in (r[2], r[3])))
    mx = {v: i for i, v in enumerate(xs)}
    my = {v: i for i, v in enumerate(ys)}
    return {k: (mx[r[0]], mx[r[1]], my[r[2]], my[r[3]]) for k, r in rects.items()}


def contacts_from_rects(rects: dict) -> set:
    """Room-level contact set (positive-length shared boundary) from piece rects."""
    out = set()
    items = list(rects.items())
    for (pa, ra), (pb, rb) in itertools.combinations(items, 2):
        a, b = pa.split("#")[0], pb.split("#")[0]
        if a == b:
            continue
        if (ra[1] == rb[0] or rb[1] == ra[0]) and min(ra[3], rb[3]) - max(ra[2], rb[2]) > 0:
            out.add(frozenset((a, b)))
        elif (ra[3] == rb[2] or rb[3] == ra[2]) and min(ra[1], rb[1]) - max(ra[0], rb[0]) > 0:
            out.add(frozenset((a, b)))
    return out


def is_guillotine(rects: dict) -> bool:
    items = list(rects.values())

    def rec(sub):
        if len(sub) <= 1:
            return True
        x0 = min(r[0] for r in sub); x1 = max(r[1] for r in sub)
        y0 = min(r[2] for r in sub); y1 = max(r[3] for r in sub)
        for x in sorted(set(r[1] for r in sub)):
            if x0 < x < x1 and all(r[1] <= x or r[0] >= x for r in sub):
                return rec([r for r in sub if r[1] <= x]) and rec([r for r in sub if r[0] >= x])
        for y in sorted(set(r[3] for r in sub)):
            if y0 < y < y1 and all(r[3] <= y or r[2] >= y for r in sub):
                return rec([r for r in sub if r[3] <= y]) and rec([r for r in sub if r[2] >= y])
        return False
    return rec(items)


def is_band(rects: dict) -> bool:
    ys = sorted(set((r[2], r[3]) for r in rects.values()))
    for (a0, a1), (b0, b1) in itertools.combinations(ys, 2):
        if a0 < b1 and b0 < a1 and (a0, a1) != (b0, b1):
            return False
    return True


def grid_shapes(P: int, symmetric: bool):
    """Every (W,H) with W+H = P+1 (a dissection into P rectangles has <= P-1 maximal segments,
    so <= W-1 interior x-cuts and <= H-1 interior y-cuts with (W-1)+(H-1) <= P-1). Any dissection
    fits one of these grids; UNSAT on all of them is a proof. `symmetric`: W<=H suffices."""
    out = []
    for W in range(1, P + 1):
        H = P + 1 - W
        if H < 1:
            continue
        if symmetric and W > H:
            continue
        out.append((W, H))
    # largest/squarest first (most likely SAT quickly)
    out.sort(key=lambda wh: (abs(wh[0] - wh[1]), -wh[0]))
    return out


def solve_family(nodes, edges, family: str, l_rooms: tuple = (), conf_budget: int | None = None):
    """family in {'band_y','band_x','slicing','rect'}. Returns (ok, rects, seconds); ok is None when
    the conflict budget ran out on some grid (UNKNOWN)."""
    pieces = [Piece(v, v) for v in nodes]
    for r in l_rooms:
        pieces.append(Piece(r + "#2", r))
    P = len(pieces)
    total = 0.0
    unknown = False
    for W, H in grid_shapes(P, symmetric=(family in ("slicing", "rect"))):
        tm = TilingModel(pieces, W, H)
        for u, v in edges:
            tm.require_room_contact(u, v)
        if family == "band_y":
            tm.require_band_layout("y")
        elif family == "band_x":
            tm.require_band_layout("x")
        elif family == "slicing":
            tm.require_guillotine()
        for r in l_rooms:
            tm.require_L_union(tm.pid_index[r], tm.pid_index[r + "#2"])
        ok, rects, dt, ncl, nv = tm.solve(conf_budget)
        total += dt
        if ok is None:
            unknown = True
            continue
        if ok:
            got = contacts_from_rects(rects)
            for u, v in edges:
                assert frozenset((u, v)) in got, (family, u, v)
            if family == "slicing":
                assert is_guillotine(rects)
            if family == "band_y":
                assert is_band(rects)
            return True, compress(rects), total
    return (None if unknown else False), None, total


def minimal_level(nodes, edges, verbose=False, use_theory=True):
    """Lowest family that carries the graph; for 'L', the minimal number of L rooms (1 or 2) and
    the witnessing room set(s). With use_theory, a K4 or a triple-lens edge settles every
    rectangle-only family as impossible (separating-triangle theorem) without a SAT run."""
    res = {}
    d = diagnostics(nodes, edges)
    if use_theory and (d["k4"] or d["lens3"] or not d["planar"]):
        why = "K4" if d["k4"] else ("edge with >=3 common neighbours" if d["lens3"] else "non-planar")
        for fam in ("band_y", "slicing", "rect"):
            res[fam] = {"ok": False, "rects": None, "seconds": 0.0, "by_theory": why}
        if verbose:
            print(f"   band/slicing/rect: False by theory ({why})")
    for fam in ("band_y", "slicing", "rect"):
        if fam in res:
            continue
        ok, rects, dt = solve_family(nodes, edges, fam)
        res[fam] = {"ok": ok, "rects": rects, "seconds": round(dt, 2)}
        if verbose:
            print(f"   {fam}: {ok} ({dt:.2f}s)")
        if ok and fam == "band_y":
            res["slicing"] = {"ok": True, "rects": rects, "seconds": 0.0, "implied": True}
            res["rect"] = {"ok": True, "rects": rects, "seconds": 0.0, "implied": True}
            break
        if ok and fam == "slicing":
            res["rect"] = {"ok": True, "rects": rects, "seconds": 0.0, "implied": True}
            break
    if not res["rect"]["ok"]:
        res["L1"] = {}
        for r in nodes:
            ok, rects, dt = solve_family(nodes, edges, "rect", l_rooms=(r,))
            res["L1"][r] = {"ok": ok, "rects": rects, "seconds": round(dt, 2)}
            if verbose:
                print(f"   L({r}): {ok} ({dt:.2f}s)")
        if not any(v["ok"] for v in res["L1"].values()):
            res["L2"] = {}
            for r1, r2 in itertools.combinations(nodes, 2):
                ok, rects, dt = solve_family(nodes, edges, "rect", l_rooms=(r1, r2))
                res["L2"][f"{r1}+{r2}"] = {"ok": ok, "rects": rects, "seconds": round(dt, 2)}
                if ok:
                    break
    return res


# ----------------------------------------------------------------------------- max edges per family

def max_edges_family(nodes, edges, family: str, l_rooms: tuple = (), lo: int | None = None):
    """Largest number of required edges a layout in `family` can carry simultaneously (the
    representation's own ceiling, independent of any heuristic). Returns (k_max, kept_edges, rects)."""
    from pysat.card import CardEnc, EncType
    pieces = [Piece(v, v) for v in nodes]
    for r in l_rooms:
        pieces.append(Piece(r + "#2", r))
    P = len(pieces)
    m = len(edges)
    best = (lo or 0, None, None)
    # descend from m: first k that is SAT is the max
    for k in range(m, (lo or 0), -1):
        found = False
        for W, H in grid_shapes(P, symmetric=(family in ("slicing", "rect"))):
            tm = TilingModel(pieces, W, H)
            sel = []
            for u, v in edges:
                s = tm.new()
                atoms = []
                for p in tm.room_pieces[u]:
                    for q in tm.room_pieces[v]:
                        atoms += tm.contact_atoms(p, q)
                tm.add([-s] + atoms)      # s -> edge realized
                sel.append(s)
            if family == "band_y":
                tm.require_band_layout("y")
            elif family == "slicing":
                tm.require_guillotine()
            for r in l_rooms:
                tm.require_L_union(tm.pid_index[r], tm.pid_index[r + "#2"])
            card = CardEnc.atleast(lits=sel, bound=k, top_id=tm.nv, encoding=EncType.seqcounter)
            tm.nv = max(tm.nv, card.nv)
            for cl in card.clauses:
                tm.add(cl)
            ok, rects, dt, _, _ = tm.solve()
            if ok:
                got = contacts_from_rects(rects)
                kept = [e for e in edges if frozenset(e) in got]
                assert len(kept) >= k
                return len(kept), kept, compress(rects)
        # k infeasible on every grid -> continue downward
    return best
