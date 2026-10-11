"""Exact planarity test for small undirected graphs (Demoucron–Malgrange–Pertuiset), dependency-free.

Why this exists: a required spatial-adjacency graph that is not planar cannot be the contact graph
of ANY partition of the plane — not rectangles, not bands, not L-shapes, nothing — so the pipeline
must refuse it as `TOPOLOGY_NON_PLANAR` before any geometry is attempted (Issue #142E; the frozen
brief B19 is the live example). `networkx` is a dev-only dependency here, and planarity of a room
graph (n <= ~20) does not justify a runtime graph library: DMP is ~120 lines, exact, and O(n^2).

Algorithm (per biconnected component; a graph is planar iff every biconnected component is):
start from a cycle embedded as two faces; repeatedly take a *fragment* of G relative to the partial
embedding H (an edge of G-H with both ends in H, or a connected component of G-V(H) plus its
attachment edges), find the faces that contain all of its attachment vertices, embed one path of the
fragment into such a face (splitting it); if some fragment has no admissible face, G is not planar.
Faces are cyclic vertex lists; the graph is simple (no multi-edges, no loops).
"""
from __future__ import annotations

from collections.abc import Hashable, Iterable

Node = Hashable


def _adjacency(nodes: Iterable[Node], edges: Iterable[tuple[Node, Node]]) -> dict[Node, set[Node]]:
    adj: dict[Node, set[Node]] = {v: set() for v in nodes}
    for a, b in edges:
        if a == b:
            continue
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    return adj


def biconnected_components(adj: dict[Node, set[Node]]) -> list[set[Node]]:
    """Tarjan: vertex sets of the biconnected components (bridges count as 2-vertex components)."""
    index: dict[Node, int] = {}
    low: dict[Node, int] = {}
    comps: list[set[Node]] = []
    counter = 0
    for root in adj:
        if root in index:
            continue
        stack: list[tuple[Node, Node | None, Iterable]] = [(root, None, iter(adj[root]))]
        edge_stack: list[tuple[Node, Node]] = []
        index[root] = low[root] = counter
        counter += 1
        while stack:
            v, parent, it = stack[-1]
            advanced = False
            for w in it:
                if w == parent:
                    continue
                if w not in index:
                    index[w] = low[w] = counter
                    counter += 1
                    edge_stack.append((v, w))
                    stack.append((w, v, iter(adj[w])))
                    advanced = True
                    break
                if index[w] < index[v]:
                    edge_stack.append((v, w))
                    low[v] = min(low[v], index[w])
            if advanced:
                continue
            stack.pop()
            if stack:
                u = stack[-1][0]
                low[u] = min(low[u], low[v])
                if low[v] >= index[u]:
                    comp: set[Node] = set()
                    while edge_stack:
                        e = edge_stack.pop()
                        comp.update(e)
                        if e == (u, v):
                            break
                    comps.append(comp)
    return comps


def _find_cycle(adj: dict[Node, set[Node]]) -> list[Node] | None:
    """Any simple cycle in a biconnected graph with >= 3 vertices (DFS back edge)."""
    start = next(iter(adj))
    parent: dict[Node, Node | None] = {start: None}
    order: list[Node] = []
    stack = [start]
    visited = set()
    while stack:
        v = stack.pop()
        if v in visited:
            continue
        visited.add(v)
        order.append(v)
        for w in sorted(adj[v], key=repr):
            if w not in visited:
                parent[w] = v
                stack.append(w)
    pos = {v: i for i, v in enumerate(order)}
    for v in order:
        for w in adj[v]:
            if w == parent[v] or parent.get(w) == v:
                continue
            # v-w is a non-tree edge; walk tree ancestors of the deeper one until the other is hit
            a, b = (v, w) if pos[v] > pos[w] else (w, v)
            path = [a]
            x = a
            while x != b and parent.get(x) is not None:
                x = parent[x]
                path.append(x)
            if x == b and len(path) >= 3:
                return path
    return None


def _is_planar_biconnected(adj: dict[Node, set[Node]]) -> bool:
    n = len(adj)
    m = sum(len(s) for s in adj.values()) // 2
    if n <= 4:
        return True
    if m > 3 * n - 6:
        return False
    cycle = _find_cycle(adj)
    if cycle is None:
        return True
    h_nodes = set(cycle)
    h_edges = {frozenset((cycle[i], cycle[(i + 1) % len(cycle)])) for i in range(len(cycle))}
    faces: list[list[Node]] = [list(cycle), list(reversed(cycle))]
    all_edges = {frozenset((a, b)) for a in adj for b in adj[a]}
    while h_edges != all_edges:
        # fragments
        fragments: list[tuple[set[Node], set[Node], set[frozenset]]] = []  # (attachments, interior, edges)
        for e in all_edges - h_edges:
            a, b = tuple(e)
            if a in h_nodes and b in h_nodes:
                fragments.append(({a, b}, set(), {e}))
        outside = set(adj) - h_nodes
        seen: set[Node] = set()
        for v in outside:
            if v in seen:
                continue
            comp = set()
            stack = [v]
            while stack:
                x = stack.pop()
                if x in comp:
                    continue
                comp.add(x)
                for y in adj[x]:
                    if y in outside and y not in comp:
                        stack.append(y)
            seen |= comp
            att = {y for x in comp for y in adj[x] if y in h_nodes}
            fe = {frozenset((x, y)) for x in comp for y in adj[x] if y in comp or y in h_nodes}
            fragments.append((att, comp, fe))
        # admissible faces
        chosen = None
        for frag in fragments:
            att, interior, fe = frag
            adm = [i for i, f in enumerate(faces) if att <= set(f)]
            if not adm:
                return False
            if len(adm) == 1:
                chosen = (frag, adm[0])
                break
            if chosen is None:
                chosen = (frag, adm[0])
        (att, interior, fe), fi = chosen
        # a path inside the fragment between two attachment vertices (or one edge)
        att_list = sorted(att, key=repr)
        if not interior:
            path = list(tuple(next(iter(fe))))
            if path[0] != att_list[0]:
                path.reverse()
        else:
            u = att_list[0]
            # BFS from u through interior to another attachment vertex (or back to u via >= 1 interior
            # vertex when the fragment has a single attachment — impossible in a biconnected graph)
            prev: dict[Node, Node | None] = {u: None}
            queue = [u]
            target = None
            while queue and target is None:
                x = queue.pop(0)
                for y in sorted(adj[x], key=repr):
                    if frozenset((x, y)) not in fe or y in prev:
                        continue
                    prev[y] = x
                    if y in att and y != u:
                        target = y
                        break
                    if y in interior:
                        queue.append(y)
            if target is None:
                return False
            path = [target]
            while prev[path[-1]] is not None:
                path.append(prev[path[-1]])
            path.reverse()
        # embed path into face fi: split the face cycle at path[0] and path[-1]
        face = faces[fi]
        i0, i1 = face.index(path[0]), face.index(path[-1])
        if i0 <= i1:
            arc1 = face[i0:i1 + 1]
            arc2 = face[i1:] + face[:i0 + 1]
        else:
            arc1 = face[i0:] + face[:i1 + 1]
            arc2 = face[i1:i0 + 1]
        inner = path[1:-1]
        new1 = arc1 + list(reversed(inner))          # path[0] .. path[-1] via face, back via path
        new2 = arc2 + inner                          # path[-1] .. path[0] via face, back via path
        faces[fi] = new1
        faces.append(new2)
        for i in range(len(path) - 1):
            h_edges.add(frozenset((path[i], path[i + 1])))
        h_nodes.update(path)
    return True


def is_planar(nodes: Iterable[Node], edges: Iterable[tuple[Node, Node]]) -> bool:
    adj = _adjacency(nodes, edges)
    for comp in biconnected_components(adj):
        if len(comp) <= 2:
            continue
        sub = {v: {w for w in adj[v] if w in comp} for v in comp}
        if not _is_planar_biconnected(sub):
            return False
    return True


__all__ = ["is_planar", "biconnected_components"]
