"""Issue #153 (Concept Engine v2 rollup repair 2/2), AC-4: run the flag-ON path over the frozen
432-context corpus against TODAY's validators (C30 furnishability, C31 public composition, the
professional drawing representation, #141/#149 priors — none of which existed when #130 last ran
this measurement) and report what changes relative to the flag-OFF baseline.

`CONCEPT_ENGINE_V2_ENABLED` only ever changes `run_general`'s ALTERNATIVES (see
`general_pipeline.py`'s own docstring on the flag) — the primary is untouched in either state. So
the only things flag ON can change per context are: (1) an exception the flag-off path never hits,
(2) the primary's own status/code (should never happen — a regression if it does), or (3) which
alternatives are shown. This script records all three, run from `backend/`:

    uv run python -m spikes.failure_log_sweep.concept_engine_v2_flagon_sweep
"""
from __future__ import annotations

import json
import os
import traceback
from collections import Counter
from pathlib import Path

from app.demo.service import DemoGenerationError, generate_demo_design
from app.vertical_slice import general_pipeline as gp
from spikes.failure_log_sweep.sweep import project_from_context

_CORPUS_PATH = Path(__file__).resolve().parents[2] / "tests" / "regression_corpus" / "corpus.json"


def _load_corpus() -> list[dict]:
    with open(_CORPUS_PATH, encoding="utf-8") as f:
        return json.load(f)["cases"]


def _run_one(case: dict, *, flag_on: bool) -> dict:
    gp.CONCEPT_ENGINE_V2_ENABLED = flag_on
    ctx = case["context"]
    try:
        project = project_from_context(ctx)
        result = generate_demo_design(project)
        return {"status": "PLANNED", "code": None,
                "n_alternatives": len(result.alternatives),
                "primary_concept": result.design.concept.circulation_class
                                   if result.design.concept else None}
    except DemoGenerationError as exc:
        return {"status": "REFUSED", "code": exc.code, "n_alternatives": 0, "primary_concept": None}
    except Exception as exc:  # noqa: BLE001 — every crash must be counted, not just the expected ones
        return {"status": "CRASH", "code": f"{type(exc).__name__}: {exc}",
                "n_alternatives": 0, "primary_concept": None,
                "traceback": traceback.format_exc()}
    finally:
        gp.CONCEPT_ENGINE_V2_ENABLED = False


def main() -> None:
    cases = _load_corpus()
    mismatches = []
    crash_reasons: Counter[str] = Counter()
    status_changes = 0
    code_changes = 0
    planned_with_alternatives = 0
    total_planned_on = 0

    for case in cases:
        off = _run_one(case, flag_on=False)
        on = _run_one(case, flag_on=True)

        if on["status"] == "PLANNED":
            total_planned_on += 1
            if on["n_alternatives"] > 0:
                planned_with_alternatives += 1

        if off["status"] != on["status"]:
            status_changes += 1
            mismatches.append({"key": case["source_key"], "kind": "status_change",
                               "off": off["status"], "on": on["status"],
                               "detail": on.get("traceback") or on.get("code")})
        elif off["status"] == "REFUSED" and off["code"] != on["code"]:
            code_changes += 1
            mismatches.append({"key": case["source_key"], "kind": "code_change",
                               "off": off["code"], "on": on["code"]})

        if on["status"] == "CRASH":
            crash_reasons[on["code"]] += 1

    report = {
        "total_contexts": len(cases),
        "planned_on_flag_on": total_planned_on,
        "planned_with_alternatives_flag_on": planned_with_alternatives,
        "status_changes": status_changes,
        "refusal_code_changes": code_changes,
        "crashes": sum(crash_reasons.values()),
        "crash_reasons": dict(crash_reasons),
        "mismatches": mismatches,
    }
    out_path = (Path(__file__).resolve().parents[3] / "docs" / "reports" / "concept-engine-v2" /
               "rollup-repair-2-flagon-sweep.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(json.dumps({k: v for k, v in report.items() if k != "mismatches"}, indent=2))
    print(f"full report written to {out_path}")


if __name__ == "__main__":
    main()
