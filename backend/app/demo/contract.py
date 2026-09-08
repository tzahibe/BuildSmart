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

from pydantic import BaseModel

from app.vertical_slice.design_output import GeometricDesign as SolvedDesign
from app.vertical_slice.validation import ValidationReport

#: Hebrew display names. Presentation lives in the contract so the renderer never has to map
#: architectural roles to words itself.
_ROOM_NAMES = {
    "LIVING": "סלון", "DINING": "פינת אוכל", "KITCHEN": "מטבח",
    "HALL": "מסדרון", "HALL_MAIN": "מסדרון", "HALL_SPUR": "מסדרון",
    "MASTER_BEDROOM": "חדר הורים", "BEDROOM": "חדר שינה",
    "SAFE_ROOM": 'ממ"ד', "BATHROOM": "חדר רחצה", "CIRCULATION": "מסדרון",
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
    validation: ValidationSummary


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
    """
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
            key = (orientation, round(coord, 4), round(start, 4), round(end, 4))
            if facts.construction.value == "NONE":
                entry = opens.get(key)
                if entry is None:
                    opens[key] = OpenInterface(orientation=orientation, coord=coord, start=start,
                                               end=end, room_ids=[room.zone_id])
                elif room.zone_id not in entry.room_ids:
                    entry.room_ids.append(room.zone_id)
                continue
            entry = walls.get(key)
            if entry is None:
                walls[key] = WallSegment(
                    orientation=orientation, coord=coord, start=start, end=end,
                    construction=facts.construction.value,
                    boundary_context=facts.boundary_context.value,
                    room_ids=[room.zone_id])
            elif room.zone_id not in entry.room_ids:
                entry.room_ids.append(room.zone_id)
    return list(walls.values()), list(opens.values())


def summarize(report: ValidationReport) -> ValidationSummary:
    statements = [_STATEMENTS[c.check_id] for c in report.checks
                  if c.passed and c.check_id in _STATEMENTS]
    warnings = [f"{_STATEMENTS.get(c.check_id, c.name)}: {c.detail}" for c in report.failures()]
    return ValidationSummary(
        passed=report.ok,
        statements=statements,
        warnings=warnings,
        checks={c.check_id: c.passed for c in report.checks},
    )


def to_demo_design(design: SolvedDesign, report: ValidationReport) -> DemoDesign:
    walls, opens = _wall_segments(design)
    doors = [DoorOut(a=d.a, b=d.b, kind=d.kind, width_m=d.width_m, x=d.center_m[0],
                     y=d.center_m[1], orientation=d.orientation)
             for d in design.interior_doors]
    entrance = design.entrance_door
    doors.append(DoorOut(a=entrance.a, b=entrance.b, kind=entrance.kind, width_m=entrance.width_m,
                         x=entrance.center_m[0], y=entrance.center_m[1],
                         orientation=entrance.orientation, is_entrance=True))
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
        validation=summarize(report),
    )
