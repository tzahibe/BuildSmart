"""The demo-facing design contract.

Named `DemoDesign`, deliberately NOT `GeometricDesign`: two types with that name already exist in
this codebase (`app.geometry.geometric_design` for the old solver, and
`app.vertical_slice.design_output` for the validated pipeline). A third would be a confusion
hazard during wiring, so the API-facing type gets its own name.

Everything here is READ off the validated pipeline's output. The only derivations are
`_wall_segments`, which turns the engine's per-room-side wall types into drawable segments —
because the renderer must never do that itself — and `_open_corridor_to_public`, the one
architectural-quality rule applied to those segments after they exist.
"""
from __future__ import annotations

import dataclasses
from typing import Literal

from pydantic import BaseModel

from app.geometry_domain.walls import BoundaryContext
from app.vertical_slice import (circulation_metrics, entrance_sequence, interior_layout,
                                quality_metrics)
from app.vertical_slice.constraints import ConstraintSource, TypedConstraint
from app.vertical_slice.exposure_policy import EXPOSURE_POLICY, ExposureRequirement
from app.vertical_slice.spec import CorridorRequirement
from app.vertical_slice.concept_generator import (
    OVER_PREFERRED_NOTICE_RATIO,
    OVER_PREFERRED_SIGNAL_RATIO,
    ROOM_TEMPLATES,
)
from app.vertical_slice.design_output import GeometricDesign as SolvedDesign
from app.vertical_slice.geometry_core.model import ProgramRole, u_to_m
from app.vertical_slice.validation import ValidationReport, check_realized_dimensions
from app.vertical_slice.building import Building
from app.vertical_slice.building_validation import BuildingValidationReport, validate_building

#: A room's realized total below this fraction of its own template TARGET, in a plan that also
#: contains an explicitly requested LAUNDRY room, is disclosed via `QualityOut.laundry_notice`.
#: Proposed for this notice specifically (2026-09-16, docs/LAUNDRY_ROOM_ACTIVATION_REPORT.md §3) —
#: mirrors `OVER_PREFERRED_NOTICE_RATIO`'s role (a threshold beside the templates, not a
#: discovered constant) in the opposite direction. Deliberately NOT a refusal gate — the
#: activation decision explicitly rules out a flat percentage-loss refusal threshold; this number
#: only decides what gets NAMED in the disclosure sentence.
LAUNDRY_REDISTRIBUTION_NOTICE_RATIO = 0.90


class InconsistentGeometryError(Exception):
    """Raised by `to_demo_design` when C27 fails: the assembled `RoomOut` list does not agree with
    itself (a room's width x depth doesn't match its own area, or the building total doesn't match
    the sum of its rooms). Never expected on a real solved design — `check_realized_dimensions`'s
    own docstring explains why — so this is a bug/tamper signal, not a feasibility outcome.
    `app.demo.service` catches this and turns it into `DemoGenerationError("INCONSISTENT_GEOMETRY",
    ...)`, the same way every other product-facing refusal is raised.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


#: Hebrew display names. Presentation lives in the contract so the renderer never has to map
#: architectural roles to words itself.
_ROOM_NAMES = {
    "LIVING": "סלון", "DINING": "פינת אוכל", "KITCHEN": "מטבח",
    "HALL": "מסדרון", "HALL_MAIN": "מסדרון", "HALL_SPUR": "מסדרון",
    "MASTER_BEDROOM": "חדר הורים", "BEDROOM": "חדר שינה",
    "SAFE_ROOM": 'ממ"ד', "BATHROOM": "חדר רחצה", "TOILET": "שירותים",
    "FAMILY_ROOM": "חדר טלוויזיה", "STUDY": "חדר עבודה", "DRESSING_ROOM": "חדר ארונות",
    "LAUNDRY": "חדר כביסה", "STORAGE": "מחסן", "STAIRWELL": "חדר מדרגות",
    "CIRCULATION": "מסדרון",
    "FLEX": "שטח גמיש (לא מוקצה)",
}


class RoomOut(BaseModel):
    """A realized room, in the two definitions documented at
    `docs/wiki/architecture/geometry-validation.md` ("Realized dimensions: gross vs net"):

    `x`/`y` is the room's GROSS rectangle's corner — the centerline allocation the walls (drawn
    from this same rectangle by `_wall_segments`) actually run along. `width_m`/`depth_m`/`area_m2`
    are the NET (usable, wall-inset) triple, so `width_m * depth_m == area_m2` always (check C27
    enforces this on every delivered plan). `gross_width_m`/`gross_depth_m`/`gross_area_m2` are
    additive: the drawing rectangle at `x`,`y` — always `>=` the net triple, since a wall inset only
    ever shrinks a room.
    """

    id: str
    type: str
    name: str
    x: float
    y: float
    width_m: float
    depth_m: float
    area_m2: float
    gross_width_m: float
    gross_depth_m: float
    gross_area_m2: float
    #: side -> {"construction": ..., "boundary_context": ..., "can_take_a_window": ...}
    walls: dict[str, dict]
    #: The role's two size ceilings (`RoomTemplate`): the PREFERRED maximum the planner sizes to
    #: and the HARD one validation C21 gates on. None for a role without a template (circulation,
    #: FLEX). `over_preferred_ratio` is area / preferred when the room is above preferred, else
    #: None — data for the drawing and for diagnostics, not a warning (see `QualityOut`).
    preferred_max_m2: float | None = None
    hard_max_m2: float | None = None
    over_preferred_ratio: float | None = None


class WallSegment(BaseModel):
    orientation: str          # "horizontal" | "vertical"
    coord: float
    start: float
    end: float
    construction: str         # STANDARD_PARTITION | RC_SAFE_ROOM | ...
    boundary_context: str     # EXTERIOR | INTERIOR
    room_ids: list[str]


class OpenInterface(BaseModel):
    """A boundary two spaces share with NO wall — an open-plan join. Drawn as absence."""

    orientation: str
    coord: float
    start: float
    end: float
    room_ids: list[str]


class DoorOut(BaseModel):
    a: str
    b: str
    kind: str
    width_m: float
    x: float
    y: float
    orientation: str
    is_entrance: bool = False
    #: The room the leaf opens into, the hinged jamb, and the open leaf's own direction — so the
    #: drawing can place a real door symbol (leaf plus swing arc) purely from these fields, without
    #: deciding anything itself and without looking up the room `swings_into` names (Issue #38).
    #: `swing_deg` is in degrees, `doors.py::Door.swing_deg`'s convention (0=+x, 90=+y, ...).
    swings_into: str = ""
    hinge_x: float = 0.0
    hinge_y: float = 0.0
    swing_deg: float = 0.0


class QualitySignal(BaseModel):
    room_id: str
    ratio: float


class WetCoreOut(BaseModel):
    """One plan's plumbing-efficiency standing (Issue #44) — see
    `app.vertical_slice.wet_core.WetCore` for what each field means and how it is computed.
    Display/ranking data only, exactly like `WetPrivacyOut`; no check gates on it."""

    shared_wall_length_m: float
    clusters: list[list[str]] = []
    cluster_count: int
    kitchen_adjacent_count: int
    plumbing_complexity_index: int


class QualityMetricsOut(BaseModel):
    """M1–M6 for this one plan (Issue #17), read-only — never an input to ranking or validation.

    Field names mirror `app.vertical_slice.quality_metrics.QualityMetrics` exactly. See that
    module's docstring for how each is computed, and
    `docs/wiki/architecture/geometry-validation.md` for the corpus baseline these numbers are
    checked against and the measured gaps against 21 professional plans.
    """

    m1_habitable_aspect_median: float | None = None
    m1_habitable_aspect_max: float | None = None
    m2_habitable_on_envelope_ratio: float | None = None
    m3_circulation_share: float
    m4_hall_door_count: int | None = None
    m4_hall_aspect_median: float | None = None
    m5_wet_adjacency_ratio: float | None = None
    m6_public_zone_contiguous: bool | None = None
    dead_space_m2: float = 0.0
    wasted_circulation_share: float = 0.0
    #: Dedicated-circulation facts (Issue #36), read off the SAME realized geometry independently
    #: of M3 — see `app.vertical_slice.circulation_metrics.CirculationMetrics` for how each is
    #: measured and `docs/architecture_reference/quality_rubric.md` section B for what they mean.
    circulation_area_m2: float = 0.0
    circulation_ratio: float = 0.0
    circulation_longest_segment_m: float | None = None
    circulation_total_length_m: float = 0.0
    circulation_narrowest_width_m: float | None = None
    circulation_dead_end_count: int = 0
    circulation_turn_count: int = 0
    circulation_duplicated_segment_count: int = 0
    circulation_duplicated_area_m2: float = 0.0
    #: Plumbing-efficiency standing (Issue #44), additive. `None` only for a payload built before
    #: this field existed — every plan `to_demo_design` produces from here on attaches one.
    wet_core: WetCoreOut | None = None


class WetPrivacyOut(BaseModel):
    """One wet room's privacy standing (Issue #37) — see
    `app.vertical_slice.wet_privacy.WetPrivacy` for what each field means and how it is computed.
    Display/ranking data only; the one hard rule it backs (C29) lives in `validation.py`."""

    zone_id: str
    entered_from: str | None = None
    entered_from_class: str
    door_facing: str | None = None
    direct_sight_line: bool
    public_exposure_score: float
    circulation_obstruction: bool
    adjacency_quality: bool
    privacy_score: float


class ExposureOut(BaseModel):
    """One room's exposure standing (Issue #19) — which sides are on the envelope, and either the
    window that was placed or the reason none was: `NO_EXTERIOR_WALL` (a planning-topology
    defect — C19 fails on this same room when its policy requires an exterior wall),
    `EXTERIOR_WALL_TOO_SHORT` (a window-sizing defect — C8 fails when the policy requires a
    window), or `WINDOW_NOT_REQUIRED` (the role's window policy is NONE)."""

    room_id: str
    exterior_sides: list[str] = []
    window_side: str | None = None
    window_width_m: float | None = None
    no_window_reason: str | None = None


class EntranceSequenceOut(BaseModel):
    """The entrance-to-circulation sequence (Issue #22, `app.vertical_slice.entrance_sequence`):
    where the front door arrives, whether that arrival zone is itself circulation, the POCKET
    (walking distance to the arrival zone's own nearest other opening — C25's own blocking fact)
    and the TUNNEL (walking distance to the first PUBLIC-group room, with private doors passed on
    the way — reported, never gating; see that module's docstring for why). `tunnel` is the
    non-blocking quality-signal text (`None` when the walk is not a tunnel). `stray_pockets` is the
    OTHER blocking shape — every OTHER circulation zone independently fronting the street with an
    unserved stub beside the entrance (`[]` when none); also C25's own blocking fact."""

    arrival_zone: str | None = None
    arrival_roles: list[str] = []
    is_circulation_arrival: bool = False
    pocket_length_m: float = 0.0
    has_public_opening: bool = False
    distance_to_public_m: float | None = None
    private_doors_passed: int = 0
    foyer: bool = False
    tunnel: str | None = None
    stray_pockets: list[list] = []


class ConstraintOut(BaseModel):
    """One `TypedConstraint` (Issue #35), as the person-facing screen and support tooling read it —
    including WHERE the requirement came from, so a request never looks like it was invented by
    the engine. Only ever attached for a constraint the brief actually carries
    (`source != ConstraintSource.NONE`); a brief without one gets an empty `QualityOut.constraints`,
    never a `NONE`-source entry."""

    kind: str
    source: str
    authoritative: bool
    min_area_m2: float | None = None


def _constraint_out(constraint: TypedConstraint) -> ConstraintOut:
    return ConstraintOut(kind=constraint.kind.value, source=constraint.source.value,
                         authoritative=constraint.authoritative, min_area_m2=constraint.min_area_m2)


class QualityOut(BaseModel):
    """Room-size quality, kept apart from validation on purpose: the preferred maximum is a soft
    target, the hard one is the gate (C21). Three tiers, thresholds beside the templates
    (`OVER_PREFERRED_SIGNAL_RATIO`, `OVER_PREFERRED_NOTICE_RATIO`):

      * every room above preferred is on its `RoomOut` as `over_preferred_ratio` — metadata;
      * `signal`: rooms between the two thresholds — for ranking and diagnostics, not shown;
      * `notices`: ONE aggregated sentence per plan naming the rooms past the notice threshold —
        the only user-facing output, in a quality style, never in `validation.warnings`.

    `over_preferred` is the planner's own flag: this plan was planned with the hard tier because
    the outline could not be planned inside the preferred maxima. Normal use of that tier is
    not a problem to report; the rooms speak for themselves through the tiers above.

    `laundry_notice` (2026-09-16, activation — docs/LAUNDRY_ROOM_ACTIVATION_REPORT.md §3): the
    opposite-direction case, contained to plans with an explicitly requested LAUNDRY room — a
    room realized materially BELOW its own template target, disclosed as a product notice, never
    a validation failure and never a refusal (the activation decision explicitly rules out a flat
    percentage-loss refusal threshold — see `LAUNDRY_REDISTRIBUTION_NOTICE_RATIO`).
    """

    over_preferred: bool = False
    signal: list[QualitySignal] = []
    notices: list[str] = []
    laundry_notice: str | None = None
    #: M1–M6 for this plan (Issue #17). `None` only for a payload built before this field existed
    #: — every plan `to_demo_design` produces from here on attaches one.
    metrics: QualityMetricsOut | None = None
    #: Typed constraints this plan's brief carries and that were proven realized (Issue #35).
    #: Empty for a brief with none — never invented.
    constraints: list[ConstraintOut] = []
    #: One `ExposureOut` per room (Issue #19), additive. `[]` only for a payload built before
    #: this field existed — every plan `to_demo_design` produces from here on attaches one entry
    #: per room.
    exposure: list[ExposureOut] = []
    #: One `WetPrivacyOut` per wet room (Issue #37), additive. `[]` for a plan with no wet rooms,
    #: or one built before this field existed.
    wet_privacy: list[WetPrivacyOut] = []
    #: The entrance-to-circulation sequence (Issue #22), additive. `None` only for a payload built
    #: before this field existed — every plan `to_demo_design` produces from here on attaches one.
    entrance_sequence: EntranceSequenceOut | None = None


class WindowOut(BaseModel):
    room_id: str
    side: str
    width_m: float
    x: float
    y: float


class RectOut(BaseModel):
    x: float
    y: float
    width_m: float
    depth_m: float


class LayoutObjectOut(BaseModel):
    """One engine-placed semantic layout object (Issue #39) — `app.vertical_slice.interior_layout.
    LayoutObject`, as-is: the renderer draws these directly, never inventing decorative furniture
    of its own. `clearance` always contains `rect` (footprint plus required use clearance)."""

    kind: str
    room_id: str
    x: float
    y: float
    width_m: float
    depth_m: float
    rotation_deg: float
    clearance_x: float
    clearance_y: float
    clearance_width_m: float
    clearance_depth_m: float


def _layout_out(design: SolvedDesign) -> list[LayoutObjectOut]:
    out: list[LayoutObjectOut] = []
    for room_layout in interior_layout.compute_layout(design):
        for obj in room_layout.placed:
            x, y, w, h = obj.rect_m
            cx, cy, cw, ch = obj.clearance_rect_m
            out.append(LayoutObjectOut(
                kind=obj.kind, room_id=obj.room_id, x=x, y=y, width_m=w, depth_m=h,
                rotation_deg=obj.rotation, clearance_x=cx, clearance_y=cy,
                clearance_width_m=cw, clearance_depth_m=ch,
            ))
    return out


class ValidationSummary(BaseModel):
    """Product language, not raw codes. `checks` keeps the codes for support/debugging."""

    passed: bool
    statements: list[str]
    warnings: list[str]
    checks: dict[str, bool]


class RelationshipOut(BaseModel):
    """One requested room relationship and whether the built plan delivers it, in plain words."""

    statement: str            # "חדר ההורים צמוד לחדרי הרחצה"
    satisfied: bool
    strength: str             # hard_requirement | preference
    source_text: str = ""


class CorridorOut(BaseModel):
    """What was asked for and what the plan actually delivers, side by side.

    `realized_width_m` is MEASURED off the realized geometry, never echoed from the request — that
    is the whole point of reporting both.
    """

    requested_width_m: float | None = None
    requested_mode: str | None = None
    realized_width_m: float | None = None
    satisfied: bool | None = None


class OutlineOut(BaseModel):
    """The rectangle a plan occupies and WHO chose it (feature 006).

    `footprint` on the design already carries the rectangle in plot coordinates; this is the
    person-facing label — width, depth, area — plus its origin: the engine's own outline search, or
    the outline the person entered under "advanced".
    """

    width_m: float
    depth_m: float
    area_m2: float
    origin: Literal["ENGINE", "PERSON"]
    #: RECTANGLE, or an L of two wings whose bounding box `width_m x depth_m` is; `wing_dims_m`
    #: then lists the primary's and the arm's (width, depth). Additive; a rectangle has none.
    shape: Literal["RECTANGLE", "L"] = "RECTANGLE"
    wing_dims_m: list[tuple[float, float]] = []


class OutlineTried(BaseModel):
    """One outline the engine planned for this request, whether or not it produced a plan."""

    width_m: float
    depth_m: float
    origin: Literal["ENGINE", "PERSON"]
    planned: bool
    plans_found: int
    latency_ms: float
    shape: Literal["RECTANGLE", "L"] = "RECTANGLE"


class SearchSummary(BaseModel):
    """What the outline search did — every outline tried and what it cost (spec 006 FR-010)."""

    outlines: list[OutlineTried]
    total_latency_ms: float


class DemoDesign(BaseModel):
    plot: RectOut
    #: The building's bounding box — the footprint itself for a one-wing house.
    footprint: RectOut
    rooms: list[RoomOut]
    walls: list[WallSegment]
    open_interfaces: list[OpenInterface]
    doors: list[DoorOut]
    windows: list[WindowOut]
    #: Engine-placed semantic layout objects (Issue #39) — `[]` only for a payload built before
    #: this field existed; every plan `to_demo_design` produces from here on attaches one entry per
    #: PLACED object (never one per requested item — an unplaceable item is simply absent here).
    layout: list[LayoutObjectOut] = []
    parking: list[RectOut]
    garden: list[RectOut]
    entrance_walk: RectOut
    gross_area_m2: float
    net_area_m2: float
    corridor: CorridorOut | None = None
    relationships: list[RelationshipOut] = []
    validation: ValidationSummary
    #: Feature 006. `None` only for a design that did not come through the demo service.
    outline: OutlineOut | None = None
    #: Feature 006. Opaque family signature — diagnostics and tests only; never parsed or shown.
    family: str | None = None
    #: Room-size quality tiers (`QualityOut`). None only for a payload that predates it.
    quality: QualityOut | None = None
    #: The footprint as its wings, one rectangle each. One entry — equal to `footprint` — for
    #: every house the engine plans today; empty only for a payload that predates the field.
    footprints: list[RectOut] = []


# --------------------------------------------------------------------------- the building
#
# Multi-level Phase 0. The building is a LIST OF LEVELS, each carrying a `DemoDesign` exactly as
# the single-storey demo produces it — `levels[0].design` is the same payload as `DemoPlanSet.plan`,
# byte for byte. Everything here is additive and defaulted: a client that reads only
# `plan`/`alternatives` sees exactly what it saw before. A two-storey building, when the engine can
# plan one, is the same type with two entries in `levels` and one in `cores` — not a new payload.


class LevelEntryOut(BaseModel):
    """How a person arrives on this level: the front door (ground) or a stair's arrival (above)."""

    kind: Literal["STREET_DOOR", "STAIR_ARRIVAL"]
    zone_id: str
    core_id: str | None = None


class LevelOut(BaseModel):
    level_id: str
    index: int
    kind: Literal["GROUND", "UPPER"]
    #: Hebrew display name, so the renderer's level tabs never map an index to a word themselves.
    name: str
    elevation_m: float
    #: PARAMETER · UNVERIFIED — see `building.FLOOR_TO_FLOOR_M`.
    floor_to_floor_m: float
    entry: LevelEntryOut
    design: DemoDesign


class CoreOut(BaseModel):
    """A stair, on the plan as REAL AREA on both levels. Empty list on a one-storey house."""

    core_id: str
    kind: Literal["STAIR"]
    archetype: Literal["STRAIGHT", "L_SHAPED", "U_HALF_LANDING"]
    lower_level_id: str
    upper_level_id: str
    zone_id: str
    footprint: RectOut
    entry_edge: str
    arrival_edge: str
    direction: str


class MassingOut(BaseModel):
    plot: RectOut
    #: One BOUNDING BOX per level, index-aligned with `DemoBuilding.levels`.
    level_outlines: list[RectOut]
    #: The rectangles that make up each level — one per wing — index-aligned with the levels.
    #: Only the ground level's touch the site; each upper region lies inside the union of the
    #: level below (building check V2).
    level_regions: list[list[RectOut]] = []
    #: Ground outline over plot. Reported for a coverage rule to read; never used as geometry.
    ground_coverage: float
    #: Roof exposed by upper retreats — a terrace once something classifies it. 0 on one level.
    retreat_m2: float


class BuildingValidationOut(BaseModel):
    """The between-level checks (V-codes), in product language like `ValidationSummary`. Only
    checks that actually ran appear — see `building_validation`'s module docstring."""

    passed: bool
    statements: list[str]
    warnings: list[str]
    checks: dict[str, bool]


class DemoBuilding(BaseModel):
    story_count: int
    levels: list[LevelOut]
    cores: list[CoreOut] = []
    massing: MassingOut
    #: Σ over levels. On one level these equal `plan.gross_area_m2` / `plan.net_area_m2`.
    total_gross_area_m2: float
    total_net_area_m2: float
    validation: BuildingValidationOut


class DemoPlanSet(BaseModel):
    """What the design request answers with: a plan, and the other plans that were also possible.

    `alternatives` is not a ranked list of runners-up — every entry passed exactly the same checks
    `plan` did (see general_pipeline._alternative_plans). Which one is "best" is a matter of taste
    the engine cannot settle, so the person is shown that the choice existed and can take it.
    Empty is a real and common answer: for many briefs the engine produces only one distinct plan.
    """

    plan: DemoDesign
    alternatives: list[DemoDesign] = []
    #: Feature 006: the outlines tried and their cost. `None` for callers outside the demo service.
    search: SearchSummary | None = None
    #: Multi-level Phase 0: `plan` as the ground level of a building. `building.levels[0].design`
    #: is `plan`. `None` for callers outside the demo service. Alternatives stay single designs
    #: until the engine can plan a second level for them.
    building: DemoBuilding | None = None


#: C-code -> the product statement it justifies. Only claims backed by a real check appear.
_STATEMENTS = {
    "C1": "אין חפיפה בין חדרים",
    "C2": "כל שטח הבניין מנוצל",
    "C3": "שטחי החדרים ומידותיהם תקינים",
    "C4": 'הממ"ד עומד בדרישות המעטפת והשטח',
    "C5": "כל החדרים נגישים פיזית מהכניסה",
    "C6": "החלל הפתוח אינו מחולק בדלתות מיותרות",
    "C7": "לכל דלת יש מקום פיזי בקיר",
    "C8": "לכל חדר הדורש אור טבעי יש חלון",
    "C9": "בכל חדר יש מקום לריהוט הבסיסי",
    "C10": "החניה מחוברת לרחוב",
    "C11": "הכניסה להולכי רגל מחוברת לבית",
    "C12": "שטחי החוץ מסווגים במפורש",
    "C13": "כל קשר שתוכנן קיים בפועל בתוכנית",
    "C14": "רוחב המסדרון עומד בדרישה שביקשת",
    "C15": "יחסי החדרים שביקשת מתקיימים בתוכנית",
    "C17": "הגישה לכל חדר רחצה תואמת את מה שביקשת",
    "C18": "החניות מחוץ לבית",
    "C20": "אף חדר אינו רצועה — הפרופורציות של כל חדר בטווח שנקבע לו",
    "C21": "אף חדר אינו גדול מהמקסימום שנקבע לסוגו",
    "C22": "האגפים מחוברים בפועל דרך התפר המוצהר, ללא קיר חוץ או חלון עליו",
}


def _rect(t: tuple[float, float, float, float]) -> RectOut:
    return RectOut(x=t[0], y=t[1], width_m=t[2], depth_m=t[3])


def _room_name(room) -> str:
    for role in room.roles:
        if role in _ROOM_NAMES:
            return _ROOM_NAMES[role]
    return room.zone_id.replace("_", " ")


def _wall_segments(design: SolvedDesign) -> tuple[list[WallSegment], list[OpenInterface]]:
    """Per-room side types -> drawable segments.

    This derivation belongs in the backend precisely because the renderer must not decide where a
    wall is. Identical segments produced by two adjacent rooms are merged so a shared wall is one
    entity carrying both room ids; an `OPEN` side yields no wall at all and is reported separately
    so the drawing can show the absence deliberately rather than by omission.

    ONE SIDE, SEVERAL NEIGHBOURS. The engine gives a wall SIDE exactly one type, which is right for
    solving — insets have to be known before dimensions — but wrong to draw. A corridor whose east
    side runs past two bedrooms, a safe room and a bathroom is typed `RC_SAFE_ROOM` for its whole
    length, because the strongest neighbour wins the side. Drawn literally that put 17 m of
    reinforced concrete on a plan whose safe room is 3 m long.

    So a side with several neighbours is CUT at their boundaries, and each piece takes the
    construction its own pair justifies: reinforced concrete only where a safe room is actually on
    one side of it. Nothing is invented — the pieces come from room rectangles the plan already
    has, and a side with one neighbour is unchanged.
    """
    rooms = {r.zone_id: r for r in design.rooms}
    is_safe = {r.zone_id: "SAFE_ROOM" in [str(x) for x in r.roles] for r in design.rooms}

    def neighbours_along(room, side, orientation, coord, start, end):
        """The pieces of this side, split where the room on the other side changes."""
        cuts = {start, end}
        for other in design.rooms:
            if other.zone_id == room.zone_id:
                continue
            ox, oy, ow, oh = other.rect_m
            touches = (abs(ox - coord) < 1e-6 or abs(ox + ow - coord) < 1e-6) if orientation == "vertical" \
                else (abs(oy - coord) < 1e-6 or abs(oy + oh - coord) < 1e-6)
            if not touches:
                continue
            lo, hi = (oy, oy + oh) if orientation == "vertical" else (ox, ox + ow)
            if hi <= start + 1e-6 or lo >= end - 1e-6:
                continue
            cuts.add(max(lo, start))
            cuts.add(min(hi, end))
        ordered = sorted(cuts)
        for lo, hi in zip(ordered, ordered[1:]):
            if hi - lo < 1e-6:
                continue
            mid = (lo + hi) / 2
            facing = None
            for other in design.rooms:
                if other.zone_id == room.zone_id:
                    continue
                ox, oy, ow, oh = other.rect_m
                touches = (abs(ox - coord) < 1e-6 or abs(ox + ow - coord) < 1e-6) if orientation == "vertical" \
                    else (abs(oy - coord) < 1e-6 or abs(oy + oh - coord) < 1e-6)
                if not touches:
                    continue
                olo, ohi = (oy, oy + oh) if orientation == "vertical" else (ox, ox + ow)
                if olo - 1e-6 <= mid <= ohi + 1e-6:
                    facing = other.zone_id
                    break
            yield lo, hi, facing

    walls: dict[tuple, WallSegment] = {}
    opens: dict[tuple, OpenInterface] = {}
    for room in design.rooms:
        x, y, w, h = room.rect_m
        edges = {
            "N": ("horizontal", y, x, x + w),
            "S": ("horizontal", y + h, x, x + w),
            "W": ("vertical", x, y, y + h),
            "E": ("vertical", x + w, y, y + h),
        }
        for side, (orientation, coord, start, end) in edges.items():
            facts = room.wall_facts[side]
            for lo, hi, facing in neighbours_along(room, side, orientation, coord, start, end):
                construction = facts.construction.value
                # Reinforced concrete belongs to the safe room's own envelope, not to every
                # neighbour that happens to share a side with it.
                if construction == "RC_SAFE_ROOM" and not (
                        is_safe.get(room.zone_id) or (facing and is_safe.get(facing))):
                    construction = "STANDARD_PARTITION"

                key = (orientation, round(coord, 4), round(lo, 4), round(hi, 4))
                if construction == "NONE":
                    entry = opens.get(key)
                    if entry is None:
                        opens[key] = OpenInterface(orientation=orientation, coord=coord, start=lo,
                                                   end=hi, room_ids=[room.zone_id])
                    elif room.zone_id not in entry.room_ids:
                        entry.room_ids.append(room.zone_id)
                    continue
                entry = walls.get(key)
                if entry is None:
                    walls[key] = WallSegment(
                        orientation=orientation, coord=coord, start=lo, end=hi,
                        construction=construction,
                        boundary_context=facts.boundary_context.value,
                        room_ids=[room.zone_id])
                else:
                    if room.zone_id not in entry.room_ids:
                        entry.room_ids.append(room.zone_id)
                    # A pair disagrees only when one of them is the safe room; that side wins.
                    if construction == "RC_SAFE_ROOM":
                        entry.construction = construction
    return list(walls.values()), list(opens.values())


_CIRCULATION_ROLES = frozenset({"HALL", "CIRCULATION"})
_EPS = 1e-6


def _is_circulation(room) -> bool:
    return bool(_CIRCULATION_ROLES & {str(getattr(role, "value", role)) for role in room.roles})


def _door_crosses(door, orientation: str, coord: float, start: float, end: float) -> bool:
    """Whether a door's opening lies (even partly) on this piece of wall line."""
    if door.orientation != orientation:
        return False
    along, across = (1, 0) if orientation == "vertical" else (0, 1)
    if abs(door.center_m[across] - coord) > _EPS:
        return False
    half = door.width_m / 2
    return door.center_m[along] - half < end - _EPS and door.center_m[along] + half > start + _EPS


def _open_corridor_to_public(design: SolvedDesign, walls: list[WallSegment],
                             opens: list[OpenInterface]) -> tuple[list[WallSegment], list[OpenInterface]]:
    """A corridor wall that only separates circulation from the open public zone is not built.

    THE WALL THIS REMOVES. In every spine parti the hall runs the full depth of the house beside
    the public column, so its long side faces living, dining and kitchen for 10-12 m with nothing
    on it but the 0.9 m cased opening `_build_access` declares — measured across every programme
    and outline this generator produces (36-50 % of the hall's interior perimeter). The engine
    types that side `PARTITION` for its whole length because a `WallMap` side carries ONE type and
    an `OPEN` side needs a full-edge match on both zones (`_discover_open_interfaces`), which a
    hall flanked by rooms never has. The result reads as ~17 m2 of enclosed corridor with the
    open-plan space directly behind the wall. Neither the generator (no tree-sibling open group
    can hold the hall) nor the topology (a declared OPEN_CONNECTION there fails C13) can express
    the opening, so it is decided here, on the SEGMENTS, the same place a multi-neighbour side is
    already cut and re-typed per pair (RC only against the safe room).

    A segment is opened only when every one of these holds — each is a real requirement the
    wall might otherwise be serving:
      * it lies between a HALL/CIRCULATION zone and a member of a declared open group, and the
        hall's declared way into that group is a CASED_OPENING — a closed plan has no open
        group, so nothing opens there;
      * it is STANDARD_PARTITION and INTERIOR — an EXTERIOR or RC_SAFE_ROOM segment is never a
        candidate, whatever faces it;
      * no DOOR lies on it — a door needs its wall, so a door-bearing piece stays, which is what
        leaves the short wall beside a private room that shares the hall's side (the master
        bedroom of a shared row). A cased opening does not count: an open segment subsumes it.

    Nothing upstream changes: `WallMap`, room rectangles, net areas and every validation check
    are untouched, so C14 still measures the corridor with its partition inset (conservative —
    a really open side is wider) and C13 is still realized by the cased opening it was declared
    with. This is a drawing-truth decision about construction, not a topology change.
    """
    rooms = {r.zone_id: r for r in design.rooms}
    group_of = {zone: frozenset(group) for group in design.open_groups for zone in group}

    # The hall's declared entrance into each public open group. Doors come only from the declared
    # DesiredAccessTopology (P8), so a CASED_OPENING door IS the declared relationship.
    opens_into: dict[str, set[frozenset[str]]] = {}
    for door in design.interior_doors:
        if door.kind != "CASED_OPENING":
            continue
        for hall, other in ((door.a, door.b), (door.b, door.a)):
            if hall in rooms and _is_circulation(rooms[hall]) and other in group_of:
                opens_into.setdefault(hall, set()).add(group_of[other])
    if not opens_into:
        return walls, opens

    real_doors = [d for d in (*design.interior_doors, design.entrance_door) if d.kind == "DOOR"]
    kept: list[WallSegment] = []
    opened: list[OpenInterface] = []
    for seg in walls:
        if (seg.construction != "STANDARD_PARTITION" or seg.boundary_context != "INTERIOR"
                or len(seg.room_ids) != 2):
            kept.append(seg)
            continue
        a, b = seg.room_ids
        hall, public = (a, b) if _is_circulation(rooms[a]) else (b, a)
        if (not _is_circulation(rooms[hall]) or _is_circulation(rooms[public])
                or group_of.get(public) not in opens_into.get(hall, set())):
            kept.append(seg)
            continue
        if any(_door_crosses(d, seg.orientation, seg.coord, seg.start, seg.end) for d in real_doors):
            kept.append(seg)
            continue
        opened.append(OpenInterface(orientation=seg.orientation, coord=seg.coord,
                                    start=seg.start, end=seg.end, room_ids=list(seg.room_ids)))
    return kept, opens + opened


def _suppress_covered_cased_openings(doors: list[DoorOut],
                                     opens: list[OpenInterface]) -> list[DoorOut]:
    """Drop a CASED_OPENING whose whole span now lies in open interface — there is no wall left
    for it to be an opening in, and drawing its jambs would put a 0.9 m frame in empty space. A
    cased opening the open interfaces cover only partly keeps its symbol: some wall remains."""
    def covered(door: DoorOut) -> bool:
        if door.kind != "CASED_OPENING":
            return False
        vertical = door.orientation == "vertical"
        coord, centre = (door.x, door.y) if vertical else (door.y, door.x)
        lo, hi = centre - door.width_m / 2, centre + door.width_m / 2
        spans = sorted((o.start, o.end) for o in opens
                       if o.orientation == door.orientation and abs(o.coord - coord) < _EPS)
        reached = lo
        for start, end in spans:
            if start > reached + _EPS:
                break  # a gap of wall before the next open span
            reached = max(reached, end)
            if reached >= hi - _EPS:
                return True
        return False

    return [d for d in doors if not covered(d)]


def _corridor_out(design: SolvedDesign, corridor: CorridorRequirement | None) -> CorridorOut | None:
    """Measured from the realized rooms — the narrowest circulation zone is what a person walks."""
    widths = [min(r.net_w_m, r.net_h_m) for r in design.rooms
              if {"HALL", "CIRCULATION"} & {str(getattr(role, "value", role)) for role in r.roles}]
    realized = round(min(widths), 2) if widths else None
    if corridor is None and realized is None:
        return None
    return CorridorOut(
        requested_width_m=corridor.width_m if corridor else None,
        requested_mode=corridor.mode.value if corridor else None,
        realized_width_m=realized,
        satisfied=(corridor.satisfied_by(realized)
                   if corridor is not None and realized is not None else None),
    )


def _template_of(room):
    role = room.roles[0]
    if role in ("HALL", "CIRCULATION", "FLEX") or role not in ProgramRole.__members__:
        return None
    return ROOM_TEMPLATES.get(ProgramRole(role))


def _room_size_facts(room) -> dict:
    """`RoomOut`'s size ceilings and the room's standing against the preferred one."""
    template = _template_of(room)
    if template is None:
        return {}
    ratio = room.net_area_m2 / template.max_area_m2
    return dict(preferred_max_m2=template.max_area_m2, hard_max_m2=template.hard_max,
                over_preferred_ratio=round(ratio, 3) if ratio > 1.0 + 1e-6 else None)


#: Excluded from `_laundry_redistribution_notice` beyond `_template_of`'s own exclusions.
#: SAFE_ROOM's `elasticity` is 0 — "Regulated minimum: never scaled down, and not inflated just
#: because the house is large" (its own template comment) — so it never grows OR shrinks through
#: either `scale_program` branch's surplus/target logic. It can still REALIZE a little under its
#: nominal target from ordinary row-depth geometry (confirmed directly: 9.3 m² against a 10.5 m²
#: target on an identical brief with NO laundry room at all) — a pre-existing property of that
#: room's usual sizing, not something a laundry request caused. Naming it in this notice would be
#: a false positive: the room is genuinely "reduced" on paper but not BY the redistribution this
#: notice exists to disclose.
_LAUNDRY_NOTICE_EXCLUDED_ROLES = (ProgramRole.SAFE_ROOM.value,)


def _laundry_redistribution_notice(design: SolvedDesign) -> str | None:
    """One aggregated sentence naming every OTHER room realized materially below its own template
    TARGET, in a plan that also contains an explicitly requested LAUNDRY room — the signal that
    the laundry room's area came from somewhere (2026-09-16, activation —
    docs/LAUNDRY_ROOM_ACTIVATION_REPORT.md §3).

    Compares each room's realized total against its OWN fixed template target — never a second
    "without laundry" solve, which can land on a genuinely different footprint candidate and
    confound a before/after comparison (see the investigation report,
    docs/LAUNDRY_AREA_BUDGET_INVESTIGATION.md). Same reference-point philosophy as the
    over-preferred check above, in the opposite direction. `None` for every plan without a
    laundry room — contained to explicit LAUNDRY_ROOM activation, nothing else.
    """
    if not any(room.roles[0] == ProgramRole.LAUNDRY.value for room in design.rooms):
        return None
    totals: dict[str, float] = {}
    targets: dict[str, float] = {}
    names: dict[str, str] = {}
    for room in design.rooms:
        if room.roles[0] in (ProgramRole.LAUNDRY.value, *_LAUNDRY_NOTICE_EXCLUDED_ROLES):
            continue
        template = _template_of(room)
        if template is None:
            continue
        role = room.roles[0]
        totals[role] = totals.get(role, 0.0) + room.net_area_m2
        targets[role] = targets.get(role, 0.0) + template.target_area_m2
        names[role] = _room_name(room)
    parts = [f"{names[role]} {realized:.1f} מ\"ר (יעד {targets[role]:.1f})"
            for role, realized in totals.items()
            if realized < targets[role] * LAUNDRY_REDISTRIBUTION_NOTICE_RATIO - 1e-6]
    if not parts:
        return None
    return f"בקשת חדר הכביסה חייבה חלוקה מחדש של השטח: {'; '.join(parts)}"


def _metrics_out(m: quality_metrics.QualityMetrics, c: circulation_metrics.CirculationMetrics,
                 wet_core: WetCoreOut | None = None) -> QualityMetricsOut:
    return QualityMetricsOut(
        **dataclasses.asdict(m),
        **{f"circulation_{k}": v for k, v in dataclasses.asdict(c).items()},
        wet_core=wet_core,
    )


def _exposure_of(design: SolvedDesign) -> list[ExposureOut]:
    """One `ExposureOut` per room, off the raw solver output — see `ExposureOut` for the reason
    codes. Reads `room.wall_facts` (geometry-derived, never the raw solver `WallType`) for which
    sides are on the envelope, and `design.windows` (placeable or not) for what `generate_windows`
    actually attempted for that role's policy tier."""
    window_of: dict[str, object] = {w.zone_id: w for w in design.windows}
    out: list[ExposureOut] = []
    for room in design.rooms:
        exterior_sides = [side for side, facts in room.wall_facts.items()
                          if facts.boundary_context is BoundaryContext.EXTERIOR]
        policies = [EXPOSURE_POLICY[ProgramRole(r)] for r in room.roles if r in ProgramRole.__members__]
        window_policy = ExposureRequirement.NONE
        if any(p.window is ExposureRequirement.REQUIRED for p in policies):
            window_policy = ExposureRequirement.REQUIRED
        elif any(p.window is ExposureRequirement.PREFERRED for p in policies):
            window_policy = ExposureRequirement.PREFERRED
        window = window_of.get(room.zone_id)
        placed = window is not None and window.placeable
        reason = None
        if not placed:
            if window_policy is ExposureRequirement.NONE:
                reason = "WINDOW_NOT_REQUIRED"
            elif not exterior_sides:
                reason = "NO_EXTERIOR_WALL"
            else:
                reason = "EXTERIOR_WALL_TOO_SHORT"
        out.append(ExposureOut(
            room_id=room.zone_id,
            exterior_sides=exterior_sides,
            window_side=window.side if placed else None,
            window_width_m=window.width_m if placed else None,
            no_window_reason=reason,
        ))
    return out


def quality_of(design: SolvedDesign) -> QualityOut:
    """The three tiers of `QualityOut` from the realized rooms — see the class for the policy."""
    signal: list[QualitySignal] = []
    notice_rooms: list[tuple[object, float, float]] = []
    for room in design.rooms:
        template = _template_of(room)
        if template is None:
            continue
        ratio = room.net_area_m2 / template.max_area_m2
        if ratio > OVER_PREFERRED_NOTICE_RATIO:
            notice_rooms.append((room, ratio, template.max_area_m2))
        elif ratio > OVER_PREFERRED_SIGNAL_RATIO:
            signal.append(QualitySignal(room_id=room.zone_id, ratio=round(ratio, 3)))
    notices: list[str] = []
    if notice_rooms:
        # One sentence for the plan, rooms grouped by their display name.
        groups: dict[str, list[tuple[float, float]]] = {}
        for room, ratio, preferred in notice_rooms:
            groups.setdefault(_room_name(room), []).append((room.net_area_m2, preferred))
        parts = [f"{name} {', '.join(f'{a:.1f}' for a, _ in items)} מ\"ר (מומלץ עד {items[0][1]:.0f})"
                 for name, items in groups.items()]
        count = len(notice_rooms)
        head = "חדר אחד גדול מהמומלץ בצורה ניכרת" if count == 1 else f"{count} חדרים גדולים מהמומלץ בצורה ניכרת"
        notices.append(f"{head}: {'; '.join(parts)}")
    return QualityOut(over_preferred=design.over_preferred, signal=signal, notices=notices,
                      laundry_notice=_laundry_redistribution_notice(design))


def summarize(report: ValidationReport,
              unsupported: list[str] | None = None,
              relationships: tuple = (),
              notes: list[str] | None = None) -> ValidationSummary:
    statements = [_STATEMENTS[c.check_id] for c in report.checks
                  if c.passed and c.check_id in _STATEMENTS]
    warnings = [f"{_STATEMENTS.get(c.check_id, c.name)}: {c.detail}" for c in report.failures()]

    # Non-blocking quality notes (Issue #38's corridor-obstruction note today) — the plan passed
    # validation; this is disclosure, not a failed check.
    warnings.extend(report.notes)

    # Something true about THIS plan that the person must read before the drawing — a house that
    # fills what its rooms can and not what was asked (`service.capacity_note`). Carried verbatim,
    # unlike `unsupported`, which quotes a request back to them.
    warnings.extend(notes or [])

    # The plan must not read as though it honoured the whole brief. Anything the person asked for
    # that this stage cannot plan is carried onto the plan screen as a warning, in their own words —
    # the checks above only ever describe what WAS done.
    for text in unsupported or []:
        warnings.append(f'לא נכלל בתכנון: "{text}"')

    # A relationship that HELD becomes a statement the person can read back; one that did not is a
    # warning. Only preferences can get here unsatisfied — a hard one never reaches a plan.
    for outcome in relationships:
        if outcome.satisfied:
            statements.append(outcome.statement)
        else:
            warnings.append(f"העדפה שלא התממשה: {outcome.statement}")
    return ValidationSummary(
        passed=report.ok,
        statements=statements,
        warnings=warnings,
        checks={c.check_id: c.passed for c in report.checks},
    )


def to_demo_design(design: SolvedDesign, report: ValidationReport,
                   unsupported: list[str] | None = None,
                   corridor: CorridorRequirement | None = None,
                   relationships: tuple = (),
                   outline: OutlineOut | None = None,
                   family: str | None = None,
                   notes: list[str] | None = None,
                   constraint: TypedConstraint | None = None) -> DemoDesign:
    """`constraint` (Issue #35): the spec's SAFE_ROOM `TypedConstraint`, attached to
    `QualityOut.constraints` when the brief actually carries one (`source != NONE`) — `None`
    (the default) keeps every caller that predates this parameter unchanged."""
    walls, opens = _wall_segments(design)
    walls, opens = _open_corridor_to_public(design, walls, opens)
    doors = [DoorOut(a=d.a, b=d.b, kind=d.kind, width_m=d.width_m, x=d.center_m[0],
                     y=d.center_m[1], orientation=d.orientation,
                     swings_into=d.swings_into, hinge_x=d.hinge_m[0], hinge_y=d.hinge_m[1],
                     swing_deg=d.swing_deg)
             for d in design.interior_doors]
    doors = _suppress_covered_cased_openings(doors, opens)
    entrance = design.entrance_door
    doors.append(DoorOut(a=entrance.a, b=entrance.b, kind=entrance.kind, width_m=entrance.width_m,
                         x=entrance.center_m[0], y=entrance.center_m[1],
                         orientation=entrance.orientation, is_entrance=True,
                         swings_into=entrance.swings_into,
                         hinge_x=entrance.hinge_m[0], hinge_y=entrance.hinge_m[1],
                         swing_deg=entrance.swing_deg))
    rooms_out = [RoomOut(
        id=r.zone_id, type=r.roles[0], name=_room_name(r),
        x=r.rect_m[0], y=r.rect_m[1], width_m=r.net_w_m, depth_m=r.net_h_m,
        area_m2=r.net_area_m2,
        gross_width_m=r.rect_m[2], gross_depth_m=r.rect_m[3],
        gross_area_m2=round(r.rect_m[2] * r.rect_m[3], 4),
        walls={side: {"construction": f.construction.value,
                      "boundary_context": f.boundary_context.value,
                      "can_take_a_window": f.can_take_a_window}
               for side, f in r.wall_facts.items()},
        **_room_size_facts(r),
    ) for r in design.rooms]
    c27 = check_realized_dimensions(rooms_out, design.gross_area_m2)
    if not c27.passed:
        raise InconsistentGeometryError(c27.detail)
    demo = DemoDesign(
        plot=_rect(design.plot_m),
        footprint=_rect(design.footprint_m),
        footprints=[_rect(f) for f in design.footprints_m],
        rooms=rooms_out,
        walls=walls,
        open_interfaces=opens,
        doors=doors,
        windows=[WindowOut(room_id=w.zone_id, side=w.side, width_m=w.width_m,
                           x=w.center_m[0], y=w.center_m[1])
                 for w in design.windows if w.width_m > 0],
        layout=_layout_out(design),
        parking=[_rect(p) for p in design.parking_m],
        garden=[_rect(r) for g in design.garden for r in g.rects_m],
        entrance_walk=_rect(design.entrance_walk_m),
        gross_area_m2=design.gross_area_m2,
        net_area_m2=design.net_area_m2,
        corridor=_corridor_out(design, corridor),
        relationships=[
            RelationshipOut(statement=o.statement, satisfied=o.satisfied,
                            strength=o.requirement.strength.value,
                            source_text=o.requirement.source_text)
            for o in relationships],
        validation=summarize(report, unsupported, relationships, notes),
        quality=quality_of(design),
        outline=outline,
        family=family,
    )
    # M1–M6 (Issue #17) need the FLATTENED walls/open-interfaces/doors this function just built
    # (adjacency, hall doors, open-plan joins) — data `quality_of(design)` above never sees, since
    # it runs on the raw solver output. Computed here, once the shape exists, and attached
    # additively onto the `quality` already built rather than threaded through `quality_of`.
    metrics = quality_metrics.measure_design(demo)
    constraints_out = ([_constraint_out(constraint)]
                       if constraint is not None and constraint.source is not ConstraintSource.NONE
                       else [])
    # Dedicated-circulation metrics (Issue #36) read the raw `SolvedDesign` directly — the same
    # `GeometricDesign` C26 (`validation.py`) and the circulation ranking term
    # (`general_pipeline._guard_demoted_hub`) already measure — rather than the flattened `demo`
    # M1-M6 reads, so a check, a ranking decision and this report can never disagree about what a
    # plan's circulation looks like.
    circulation = circulation_metrics.measure(design)
    # Entrance sequence (Issue #22) reads the SAME raw `SolvedDesign` circulation does, for the
    # same reason: a check (C25), a ranking decision and this report must never disagree about
    # what a plan's entrance sequence looks like.
    entrance_seq = entrance_sequence.measure(design)
    entrance_seq_out = EntranceSequenceOut(
        arrival_zone=entrance_seq.arrival_zone,
        arrival_roles=list(entrance_seq.arrival_roles),
        is_circulation_arrival=entrance_seq.is_circulation_arrival,
        #: `math.inf` only for a fully sealed arrival zone (no other opening at all) — capped for
        #: JSON (`Infinity` is not valid JSON); `classify_pocket` already flagged it either way.
        pocket_length_m=min(entrance_seq.pocket_length_m, 999.0),
        has_public_opening=entrance_seq.has_public_opening,
        distance_to_public_m=entrance_seq.distance_to_public_m,
        private_doors_passed=entrance_seq.private_doors_passed,
        foyer=entrance_seq.foyer,
        tunnel=entrance_sequence.classify_tunnel(entrance_seq),
        stray_pockets=[[zone_id, length] for zone_id, length in entrance_seq.stray_pockets],
    )
    # Exposure (Issue #19) needs `design.rooms[].wall_facts`/`design.windows`, present on the raw
    # solver output but not on `quality_of`'s own narrow `SimpleNamespace`-shaped unit tests —
    # same reason metrics is attached here rather than threaded through `quality_of`.
    exposure = _exposure_of(design)
    wet_privacy = [WetPrivacyOut(**dataclasses.asdict(p)) for p in design.wet_privacy]
    wet_core = (WetCoreOut(**dataclasses.asdict(design.wet_core))
               if design.wet_core is not None else None)
    return demo.model_copy(update={
        "quality": demo.quality.model_copy(update={
            "metrics": _metrics_out(metrics, circulation, wet_core),
            "constraints": constraints_out,
            "exposure": exposure,
            "wet_privacy": wet_privacy,
            "entrance_sequence": entrance_seq_out})
    })


# --------------------------------------------------------------------------- building payload

_LEVEL_NAMES = {0: "קומת קרקע", 1: "קומה א׳", 2: "קומה ב׳", 3: "קומה ג׳"}

#: V-code -> the product statement it justifies. Only claims backed by a check that ran appear.
_BUILDING_STATEMENTS = {
    "V1": "המדרגות תופסות את אותו מלבן בכל הקומות",
    "V2": "כל קומה עליונה נמצאת בתוך המתאר של הקומה שמתחתיה",
    "V3": "אף חדר אינו חופף למדרגות",
    "V4": "כל החדרים בכל הקומות נגישים פיזית מהכניסה",
    "V5": "המדרגות נפתחות אל שטח תנועה בשתי הקומות",
    "V6": 'ממ"דים בקומות שונות מיושרים זה מעל זה',
    "V7": "חשבון השטחים תקין: שטח כל קומה שווה למתאר שלה",
}


def _level_name(index: int) -> str:
    return _LEVEL_NAMES.get(index, f"קומה {index}")


def summarize_building(report: BuildingValidationReport) -> BuildingValidationOut:
    return BuildingValidationOut(
        passed=report.ok,
        statements=[_BUILDING_STATEMENTS[c.check_id] for c in report.checks
                    if c.passed and c.check_id in _BUILDING_STATEMENTS],
        warnings=[f"{_BUILDING_STATEMENTS.get(c.check_id, c.name)}: {c.detail}"
                  for c in report.failures()],
        checks={c.check_id: c.passed for c in report.checks},
    )


def to_demo_building(building: Building, level_designs: list[DemoDesign]) -> DemoBuilding:
    """The building payload, given each level's ALREADY-BUILT `DemoDesign`.

    The designs are passed in rather than rebuilt so that `levels[0].design` is the very object
    `DemoPlanSet.plan` carries — the same corridor opening, notes and quality metadata — and not a
    second rendering of the same geometry that could drift from it.
    """
    if len(level_designs) != building.story_count:
        raise ValueError(f"{len(level_designs)} level designs for {building.story_count} level(s)")
    report = validate_building(building)
    return DemoBuilding(
        story_count=building.story_count,
        levels=[LevelOut(
            level_id=plan.level.level_id, index=plan.level.index, kind=plan.level.kind.value,
            name=_level_name(plan.level.index),
            elevation_m=plan.level.elevation_m, floor_to_floor_m=plan.level.floor_to_floor_m,
            entry=LevelEntryOut(kind=plan.entry.kind.value, zone_id=plan.entry.zone_id,
                                core_id=plan.entry.core_id),
            design=design,
        ) for plan, design in zip(building.levels, level_designs)],
        cores=[CoreOut(
            core_id=c.core_id, kind=c.kind.value, archetype=c.archetype.value,
            lower_level_id=c.lower_level_id, upper_level_id=c.upper_level_id,
            zone_id=c.zone_id or c.core_id,
            footprint=RectOut(x=u_to_m(c.footprint_u.x), y=u_to_m(c.footprint_u.y),
                              width_m=u_to_m(c.footprint_u.w), depth_m=u_to_m(c.footprint_u.h)),
            entry_edge=c.entry_edge.value, arrival_edge=c.arrival_edge.value,
            direction=c.direction.value,
        ) for c in building.cores],
        massing=MassingOut(
            plot=_rect(building.massing.plot_m),
            level_outlines=[_rect(o) for o in building.massing.level_outlines_m],
            level_regions=[[_rect(r) for r in regions]
                           for regions in building.massing.level_regions_m],
            ground_coverage=building.massing.ground_coverage,
            retreat_m2=building.massing.retreat_m2,
        ),
        total_gross_area_m2=building.total_gross_m2,
        total_net_area_m2=building.total_net_m2,
        validation=summarize_building(report),
    )

