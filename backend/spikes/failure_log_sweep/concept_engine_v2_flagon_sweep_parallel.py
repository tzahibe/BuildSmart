"""Parallel variant of `concept_engine_v2_flagon_sweep.py` (Issue #153, AC-4) — same measurement,
`ProcessPoolExecutor`-parallelised across contexts so the 432-context x2 (flag off/on) sweep
finishes in practical time. Run from `backend/`:

    uv run python -m spikes.failure_log_sweep.concept_engine_v2_flagon_sweep_parallel
"""
from __future__ import annotations

import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from spikes.failure_log_sweep.concept_engine_v2_flagon_sweep import _load_corpus, _run_one


def _run_both(case: dict) -> tuple[dict, dict]:
    off = _run_one(case, flag_on=False)
    on = _run_one(case, flag_on=True)
    return off, on


def main() -> None:
    cases = _load_corpus()
    mismatches = []
    crash_reasons: Counter[str] = Counter()
    status_changes = 0
    code_changes = 0
    planned_with_alternatives = 0
    total_planned_on = 0

    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_run_both, case): case for case in cases}
        done = 0
        for fut in as_completed(futures):
            case = futures[fut]
            off, on = fut.result()
            done += 1
            if done % 50 == 0:
                print(f"{done}/{len(cases)} done", flush=True)

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
