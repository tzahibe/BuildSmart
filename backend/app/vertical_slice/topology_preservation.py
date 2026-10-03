"""Preservation measurement (Issue #162/#142A, AC-5).

"A valid plan that destroyed the requested topology is a FAIL, not a pass" — the Issue's own
words, matching #160's own AC-9 finding (the #134 donor failure mode this Issue exists to avoid
repeating). `realize_layout`'s own `RealizedLayout.ok` answers a DIFFERENT question — "is this a
valid, buildable house" — never "did it keep what was requested." This module answers the second
question only, off the SAME realized rects/access edges `realize_layout` already produced, never
re-deriving geometry.
"""
from __future__ import annotations

from dataclasses import dataclass

from .geometry_core.model import Rect


@dataclass(frozen=True)
class PreservationResult:
    name: str
    preserved: int
    requested: int
    lost: tuple[str, ...]

    @property
    def fully_preserved(self) -> bool:
        return self.requested == 0 or self.preserved == self.requested


def verdict(result: PreservationResult) -> str:
    """PASS only when every requested relationship was kept — never merely "the realizer/
    validator accepted this plan" (AC-5, AC-9's own discipline)."""
    return "PASS" if result.fully_preserved else "FAIL"


def _touching_pairs(rects: dict[str, Rect]) -> frozenset:
    ids = list(rects.keys())
    pairs = set()
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            if rects[ids[i]].shared_edge_len_u(rects[ids[j]]) > 0:
                pairs.add(frozenset((ids[i], ids[j])))
    return frozenset(pairs)


def measure_spatial_adjacency(rects: dict[str, Rect], requested_edges) -> PreservationResult:
    """Every requested (undirected) room-id pair against the REALIZED rects' own real touching
    (`Rect.shared_edge_len_u`), never the placement that was asked for — a pair geometrically
    collapsed by the realizer (e.g. a row forced to drop a cross-connection) is LOST here even
    when the realized house is otherwise perfectly valid."""
    touching = _touching_pairs(rects)
    requested = list(requested_edges)
    lost, preserved = [], 0
    for pair in requested:
        a, b = tuple(pair)
        if frozenset((a, b)) in touching:
            preserved += 1
        else:
            lost.append(f"{a}-{b}")
    return PreservationResult("spatial_adjacency", preserved, len(requested), tuple(lost))


def measure_access_graph(access_edges, requested_edges) -> PreservationResult:
    """Every requested (undirected) room-id pair against the REALIZED doors only
    (`fixture.access.edges` — every realized access edge IS a door; see
    `rectilinear_realizer.realize_layout`'s own `ConnectionKind.DOOR` construction)."""
    realized_pairs = frozenset(frozenset((e.a, e.b)) for e in access_edges)
    requested = list(requested_edges)
    lost, preserved = [], 0
    for pair in requested:
        a, b = tuple(pair)
        if frozenset((a, b)) in realized_pairs:
            preserved += 1
        else:
            lost.append(f"{a}-{b}")
    return PreservationResult("access_graph", preserved, len(requested), tuple(lost))


__all__ = ["PreservationResult", "verdict", "measure_spatial_adjacency", "measure_access_graph"]
