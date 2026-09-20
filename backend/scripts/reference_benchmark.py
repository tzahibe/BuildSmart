"""Print the reference benchmark report (Issue #32) for one corpus context.

    uv run python scripts/reference_benchmark.py --context 0
    uv run python scripts/reference_benchmark.py --context 0 --list

Run from `backend/`. `--context <id>` is the 0-based index into
`tests/regression_corpus/corpus.json`'s `cases` list (the same 432-context frozen corpus other
tooling in this repo calls "a context") — replayed through `generate_demo_design`, the same
deterministic path `tests/regression_corpus/freeze_quality_baseline.py` uses, then handed to
`app.vertical_slice.reference_benchmark.benchmark()` alongside the curated reference-plan index.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_ROOT.parent
_CORPUS_PATH = _BACKEND_ROOT / "tests" / "regression_corpus" / "corpus.json"
_REFERENCES_PATH = _REPO_ROOT / "docs" / "architecture_reference" / "references" / "index.json"


def _load_corpus_context(context_id: int) -> dict:
    with open(_CORPUS_PATH, encoding="utf-8") as f:
        corpus = json.load(f)
    cases = corpus["cases"]
    if not 0 <= context_id < len(cases):
        raise SystemExit(f"--context {context_id} out of range (corpus has {len(cases)} cases)")
    return cases[context_id]["context"]


def _load_references() -> list[dict]:
    with open(_REFERENCES_PATH, encoding="utf-8") as f:
        return json.load(f)["entries"]


def print_report(context_id: int) -> None:
    from app.demo.service import generate_demo_design
    from app.vertical_slice.reference_benchmark import benchmark
    from spikes.failure_log_sweep.sweep import project_from_context

    context = _load_corpus_context(context_id)
    result = generate_demo_design(project_from_context(context))
    report = benchmark(result.design, _load_references())

    print(f"context {context_id} — footprint family: {report.footprint_family}")
    for section in report.sections:
        status = "measured" if section.measured else "not_measured"
        print(f"  [{section.section}] {section.title} ({status})")
        if section.measured:
            print(f"      value: {section.value}")
            if section.reference_range is not None:
                low, high = section.reference_range
                print(f"      reference_range: {low}-{high}")
            if section.reference_entries:
                print(f"      reference_entries: {', '.join(section.reference_entries)}")
        print(f"      finding: {section.finding}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--context", type=int, required=True,
                    help="0-based index into tests/regression_corpus/corpus.json's cases")
    args = ap.parse_args()
    print_report(args.context)
    return 0


if __name__ == "__main__":
    sys.exit(main())
