"""The demo-facing design contract.

Named `DemoDesign`, deliberately NOT `GeometricDesign`: two types with that name already exist in
this codebase (`app.geometry.geometric_design` for the old solver, and
`app.vertical_slice.design_output` for the validated pipeline). A third would be a confusion
hazard during wiring, so the API-facing type gets its own name.

Everything here is READ off the validated pipeline's output. The only derivation is
`_wall_segments`, which turns the engine's per-room-side wall types into drawable segments —
because the renderer must never do that itself.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.vertical_slice.spec import CorridorRequirement
from app.vertical_slice.design_output import GeometricDesign as SolvedDesign
from app.vertical_slice.validation import ValidationReport

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
    id: str
    type: str
    name: str
    x: float
    y: float
    width_m: float
    depth_m: float
    area_m2: float
    #: side -> {"construction": ..., "boundary_context": ..., "can_take_a_window": ...}
    walls: dict[str, dict]


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
    #: The room the leaf opens into, and the hinged jamb — so the drawing can show a real door
    #: symbol (leaf plus swing arc) instead of a gap in a wall, without deciding anything itself.
    swings_into: str = ""
    hinge_x: float = 0.0
    hinge_y: float = 0.0


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


class OutlineTried(BaseModel):
    """One outline the engine planned for this request, whether or not it produced a plan."""

    width_m: float
    depth_m: float
    origin: Literal["ENGINE", "PERSON"]
    planned: bool
    plans_found: int
    latency_ms: float


class SearchSummary(BaseModel):
    """What the outline search did — every outline tried and what it cost (spec 006 FR-010)."""

    outlines: list[OutlineTried]
    total_latency_ms: float


class DemoDesign(BaseModel):
    plot: RectOut
    footprint: RectOut
    rooms: list[RoomOut]
    walls: list[WallSegment]
    open_interfaces: list[OpenInterface]
    doors: list[DoorOut]
    windows: list[WindowOut]
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


def summarize(report: ValidationReport,
              unsupported: list[str] | None = None,
              relationships: tuple = ()) -> ValidationSummary:
    statements = [_STATEMENTS[c.check_id] for c in report.checks
                  if c.passed and c.check_id in _STATEMENTS]
    warnings = [f"{_STATEMENTS.get(c.check_id, c.name)}: {c.detail}" for c in report.failures()]

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
                   family: str | None = None) -> DemoDesign:
    walls, opens = _wall_segments(design)
    doors = [DoorOut(a=d.a, b=d.b, kind=d.kind, width_m=d.width_m, x=d.center_m[0],
                     y=d.center_m[1], orientation=d.orientation,
                     swings_into=d.swings_into, hinge_x=d.hinge_m[0], hinge_y=d.hinge_m[1])
             for d in design.interior_doors]
    entrance = design.entrance_door
    doors.append(DoorOut(a=entrance.a, b=entrance.b, kind=entrance.kind, width_m=entrance.width_m,
                         x=entrance.center_m[0], y=entrance.center_m[1],
                         orientation=entrance.orientation, is_entrance=True,
                         swings_into=entrance.swings_into,
                         hinge_x=entrance.hinge_m[0], hinge_y=entrance.hinge_m[1]))
    return DemoDesign(
        plot=_rect(design.plot_m),
        footprint=_rect(design.footprint_m),
        rooms=[RoomOut(
            id=r.zone_id, type=r.roles[0], name=_room_name(r),
            x=r.rect_m[0], y=r.rect_m[1], width_m=r.rect_m[2], depth_m=r.rect_m[3],
            area_m2=r.net_area_m2,
            walls={side: {"construction": f.construction.value,
                          "boundary_context": f.boundary_context.value,
                          "can_take_a_window": f.can_take_a_window}
                   for side, f in r.wall_facts.items()},
        ) for r in design.rooms],
        walls=walls,
        open_interfaces=opens,
        doors=doors,
        windows=[WindowOut(room_id=w.zone_id, side=w.side, width_m=w.width_m,
                           x=w.center_m[0], y=w.center_m[1])
                 for w in design.windows if w.width_m > 0],
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
        validation=summarize(report, unsupported, relationships),
        outline=outline,
        family=family,
    )
