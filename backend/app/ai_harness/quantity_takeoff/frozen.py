"""#265 (ROOT #262) — everything FROZEN before any evaluation result was inspected.

This module is committed in a commit that **precedes** every results commit on this branch, so the
git history proves the order (AC-6). Nothing in it may be edited after a result exists: the
reliability grades, the convention choices, the abstention reason codes, the self-validation bands
and the per-material tolerances **are** the experiment. Widening a tolerance or relaxing a band to
make a number pass invalidates it; a refusal and an abstention are results.

The pattern is #242's R1 (`app/ai_harness/representation_ceiling/frozen.py`), deliberately.

Two measurements from #263 (PR #264) are load-bearing here and are restated as constants so a test
can assert them rather than trust the prose:

  * across all 179 real rooms in the repository's 19 ResPlan plans, the stated `area_m2` equals the
    shoelace area of the room's own polygon to 0.00061 m2 -- so that field is an identity, not a
    reference (IDENTITY_* below);
  * 0 of 20 fixtures carry a height, material, finish or paint field, and the one acquired model's
    `Volume / GrossArea` spans 2.045 m to 4.225 m on a single storey -- so a wall height is an input
    with provenance or it is absent, never a quotient (NO_HEIGHT_FROM_VOLUME below).
"""
from __future__ import annotations

from enum import Enum

# ===========================================================================================
# 1.  Reliability grades (#263 contract field V5) and what each may support
# ===========================================================================================


class Reliability(str, Enum):
    """#263 V5, verbatim. There is deliberately no grade between STATED and DERIVED, and no grade
    meaning "typical", "assumed", "default" or "industry standard": the directive forbids inferring
    heights, finish types and product coverage, and #263 recorded that a promoted default is not a
    provenance."""

    VERIFIED = "VERIFIED"
    """Independent physical measurement, or a professional takeoff signed by a third party."""
    STATED = "STATED"
    """The publisher asserts it, the method is documented, nobody checked it independently."""
    DERIVED = "DERIVED"
    """The publisher computed it from their own geometry. Cross-check only."""
    UNVERIFIED = "UNVERIFIED"
    """No method, or a method that cannot be established."""


#: Only these two may support an accuracy claim (#263 1.2 V5). DERIVED is usable as a cross-check
#: and must be reported as one; UNVERIFIED is usable for nothing.
ACCURACY_BEARING: frozenset[Reliability] = frozenset({Reliability.VERIFIED, Reliability.STATED})

#: Cross-check only -- a comparison may be computed and reported, labelled, but may not be
#: aggregated into an accuracy figure.
CROSS_CHECK_ONLY: frozenset[Reliability] = frozenset({Reliability.DERIVED})


class MeasurementMethod(str, Enum):
    """#263 V2, verbatim and closed. The two weakest members are named as weak here, in the type,
    rather than in a comment a caller can skip.

    There is no member for "computed from a volume", "scaled from a raster", "assumed" or
    "typical". A height recovered as volume/area has no member to declare itself under and
    therefore cannot enter the schema at all -- which is the point (#263's 2.045-4.225 m finding).
    """

    AS_BUILT_PHYSICAL_SURVEY = "AS_BUILT_PHYSICAL_SURVEY"
    INSTRUMENTED_SURVEY = "INSTRUMENTED_SURVEY"
    PROFESSIONAL_TAKEOFF = "PROFESSIONAL_TAKEOFF"
    DESIGN_DRAWING_DIMENSION = "DESIGN_DRAWING_DIMENSION"
    """Weaker: a design dimension is an intent, not a measurement (#263 V2)."""
    PUBLISHER_COMPUTED = "PUBLISHER_COMPUTED"
    """Weaker: the publisher computed it from their own model (#263 V2)."""


#: The methods #263 labels weaker. A value carrying one of these can never grade VERIFIED, and the
#: schema enforces that rather than asking the caller to remember it.
WEAKER_METHODS: frozenset[MeasurementMethod] = frozenset(
    {MeasurementMethod.DESIGN_DRAWING_DIMENSION, MeasurementMethod.PUBLISHER_COMPUTED}
)

#: A publisher-computed figure is, by #263 1.3 condition 2, a product of the same class of
#: calculation as the one under test whenever the quantity under test is of the same class. The
#: self-validation guard refuses it as ground truth; see `selfcheck.py`.
SAME_CLASS_METHODS: frozenset[MeasurementMethod] = frozenset({MeasurementMethod.PUBLISHER_COMPUTED})


class MeasurementConvention(str, Enum):
    """#263 P11's three admissible conventions, plus the explicit absence.

    UNSTATED is a value the schema must be able to carry, because #263 1.1 caps such a project at
    its 2 "tolerance-limited" grade rather than rejecting it. It is NOT a default: a project
    recorded UNSTATED can never support an accuracy claim (see `may_support_accuracy`).
    """

    INTERNAL_CLEAR = "INTERNAL_CLEAR"
    CENTRE_LINE = "CENTRE_LINE"
    EXTERNAL = "EXTERNAL"
    UNSTATED = "UNSTATED"


# ===========================================================================================
# 2.  The four materials, their units, and the calculation class each one is
# ===========================================================================================


class Material(str, Enum):
    FLOORING_AREA = "FLOORING_AREA"
    FLOORING_PURCHASE = "FLOORING_PURCHASE"
    WALL_PAINT_AREA = "WALL_PAINT_AREA"
    CEILING_PAINT_AREA = "CEILING_PAINT_AREA"
    BASEBOARD_LENGTH = "BASEBOARD_LENGTH"


UNITS: dict[Material, str] = {
    Material.FLOORING_AREA: "m2",
    Material.FLOORING_PURCHASE: "pack",
    Material.WALL_PAINT_AREA: "m2",
    Material.CEILING_PAINT_AREA: "m2",
    Material.BASEBOARD_LENGTH: "m",
}


class CalculationClass(str, Enum):
    """What kind of calculation each quantity IS. #263 1.3 condition 2 disqualifies a reference
    whose provenance makes it a product of the same class, so the class has to be a first-class
    value the guard can compare -- not a judgement a reader makes."""

    PLAN_POLYGON_AREA = "PLAN_POLYGON_AREA"
    PLAN_POLYGON_PERIMETER = "PLAN_POLYGON_PERIMETER"
    PERIMETER_TIMES_HEIGHT = "PERIMETER_TIMES_HEIGHT"
    AREA_TIMES_WASTAGE_OVER_PACK = "AREA_TIMES_WASTAGE_OVER_PACK"


CALCULATION_CLASS: dict[Material, CalculationClass] = {
    Material.FLOORING_AREA: CalculationClass.PLAN_POLYGON_AREA,
    Material.CEILING_PAINT_AREA: CalculationClass.PLAN_POLYGON_AREA,
    Material.BASEBOARD_LENGTH: CalculationClass.PLAN_POLYGON_PERIMETER,
    Material.WALL_PAINT_AREA: CalculationClass.PERIMETER_TIMES_HEIGHT,
    Material.FLOORING_PURCHASE: CalculationClass.AREA_TIMES_WASTAGE_OVER_PACK,
}

#: A per-room floor area stated by a publisher is a PLAN_POLYGON_AREA figure. Offering it as the
#: reference for FLOORING_AREA or CEILING_PAINT_AREA is "polygon area in, polygon area out".
#: This mapping is what `selfcheck.refuse_same_class` applies.
REFERENCE_VALUE_CLASS_CONFLICT: dict[CalculationClass, frozenset[CalculationClass]] = {
    CalculationClass.PLAN_POLYGON_AREA: frozenset({CalculationClass.PLAN_POLYGON_AREA}),
    CalculationClass.PLAN_POLYGON_PERIMETER: frozenset({CalculationClass.PLAN_POLYGON_PERIMETER}),
    CalculationClass.PERIMETER_TIMES_HEIGHT: frozenset(
        {CalculationClass.PERIMETER_TIMES_HEIGHT, CalculationClass.PLAN_POLYGON_PERIMETER}
    ),
    CalculationClass.AREA_TIMES_WASTAGE_OVER_PACK: frozenset(
        {CalculationClass.AREA_TIMES_WASTAGE_OVER_PACK, CalculationClass.PLAN_POLYGON_AREA}
    ),
}


# ===========================================================================================
# 3.  The self-validation bands -- the empirical half of the guard
# ===========================================================================================

#: #263's measurement, restated so a test asserts it: across all 179 real rooms of the 19 ResPlan
#: plans, |stated area_m2 - shoelace(own polygon)| never exceeds this.
RESPLAN_ROOMS = 179
RESPLAN_PLANS = 19
RESPLAN_MAX_AREA_RESIDUAL_M2 = 0.00061299

#: A reference value whose residual against the harness's own computation from the SAME supplied
#: geometry falls inside this band carries no information the geometry does not, whatever its
#: declared provenance says. The harness REFUSES it as an identity rather than scoring it.
#:
#: Justification. The band must sit far above the identity it has to catch and far below the
#: smallest discrepancy a genuine independent measurement could plausibly show.
#:   * above the identity: 0.0005% of a 42 m2 room is 0.021 m2, 34x #263's observed 0.00061 m2
#:     worst case, and the 0.01 m2 floor is 16x it for a small room where the relative term is
#:     tiny. Both of the 19 plans' terms clear the observation by more than an order of magnitude.
#:   * below a real discrepancy: public per-room areas are published to 0.01-0.1 m2, so two
#:     independent measurers of one room agree to the published rounding at best; a survey-vs-
#:     drawing comparison on one convention differs by of the order of 1%, which is 20x the
#:     relative term. A real reference has never been observed inside this band and an identity
#:     has never been observed outside it.
#: A residual of EXACTLY zero is an identity under any band and is refused unconditionally.
IDENTITY_ABS_M2 = 0.01
IDENTITY_ABS_M = 0.01
IDENTITY_REL = 0.0005

#: There is no way to turn a stated volume into a height. #263 measured Volume/GrossArea spanning
#: this interval across rooms on one storey of one real building, including 2.045 m for a bathroom
#: and 2.411 m for a kitchen. The schema has no field a quotient could enter under; this constant
#: exists so the report's claim and the test assert the same two numbers.
NO_HEIGHT_FROM_VOLUME = True
OBSERVED_VOLUME_OVER_AREA_SPAN_M = (2.045, 4.225)


# ===========================================================================================
# 4.  The convention choices -- frozen, and named as choices where contested
# ===========================================================================================

#: F1. Flooring is measured over the net internal floor area with no deduction for the footprint of
#: sanitary ware, built-in units or a chimney breast. CHOICE: SMM7/NRM2 practice makes no deduction
#: for a void of 0.50 m2 or less and no field in the schema states such a footprint; an alternative
#: convention deducts them. Bound: a shower tray or a chimney breast is 0.6-1.0 m2, so a bathroom's
#: flooring area can be overstated by up to ~1 m2 under this choice.
FLOORING_DEDUCTS_FIXTURE_FOOTPRINT = False

#: F1. Flooring is measured to the room face of the wall and is NOT carried through a door reveal.
#: CHOICE: the alternative adds door_width x wall_thickness per doorway. Bound: ~0.9 m x 0.1 m =
#: 0.09 m2 per door, so a 4-door dwelling understates by ~0.36 m2 under this choice.
FLOORING_INCLUDES_DOOR_REVEAL = False

#: F1. Purchase quantity rounds UP to whole packs. Not a choice: a pack is indivisible.
FLOORING_PURCHASE_ROUNDS_UP = True

#: F2. Wall paint is measured floor to ceiling and the skirting band is NOT deducted. CHOICE: IS
#: 1200 and common decorating practice measure the full height; an alternative deducts the skirting
#: band. Bound: 0.10 m of a 2.50 m height is 4.0% of the wall area -- LARGER than this material's
#: own tolerance, which is why a reference measured the other way cannot be absorbed and a project
#: whose convention is UNSTATED cannot support an accuracy claim for this material.
WALL_PAINT_DEDUCTS_SKIRTING_BAND = False

#: F2. Every opening with a stated area is deducted, whatever its size. CHOICE: SMM7 makes no
#: deduction for a void of 0.50 m2 or less; this harness deducts all of them, because #263's
#: contract field P9 requires opening areas to be stated by the source and discarding a stated
#: measurement to follow a rounding rule would make the result depend on the rule rather than the
#: measurement. Bound: on a door-sized 1.7 m2 opening the two conventions do not differ; they
#: differ only on small high-level windows and vents.
WALL_PAINT_DEDUCTS_EVERY_STATED_OPENING = True

#: F2. A room for which the source states no opening at all is computed with a zero deduction only
#: when the source's opening schedule is declared COMPLETE for the project. Otherwise F2 abstains:
#: "no openings listed" and "openings not listed" are different facts and conflating them is how a
#: missing deduction becomes a silent 10% error.
WALL_PAINT_REQUIRES_COMPLETE_OPENING_SCHEDULE = True

#: F3. The ceiling's paintable area equals the room's net plan area. ASSUMPTION, not a choice the
#: schema can check: the ceiling is flat, horizontal, coincident in plan with the floor, and
#: carries no dropped bulkhead or soffit. No plan-view field detects a slope or a bulkhead, so this
#: assumption is recorded on every F3 result and step 3 must state it next to any F3 figure.
#: Bound: a 30 degree monopitch understates by 15.5%; a 0.4 m bulkhead around a 14 m perimeter adds
#: 5.6 m2 of vertical face this formula does not count.
CEILING_IS_FLAT_AND_COINCIDENT_WITH_FLOOR = True

#: F3. A stated ceiling opening (skylight well, stair void) is deducted. Same reasoning as F2.
CEILING_DEDUCTS_EVERY_STATED_OPENING = True

#: F4. The skirting breaks at a door opening and the FULL stated structural opening width is
#: deducted. CHOICE: the alternatives deduct the leaf width only, or deduct nothing and let the
#: architrave absorb the run. Bound: an architrave is 60-80 mm each side, so ~0.15 m per doorway,
#: which on a 14 m perimeter is ~1.1% per door.
BASEBOARD_BREAKS_AT_DOOR_OPENINGS = True

#: F4. The skirting does not return into the door reveal. CHOICE: paired with the line above; the
#: two together are the one convention a reference must match.
BASEBOARD_RETURNS_INTO_REVEAL = False

#: F4. No deduction for built-in furniture, fitted wardrobes or kitchen units standing against a
#: wall. CHOICE forced by the schema: no #263 field states them, so there is nothing to deduct.
#: Bound: a 3 m wardrobe run is 21% of a 14 m perimeter, so this is the largest single unquantified
#: term in F4 and step 3 must say so wherever a bedroom or a kitchen is compared.
BASEBOARD_DEDUCTS_BUILT_IN_FURNITURE = False

#: F4. A cased opening or an archway with no leaf is a door opening for F4's purpose when the
#: source states its width. An access edge with no stated width makes F4 abstain -- it is not
#: treated as a solid wall.
BASEBOARD_TREATS_CASED_OPENINGS_AS_BREAKS = True


# ===========================================================================================
# 5.  The acceptance thresholds -- per material, with the justification beside each
# ===========================================================================================

#: Tolerance on the per-scope comparison, as a fraction of the reference value. A comparison is
#: WITHIN tolerance when |computed - reference| <= TOLERANCE_REL[material] * |reference|.
#:
#: Every number below is the sum of named, bounded terms. None of them is an industry round number
#: chosen because it looked reasonable, and none of them was chosen after a result was seen.
TOLERANCE_REL: dict[Material, float] = {
    # 2.0% = the drawing/scale term (~1%: a dimensioned drawing at a stated scale, and #263 P3
    # requires a MEASURED scale) doubled for headroom. The convention term is deliberately NOT in
    # this budget: internal-clear vs centre-line on a 3x4 m room with 0.10 m partitions differs by
    # ~12%, four times this tolerance, so it is handled by refusing the accuracy claim when P11 is
    # UNSTATED instead of by widening the tolerance to swallow it.
    Material.FLOORING_AREA: 0.020,
    # Same measurement, same budget: F3 reads the same plan polygon as F1.
    Material.CEILING_PAINT_AREA: 0.020,
    # 2.5% = the 2.0% plan term plus ~0.5-1.1% for the door-opening convention (an architrave is
    # ~0.15 m per doorway, ~1.1% of a 14 m perimeter). The built-in-furniture term is NOT in this
    # budget because it is unbounded by any schema field; it is reported, not absorbed.
    Material.BASEBOARD_LENGTH: 0.025,
    # 3.0% = the 2.0% perimeter term plus 1.0% for the stated height (25 mm on 2.50 m, a realistic
    # as-built variation across one room) ; the opening deduction is a stated measurement under P9
    # and contributes no budget of its own. The 4.0% skirting-band convention term is NOT in this
    # budget -- it is bigger than the tolerance, so a reference that does not state its convention
    # is refused the accuracy claim rather than compared loosely.
    Material.WALL_PAINT_AREA: 0.030,
    # 0% relative; see TOLERANCE_ABS. Pack count is deterministic integer arithmetic once area,
    # pack coverage and wastage are inputs, so any mismatch is a rule error, not measurement noise.
    Material.FLOORING_PURCHASE: 0.0,
}

#: Absolute floor on the tolerance, so a small room is not held to an unmeasurable band. Chosen as
#: the coarsest rounding public per-room figures are published at (0.1 m2 / 0.1 m), which is the
#: smallest difference a reference can even express. For FLOORING_PURCHASE it is 0: an exact
#: integer match is required.
TOLERANCE_ABS: dict[Material, float] = {
    Material.FLOORING_AREA: 0.10,
    Material.CEILING_PAINT_AREA: 0.10,
    Material.BASEBOARD_LENGTH: 0.10,
    Material.WALL_PAINT_AREA: 0.10,
    Material.FLOORING_PURCHASE: 0.0,
}

#: A percentage error is reported only where it is meaningful. Below this reference magnitude the
#: denominator dominates and the percentage is noise, so the absolute error is reported alone.
#: 1.0 m2 / 1.0 m is the smallest scope any of the four materials can have on a real room.
MIN_MEANINGFUL_DENOMINATOR: dict[Material, float] = {
    Material.FLOORING_AREA: 1.0,
    Material.CEILING_PAINT_AREA: 1.0,
    Material.BASEBOARD_LENGTH: 1.0,
    Material.WALL_PAINT_AREA: 1.0,
    Material.FLOORING_PURCHASE: 1.0,
}

#: A material PASSES on a project when at least this fraction of its accuracy-bearing comparisons
#: are within tolerance. 0.90 = one room in ten may be out, which is where a single mis-scheduled
#: opening or an unrecorded wardrobe lands; a lower bar would let a systematic convention error
#: pass as scatter.
MIN_WITHIN_TOLERANCE_RATE = 0.90

#: A material PASSES on a project only if at most this fraction of its scopes abstained. An
#: instrument that abstains on half a building is not usable even when everything it does compute
#: is right, and the directive asks for the abstention rate precisely so this cannot be hidden.
MAX_ABSTENTION_RATE = 0.25

#: Any failure -- an unexpected exception inside a formula -- fails the material on that project
#: outright. A formula that crashes is not an instrument.
MAX_FAILURE_RATE = 0.0

#: #263 1.4's minimum viable set, restated so step 3 cannot lower it after seeing results.
MIN_PROJECTS_WITH_HEIGHT = 3      # for the wall-paint claim (P8 + P9 present)
MIN_PROJECTS_WITHOUT_HEIGHT = 5   # for the other three materials
MIN_DISTINCT_PUBLISHERS = 2


class Verdict(str, Enum):
    GO = "GO"
    CONDITIONAL_GO = "CONDITIONAL_GO"
    NO_GO = "NO_GO"
    NOT_EVALUABLE = "NOT_EVALUABLE"


def verdict(
    *,
    projects_with_height: int,
    projects_without_height: int,
    distinct_publishers: int,
    materials_passing: int,
    materials_evaluated: int,
) -> tuple[Verdict, str]:
    """The bar step 3 APPLIES. It is frozen here, before any result exists, so that the words GO,
    CONDITIONAL GO and NO-GO cannot be redefined around a number once the number is known. Step 3
    may run this function and must not replace it.

    NOT_EVALUABLE comes first and is the expected outcome on today's data: #263 acquired zero
    VERIFIED or independently STATED reference quantities, so `materials_evaluated` is 0 and no
    accuracy figure may be reported at all. That is a finding, not a failure of this function.
    """
    if materials_evaluated == 0:
        return Verdict.NOT_EVALUABLE, (
            "no material has a single accuracy-bearing reference value: #263 acquired none, so no "
            "accuracy figure may be reported (ROOT #262 AC-2)"
        )
    if distinct_publishers < MIN_DISTINCT_PUBLISHERS:
        return Verdict.NOT_EVALUABLE, (
            f"{distinct_publishers} distinct publisher(s) < {MIN_DISTINCT_PUBLISHERS}: one "
            f"publisher's measurement convention cannot be mistaken for reality (#263 1.4)"
        )
    if projects_without_height < MIN_PROJECTS_WITHOUT_HEIGHT:
        return Verdict.NOT_EVALUABLE, (
            f"{projects_without_height} project(s) < {MIN_PROJECTS_WITHOUT_HEIGHT} for the three "
            f"materials that need no height (#263 1.4)"
        )
    if materials_passing == materials_evaluated and projects_with_height >= MIN_PROJECTS_WITH_HEIGHT:
        return Verdict.GO, (
            f"all {materials_evaluated} evaluated materials pass and {projects_with_height} "
            f"project(s) carry P8/P9, so the wall-paint claim is supported too"
        )
    if materials_passing >= 1:
        return Verdict.CONDITIONAL_GO, (
            f"{materials_passing} of {materials_evaluated} evaluated materials pass; the rest do "
            f"not, or the wall-paint evidence base is under {MIN_PROJECTS_WITH_HEIGHT} projects"
        )
    return Verdict.NO_GO, f"0 of {materials_evaluated} evaluated materials pass their frozen tolerance"


# ===========================================================================================
# 6.  Abstention and refusal reason codes
# ===========================================================================================


class AbstentionReason(str, Enum):
    """An abstention is a RESULT, not an exception (AC-3). Every code names the one input whose
    absence caused it, so the harness's manual-correction-effort metric is a count of these rather
    than an opinion."""

    FLOOR_AREA_NOT_STATED = "FLOOR_AREA_NOT_STATED"
    PERIMETER_NOT_AVAILABLE = "PERIMETER_NOT_AVAILABLE"
    WALL_HEIGHT_NOT_STATED = "WALL_HEIGHT_NOT_STATED"
    OPENING_AREA_NOT_STATED = "OPENING_AREA_NOT_STATED"
    OPENING_SCHEDULE_NOT_COMPLETE = "OPENING_SCHEDULE_NOT_COMPLETE"
    DOOR_WIDTH_NOT_STATED = "DOOR_WIDTH_NOT_STATED"
    PACK_COVERAGE_NOT_STATED = "PACK_COVERAGE_NOT_STATED"
    WASTAGE_ALLOWANCE_NOT_STATED = "WASTAGE_ALLOWANCE_NOT_STATED"
    FINISH_NOT_STATED = "FINISH_NOT_STATED"
    UNSUPPORTED_FINISH_CATEGORY = "UNSUPPORTED_FINISH_CATEGORY"
    PROVENANCE_INCOMPLETE = "PROVENANCE_INCOMPLETE"


class RefusalReason(str, Enum):
    """A refusal is about the REFERENCE value, not about the inputs. The harness declines to score
    itself against the figure; it still computes and reports the quantity (AC-5)."""

    SAME_CALCULATION_CLASS = "SAME_CALCULATION_CLASS"
    """#263 1.3 condition 2: the reference is a product of the calculation under test."""
    GEOMETRIC_IDENTITY = "GEOMETRIC_IDENTITY"
    """The reference sits inside the identity band against this harness's own figure from the same
    supplied geometry, whatever its declared provenance claims."""
    DERIVED_FROM_SUPPLIED_GEOMETRY = "DERIVED_FROM_SUPPLIED_GEOMETRY"
    """The reference value's own provenance says it was computed from the geometry supplied here."""
    NOT_INDEPENDENT = "NOT_INDEPENDENT"
    """#263 V6: the value does not carry an independence statement, or states it originates in
    BuildSmart or a BuildSmart-derived artifact."""
    NOT_ACCURACY_BEARING = "NOT_ACCURACY_BEARING"
    """V5 grades DERIVED or UNVERIFIED: cross-check only, never an accuracy claim."""
    CONVENTION_UNSTATED = "CONVENTION_UNSTATED"
    """#263 P11 is UNSTATED, so the comparison would measure the convention, not the engine."""


#: Comparison B's single fixed answer. #257 proved no plan or document ingestion exists anywhere in
#: the product or its history, so there are no automatically extracted measurements to compute
#: from. B is a separate output that reports this and carries no number -- never folded into A.
COMPARISON_B_STATUS = "NOT APPLICABLE"
COMPARISON_B_REASON = (
    "NOT APPLICABLE: comparison B scores quantities computed from AUTOMATICALLY EXTRACTED "
    "measurements, and #257 (PR #258) established that no plan or document ingestion capability "
    "exists -- no PDF, raster, OCR, DXF, DWG, IFC or SVG-parsing dependency on any of 71 branch "
    "tips or anywhere in history, and python-multipart is absent from the lockfile, so the service "
    "cannot physically accept an uploaded file. There is nothing to extract with, so B has no "
    "numerator and no denominator. It is reported separately and is never folded into A."
)

#: Said once, in the module the report cites: a unit test on synthetic geometry proves the formula
#: computes what it says it computes. It is CORRECTNESS. It is not accuracy, it is not evidence
#: about any real building, and no synthetic figure may appear in comparison A (ROOT #262 AC-2).
SYNTHETIC_TESTS_ARE_CORRECTNESS_ONLY = (
    "A unit test on synthetic geometry establishes CORRECTNESS -- that the formula computes the "
    "quantity it documents, with the deductions and conventions it documents. It establishes "
    "NOTHING about accuracy against a real building, and is never reported as accuracy."
)


def within_tolerance(material: Material, computed: float, reference: float) -> bool:
    """The frozen acceptance test, in one place so no caller can re-derive it differently."""
    err = abs(computed - reference)
    return err <= max(TOLERANCE_ABS[material], TOLERANCE_REL[material] * abs(reference))


def percentage_error(material: Material, computed: float, reference: float) -> float | None:
    """The percentage error, or None where the denominator makes it meaningless."""
    if abs(reference) < MIN_MEANINGFUL_DENOMINATOR[material]:
        return None
    return 100.0 * (computed - reference) / reference


def may_support_accuracy(reliability: Reliability, convention: MeasurementConvention) -> bool:
    """#263 1.2 V5 and 1.1 P11 together. Both gates, always both."""
    return reliability in ACCURACY_BEARING and convention is not MeasurementConvention.UNSTATED
