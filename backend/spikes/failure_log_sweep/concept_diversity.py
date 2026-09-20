"""Concept Engine v2 (1/5) diversity baseline — Issue #75.

    .venv/bin/python3 spikes/failure_log_sweep/concept_diversity.py

For every PLANNED case of the frozen regression corpus (`tests/regression_corpus/corpus.json`),
replays the request through `generate_demo_design` and reports the `CirculationClass` of every
plan the screen would SHOW (the primary plus its alternatives) — the "before" number the Concept
Engine v2 ROOT Issue needs: the share of briefs whose shown set already contains 2 or more
distinct classes. Writes `docs/reports/concept-engine-v2-diversity-baseline.md`.

Classes are read off the REALIZED geometry (`concept_spec.realized_circulation_class`, computed
inside `general_pipeline._realize`), matched back to each shown `DemoDesign` by its own
room-rectangle signature — the same identity `general_pipeline.RealizedPlan.layout_signature`
uses — because `generate_demo_design`'s result carries `DemoDesign` objects (the contract layer),
not the `RealizedPlan` the class was computed from.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.demo import service as svc  # noqa: E402
from app.vertical_slice import general_pipeline as gp  # noqa: E402
from app.vertical_slice.concept_spec import CirculationClass  # noqa: E402
from spikes.failure_log_sweep.sweep import project_from_context  # noqa: E402

_CORPUS_PATH = Path(__file__).resolve().parents[2] / "tests" / "regression_corpus" / "corpus.json"
_REPORT_PATH = (Path(__file__).resolve().parents[2] / "docs" / "reports"
               / "concept-engine-v2-diversity-baseline.md")


def _layout_signature_of_rooms(rooms) -> tuple:
    """The same identity `RealizedPlan.layout_signature` computes — see that property's own
    docstring — built here from whichever room list (a `RealizedPlan.design.rooms` or a
    `DemoDesign.rooms`) is at hand, since both carry the same zone id + metres rectangle."""
    return tuple(sorted((zid, round(x, 3), round(y, 3), round(w, 3), round(h, 3))
                        for zid, x, y, w, h in rooms))


def _demo_design_rooms(design) -> tuple:
    return tuple((r.id, r.x, r.y, r.width_m, r.depth_m) for r in design.rooms)


def _realized_plan_rooms(design) -> tuple:
    return tuple((r.zone_id, *r.rect_m) for r in design.rooms)


class _ClassRecorder:
    """Records every `_realize` call's realized class, keyed by its layout signature, so a
    `DemoDesign` the demo service later hands back can be matched to the class it was realized
    with. `install`/`remove`/`reset` mirror `spikes.failure_log_sweep.sweep.StrategyRecorder`."""

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


def diversity_report(corpus_path: Path = _CORPUS_PATH) -> dict:
    with open(corpus_path, encoding="utf-8") as f:
        corpus = json.load(f)

    recorder = _ClassRecorder()
    recorder.install()
    per_brief: list[dict] = []
    try:
        for case in corpus["cases"]:
            if case["expected_outcome"] != "PLANNED":
                continue
            recorder.reset()
            project = project_from_context(case["context"])
            try:
                result = svc.generate_demo_design(project)
            except Exception:  # noqa: BLE001 - a handful of contexts are expected to raise
                continue
            shown = [result.design, *result.alternatives]
            classes = recorder.classes_of(shown)
            per_brief.append({
                "context_id": case["context"].get("project_id", "?"),
                "shown": len(shown),
                "matched": len(classes),
                "classes": sorted({c.value for c in classes}),
            })
    finally:
        recorder.remove()

    n = len(per_brief)
    multi = sum(1 for b in per_brief if len(b["classes"]) >= 2)
    class_counter: Counter = Counter(c for b in per_brief for c in b["classes"])
    return {
        "n_briefs": n,
        "briefs_with_2_or_more_classes": multi,
        "share_with_2_or_more_classes": (multi / n) if n else 0.0,
        "class_counts": dict(sorted(class_counter.items())),
        "per_brief": per_brief,
    }


def render_report(stats: dict) -> str:
    lines = [
        "# Concept Engine v2 — diversity baseline (Issue #75)",
        "",
        "The \"before\" number the Concept Engine v2 ROOT Issue needs: how many circulation classes "
        "a brief's SHOWN plan set (primary + alternatives) already contains, measured on the frozen "
        "432-context regression corpus's PLANNED cases via "
        "`app.vertical_slice.concept_spec.realized_circulation_class` — read off the realized "
        "geometry, never the tree/strategy that built it. Generated by "
        "`spikes/failure_log_sweep/concept_diversity.py`; metadata only — see Issue #75, no "
        "behavior change.",
        "",
        f"- PLANNED briefs measured: {stats['n_briefs']}",
        f"- briefs with 2 or more distinct circulation classes shown: "
        f"{stats['briefs_with_2_or_more_classes']} of {stats['n_briefs']} "
        f"({100 * stats['share_with_2_or_more_classes']:.1f}%)",
        "",
        "## Circulation class counts across every shown plan",
        "",
    ]
    for cls, count in stats["class_counts"].items():
        lines.append(f"- {cls}: {count}")
    lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    stats = diversity_report()
    print(json.dumps({k: v for k, v in stats.items() if k != "per_brief"}, indent=2))
    _REPORT_PATH.write_text(render_report(stats), encoding="utf-8")
    print(f"wrote {_REPORT_PATH}")
