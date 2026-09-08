"""General Concept Generator V1.

Replaces the hand-authored canonical concept on the general path. `concept.py` keeps its
hard-coded 3BR+safe-room fixture ONLY as the frozen regression baseline that
`pipeline.run_demo` and the baseline tests pin; nothing general calls it any more.

WHAT WAS KEPT FROM THE CANONICAL CONCEPT (architectural patterns, re-derived generically):
  * open-plan LDK as one open group with no artificial doors between its zones;
  * a circulation spine that borders every private room, so no room is reached through another
    (destination-only rooms are never transit);
  * the safe room reached directly from circulation, never through a bedroom;
  * an ensuite paired with the master bedroom, entered from the bedroom rather than the hall;
  * forced cuts ONLY where two sibling subtrees must align, unforced everywhere else — the
    lesson that hand-forcing every depth produced two infeasible values in a row.

WHAT WAS DISCARDED (canonical-fixture accidents, not architecture):
  * every literal dimension (12.0 x 14.2, and the 4.7 / 1.6 / 3.45 / 5.0 / 4.5 / 3.8 cuts);
  * the fixed eleven-room list and its literal area bands;
  * the fixed access-edge list;
  * the two-segment hall (HALL_MAIN/HALL_SPUR): a single spine column bordering the whole
    private stack serves every room, so branching is generated only when a layout needs it.

TOPOLOGY BEFORE DIMENSIONS: this module decides grouping, zoning, open groups and the access
graph from the programme alone. Only after that does it choose a footprint and column widths,
and Geometry Core remains solely responsible for exact realization.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from .concept import Concept
from .geometry_core.model import (
    ConnectionKind,
    Cut,
    DesiredAccessEdge,
    DesiredAccessTopology,
    Fixture,
    Leaf,
    Node,
    ProgramRole,
    Rect,
    Side,
    Split,
    Wing,
    ZoneSpec,
    m_to_u,
    u_to_m,
)
from .safe_adapter import SolverGeometryCandidate
from .spec import ArchitecturalSpec

# --------------------------------------------------------------------------- product policy
# PRODUCT POLICY placeholders, in the same sense as WALL_THICKNESS_M's safe-room entry: plausible
# working values, not verified regulation. `elasticity` says how much of a larger house a role
# should absorb: a living room grows with the house, a bathroom or a safe room does not.

@dataclass(frozen=True)
class RoomTemplate:
    min_area_m2: float
    target_area_m2: float
    max_area_m2: float
    min_short_side_m: float
    max_aspect_ratio: float = 2.5
    elasticity: float = 0.0


ROOM_TEMPLATES: dict[ProgramRole, RoomTemplate] = {
    ProgramRole.LIVING: RoomTemplate(16.0, 22.0, 46.0, 3.0, 2.5, elasticity=3.0),
    ProgramRole.DINING: RoomTemplate(10.0, 14.0, 30.0, 2.6, 3.0, elasticity=1.5),
    ProgramRole.KITCHEN: RoomTemplate(9.0, 13.0, 26.0, 2.4, 3.0, elasticity=1.0),
    ProgramRole.MASTER_BEDROOM: RoomTemplate(12.0, 15.0, 26.0, 3.0, 2.5, elasticity=1.0),
    ProgramRole.BEDROOM: RoomTemplate(9.5, 12.5, 22.0, 2.6, 2.5, elasticity=0.6),
    # Regulated minimum: never scaled down, and not inflated just because the house is large.
    ProgramRole.SAFE_ROOM: RoomTemplate(9.0, 10.5, 14.0, 2.4, 2.5, elasticity=0.0),
    ProgramRole.BATHROOM: RoomTemplate(4.5, 6.5, 12.0, 1.6, 3.0, elasticity=0.2),
    ProgramRole.HALL: RoomTemplate(5.0, 11.0, 30.0, 1.2, 8.0, elasticity=0.8),
}

#: Net/gross ratio used to size a footprint from a programme. Measured 0.90-0.92 in the spike.
ASSUMED_EFFICIENCY = 0.90
#: Wall inset allowance used by the pre-check (exterior half 0.15 + partition half 0.05).
_EDGE_INSET_ALLOWANCE_M = 0.20
#: Floors are raised slightly above the bare minimum so the fixed point settles
#: ABOVE the pre-check threshold instead of a few centimetres under it.
_FLOOR_MARGIN = 1.06
#: Preferred footprint proportion (width:depth) before the candidate clamps it.
_FOOTPRINT_ASPECT_PREF = 0.82


class ZoneGroup(str, Enum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    SERVICE = "SERVICE"
    CIRCULATION = "CIRCULATION"


class ConceptStrategy(str, Enum):
    #: public column | hall spine | private column, all in one wing.
    SPINE_PUBLIC_PRIVATE = "SPINE_PUBLIC_PRIVATE"
    #: as above, but the service (wet) rooms are clustered at the far end of the private stack.
    SPINE_SERVICE_CLUSTER = "SPINE_SERVICE_CLUSTER"
    #: rooms on BOTH sides of the hall (double-loaded corridor) — halves the row count.
    SPINE_DOUBLE_LOADED = "SPINE_DOUBLE_LOADED"
    #: private stack split across two columns with a branched hall (for larger programmes).
    BRANCHED_TWO_STACK = "BRANCHED_TWO_STACK"
    #: public zones as a full-width band across the front, corridor and bedrooms behind it.
    FRONT_PUBLIC_BAND = "FRONT_PUBLIC_BAND"
    #: programme allocated across two safe wings.
    MULTI_WING_SPLIT = "MULTI_WING_SPLIT"


class RejectionReason(str, Enum):
    INSUFFICIENT_TOTAL_AREA = "INSUFFICIENT_TOTAL_AREA"
    INSUFFICIENT_WING_AREA = "INSUFFICIENT_WING_AREA"
    WING_TOO_NARROW = "WING_TOO_NARROW"
    ROOM_BELOW_MINIMUM_DIMENSION = "ROOM_BELOW_MINIMUM_DIMENSION"
    SAFE_ROOM_CONSTRAINT = "SAFE_ROOM_CONSTRAINT"
    ACCESS_DEGREE_EXCEEDED = "ACCESS_DEGREE_EXCEEDED"
    OPEN_GROUP_INCOMPATIBLE = "OPEN_GROUP_INCOMPATIBLE"
    NO_SEAM_ALIGNMENT = "NO_SEAM_ALIGNMENT"
    CIRCULATION_WOULD_CROSS_PRIVATE = "CIRCULATION_WOULD_CROSS_PRIVATE"


@dataclass(frozen=True)
class ConceptRejection:
    strategy: ConceptStrategy
    reason: RejectionReason
    detail: str
    wing_orders: tuple[int, ...] = ()


@dataclass(frozen=True)
class ProgramRoom:
    zone_id: str
    role: ProgramRole
    group: ZoneGroup
    template: RoomTemplate
    #: Entered from this room rather than from circulation (an ensuite).
    entered_from: str | None = None


@dataclass(frozen=True)
class ConceptCandidate:
    concept: Concept
    strategy: ConceptStrategy
    wing_orders: tuple[int, ...]
    rationale: str
    used_area_m2: float
    unused_wing_area_m2: float


@dataclass(frozen=True)
class GenerationResult:
    candidates: tuple[ConceptCandidate, ...]
    rejections: tuple[ConceptRejection, ...]
    program: tuple[ProgramRoom, ...]

    @property
    def any(self) -> bool:
        return bool(self.candidates)


# --------------------------------------------------------------------------- 1. programme

def build_room_program(spec: ArchitecturalSpec) -> list[ProgramRoom]:
    """ArchitecturalSpec -> room groups. No scenario branching, no fixed room list."""
    program = spec.program
    rooms: list[ProgramRoom] = []

    def add(zone_id: str, role: ProgramRole, group: ZoneGroup, entered_from: str | None = None):
        rooms.append(ProgramRoom(zone_id, role, group, ROOM_TEMPLATES[role], entered_from))

    # Public zones. Open-plan yields three zones of one space; otherwise living + kitchen only,
    # because a separate dining room is a choice the spec does not currently express.
    if program.open_plan_living:
        add("LIVING", ProgramRole.LIVING, ZoneGroup.PUBLIC)
        add("DINING", ProgramRole.DINING, ZoneGroup.PUBLIC)
        add("KITCHEN", ProgramRole.KITCHEN, ZoneGroup.PUBLIC)
    else:
        add("LIVING", ProgramRole.LIVING, ZoneGroup.PUBLIC)
        add("KITCHEN", ProgramRole.KITCHEN, ZoneGroup.PUBLIC)

    add("HALL", ProgramRole.HALL, ZoneGroup.CIRCULATION)

    if program.bedrooms >= 1:
        add("MASTER", ProgramRole.MASTER_BEDROOM, ZoneGroup.PRIVATE)
    for i in range(1, program.bedrooms):
        add(f"BEDROOM_{i}", ProgramRole.BEDROOM, ZoneGroup.PRIVATE)

    if program.safe_room:
        add("SAFE_ROOM", ProgramRole.SAFE_ROOM, ZoneGroup.PRIVATE)

    # Wet rooms: with two or more and a master present, the first is an ensuite entered from
    # the master; the rest are shared and entered from circulation.
    for i in range(1, program.wet_rooms + 1):
        ensuite = (i == 1 and program.wet_rooms >= 2 and program.bedrooms >= 1)
        add(f"BATH_{i}", ProgramRole.BATHROOM, ZoneGroup.SERVICE,
            entered_from="MASTER" if ensuite else None)

    return rooms


def scale_program(rooms: list[ProgramRoom], net_available_m2: float,
                  area_floors: dict[str, float] | None = None) -> dict[str, ZoneSpec]:
    """Fit the programme's target areas to the area actually available.

    Geometry Core tiles the footprint EXACTLY, so the room areas must be able to absorb all of
    it — a fixed template list would either overflow a small wing or leave a large one
    unsatisfiable. Surplus is distributed by `elasticity`, so a bigger house grows its living
    space rather than its safe room or its bathrooms.
    """
    floors = area_floors or {}

    def floor_of(room: ProgramRoom) -> float:
        return max(room.template.min_area_m2, floors.get(room.zone_id, 0.0))

    base = sum(max(r.template.target_area_m2, floor_of(r)) for r in rooms)
    surplus = net_available_m2 - base
    weight_total = sum(r.template.elasticity for r in rooms) or 1.0

    targets: dict[str, float] = {}
    for room in rooms:
        t = room.template
        start = max(t.target_area_m2, floor_of(room))
        if surplus >= 0:
            extra = surplus * (t.elasticity / weight_total)
            targets[room.zone_id] = max(start, min(start + extra, max(t.max_area_m2, start)))
        else:
            # Shrink proportionally, but never below the room's floor.
            shrink = (-surplus) * (start / base)
            targets[room.zone_id] = max(start - shrink, floor_of(room))

    # Re-balance any residue onto the elastic rooms so the totals still add up.
    residue = net_available_m2 - sum(targets.values())
    elastic = [r for r in rooms if r.template.elasticity > 0]
    for _ in range(4):
        if abs(residue) < 0.05 or not elastic:
            break
        share = residue / sum(r.template.elasticity for r in elastic)
        for room in elastic:
            t = room.template
            targets[room.zone_id] = max(
                floor_of(room),
                min(targets[room.zone_id] + share * t.elasticity,
                    max(t.max_area_m2, floor_of(room))),
            )
        residue = net_available_m2 - sum(targets.values())

    specs: dict[str, ZoneSpec] = {}
    for room in rooms:
        t = room.template
        target = targets[room.zone_id]
        roles = (room.role,) if room.role is not ProgramRole.HALL else (
            ProgramRole.HALL, ProgramRole.CIRCULATION)
        specs[room.zone_id] = ZoneSpec(
            zone_id=room.zone_id,
            roles=roles,
            net_area_min_m2=max(floor_of(room), target * 0.70),
            net_area_target_m2=target,
            net_area_max_m2=max(target * 1.45, t.min_area_m2 * 1.5),
            min_short_side_m=t.min_short_side_m,
            max_aspect_ratio=t.max_aspect_ratio,
        )
    return specs


def target_gross_area_m2(rooms: list[ProgramRoom]) -> float:
    return sum(r.template.target_area_m2 for r in rooms) / ASSUMED_EFFICIENCY


# --------------------------------------------------------------------------- 2. footprint

def minimum_footprint_width_m(rooms: list[ProgramRoom]) -> float:
    """A three-column layout cannot be narrower than its columns' own minimums. Deriving the
    footprint proportions from an aspect preference alone produced columns too narrow for a
    3 m master bedroom, so the requirement floors the width."""
    public = [r for r in rooms if r.group is ZoneGroup.PUBLIC]
    private = [r for r in rooms if r.group in (ZoneGroup.PRIVATE, ZoneGroup.SERVICE)]
    hall = ROOM_TEMPLATES[ProgramRole.HALL].min_short_side_m + _EDGE_INSET_ALLOWANCE_M
    return _column_min_width(public) + hall + _column_min_width(private)


def footprint_of(candidate: Rect, width_m: float, depth_m: float) -> Rect:
    """A grid-aligned sub-rectangle of a proven-safe candidate, anchored to its street side and
    centred across it — the same convention the site stage uses."""
    w_u = min(candidate.w, max(1, m_to_u(width_m)))
    h_u = min(candidate.h, max(1, m_to_u(depth_m)))
    return Rect(candidate.x + (candidate.w - w_u) // 2, candidate.y, w_u, h_u)


def choose_footprint(candidate: Rect, target_gross_m2: float,
                     min_width_m: float = 0.0) -> Rect:
    """A grid-aligned sub-rectangle of a proven-safe candidate, sized for the programme.

    Anchored to the candidate's street side and centred across it — the same convention the
    site stage uses — so a candidate that exactly fits reproduces the canonical placement.
    """
    cw, ch = u_to_m(candidate.w), u_to_m(candidate.h)
    width = max(min_width_m, math.sqrt(target_gross_m2 * _FOOTPRINT_ASPECT_PREF))
    width = min(width, cw)
    depth = min(ch, target_gross_m2 / max(width, 1e-6))
    if width > cw:
        width = cw
        depth = min(ch, target_gross_m2 / width)
    w_u = min(candidate.w, max(1, m_to_u(width)))
    h_u = min(candidate.h, max(1, m_to_u(depth)))
    return Rect(candidate.x + (candidate.w - w_u) // 2, candidate.y, w_u, h_u)


# --------------------------------------------------------------------------- 3. tree synthesis

def _h_chain(nodes: list[Node]) -> Node:
    """Right-nested H chain. Unforced: nothing outside the column aligns to these boundaries."""
    if len(nodes) == 1:
        return nodes[0]
    return Split(Cut.H, nodes[0], _h_chain(nodes[1:]), None)


def _private_rows(rooms: list[ProgramRoom]) -> list[Node]:
    """Private + service rooms as stack rows. An ensuite is paired into its bedroom's row with a
    V-split, so the bedroom keeps the hall frontage and the ensuite is entered from it."""
    ensuites = {r.entered_from: r for r in rooms if r.entered_from}
    rows: list[Node] = []
    for room in rooms:
        if room.entered_from:
            continue
        ensuite = ensuites.get(room.zone_id)
        if ensuite is not None:
            rows.append(Split(Cut.V, Leaf(room.zone_id), Leaf(ensuite.zone_id), None))
        else:
            rows.append(Leaf(room.zone_id))
    return rows


def _rows_of(stack: list[ProgramRoom]) -> list[list[ProgramRoom]]:
    """Stack rows: an ensuite shares its bedroom's row (a V-split), everything else is its own."""
    present = {r.zone_id for r in stack}
    ensuites = {r.entered_from: r for r in stack
                if r.entered_from and r.entered_from in present}
    paired = {r.zone_id for r in ensuites.values()}
    rows: list[list[ProgramRoom]] = []
    for room in stack:
        if room.zone_id in paired:
            continue  # contributed by its bedroom's row
        mate = ensuites.get(room.zone_id)
        rows.append([room, mate] if mate else [room])
    return rows


def _orient_row(row: list[ProgramRoom], corridor_on_east: bool) -> list[ProgramRoom]:
    """Order a shared row so the member that needs corridor access actually touches it.

    A V-split places `row[0]` to the WEST and `row[1]` to the EAST, so the corridor-facing
    position depends on which side of the hall the column sits. Placing the bedroom first
    unconditionally was correct for the east column and wrong for the west one: there it put the
    ensuite against the corridor and buried the bedroom behind it, so HALL-MASTER was declared
    but no door could ever be built.

    The rule is general, not per-fixture: the member entered from CIRCULATION takes the
    corridor-facing slot; the member entered from its neighbour (an ensuite) takes the far one.
    """
    if len(row) < 2:
        return row
    corridor_facing = [r for r in row if r.entered_from is None]
    dependent = [r for r in row if r.entered_from is not None]
    if not corridor_facing or not dependent:
        return row
    return dependent + corridor_facing if corridor_on_east else corridor_facing + dependent


@dataclass(frozen=True)
class ColumnPlan:
    width_m: float
    rows: list[list[ProgramRoom]]
    row_depths_m: list[float]


@dataclass(frozen=True)
class LayoutPlan:
    west: ColumnPlan
    east: ColumnPlan
    hall_w_m: float
    specs: dict[str, ZoneSpec]


def _row_widths(row: list[ProgramRoom], net_width: float) -> list[float] | None:
    """Widths for the members of a shared row, or None if they cannot all fit.

    Area share alone is not enough: an ensuite is ~30% of its bedroom by area, and 30% of a
    5 m column is 1.39 m — under a bathroom's 1.6 m minimum. Every member gets its minimum
    first; only the surplus is shared by area.
    """
    minimums = [r.template.min_short_side_m for r in row]
    if sum(minimums) > net_width + 1e-9:
        return None
    surplus = net_width - sum(minimums)
    areas = [r.template.target_area_m2 for r in row]
    total = sum(areas) or 1.0
    return [m + surplus * a / total for m, a in zip(minimums, areas)]


def _width_share(room: ProgramRoom, row: list[ProgramRoom]) -> float:
    """Area-proportional share, used only where no net width is available to clamp against."""
    total = sum(r.template.target_area_m2 for r in row)
    return room.template.target_area_m2 / total if total else 1.0 / len(row)


def _column_min_width(rooms: list[ProgramRoom]) -> float:
    """Narrowest a column may be: the widest minimum among its rows (a shared row needs both of
    its rooms side by side), plus the wall inset allowance."""
    widest = 0.0
    for row in _rows_of(rooms):
        widest = max(widest, sum(r.template.min_short_side_m for r in row))
    return widest + _EDGE_INSET_ALLOWANCE_M


def _column_width(rooms: list[ProgramRoom], specs_area: dict[str, float], net_depth: float) -> float:
    """A column runs the footprint's full depth, so its width is forced by area / depth."""
    return sum(specs_area[r.zone_id] for r in rooms) / max(net_depth, 1e-6)


def _row_depths(rows: list[list[ProgramRoom]], areas: dict[str, float], net_width: float,
                column_depth: float) -> list[float] | None:
    """Row depths, chosen DIRECTLY rather than inferred from areas.

    The first design drove depth from area (`depth = area / width`) and then tried to steer the
    areas until the depths came out legal. That is an unstable fixed point: a small room in a
    wide column is always too shallow, and nudging its area moves the column width too. Choosing
    the depth first — floored by each row's own minimum short side — and deriving the areas from
    `width x depth` afterwards makes the result feasible BY CONSTRUCTION.
    """
    wanted = []
    for row in rows:
        area = sum(areas[r.zone_id] for r in row)
        floor = max(r.template.min_short_side_m for r in row) + _EDGE_INSET_ALLOWANCE_M
        wanted.append(max(area / max(net_width, 1e-6), floor))
    total = sum(wanted)
    if total > column_depth + 1e-9:
        return None  # the rows genuinely do not fit at their own minimum depths
    surplus = column_depth - total
    weights = [max(0.15, sum(r.template.elasticity for r in row)) for row in rows]
    wsum = sum(weights)
    return [round((d + surplus * w / wsum) / 0.05) * 0.05 for d, w in zip(wanted, weights)]


def plan_layout(rooms: list[ProgramRoom], west: list[ProgramRoom], east: list[ProgramRoom],
                hall_ids: list[str], footprint_w_m: float, footprint_h_m: float,
                ) -> tuple[LayoutPlan | None, str]:
    """Column widths, row depths and the resulting zone specs, all mutually consistent."""
    net_depth = max(footprint_h_m - _EDGE_INSET_ALLOWANCE_M, 1e-6)
    net_available = footprint_w_m * footprint_h_m * ASSUMED_EFFICIENCY
    base = scale_program(rooms, net_available)
    areas = {z: spec.net_area_target_m2 for z, spec in base.items()}

    hall_area = sum(areas[h] for h in hall_ids)
    hall_w = max(base[hall_ids[0]].min_short_side_m + _EDGE_INSET_ALLOWANCE_M,
                 hall_area / net_depth + _EDGE_INSET_ALLOWANCE_M)
    hall_w = round(min(hall_w, 2.4) / 0.05) * 0.05

    usable = footprint_w_m - hall_w
    west_min = _column_min_width(west)
    east_min = _column_min_width(east)
    if west_min + east_min > usable + 1e-9:
        return None, (f"columns need {west_min:.2f} + {east_min:.2f} m of width but only "
                      f"{usable:.2f} m is available beside the {hall_w:.2f} m hall")
    # Area share is the NATURAL width (a column runs the full depth, so width == area / depth).
    # Only then is a column raised to its own minimum, taking the difference from its neighbour
    # — allocating minimums first and sharing the surplus starved whichever column had the
    # larger programme.
    west_raw = _column_width(west, areas, net_depth)
    east_raw = _column_width(east, areas, net_depth)
    west_w = usable * west_raw / max(west_raw + east_raw, 1e-6)
    west_w = min(max(west_w, west_min), usable - east_min)
    west_w = round(west_w / 0.05) * 0.05
    east_w = round((usable - west_w) / 0.05) * 0.05
    west_w = footprint_w_m - hall_w - east_w  # absorb rounding

    # The hall sits between the two columns, so it is EAST of the west column and WEST of the
    # east one. Orient every shared row accordingly, before widths, specs or the tree are built.
    west_rows = [_orient_row(r, corridor_on_east=True) for r in _rows_of(west)]
    east_rows = [_orient_row(r, corridor_on_east=False) for r in _rows_of(east)]

    plans = []
    for name, width, rows in (("west", west_w, west_rows), ("east", east_w, east_rows)):
        net_w = width - _EDGE_INSET_ALLOWANCE_M
        if net_w <= 0:
            return None, f"{name} column has no net width at {width:.2f} m"
        for row in rows:
            if _row_widths(row, net_w) is None:
                return None, (f"{' + '.join(r.zone_id for r in row)} cannot share the {name} "
                              f"column's {net_w:.2f} m of net width at their minimums")
        depths = _row_depths(rows, areas, net_w, footprint_h_m)
        if depths is None:
            return None, (f"{name} column needs more than {footprint_h_m:.2f} m of depth for its "
                          f"{len(rows)} rows at their minimum dimensions")
        plans.append(ColumnPlan(width, rows, depths))

    # Areas now FOLLOW the geometry: each zone's band is centred on the rect it will occupy.
    specs: dict[str, ZoneSpec] = {}
    for plan in plans:
        net_w = plan.width_m - _EDGE_INSET_ALLOWANCE_M
        for row, depth in zip(plan.rows, plan.row_depths_m):
            net_d = depth - _EDGE_INSET_ALLOWANCE_M / 2
            widths_in_row = _row_widths(row, net_w) or [net_w / len(row)] * len(row)
            for room, w in zip(row, widths_in_row):
                target = w * net_d
                specs[room.zone_id] = ZoneSpec(
                    room.zone_id, _roles_of(room),
                    net_area_min_m2=target * 0.60,
                    net_area_target_m2=target,
                    net_area_max_m2=target * 1.60,
                    min_short_side_m=room.template.min_short_side_m,
                    max_aspect_ratio=max(room.template.max_aspect_ratio,
                                         max(w, net_d) / max(1e-6, min(w, net_d)) + 0.3),
                )
    for hall_id in hall_ids:
        hall_depth = footprint_h_m / len(hall_ids)
        target = (hall_w - _EDGE_INSET_ALLOWANCE_M) * (hall_depth - _EDGE_INSET_ALLOWANCE_M / 2)
        specs[hall_id] = ZoneSpec(
            hall_id, (ProgramRole.HALL, ProgramRole.CIRCULATION),
            target * 0.55, target, target * 1.75,
            ROOM_TEMPLATES[ProgramRole.HALL].min_short_side_m, 12.0)

    return LayoutPlan(plans[0], plans[1], hall_w, specs), ""


def _roles_of(room: ProgramRoom) -> tuple[ProgramRole, ...]:
    if room.role is ProgramRole.HALL:
        return (ProgramRole.HALL, ProgramRole.CIRCULATION)
    return (room.role,)


def _forced_chain(rows: list[list[ProgramRoom]], depths: list[float], net_width: float) -> Node:
    """Right-nested H chain with every cut forced to the depth chosen above; a shared row gets a
    forced V cut at its members' width share."""
    def row_node(row: list[ProgramRoom]) -> Node:
        if len(row) == 1:
            return Leaf(row[0].zone_id)
        widths = _row_widths(row, net_width) or [net_width / len(row)] * len(row)
        first_w = widths[0] + _EDGE_INSET_ALLOWANCE_M / 2
        return Split(Cut.V, Leaf(row[0].zone_id), Leaf(row[1].zone_id),
                     m_to_u(round(first_w / 0.05) * 0.05))

    def build(index: int) -> Node:
        if index == len(rows) - 1:
            return row_node(rows[index])
        return Split(Cut.H, row_node(rows[index]), build(index + 1), m_to_u(depths[index]))

    return build(0)


# --------------------------------------------------------------------------- 5. access graph

def _build_access(rooms: list[ProgramRoom], hall_ids: list[str],
                  public_ids: list[str], open_plan: bool,
                  hall_for: dict[str, str]) -> tuple[DesiredAccessTopology, tuple[tuple[str, ...], ...]]:
    """Access topology from the programme — never from the rectangle dimensions.

    Rules applied, all general: circulation reaches every private and service room directly;
    the safe room is reached from circulation, never through a bedroom; an ensuite is entered
    from its bedroom; open-plan zones connect with OPEN_CONNECTION and therefore no doors.
    """
    edges: list[DesiredAccessEdge] = []
    groups: list[tuple[str, ...]] = []

    if open_plan and len(public_ids) > 1:
        groups.append(tuple(public_ids))
        for a, b in zip(public_ids, public_ids[1:]):
            edges.append(DesiredAccessEdge(a, b, ConnectionKind.OPEN_CONNECTION))
        edges.append(DesiredAccessEdge(hall_ids[0], public_ids[0], ConnectionKind.DOOR))
    else:
        for public_id in public_ids:
            edges.append(DesiredAccessEdge(hall_ids[0], public_id, ConnectionKind.DOOR))

    if len(hall_ids) > 1:
        groups.append(tuple(hall_ids))
        for a, b in zip(hall_ids, hall_ids[1:]):
            edges.append(DesiredAccessEdge(a, b, ConnectionKind.OPEN_CONNECTION))

    for room in rooms:
        if room.group in (ZoneGroup.PUBLIC, ZoneGroup.CIRCULATION):
            continue
        if room.entered_from:
            edges.append(DesiredAccessEdge(room.entered_from, room.zone_id, ConnectionKind.DOOR))
        else:
            edges.append(DesiredAccessEdge(hall_for[room.zone_id], room.zone_id, ConnectionKind.DOOR))

    return DesiredAccessTopology(tuple(edges)), tuple(groups)


# --------------------------------------------------------------------------- 6. strategies
#
# Every strategy is the SAME layout — west column | hall spine | east column — and differs only
# in how the programme is allocated between the two columns. The hall runs the full depth
# against both, so every room borders circulation directly and none is reached through another.

def _build(spec: ArchitecturalSpec, rooms: list[ProgramRoom], candidate: Rect,
           strategy: ConceptStrategy, west: list[ProgramRoom], east: list[ProgramRoom],
           rationale: str) -> tuple[ConceptCandidate | None, ConceptRejection | None]:
    if not west or not east:
        return None, ConceptRejection(strategy, RejectionReason.INSUFFICIENT_WING_AREA,
                                      "allocation left a column empty")
    hall_ids = ["HALL"]
    gross = target_gross_area_m2(rooms)
    min_width = minimum_footprint_width_m(rooms)

    # Bounded, deterministic search over footprint PROPORTIONS. A single aspect constant cannot
    # work: widen the footprint and the columns get wide enough but the rows get shallow; deepen
    # it and the reverse. Rather than guess, walk the width from the layout's own minimum up to
    # the candidate's, at 0.25 m steps, and take the first proportion the planner accepts.
    footprint = None
    plan = None
    why = "no footprint proportion satisfied the programme"
    max_width = u_to_m(candidate.w)
    max_depth = u_to_m(candidate.h)

    widths: list[float] = []
    w = min_width
    while w <= max_width + 1e-9 and len(widths) < 14:
        widths.append(round(w / 0.05) * 0.05)
        w += 0.5

    for width in widths:
        # Depth is searched too, not just derived: the minimum-dimension floors make rooms
        # LARGER than their template targets, so the programme genuinely needs more gross area
        # than the template estimate. Re-proportioning a fixed area can never satisfy that;
        # letting the footprint grow into the proven-safe candidate can.
        base_depth = min(max_depth, gross / max(width, 1e-6))
        depth = base_depth
        step = max(0.25, (max_depth - base_depth) / 6) if max_depth > base_depth else 0.0
        for _ in range(7):
            trial = footprint_of(candidate, width, depth)
            tw, th = u_to_m(trial.w), u_to_m(trial.h)
            attempt, reason = plan_layout(rooms, west, east, hall_ids, tw, th)
            if attempt is not None:
                footprint, plan = trial, attempt
                break
            why = reason
            if step <= 0 or depth >= max_depth - 1e-9:
                break
            depth = min(max_depth, depth + step)
        if plan is not None:
            break

    if plan is None or footprint is None:
        return None, ConceptRejection(strategy, RejectionReason.ROOM_BELOW_MINIMUM_DIMENSION, why)
    fw, fh = u_to_m(footprint.w), u_to_m(footprint.h)

    specs = plan.specs
    west_tree = _forced_chain(plan.west.rows, plan.west.row_depths_m,
                              plan.west.width_m - _EDGE_INSET_ALLOWANCE_M)
    east_tree = _forced_chain(plan.east.rows, plan.east.row_depths_m,
                              plan.east.width_m - _EDGE_INSET_ALLOWANCE_M)
    tree = Split(Cut.V, west_tree,
                 Split(Cut.V, Leaf("HALL"), east_tree, m_to_u(plan.hall_w_m)),
                 m_to_u(plan.west.width_m))

    public_ids = [r.zone_id for r in rooms if r.group is ZoneGroup.PUBLIC]
    hall_for = {r.zone_id: "HALL" for r in rooms
                if r.group in (ZoneGroup.PRIVATE, ZoneGroup.SERVICE)}
    access, groups = _build_access(rooms, hall_ids, public_ids,
                                   spec.program.open_plan_living, hall_for)

    wing = Wing("W", footprint.x, footprint.y, footprint.w, footprint.h, tree)
    fixture = Fixture(f"GEN_{strategy.value}", (wing,),
                      tuple(specs[r.zone_id] for r in rooms), access, open_groups=groups)
    return ConceptCandidate(
        Concept(fixture, "HALL", Side.N, fw, fh), strategy, (0,),
        rationale=(f"{rationale}; west {plan.west.width_m:.2f} m ({len(plan.west.rows)} rows) | "
                   f"hall {plan.hall_w_m:.2f} m | east {plan.east.width_m:.2f} m "
                   f"({len(plan.east.rows)} rows) over {fh:.2f} m"),
        used_area_m2=round(fw * fh, 2),
        unused_wing_area_m2=round(candidate.area_m2() - fw * fh, 2),
    ), None


def _allocations(rooms: list[ProgramRoom]) -> list[tuple[ConceptStrategy, list[ProgramRoom],
                                                         list[ProgramRoom], str]]:
    """The bounded, deterministic candidate set. Architectural priorities are explicit here:
    the public zones stay together nearest the entrance, bedrooms stay grouped, and wet rooms
    are either clustered or distributed — never scattered arbitrarily."""
    public = [r for r in rooms if r.group is ZoneGroup.PUBLIC]
    private = [r for r in rooms if r.group is ZoneGroup.PRIVATE]
    service = [r for r in rooms if r.group is ZoneGroup.SERVICE]
    ensuite = [r for r in service if r.entered_from]
    shared_wet = [r for r in service if not r.entered_from]

    out = []
    # 1. Public one side, everything private the other.
    out.append((ConceptStrategy.SPINE_PUBLIC_PRIVATE, list(public),
                private + service, "public wing vs private wing"))
    # 2. Balanced: split the private rows so both columns carry a similar number.
    rows = _rows_of(private + service)
    half = max(1, (len(rows) + len(public)) // 2 - len(public))
    west_extra = [r for row in rows[:half] for r in row]
    east_rest = [r for row in rows[half:] for r in row]
    if east_rest:
        out.append((ConceptStrategy.SPINE_DOUBLE_LOADED, public + west_extra, east_rest,
                    "double-loaded: rooms on both sides of the hall"))
    # 3. Wet rooms clustered opposite the public zones.
    if shared_wet and len(private) > 1:
        out.append((ConceptStrategy.SPINE_SERVICE_CLUSTER,
                    public + private[:1] + ensuite,
                    private[1:] + shared_wet, "wet rooms clustered"))
    # 4. Evenly balanced by TOTAL row count, public included — the variant large programmes
    #    need, where even a half/half private split leaves one column too deep.
    if len(rows) >= 4:
        total = len(public) + len(rows)
        take = max(1, total // 2 - len(public) + 1)
        west_b = [r for row in rows[:take] for r in row]
        east_b = [r for row in rows[take:] for r in row]
        if east_b:
            out.append((ConceptStrategy.SPINE_DOUBLE_LOADED, public + west_b, east_b,
                        "balanced by total row count"))
    # 5. Bedrooms grouped opposite public + the shared wet rooms (an ensuite always travels
    #    with its bedroom, or it would be orphaned in a column its mate is not in).
    if shared_wet:
        out.append((ConceptStrategy.BRANCHED_TWO_STACK, public + shared_wet,
                    private + ensuite, "bedrooms grouped opposite public and service"))
    return out


def _forced_v_chain(rooms: list[ProgramRoom], widths: list[float]) -> Node:
    """Right-nested V chain with every cut forced to the width chosen for it."""
    def build(index: int) -> Node:
        if index == len(rooms) - 1:
            return Leaf(rooms[index].zone_id)
        return Split(Cut.V, Leaf(rooms[index].zone_id), build(index + 1), m_to_u(widths[index]))
    return build(0)


def _front_band_concept(spec: ArchitecturalSpec, rooms: list[ProgramRoom], candidate: Rect,
                        ) -> tuple[ConceptCandidate | None, ConceptRejection | None]:
    """Public zones as a full-width band across the front; corridor and bedrooms behind it.

    This is the parti that unblocks large programmes. In the two-column spine the public zones
    sit IN a column and consume its depth — a living room needs ~5 m of it — so a 4BR + safe
    room + 3 wet programme wanted seven bedroom rows in whatever depth was left and never fitted.
    Moving the public zones ACROSS the front frees the entire rear depth for bedrooms, and the
    hall gains a third neighbour: it borders the public band to the north AND both bedroom
    columns to east and west.

    Why the corridor is still straight: a genuinely BENT (L or T) corridor cannot be one
    open-plan space in this engine, because open-marking requires the group's leaves to be
    siblings in the slicing tree and two siblings are always aligned rectangles. Declaring a
    bent hall as an open group would leave a real partition wall between its arms while the
    access graph claimed they were joined — connected on paper, walled in fact. So the shape of
    the parti changes instead of the shape of the corridor.
    """
    strategy = ConceptStrategy.FRONT_PUBLIC_BAND
    public = [r for r in rooms if r.group is ZoneGroup.PUBLIC]
    private = [r for r in rooms if r.group in (ZoneGroup.PRIVATE, ZoneGroup.SERVICE)]
    if len(public) < 2 or len(private) < 3:
        return None, ConceptRejection(
            strategy, RejectionReason.INSUFFICIENT_WING_AREA,
            f"{len(public)} public / {len(private)} private rooms — too few to be worth a "
            f"separate front band")

    rows = _rows_of(private)
    if len(rows) < 3:
        return None, ConceptRejection(strategy, RejectionReason.INSUFFICIENT_WING_AREA,
                                      "too few private rows for two rear columns")
    # Try several rear splits, nearest-balanced first. Fixing the split at the midpoint made a
    # 4BR programme fail on a column that needed 11.6 m of depth where 9.95 m existed, while a
    # 3/4 split of the same rows fits — the balance point is a search variable, not a constant.
    midpoint = (len(rows) + 1) // 2
    split_options = sorted(range(1, len(rows)), key=lambda i: (abs(i - midpoint), i))

    gross = target_gross_area_m2(rooms)
    min_width = minimum_footprint_width_m(rooms)
    max_width, max_depth = u_to_m(candidate.w), u_to_m(candidate.h)

    plan = None
    footprint = None
    west_rows: list[list[ProgramRoom]] = []
    east_rows: list[list[ProgramRoom]] = []
    why = "no footprint proportion satisfied the front-band parti"
    width = min_width
    while width <= max_width + 1e-9 and plan is None:
        depth = min(max_depth, gross / max(width, 1e-6))
        step = max(0.25, (max_depth - depth) / 6) if max_depth > depth else 0.0
        for _ in range(7):
            trial = footprint_of(candidate, width, depth)
            for split_at in split_options:
                west_try = [_orient_row(r, corridor_on_east=True) for r in rows[:split_at]]
                east_try = [_orient_row(r, corridor_on_east=False) for r in rows[split_at:]]
                attempt, reason = _plan_front_band(rooms, public, west_try, east_try,
                                                   u_to_m(trial.w), u_to_m(trial.h))
                if attempt is not None:
                    footprint, plan = trial, attempt
                    west_rows, east_rows = west_try, east_try
                    break
                why = reason
            if plan is not None:
                break
            if step <= 0 or depth >= max_depth - 1e-9:
                break
            depth = min(max_depth, depth + step)
        width += 0.5

    if plan is None or footprint is None:
        return None, ConceptRejection(strategy, RejectionReason.ROOM_BELOW_MINIMUM_DIMENSION, why)

    band_depth, public_widths, west_w, hall_w, east_w, west_depths, east_depths, specs = plan
    fw, fh = u_to_m(footprint.w), u_to_m(footprint.h)

    band_tree = _forced_v_chain(public, public_widths)
    rear = Split(Cut.V,
                 _forced_chain(west_rows, west_depths, west_w - _EDGE_INSET_ALLOWANCE_M),
                 Split(Cut.V, Leaf("HALL"),
                       _forced_chain(east_rows, east_depths, east_w - _EDGE_INSET_ALLOWANCE_M),
                       m_to_u(hall_w)),
                 m_to_u(west_w))
    tree = Split(Cut.H, band_tree, rear, m_to_u(band_depth))

    hall_for = {r.zone_id: "HALL" for r in private}
    access, groups = _build_access(rooms, ["HALL"], [r.zone_id for r in public],
                                   spec.program.open_plan_living, hall_for)

    wing = Wing("W", footprint.x, footprint.y, footprint.w, footprint.h, tree)
    fixture = Fixture(f"GEN_{strategy.value}", (wing,),
                      tuple(specs[r.zone_id] for r in rooms), access, open_groups=groups)
    return ConceptCandidate(
        Concept(fixture, "HALL", Side.N, fw, fh), strategy, (0,),
        rationale=(f"front public band {band_depth:.2f} m deep; rear west {west_w:.2f} m "
                   f"({len(west_rows)} rows) | hall {hall_w:.2f} m | east {east_w:.2f} m "
                   f"({len(east_rows)} rows)"),
        used_area_m2=round(fw * fh, 2),
        unused_wing_area_m2=round(candidate.area_m2() - fw * fh, 2),
    ), None


def _plan_front_band(rooms, public, west_rows, east_rows, fw, fh):
    """Band depth, public widths, rear column widths and row depths — all mutually consistent.

    Order matters, and it is the opposite of the obvious one. Sizing the rooms from the whole
    footprint first inflates the BEDROOMS when the footprint is generous, and inflated bedrooms
    need more rear depth than exists. So the rear is sized from the bedrooms' own programme,
    takes exactly the depth it needs, and the PUBLIC BAND absorbs whatever depth is left over —
    which is what a living room's elasticity is for.
    """
    private = [r for row in west_rows + east_rows for r in row]
    modest = scale_program(rooms, sum(r.template.target_area_m2 for r in rooms))
    areas = {z: spec.net_area_target_m2 for z, spec in modest.items()}

    hall_w = round(max(ROOM_TEMPLATES[ProgramRole.HALL].min_short_side_m
                       + _EDGE_INSET_ALLOWANCE_M, 1.4) / 0.05) * 0.05
    west = [r for row in west_rows for r in row]
    east = [r for row in east_rows for r in row]
    usable = fw - hall_w
    west_min, east_min = _column_min_width(west), _column_min_width(east)
    if west_min + east_min > usable + 1e-9:
        return None, (f"rear columns need {west_min:.2f} + {east_min:.2f} m beside the "
                      f"{hall_w:.2f} m hall but only {usable:.2f} m is available")

    west_raw = sum(areas[r.zone_id] for r in west)
    east_raw = sum(areas[r.zone_id] for r in east)
    west_w = usable * west_raw / max(west_raw + east_raw, 1e-6)
    west_w = round(min(max(west_w, west_min), usable - east_min) / 0.05) * 0.05
    east_w = round((usable - west_w) / 0.05) * 0.05
    west_w = fw - hall_w - east_w

    # How much depth the rear genuinely needs, from the bedrooms' own programme.
    rear_need = 0.0
    for name, width, rws in (("west", west_w, west_rows), ("east", east_w, east_rows)):
        net_w = width - _EDGE_INSET_ALLOWANCE_M
        for row in rws:
            if _row_widths(row, net_w) is None:
                return None, (f"{' + '.join(r.zone_id for r in row)} cannot share the rear "
                              f"{name} column's {net_w:.2f} m of net width at their minimums")
        need = sum(max(sum(areas[r.zone_id] for r in row) / max(net_w, 1e-6),
                       max(r.template.min_short_side_m for r in row) + _EDGE_INSET_ALLOWANCE_M)
                   for row in rws)
        rear_need = max(rear_need, need)

    band_min = max(r.template.min_short_side_m for r in public) + _EDGE_INSET_ALLOWANCE_M
    # Round the rear UP: rounding to nearest could land a couple of centimetres BELOW the
    # requirement this value was just derived from, and the row planner would then reject it.
    rear_depth = math.ceil(min(rear_need, fh - band_min) / 0.05 - 1e-9) * 0.05
    band_depth = round((fh - rear_depth) / 0.05) * 0.05
    rear_depth = fh - band_depth
    if rear_depth < 1.0 or band_depth < band_min - 1e-9:
        return None, (f"rear needs {rear_need:.2f} m and the front band at least {band_min:.2f} m, "
                      f"which does not fit {fh:.2f} m of depth")

    depths = []
    for name, width, rws in (("west", west_w, west_rows), ("east", east_w, east_rows)):
        net_w = width - _EDGE_INSET_ALLOWANCE_M
        d = _row_depths(rws, areas, net_w, rear_depth)
        if d is None:
            return None, (f"rear {name} column needs more than {rear_depth:.2f} m of depth for "
                          f"its {len(rws)} rows at their minimum dimensions")
        depths.append(d)

    # The first public zone must span the hall's x-range, or the hall has no public neighbour.
    needed_first = west_w + hall_w
    remaining = fw - needed_first
    other = public[1:]
    other_area = sum(areas[r.zone_id] for r in other) or 1.0
    widths = [needed_first]
    for room in other[:-1]:
        widths.append(round(remaining * areas[room.zone_id] / other_area / 0.05) * 0.05)
    last_w = fw - sum(widths)
    for room, w in zip(public, widths + [last_w]):
        if w - _EDGE_INSET_ALLOWANCE_M + 1e-6 < room.template.min_short_side_m:
            return None, (f"{room.zone_id} would be {w:.2f} m wide in the front band, below its "
                          f"{room.template.min_short_side_m} m minimum")

    specs: dict[str, ZoneSpec] = {}
    net_band = band_depth - _EDGE_INSET_ALLOWANCE_M
    for room, w in zip(public, widths + [last_w]):
        target = (w - _EDGE_INSET_ALLOWANCE_M) * net_band
        specs[room.zone_id] = ZoneSpec(room.zone_id, _roles_of(room), target * 0.55, target,
                                       target * 1.70, room.template.min_short_side_m,
                                       max(room.template.max_aspect_ratio, 4.0))
    for width, rws, ds in ((west_w, west_rows, depths[0]), (east_w, east_rows, depths[1])):
        net_w = width - _EDGE_INSET_ALLOWANCE_M
        for row, depth in zip(rws, ds):
            net_d = depth - _EDGE_INSET_ALLOWANCE_M / 2
            widths_in_row = _row_widths(row, net_w) or [net_w / len(row)] * len(row)
            for room, w in zip(row, widths_in_row):
                target = w * net_d
                specs[room.zone_id] = ZoneSpec(
                    room.zone_id, _roles_of(room), target * 0.55, target, target * 1.70,
                    room.template.min_short_side_m,
                    max(room.template.max_aspect_ratio,
                        max(w, net_d) / max(1e-6, min(w, net_d)) + 0.3))
    target_hall = (hall_w - _EDGE_INSET_ALLOWANCE_M) * (rear_depth - _EDGE_INSET_ALLOWANCE_M / 2)
    specs["HALL"] = ZoneSpec("HALL", (ProgramRole.HALL, ProgramRole.CIRCULATION),
                             target_hall * 0.5, target_hall, target_hall * 1.9,
                             ROOM_TEMPLATES[ProgramRole.HALL].min_short_side_m, 14.0)

    return (band_depth, widths, west_w, hall_w, east_w, depths[0], depths[1], specs), ""


def _multi_wing_assessment(candidates: list[SolverGeometryCandidate],
                           ) -> ConceptRejection | None:
    """Evaluate whether a second safe wing can host part of the programme.

    A secondary wing is usable only if circulation in the primary wing can reach it directly,
    which means the hall column must sit against the seam. But the hall must also border the
    room stacks, and in an L decomposition the seam covers only PART of the primary wing's side
    — so a hall placed against it would be partly exterior and partly seam, and a single leaf
    side cannot be both (the spike's L2 finding). Reaching the wing would therefore require
    routing circulation through a private room, which the architectural priorities forbid.

    The wing is CONSIDERED and declined with the reason, never silently ignored.
    """
    if len(candidates) < 2:
        return None
    primary, secondary = candidates[0], candidates[1]
    if secondary.order not in primary.adjacent_orders:
        return ConceptRejection(
            ConceptStrategy.MULTI_WING_SPLIT, RejectionReason.NO_SEAM_ALIGNMENT,
            f"wing {secondary.order} ({secondary.area_m2:.1f} m2) shares no boundary with the "
            f"primary wing, so no access topology can span them",
            (primary.order, secondary.order))

    seam_u = primary.rect.shared_edge_len_u(secondary.rect)
    vertical_seam = (primary.rect.x2 == secondary.rect.x or secondary.rect.x2 == primary.rect.x)
    primary_side_u = primary.rect.h if vertical_seam else primary.rect.w
    if seam_u < primary_side_u:
        return ConceptRejection(
            ConceptStrategy.MULTI_WING_SPLIT, RejectionReason.CIRCULATION_WOULD_CROSS_PRIVATE,
            f"seam covers {u_to_m(seam_u):.1f} m of the primary wing's "
            f"{u_to_m(primary_side_u):.1f} m side, so a hall column against it would be part "
            f"exterior and part seam; reaching wing {secondary.order} "
            f"({secondary.area_m2:.1f} m2) would route circulation through a private room",
            (primary.order, secondary.order))
    return None


# --------------------------------------------------------------------------- 7. entry point

def generate_concepts(spec: ArchitecturalSpec,
                      candidates: list[SolverGeometryCandidate]) -> GenerationResult:
    """A small, bounded, deterministic set of plausible concepts, best first."""
    rooms = build_room_program(spec)
    accepted: list[ConceptCandidate] = []
    rejections: list[ConceptRejection] = []

    if not candidates:
        return GenerationResult((), (ConceptRejection(
            ConceptStrategy.SPINE_PUBLIC_PRIVATE, RejectionReason.INSUFFICIENT_TOTAL_AREA,
            "no safe solver geometry available"),), tuple(rooms))

    needed = target_gross_area_m2(rooms)
    usable = [c for c in candidates if c.area_m2 >= needed * 0.55]
    if not usable:
        return GenerationResult((), (ConceptRejection(
            ConceptStrategy.SPINE_PUBLIC_PRIVATE, RejectionReason.INSUFFICIENT_TOTAL_AREA,
            f"largest safe wing is {candidates[0].area_m2:.1f} m2; the programme needs about "
            f"{needed:.1f} m2"),), tuple(rooms))

    primary = usable[0]
    band, rejection = _front_band_concept(spec, rooms, primary.rect)
    if band is not None:
        accepted.append(band)
    elif rejection is not None:
        rejections.append(rejection)

    for strategy, west, east, rationale in _allocations(rooms):
        candidate, rejection = _build(spec, rooms, primary.rect, strategy, west, east, rationale)
        if candidate is not None:
            accepted.append(candidate)
        elif rejection is not None:
            rejections.append(rejection)

    multi = _multi_wing_assessment(candidates)
    if multi is not None:
        rejections.append(multi)

    return GenerationResult(tuple(accepted), tuple(rejections), tuple(rooms))
