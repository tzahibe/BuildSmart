"""Issue #142E — exact band embedding, planarity and typed refusals (unit level)."""
from __future__ import annotations

from itertools import combinations

import pytest

from app.vertical_slice.band_embedding import (
    BandEmbedding,
    BandEmbeddingRefusal,
    embed_band,
    find_k4,
    find_triple_lens,
    verify_rows,
)
from app.vertical_slice.geometry_core.model import ProgramRole
from app.vertical_slice.graph_planarity import biconnected_components, is_planar
from app.vertical_slice.rectilinear_realizer import ZoneIntent


def _zones(ids, role=ProgramRole.BEDROOM):
    return {i: ZoneIntent(i, role, 12.0, 9.0, 16.0, 2.6, 2.5) for i in ids}


# --------------------------------------------------------------------------- planarity

def test_planarity_classics():
    assert not is_planar(range(5), list(combinations(range(5), 2)))                      # K5
    assert not is_planar(range(6), [(a, b) for a in range(3) for b in range(3, 6)])      # K3,3
    assert is_planar(range(4), list(combinations(range(4), 2)))                           # K4
    petersen = [(i, (i + 1) % 5) for i in range(5)] + [(i, i + 5) for i in range(5)] + \
               [(5 + i, 5 + (i + 2) % 5) for i in range(5)]
    assert not is_planar(range(10), petersen)
    grid = [((i, j), (i + 1, j)) for i in range(3) for j in range(4)] + \
           [((i, j), (i, j + 1)) for i in range(4) for j in range(3)]
    assert is_planar([(i, j) for i in range(4) for j in range(4)], grid)
    wheel = [("c", i) for i in range(6)] + [(i, (i + 1) % 6) for i in range(6)]
    assert is_planar(["c", *range(6)], wheel)
    assert is_planar(["a", "b", "c"], [])                                                 # edgeless


def test_biconnected_components_split_at_articulation():
    adj = {"a": {"b", "c"}, "b": {"a", "c"}, "c": {"a", "b", "d"}, "d": {"c", "e"}, "e": {"d"}}
    comps = sorted(sorted(c) for c in biconnected_components(adj))
    assert ["a", "b", "c"] in comps and ["c", "d"] in comps and ["d", "e"] in comps


# --------------------------------------------------------------------------- obstructions

def test_k4_and_triple_lens_detection():
    adj = {"a": {"b", "c", "d"}, "b": {"a", "c", "d"}, "c": {"a", "b", "d"}, "d": {"a", "b", "c"}}
    assert find_k4(adj) == ("a", "b", "c", "d")
    lens = {"a": {"b", "x", "y", "z"}, "b": {"a", "x", "y", "z"}, "x": {"a", "b"}, "y": {"a", "b"}, "z": {"a", "b"}}
    assert find_k4(lens) is None
    assert find_triple_lens(lens) == (("a", "b"), ("x", "y", "z"))


def test_refusals_are_typed_and_never_partial():
    z = _zones("abcd")
    r = embed_band(z, list(combinations("abcd", 2)))
    assert isinstance(r, BandEmbeddingRefusal)
    assert r.code == "TOPOLOGY_REPRESENTATION_LIMIT" and r.proof_complete
    lens = _zones("abxyz")
    r2 = embed_band(lens, [("a", "b"), ("a", "x"), ("b", "x"), ("a", "y"), ("b", "y"), ("a", "z"), ("b", "z")])
    assert isinstance(r2, BandEmbeddingRefusal) and r2.code == "TOPOLOGY_REPRESENTATION_LIMIT"
    k33 = _zones("abcdef")
    r3 = embed_band(k33, [(a, b) for a in "abc" for b in "def"])
    assert isinstance(r3, BandEmbeddingRefusal) and r3.code == "TOPOLOGY_NON_PLANAR"
    for ref in (r, r2, r3):
        assert not hasattr(ref, "candidates")


# --------------------------------------------------------------------------- embeddings

def test_path_graph_embeds_as_a_single_band_and_every_candidate_carries_all_edges():
    z = _zones("abcdef")
    edges = [("a", "b"), ("b", "c"), ("c", "d"), ("d", "e"), ("e", "f")]
    r = embed_band(z, edges)
    assert isinstance(r, BandEmbedding)
    assert any(len(c.rows) == 1 for c in r.candidates)
    for c in r.candidates:
        assert verify_rows(c.rows, c.n_cols, edges) == []
        assert all(sum(s for _, s in row) == c.n_cols for row in c.rows)


def test_hub_of_degree_eight_embeds():
    """A hub touching 8 rooms (the production #142A search capped every slot at 4)."""
    ids = ["h"] + [f"r{i}" for i in range(8)]
    z = _zones(ids); z["h"] = ZoneIntent("h", ProgramRole.HALL, 12.0, 5.0, 30.0, 1.2, 2.5)
    edges = [("h", r) for r in ids[1:]]
    r = embed_band(z, edges)
    assert isinstance(r, BandEmbedding)
    assert verify_rows(r.candidates[0].rows, r.candidates[0].n_cols, edges) == []


def test_wheel_graph_embeds_with_extra_contacts_allowed():
    ids = ["c", "n", "e", "s", "w"]
    z = _zones(ids)
    edges = [("c", "n"), ("c", "e"), ("c", "s"), ("c", "w"), ("n", "e"), ("e", "s"), ("s", "w"), ("w", "n")]
    r = embed_band(z, edges)
    assert isinstance(r, BandEmbedding)
    assert verify_rows(r.candidates[0].rows, r.candidates[0].n_cols, edges) == []


def test_embedding_is_deterministic():
    z = _zones("abcdefg")
    edges = [("a", "b"), ("a", "c"), ("a", "d"), ("b", "e"), ("c", "f"), ("d", "g"), ("e", "f")]
    r1 = embed_band(z, edges); r2 = embed_band(z, edges)
    assert isinstance(r1, BandEmbedding)
    assert [c.rows for c in r1.candidates] == [c.rows for c in r2.candidates]


def test_invalid_input_is_a_typed_refusal():
    z = _zones("ab")
    r = embed_band(z, [("a", "zz")])
    assert isinstance(r, BandEmbeddingRefusal) and r.code == "INVALID_INPUT"
    r2 = embed_band(z, [("a", "a")])
    assert isinstance(r2, BandEmbeddingRefusal) and r2.code == "INVALID_INPUT"


@pytest.mark.parametrize("n", [3, 5, 7])
def test_search_bound_yields_exhausted_not_impossible(n):
    """A tiny node budget must report EMBEDDING_SEARCH_EXHAUSTED, never a false BAND_UNSAT."""
    ids = [f"r{i}" for i in range(n)]
    z = _zones(ids)
    edges = [(ids[i], ids[i + 1]) for i in range(n - 1)]
    r = embed_band(z, edges, node_limit=1)
    assert isinstance(r, BandEmbeddingRefusal)
    assert r.code == "EMBEDDING_SEARCH_EXHAUSTED" and not r.proof_complete
