"""Stage 4 — Doors.

Reuses the exact opening-generation rule the geometry-core spike proved (`validate.py`'s
`generate_openings`: openings come ONLY from `DesiredAccessTopology`, and OPEN_CONNECTION is
always skipped — that is what keeps open-plan free of artificial doors, proof P8). This module
adds what the spike deliberately did not need: a concrete 2D door position and a physical-
placement check (a door needs real clearance on the shared wall, not just nonzero contact).
"""
from __future__ import annotations

from dataclasses import dataclass

from .geometry_core.model import ConnectionKind, Fixture, Rect, Side, m_to_u, u_to_m
from .site import EntranceWalk

INTERIOR_DOOR_WIDTH_M = 0.9
ENTRANCE_DOOR_WIDTH_M = 1.0
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


def generate_interior_doors(fixture: Fixture, rects: dict[str, Rect]) -> list[Door]:
    """One `Door` per non-OPEN_CONNECTION edge in the fixture's DesiredAccessTopology."""
    doors: list[Door] = []
    width_u = m_to_u(INTERIOR_DOOR_WIDTH_M)
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
        doors.append(Door(e.a, e.b, e.kind, INTERIOR_DOOR_WIDTH_M, center, orientation,
                           placeable, u_to_m(shared_u)))
    return doors


def build_entrance_door(entrance: EntranceWalk, footprint: Rect,
                        entrance_zone_id: str = "HALL_MAIN") -> Door:
    """The one exterior-to-interior door: street -> entrance hall. Not part of the fixture's
    DesiredAccessTopology (that graph is interior-only, see concept.py's module docstring) —
    the entrance is a site-level concern, resolved here against the footprint's street wall.

    `entrance_zone_id` defaults to the canonical fixture's hall name so the frozen baseline is
    unaffected; the concept generator passes its own hall id. Hard-coding it meant the general
    concept's hall was never seeded into the accessibility graph, and every room reported as
    unreachable."""
    width_u = m_to_u(ENTRANCE_DOOR_WIDTH_M)
    x, y = entrance.door_point_u
    on_wall = footprint.x <= x <= footprint.x2 and y == footprint.y
    placeable = on_wall and (x - footprint.x) >= width_u and (footprint.x2 - x) >= width_u
    return Door("OUTSIDE", entrance_zone_id, ConnectionKind.DOOR, ENTRANCE_DOOR_WIDTH_M,
                (x, y), "horizontal", placeable, footprint.w if on_wall else 0.0)
