"""CLI: scores the frozen generation dataset (`frozen_runner`) and renders the PRIMARY
`docs/reports/llm-topology-poc/results.md` (Issue #151, AC-5 through AC-27).

`--commit-sha`/`--generated-at` are supplied by the caller (obtained via a plain `git log` command)
rather than this module shelling out to git itself — see AC-13's provenance requirement, same
convention as `build_report.py`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

from app.ai_harness.topology_poc import frozen_runner, generation_dataset, primary_report
from app.ai_harness.topology_poc import priors as priors_mod
from app.ai_harness.topology_poc.report import Provenance
from app.ai_harness.topology_poc.result_types import save_checkpoint

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_REPO_ROOT = os.path.dirname(_BACKEND_DIR)
DEFAULT_RESULTS_MD = os.path.join(_REPO_ROOT, "docs", "reports", "llm-topology-poc", "results.md")
DEFAULT_BASELINE_JSON = os.path.join(_REPO_ROOT, "docs", "reports", "llm-topology-poc", "baseline.json")


def _sha256_of(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=generation_dataset.DEFAULT_GENERATION_DATASET_JSON)
    parser.add_argument("--baseline", default=DEFAULT_BASELINE_JSON)
    parser.add_argument("--checkpoint", default=frozen_runner.DEFAULT_PRIMARY_CHECKPOINT_PATH)
    parser.add_argument("--write-report", default=DEFAULT_RESULTS_MD)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--generated-at", required=True)
    args = parser.parse_args(argv)

    dataset = generation_dataset.load_dataset(args.dataset)
    with open(args.baseline, encoding="utf-8") as f:
        baseline = json.load(f)

    results = frozen_runner.run_all_briefs_from_dataset(args.dataset)
    save_checkpoint(args.checkpoint, results)

    p = priors_mod.load_priors()
    provenance = Provenance(
        fullcorpus_json_path=os.path.relpath(p.fullcorpus_json_path, start=_REPO_ROOT),
        room_proportions_json_path=os.path.relpath(p.room_proportions_json_path, start=_REPO_ROOT),
        commit_sha=args.commit_sha, generated_at_utc=args.generated_at,
        train_count=p.train_count, holdout_count=p.holdout_count,
        artifact_sha256=_sha256_of(p.fullcorpus_json_path))

    dataset_meta = {k: v for k, v in dataset.items() if k != "records"}
    text = primary_report.render_results_md(
        results, provenance=provenance, dataset_meta=dataset_meta,
        gate_spec=baseline["primary_go_stop_gate"])

    os.makedirs(os.path.dirname(args.write_report), exist_ok=True)
    with open(args.write_report, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"wrote {args.write_report} from {len(results)} briefs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
