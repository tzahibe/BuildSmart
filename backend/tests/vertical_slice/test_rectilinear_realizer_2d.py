"""Issue #162 (#142A) — Realizability gap closure: a 2D structural carrier beyond the fixed
5-room pinwheel, and a dimension solver that can size it.

AC-1: `GridWing` (`app/vertical_slice/rectilinear_realizer.py`) represents a genuine 2D placement
for n > 5 rooms carrying MORE than n-1 adjacencies, with multiple depths (rows) and branching
(a row spanning multiple columns) — proven on a synthetic 9-room graph a `RowWing` provably
cannot hold (its own slot chain touches at most n-1 = 8 pairs by construction).

AC-2: `graph_embedding.embed_adjacency_graph` never falls back to a row or a fixed pinwheel when
the requested graph cannot be embedded — it REFUSES with a measured `TOPOLOGY_EMBEDDING` reason
naming the best achieved.

AC-5: preservation (`topology_preservation.py`) is measured against the REALIZED geometry, not
merely "did `realize_layout` accept it" — a plan `realize_layout` calls `ok` can still lose a
requested spatial-adjacency pair and FAIL preservation (the #134 donor failure mode).
"""
from __future__ import annotations

from itertools import combinations

from app.vertical_slice.geometry_core.model import ProgramRole
from app.vertical_slice.graph_embedding import EmbeddingRefusal, embed_adjacency_graph
from app.vertical_slice.rectilinear_realizer import (
    GridCell,
    GridWing,
    RealizationIntent,
    RealizedLayout,
    Refusal,
    RowWing,
    ZoneIntent,
    realize_layout,
)
from app.vertical_slice.topology_preservation import measure_spatial_adjacency, verdict


def _zi(zone_id, role, target, lo, hi, min_short, max_aspect) -> ZoneIntent:
    return ZoneIntent(zone_id, role, target, lo, hi, min_short, max_aspect)


def _touching_pairs(rects) -> set:
    ids = list(rects.keys())
    pairs = set()
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            if rects[ids[i]].shared_edge_len_u(rects[ids[j]]) > 0:
                pairs.add(frozenset((ids[i], ids[j])))
    return pairs


# --------------------------------------------------------------------------- AC-1 fixture

#: A 9-room, 10-edge house: a public row (LIVING/KITCHEN/DINING), a 3-segment hall row beneath it,
#: and a private row (3 bedrooms) beneath that — more than n-1=8 edges, and genuinely 2D (3 row
#: "depths", the hall row branching to all 3 bedrooms below and all 3 public rooms above).
_NINE_ROOM_ZONES = {
    "LIVING": _zi("LIVING", ProgramRole.LIVING, 18.0, 12.0, 30.0, 2.6, 3.0),
    "KITCHEN": _zi("KITCHEN", ProgramRole.KITCHEN, 12.0, 8.0, 18.0, 2.2, 3.0),
    "DINING": _zi("DINING", ProgramRole.DINING, 12.0, 8.0, 18.0, 2.2, 3.0),
    "HALL_A": _zi("HALL_A", ProgramRole.HALL, 3.5, 2.0, 10.0, 1.1, 8.0),
    "HALL_B": _zi("HALL_B", ProgramRole.HALL, 3.5, 2.0, 10.0, 1.1, 8.0),
    "HALL_C": _zi("HALL_C", ProgramRole.HALL, 3.5, 2.0, 10.0, 1.1, 8.0),
    "BEDROOM_1": _zi("BEDROOM_1", ProgramRole.BEDROOM, 12.0, 8.0, 18.0, 2.6, 2.5),
    "BEDROOM_2": _zi("BEDROOM_2", ProgramRole.BEDROOM, 12.0, 8.0, 18.0, 2.6, 2.5),
    "BEDROOM_3": _zi("BEDROOM_3", ProgramRole.BEDROOM, 12.0, 8.0, 18.0, 2.6, 2.5),
}
_NINE_ROOM_EDGES = (
    ("LIVING", "KITCHEN"), ("KITCHEN", "DINING"),
    ("LIVING", "HALL_A"), ("KITCHEN", "HALL_B"), ("DINING", "HALL_C"),
    ("HALL_A", "HALL_B"), ("HALL_B", "HALL_C"),
    ("HALL_A", "BEDROOM_1"), ("HALL_B", "BEDROOM_2"), ("HALL_C", "BEDROOM_3"),
)
_NINE_ROOM_ROWS = (
    (GridCell("LIVING"), GridCell("KITCHEN"), GridCell("DINING")),
    (GridCell("HALL_A"), GridCell("HALL_B"), GridCell("HALL_C")),
    (GridCell("BEDROOM_1"), GridCell("BEDROOM_2"), GridCell("BEDROOM_3")),
)


def _nine_room_grid_intent(width_m: float = 9.1, height_m: float = 9.9) -> RealizationIntent:
    wing = GridWing(wing_id="MAIN", width_m=width_m, height_m=height_m, n_cols=3,
                     rows=_NINE_ROOM_ROWS, zones=_NINE_ROOM_ZONES)
    return RealizationIntent(name="NINE_ROOM_GRID", wings=(wing,))


def test_grid_wing_realizes_nine_rooms_with_more_than_n_minus_1_adjacencies():
    """AC-1: a real, validated house, 9 rooms, with 12 genuinely touching pairs — 4 more than a
    RowWing's own n-1=8 ceiling — proving GridWing is a genuine 2D structural carrier, not merely
    a relabelled row."""
    result = realize_layout(_nine_room_grid_intent())
    assert isinstance(result, RealizedLayout), result
    assert result.ok
    assert len(result.design.rooms) == 9

    touching = _touching_pairs(result.rects)
    n = len(_NINE_ROOM_ZONES)
    assert len(touching) > n - 1, touching
    assert len(touching) >= 12, touching

    requested = {frozenset(e) for e in _NINE_ROOM_EDGES}
    assert requested <= touching, requested - touching


def test_grid_wing_has_multiple_depths_and_branching():
    """AC-1's own "multiple depths" (3 stacked row bands) and "branching" (HALL_B touches 4
    neighbours: HALL_A, HALL_C, KITCHEN above, BEDROOM_2 below — a multi-arm junction no single
    row chain slot can ever have, since a row slot touches at most 2 neighbours)."""
    result = realize_layout(_nine_room_grid_intent())
    assert isinstance(result, RealizedLayout), result
    rows_of = {"LIVING": 0, "KITCHEN": 0, "DINING": 0, "HALL_A": 1, "HALL_B": 1, "HALL_C": 1,
               "BEDROOM_1": 2, "BEDROOM_2": 2, "BEDROOM_3": 2}
    depths = {rows_of[zid] for zid in result.rects if zid in rows_of}
    assert depths == {0, 1, 2}

    touching = _touching_pairs(result.rects)
    hall_b_neighbours = {next(iter(pair - {"HALL_B"})) for pair in touching if "HALL_B" in pair}
    assert hall_b_neighbours == {"HALL_A", "HALL_C", "KITCHEN", "BEDROOM_2"}


def test_a_row_wing_cannot_hold_the_same_nine_room_graph():
    """The comparison AC-1 asks for: the identical 9 rooms/10 edges, placed in the best possible
    single `RowWing` order (exhaustive search is infeasible for 9! — this picks a reasonable
    circulation-first order), realize at most n-1=8 touching pairs by construction, never the
    full 10 requested — the ceiling `GridWing` exists to lift."""
    order = ("LIVING", "HALL_A", "BEDROOM_1", "HALL_B", "KITCHEN", "BEDROOM_2", "HALL_C",
              "DINING", "BEDROOM_3")
    assert set(order) == set(_NINE_ROOM_ZONES)
    wing = RowWing(wing_id="MAIN", width_m=30.0, height_m=5.0, slots=order,
                    zones=_NINE_ROOM_ZONES)
    result = realize_layout(RealizationIntent(name="NINE_ROOM_ROW", wings=(wing,)))
    if isinstance(result, RealizedLayout):
        touching = _touching_pairs(result.rects)
        assert len(touching) <= len(_NINE_ROOM_ZONES) - 1
        requested = {frozenset(e) for e in _NINE_ROOM_EDGES}
        assert not requested <= touching
    else:
        assert isinstance(result, Refusal)


def test_embed_adjacency_graph_chooses_grid_for_the_nine_room_graph():
    """AC-1 via the decision layer: `embed_adjacency_graph` itself picks a `GridWing` (never a
    `RowWing`) for this graph, because only a 2D structure can carry all 10 requested edges."""
    wing = embed_adjacency_graph(_NINE_ROOM_ZONES, _NINE_ROOM_EDGES)
    assert isinstance(wing, GridWing), wing


# --------------------------------------------------------------------------- AC-2

def test_embedding_refuses_a_graph_no_available_structure_can_hold():
    """AC-2: K6 (6 rooms, all 15 pairs requested) exceeds every row/pinwheel/grid shape this
    realizer has for n=6 — refused with a measured `TOPOLOGY_EMBEDDING` reason, never silently
    downgraded to a row or any other partial structure presented as success."""
    zones = {f"R{i}": _zi(f"R{i}", ProgramRole.BEDROOM, 10.0, 7.0, 16.0, 2.4, 2.5)
              for i in range(6)}
    edges = list(combinations(zones.keys(), 2))
    result = embed_adjacency_graph(zones, edges)
    assert isinstance(result, EmbeddingRefusal), result
    assert result.constraint == "TOPOLOGY_EMBEDDING"
    assert result.required_edges == 15
    assert result.best_edges_achieved < result.required_edges
    assert str(result.best_edges_achieved) in result.detail
    assert str(result.required_edges) in result.detail


def test_embedding_refusal_is_never_a_wing():
    """The refusal's own type is distinct from every `Wing` — a caller cannot accidentally feed
    an `EmbeddingRefusal` to `realize_layout` as if it were a placement (AC-2's "no fallback")."""
    zones = {f"R{i}": _zi(f"R{i}", ProgramRole.BEDROOM, 10.0, 7.0, 16.0, 2.4, 2.5)
              for i in range(6)}
    edges = list(combinations(zones.keys(), 2))
    result = embed_adjacency_graph(zones, edges)
    assert not isinstance(result, (GridWing, RowWing))
    assert not hasattr(result, "wing_id")


def test_embedding_succeeds_when_the_graph_fits_within_capacity():
    """Control: the SAME 6 rooms with only 5 edges (<= n-1) embed successfully as a RowWing — the
    refusal above is about THIS graph's own density, not a blanket failure for n=6."""
    zones = {f"R{i}": _zi(f"R{i}", ProgramRole.BEDROOM, 10.0, 7.0, 16.0, 2.4, 2.5)
              for i in range(6)}
    edges = [("R0", "R1"), ("R1", "R2"), ("R2", "R3"), ("R3", "R4"), ("R4", "R5")]
    result = embed_adjacency_graph(zones, edges)
    assert isinstance(result, RowWing), result


# --------------------------------------------------------------------------- AC-5

def test_preservation_fails_on_a_valid_plan_that_lost_a_requested_adjacency():
    """AC-5/AC-9's own discipline: a hand-built, perfectly VALID `RowWing` realization (`.ok` is
    True) that was asked to carry a TRIANGLE (LIVING-HUB, HUB-BEDROOM, LIVING-BEDROOM all mutually
    touching) — a shape no 1D chain can ever hold (a chain's own two end slots are never adjacent
    to each other). PRESERVED must report FAIL even though `realize_layout` accepted the house,
    never conflating "valid" with "preserved" (the #134 donor failure mode)."""
    zones = {
        "LIVING": _zi("LIVING", ProgramRole.LIVING, 16.0, 10.0, 26.0, 2.6, 3.0),
        "HUB": _zi("HUB", ProgramRole.HALL, 6.0, 4.0, 14.0, 1.2, 6.0),
        "BEDROOM": _zi("BEDROOM", ProgramRole.BEDROOM, 10.0, 7.0, 16.0, 2.4, 2.5),
    }
    wing = RowWing(wing_id="MAIN", width_m=8.6, height_m=3.5, slots=("LIVING", "HUB", "BEDROOM"),
                    zones=zones)
    result = realize_layout(RealizationIntent(name="TRIANGLE_IN_A_ROW", wings=(wing,)))
    assert isinstance(result, RealizedLayout), result
    assert result.ok

    requested_edges = [("LIVING", "HUB"), ("HUB", "BEDROOM"), ("LIVING", "BEDROOM")]
    preservation = measure_spatial_adjacency(result.rects, requested_edges)
    assert verdict(preservation) == "FAIL"
    assert preservation.preserved < preservation.requested
    assert "LIVING-BEDROOM" in preservation.lost or "BEDROOM-LIVING" in preservation.lost


def test_preservation_passes_when_every_requested_adjacency_is_realized():
    """Control: the GridWing case above (AC-1) preserves every one of its 10 requested edges — a
    PASS verdict is reachable, this is not a function that always fails."""
    result = realize_layout(_nine_room_grid_intent())
    assert isinstance(result, RealizedLayout), result
    preservation = measure_spatial_adjacency(result.rects, _NINE_ROOM_EDGES)
    assert verdict(preservation) == "PASS"
    assert preservation.lost == ()
