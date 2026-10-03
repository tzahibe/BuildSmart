"""Concept Engine v2 (3/5) adaptation report — Issue #76.

    .venv/bin/python3 spikes/failure_log_sweep/concept_adaptation_report.py

For every PLANNED case in the frozen 432-context regression corpus (`tests/regression_corpus/
corpus.json`), replays the request and looks at the FIRST candidate `general_pipeline._realize`
built for that brief (generator order, before ranking/selection ever runs — `concept_score`'s own
"first realization") and classifies it, per circulation class:

    accepted    `concept_score` does not reject it (the plan validated and passed safety):
                nothing to adapt.
    adapted     the first realization needed a move (`concept_score.adapt`) that names a target
                `ConceptSpec`, AND another candidate this SAME brief's generator already realized
                (recorded the same way) already matches it — the delta between the two `concept_
                score` totals is reported. Never a new solve: this measures whether the ladder
                would have found something worth trying among what the generator already tried,
                not whether a brand-new geometry could be synthesized (out of scope for a
                metadata-only Issue — see `concept_score.py`'s own module docstring).
    dropped     `adapt` returned `None` (no applicable move, or the plan failed C24/C19), or no
                matching sibling was ever realized for this brief.

Metadata only — see Issue #76, item 4: no runtime behavior change, nothing wired into
`run_general`. Writes `docs/reports/concept-engine-v2-adaptation-report.md`.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.demo import service as svc  # noqa: E402
from app.vertical_slice import concept_spec  # noqa: E402
from app.vertical_slice import general_pipeline as gp  # noqa: E402
from app.vertical_slice.concept_score import adapt, concept_score  # noqa: E402
from spikes.failure_log_sweep.sweep import project_from_context  # noqa: E402

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_DIR.parent
_CORPUS_PATH = _BACKEND_DIR / "tests" / "regression_corpus" / "corpus.json"
_REPORT_PATH = _REPO_ROOT / "docs" / "reports" / "concept-engine-v2-adaptation-report.md"
#: Default resume file for `--start`/`--end` chunked runs (each full 404-brief pass costs one
#: `svc.generate_demo_design` call per brief — several minutes; chunking lets one run resume from
#: where the last one left off instead of replaying the whole corpus every time).
_RESUME_PATH = _BACKEND_DIR / "spikes" / "failure_log_sweep" / "_concept_adaptation_resume.json"


class _PlanRecorder:
    """Records every `RealizedPlan` `general_pipeline._realize` builds for the CURRENT brief, in
    the generator's own attempt order — the same instrumentation style `concept_diversity.py`
    uses (Issue #75's `_ClassRecorder`), extended to keep the plan objects themselves rather than
    only their class, so a sibling candidate can be looked up by its own `ConceptSpec`."""

    def __init__(self):
        self._orig = gp._realize
        self.plans: list = []

    def reset(self) -> None:
        self.plans = []

    def install(self) -> None:
        rec = self

        def realize(*args, **kwargs):
            plan = rec._orig(*args, **kwargs)
            rec.plans.append(plan)
            return plan

        gp._realize = realize

    def remove(self) -> None:
        gp._realize = self._orig


def _sibling_for(adapted_spec: concept_spec.ConceptSpec, plans: list, skip_index: int):
    """The first OTHER recorded plan whose own `ConceptSpec` already matches what `adapt`
    proposed (same class, zoning and wet-core strategy) — never a new solve."""
    for plan in plans:
        if plan.index == skip_index:
            continue
        candidate_spec = concept_spec.concept_spec_of(plan.concept)
        if (candidate_spec.circulation_class == adapted_spec.circulation_class
                and candidate_spec.zoning == adapted_spec.zoning
                and candidate_spec.wet_core_strategy == adapted_spec.wet_core_strategy):
            return plan
    return None


def _planned_cases(corpus_path: Path) -> list[dict]:
    with open(corpus_path, encoding="utf-8") as f:
        corpus = json.load(f)
    return [c for c in corpus["cases"] if c["expected_outcome"] == "PLANNED"]


def _score_one_brief(case: dict, recorder: "_PlanRecorder") -> dict | None:
    """One PLANNED case's result row, or `None` for the handful of contexts the demo service
    itself is expected to raise on (unrelated to this Issue)."""
    recorder.reset()
    project = project_from_context(case["context"])
    try:
        svc.generate_demo_design(project)
    except Exception:  # noqa: BLE001 - a handful of contexts are expected to raise
        return None
    plans = recorder.plans
    if not plans:
        return None
    first = plans[0]
    cls = first.circulation_class.value if first.circulation_class is not None else "UNKNOWN"
    spec0 = concept_spec.concept_spec_of(first.concept)
    score0 = concept_score(first)
    delta = None
    if not score0.rejected:
        category = "accepted"
    else:
        adapted_spec = adapt(spec0, first, score0, attempt=0)
        sibling = _sibling_for(adapted_spec, plans, first.index) if adapted_spec else None
        if sibling is not None:
            category = "adapted"
            delta = concept_score(sibling).total - score0.total
        else:
            category = "dropped"
    return {
        "context_id": case["context"].get("project_id", "?"),
        "class": cls,
        "category": category,
        "score_delta": delta,
    }


def score_briefs(cases: list[dict]) -> list[dict]:
    """One result row per case in `cases` (already filtered to PLANNED) — the per-brief work a
    chunked `--start`/`--end` run and a single full run both call identically."""
    recorder = _PlanRecorder()
    recorder.install()
    try:
        return [row for case in cases if (row := _score_one_brief(case, recorder)) is not None]
    finally:
        recorder.remove()


def aggregate(per_brief: list[dict]) -> dict:
    per_class: dict[str, Counter] = defaultdict(Counter)
    deltas: dict[str, list] = defaultdict(list)
    for row in per_brief:
        per_class[row["class"]][row["category"]] += 1
        if row["score_delta"] is not None:
            deltas[row["class"]].append(row["score_delta"])
    return {
        "n_briefs": len(per_brief),
        "per_class": {cls: dict(counts) for cls, counts in sorted(per_class.items())},
        "score_deltas": {cls: {
            "n": len(values),
            "mean": round(sum(values) / len(values), 3) if values else None,
        } for cls, values in sorted(deltas.items())},
        "per_brief": per_brief,
    }


def adaptation_report(corpus_path: Path = _CORPUS_PATH) -> dict:
    """The full report in one pass — every PLANNED case, one process. See `--start`/`--end` on
    the CLI below for a chunked/resumable equivalent of exactly this same per-brief logic."""
    return aggregate(score_briefs(_planned_cases(corpus_path)))


def render_report(stats: dict) -> str:
    lines = [
        "# Concept Engine v2 — concept adaptation report (Issue #76)",
        "",
        "Offline measurement of the bounded realize-measure-adapt loop's first rung, over the "
        "frozen 432-context regression corpus's PLANNED cases: for each brief's FIRST realized "
        "candidate (generator order, before ranking/selection), whether `concept_score` already "
        "accepts it, `adapt` names a target concept that another already-realized candidate for "
        "the same brief already matches (`adapted`), or neither (`dropped`). No runtime behavior "
        "change — see `app.vertical_slice.concept_score` and `spikes/failure_log_sweep/"
        "concept_adaptation_report.py`.",
        "",
        f"- PLANNED briefs measured: {stats['n_briefs']}",
        "",
        "## Per circulation class: accepted / adapted / dropped",
        "",
    ]
    for cls, counts in stats["per_class"].items():
        parts = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        lines.append(f"- {cls}: {parts}")
    lines.append("")
    lines.append("## Score deltas where a sibling was found (`adapted` cases)")
    lines.append("")
    any_delta = False
    for cls, d in stats["score_deltas"].items():
        if d["n"]:
            any_delta = True
            lines.append(f"- {cls}: n={d['n']}, mean delta={d['mean']}")
    if not any_delta:
        lines.append("- none in this corpus — see the per-class counts above.")
    lines.append("")
    total_adapted_or_dropped = sum(
        counts.get("adapted", 0) + counts.get("dropped", 0) for counts in stats["per_class"].values())
    if total_adapted_or_dropped == 0:
        lines.append(
            "Every brief's first realized candidate was already `accepted` on this frozen "
            "corpus — the ladder never had a case to bite on here. `run_general`'s existing "
            "candidate ordering and validation (C24/C19 among them) already reject or reorder "
            "away most of what `adapt` would otherwise be asked to fix before the FIRST "
            "candidate this measurement looks at is even reached; a corpus of harder or "
            "adversarial briefs — or a caller that measures every ATTEMPTED candidate, not "
            "only the first — is where `adapted`/`dropped` counts would first appear. No "
            "HUB_LOBBY or TWO_WING first candidate appears either, consistent with Issue #75's "
            "diversity baseline (`concept-engine-v2-diversity-baseline.md`): a hub-lobby plan "
            "never yet sizes within the hard template maxima on this corpus, and a two-wing "
            "candidate is never the FIRST one the generator tries.")
        lines.append("")
    return "\n".join(lines) + "\n"


def _load_resume(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_resume(path: Path, rows: list[dict]) -> None:
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=int, default=None,
                        help="chunk the PLANNED cases: score cases[start:end], "
                             "append to --resume, and stop (no report written).")
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument("--resume", type=Path, default=_RESUME_PATH,
                        help="where chunked runs accumulate their rows.")
    parser.add_argument("--finalize", action="store_true",
                        help="aggregate --resume's accumulated rows and write the report "
                             "(no further scoring).")
    args = parser.parse_args()

    if args.finalize:
        report_stats = aggregate(_load_resume(args.resume))
    elif args.start is not None or args.end is not None:
        cases = _planned_cases(_CORPUS_PATH)[args.start:args.end]
        rows = _load_resume(args.resume) + score_briefs(cases)
        _save_resume(args.resume, rows)
        print(f"scored {len(rows)} briefs so far -> {args.resume}")
        return
    else:
        report_stats = adaptation_report()

    print(json.dumps({k: v for k, v in report_stats.items() if k != "per_brief"}, indent=2))
    _REPORT_PATH.write_text(render_report(report_stats), encoding="utf-8")
    print(f"wrote {_REPORT_PATH}")


if __name__ == "__main__":
    main()
