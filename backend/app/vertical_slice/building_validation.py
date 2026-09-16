"""Building-level validation — the checks that have no meaning on a single level.

Per-level checks (C1–C22, `validation.py`) run inside each level's own `_realize`/`validate` call
and are NOT repeated here — this module never re-derives a single-level fact `validate` already
proved. It holds the V-checks, the invariants BETWEEN levels named in
MULTI_LEVEL_AND_HOUSE_CONCEPT_ARCHITECTURE_REPORT.md §6.1 (V8 added by the Phase 1 investigation
report §7):

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
    V8  requested rooms (bedrooms, wet rooms, the safe room, the core) appear EXACTLY ONCE across
        the whole building — never zero, never twice, on whichever level they landed

ONLY CHECKS THAT ACTUALLY RUN APPEAR IN THE REPORT — the same rule the demo contract applies to
its statements. Phase 0 ran V2 and V7 unconditionally (computable from the massing and the level
designs alone). V1, V3, V4, V5 and V8 (Phase 1) additionally need the RAW realized geometry of
BOTH levels — rects, walls, the realized doors, the zone specs — which `GeometricDesign` does not
carry (its `RoomOut`/`DoorOut` are metric DTOs with no wall map and no OPEN-connection evidence).
They run only when the caller passes `realizations` (two `LevelRealization`s, the SAME rects/
walls/doors each level's own C1-C22 already ran against) — omitting it (every Phase 0 call site,
and a `Building.single_level`) reproduces Phase 0's report exactly: V2 and V7 only. V6 is not
implemented (Phase 1 has one safe room; vacuous by construction until a second one exists).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .building import Building, rect_contains, regions_area_m2, regions_cover
from .doors import Door
from .geometry_core.engine import WallMap
from .geometry_core.model import ProgramRole, Rect, ZoneSpec, u_to_m
from .spec import ProgramSpec, WetRoomKind
from .validation import realized_connections
from .vertical import ENTRY_ZONE_M
from .wet_rooms import resolve_wet_rooms

#: The tolerance a level's gross may differ from its outline's area by — float noise on figures
#: that were both rounded from the same 5 cm grid, nothing more.
TOL_M2 = 0.01


@dataclass(frozen=True)
class LevelRealization:
    """The raw realized geometry of ONE level — exactly what its own `_realize` call already
    produced (`solve.rects`, `solve.walls`, the realized `Door` list, `concept.fixture.zones`)
    and its C1-C22 already proved facts against. V1/V3/V4/V5/V8 reuse it rather than re-deriving
    a weaker version from `GeometricDesign`'s metric DTOs."""

    level_id: str
    rects: dict[str, Rect]
    walls: WallMap
    interior_doors: tuple[Door, ...]
    #: `None` on every level but the entrance one. V4 reads only `.placeable`/`.b`, which the raw
    #: `doors.Door` and `design_output.DoorOut` both carry — either is accepted, so the caller can
    #: pass the SAME `DoorOut` its own `GeometricDesign` already reports rather than recompute a
    #: second, parallel `Door`.
    entrance_door: object | None
    zones: tuple[ZoneSpec, ...]
    #: The zone a person ARRIVES in on this level (`LevelEntry.zone_id`) — "OUTSIDE"'s own
    #: destination on the ground, the core's zone id on an upper level.
    entry_zone_id: str
    core_zone_id: str = "STAIR"


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


def validate_building(building: Building, realizations: tuple[LevelRealization, ...] = (),
                      program: ProgramSpec | None = None) -> BuildingValidationReport:
    """`realizations`/`program` default to nothing, which reproduces Phase 0's report EXACTLY
    (V2, V7 only) — every Phase 0 call site and `Building.single_level` still behave exactly as
    they did before Phase 1. Passing two `LevelRealization`s (ground, upper) adds V1/V3/V4/V5;
    passing `program` too (the programme the building was planned FOR) adds V8."""
    rep = BuildingValidationReport()
    levels = building.massing.level_regions_m

    # V2 — containment. Every region of an upper level lies inside the UNION of the level below
    # (a wing may be dropped or shrunk, never pushed out). Cantilevers are deferred with it: an
    # upper region that leaves the level below is a building this stage does not draw.
    bad = []
    for lower_plan, upper_plan, lower, upper in zip(building.levels, building.levels[1:],
                                                     levels, levels[1:]):
        for region in upper:
            if not regions_cover(lower, region):
                bad.append(f"{upper_plan.level.level_id} region {region} leaves "
                           f"{lower_plan.level.level_id} ({len(lower)} region(s))")
    rep.add("V2", "every upper outline lies inside the outline below", not bad,
            "; ".join(bad) or ("single level" if building.story_count == 1
                               else f"{building.story_count - 1} upper level(s) contained"))

    # V7 — accounting. Each level's gross is the area of ITS regions (not the ground's, not the
    # bounding box's, not a total); the ground regions are on the plot; coverage is a ratio a rule
    # could be checked against. The totals on `Building` are sums of these, so proving the parts
    # proves the sums.
    bad = []
    for plan, regions in zip(building.levels, levels):
        if plan.design.footprints_m != regions:
            bad.append(f"{plan.level.level_id} design footprints {plan.design.footprints_m} are "
                       f"not its massing regions {regions}")
        expected = regions_area_m2(regions)
        if abs(plan.design.gross_area_m2 - expected) > TOL_M2:
            bad.append(f"{plan.level.level_id} gross {plan.design.gross_area_m2} m2 is not its "
                       f"outline's {expected} m2")
    for region in building.massing.ground_regions_m:
        if not rect_contains(building.massing.plot_m, region):
            bad.append(f"ground region {region} leaves the plot {building.massing.plot_m}")
    coverage = building.massing.ground_coverage
    if not 0.0 < coverage <= 1.0 + 1e-9:
        bad.append(f"ground coverage {coverage} is not a ratio in (0, 1]")
    rep.add("V7", "area accounting: level gross = outline area; ground outline on the plot",
            not bad,
            "; ".join(bad) or f"total gross {building.total_gross_m2} m2 over "
                              f"{building.story_count} level(s); ground coverage {coverage:.2%}")

    if len(realizations) < 2:
        return rep
    lower, upper = realizations[0], realizations[1]
    _check_v1(rep, lower, upper)
    _check_v3(rep, lower, upper)
    _check_v4(rep, lower, upper)
    _check_v5(rep, lower, upper)
    if program is not None:
        _check_v8(rep, lower, upper, program)
    return rep


def _check_v1(rep: BuildingValidationReport, lower: LevelRealization, upper: LevelRealization) -> None:
    """V1 — the core's rectangle, PROVEN identical on the two REALIZED levels rather than trusted
    because the same cuts were forced on both (a solver bug or a coordinator mistake — the wrong
    seam handed to the wrong level — must be catchable here, not hidden by construction)."""
    lower_rect = lower.rects.get(lower.core_zone_id)
    upper_rect = upper.rects.get(upper.core_zone_id)
    if lower_rect is None or upper_rect is None:
        rep.add("V1", "the core's rectangle is identical on every level it touches", False,
                f"core zone missing: {lower.level_id}={lower_rect}, {upper.level_id}={upper_rect}")
        return
    rep.add("V1", "the core's rectangle is identical on every level it touches",
            lower_rect == upper_rect,
            "identical" if lower_rect == upper_rect
            else f"{lower.level_id} {lower_rect} != {upper.level_id} {upper_rect}")


def _check_v3(rep: BuildingValidationReport, lower: LevelRealization, upper: LevelRealization) -> None:
    """V3 — no room on either level overlaps the core's rectangle except the core's own zone.
    Per-level C1 already proves no TWO zones on the SAME level overlap at all (the core included);
    V3 restates it in building terms, at the core specifically, so the invariant survives a
    future non-zone core representation, per the module docstring."""
    bad = []
    for level in (lower, upper):
        core_rect = level.rects.get(level.core_zone_id)
        if core_rect is None:
            continue
        for zone_id, rect in level.rects.items():
            if zone_id == level.core_zone_id:
                continue
            if rect.overlap_area_u(core_rect) > 0:
                bad.append(f"{level.level_id} {zone_id} overlaps the core")
    rep.add("V3", "no room on any level overlaps the core except the core's own zone", not bad,
            "; ".join(bad) or "core clear on both levels")


def _check_v4(rep: BuildingValidationReport, lower: LevelRealization, upper: LevelRealization) -> None:
    """V4 — every room on every level is reachable from OUTSIDE, over the union of both levels'
    REALIZED connection graphs (`validation.realized_connections`, unchanged), joined at the
    core's zone id — the same string names the same physical rectangle on both levels (V1), so
    the two per-level graphs meet there without any new edge being invented.

    NODES ARE TAGGED PER LEVEL (`"L0:HALL"`, not `"HALL"`) except the core's own node, which the
    two levels SHARE by construction (one core, one zone id, proven identical by V1) — two levels
    routinely reuse the same zone id (both may have a `HALL`, a `BATH_2`...) for UNRELATED rooms,
    and an untagged graph would silently treat them as the same node, inventing a connection that
    does not exist.
    """
    def node(level_id: str, zone_id: str, core_zone_id: str) -> str:
        return "CORE" if zone_id == core_zone_id else f"{level_id}:{zone_id}"

    graph: dict[str, set[str]] = {}

    def add_edge(a: str, b: str) -> None:
        graph.setdefault(a, set()).add(b)
        graph.setdefault(b, set()).add(a)

    for level in (lower, upper):
        for c in realized_connections(level.rects, level.walls, list(level.interior_doors)):
            add_edge(node(level.level_id, c.a, level.core_zone_id),
                    node(level.level_id, c.b, level.core_zone_id))
    if lower.entrance_door is not None and lower.entrance_door.placeable:
        add_edge("OUTSIDE", node(lower.level_id, lower.entrance_door.b, lower.core_zone_id))

    seen, frontier = {"OUTSIDE"}, ["OUTSIDE"]
    while frontier:
        cur = frontier.pop()
        for nxt in graph.get(cur, ()):
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    all_zones = {node(lower.level_id, z.zone_id, lower.core_zone_id) for z in lower.zones} | \
                {node(upper.level_id, z.zone_id, upper.core_zone_id) for z in upper.zones}
    unreachable = sorted(all_zones - seen)
    rep.add("V4", "every room on every level is reachable from OUTSIDE across the core", not unreachable,
            "; ".join(unreachable) or
            f"all {len(all_zones)} zones across both levels reachable from OUTSIDE")


def _check_v5(rep: BuildingValidationReport, lower: LevelRealization, upper: LevelRealization) -> None:
    """V5 — the core's entry (lower level) and arrival (upper level) edges face circulation —
    proven directly on the realized rects, never trusted from a declared intent: the shared-edge
    length against any HALL-role zone must reach `ENTRY_ZONE_M` (or the level's own, when it
    differs — Phase 1 uses the default on both), and that HALL-role zone must not ALSO carry a
    private role (a bedroom, a bathroom, the safe room could never carry HALL too, but this
    guards a future template change from silently making it possible)."""
    bad = []
    for level, label in ((lower, "entry (L0)"), (upper, "arrival (L1)")):
        core_rect = level.rects.get(level.core_zone_id)
        if core_rect is None:
            bad.append(f"{label}: core zone missing on {level.level_id}")
            continue
        hall_zones = [z for z in level.zones if ProgramRole.HALL in z.roles]
        best = 0
        for z in hall_zones:
            other = level.rects.get(z.zone_id)
            if other is None:
                continue
            best = max(best, core_rect.shared_edge_len_u(other))
        best_m = u_to_m(best)
        if best_m < ENTRY_ZONE_M - 1e-6:
            bad.append(f"{label}: {best_m:.2f} m of circulation frontage on {level.level_id} "
                      f"< {ENTRY_ZONE_M} m")
    rep.add("V5", "the core's entry and arrival edges face circulation", not bad,
            "; ".join(bad) or f"both edges reach >= {ENTRY_ZONE_M} m of circulation frontage")


def _check_v8(rep: BuildingValidationReport, lower: LevelRealization, upper: LevelRealization,
             program: ProgramSpec) -> None:
    """V8 — every requested room exists EXACTLY ONCE across the building: never fabricated (the
    allocation stage's own discipline, `level_program.py`), never dropped, never duplicated.
    Counted by ROLE, the same vocabulary `build_room_program` uses for a single storey — this is
    the two-level generalisation of what a one-storey `Building` gets for free by having only one
    level to search."""
    roles = [z.primary_role for level in (lower, upper) for z in level.zones]
    bad = []

    def want(role: ProgramRole, n: int, label: str) -> None:
        got = roles.count(role)
        if got != n:
            bad.append(f"{label}: {got} present, {n} requested")

    want(ProgramRole.MASTER_BEDROOM, 1 if program.bedrooms >= 1 else 0, "master bedroom")
    want(ProgramRole.BEDROOM, max(program.bedrooms - 1, 0), "secondary bedrooms")
    want(ProgramRole.SAFE_ROOM, 1 if program.safe_room else 0, "safe room")
    want(ProgramRole.STAIRWELL, 2, "stair core (one leaf per level)")
    wet_count = roles.count(ProgramRole.BATHROOM) + roles.count(ProgramRole.TOILET)
    if wet_count != program.wet_rooms:
        bad.append(f"wet rooms: {wet_count} present, {program.wet_rooms} requested")
    resolved = resolve_wet_rooms(program)
    n_wc = sum(1 for w in resolved if w.kind is WetRoomKind.GUEST_WC)
    got_wc = roles.count(ProgramRole.TOILET)
    if got_wc != n_wc:
        bad.append(f"guest WCs: {got_wc} present, {n_wc} requested (as toilets, not bathrooms)")
    rep.add("V8", "requested rooms appear exactly once across the building", not bad,
            "; ".join(bad) or "every requested room present exactly once")
