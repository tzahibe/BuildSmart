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
from .wet_core import WetCore, compute_wet_core
from .wet_privacy import WetPrivacy, compute_wet_privacy
from .windows import Window, seam_sides_of

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
    swing_deg: float = 0.0


@dataclass(frozen=True)
class WindowOut:
    zone_id: str
    side: str
    width_m: float
    center_m: tuple[float, float]
    placeable: bool
    #: Non-regulatory status — see `windows.py` module docstring. Reports whether THIS zone got a
    #: real exterior window (`EXTERIOR_WINDOW`) or not (`MECHANICAL_VENTILATION_REQUIRED`),
    #: chiefly meaningful for a wet room (BATHROOM), which is never required to have one.
    ventilation_status: str


@dataclass(frozen=True)
class OutdoorOut:
    region_id: str
    classification: str
    rects_m: tuple[RectM, ...]


@dataclass(frozen=True)
class GeometricDesign:
    plot_m: RectM
    #: The building's BOUNDING BOX in metres — the footprint itself for a one-wing house. Kept
    #: under its old name because a frame, a building line and every existing reader want the
    #: box; `footprints_m` is the footprint proper.
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
    #: The fixture's declared open-plan groups, carried through verbatim so a consumer can tell a
    #: PUBLIC open-plan zone from any other neighbour without re-deriving it from wall types (an
    #: `OPEN` side proves two zones share a group; the absence of one proves nothing — see
    #: `_discover_open_interfaces`'s full-side precondition). Read by the demo contract's
    #: corridor-opening post-process. Empty for a closed plan.
    open_groups: tuple[tuple[str, ...], ...] = ()
    #: The concept this design realized was planned with rooms allowed past their PREFERRED
    #: maxima up to the HARD ones (`ConceptCandidate.over_preferred`). Carried for the demo
    #: contract's quality metadata; never a validation fact.
    over_preferred: bool = False
    #: The footprint as its wings, one rectangle each, in metres (`footprint.py`). One entry —
    #: equal to `footprint_m` — for every house the engine plans today.
    footprints_m: tuple[RectM, ...] = ()
    #: One `WetPrivacy` per wet room (Issue #37), additive. `()` for a caller that does not pass
    #: `wet_rooms` to `assemble` — every production caller does.
    wet_privacy: tuple[WetPrivacy, ...] = ()
    #: Plumbing-efficiency standing (Issue #44), additive. `None` only for a `GeometricDesign`
    #: built before this field existed — `assemble` always computes one.
    wet_core: WetCore | None = None

    def __post_init__(self) -> None:
        if not self.footprints_m:
            object.__setattr__(self, "footprints_m", (self.footprint_m,))


def _rect_m(r: Rect) -> RectM:
    return (u_to_m(r.x), u_to_m(r.y), u_to_m(r.w), u_to_m(r.h))


def _door_out(d: Door) -> DoorOut:
    return DoorOut(
        a=d.a, b=d.b, kind=d.kind.value, width_m=d.width_m,
        center_m=(u_to_m(d.center_u[0]), u_to_m(d.center_u[1])),
        orientation=d.orientation, placeable=d.placeable, shared_length_m=d.shared_length_m,
        swings_into=d.swings_into,
        hinge_m=(u_to_m(d.hinge_at[0]), u_to_m(d.hinge_at[1])),
        swing_deg=d.swing_deg,
    )


def _window_out(w: Window) -> WindowOut:
    return WindowOut(
        zone_id=w.zone_id, side=w.side.value, width_m=w.width_m,
        center_m=(u_to_m(w.center_u[0]), u_to_m(w.center_u[1])), placeable=w.placeable,
        ventilation_status=w.ventilation_status,
    )


def _outdoor_out(o: OutdoorRegion) -> OutdoorOut:
    return OutdoorOut(o.region_id, o.classification.value, tuple(_rect_m(r) for r in o.rects))


def assemble(fixture: Fixture, rects: dict[str, Rect], walls: WallMap, wall_iterations: int,
             interior_doors: list[Door], entrance_door: Door, windows: list[Window],
             furniture: list[FurnitureCheck], site: SitePlan,
             over_preferred: bool = False, wet_rooms: tuple = ()) -> GeometricDesign:
    rooms = []
    net_total = 0.0
    seams = seam_sides_of(fixture)
    for z in fixture.zones:
        r = rects.get(z.zone_id)
        if r is None:
            continue
        nw, nh, na = net_rect_m(z.zone_id, r, walls)
        net_total += na
        facts = wall_facts_for_room(z.zone_id, r, site.footprint, walls, wings=site.wings,
                                    seam_sides=seams.get(z.zone_id, frozenset()))
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
        open_groups=tuple(tuple(g) for g in fixture.open_groups),
        over_preferred=over_preferred,
        footprints_m=tuple(_rect_m(w) for w in site.wings),
        wet_privacy=compute_wet_privacy(fixture, rects, walls, interior_doors, wet_rooms),
        wet_core=compute_wet_core(fixture, rects, walls),
    )
