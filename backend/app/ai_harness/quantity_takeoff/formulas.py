"""#265 — the four quantity formulas (AC-2), and abstention as a first-class outcome (AC-3).

Layer 4. Each formula reads layer 3 (`RoomGeometry`) and provenance-carrying inputs, and nothing
else; none of them touches a polygon except through `RoomGeometry`. No formula raises on a missing
input: it returns a `Quantity` whose outcome is `ABSTAINED` and whose reason names the ONE field
whose absence caused it. `FAILED` exists only for an unexpected exception, so the failure rate and
the abstention rate stay separately countable.

The conventions and assumptions of every formula live in `frozen.py` and are copied onto EVERY
result, so no figure ever travels without them. The report's section 3 states them in prose; this
module states them in code; `frozen.py` holds the switch. All three say the same thing.

No generator validator is imported here, by this module or by any other module in this package.
#242's R1 measured why: they refused a policy condition unrelated to geometry in 18 of 19 real
plans, so they encode what the generator may build rather than what a building is.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from app.ai_harness.quantity_takeoff import frozen as F
from app.ai_harness.quantity_takeoff.frozen import AbstentionReason as A
from app.ai_harness.quantity_takeoff.frozen import Material
from app.ai_harness.quantity_takeoff.schema import (
    DOOR_KINDS,
    OpeningKind,
    ProductSpec,
    ReferenceProject,
    RoomRecord,
    Surface,
)


class Outcome(str, Enum):
    COMPUTED = "COMPUTED"
    ABSTAINED = "ABSTAINED"
    """A first-class RESULT, not an exception and never an estimate (AC-3)."""
    FAILED = "FAILED"
    """An unexpected exception inside a formula. Counted separately from an abstention."""


@dataclass(frozen=True)
class Quantity:
    material: Material
    scope: str
    outcome: Outcome
    unit: str
    value: float | None = None
    conventions: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    inputs_used: tuple[str, ...] = ()
    reason: A | None = None
    reason_detail: str = ""
    missing_field: str | None = None
    """For the manual-correction-effort metric: the one provenance-carrying input a human would
    have to supply to turn this abstention into a computation."""
    workings: dict[str, float] = field(default_factory=dict)
    """The intermediate terms, so a disagreement is locatable: area, perimeter, height, deductions."""

    @property
    def computed(self) -> bool:
        return self.outcome is Outcome.COMPUTED


def _abstain(material: Material, scope: str, reason: A, detail: str,
             missing_field: str | None) -> Quantity:
    return Quantity(material=material, scope=scope, outcome=Outcome.ABSTAINED,
                    unit=F.UNITS[material], reason=reason, reason_detail=detail,
                    missing_field=missing_field)


# --------------------------------------------------------------------------- shared input reads

def _area_m2(room: RoomRecord) -> tuple[float | None, str]:
    """The room's net plan area and where it came from. The POLYGON is preferred when present: it
    is the geometry the harness is being tested on, and using the source's own stated area as the
    harness's answer would make the comparison compare a number with itself."""
    g = room.geometry
    if g is not None:
        return g.area_m2(), "P1 polygon (shoelace, layer 3)"
    if room.stated_area is not None:
        return float(room.stated_area.value), "P4 stated area"
    return None, ""


def _perimeter_m(room: RoomRecord) -> tuple[float | None, str]:
    g = room.geometry
    if g is not None:
        return g.perimeter_m(), "P1 polygon (layer 3)"
    if room.stated_perimeter is not None:
        return float(room.stated_perimeter.value), "P5 stated perimeter"
    return None, ""


def _finish(room: RoomRecord, surface: Surface) -> str | None:
    m = room.finishes.get(surface)
    return None if m is None else str(m.value)


# --------------------------------------------------------------------------- F1 flooring

F1_CONVENTIONS = (
    f"FLOORING_DEDUCTS_FIXTURE_FOOTPRINT={F.FLOORING_DEDUCTS_FIXTURE_FOOTPRINT} (CHOICE: SMM7/NRM2 "
    "make no deduction for a void <= 0.50 m2 and no schema field states a fixture footprint; the "
    "alternative deducts them. Bound: a shower tray or chimney breast is 0.6-1.0 m2)",
    f"FLOORING_INCLUDES_DOOR_REVEAL={F.FLOORING_INCLUDES_DOOR_REVEAL} (CHOICE: measured to the room "
    "face of the wall, not carried under the leaf. Bound: ~0.09 m2 per doorway)",
)
F1_ASSUMPTIONS = (
    "the floor is a single horizontal plane coincident with the room's plan outline; a split level "
    "or a stepped floor is not detectable from any schema field",
    "the measurement convention is whatever P11 states; a comparison across two conventions "
    "measures the convention, not the engine, which is why an UNSTATED P11 is refused the "
    "accuracy claim rather than compared loosely",
)
F1Q_CONVENTIONS = (
    f"FLOORING_PURCHASE_ROUNDS_UP={F.FLOORING_PURCHASE_ROUNDS_UP} (not a choice: a pack is "
    "indivisible)",
)
F1Q_ASSUMPTIONS = (
    "the wastage allowance is AN INPUT, NOT A GUESS: it varies with the pattern, the laying "
    "direction and the room's shape, and no schema field determines it. Absent => abstain",
    "one finish per room; a room with two floor finishes has two quantities and the schema would "
    "have to carry two scopes for it",
)


def flooring_area(project: ReferenceProject, room: RoomRecord) -> Quantity:
    """F1a. `net_floor_area = area(room polygon) or stated_area` [m2]. No deductions."""
    m = Material.FLOORING_AREA
    area, src = _area_m2(room)
    if area is None:
        return _abstain(m, room.id, A.FLOOR_AREA_NOT_STATED,
                        "the room carries neither a P1 polygon nor a P4 stated area",
                        f"rooms[{room.id}].polygon or .stated_area")
    if project.distinguishes_finishes and _finish(room, Surface.FLOOR) is None:
        return _abstain(m, room.id, A.FINISH_NOT_STATED,
                        "the project distinguishes finishes per surface (P10) but this room's "
                        "floor finish is not stated, so 'the flooring area' has no referent",
                        f"rooms[{room.id}].finishes[FLOOR]")
    return Quantity(material=m, scope=room.id, outcome=Outcome.COMPUTED, unit=F.UNITS[m],
                    value=area, conventions=F1_CONVENTIONS, assumptions=F1_ASSUMPTIONS,
                    inputs_used=(src, f"P11 convention={project.convention.value}"),
                    workings={"net_floor_area_m2": area})


def flooring_purchase(project: ReferenceProject, room: RoomRecord,
                      area_q: Quantity | None = None) -> Quantity:
    """F1b. `packs = ceil(net_floor_area * (1 + wastage) / pack_coverage)` [pack].

    Separate from F1a on purpose: a missing product field must never cost the geometry.
    """
    m = Material.FLOORING_PURCHASE
    area_q = area_q if area_q is not None else flooring_area(project, room)
    if not area_q.computed:
        return _abstain(m, room.id, area_q.reason or A.FLOOR_AREA_NOT_STATED,
                        f"the flooring area abstained: {area_q.reason_detail}", area_q.missing_field)
    finish = _finish(room, Surface.FLOOR)
    if finish is None:
        return _abstain(m, room.id, A.FINISH_NOT_STATED,
                        "P10 does not state this room's floor finish, so there is no product and "
                        "therefore no pack size; a purchase quantity without a product is a guess",
                        f"rooms[{room.id}].finishes[FLOOR]")
    spec: ProductSpec | None = project.product_specs.get(finish)
    if spec is None:
        # An UNSUPPORTED CATEGORY, not a missing field: the harness has reached a finish for which
        # it holds no product convention at all. The directive asks for this count separately.
        return _abstain(m, room.id, A.UNSUPPORTED_FINISH_CATEGORY,
                        f"no layer-5 ProductSpec is supplied for the floor finish {finish!r}, so "
                        "there is no pack size to divide by and no pack convention for the "
                        "category",
                        f"product_specs[{finish!r}]")
    if spec.pack_coverage_m2 is None:
        return _abstain(m, room.id, A.PACK_COVERAGE_NOT_STATED,
                        f"ProductSpec({spec.finish_category}) carries no pack coverage",
                        f"product_specs[{spec.finish_category}].pack_coverage_m2")
    if spec.wastage_fraction is None:
        return _abstain(m, room.id, A.WASTAGE_ALLOWANCE_NOT_STATED,
                        "the wastage allowance is an input, not a guess (this Issue's words): "
                        f"ProductSpec({spec.finish_category}) carries none",
                        f"product_specs[{spec.finish_category}].wastage_fraction")
    cov = float(spec.pack_coverage_m2.value)
    if cov <= 0:
        return _abstain(m, room.id, A.PACK_COVERAGE_NOT_STATED,
                        f"pack coverage {cov} is not a positive area",
                        f"product_specs[{spec.finish_category}].pack_coverage_m2")
    waste = float(spec.wastage_fraction.value)
    needed = float(area_q.value) * (1.0 + waste)
    packs = math.ceil(needed / cov)
    return Quantity(material=m, scope=room.id, outcome=Outcome.COMPUTED, unit=F.UNITS[m],
                    value=float(packs), conventions=F1Q_CONVENTIONS, assumptions=F1Q_ASSUMPTIONS,
                    inputs_used=(f"F1a area {area_q.value:.4f} m2",
                                 f"P10 finish={finish}",
                                 f"layer 5 pack_coverage_m2={cov}",
                                 f"layer 5 wastage_fraction={waste}"),
                    workings={"net_floor_area_m2": float(area_q.value),
                              "wastage_fraction": waste, "area_with_wastage_m2": needed,
                              "pack_coverage_m2": cov, "packs": float(packs)})


# --------------------------------------------------------------------------- F2 wall paint

F2_CONVENTIONS = (
    f"WALL_PAINT_DEDUCTS_SKIRTING_BAND={F.WALL_PAINT_DEDUCTS_SKIRTING_BAND} (CHOICE, and the "
    "largest one: IS 1200 and common decorating practice measure floor to ceiling. Bound: 0.10 m "
    "of a 2.50 m height is 4.0% of the wall area, LARGER than this material's 3.0% tolerance)",
    f"WALL_PAINT_DEDUCTS_EVERY_STATED_OPENING={F.WALL_PAINT_DEDUCTS_EVERY_STATED_OPENING} (CHOICE: "
    "SMM7 makes no deduction for a void <= 0.50 m2; this harness deducts every opening whose area "
    "P9 states, because discarding a stated measurement to follow a rounding rule makes the answer "
    "depend on the rule rather than on the measurement)",
    f"WALL_PAINT_REQUIRES_COMPLETE_OPENING_SCHEDULE={F.WALL_PAINT_REQUIRES_COMPLETE_OPENING_SCHEDULE}"
    " (not a choice: 'no openings listed' and 'openings not listed' are different facts)",
)
F2_ASSUMPTIONS = (
    "THE HEIGHT IS NEVER INFERRED. Not from a volume (#263 measured Volume/GrossArea at 2.045 m for "
    "a bathroom and 2.411 m for a kitchen on the SAME storey, spanning 2.045-4.225 m across the "
    "building), not from a storey count, not from a regional norm. Absent => abstain",
    "the walls are vertical, plane and of one height around the room, so the plan perimeter is the "
    "perimeter at every height; a rake, a vault or a dropped head breaks this and no schema field "
    "detects any of them",
    "the paintable surface is the whole wall minus the stated openings: no deduction for a fitted "
    "wardrobe or a tiled splashback, because no #263 field states either. In a wet room this is "
    "the dominant unquantified term",
)


def wall_paint_area(project: ReferenceProject, room: RoomRecord) -> Quantity:
    """F2. `paintable = perimeter * wall_height - sum(stated areas of this room's wall openings)`."""
    m = Material.WALL_PAINT_AREA
    per, src = _perimeter_m(room)
    if per is None:
        return _abstain(m, room.id, A.PERIMETER_NOT_AVAILABLE,
                        "the room carries neither a P1 polygon nor a P5 stated perimeter",
                        f"rooms[{room.id}].polygon or .stated_perimeter")
    if room.wall_height is None:
        return _abstain(m, room.id, A.WALL_HEIGHT_NOT_STATED,
                        "P8 wall height is not stated by the source. ROOT #262 AC-4 forbids "
                        "inferring it and #263 measured why a volume cannot supply it: "
                        "Volume/GrossArea spans 2.045-4.225 m on one storey",
                        f"rooms[{room.id}].wall_height")
    if project.distinguishes_finishes and _finish(room, Surface.WALL) is None:
        return _abstain(m, room.id, A.FINISH_NOT_STATED,
                        "the project distinguishes finishes (P10) but this room's wall finish is "
                        "not stated", f"rooms[{room.id}].finishes[WALL]")
    wall_openings = tuple(o for o in project.openings_of(room.id) if o.surface is Surface.WALL)
    if not project.opening_schedule_complete:
        return _abstain(m, room.id, A.OPENING_SCHEDULE_NOT_COMPLETE,
                        "the source does not declare its opening schedule complete, so a zero "
                        "deduction would be an assumption rather than a measurement; a missing "
                        "door is a silent ~10% overstatement",
                        "opening_schedule_complete")
    missing = [o.id for o in wall_openings if o.area is None]
    if missing:
        return _abstain(m, room.id, A.OPENING_AREA_NOT_STATED,
                        f"P9 opening area is not stated for {missing}; a partial deduction is not "
                        "a defensible quantity, and an area assembled from a plan-view width and "
                        "an assumed height is the inference AC-4 forbids",
                        f"openings[{missing[0]}].area")
    height = float(room.wall_height.value)
    gross = per * height
    ded = sum(float(o.area.value) for o in wall_openings if o.area is not None)
    return Quantity(material=m, scope=room.id, outcome=Outcome.COMPUTED, unit=F.UNITS[m],
                    value=gross - ded, conventions=F2_CONVENTIONS, assumptions=F2_ASSUMPTIONS,
                    inputs_used=(src, f"P8 wall_height={height} ({room.wall_height.provenance.method.value})",
                                 f"P9 {len(wall_openings)} stated opening area(s)",
                                 f"P11 convention={project.convention.value}"),
                    workings={"perimeter_m": per, "wall_height_m": height,
                              "gross_wall_area_m2": gross, "opening_deduction_m2": ded,
                              "openings": float(len(wall_openings))})


# --------------------------------------------------------------------------- F3 ceiling paint

F3_CONVENTIONS = (
    f"CEILING_DEDUCTS_EVERY_STATED_OPENING={F.CEILING_DEDUCTS_EVERY_STATED_OPENING} (same reasoning "
    "as F2: a stated measurement is not discarded to follow a rounding rule)",
)
F3_ASSUMPTIONS = (
    f"CEILING_IS_FLAT_AND_COINCIDENT_WITH_FLOOR={F.CEILING_IS_FLAT_AND_COINCIDENT_WITH_FLOOR}. THE "
    "ASSUMPTION THAT MATTERS, AND IT IS NOT CHECKABLE: no plan-view field detects a slope, a vault "
    "or a dropped bulkhead, and #263's contract has no field for a ceiling form, so this cannot be "
    "made an input without inventing a field the contract never required. Bound: a 30 degree "
    "monopitch understates the developed area by 15.5%; a 0.4 m bulkhead around a 14 m perimeter "
    "adds 5.6 m2 of vertical face this formula does not count. Both exceed F3's 2.0% tolerance by "
    "an order of magnitude",
    "ceiling paint covers the whole soffit: no deduction for a light fitting or a grille",
)


def ceiling_paint_area(project: ReferenceProject, room: RoomRecord) -> Quantity:
    """F3. `ceiling_paintable = net_floor_area - sum(stated CEILING opening areas)` [m2]."""
    m = Material.CEILING_PAINT_AREA
    area, src = _area_m2(room)
    if area is None:
        return _abstain(m, room.id, A.FLOOR_AREA_NOT_STATED,
                        "the room carries neither a P1 polygon nor a P4 stated area, and the "
                        "ceiling's plan area is the floor's",
                        f"rooms[{room.id}].polygon or .stated_area")
    if project.distinguishes_finishes and _finish(room, Surface.CEILING) is None:
        return _abstain(m, room.id, A.FINISH_NOT_STATED,
                        "the project distinguishes finishes (P10) but this room's ceiling finish "
                        "is not stated", f"rooms[{room.id}].finishes[CEILING]")
    ceil_openings = tuple(o for o in project.openings_of(room.id)
                          if o.surface is Surface.CEILING or o.kind is OpeningKind.CEILING_OPENING)
    missing = [o.id for o in ceil_openings if o.area is None]
    if missing:
        return _abstain(m, room.id, A.OPENING_AREA_NOT_STATED,
                        f"a ceiling opening is listed for this room but P9 states no area for "
                        f"{missing}", f"openings[{missing[0]}].area")
    ded = sum(float(o.area.value) for o in ceil_openings if o.area is not None)
    return Quantity(material=m, scope=room.id, outcome=Outcome.COMPUTED, unit=F.UNITS[m],
                    value=area - ded, conventions=F3_CONVENTIONS, assumptions=F3_ASSUMPTIONS,
                    inputs_used=(src, f"{len(ceil_openings)} stated ceiling opening(s)",
                                 f"P11 convention={project.convention.value}"),
                    workings={"net_plan_area_m2": area, "ceiling_opening_deduction_m2": ded})


# --------------------------------------------------------------------------- F4 baseboard

F4_CONVENTIONS = (
    f"BASEBOARD_BREAKS_AT_DOOR_OPENINGS={F.BASEBOARD_BREAKS_AT_DOOR_OPENINGS} with the FULL stated "
    "structural opening width (CHOICE: the alternatives deduct the leaf width only, or deduct "
    "nothing and let the architrave absorb the run. Bound: ~0.15 m per doorway, ~1.1% of a 14 m "
    "perimeter per door)",
    f"BASEBOARD_RETURNS_INTO_REVEAL={F.BASEBOARD_RETURNS_INTO_REVEAL} (CHOICE, paired with the line "
    "above; the two together are the one convention a reference takeoff must match)",
    f"BASEBOARD_DEDUCTS_BUILT_IN_FURNITURE={F.BASEBOARD_DEDUCTS_BUILT_IN_FURNITURE} (CHOICE FORCED "
    "BY THE SCHEMA: no #263 field states a fitted wardrobe or a kitchen unit run. Bound: a 3 m "
    "wardrobe run is 21% of a 14 m perimeter -- the largest single unquantified term in any of the "
    "four formulas, and deliberately NOT inside F4's tolerance budget)",
    f"BASEBOARD_TREATS_CASED_OPENINGS_AS_BREAKS={F.BASEBOARD_TREATS_CASED_OPENINGS_AS_BREAKS} (an "
    "archway with a stated width is a break; an access edge with NO stated width makes F4 abstain "
    "rather than be silently treated as solid wall)",
)
F4_ASSUMPTIONS = (
    "the skirting runs around the full room perimeter at floor level and the plan perimeter is its "
    "run; a bay, a niche or a curved wall measured as a chord is understated",
    "every door opening of the room is listed. An unlisted door is an undeducted break and the "
    "error is invisible and one-directional, which is why a missing width abstains",
)


def baseboard_length(project: ReferenceProject, room: RoomRecord) -> Quantity:
    """F4. `baseboard = perimeter - sum(stated widths of this room's door openings)` [m]."""
    m = Material.BASEBOARD_LENGTH
    per, src = _perimeter_m(room)
    if per is None:
        return _abstain(m, room.id, A.PERIMETER_NOT_AVAILABLE,
                        "the room carries neither a P1 polygon nor a P5 stated perimeter",
                        f"rooms[{room.id}].polygon or .stated_perimeter")
    doors = tuple(o for o in project.openings_of(room.id) if o.kind in DOOR_KINDS)
    missing = [o.id for o in doors if o.width is None]
    if missing:
        return _abstain(m, room.id, A.DOOR_WIDTH_NOT_STATED,
                        f"P6 door width is not stated for {missing}. Baseboard length computed "
                        "without door deductions is not a defensible quantity (#263 2), and "
                        "treating the opening as solid wall is a silent one-directional error",
                        f"openings[{missing[0]}].width")
    ded = sum(float(o.width.value) for o in doors if o.width is not None)
    return Quantity(material=m, scope=room.id, outcome=Outcome.COMPUTED, unit=F.UNITS[m],
                    value=per - ded, conventions=F4_CONVENTIONS, assumptions=F4_ASSUMPTIONS,
                    inputs_used=(src, f"P6 {len(doors)} stated door width(s)",
                                 f"P11 convention={project.convention.value}"),
                    workings={"perimeter_m": per, "door_deduction_m": ded,
                              "doors": float(len(doors))})


#: The five quantities, in the order the report states them.
FORMULAS = {
    Material.FLOORING_AREA: flooring_area,
    Material.FLOORING_PURCHASE: flooring_purchase,
    Material.WALL_PAINT_AREA: wall_paint_area,
    Material.CEILING_PAINT_AREA: ceiling_paint_area,
    Material.BASEBOARD_LENGTH: baseboard_length,
}


def compute_all(project: ReferenceProject, room: RoomRecord) -> dict[Material, Quantity]:
    """Every quantity for one room. An unexpected exception becomes `FAILED`, never a traceback out
    of the harness, so the failure rate is a number rather than a crashed run."""
    out: dict[Material, Quantity] = {}
    area_q: Quantity | None = None
    for material, fn in FORMULAS.items():
        try:
            if material is Material.FLOORING_PURCHASE:
                q = flooring_purchase(project, room, area_q)
            else:
                q = fn(project, room)
                if material is Material.FLOORING_AREA:
                    area_q = q
        except Exception as exc:  # noqa: BLE001 -- a failure is a recorded result
            q = Quantity(material=material, scope=room.id, outcome=Outcome.FAILED,
                         unit=F.UNITS[material],
                         reason_detail=f"{type(exc).__name__}: {exc}")
        out[material] = q
    return out
