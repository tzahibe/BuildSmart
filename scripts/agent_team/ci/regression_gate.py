"""GATE 4 — regression budget over the frozen corpus.

Inputs: the base and head snapshots written by `backend/spikes/failure_log_sweep/corpus_snapshot.py
--save`, and the manifest (its `regression_budget`). Produces `regression_report.json` (the full
before/after/LOST/GAINED/... document) and fails when any budget rule is violated.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from agent_team.ci.common import GateReport, repo_root, write_report
from agent_team.issue_contract import parse_budget_value
from agent_team.regression_budget import evaluate as evaluate_budget


def compare_snapshots(before: dict, after: dict, root: Path) -> dict:
    sys.path.insert(0, str(root / "backend"))
    from spikes.failure_log_sweep.corpus_snapshot import compare  # noqa: WPS433
    return compare(before, after)


def evaluate(report: dict, budget_spec: dict) -> GateReport:
    rep = GateReport("gate-4-regression")
    rules = tuple(parse_budget_value(k, v) for k, v in budget_spec.items())
    ev = evaluate_budget(report, rules)
    b, a = report["before"], report["after"]
    rep.add("corpus replayed", a.get("total", 0) > 0, f"{a.get('total', 0)} contexts")
    rep.add("before planned/refused/crashes", True, f"{b['planned']}/{b['refused']}/{b['crashes']}")
    rep.add("after planned/refused/crashes", True, f"{a['planned']}/{a['refused']}/{a['crashes']}")
    for key, count in ev.counts.items():
        rule = budget_spec.get(key, "0" if key != "GAINED" else "allowed")
        violated = any(v.key == key for v in ev.violations)
        detail = f"observed {count}, budget {rule}"
        if violated:
            detail += " — " + next(v.detail for v in ev.violations if v.key == key)
        rep.add(f"budget {key}", not violated, detail)
    rep.add("byte-identical primaries", True, str(report.get("byte_identical_primaries")))
    rep.extra["budget_ok"] = ev.ok
    rep.extra["counts"] = ev.counts
    rep.extra["base_sha"] = report.get("base_sha")
    rep.extra["head_sha"] = report.get("head_sha")
    if not ev.ok:
        rep.ok = False
    return rep


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--report", default=None)
    args = ap.parse_args()
    root = repo_root()
    before = json.loads(Path(args.before).read_text(encoding="utf-8"))
    after = json.loads(Path(args.after).read_text(encoding="utf-8"))
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    report = compare_snapshots(before, after, root)
    out = Path(args.report) if args.report else root / ".agent" / "ci" / "regression_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    rep = evaluate(report, manifest.get("regression_budget", {}))
    write_report(rep, root / ".agent" / "ci" / "regression_gate_report.json")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
