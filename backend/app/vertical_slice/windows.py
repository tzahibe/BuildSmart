"""Stage 5 — Windows.

New in this vertical slice (not proven by the geometry-core spike, which explicitly excluded
windows). Rule, deliberately simple: every zone whose role requires daylight gets one window
centered on its widest EXTERIOR wall, sized as a fraction of that wall's length within a
min/max band. PARAMETER · UNVERIFIED: the fraction/min/max below are plausible placeholders,
not sourced from a specific glazing-ratio code requirement (same disclosure discipline as
`geometry_core.model.WALL_THICKNESS_M`'s RC_SAFE_ROOM entry).

`DAYLIGHT_ROLES` and `WET_ROOM_PREFERRED_ROLES` below are DERIVED from `exposure_policy.py`
(Issue #19) — that module is the single declared policy per `ProgramRole`; this module only
consumes it. A role whose `window` policy is REQUIRED lands in `DAYLIGHT_ROLES` (validation's C8
gates on that set); PREFERRED lands in `WET_ROOM_PREFERRED_ROLES` (best-effort, never gating —
real codes often allow mechanical ventilation instead of a window, and this slice does not
attempt to model which one an authoritative rule would demand for these roles). A real exterior
wall should not go to waste when a PREFERRED-tier room happens to land on one — most wet rooms
already do, since a room at the outer edge of a west/east column borders the footprint's own
exterior by construction — so `generate_windows` attempts a (smaller, PROVISIONAL — not sourced
from any external tool or verified glazing code) window for `WET_ROOM_PREFERRED_ROLES` too:
a real exterior wall and enough of it, or nothing, never fabricated, and never gating C8 either
way. A role whose policy is NONE (HALL, CIRCULATION, STORAGE, …) is not attempted at all.

Every generated `Window` carries `ventilation_status`, a plain descriptive (non-regulatory) label
— `EXTERIOR_WINDOW` when one was placed, `MECHANICAL_VENTILATION_REQUIRED` when it was not —
useful for a caller to report which rooms got daylight and which did not, without asserting
that either state is itself what any code requires.
"""
from __future__ import annotations

from dataclasses import dataclass

from .exposure_policy import EXPOSURE_POLICY, ExposureRequirement
from .geometry_adapter import envelope_sides
from .geometry_core.model import Fixture, Rect, Side, m_to_u, u_to_m

#: Roles whose window policy is REQUIRED — validation's C8 gates on exactly this set.
DAYLIGHT_ROLES = frozenset(
    role for role, policy in EXPOSURE_POLICY.items()
    if policy.window is ExposureRequirement.REQUIRED
)

WINDOW_WALL_FRACTION = 0.4
WINDOW_MIN_WIDTH_M = 0.9
WINDOW_MAX_WIDTH_M = 2.0

#: Roles whose window policy is PREFERRED — attempted best-effort, never required, never gating
#: C8 (`validation.py`). See module docstring.
WET_ROOM_PREFERRED_ROLES = frozenset(
    role for role, policy in EXPOSURE_POLICY.items()
    if policy.window is ExposureRequirement.PREFERRED
)

#: Smaller than a habitable room's window on purpose (a bathroom customarily takes a narrower,
#: often frosted, opening) — PRODUCT POLICY placeholders, PROVISIONAL and unverified, same
#: disclosure as `WINDOW_WALL_FRACTION` above and NOT copied from any external tool's suggestion.
WET_ROOM_WINDOW_WALL_FRACTION = 0.25
WET_ROOM_WINDOW_MIN_WIDTH_M = 0.5
WET_ROOM_WINDOW_MAX_WIDTH_M = 1.0

#: Non-regulatory status labels for `Window.ventilation_status` — see module docstring.
EXTERIOR_WINDOW = "EXTERIOR_WINDOW"
MECHANICAL_VENTILATION_REQUIRED = "MECHANICAL_VENTILATION_REQUIRED"


@dataclass(frozen=True)
class Window:
    zone_id: str
    side: Side
    width_m: float
    center_u: tuple[int, int]
    placeable: bool
    ventilation_status: str = EXTERIOR_WINDOW


def _wall_length_u(rect: Rect, side: Side) -> int:
    return rect.h if side in (Side.N, Side.S) else rect.w


def _widest_exterior_side(rect: Rect, footprint: Rect, wings: tuple[Rect, ...] = (),
                          seam_sides: frozenset[Side] = frozenset()) -> Side | None:
    # `envelope_sides` now lives in geometry_adapter (unchanged behaviour) — it is a
    # Rect-dependent geometric computation, and that dependency is isolated there. It remains
    # the fix for the safe-room window defect: exposure is a GEOMETRIC fact and must never be
    # read off a `WallType` whose RC precedence may have overwritten it.
    sides = envelope_sides(rect, footprint, wings=wings, seam_sides=seam_sides)
    if not sides:
        return None
    return max(sides, key=lambda s: _wall_length_u(rect, s))


def seam_sides_of(fixture: Fixture) -> dict[str, frozenset[Side]]:
    """Per zone, the sides the fixture declares as seams to another wing — never exterior, however
    the geometry looks. Empty for every zone of a one-wing fixture."""
    out: dict[str, set[Side]] = {}
    for wing in fixture.wings:
        for zone_id, side in wing.seam_leaf_sides:
            out.setdefault(zone_id, set()).add(side)
    return {zone_id: frozenset(sides) for zone_id, sides in out.items()}


def generate_windows(fixture: Fixture, rects: dict[str, Rect], footprint: Rect,
                     wings: tuple[Rect, ...] = ()) -> list[Window]:
    """`footprint` is the building's bounding box; `wings` its rectangles (one, today). A window
    goes on the widest side of the room that is on its OWN wing's envelope and not a seam."""
    seams = seam_sides_of(fixture)
    windows: list[Window] = []
    for zone in fixture.zones:
        roles = set(zone.roles)
        if roles & DAYLIGHT_ROLES:
            min_m, max_m, fraction = WINDOW_MIN_WIDTH_M, WINDOW_MAX_WIDTH_M, WINDOW_WALL_FRACTION
        elif roles & WET_ROOM_PREFERRED_ROLES:
            min_m, max_m, fraction = (WET_ROOM_WINDOW_MIN_WIDTH_M, WET_ROOM_WINDOW_MAX_WIDTH_M,
                                       WET_ROOM_WINDOW_WALL_FRACTION)
        else:
            continue
        rect = rects.get(zone.zone_id)
        if rect is None:
            continue
        min_u, max_u = m_to_u(min_m), m_to_u(max_m)
        side = _widest_exterior_side(rect, footprint, wings, seams.get(zone.zone_id, frozenset()))
        if side is None:
            windows.append(Window(zone.zone_id, Side.N, 0.0, (rect.x, rect.y), placeable=False,
                                   ventilation_status=MECHANICAL_VENTILATION_REQUIRED))
            continue
        wall_len_u = _wall_length_u(rect, side)
        width_u = max(min_u, min(max_u, int(wall_len_u * fraction)))
        placeable = width_u <= wall_len_u and width_u >= min_u
        width_u = min(width_u, wall_len_u)
        if side in (Side.N, Side.S):
            mid = rect.y + (0 if side is Side.N else rect.h)
            center = (rect.x + rect.w // 2, mid)
        else:
            mid = rect.x + (0 if side is Side.W else rect.w)
            center = (mid, rect.y + rect.h // 2)
        status = EXTERIOR_WINDOW if placeable else MECHANICAL_VENTILATION_REQUIRED
        windows.append(Window(zone.zone_id, side, u_to_m(width_u), center, placeable,
                               ventilation_status=status))
    return windows
