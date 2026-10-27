"""#265 — the self-validation guard (AC-5).

Two independent refusals. Either one alone is enough; the second exists because the first trusts a
declaration, and declarations are wrong.

**R1, the declared-provenance refusal.** The reference value says where it came from, and that can
disqualify it: #263 1.3 condition 2 (a product of the same class of calculation under test),
condition 4 (the scale, or the value, recoverable from the supplied geometry by construction), V6
(independence), V5 (grade) and P11 (convention).

**R2, the geometric-identity refusal.** Independent of every declaration: recompute the quantity
from the SUPPLIED geometry and compare it to the offered reference. Inside the frozen identity band
the reference carries no information the geometry does not, so it is refused -- whatever its
provenance claims. This is the guard that catches #263's measurement: across all 179 real rooms of
the repository's 19 ResPlan plans, the stated `area_m2` equals the shoelace area of the room's own
polygon to 0.00061299 m2, so scoring against it would report an identity as an accuracy.

The partition below is #263's own: its 1.3 conditions reject a candidate OUTRIGHT, while its 1.2
V5 grades DERIVED as usable "as a cross-check only". So a refusal is either `FATAL` (the value is
not evidence of anything and is dropped from both the accuracy figure and the cross-check) or
`CROSS_CHECK_ONLY` (the comparison is computed and reported, labelled, and never aggregated).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.ai_harness.quantity_takeoff import frozen as F
from app.ai_harness.quantity_takeoff.frozen import RefusalReason as R
from app.ai_harness.quantity_takeoff.schema import ReferenceProject, ReferenceValue

#: Tokens that make a V6 independence statement self-defeating. A reference value whose own
#: statement names this system is not independent of it.
NON_INDEPENDENT_TOKENS = ("buildsmart", "this system", "our own calculation", "the harness",
                          "sddproject")


class Severity(str, Enum):
    FATAL = "FATAL"
    """#263 1.3: rejected outright. Not an accuracy claim and not even a cross-check."""
    CROSS_CHECK_ONLY = "CROSS_CHECK_ONLY"
    """#263 1.2 V5 / 1.1 P11: reportable, labelled, never aggregated into an accuracy figure."""


SEVERITY: dict[R, Severity] = {
    R.SAME_CALCULATION_CLASS: Severity.FATAL,
    R.GEOMETRIC_IDENTITY: Severity.FATAL,
    R.DERIVED_FROM_SUPPLIED_GEOMETRY: Severity.FATAL,
    R.NOT_INDEPENDENT: Severity.FATAL,
    R.NOT_ACCURACY_BEARING: Severity.CROSS_CHECK_ONLY,
    R.CONVENTION_UNSTATED: Severity.CROSS_CHECK_ONLY,
}


@dataclass(frozen=True)
class Refusal:
    reason: R
    severity: Severity
    detail: str


def identity_band(material: F.Material, reference: float) -> float:
    """`max(absolute floor, relative term x |reference|)`, frozen before any result existed.

    Placed 34x above #263's observed 0.00061299 m2 worst case on a 42 m2 room and ~20x below the
    ~1% a survey-versus-drawing comparison on one convention shows.
    """
    floor = F.IDENTITY_ABS_M if F.UNITS[material] == "m" else F.IDENTITY_ABS_M2
    if F.UNITS[material] == "pack":
        return 0.0
    return max(floor, F.IDENTITY_REL * abs(reference))


def refuse_declared(project: ReferenceProject, ref: ReferenceValue) -> tuple[Refusal, ...]:
    """R1. Everything the value's own declarations disqualify it for."""
    out: list[Refusal] = []
    p = ref.provenance

    if ref.computed_from_supplied_geometry:
        out.append(Refusal(R.DERIVED_FROM_SUPPLIED_GEOMETRY, SEVERITY[R.DERIVED_FROM_SUPPLIED_GEOMETRY],
                           "the value declares it was computed from the geometry supplied in this "
                           "same project, so agreement would prove only that the arithmetic "
                           "inverted correctly (#263 1.3 condition 4)"))

    own = F.CALCULATION_CLASS[ref.material]
    conflicting = F.REFERENCE_VALUE_CLASS_CONFLICT[own]
    eff = ref.effective_class
    if eff is not None and eff in conflicting:
        out.append(Refusal(R.SAME_CALCULATION_CLASS, SEVERITY[R.SAME_CALCULATION_CLASS],
                           f"the reference is a {eff.value} figure and {ref.material.value} IS a "
                           f"{own.value} calculation: polygon in, polygon out (#263 1.3 condition "
                           f"2)" + ("" if ref.reference_class is not None else
                                    f" -- the class was not declared and was taken from the method "
                                    f"{p.method.value}")))

    low = p.independence.lower()
    if any(t in low for t in NON_INDEPENDENT_TOKENS):
        out.append(Refusal(R.NOT_INDEPENDENT, SEVERITY[R.NOT_INDEPENDENT],
                           f"the V6 independence statement names this system: {p.independence!r}"))

    if not p.may_support_accuracy_claim:
        out.append(Refusal(R.NOT_ACCURACY_BEARING, SEVERITY[R.NOT_ACCURACY_BEARING],
                           f"V5 grade {p.reliability.value}: only VERIFIED and STATED may support "
                           f"an accuracy claim (#263 1.2)"))

    if project.convention is F.MeasurementConvention.UNSTATED:
        out.append(Refusal(R.CONVENTION_UNSTATED, SEVERITY[R.CONVENTION_UNSTATED],
                           "P11 is UNSTATED: internal-clear versus centre-line on a 3x4 m room "
                           "with 0.10 m partitions differs by ~12%, four times the largest frozen "
                           "tolerance, so the comparison would measure the convention"))
    return tuple(out)


def refuse_identity(material: F.Material, reference: float,
                    computed_from_supplied_geometry: float | None) -> Refusal | None:
    """R2. The empirical half: does the reference carry any information the geometry does not?"""
    if computed_from_supplied_geometry is None:
        return None
    residual = abs(computed_from_supplied_geometry - reference)
    band = identity_band(material, reference)
    if residual == 0.0:
        return Refusal(R.GEOMETRIC_IDENTITY, SEVERITY[R.GEOMETRIC_IDENTITY],
                       "the reference is EXACTLY the figure this harness computes from the "
                       "supplied geometry: an identity under any band")
    if residual <= band:
        return Refusal(R.GEOMETRIC_IDENTITY, SEVERITY[R.GEOMETRIC_IDENTITY],
                       f"residual {residual:.8g} <= identity band {band:.8g}: the reference "
                       f"carries no information the supplied geometry does not, so scoring "
                       f"against it would report an identity as an accuracy")
    return None


def screen(project: ReferenceProject, ref: ReferenceValue,
           computed_from_supplied_geometry: float | None) -> tuple[Refusal, ...]:
    """Both halves, in one call. Empty means the comparison may support an accuracy claim."""
    out = list(refuse_declared(project, ref))
    r2 = refuse_identity(ref.material, ref.value, computed_from_supplied_geometry)
    if r2 is not None:
        out.append(r2)
    return tuple(out)


def worst(refusals: tuple[Refusal, ...]) -> Severity | None:
    if any(r.severity is Severity.FATAL for r in refusals):
        return Severity.FATAL
    if refusals:
        return Severity.CROSS_CHECK_ONLY
    return None
