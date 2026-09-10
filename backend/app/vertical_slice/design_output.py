"""Stage 9 — `GeometricDesign`: this vertical slice's own output DTO.

Deliberately NOT `app.geometry.geometric_design.GeometricDesign` — that DTO is built from the
live pipeline's `ArchitecturalSpec`/`RoomInstance`/`GeometrySolverResult` types (a different,
older domain model entirely; see that module's docstring). Reconciling the two — deciding
whether this slice's output replaces it, feeds it, or stays parallel — is real integration
work belonging to a later phase.

Two properties matter for the general-geometry migration:

  * EVERYTHING HERE IS IN METRES. No grid units cross this boundary. That is what lets the
    renderer stop importing solver internals (report §11, task §9): unit conversion happens
    once, here, at the contract.
  * Wall facts are ORTHOGONAL (`geometry_domain.walls.WallFacts`). `RoomOut.walls` keeps the
    raw solver `WallType` strings for continuity, and `RoomOut.wall_facts` carries the two
    independent facts the solver's single enum collapses — which is how an exterior ממ"ד wall
    can report EXTERIOR *and* RC_SAFE_ROOM at once (report §8, task §7).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.geometry_domain.walls import WallFacts

from .doors import Door
from .furniture import FurnitureCheck
from .geometry_adapter import wall_facts_for_room
from .geometry_core.engine import WallMap, net_rect_m
from .geometry_core.model import Fixture, OutdoorRegion, Rect, Side, u_to_m
from .site import SitePlan
from .windows import Window

#: (x, y, w, h) in metres.
RectM = tuple[float, float, float, float]


@dataclass(frozen=True)
class RoomOut:
    zone_id: str
    roles: tuple[str, ...]
    rect_m: RectM                               # centerline, plot-absolute, metres
    net_w_m: float
    net_h_m: float
    net_area_m2: float
    walls: dict[str, str]                       # side -> raw solver WallType (continuity)
    wall_facts: dict[str, WallFacts]            # side -> orthogonal (context, construction)


@dataclass(frozen=True)
class DoorOut:
    a: str
    b: str
    kind: str
    width_m: float
    center_m: tuple[float, float]
    orientation: str
    placeable: bool
    shared_length_m: float
    #: Architectural decisions made by the engine, drawn by the renderer — never inferred there.
    swings_into: str = ""
    hinge_m: tuple[float, float] = (0.0, 0.0)


@dataclass(frozen=True)
class WindowOut:
    zone_id: str
    side: str
    width_m: float
    center_m: tuple[float, float]
    placeable: bool


@dataclass(frozen=True)
class OutdoorOut:
    region_id: str
    classification: str
    rects_m: tuple[RectM, ...]


@dataclass(frozen=True)
class GeometricDesign:
    plot_m: RectM
    footprint_m: RectM
    rooms: tuple[RoomOut, ...]
    interior_doors: tuple[DoorOut, ...]
    entrance_door: DoorOut
    windows: tuple[WindowOut, ...]
    parking_m: tuple[RectM, ...]
    garden: tuple[OutdoorOut, ...]
    entrance_walk_m: RectM
    gross_area_m2: float
    net_area_m2: float
    wall_iterations: int


def _rect_m(r: Rect) -> RectM:
    return (u_to_m(r.x), u_to_m(r.y), u_to_m(r.w), u_to_m(r.h))


def _door_out(d: Door) -> DoorOut:
    return DoorOut(
        a=d.a, b=d.b, kind=d.kind.value, width_m=d.width_m,
        center_m=(u_to_m(d.center_u[0]), u_to_m(d.center_u[1])),
        orientation=d.orientation, placeable=d.placeable, shared_length_m=d.shared_length_m,
        swings_into=d.swings_into,
        hinge_m=(u_to_m(d.hinge_at[0]), u_to_m(d.hinge_at[1])),
    )


def _window_out(w: Window) -> WindowOut:
    return WindowOut(
        zone_id=w.zone_id, side=w.side.value, width_m=w.width_m,
        center_m=(u_to_m(w.center_u[0]), u_to_m(w.center_u[1])), placeable=w.placeable,
    )


def _outdoor_out(o: OutdoorRegion) -> OutdoorOut:
    return OutdoorOut(o.region_id, o.classification.value, tuple(_rect_m(r) for r in o.rects))


def assemble(fixture: Fixture, rects: dict[str, Rect], walls: WallMap, wall_iterations: int,
             interior_doors: list[Door], entrance_door: Door, windows: list[Window],
             furniture: list[FurnitureCheck], site: SitePlan) -> GeometricDesign:
    rooms = []
    net_total = 0.0
    for z in fixture.zones:
        r = rects.get(z.zone_id)
        if r is None:
            continue
        nw, nh, na = net_rect_m(z.zone_id, r, walls)
        net_total += na
        facts = wall_facts_for_room(z.zone_id, r, site.footprint, walls)
        rooms.append(RoomOut(
            zone_id=z.zone_id,
            roles=tuple(role.value for role in z.roles),
            rect_m=_rect_m(r),
            net_w_m=nw, net_h_m=nh, net_area_m2=na,
            walls={s.value: walls[(z.zone_id, s)].value for s in Side},
            wall_facts={s.value: facts[s] for s in Side},
        ))
    return GeometricDesign(
        plot_m=_rect_m(site.plot),
        footprint_m=_rect_m(site.footprint),
        rooms=tuple(rooms),
        interior_doors=tuple(_door_out(d) for d in interior_doors),
        entrance_door=_door_out(entrance_door),
        windows=tuple(_window_out(w) for w in windows),
        parking_m=tuple(_rect_m(p) for p in site.parking),
        garden=tuple(_outdoor_out(o) for o in site.garden),
        entrance_walk_m=_rect_m(site.entrance.path_rect),
        gross_area_m2=fixture.footprint_area_m2(),
        net_area_m2=round(net_total, 2),
        wall_iterations=wall_iterations,
    )
