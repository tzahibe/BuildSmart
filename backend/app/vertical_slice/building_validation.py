"""Building-level validation — the checks that have no meaning on a single level.

Per-level checks (C1–C21, `validation.py`) run inside each level's pipeline and are not repeated
here. This module holds the V-checks, the invariants BETWEEN levels named in
MULTI_LEVEL_AND_HOUSE_CONCEPT_ARCHITECTURE_REPORT.md §6.1:

    V1  the core's rectangle is identical on every level it touches
    V2  every upper outline lies inside the outline below it (no cantilever)
    V3  no room on any level overlaps a core's rectangle except the core's own zone
    V4  every room on every level is reachable from OUTSIDE over the REALIZED connections of all
        levels joined by the core's realized entry and arrival openings
    V5  the core's entry and arrival edges face circulation — never a bedroom, a bathroom or the
        safe room
    V6  two safe rooms on different levels are vertically aligned
    V7  area accounting: each level's gross is its outline's area; coverage is the ground outline
        over the plot; the ground outline lies inside the plot

ONLY CHECKS THAT ACTUALLY RUN APPEAR IN THE REPORT — the same rule the demo contract applies to
its statements. Phase 0 runs V2 and V7, both computable from the massing and the level designs.
V1, V3 and V6 need a realized core and V4/V5 need the realized access graph of two levels; they
arrive with the first two-level plan (Phase 1) and are listed above so the numbering is fixed
now, not so a reader believes they are enforced.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .building import Building, rect_area_m2, rect_contains

#: The tolerance a level's gross may differ from its outline's area by — float noise on figures
#: that were both rounded from the same 5 cm grid, nothing more.
TOL_M2 = 0.01


@dataclass(frozen=True)
class BuildingCheck:
    check_id: str
    name: str
    passed: bool
    detail: str = ""


@dataclass
class BuildingValidationReport:
    checks: list[BuildingCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.passed for c in self.checks)

    def add(self, check_id: str, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append(BuildingCheck(check_id, name, passed, detail))

    def failures(self) -> list[BuildingCheck]:
        return [c for c in self.checks if not c.passed]


def validate_building(building: Building) -> BuildingValidationReport:
    rep = BuildingValidationReport()
    outlines = building.massing.level_outlines_m

    # V2 — containment. Cantilevers are deferred with it: an upper outline that leaves the outline
    # below is a building this stage does not draw.
    bad = []
    for lower_plan, upper_plan, lower, upper in zip(building.levels, building.levels[1:],
                                                     outlines, outlines[1:]):
        if not rect_contains(lower, upper):
            bad.append(f"{upper_plan.level.level_id} outline {upper} leaves "
                       f"{lower_plan.level.level_id} outline {lower}")
    rep.add("V2", "every upper outline lies inside the outline below", not bad,
            "; ".join(bad) or ("single level" if building.story_count == 1
                               else f"{building.story_count - 1} upper outline(s) contained"))

    # V7 — accounting. Each level's gross is the area of ITS outline (not the ground's, not a
    # total); the ground outline is on the plot; coverage is a ratio a rule could be checked
    # against. The totals on `Building` are sums of these, so proving the parts proves the sums.
    bad = []
    for plan, outline in zip(building.levels, outlines):
        if plan.design.footprint_m != outline:
            bad.append(f"{plan.level.level_id} design footprint {plan.design.footprint_m} is not "
                       f"its massing outline {outline}")
        expected = rect_area_m2(outline)
        if abs(plan.design.gross_area_m2 - expected) > TOL_M2:
            bad.append(f"{plan.level.level_id} gross {plan.design.gross_area_m2} m2 is not its "
                       f"outline's {expected} m2")
    if not rect_contains(building.massing.plot_m, building.massing.ground_outline_m):
        bad.append(f"ground outline {building.massing.ground_outline_m} leaves the plot "
                   f"{building.massing.plot_m}")
    coverage = building.massing.ground_coverage
    if not 0.0 < coverage <= 1.0 + 1e-9:
        bad.append(f"ground coverage {coverage} is not a ratio in (0, 1]")
    rep.add("V7", "area accounting: level gross = outline area; ground outline on the plot",
            not bad,
            "; ".join(bad) or f"total gross {building.total_gross_m2} m2 over "
                              f"{building.story_count} level(s); ground coverage {coverage:.2%}")
    return rep
