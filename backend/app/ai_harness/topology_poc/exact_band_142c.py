"""#142C — exact band embedding through the UNCHANGED GridWing path (bounded experiment driver).

One question: does an EXACT band embedding (a `GridWing` that provably carries every required
spatial-adjacency edge) unlock the existing `GridWing` -> `_solve_grid` -> `realize_layout` ->
`validate` path for the topologies GridWing already has the expressive power to represent?

Stages, reported separately for every brief (a downstream failure is never a topology failure):

    GRAPH -> EXACT BAND EMBEDDING -> GRIDWING SIZING -> REALIZATION -> VALIDATORS

The exact embedding is NOT computed here. It is read from a committed witness artifact produced by
the isolated SAT prototype (`backend/spikes/topology_representation/band_witnesses.py`, `python-sat`
in a scratch venv) — so no solver dependency enters the project. Every witness is re-verified here,
geometrically, with the realizer's own `Rect.shared_edge_len_u`, before it is trusted (EMBEDDING
stage PASS means: this module confirmed every required edge is a positive-length shared boundary of
the witness's own cell grid). Briefs the prototype proved UNSAT are reported as
`UNSAT — REPRESENTATION_LIMIT` (K4 / triple-lens obstruction) or `UNSAT — NON_PLANAR_TOPOLOGY`,
never attempted, never weakened.

Downstream is the unchanged #142A machinery: `GridWing` + `realize_layout` (every refusal below is
that function's own), the same `ROOM_TEMPLATES` zone bounds, the same wet-room resolution, the same
`buildable` (brief footprint + 4 m) — plus a caller-side envelope ladder (scale x aspect over the
rooms' own total target area), the same "retry a fully specified envelope, never approximate"
discipline `gap_closure_142a` and `stage1_gate` use. Witness order is the prototype's generic
plausibility ranking; no witness or envelope is chosen per brief by hand.

No validator, access rule, room minimum, wet-core rule, critic or proposal datum changes.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field

from app.vertical_slice.geometry_core.model import Rect, m_to_u
from app.vertical_slice.rectilinear_realizer import (
    GridCell,
    GridWing,
    RealizationIntent,
    RealizedLayout,
    Refusal,
    realize_layout,
)
from app.vertical_slice.topology_preservation import measure_access_graph, measure_spatial_adjacency

from . import generation_dataset, priors as priors_mod, schema
from .gap_closure_142a import (
    _DIMENSION_SOLVER_CONSTRAINTS,
    _zones_for,
    best_policy_valid_proposal,
    resolve_wet_rooms,
)

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_REPO_ROOT = os.path.dirname(_BACKEND_DIR)
REPORT_DIR = os.path.join(_REPO_ROOT, "docs", "reports", "142c-exact-band-embedding")
DEFAULT_WITNESSES_JSON = os.path.join(REPORT_DIR, "witnesses.json")
DEFAULT_RESULTS_JSON = os.path.join(REPORT_DIR, "results.json")
DEFAULT_RESULTS_MD = os.path.join(REPORT_DIR, "results.md")

#: Caller-side envelope ladder over the rooms' own total TARGET area: scale (envelope area / total
#: target) x aspect (width / height). Fully specified envelopes, tried in this fixed order for every
#: witness of every brief; nothing inside the realizer approximates.
_SCALES = (1.0, 0.9, 1.1, 0.8, 1.2, 0.75, 1.3, 0.7, 1.4, 0.6, 1.5)
_ASPECTS = (1.0, 1.25, 0.8, 1.5, 0.67, 1.75, 0.57, 2.0, 0.5)

#: Stage names in pipeline order.
STAGES = ("EMBEDDING", "SIZING", "REALIZATION", "VALIDATORS")

#: `realize_layout` refusal constraints that belong to the SIZING stage (`_build_grid_wing`'s own
#: build-then-check: `_solve_grid` and the per-cell area / short-side bounds).
_SIZING_CONSTRAINTS = _DIMENSION_SOLVER_CONSTRAINTS | {"GRID_ROW_SPAN_MISMATCH", "EMPTY_GRID"}


def stage_of_refusal(constraint: str) -> str:
    if constraint in _SIZING_CONSTRAINTS:
        return "SIZING"
    if constraint == "VALIDATION_FAILED":
        return "VALIDATORS"
    return "REALIZATION"   # ENVELOPE_TOO_LARGE, NO_ENTRANCE, internal construction defects


@dataclass
class WitnessResult:
    index: int
    score: float
    n_rows: int
    n_cols: int
    embedding_verified: bool
    envelopes_tried: int = 0
    best_stage_reached: str = "EMBEDDING"          # furthest stage that PASSED
    refusals: dict = field(default_factory=dict)    # constraint -> count over envelopes
    first_sizing_pass_envelope: "str | None" = None
    success_envelope: "str | None" = None
    spatial: "str | None" = None
    access: "str | None" = None
    access_lost: list = field(default_factory=list)
    rects_m: "dict | None" = None
    validator_failures_sample: list = field(default_factory=list)


@dataclass
class BriefResult:
    brief_id: str
    n: int
    m: int
    classification: str
    reason: str
    stage_pass: dict                       # stage -> True/False/None (None = not applicable)
    witnesses_available: int
    witnesses_tried: int
    witness_results: list
    success: bool
    success_witness: "int | None"
    stage_histogram: dict                  # stage -> {constraint: count}
    a142_result: str
    seconds: float


def _unit_rects(rows, n_cols) -> dict[str, Rect]:
    rects = {}
    for r_idx, row in enumerate(rows):
        c0 = 0
        for zid, span in row:
            rects[zid] = Rect(c0, r_idx, span, 1)
            c0 += span
        if c0 != n_cols:
            raise ValueError(f"row {r_idx} spans sum to {c0}, not n_cols={n_cols}")
    return rects


def verify_embedding(rows, n_cols, edges) -> tuple[bool, list]:
    """EMBEDDING stage: every required pair shares a positive-length boundary in the witness's own
    cell grid, by the realizer's own `Rect.shared_edge_len_u` (the same test `_build_grid_wing` and
    `measure_spatial_adjacency` apply to real rects)."""
    rects = _unit_rects(rows, n_cols)
    missing = [e for e in edges if rects[e[0]].shared_edge_len_u(rects[e[1]]) <= 0]
    return not missing, missing


def _envelopes(total_target_m2: float, buildable: Rect) -> list[tuple[float, float]]:
    out = []
    for s in _SCALES:
        for a in _ASPECTS:
            area = total_target_m2 * s
            w = round((area * a) ** 0.5, 1); h = round((area / a) ** 0.5, 1)
            if m_to_u(w) > buildable.w or m_to_u(h) > buildable.h:
                continue
            out.append((w, h))
    return out


def run_witness(brief_id, idx, witness, zones, wet_rooms, edges, access_edges, buildable,
                envelopes) -> WitnessResult:
    rows = [[(z, int(s)) for z, s in row] for row in witness["rows"]]
    n_cols = int(witness["n_cols"])
    wr = WitnessResult(idx, witness["score"], len(rows), n_cols, False)
    ok, missing = verify_embedding(rows, n_cols, edges)
    wr.embedding_verified = ok
    if not ok:
        wr.refusals["EMBEDDING_NOT_VERIFIED"] = len(missing)
        return wr
    grid_rows = tuple(tuple(GridCell(z, s) for z, s in row) for row in rows)
    best = 0
    for (w_m, h_m) in envelopes:
        wing = GridWing(wing_id=brief_id, width_m=w_m, height_m=h_m, n_cols=n_cols, rows=grid_rows,
                        zones=zones)
        res = realize_layout(RealizationIntent(name=brief_id, wings=(wing,), wet_rooms=wet_rooms),
                             buildable=buildable)
        wr.envelopes_tried += 1
        if isinstance(res, RealizedLayout):
            sp = measure_spatial_adjacency(res.rects, frozenset(frozenset(e) for e in edges))
            ac = measure_access_graph(res.fixture.access.edges, access_edges)
            wr.success_envelope = f"{w_m}x{h_m} m"
            wr.best_stage_reached = "VALIDATORS"
            wr.spatial = f"{sp.preserved}/{sp.requested}"
            wr.access = f"{ac.preserved}/{ac.requested}"
            wr.access_lost = sorted(list(e) for e in ac.lost)
            wr.rects_m = {k: {"x": round(r.x * 0.05, 2), "y": round(r.y * 0.05, 2),
                              "w": round(r.w * 0.05, 2), "d": round(r.h * 0.05, 2),
                              "area_m2": round(r.area_m2(), 2)} for k, r in sorted(res.rects.items())}
            if wr.first_sizing_pass_envelope is None:
                wr.first_sizing_pass_envelope = wr.success_envelope
            return wr
        assert isinstance(res, Refusal)
        wr.refusals[res.constraint] = wr.refusals.get(res.constraint, 0) + 1
        stage = stage_of_refusal(res.constraint)
        reached = {"SIZING": 1, "REALIZATION": 2, "VALIDATORS": 3}[stage]   # stage that FAILED
        # the furthest PASSED stage is the one before the failing stage
        if reached - 1 > best:
            best = reached - 1
        if stage != "SIZING" and wr.first_sizing_pass_envelope is None:
            wr.first_sizing_pass_envelope = f"{w_m}x{h_m} m"
        if stage == "VALIDATORS" and len(wr.validator_failures_sample) < 3:
            wr.validator_failures_sample.append(f"{w_m}x{h_m} m: {res.detail}")
    wr.best_stage_reached = STAGES[best]
    return wr


def run_brief(record, proposal, wrec, a142_result: str, max_witnesses: int) -> BriefResult:
    t0 = time.time()
    bid = record["brief_id"]
    zones = _zones_for(proposal)
    edges = [tuple(e) for e in wrec["edges"]]
    cls = wrec["classification"]
    stage_pass = {s: None for s in STAGES}
    if cls != "BAND_REPRESENTABLE":
        stage_pass["EMBEDDING"] = False
        label = {"NON_PLANAR": "UNSAT — NON_PLANAR_TOPOLOGY",
                 "RECTANGULAR_OBSTRUCTION": "UNSAT — REPRESENTATION_LIMIT",
                 "BAND_UNSAT": "UNSAT — BAND_LIMIT"}[cls]
        return BriefResult(bid, wrec["n"], wrec["m"], label, wrec["reason"], stage_pass, 0, 0, [],
                           False, None, {}, a142_result, round(time.time() - t0, 1))

    wet_rooms = resolve_wet_rooms(proposal)
    fw, fd = record["brief"]["footprint_width_m"], record["brief"]["footprint_depth_m"]
    buildable = Rect(0, 0, m_to_u(fw) + m_to_u(4.0), m_to_u(fd) + m_to_u(4.0))
    total_target = sum(z.target_area_m2 for z in zones.values())
    envelopes = _envelopes(total_target, buildable)
    access_edges = [(a, b) for a, b in proposal.access_graph if a != schema.ENTRANCE_ID]

    results: list[WitnessResult] = []
    hist: dict[str, dict] = {s: {} for s in STAGES}
    success_idx = None
    for idx, witness in enumerate(wrec["witnesses"][:max_witnesses]):
        wr = run_witness(bid, idx, witness, zones, wet_rooms, edges, access_edges, buildable, envelopes)
        results.append(wr)
        for c, k in wr.refusals.items():
            st = "EMBEDDING" if c == "EMBEDDING_NOT_VERIFIED" else stage_of_refusal(c)
            hist[st][c] = hist[st].get(c, 0) + k
        if wr.success_envelope is not None:
            success_idx = idx
            break

    stage_pass["EMBEDDING"] = any(r.embedding_verified for r in results)
    order = {s: i for i, s in enumerate(STAGES)}
    furthest = max((order[r.best_stage_reached] for r in results), default=0)
    stage_pass["SIZING"] = furthest >= 1
    stage_pass["REALIZATION"] = furthest >= 2
    stage_pass["VALIDATORS"] = furthest >= 3
    return BriefResult(bid, wrec["n"], wrec["m"], "BAND_REPRESENTABLE", "", stage_pass,
                       len(wrec["witnesses"]), len(results), [asdict(r) for r in results],
                       success_idx is not None, success_idx, hist, a142_result,
                       round(time.time() - t0, 1))


#: #142A's own per-brief outcome (docs/reports/142a-realizability-gap-closure/results.md) for the
#: comparison column; briefs #142A did not run are "not run".
_A142 = {"B01": "REFUSED DIMENSION_SOLVER (pinwheel, SHORT_SIDE_INFEASIBLE)",
         "B10": "REFUSED TOPOLOGY_EMBEDDING 9/14", "B13": "REFUSED TOPOLOGY_EMBEDDING 9/12",
         "B15": "REFUSED TOPOLOGY_EMBEDDING 9/15", "B16": "REFUSED TOPOLOGY_EMBEDDING 11/19"}


def run_all(witnesses_path: str = DEFAULT_WITNESSES_JSON, max_witnesses: int = 150,
            brief_ids: "tuple[str, ...] | None" = None) -> tuple[list[BriefResult], dict, dict]:
    wit = json.load(open(witnesses_path))
    dataset = generation_dataset.load_dataset(generation_dataset.DEFAULT_GENERATION_DATASET_JSON)
    if wit["dataset_sha256"] != dataset["dataset_sha256"]:
        raise RuntimeError("witness artifact was built from a different frozen dataset")
    pri = priors_mod.load_priors()
    out = []
    for record in dataset["records"]:
        bid = record["brief_id"]
        if brief_ids and bid not in brief_ids:
            continue
        proposal = best_policy_valid_proposal(record, pri)
        wrec = wit["briefs"][bid]
        # the witness artifact must describe THIS proposal's graph exactly
        if sorted(sorted(e) for e in proposal.spatial_adjacency) != sorted(sorted(e) for e in wrec["edges"]):
            raise RuntimeError(f"{bid}: witness artifact edges differ from the selected proposal")
        br = run_brief(record, proposal, wrec, _A142.get(bid, "not run"), max_witnesses)
        out.append(br)
        print(f"{bid}: {br.classification} stages={br.stage_pass} success={br.success} "
              f"(witnesses {br.witnesses_tried}/{br.witnesses_available}, {br.seconds}s)", flush=True)
    return out, wit, dataset


def render_md(results: list[BriefResult], wit: dict, dataset: dict) -> str:
    L = []
    L.append("# #142C — Exact band embedding through the unchanged GridWing path")
    L.append("")
    L.append("Question: does an exact band embedding unlock the existing `GridWing` -> `_solve_grid` -> "
             "`realize_layout` -> `validate` path for the topologies GridWing can already represent? "
             "Stages are reported separately; a downstream failure is never reported as a topology failure.")
    L.append("")
    L.append(f"Frozen dataset sha256 `{dataset['dataset_sha256']}` (same selection rule as #160/#142A: best "
             f"policy-valid proposal in each brief's top-8). Witness artifact: `witnesses.json` "
             f"(isolated SAT prototype, K={wit['K']} distinct band layouts per brief, {wit['seconds_cap']} s cap). "
             f"Envelope ladder: {len(_SCALES)} scales x {len(_ASPECTS)} aspects over the rooms' total target area, "
             f"bounded by the brief footprint + 4 m. Nothing in `app/vertical_slice` changed.")
    L.append("")
    band = [r for r in results if r.classification == "BAND_REPRESENTABLE"]
    n_emb = sum(1 for r in band if r.stage_pass["EMBEDDING"])
    n_siz = sum(1 for r in band if r.stage_pass["SIZING"])
    n_rea = sum(1 for r in band if r.stage_pass["REALIZATION"])
    n_val = sum(1 for r in band if r.stage_pass["VALIDATORS"])
    L.append("## Headline")
    L.append("")
    L.append(f"| stage | passed / band-representable briefs |")
    L.append("|---|---|")
    L.append(f"| exact band embedding (verified geometrically) | {n_emb}/{len(band)} |")
    L.append(f"| GridWing sizing (`_solve_grid` + per-cell bounds) | {n_siz}/{len(band)} |")
    L.append(f"| realization (footprint, entrance, doors, windows) | {n_rea}/{len(band)} |")
    L.append(f"| validators PASS (unchanged `validate`) | **{n_val}/{len(band)}** |")
    L.append("")
    L.append(f"Primary criterion (>= 9/13 band-representable briefs realized with validator PASS): "
             f"**{'MET' if n_val >= 9 else 'NOT MET'}** ({n_val}/{len(band)}).")
    L.append("")
    L.append("## Stage-by-stage matrix, all 20 briefs")
    L.append("")
    L.append("| brief | n | m | classification | EMBEDDING | SIZING | REALIZATION | VALIDATORS | witnesses tried/available | success envelope | spatial | access | #142A |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        def f(s):
            v = r.stage_pass[s]
            return "—" if v is None else ("PASS" if v else "FAIL")
        succ = next((w for w in r.witness_results if w["success_envelope"]), None)
        L.append(f"| {r.brief_id} | {r.n} | {r.m} | {r.classification} | {f('EMBEDDING')} | {f('SIZING')} | "
                 f"{f('REALIZATION')} | {f('VALIDATORS')} | {r.witnesses_tried}/{r.witnesses_available} | "
                 f"{succ['success_envelope'] if succ else '—'} | {succ['spatial'] if succ else '—'} | "
                 f"{succ['access'] if succ else '—'} | {r.a142_result} |")
    L.append("")
    L.append("## UNSAT briefs (never attempted, never weakened)")
    L.append("")
    for r in results:
        if r.classification != "BAND_REPRESENTABLE":
            L.append(f"- **{r.brief_id}** — `{r.classification}`: {r.reason}")
    L.append("")
    L.append("## Failure attribution for every band-representable brief that died after exact embedding")
    L.append("")
    for r in band:
        if r.success:
            continue
        L.append(f"### {r.brief_id} — furthest stage passed: "
                 f"{max((s for s in STAGES if r.stage_pass[s]), key=STAGES.index, default='none')}")
        for st in STAGES:
            if r.stage_histogram.get(st):
                L.append(f"- {st} refusals over all witnesses x envelopes: {r.stage_histogram[st]}")
        sample = [w for w in r.witness_results if w["validator_failures_sample"]][:2]
        for w in sample:
            L.append(f"- witness {w['index']} validator detail: {w['validator_failures_sample'][0]}")
        L.append("")
    L.append("## Successful cases — realized geometry")
    L.append("")
    for r in band:
        if not r.success:
            continue
        w = r.witness_results[r.success_witness]
        L.append(f"### {r.brief_id} — witness {w['index']} (rank score {w['score']}, {w['n_rows']} rows x {w['n_cols']} cols), "
                 f"envelope {w['success_envelope']}, spatial {w['spatial']}, access {w['access']}"
                 + (f", access lost: {w['access_lost']}" if w['access_lost'] else ""))
        L.append("")
        L.append("| room | x | y | w | d | area m2 |")
        L.append("|---|---|---|---|---|---|")
        for k, v in w["rects_m"].items():
            L.append(f"| {k} | {v['x']} | {v['y']} | {v['w']} | {v['d']} | {v['area_m2']} |")
        L.append("")
    L.append("## Reproducing")
    L.append("")
    L.append("```")
    L.append("# stage 1 (isolated venv with python-sat; regenerates witnesses.json, deterministic):")
    L.append("python backend/spikes/topology_representation/band_witnesses.py <briefs.json> docs/reports/142c-exact-band-embedding/witnesses.json 150 120")
    L.append("# stage 2 (project venv, no solver dependency):")
    L.append("cd backend && uv run python -m app.ai_harness.topology_poc.exact_band_142c")
    L.append("```")
    L.append("")
    return "\n".join(L)


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--witnesses", default=DEFAULT_WITNESSES_JSON)
    p.add_argument("--max-witnesses", type=int, default=150)
    p.add_argument("--briefs", default=None, help="comma-separated subset")
    p.add_argument("--write-json", default=DEFAULT_RESULTS_JSON)
    p.add_argument("--write-report", default=DEFAULT_RESULTS_MD)
    a = p.parse_args(argv)
    ids = tuple(a.briefs.split(",")) if a.briefs else None
    results, wit, dataset = run_all(a.witnesses, a.max_witnesses, ids)
    os.makedirs(os.path.dirname(a.write_json), exist_ok=True)
    with open(a.write_json, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in results], f, indent=1)
    with open(a.write_report, "w", encoding="utf-8") as f:
        f.write(render_md(results, wit, dataset))
    print(f"wrote {a.write_report}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
