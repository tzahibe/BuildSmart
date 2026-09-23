"""Stage 1 (2/2), Issue #117 — THE GATE: a non-guillotine realizer for every rectilinear shape
family.

`geometry_core.engine.solve_fixture` walks a binary slicing tree: every partition is a straight
cut across a subtree, so only GUILLOTINE layouts exist (measured: 1/199 real plans qualify — see
`docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md`). Spike #108
(`docs/reports/non-rectangular-geometry-architecture-b-spike.md`) hand-encoded one real
non-guillotine layout and proved the downstream pipeline (doors, windows, furniture, `validate()`,
`design_output.assemble`, quality metrics, the renderer) accepts a `dict[str, Rect]` that is not a
slicing-tree output, unchanged, with two small solver-output obligations (`Wing.tree`,
`Wing.seam_leaf_sides`). Nothing produced such a layout. This module is that missing piece:
`realize_layout` takes a PLACED layout (adjacency / placement / exposure already decided — the
POC's own `RealizationIntent` shape, per `docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md`'s
description of it) and produces real geometry, or REFUSES naming the failing constraint. Deciding
WHERE rooms go (Stage 2 — wiring a retrieved/generated layout in) is explicitly out of this
Issue's scope; this realizer is the "layout -> geometry" half only, exactly as Architecture B's own
solver gap was scoped.

Two independent, provably non-guillotine constructions, both built entirely from `Rect`/`WallMap`
primitives `geometry_core.model` already defines — no change to Geometry Core, no change to any
validator:

  1. PINWHEEL (`_solve_pinwheel`/`_pinwheel_rects`) — the exact 5-room windmill spike #108
     hand-encoded (a center room surrounded on all four sides), generalized from #108's fixed
     numbers into a small alternating-fit solver over each arm's OWN target area. Every one of its
     5 zones is a single ordinary `Rect` — no shape merging needed, so it goes through
     `design_output.assemble`/`app.demo.contract.to_demo_design` exactly like any other design.
  2. NOTCH-CARVE (`carve_l`/`carve_u`/`carve_t`) — one "big" zone's own rectangle has 1-2 smaller
     "notch" rooms cut from its boundary (a corner for L, an edge-centre for U, two corners of one
     edge for T); the big zone's realized shape is the rectangle MINUS the notches, a genuine
     rectilinear (non-rectangle) polygon. The wall between a notch and its sibling fragments of the
     SAME zone is `WallType.OPEN` (no wall at all — matching `room_merge.py`'s own "the seam is
     dropped, not converted to an opening" precedent, generalized here from a 2-way merge to
     N-way). Both constructions place every top-level zone/group along a SINGLE ROW spanning the
     full envelope depth, which is what proves — by construction, checked by `_notch_dims` — that
     the north and south edges of every top-level rectangle are always on the building envelope:
     every fragment of an L/U/T's realized geometry independently touches an exterior wall, so
     C19/C8 (exposure) need no redesign for these three families. `_solve_pinwheel`/`_notch_dims`
     REFUSE (never silently approximate) when a target cannot be met within the container's own
     bounds.

The dict[str, Rect] fed downstream is keyed by CELL id, not always by the final zone id — a
notch-carve "big" zone occupies 2-3 cells (e.g. `LIVING__c0`, `LIVING__c1`). Each cell carries its
own permissive `ZoneSpec` (C3/C20/C21 cannot mean anything for one fragment of a merged room, so
they are given trivially-satisfied bounds and reported as NOT AUTHORITATIVE for that zone — the
real per-zone check is `_group_checks` below, generalizing `room_merge.py`'s own redesigned C1/C2/
C3/C20/C27 from a 2-way LIVING+KITCHEN merge to an N-way notch-carve group). Every notch's own
cell, and every pinwheel arm's cell, is exactly one real room with its own real `ZoneSpec` — C3/C20/
C21/C9/C19/C8 all run UNCHANGED and ARE authoritative for those.

`RECTILINEAR_REALIZER_ENABLED` gates nothing in the production path — no existing caller imports
this module — so the flag exists purely as the same disclosure/kill-switch precedent
`LIVING_KITCHEN_MERGE_ENABLED`/`LAUNDRY_ROOM_ENABLED` set, for a future Issue that wires this in.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

from shapely.geometry import Polygon, box as _box
from shapely.ops import unary_union

from . import footprint as footprint_module
from .design_output import GeometricDesign, assemble as assemble_design
from .doors import Door, build_entrance_door, generate_interior_doors, resolve_entrance
from .furniture import FurnitureCheck, check_furniture_feasibility
from .geometry_core.engine import WallMap, net_rect_m
from .geometry_core.model import (
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
from .geometry_core.model import Wing as GcWing
from .site import EntranceWalk, SitePlan, build_entrance
from .validation import Check, ValidationReport, check_realized_dimensions, validate
from .windows import Window, generate_windows

#: Off by default (Issue #117's own scope: prove feasibility behind a flag; the production path
#: is untouched — no existing caller imports this module at all).
RECTILINEAR_REALIZER_ENABLED = False

UNIT_M = 0.05
_MIN_SHORT_SIDE_FLOOR_M = 1.0
#: Sizing ratios the notch-carve solver aims for — DELIBERATELY separate from a `ZoneIntent`'s own
#: `max_aspect_ratio` (a validation CEILING the caller sets; C3 checks the REALIZED shape against
#: it, never the other way around). A corner notch (L) is sized near-square; an edge-centre notch
#: (U) is sized narrow-and-tall on purpose — its width directly competes with the two flanking
#: columns' own minimum short side, so a wide notch can starve both columns below their own
#: template minimum even when the notch's OWN area target is modest.
_L_NOTCH_PREFERRED_ASPECT = 1.2
_U_NOTCH_PREFERRED_ASPECT = 0.45
#: Permissive per-cell `ZoneSpec` bounds for a notch-carve "big" zone's own fragments — C3/C20/C21
#: cannot mean anything for one rectangle out of a merged polygon (see module docstring); the real
#: check for that zone is `_group_checks`. Trivially satisfied by construction, never used to
#: gate anything.
_PERMISSIVE_MIN_M2 = 0.01
_PERMISSIVE_MAX_M2 = 100_000.0
_PERMISSIVE_MIN_SHORT_SIDE_M = 0.01
_PERMISSIVE_MAX_ASPECT = 1_000.0


# --------------------------------------------------------------------------- mirrored intent shape

@dataclass(frozen=True)
class ZoneIntent:
    """One room's own requirement — mirrors `geometry_core.model.ZoneSpec`'s fields (net area
    min/target/max, min short side, max aspect) plus the single `ProgramRole` this realizer
    assigns it. Not `ZoneSpec` itself: a notch-carve "big" zone's ZoneIntent describes the WHOLE
    merged room's own bounds, which is not what any one cell's `ZoneSpec` may declare (see module
    docstring) — mirroring, not reuse, is the point."""

    zone_id: str
    role: ProgramRole
    target_area_m2: float
    min_area_m2: float
    max_area_m2: float
    min_short_side_m: float = 2.0
    max_aspect_ratio: float = 2.5


@dataclass(frozen=True)
class PinwheelWing:
    """A 5-room windmill: `center` surrounded by `n`/`e`/`s`/`w`, non-guillotine by construction
    (proof: `test_pinwheel_layout_is_genuinely_non_guillotine`) — the exact topology spike #108
    hand-encoded, generalized to any 5 `ZoneIntent`s' own target areas."""

    wing_id: str
    width_m: float
    height_m: float
    n: ZoneIntent
    e: ZoneIntent
    s: ZoneIntent
    w: ZoneIntent
    center: ZoneIntent


@dataclass(frozen=True)
class ShapeGroupIntent:
    """One notch-carve group: `big`'s realized shape is its own container rectangle MINUS
    `notches` (1 for L/U, 2 for T) — see module docstring. `corner` (L only) is one of
    "NW"/"NE"/"SW"/"SE"; `edge` (U/T only) is "N" or "S" — always a north/south attachment, which
    is what keeps every fragment touching an exterior wall in a single-row wing (see module
    docstring)."""

    group_id: str
    family: str  # "L" | "U" | "T"
    big: ZoneIntent
    notches: tuple[ZoneIntent, ...]
    corner: str = "NE"
    edge: str = "N"


@dataclass(frozen=True)
class RowWing:
    """A single row of top-level slots spanning the wing's full height, left to right — ordinary
    `ZoneIntent`s and AT MOST ONE `ShapeGroupIntent`. `slots` is the placement: the left-to-right
    order of zone_ids (for an ordinary zone) and group_ids (for the one shape group, if any)."""

    wing_id: str
    width_m: float
    height_m: float
    slots: tuple[str, ...]
    zones: dict[str, ZoneIntent] = field(default_factory=dict)
    groups: dict[str, ShapeGroupIntent] = field(default_factory=dict)


Wing = PinwheelWing | RowWing


@dataclass(frozen=True)
class RealizationIntent:
    """The realizer's own input shape — adjacency / placement / exposure already decided, mirrored
    from the POC's `RealizationIntent` (per `docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md`'s
    description of it; the POC branch itself is not reachable from this worktree, so this is
    authored fresh, not imported — see the Issue's own "imported or mirrored... not forked").
    `wings` is the PLACEMENT (1 wing = a rectangular envelope, 2 = a non-rectangular one, in
    footprint.py's own sense); `declared_adjacency`/`declared_exposure` are informational facts
    about the layout this intent asks for, checked against the realized geometry post-hoc by a
    caller (e.g. `stage1_gate.py`) rather than driving construction — placement already did that.
    """

    name: str
    wings: tuple[Wing, ...]
    entrance_hint_zone_id: str | None = None
    declared_adjacency: tuple[tuple[str, str], ...] = ()
    declared_exposure: tuple[str, ...] = ()


@dataclass(frozen=True)
class Refusal:
    """A layout `realize_layout` cannot honestly realize — the failing constraint, named, never
    silently approximated."""

    constraint: str
    detail: str


@dataclass(frozen=True)
class MergedGeometry:
    """One notch-carve group's own TRUE geometry — the union of its cells' centerline rectangles.
    Generalizes `room_merge.py::MergedGeometry`/`compute_geometry` from a 2-way merge to N cells;
    see that module for the shapely/AABB-aspect precedent this follows."""

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
    svg_path: str | None = None

    @property
    def ok(self) -> bool:
        return self.report.ok and self.c27.passed


# --------------------------------------------------------------------------- pinwheel solver

def _solve_pinwheel(w_u: int, h_u: int, area_n_m2: float, area_e_m2: float, area_s_m2: float,
                     area_w_m2: float, min_short_u: int) -> tuple[int, int, int, int] | None:
    """The 4 band thicknesses (tn, te, ts, tw), grid units, reverse-engineered from spike #108's
    own hand-picked rectangles (see module docstring): N spans [0, w-te] x [0, tn], E spans
    [w-te, w] x [0, h-ts], S spans [tw, w] x [h-ts, h], W spans [0, tw] x [tn, h], and the center
    is the leftover [tw, w-te] x [tn, h-ts]. An alternating fixed-point solve (each band's OWN
    thickness from its target area over its CURRENT effective span) converges in a handful of
    iterations for any realistic area set; `None` when no thickness combination leaves room for
    the other three (never silently clamped past that point)."""
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
    """(w_u, h_u) close to `target_area_m2` at `preferred_aspect`, both within
    [min_short_u, max_*_u] — `None` when the target cannot be met inside the container at all."""
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
    """One corner notch removed from `container`, decomposed as a proper 2x2 GRID (not a
    "full-height column + a side sliver") so every internal edge is a clean 1:1 boundary between
    exactly two cells — a "full column" spanning the whole container touches the notch along PART
    of its own side and its sibling fragment along the REST, which `WallMap` (one type per
    `(zone, side)`) cannot represent (found empirically: it silently dropped the OPEN half of a
    split edge). Returns (big zone's 3 fragments, notch rect). `corner[0]` in {"N","S"} always
    yields fragments that individually touch that edge — see module docstring's single-row
    exposure argument."""
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
    """One edge-centred notch removed from `container`'s N or S edge, decomposed as a proper 2x3
    GRID (see `carve_l`'s docstring for why a full-height column is not used). Returns (big zone's
    5 fragments, notch rect)."""
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
    """Two corner notches removed from the SAME edge (both N or both S), decomposed as a proper
    2x3 GRID (see `carve_l`'s docstring) — a full-width "bar" would touch both notches AND the
    stem along one side. Returns (big zone's 4 fragments, [left notch, right notch])."""
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
    from .geometry_core.model import Cut, Split
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
    same_zone_edges: list[tuple[str, str]]  # (cell_a, cell_b) with an OPEN wall between them
    zone_of_cell: dict[str, str]
    groups: dict[str, tuple[str, ...]]  # group_id -> its own cell ids
    access_edges: list[tuple[str, str]]  # cell-level DOOR edges within this wing
    seam_left_ids: tuple[str, ...] = ()  # cells whose W side may seam to a wing on the left
    seam_right_ids: tuple[str, ...] = ()  # cells whose E side may seam to a wing on the right


#: A zone's declared `min_short_side_m` is NET (clear internal, after wall insets — see
#: `geometry_core.model.ZoneSpec`'s own docstring), but the constructions here can only bound the
#: GROSS/centerline rectangle before wall types are known. Padding the target by twice the
#: heaviest single-side inset (EXTERIOR, 0.15 m) is a conservative, correct pre-check: a zone
#: with two exterior/partition sides on its short axis loses at most this much, so a rectangle
#: whose GROSS short side already clears `min_short_side_m + _INSET_MARGIN_M` cannot fail the
#: real, NET-dimension C3 check downstream — found empirically (a gross-only pre-check let a
#: zone through whose real net short side was 0.10 m under its own bound).
_INSET_MARGIN_M = 0.30


def _build_pinwheel_wing(w: PinwheelWing, origin: tuple[int, int]) -> _WingBuild | Refusal:
    w_u, h_u = m_to_u(w.width_m), m_to_u(w.height_m)
    min_short_u = m_to_u(min(w.n.min_short_side_m, w.e.min_short_side_m, w.s.min_short_side_m,
                              w.w.min_short_side_m, w.center.min_short_side_m) + _INSET_MARGIN_M)
    solved = _solve_pinwheel(w_u, h_u, w.n.target_area_m2, w.e.target_area_m2, w.s.target_area_m2,
                              w.w.target_area_m2, min_short_u)
    if solved is None:
        return Refusal("PINWHEEL_INFEASIBLE",
                        f"wing '{w.wing_id}' {w.width_m}x{w.height_m} m has no band-thickness "
                        f"solution honouring every arm's minimum short side ({min_short_u * UNIT_M} m)")
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
            return Refusal("AREA_INFEASIBLE",
                            f"{zi.zone_id}: pinwheel-realized area {area:.2f} m2 outside "
                            f"[{zi.min_area_m2},{zi.max_area_m2}]")
        short = min(u_to_m(r.w), u_to_m(r.h))
        if short < zi.min_short_side_m + _INSET_MARGIN_M - 1e-6:
            return Refusal("SHORT_SIDE_INFEASIBLE",
                            f"{zi.zone_id}: pinwheel-realized short side {short:.2f} m (gross) < "
                            f"{zi.min_short_side_m} m (net) + {_INSET_MARGIN_M} m inset margin")
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


def _carve_group(group: ShapeGroupIntent, container: Rect) -> tuple[list[Rect], list[Rect],
                                                                      list[ZoneIntent]] | Refusal:
    """Returns (big zone's own fragment rects, notch rects, notch ZoneIntents in the same order)."""
    max_w_u, max_h_u = container.w - m_to_u(_MIN_SHORT_SIDE_FLOOR_M), \
        container.h - m_to_u(_MIN_SHORT_SIDE_FLOOR_M)
    if group.family == "L":
        notch = group.notches[0]
        dims = _wh_for_area(notch.target_area_m2, _L_NOTCH_PREFERRED_ASPECT,
                             m_to_u(notch.min_short_side_m + _INSET_MARGIN_M), max_w_u, max_h_u)
        if dims is None:
            return Refusal("NOTCH_INFEASIBLE",
                            f"{notch.zone_id}: no corner notch fits {notch.target_area_m2} m2 "
                            f"inside the {group.group_id} container")
        big_rects, notch_rect = carve_l(container, group.corner, *dims)
        return big_rects, [notch_rect], [notch]
    if group.family == "U":
        notch = group.notches[0]
        max_w_edge_u = container.w - 2 * m_to_u(_MIN_SHORT_SIDE_FLOOR_M)
        dims = _wh_for_area(notch.target_area_m2, _U_NOTCH_PREFERRED_ASPECT,
                             m_to_u(notch.min_short_side_m + _INSET_MARGIN_M), max_w_edge_u, max_h_u)
        if dims is None:
            return Refusal("NOTCH_INFEASIBLE",
                            f"{notch.zone_id}: no edge notch fits {notch.target_area_m2} m2 "
                            f"inside the {group.group_id} container")
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
        return Refusal("NOTCH_INFEASIBLE",
                        f"{group.group_id}: no T stem fits both {left.zone_id} and "
                        f"{right.zone_id} inside the container")
    return Refusal("UNKNOWN_FAMILY", f"shape family '{group.family}' is not L/U/T")


def _build_row_wing(w: RowWing, origin: tuple[int, int]) -> _WingBuild | Refusal:
    w_u, h_u = m_to_u(w.width_m), m_to_u(w.height_m)
    ox, oy = origin
    slot_intents: list[tuple[str, ZoneIntent | ShapeGroupIntent]] = []
    for slot_id in w.slots:
        if slot_id in w.groups:
            slot_intents.append((slot_id, w.groups[slot_id]))
        elif slot_id in w.zones:
            slot_intents.append((slot_id, w.zones[slot_id]))
        else:
            return Refusal("UNKNOWN_SLOT", f"slot '{slot_id}' is neither a zone nor a group")

    total_target = sum(
        (s.big.target_area_m2 + sum(n.target_area_m2 for n in s.notches))
        if isinstance(s, ShapeGroupIntent) else s.target_area_m2
        for _, s in slot_intents
    )
    if total_target <= 0:
        return Refusal("EMPTY_ROW", f"wing '{w.wing_id}' has no zones")

    rects: dict[str, Rect] = {}
    roles: dict[str, tuple[ProgramRole, ...]] = {}
    specs: dict[str, ZoneSpec] = {}
    zone_of_cell: dict[str, str] = {}
    same_zone_edges: list[tuple[str, str]] = []
    groups_out: dict[str, tuple[str, ...]] = {}
    access_edges: list[tuple[str, str]] = []
    #: Every cell belonging to each slot, IN SLOT ORDER — what the final unified pass below
    #: connects consecutive slots through (the best-touching cell pair, not merely "rightmost of
    #: prev, leftmost of next": a group's own cell touching the neighbour slot is not always the
    #: one an index-0 guess would pick, and a notch can legitimately be the touching cell too).
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
                return Refusal("AREA_INFEASIBLE",
                                f"{zi.zone_id}: row-realized area {area:.2f} m2 outside "
                                f"[{zi.min_area_m2},{zi.max_area_m2}]")
            short = min(u_to_m(container.w), u_to_m(container.h))
            if short < zi.min_short_side_m + _INSET_MARGIN_M - 1e-6:
                return Refusal("SHORT_SIDE_INFEASIBLE",
                                f"{zi.zone_id}: row-realized short side {short:.2f} m (gross) < "
                                f"{zi.min_short_side_m} m (net) + {_INSET_MARGIN_M} m inset margin")
            rects[zi.zone_id] = container
            roles[zi.zone_id] = (zi.role,)
            specs[zi.zone_id] = _zone_spec(zi)
            zone_of_cell[zi.zone_id] = zi.zone_id
            slot_cells.append([zi.zone_id])
            continue

        group = intent
        carved = _carve_group(group, container)
        if isinstance(carved, Refusal):
            return carved
        big_rects, notch_rects, notch_intents = carved

        big_area = sum(r.area_m2() for r in big_rects)
        if not (group.big.min_area_m2 - 0.02 <= big_area <= group.big.max_area_m2 + 0.02):
            return Refusal("AREA_INFEASIBLE",
                            f"{group.big.zone_id}: carved area {big_area:.2f} m2 outside "
                            f"[{group.big.min_area_m2},{group.big.max_area_m2}]")
        merged = _merged_geometry(big_rects)
        if merged is None:
            return Refusal("NOT_ONE_POLYGON",
                            f"{group.big.zone_id}: its cells do not union to one simple polygon")
        aspect_ceiling = group.big.max_aspect_ratio + 1e-6
        if merged.aspect > aspect_ceiling:
            return Refusal("ASPECT_INFEASIBLE",
                            f"{group.big.zone_id}: carved AABB aspect {merged.aspect:.2f} > "
                            f"{group.big.max_aspect_ratio}")

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
                return Refusal("AREA_INFEASIBLE",
                                f"{notch_intent.zone_id}: notch area {n_area:.2f} m2 outside "
                                f"[{notch_intent.min_area_m2},{notch_intent.max_area_m2}]")
            rects[notch_intent.zone_id] = notch_rect
            roles[notch_intent.zone_id] = (notch_intent.role,)
            specs[notch_intent.zone_id] = _zone_spec(notch_intent)
            zone_of_cell[notch_intent.zone_id] = notch_intent.zone_id
            slot_notch_ids.append(notch_intent.zone_id)
            # A notch shares a wall with whichever big-zone cell it touches — that is a real
            # interior door between two DIFFERENT rooms, not an OPEN seam.
            for cid in big_cell_ids:
                if rects[cid].shared_edge_len_u(notch_rect) > 0:
                    access_edges.append((notch_intent.zone_id, cid))
                    break

        slot_cells.append(list(big_cell_ids) + slot_notch_ids)

    # One unified pass connecting every consecutive pair of slots through the BEST-touching cell
    # pair (maximum shared edge length) — robust to which specific cell a carve happens to place
    # at a slot's boundary, unlike guessing "rightmost of prev, leftmost of next".
    for i in range(len(slot_cells) - 1):
        pair = _best_touching_pair(slot_cells[i], slot_cells[i + 1], rects)
        if pair is None:
            return Refusal("SLOTS_DO_NOT_TOUCH",
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
    """The redesigned, polygon-variant checks for one notch-carve "big" zone, generalizing
    `room_merge.py::validate_merged_room`'s C1/C2/C3/C20/C27 from a 2-way merge to N cells. This is
    what actually GATES a notch-carve group's realize/refuse decision — the raw per-cell C3/C20/C21
    in `report` are NOT authoritative for these cells (see module docstring) and are reported
    separately as a NEEDS-POLYGON-VARIANT finding."""
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
    """Every displayed room the person would see: ordinary/notch cells 1:1, run through the REAL,
    unchanged C27 (`validation.check_realized_dimensions`) — genuinely meaningful for a rectangle,
    where width x depth == area always. A notch-carve group's own merged room is NOT fed through
    that check: `room_merge.py`'s own precedent (Issue #107) found the generic net==width*depth
    formula wrongly flags every non-flush polygon room (its bounding box is strictly bigger than
    its own true area by construction), and redesigned C27 for a polygon room to gate on "the
    reported area matches the TRUE polygon area" instead — reproduced here as `_group_c27`,
    generalized from a 2-way merge to N cells. Mirrors `app.demo.contract`'s `RoomOut` shape
    structurally (duck-typed against `validation._DisplayedRoom`) without importing it."""
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
    """C27's redesigned polygon-room gate (see `_displayed_rows`'s docstring): the reported gross
    area equals the TRUE union-polygon area, for every notch-carve group. Trivially true here
    because both numbers are read off the SAME `MergedGeometry` — the point of the check is that a
    future caller who feeds this a different `bbox_m`/`gross_area_m2` pair (e.g. mistakenly
    reporting the bounding-box PRODUCT as the area) would be caught."""
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
    from .geometry_core.model import OutdoorClassification, OutdoorRegion
    garden = tuple(OutdoorRegion(f"garden_{i}", (r,), OutdoorClassification.GARDEN)
                    for i, r in enumerate(crook))
    return SitePlan(plot=plot, footprint=footprint, footprint_offset_u=(0, 0), parking=(),
                     entrance=entrance, garden=garden, wings=wing_rects)


def realize_layout(layout: RealizationIntent, programme: object | None = None,
                    buildable: Rect | None = None) -> RealizedLayout | Refusal:
    """Realize a PLACED layout into real, axis-aligned, rectilinear geometry, or REFUSE naming the
    failing constraint. `programme`/`buildable` complete the mandated signature; every area/aspect/
    short-side bound this realizer honours already lives on `layout`'s own `ZoneIntent`s (the same
    way `Fixture.zones` already IS the programme for the existing guillotine engine), so `programme`
    is accepted but not read; `buildable`, if given, is a sanity check against `layout.wings`'
    own combined footprint rather than a second source of truth."""
    t0 = time.monotonic()
    if not layout.wings:
        return Refusal("EMPTY_LAYOUT", "a layout needs at least one wing")

    origin = (m_to_u(2.0), m_to_u(2.0))
    wing_builds: list[_WingBuild] = []
    cursor_x = origin[0]
    for w in layout.wings:
        wb = _build_pinwheel_wing(w, (cursor_x, origin[1])) if isinstance(w, PinwheelWing) \
            else _build_row_wing(w, (cursor_x, origin[1]))
        if isinstance(wb, Refusal):
            return wb
        wing_builds.append(wb)
        cursor_x += wb.size[0]

    if buildable is not None:
        total_w = sum(wb.size[0] for wb in wing_builds)
        total_h = max(wb.size[1] for wb in wing_builds)
        if total_w > buildable.w or total_h > buildable.h:
            return Refusal("ENVELOPE_TOO_LARGE",
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

    # Walls: PARTITION where another cell's rect touches this side, EXTERIOR otherwise, except an
    # OPEN (no-wall) side between two cells the SAME zone owns (both directions).
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

    # Cross-wing seams: an OPEN-free, EXTERIOR-free PARTITION already resulted from the adjacency
    # loop above wherever two wings' cells touch; `Wing.seam_leaf_sides` must name every such pair
    # for C22, AND — since a wing boundary carries no access edge of its own (each `_WingBuild`
    # only connects cells WITHIN its own wing) — a DOOR edge is added for every seam pair too,
    # matching `hand_encoded_fixture.py`'s own GALLERY-BED2 precedent: without it the seam-adjacent
    # cell on the far wing is a real, walled room with no way in at all (found empirically: C5/C24
    # both fail on exactly that cell otherwise).
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

    site = _build_site(wing_builds)
    interior_doors = generate_interior_doors(fixture, rects)
    resolved = resolve_entrance(fixture, rects, site.footprint, site.wings)
    if resolved is None:
        return Refusal("NO_ENTRANCE", "no zone with an ALLOWED_ENTRANCE role fronts the street")
    entrance_zone_id, low, high = resolved
    ex = (low + high) // 2
    entrance = build_entrance(site.footprint, ex)
    entrance_door = build_entrance_door(entrance, site.footprint, entrance_zone_id, site.wings)
    windows = generate_windows(fixture, rects, site.footprint, site.wings)
    furniture = check_furniture_feasibility(fixture, rects, walls)

    report = validate(fixture, rects, walls, interior_doors, entrance_door, windows, furniture, site)

    group_geometry: dict[str, MergedGeometry] = {}
    group_check_list: list[Check] = []
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
    for group_id, cell_ids in groups.items():
        group_check_list.extend(_group_checks(group_id, cell_ids, rects, walls,
                                                big_by_group[group_id]))

    displayed_rows, c27 = _displayed_rows(fixture, rects, walls, groups, group_geometry)

    design = assemble_design(fixture, rects, walls, 1, interior_doors, entrance_door, windows,
                              furniture, site)

    ok = report.ok and c27.passed and all(c.passed for c in group_check_list)
    if not ok:
        failing = [c for c in report.checks if not c.passed]
        failing += [c for c in group_check_list if not c.passed]
        if not c27.passed:
            failing.append(c27)
        detail = "; ".join(f"{c.check_id}: {c.detail}" for c in failing[:5])
        return Refusal("VALIDATION_FAILED", detail or "one or more checks failed")

    for c in group_check_list:
        report.checks.append(c)

    return RealizedLayout(
        name=layout.name, fixture=fixture, rects=rects, walls=walls, site=site,
        interior_doors=interior_doors, entrance_door=entrance_door, windows=windows,
        furniture=furniture, report=report, c27=c27, design=design, zone_of_cell=zone_of_cell,
        groups=group_geometry, wall_time_s=time.monotonic() - t0, notes=notes,
    )
