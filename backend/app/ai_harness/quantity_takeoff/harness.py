"""#265 — the evaluation harness (AC-4).

Takes reference projects in the schema, computes what it can, abstains where it cannot, refuses
what it must not score itself against, and emits per material every metric ROOT #262's directive
lists.

**Comparison A and comparison B are separate output objects.** B carries no numerator, no
denominator and no metric dictionary: #257 established that no plan or document ingestion
capability exists anywhere in the product or its history, so there are no automatically extracted
measurements to compute from. Folding B into A is the failure the directive names by name, so the
two are different types here rather than two keys a caller might merge.

Nothing in this module is accuracy unless it survived `selfcheck`. A comparison that cleared fewer
than all three gates is still computed and reported, under `cross_check_only`, and is never
aggregated into an accuracy figure.
"""
from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from enum import Enum

from app.ai_harness.quantity_takeoff import formulas as FO
from app.ai_harness.quantity_takeoff import frozen as F
from app.ai_harness.quantity_takeoff import selfcheck as SC
from app.ai_harness.quantity_takeoff.frozen import Material
from app.ai_harness.quantity_takeoff.schema import (
    DOOR_KINDS,
    ReferenceProject,
    Surface,
)

#: Which #263 per-project fields each material needs, for the provenance-completeness metric.
#: "P1|P4" means either satisfies it.
REQUIRED_P_FIELDS: dict[Material, tuple[str, ...]] = {
    Material.FLOORING_AREA: ("P1|P4", "P2", "P3", "P10", "P11"),
    Material.FLOORING_PURCHASE: ("P1|P4", "P2", "P3", "P10", "P11", "L5:pack", "L5:wastage"),
    Material.CEILING_PAINT_AREA: ("P1|P4", "P2", "P3", "P10", "P11"),
    Material.BASEBOARD_LENGTH: ("P1|P5", "P2", "P3", "P6", "P11"),
    Material.WALL_PAINT_AREA: ("P1|P5", "P2", "P3", "P6", "P7", "P8", "P9", "P11"),
}


class ComparisonStatus(str, Enum):
    ACCURACY = "ACCURACY"
    """Cleared all three gates: V5 accuracy-bearing, P11 stated, and no refusal."""
    CROSS_CHECK_ONLY = "CROSS_CHECK_ONLY"
    REFUSED = "REFUSED"
    """#263 1.3: not evidence of anything. The quantity is still reported; the comparison is not."""


@dataclass(frozen=True)
class ScopeComparison:
    project_id: str
    material: Material
    scope: str
    unit: str
    status: ComparisonStatus
    computed: float | None
    reference: float | None
    absolute_error: float | None
    percentage_error: float | None
    """None where the reference is below `MIN_MEANINGFUL_DENOMINATOR`: the denominator dominates."""
    within_tolerance: bool | None
    refusals: tuple[dict, ...] = ()
    identity_residual: float | None = None
    identity_band: float | None = None


@dataclass
class MaterialMetrics:
    material: Material
    unit: str
    tolerance_rel: float
    tolerance_abs: float
    scopes_attempted: int = 0
    computed: int = 0
    abstained: int = 0
    failed: int = 0
    abstention_rate: float = 0.0
    failure_rate: float = 0.0
    accuracy_comparisons: int = 0
    cross_check_comparisons: int = 0
    refused_comparisons: int = 0
    mean_absolute_error: float | None = None
    max_absolute_error: float | None = None
    mean_percentage_error: float | None = None
    max_abs_percentage_error: float | None = None
    within_tolerance: int = 0
    within_tolerance_rate: float | None = None
    passes: bool | None = None
    """None means NOT EVALUABLE -- there is no accuracy-bearing comparison, so the question of
    passing does not arise. It is never silently False and never silently True."""
    missing_measurements: list[dict] = field(default_factory=list)
    unsupported_categories: list[dict] = field(default_factory=list)
    manual_correction_effort: dict[str, int] = field(default_factory=dict)
    manual_correction_effort_total: int = 0
    abstention_reasons: dict[str, int] = field(default_factory=dict)
    refusal_reasons: dict[str, int] = field(default_factory=dict)
    provenance_completeness: dict = field(default_factory=dict)


@dataclass
class ComparisonA:
    label: str = "A"
    description: str = ("quantities computed from VERIFIED INPUT MEASUREMENTS supplied in the "
                        "schema, scored against reference values that cleared all three gates")
    applicable: bool = True
    per_material: dict[str, MaterialMetrics] = field(default_factory=dict)


@dataclass(frozen=True)
class ComparisonB:
    """A different type from `ComparisonA`, on purpose: there is no field here a number could be
    written into, so B cannot be quietly folded into A."""

    label: str = "B"
    description: str = ("quantities computed from AUTOMATICALLY EXTRACTED measurements, scored "
                        "against the same reference values")
    applicable: bool = False
    status: str = F.COMPARISON_B_STATUS
    reason: str = F.COMPARISON_B_REASON


@dataclass
class HarnessReport:
    projects: list[dict] = field(default_factory=list)
    quantities: list[dict] = field(default_factory=list)
    comparison_a: ComparisonA = field(default_factory=ComparisonA)
    comparison_b: ComparisonB = field(default_factory=ComparisonB)
    verdict: str = ""
    verdict_reason: str = ""
    layer_1_source_measurement_accuracy: str = ""
    correctness_note: str = F.SYNTHETIC_TESTS_ARE_CORRECTNESS_ONLY
    frozen_thresholds: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- provenance completeness

def _p_field_present(project: ReferenceProject, room, token: str) -> bool:
    if token == "P1|P4":
        return room.polygon is not None or room.stated_area is not None
    if token == "P1|P5":
        return room.polygon is not None or room.stated_perimeter is not None
    if token == "P2":
        return bool(project.licence.strip())
    if token == "P3":
        return project.scale is not None
    if token == "P6":
        doors = [o for o in project.openings_of(room.id) if o.kind in DOOR_KINDS]
        return all(o.width is not None for o in doors)
    if token == "P7":
        wins = [o for o in project.openings_of(room.id) if o.surface is Surface.WALL
                and o.kind not in DOOR_KINDS]
        return all(o.width is not None and o.sill_height is not None and o.head_height is not None
                   for o in wins)
    if token == "P8":
        return room.wall_height is not None
    if token == "P9":
        walls = [o for o in project.openings_of(room.id) if o.surface is Surface.WALL]
        return project.opening_schedule_complete and all(o.area is not None for o in walls)
    if token == "P10":
        return bool(room.finishes)
    if token == "P11":
        return (project.wall_thickness is not None
                and project.convention is not F.MeasurementConvention.UNSTATED)
    if token == "L5:pack":
        f = room.finishes.get(Surface.FLOOR)
        spec = project.product_specs.get(str(f.value)) if f is not None else None
        return spec is not None and spec.pack_coverage_m2 is not None
    if token == "L5:wastage":
        f = room.finishes.get(Surface.FLOOR)
        spec = project.product_specs.get(str(f.value)) if f is not None else None
        return spec is not None and spec.wastage_fraction is not None
    raise ValueError(f"unknown provenance token {token!r}")


def provenance_completeness(project: ReferenceProject, material: Material) -> dict:
    """Two fractions, as the report's metric table says: the per-project P fields this material
    needs that are actually present with a provenance, and the state of the V fields over the
    project's reference values for it.

    V1-V6 are enforced by `Provenance.__post_init__`, so an incomplete one cannot be constructed;
    the informative figures are therefore how many reference values exist at all and what they are
    graded, which is what is reported here rather than a fraction that is 1.0 by construction.
    """
    tokens = REQUIRED_P_FIELDS[material]
    present = 0
    total = 0
    missing: dict[str, int] = {}
    for room in project.rooms:
        for tok in tokens:
            total += 1
            if _p_field_present(project, room, tok):
                present += 1
            else:
                missing[tok] = missing.get(tok, 0) + 1
    refs = [r for r in project.references if r.material is material]
    grades: dict[str, int] = {}
    weaker = 0
    for r in refs:
        grades[r.provenance.reliability.value] = grades.get(r.provenance.reliability.value, 0) + 1
        if r.provenance.method in F.WEAKER_METHODS:
            weaker += 1
    return {
        "p_fields_required": list(tokens),
        "p_field_slots": total,
        "p_field_slots_present": present,
        "p_fraction": (present / total) if total else None,
        "p_fields_missing_counts": missing,
        "reference_values": len(refs),
        "v_fields_per_value": 6,
        "v_fields_complete_fraction": 1.0 if refs else None,
        "v_fields_note": ("V1-V6 are enforced by the constructor, so an incomplete provenance "
                          "cannot exist; the informative figures are the count and the grades"),
        "v5_grades": grades,
        "v2_weaker_methods": weaker,
    }


# --------------------------------------------------------------------------- the run

def evaluate(projects: list[ReferenceProject]) -> HarnessReport:
    report = HarnessReport()
    report.frozen_thresholds = {
        "tolerance_rel": {m.value: v for m, v in F.TOLERANCE_REL.items()},
        "tolerance_abs": {m.value: v for m, v in F.TOLERANCE_ABS.items()},
        "min_within_tolerance_rate": F.MIN_WITHIN_TOLERANCE_RATE,
        "max_abstention_rate": F.MAX_ABSTENTION_RATE,
        "max_failure_rate": F.MAX_FAILURE_RATE,
        "identity_abs_m2": F.IDENTITY_ABS_M2,
        "identity_abs_m": F.IDENTITY_ABS_M,
        "identity_rel": F.IDENTITY_REL,
        "min_meaningful_denominator": {m.value: v for m, v in F.MIN_MEANINGFUL_DENOMINATOR.items()},
        "min_projects_with_height": F.MIN_PROJECTS_WITH_HEIGHT,
        "min_projects_without_height": F.MIN_PROJECTS_WITHOUT_HEIGHT,
        "min_distinct_publishers": F.MIN_DISTINCT_PUBLISHERS,
    }

    metrics: dict[Material, MaterialMetrics] = {
        m: MaterialMetrics(material=m, unit=F.UNITS[m], tolerance_rel=F.TOLERANCE_REL[m],
                           tolerance_abs=F.TOLERANCE_ABS[m])
        for m in Material
    }
    errors: dict[Material, list[float]] = {m: [] for m in Material}
    pcts: dict[Material, list[float]] = {m: [] for m in Material}

    for project in projects:
        report.projects.append({
            "project_id": project.project_id,
            "publisher": project.publisher,
            "licence": project.licence,
            "rooms": len(project.rooms),
            "openings": len(project.openings),
            "convention": project.convention.value,
            "opening_schedule_complete": project.opening_schedule_complete,
            "has_stated_scale": project.scale is not None,
            "has_wall_thickness": project.wall_thickness is not None,
            "rooms_with_stated_height": sum(1 for r in project.rooms if r.wall_height is not None),
            "reference_values": len(project.references),
        })
        for room in project.rooms:
            quantities = FO.compute_all(project, room)
            for material, q in quantities.items():
                mm = metrics[material]
                mm.scopes_attempted += 1
                if q.outcome is FO.Outcome.COMPUTED:
                    mm.computed += 1
                elif q.outcome is FO.Outcome.ABSTAINED:
                    mm.abstained += 1
                    key = q.reason.value if q.reason else "UNKNOWN"
                    mm.abstention_reasons[key] = mm.abstention_reasons.get(key, 0) + 1
                    mm.missing_measurements.append({
                        "project_id": project.project_id, "scope": q.scope,
                        "field": q.missing_field, "reason": key, "detail": q.reason_detail,
                    })
                    if q.missing_field:
                        mm.manual_correction_effort[q.missing_field] = (
                            mm.manual_correction_effort.get(q.missing_field, 0) + 1)
                    if q.reason is F.AbstentionReason.UNSUPPORTED_FINISH_CATEGORY:
                        mm.unsupported_categories.append({
                            "project_id": project.project_id, "scope": q.scope,
                            "category": q.missing_field, "detail": q.reason_detail})
                else:
                    mm.failed += 1

                report.quantities.append({
                    "project_id": project.project_id, "material": material.value,
                    "scope": q.scope, "outcome": q.outcome.value, "unit": q.unit,
                    "value": q.value, "reason": q.reason.value if q.reason else None,
                    "reason_detail": q.reason_detail, "missing_field": q.missing_field,
                    "conventions": list(q.conventions), "assumptions": list(q.assumptions),
                    "inputs_used": list(q.inputs_used), "workings": q.workings,
                })

                for ref in project.references_for(material, room.id):
                    refusals = SC.screen(project, ref, q.value if q.computed else None)
                    sev = SC.worst(refusals)
                    status = (ComparisonStatus.REFUSED if sev is SC.Severity.FATAL
                              else ComparisonStatus.CROSS_CHECK_ONLY if sev
                              else ComparisonStatus.ACCURACY)
                    band = SC.identity_band(material, ref.value)
                    resid = (abs(q.value - ref.value) if q.computed and q.value is not None
                             else None)
                    err = resid if q.computed else None
                    signed = ((q.value - ref.value) if q.computed and q.value is not None
                              else None)
                    pct = (F.percentage_error(material, q.value, ref.value)
                           if q.computed and q.value is not None else None)
                    wt = (F.within_tolerance(material, q.value, ref.value)
                          if q.computed and q.value is not None else None)
                    cmp_ = ScopeComparison(
                        project_id=project.project_id, material=material, scope=room.id,
                        unit=F.UNITS[material], status=status, computed=q.value,
                        reference=ref.value, absolute_error=signed, percentage_error=pct,
                        within_tolerance=wt,
                        refusals=tuple({"reason": r.reason.value, "severity": r.severity.value,
                                        "detail": r.detail} for r in refusals),
                        identity_residual=resid, identity_band=band)
                    for r in refusals:
                        mm.refusal_reasons[r.reason.value] = mm.refusal_reasons.get(r.reason.value, 0) + 1
                    if status is ComparisonStatus.REFUSED:
                        mm.refused_comparisons += 1
                    elif status is ComparisonStatus.CROSS_CHECK_ONLY:
                        mm.cross_check_comparisons += 1
                    else:
                        mm.accuracy_comparisons += 1
                        if err is not None:
                            errors[material].append(err)
                            if wt:
                                mm.within_tolerance += 1
                        if pct is not None:
                            pcts[material].append(pct)
                    report.quantities[-1].setdefault("comparisons", []).append(asdict(cmp_) | {
                        "material": material.value, "status": status.value})

    for m, mm in metrics.items():
        n = mm.scopes_attempted
        mm.abstention_rate = (mm.abstained / n) if n else 0.0
        mm.failure_rate = (mm.failed / n) if n else 0.0
        es = errors[m]
        if es:
            mm.mean_absolute_error = statistics.fmean(abs(e) for e in es)
            mm.max_absolute_error = max(abs(e) for e in es)
        ps = pcts[m]
        if ps:
            mm.mean_percentage_error = statistics.fmean(ps)
            mm.max_abs_percentage_error = max(abs(p) for p in ps)
        if mm.accuracy_comparisons:
            mm.within_tolerance_rate = mm.within_tolerance / mm.accuracy_comparisons
            mm.passes = bool(
                mm.within_tolerance_rate >= F.MIN_WITHIN_TOLERANCE_RATE
                and mm.abstention_rate <= F.MAX_ABSTENTION_RATE
                and mm.failure_rate <= F.MAX_FAILURE_RATE
            )
        else:
            mm.within_tolerance_rate = None
            mm.passes = None
        mm.manual_correction_effort_total = sum(mm.manual_correction_effort.values())
        mm.provenance_completeness = {
            p.project_id: provenance_completeness(p, m) for p in projects
        }
        report.comparison_a.per_material[m.value] = mm

    evaluated = sum(1 for mm in metrics.values() if mm.passes is not None)
    passing = sum(1 for mm in metrics.values() if mm.passes)
    with_h = sum(1 for p in projects if any(r.wall_height is not None for r in p.rooms))
    publishers = len({p.publisher for p in projects})
    v, why = F.verdict(projects_with_height=with_h, projects_without_height=len(projects),
                       distinct_publishers=publishers, materials_passing=passing,
                       materials_evaluated=evaluated)
    report.verdict, report.verdict_reason = v.value, why
    report.layer_1_source_measurement_accuracy = (
        "NOT TESTABLE: layer 1 asks whether the SOURCE's measurements are right, which needs an "
        "independent measurement of the same building. #263 acquired none, so this layer is "
        "unmeasurable today -- and together with comparison B that is two of the directive's five "
        "layers, which is itself a finding for the pivot."
    )
    return report


def to_json(report: HarnessReport) -> dict:
    d = asdict(report)
    d["comparison_a"]["per_material"] = {
        k: {kk: (vv.value if isinstance(vv, Enum) else vv) for kk, vv in v.items()}
        for k, v in d["comparison_a"]["per_material"].items()
    }
    return d
