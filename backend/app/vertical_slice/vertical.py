"""Vertical circulation — the stair as a first-class architectural object.

Phase 1 (`level_program.py`, `level_planner.py`, `building_coordinator.py`) produces these: a
`VerticalCore` is built by `VerticalCore.realize` from the SAME pinned rectangle both levels'
forced cuts placed — see `MULTI_LEVEL_PHASE_1_INVESTIGATION_REPORT.md` §4–§5 and the follow-up
report for the seat this core realizes (`level_planner.CoreLobbyForm`).

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

from .geometry_core.model import ProgramRole, Rect, Side, ZoneSpec

#: PARAMETER · UNVERIFIED, every value below — plausible working figures for a private house,
#: NOT sourced from any regulation (matches how `WALL_THICKNESS_M[RC_SAFE_ROOM]` is flagged in
#: `geometry_core.model`). First report §9: floor-to-floor comes from `building.FLOOR_TO_FLOOR_M`;
#: riser and going are assumed here because no rule source has supplied them yet.
RISER_M = 0.175
GOING_M = 0.28
#: Clear circulation length the entry (L0) / arrival (L1) edge must share with a HALL-role zone —
#: an assumption, not a code minimum (first report §9).
ENTRY_ZONE_M = 1.0


def risers_for(floor_to_floor_m: float) -> int:
    return round(floor_to_floor_m / RISER_M)


def straight_flight_run_m(floor_to_floor_m: float) -> float:
    """Net length of a straight flight's TREADS ONLY — one fewer going than risers, since the
    top riser is the upper floor itself."""
    return (risers_for(floor_to_floor_m) - 1) * GOING_M


def straight_flight_length_m(floor_to_floor_m: float, wall_allowance_m: float = 0.10) -> float:
    """Centerline length of the STRAIGHT flight's own rectangle — the run plus a wall allowance,
    snapped to the 5 cm grid. This is the `L` every level's forced cuts pin to."""
    raw = straight_flight_run_m(floor_to_floor_m) + wall_allowance_m
    return round(raw / 0.05) * 0.05


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
    #: Clear circulation length V5 requires to be shared with a HALL-role zone at the entry (L0)
    #: / arrival (L1) end. `None` on a core built before Phase 1 (Phase 0 tests) — V5 then falls
    #: back to `ENTRY_ZONE_M`.
    entry_zone_m: float | None = None
    arrival_zone_m: float | None = None

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

    @classmethod
    def realize(cls, core_id: str, lower_level_id: str, upper_level_id: str,
               lower_rects: dict[str, Rect], upper_rects: dict[str, Rect],
               lower_zones: tuple[ZoneSpec, ...], upper_zones: tuple[ZoneSpec, ...],
               floor_to_floor_m: float, zone_id: str = "STAIR") -> "VerticalCore":
        """Build the REALIZED core from two solved levels' rects — never from the plan that asked
        for them. `footprint_u` is the lower level's realized rect (`building_validation.V1` then
        PROVES it equals the upper's, rather than assuming it because the same cuts were forced
        on both levels — a solver bug or a coordinator mistake must be catchable here, not hidden
        by construction).

        `entry_edge`/`arrival_edge` are DIAGNOSTIC — the side of the stair rect with the longest
        shared run against a HALL-role zone, used by the renderer. They are NOT what proves V5:
        V5 re-measures the same shared-edge length independently against the realized rects, the
        way every other building check proves against realized geometry rather than a declared
        field.
        """
        from .geometry_core.engine import _side_facing  # local: engine-internal, diagnostic use only

        lower_rect, upper_rect = lower_rects[zone_id], upper_rects[zone_id]

        def best_side(rect: Rect, rects: dict[str, Rect], zones: tuple[ZoneSpec, ...]) -> Side:
            hall_ids = {z.zone_id for z in zones if ProgramRole.HALL in z.roles} - {zone_id}
            totals: dict[Side, int] = {}
            for zid in hall_ids:
                other = rects.get(zid)
                if other is None:
                    continue
                side = _side_facing(rect, other)
                if side is None:
                    continue
                totals[side] = totals.get(side, 0) + rect.shared_edge_len_u(other)
            return max(totals, key=totals.get) if totals else Side.S

        run = straight_flight_run_m(floor_to_floor_m)
        return cls(core_id, lower_level_id, upper_level_id, lower_rect,
                  entry_edge=best_side(lower_rect, lower_rects, lower_zones),
                  arrival_edge=best_side(upper_rect, upper_rects, upper_zones),
                  direction=Side.S, zone_id=zone_id,
                  going_m=run / max(risers_for(floor_to_floor_m) - 1, 1),
                  rise_m=floor_to_floor_m, entry_zone_m=ENTRY_ZONE_M, arrival_zone_m=ENTRY_ZONE_M)
