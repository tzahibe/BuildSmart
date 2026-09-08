"""Stage 1 — `ArchitecturalSpec`: the vertical slice's input contract.

This is deliberately tiny. It is NOT the `app.architect.models.ArchitecturalSpec` used by the
live `app/design` pipeline (a different, older domain model) — building a translator between
the two is real integration work, out of scope for "first vertical slice only, no new
domain-model research." This module's `ArchitecturalSpec` is this slice's own, self-contained
input, and is named to match the pipeline the review approved
(ArchitecturalSpec -> Concept/DesiredAccessTopology -> Site -> Geometry Core -> ...).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlotSpec:
    """A rectangular plot, street-facing edge at y=0. PARAMETER · UNVERIFIED: setbacks below
    are plausible placeholders, not sourced from a specific municipal plan (matches how
    `RC_SAFE_ROOM` thickness is flagged in geometry_core.model — no regulation number here is
    a verified legal figure)."""

    width_m: float
    depth_m: float
    front_setback_m: float = 5.5   # building line offset from the street edge (parking lives here)
    side_setback_m: float = 3.0
    rear_setback_m: float = 4.0

    def buildable_origin_m(self) -> tuple[float, float]:
        return (self.side_setback_m, self.front_setback_m)

    def buildable_size_m(self) -> tuple[float, float]:
        return (
            self.width_m - 2 * self.side_setback_m,
            self.depth_m - self.front_setback_m - self.rear_setback_m,
        )


@dataclass(frozen=True)
class ProgramSpec:
    """What the house must contain. Counts only — the concept stage decides the actual rooms."""

    bedrooms: int = 3
    safe_room: bool = True
    open_plan_living: bool = True
    wet_rooms: int = 2
    parking_spaces: int = 2


@dataclass(frozen=True)
class ArchitecturalSpec:
    plot: PlotSpec
    program: ProgramSpec


def demo_spec() -> ArchitecturalSpec:
    """The one scenario this vertical slice targets: ~150-180 m² single-floor private house,
    3 bedrooms + safe room, open-plan LDK, 2 wet rooms, 2 parking spaces, entrance + garden."""
    return ArchitecturalSpec(
        plot=PlotSpec(width_m=20.0, depth_m=24.0),
        program=ProgramSpec(bedrooms=3, safe_room=True, open_plan_living=True,
                             wet_rooms=2, parking_spaces=2),
    )
