"""#267 (ROOT #262) — the step-3 run: the ground-truth comparison.

    PYTHONPATH=backend python -m app.ai_harness.quantity_takeoff.run267 <out.json>

It runs the **same** harness, against the **same** 1923 reference quantities, with one thing
changed: the geometry now comes from the figured ground plan (Plate 8) instead of from the
plasterer's dimension columns. Nothing frozen is edited, no threshold is revised and the
self-validation guard is not weakened — this module only supplies a different input and records
what the instrument does with it.

What it writes out is the whole of step 3's evidence: comparison A per material with every metric
the directive lists, comparison B as a separate object that holds no number, the abstention and
failure rates, the manual-correction-effort counts, the provenance-completeness fractions, the
convention audit, the height evidence, the interpretation sensitivity, and the before/after of the
self-validation guard.
"""
from __future__ import annotations

import json
import sys

from app.ai_harness.quantity_takeoff import fletcher as FL
from app.ai_harness.quantity_takeoff import frozen as F
from app.ai_harness.quantity_takeoff import harness as H
from app.ai_harness.quantity_takeoff import plate8 as P8
from app.ai_harness.quantity_takeoff import selfcheck as SC
from app.ai_harness.quantity_takeoff.frozen import Material


def guard_before_and_after() -> dict:
    """The one measurement that says whether step 3 achieved anything at all.

    R2, the geometric-identity half of the guard, asks whether the reference carries information
    the supplied geometry does not. Against #265's geometry — the plasterer's own dimension
    columns — the answer was *no*, at a residual of exactly 0.0. Against Plate 8's figures it is
    *yes*. R1, the declared-class half, refuses both; that is this run's main finding and it is
    reported, not worked around.
    """
    rows = []
    for label, proj in (("#265: geometry from the takeoff's own dimension columns", FL.project()),
                        ("#267: geometry figured on Plate 8", P8.project())):
        report = H.evaluate([proj])
        js = H.to_json(report)
        resid = []
        for q in js["quantities"]:
            for c in q.get("comparisons", []):
                if c["identity_residual"] is not None:
                    resid.append({
                        "material": c["material"], "scope": c["scope"],
                        "computed": c["computed"], "reference": c["reference"],
                        "identity_residual": c["identity_residual"],
                        "identity_band": c["identity_band"],
                        "headroom_over_the_band": (c["identity_residual"] / c["identity_band"]
                                                   if c["identity_band"] else None),
                        "r2_refused_it_as_an_identity": any(
                            r["reason"] == "GEOMETRIC_IDENTITY" for r in c["refusals"]),
                        "r1_refusals": [r["reason"] for r in c["refusals"]
                                        if r["reason"] != "GEOMETRIC_IDENTITY"],
                    })
        rows.append({"arm": label,
                     "comparisons_with_a_computed_quantity": len(resid),
                     "detail": resid})
    return {
        "what_this_shows": (
            "R2 refused #265's three ceiling comparisons at a residual of EXACTLY 0.0 because the "
            "geometry and the reference were the same numbers. With the geometry taken off Plate "
            "8 instead, the one comparison the plate can close clears R2 by a wide margin. R1 "
            "still refuses it on the declared calculation class, which is a property of the "
            "instrument and not of the source."),
        "arms": rows,
    }


def main(out_path: str | None = None) -> dict:
    primary = H.evaluate([P8.project()])
    js = H.to_json(primary)
    refused = sum(mm["refused_comparisons"] for mm in js["comparison_a"]["per_material"].values())
    cross = sum(mm["cross_check_comparisons"] for mm in js["comparison_a"]["per_material"].values())
    acc = sum(mm["accuracy_comparisons"] for mm in js["comparison_a"]["per_material"].values())
    attempted = sum(mm["scopes_attempted"] for mm in js["comparison_a"]["per_material"].values())
    computed = sum(mm["computed"] for mm in js["comparison_a"]["per_material"].values())
    abstained = sum(mm["abstained"] for mm in js["comparison_a"]["per_material"].values())
    failed = sum(mm["failed"] for mm in js["comparison_a"]["per_material"].values())

    result: dict = {
        "issue": 267,
        "root": 262,
        "what_this_is": (
            "Step 3's comparison. The 1923 professional takeoff's quantities are scored against "
            "quantities computed from geometry taken off the FIGURED GROUND PLAN (Plate 8), "
            "independently of the dimension columns the takeoff was squared from. No threshold "
            "was revised, nothing frozen was edited and the self-validation guard was not "
            "weakened."),
        "correctness_note": F.SYNTHETIC_TESTS_ARE_CORRECTNESS_ONLY,
        "geometry_provenance": ("docs/reports/construction-intelligence/data/"
                                "plate8-ground-plan-geometry.json — one citation per figure, "
                                "naming the plate, the leaf and the pair of wall faces the figure "
                                "runs between"),
        "summary": {
            "rooms_in_the_takeoff": 3,
            "rooms_the_plate_could_close": 1,
            "scopes_attempted": attempted,
            "quantities_computed": computed,
            "quantities_abstained": abstained,
            "quantities_failed": failed,
            "reference_values_offered": js["projects"][0]["reference_values"],
            "comparisons_refused": refused,
            "comparisons_cross_check_only": cross,
            "comparisons_scored_as_accuracy": acc,
            "verdict_from_the_frozen_function": js["verdict"],
            "verdict_reason": js["verdict_reason"],
        },
        "self_validation_guard_before_and_after": guard_before_and_after(),
        "heights_are_figured_on_no_plate": P8.heights_are_figured_on_no_plate(),
        "interpretation_sensitivity": P8.interpretation_sensitivity(),
        "convention_audit": FL.convention_audit(),
        "comparison_b": {
            "status": F.COMPARISON_B_STATUS,
            "reason": F.COMPARISON_B_REASON,
            "note": ("reported here as its own object, exactly as the harness types it: there is "
                     "no field in it a number could be written into"),
        },
        "frozen_thresholds_as_applied": js["frozen_thresholds"],
        "report": js,
    }

    # The per-comparison detail, flattened, because three rooms is small enough to print whole.
    flat = []
    for q in js["quantities"]:
        for c in q.get("comparisons", []):
            flat.append({k: c[k] for k in (
                "material", "scope", "status", "computed", "reference", "absolute_error",
                "percentage_error", "within_tolerance", "identity_residual", "identity_band")}
                | {"refusals": [r["reason"] for r in c["refusals"]]})
    result["comparisons"] = flat

    # Abstentions, flattened the same way, because the abstention rate is a headline here.
    result["abstentions"] = [
        {"material": m, "scope": mm_row["scope"], "reason": mm_row["reason"],
         "missing_field": mm_row["field"]}
        for m, mm in js["comparison_a"]["per_material"].items()
        for mm_row in mm["missing_measurements"]
    ]
    result["manual_correction_effort"] = {
        m: {"per_field": mm["manual_correction_effort"],
            "total": mm["manual_correction_effort_total"]}
        for m, mm in js["comparison_a"]["per_material"].items()
    }
    result["unsupported_categories"] = {
        m: mm["unsupported_categories"] for m, mm in js["comparison_a"]["per_material"].items()
        if mm["unsupported_categories"]
    }

    if out_path:
        with open(out_path, "w") as fh:
            json.dump(result, fh, indent=1, sort_keys=False)
    return result


if __name__ == "__main__":
    r = main(sys.argv[1] if len(sys.argv) > 1 else None)
    print(json.dumps(r["summary"], indent=1))
    for c in r["comparisons"]:
        print(c["material"], c["scope"], c["status"], c["percentage_error"], c["refusals"])
    print("materials:")
    for m in Material:
        mm = r["report"]["comparison_a"]["per_material"][m.value]
        print(" ", m.value, "computed", mm["computed"], "abstained", mm["abstained"],
              "failed", mm["failed"], "abstention_rate", round(mm["abstention_rate"], 4),
              "passes", mm["passes"])
