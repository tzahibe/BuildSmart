"""CLI: renders the FORCED LOCAL-MODEL CONTROL RUN report,
`docs/reports/llm-topology-poc/results-control-llama.md`, from `runner.py`'s (live-Ollama)
checkpoint (Issue #151, AC-5, AC-6, AC-7, AC-13, AC-17). The PRIMARY run's `results.md` is built by
`build_primary_report.py` instead, from the frozen dataset — never from this module.

`--commit-sha`/`--generated-at` are supplied by the caller (obtained via a plain `git log` command)
rather than this module shelling out to git itself — see AC-13's provenance requirement.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

from app.ai_harness.topology_poc import priors as priors_mod
from app.ai_harness.topology_poc import report as report_mod
from app.ai_harness.topology_poc.runner import DEFAULT_CHECKPOINT_PATH, load_checkpoint

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DEFAULT_RESULTS_MD = os.path.join(
    os.path.dirname(_BACKEND_DIR), "docs", "reports", "llm-topology-poc", "results-control-llama.md")


def _sha256_of(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT_PATH)
    parser.add_argument("--write-report", default=DEFAULT_RESULTS_MD)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--generated-at", required=True)
    args = parser.parse_args(argv)

    results = load_checkpoint(args.checkpoint)
    if not results:
        print(f"no results at {args.checkpoint} — run the runner first", file=sys.stderr)
        return 1

    p = priors_mod.load_priors()
    provenance = report_mod.Provenance(
        fullcorpus_json_path=os.path.relpath(p.fullcorpus_json_path, start=os.path.dirname(_BACKEND_DIR)),
        room_proportions_json_path=os.path.relpath(
            p.room_proportions_json_path, start=os.path.dirname(_BACKEND_DIR)),
        commit_sha=args.commit_sha, generated_at_utc=args.generated_at,
        train_count=p.train_count, holdout_count=p.holdout_count,
        artifact_sha256=_sha256_of(p.fullcorpus_json_path))

    text = report_mod.render_control_results_md(results, provenance)
    os.makedirs(os.path.dirname(args.write_report), exist_ok=True)
    with open(args.write_report, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"wrote {args.write_report} from {len(results)} briefs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
