"""Issue #223's before/after figure pair: ONE brief, drawn twice by the product's own renderer.

* `after`  — the parcel the person entered, carried through to the payload (this branch).
* `before` — the identical brief with `Programme.site_frame` forced to `None`, which is EXACTLY
  what `_build_site` received on `main`: no parcel, so a plot synthesised from the footprint plus
  a 2 m skirt, no parking, and a garden that is only the crook of a multi-wing footprint.

Both payloads come from the same `run_brain` call shape and the same `to_demo_design`, so the only
difference in the figures is the site. The brain's production sizer is used rather than the 30 s
exact sizer of `?engine=brain`: the SITE is what is being drawn, and it is identical either way.

Run from backend/:
    uv run python -m app.ai_harness.drawing_audit.figures_223 <out_dir>
then, from the repo root:
    DRAWING_AUDIT_DESIGNS_DIR=<out_dir>/designs DRAWING_AUDIT_SVG_DIR=<out_dir>/svg \
        npx vitest run src/design/drawing-audit-render.test.tsx --root frontend
    node backend/app/ai_harness/drawing_audit/rasterise.mjs <out_dir>/svg <out_dir>/png frontend
"""
from __future__ import annotations

import json
import os
import sys

from app.demo.contract import to_demo_design
from app.vertical_slice.brain import proposer
from app.vertical_slice.brain.runner import run_brain
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec

#: The brief of `tests/demo/test_site_from_brief.py`, so the figures and the tests describe the
#: same house on the same land: 23 x 20 m of parcel, a 15 x 12 m outline, two bays asked for.
PLOT_W_M, PLOT_D_M = 23.0, 20.0
OUTLINE = (15.0, 12.0)
SPEC = ArchitecturalSpec(
    plot=PlotSpec(width_m=PLOT_W_M, depth_m=PLOT_D_M, front_setback_m=0.0, side_setback_m=0.0,
                  rear_setback_m=0.0),
    program=ProgramSpec(bedrooms=3, safe_room=False, wet_rooms=2, parking_spaces=2,
                        target_built_area_m2=180.0),
)


def _first_payload(with_parcel: bool):
    real = proposer.site_frame_for
    if not with_parcel:
        proposer.site_frame_for = lambda spec: None
    try:
        res = run_brain(SPEC, OUTLINE, brief="DRAWING-site-parcel")
    finally:
        proposer.site_frame_for = real
    if not res.distinct:
        raise SystemExit("the brain planned nothing for this brief")
    plan = res.distinct[0]
    return plan, to_demo_design(plan.realized.design, plan.realized.report)


def main(out_dir: str) -> None:
    designs = os.path.join(out_dir, "designs")
    os.makedirs(designs, exist_ok=True)
    facts = {}
    for name, with_parcel in (("site-parcel__before", False), ("site-parcel__after", True)):
        plan, payload = _first_payload(with_parcel)
        with open(os.path.join(designs, f"{name}.json"), "w") as fh:
            json.dump(payload.model_dump(mode="json"), fh)
        facts[name] = {
            "parti": plan.parti,
            "plot_m": [payload.plot.width_m, payload.plot.depth_m],
            "plot_area_m2": round(payload.plot.width_m * payload.plot.depth_m, 1),
            "footprint_m": [payload.footprint.x, payload.footprint.y,
                            payload.footprint.width_m, payload.footprint.depth_m],
            "parking_bays": len(payload.parking),
            "garden_regions": len(payload.garden),
            "garden_m2": round(sum(g.width_m * g.depth_m for g in payload.garden), 1),
            "site_warnings": [w for w in payload.validation.warnings if "מגרש" in w],
        }
    facts["brief"] = {"plot_m": [PLOT_W_M, PLOT_D_M], "outline_m": list(OUTLINE),
                      "parking_spaces": SPEC.program.parking_spaces}
    with open(os.path.join(out_dir, "figure-facts.json"), "w") as fh:
        json.dump(facts, fh, indent=1, ensure_ascii=False)
    print(json.dumps(facts, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/figures-223")
