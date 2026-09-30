"""Issue #155, AC-1 — deterministic selection of 8 briefs from the frozen 432-context regression
corpus (`tests/regression_corpus/corpus.json`), by a stable hash of each context's own
`source_key` (a canonical JSON string of the context's numeric fields — unique across all 404
PLANNED cases, measured; see `tests/regression_corpus/freeze_corpus.py`).

Only PLANNED cases with 2-5 bedrooms are eligible (the Issue's own required spread). 6 buckets —
{SMALL, MEDIUM, LARGE} built-area terciles x {with, without SAFE_ROOM} — each contribute exactly
one brief (the candidate with the LOWEST stable hash in that bucket), guaranteeing the size and
SAFE_ROOM spread by construction. Two more slots (NARROW, then WIDE plot) fill the same way,
guaranteeing at least one narrow and one wide plot. The only cherry-picked part is the FIXED bucket
list below — which case wins each bucket is always the lowest stable hash, never chosen by content.

Re-running `select_briefs` against the same (byte-identical, frozen) corpus always returns the
same 8 ids — proven by `tests/vertical_slice/test_two_path_demo_selection.py`. The committed ids
themselves live in `docs/reports/two-path-demo/selected_briefs.json`.
"""
from __future__ import annotations

import hashlib
import json
import os

_CORPUS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "tests", "regression_corpus", "corpus.json")

_REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))), "docs", "reports", "two-path-demo")
COMMITTED_BRIEFS_PATH = os.path.join(_REPORT_DIR, "selected_briefs.json")

#: 6 buckets guarantee small/medium/large x with/without SAFE_ROOM spread; 2 more slots guarantee
#: at least one narrow and one wide plot. Order is fixed so re-runs are reproducible.
_SIZE_SAFE_BUCKETS: tuple[tuple[str, bool], ...] = (
    ("SMALL", True), ("SMALL", False),
    ("MEDIUM", True), ("MEDIUM", False),
    ("LARGE", True), ("LARGE", False),
)
_PLOT_SLOTS = ("NARROW", "WIDE")

#: plot_width_m / plot_depth_m thresholds — measured against the corpus's own 2-5 bedroom PLANNED
#: pool (min ratio 0.557, max 1.333): 0.8/1.2 leaves a genuinely "narrow"/"wide" tail on each side
#: (161/33 candidates respectively out of 302), not merely the plot furthest from square.
NARROW_MAX_RATIO = 0.8
WIDE_MIN_RATIO = 1.2

MIN_BEDROOMS = 2
MAX_BEDROOMS = 5


def stable_hash(source_key: str) -> int:
    """A deterministic, content-derived integer for `source_key` — sha256, not Python's own
    salted `hash()` (which varies run to run by design)."""
    return int(hashlib.sha256(source_key.encode("utf-8")).hexdigest(), 16)


def load_corpus() -> dict:
    with open(_CORPUS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _eligible_pool(corpus: dict) -> list[dict]:
    planned = [c for c in corpus["cases"] if c["expected_outcome"] == "PLANNED"]
    return [c for c in planned if MIN_BEDROOMS <= c["context"]["bedrooms"] <= MAX_BEDROOMS]


def _size_tier(built_area_m2: float, p33: float, p66: float) -> str:
    if built_area_m2 <= p33:
        return "SMALL"
    if built_area_m2 <= p66:
        return "MEDIUM"
    return "LARGE"


def _plot_ratio(ctx: dict) -> float:
    return ctx["plot_width_m"] / ctx["plot_depth_m"]


def select_briefs(corpus: dict) -> list[str]:
    """Returns 8 `source_key` ids. Deterministic in the corpus alone — no randomness, no wall
    clock, no environment dependence."""
    pool = _eligible_pool(corpus)
    areas = sorted(c["context"]["built_area_m2"] for c in pool)
    n = len(areas)
    p33, p66 = areas[n // 3], areas[(2 * n) // 3]

    selected: list[str] = []
    selected_set: set[str] = set()

    def _pick(predicate) -> None:
        candidates = [c for c in pool
                      if c["source_key"] not in selected_set and predicate(c["context"])]
        if not candidates:
            return
        winner = min(candidates, key=lambda c: stable_hash(c["source_key"]))
        selected.append(winner["source_key"])
        selected_set.add(winner["source_key"])

    for size_tier, safe_room in _SIZE_SAFE_BUCKETS:
        _pick(lambda ctx, size_tier=size_tier, safe_room=safe_room:
              _size_tier(ctx["built_area_m2"], p33, p66) == size_tier
              and ctx["safe_room"] == safe_room)

    for slot in _PLOT_SLOTS:
        if slot == "NARROW":
            _pick(lambda ctx: _plot_ratio(ctx) <= NARROW_MAX_RATIO)
        else:
            _pick(lambda ctx: _plot_ratio(ctx) >= WIDE_MIN_RATIO)

    if len(selected) != 8:
        raise RuntimeError(
            f"selection produced {len(selected)} briefs, expected 8 — the corpus's own "
            f"composition no longer supports every bucket this algorithm requires")
    return selected


def load_committed_briefs() -> list[str]:
    with open(COMMITTED_BRIEFS_PATH, encoding="utf-8") as f:
        return json.load(f)["brief_ids"]
