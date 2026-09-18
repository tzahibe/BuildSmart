"""Exposure policy — Issue #19.

A room's need for the building envelope is really two separate questions: must it TOUCH an
exterior wall at all (a planning-topology fact, checked by `validation.py`'s C19), and does it
need a WINDOW once it does (a sizing fact, checked by C8 — "a window of at least the minimum
width is placed where required"). Before this module the two were conflated into one set,
`windows.py::DAYLIGHT_ROLES`, gated only by C8: an interior bedroom and an exterior bedroom with
a too-short wall both failed the same way, for different reasons, and only a handful of roles
were covered at all (FAMILY_ROOM, STUDY, DRESSING_ROOM, LAUNDRY, STORAGE, CIRCULATION had no
policy whatsoever).

This table is now the single declared policy per `ProgramRole`, and `windows.py`'s
`DAYLIGHT_ROLES`/`WET_ROOM_PREFERRED_ROLES` are DERIVED from it rather than hand-maintained
separately.

REQUIRED means the validator fails closed if the fact does not hold. PREFERRED means
`generate_windows` still attempts it best-effort (never fabricated, never gating). NONE means
neither is attempted.

Owner's decision (recorded in the Issue #19 contract): REQUIRED/REQUIRED for LIVING, DINING,
KITCHEN, BEDROOM, MASTER_BEDROOM, SAFE_ROOM, FAMILY_ROOM, STUDY; PREFERRED/PREFERRED for
BATHROOM, TOILET, DRESSING_ROOM; NONE for HALL, CIRCULATION, STORAGE, ENTRANCE, STAIRWELL, FLEX.
LAUNDRY was NONE at that Issue's own scope — its Issue (#21) now sets it to REQUIRED/REQUIRED: a
laundry room the person explicitly asked for must be an enclosed room with a real exterior wall
and a window, not a windowless utility box, same as any other habitable room. `generate_windows`
sizes LAUNDRY's window narrower than a habitable room's (`LAUNDRY_WINDOW_MIN_WIDTH_M`, 0.6 m) —
still REQUIRED-tier, so C8 still gates on it, just at the smaller service-window size.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .geometry_core.model import ProgramRole


class ExposureRequirement(str, Enum):
    REQUIRED = "REQUIRED"
    PREFERRED = "PREFERRED"
    NONE = "NONE"


@dataclass(frozen=True)
class ExposurePolicy:
    exterior_wall: ExposureRequirement
    window: ExposureRequirement


_REQUIRED = ExposurePolicy(ExposureRequirement.REQUIRED, ExposureRequirement.REQUIRED)
_PREFERRED = ExposurePolicy(ExposureRequirement.PREFERRED, ExposureRequirement.PREFERRED)
_NONE = ExposurePolicy(ExposureRequirement.NONE, ExposureRequirement.NONE)

#: Every `ProgramRole` has an entry — the policy covers every room type, not a subset.
EXPOSURE_POLICY: dict[ProgramRole, ExposurePolicy] = {
    ProgramRole.ENTRANCE: _NONE,
    ProgramRole.HALL: _NONE,
    ProgramRole.LIVING: _REQUIRED,
    ProgramRole.DINING: _REQUIRED,
    ProgramRole.KITCHEN: _REQUIRED,
    ProgramRole.FAMILY_ROOM: _REQUIRED,
    ProgramRole.BEDROOM: _REQUIRED,
    ProgramRole.MASTER_BEDROOM: _REQUIRED,
    ProgramRole.STUDY: _REQUIRED,
    ProgramRole.DRESSING_ROOM: _PREFERRED,
    ProgramRole.SAFE_ROOM: _REQUIRED,
    ProgramRole.BATHROOM: _PREFERRED,
    ProgramRole.TOILET: _PREFERRED,
    #: Issue #21: an explicitly requested laundry room is guaranteed an exterior wall and a window
    #: (a smaller, service-sized one — see `windows.py::LAUNDRY_WINDOW_MIN_WIDTH_M`), gated closed
    #: by C19/C8 like any other REQUIRED role.
    ProgramRole.LAUNDRY: _REQUIRED,
    ProgramRole.STORAGE: _NONE,
    ProgramRole.CIRCULATION: _NONE,
    ProgramRole.STAIRWELL: _NONE,
    ProgramRole.FLEX: _NONE,
}

#: Every role whose `exterior_wall` policy is REQUIRED — what C19 gates on.
REQUIRED_EXTERIOR_ROLES = frozenset(
    role for role, policy in EXPOSURE_POLICY.items()
    if policy.exterior_wall is ExposureRequirement.REQUIRED
)
