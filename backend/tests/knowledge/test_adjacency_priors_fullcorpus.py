"""Issue #149-B.

AC-2: the train/holdout split is deterministic by plan id (order-independent), the prior is built
from TRAIN only, and the "near real" calibration is measured on HOLDOUT only.
AC-4: spatial adjacency (`adjacency`-typed edges) and access (`via_door`/`direct`-typed edges) are
kept strictly separate — never inferred one from the other — and `via_window` edges are excluded
from both.
AC-7: the scanner fails loudly (raises, CLI exits non-zero) on a missing/empty pickle or zero usable
plans — never a silent empty artifact.

Every test builds a tiny synthetic pickle (never the real 17,107-plan corpus, which is an external,
machine-local dataset not part of this repository) so these tests are hermetic and reproducible in
CI.
"""
from __future__ import annotations

import pickle

import networkx as nx
import pytest

from app.knowledge import adjacency_priors_fullcorpus as fc


def _graph(nodes: dict, edges: list) -> nx.Graph:
    g = nx.Graph()
    for node_id, node_type in nodes.items():
        g.add_node(node_id, type=node_type)
    for a, b, edge_type in edges:
        g.add_edge(a, b, type=edge_type)
    return g


def _plan(plan_id, nodes, edges):
    return {"id": plan_id, "graph": _graph(nodes, edges)}


def _write_pickle(path, plans):
    with open(path, "wb") as f:
        pickle.dump(plans, f)


# --------------------------------------------------------------------------- AC-7: fails loudly

def test_raises_on_missing_pickle(tmp_path):
    with pytest.raises(fc.EmptyFullCorpusError):
        fc.load_full_corpus_plans(str(tmp_path / "does-not-exist.pkl"))


def test_raises_on_empty_pickle(tmp_path):
    path = tmp_path / "empty.pkl"
    _write_pickle(path, [])
    with pytest.raises(fc.EmptyFullCorpusError):
        fc.load_full_corpus_plans(str(path))


def test_raises_when_every_plan_has_no_role_rooms(tmp_path):
    """A plan with only a front_door node (no living/kitchen/bedroom/bathroom/balcony) contributes
    zero role data — skipped with a reason, never silently counted as usable."""
    path = tmp_path / "no_rooms.pkl"
    _write_pickle(path, [_plan(0, {"front_door_0": "front_door"}, [])])
    with pytest.raises(fc.EmptyFullCorpusError):
        fc.load_full_corpus_plans(str(path))


def test_cli_exits_non_zero_on_missing_pickle(tmp_path, capsys):
    exit_code = fc.main(["--corpus-pkl", str(tmp_path / "missing.pkl")])
    assert exit_code != 0
    assert "adjacency_priors_fullcorpus" in capsys.readouterr().err


def test_skipped_reason_is_recorded(tmp_path):
    path = tmp_path / "mixed.pkl"
    _write_pickle(path, [
        _plan(0, {"front_door_0": "front_door"}, []),
        _plan(1, {"living_0": "living", "kitchen_0": "kitchen"},
              [("living_0", "kitchen_0", "adjacency")]),
    ])
    plans, total_loaded, skipped = fc.load_full_corpus_plans(str(path))
    assert total_loaded == 2
    assert len(plans) == 1
    assert skipped == {"no_role_rooms": 1}


# --------------------------------------------------------------------------- AC-2: train/holdout

def test_split_is_deterministic_and_order_independent():
    ids = [str(i) for i in range(50)]
    first = {i: fc._split_for(i) for i in ids}
    second = {i: fc._split_for(i) for i in reversed(ids)}
    assert first == second
    assert set(first.values()) <= {"TRAIN", "HOLDOUT"}


def test_split_is_a_function_of_plan_id_not_list_position(tmp_path):
    """The same plan id lands in the same split bucket regardless of where in the pickle list it
    sits — proves the split cannot depend on corpus ordering (AC-2)."""
    plan_a = _plan(12345, {"living_0": "living", "kitchen_0": "kitchen"},
                   [("living_0", "kitchen_0", "adjacency")])
    plan_b = _plan(99999, {"living_0": "living", "kitchen_0": "kitchen"},
                   [("living_0", "kitchen_0", "adjacency")])
    path_forward = tmp_path / "forward.pkl"
    path_reversed = tmp_path / "reversed.pkl"
    _write_pickle(path_forward, [plan_a, plan_b])
    _write_pickle(path_reversed, [plan_b, plan_a])
    forward, _, _ = fc.load_full_corpus_plans(str(path_forward))
    backward, _, _ = fc.load_full_corpus_plans(str(path_reversed))
    forward_splits = {p.plan_id: p.split for p in forward}
    backward_splits = {p.plan_id: p.split for p in backward}
    assert forward_splits == backward_splits


def test_build_report_raises_when_train_split_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(fc, "_split_for", lambda plan_id: "HOLDOUT")
    path = tmp_path / "all_holdout.pkl"
    _write_pickle(path, [
        _plan(0, {"living_0": "living", "kitchen_0": "kitchen"},
              [("living_0", "kitchen_0", "adjacency")]),
    ])
    with pytest.raises(fc.EmptyFullCorpusError):
        fc.build_report(str(path))


def test_build_report_raises_when_holdout_split_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(fc, "_split_for", lambda plan_id: "TRAIN")
    path = tmp_path / "all_train.pkl"
    _write_pickle(path, [
        _plan(0, {"living_0": "living", "kitchen_0": "kitchen"},
              [("living_0", "kitchen_0", "adjacency")]),
    ])
    with pytest.raises(fc.EmptyFullCorpusError):
        fc.build_report(str(path))


def test_prior_is_built_from_train_only(tmp_path, monkeypatch):
    """A HOLDOUT-only plan's own adjacency pattern must never contribute to the TRAIN-built rows —
    proven by making TRAIN and HOLDOUT disagree and checking only TRAIN's pattern survives."""
    splits = {0: "TRAIN", 1: "HOLDOUT"}
    monkeypatch.setattr(fc, "_split_for", lambda plan_id: splits[plan_id])
    path = tmp_path / "corpus.pkl"
    _write_pickle(path, [
        _plan(0, {"living_0": "living", "bedroom_0": "bedroom"},
              [("living_0", "bedroom_0", "adjacency")]),
        _plan(1, {"living_0": "living", "bedroom_0": "bedroom"}, []),  # HOLDOUT, NOT adjacent
    ])
    plans, _, _ = fc.load_full_corpus_plans(str(path))
    train = [p for p in plans if p.split == "TRAIN"]
    spatial_rows, _ = fc.compute_pair_rows(train, "touching_without_door_pairs")
    row = fc.row_for(spatial_rows, "BEDROOM", "LIVING")
    assert row is not None
    assert row.sample_count == 1  # only the TRAIN plan
    assert row.positive_count == 1


# --------------------------------------------------------------------------- AC-4: adjacency != access

def test_spatial_and_access_are_measured_from_disjoint_edge_types(tmp_path, monkeypatch):
    monkeypatch.setattr(fc, "_split_for", lambda plan_id: "TRAIN")
    path = tmp_path / "corpus.pkl"
    _write_pickle(path, [
        _plan(0, {"living_0": "living", "bedroom_0": "bedroom"},
              [("living_0", "bedroom_0", "adjacency")]),
        _plan(1, {"living_0": "living", "bathroom_0": "bathroom"},
              [("living_0", "bathroom_0", "via_door")]),
    ])
    plans, _, _ = fc.load_full_corpus_plans(str(path))
    spatial_rows, _ = fc.compute_pair_rows(plans, "touching_without_door_pairs")
    access_rows, _ = fc.compute_pair_rows(plans, "access_pairs")

    bedroom_living_spatial = fc.row_for(spatial_rows, "BEDROOM", "LIVING")
    bedroom_living_access = fc.row_for(access_rows, "BEDROOM", "LIVING")
    assert bedroom_living_spatial.positive_count == 1
    assert bedroom_living_access.positive_count == 0  # never inferred from spatial adjacency

    bathroom_living_spatial = fc.row_for(spatial_rows, "BATHROOM", "LIVING")
    bathroom_living_access = fc.row_for(access_rows, "BATHROOM", "LIVING")
    assert bathroom_living_spatial.positive_count == 0  # a via_door edge is NOT an adjacency edge
    assert bathroom_living_access.positive_count == 1


def test_via_window_edges_excluded_from_both_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(fc, "_split_for", lambda plan_id: "TRAIN")
    path = tmp_path / "corpus.pkl"
    _write_pickle(path, [
        _plan(0, {"bedroom_0": "bedroom", "balcony_0": "balcony"},
              [("bedroom_0", "balcony_0", "via_window")]),
    ])
    plans, _, _ = fc.load_full_corpus_plans(str(path))
    spatial_rows, _ = fc.compute_pair_rows(plans, "touching_without_door_pairs")
    access_rows, _ = fc.compute_pair_rows(plans, "access_pairs")
    spatial_row = fc.row_for(spatial_rows, "BALCONY", "BEDROOM")
    access_row = fc.row_for(access_rows, "BALCONY", "BEDROOM")
    assert spatial_row.positive_count == 0
    assert access_row.positive_count == 0


# --------------------------------------------------------------------------- Table C: spatial touching (UNION)

def test_spatial_touching_is_union_of_adjacency_and_via_door_only(tmp_path, monkeypatch):
    """Table C = adjacency pairs UNION via_door pairs, per plan — never `direct` (front-door-to-room,
    not room-to-room), and section A/B stay untouched by this union."""
    monkeypatch.setattr(fc, "_split_for", lambda plan_id: "TRAIN")
    path = tmp_path / "corpus.pkl"
    _write_pickle(path, [
        _plan(0, {"living_0": "living", "bedroom_0": "bedroom"},
              [("living_0", "bedroom_0", "adjacency")]),
        _plan(1, {"living_0": "living", "bathroom_0": "bathroom"},
              [("living_0", "bathroom_0", "via_door")]),
        _plan(2, {"front_door_0": "front_door", "living_0": "living"},
              [("front_door_0", "living_0", "direct")]),
    ])
    plans, _, _ = fc.load_full_corpus_plans(str(path))
    spatial_rows, _ = fc.compute_pair_rows(plans, "touching_without_door_pairs")
    touching_rows, _ = fc.compute_pair_rows(plans, "spatial_touching_pairs")

    # BEDROOM-LIVING: adjacency edge -> touching in both A and C
    assert fc.row_for(spatial_rows, "BEDROOM", "LIVING").positive_count == 1
    assert fc.row_for(touching_rows, "BEDROOM", "LIVING").positive_count == 1

    # BATHROOM-LIVING: via_door only -> NOT touching in A, IS touching in C (the repair)
    assert fc.row_for(spatial_rows, "BATHROOM", "LIVING").positive_count == 0
    assert fc.row_for(touching_rows, "BATHROOM", "LIVING").positive_count == 1

    # `direct` (front door) never contributes to spatial_touching_pairs — no role-pair to test
    # directly, but plan 2's front_door<->living edge must not create any role-pair row at all
    # since front_door isn't a role; nothing to assert beyond the two rows above existing cleanly.


def test_spatial_touching_holdout_calibration_uses_its_own_pattern(tmp_path, monkeypatch):
    """The touching-table holdout calibration is measured on each HOLDOUT plan's own
    `spatial_touching_pairs` pattern against TRAIN's touching rows — not the adjacency-only one."""
    monkeypatch.setattr(fc, "_split_for", lambda plan_id: "TRAIN" if plan_id % 2 == 0 else "HOLDOUT")
    path = tmp_path / "corpus.pkl"
    plans = []
    for i in range(20):
        plans.append(_plan(i, {"living_0": "living", "bathroom_0": "bathroom"},
                           [("living_0", "bathroom_0", "via_door")]))
    _write_pickle(path, plans)
    report = fc.build_report(str(path))
    # via_door-only pattern: BATHROOM-LIVING never counts as adjacent in Table A -> no supported
    # eligible pair -> no HOLDOUT plan scorable under section A would be the naive expectation, but
    # section A still has a row (positive_count=0, meets_min_support True) so it IS scorable; the
    # touching table instead sees it as always-positive.
    assert report.touching_holdout_scored_count > 0
    touching_row = fc.row_for(report.touching_rows, "BATHROOM", "LIVING")
    assert touching_row.positive_count == touching_row.sample_count  # always touching under Table C
    spatial_row = fc.row_for(report.spatial_rows, "BATHROOM", "LIVING")
    assert spatial_row.positive_count == 0  # never adjacency-typed under Table A


def test_headline_pairs_missing_from_corpus_vocabulary_are_unmeasurable():
    """MASTER/ENSUITE/DINING/CIRCULATION are not ResPlan node types — the report must mark them
    UNMEASURABLE rather than silently omitting or fabricating a value."""
    for role_a, role_b in fc.HEADLINE_PAIRS:
        if role_a not in fc._ROLE_BY_NODE_TYPE.values() or role_b not in fc._ROLE_BY_NODE_TYPE.values():
            text = fc._headline_row_text((), role_a, role_b, "spatial")
            assert "UNMEASURABLE" in text


# --------------------------------------------------------------------------- CLI end-to-end

def test_cli_writes_json_and_report_on_a_real_minimal_corpus(tmp_path, monkeypatch):
    monkeypatch.setattr(fc, "_split_for", lambda plan_id: "TRAIN" if plan_id % 2 == 0 else "HOLDOUT")
    path = tmp_path / "corpus.pkl"
    plans = []
    for i in range(20):
        plans.append(_plan(i, {"living_0": "living", "bedroom_0": "bedroom"},
                           [("living_0", "bedroom_0", "adjacency")]))
    _write_pickle(path, plans)
    json_out = tmp_path / "out.json"
    report_out = tmp_path / "out.md"
    exit_code = fc.main(["--corpus-pkl", str(path), "--write-json", str(json_out),
                        "--write-report", str(report_out)])
    assert exit_code == 0
    assert json_out.exists()
    assert report_out.exists()
    assert "holdout" in report_out.read_text().lower()
