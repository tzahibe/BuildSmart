"""#265 — the runner.

    PYTHONPATH=backend python -m app.ai_harness.quantity_takeoff.run <out.json>

Runs the AC-5 demonstration: the repository's own 19 real plans, in both arms, with their own
`area_m2` offered as the reference for the two area materials. It produces no accuracy figure,
because there is nothing accuracy could be measured against -- `frozen.verdict` returns
NOT_EVALUABLE before examining anything, and every one of the 358 offered reference values is
refused.

Nothing in this module invents a reference value. If the only way to show a number were to
manufacture one, it shows no number.
"""
from __future__ import annotations

import json
import sys

from app.ai_harness.quantity_takeoff import fletcher as FL
from app.ai_harness.quantity_takeoff import frozen as F
from app.ai_harness.quantity_takeoff import harness as H
from app.ai_harness.quantity_takeoff import resplan as RP
from app.ai_harness.quantity_takeoff import selfcheck as SC
from app.ai_harness.quantity_takeoff.frozen import Material
from app.ai_harness.quantity_takeoff.schema import RoomGeometry


def identity_evidence() -> dict:
    """#263's measurement, re-measured here rather than quoted: the residual between every real
    room's stated `area_m2` and the shoelace area of its own polygon, against the frozen band."""
    plans = RP.load_real_plans()
    rows = []
    for pid, ref in sorted(plans.items()):
        for r in ref["rooms"]:
            stated = float(r["area_m2"])
            shoelace = RoomGeometry(tuple((float(x), float(y)) for x, y in r["polygon"])).area_m2()
            resid = abs(stated - shoelace)
            band = SC.identity_band(Material.FLOORING_AREA, stated)
            rows.append({"plan": pid, "room": r["id"], "stated_area_m2": stated,
                         "shoelace_area_m2": shoelace, "residual_m2": resid,
                         "identity_band_m2": band, "inside_band": resid <= band})
    worst = max(rows, key=lambda x: x["residual_m2"])
    return {
        "rooms": len(rows),
        "plans": len(plans),
        "max_residual_m2": worst["residual_m2"],
        "worst_room": {k: worst[k] for k in ("plan", "room", "stated_area_m2", "shoelace_area_m2")},
        "inside_band": sum(1 for r in rows if r["inside_band"]),
        "outside_band": sum(1 for r in rows if not r["inside_band"]),
        "frozen_band_rule": "max(IDENTITY_ABS_M2=0.01, IDENTITY_REL=0.0005 x |reference|)",
        "headroom_at_worst_room": (worst["identity_band_m2"] / worst["residual_m2"]
                                   if worst["residual_m2"] else None),
        "per_room": rows,
    }


def main(out_path: str | None = None) -> dict:
    result: dict = {
        "issue": 265,
        "root": 262,
        "what_this_is": (
            "The INSTRUMENT, not the measurement. #263 established that no reference quantity for "
            "flooring, ceiling paintable area, baseboard length or wall paintable area exists in "
            "public licensed form, so no accuracy figure is produced here and none could honestly "
            "be. This run is the AC-5 demonstration: the harness is handed the repository's own 19 "
            "real plans with their own area field offered as ground truth, and it declines."
        ),
        "correctness_note": F.SYNTHETIC_TESTS_ARE_CORRECTNESS_ONLY,
        "identity_evidence": identity_evidence(),
        "arms": {},
    }
    fl_report = H.evaluate([FL.project()])
    fl = H.to_json(fl_report)
    result["fletcher_1923"] = {
        "what_it_is": (
            "Banister Fletcher & H. P. Fletcher, Quantities, 9th ed. 1923, Chapter XXII, "
            "'Proposed Entrance Lodge' -- a professional plasterer's takeoff under CC Public "
            "Domain Mark 1.0. The first artefact in this work that carries a reference quantity "
            "for the materials under test."
        ),
        "what_it_validates": (
            "axes 2-5 of the owner's five: geometric calculation, material quantity, completeness "
            "of required inputs, and provenance/auditability -- and the CONVENTIONS and DEDUCTIONS "
            "better than anything else available, because they are written out on the page."
        ),
        "what_it_does_not_validate": (
            "AXIS 1, SOURCE MEASUREMENT ACCURACY. Nobody measured this lodge; it was never built. "
            "It is a designed exercise taken off by a professional. No public source anywhere "
            "measures a verified BUILT house, so axis 1 remains untestable and must be reported "
            "as such, separately, exactly as comparison B is."
        ),
        "summary": {
            "rooms": fl["projects"][0]["rooms"],
            "reference_values_offered": fl["projects"][0]["reference_values"],
            "comparisons_refused": sum(mm["refused_comparisons"]
                                       for mm in fl["comparison_a"]["per_material"].values()),
            "comparisons_cross_check_only": sum(mm["cross_check_comparisons"]
                                                for mm in fl["comparison_a"]["per_material"].values()),
            "comparisons_scored_as_accuracy": sum(mm["accuracy_comparisons"]
                                                  for mm in fl["comparison_a"]["per_material"].values()),
            "verdict": fl["verdict"],
            "verdict_reason": fl["verdict_reason"],
        },
        "convention_audit": FL.convention_audit(),
        "report": fl,
    }
    for arm in RP.ARMS:
        report = H.evaluate(RP.projects(arm))
        js = H.to_json(report)
        refused = sum(mm["refused_comparisons"] for mm in js["comparison_a"]["per_material"].values())
        cross = sum(mm["cross_check_comparisons"] for mm in js["comparison_a"]["per_material"].values())
        acc = sum(mm["accuracy_comparisons"] for mm in js["comparison_a"]["per_material"].values())
        result["arms"][arm] = {
            "summary": {
                "projects": len(js["projects"]),
                "reference_values_offered": sum(p["reference_values"] for p in js["projects"]),
                "comparisons_refused": refused,
                "comparisons_cross_check_only": cross,
                "comparisons_scored_as_accuracy": acc,
                "verdict": js["verdict"],
                "verdict_reason": js["verdict_reason"],
            },
            "report": js,
        }
    if out_path:
        with open(out_path, "w") as fh:
            json.dump(result, fh, indent=1, sort_keys=False)
    return result


if __name__ == "__main__":
    r = main(sys.argv[1] if len(sys.argv) > 1 else None)
    for arm, d in r["arms"].items():
        print(arm, json.dumps(d["summary"], indent=1))
    print("fletcher:", json.dumps(r["fletcher_1923"]["summary"], indent=1))
    print("identity:", json.dumps({k: v for k, v in r["identity_evidence"].items()
                                   if k != "per_room"}, indent=1))
