"""#142D — exact per-cell band sizing POC: `exact topology witness -> exact per-cell sizing ->
existing realization -> unchanged validators`, every band-representable frozen brief, every witness.

Primary question: with band topology fixed and valid, can an independent per-cell sizing replace
`_solve_grid`'s rank-1 proportional fit and materially unlock the existing realization pipeline?

The sizing oracle (`backend/spikes/topology_representation/cell_sizing_oracle.py`) is experimental and
isolated; it decides per witness whether ANY band heights / column widths satisfy the realizer's own
per-cell checks (certificates -> alternating LP -> exact branch-and-bound). A feasible sizing is
handed to the UNCHANGED `realize_layout` by replacing `_solve_grid` for the duration of that one
call (`unittest.mock.patch.object` — an experiment-only injection, `app/vertical_slice` is not
modified); everything after the sizing step — `_build_grid_wing`'s own re-checks, walls, access edges,
entrance, doors, windows, furniture, `validate` — is production code.

Every failed brief ends in exactly one category:
  SIZING_MODEL_LIMIT     a feasible sizing exists (or may exist: oracle UNKNOWN) that the experimental
                         solver could not find / express within its limits
  BAND_GEOMETRY_LIMIT    topology is band-representable, but no witness in the (complete) band family
                         has a geometrically valid sizing — with the oracle's proof per witness
  UNKNOWN_WITHIN_SEARCH_BOUND  as above, but the witness family was NOT exhausted
  DOWNSTREAM_CONSTRAINT  sizing succeeded for >= 1 witness; realization/validators rejected every one

Two result sets are kept apart: PRODUCTION semantics (the oracle enforces exactly what
`_build_grid_wing` checks: GROSS cell area vs the zone's bounds, short side) and a CORRECTED-semantics
counterfactual (NET area as validator C3 reads it, plus the validators' max aspect). A third, clearly
labelled pass re-orders witnesses by entrance/access plausibility (§9) without changing any constraint.
"""
from __future__ import annotations

import dataclasses
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from unittest import mock

from app.vertical_slice import rectilinear_realizer as rr
from app.vertical_slice.geometry_core.model import Rect, m_to_u
from app.vertical_slice.topology_preservation import measure_access_graph, measure_spatial_adjacency

from . import generation_dataset, priors as priors_mod, schema
from .exact_band_142c import verify_embedding
from .gap_closure_142a import _zones_for, best_policy_valid_proposal, resolve_wet_rooms
from app.vertical_slice import access_rules
from app.vertical_slice.doors import ALLOWED_ENTRANCE_ROLES
from app.vertical_slice.exposure_policy import REQUIRED_EXTERIOR_ROLES
from app.vertical_slice.geometry_core.model import ProgramRole

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_REPO_ROOT = os.path.dirname(_BACKEND_DIR)
REPORT_DIR = os.path.join(_REPO_ROOT, "docs", "reports", "142d-exact-cell-sizing")
SPIKES_DIR = os.path.join(_BACKEND_DIR, "spikes", "topology_representation")
sys.path.insert(0, SPIKES_DIR)
from cell_sizing_oracle import Semantics, build_cells, check_point, decide, to_units  # noqa: E402

STAGES = ("EMBEDDING", "SIZING", "REALIZATION", "VALIDATORS")

#: Net insets per side (geometry_core.model: half wall thickness — EXTERIOR 0.30/2, PARTITION 0.10/2).
_INSET_EXTERIOR_M = 0.15
_INSET_PARTITION_M = 0.05


def cell_insets(rows, n_cols) -> tuple[dict, dict]:
    """Per zone: total horizontal / vertical net inset implied by the witness's own wall typing
    (`realize_layout`: EXTERIOR where no cell touches that side, PARTITION otherwise)."""
    R = len(rows); bw = {}; bh = {}
    for r, row in enumerate(rows):
        c0 = 0
        for zid, span in row:
            c1 = c0 + int(span)
            bw[zid] = (_INSET_EXTERIOR_M if c0 == 0 else _INSET_PARTITION_M) + (_INSET_EXTERIOR_M if c1 == n_cols else _INSET_PARTITION_M)
            bh[zid] = (_INSET_EXTERIOR_M if r == 0 else _INSET_PARTITION_M) + (_INSET_EXTERIOR_M if r == R - 1 else _INSET_PARTITION_M)
            c0 = c1
    return bw, bh


def witness_flags(rows, n_cols, roles: dict, wet_rooms) -> dict:
    """Topology-level §9 properties of a witness (measured, never enforced):
    entrance_ok  — a HALL/CIRCULATION/LIVING cell lies in row 0 (the street band: `resolve_entrance`
                   reads the footprint's y=min edge, which is `GridWing.rows[0]`)
    access_ok    — every room touches >= 1 room it may legally be entered from (`edge_role_pair_allowed`,
                   narrowed for wet rooms exactly as `_filter_wet_room_access` does)
    exposure_ok  — every REQUIRED_EXTERIOR role cell touches the envelope (C19/C8 precondition)"""
    R = len(rows)
    cells = {}
    for r, row in enumerate(rows):
        c0 = 0
        for zid, span in row:
            cells[zid] = (r, c0, c0 + int(span)); c0 += int(span)
    def touch(a, b):
        ra, a0, a1 = cells[a]; rb, b0, b1 = cells[b]
        if ra == rb:
            return a1 == b0 or b1 == a0
        return abs(ra - rb) == 1 and a0 < b1 and b0 < a1
    wet = {w.zone_id: w for w in wet_rooms}
    def legal(a, b):
        if not access_rules.edge_role_pair_allowed((roles[a],), (roles[b],)):
            return False
        for x, y in ((a, b), (b, a)):
            if x in wet:
                wr = wet[x]
                if wr.host_zone is not None:
                    if y != wr.host_zone: return False
                elif roles[y] not in (ProgramRole.HALL, ProgramRole.CIRCULATION): return False
        return True
    ids = list(cells)
    entrance_ok = any(roles[z] in ALLOWED_ENTRANCE_ROLES for z, (r, _a, _b) in cells.items() if r == 0)
    access_ok = all(any(touch(a, b) and legal(a, b) for b in ids if b != a) for a in ids)
    exposure_ok = all((r == 0 or r == R - 1 or c0 == 0 or c1 == n_cols) for z, (r, c0, c1) in cells.items()
                      if roles[z] in REQUIRED_EXTERIOR_ROLES)
    return {"entrance_ok": entrance_ok, "access_ok": access_ok, "exposure_ok": exposure_ok}
_SIZING = {"AREA_INFEASIBLE", "SHORT_SIDE_INFEASIBLE", "GRID_INFEASIBLE", "GRID_ROW_SPAN_MISMATCH", "EMPTY_GRID"}


def stage_of(constraint: str) -> str:
    if constraint in _SIZING:
        return "SIZING"
    if constraint == "VALIDATION_FAILED":
        return "VALIDATORS"
    return "REALIZATION"


@dataclass
class WitnessOutcome:
    index: int
    n_rows: int
    n_cols: int
    oracle_status: str                 # FEASIBLE | INFEASIBLE | UNKNOWN
    oracle_method: str
    certificate: "str | None"
    sizing_m: "dict | None"            # {"h": [...], "w": [...]} (metres) when FEASIBLE
    envelope_m: "str | None"
    stage_reached: str                 # furthest stage PASSED (EMBEDDING if sizing failed)
    refusal: "str | None"
    refusal_detail: "str | None"
    validator_failed_checks: list = field(default_factory=list)
    spatial: "str | None" = None
    access: "str | None" = None
    access_lost: list = field(default_factory=list)
    rects_m: "dict | None" = None
    flags: dict = field(default_factory=dict)


@dataclass
class BriefOutcome:
    brief_id: str
    semantics: str
    n: int
    m: int
    family_complete: bool
    witnesses_examined: int
    oracle: dict                       # FEASIBLE / INFEASIBLE / UNKNOWN counts, by method
    sizing_pass: int                   # realizer's own `_build_grid_wing` accepted the injected sizing
    realization_pass: int
    validator_pass: int
    first_success: "dict | None"
    dominant_rejections: dict          # stage -> {reason: count}
    category: str
    outcomes: list
    seconds: float
    flags_count: dict = field(default_factory=dict)


def _validator_failures(detail: str) -> list[str]:
    import re
    return sorted({t for t in re.findall(r"\b(C\d+)\b", detail)})


def run_witness(bid, idx, witness, zones, wet_rooms, edges, access_edges, buildable, zones_bounds,
                sem: Semantics, w_max, h_max, node_limit, time_limit) -> WitnessOutcome:
    rows = [[(z, int(s)) for z, s in witness["rows"]] for row in [None]][0] if False else \
        [[(z, int(s)) for z, s in row] for row in witness["rows"]]
    n_cols = int(witness["n_cols"])
    ok, missing = verify_embedding(rows, n_cols, edges)
    assert ok, f"{bid} witness {idx} does not carry {missing}"
    if sem.area == "net":
        bw, bh = cell_insets(rows, n_cols)
        ng = getattr(sem, "net_gate", False)
        sem = Semantics(area="net", aspect=sem.aspect, net_inset_w=bw, net_inset_h=bh, label=sem.label)
        sem.net_gate = ng
    d = decide(rows, n_cols, zones_bounds, w_max, h_max, sem, node_limit=node_limit, time_limit=time_limit)
    wo = WitnessOutcome(idx, len(rows), n_cols, d["status"], d.get("method", "?"), d.get("certificate"),
                        None, None, "EMBEDDING", None, None)
    wo.flags = witness_flags(rows, n_cols, {z: zi.role for z, zi in zones.items()}, wet_rooms)
    if d["status"] != "FEASIBLE":
        return wo
    h_m, w_m = d["h"], d["w"]
    wo.sizing_m = {"h": [round(x, 3) for x in h_m], "w": [round(x, 3) for x in w_m]}
    W = round(sum(w_m), 2); H = round(sum(h_m), 2)
    row_h = to_units(h_m, m_to_u(H)); col_w = to_units(w_m, m_to_u(W))
    wo.envelope_m = f"{W}x{H} m"
    grid_rows = tuple(tuple(rr.GridCell(z, s) for z, s in row) for row in rows)
    wing = rr.GridWing(wing_id=bid, width_m=W, height_m=H, n_cols=n_cols, rows=grid_rows, zones=zones)

    def injected(w_u, h_u, rows_, n_cols_, zones_, min_short_u):
        return row_h, col_w

    patches = [mock.patch.object(rr, "_solve_grid", injected)]
    if getattr(sem, "net_gate", False):
        # COUNTERFACTUAL (clearly labelled, experiment-only): make `_build_grid_wing`'s AREA and
        # SHORT-SIDE gates consistent with the NET semantics the validators use — both gates are skipped
        # (bounds widened for the gate call only) and the true ZoneSpecs are restored for everything
        # downstream, so C3/C20/C21 still judge the room on its real net bounds. No production change.
        original_build = rr._build_grid_wing

        def build_with_net_gate(w, origin):
            # area AND short-side gates skipped for the gate call (the oracle already guaranteed NET area and
            # NET short side with the witness's real insets; C3 re-checks both on net downstream)
            widened = {z: dataclasses.replace(zi, min_area_m2=0.0, max_area_m2=1e6, min_short_side_m=0.0) for z, zi in w.zones.items()}
            wb = original_build(dataclasses.replace(w, zones=widened), origin)
            if isinstance(wb, rr.Refusal):
                return wb
            true_specs = {z: rr._zone_spec(zi) for z, zi in w.zones.items()}
            return dataclasses.replace(wb, specs=true_specs)
        patches.append(mock.patch.object(rr, "_build_grid_wing", build_with_net_gate))
    with patches[0]:
        if len(patches) > 1:
            patches[1].start()
        try:
            res = rr.realize_layout(rr.RealizationIntent(name=bid, wings=(wing,), wet_rooms=wet_rooms),
                                    buildable=buildable)
        finally:
            if len(patches) > 1:
                patches[1].stop()
    if isinstance(res, rr.RealizedLayout):
        sp = measure_spatial_adjacency(res.rects, frozenset(frozenset(e) for e in edges))
        ac = measure_access_graph(res.fixture.access.edges, access_edges)
        wo.stage_reached = "VALIDATORS"
        wo.spatial = f"{sp.preserved}/{sp.requested}"; wo.access = f"{ac.preserved}/{ac.requested}"
        wo.access_lost = sorted(str(e) for e in ac.lost)
        wo.rects_m = {k: {"x": round(r.x * 0.05, 2), "y": round(r.y * 0.05, 2), "w": round(r.w * 0.05, 2),
                          "d": round(r.h * 0.05, 2), "area_m2": round(r.area_m2(), 2)} for k, r in sorted(res.rects.items())}
        return wo
    wo.refusal = res.constraint; wo.refusal_detail = res.detail[:400]
    st = stage_of(res.constraint)
    wo.stage_reached = {"SIZING": "EMBEDDING", "REALIZATION": "SIZING", "VALIDATORS": "REALIZATION"}[st]
    if st == "VALIDATORS":
        wo.validator_failed_checks = _validator_failures(res.detail)
    return wo


def run_brief(record, proposal, wrec, sem: Semantics, max_witnesses, node_limit, time_limit,
              order=None) -> BriefOutcome:
    t0 = time.time()
    bid = record["brief_id"]
    zones = _zones_for(proposal)
    zones_bounds = {z: {"min": zi.min_area_m2, "max": zi.max_area_m2, "target": zi.target_area_m2,
                        "min_short": zi.min_short_side_m, "max_aspect": zi.max_aspect_ratio}
                    for z, zi in zones.items()}
    edges = [tuple(e) for e in wrec["edges"]]
    wet_rooms = resolve_wet_rooms(proposal)
    fw, fd = record["brief"]["footprint_width_m"], record["brief"]["footprint_depth_m"]
    w_max, h_max = fw + 4.0, fd + 4.0
    buildable = Rect(0, 0, m_to_u(fw) + m_to_u(4.0), m_to_u(fd) + m_to_u(4.0))
    access_edges = [(a, b) for a, b in proposal.access_graph if a != schema.ENTRANCE_ID]
    witnesses = list(enumerate(wrec["witnesses"]))
    if order == "counterfactual":
        roles = {z: zi.role for z, zi in zones.items()}
        def key(item):
            i, wt = item
            rows_ = [[(z, int(s_)) for z, s_ in row] for row in wt["rows"]]
            f = witness_flags(rows_, int(wt["n_cols"]), roles, wet_rooms)
            return (not f["entrance_ok"], not f["access_ok"], not f["exposure_ok"], wt["score"])
        witnesses.sort(key=key)
    witnesses = witnesses[:max_witnesses]
    outcomes = []
    oracle = {"FEASIBLE": 0, "INFEASIBLE": 0, "UNKNOWN": 0, "by_method": {}}
    rej = {s: {} for s in STAGES}
    first = None
    for idx, wt in witnesses:
        wo = run_witness(bid, idx, wt, zones, wet_rooms, edges, access_edges, buildable, zones_bounds,
                         sem, w_max, h_max, node_limit, time_limit)
        outcomes.append(wo)
        oracle[wo.oracle_status] += 1
        oracle["by_method"][wo.oracle_method] = oracle["by_method"].get(wo.oracle_method, 0) + 1
        if wo.refusal:
            st = stage_of(wo.refusal)
            key = wo.refusal if st != "VALIDATORS" else "VALIDATION_FAILED " + "+".join(wo.validator_failed_checks)
            rej[st][key] = rej[st].get(key, 0) + 1
        if wo.stage_reached == "VALIDATORS" and first is None:
            first = asdict(wo)
    sizing_pass = sum(1 for o in outcomes if o.stage_reached in ("SIZING", "REALIZATION", "VALIDATORS"))
    realization_pass = sum(1 for o in outcomes if o.stage_reached in ("REALIZATION", "VALIDATORS"))
    validator_pass = sum(1 for o in outcomes if o.stage_reached == "VALIDATORS")
    complete = bool(wrec.get("enumeration", {}).get("complete"))
    if validator_pass:
        category = "PASS"
    elif sizing_pass:
        category = "DOWNSTREAM_CONSTRAINT"
    elif oracle["FEASIBLE"]:
        category = "SIZING_MODEL_LIMIT (feasible per oracle, rejected by _build_grid_wing after unit rounding)"
    elif oracle["UNKNOWN"]:
        category = "SIZING_MODEL_LIMIT (oracle UNKNOWN within limits)"
    elif complete and len(witnesses) == len(wrec["witnesses"]):
        category = "BAND_GEOMETRY_LIMIT"
    else:
        category = "UNKNOWN_WITHIN_SEARCH_BOUND"
    # dominant: only non-empty stages
    dominant = {s: dict(sorted(v.items(), key=lambda kv: -kv[1])[:6]) for s, v in rej.items() if v}
    flags_count = {k: sum(1 for o in outcomes if o.flags.get(k)) for k in ("entrance_ok", "access_ok", "exposure_ok")}
    flags_count["all_three"] = sum(1 for o in outcomes if all(o.flags.get(k) for k in ("entrance_ok", "access_ok", "exposure_ok")))
    bo = BriefOutcome(bid, sem.label, wrec["n"], wrec["m"], complete, len(outcomes), oracle, sizing_pass,
                      realization_pass, validator_pass, first, dominant, category,
                      [asdict(o) for o in outcomes], round(time.time() - t0, 1))
    bo.flags_count = flags_count
    return bo


def load_witness_sets(paths: list[str]) -> dict:
    merged = {}
    sha = None
    for p in paths:
        w = json.load(open(p))
        sha = sha or w["dataset_sha256"]
        assert w["dataset_sha256"] == sha
        for bid, rec in w["briefs"].items():
            if rec["classification"] == "BAND_REPRESENTABLE":
                if bid not in merged or len(rec["witnesses"]) > len(merged[bid]["witnesses"]):
                    merged[bid] = rec
    return {"dataset_sha256": sha, "briefs": merged}


def run_all(witness_paths, sem: Semantics, max_witnesses=5000, node_limit=4000, time_limit=30.0,
            brief_ids=None, orders=None) -> list[BriefOutcome]:
    wit = load_witness_sets(witness_paths)
    dataset = generation_dataset.load_dataset(generation_dataset.DEFAULT_GENERATION_DATASET_JSON)
    assert wit["dataset_sha256"] == dataset["dataset_sha256"]
    pri = priors_mod.load_priors()
    out = []
    for record in dataset["records"]:
        bid = record["brief_id"]
        if bid not in wit["briefs"] or (brief_ids and bid not in brief_ids):
            continue
        proposal = best_policy_valid_proposal(record, pri)
        wrec = wit["briefs"][bid]
        assert sorted(sorted(e) for e in proposal.spatial_adjacency) == sorted(sorted(e) for e in wrec["edges"])
        bo = run_brief(record, proposal, wrec, sem, max_witnesses, node_limit, time_limit, order=orders)
        out.append(bo)
        print(f"[{sem.label}] {bid}: examined {bo.witnesses_examined} (family complete={bo.family_complete}) "
              f"oracle {bo.oracle['FEASIBLE']}F/{bo.oracle['INFEASIBLE']}I/{bo.oracle['UNKNOWN']}U "
              f"sizing {bo.sizing_pass} realization {bo.realization_pass} validators {bo.validator_pass} "
              f"-> {bo.category} ({bo.seconds}s)", flush=True)
    return out


__all__ = ["run_all", "run_brief", "BriefOutcome", "WitnessOutcome", "Semantics", "STAGES", "REPORT_DIR"]
