"""Structured concept pattern prior (Issue #77, Concept Engine v2 2/5).

Turns the architectural references (`docs/architecture_reference/references/`) and the 21-plan
census (`specs/005-hub-private-wing/spec.md` §1) into a small, deterministic table of concept
*patterns* — a `CirculationClass` × `ZoningSplit` × `WetCoreGrouping` × `MasterPlacement`
combination, with an `applicability` (which briefs/outlines it is worth trying for) and a
`frequency` (how strongly the evidence favours it, used only to ORDER the answer) — and one
lookup:

    patterns_for(brief, outline) -> tuple[Pattern, ...]

Answers exactly one question, in the owner's own words (2026-09-20): "which concepts are worth
trying, and in what order?" — descriptive metadata only, never geometry, never an images/plan
file. `applicability` is a PRIOR, not a feasibility gate: a returned pattern can still turn out
infeasible once a real outline is solved (the existing generator/solver already rejects those
cases with a precise reason) — this module never claims otherwise, and nothing in the pipeline
calls it yet (no runtime behavior change; wiring it into selection is Concept Engine v2's own
later stage, out of scope here).

Every `Pattern` cites its own evidence: either a `specs/005-hub-private-wing/spec.md` §1 census
line (a measured fact over 21 professional plans) or archetype ids from
`docs/architecture_reference/references/index.json` (counted via that file's own `concept` block
— see `test_reference_index.py`), or both. See each `Pattern`'s `source` field.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Protocol, runtime_checkable

from . import reference_benchmark
from .concept_spec import CirculationClass, EntranceSide, MasterPlacement, WetCoreGrouping, ZoningSplit


@runtime_checkable
class Brief(Protocol):
    """Duck-typed: the programme counts `patterns_for` keys on — the same fields
    `app.vertical_slice.spec.ProgramSpec` already carries (`bedrooms`, `wet_rooms`); `levels`
    ("single"/"multi", matching `references/index.json`'s own enum) defaults to `"single"` via
    `getattr` for any brief type that doesn't carry it yet (today's `ProgramSpec` does not)."""

    bedrooms: int
    wet_rooms: int


@runtime_checkable
class Outline(Protocol):
    """Duck-typed: an outline's own width/depth, before any geometry is solved — the same
    `.width_m`/`.depth_m` shape `reference_benchmark.classify_footprint_family` reads off a
    realized design's `.footprint`. `shape` ("RECTANGLE"/"L") is optional via `getattr`, matching
    that function's own default."""

    width_m: float
    depth_m: float


def _footprint_family(outline: Outline) -> str:
    """`reference_benchmark.classify_footprint_family`, reused (not re-derived) — see that
    function's own docstring for the ratio/shape rule. Adapts `outline` into the `design`-shaped
    object that function expects (`.footprint.width_m/.depth_m`, optional `.outline.shape`)."""
    design_like = SimpleNamespace(footprint=outline, outline=outline)
    return reference_benchmark.classify_footprint_family(design_like)


@dataclass(frozen=True)
class Applicability:
    """Which briefs/outlines a `Pattern` is worth trying for. A PRIOR, deliberately permissive
    (see the module docstring) — only genuinely evidenced constraints narrow a band below "the
    whole realistic private-house range"; see each `Pattern`'s own citation for what, if anything,
    narrows it."""

    footprint_families: tuple[str, ...]
    width_band_m: tuple[float, float]
    depth_band_m: tuple[float, float]
    bedrooms_range: tuple[int, int]
    wet_rooms_range: tuple[int, int]
    levels: tuple[str, ...]

    def matches(self, footprint_family: str, width_m: float, depth_m: float, bedrooms: int,
               wet_rooms: int, levels: str) -> bool:
        return (
            footprint_family in self.footprint_families
            and self.width_band_m[0] <= width_m <= self.width_band_m[1]
            and self.depth_band_m[0] <= depth_m <= self.depth_band_m[1]
            and self.bedrooms_range[0] <= bedrooms <= self.bedrooms_range[1]
            and self.wet_rooms_range[0] <= wet_rooms <= self.wet_rooms_range[1]
            and levels in self.levels
        )


@dataclass(frozen=True)
class Pattern:
    """One concept pattern record — the same descriptive vocabulary
    `docs/architecture_reference/references/index.json`'s `concept` block uses
    (`app.vertical_slice.concept_spec`'s enums), plus `applicability` and a `frequency` used only
    to order `patterns_for`'s answer (ties broken by this tuple's position in `PATTERNS`, i.e.
    documented order — see `patterns_for`)."""

    name: str
    circulation_class: CirculationClass
    zoning_split: ZoningSplit
    wet_core_grouping: WetCoreGrouping
    master_placement: MasterPlacement
    entrance_side: EntranceSide
    applicability: Applicability
    frequency: float
    source: str


#: A private house's realistic footprint size range — the same band every `Applicability` below
#: uses for `width_band_m`/`depth_band_m` unless a specific citation narrows it further (see each
#: `Pattern`'s `source`). Not itself a footprint-family discriminator (`classify_footprint_family`
#: already decides that from `outline`'s own width/depth ratio) — just the outer bound of what a
#: V1-scope private house's footprint spans (`docs/wiki/decisions/private-house-v1-scope.md`).
_ANY_SIZE_M = (3.0, 30.0)
_ANY_BEDROOMS = (1, 8)
_ANY_WET_ROOMS = (0, 5)
_ANY_LEVELS = ("single", "multi")

PATTERNS: tuple[Pattern, ...] = (
    # ---------------------------------------------------------------------------- rectangle
    Pattern(
        name="HUB_LOBBY_RECTANGLE",
        circulation_class=CirculationClass.HUB_LOBBY,
        zoning_split=ZoningSplit.FRONT_REAR,
        wet_core_grouping=WetCoreGrouping.MIXED,
        master_placement=MasterPlacement.HUB_FOOT,
        entrance_side=EntranceSide.FRONT,
        applicability=Applicability(("rectangle",), _ANY_SIZE_M, _ANY_SIZE_M, _ANY_BEDROOMS,
                                    _ANY_WET_ROOMS, _ANY_LEVELS),
        frequency=18 / 21,
        source='specs/005-hub-private-wing/spec.md §1, "Private-wing circulation" row: '
               '"Compact room lobby (מבואת חדרים) ... ~18/21" of 21 professional plans; '
               "archetype ids rect-4br-family, rect-5br-ensuite, rect-3br-hub-lobby, "
               "rect-6br-large, rect-3br-multi (index.json)",
    ),
    Pattern(
        name="SPINE_RECTANGLE",
        circulation_class=CirculationClass.SPINE,
        zoning_split=ZoningSplit.SIDE_BY_SIDE,
        wet_core_grouping=WetCoreGrouping.ALL_SHARED,
        master_placement=MasterPlacement.WING_END,
        entrance_side=EntranceSide.FRONT,
        applicability=Applicability(("rectangle",), _ANY_SIZE_M, _ANY_SIZE_M, _ANY_BEDROOMS,
                                    _ANY_WET_ROOMS, _ANY_LEVELS),
        frequency=5 / 10,
        source="index.json rectangle-family entries tagged spine (5 of 10): rect-3br-compact, "
               "rect-2br-starter, rect-4br-safe-room, rect-4br-multi, rect-2br-annex",
    ),
    # -------------------------------------------------------------------------- wide-rectangle
    Pattern(
        name="FRONT_BAND_WIDE",
        circulation_class=CirculationClass.FRONT_BAND,
        zoning_split=ZoningSplit.FRONT_REAR,
        wet_core_grouping=WetCoreGrouping.ALL_SHARED,
        master_placement=MasterPlacement.WING_END,
        entrance_side=EntranceSide.FRONT,
        applicability=Applicability(("wide-rectangle",), _ANY_SIZE_M, _ANY_SIZE_M, _ANY_BEDROOMS,
                                    _ANY_WET_ROOMS, _ANY_LEVELS),
        frequency=4 / 8,
        source="index.json wide-rectangle entries tagged front-band (4 of 8): "
               "wide-3br-front-band, wide-4br-front-band, wide-3br-multi, wide-4br-flex",
    ),
    Pattern(
        name="HUB_LOBBY_WIDE",
        circulation_class=CirculationClass.HUB_LOBBY,
        zoning_split=ZoningSplit.FRONT_REAR,
        wet_core_grouping=WetCoreGrouping.ALL_SHARED,
        master_placement=MasterPlacement.HUB_FOOT,
        entrance_side=EntranceSide.FRONT,
        applicability=Applicability(("wide-rectangle",), _ANY_SIZE_M, _ANY_SIZE_M, _ANY_BEDROOMS,
                                    _ANY_WET_ROOMS, _ANY_LEVELS),
        frequency=2 / 8,
        source="index.json wide-rectangle entries tagged hub-lobby (2 of 8): wide-5br-hub, "
               'wide-2br-multi; the census\'s ~18/21 room-lobby dominance '
               "(specs/005-hub-private-wing/spec.md §1) is not itself width-segmented",
    ),
    Pattern(
        name="TWO_WING_WIDE",
        circulation_class=CirculationClass.TWO_WING,
        zoning_split=ZoningSplit.WRAPPED,
        wet_core_grouping=WetCoreGrouping.ALL_SHARED,
        master_placement=MasterPlacement.OWN_WING,
        entrance_side=EntranceSide.FRONT,
        applicability=Applicability(("wide-rectangle",), (12.0, 30.0), _ANY_SIZE_M,
                                    _ANY_BEDROOMS, _ANY_WET_ROOMS, ("single",)),
        frequency=1 / 8,
        source="index.json wide-6br-large ('six bedrooms split across two side-by-side wings'); "
               "wide-4br-front-band annotation.md: \"at 12.5 m or more of frontage, the plot "
               'supports a genuine side-by-side bedroom-wing regime" (the 12.0 m width floor)',
    ),
    # ------------------------------------------------------------------------------ narrow-deep
    Pattern(
        name="SPINE_NARROW_DEEP",
        circulation_class=CirculationClass.SPINE,
        zoning_split=ZoningSplit.SIDE_BY_SIDE,
        wet_core_grouping=WetCoreGrouping.ALL_SHARED,
        master_placement=MasterPlacement.WING_END,
        entrance_side=EntranceSide.FRONT,
        applicability=Applicability(("narrow-deep",), _ANY_SIZE_M, _ANY_SIZE_M, _ANY_BEDROOMS,
                                    _ANY_WET_ROOMS, _ANY_LEVELS),
        frequency=8 / 8,
        source="index.json every narrow-deep entry tagged spine (8 of 8): deep-3br-spine, "
               "deep-4br-spine, deep-2br-small, deep-5br-spine, deep-3br-multi, "
               "deep-4br-safe-room, deep-2br-multi, deep-6br-large — each annotation states the "
               "narrow lot leaves no width for a hub",
    ),
    Pattern(
        name="HUB_LOBBY_NARROW_DEEP",
        circulation_class=CirculationClass.HUB_LOBBY,
        zoning_split=ZoningSplit.FRONT_REAR,
        wet_core_grouping=WetCoreGrouping.MIXED,
        master_placement=MasterPlacement.HUB_FOOT,
        entrance_side=EntranceSide.FRONT,
        applicability=Applicability(("narrow-deep",), _ANY_SIZE_M, _ANY_SIZE_M, _ANY_BEDROOMS,
                                    _ANY_WET_ROOMS, ("single",)),
        frequency=0.10,
        source="index.json deep-2br-small annotation.md Trade-offs: \"a narrower lot simply "
               "can't reach the hub-parti quality tier the wider entries in this set can\" — "
               "implying a hub becomes worth trying as width increases; kept low-priority "
               "pending a real wide narrow-deep archetype in this set",
    ),
    # ------------------------------------------------------------------------------------- L
    Pattern(
        name="TWO_WING_L",
        circulation_class=CirculationClass.TWO_WING,
        zoning_split=ZoningSplit.WRAPPED,
        wet_core_grouping=WetCoreGrouping.ALL_SHARED,
        master_placement=MasterPlacement.OWN_WING,
        entrance_side=EntranceSide.ENTRY_COURT,
        applicability=Applicability(("L",), _ANY_SIZE_M, _ANY_SIZE_M, _ANY_BEDROOMS,
                                    _ANY_WET_ROOMS, _ANY_LEVELS),
        frequency=6 / 6,
        source="index.json every L entry tagged two-wing (6 of 6): l-3br-corner, "
               "l-4br-wide-plot, l-5br-two-wing, l-3br-multi, l-2br-compact, l-4br-safe-room; "
               'l-5br-two-wing annotation.md: "two wings joined at a seam ... is the census\'s '
               'dominant pattern for the 13 of 21 reference plans that weren\'t simple '
               'rectangles"',
    ),
    Pattern(
        name="HUB_LOBBY_L",
        circulation_class=CirculationClass.HUB_LOBBY,
        zoning_split=ZoningSplit.WRAPPED,
        wet_core_grouping=WetCoreGrouping.MIXED,
        master_placement=MasterPlacement.HUB_FOOT,
        entrance_side=EntranceSide.ENTRY_COURT,
        applicability=Applicability(("L",), _ANY_SIZE_M, _ANY_SIZE_M, (3, 8), (1, 5),
                                    _ANY_LEVELS),
        frequency=0.15,
        source="specs/005-hub-private-wing/spec.md FR-1: the hub parti is offered 'in addition "
               "to' the existing partis, so an L massing's own private wing can still adopt a "
               "hub organisation; the 3-bedroom floor borrows index.json rect-3br-hub-lobby "
               'annotation.md\'s own trade-off ("a dedicated hub-lobby only pays off when three '
               'or more rooms genuinely branch from it"); no L archetype in this set '
               "demonstrates it yet",
    ),
    # ------------------------------------------------------------------------------ irregular
    #
    # `classify_footprint_family` never returns "irregular" today (see its own docstring) — the
    # engine has no massing capability that would produce one. These three patterns exist for the
    # same reason `CirculationClass.BRANCHED`/`RING` do (see that enum's docstring): so this
    # module does not need to change the day a future massing capability produces one.
    Pattern(
        name="RING_IRREGULAR",
        circulation_class=CirculationClass.RING,
        zoning_split=ZoningSplit.WRAPPED,
        wet_core_grouping=WetCoreGrouping.ALL_SHARED,
        master_placement=MasterPlacement.OWN_WING,
        entrance_side=EntranceSide.ENTRY_COURT,
        applicability=Applicability(("irregular",), (16.0, 30.0), (16.0, 30.0), (3, 8), (1, 5),
                                    _ANY_LEVELS),
        frequency=2 / 21,
        source='specs/005-hub-private-wing/spec.md §1: "ring around a patio in 2" of 21 '
               "professional plans; archetype ids irr-4br-courtyard, irr-4br-multi-courtyard "
               '(index.json notes: "large plot (frontage ≳ 20 m)")',
    ),
    Pattern(
        name="BRANCHED_IRREGULAR",
        circulation_class=CirculationClass.BRANCHED,
        zoning_split=ZoningSplit.SIDE_BY_SIDE,
        wet_core_grouping=WetCoreGrouping.ALL_SHARED,
        master_placement=MasterPlacement.OWN_WING,
        entrance_side=EntranceSide.SIDE,
        applicability=Applicability(("irregular",), _ANY_SIZE_M, _ANY_SIZE_M, _ANY_BEDROOMS,
                                    _ANY_WET_ROOMS, ("single",)),
        frequency=1 / 4,
        source="index.json irr-3br-t-shape annotation.md: \"the T's stem holds the shared "
               'circulation connecting both arms"',
    ),
    Pattern(
        name="TWO_WING_IRREGULAR",
        circulation_class=CirculationClass.TWO_WING,
        zoning_split=ZoningSplit.WRAPPED,
        wet_core_grouping=WetCoreGrouping.ALL_SHARED,
        master_placement=MasterPlacement.OWN_WING,
        entrance_side=EntranceSide.SIDE,
        applicability=Applicability(("irregular",), _ANY_SIZE_M, _ANY_SIZE_M, _ANY_BEDROOMS,
                                    _ANY_WET_ROOMS, ("single",)),
        frequency=1 / 4,
        source="index.json irr-5br-angled annotation.md cites the census's 13/21 non-rectangular "
               "majority (the same evidence l-5br-two-wing's TWO_WING_L pattern uses)",
    ),
)


def patterns_for(brief: Brief, outline: Outline) -> tuple[Pattern, ...]:
    """The 2-3 concept patterns worth trying for `brief`/`outline`, best first.

    Deterministic: keyed by `reference_benchmark.classify_footprint_family` (via `outline`), the
    outline's own width/depth, and the programme counts (`brief.bedrooms`/`.wet_rooms`) — same
    inputs, same answer, every run. Ordered by `frequency` descending; ties broken by each
    `Pattern`'s position in `PATTERNS` (documented order). Returns at most 3 (never fabricates a
    default when `PATTERNS` has fewer matches than 3, and never fewer than 2 for any footprint
    family × programme combination the frozen 432-context corpus contains — see
    `test_concept_patterns.py`)."""
    footprint_family = _footprint_family(outline)
    width_m = outline.width_m
    depth_m = outline.depth_m
    bedrooms = brief.bedrooms
    wet_rooms = getattr(brief, "wet_rooms", 0)
    levels = getattr(brief, "levels", "single")

    matches = [p for p in PATTERNS
              if p.applicability.matches(footprint_family, width_m, depth_m, bedrooms, wet_rooms,
                                         levels)]
    ordered = sorted(matches, key=lambda p: (-p.frequency, PATTERNS.index(p)))
    return tuple(ordered[:3])
