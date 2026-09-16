"""One-time (re-runnable) authoring script that freezes the real 432-context regression corpus
into tests/regression_corpus/corpus.json.

Why the context dict, not ProgramSpec alone: `app/demo/service.py:generate_demo_design(project)`
calls `spec_for(project)` for the `ArchitecturalSpec`, but *separately* calls `_outlines_for(project)`
(the outline/footprint search) and passes both `spec` AND `project` into
`_plan_outlines_until_one_plans`. `ProgramSpec` alone carries none of the plot/footprint/
street-facing data those steps need, so a `ProgramSpec`-only fixture would silently drop the
outline-selection step the original sweeps exercised. The 10-field context dict already in
`app/data/failures.json` — read by `sweep.py::project_from_context()`'s `NEEDED` tuple — is
*provably* sufficient: `project_from_context` is a total deterministic function of exactly those
10 fields, and `generate_demo_design` is a total deterministic function of the resulting `Project`
alone. No LLM anywhere in this chain.

Run from `backend/`:
    uv run python -m tests.regression_corpus.freeze_corpus
"""

from __future__ import annotations

import dataclasses
import enum
import json
import os

from app.demo.requirements_view import spec_for
from app.demo.service import DemoGenerationError, generate_demo_design
from spikes.failure_log_sweep.sweep import distinct_contexts, key_of, project_from_context

_OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "corpus.json")


def _to_jsonable(obj):
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, (tuple, list)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj


def freeze() -> dict:
    """A REFUSAL (`DemoGenerationError`) is a legitimate, reproducible, deterministic outcome for
    some contexts — matching the historical "404 planned, 28 refused" split — and is frozen as a
    case with `expected_outcome="REFUSED"`, not discarded. Only a genuinely unexpected exception
    (e.g. malformed context data) is recorded as `skipped`."""
    contexts = distinct_contexts()
    cases, skipped = [], []

    for ctx in contexts:
        source_key = key_of(ctx)
        try:
            project = project_from_context(ctx)
        except Exception as e:  # noqa: BLE001 - recording every skip reason is the point
            skipped.append({"source_key": source_key, "reason": f"{type(e).__name__}: {e}"})
            continue

        try:
            generate_demo_design(project)  # the real replay — proves the context alone reproduces a run
            program = _to_jsonable(spec_for(project).program)
            cases.append({"source_key": source_key, "context": ctx, "expected_outcome": "PLANNED",
                          "expected_code": None, "program": program})
        except DemoGenerationError as e:
            cases.append({"source_key": source_key, "context": ctx, "expected_outcome": "REFUSED",
                          "expected_code": e.code, "program": None})
        except Exception as e:  # noqa: BLE001
            skipped.append({"source_key": source_key, "reason": f"{type(e).__name__}: {e}"})

    planned = sum(1 for c in cases if c["expected_outcome"] == "PLANNED")
    refused = sum(1 for c in cases if c["expected_outcome"] == "REFUSED")
    corpus = {
        "version": 1,
        "source": "app/data/failures.json via spikes/failure_log_sweep/sweep.py::distinct_contexts()",
        "source_context_count": len(contexts),
        "frozen_count": len(cases),
        "planned_count": planned,
        "refused_count": refused,
        "skipped_count": len(skipped),
        "cases": cases,
        "skipped": skipped,
    }
    with open(_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(corpus, f, indent=2, ensure_ascii=False)
    return corpus


if __name__ == "__main__":
    result = freeze()
    print(f"source contexts: {result['source_context_count']}")
    print(f"frozen: {result['frozen_count']} (planned: {result['planned_count']}, refused: {result['refused_count']})")
    print(f"skipped: {result['skipped_count']}")
