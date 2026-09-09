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
from enum import Enum


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


class CorridorWidthMode(str, Enum):
    """How the person worded a corridor width, which decides what may be done with it.

    EXACT and MINIMUM are binding: a plan that does not meet them is not returned. PREFERENCE is
    attempted first and dropped with a warning if the programme cannot fit it — the distinction
    exists because "המסדרון חייב להיות לפחות 1.6 מטר" and "אני מעדיף מסדרון של 2 מטר" ask for the
    same thing and must fail differently.
    """

    EXACT = "exact"        # "מסדרון ברוחב 1.8 מטר" — plan to this width
    MINIMUM = "minimum"    # "לפחות 1.6 מטר" — never narrower; wider is fine
    PREFERENCE = "preference"


@dataclass(frozen=True)
class CorridorRequirement:
    """An authoritative corridor width, in metres, plus how binding it is."""

    width_m: float
    mode: CorridorWidthMode = CorridorWidthMode.MINIMUM

    @property
    def is_binding(self) -> bool:
        return self.mode is not CorridorWidthMode.PREFERENCE

    def satisfied_by(self, realized_m: float, *, tol_m: float = 0.005) -> bool:
        """Does a realized corridor meet this requirement?

        MINIMUM and PREFERENCE are one-sided — wider is always fine. EXACT is two-sided, but only
        downward-strict in practice: the grid is 5 cm, so a couple of millimetres of rounding must
        not fail a plan that is otherwise exactly right.
        """
        if self.mode is CorridorWidthMode.EXACT:
            # Never narrower than asked; up to one partition-half wider is accepted. The planner
            # fixes the corridor before wall types are known and budgets for the thickest wall the
            # hall might touch, so a corridor that lands slightly generous is the cost of never
            # landing short. Rejecting it would send the person to change a request that was met.
            return -tol_m <= realized_m - self.width_m <= 0.105
        return realized_m >= self.width_m - tol_m


@dataclass(frozen=True)
class ProgramSpec:
    """What the house must contain. Counts, plus the size the user asked for.

    `target_built_area_m2` is the TARGET BUILT AREA the person entered — the gross area the
    generated house should come out at, not a ceiling it merely has to stay under. It is optional
    because the site-driven scenarios (`run_general` on an L-shaped or curved parcel) have no user
    target at all; there it stays `None` and the generator keeps its original programme-minimum
    sizing, which is what those baselines were measured against.
    """

    bedrooms: int = 3
    safe_room: bool = True
    open_plan_living: bool = True
    wet_rooms: int = 2
    parking_spaces: int = 2
    target_built_area_m2: float | None = None
    #: The corridor width the person asked for, when they asked for one. `None` keeps the
    #: generator's own derived width and its existing default behaviour.
    corridor: CorridorRequirement | None = None


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
