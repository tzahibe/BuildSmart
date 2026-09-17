"""Cross-commit primary-signature gate over the frozen, committed regression corpus.

`snapshot.py` does the same job over the gitignored production log (`app/data/failures.json`);
this sibling reads `tests/regression_corpus/corpus.json` (the same 432 contexts, frozen in git)
so the gate can run in CI and in a fresh validation worktree. It reuses `project_from_context`,
`signature` and `generate_demo_design` unchanged — same replay, same signature, machine-readable
output on top.

    .venv/bin/python3 spikes/failure_log_sweep/corpus_snapshot.py --save before.json [--workers 4]
    ...change the code...
    .venv/bin/python3 spikes/failure_log_sweep/corpus_snapshot.py --save after.json
    .venv/bin/python3 spikes/failure_log_sweep/corpus_snapshot.py --compare before.json after.json \\
        --report regression_report.json

The report is what `scripts/agent_team/regression_budget.py` evaluates:

    before/after planned, refused, crashes · LOST · GAINED · new crashes · status changes
    (REFUSED<->CRASH) · refusal-code changes · primary-signature changes, each with the context.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

CORPUS = Path(__file__).resolve().parents[2] / "tests" / "regression_corpus" / "corpus.json"


def corpus_contexts(path: Path = CORPUS) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [case["context"] for case in data["cases"]]


def _run_one(ctx: dict) -> tuple[str, dict]:
    # Imported inside the worker so `--workers N` forks cleanly and the import cost is per process.
    from app.demo import service as svc  # noqa: WPS433
    from spikes.failure_log_sweep.sweep import key_of, project_from_context, signature  # noqa: WPS433

    key = key_of(ctx)
    t0 = time.perf_counter()
    try:
        res = svc.generate_demo_design(project_from_context(ctx))
        out = {"status": "PLANNED", "sig": [list(s) for s in signature(res.design)], "area": res.design.gross_area_m2}
    except svc.DemoGenerationError as exc:
        out = {"status": "REFUSED", "code": exc.code + ("+outline" if "כן מתאפשר" in exc.message else "")}
    except Exception as exc:  # noqa: BLE001 — a crash is a result, not an abort
        out = {"status": "CRASH", "code": f"{type(exc).__name__}: {exc}"}
    out["ms"] = round((time.perf_counter() - t0) * 1000, 1)
    out["context"] = {k: ctx[k] for k in ("plot_width_m", "plot_depth_m", "street_facing_side", "built_area_m2",
                                          "footprint_width_m", "footprint_depth_m", "bedrooms", "wet_rooms",
                                          "safe_room", "open_plan")}
    return key, out


def run_all(workers: int = 1, corpus: Path = CORPUS) -> dict:
    contexts = corpus_contexts(corpus)
    if workers <= 1:
        results = [_run_one(c) for c in contexts]
    else:
        with mp.get_context("fork").Pool(workers) as pool:
            results = pool.map(_run_one, contexts, chunksize=4)
    return dict(sorted(results))


def _git_sha() -> str | None:
    try:
        import subprocess
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True,
                              cwd=str(Path(__file__).resolve().parents[2])).stdout.strip()
    except Exception:  # noqa: BLE001
        return None


def save(path: Path, workers: int, corpus: Path = CORPUS) -> dict:
    t0 = time.time()
    results = run_all(workers, corpus)
    doc = {"version": 1, "sha": _git_sha(), "corpus": str(corpus), "workers": workers,
           "seconds": round(time.time() - t0, 1), "results": results}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    return doc


def _status_counts(results: dict) -> dict:
    c = Counter(v["status"] for v in results.values())
    return {"planned": c.get("PLANNED", 0), "refused": c.get("REFUSED", 0), "crashes": c.get("CRASH", 0), "total": len(results)}


def compare(before_doc: dict, after_doc: dict) -> dict:
    before, after = before_doc["results"], after_doc["results"]
    keys = sorted(set(before) | set(after))
    lost, gained, new_crashes, status_changes, code_changes, sig_changes = [], [], [], [], [], []
    for k in keys:
        b, a = before.get(k), after.get(k)
        if b is None or a is None:
            status_changes.append({"key": k, "context": (a or b)["context"], "before": b and b["status"], "after": a and a["status"],
                                   "note": "context present on one side only"})
            continue
        row = {"key": k, "context": a["context"], "before": b["status"], "after": a["status"]}
        if b["status"] == "PLANNED" and a["status"] != "PLANNED":
            lost.append({**row, "after_code": a.get("code")})
        elif b["status"] != "PLANNED" and a["status"] == "PLANNED":
            gained.append({**row, "area": a.get("area"), "asked": a["context"]["built_area_m2"]})
        elif b["status"] != a["status"]:
            status_changes.append(row)
        elif b["status"] == "REFUSED" and b.get("code") != a.get("code"):
            code_changes.append({**row, "before_code": b.get("code"), "after_code": a.get("code")})
        elif b["status"] == "PLANNED" and b["sig"] != a["sig"]:
            sig_changes.append({**row, "before_area": b.get("area"), "after_area": a.get("area")})
        if a["status"] == "CRASH" and b["status"] != "CRASH":
            new_crashes.append({**row, "error": a.get("code")})
    return {
        "version": 1,
        "base_sha": before_doc.get("sha"), "head_sha": after_doc.get("sha"),
        "before": _status_counts(before), "after": _status_counts(after),
        "lost": lost, "gained": gained, "crashes": new_crashes, "status_changes": status_changes,
        "refusal_code_changes": code_changes, "primary_signature_changes": sig_changes,
        "byte_identical_primaries": sum(1 for k in keys if k in before and k in after and before[k]["status"] == "PLANNED"
                                        and after[k]["status"] == "PLANNED" and before[k]["sig"] == after[k]["sig"]),
        "refusal_codes": {
            "before": dict(Counter(v.get("code") for v in before.values() if v["status"] == "REFUSED")),
            "after": dict(Counter(v.get("code") for v in after.values() if v["status"] == "REFUSED")),
        },
        "timing": {"before_seconds": before_doc.get("seconds"), "after_seconds": after_doc.get("seconds"),
                   "median_ms_before": _median([v["ms"] for v in before.values() if "ms" in v]),
                   "median_ms_after": _median([v["ms"] for v in after.values() if "ms" in v])},
    }


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def summarize(report: dict) -> str:
    b, a = report["before"], report["after"]
    lines = [
        f"planned before={b['planned']} after={a['planned']}   refused before={b['refused']} after={a['refused']}"
        f"   crashes before={b['crashes']} after={a['crashes']}",
        f"LOST={len(report['lost'])}  GAINED={len(report['gained'])}  new crashes={len(report['crashes'])}"
        f"  status changes={len(report['status_changes'])}  refusal-code changes={len(report['refusal_code_changes'])}"
        f"  primary-signature changes={len(report['primary_signature_changes'])}"
        f"  byte-identical primaries={report['byte_identical_primaries']}",
    ]
    for row in report["lost"]:
        lines.append(f"  LOST {row['context']} -> {row['after']} {row.get('after_code')}")
    for row in report["gained"]:
        pct = 100 * row["area"] / row["asked"] if row.get("area") and row.get("asked") else 0
        lines.append(f"  GAINED {row['context']} built {row.get('area')} ({pct:.0f}% of asked)")
    for row in report["crashes"]:
        lines.append(f"  CRASH {row['context']} {row.get('error')}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--save", metavar="OUT.json")
    g.add_argument("--compare", nargs=2, metavar=("BEFORE.json", "AFTER.json"))
    ap.add_argument("--report", metavar="REPORT.json", help="with --compare: write the machine-readable report here")
    ap.add_argument("--workers", type=int, default=max(1, min(4, (os.cpu_count() or 2) // 2)))
    ap.add_argument("--corpus", type=Path, default=CORPUS)
    args = ap.parse_args()
    if args.save:
        doc = save(Path(args.save), args.workers, args.corpus)
        counts = _status_counts(doc["results"])
        print(f"saved {counts['total']} scenarios: planned {counts['planned']} refused {counts['refused']} "
              f"crashes {counts['crashes']} in {doc['seconds']}s ({args.workers} workers)")
        return 0
    before = json.load(open(args.compare[0], encoding="utf-8"))
    after = json.load(open(args.compare[1], encoding="utf-8"))
    report = compare(before, after)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=1, ensure_ascii=False)
    print(summarize(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
