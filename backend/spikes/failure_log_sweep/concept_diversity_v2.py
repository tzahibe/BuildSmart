"""Concept Engine v2 diversity measurement, flag ON — Issue #78 (single-outline), re-run for
Issue #79 (generator-level pattern compilers + cross-outline search, both wired in behind the
same flag by this point in `demo.service`/`concept_engine_v2`).

    .venv/bin/python3 spikes/failure_log_sweep/concept_diversity_v2.py [--start N] [--end N]
        [--resume PATH] [--finalize]

For every PLANNED case of the frozen regression corpus, flips `general_pipeline.
CONCEPT_ENGINE_V2_ENABLED` on for the duration of the call and replays the request, reporting:

  * the circulation class of every plan the screen would SHOW (primary + alternatives) — same
    method `concept_diversity.py` (Issue #75) uses for the flag-off baseline, so the two numbers
    are directly comparable;
  * whether the primary's own layout/family signature changed versus a flag-off replay of the
    SAME context (the AC-2/regression-budget invariant: LOST 0, primary_signature_changes 0).

Chunked like `concept_adaptation_report.py` (Issue #76): each brief costs several extra solver
realizations on top of the base run, so a full 404-brief pass is run in resumable chunks.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.demo import service as svc  # noqa: E402
from app.vertical_slice import general_pipeline as gp  # noqa: E402
from app.vertical_slice.concept_compilers import (_branched_unsupported,  # noqa: E402
                                                  _hub_lobby_unsupported)
from app.vertical_slice.concept_spec import CirculationClass  # noqa: E402
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec  # noqa: E402
from spikes.failure_log_sweep.sweep import project_from_context  # noqa: E402

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_DIR.parent
_CORPUS_PATH = _BACKEND_DIR / "tests" / "regression_corpus" / "corpus.json"
_REPORT_PATH = _REPO_ROOT / "docs" / "reports" / "concept-engine-v2-diversity-report.md"
_RESUME_PATH = _BACKEND_DIR / "spikes" / "failure_log_sweep" / "_concept_diversity_v2_resume.json"


def _layout_signature_of_rooms(rooms) -> tuple:
    return tuple(sorted((zid, round(x, 3), round(y, 3), round(w, 3), round(h, 3))
                        for zid, x, y, w, h in rooms))


def _demo_design_rooms(design) -> tuple:
    return tuple((r.id, r.x, r.y, r.width_m, r.depth_m) for r in design.rooms)


def _realized_plan_rooms(design) -> tuple:
    return tuple((r.zone_id, *r.rect_m) for r in design.rooms)


class _ClassRecorder:
    """Records every `_realize` call's realized class, keyed by its layout signature — the same
    instrumentation `concept_diversity.py`'s `_ClassRecorder` uses (Issue #75)."""

    def __init__(self):
        self._orig = gp._realize
        self.by_signature: dict[tuple, CirculationClass] = {}

    def reset(self) -> None:
        self.by_signature = {}

    def install(self) -> None:
        rec = self

        def realize(*args, **kwargs):
            plan = rec._orig(*args, **kwargs)
            sig = _layout_signature_of_rooms(_realized_plan_rooms(plan.design))
            if plan.circulation_class is not None:
                rec.by_signature[sig] = plan.circulation_class
            return plan

        gp._realize = realize

    def remove(self) -> None:
        gp._realize = self._orig

    def classes_of(self, demo_designs) -> list[CirculationClass]:
        out = []
        for design in demo_designs:
            sig = _layout_signature_of_rooms(_demo_design_rooms(design))
            cls = self.by_signature.get(sig)
            if cls is not None:
                out.append(cls)
        return out


def _planned_cases(corpus_path: Path) -> list[dict]:
    with open(corpus_path, encoding="utf-8") as f:
        corpus = json.load(f)
    return [c for c in corpus["cases"] if c["expected_outcome"] == "PLANNED"]


def _score_one_brief(case: dict, recorder: "_ClassRecorder") -> dict | None:
    """One PLANNED case's row: flag OFF primary signature, then flag ON shown-plan classes and
    primary signature — `None` for the handful of contexts the demo service itself raises on."""
    context_id = case["context"].get("project_id", "?")
    project = project_from_context(case["context"])

    gp.CONCEPT_ENGINE_V2_ENABLED = False
    try:
        off_result = svc.generate_demo_design(project)
    except Exception:  # noqa: BLE001 - a handful of contexts are expected to raise either way
        off_result = None

    recorder.reset()
    gp.CONCEPT_ENGINE_V2_ENABLED = True
    try:
        on_result = svc.generate_demo_design(project)
    except Exception:  # noqa: BLE001
        on_result = None
    finally:
        gp.CONCEPT_ENGINE_V2_ENABLED = False

    if off_result is None and on_result is None:
        return None

    lost = off_result is not None and on_result is None
    gained = off_result is None and on_result is not None
    primary_signature_changed = (
        off_result is not None and on_result is not None
        and _demo_design_rooms(off_result.design) != _demo_design_rooms(on_result.design))

    if on_result is None:
        return {
            "context_id": context_id, "lost": lost, "gained": gained,
            "primary_signature_changed": primary_signature_changed,
            "n_shown": 0, "n_classes": 0, "classes": [],
        }

    shown = [on_result.design, *on_result.alternatives]
    classes = recorder.classes_of(shown)
    return {
        "context_id": context_id, "lost": lost, "gained": gained,
        "primary_signature_changed": primary_signature_changed,
        "n_shown": len(shown), "n_classes": len(set(classes)),
        "classes": sorted({c.value for c in classes}),
    }


def score_briefs(cases: list[dict]) -> list[dict]:
    recorder = _ClassRecorder()
    recorder.install()
    try:
        return [row for case in cases if (row := _score_one_brief(case, recorder)) is not None]
    finally:
        recorder.remove()
        gp.CONCEPT_ENGINE_V2_ENABLED = False


def aggregate(per_brief: list[dict]) -> dict:
    n = len(per_brief)
    multi = sum(1 for b in per_brief if b["n_classes"] >= 2)
    class_counter: Counter = Counter(c for b in per_brief for c in b["classes"])
    lost = sum(1 for b in per_brief if b["lost"])
    gained = sum(1 for b in per_brief if b["gained"])
    primary_changed = sum(1 for b in per_brief if b["primary_signature_changed"])
    return {
        "n_briefs": n,
        "briefs_with_2_or_more_classes": multi,
        "share_with_2_or_more_classes": (multi / n) if n else 0.0,
        "class_counts": dict(sorted(class_counter.items())),
        "lost": lost,
        "gained": gained,
        "primary_signature_changes": primary_changed,
        "per_brief": per_brief,
    }


def _spec_for(context: dict) -> ArchitecturalSpec:
    """A spec carrying this context's PROGRAMME, for asking a compiler whether it supports it.

    Both compiler preconditions (`concept_compilers._hub_lobby_unsupported` /
    `_branched_unsupported`) read `spec.program` only, so the plot is nominal — the programme is
    the whole question here."""
    return ArchitecturalSpec(
        plot=PlotSpec(width_m=float(context.get("plot_width_m") or 16.0),
                      depth_m=float(context.get("plot_depth_m") or 20.0)),
        program=ProgramSpec(bedrooms=int(context.get("bedrooms") or 0),
                            wet_rooms=int(context.get("wet_rooms") or 0),
                            safe_room=bool(context.get("safe_room"))))


def _hub_lobby_eligible(context: dict) -> bool:
    """Whether `compile_hub_lobby` supports this brief — ASKED OF THE COMPILER ITSELF.

    This used to be a hand-written copy of the precondition, and it silently went stale when
    attempt 4 taught the compiler a 3-wet-room (GUEST_WC) variant: the committed report then
    reported briefs as excluded that the code already served (review finding, attempt 5). The copy
    is gone — a report about what the compilers cover now cannot disagree with them."""
    return _hub_lobby_unsupported(_spec_for(context)) is None


def _branched_eligible(context: dict) -> bool:
    """Whether `compile_branched` supports this brief, asked of the compiler itself (see
    `_hub_lobby_eligible` for why this is not a copy of the precondition)."""
    return _branched_unsupported(_spec_for(context)) is None


def _compiler_eligibility_breakdown(cases: list[dict]) -> dict:
    """Per-precondition breakdown (lead direction after attempt 2, 2026-09-22, (c)): how many
    PLANNED cases satisfy `compile_hub_lobby`'s own precondition, `compile_branched`'s own, either,
    and how many PLANNED cases satisfy NEITHER (the residual population still excluded, with the
    reason each one is excluded) — the structural ceiling on what the two compilers could
    contribute, independent of how general their own bedroom/wet-room sizing becomes."""
    n = len(cases)
    hub_elig = [c for c in cases if _hub_lobby_eligible(c["context"])]
    branched_elig = [c for c in cases if _branched_eligible(c["context"])]
    either = [c for c in cases
             if _hub_lobby_eligible(c["context"]) or _branched_eligible(c["context"])]
    excluded = [c for c in cases
               if not _hub_lobby_eligible(c["context"]) and not _branched_eligible(c["context"])]
    # Each excluded brief is labelled with the two compilers' OWN refusal messages, never with a
    # restatement of their preconditions in this file's prose: the prose copy is what went stale
    # after attempt 4 (review finding, attempt 5), and a report of what the compilers do not cover
    # has to be quoted from them to stay true as they generalize.
    reason_counter: Counter = Counter()
    for c in excluded:
        spec = _spec_for(c["context"])
        reason_counter[f"hub_lobby: {_hub_lobby_unsupported(spec)} · "
                      f"branched: {_branched_unsupported(spec)}"] += 1
    return {
        "n_briefs": n,
        "hub_lobby_eligible_count": len(hub_elig),
        "branched_eligible_count": len(branched_elig),
        "either_eligible_count": len(either),
        "excluded_count": len(excluded),
        "excluded_reasons": dict(sorted(reason_counter.items(), key=lambda kv: -kv[1])),
    }


def diversity_report(corpus_path: Path = _CORPUS_PATH) -> dict:
    cases = _planned_cases(corpus_path)
    stats = aggregate(score_briefs(cases))
    stats["eligibility"] = _compiler_eligibility_breakdown(cases)
    return stats


def render_report(stats: dict) -> str:
    lines = [
        "# Concept Engine v2 — diversity report, flag ON (Issue #79)",
        "",
        "`general_pipeline.CONCEPT_ENGINE_V2_ENABLED = True` for the duration of each call, over "
        "the frozen 432-context regression corpus's PLANNED cases: how many circulation classes a "
        "brief's SHOWN plan set (primary + alternatives) contains once "
        "`concept_engine_v2.plans_per_class`/`plans_per_class_cross_outline` (Issue #79's "
        "generator-level pattern compilers, `concept_compilers.py`, plus cross-outline search) "
        "replace the ordinary alternatives walk, compared against the flag-off baseline "
        "(`concept-engine-v2-diversity-baseline.md`, Issue #75: 49/404, 12.1%) and the "
        "single-outline Issue #78 measurement (71/404, 17.6%). Generated by "
        "`spikes/failure_log_sweep/concept_diversity_v2.py`.",
        "",
        f"- PLANNED briefs measured: {stats['n_briefs']}",
        f"- briefs with 2 or more distinct circulation classes shown: "
        f"{stats['briefs_with_2_or_more_classes']} of {stats['n_briefs']} "
        f"({100 * stats['share_with_2_or_more_classes']:.1f}%)",
        f"- LOST (planned flag-off, refused flag-on): {stats['lost']}",
        f"- GAINED (refused flag-off, planned flag-on): {stats['gained']}",
        f"- primary_signature_changes (primary's own rooms differ flag-on vs flag-off): "
        f"{stats['primary_signature_changes']}",
        "",
        "## Circulation class counts across every shown plan (flag ON)",
        "",
    ]
    for cls, count in stats["class_counts"].items():
        lines.append(f"- {cls}: {count}")
    lines.append("")
    if "eligibility" in stats:
        n = stats["n_briefs"]
        elig = stats["eligibility"]
        share = stats["share_with_2_or_more_classes"]
        verdict = "meets" if share >= 0.40 else "below"
        lines += [
            "## AC-3 assessment (Issue #79, attempt 3)",
            "",
            f"Share with ≥2 classes shown: {stats['briefs_with_2_or_more_classes']}/{n} "
            f"({100 * share:.1f}%) — {verdict} the 40% bar.",
            "",
            "### Per-precondition eligibility breakdown (lead direction 2026-09-22 (c))",
            "",
            "`compile_hub_lobby` and `compile_branched` now each support a SAFE_ROOM-aware and an "
            "open-plan-aware variant (attempt 3); what still bounds them is the room-count shape "
            "each was calibrated and verified against. Every count and every reason below is read "
            "from the compilers themselves (`_hub_lobby_unsupported` / `_branched_unsupported`), "
            "never from a restatement of their preconditions here — the earlier restatement went "
            "stale the moment attempt 4 added `compile_hub_lobby`'s 3-wet-room GUEST_WC row, and "
            "under-reported what the code already covered (review finding, attempt 5).",
            "",
            f"- `compile_hub_lobby`-eligible: {elig['hub_lobby_eligible_count']}/{n}",
            f"- `compile_branched`-eligible: {elig['branched_eligible_count']}/{n}",
            f"- eligible for either compiler: {elig['either_eligible_count']}/{n} "
            f"({100 * elig['either_eligible_count'] / n:.1f}%)" if n else "n/a",
            f"- excluded from both (residual population): {elig['excluded_count']}/{n}",
            "",
            "#### Residual population excluded from both compilers, by reason",
            "",
        ]
        for reason, count in elig["excluded_reasons"].items():
            lines.append(f"- {reason}: {count}")
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
    parser.add_argument("--start", type=int, default=None)
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument("--resume", type=Path, default=_RESUME_PATH)
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()

    if args.finalize:
        report_stats = aggregate(_load_resume(args.resume))
        report_stats["eligibility"] = _compiler_eligibility_breakdown(_planned_cases(_CORPUS_PATH))
    elif args.start is not None or args.end is not None:
        cases = _planned_cases(_CORPUS_PATH)[args.start:args.end]
        rows = _load_resume(args.resume) + score_briefs(cases)
        _save_resume(args.resume, rows)
        print(f"scored {len(rows)} briefs so far -> {args.resume}")
        return
    else:
        report_stats = diversity_report()

    print(json.dumps({k: v for k, v in report_stats.items() if k != "per_brief"}, indent=2))
    _REPORT_PATH.write_text(render_report(report_stats), encoding="utf-8")
    print(f"wrote {_REPORT_PATH}")


if __name__ == "__main__":
    main()
