"""Gate 2 harness — the six frozen cases through ONE code path (ADR-001 §5, #197).

    PYTHONPATH=backend python -m app.ai_harness.shape_agnostic.run <out_dir> [case_id ...]

Per case, the same sequence with no per-case branch anywhere:

    brief + envelope  ->  programme (the brain's own `programme_from_spec`, Stage 3 banding)
                      ->  partis (the brain's own `DeterministicProposer`)
                      ->  representation pre-check (K4 / triple-lens: refused before any geometry)
                      ->  `embed_band` (UNCHANGED; which rooms share a band, in what order)
                      ->  `solve_staircase_layout` inside the envelope polygon (formulation A)
                      ->  `realize_cells` (walls, doors, entrance, windows, UNCHANGED validators)
                      ->  `topology_preservation` + the Stage 3 area verdict

Everything is recorded: status per stage, runtime, the typed refusal when there is one, and a
DemoDesign JSON for every realized plan so the product's own `DemoPlan` draws it. Failures are
reported as what they are; nothing is retried with a relaxed constraint.
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter

from app.ai_harness.shape_agnostic.cells import CIRC as _CELL_CIRC
from app.ai_harness.shape_agnostic.cells import PUBLIC as _CELL_PUBLIC
from app.ai_harness.shape_agnostic.cells import duplicated_layouts, from_bands, moves
from app.ai_harness.shape_agnostic.spine import choose_spine, embed_spine
from app.ai_harness.shape_agnostic.stacks import (
    expand_wings,
    merge_stack,
    propose_stacks,
)
from app.demo.contract import to_demo_design
from app.demo.service import spec_for
from app.vertical_slice.band_embedding import (
    BandEmbeddingRefusal,
    embed_band,
    find_k4,
    find_triple_lens,
)
from app.vertical_slice.band_pipeline import hard_rejections, orient, placement_flags
from app.vertical_slice.band_sizing import contact_requirements
from app.vertical_slice.brain.area import assess_area
from app.vertical_slice.brain.proposer import (
    DeterministicProposer,
    _hall_intent,
    programme_from_spec,
)
from app.vertical_slice.brain.runner import AREA_BAND_LADDER, _arrival_zone, _rebanded
from app.vertical_slice.envelope import Envelope
from app.vertical_slice.rectilinear_realizer import RealizedLayout, realize_cells
from app.vertical_slice.staircase_sizing import solve_staircase_layout
from app.vertical_slice.topology_preservation import (
    measure_access_graph,
    measure_spatial_adjacency,
)

CASES_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "docs", "reports",
                          "shape-agnostic-realizer", "cases", "frozen-six.json")
MAX_CANDIDATES = 150         # embedder candidates examined per parti; the selection + oracle screens are cheap
MAX_SIZINGS = 12             # candidates actually sized per parti (both orientations count)

try:                         # the MILP oracle (formulation B) where scipy exists — research tooling:
    from app.ai_harness.shape_agnostic.milp_cells import (
        cells_placement,
        cells_rects,
        cells_wings,
    )
    from app.ai_harness.shape_agnostic.milp_oracle import (
        milp_heights,
        milp_placement,
        milp_spine_placement,
        placement_rects,
        spine_geometry,
        spine_intents,
    )
except ImportError:          # pragma: no cover
    milp_heights = milp_placement = milp_spine_placement = spine_geometry = spine_intents = placement_rects = None
    cells_placement = cells_rects = cells_wings = None


def _project_for(case: dict):
    from tests.vertical_slice.test_hub_guard import _project
    env = Envelope(tuple(tuple(v) for v in case["envelope"]))
    bw, bd = env.width_u * 0.05, env.depth_u * 0.05
    prog = case["programme"]
    return _project(dict(bedrooms=prog["bedrooms"], wet_rooms=prog["wet_rooms"],
                         safe_room=prog["safe_room"], open_plan=prog.get("open_plan", False),
                         built_area_m2=case["footprint"]["gross_m2"],
                         footprint_width_m=round(bw, 2), footprint_depth_m=round(bd, 2),
                         plot_width_m=round(bw + 8, 2), plot_depth_m=round(bd + 8, 2))), env


def _adjacency(pairs) -> dict[str, set[str]]:
    adj: dict[str, set[str]] = {}
    for a, b in pairs:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    return adj


def _extra(case: dict, kind: str, zones: dict) -> list[tuple[str, str]]:
    """The case's own extra contacts/doors, by ROLE name, mapped onto this programme's zone ids —
    the first zone of each role. Written in the frozen spec before any code; a role the programme
    does not carry is reported, never silently dropped."""
    by_role: dict[str, str] = {}
    for zid, zi in zones.items():
        by_role.setdefault(zi.role.name, zid)
    out = []
    for a, b in case.get(kind, []):
        if a not in by_role or b not in by_role:
            raise InvalidCase(f"{kind} names a role this programme does not carry: {a}-{b} "
                              f"(programme roles: {sorted(by_role)})")
        out.append((by_role[a], by_role[b]))
    return out


class InvalidCase(Exception):
    """The frozen spec asks for something the brief's own programme cannot express. Reported as
    such — never silently dropped, which is how a K4 once collapsed into a triangle and 'solved'."""


def _transposed_envelope(env: Envelope) -> Envelope:
    return Envelope(tuple((y, x) for x, y in env.vertices_m))


def _transpose_rects(rects: dict) -> dict:
    from app.vertical_slice.geometry_core.model import Rect
    return {z: Rect(r.y, r.x, r.h, r.w) for z, r in rects.items()}


#: "area" (Gate 3: grow habitable rooms, width x mid-height proxy) or "target" (A1: exact net areas
#: track the programme targets, circulation overshoot penalised). Set SHAPE_AGNOSTIC_OBJECTIVE.
OBJECTIVE = os.environ.get("SHAPE_AGNOSTIC_OBJECTIVE", "area")
SPINE_MAX_LAYOUTS = 40
#: stacks (the 2D wing's minimal form): how many (pair, order) options a proposal tries
STACK_MAX_OPTIONS = 6
#: cross-band cells (#200): which zones are tried two rows deep, layouts per zone, budgets
CELLS_MAX_LAYOUTS = 24
CELLS_MAX_PARTITIONS = 8
CELLS_BUDGET_S = 60.0
CELLS_K = 6
#: moves (`cells.moves`) are applied to this many band candidates that pass the SELECTION screen
CELLS_MOVE_SEEDS = 12
STACK_BUDGET_S = 60.0
SPINE_BUDGET_S = 90.0


def _dump_design(case: dict, prop, best, out_dir: str, family: str) -> None:
    plan, out = best
    design = to_demo_design(out.design, out.report, family=f"spike:{family}:{prop.name}",
                            notes=[f"{case['id']} — {prop.name} ({family}); {plan['area']} {plan['gross_pct']}%"])
    path = os.path.join(out_dir, "designs", f"{case['id']}__{prop.name}__{family}.json")
    with open(path, "w") as fh:
        json.dump(design.model_dump(mode="json"), fh)
    plan["render"] = os.path.basename(path)


def _proportions(out, intents: dict) -> dict:
    """Proportion metrics of a realized plan: mean relative |net - target| over habitable rooms,
    circulation share of the net area, and the smallest bedroom as a share of its target."""
    from app.vertical_slice.geometry_core.model import ProgramRole
    circ = {ProgramRole.HALL.value, ProgramRole.CIRCULATION.value}
    devs, beds, circ_net, total = [], [], 0.0, 0.0
    for r in out.design.rooms:
        z = intents.get(r.zone_id)
        total += r.net_area_m2
        if z is None:
            continue
        if set(r.roles) & circ:
            circ_net += r.net_area_m2
            continue
        if z.target_area_m2 > 0:
            devs.append(abs(r.net_area_m2 - z.target_area_m2) / z.target_area_m2)
        if ProgramRole.BEDROOM.value in r.roles or ProgramRole.MASTER_BEDROOM.value in r.roles:
            beds.append(r.net_area_m2 / z.target_area_m2 if z.target_area_m2 else 1.0)
    return {"room_dev_pct": round(100 * sum(devs) / len(devs), 1) if devs else None,
            "circ_pct": round(100 * circ_net / total, 1) if total else None,
            "min_bed_pct": round(100 * min(beds), 1) if beds else None}


def _stack_family(case, prop, zones, p, union, spatial, access, orientations, requested, rec):
    """The 2D wing, minimal form (`stacks.py`): the band pipeline run with two small rooms merged
    into one column for the embedding and the screens, expanded into their own heights by the
    exact sizer, realized as ordinary cells with the column as its own wing. Plans tagged
    family="stack"; the first plan that counts is returned with its realization."""
    t0 = time.monotonic()
    reasons: Counter = Counter()
    # one pair per tier (both orders), wet -> public -> bedrooms, within the option cap
    from app.ai_harness.shape_agnostic.stacks import _tier
    options, seen_tiers = [], {}
    for a, b in propose_stacks(zones, union):
        t = _tier(zones[a].role)
        if seen_tiers.setdefault(t, frozenset((a, b))) != frozenset((a, b)):
            continue
        options.append((a, b))
    options = options[:STACK_MAX_OPTIONS]
    if not options:
        return None
    union_m = sorted({tuple(sorted(e)) for e in spatial} | {tuple(sorted(e)) for e in access})
    contacts_m = contact_requirements(zones, union_m, access)
    best = None
    sized = 0
    for stack in options:
        if time.monotonic() - t0 > STACK_BUDGET_S or sized >= MAX_SIZINGS:
            break
        z2, e2, a2, pid = merge_stack(zones, spatial, access, stack)
        union2 = sorted({tuple(sorted(e)) for e in e2} | {tuple(sorted(e)) for e in a2})
        adj = _adjacency(union2)
        if find_k4(adj) or find_triple_lens(adj):
            reasons["STACK_REPRESENTATION"] += 1
            continue
        emb = embed_band(z2, union2, max_candidates=MAX_CANDIDATES)
        if isinstance(emb, BandEmbeddingRefusal):
            reasons[f"STACK_EMBEDDING_{emb.code}"] += 1
            continue
        rec["stages"]["STACK_CANDIDATES"] += len(emb.candidates)
        for cand in emb.candidates:
            if time.monotonic() - t0 > STACK_BUDGET_S or sized >= MAX_SIZINGS:
                break
            flags = placement_flags(cand, z2, p.resolved_wet, tuple(a2))
            rejected = hard_rejections(flags)
            if rejected:
                for k in rejected:
                    reasons[f"STACK_SELECTION_{k}"] += 1
                continue
            oriented, _flipped = orient(cand, flags)
            for orient_tag, env_o in orientations:
                bands = oriented.bands
                # the 15 ms feasibility screen at the loosest rung, as the band family runs it: an
                # exact placement under the target objective can take seconds to prove infeasible
                zl = _rebanded(zones, p, None)
                screen = milp_heights(bands, {z: zl.get(z, zi) for z, zi in z2.items()}, union_m, env_o,
                                      min_contact_u=contacts_m, k=16, stacks={pid: tuple(zl[m] for m in stack)})
                reasons[f"STACK_SCREEN_{screen.status}"] += 1
                if screen.status != "FEASIBLE":
                    continue
                for rung in AREA_BAND_LADDER:
                    if time.monotonic() - t0 > STACK_BUDGET_S:
                        break                              # an exact placement can cost seconds per rung
                    zr = _rebanded(zones, p, rung) if rung != AREA_BAND_LADDER[0] else zones
                    z2r = {z: zr.get(z, zi) for z, zi in z2.items()}
                    stacks = {pid: tuple(zr[m] for m in stack)}
                    o = milp_placement(bands, z2r, union_m, env_o, min_contact_u=contacts_m,
                                       objective=OBJECTIVE, stacks=stacks)
                    reasons[f"STACK_{o.status}"] += 1
                    if o.status != "FEASIBLE":
                        if o.status == "BAND_GAP":
                            break
                        continue
                    sized += 1
                    sz = o.as_sizing()
                    cell_rects, intents = placement_rects(bands, z2r, o, stacks)
                    wing_rects = expand_wings(sz.band_rects(bands), sz.rects(bands),
                                              {pid: tuple(m.zone_id for m in stacks[pid])})
                    if orient_tag == "V":
                        cell_rects = _transpose_rects(cell_rects)
                        wing_rects = tuple(_transpose_rects(dict(enumerate(wing_rects))).values())
                    out = realize_cells(f"{case['id']}:{prop.name}:stack", cell_rects, intents, wing_rects, access,
                                        wet_rooms=p.resolved_wet)
                    if not isinstance(out, RealizedLayout):
                        reasons[f"STACK_{out.constraint}"] += 1
                        rec["refusals"].append({"parti": prop.name, "stage": "STACK_REALIZATION",
                                                "code": out.constraint, "detail": out.detail[:200]})
                        break
                    sp = measure_spatial_adjacency(out.rects, frozenset(frozenset(e) for e in spatial))
                    ac = measure_access_graph(out.fixture.access.edges, access)
                    gross = float(out.design.gross_area_m2)
                    net = float(out.design.net_area_m2 or 0.0)
                    verdict = assess_area(requested, gross, net, p.capacity_m2)
                    full = sp.preserved == sp.requested and ac.preserved == ac.requested
                    plan = {"family": "stack", "parti": prop.name, "stack": list(stack), "bands": len(bands),
                            "rung": rung, "orientation": orient_tag,
                            "contacts": f"{sp.preserved}/{sp.requested}",
                            "doors": f"{ac.preserved}/{ac.requested}",
                            "lost_doors": sorted(str(e) for e in ac.lost),
                            "arrival": _arrival_zone(out),
                            "gross_m2": round(gross, 1), "net_m2": round(net, 1),
                            "area": verdict.code, "gross_pct": verdict.gross_pct,
                            "wings": [(round(w.x * .05, 2), round(w.y * .05, 2), round(w.w * .05, 2),
                                       round(w.h * .05, 2)) for w in wing_rects],
                            "non_rectangular": len({(w.x, w.w) for w in sz.band_rects(bands)}) > 1,
                            "validators": len(out.report.checks),
                            "counts": bool(full and verdict.acceptable), **_proportions(out, intents)}
                    rec["plans"].append(plan)
                    if plan["counts"] and best is None:
                        best = (plan, out)
                    break
                if best is not None:
                    break
            if best is not None:
                break
        if best is not None:
            break
    rec["stages"]["STACK_SIZED"] += sized
    for k, v in reasons.items():
        rec["stages"][k] += v
    rec["stages"]["STACK_SECONDS"] += round(time.monotonic() - t0, 1)
    return best


def _cells_selection(layout, zones, orient_tag: str) -> list[str]:
    """Production's SELECTION questions for a cell layout (cf. `_spine_selection`): an arrival
    room can front the street; every REQUIRED-exposure room and the safe room has an exterior
    wall — a cell is exterior when it is first or last in one of its rows, in row 0, or in the
    last row (bands along the street); across the street (V) the street wall is the left edge."""
    from app.vertical_slice.doors import ALLOWED_ENTRANCE_ROLES
    from app.vertical_slice.exposure_policy import REQUIRED_EXTERIOR_ROLES
    from app.vertical_slice.geometry_core.model import ProgramRole
    role = lambda z: getattr(zones[z], "role", None)
    failed = []
    R = layout.n_rows
    fronting = set(layout.rows[0]) if orient_tag == "H" else {row[0] for row in layout.rows}
    if not any(role(z) in ALLOWED_ENTRANCE_ROLES for z in fronting):
        failed.append("entrance_feasible")
    foyers = [z for z in layout.zones if role(z) is ProgramRole.CIRCULATION]
    if foyers and not any(z in fronting for z in foyers):
        failed.append("foyer_fronts_street")
    exterior = set(layout.rows[0]) | set(layout.rows[-1])
    for row in layout.rows:
        exterior.add(row[0]); exterior.add(row[-1])
    buried = [z for z in layout.zones
              if (role(z) in REQUIRED_EXTERIOR_ROLES or role(z) is ProgramRole.SAFE_ROOM) and z not in exterior]
    if buried:
        failed.append("exposure_ok")
    return failed


def _cells_family(case, prop, zones, p, union, spatial, access, contacts, orientations, requested, rec):
    """Cross-band cells (#200): a zone two rows deep — the hub hall, the living room, the kitchen
    or dining room — found through the band embedding itself (`duplicated_layouts`), sized by the
    unified exact sizer, realized as ordinary cells (each its own wing). Plans tagged
    family="cells"; the first plan that counts is returned with its realization."""
    t0 = time.monotonic()
    reasons: Counter = Counter()
    deep = [z for z in zones if getattr(zones[z], "role", None) in _CELL_CIRC] + \
           [z for z in zones if getattr(zones[z], "role", None) in _CELL_PUBLIC]
    best = None
    sized = 0

    def sources():
        # 1. moves on the band family's own screened candidates: a public or circulation room
        #    extended one row (cheap — no embedding), the stack as a split
        emb = embed_band(zones, union, max_candidates=MAX_CANDIDATES)
        seeds = []
        if not isinstance(emb, BandEmbeddingRefusal):
            for cand in emb.candidates:
                flags = placement_flags(cand, zones, p.resolved_wet, tuple(access))
                if not hard_rejections(flags):
                    seeds.append(orient(cand, flags)[0])       # the street side the screen chose
                if len(seeds) >= CELLS_MOVE_SEEDS:
                    break
        moved = []
        seen = set()
        for cand in seeds:
            for lay in moves(from_bands(cand.bands), zones, union):
                if lay.rows not in seen and lay.spanning:
                    seen.add(lay.rows); moved.append(lay)
        yield "moves", moved
        # 2. a zone two rows deep through the band embedding itself
        for zone_id in deep:
            yield zone_id, duplicated_layouts(zones, union, zone_id, max_candidates=CELLS_MAX_LAYOUTS,
                                              max_partitions=CELLS_MAX_PARTITIONS)

    for zone_id, layouts in sources():
        if time.monotonic() - t0 > CELLS_BUDGET_S or sized >= MAX_SIZINGS:
            break
        rec["stages"]["CELLS_LAYOUTS"] += len(layouts)
        for layout in layouts:
            if time.monotonic() - t0 > CELLS_BUDGET_S or sized >= MAX_SIZINGS:
                break
            for orient_tag, env_o in orientations:
                rejected = _cells_selection(layout, zones, orient_tag)
                if rejected:
                    for k in rejected:
                        reasons[f"CELLS_SELECTION_{k}"] += 1
                    continue
                for rung in AREA_BAND_LADDER:
                    if time.monotonic() - t0 > CELLS_BUDGET_S:
                        break
                    zr = _rebanded(zones, p, rung) if rung != AREA_BAND_LADDER[0] else zones
                    o = cells_placement(layout, zr, union, env_o, min_contact_u=contacts, k=CELLS_K,
                                        objective=OBJECTIVE)
                    reasons[f"CELLS_{o.status}"] += 1
                    if o.status != "FEASIBLE":
                        if o.status == "BAND_GAP":
                            break
                        continue
                    sized += 1
                    cell_rects, wing_rects = cells_rects(layout, o), cells_wings(layout, o)
                    if orient_tag == "V":
                        cell_rects = _transpose_rects(cell_rects)
                        wing_rects = tuple(_transpose_rects(dict(enumerate(wing_rects))).values())
                    out = realize_cells(f"{case['id']}:{prop.name}:cells", cell_rects, zr, wing_rects, access,
                                        wet_rooms=p.resolved_wet)
                    if not isinstance(out, RealizedLayout):
                        reasons[f"CELLS_{out.constraint}"] += 1
                        rec["refusals"].append({"parti": prop.name, "stage": "CELLS_REALIZATION",
                                                "code": out.constraint, "detail": out.detail[:200]})
                        break
                    sp = measure_spatial_adjacency(out.rects, frozenset(frozenset(e) for e in spatial))
                    ac = measure_access_graph(out.fixture.access.edges, access)
                    gross = float(out.design.gross_area_m2)
                    net = float(out.design.net_area_m2 or 0.0)
                    verdict = assess_area(requested, gross, net, p.capacity_m2)
                    full = sp.preserved == sp.requested and ac.preserved == ac.requested
                    plan = {"family": "cells", "parti": prop.name, "deep": zone_id, "spanning": list(layout.spanning),
                            "rows": layout.n_rows,
                            "layout": [list(r) for r in layout.rows], "rung": rung, "orientation": orient_tag,
                            "contacts": f"{sp.preserved}/{sp.requested}",
                            "doors": f"{ac.preserved}/{ac.requested}",
                            "lost_doors": sorted(str(e) for e in ac.lost),
                            "arrival": _arrival_zone(out),
                            "gross_m2": round(gross, 1), "net_m2": round(net, 1),
                            "area": verdict.code, "gross_pct": verdict.gross_pct,
                            "wings": [(round(w.x * .05, 2), round(w.y * .05, 2), round(w.w * .05, 2),
                                       round(w.h * .05, 2)) for w in wing_rects],
                            "non_rectangular": True,
                            "validators": len(out.report.checks),
                            "counts": bool(full and verdict.acceptable), **_proportions(out, zr)}
                    rec["plans"].append(plan)
                    if plan["counts"] and best is None:
                        best = (plan, out)
                    break
                if best is not None:
                    break
            if best is not None:
                break
        if best is not None:
            break
    rec["stages"]["CELLS_SIZED"] += sized
    for k, v in reasons.items():
        rec["stages"][k] += v
    rec["stages"]["CELLS_SECONDS"] += round(time.monotonic() - t0, 1)
    return best


def _spine_selection(layout, zones, orient_tag: str) -> list[str]:
    """The production SELECTION questions for a spine layout, before any geometry is sized — the
    HARD flags `placement_flags` asks of a band candidate, read off the layout's structure:

    entrance_feasible — can an allowed arrival room front the street? Bands along the street (H):
    the embedding already guarantees it (a spine that fronts is three door widths wide, else the
    street band holds an arrival room). Bands across the street (V): the street wall is the layout's
    LEFT edge, so the outermost-left cells front it — a section band with no left part puts the
    spine's long wall there.
    exposure_ok — every REQUIRED-exposure room (and the safe room) has an exterior wall: the outer
    cell of a side row, any cell of the top/bottom plain band, the end cells of a plain band, or a
    cell in the section's first/last row when nothing sits above/below it. A room inside a side row
    of a middle band is buried, as in the band family; it is skipped, not sized and refused."""
    from app.vertical_slice.doors import ALLOWED_ENTRANCE_ROLES
    from app.vertical_slice.exposure_policy import REQUIRED_EXTERIOR_ROLES
    from app.vertical_slice.geometry_core.model import ProgramRole
    failed = []
    role = lambda z: getattr(zones[z], "role", None)
    if orient_tag == "V":
        fronting = {band[0] for band in layout.top + layout.bottom}
        for left, _right in layout.bands:
            fronting.add(left[0] if left else layout.spine)
        if not any(role(z) in ALLOWED_ENTRANCE_ROLES for z in fronting):
            failed.append("entrance_feasible")
    # a FOYER (a CIRCULATION room off the spine with at most one other neighbour — the brain's
    # degree-2 ENTRY) exists to hold the front door: it must front the street, else the parti's
    # point is lost (the door would open into the living room and the foyer float at the back)
    foyers = [z for z in layout.cells if z != layout.spine and role(z) is ProgramRole.CIRCULATION]
    if foyers:
        if orient_tag == "H":
            fronting = set(layout.top[0]) if layout.top else set()
        if not any(z in fronting for z in foyers):
            failed.append("foyer_fronts_street")
    exterior = {layout.spine}
    for band in layout.top + layout.bottom:
        exterior.update(band[0:1]); exterior.update(band[-1:])
    if layout.top:
        exterior.update(layout.top[0])
    if layout.bottom:
        exterior.update(layout.bottom[-1])
    for r, (left, right) in enumerate(layout.bands):
        exterior.update(left[0:1]); exterior.update(right[-1:])
        if (r == 0 and not layout.top) or (r == len(layout.bands) - 1 and not layout.bottom):
            exterior.update(left); exterior.update(right)
    buried = [z for z in layout.cells
              if (role(z) in REQUIRED_EXTERIOR_ROLES or role(z) is ProgramRole.SAFE_ROOM) and z not in exterior]
    if buried:
        failed.append("exposure_ok")
    return failed


def _spine_family(case, prop, zones, p, union, spatial, access, contacts, orientations, requested, rec):
    """Path B for one proposal: embed around the hub, size every layout with the exact spine oracle
    (both orientations, the Stage 3 ladder), realize through `realize_cells`. Returns the first plan
    that counts, with its realization, or None; every refusal is recorded on `rec`."""
    t0 = time.monotonic()
    reasons: Counter = Counter()
    spine = choose_spine(zones, union)
    if spine is None:
        rec["stages"]["SPINE_NO_CIRCULATION"] += 1
        return None
    layouts = embed_spine(zones, union, spine, max_candidates=SPINE_MAX_LAYOUTS)
    rec["stages"]["SPINE_LAYOUTS"] += len(layouts)
    if not layouts:
        rec["refusals"].append({"parti": prop.name, "stage": "SPINE_EMBEDDING", "code": "NO_SPINE_LAYOUT",
                                "detail": f"the contact graph does not split around {spine} into embeddable sides"})
        return None
    best = None
    sized = 0
    for layout in layouts:
        if time.monotonic() - t0 > SPINE_BUDGET_S or sized >= MAX_SIZINGS:
            break
        for orient_tag, env_o in orientations:
            rejected = _spine_selection(layout, zones, orient_tag)
            if rejected:
                for k in rejected:
                    reasons[f"SPINE_SELECTION_{k}"] += 1
                continue
            for rung in AREA_BAND_LADDER:
                zr = _rebanded(zones, p, rung) if rung != AREA_BAND_LADDER[0] else zones
                o = milp_spine_placement(layout, zr, union, env_o, min_contact_u=contacts, objective=OBJECTIVE)
                reasons[f"SPINE_{o.status}"] += 1
                if o.status != "FEASIBLE":
                    if o.status == "BAND_GAP":
                        break
                    continue
                sized += 1
                zi = spine_intents(layout, zr)
                cell_rects, wing_rects = spine_geometry(layout, o)
                if orient_tag == "V":
                    cell_rects = _transpose_rects(cell_rects)
                    wing_rects = tuple(_transpose_rects(dict(enumerate(wing_rects))).values())
                out = realize_cells(f"{case['id']}:{prop.name}:spine", cell_rects, zi, wing_rects, access,
                                    wet_rooms=p.resolved_wet)
                if not isinstance(out, RealizedLayout):
                    reasons[f"SPINE_{out.constraint}"] += 1
                    rec["refusals"].append({"parti": prop.name, "stage": "SPINE_REALIZATION",
                                            "code": out.constraint, "detail": out.detail[:200]})
                    break
                sp = measure_spatial_adjacency(out.rects, frozenset(frozenset(e) for e in spatial))
                ac = measure_access_graph(out.fixture.access.edges, access)
                gross = float(out.design.gross_area_m2)
                net = float(out.design.net_area_m2 or 0.0)
                verdict = assess_area(requested, gross, net, p.capacity_m2)
                full = sp.preserved == sp.requested and ac.preserved == ac.requested
                plan = {"family": "spine", "parti": prop.name, "spine": spine, "rows": layout.n_rows,
                        "section": list(layout.section), "rung": rung, "orientation": orient_tag,
                        "contacts": f"{sp.preserved}/{sp.requested}",
                        "doors": f"{ac.preserved}/{ac.requested}",
                        "lost_doors": sorted(str(e) for e in ac.lost),
                        "arrival": _arrival_zone(out),
                        "gross_m2": round(gross, 1), "net_m2": round(net, 1),
                        "area": verdict.code, "gross_pct": verdict.gross_pct,
                        "wings": [(round(w.x * .05, 2), round(w.y * .05, 2), round(w.w * .05, 2),
                                   round(w.h * .05, 2)) for w in wing_rects],
                        "non_rectangular": len({(w.x, w.w) for w in wing_rects}) > 1,
                        "validators": len(out.report.checks),
                        "counts": bool(full and verdict.acceptable), **_proportions(out, zi)}
                rec["plans"].append(plan)
                if plan["counts"] and best is None:
                    best = (plan, out)
                break
            if best is not None:
                break
        if best is not None:
            break
    rec["stages"]["SPINE_SIZED"] += sized
    for k, v in reasons.items():
        rec["stages"][k] += v
    rec["stages"]["SPINE_SECONDS"] += round(time.monotonic() - t0, 1)
    return best


def run_case(case: dict, out_dir: str) -> dict:
    t0 = time.monotonic()
    rec: dict = {"id": case["id"], "expected": case["expected"], "stages": Counter(), "plans": [],
                 "refusals": []}
    project, env = _project_for(case)
    spec = spec_for(project)
    # The programme is scaled to the floor that EXISTS — the envelope polygon's area — not to its
    # bounding box: on F2 the box is 224 m² and the L is 182 m², and rooms scaled to the box can
    # never fit the L. `programme_from_spec` takes a rectangle, so pass the equivalent one.
    W = env.width_u * 0.05
    p = programme_from_spec(spec, (W, env.area_m2 / W))
    requested = case["footprint"]["gross_m2"]
    proposals = DeterministicProposer().propose(p)
    rec["partis"] = [x.name for x in proposals]
    os.makedirs(os.path.join(out_dir, "designs"), exist_ok=True)
    # the same algorithm in both orientations: bands along the street, and bands across it (the
    # envelope transposed, the result transposed back). Neither names a shape.
    orientations = (("H", env), ("V", _transposed_envelope(env)))

    for prop in proposals:
        zones = {z: p.zones[z] for z in prop.rooms if z in p.zones}
        for z in prop.rooms:
            if z not in zones:
                zones[z] = _hall_intent(z, target=7.0)
        try:
            spatial = list(prop.spatial) + _extra(case, "contacts_extra", zones)
            access = [(a, b) for a, b in prop.access if a != "ENTRANCE"] + _extra(case, "access_extra", zones)
            # one door per unordered pair: a case extra that repeats a parti pair the other way round
            # (F4's KITCHEN-LIVING over LIVING-KITCHEN) is the same door, not a second one — two
            # doors on one wall overlap and C28 refuses every plan (F4, day 2)
            seen_pairs: set = set()
            access = [e for e in access if not (frozenset(e) in seen_pairs or seen_pairs.add(frozenset(e)))]
        except InvalidCase as exc:
            rec["stages"]["INVALID_CASE"] += 1
            rec["refusals"].append({"parti": prop.name, "stage": "CASE", "code": "INVALID_CASE",
                                    "detail": str(exc)[:200]})
            continue
        union = sorted({tuple(sorted(e)) for e in spatial} | {tuple(sorted(e)) for e in access})

        # 1. representation: refused before any geometry, in milliseconds
        adj = _adjacency(union)
        k4, lens = find_k4(adj), find_triple_lens(adj)
        if k4 or lens:
            rec["stages"]["REPRESENTATION"] += 1
            rec["refusals"].append({"parti": prop.name, "stage": "REPRESENTATION",
                                    "code": "TOPOLOGY_REPRESENTATION_LIMIT",
                                    "detail": f"K4 {k4}" if k4 else f"triple-lens {lens}"})
            continue

        # 2. embedding (unchanged)
        emb = embed_band(zones, union, max_candidates=MAX_CANDIDATES)
        if isinstance(emb, BandEmbeddingRefusal):
            rec["stages"]["EMBEDDING"] += 1
            rec["refusals"].append({"parti": prop.name, "stage": "EMBEDDING", "code": emb.code,
                                    "detail": emb.detail[:200]})
            continue
        contacts = contact_requirements(zones, union, access)

        # 3. sizing inside the envelope, then realization; both orientations; the Stage 3 ladder
        sized = 0
        best = None
        reasons: Counter = Counter()
        screened = 0
        for cand in emb.candidates:
          # the production pipeline's own SELECTION step, reused: an allowed arrival room must be
          # able to front the street in some orientation, every door pair must touch legally,
          # REQUIRED exposure rooms must lie on the envelope, every room must be reachable. A
          # candidate failing these is never sized (it was: F4 spent 13 of 20 oracle-feasible
          # sizings on layouts with no entrance-eligible room in the street band).
          flags = placement_flags(cand, zones, p.resolved_wet, tuple(access))
          rejected = hard_rejections(flags)
          if rejected:
              for k in rejected:
                  reasons[f"SELECTION_{k}"] += 1
              continue
          oriented, _flipped = orient(cand, flags)
          for orient_tag, env_o in orientations:
            for bands in (oriented.bands,):
                if sized >= MAX_SIZINGS:
                    break
                seed = None
                if milp_heights is not None:
                    # 15 ms: does ANY height vector satisfy every constraint at the loosest band
                    # rung? If not, no rung can, and the exact sizer is not asked.
                    screened += 1
                    o = milp_heights(bands, _rebanded(zones, p, None), union, env_o,
                                     min_contact_u=contacts, k=16)
                    reasons[f"ORACLE_{o.status}"] += 1
                    if o.status != "FEASIBLE":
                        continue
                    seed = o.heights_u
                sized += 1
                for rung in AREA_BAND_LADDER:
                    zr = _rebanded(zones, p, rung) if rung != AREA_BAND_LADDER[0] else zones
                    if milp_placement is not None:
                        # the aligned oracle IS the sizer: heights and boundaries from one exact
                        # MILP, insets to a fixed point, no search left to fail
                        sz = milp_placement(bands, zr, union, env_o, min_contact_u=contacts,
                                            objective=OBJECTIVE).as_sizing()
                    else:
                        sz = solve_staircase_layout(bands, zr, union, env_o, min_contact_u=contacts,
                                                    node_limit=800, seed=seed)
                    if sz.status != "FEASIBLE":
                        reasons[sz.status] += 1
                        if sz.status == "BAND_GAP":
                            break                      # structural: no band width fixes a split envelope
                        continue                       # INFEASIBLE / ALIGNMENT_UNSAT / UNKNOWN: a wider band may
                    cell_rects, wing_rects = sz.rects(bands), sz.band_rects(bands)
                    if orient_tag == "V":
                        cell_rects = _transpose_rects(cell_rects)
                        wing_rects = tuple(_transpose_rects(dict(enumerate(wing_rects))).values())
                    out = realize_cells(f"{case['id']}:{prop.name}", cell_rects, zr,
                                        wing_rects, access, wet_rooms=p.resolved_wet)
                    if not isinstance(out, RealizedLayout):
                        reasons[out.constraint] += 1
                        break
                    sp = measure_spatial_adjacency(out.rects, frozenset(frozenset(e) for e in spatial))
                    ac = measure_access_graph(out.fixture.access.edges, access)
                    gross = float(out.design.gross_area_m2)
                    net = float(out.design.net_area_m2 or 0.0)
                    verdict = assess_area(requested, gross, net, p.capacity_m2)
                    full = sp.preserved == sp.requested and ac.preserved == ac.requested
                    plan = {"family": "band", "parti": prop.name, "bands": len(bands), "rung": rung,
                            "orientation": orient_tag,
                            "contacts": f"{sp.preserved}/{sp.requested}",
                            "doors": f"{ac.preserved}/{ac.requested}",
                            "lost_doors": sorted(str(e) for e in ac.lost),
                            "arrival": _arrival_zone(out),
                            "gross_m2": round(gross, 1), "net_m2": round(net, 1),
                            "area": verdict.code, "gross_pct": verdict.gross_pct,
                            "wings": [(round(w.x * .05, 2), round(w.y * .05, 2), round(w.w * .05, 2),
                                       round(w.h * .05, 2)) for w in wing_rects],
                            "non_rectangular": len({(w.x, w.w) for w in sz.band_rects(bands)}) > 1,
                            "validators": len(out.report.checks),
                            "counts": bool(full and verdict.acceptable), **_proportions(out, zr)}
                    rec["plans"].append(plan)
                    if plan["counts"] and best is None:
                        best = (plan, out)
                    break                                 # this candidate is sized; next candidate
            if best is not None:
                break
          if best is not None:
              break
        rec["stages"]["SIZED_CANDIDATES"] += sized
        rec["stages"]["SCREENED"] += screened
        for k, v in reasons.items():
            rec["stages"][k] += v
        if best is not None:
            _dump_design(case, prop, best, out_dir, "band")

        # 4. the SPINE family (ADR-001 path B): the same programme, contacts and envelope; a
        # circulation cell spanning a run of bands, plain street/back bands around it. Same
        # realizer, validators and area verdicts; plans are tagged by family.
        if milp_spine_placement is not None:
            spine_best = _spine_family(case, prop, zones, p, union, spatial, access, contacts,
                                       orientations, requested, rec)
            if spine_best is not None:
                _dump_design(case, prop, spine_best, out_dir, "spine")

        # 5. the 2D wing, minimal form: two small rooms stacked in one column of a band
        if milp_placement is not None:
            stack_best = _stack_family(case, prop, zones, p, union, spatial, access, orientations, requested, rec)
            if stack_best is not None:
                _dump_design(case, prop, stack_best, out_dir, "stack")

        # 6. cross-band cells (#200): a hub or public room two rows deep, the unified exact sizer
        if cells_placement is not None:
            cells_best = _cells_family(case, prop, zones, p, union, spatial, access, contacts, orientations,
                                       requested, rec)
            if cells_best is not None:
                _dump_design(case, prop, cells_best, out_dir, "cells")

    rec["seconds"] = round(time.monotonic() - t0, 1)
    counted = [x for x in rec["plans"] if x["counts"]]
    rec["solved"] = bool(counted)
    rec["distinct_footprints"] = len({tuple(x["wings"]) for x in counted})
    rec["stages"] = dict(rec["stages"])
    return rec


def main(argv: list[str]) -> None:
    out_dir = argv[0] if argv else "shape_agnostic_out"
    os.makedirs(out_dir, exist_ok=True)
    spec = json.load(open(os.path.normpath(CASES_PATH)))
    wanted = set(argv[1:])
    results = []
    for case in spec["cases"]:
        if wanted and case["id"] not in wanted:
            continue
        rec = run_case(case, out_dir)
        results.append(rec)
        counted = [x for x in rec["plans"] if x["counts"]]
        print(f"{rec['id']:24} solved={rec['solved']!s:5} plans={len(counted)}/{len(rec['plans'])} "
              f"distinct_footprints={rec['distinct_footprints']} {rec['seconds']:6.1f}s "
              f"stages={rec['stages']}", flush=True)
    with open(os.path.join(out_dir, "results.json"), "w") as fh:
        json.dump(results, fh, indent=2, default=str)


if __name__ == "__main__":
    main(sys.argv[1:])
