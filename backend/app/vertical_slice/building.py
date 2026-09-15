"""The building as a list of levels — the multi-level domain model (Phase 0: domain and contracts).

    Building
      -> levels[]        each one a LevelPlan: TODAY'S pipeline output for one level, unchanged
      -> cores[]         the stairs (vertical.VerticalCore); empty on a single-storey house
      -> massing         plot, one outline per level, coverage

WHY A LIST OF LEVELS AND NOT A SECOND WING. `Fixture.wings` already exists and the solver iterates
wings, so "make the upper floor a second wing" looks cheap. It is wrong three ways: zone ids must
be unique within a fixture (two HALLs), `seam_leaf_sides` models wings as HORIZONTALLY adjacent
rectangles that share a wall — an upper floor shares nothing horizontally — and every downstream
stage (doors, windows, validation, assembly) reads `fixture.zones` as one flat set for one plan.
Per-level fixtures keep every existing stage's contract literally unchanged; the coupling between
levels lives in the INPUTS (a pinned stair leaf) and in one building-level validator
(`building_validation`), not in the engine.

SINGLE-STOREY COMPATIBILITY IS THE INVARIANT THIS MODULE IS BUILT AROUND. `Building.single_level`
wraps the design the demo produces today; `levels[0].design` IS that design (same object), the
totals equal its own gross/net, and nothing about the design changes. A one-storey house is a
`Building` with one level and no cores — the two-storey path, when it exists, is the same type
with two levels and one core, never a different code path.

Nothing here reads `HouseConcept`: the concept reaches the engine only through the level programs
the allocation stage will derive from it (Phase 2). `Level.floor_to_floor_m` is a PARAMETER ·
UNVERIFIED in exactly the sense `WALL_THICKNESS_M[RC_SAFE_ROOM]` is: a plausible working figure,
not a sourced regulation, and the stair's rise depends on it.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from .design_output import GeometricDesign, RectM
from .validation import ValidationReport
from .vertical import VerticalCore

if TYPE_CHECKING:  # typing only — keeps this module free of the generator's import weight
    from .concept_generator import ConceptCandidate
    from .general_pipeline import SafetyReport

#: PARAMETER · UNVERIFIED — a plausible floor-to-floor height for a private house. The stair's rise
#: and, through a riser/tread rule, its going derive from it. Not a regulation figure.
FLOOR_TO_FLOOR_M = 3.0


class LevelKind(str, Enum):
    GROUND = "GROUND"
    UPPER = "UPPER"


@dataclass(frozen=True)
class Level:
    """One storey. `index` 0 is the entrance level; `elevation_m` is measured from its floor."""

    level_id: str
    index: int
    kind: LevelKind
    elevation_m: float = 0.0
    floor_to_floor_m: float = FLOOR_TO_FLOOR_M

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError(f"level index must be >= 0, got {self.index}")
        if (self.index == 0) != (self.kind is LevelKind.GROUND):
            raise ValueError("level 0 is the GROUND level and no other level is")
        if self.floor_to_floor_m <= 0:
            raise ValueError("floor_to_floor_m must be positive")


class LevelEntryKind(str, Enum):
    """How a person arrives on a level. The ground level is entered from the street through its
    front door; every other level is entered from a stair's arrival edge. This is what a per-level
    reachability check seeds from — `OUTSIDE` on the ground, the stair zone above."""

    STREET_DOOR = "STREET_DOOR"
    STAIR_ARRIVAL = "STAIR_ARRIVAL"


@dataclass(frozen=True)
class LevelEntry:
    kind: LevelEntryKind
    #: The zone the person arrives IN: the entrance hall behind the front door, or the stair zone.
    zone_id: str
    core_id: str | None = None

    def __post_init__(self) -> None:
        if self.kind is LevelEntryKind.STAIR_ARRIVAL and self.core_id is None:
            raise ValueError("a STAIR_ARRIVAL entry must name the core it arrives from")
        if self.kind is LevelEntryKind.STREET_DOOR and self.core_id is not None:
            raise ValueError("a STREET_DOOR entry has no core")


@dataclass(frozen=True)
class LevelPlan:
    """One level taken all the way through today's pipeline: concept, design, checks. The design
    is the SAME `GeometricDesign` the single-storey demo produces — nothing is re-shaped here."""

    level: Level
    entry: LevelEntry
    design: GeometricDesign
    validation: ValidationReport
    concept: "ConceptCandidate | None" = None
    safety: "SafetyReport | None" = None

    @property
    def ok(self) -> bool:
        return self.validation.ok and (self.safety is None or self.safety.ok)

    @property
    def outline_m(self) -> RectM:
        return self.design.footprint_m


def rect_area_m2(rect: RectM) -> float:
    return round(rect[2] * rect[3], 4)


def rect_contains(outer: RectM, inner: RectM, tol: float = 1e-6) -> bool:
    ox, oy, ow, oh = outer
    ix, iy, iw, ih = inner
    return (ix >= ox - tol and iy >= oy - tol
            and ix + iw <= ox + ow + tol and iy + ih <= oy + oh + tol)


@dataclass(frozen=True)
class Massing:
    """The plot and one outline per level, index-aligned with `Building.levels`.

    The SITE limits only `level_outlines_m[0]` — the footprint touching the land. Upper outlines
    are limited by the outline below them (containment, checked by V2), never by the plot directly.
    """

    plot_m: RectM
    level_outlines_m: tuple[RectM, ...]

    def __post_init__(self) -> None:
        if not self.level_outlines_m:
            raise ValueError("a massing needs at least the ground outline")

    @property
    def ground_outline_m(self) -> RectM:
        return self.level_outlines_m[0]

    @property
    def ground_coverage(self) -> float:
        """Ground outline over plot — the one ratio a coverage rule would be checked against.
        Reported, never used as geometry (a coverage limit is validation, not a shrunken region)."""
        plot = rect_area_m2(self.plot_m)
        return round(rect_area_m2(self.ground_outline_m) / plot, 4) if plot > 0 else 0.0

    @property
    def retreat_m2(self) -> float:
        """Area of every level's outline NOT covered by the level above it — the roof an upper
        retreat exposes (a terrace, once something classifies it). Zero on a single level."""
        total = 0.0
        for lower, upper in zip(self.level_outlines_m, self.level_outlines_m[1:]):
            total += rect_area_m2(lower) - rect_area_m2(upper)
        return round(total, 4)


@dataclass(frozen=True)
class Building:
    levels: tuple[LevelPlan, ...]
    massing: Massing
    cores: tuple[VerticalCore, ...] = ()

    def __post_init__(self) -> None:
        if not self.levels:
            raise ValueError("a building has at least one level")
        indices = [plan.level.index for plan in self.levels]
        if indices != list(range(len(self.levels))):
            raise ValueError(f"levels must be ordered 0..n-1 by index, got {indices}")
        ids = [plan.level.level_id for plan in self.levels]
        if len(set(ids)) != len(ids):
            raise ValueError(f"level ids must be unique, got {ids}")
        if len(self.massing.level_outlines_m) != len(self.levels):
            raise ValueError("massing carries one outline per level")
        for plan in self.levels:
            expected = (LevelEntryKind.STREET_DOOR if plan.level.index == 0
                        else LevelEntryKind.STAIR_ARRIVAL)
            if plan.entry.kind is not expected:
                raise ValueError(f"level {plan.level.level_id} must be entered by {expected.value}")
            if plan.entry.core_id is not None and not any(
                    c.core_id == plan.entry.core_id and c.touches(plan.level.level_id)
                    for c in self.cores):
                raise ValueError(f"level {plan.level.level_id} arrives from core "
                                 f"{plan.entry.core_id}, which does not reach it")
        for core in self.cores:
            for level_id in core.level_ids:
                if level_id not in ids:
                    raise ValueError(f"core {core.core_id} names unknown level {level_id}")
        if len(self.levels) > 1 and not self.cores:
            raise ValueError("a building with more than one level needs a vertical core")

    @property
    def story_count(self) -> int:
        return len(self.levels)

    @property
    def ground(self) -> LevelPlan:
        return self.levels[0]

    def level(self, level_id: str) -> LevelPlan:
        for plan in self.levels:
            if plan.level.level_id == level_id:
                return plan
        raise KeyError(level_id)

    @property
    def total_gross_m2(self) -> float:
        """Σ over levels of each level's gross — GFA in the spec-V2 sense. On one level this is
        exactly that level's `gross_area_m2`, which is what the demo has always reported."""
        return round(sum(plan.design.gross_area_m2 for plan in self.levels), 2)

    @property
    def total_net_m2(self) -> float:
        return round(sum(plan.design.net_area_m2 for plan in self.levels), 2)

    @property
    def ok(self) -> bool:
        return all(plan.ok for plan in self.levels)

    @classmethod
    def single_level(cls, design: GeometricDesign, validation: ValidationReport, *,
                     concept: "ConceptCandidate | None" = None,
                     safety: "SafetyReport | None" = None) -> "Building":
        """Today's one-storey design as a building. The design object is carried as-is."""
        level = Level(level_id="L0", index=0, kind=LevelKind.GROUND)
        entry = LevelEntry(LevelEntryKind.STREET_DOOR, zone_id=design.entrance_door.b)
        plan = LevelPlan(level=level, entry=entry, design=design, validation=validation,
                         concept=concept, safety=safety)
        return cls(levels=(plan,), massing=Massing(design.plot_m, (design.footprint_m,)))
