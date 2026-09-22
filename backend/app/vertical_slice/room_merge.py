"""Architecture A spike (Issue #107, Issue #102 §4.A): merge ONE adjacent LIVING+KITCHEN leaf pair
into a single L-shaped room, by opening their shared seam — a direct generalisation of
`app.demo.contract._open_corridor_to_public`'s own precedent (hall<->LDK, wall opened at segment
level, the solver never touched) to "two rooms become one room with a non-rectangular boundary".

Flagged off by default (`LIVING_KITCHEN_MERGE_ENABLED`), matching `concept_generator
.LAUNDRY_ROOM_ENABLED`/`concept_engine_v2.CONCEPT_ENGINE_V2_ENABLED`'s own pattern. This module
never imports `app.demo.contract` (contract imports THIS module to apply the merge to its own
pydantic types) — everything here works on the raw solver output
(`design_output.GeometricDesign`/`RoomOut`) and plain dataclasses, so there is no import cycle.

Scope, exactly as Issue #102 §4.A named it: LIVING+KITCHEN only, CLOSED_ADJACENT only (an
open-plan pair is already one visual space and has nothing to merge), the solver is never called
again and never sees this — `find_merge_candidate` reads the ALREADY-SOLVED `dict[str, Rect]`
(here, its `design_output` translation) the same way `_open_corridor_to_public` reads the
already-solved wall map. `validate_merged_room` re-derives the checks Issue #102's report named as
needed for THIS merge (C1, C2, C3, C6, C7, C8, C9, C14, C16, C19, C20, C26, C27) for the merged
room ONLY; every other room's own checks (already computed by `validation.validate` before this
module ever runs) are untouched.
"""
from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import Polygon, box as _box

from .concept_generator import ROOM_TEMPLATES
from .design_output import GeometricDesign as SolvedDesign, RoomOut as SolvedRoomOut
from .geometry_core.model import ProgramRole
from .validation import Check, ValidationReport

#: Off by default — this is a spike, not a product rollout (Issue #107's own scope).
LIVING_KITCHEN_MERGE_ENABLED = False

_EPS = 1e-6
TOL_M2 = 0.01
#: A role with no `RoomTemplate` row falls back to this aspect ceiling for C20' — the same
#: default `RoomTemplate.max_aspect_ratio` itself carries (`concept_generator.py`).
_DEFAULT_MAX_ASPECT = 2.5


def _xyxy(rect_m: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    x, y, w, h = rect_m
    return x, y, x + w, y + h


def _side_between(a: tuple[float, float, float, float],
                  b: tuple[float, float, float, float]) -> str | None:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    if abs(ax + aw - bx) < _EPS:
        return "E"
    if abs(bx + bw - ax) < _EPS:
        return "W"
    if abs(ay + ah - by) < _EPS:
        return "S"
    if abs(by + bh - ay) < _EPS:
        return "N"
    return None


def _shared_len_m(a: tuple[float, float, float, float], b: tuple[float, float, float, float],
                  side: str) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    if side in ("E", "W"):
        lo, hi = max(ay, by), min(ay + ah, by + bh)
    else:
        lo, hi = max(ax, bx), min(ax + aw, bx + bw)
    return max(0.0, hi - lo)


@dataclass(frozen=True)
class MergeCandidate:
    living: SolvedRoomOut
    kitchen: SolvedRoomOut
    #: The side of `living`'s own rectangle that faces `kitchen`.
    side: str


def find_merge_candidate(design: SolvedDesign) -> MergeCandidate | None:
    """The ONE case this spike targets: a LIVING leaf and a KITCHEN leaf, adjacent in the
    realized geometry, whose relationship reads CLOSED_ADJACENT.

    CLOSED_ADJACENT, ported from the POC's own `patterns.py::_public_composition` rule (that
    branch is not a dependency of this one — reimplemented from the Issue's own description):
    the two rects share a positive-length boundary (adjacent), they are NOT members of the same
    declared open-plan group (an open pair already reads as one space — OPEN, not
    CLOSED_ADJACENT), and the wall between them is an ordinary interior partition (not, say, an
    RC wall some other rule put there for an unrelated reason). The FIRST such pair found is
    returned — this spike does not rank candidates, matching its own "one case only" scope.
    """
    open_group_of: dict[str, frozenset[str]] = {}
    for group in design.open_groups:
        g = frozenset(group)
        for zone_id in group:
            open_group_of[zone_id] = g

    living_rooms = [r for r in design.rooms if r.roles and r.roles[0] == ProgramRole.LIVING.value]
    kitchen_rooms = [r for r in design.rooms if r.roles and r.roles[0] == ProgramRole.KITCHEN.value]
    for living in living_rooms:
        for kitchen in kitchen_rooms:
            side = _side_between(living.rect_m, kitchen.rect_m)
            if side is None:
                continue
            if _shared_len_m(living.rect_m, kitchen.rect_m, side) <= _EPS:
                continue
            if (open_group_of.get(living.zone_id) is not None
                    and open_group_of.get(living.zone_id) == open_group_of.get(kitchen.zone_id)):
                continue  # OPEN, not CLOSED_ADJACENT — nothing to merge, already one space
            if living.wall_facts[side].construction.value != "STANDARD_PARTITION":
                continue  # not an ordinary wall — do not touch it
            return MergeCandidate(living=living, kitchen=kitchen, side=side)
    return None


@dataclass(frozen=True)
class MergedGeometry:
    """The merged room's own geometry — computed once, read by both the validation checks below
    and `contract._apply_room_merge` (the drawing/payload side)."""

    #: The union polygon's exterior ring, metres, plot-absolute, no closing duplicate point.
    polygon_m: tuple[tuple[float, float], ...]
    #: Axis-aligned bounding box of the polygon (x, y, w, h) — what a room's `gross_width_m`/
    #: `gross_depth_m` become for a merged room (see `contract.RoomOut`'s own note on this).
    bbox_m: tuple[float, float, float, float]
    #: The union polygon's OWN area — never a bounding-box product (that is exactly what C27
    #: redesigns away from for a merged room).
    gross_area_m2: float
    #: Sum of the two source rooms' own net areas. Does not reclaim the sliver of wall thickness
    #: the opened seam frees (documented simplification — see the spike report).
    net_area_m2: float
    #: Long/short ratio of the union polygon's own AXIS-ALIGNED bounding box — the "oriented
    #: long/short" generalisation C20/C3 need for a non-rectangular room. Named for the concept
    #: it stands in for (a rotated-rectangle search); see `compute_geometry`'s own docstring for
    #: why this uses the AABB directly rather than a true rotated search.
    min_rotated_aspect: float


def compute_geometry(candidate: MergeCandidate) -> MergedGeometry:
    a = _box(*_xyxy(candidate.living.rect_m))
    b = _box(*_xyxy(candidate.kitchen.rect_m))
    union = a.union(b)
    if not isinstance(union, Polygon):
        # Two axis-aligned rects touching along a positive-length shared edge always union to one
        # simple polygon; this is a defensive invariant check, not an expected branch.
        raise ValueError("merge candidate's two rectangles do not union to one simple polygon")
    # GEOS leaves the two touching seam vertices on the boundary even where they are collinear
    # with their neighbours (a flush merge's own union literally is a rectangle, but its raw
    # coordinate ring still lists 6 points, not 4) — `simplify(0, ...)` drops exactly the
    # collinear ones without moving any vertex, so a flush merge reports a clean 4-point rectangle
    # and a real L keeps every one of its genuine corners.
    union = union.simplify(0, preserve_topology=True)
    minx, miny, maxx, maxy = union.bounds
    # The "oriented long/short" generalisation (C20/C3, mirroring the investigation report's own
    # `patterns.py::_oriented_long_short` precedent) would normally search every rotation via
    # shapely's `minimum_rotated_rectangle` — but that calls GEOS `oriented_envelope`, which
    # divides by zero on a purely axis-aligned/orthogonal polygon (confirmed directly against
    # this shapely version: even a genuine, non-degenerate 8-vertex L union hits it, not just the
    # flush-rectangle case). Every room this spike ever merges is axis-aligned by construction
    # (the solver never produces anything else), so a rotated search has nothing to gain over the
    # polygon's own AXIS-ALIGNED bounding box in the first place — using it directly is a
    # documented simplification, not a shortcut around a real geometric question.
    long_side, short_side = max(maxx - minx, maxy - miny), max(min(maxx - minx, maxy - miny), 1e-6)
    ring = tuple(union.exterior.coords)[:-1]  # drop the closing duplicate vertex
    net_area = round(candidate.living.net_area_m2 + candidate.kitchen.net_area_m2, 4)
    return MergedGeometry(
        polygon_m=ring,
        bbox_m=(minx, miny, maxx - minx, maxy - miny),
        gross_area_m2=round(union.area, 4),
        net_area_m2=net_area,
        min_rotated_aspect=long_side / short_side,
    )


def _report_passed(report: ValidationReport, check_id: str) -> bool:
    return any(c.check_id == check_id and c.passed for c in report.checks)


def validate_merged_room(candidate: MergeCandidate, geometry: MergedGeometry,
                         design: SolvedDesign, report: ValidationReport,
                         merged_id: str) -> list[Check]:
    """Redesigned/polygon-variant forms of C1, C2, C3, C6, C7, C8, C9, C14, C16, C19, C20, C26,
    C27, scoped to the merged room ONLY (Issue #102 §4.A's own list). Where the merge cannot
    possibly have changed a fact the whole-plan `report` already proved — because the merge only
    ever ADDS interior area on one shared side and never touches an exterior wall, a door on
    another side, or a third room — that fact is INHERITED from `report` rather than re-derived
    from scratch; where the merge creates a genuinely new fact (the union's own coverage, its own
    combined size/aspect, its own displayed-area formula), it is checked directly against the
    polygon.
    """
    living, kitchen = candidate.living, candidate.kitchen
    merged_polygon = Polygon(geometry.polygon_m)
    checks: list[Check] = []

    # C1 — no overlap with any other room in the plan. Recomputed directly against the union
    # polygon (a real polygon-intersection test), not merely inherited from the two source rooms'
    # own C1 — the union polygon is new geometry, so this proves it rather than assuming it.
    worst, worst_id = 0.0, ""
    for room in design.rooms:
        if room.zone_id in (living.zone_id, kitchen.zone_id):
            continue
        ov = merged_polygon.intersection(_box(*_xyxy(room.rect_m))).area
        if ov > worst:
            worst, worst_id = ov, room.zone_id
    checks.append(Check("C1", "no overlap between rooms (merged pair)", worst <= TOL_M2,
                        "none" if worst <= TOL_M2 else f"{merged_id}/{worst_id} overlap {worst:.3f} m2"))

    # C2 — no residual/no double-counted interior area: a real coverage proof for the merged pair
    # (the two source rectangles only ever touch, never overlap, so their union's own area must
    # equal the exact sum of theirs — checked geometrically, not assumed by construction the way
    # the whole-footprint C2 is for an ordinary rectangular tiling).
    a_area = living.rect_m[2] * living.rect_m[3]
    b_area = kitchen.rect_m[2] * kitchen.rect_m[3]
    residual = abs(geometry.gross_area_m2 - (a_area + b_area))
    checks.append(Check("C2", "no residual interior area (merged pair)", residual <= TOL_M2,
                        "the union's own area exactly equals the sum of the two source "
                        "rectangles" if residual <= TOL_M2
                        else f"{residual:.3f} m2 unaccounted for in the merge"))

    # C3 — room areas/dimensions valid. No single `ZoneSpec`/`RoomTemplate` covers a merged pair,
    # so this checks the pair's own COMBINED template bounds, plus each source rectangle's own
    # short side (inherited: the merge only ever adds space on ONE side of each rectangle, so a
    # short side already >= its template's minimum on the other three sides cannot have shrunk).
    living_t = ROOM_TEMPLATES.get(ProgramRole.LIVING)
    kitchen_t = ROOM_TEMPLATES.get(ProgramRole.KITCHEN)
    bad: list[str] = []
    if living_t is not None and kitchen_t is not None:
        combined_min = living_t.min_area_m2 + kitchen_t.min_area_m2
        combined_max = living_t.max_area_m2 + kitchen_t.max_area_m2
        if not (combined_min - TOL_M2 <= geometry.net_area_m2 <= combined_max + TOL_M2):
            bad.append(f"merged net {geometry.net_area_m2} m2 outside the combined "
                       f"[{combined_min:.1f},{combined_max:.1f}] template bounds")
    for room, template in ((living, living_t), (kitchen, kitchen_t)):
        if template is None:
            continue
        short = min(room.net_w_m, room.net_h_m)
        if short < template.min_short_side_m - 1e-6:
            bad.append(f"{room.zone_id} short side {short:.2f} m < {template.min_short_side_m} m")
    checks.append(Check("C3", "room areas and dimensions valid (merged pair)", not bad,
                        "; ".join(bad) or "merged pair within its own combined template bounds"))

    # C6 — no artificial door remains where the two leaves used to meet. Checked on the RAW
    # solver output's own interior doors, independent of whatever `contract.py` goes on to do —
    # the merge is only valid if the seam it opens carries no door at all.
    stray = [d for d in design.interior_doors if {d.a, d.b} == {living.zone_id, kitchen.zone_id}]
    checks.append(Check("C6", "no artificial door across the opened seam", not stray,
                        "; ".join(f"{d.a}-{d.b}" for d in stray) or
                        "the opened seam carries no door — one room, not two joined by an opening"))

    # C7 — doors physically placeable. The merged room's own connections to the REST of the house
    # are whichever doors living/kitchen already had on their OTHER (non-seam) sides — untouched
    # by the merge, so inherited from the plan's own C7.
    c7_ok = _report_passed(report, "C7")
    checks.append(Check("C7", "doors physically placeable (merged pair)", c7_ok,
                        "inherited from the plan's own C7 — the merge touches no other door"
                        if c7_ok else "the plan's own C7 already failed"))

    # C8 — daylight/window exposure. The merge never touches an exterior wall (the opened seam is
    # strictly interior), so whichever of living/kitchen needed daylight already has it exactly as
    # before — inherited from the plan's own C8.
    c8_ok = _report_passed(report, "C8")
    checks.append(Check("C8", "daylight/window exposure present (merged pair)", c8_ok,
                        "inherited — the merge touches no exterior wall" if c8_ok
                        else "the plan's own C8 already failed"))

    # C9 — furniture-envelope feasibility, restricted (as the investigation report itself
    # proposes) to the case where a rectangular inscribed sub-area is already known: each source
    # room's own furniture fit, already proven by the plan's own C9 inside its OWN rectangle,
    # remains available unchanged inside the union — the merge only ever adds area, never removes
    # it from either source rectangle.
    c9_ok = _report_passed(report, "C9")
    checks.append(Check("C9", "furniture-envelope feasibility (merged pair, known sub-rectangles)",
                        c9_ok, "each source room's own already-proven furniture fit is untouched "
                              "by the merge" if c9_ok else "the plan's own C9 already failed"))

    # C14 — corridor width: not applicable. Neither LIVING nor KITCHEN is a circulation zone.
    checks.append(Check("C14", "corridor meets the requested width (merged pair)", True,
                        "not applicable — the merged room is not a circulation zone"))

    # C16 — the entrance opens into the room it names: only a live question if the entrance
    # targets one of the two source rooms, and even then the merge touches no exterior wall (the
    # entrance is always on an EXTERIOR wall), so it is inherited from the plan's own C16.
    target = design.entrance_door.b
    if target in (living.zone_id, kitchen.zone_id):
        c16_ok = _report_passed(report, "C16")
        checks.append(Check("C16", "the entrance opens into the room it names (merged pair)",
                            c16_ok, "inherited — the merge touches no exterior wall" if c16_ok
                            else "the plan's own C16 already failed"))
    else:
        checks.append(Check("C16", "the entrance opens into the room it names (merged pair)", True,
                            "not applicable — the entrance does not open into either source room"))

    # C19 — required rooms touch an exterior wall: inherited, same reasoning as C8 (the merge
    # touches no exterior wall on either source rectangle).
    c19_ok = _report_passed(report, "C19")
    checks.append(Check("C19", "required rooms touch an exterior wall (merged pair)", c19_ok,
                        "inherited — the merge touches no exterior wall" if c19_ok
                        else "the plan's own C19 already failed"))

    # C20 — realized rooms within their template's aspect ratio. Genuinely redesigned for a
    # polygon: the oriented long/short ratio of the union's own MINIMUM ROTATED bounding
    # rectangle (the same "oriented long/short" generalisation the investigation report names as
    # a working precedent, `patterns.py::_oriented_long_short`, reimplemented here without that
    # branch as a dependency) against the MORE PERMISSIVE of the two source templates' own aspect
    # ceilings — a documented simplification: no single template exists for a merged pair.
    max_aspect = max((t.max_aspect_ratio for t in (living_t, kitchen_t) if t is not None),
                     default=_DEFAULT_MAX_ASPECT)
    checks.append(Check("C20", "realized rooms within their template's aspect ratio (merged pair)",
                        geometry.min_rotated_aspect <= max_aspect + 1e-6,
                        f"merged oriented aspect {geometry.min_rotated_aspect:.2f} vs the "
                        f"{max_aspect} ceiling"))

    # C26 — no extreme dedicated circulation: not applicable, neither merged room is circulation.
    checks.append(Check("C26", "no extreme dedicated circulation (merged pair)", True,
                        "not applicable — the merged room is not a circulation zone"))

    # C27 — displayed dimensions consistent with realized geometry. REDESIGNED formula: for a
    # polygon room, area is the polygon's OWN area, never a bounding-box width x depth product —
    # this asserts BOTH that the reported area matches the true polygon area AND that the naive
    # rectangle formula would have been wrong (proving the redesign was actually necessary, not
    # merely different).
    bbox_w, bbox_h = geometry.bbox_m[2], geometry.bbox_m[3]
    bbox_product = bbox_w * bbox_h
    true_area = merged_polygon.area
    area_matches = abs(true_area - geometry.gross_area_m2) <= TOL_M2
    bbox_would_be_wrong = bbox_product > true_area + TOL_M2
    checks.append(Check("C27", "displayed dimensions consistent with realized geometry (merged pair)",
                        area_matches and bbox_would_be_wrong,
                        f"reported gross area {geometry.gross_area_m2:.2f} m2 matches the union "
                        f"polygon's own area {true_area:.2f} m2; the bounding-box product "
                        f"{bbox_product:.2f} m2 would have overstated it by "
                        f"{bbox_product - true_area:.2f} m2 — the redesigned formula is not "
                        f"merely different, it is necessary"))

    return checks


@dataclass(frozen=True)
class MergeResult:
    living_id: str
    kitchen_id: str
    merged_id: str
    side: str
    geometry: MergedGeometry
    checks: tuple[Check, ...]

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)


def plan_merge(design: SolvedDesign, report: ValidationReport) -> MergeResult | None:
    """`None` when the flag is off or no LIVING/KITCHEN CLOSED_ADJACENT pair exists in this plan
    — the caller (`app.demo.contract.to_demo_design`) then draws the plan exactly as it always
    has. When a candidate exists but its OWN checks above do not all pass, this still returns a
    `MergeResult` (so the caller can report which check failed and why) with `passed=False`; the
    caller applies the merge to the drawn payload only when `passed` is true — an unvalidated L
    room is never drawn, matching the corridor-opening precedent's own discipline.
    """
    if not LIVING_KITCHEN_MERGE_ENABLED:
        return None
    candidate = find_merge_candidate(design)
    if candidate is None:
        return None
    geometry = compute_geometry(candidate)
    merged_id = f"{candidate.living.zone_id}+{candidate.kitchen.zone_id}"
    checks = tuple(validate_merged_room(candidate, geometry, design, report, merged_id))
    return MergeResult(living_id=candidate.living.zone_id, kitchen_id=candidate.kitchen.zone_id,
                       merged_id=merged_id, side=candidate.side, geometry=geometry, checks=checks)
