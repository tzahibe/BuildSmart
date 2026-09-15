"""Vertical circulation — the stair as a first-class architectural object.

DOMAIN ONLY (multi-level Phase 0). Nothing produces a `VerticalCore` yet: the concept generator has
no way to seat one (`_allocations` places no circulation room but HALL — see
MULTI_LEVEL_AND_HOUSE_CONCEPT_ARCHITECTURE_REPORT.md §1 items 4–5), and a `Building` today has one
level and no cores. The type exists now so that the contract, the validator and the renderer are
written against it rather than against a `STAIRWELL` room that happens to be in two plans.

WHAT THE PLANNER NEEDS, and nothing more: one rectangle, the same on every level the core
touches; which edge is entered at the bottom and which is stepped off at the top; the direction
of travel. Treads, risers, handrails and headroom are the renderer's and the rules layer's —
`going_m`, `width_m` and `rise_m` are carried as PARAMETERS derived from a floor-to-floor height
and a riser/tread rule that is not modelled here, never as literals.

The stair occupies REAL AREA on both levels. On each it is realized as an ordinary
`ProgramRole.STAIRWELL` zone (a leaf of that level's slicing tree, pinned by forced cuts), so C1
proves nothing overlaps it and C2 counts it; the building-level check V1 proves the two
rectangles are one rectangle.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .geometry_core.model import Rect, Side


class VerticalCoreKind(str, Enum):
    STAIR = "STAIR"


class StairArchetype(str, Enum):
    """Phase 1 supports STRAIGHT only: one rectangle, entry and arrival on its two short ends, the
    shape the `STAIRWELL` template's aspect 4.0 already admits. L and U flights are two rectangles
    or a near-square with a landing and belong beside the hub lobby — a later phase."""

    STRAIGHT = "STRAIGHT"
    L_SHAPED = "L_SHAPED"
    U_HALF_LANDING = "U_HALF_LANDING"


@dataclass(frozen=True)
class VerticalCore:
    """One stair connecting two adjacent levels.

    `footprint_u` is plot-absolute centerline geometry in grid units — the same frame every
    level's solved rectangles are in — and is BY CONSTRUCTION identical on both levels (the same
    forced cuts pin the same leaf). Building validation V1 checks that it is, rather than trusting
    the construction.

    `zone_id` is the id of the `STAIRWELL` zone that realizes this core on each level's fixture.
    """

    core_id: str
    lower_level_id: str
    upper_level_id: str
    footprint_u: Rect
    #: Lower level: the edge the bottom step is entered from. Must face circulation (V5).
    entry_edge: Side
    #: Upper level: the edge you step off onto circulation. Must face circulation (V5).
    arrival_edge: Side
    #: Direction of travel from the bottom step.
    direction: Side
    kind: VerticalCoreKind = VerticalCoreKind.STAIR
    archetype: StairArchetype = StairArchetype.STRAIGHT
    zone_id: str | None = None
    #: PARAMETER · UNVERIFIED when set: derived from floor-to-floor and a riser/tread rule that
    #: lives in a RuleSet, not here. `None` until a rule supplies them.
    width_m: float | None = None
    going_m: float | None = None
    rise_m: float | None = None

    def __post_init__(self) -> None:
        if self.lower_level_id == self.upper_level_id:
            raise ValueError("a vertical core connects two DIFFERENT levels")
        if self.footprint_u.w <= 0 or self.footprint_u.h <= 0:
            raise ValueError(f"a vertical core needs a real footprint, got {self.footprint_u}")
        if self.zone_id is None:
            object.__setattr__(self, "zone_id", self.core_id)

    @property
    def level_ids(self) -> tuple[str, str]:
        return (self.lower_level_id, self.upper_level_id)

    def touches(self, level_id: str) -> bool:
        return level_id in self.level_ids
