"""R1 (#242) — the realizer entry the experiment drives, and the verdict on one run.

`rectilinear_realizer.realize_cells` is the shape-agnostic entry, but it declares `groups = {}` and
`open_pairs = set()` and says so ("No groups, so no polygon rooms"). Arm 2 needs a room made of
several same-zone cells with an OPEN wall between them, validated on their union through
`_group_checks` — the mechanism `realize_layout` already uses for its notch-carve zones. This
module is `realize_cells` with exactly that, and nothing else: it calls the SAME private helpers
(`_side_between`, `_group_checks`, `_displayed_rows`, `_filter_wet_room_access`, `_build_site`),
the SAME `validate`, `generate_interior_doors`, `resolve_entrance`, `generate_windows`,
`check_furniture_feasibility` and `assemble`, and gates on the SAME three terms
(`report.ok and c27.passed and all group checks`). With no groups it must agree with
`realize_cells` on every layout — `test_wrapper_agrees_with_realize_cells` holds it to that.

What it adds over `realize_cells`: the failing check IDS are returned in full (the real function
joins the first five into a string), so a refusal can be aggregated by check.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

from app.vertical_slice.design_output import assemble as assemble_design
from app.vertical_slice.doors import build_entrance_door, generate_interior_doors, resolve_entrance
from app.vertical_slice.furniture import check_furniture_feasibility
from app.vertical_slice.geometry_core.engine import WallMap, net_rect_m
from app.vertical_slice.geometry_core.model import (
    ConnectionKind,
    DesiredAccessEdge,
    DesiredAccessTopology,
    Fixture,
    ProgramRole,
    Rect,
    Side,
    WallType,
    ZoneSpec,
    m_to_u,
)
from app.vertical_slice.geometry_core.model import Wing as GcWing
from app.vertical_slice.rectilinear_realizer import (
    MergedGeometry,
    ZoneIntent,
    _build_site,
    _displayed_rows,
    _filter_wet_room_access,
    _group_checks,
    _leaf_chain,
    _merged_geometry,
    _permissive_spec,
    _side_between,
    _WingBuild,
)
from app.vertical_slice.site import build_entrance
from app.vertical_slice.spec import WetRoomKind, WetRoomStrength
from app.vertical_slice.validation import Check, validate
from app.vertical_slice.wet_rooms import ResolvedWetRoom
from app.vertical_slice.windows import generate_windows

from .convert import Layout


@dataclass
class Outcome:
    carried: bool
    #: set when the run stopped BEFORE validation (no entrance, a cell outside the wings, ...)
    code: str | None = None
    #: every failing check id, group-check ids stripped of their zone (`GROUP-C3:LIVING_0` -> `GROUP-C3`)
    failing: tuple[str, ...] = ()
    #: check id -> its detail text, for the report
    details: dict[str, str] = field(default_factory=dict)
    n_checks: int = 0


def _norm(check_id: str) -> str:
    return check_id.split(":", 1)[0]


def _wet_rooms(layout: Layout, cells_of: dict[str, list[str]],
               wanted: list[tuple[str, str]]) -> tuple[ResolvedWetRoom, ...]:
    """The declared kind of every wet ZONE, expanded to its cells (a wet room of several cells
    declares each of them with the zone's kind; an ensuite's host is the host cell the door lands
    on, else the host zone's first cell). Zone ids == cell ids for a single-cell room."""
    out: list[ResolvedWetRoom] = []
    zone_of = layout.zone_of_cell
    for zone, (kind, host_zone) in sorted(layout.wet.items()):
        for c in sorted(cells_of.get(zone, [])):
            host = None
            if kind is WetRoomKind.ENSUITE and host_zone is not None:
                host = next((hb for ca, cb in wanted for wc, hb in ((ca, cb), (cb, ca))
                             if zone_of[wc] == zone and zone_of[hb] == host_zone), None)
                if host is None:
                    host = sorted(cells_of.get(host_zone, [host_zone]))[0]
            out.append(ResolvedWetRoom(c, kind, host, WetRoomStrength.REQUIRED, True))
    return tuple(out)


def realize(name: str, layout: Layout, intents: dict[str, ZoneIntent]) -> Outcome:
    """`intents` is keyed by ZONE id (a room), as the product's `ZoneIntent`s are."""
    rects, groups = layout.cells, layout.groups
    if not rects or not layout.wings:
        return Outcome(False, code="EMPTY_LAYOUT")
    off = m_to_u(2.0)
    rects = {z: Rect(r.x + off, r.y + off, r.w, r.h) for z, r in rects.items()}
    wing_rects = tuple(Rect(r.x + off, r.y + off, r.w, r.h) for r in layout.wings)
    zone_of_cell = layout.zone_of_cell
    grouped = {c for cells in groups.values() for c in cells}
    roles = {c: (intents[zone_of_cell[c]].role,) for c in rects}
    specs: dict[str, ZoneSpec] = {}
    for c in rects:
        i = intents[zone_of_cell[c]]
        specs[c] = (_permissive_spec(c, i.role) if c in grouped else
                    ZoneSpec(c, roles[c], i.min_area_m2, i.target_area_m2, i.max_area_m2,
                             i.min_short_side_m, i.max_aspect_ratio))
    open_pairs: set[frozenset[str]] = set()
    for cells in groups.values():
        for i, a in enumerate(cells):
            for b in cells[i + 1:]:
                if rects[a].shared_edge_len_u(rects[b]) > 0:
                    open_pairs.add(frozenset((a, b)))
    wing_of_cell: dict[str, int] = {}
    for z, r in rects.items():
        for i, w in enumerate(wing_rects):
            if w.x <= r.x and w.y <= r.y and r.x2 <= w.x2 and r.y2 <= w.y2:
                wing_of_cell[z] = i
                break
        else:
            return Outcome(False, code="CELL_OUTSIDE_WINGS")

    walls: WallMap = {}
    safe_ids = {z for z, rs in roles.items() if ProgramRole.SAFE_ROOM in rs}
    touching_all: dict[str, dict[Side, list[str]]] = {}
    for zone_id, rect in rects.items():
        touching: dict[Side, list[str]] = {}
        for other_id, other in rects.items():
            if other_id == zone_id or rect.shared_edge_len_u(other) <= 0:
                continue
            side = _side_between(rect, other)
            if side is not None:
                touching.setdefault(side, []).append(other_id)
        touching_all[zone_id] = touching
        for side in Side:
            others = touching.get(side, [])
            if others and any(frozenset((zone_id, o)) in open_pairs for o in others):
                walls[(zone_id, side)] = WallType.OPEN
            elif zone_id in safe_ids or any(o in safe_ids for o in others):
                walls[(zone_id, side)] = WallType.RC_SAFE_ROOM
            elif others:
                walls[(zone_id, side)] = WallType.PARTITION
            else:
                walls[(zone_id, side)] = WallType.EXTERIOR

    seam_sides: dict[int, list[tuple[str, Side]]] = {i: [] for i in range(len(wing_rects))}
    for zone_id, touching in touching_all.items():
        for side, others in touching.items():
            if any(wing_of_cell[o] != wing_of_cell[zone_id] for o in others):
                seam_sides[wing_of_cell[zone_id]].append((zone_id, side))
    cells_of: dict[str, list[str]] = {}
    for c, z in zone_of_cell.items():
        cells_of.setdefault(z, []).append(c)
    wanted: list[tuple[str, str]] = []
    for a, b in layout.access:
        if a == b or a not in cells_of or b not in cells_of:
            continue
        best = max(((rects[ca].shared_edge_len_u(rects[cb]), ca, cb)
                    for ca in cells_of[a] for cb in cells_of[b]), default=(0, None, None))
        if best[0] > 0:
            wanted.append((best[1], best[2]))
    declared = frozenset(frozenset(p) for p in wanted)
    wet_rooms = _wet_rooms(layout, cells_of, wanted)
    realized_pairs = _filter_wet_room_access(list(wanted), roles, wet_rooms, declared)

    wings_out = []
    for i, w in enumerate(wing_rects):
        zone_ids = tuple(z for z in rects if wing_of_cell[z] == i)
        wings_out.append(GcWing(wing_id=f"W{i}", origin_x_u=w.x, origin_y_u=w.y, w_u=w.w, h_u=w.h,
                                tree=_leaf_chain(zone_ids), seam_leaf_sides=tuple(seam_sides[i])))
    zones = tuple(ZoneSpec(zid, roles[zid], specs[zid].net_area_min_m2, specs[zid].net_area_target_m2,
                           specs[zid].net_area_max_m2, specs[zid].min_short_side_m,
                           specs[zid].max_aspect_ratio) for zid in rects)
    edges = tuple(DesiredAccessEdge(a, b, ConnectionKind.DOOR) for a, b in realized_pairs)
    open_groups = tuple(tuple(sorted(pair)) for pair in open_pairs)
    fixture = Fixture(name, tuple(wings_out), zones, DesiredAccessTopology(edges), open_groups)

    wing_builds = [_WingBuild(f"W{i}", (w.x, w.y), (w.w, w.h), {}, {}, {}, [], {}, {}, [])
                   for i, w in enumerate(wing_rects)]
    site = _build_site(wing_builds)
    interior_doors = generate_interior_doors(fixture, rects)
    resolved = resolve_entrance(fixture, rects, site.footprint, site.wings)
    if resolved is None:
        return Outcome(False, code="NO_ENTRANCE")
    entrance_zone_id, low, high = resolved
    entrance = build_entrance(site.footprint, (low + high) // 2)
    site = dataclasses.replace(site, entrance=entrance)
    entrance_door = build_entrance_door(entrance, site.footprint, entrance_zone_id, site.wings)
    windows = generate_windows(fixture, rects, site.footprint, site.wings)
    furniture = check_furniture_feasibility(fixture, rects, walls)
    report = validate(fixture, rects, walls, interior_doors, entrance_door, windows, furniture, site,
                      wet_rooms=wet_rooms)

    group_geometry: dict[str, MergedGeometry] = {}
    group_checks: list[Check] = []
    for zone_id, cell_ids in groups.items():
        merged = _merged_geometry([rects[c] for c in cell_ids])
        if merged is not None:
            net_area = round(sum(net_rect_m(c, rects[c], walls)[2] for c in cell_ids), 4)
            group_geometry[zone_id] = MergedGeometry(merged.polygon_m, merged.bbox_m,
                                                     merged.gross_area_m2, net_area, merged.aspect)
        group_checks.extend(_group_checks(zone_id, tuple(cell_ids), rects, walls, intents[zone_id]))
    _, c27 = _displayed_rows(fixture, rects, walls, groups, group_geometry)
    # as in `realize_cells`, assembled before the verdict: a plan the downstream cannot assemble is
    # an error, not a quiet refusal
    assemble_design(fixture, rects, walls, 1, interior_doors, entrance_door, windows, furniture, site)

    failing = [c for c in report.checks if not c.passed] + [c for c in group_checks if not c.passed]
    if not c27.passed:
        failing.append(c27)
    n_checks = len(report.checks) + len(group_checks) + 1
    if not (report.ok and c27.passed and all(c.passed for c in group_checks)):
        details: dict[str, str] = {}
        for c in failing:
            details.setdefault(_norm(c.check_id), c.detail)
        return Outcome(False, code="VALIDATION_FAILED", failing=tuple(sorted({_norm(c.check_id) for c in failing})),
                       details=details, n_checks=n_checks)
    return Outcome(True, n_checks=n_checks)
