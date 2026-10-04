"""#142F — Architectural intent-aware candidate selection among already-valid band layouts (experiment).

Question: how much of the gap from 4/13 (the merged #142E baseline) closes by CHOOSING, among exact
band layouts, those that already respect architectural intent — entrance, physically supported
access, mandatory exposure, SAFE_ROOM placement — before any new geometry or realizer capability?

Nothing in production changes. This module reads the frozen-brief fixture, runs the merged pipeline
as the baseline (E), and runs the experiment (F) on top of the production embedder/sizer/realizer:

  F1  required contacts = spatial_adjacency ∪ direct access pairs (the invariant "a door needs a
      shared wall"); a proposal whose union is unembeddable is diagnosed, never silently changed
  F2  per-candidate feasibility flags decided FROM THE EMBEDDING (no geometry): entrance band,
      access contact + legality, mandatory exposure on the envelope, SAFE_ROOM on the envelope,
      reachability from the entrance room through legal contacts
  F3  orientation: a band layout can be flipped top/bottom for free, so an entrance-eligible room
      in the LAST band becomes the street band by flipping (never by patching a door on)
  F4  HARD filter (entrance ∧ access-contact ∧ exposure ∧ reachability); SOFT properties recorded
  F5  door-aware sizing: access pairs get a shared boundary >= door width + margins (the
      realizer's own `_build_grid_wing` rule), same-band access pairs force the band height to it
  F6  unchanged realize_layout + validate; RC counterfactual = PASS or "fails only C4"
"""
from __future__ import annotations

import json
import math
import os
import time
from unittest import mock
from collections import Counter
from dataclasses import asdict, dataclass, field

from app.vertical_slice import access_rules, band_sizing
from app.vertical_slice import rectilinear_realizer as rr
from app.vertical_slice.band_embedding import BandEmbedding, BandEmbeddingRefusal, BandPlacement, embed_band
from app.vertical_slice.band_pipeline import PipelineInput, PipelineSuccess, run_band_pipeline
from app.vertical_slice.band_sizing import LayoutSizing, _bellman_ford_from, _height_bounds, _layout_cells, _prefix_interval, _width_interval
from app.vertical_slice.doors import ALLOWED_ENTRANCE_ROLES, DOOR_MARGIN_M
from app.vertical_slice.exposure_policy import EXPOSURE_POLICY, REQUIRED_EXTERIOR_ROLES, ExposureRequirement
from app.vertical_slice.geometry_core.model import ProgramRole, Rect, m_to_u
from app.vertical_slice.rectilinear_realizer import GridCell, GridWing, RealizationIntent, RealizedLayout, Refusal, ZoneIntent, realize_layout
from app.vertical_slice.spec import WetRoomKind, WetRoomStrength
from app.vertical_slice.topology_preservation import measure_access_graph, measure_spatial_adjacency
from app.vertical_slice.wet_rooms import ResolvedWetRoom

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
FIXTURE = os.path.join(_BACKEND, "tests", "fixtures", "frozen_briefs_142.json")
REPORT_DIR = os.path.join(os.path.dirname(_BACKEND), "docs", "reports", "142f-intent-aware-embedding")
ENTRANCE_ID = "ENTRANCE"
BUILDABLE_MARGIN_M = 4.0


# ----------------------------------------------------------------------------- fixture

def load_brief(bid: str, brief: dict) -> PipelineInput:
    zones = {z: ZoneIntent(z, ProgramRole(v["role"]), v["target"], v["min"], v["max"], v["min_short"], v["max_aspect"])
             for z, v in brief["zones"].items()}
    roles = {r["id"]: ProgramRole(r["role"]) for r in brief["rooms"]}
    incoming: dict[str, list[str]] = {}
    for a, b in brief["access_graph"]:
        incoming.setdefault(b, []).append(a)
    wet = []
    for rid, role in roles.items():
        if role not in (ProgramRole.BATHROOM, ProgramRole.TOILET):
            continue
        hosts = [a for a in incoming.get(rid, ()) if roles.get(a) in (ProgramRole.BEDROOM, ProgramRole.MASTER_BEDROOM)]
        if hosts:
            wet.append(ResolvedWetRoom(rid, WetRoomKind.ENSUITE, hosts[0], WetRoomStrength.REQUIRED, True))
        else:
            kind = WetRoomKind.GUEST_WC if role is ProgramRole.TOILET else WetRoomKind.SHARED_BATHROOM
            wet.append(ResolvedWetRoom(rid, kind, None, WetRoomStrength.REQUIRED, True))
    return PipelineInput(name=bid, zones=zones, required_edges=tuple(tuple(e) for e in brief["spatial_adjacency"]),
                         footprint_m=tuple(brief["footprint_m"]), wet_rooms=tuple(wet),
                         access_edges=tuple((a, b) for a, b in brief["access_graph"] if a != ENTRANCE_ID))


# ----------------------------------------------------------------------------- flags (embedding only)

def _cells(p: BandPlacement) -> dict[str, tuple[int, int, int]]:
    out = {}
    for r, row in enumerate(p.rows):
        c0 = 0
        for z, span in row:
            out[z] = (r, c0, c0 + span); c0 += span
    return out


def _touch(cells, a, b) -> bool:
    ra, a0, a1 = cells[a]; rb, b0, b1 = cells[b]
    return (a1 == b0 or b1 == a0) if ra == rb else (abs(ra - rb) == 1 and a0 < b1 and b0 < a1)


def _legal(roles, wet, a, b) -> bool:
    if not access_rules.edge_role_pair_allowed((roles[a],), (roles[b],)):
        return False
    for x, y in ((a, b), (b, a)):
        if x in wet:
            w = wet[x]
            if w.host_zone is not None and y != w.host_zone:
                return False
            if w.host_zone is None and roles[y] not in (ProgramRole.HALL, ProgramRole.CIRCULATION):
                return False
    return True


def candidate_flags(p: BandPlacement, inp: PipelineInput) -> dict:
    """Everything decidable from the band placement alone (no sizing, no realization)."""
    cells = _cells(p); R = len(p.rows)
    roles = {z: zi.role for z, zi in inp.zones.items()}
    wet = {w.zone_id: w for w in inp.wet_rooms}
    on_env = {z: (r == 0 or r == R - 1 or c0 == 0 or c1 == p.n_cols) for z, (r, c0, c1) in cells.items()}
    entrance_rows = sorted({cells[z][0] for z in cells if roles[z] in ALLOWED_ENTRANCE_ROLES})
    entrance_now = 0 in entrance_rows
    entrance_flip = (R - 1) in entrance_rows
    # access pairs: physically supported (contact) and legal
    access = [(a, b) for a, b in inp.access_edges if a in cells and b in cells]
    missing_contact = [(a, b) for a, b in access if not _touch(cells, a, b)]
    illegal = [(a, b) for a, b in access if _touch(cells, a, b) and not _legal(roles, wet, a, b)]
    # every room has >= 1 legal contact (production flag) and reachability from an entrance room
    ids = list(cells)
    has_partner = {a: any(_touch(cells, a, b) and _legal(roles, wet, a, b) for b in ids if b != a) for a in ids}
    entrance_rooms = [z for z in ids if roles[z] in ALLOWED_ENTRANCE_ROLES]
    reach = set()
    if entrance_rooms:
        start = sorted(entrance_rooms, key=lambda z: (cells[z][0], z))[0]
        reach = {start}; stack = [start]
        while stack:
            x = stack.pop()
            for y in ids:
                if y not in reach and _touch(cells, x, y) and _legal(roles, wet, x, y):
                    reach.add(y); stack.append(y)
    exposure_required = [z for z in ids if roles[z] in REQUIRED_EXTERIOR_ROLES]
    exposure_preferred = [z for z in ids if EXPOSURE_POLICY[roles[z]].exterior_wall is ExposureRequirement.PREFERRED]
    buried_required = [z for z in exposure_required if not on_env[z]]
    safe = [z for z in ids if roles[z] is ProgramRole.SAFE_ROOM]
    street_width = sum(span for _, span in p.rows[0])
    public_front = sum(span for z, span in p.rows[0] if roles[z] in (ProgramRole.LIVING, ProgramRole.DINING, ProgramRole.KITCHEN, ProgramRole.HALL))
    hub = max(ids, key=lambda z: sum(1 for e in inp.required_edges if z in e))
    return {
        # HARD
        "entrance_now": entrance_now, "entrance_flip": entrance_flip,
        "entrance_feasible": entrance_now or entrance_flip, "entrance_rows": entrance_rows,
        "access_contact_ok": not missing_contact and not illegal,
        "access_missing_contact": missing_contact, "access_illegal_pair": illegal,
        "exposure_ok": not buried_required, "buried_required": buried_required,
        "safe_room_on_envelope": all(on_env[z] for z in safe) if safe else None,
        "safe_room_has_legal_partner": all(has_partner[z] for z in safe) if safe else None,
        "all_rooms_have_legal_partner": all(has_partner.values()),
        "reachable_from_entrance": len(reach) == len(ids) if entrance_rooms else False,
        "unreachable": sorted(set(ids) - reach),
        # SOFT
        "n_bands": R, "preferred_on_envelope": sum(1 for z in exposure_preferred if on_env[z]),
        "preferred_total": len(exposure_preferred),
        "public_front_share": round(public_front / street_width, 2) if street_width else 0.0,
        "hub_band_is_middle": 0 < cells[hub][0] < R - 1,
        "bedrooms_bands": len({cells[z][0] for z in ids if roles[z] in (ProgramRole.BEDROOM, ProgramRole.MASTER_BEDROOM)}),
    }


def access_policy_conflicts(inp: PipelineInput) -> list[tuple[str, str, str]]:
    """Access pairs no layout can ever carry as a door: illegal under `edge_role_pair_allowed` or
    the realizer's own wet-room filter (`_filter_wet_room_access`: an ENSUITE only from its host,
    a shared bathroom / guest WC only from HALL/CIRCULATION — stricter than `ALLOWED_ENTERED_FROM`,
    which also admits LIVING for wet rooms). Decided from the proposal alone."""
    roles = {z: zi.role for z, zi in inp.zones.items()}
    wet = {w.zone_id: w for w in inp.wet_rooms}
    out = []
    for a, b in inp.access_edges:
        if a not in roles or b not in roles:
            continue
        if not access_rules.edge_role_pair_allowed((roles[a],), (roles[b],)):
            out.append((a, b, "edge_role_pair_allowed forbids this role pair")); continue
        for x, y in ((a, b), (b, a)):
            if x in wet:
                w = wet[x]
                if w.host_zone is not None and y != w.host_zone:
                    out.append((a, b, f"{x} is an ENSUITE of {w.host_zone}; the realizer's wet-room filter admits no other door")); break
                if w.host_zone is None and roles[y] not in (ProgramRole.HALL, ProgramRole.CIRCULATION):
                    out.append((a, b, f"{x} is a shared wet room; the realizer's filter admits a door only from HALL/CIRCULATION (ALLOWED_ENTERED_FROM would admit {roles[y].value})")); break
    return out


def flipped(p: BandPlacement) -> BandPlacement:
    return BandPlacement(tuple(reversed(p.rows)), p.n_cols, p.score, tuple(reversed(p.bands)))


# ----------------------------------------------------------------------------- door-aware sizing (experiment)

def _door_min_u(roles, a, b) -> int:
    kind = access_rules.door_kind_for_zones((roles[a],), (roles[b],))
    return m_to_u(access_rules.DOOR_WIDTH_M[kind]) + 2 * m_to_u(DOOR_MARGIN_M)


def solve_band_layout_doors(bands, zones, spatial, access, *, w_max_m, h_max_m, node_limit=4000) -> LayoutSizing:
    """`band_sizing.solve_band_layout` with a per-pair minimum shared boundary: >= 1 unit for
    spatial-only pairs, >= door width + margins for access pairs (cross-band: overlap; same-band
    consecutive: the band height). Experiment-only; production sizing is untouched."""
    cells, (W_node,) = _layout_cells(bands, zones)
    N = W_node + 1; R = len(bands)
    roles = {z: zones[z].role for z in zones}
    by_zone = {c.zone_id: c for c in cells}
    tol = 0.01
    w_max = m_to_u(w_max_m); h_cap = m_to_u(h_max_m)
    pairs: dict[frozenset, int] = {}
    for a, b in spatial:
        pairs[frozenset((a, b))] = max(pairs.get(frozenset((a, b)), 1), 1)
    for a, b in access:
        pairs[frozenset((a, b))] = max(pairs.get(frozenset((a, b)), 1), _door_min_u(roles, a, b))
    hL0 = [0] * R; hU0 = [h_cap] * R
    for cell in cells:
        lo, hi = _height_bounds(cell, tol, h_cap)
        hL0[cell.r] = max(hL0[cell.r], lo); hU0[cell.r] = min(hU0[cell.r], hi)
    for pr, need in pairs.items():
        a, b = tuple(pr); ca, cb = by_zone[a], by_zone[b]
        if ca.r == cb.r and need > 1:
            hL0[ca.r] = max(hL0[ca.r], need)
    if any(hL0[r] > hU0[r] for r in range(R)):
        return LayoutSizing("INFEASIBLE", nodes=0, detail="band depth cannot host a door on a same-band access pair")
    total = sum(z.target_area_m2 for z in zones.values()) or 1.0
    row_tot = [sum(zones[z].target_area_m2 for z in band) for band in bands]
    H_est = min(h_cap, m_to_u(math.sqrt(total))); W_est = min(w_max, m_to_u(math.sqrt(total)))
    h_est = [H_est * rt / total for rt in row_tot]

    def system(h, hU):
        cons = []
        for cell in cells:
            lo, hi = _width_interval(cell, h[cell.r], (hU or h)[cell.r], tol)
            if lo > hi:
                return None
            cons.append((cell.c0, cell.c1, hi)); cons.append((cell.c1, cell.c0, -lo))
        for pr, need in pairs.items():
            a, b = tuple(pr); ca, cb = by_zone[a], by_zone[b]
            if ca.r == cb.r:
                continue
            if abs(ca.r - cb.r) != 1:
                return None
            cons.append((cb.c1, ca.c0, -need)); cons.append((ca.c1, cb.c0, -need))
        cons.append((0, N - 1, w_max))
        return cons

    def feasible(hL, hU):
        cons = system(hL, hU)
        return cons is not None and _bellman_ford_from(N - 1, cons, 0) is not None

    def choose(h):
        cons = system(h, None)
        if cons is None or _bellman_ford_from(N - 1, cons, 0) is None:
            return None
        fixed = []; P = [0] * N
        iv = _prefix_interval(N - 1, cons, W_node)
        if iv is None:
            return None
        Wv = max(iv[0], min(iv[1], int(round(W_est)))); fixed += [(0, W_node, Wv), (W_node, 0, -Wv)]; P[W_node] = Wv
        for r, band in enumerate(bands):
            cum = 0.0
            ids = [c for c in cells if c.r == r]
            for cell in ids[:-1]:
                cum += zones[cell.zone_id].target_area_m2 / row_tot[r] * Wv
                iv = _prefix_interval(N - 1, cons + fixed, cell.c1)
                if iv is None or iv[0] > iv[1]:
                    return None
                val = max(iv[0], min(iv[1], int(round(cum)))); fixed += [(0, cell.c1, val), (cell.c1, 0, -val)]; P[cell.c1] = val
        return P if _bellman_ford_from(N - 1, cons + fixed, 0) is not None else None

    def finish(h, P, nodes):
        positions = tuple(tuple(P[i] for i in [c.c0 for c in cells if c.r == r] + [W_node]) for r in range(R))
        xs = sorted({x for band in positions for x in band}); col_of = {x: i for i, x in enumerate(xs)}
        rows = tuple(tuple((bands[r][i], col_of[positions[r][i + 1]] - col_of[positions[r][i]]) for i in range(len(bands[r]))) for r in range(R))
        return LayoutSizing("FEASIBLE", tuple(h), positions, rows, len(xs) - 1, tuple(xs[i + 1] - xs[i] for i in range(len(xs) - 1)), nodes)

    stack = [(hL0, hU0)]; nodes = 0
    while stack:
        hL, hU = stack.pop(); nodes += 1
        if nodes > node_limit:
            return LayoutSizing("UNKNOWN", nodes=nodes, detail="node budget exhausted")
        if sum(hL) > h_cap or not feasible(hL, hU):
            continue
        h = [max(hL[r], min(hU[r], int(round(h_est[r])))) for r in range(R)]
        if sum(h) <= h_cap:
            P = choose(h)
            if P is not None:
                return finish(h, P, nodes)
        if hL == hU:
            continue
        r = max(range(R), key=lambda i: (hU[i] - hL[i], -i)); mid = (hL[r] + hU[r]) // 2
        lower = (list(hL), hU[:r] + [mid] + hU[r + 1:]); upper = (hL[:r] + [mid + 1] + hL[r + 1:], list(hU))
        if h_est[r] > mid + 0.5:
            stack.append(lower); stack.append(upper)
        else:
            stack.append(upper); stack.append(lower)
    return LayoutSizing("INFEASIBLE", nodes=nodes, detail="every height box pruned (proof)")


# ----------------------------------------------------------------------------- the experiment

@dataclass
class CandidateRow:
    index: int
    source: str                     # "spatial" | "union"
    flags: dict
    hard_ok: bool
    oriented: bool                  # flipped to put the entrance band at the street
    sizing: str | None = None       # FEASIBLE/INFEASIBLE/UNKNOWN (door-aware)
    outcome: str | None = None      # PASS | refusal constraint | VALIDATION_FAILED
    failed_checks: tuple = ()
    rc_counterfactual_pass: bool = False
    spatial: str | None = None
    access: str | None = None


@dataclass
class BriefResult:
    brief_id: str
    baseline: dict
    union_embedding: str            # OK | refusal code
    union_detail: str
    access_pairs_not_in_spatial: int
    candidates: int
    hard_feasible: int
    flag_counts: dict
    sizable: int
    realized: int
    passed: int
    rc_counterfactual_passes: int
    outcome: str
    stage_histogram: dict
    first_pass: dict | None
    explanation: str
    rows: list = field(default_factory=list)
    seconds: float = 0.0


def _validator_checks(detail: str):
    import re
    return tuple(sorted(set(re.findall(r"\b(C\d+)\b", detail))))


def run_brief(bid: str, inp: PipelineInput, max_candidates: int = 150, raw_cap: int = 800) -> BriefResult:
    t0 = time.monotonic()
    # ---- baseline (merged #142E pipeline, unchanged)
    base = run_band_pipeline(inp)
    if isinstance(base, PipelineSuccess):
        baseline = {"outcome": "PASS", "sized": sum(1 for r in base.records if r.stage_reached != "EMBEDDING") or 1,
                    "realized": 1, "spatial": base.spatial_preserved, "access": base.access_preserved}
    else:
        baseline = {"outcome": base.code, "stage": base.stage,
                    "sized": sum(1 for r in base.records if r.stage_reached != "EMBEDDING"),
                    "realized": sum(1 for r in base.records if r.stage_reached in ("REALIZATION", "VALIDATORS"))}
    # ---- F1: union of contacts
    spatial = {frozenset(e) for e in inp.required_edges}
    access = [(a, b) for a, b in inp.access_edges if a in inp.zones and b in inp.zones]
    union_edges = sorted({tuple(sorted(e)) for e in spatial} | {tuple(sorted((a, b))) for a, b in access})
    not_in_spatial = sum(1 for a, b in access if frozenset((a, b)) not in spatial)
    emb_u = embed_band(inp.zones, union_edges, max_candidates=max_candidates, raw_cap=raw_cap)
    if isinstance(emb_u, BandEmbeddingRefusal):
        emb_s = embed_band(inp.zones, inp.required_edges, max_candidates=max_candidates, raw_cap=raw_cap)
        s_code = emb_s.code if isinstance(emb_s, BandEmbeddingRefusal) else "OK"
        return BriefResult(bid, baseline, emb_u.code, emb_u.detail, not_in_spatial, 0, 0, {}, 0, 0, 0, 0,
                           f"ACCESS_SPATIAL_CONTRADICTION ({emb_u.code})" if s_code == "OK" else emb_u.code,
                           {"EMBEDDING": {emb_u.code: 1}}, None,
                           ("the spatial graph alone embeds but spatial ∪ access does not: the proposal's access "
                            "requirements contradict its adjacency under rectangles/bands" if s_code == "OK" else
                            "the spatial graph itself is refused"), [], round(time.monotonic() - t0, 2))
    # ---- F2/F3/F4: flags, orientation, hard filter
    rows: list[CandidateRow] = []
    flag_counts = Counter()
    for i, p in enumerate(emb_u.candidates):
        f = candidate_flags(p, inp)
        for k in ("entrance_now", "entrance_feasible", "access_contact_ok", "exposure_ok", "reachable_from_entrance", "all_rooms_have_legal_partner"):
            flag_counts[k] += bool(f[k])
        if f["safe_room_on_envelope"] is not None:
            flag_counts["safe_room_on_envelope"] += bool(f["safe_room_on_envelope"])
        hard = f["entrance_feasible"] and f["access_contact_ok"] and f["exposure_ok"] and f["reachable_from_entrance"] \
            and (f["safe_room_on_envelope"] is not False)
        flag_counts["hard_ok"] += hard
        rows.append(CandidateRow(i, "union", f, hard, (not f["entrance_now"]) and f["entrance_flip"]))
    fw, fd = inp.footprint_m
    bw, bd = fw + BUILDABLE_MARGIN_M, fd + BUILDABLE_MARGIN_M
    buildable = Rect(0, 0, m_to_u(bw), m_to_u(bd))
    roles = {z: zi.role for z, zi in inp.zones.items()}
    hist: dict[str, Counter] = {"SIZING": Counter(), "REALIZATION": Counter(), "VALIDATORS": Counter()}
    sizable = realized = passed = rc = 0
    detail_samples: list[str] = []
    conflicts = access_policy_conflicts(inp)
    first_pass = None
    for row in rows:
        if not row.hard_ok:
            continue
        p = emb_u.candidates[row.index]
        if row.oriented:
            p = flipped(p)
        sz = solve_band_layout_doors(p.bands, inp.zones, [tuple(e) for e in spatial], access, w_max_m=bw, h_max_m=bd)
        row.sizing = sz.status
        if sz.status != "FEASIBLE":
            hist["SIZING"][sz.status] += 1
            continue
        sizable += 1
        W_m = round(sum(sz.col_w_u) * 0.05, 2); H_m = round(sum(sz.row_h_u) * 0.05, 2)
        wing = GridWing(bid, W_m, H_m, sz.n_cols, tuple(tuple(GridCell(z, s) for z, s in r) for r in sz.rows), inp.zones)
        row_h, col_w = list(sz.row_h_u), list(sz.col_w_u)
        # EXPERIMENT-ONLY injection (as #142D): the production `_build_grid_wing` re-solves the sizing
        # from the GridWing's columns and knows nothing of door widths, so the door-aware widths are
        # handed to it for this one call; every check downstream is unchanged production code.
        with mock.patch.object(rr, "_solve_grid", lambda w: (row_h, col_w)):
            res = realize_layout(RealizationIntent(name=bid, wings=(wing,), wet_rooms=inp.wet_rooms), buildable=buildable)
        if isinstance(res, RealizedLayout):
            realized += 1; passed += 1; rc += 1
            row.outcome = "PASS"; row.rc_counterfactual_pass = True
            sp = measure_spatial_adjacency(res.rects, frozenset(frozenset(e) for e in inp.required_edges))
            ac = measure_access_graph(res.fixture.access.edges, access)
            row.spatial, row.access = f"{sp.preserved}/{sp.requested}", f"{ac.preserved}/{ac.requested}"
            if first_pass is None:
                first_pass = {"candidate": row.index, "oriented": row.oriented, "rows": sz.rows, "envelope_m": [W_m, H_m],
                              "spatial": row.spatial, "access": row.access,
                              "rects_m": {k: [round(r.x * 0.05, 2), round(r.y * 0.05, 2), round(r.w * 0.05, 2), round(r.h * 0.05, 2)] for k, r in sorted(res.rects.items())}}
            continue
        assert isinstance(res, Refusal)
        row.outcome = res.constraint
        if res.constraint == "VALIDATION_FAILED":
            realized += 1
            row.failed_checks = _validator_checks(res.detail)
            if len(detail_samples) < 3:
                detail_samples.append(f"candidate {row.index}: {res.detail[:400]}")
            hist["VALIDATORS"]["+".join(row.failed_checks)] += 1
            if row.failed_checks == ("C4",):
                row.rc_counterfactual_pass = True; rc += 1
        elif res.constraint in ("AREA_INFEASIBLE", "SHORT_SIDE_INFEASIBLE", "GRID_INFEASIBLE", "GRID_SIZING_UNKNOWN"):
            hist["SIZING"][res.constraint] += 1
        else:
            hist["REALIZATION"][res.constraint] += 1
    hard_feasible = sum(1 for r in rows if r.hard_ok)
    if passed:
        outcome = "PASS"
    elif rc:
        outcome = "FAILS_ONLY_C4"
    elif realized:
        top = hist["VALIDATORS"].most_common(1)[0][0]
        outcome = "VALIDATION_FAILED " + top
    elif sizable:
        outcome = "REALIZATION_FAILED " + (hist["REALIZATION"].most_common(1)[0][0] if hist["REALIZATION"] else "")
    elif hard_feasible:
        outcome = "SIZING_INFEASIBLE (door-aware)"
    elif conflicts:
        outcome = "ACCESS_POLICY_CONFLICT " + "; ".join(f"{a}->{b}: {why}" for a, b, why in conflicts)
    else:
        # which hard flag kills every candidate?
        kills = {k: len(rows) - flag_counts[k] for k in ("entrance_feasible", "access_contact_ok", "exposure_ok", "reachable_from_entrance")}
        outcome = "NO_HARD_FEASIBLE_CANDIDATE " + ", ".join(f"{k}:{v} fail" for k, v in kills.items() if v)
    return BriefResult(bid, baseline, "OK", f"{len(emb_u.candidates)} candidates / {emb_u.layouts_found} layouts, complete={emb_u.search_complete}",
                       not_in_spatial, len(rows), hard_feasible, dict(flag_counts), sizable, realized, passed, rc,
                       outcome, {k: dict(v) for k, v in hist.items() if v}, first_pass,
                       " | ".join(detail_samples) + (" | POLICY: " + "; ".join(f"{a}->{b}" for a, b, _ in conflicts) if conflicts else ""),
                       [asdict(r) for r in rows], round(time.monotonic() - t0, 2))


def main(out_json: str | None = None, briefs: tuple[str, ...] | None = None, max_candidates: int = 150, raw_cap: int = 800):
    fx = json.load(open(FIXTURE))
    results = []
    for bid in sorted(fx["briefs"]):
        if briefs and bid not in briefs:
            continue
        inp = load_brief(bid, fx["briefs"][bid])
        r = run_brief(bid, inp, max_candidates=max_candidates, raw_cap=raw_cap)
        results.append(r)
        print(f"{bid}: E={r.baseline['outcome']} | F={r.outcome} | union={r.union_embedding} access∉spatial={r.access_pairs_not_in_spatial} "
              f"cand={r.candidates} hard={r.hard_feasible} sizable={r.sizable} realized={r.realized} pass={r.passed} rc={r.rc_counterfactual_passes} "
              f"| flags {r.flag_counts} | {r.seconds}s", flush=True)
    if out_json:
        os.makedirs(os.path.dirname(out_json), exist_ok=True)
        json.dump([asdict(r) for r in results], open(out_json, "w"), indent=1, default=str)
    return results


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else None,
         tuple(sys.argv[2].split(",")) if len(sys.argv) > 2 and sys.argv[2] != "-" else None,
         int(sys.argv[3]) if len(sys.argv) > 3 else 150, int(sys.argv[4]) if len(sys.argv) > 4 else 800)
