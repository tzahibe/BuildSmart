"""Cross-band cells (#200): one representation — Cell = row interval x column interval — for the
band family, the spine, the stack and a room two bands deep; one exact sizer for all of them."""
import pytest

from app.ai_harness.shape_agnostic.cells import (
    CellLayout,
    duplicated_layouts,
    extend,
    from_bands,
    moves,
    split,
)
from app.vertical_slice.geometry_core.model import ProgramRole as R
from tests.vertical_slice.test_spine_embedding import _hub_programme, _z

ACCESS = [("HALL", "LIVING"), ("LIVING", "KITCHEN"), ("HALL", "BED1"), ("HALL", "BED2"), ("HALL", "MASTER"),
          ("HALL", "BATH")]


def _union(edges):
    return sorted({tuple(sorted(e)) for e in edges} | {tuple(sorted(e)) for e in ACCESS})


def test_a_band_layout_is_a_cell_layout_with_no_spanning_zone():
    lay = from_bands((("KITCHEN", "LIVING"), ("BED1", "HALL", "MASTER"), ("BED2", "BATH")))
    assert lay.n_rows == 3 and lay.spanning == () and lay.problems() == []
    assert lay.span("HALL") == (1, 1)


def test_a_spanning_zone_keeps_c22_first_or_last_in_all_its_rows_or_none():
    ok = CellLayout((("KITCHEN", "LIVING"), ("BED1", "HALL", "LIVING"), ("BED2", "HALL", "BATH")))
    assert ok.problems() == [] and ok.span("LIVING") == (0, 1) and ok.span("HALL") == (1, 2)
    bad = CellLayout((("LIVING", "KITCHEN"), ("BED1", "HALL", "LIVING")))      # LIVING first, then last
    assert any("C22" in p for p in bad.problems())
    gap = CellLayout((("LIVING",), ("HALL",), ("LIVING",)))
    assert any("contiguous" in p for p in gap.problems())


def test_possible_contacts_are_sequence_neighbours_or_adjacent_row_intervals():
    lay = CellLayout((("KITCHEN", "LIVING"), ("BED1", "HALL", "LIVING"), ("BED2", "HALL", "BATH")))
    poss = lay.possible_contacts()
    assert frozenset(("HALL", "LIVING")) in poss          # neighbours in row 1
    assert frozenset(("KITCHEN", "BED1")) in poss         # rows 0 and 1
    assert frozenset(("KITCHEN", "BED2")) not in poss     # rows 0 and 2: no shared wall
    assert frozenset(("LIVING", "BATH")) in poss          # LIVING spans rows 0-1, BATH is in row 2


def test_extend_and_split_are_the_spine_and_the_stack():
    lay = from_bands((("KITCHEN", "LIVING", "BATH", "WC"), ("BED1", "HALL", "MASTER"), ("BED2",)))
    deep = extend(lay, "KITCHEN", 1, 0)
    assert deep is not None and deep.span("KITCHEN") == (0, 1) and deep.rows[1][0] == "KITCHEN"
    assert extend(lay, "KITCHEN", 2, 0) is None                         # not an adjacent row
    stacked = split(lay, 0, "BATH", "WC")
    assert stacked is not None and stacked.n_rows == 4
    assert stacked.rows[0] == ("KITCHEN", "LIVING", "BATH") and stacked.rows[1] == ("KITCHEN", "LIVING", "WC")
    assert stacked.span("LIVING") == (0, 1) and stacked.span("BATH") == (0, 0) and stacked.span("WC") == (1, 1)


def test_moves_keep_every_required_contact_possible():
    zones, edges = _hub_programme()
    zones["WC"] = _z("WC", R.TOILET, 4, 3.5, 5.5, 1.4, 2.5)
    edges = edges + [("HALL", "WC")]
    lay = from_bands((("KITCHEN", "LIVING", "BATH", "WC"), ("BED1", "HALL", "MASTER"), ("BED2",)))
    for m in moves(lay, zones, edges):
        assert m.problems() == [] and m.admits(edges)


def test_duplication_finds_layouts_with_the_zone_two_rows_deep():
    zones, edges = _hub_programme()
    for z in ("LIVING", "HALL"):
        found = duplicated_layouts(zones, _union(edges), z)
        assert found
        for lay in found:
            assert lay.span(z)[1] - lay.span(z)[0] == 1 and lay.problems() == [] and lay.admits(_union(edges))
            assert sorted(lay.zones) == sorted(zones)


def test_the_unified_sizer_realizes_a_band_layout_and_a_two_row_hall():
    pytest.importorskip("scipy")
    from app.ai_harness.shape_agnostic.milp_cells import (
        cells_placement,
        cells_rects,
        cells_wings,
    )
    from app.vertical_slice.band_embedding import embed_band
    from app.vertical_slice.band_sizing import contact_requirements
    from app.vertical_slice.envelope import Envelope
    from app.vertical_slice.rectilinear_realizer import RealizedLayout, realize_cells
    from app.vertical_slice.topology_preservation import (
        measure_access_graph,
        measure_spatial_adjacency,
    )
    from tests.vertical_slice.test_milp_spine import WET
    zones, edges = _hub_programme()
    union = _union(edges)
    contacts = contact_requirements(zones, union, ACCESS)
    env = Envelope.rectangle(14, 12)
    pools = {"band": [from_bands(c.bands) for c in embed_band(zones, union, max_candidates=30).candidates],
             "deep hall": duplicated_layouts(zones, union, "HALL", max_candidates=60)}
    arrival = {R.HALL, R.CIRCULATION, R.LIVING}
    for name, layouts in pools.items():
        for lay in layouts:
            if not any(zones[z].role in arrival for z in lay.rows[0]):
                continue                                   # production's entrance screen, as the harness applies it
            res = cells_placement(lay, zones, union, env, min_contact_u=contacts, k=6)
            if res.status != "FEASIBLE":
                continue
            rects, wings = cells_rects(lay, res), cells_wings(lay, res)
            for z, r in rects.items():
                r0, r1 = lay.span(z)
                assert r.h == sum(res.heights_u[r0:r1 + 1]), z           # a spanning cell is one rectangle
            out = realize_cells(name, rects, zones, wings, ACCESS, wet_rooms=WET)
            if not isinstance(out, RealizedLayout):
                continue
            sp = measure_spatial_adjacency(out.rects, frozenset(frozenset(e) for e in edges))
            ac = measure_access_graph(out.fixture.access.edges, ACCESS)
            assert sp.preserved == sp.requested and ac.preserved == ac.requested
            break
        else:
            pytest.fail(f"no {name} layout realized")
