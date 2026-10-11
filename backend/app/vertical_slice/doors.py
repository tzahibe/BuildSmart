"""Stage 4 — Doors.

Reuses the exact opening-generation rule the geometry-core spike proved (`validate.py`'s
`generate_openings`: openings come ONLY from `DesiredAccessTopology`, and OPEN_CONNECTION is
always skipped — that is what keeps open-plan free of artificial doors, proof P8). This module
adds what the spike deliberately did not need: a concrete 2D door position and a physical-
placement check (a door needs real clearance on the shared wall, not just nonzero contact).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import access_rules
from .access_rules import DoorKind
from .geometry_core.model import (
    ConnectionKind,
    Fixture,
    ProgramRole,
    Rect,
    Side,
    m_to_u,
    u_to_m,
)
from . import footprint as footprint_module
from .site import EntranceWalk

#: Unchanged widths (`access_rules.DOOR_WIDTH_M`) kept as module constants so nothing else that
#: imported them by name has to change.
INTERIOR_DOOR_WIDTH_M = access_rules.DOOR_WIDTH_M[DoorKind.ROOM_DOOR]
ENTRANCE_DOOR_WIDTH_M = access_rules.DOOR_WIDTH_M[DoorKind.ENTRANCE_DOOR]
DOOR_MARGIN_M = 0.1  # clearance from a corner on each side of the door


@dataclass(frozen=True)
class Door:
    a: str
    b: str
    kind: ConnectionKind
    width_m: float
    center_u: tuple[int, int]     # midpoint of the opening, in plot-absolute grid units
    orientation: str              # "vertical" (in an E/W-facing wall) or "horizontal" (N/S-facing)
    placeable: bool
    shared_length_m: float
    #: WHICH ROOM THE LEAF SWINGS INTO, and which end of the opening it is hinged at. Both are
    #: architectural decisions, so the ENGINE makes them and the renderer only draws them — the same
    #: rule that stopped the drawing inferring where doors are in the first place. `swings_into` is
    #: a zone id; `hinge_at` is the (x, y) grid point of the hinged jamb.
    swings_into: str = ""
    hinge_at: tuple[int, int] = (0, 0)
    #: The direction the OPEN leaf's tip points from `hinge_at`, in degrees, measured the same way
    #: `orientation`'s axes are (0=+x/east, 90=+y/south, 180=-x/west, 270=-y/north; y grows toward
    #: the plot's far edge, matching every other grid coordinate in this module). Always exactly 90
    #: degrees from the wall the door is set into (0/180 for a "vertical" door, 90/270 for a
    #: "horizontal" one) — `door_clearance.py` uses it, with `hinge_at` and `width_m`, to build the
    #: swing envelope, and the renderer uses it to place the open leaf without looking up a room.
    swing_deg: float = 0.0


def _side_between(a: Rect, b: Rect) -> Side | None:
    if a.x2 == b.x:
        return Side.E
    if b.x2 == a.x:
        return Side.W
    if a.y2 == b.y:
        return Side.S
    if b.y2 == a.y:
        return Side.N
    return None


#: Roles a door should NOT swing into: you do not push a door open into a corridor people are
#: walking down. Everything else takes the swing.
_NEVER_SWING_INTO = (ProgramRole.HALL, ProgramRole.CIRCULATION)


def swing_deg_for(rects: dict[str, Rect], into: str, center: tuple[int, int],
                  orientation: str) -> float:
    """The open leaf's direction (see `Door.swing_deg`) for a leaf swinging into zone `into`,
    perpendicular to the wall the opening sits in, toward that zone's own side of it. Exported so
    `door_clearance.py` can recompute it when it flips a door's swing to the OTHER zone."""
    room = rects.get(into)
    cx, cy = center
    if orientation == "horizontal":                 # opening runs along x; swing is +/- y
        room_mid = (room.y + room.y2) / 2 if room is not None else cy + 1
        return 90.0 if room_mid > cy else 270.0
    room_mid = (room.x + room.x2) / 2 if room is not None else cx + 1  # opening along y; swing +/- x
    return 0.0 if room_mid > cx else 180.0


def hinge_at_for(rects: dict[str, Rect], into: str, center: tuple[int, int],
                 orientation: str, width_u: int) -> tuple[int, int]:
    """The hinged jamb (see `Door.hinge_at`) for a leaf swinging into zone `into`: the jamb NEARER
    that zone's own corner, so the open leaf lies back along a wall instead of standing in the
    middle of the floor. Exported for the same reason as `swing_deg_for`."""
    room = rects.get(into)
    cx, cy = center
    half = width_u // 2
    if room is None:
        return (cx - half, cy) if orientation == "horizontal" else (cx, cy - half)
    if orientation == "horizontal":                 # opening runs along x, in an N/S wall
        low, high = (cx - half, cy), (cx + half, cy)
        nearer_low = abs(cx - half - room.x) <= abs(room.x2 - (cx + half))
    else:                                           # opening runs along y, in an E/W wall
        low, high = (cx, cy - half), (cx, cy + half)
        nearer_low = abs(cy - half - room.y) <= abs(room.y2 - (cy + half))
    return low if nearer_low else high


def _swing(fixture: Fixture, rects: dict[str, Rect], a: str, b: str,
           center: tuple[int, int], orientation: str,
           width_u: int) -> tuple[str, tuple[int, int], float]:
    """Which room the leaf opens into, which jamb it hangs from, and which way it swings.

    Two conventions, both ordinary and both deterministic:

      * A door swings INTO the room being entered, never out into circulation — a leaf opening into
        a corridor blocks the corridor. Between two ordinary rooms the smaller one takes it, which
        is why a bathroom door opens inward.
      * It hangs from the jamb NEARER the room's corner, so the open leaf lies back along a wall
        instead of standing in the middle of the floor.

    `door_clearance.py`'s conflict resolution can override this default `into` by calling
    `hinge_at_for`/`swing_deg_for` directly for the OTHER zone — this function only picks the
    default before any conflict is known.
    """
    roles = {z.zone_id: z.roles for z in fixture.zones}

    def is_circulation(zone_id: str) -> bool:
        return any(r in _NEVER_SWING_INTO for r in roles.get(zone_id, ()))

    if is_circulation(a) and not is_circulation(b):
        into = b
    elif is_circulation(b) and not is_circulation(a):
        into = a
    else:
        ra, rb = rects.get(a), rects.get(b)
        into = a if (ra and rb and ra.w * ra.h <= rb.w * rb.h) else b

    return into, hinge_at_for(rects, into, center, orientation, width_u), \
        swing_deg_for(rects, into, center, orientation)


def generate_interior_doors(fixture: Fixture, rects: dict[str, Rect]) -> list[Door]:
    """One `Door` per non-OPEN_CONNECTION edge in the fixture's DesiredAccessTopology.

    Width comes from `access_rules.door_kind_for_zones` on the edge's two roles: SERVICE_DOOR
    (0.8 m) for LAUNDRY/STORAGE/TOILET, ROOM_DOOR (0.9 m, `INTERIOR_DOOR_WIDTH_M`) otherwise.
    """
    doors: list[Door] = []
    roles_of = {z.zone_id: z.roles for z in fixture.zones}
    margin_u = m_to_u(DOOR_MARGIN_M)
    for e in fixture.access.edges:
        if e.kind is ConnectionKind.OPEN_CONNECTION:
            continue
        ra, rb = rects.get(e.a), rects.get(e.b)
        if ra is None or rb is None:
            continue
        side = _side_between(ra, rb)
        if side is None:
            continue
        shared_u = ra.shared_edge_len_u(rb)
        if shared_u <= 0:
            continue
        door_kind = access_rules.door_kind_for_zones(roles_of.get(e.a, ()), roles_of.get(e.b, ()))
        width_m = access_rules.DOOR_WIDTH_M[door_kind]
        width_u = m_to_u(width_m)
        placeable = shared_u >= width_u + 2 * margin_u
        if side in (Side.E, Side.W):
            lo, hi = max(ra.y, rb.y), min(ra.y2, rb.y2)
            mid_y = (lo + hi) // 2
            center = (ra.x2 if side is Side.E else ra.x, mid_y)
            orientation = "vertical"
        else:
            lo, hi = max(ra.x, rb.x), min(ra.x2, rb.x2)
            mid_x = (lo + hi) // 2
            center = (mid_x, ra.y2 if side is Side.S else ra.y)
            orientation = "horizontal"
        swings_into, hinge_at, swing_deg = _swing(fixture, rects, e.a, e.b, center, orientation, width_u)
        doors.append(Door(e.a, e.b, e.kind, width_m, center, orientation,
                           placeable, u_to_m(shared_u), swings_into, hinge_at, swing_deg))
    return doors


#: Which zones a front door may open into, best first — the ARRIVAL-ROOM POLICY (Issue #20). A
#: visitor enters a house through its circulation or the living room — never straight into a
#: kitchen or dining room (a plan whose only street-fronting public room was the dining room used
#: to get its front door there, which reads as a random room, not an entrance) and never into a
#: private room (BEDROOM, MASTER_BEDROOM, SAFE_ROOM, STUDY, DRESSING_ROOM) or a wet/service room —
#: neither of which was ever in this tuple. `resolve_entrance` returns `None`, not a lesser zone,
#: when nothing in this tuple fronts the street.
ENTRANCE_ZONE_PRIORITY = (
    ProgramRole.HALL, ProgramRole.CIRCULATION, ProgramRole.LIVING,
)

#: The same roles as a set, for a plain "is this an allowed arrival room?" test — C23 (defense in
#: depth on every realized plan, whichever path produced it) reads this rather than re-deriving it
#: from the priority tuple above.
ALLOWED_ENTRANCE_ROLES = frozenset(ENTRANCE_ZONE_PRIORITY)


def resolve_entrance(fixture: Fixture, rects: dict[str, Rect],
                     footprint: Rect, wings: tuple[Rect, ...] = ()) -> tuple[str, int, int] | None:
    """Which zone the front door can actually open into, and where on the street wall it goes.

    THE DEFECT THIS REPLACES. The entrance used to be placed at the footprint's horizontal centre
    and labelled `HALL` regardless of what was behind it. In the front-band parti the hall sits
    BEHIND the public band and never touches the street wall at all, so the front door was drawn in
    the middle of the dining room's exterior wall while the access graph recorded a connection to a
    hall 6.7 m away — and C5 then computed "every room is reachable from the entrance" from that
    non-existent connection.

    Read off the realized geometry instead: the zones that genuinely front the street, taken in
    priority order. Returns the chosen zone and the SPAN of street wall the door may sit in — a
    span rather than a point, because the caller also has to keep the walk clear of the parking
    bays, and only it knows where those are. `None` when no acceptable zone fronts the street, so
    the caller can refuse rather than invent a door.

    `footprint` is the building's bounding box and `wings` its rectangles; the street wall is the
    bounding box's y = min line, and a zone fronts it when its own wing reaches that line. The
    corner clearance below is measured against the zone's WING — the wall the door actually sits
    in — which is the bounding box itself when there is one wing.
    """
    roles = {z.zone_id: z.roles for z in fixture.zones}
    width_u = m_to_u(ENTRANCE_DOOR_WIDTH_M)
    wings = wings or (footprint,)

    fronting = []
    for zone_id, rect in rects.items():
        if rect.y != footprint.y:                     # not on the street wall
            continue
        wing = footprint_module.wing_of(wings, rect)
        span_start, span_end = max(rect.x, wing.x), min(rect.x2, wing.x2)
        if span_end - span_start < width_u:           # too little frontage to hold a door
            continue
        best = None
        for rank, role in enumerate(ENTRANCE_ZONE_PRIORITY):
            if role in roles.get(zone_id, ()):
                best = rank
                break
        if best is not None:
            fronting.append((best, zone_id, span_start, span_end))

    if not fronting:
        return None

    # Best role wins; a tie goes to the widest frontage, then to the leftmost, so the choice is
    # deterministic rather than dependent on dict ordering.
    fronting.sort(key=lambda f: (f[0], -(f[3] - f[2]), f[2]))
    _, zone_id, span_start, span_end = fronting[0]

    # The existing placeability rule still applies: a full door width of wall on each side, measured
    # against the WING's street wall, so the door is not jammed into a corner of the building.
    wing = footprint_module.wing_of(wings, rects[zone_id])
    low = max(span_start, wing.x + width_u)
    high = min(span_end, wing.x2 - width_u)
    if low > high:
        return None
    return zone_id, low, high


def street_fronting_roles(fixture: Fixture, rects: dict[str, Rect], footprint: Rect,
                          wings: tuple[Rect, ...] = ()) -> tuple[str, ...]:
    """Every distinct role of a zone that fronts the street with enough frontage for a door —
    WHATEVER that role is, allowed or not by the arrival-room policy above.

    Used to report what a refused entrance found: `resolve_entrance` returns `None` when nothing
    ALLOWED fronts the street, and a refusal that just says "no entrance" without saying what WAS
    there (a kitchen, a dining room) is not something a person can act on — see the fixture test
    in `test_entrance_policy.py` for that use.

    `app.demo.service._street_fronting_roles` is a SEPARATE implementation of the same idea, not
    this function reused: the product refusal path works off `DemoDesign` (metre-scale, already
    realized) rather than this engine-level `Fixture`/`Rect` (grid-unit, pre-realization) pair, so
    it cannot call this one without threading grid-unit wing geometry back through the product
    layer for a message-text nicety. See that function's own docstring for the deliberate
    difference in strictness (it does not require full door-width frontage, since it only NAMES
    rooms for an already-gated message and can safely be coarser, never stricter, than this one).
    """
    roles_of = {z.zone_id: z.roles for z in fixture.zones}
    width_u = m_to_u(ENTRANCE_DOOR_WIDTH_M)
    wings = wings or (footprint,)
    found: set[str] = set()
    for zone_id, rect in rects.items():
        if rect.y != footprint.y:
            continue
        wing = footprint_module.wing_of(wings, rect)
        span_start, span_end = max(rect.x, wing.x), min(rect.x2, wing.x2)
        if span_end - span_start < width_u:
            continue
        found.update(r.value for r in roles_of.get(zone_id, ()))
    return tuple(sorted(found))


def build_entrance_door(entrance: EntranceWalk, footprint: Rect,
                        entrance_zone_id: str = "HALL_MAIN",
                        wings: tuple[Rect, ...] = ()) -> Door:
    """The one exterior-to-interior door: street -> entrance hall. Not part of the fixture's
    DesiredAccessTopology (that graph is interior-only, see concept.py's module docstring) —
    the entrance is a site-level concern, resolved here against the footprint's street wall.

    `entrance_zone_id` defaults to the canonical fixture's hall name so the frozen baseline is
    unaffected; the concept generator passes its own hall id. Hard-coding it meant the general
    concept's hall was never seeded into the accessibility graph, and every room reported as
    unreachable."""
    width_u = m_to_u(ENTRANCE_DOOR_WIDTH_M)
    x, y = entrance.door_point_u
    # The wall the door sits in is the STREET WING's — the one wing when there is one; with
    # several, the wing whose street-side wall holds the door point (None when none does).
    wing = footprint_module.wing_on_street_line(wings or (footprint,), x, y)
    on_wall = wing is not None and y == footprint.y
    placeable = on_wall and (x - wing.x) >= width_u and (wing.x2 - x) >= width_u
    # A front door opens INWARD, always — outward into the street is not a thing. The street wall
    # is always the footprint's north edge (`site.py` puts the street at y=0), so "inward" is
    # always +y (south, `swing_deg=90.0`) in this module's grid convention — never derived from a
    # room lookup, the same as every other fact about this door.
    half = width_u // 2
    return Door("OUTSIDE", entrance_zone_id, ConnectionKind.DOOR, ENTRANCE_DOOR_WIDTH_M,
                (x, y), "horizontal", placeable, wing.w if on_wall else 0.0,
                entrance_zone_id, (x - half, y), 90.0)
