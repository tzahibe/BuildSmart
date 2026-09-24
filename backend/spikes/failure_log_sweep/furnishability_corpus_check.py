"""One-off measurement for Issue #40 AC-3: replay the frozen 432-context regression corpus
through the REAL service (no changes to search/validation gating — `furnishability.py`'s C30 is
not wired live, see `validation.check_furnishability`'s own docstring), and report:

  1. LOST / status changes against `corpus.json`'s own recorded `expected_outcome`/`expected_code`
     (must be 0/0 for AC-3).
  2. The tier distribution `furnishability.compute_usability` reports on every PLANNED context's
     final delivered design (primary only) — additive disclosure data, reported for the PR per
     Issue #40's own AC-3 requirement, never a gate.

Runs the 432 cases across a `ProcessPoolExecutor` (one process per core) — each case is fully
independent, so this only speeds up the same replay `test_frozen_regression_corpus.py` does one at
a time; it does not change what is measured.

    uv run python spikes/failure_log_sweep/furnishability_corpus_check.py
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.demo.service import DemoGenerationError, generate_demo_design  # noqa: E402
from app.vertical_slice import furnishability  # noqa: E402
from spikes.failure_log_sweep.sweep import project_from_context  # noqa: E402

_CORPUS_PATH = (Path(__file__).resolve().parents[2] / "tests" / "regression_corpus"
               / "corpus.json")


def _process_case(case: dict) -> dict:
    """Runs in a worker process (`ProcessPoolExecutor` below) — the 432-context corpus is CPU-bound
    and embarrassingly parallel (each case is fully independent), so this is a pure speed-up of the
    same replay `test_frozen_regression_corpus.py` does one at a time; it changes nothing about
    what is measured."""
    project = project_from_context(case["context"])
    expected = case["expected_outcome"]
    try:
        result = generate_demo_design(project)
        actual = "PLANNED"
    except DemoGenerationError as exc:
        actual = "REFUSED"
        actual_code = exc.code
    out = {"source_key": case["source_key"], "expected": expected, "actual": actual}
    if actual != expected:
        return out
    if expected == "REFUSED" and actual_code != case["expected_code"]:
        out["expected_code"] = case["expected_code"]
        out["actual_code"] = actual_code
        return out
    if actual == "PLANNED":
        out["tiers"] = [u.tier for u in result.design.quality.usability]
    return out


def main() -> None:
    with open(_CORPUS_PATH, encoding="utf-8") as f:
        corpus = json.load(f)
    cases = corpus["cases"]
    print(f"cases: {len(cases)}")

    lost = []
    status_changed = []
    tier_counts: Counter[str] = Counter()
    room_count = 0
    started = time.perf_counter()
    with ProcessPoolExecutor() as pool:
        for i, out in enumerate(pool.map(_process_case, cases, chunksize=4), start=1):
            expected, actual = out["expected"], out["actual"]
            if actual != expected:
                status_changed.append((out["source_key"], expected, actual))
                if expected == "PLANNED":
                    lost.append(out["source_key"])
            elif "actual_code" in out:
                status_changed.append((out["source_key"], out["expected_code"], out["actual_code"]))
            elif "tiers" in out:
                tier_counts.update(out["tiers"])
                room_count += len(out["tiers"])
            if i % 50 == 0:
                print(f"  {i}/{len(cases)}", flush=True)
    print(f"done in {time.perf_counter() - started:.0f}s")

    print(f"\nLOST: {len(lost)}  status_changed: {len(status_changed)}")
    for key in lost:
        print("  LOST:", key)
    for key, exp, act in status_changed:
        print("  CHANGED:", key, exp, "->", act)

    print(f"\nfurnishability tier distribution over {room_count} rooms "
         f"(primary design of every PLANNED context):")
    for tier in (furnishability.GOOD, furnishability.ACCEPTABLE, furnishability.POOR,
                furnishability.UNUSABLE):
        n = tier_counts.get(tier, 0)
        pct = 100 * n / room_count if room_count else 0.0
        print(f"  {tier:10s} {n:5d}  ({pct:4.1f}%)")


if __name__ == "__main__":
    main()
