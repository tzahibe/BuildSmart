"""#213 — run the SAME brief through production and through the brain, render both with the
PRODUCT'S OWN drawing path, and record objective facts only.

Both engines are reached through one function, `app.demo.service.generate_demo_design` — the exact
function `POST /projects/{id}/design/demo` calls, with `brain=True` being exactly what
`?engine=brain` sets (`demo/router.py:_brain_requested`). Nothing here re-implements a pipeline, a
sizer or a drawing: the payload is the product's `DemoDesign` and the figure is `DemoPlan`
(rendered by `frontend/src/design/drawing-audit-render.test.tsx`, rasterised by
`drawing_audit/rasterise.mjs`). A harness drawer is never used.

The measurements extend `brain_eval/compare.py`'s `profile()` (imported, not copied) with the
payload-level facts the drawing depends on (`drawing_audit.run.analyse`) and the per-check
validator result the contract already carries.

Non-rectangular envelopes: the product cannot be handed one (`demo/scope.py:362` refuses any
`selected_footprint.shape_type` other than RECTANGLE, and `service._brain_result` hands
`run_brain` a `(width_m, depth_m)` pair which `brain/exact_pipeline.py:128` turns into
`Envelope.rectangle`). For a frozen polygon case this harness therefore records the refusal AND
runs both engines on the case's bounding rectangle — what a user asking for that site actually
receives today — never substituting one for the other silently.

Run from backend/:
    uv run python -m app.ai_harness.comparison_corpus.run <out_dir> [brief ids ...]
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback

from app.ai_harness.brain_eval.compare import profile
from app.ai_harness.comparison_corpus import corpus as corpus_mod
from app.ai_harness.drawing_audit.run import analyse
from app.ai_harness.topology_poc import briefs as briefs_mod
from app.demo import service as svc

#: The payload facts worth carrying into the report's objective table; the rest of `analyse()`'s
#: output stays in results.json for anyone checking a cell.
ANALYSIS_KEYS = ("footprints", "garden_rects", "uncovered_m2", "windows_on_interior_walls",
                 "windows_without_wall", "doors_without_wall", "rooms_outside_any_footprint",
                 "overlapping_rooms", "overlapping_wall_segments", "habitable_rooms_without_window",
                 "polygon_rooms", "flex_rooms", "walk_reaches_door")


def project_for(b):
    from tests.vertical_slice.test_hub_guard import _project
    return _project(dict(bedrooms=b.bedrooms, wet_rooms=b.wet_rooms, safe_room=b.safe_room,
                         open_plan=b.open_plan, built_area_m2=b.built_area_m2,
                         footprint_width_m=b.footprint_width_m, footprint_depth_m=b.footprint_depth_m,
                         plot_width_m=b.footprint_width_m + 8, plot_depth_m=b.footprint_depth_m + 8))


def _dump(out_dir: str, name: str, design) -> str:
    os.makedirs(os.path.join(out_dir, "designs"), exist_ok=True)
    path = os.path.join(out_dir, "designs", f"{name}.json")
    with open(path, "w") as fh:
        json.dump(design.model_dump(mode="json"), fh)
    return f"{name}.json"


def _layout_family(design) -> str | None:
    """Which layout family sized a brain plan, read off the note `_brain_result` attaches."""
    for w in design.validation.warnings:
        if w.startswith("sized by the "):
            return w.split("(")[-1].rstrip(")").replace(" layout", "")
    return None


def measure(design, requested_m2: float, seconds: float) -> dict:
    """One delivered plan's objective facts. No judgment: every value is read off the payload."""
    raw = json.loads(design.model_dump_json())
    checks = design.validation.checks or {}
    a = analyse(raw)
    return {
        **profile(design, requested_m2),
        **{k: a[k] for k in ANALYSIS_KEYS if k in a},
        "seconds": round(seconds, 1),
        "family": design.family,
        "layout_family": _layout_family(design),
        "validators_total": len(checks),
        "validators_failed": sorted(k for k, ok in checks.items() if not ok),
        "validation_passed": design.validation.passed,
        "alternatives_note": None,
    }


def run_engine(project, requested_m2: float, *, brain: bool, out_dir: str, name: str) -> dict:
    """One engine on one brief, through the product's own entry point."""
    t0 = time.monotonic()
    try:
        res = svc.generate_demo_design(project, brain=brain)
    except svc.DemoGenerationError as exc:
        return {"outcome": "REFUSED", "code": exc.code, "detail": exc.detail[:400],
                "seconds": round(time.monotonic() - t0, 1)}
    except Exception:                                  # noqa: BLE001 — recorded, never hidden
        return {"outcome": "EXCEPTION", "detail": traceback.format_exc()[-800:],
                "seconds": round(time.monotonic() - t0, 1)}
    secs = time.monotonic() - t0
    out = {"outcome": "PLAN", "render": _dump(out_dir, name, res.design),
           "alternatives": len(res.alternatives), **measure(res.design, requested_m2, secs)}
    out["alternative_families"] = [a.family for a in res.alternatives]
    return out


def run_real(entry, b, out_dir: str) -> dict:
    rec = {"brief": entry.brief_id, "source": entry.source, "family": entry.family,
           "note": entry.note, "requested_m2": b.built_area_m2,
           "envelope": f"{b.footprint_width_m} x {b.footprint_depth_m}",
           "programme": {"bedrooms": b.bedrooms, "wet_rooms": b.wet_rooms,
                         "safe_room": b.safe_room, "open_plan": b.open_plan}}
    project = project_for(b)
    rec["production"] = run_engine(project, b.built_area_m2, brain=False, out_dir=out_dir,
                                   name=f"{entry.brief_id}__production")
    rec["brain"] = run_engine(project, b.built_area_m2, brain=True, out_dir=out_dir,
                              name=f"{entry.brief_id}__brain")
    print(f"{entry.brief_id:20} {entry.family:22} production={rec['production']['outcome']} "
          f"brain={rec['brain']['outcome']} "
          f"({rec['production'].get('seconds')}s / {rec['brain'].get('seconds')}s)", flush=True)
    return rec


def run_frozen(entry, case, out_dir: str) -> dict:
    """A frozen case: the polygon the product cannot take, and the rectangle it can.

    The refusal is not caught from an exception — the product never gets the chance to raise one,
    because `Project` has nowhere to put a polygon. That IS the finding, and it is recorded with
    the two lines that make it true.
    """
    from app.ai_harness.shape_agnostic.run import _project_for as frozen_project
    project, env = frozen_project(case)
    bbox_w, bbox_d = round(env.width_u * 0.05, 2), round(env.depth_u * 0.05, 2)
    requested = case["footprint"]["gross_m2"]
    rec = {"brief": entry.brief_id, "source": entry.source, "family": entry.family,
           "note": entry.note, "requested_m2": requested,
           "envelope": f"polygon, bbox {bbox_w} x {bbox_d}",
           "envelope_polygon": case["envelope"],
           "envelope_area_m2": round(env.area_m2, 1),
           "bbox_area_m2": round(bbox_w * bbox_d, 1),
           "programme": case["programme"],
           "polygon_into_product": {
               "outcome": "CANNOT_BUILD",
               "detail": ("the product has nowhere to put an orthogonal polygon: "
                          "`Project.selected_footprint` is width x depth and "
                          "demo/scope.py:362 refuses shape_type != RECTANGLE; "
                          "service._brain_result passes (outline.width_m, outline.depth_m) and "
                          "brain/exact_pipeline.py:128 builds Envelope.rectangle from it"),
           }}
    rec["production"] = run_engine(project, requested, brain=False, out_dir=out_dir,
                                   name=f"{entry.brief_id}__production")
    rec["brain"] = run_engine(project, requested, brain=True, out_dir=out_dir,
                              name=f"{entry.brief_id}__brain")
    print(f"{entry.brief_id:20} {entry.family:22} (bbox) production={rec['production']['outcome']} "
          f"brain={rec['brain']['outcome']}", flush=True)
    return rec


def build_corpus(briefs):
    return [*corpus_mod.real_entries(briefs), *corpus_mod.FROZEN]


def main(argv: list[str]) -> None:
    out_dir = argv[0]
    wanted = set(argv[1:])
    os.makedirs(os.path.join(out_dir, "designs"), exist_ok=True)
    path = os.path.join(out_dir, "results.json")
    done = {r["brief"]: r for r in json.load(open(path))} if os.path.exists(path) else {}
    briefs = {b.brief_id: b for b in briefs_mod.select_briefs()}
    from app.ai_harness.shape_agnostic.run import CASES_PATH
    cases = {c["id"]: c for c in json.load(open(os.path.normpath(CASES_PATH)))["cases"]}
    for entry in build_corpus(briefs.values()):
        if wanted and entry.brief_id not in wanted:
            continue
        if entry.brief_id in done and not wanted:
            continue
        rec = (run_real(entry, briefs[entry.brief_id], out_dir) if entry.source == "real"
               else run_frozen(entry, cases[entry.brief_id], out_dir))
        done[entry.brief_id] = rec
        order = [e.brief_id for e in build_corpus(briefs.values())]
        json.dump([done[k] for k in order if k in done], open(path, "w"), indent=1, default=str)


if __name__ == "__main__":
    main(sys.argv[1:])
