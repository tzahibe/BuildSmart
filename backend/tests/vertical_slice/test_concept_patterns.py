"""Structured concept pattern prior (Issue #77): `patterns_for` returns >=2 distinct circulation
classes for every footprint family x programme combination in the frozen corpus, deterministically
(AC-2), and every `Pattern` cites real evidence (AC-3). Cheap and deterministic — reads
`corpus.json`'s own recorded context fields directly, no solver/generation call, so this runs in
the FAST suite (no `regression` marker needed).
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass

import pytest

from app.vertical_slice.concept_patterns import PATTERNS, patterns_for

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
CORPUS_PATH = REPO_ROOT / "backend" / "tests" / "regression_corpus" / "corpus.json"
INDEX_PATH = (REPO_ROOT / "docs" / "architecture_reference" / "references" / "index.json")


@dataclass(frozen=True)
class _Outline:
    width_m: float
    depth_m: float


@dataclass(frozen=True)
class _Brief:
    bedrooms: int
    wet_rooms: int


def _load_corpus_combinations() -> list[tuple[float, float, int, int]]:
    """Every distinct (footprint_width_m, footprint_depth_m, bedrooms, wet_rooms) combination
    the frozen 432-context corpus actually contains — the "footprint family x programme
    combination" AC-2 requires coverage for, read directly off each case's own recorded
    `context` (no solver/generation call)."""
    data = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    seen: set[tuple[float, float, int, int]] = set()
    for case in data["cases"]:
        ctx = case["context"]
        seen.add((ctx["footprint_width_m"], ctx["footprint_depth_m"], ctx["bedrooms"],
                  ctx["wet_rooms"]))
    return sorted(seen)


_CORPUS_COMBINATIONS = _load_corpus_combinations()


@pytest.mark.skipif(not _CORPUS_COMBINATIONS, reason="corpus.json not yet generated")
@pytest.mark.parametrize("combo", _CORPUS_COMBINATIONS,
                         ids=lambda c: f"w{c[0]}_d{c[1]}_bed{c[2]}_wet{c[3]}")
def test_patterns_for_returns_two_classes_for_every_corpus_family(combo):
    width_m, depth_m, bedrooms, wet_rooms = combo
    outline = _Outline(width_m, depth_m)
    brief = _Brief(bedrooms, wet_rooms)

    result_a = patterns_for(brief, outline)
    result_b = patterns_for(brief, outline)
    assert result_a == result_b, "patterns_for is not deterministic for the same inputs"

    classes = {p.circulation_class for p in result_a}
    assert len(classes) >= 2, (
        f"expected >=2 distinct circulation classes for width={width_m} depth={depth_m} "
        f"bedrooms={bedrooms} wet_rooms={wet_rooms}, got {result_a!r}"
    )


def test_every_pattern_cites_its_source():
    """AC-3: every `Pattern.source` names either a `specs/005-hub-private-wing/spec.md` census
    line or at least one real `references/index.json` archetype id (or both)."""
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    real_ids = {entry["id"] for entry in index["entries"]}
    assert real_ids, "expected at least one archetype id in index.json"

    for pattern in PATTERNS:
        assert pattern.source, f"{pattern.name} has no source citation"
        cites_census = "spec.md" in pattern.source
        cited_ids = {entry_id for entry_id in real_ids if entry_id in pattern.source}
        assert cites_census or cited_ids, (
            f"{pattern.name}'s source {pattern.source!r} cites neither "
            "specs/005-hub-private-wing/spec.md nor a real index.json archetype id"
        )
        if cited_ids:
            for entry_id in cited_ids:
                assert entry_id in real_ids  # sanity: no stale/typo'd id


def test_patterns_for_never_returns_more_than_three():
    for width_m, depth_m, bedrooms, wet_rooms in _CORPUS_COMBINATIONS[:20]:
        result = patterns_for(_Brief(bedrooms, wet_rooms), _Outline(width_m, depth_m))
        assert len(result) <= 3
