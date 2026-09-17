"""One-time (re-runnable) authoring script that computes the M1–M6 corpus summary over the
PLANNED cases of the frozen regression corpus (`corpus.json`) and writes
`tests/regression_corpus/quality_baseline.json` — the committed baseline
`test_quality_baseline.py` checks every future run against.

Why PLANNED cases only, replayed through `generate_demo_design` again rather than trusting
`corpus.json`'s own `program` field: the M1–M6 metrics need the REALIZED geometry (rooms, walls,
doors, open interfaces) `DemoDesign` carries, not the `ArchitecturalSpec.program` `corpus.json`
freezes for the outcome check alone. `project_from_context` + `generate_demo_design` is the same
deterministic replay `test_frozen_context_reproduces_expected_outcome` already relies on.

Run from `backend/`:
    uv run python -m tests.regression_corpus.freeze_quality_baseline
"""
from __future__ import annotations

import json
import os

from app.demo.service import generate_demo_design
from app.vertical_slice.quality_metrics import (
    CIRCULATION_SHARE_TOLERANCE,
    HALL_ASPECT_TOLERANCE,
    PUBLIC_CONTIGUOUS_SHARE_TOLERANCE,
    WET_ADJACENCY_SHARE_TOLERANCE,
    baseline_summary,
    summarize,
)
from spikes.failure_log_sweep.sweep import project_from_context

_CORPUS_PATH = os.path.join(os.path.dirname(__file__), "corpus.json")
_OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "quality_baseline.json")


def freeze() -> dict:
    with open(_CORPUS_PATH, encoding="utf-8") as f:
        corpus = json.load(f)

    designs = []
    for case in corpus["cases"]:
        if case["expected_outcome"] != "PLANNED":
            continue
        project = project_from_context(case["context"])
        result = generate_demo_design(project)
        designs.append(result.design)

    summary = summarize(designs)
    baseline = baseline_summary(summary)
    baseline["source"] = ("tests/regression_corpus/corpus.json PLANNED cases, replayed through "
                          "generate_demo_design (freeze_quality_baseline.py)")
    baseline["tolerance"] = {
        "m3_circulation_share_median": CIRCULATION_SHARE_TOLERANCE,
        "m4_hall_aspect_median": HALL_ASPECT_TOLERANCE,
        "m5_wet_adjacency_share": WET_ADJACENCY_SHARE_TOLERANCE,
        "m6_public_contiguous_share": PUBLIC_CONTIGUOUS_SHARE_TOLERANCE,
    }
    with open(_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(baseline, f, indent=2, ensure_ascii=False)
    return baseline


if __name__ == "__main__":
    result = freeze()
    print(json.dumps(result, indent=2, ensure_ascii=False))
