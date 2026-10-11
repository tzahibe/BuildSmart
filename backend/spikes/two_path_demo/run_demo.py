"""Issue #155 — what main can draw today, beside the non-guillotine realizer, same briefs, same
drawing layer, measured.

For each of the 8 briefs `selection.py` chose (AC-1), builds TWO plans through the SAME shipping
contract-building entry point, `app.demo.contract.to_demo_design` (Issue #146's own drawing layer
draws nothing that is not on the `DemoDesign` this function produces — see that module's own
docstring):

  - path A — `app.demo.service.generate_demo_design`, exactly as main behaves today, every flag at
    its default. `to_demo_design` is called INSIDE it (`app/demo/service.py:845`).
  - path B — `app.vertical_slice.rectilinear_realizer.realize_layout`, with
    `RECTILINEAR_REALIZER_ENABLED` forced on IN THIS PROCESS ONLY (`_realizer_forced_on`, restored
    on exit no matter what) — the module's own committed default never changes. A REALIZED layout
    is then handed to the SAME `to_demo_design`, called directly here.

PLACEMENT for path B (which family, which real room role goes where) is this script's OWN
deterministic choice, reusing `spikes/geometry_shapes/stage1_gate.py`'s own proven intent-builders
(`build_pinwheel_intent`/`build_notch_intent`/`build_two_wing_intent`) rather than re-deriving that
heuristic — the realizer's mandated input is a PLACED layout; deciding placement from scratch is
Stage 2's job, out of this Issue's scope (see this Issue's own "Out of scope").

Every REALIZED path-B plan is validated by the UNCHANGED validator chain
(`app.vertical_slice.validation.validate`, which includes C31) exactly as `realize_layout` already
does internally, PLUS C30 (`check_furnishability`) called directly — C30 is disclosure-only, not
wired into `validate()` by an existing, documented maintainer scope decision
(`validation.py::check_furnishability`'s own docstring), so it is run and reported here rather than
silently skipped. A REFUSED path-B plan is reported with its exact refusal code/detail and is NEVER
replaced by a different, easier brief or a rescaled "pass" beyond this script's own disclosed retry
ladder (identical to `stage1_gate.py`'s: both larger and smaller envelope scales, up to 9 attempts,
never approximating — `realize_layout` itself never does either).

Run from `backend/`:
    uv run python -m spikes.two_path_demo.run_demo
"""
from __future__ import annotations

import contextlib
import dataclasses
import json
import os

from app.demo.contract import DemoDesign, to_demo_design
from app.demo.service import DemoGenerationError, generate_demo_design
from app.vertical_slice import rectilinear_realizer
from app.vertical_slice.rectilinear_realizer import RealizedLayout, Refusal, realize_layout
from app.vertical_slice.validation import check_furnishability
from spikes.failure_log_sweep.sweep import project_from_context
from spikes.geometry_shapes.stage1_gate import (
    SourceLayout,
    build_notch_intent,
    build_pinwheel_intent,
    build_two_wing_intent,
    load_source_layout,
)
from spikes.two_path_demo import selection

_REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))), "docs", "reports", "two-path-demo")
#: NOT named "data" — the repo's own `.gitignore` has a bare `data/` rule that matches a
#: directory of that name anywhere in the tree, which would silently un-track this report's own
#: evidence.
_DATA_DIR = os.path.join(_REPORT_DIR, "contracts")

#: One construction family attempted per brief — matching `stage1_gate.py`'s own one-attempt-per-
#: case precedent (never a multi-family sweep that would let an easy family flatter the realizer).
#: Assignment is a stable hash of the brief id, not the brief's own content.
_FAMILIES = ("PINWHEEL", "L", "U", "TWO_WING")

#: Identical to `stage1_gate.py`'s own `_RETRY_SCALES` — this script's OWN retry policy, not the
#: realizer's: a short-side refusal wants a BIGGER envelope, a circulation-ratio refusal wants a
#: SMALLER one (measured empirically there; neither direction alone clears every real context).
_RETRY_SCALES = (1.0, 0.9, 0.95, 1.15, 0.85, 1.3, 0.8, 1.45, 0.75)
_RETRYABLE_CONSTRAINTS = (
    "SHORT_SIDE_INFEASIBLE", "AREA_INFEASIBLE", "ASPECT_INFEASIBLE",
    "NOTCH_INFEASIBLE", "PINWHEEL_INFEASIBLE", "VALIDATION_FAILED",
)


def family_for(brief_id: str) -> str:
    idx = selection.stable_hash(brief_id) % len(_FAMILIES)
    return _FAMILIES[idx]


@contextlib.contextmanager
def _realizer_forced_on():
    """`RECTILINEAR_REALIZER_ENABLED` forced True for the duration of this context, IN THIS
    PROCESS ONLY — restored on exit even if an exception is raised. This script is the only place
    in the repo that does this; the module's own committed default (`False`) is untouched."""
    original = rectilinear_realizer.RECTILINEAR_REALIZER_ENABLED
    rectilinear_realizer.RECTILINEAR_REALIZER_ENABLED = True
    try:
        yield
    finally:
        rectilinear_realizer.RECTILINEAR_REALIZER_ENABLED = original


@dataclasses.dataclass
class PathResult:
    brief_id: str
    path: str  # "A" | "B"
    outcome: str  # "REALIZED" | "REFUSED"
    refusal_code: str | None = None
    refusal_detail: str | None = None
    family: str | None = None  # path B only
    demo_design: DemoDesign | None = None
    c30_passed: bool | None = None
    c30_detail: str | None = None
    #: ground truth from the realizer's own construction (path B only) — see
    #: `docs/reports/two-path-demo/results.md`'s "What this does and does not prove" for why this
    #: is reported SEPARATELY from the DemoDesign-contract-level non-rectangular count.
    notch_group_count: int = 0
    is_multi_wing_envelope: bool = False


def run_path_a(case: dict) -> PathResult:
    project = project_from_context(case["context"])
    try:
        result = generate_demo_design(project)
    except DemoGenerationError as exc:
        return PathResult(case["source_key"], "A", "REFUSED", exc.code, exc.message)
    return PathResult(case["source_key"], "A", "REALIZED", demo_design=result.design)


def _build_intent(family: str, source: SourceLayout, name: str, scale: float):
    if family == "PINWHEEL":
        return build_pinwheel_intent(name, source, scale)
    if family in ("L", "U"):
        return build_notch_intent(name, source, family, scale)
    return build_two_wing_intent(name, source, scale)


def run_path_b(case: dict, family: str) -> PathResult:
    brief_id = case["source_key"]
    source = load_source_layout(brief_id, case["context"])
    intent = None
    result: RealizedLayout | Refusal | None = None
    with _realizer_forced_on():
        for scale in _RETRY_SCALES:
            if isinstance(result, RealizedLayout):
                break
            if isinstance(result, Refusal) and result.constraint not in _RETRYABLE_CONSTRAINTS:
                break
            candidate = _build_intent(family, source, brief_id, scale)
            if candidate is None:
                continue
            intent = candidate
            result = realize_layout(intent)

        if intent is None:
            return PathResult(brief_id, "B", "REFUSED", "NO_USABLE_ROOMS",
                              "not enough usable real rooms in this context to build a "
                              f"{family} layout at any of this script's retry scales",
                              family=family)
        if isinstance(result, Refusal):
            return PathResult(brief_id, "B", "REFUSED", result.constraint, result.detail,
                              family=family)

        # Same shipping contract-building entry point path A goes through internally
        # (`app/demo/service.py:845`) — called directly here, still fully inside the
        # `_realizer_forced_on()` context (though `to_demo_design` itself reads no such flag).
        demo = to_demo_design(result.design, result.report)
        c30 = check_furnishability(result.design)

    return PathResult(
        brief_id, "B", "REALIZED", family=family, demo_design=demo,
        c30_passed=c30.passed, c30_detail=c30.detail,
        notch_group_count=len(result.groups),
        is_multi_wing_envelope=family == "TWO_WING",
    )


def contract_non_rectangular(demo: DemoDesign) -> tuple[int, bool]:
    """The observable-in-the-shipped-contract non-rectangular count (AC-5): a room whose own
    `shape` is not `RECTANGLE`/unset, and whether the envelope is drawn as more than one wing
    (`footprintsOf` in `DemoPlan.tsx` — one rectangle per wing; more than one is not a single
    axis-aligned rectangle). Computed identically for path A and path B — the SAME predicate
    applied to the SAME contract shape both paths produce."""
    non_rect_rooms = sum(1 for r in demo.rooms if r.shape not in (None, "RECTANGLE"))
    non_rect_envelope = len(demo.footprints) > 1
    return non_rect_rooms, non_rect_envelope


def run_all() -> list[tuple[PathResult, PathResult]]:
    corpus = selection.load_corpus()
    ids = selection.select_briefs(corpus)
    committed = selection.load_committed_briefs()
    if ids != committed:
        raise RuntimeError(
            "selection.select_briefs() no longer matches the committed "
            f"{selection.COMMITTED_BRIEFS_PATH} — AC-1 requires the sample to never change after "
            "being committed; investigate before regenerating the report")
    cases = {c["source_key"]: c for c in corpus["cases"]}
    pairs = []
    for brief_id in ids:
        case = cases[brief_id]
        a = run_path_a(case)
        b = run_path_b(case, family_for(brief_id))
        pairs.append((a, b))
    return pairs


def _short_id(brief_id: str, index: int) -> str:
    return f"brief-{index:02d}"


def _metrics_dict(demo: DemoDesign | None) -> dict | None:
    if demo is None:
        return None
    m = demo.quality.metrics
    return {
        "m1_habitable_aspect_median": m.m1_habitable_aspect_median,
        "m1_habitable_aspect_max": m.m1_habitable_aspect_max,
        "m2_habitable_on_envelope_ratio": m.m2_habitable_on_envelope_ratio,
        "m3_circulation_share": m.m3_circulation_share,
        "m4_hall_door_count": m.m4_hall_door_count,
        "m4_hall_aspect_median": m.m4_hall_aspect_median,
        "m5_wet_adjacency_ratio": m.m5_wet_adjacency_ratio,
        "m6_public_zone_contiguous": m.m6_public_zone_contiguous,
        "validation_passed": demo.validation.passed,
    }


def write_data_files(pairs: list[tuple[PathResult, PathResult]]) -> None:
    """Writes `<short>-A.json`/`<short>-B.json` (the real `DemoDesign` contract — Issue #146's
    drawing layer's own input, for each path that REALIZED) and `<short>-meta.json` (verdicts,
    M1-M6, refusal codes, street orientation — everything the frontend composite step needs to
    label a plan without re-deriving anything from the contract itself)."""
    corpus = selection.load_corpus()
    cases = {c["source_key"]: c for c in corpus["cases"]}
    os.makedirs(_DATA_DIR, exist_ok=True)
    for i, (a, b) in enumerate(pairs):
        short = _short_id(a.brief_id, i)
        ctx = cases[a.brief_id]["context"]
        for path_result, letter in ((a, "A"), (b, "B")):
            if path_result.demo_design is None:
                continue
            out_path = os.path.join(_DATA_DIR, f"{short}-{letter}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(path_result.demo_design.model_dump_json(indent=2))
        meta = {
            "brief_id": a.brief_id,
            "street_facing_side": ctx["street_facing_side"],
            "family_b": b.family,
            "a": {
                "outcome": a.outcome, "refusal_code": a.refusal_code,
                "refusal_detail": a.refusal_detail, "metrics": _metrics_dict(a.demo_design),
            },
            "b": {
                "outcome": b.outcome, "refusal_code": b.refusal_code,
                "refusal_detail": b.refusal_detail, "metrics": _metrics_dict(b.demo_design),
                "c30_passed": b.c30_passed, "c30_detail": b.c30_detail,
            },
        }
        with open(os.path.join(_DATA_DIR, f"{short}-meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    from spikes.two_path_demo import report as report_module

    results = run_all()
    write_data_files(results)
    report_text = report_module.write_report(results)
    os.makedirs(_REPORT_DIR, exist_ok=True)
    with open(os.path.join(_REPORT_DIR, "results.md"), "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"wrote {os.path.join(_REPORT_DIR, 'results.md')}")
