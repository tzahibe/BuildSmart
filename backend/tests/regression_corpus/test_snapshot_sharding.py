"""Issue #67 (O3): `corpus_snapshot.py --shard I/N` / `--merge` shard the gate-4 corpus snapshot
across parallel runner jobs. These tests prove the partition is deterministic, complete and
disjoint (AC-1); `--merge` refuses an unsafe shard set with a message naming the problem (AC-2);
and merging N shards of a small fixture corpus reproduces the same document `--save` would have
produced for the whole corpus, up to volatile timing/writer fields (AC-3). No `regression` marker:
these run in every tier, including gate-3 verification, which runs pytest targets with no
TEST_MODE set.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from spikes.failure_log_sweep import corpus_snapshot as cs
from spikes.failure_log_sweep.sweep import key_of

CORPUS = cs.CORPUS


# ------------------------------------------------------------------ AC-1


def test_shards_are_disjoint_complete_and_stable():
    n = 4
    all_keys = set(cs.sorted_context_keys(CORPUS))
    assert len(all_keys) == 432

    def shard_key_sets():
        return [{key_of(c) for c in cs.shard_contexts(f"{i}/{n}", CORPUS)} for i in range(n)]

    sets_a = shard_key_sets()
    union = set().union(*sets_a)
    assert union == all_keys, "every context key must land in exactly one shard"
    for a in range(n):
        for b in range(a + 1, n):
            assert not (sets_a[a] & sets_a[b]), f"shards {a} and {b} overlap"

    sets_b = shard_key_sets()
    assert sets_a == sets_b, "the same key must always land in the same shard"

    ordered = sorted(all_keys)
    for idx, key in enumerate(ordered):
        assert key in sets_a[idx % n], f"key {key!r} at index {idx} is not in shard {idx % n}"


def test_shard_spec_validation_rejects_out_of_range_or_malformed():
    with pytest.raises(ValueError, match="I/N"):
        cs.parse_shard_spec("garbage")
    with pytest.raises(ValueError):
        cs.parse_shard_spec("4/4")
    with pytest.raises(ValueError):
        cs.parse_shard_spec("-1/4")
    assert cs.parse_shard_spec("0/4") == (0, 4)


# ------------------------------------------------------------------ AC-2


def _shard_doc(results, *, sha="abc123", corpus_hash="hash1", workers=1, seconds=1.0):
    return {"version": 1, "sha": sha, "corpus": str(CORPUS), "corpus_hash": corpus_hash,
            "workers": workers, "seconds": seconds, "written_at": "t", "results": results}


def _disjoint_halves(keys: list[str]) -> tuple[dict, dict]:
    mid = len(keys) // 2
    a = {k: {"status": "PLANNED"} for k in keys[:mid]}
    b = {k: {"status": "PLANNED"} for k in keys[mid:]}
    return a, b


def test_merge_refuses_missing_duplicate_and_mismatched_shards():
    keys = cs.sorted_context_keys(CORPUS)

    # missing shard
    partial = {k: {"status": "PLANNED"} for k in keys[:5]}
    with pytest.raises(cs.ShardMergeError, match="missing shard"):
        cs.merge_shards([_shard_doc(partial)], CORPUS)

    # duplicated key
    full = {k: {"status": "PLANNED"} for k in keys}
    items = list(full.items())
    overlap = len(items) * 3 // 5
    part_a = dict(items[:overlap])
    part_b = dict(items[overlap - 1:])  # one key (index overlap-1) present in both parts
    with pytest.raises(cs.ShardMergeError, match="duplicate context key"):
        cs.merge_shards([_shard_doc(part_a), _shard_doc(part_b)], CORPUS)

    # head_sha mismatch
    part_a, part_b = _disjoint_halves(keys)
    with pytest.raises(cs.ShardMergeError, match="head_sha mismatch"):
        cs.merge_shards([_shard_doc(part_a, sha="sha-A"), _shard_doc(part_b, sha="sha-B")], CORPUS)

    # corpus_hash mismatch
    with pytest.raises(cs.ShardMergeError, match="corpus_hash mismatch"):
        cs.merge_shards(
            [_shard_doc(part_a, corpus_hash="hash-A"), _shard_doc(part_b, corpus_hash="hash-B")], CORPUS,
        )


def test_merge_accepts_a_complete_consistent_shard_set():
    keys = cs.sorted_context_keys(CORPUS)
    part_a, part_b = _disjoint_halves(keys)
    doc = cs.merge_shards([_shard_doc(part_a), _shard_doc(part_b)], CORPUS)
    assert set(doc["results"]) == set(keys)
    assert doc["sha"] == "abc123" and doc["corpus_hash"] == "hash1"
    assert "shard" not in doc  # the merged document has the same shape as a plain --save


# ------------------------------------------------------------------ AC-3


def _fixture_corpus(tmp_path) -> Path:
    real = json.loads(CORPUS.read_text(encoding="utf-8"))
    fixture = {"cases": real["cases"][:9]}
    path = tmp_path / "fixture_corpus.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    return path


def test_merged_shards_equal_single_node_snapshot(tmp_path):
    fixture = _fixture_corpus(tmp_path)

    single = cs.save(tmp_path / "single.json", workers=1, corpus=fixture)

    n = 3
    shard_docs = [
        cs.save(tmp_path / f"shard-{i}.json", workers=1, corpus=fixture, shard=f"{i}/{n}")
        for i in range(n)
    ]
    merged = cs.merge_shards(shard_docs, fixture)

    assert cs.snapshots_equal(merged, single)
    assert cs.normalize_for_compare(merged) == cs.normalize_for_compare(single)
    assert len(merged["results"]) == 9


def test_assert_equal_detects_a_real_difference():
    a = {"sha": "x", "corpus_hash": "h", "workers": 1, "seconds": 1.0, "written_at": "t1",
         "results": {"k": {"status": "PLANNED", "sig": [["a"]], "ms": 5.0}}}
    b = {"sha": "x", "corpus_hash": "h", "workers": 1, "seconds": 2.0, "written_at": "t2",
         "results": {"k": {"status": "PLANNED", "sig": [["a"]], "ms": 9.0}}}
    assert cs.snapshots_equal(a, b) and cs.describe_snapshot_diff(a, b) == []

    b["results"]["k"]["sig"] = [["b"]]
    assert not cs.snapshots_equal(a, b)
    assert any("k:" in d for d in cs.describe_snapshot_diff(a, b))


def test_assert_equal_ignores_missing_corpus_hash_and_worker_count():
    # A single-node snapshot written by an older, pre-sharding script never recorded `corpus_hash`
    # at all — that must be a note, not a snapshot difference (repair, 2026-09-21).
    a = {"sha": "x", "corpus_hash": "h", "workers": 4, "seconds": 1.0, "written_at": "t1",
         "results": {"k": {"status": "PLANNED", "sig": [["a"]], "ms": 5.0}}}
    b = {"sha": "x", "seconds": 2.0, "written_at": "t2",
         "results": {"k": {"status": "PLANNED", "sig": [["a"]], "ms": 9.0}}}
    assert cs.describe_snapshot_diff(a, b) == []
    assert cs.snapshots_equal(a, b)
    assert any("corpus_hash" in n for n in cs.describe_snapshot_notes(a, b))
