"""Stage 2 (B/2), Issue #134 — the non-guillotine realizer, wired to the Stage 2 contract.

Transcribed from Stage 1 Issue #117's `app.vertical_slice.rectilinear_realizer` (on
`integration/rectilinear-realizer`, not merged to `main`, not importable from this worktree — see
`docs/stage2/CONTRACT.md`'s own "transcribed, not imported" precedent) with three changes, all
additive, none touching #117's own solver logic:

1. The mirrored intent shapes (`ZoneIntent`/`PinwheelWing`/`RowWing`/`ShapeGroupIntent`/`Wing`/
   `RealizerInput`) are DELETED here and imported from `stage2.contract` instead — Issue #133's own
   point (§4 of `docs/stage2/CONTRACT.md`): one shape, one owner, not a second copy per child.
2. `wet_rooms` (already carried on `contract.RealizerInput`, unused by #117's own `realize_layout`)
   is threaded through to `assemble_design`/`validate` so C17/C29 can run on the output — the exact
   gap `docs/stage2/CONTRACT.md` §5 names as Required Behaviour 5's real fix.
3. A `safe_room_constraint` parameter (default `None`, preserving #117's own behaviour exactly when
   omitted) is threaded to `validate` for C4's authoritative-SAFE_ROOM branch, and any zone whose
   role is `ProgramRole.SAFE_ROOM` gets `WallType.RC_SAFE_ROOM` on all four sides instead of the
   ordinary PARTITION/EXTERIOR/OPEN wall-type derivation — #117's own wall loop never produced
   `RC_SAFE_ROOM` (it had no safe-room caller yet), and C4 fails closed on any safe-room zone that
   is not RC on every side (see `validation.py`'s own C4 check).

Refusals are `contract.RealizerRefusal` directly (not a locally-defined type) — Required Behaviour 4
of Issue #133: the realizer's own refusal IS the contract's refusal, never a parallel shape a caller
must translate.

`STAGE2_REALIZER_ENABLED` gates nothing — no existing caller imports `app.vertical_slice.stage2` at
all, so the frozen 432-context regression corpus is unaffected by construction (AC-6). Same
disclosure/kill-switch precedent as `RECTILINEAR_REALIZER_ENABLED`/`STAGE2_CONTRACT_ENABLED`.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

from shapely.geometry import Polygon, box as _box
from shapely.ops import unary_union

from .. import footprint as footprint_module
from ..constraints import TypedConstraint
from ..design_output import GeometricDesign, assemble as assemble_design
from ..doors import Door, build_entrance_door, generate_interior_doors, resolve_entrance
from ..furniture import FurnitureCheck, check_furniture_feasibility
from ..geometry_core.engine import WallMap, net_rect_m
from ..geometry_core.model import (
    ConnectionKind,
    DesiredAccessEdge,
    DesiredAccessTopology,
    Fixture,
    Leaf,
    ProgramRole,
    Rect,
    Side,
    WallType,
    ZoneSpec,
    m_to_u,
    u_to_m,
)
from ..geometry_core.model import Wing as GcWing
from ..site import EntranceWalk, SitePlan, build_entrance
from ..validation import Check, ValidationReport, check_realized_dimensions, validate
from ..windows import Window, generate_windows
from .contract import (
    PinwheelWing,
    RealizerInput,
    RealizerRefusal,
    RowWing,
    ShapeGroupIntent,
    Wing,
    ZoneIntent,
)

#: Off by default — the same disclosure/kill-switch precedent as `RECTILINEAR_REALIZER_ENABLED`/
#: `STAGE2_CONTRACT_ENABLED`. No existing caller imports this module, so this gates nothing.
STAGE2_REALIZER_ENABLED = False

UNIT_M = 0.05
_MIN_SHORT_SIDE_FLOOR_M = 1.0
_L_NOTCH_PREFERRED_ASPECT = 2.3
_U_NOTCH_PREFERRED_ASPECT = 2.6
_PERMISSIVE_MIN_M2 = 0.01
_PERMISSIVE_MAX_M2 = 100_000.0
_PERMISSIVE_MIN_SHORT_SIDE_M = 0.01
_PERMISSIVE_MAX_ASPECT = 1_000.0
_INSET_MARGIN_M = 0.30


@dataclass(frozen=True)
class MergedGeometry:
    polygon_m: tuple[tuple[float, float], ...]
    bbox_m: tuple[float, float, float, float]
    gross_area_m2: float
    net_area_m2: float
    aspect: float


@dataclass
class RealizedLayout:
    name: str
    fixture: Fixture
    rects: dict[str, Rect]
    walls: WallMap
    site: SitePlan
    interior_doors: list[Door]
    entrance_door: Door
    windows: list[Window]
    furniture: list[FurnitureCheck]
    report: ValidationReport
    c27: Check
    design: GeometricDesign
    zone_of_cell: dict[str, str]
    groups: dict[str, MergedGeometry]
    wall_time_s: float
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.report.ok and self.c27.passed


# --------------------------------------------------------------------------- pinwheel solver

def _solve_pinwheel(w_u: int, h_u: int, area_n_m2: float, area_e_m2: float, area_s_m2: float,
                     area_w_m2: float, min_short_u: int) -> tuple[int, int, int, int] | None:
    if w_u <= 0 or h_u <= 0:
        return None
    tn = max(min_short_u, round(area_n_m2 / (w_u * UNIT_M) / UNIT_M))
    te = max(min_short_u, round(area_e_m2 / (h_u * UNIT_M) / UNIT_M))
    ts = max(min_short_u, round(area_s_m2 / (w_u * UNIT_M) / UNIT_M))
    tw = max(min_short_u, round(area_w_m2 / (h_u * UNIT_M) / UNIT_M))
    for _ in range(30):
        eff_w = max(w_u - te, min_short_u)
        tn = max(min_short_u, round(area_n_m2 / (eff_w * UNIT_M) / UNIT_M))
        eff_h = max(h_u - ts, min_short_u)
        te = max(min_short_u, round(area_e_m2 / (eff_h * UNIT_M) / UNIT_M))
        eff_w2 = max(w_u - tw, min_short_u)
        ts = max(min_short_u, round(area_s_m2 / (eff_w2 * UNIT_M) / UNIT_M))
        eff_h2 = max(h_u - tn, min_short_u)
        tw = max(min_short_u, round(area_w_m2 / (eff_h2 * UNIT_M) / UNIT_M))
    if tn + ts + min_short_u > h_u or te + tw + min_short_u > w_u:
        return None
    if tn < min_short_u or te < min_short_u or ts < min_short_u or tw < min_short_u:
        return None
    return tn, te, ts, tw


def _pinwheel_rects(ox: int, oy: int, w_u: int, h_u: int, tn: int, te: int, ts: int,
                     tw: int) -> dict[str, Rect]:
    return {
        "n": Rect(ox, oy, w_u - te, tn),
        "e": Rect(ox + w_u - te, oy, te, h_u - ts),
        "s": Rect(ox + tw, oy + h_u - ts, w_u - tw, ts),
        "w": Rect(ox, oy + tn, tw, h_u - tn),
        "center": Rect(ox + tw, oy + tn, w_u - tw - te, h_u - tn - ts),
    }


# --------------------------------------------------------------------------- notch-carve solver

def _wh_for_area(target_area_m2: float, preferred_aspect: float, min_short_u: int,
                  max_w_u: int, max_h_u: int) -> tuple[int, int] | None:
    w_u = max(min_short_u, round(math.sqrt(max(target_area_m2, 1e-6) * preferred_aspect) / UNIT_M))
    w_u = min(w_u, max_w_u)
    if w_u < min_short_u:
        return None
    h_u = max(min_short_u, round((target_area_m2 / (w_u * UNIT_M)) / UNIT_M))
    if h_u < min_short_u or h_u > max_h_u:
        return None
    return w_u, h_u


def carve_l(container: Rect, corner: str, notch_w_u: int,
            notch_h_u: int) -> tuple[list[Rect], Rect]:
    north = corner[0] == "N"
    west = corner[1] == "W"
    row0_h = notch_h_u if north else container.h - notch_h_u
    row1_h = container.h - row0_h
    col0_w = notch_w_u if west else container.w - notch_w_u
    col1_w = container.w - col0_w
    c00 = Rect(container.x, container.y, col0_w, row0_h)
    c01 = Rect(container.x + col0_w, container.y, col1_w, row0_h)
    c10 = Rect(container.x, container.y + row0_h, col0_w, row1_h)
    c11 = Rect(container.x + col0_w, container.y + row0_h, col1_w, row1_h)
    if north and west:
        notch, big = c00, [c01, c10, c11]
    elif north and not west:
        notch, big = c01, [c00, c10, c11]
    elif not north and west:
        notch, big = c10, [c00, c01, c11]
    else:
        notch, big = c11, [c00, c01, c10]
    return big, notch


def carve_u(container: Rect, edge: str, notch_w_u: int, notch_h_u: int) -> tuple[list[Rect], Rect]:
    notch_x = container.x + (container.w - notch_w_u) // 2
    col0_w = notch_x - container.x
    col1_w = notch_w_u
    col2_w = container.x2 - (notch_x + notch_w_u)
    row0_h = notch_h_u if edge == "N" else container.h - notch_h_u
    row1_h = container.h - row0_h
    xs = (container.x, container.x + col0_w, container.x + col0_w + col1_w)
    ws = (col0_w, col1_w, col2_w)
    row0 = [Rect(x, container.y, w, row0_h) for x, w in zip(xs, ws)]
    row1 = [Rect(x, container.y + row0_h, w, row1_h) for x, w in zip(xs, ws)]
    if edge == "N":
        notch, big = row0[1], [row0[0], row0[2], row1[0], row1[1], row1[2]]
    else:
        notch, big = row1[1], [row0[0], row0[1], row0[2], row1[0], row1[2]]
    return big, notch


def carve_t(container: Rect, edge: str, notch_w_left_u: int, notch_w_right_u: int,
            notch_h_u: int) -> tuple[list[Rect], list[Rect]]:
    stem_w_u = container.w - notch_w_left_u - notch_w_right_u
    xs = (container.x, container.x + notch_w_left_u, container.x2 - notch_w_right_u)
    ws = (notch_w_left_u, stem_w_u, notch_w_right_u)
    row_bar_h = container.h - notch_h_u if edge == "N" else notch_h_u
    row_notch_h = container.h - row_bar_h
    bar_y = container.y if edge == "N" else container.y + row_notch_h
    notch_y = container.y + row_bar_h if edge == "N" else container.y
    bar_row = [Rect(x, bar_y, w, row_bar_h) for x, w in zip(xs, ws)]
    notch_row = [Rect(x, notch_y, w, row_notch_h) for x, w in zip(xs, ws)]
    big = [bar_row[0], bar_row[1], bar_row[2], notch_row[1]]
    return big, [notch_row[0], notch_row[2]]


# --------------------------------------------------------------------------- geometry helpers

def _merged_geometry(cell_rects: list[Rect]) -> MergedGeometry | None:
    boxes = [_box(u_to_m(r.x), u_to_m(r.y), u_to_m(r.x2), u_to_m(r.y2)) for r in cell_rects]
    union = unary_union(boxes)
    if not isinstance(union, Polygon):
        return None
    union = union.simplify(0, preserve_topology=True)
    minx, miny, maxx, maxy = union.bounds
    long_side = max(maxx - minx, maxy - miny)
    short_side = max(min(maxx - minx, maxy - miny), 1e-6)
    ring = tuple(union.exterior.coords)[:-1]
    return MergedGeometry(
        polygon_m=ring, bbox_m=(minx, miny, maxx - minx, maxy - miny),
        gross_area_m2=round(union.area, 4), net_area_m2=0.0, aspect=long_side / short_side,
    )


def _side_between(a: Rect, b: Rect) -> Side | None:
    if a.x2 == b.x:
        return Side.E
    if b.x2 == a.x:
        return Side.W
    if a.y2 == b.y:
        return Side.S
    if b.y2 == a.y:
        return Side.N
    return None


def _permissive_spec(zone_id: str, role: ProgramRole) -> ZoneSpec:
    return ZoneSpec(zone_id, (role,), _PERMISSIVE_MIN_M2, _PERMISSIVE_MIN_M2, _PERMISSIVE_MAX_M2,
                     _PERMISSIVE_MIN_SHORT_SIDE_M, _PERMISSIVE_MAX_ASPECT)


def _zone_spec(zi: ZoneIntent) -> ZoneSpec:
    return ZoneSpec(zi.zone_id, (zi.role,), zi.min_area_m2, zi.target_area_m2, zi.max_area_m2,
                     zi.min_short_side_m, zi.max_aspect_ratio)


def _leaf_chain(zone_ids: tuple[str, ...]):
    from ..geometry_core.model import Cut, Split
    node = Leaf(zone_ids[-1])
    for zone_id in reversed(zone_ids[:-1]):
        node = Split(Cut.V, Leaf(zone_id), node, None)
    return node


# --------------------------------------------------------------------------- wing builders

@dataclass
class _WingBuild:
    wing_id: str
    origin: tuple[int, int]
    size: tuple[int, int]
    rects: dict[str, Rect]
    roles: dict[str, tuple[ProgramRole, ...]]
    specs: dict[str, ZoneSpec]
    same_zone_edges: list[tuple[str, str]]
    zone_of_cell: dict[str, str]
    groups: dict[str, tuple[str, ...]]
    access_edges: list[tuple[str, str]]
    seam_left_ids: tuple[str, ...] = ()
    seam_right_ids: tuple[str, ...] = ()


def _build_pinwheel_wing(w: PinwheelWing, origin: tuple[int, int]) -> _WingBuild | RealizerRefusal:
    w_u, h_u = m_to_u(w.width_m), m_to_u(w.height_m)
    min_short_u = m_to_u(min(w.n.min_short_side_m, w.e.min_short_side_m, w.s.min_short_side_m,
                              w.w.min_short_side_m, w.center.min_short_side_m) + _INSET_MARGIN_M)
    solved = _solve_pinwheel(w_u, h_u, w.n.target_area_m2, w.e.target_area_m2, w.s.target_area_m2,
                              w.w.target_area_m2, min_short_u)
    if solved is None:
        return RealizerRefusal("PINWHEEL_INFEASIBLE",
                                f"wing '{w.wing_id}' {w.width_m}x{w.height_m} m has no "
                                f"band-thickness solution honouring every arm's minimum short "
                                f"side ({min_short_u * UNIT_M} m)")
    tn, te, ts, tw = solved
    ox, oy = origin
    rects_by_slot = _pinwheel_rects(ox, oy, w_u, h_u, tn, te, ts, tw)
    intents = {"n": w.n, "e": w.e, "s": w.s, "w": w.w, "center": w.center}
    rects: dict[str, Rect] = {}
    roles: dict[str, tuple[ProgramRole, ...]] = {}
    specs: dict[str, ZoneSpec] = {}
    zone_of_cell: dict[str, str] = {}
    for slot, zi in intents.items():
        r = rects_by_slot[slot]
        area = r.area_m2()
        if not (zi.min_area_m2 - 0.02 <= area <= zi.max_area_m2 + 0.02):
            return RealizerRefusal("AREA_INFEASIBLE",
                                    f"{zi.zone_id}: pinwheel-realized area {area:.2f} m2 outside "
                                    f"[{zi.min_area_m2},{zi.max_area_m2}]")
        short = min(u_to_m(r.w), u_to_m(r.h))
        if short < zi.min_short_side_m + _INSET_MARGIN_M - 1e-6:
            return RealizerRefusal("SHORT_SIDE_INFEASIBLE",
                                    f"{zi.zone_id}: pinwheel-realized short side {short:.2f} m "
                                    f"(gross) < {zi.min_short_side_m} m (net) + "
                                    f"{_INSET_MARGIN_M} m inset margin")
        rects[zi.zone_id] = r
        roles[zi.zone_id] = (zi.role,)
        specs[zi.zone_id] = _zone_spec(zi)
        zone_of_cell[zi.zone_id] = zi.zone_id
    access_edges = [
        (w.n.zone_id, w.center.zone_id), (w.s.zone_id, w.center.zone_id),
        (w.e.zone_id, w.center.zone_id), (w.w.zone_id, w.center.zone_id),
    ]
    return _WingBuild(w.wing_id, origin, (w_u, h_u), rects, roles, specs, [], zone_of_cell, {},
                       access_edges, seam_left_ids=(w.w.zone_id,), seam_right_ids=(w.e.zone_id,))


def _carve_group(group: ShapeGroupIntent, container: Rect
                  ) -> tuple[list[Rect], list[Rect], list[ZoneIntent]] | RealizerRefusal:
    max_w_u, max_h_u = container.w - m_to_u(_MIN_SHORT_SIDE_FLOOR_M), \
        container.h - m_to_u(_MIN_SHORT_SIDE_FLOOR_M)
    if group.family == "L":
        notch = group.notches[0]
        dims = _wh_for_area(notch.target_area_m2, _L_NOTCH_PREFERRED_ASPECT,
                             m_to_u(notch.min_short_side_m + _INSET_MARGIN_M), max_w_u, max_h_u)
        if dims is None:
            return RealizerRefusal("NOTCH_INFEASIBLE",
                                    f"{notch.zone_id}: no corner notch fits "
                                    f"{notch.target_area_m2} m2 inside the {group.group_id} "
                                    f"container")
        big_rects, notch_rect = carve_l(container, group.corner, *dims)
        return big_rects, [notch_rect], [notch]
    if group.family == "U":
        notch = group.notches[0]
        max_w_edge_u = container.w - 2 * m_to_u(_MIN_SHORT_SIDE_FLOOR_M)
        dims = _wh_for_area(notch.target_area_m2, _U_NOTCH_PREFERRED_ASPECT,
                             m_to_u(notch.min_short_side_m + _INSET_MARGIN_M), max_w_edge_u, max_h_u)
        if dims is None:
            return RealizerRefusal("NOTCH_INFEASIBLE",
                                    f"{notch.zone_id}: no edge notch fits "
                                    f"{notch.target_area_m2} m2 inside the {group.group_id} "
                                    f"container")
        big_rects, notch_rect = carve_u(container, group.edge, *dims)
        return big_rects, [notch_rect], [notch]
    if group.family == "T":
        left, right = group.notches
        min_short_padded = max(left.min_short_side_m, right.min_short_side_m) + _INSET_MARGIN_M
        h_u = max(m_to_u(min_short_padded), round(container.h * 0.35 / UNIT_M))
        h_u = min(h_u, max_h_u)
        for _ in range(6):
            w_left_u = max(m_to_u(left.min_short_side_m + _INSET_MARGIN_M),
                            round(left.target_area_m2 / (h_u * UNIT_M) / UNIT_M))
            w_right_u = max(m_to_u(right.min_short_side_m + _INSET_MARGIN_M),
                             round(right.target_area_m2 / (h_u * UNIT_M) / UNIT_M))
            stem_w_u = container.w - w_left_u - w_right_u
            if stem_w_u >= m_to_u(_MIN_SHORT_SIDE_FLOOR_M) and h_u >= m_to_u(min_short_padded):
                big_rects, notch_rects = carve_t(container, group.edge, w_left_u, w_right_u, h_u)
                return big_rects, notch_rects, [left, right]
            h_u += m_to_u(0.2)
            if h_u > max_h_u:
                break
        return RealizerRefusal("NOTCH_INFEASIBLE",
                                f"{group.group_id}: no T stem fits both {left.zone_id} and "
                                f"{right.zone_id} inside the container")
    return RealizerRefusal("UNKNOWN_FAMILY", f"shape family '{group.family}' is not L/U/T")


def _build_row_wing(w: RowWing, origin: tuple[int, int]) -> _WingBuild | RealizerRefusal:
    w_u, h_u = m_to_u(w.width_m), m_to_u(w.height_m)
    ox, oy = origin
    slot_intents: list[tuple[str, ZoneIntent | ShapeGroupIntent]] = []
    for slot_id in w.slots:
        if slot_id in w.groups:
            slot_intents.append((slot_id, w.groups[slot_id]))
        elif slot_id in w.zones:
            slot_intents.append((slot_id, w.zones[slot_id]))
        else:
            return RealizerRefusal("UNKNOWN_SLOT", f"slot '{slot_id}' is neither a zone nor a group")

    total_target = sum(
        (s.big.target_area_m2 + sum(n.target_area_m2 for n in s.notches))
        if isinstance(s, ShapeGroupIntent) else s.target_area_m2
        for _, s in slot_intents
    )
    if total_target <= 0:
        return RealizerRefusal("EMPTY_ROW", f"wing '{w.wing_id}' has no zones")

    rects: dict[str, Rect] = {}
    roles: dict[str, tuple[ProgramRole, ...]] = {}
    specs: dict[str, ZoneSpec] = {}
    zone_of_cell: dict[str, str] = {}
    same_zone_edges: list[tuple[str, str]] = []
    groups_out: dict[str, tuple[str, ...]] = {}
    access_edges: list[tuple[str, str]] = []
    slot_cells: list[list[str]] = []

    cursor_x = ox
    remaining_w = w_u
    for idx, (slot_id, intent) in enumerate(slot_intents):
        is_last = idx == len(slot_intents) - 1
        if isinstance(intent, ShapeGroupIntent):
            slot_target = intent.big.target_area_m2 + sum(n.target_area_m2 for n in intent.notches)
        else:
            slot_target = intent.target_area_m2
        frac = slot_target / total_target
        slot_w_u = remaining_w if is_last else max(m_to_u(_MIN_SHORT_SIDE_FLOOR_M),
                                                     round(w_u * frac))
        slot_w_u = min(slot_w_u, remaining_w)
        container = Rect(cursor_x, oy, slot_w_u, h_u)
        cursor_x += slot_w_u
        remaining_w -= slot_w_u

        if isinstance(intent, ZoneIntent):
            zi = intent
            area = container.area_m2()
            if not (zi.min_area_m2 - 0.02 <= area <= zi.max_area_m2 + 0.02):
                return RealizerRefusal("AREA_INFEASIBLE",
                                        f"{zi.zone_id}: row-realized area {area:.2f} m2 outside "
                                        f"[{zi.min_area_m2},{zi.max_area_m2}]")
            short = min(u_to_m(container.w), u_to_m(container.h))
            if short < zi.min_short_side_m + _INSET_MARGIN_M - 1e-6:
                return RealizerRefusal("SHORT_SIDE_INFEASIBLE",
                                        f"{zi.zone_id}: row-realized short side {short:.2f} m "
                                        f"(gross) < {zi.min_short_side_m} m (net) + "
                                        f"{_INSET_MARGIN_M} m inset margin")
            rects[zi.zone_id] = container
            roles[zi.zone_id] = (zi.role,)
            specs[zi.zone_id] = _zone_spec(zi)
            zone_of_cell[zi.zone_id] = zi.zone_id
            slot_cells.append([zi.zone_id])
            continue

        group = intent
        carved = _carve_group(group, container)
        if isinstance(carved, RealizerRefusal):
            return carved
        big_rects, notch_rects, notch_intents = carved

        big_area = sum(r.area_m2() for r in big_rects)
        if not (group.big.min_area_m2 - 0.02 <= big_area <= group.big.max_area_m2 + 0.02):
            return RealizerRefusal("AREA_INFEASIBLE",
                                    f"{group.big.zone_id}: carved area {big_area:.2f} m2 outside "
                                    f"[{group.big.min_area_m2},{group.big.max_area_m2}]")
        merged = _merged_geometry(big_rects)
        if merged is None:
            return RealizerRefusal("NOT_ONE_POLYGON",
                                    f"{group.big.zone_id}: its cells do not union to one simple "
                                    f"polygon")
        aspect_ceiling = group.big.max_aspect_ratio + 1e-6
        if merged.aspect > aspect_ceiling:
            return RealizerRefusal("ASPECT_INFEASIBLE",
                                    f"{group.big.zone_id}: carved AABB aspect {merged.aspect:.2f} "
                                    f"> {group.big.max_aspect_ratio}")

        big_cell_ids = [f"{group.big.zone_id}__c{i}" for i in range(len(big_rects))]
        for cid, r in zip(big_cell_ids, big_rects):
            rects[cid] = r
            roles[cid] = (group.big.role,)
            specs[cid] = _permissive_spec(cid, group.big.role)
            zone_of_cell[cid] = group.big.zone_id
        for i in range(len(big_cell_ids)):
            for j in range(i + 1, len(big_cell_ids)):
                if big_rects[i].shared_edge_len_u(big_rects[j]) > 0:
                    same_zone_edges.append((big_cell_ids[i], big_cell_ids[j]))
        groups_out[group.big.zone_id] = tuple(big_cell_ids)

        slot_notch_ids: list[str] = []
        for ni, (notch_rect, notch_intent) in enumerate(zip(notch_rects, notch_intents)):
            n_area = notch_rect.area_m2()
            if not (notch_intent.min_area_m2 - 0.02 <= n_area <= notch_intent.max_area_m2 + 0.02):
                return RealizerRefusal("AREA_INFEASIBLE",
                                        f"{notch_intent.zone_id}: notch area {n_area:.2f} m2 "
                                        f"outside [{notch_intent.min_area_m2},"
                                        f"{notch_intent.max_area_m2}]")
            rects[notch_intent.zone_id] = notch_rect
            roles[notch_intent.zone_id] = (notch_intent.role,)
            specs[notch_intent.zone_id] = _zone_spec(notch_intent)
            zone_of_cell[notch_intent.zone_id] = notch_intent.zone_id
            slot_notch_ids.append(notch_intent.zone_id)
            for cid in big_cell_ids:
                if rects[cid].shared_edge_len_u(notch_rect) > 0:
                    access_edges.append((notch_intent.zone_id, cid))
                    break

        slot_cells.append(list(big_cell_ids) + slot_notch_ids)

    for i in range(len(slot_cells) - 1):
        pair = _best_touching_pair(slot_cells[i], slot_cells[i + 1], rects)
        if pair is None:
            return RealizerRefusal("SLOTS_DO_NOT_TOUCH",
                                    f"no cell of slot {i} touches any cell of slot {i + 1}")
        access_edges.append(pair)

    first_cells, last_cells = slot_cells[0], slot_cells[-1]
    seam_left = tuple(sorted(first_cells, key=lambda c: rects[c].x))[:1]
    seam_right = tuple(sorted(last_cells, key=lambda c: -rects[c].x2))[:1]

    return _WingBuild(w.wing_id, origin, (w_u, h_u), rects, roles, specs, same_zone_edges,
                       zone_of_cell, groups_out, access_edges, seam_left, seam_right)


def _best_touching_pair(cells_a: list[str], cells_b: list[str],
                         rects: dict[str, Rect]) -> tuple[str, str] | None:
    best: tuple[str, str] | None = None
    best_len = 0
    for a in cells_a:
        for b in cells_b:
            shared = rects[a].shared_edge_len_u(rects[b])
            if shared > best_len:
                best_len, best = shared, (a, b)
    return best


# --------------------------------------------------------------------------- assembly + validation

def _group_checks(group_id: str, cell_ids: tuple[str, ...], rects: dict[str, Rect],
                   walls: WallMap, big: ZoneIntent) -> list[Check]:
    cell_rects = [rects[c] for c in cell_ids]
    merged = _merged_geometry(cell_rects)
    checks: list[Check] = []
    if merged is None:
        checks.append(Check(f"GROUP-C2:{group_id}", "notch-carve cells union to one polygon",
                             False, "cells do not form one simple polygon"))
        return checks
    net_area = round(sum(net_rect_m(c, rects[c], walls)[2] for c in cell_ids), 4)
    checks.append(Check(f"GROUP-C2:{group_id}", "notch-carve cells union to one polygon (C2)",
                         True, f"{len(cell_ids)} cells union to one simple rectilinear polygon, "
                               f"gross area {merged.gross_area_m2:.2f} m2"))
    area_ok = big.min_area_m2 - 0.05 <= net_area <= big.max_area_m2 + 0.05
    checks.append(Check(f"GROUP-C3:{group_id}", "merged zone net area within its own bounds (C3')",
                         area_ok, f"{group_id} net {net_area:.2f} m2 vs "
                                  f"[{big.min_area_m2},{big.max_area_m2}]"))
    aspect_ok = merged.aspect <= big.max_aspect_ratio + 1e-6
    checks.append(Check(f"GROUP-C20:{group_id}", "merged zone AABB aspect within bound (C20')",
                         aspect_ok, f"{group_id} oriented aspect {merged.aspect:.2f} vs "
                                    f"{big.max_aspect_ratio}"))
    return checks


def _displayed_rows(fixture: Fixture, rects: dict[str, Rect], walls: WallMap,
                     groups: dict[str, tuple[str, ...]], group_geometry: dict[str, MergedGeometry],
                     ) -> tuple[list, Check]:
    grouped_cells = {c for cells in groups.values() for c in cells}

    @dataclass
    class _Row:
        id: str
        width_m: float
        depth_m: float
        area_m2: float
        gross_width_m: float
        gross_depth_m: float
        gross_area_m2: float

    rows: list[_Row] = []
    for z in fixture.zones:
        if z.zone_id in grouped_cells or z.zone_id not in rects:
            continue
        nw, nh, na = net_rect_m(z.zone_id, rects[z.zone_id], walls)
        r = rects[z.zone_id]
        rows.append(_Row(z.zone_id, nw, nh, na, u_to_m(r.w), u_to_m(r.h),
                          round(u_to_m(r.w) * u_to_m(r.h), 4)))
    rect_gross_total = round(sum(r.gross_area_m2 for r in rows), 4)
    c27 = check_realized_dimensions(rows, rect_gross_total) if rows else Check(
        "C27", "displayed dimensions consistent with realized geometry", True, "no rectangle rooms")

    for group_id, cell_ids in groups.items():
        merged = group_geometry[group_id]
        bbox_w, bbox_h = merged.bbox_m[2], merged.bbox_m[3]
        rows.append(_Row(group_id, bbox_w, bbox_h, merged.net_area_m2, bbox_w, bbox_h,
                          merged.gross_area_m2))
    group_c27 = _group_c27(group_geometry)
    c27 = Check("C27", c27.name, c27.passed and group_c27.passed,
                c27.detail + (("; " + group_c27.detail) if group_geometry else ""))
    return rows, c27


def _group_c27(group_geometry: dict[str, MergedGeometry]) -> Check:
    return Check("C27'", "notch-carve group's reported area matches its true polygon area",
                 True, f"{len(group_geometry)} group(s): gross/net area read directly off the "
                       f"group's own MergedGeometry, never a bounding-box width x depth product")


def _build_site(wings: list[_WingBuild]) -> SitePlan:
    wing_rects = tuple(Rect(*wb.origin, *wb.size) for wb in wings)
    footprint = footprint_module.bounding_box(wing_rects)
    plot = Rect(0, 0, footprint.x2 + m_to_u(2.0), footprint.y2 + m_to_u(2.0))
    entrance_x = footprint.x + footprint.w // 2
    entrance = build_entrance(footprint, entrance_x)
    crook = [r for r in footprint_module.remainder_within_bbox(wing_rects) if r.w > 0 and r.h > 0]
    from ..geometry_core.model import OutdoorClassification, OutdoorRegion
    garden = tuple(OutdoorRegion(f"garden_{i}", (r,), OutdoorClassification.GARDEN)
                    for i, r in enumerate(crook))
    return SitePlan(plot=plot, footprint=footprint, footprint_offset_u=(0, 0), parking=(),
                     entrance=entrance, garden=garden, wings=wing_rects)


def _apply_safe_room_walls(rects: dict[str, Rect], roles: dict[str, tuple[ProgramRole, ...]],
                            walls: WallMap) -> None:
    """C4 fails closed unless every side of a SAFE_ROOM zone is `WallType.RC_SAFE_ROOM` (see
    `validation.py`'s own C4 check). #117's own wall-derivation loop never produced this wall type
    (it had no safe-room caller); this override runs AFTER that loop, only for zones whose role is
    `ProgramRole.SAFE_ROOM`, never touching any other zone's own PARTITION/EXTERIOR/OPEN wall."""
    for zone_id, zone_roles in roles.items():
        if ProgramRole.SAFE_ROOM not in zone_roles or zone_id not in rects:
            continue
        for side in Side:
            walls[(zone_id, side)] = WallType.RC_SAFE_ROOM


def realize_layout(layout: RealizerInput, programme: object | None = None,
                    buildable: Rect | None = None,
                    safe_room_constraint: TypedConstraint | None = None,
                    ) -> RealizedLayout | RealizerRefusal:
    """Realize a PLACED `contract.RealizerInput` into real, axis-aligned, rectilinear geometry, or
    REFUSE with a `contract.RealizerRefusal` naming the failing constraint — the Stage 2 realization
    step (Required Behaviour 3). `wet_rooms` (on `layout`) and `safe_room_constraint` reach
    `validate()` so C17/C29/C4 all run and are authoritative on the output (Required Behaviour 4/5)."""
    t0 = time.monotonic()
    if not layout.wings:
        return RealizerRefusal("EMPTY_LAYOUT", "a layout needs at least one wing")

    origin = (m_to_u(2.0), m_to_u(2.0))
    wing_builds: list[_WingBuild] = []
    cursor_x = origin[0]
    for w in layout.wings:
        wb = _build_pinwheel_wing(w, (cursor_x, origin[1])) if isinstance(w, PinwheelWing) \
            else _build_row_wing(w, (cursor_x, origin[1]))
        if isinstance(wb, RealizerRefusal):
            return wb
        wing_builds.append(wb)
        cursor_x += wb.size[0]

    if buildable is not None:
        total_w = sum(wb.size[0] for wb in wing_builds)
        total_h = max(wb.size[1] for wb in wing_builds)
        if total_w > buildable.w or total_h > buildable.h:
            return RealizerRefusal(
                "ENVELOPE_TOO_LARGE",
                f"realized footprint {u_to_m(total_w)}x{u_to_m(total_h)} m exceeds the "
                f"buildable envelope {u_to_m(buildable.w)}x{u_to_m(buildable.h)} m")

    rects: dict[str, Rect] = {}
    roles: dict[str, tuple[ProgramRole, ...]] = {}
    specs: dict[str, ZoneSpec] = {}
    zone_of_cell: dict[str, str] = {}
    walls: WallMap = {}
    groups: dict[str, tuple[str, ...]] = {}
    access_pairs: list[tuple[str, str]] = []
    for wb in wing_builds:
        rects.update(wb.rects)
        roles.update(wb.roles)
        specs.update(wb.specs)
        zone_of_cell.update(wb.zone_of_cell)
        groups.update(wb.groups)
        access_pairs.extend(wb.access_edges)

    open_pairs: set[frozenset[str]] = set()
    for wb in wing_builds:
        for a, b in wb.same_zone_edges:
            open_pairs.add(frozenset((a, b)))
    for zone_id, rect in rects.items():
        touching: dict[Side, str] = {}
        for other_id, other in rects.items():
            if other_id == zone_id or rect.shared_edge_len_u(other) <= 0:
                continue
            side = _side_between(rect, other)
            if side is not None:
                touching[side] = other_id
        for side in Side:
            other_id = touching.get(side)
            if other_id is not None and frozenset((zone_id, other_id)) in open_pairs:
                walls[(zone_id, side)] = WallType.OPEN
            elif other_id is not None:
                walls[(zone_id, side)] = WallType.PARTITION
            else:
                walls[(zone_id, side)] = WallType.EXTERIOR

    wings_out = []
    seam_sides: dict[str, tuple[tuple[str, Side], ...]] = {}
    for i, wb in enumerate(wing_builds):
        sides: list[tuple[str, Side]] = []
        if i > 0:
            prev = wing_builds[i - 1]
            for lid in wb.seam_left_ids:
                for rid in prev.seam_right_ids:
                    if rects[lid].shared_edge_len_u(rects[rid]) > 0:
                        sides.append((lid, Side.W))
                        access_pairs.append((rid, lid))
        if i < len(wing_builds) - 1:
            nxt = wing_builds[i + 1]
            for rid in wb.seam_right_ids:
                for lid in nxt.seam_left_ids:
                    if rects[rid].shared_edge_len_u(rects[lid]) > 0:
                        sides.append((rid, Side.E))
        seam_sides[wb.wing_id] = tuple(sides)

    for wb in wing_builds:
        zone_ids = tuple(wb.rects.keys())
        wings_out.append(GcWing(
            wing_id=wb.wing_id, origin_x_u=wb.origin[0], origin_y_u=wb.origin[1],
            w_u=wb.size[0], h_u=wb.size[1], tree=_leaf_chain(zone_ids),
            seam_leaf_sides=seam_sides[wb.wing_id],
        ))

    zones = tuple(ZoneSpec(zid, roles[zid], specs[zid].net_area_min_m2, specs[zid].net_area_target_m2,
                            specs[zid].net_area_max_m2, specs[zid].min_short_side_m,
                            specs[zid].max_aspect_ratio) for zid in rects)
    edges = tuple(DesiredAccessEdge(a, b, ConnectionKind.DOOR) for a, b in access_pairs)
    open_groups = tuple(tuple(sorted(pair)) for pair in open_pairs)
    fixture = Fixture(layout.name, tuple(wings_out), zones, DesiredAccessTopology(edges), open_groups)

    _apply_safe_room_walls(rects, roles, walls)

    site = _build_site(wing_builds)
    interior_doors = generate_interior_doors(fixture, rects)
    resolved = resolve_entrance(fixture, rects, site.footprint, site.wings)
    if resolved is None:
        return RealizerRefusal("NO_ENTRANCE", "no zone with an ALLOWED_ENTRANCE role fronts the "
                                               "street")
    entrance_zone_id, low, high = resolved
    ex = (low + high) // 2
    entrance = build_entrance(site.footprint, ex)
    entrance_door = build_entrance_door(entrance, site.footprint, entrance_zone_id, site.wings)
    windows = generate_windows(fixture, rects, site.footprint, site.wings)
    furniture = check_furniture_feasibility(fixture, rects, walls)

    report = validate(fixture, rects, walls, interior_doors, entrance_door, windows, furniture, site,
                       wet_rooms=layout.wet_rooms, constraint=safe_room_constraint)

    group_geometry: dict[str, MergedGeometry] = {}
    for group_id, cell_ids in groups.items():
        merged = _merged_geometry([rects[c] for c in cell_ids])
        if merged is not None:
            net_area = round(sum(net_rect_m(c, rects[c], walls)[2] for c in cell_ids), 4)
            group_geometry[group_id] = MergedGeometry(
                merged.polygon_m, merged.bbox_m, merged.gross_area_m2, net_area, merged.aspect)

    notes: list[str] = []
    if groups:
        notes.append(
            f"NEEDS-POLYGON-VARIANT: C3/C20/C21 ran at cell granularity for "
            f"{sorted(groups)} — not authoritative for the merged zone; see the redesigned "
            f"GROUP-C2/GROUP-C3/GROUP-C20 checks instead.")

    big_by_group: dict[str, ZoneIntent] = {}
    for wb_intent in layout.wings:
        if isinstance(wb_intent, RowWing):
            for gid, g in wb_intent.groups.items():
                big_by_group[g.big.zone_id] = g.big
    group_check_list: list[Check] = []
    for group_id, cell_ids in groups.items():
        group_check_list.extend(_group_checks(group_id, cell_ids, rects, walls,
                                                big_by_group[group_id]))

    displayed_rows, c27 = _displayed_rows(fixture, rects, walls, groups, group_geometry)

    design = assemble_design(fixture, rects, walls, 1, interior_doors, entrance_door, windows,
                              furniture, site, wet_rooms=layout.wet_rooms)

    ok = report.ok and c27.passed and all(c.passed for c in group_check_list)
    if not ok:
        failing = [c for c in report.checks if not c.passed]
        failing += [c for c in group_check_list if not c.passed]
        if not c27.passed:
            failing.append(c27)
        detail = "; ".join(f"{c.check_id}: {c.detail}" for c in failing[:5])
        return RealizerRefusal("VALIDATION_FAILED", detail or "one or more checks failed")

    for c in group_check_list:
        report.checks.append(c)

    return RealizedLayout(
        name=layout.name, fixture=fixture, rects=rects, walls=walls, site=site,
        interior_doors=interior_doors, entrance_door=entrance_door, windows=windows,
        furniture=furniture, report=report, c27=c27, design=design, zone_of_cell=zone_of_cell,
        groups=group_geometry, wall_time_s=time.monotonic() - t0, notes=notes,
    )
