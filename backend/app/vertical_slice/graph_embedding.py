"""Graph -> wing embedding DECISION (Issue #162/#142A; ROW/GRID made EXACT in Issue #142E).

`rectilinear_realizer.py` gained a genuine 2D structural carrier (`GridWing`, alongside the
existing `PinwheelWing`/`RowWing`) in this same Issue, but a `Wing` already requires placement
DECIDED — room-to-slot assignment, not merely room ids and roles. This module is the missing
decision step: given a plain room graph (ids, each room's own `ZoneIntent`, and the undirected
spatial-adjacency pairs it must carry), `embed_adjacency_graph` searches every 2D structure this
realizer offers and returns the first `Wing` whose own slot/grid adjacency can carry the FULL
requested graph — or, when none can, an `EmbeddingRefusal` naming the measured best achieved
(AC-2): **never a silent row fallback**, and never a silently downgraded, partially-connected
layout presented as success.

Three structures are tried, in this fixed order, never mixed within one decision:

  1. **PINWHEEL** (`n == 5` only) — exhaustive 5! search over the 5 room-to-slot assignments,
     scored against the 8 slot-pairs a `PinwheelWing` can ever physically touch (4 spokes + 4
     corner interlocks — see `rectilinear_realizer`'s own module docstring).
  2. **ROW** (`n - 1` edge ceiling) — the degenerate 1-row case of the SAME grid search below
     (`n_rows == 1`), kept distinct only in the RETURNED `Wing` type (`RowWing`, not `GridWing`),
     matching `rectilinear_realizer`'s own existing structure.
  3. **GRID** (`n_rows` from 2 up to `_MAX_GRID_ROWS`) — a greedy-construct-then-local-search
     heuristic assignment (degree-first greedy placement, then bounded pairwise-swap refinement,
     both fully deterministic — no randomness) onto each candidate grid shape's own slot adjacency
     (within-row chain + overlapping-column cross-row pairs — see `GridWing`'s own docstring for
     why overlap is geometrically exact, not merely logical).

This is a HEURISTIC search, not a completeness proof: when every shape tried falls short of the
full requested graph, the refusal reports the BEST achieved, honestly, never a claim that no
larger search could do better — exactly the same "measured, not guessed" discipline
`rectilinear_realizer._solve_pinwheel`/`_solve_grid` already apply to sizing.

Disclosed gap: "which structure to try" and "which assignment of it to use" are decided together,
in one search, per shape — there is no separate step that commits to a structure and then asks
whether an assignment of it succeeds. Every shortfall is therefore reported as the single
`TOPOLOGY_EMBEDDING` constraint (`gap_closure_142a.classify_refusal`'s own docstring), never the
AC-6 taxonomy's distinct `PLACEMENT` bucket ("a structure was selected but no assignment of it
could satisfy the request") — `PLACEMENT` is a defined bucket this implementation does not yet
produce.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations

from .band_embedding import BandEmbedding, embed_band
from .rectilinear_realizer import GridCell, GridWing, PinwheelWing, RowWing, Wing, ZoneIntent

#: The 8 slot-pairs a `PinwheelWing` can ever realize as a physically-touching pair (module
#: docstring): the 4 spokes (center always touches every arm) plus the 4 corner interlocks.
_PINWHEEL_SLOTS = ("center", "n", "e", "s", "w")
_PINWHEEL_ACHIEVABLE_SLOT_PAIRS = (
    ("center", "n"), ("center", "e"), ("center", "s"), ("center", "w"),
    ("n", "e"), ("e", "s"), ("s", "w"), ("w", "n"),
)

#: Bounds how many grid shapes this search tries (row counts 1..this, 1 being the ROW case) —
#: a search-COST bound, not a structural ceiling: `GridWing` itself has no row-count limit.
_MAX_GRID_ROWS = 6
#: Local-search refinement passes (bounded, deterministic — see module docstring).
_LOCAL_SEARCH_PASSES = 25


@dataclass(frozen=True)
class EmbeddingRefusal:
    """No available 2D structure (row/pinwheel/grid) can carry the full requested graph — the
    TOPOLOGY_EMBEDDING classification (Issue #162/#142A, AC-2/AC-6), never a silent row/pinwheel
    fallback."""

    constraint: str
    detail: str
    best_edges_achieved: int
    required_edges: int
    best_form: str


def _edge_set(edges) -> frozenset:
    return frozenset(frozenset(e) for e in edges)


def _row_lengths_for(n: int, n_rows: int) -> tuple[int, ...]:
    base, rem = divmod(n, n_rows)
    return tuple([base + 1] * rem + [base] * (n_rows - rem))


def _slot_positions(row_lengths: tuple[int, ...], n_cols: int) -> list[tuple[int, int, int]]:
    """One `(row_idx, col_start, col_span)` per slot, flattened row-major — the LAST slot in a
    row shorter than `n_cols` absorbs the remainder, so every row still tiles the full width
    (mirrors `GridWing`'s own `col_span` contract)."""
    slots = []
    for r_idx, row_len in enumerate(row_lengths):
        for i in range(row_len):
            span = 1 if i < row_len - 1 else n_cols - (row_len - 1)
            slots.append((r_idx, i, span))
    return slots


def _slot_adjacency(slots: list[tuple[int, int, int]]) -> frozenset:
    """Index-pair adjacency among `slots`: each row's own left-right chain, plus every cross-row
    pair whose column ranges overlap — the exact geometric touching `GridWing` guarantees by
    construction (uniform column boundaries shared by every row)."""
    adj: set = set()
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


def _assign_rooms_to_slots(room_ids: list[str], edges: frozenset, slot_adj: frozenset,
                            n_slots: int) -> tuple[dict[int, str], int]:
    """Greedy-construct (highest-degree room first, into the slot most connected to what is
    already placed) then bounded pairwise-swap local search — deterministic, no randomness.
    Returns the slot->room assignment and the number of requested edges it achieves."""
    degree: dict[str, int] = {r: 0 for r in room_ids}
    for e in edges:
        a, b = tuple(e)
        degree[a] += 1
        degree[b] += 1
    order = sorted(room_ids, key=lambda r: (-degree[r], r))
    slot_degree = {i: sum(1 for j in range(n_slots) if frozenset((i, j)) in slot_adj)
                   for i in range(n_slots)}
    slot_order = sorted(range(n_slots), key=lambda i: (-slot_degree[i], i))

    assignment: dict[int, str] = {}
    placed: dict[str, int] = {}
    empty = list(slot_order)
    for room in order:
        if not empty:
            break
        best_slot, best_score = empty[0], -1
        for slot in empty:
            score = sum(1 for other_room, other_slot in placed.items()
                        if frozenset((slot, other_slot)) in slot_adj
                        and frozenset((room, other_room)) in edges)
            if score > best_score:
                best_score, best_slot = score, slot
        assignment[best_slot] = room
        placed[room] = best_slot
        empty.remove(best_slot)

    def _score(assign: dict[int, str]) -> int:
        room_to_slot = {v: k for k, v in assign.items()}
        total = 0
        for e in edges:
            a, b = tuple(e)
            if a in room_to_slot and b in room_to_slot and \
                    frozenset((room_to_slot[a], room_to_slot[b])) in slot_adj:
                total += 1
        return total

    cur_score = _score(assignment)
    slot_list = list(assignment.keys())
    for _ in range(_LOCAL_SEARCH_PASSES):
        improved = False
        for i in range(len(slot_list)):
            for j in range(i + 1, len(slot_list)):
                s1, s2 = slot_list[i], slot_list[j]
                assignment[s1], assignment[s2] = assignment[s2], assignment[s1]
                new_score = _score(assignment)
                if new_score > cur_score:
                    cur_score, improved = new_score, True
                else:
                    assignment[s1], assignment[s2] = assignment[s2], assignment[s1]
        if not improved:
            break
    return assignment, cur_score


def _best_pinwheel(room_ids: list[str], edges: frozenset) -> tuple[dict[str, str], int]:
    best_mapping, best_score = None, -1
    for perm in permutations(room_ids):
        mapping = dict(zip(_PINWHEEL_SLOTS, perm))
        achieved = {frozenset((mapping[a], mapping[b])) for a, b in _PINWHEEL_ACHIEVABLE_SLOT_PAIRS}
        score = len(edges & achieved)
        if score > best_score:
            best_score, best_mapping = score, mapping
    assert best_mapping is not None
    return best_mapping, best_score


def _default_envelope(zones: dict[str, ZoneIntent], aspect: float) -> tuple[float, float]:
    total = sum(z.target_area_m2 for z in zones.values())
    width = max(1.0, (total * aspect) ** 0.5)
    height = max(1.0, total / width)
    return round(width, 2), round(height, 2)


def _grid_wing_from_assignment(wing_id: str, assignment: dict[int, str],
                                slots: list[tuple[int, int, int]], row_lengths: tuple[int, ...],
                                n_cols: int, zones: dict[str, ZoneIntent], width_m: float,
                                height_m: float) -> GridWing:
    rows: list[tuple[GridCell, ...]] = []
    idx = 0
    for row_len in row_lengths:
        row_cells = []
        for _ in range(row_len):
            room_id = assignment[idx]
            _, _, span = slots[idx]
            row_cells.append(GridCell(room_id, col_span=span))
            idx += 1
        rows.append(tuple(row_cells))
    return GridWing(wing_id=wing_id, width_m=width_m, height_m=height_m, n_cols=n_cols,
                     rows=tuple(rows), zones=zones)


def embed_adjacency_graph(zones: dict[str, ZoneIntent], edges, wing_id: str = "MAIN",
                           envelope_scale: float = 1.0,
                           envelope_override: "tuple[float, float] | None" = None
                           ) -> "Wing | EmbeddingRefusal":
    """Decides placement for `zones` (room id -> its own sizing/role intent) carrying the
    undirected `edges` (iterable of 2-element id pairs) — never mutates `zones`/`edges`. Returns
    the chosen `Wing` the FIRST structure found that carries every requested edge, in PINWHEEL (if
    `len(zones) == 5`) -> ROW -> GRID order; `EmbeddingRefusal` when none does (AC-2)."""
    room_ids = list(zones.keys())
    n = len(room_ids)
    edge_set = _edge_set(edges)
    required = len(edge_set)

    best_score, best_form = -1, "NONE"

    if n == 5:
        mapping, score = _best_pinwheel(room_ids, edge_set)
        if score >= required:
            width_m, height_m = envelope_override or _default_envelope(zones, 1.0)
            return PinwheelWing(
                wing_id=wing_id, width_m=width_m, height_m=height_m, n=zones[mapping["n"]],
                e=zones[mapping["e"]], s=zones[mapping["s"]], w=zones[mapping["w"]],
                center=zones[mapping["center"]])
        best_score, best_form = score, "PINWHEEL (5 zones)"

    # Issue #142E: ROW/GRID are decided EXACTLY by `band_embedding.embed_band` (a single-band
    # layout is a RowWing, anything else a GridWing). The #142A greedy slot heuristic below is kept
    # only to report, in a refusal, how much of the graph the old search would have carried.
    exact = embed_band(zones, edge_set)
    if isinstance(exact, BandEmbedding):
        # keep #142A's structure order: a single-band (ROW) layout is preferred when one exists
        best = next((c for c in exact.candidates if len(c.rows) == 1), exact.candidates[0])
        n_rows = len(best.rows)
        aspect = best.n_cols / n_rows
        width_m, height_m = envelope_override or _default_envelope(zones, aspect)
        if envelope_override is None and envelope_scale != 1.0:
            width_m = round(width_m * envelope_scale ** 0.5, 2)
            height_m = round(height_m * envelope_scale ** 0.5, 2)
        if n_rows == 1:
            return RowWing(wing_id=wing_id, width_m=width_m, height_m=height_m,
                            slots=tuple(z for z, _ in best.rows[0]), zones=zones)
        return best.to_grid_wing(wing_id, width_m, height_m, zones, envelope_is_bound=False)
    exact_detail = f"{exact.code}: {exact.detail}"

    max_rows = min(n, _MAX_GRID_ROWS) if n > 0 else 0
    for n_rows in range(1, max_rows + 1):
        row_lengths = _row_lengths_for(n, n_rows)
        n_cols = max(row_lengths)
        slots = _slot_positions(row_lengths, n_cols)
        slot_adj = _slot_adjacency(slots)
        assignment, score = _assign_rooms_to_slots(room_ids, edge_set, slot_adj, len(slots))
        form = "ROW" if n_rows == 1 else f"GRID {n_rows}x{n_cols}"
        if score > best_score:
            best_score, best_form = score, form

    return EmbeddingRefusal(
        "TOPOLOGY_EMBEDDING",
        f"no available 2D structure (pinwheel / exact band layout) can embed the requested graph "
        f"among {n} rooms — {exact_detail}; the #142A heuristic's best partial placement was "
        f"{best_form}, achieving {best_score}/{required} requested spatial-adjacency pairs",
        best_score, required, best_form)


__all__ = ["EmbeddingRefusal", "embed_adjacency_graph"]
