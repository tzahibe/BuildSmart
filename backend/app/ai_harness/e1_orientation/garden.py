"""WHERE THE GARDEN ACTUALLY IS, per brief (E1 requirement 5).

The owner's instruction: *"Use the actual site geometry and garden orientation. Do not assume that
the rear of every building automatically represents the desired garden relationship."*

`site.classify_garden` returns up to four bands around the footprint — rear yard, two side yards,
and the front strip beside the parking. This measures them on the REAL site plan of the delivered
plan for each frozen brief, so the experiment knows, per brief, whether "garden" means the rear at
all. A brief whose dominant outdoor space is a side yard is one where a REAR_PUBLIC_BAND is the
wrong move, and E1 must say so rather than produce a plan facing the wrong way.

    PYTHONPATH=backend python -m app.ai_harness.e1_orientation.garden <out.json>
"""
from __future__ import annotations

import json
import sys

from app.ai_harness.topology_poc import briefs as briefs_mod
from app.demo import service as svc

BRIEFS = ("B08", "B20", "B02", "B11", "B16", "B19", "B06", "B09")

#: A band narrower than this cannot hold anything a room would want to face — it is a setback, not
#: a garden. One parking bay is 5 m deep; half of that is already a generous floor for "usable".
MIN_USABLE_DEPTH_M = 2.5


def _project_for(b):
    from tests.vertical_slice.test_hub_guard import _project
    return _project(dict(bedrooms=b.bedrooms, wet_rooms=b.wet_rooms, safe_room=b.safe_room,
                         open_plan=b.open_plan, built_area_m2=b.built_area_m2,
                         footprint_width_m=b.footprint_width_m,
                         footprint_depth_m=b.footprint_depth_m,
                         plot_width_m=b.footprint_width_m + 8,
                         plot_depth_m=b.footprint_depth_m + 8))


def classify_bands(design) -> dict:
    """Each garden band named by the side of the building it lies on, with its own depth."""
    fp = design.footprint
    fx0, fy0 = fp.x, fp.y
    fx1, fy1 = fp.x + fp.width_m, fp.y + fp.depth_m
    out = []
    for i, g in enumerate(design.garden):
        gx0, gy0 = g.x, g.y
        gx1, gy1 = g.x + g.width_m, g.y + g.depth_m
        if gy0 >= fy1 - 1e-6:
            side, depth = "REAR", gy1 - gy0            # south of the building
        elif gy1 <= fy0 + 1e-6:
            side, depth = "STREET", gy1 - gy0          # north, the setback/parking band
        elif gx1 <= fx0 + 1e-6:
            side, depth = "WEST", gx1 - gx0
        elif gx0 >= fx1 - 1e-6:
            side, depth = "EAST", gx1 - gx0
        else:
            side, depth = "CROOK", min(g.width_m, g.depth_m)
        out.append({"id": f"garden_{i}", "side": side, "depth_m": round(depth, 2),
                    "area_m2": round(g.width_m * g.depth_m, 2),
                    "frontage_m": round(g.width_m if side in ("REAR", "STREET") else g.depth_m, 2)})
    return out


def run_brief(bid: str) -> dict:
    b = {x.brief_id: x for x in briefs_mod.select_briefs()}[bid]
    result = svc.generate_demo_design(_project_for(b))
    design = result.design
    bands = classify_bands(design)
    usable = [x for x in bands if x["side"] != "STREET" and x["depth_m"] >= MIN_USABLE_DEPTH_M]
    rear = next((x for x in bands if x["side"] == "REAR"), None)
    dominant = max(usable, key=lambda x: x["area_m2"]) if usable else None
    return {
        "brief": bid,
        "plot": [design.plot.width_m, design.plot.depth_m],
        "footprint": [design.footprint.width_m, design.footprint.depth_m],
        "footprint_origin": [design.footprint.x, design.footprint.y],
        "bands": bands,
        "rear_depth_m": rear["depth_m"] if rear else 0.0,
        "rear_area_m2": rear["area_m2"] if rear else 0.0,
        "rear_is_usable": bool(rear and rear["depth_m"] >= MIN_USABLE_DEPTH_M),
        "dominant_usable_side": dominant["side"] if dominant else None,
        "dominant_area_m2": dominant["area_m2"] if dominant else 0.0,
        # The question E1 actually needs answered, per brief.
        "garden_orientation_is_rear": bool(dominant and dominant["side"] == "REAR"),
    }


def main(path: str) -> None:
    rows = []
    for bid in BRIEFS:
        try:
            rows.append(run_brief(bid))
        except Exception as exc:
            rows.append({"brief": bid, "error": f"{type(exc).__name__}: {exc}"})
        print(f"{bid}: {rows[-1].get('dominant_usable_side', rows[-1].get('error'))}", flush=True)
    with open(path, "w") as fh:
        json.dump(rows, fh, indent=2)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "garden.json")
