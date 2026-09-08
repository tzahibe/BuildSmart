"""Stage 5 — Windows.

New in this vertical slice (not proven by the geometry-core spike, which explicitly excluded
windows). Rule, deliberately simple: every zone whose role requires daylight gets one window
centered on its widest EXTERIOR wall, sized as a fraction of that wall's length within a
min/max band. PARAMETER · UNVERIFIED: the fraction/min/max below are plausible placeholders,
not sourced from a specific glazing-ratio code requirement (same disclosure discipline as
`geometry_core.model.WALL_THICKNESS_M`'s RC_SAFE_ROOM entry).

WET_ROOMS (bathrooms) and circulation are not required to have a window in this scope — real
codes often allow mechanical ventilation instead; modeling that choice is future work.
"""
from __future__ import annotations

from dataclasses import dataclass

from .geometry_adapter import envelope_sides
from .geometry_core.model import Fixture, ProgramRole, Rect, Side, m_to_u, u_to_m

DAYLIGHT_ROLES = frozenset({
    ProgramRole.LIVING, ProgramRole.DINING, ProgramRole.KITCHEN,
    ProgramRole.BEDROOM, ProgramRole.MASTER_BEDROOM, ProgramRole.SAFE_ROOM,
})

WINDOW_WALL_FRACTION = 0.4
WINDOW_MIN_WIDTH_M = 0.9
WINDOW_MAX_WIDTH_M = 2.0


@dataclass(frozen=True)
class Window:
    zone_id: str
    side: Side
    width_m: float
    center_u: tuple[int, int]
    placeable: bool


def _wall_length_u(rect: Rect, side: Side) -> int:
    return rect.h if side in (Side.N, Side.S) else rect.w


def _widest_exterior_side(rect: Rect, footprint: Rect) -> Side | None:
    # `envelope_sides` now lives in geometry_adapter (unchanged behaviour) — it is a
    # Rect-dependent geometric computation, and that dependency is isolated there. It remains
    # the fix for the safe-room window defect: exposure is a GEOMETRIC fact and must never be
    # read off a `WallType` whose RC precedence may have overwritten it.
    sides = envelope_sides(rect, footprint)
    if not sides:
        return None
    return max(sides, key=lambda s: _wall_length_u(rect, s))


def generate_windows(fixture: Fixture, rects: dict[str, Rect], footprint: Rect) -> list[Window]:
    windows: list[Window] = []
    min_u, max_u = m_to_u(WINDOW_MIN_WIDTH_M), m_to_u(WINDOW_MAX_WIDTH_M)
    for zone in fixture.zones:
        if not (set(zone.roles) & DAYLIGHT_ROLES):
            continue
        rect = rects.get(zone.zone_id)
        if rect is None:
            continue
        side = _widest_exterior_side(rect, footprint)
        if side is None:
            windows.append(Window(zone.zone_id, Side.N, 0.0, (rect.x, rect.y), placeable=False))
            continue
        wall_len_u = _wall_length_u(rect, side)
        width_u = max(min_u, min(max_u, int(wall_len_u * WINDOW_WALL_FRACTION)))
        placeable = width_u <= wall_len_u and width_u >= min_u
        width_u = min(width_u, wall_len_u)
        if side in (Side.N, Side.S):
            mid = rect.y + (0 if side is Side.N else rect.h)
            center = (rect.x + rect.w // 2, mid)
        else:
            mid = rect.x + (0 if side is Side.W else rect.w)
            center = (mid, rect.y + rect.h // 2)
        windows.append(Window(zone.zone_id, side, u_to_m(width_u), center, placeable))
    return windows
