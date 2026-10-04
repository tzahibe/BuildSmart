"""Band pipeline — required topology -> exact band embedding -> exact per-cell sizing -> existing
realization -> unchanged validators, with a TYPED diagnosis of where a proposal dies (Issue #142E).

This is the production counterpart of the #142C/#142D harness drivers. It changes no validator,
access rule, room bound or realizer policy: the embedding is exact (`band_embedding`), the sizing is
exact on NET semantics (`band_sizing`, wired into `rectilinear_realizer._build_grid_wing`), and every
candidate placement is handed to the unchanged `realize_layout`. Candidates are tried in the
embedder's plausibility order until one realizes and passes `validate`; if none does, the result is
a `PipelineDiagnosis` naming the furthest stage reached and the dominant reason, with the per-stage
histogram the next experiment needs. Known downstream limits are instrumented, not fixed (#142E Part
D): entrance placement, safe-room RC walls, access-vs-spatial mismatch, exposure.

Diagnosis codes (stage order):
  TOPOLOGY_NON_PLANAR            the required graph is not planar (no partition of the plane carries it)
  TOPOLOGY_REPRESENTATION_LIMIT  K4 / triple-lens: no dissection into rectangles carries it
  BAND_UNSAT                     planar, unobstructed, but no band layout exists (search complete)
  EMBEDDING_SEARCH_EXHAUSTED     no band layout found within the search bound (not a proof)
  BAND_GEOMETRY_LIMIT            every band layout found is dimensionally infeasible (proofs) and
                                 the enumeration was complete
  SIZING_INFEASIBLE              every candidate tried is infeasible/unknown but the family was
                                 not exhausted (or some decisions hit the budget)
  NO_ENTRANCE                    sized, but no entrance-role room fronts the street in any candidate
  SAFE_ROOM_RC_MISSING           reached the validators; C4 fails (this realizer assigns no RC walls)
  ACCESS_SPATIAL_MISMATCH        reached the validators; C5/C24 fail and a room has no legal door partner
  EXPOSURE_INFEASIBLE            reached the validators; C19/C8 fail (a daylight room has no exterior wall)
  VALIDATION_FAILED              reached the validators; other checks fail
  REALIZATION_FAILED             a realization refusal other than NO_ENTRANCE
"""
from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field

from . import access_rules
from .band_embedding import BandEmbedding, BandEmbeddingRefusal, BandPlacement, embed_band
from .band_sizing import solve_band_layout
from .doors import ALLOWED_ENTRANCE_ROLES
from .exposure_policy import REQUIRED_EXTERIOR_ROLES
from .geometry_core.model import ProgramRole, Rect, m_to_u
from .rectilinear_realizer import RealizationIntent, RealizedLayout, Refusal, ZoneIntent, realize_layout
from .topology_preservation import measure_access_graph, measure_spatial_adjacency
from .wet_rooms import ResolvedWetRoom

#: Buildable margin around the brief footprint — the same `+4 m` the #142A/#142C/#142D drivers used.
BUILDABLE_MARGIN_M = 4.0
DEFAULT_MAX_CANDIDATES = 120
#: Candidates are sized first (~1 ms each, exact) and only sizable ones are realized (walls, doors,
#: windows, validators — a few ms each), at most this many, in plausibility order.
DEFAULT_MAX_REALIZATIONS = 150
STAGES = ("EMBEDDING", "SIZING", "REALIZATION", "VALIDATORS")
_SIZING_REFUSALS = frozenset({"GRID_INFEASIBLE", "GRID_SIZING_UNKNOWN", "AREA_INFEASIBLE",
                              "SHORT_SIDE_INFEASIBLE", "GRID_ROW_SPAN_MISMATCH", "EMPTY_GRID"})


@dataclass(frozen=True)
class PipelineInput:
    name: str
    zones: dict[str, ZoneIntent]
    required_edges: tuple[tuple[str, str], ...]          # undirected spatial-adjacency pairs
    footprint_m: tuple[float, float]                      # (width, depth) of the brief's footprint
    wet_rooms: tuple[ResolvedWetRoom, ...] = ()
    access_edges: tuple[tuple[str, str], ...] = ()       # directed (from, to) room pairs, diagnostics only


@dataclass
class CandidateRecord:
    index: int
    n_bands: int
    n_cols: int
    stage_reached: str                    # furthest stage PASSED
    refusal: str | None = None
    refusal_detail: str | None = None
    validator_failed_checks: tuple[str, ...] = ()
    flags: dict = field(default_factory=dict)


@dataclass
class PipelineDiagnosis:
    code: str
    stage: str                            # stage at which the pipeline stopped
    detail: str
    candidates_tried: int = 0
    stage_histogram: dict = field(default_factory=dict)   # stage -> {reason: count}
    warnings: tuple[str, ...] = ()
    records: list = field(default_factory=list)
    seconds: float = 0.0


@dataclass
class PipelineSuccess:
    realized: RealizedLayout
    placement: BandPlacement
    candidate_index: int
    candidates_tried: int
    spatial_preserved: str
    access_preserved: str
    access_lost: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    records: list = field(default_factory=list)
    seconds: float = 0.0


# ----------------------------------------------------------------------------- diagnostics

def _validator_failures(detail: str) -> tuple[str, ...]:
    import re
    return tuple(sorted(set(re.findall(r"\b(C\d+)\b", detail))))


def placement_flags(p: BandPlacement, zones: dict[str, ZoneIntent],
                    wet_rooms: tuple[ResolvedWetRoom, ...]) -> dict:
    """Topology-level properties the downstream stages will test (instrumentation, never enforced):
    entrance_ok — an ALLOWED_ENTRANCE role in the street band (row 0; `resolve_entrance` reads the
    footprint's y = min edge); access_ok — every room touches >= 1 room it may legally be entered
    from (wet rooms as `_filter_wet_room_access`); exposure_ok — every REQUIRED_EXTERIOR role touches
    the envelope."""
    R = len(p.rows)
    cells: dict[str, tuple[int, int, int]] = {}
    for r, row in enumerate(p.rows):
        c0 = 0
        for z, span in row:
            cells[z] = (r, c0, c0 + span); c0 += span
    roles = {z: zi.role for z, zi in zones.items()}
    wet = {w.zone_id: w for w in wet_rooms}

    def touch(a, b):
        ra, a0, a1 = cells[a]; rb, b0, b1 = cells[b]
        return (a1 == b0 or b1 == a0) if ra == rb else (abs(ra - rb) == 1 and a0 < b1 and b0 < a1)

    def legal(a, b):
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

    ids = list(cells)
    return {
        "entrance_ok": any(roles[z] in ALLOWED_ENTRANCE_ROLES for z, (r, _a, _b) in cells.items() if r == 0),
        "access_ok": all(any(touch(a, b) and legal(a, b) for b in ids if b != a) for a in ids),
        "exposure_ok": all(r == 0 or r == R - 1 or c0 == 0 or c1 == p.n_cols
                           for z, (r, c0, c1) in cells.items() if roles[z] in REQUIRED_EXTERIOR_ROLES),
    }


def input_warnings(inp: PipelineInput) -> tuple[str, ...]:
    """Proposal-level facts worth surfacing before any geometry (Part D instrumentation)."""
    out = []
    spatial = {frozenset(e) for e in inp.required_edges}
    unsupported = sorted(f"{a}->{b}" for a, b in inp.access_edges
                         if a in inp.zones and b in inp.zones and frozenset((a, b)) not in spatial)
    if unsupported:
        out.append("ACCESS_SPATIAL_MISMATCH: access edges with no required shared wall: " + ", ".join(unsupported))
    if any(zi.role is ProgramRole.SAFE_ROOM for zi in inp.zones.values()):
        out.append("SAFE_ROOM_RC_MISSING: the rectilinear realizer assigns no RC_SAFE_ROOM walls; "
                   "validator C4 will fail for any SAFE_ROOM it realizes")
    return tuple(out)


def _downstream_code(records: list[CandidateRecord]) -> tuple[str, str, str]:
    """(code, stage, detail) from the furthest stage any candidate passed and the dominant reason."""
    order = {s: i for i, s in enumerate(STAGES)}
    furthest = max((order[r.stage_reached] for r in records), default=0)
    if furthest == 0:
        return "SIZING_INFEASIBLE", "SIZING", "no candidate placement could be sized"
    if furthest == 1:
        reasons = Counter(r.refusal for r in records
                          if r.stage_reached == "SIZING" and r.refusal != "NOT_REALIZED_BUDGET")
        top = reasons.most_common(1)[0][0] if reasons else "REALIZATION"
        if top == "NO_ENTRANCE":
            return "NO_ENTRANCE", "REALIZATION", "sized candidates have no ALLOWED_ENTRANCE role fronting the street band"
        return "REALIZATION_FAILED", "REALIZATION", f"dominant realization refusal: {top}"
    checks = Counter()
    for r in records:
        if r.stage_reached == "REALIZATION":
            for c in r.validator_failed_checks:
                checks[c] += 1
    if checks.get("C4"):
        return "SAFE_ROOM_RC_MISSING", "VALIDATORS", f"C4 failed on {checks['C4']} candidate(s): no RC walls assigned"
    if checks.get("C24") or checks.get("C5"):
        return "ACCESS_SPATIAL_MISMATCH", "VALIDATORS", (
            f"door-ability failed (C24 {checks.get('C24', 0)}, C5 {checks.get('C5', 0)}): a room has no legal door partner among its shared walls")
    if checks.get("C19") or checks.get("C8"):
        return "EXPOSURE_INFEASIBLE", "VALIDATORS", f"exposure failed (C19 {checks.get('C19', 0)}, C8 {checks.get('C8', 0)})"
    return "VALIDATION_FAILED", "VALIDATORS", "validators failed: " + ", ".join(f"{k} x{v}" for k, v in checks.most_common(5))


# ----------------------------------------------------------------------------- the pipeline

def run_band_pipeline(inp: PipelineInput, *, max_candidates: int = DEFAULT_MAX_CANDIDATES,
                      max_realizations: int = DEFAULT_MAX_REALIZATIONS,
                      embed_node_limit: int | None = None) -> PipelineSuccess | PipelineDiagnosis:
    t0 = time.monotonic()
    warnings = input_warnings(inp)
    kwargs = {"max_candidates": max_candidates}
    if embed_node_limit is not None:
        kwargs["node_limit"] = embed_node_limit
    emb = embed_band(inp.zones, inp.required_edges, **kwargs)
    if isinstance(emb, BandEmbeddingRefusal):
        return PipelineDiagnosis(emb.code, "EMBEDDING", emb.detail, 0, {"EMBEDDING": {emb.code: 1}},
                                 warnings, [], round(time.monotonic() - t0, 4))

    fw, fd = inp.footprint_m
    bw, bd = fw + BUILDABLE_MARGIN_M, fd + BUILDABLE_MARGIN_M
    buildable = Rect(0, 0, m_to_u(bw), m_to_u(bd))
    records: list[CandidateRecord] = []
    hist: dict[str, Counter] = {s: Counter() for s in STAGES}
    # stage 1: size every candidate (cheap, exact); stage 2: realize the sizable ones in order
    sizable: list[tuple[int, BandPlacement, CandidateRecord]] = []
    for idx, placement in enumerate(emb.candidates):
        rec = CandidateRecord(idx, len(placement.rows), placement.n_cols, "EMBEDDING",
                              flags=placement_flags(placement, inp.zones, inp.wet_rooms))
        sz = solve_band_layout(placement.bands, inp.zones, inp.required_edges, w_max_m=bw, h_max_m=bd)
        if sz.status != "FEASIBLE":
            rec.refusal = "GRID_INFEASIBLE" if sz.status == "INFEASIBLE" else "GRID_SIZING_UNKNOWN"
            rec.refusal_detail = sz.detail
            hist["SIZING"][rec.refusal] += 1
            records.append(rec)
            continue
        sizable.append((idx, placement, rec, sz))
    for idx, placement, rec, sz in sizable[:max_realizations]:
        # the solved interleaving becomes the GridWing's columns; the wing tiles exactly the solved size
        W_m = round(sum(sz.col_w_u) * 0.05, 2); H_m = round(sum(sz.row_h_u) * 0.05, 2)
        sized = BandPlacement(sz.rows, sz.n_cols, placement.score, placement.bands)
        wing = sized.to_grid_wing(inp.name, W_m, H_m, inp.zones, envelope_is_bound=False)
        res = realize_layout(RealizationIntent(name=inp.name, wings=(wing,), wet_rooms=inp.wet_rooms),
                             buildable=buildable)
        if isinstance(res, RealizedLayout):
            rec.stage_reached = "VALIDATORS"
            records.append(rec)
            sp = measure_spatial_adjacency(res.rects, frozenset(frozenset(e) for e in inp.required_edges))
            ac = measure_access_graph(res.fixture.access.edges, list(inp.access_edges))
            return PipelineSuccess(res, sized, idx, len(records), f"{sp.preserved}/{sp.requested}",
                                   f"{ac.preserved}/{ac.requested}", tuple(sorted(str(e) for e in ac.lost)),
                                   warnings, records, round(time.monotonic() - t0, 4))
        assert isinstance(res, Refusal)
        rec.refusal, rec.refusal_detail = res.constraint, res.detail[:300]
        if res.constraint in _SIZING_REFUSALS:
            rec.stage_reached = "EMBEDDING"; hist["SIZING"][res.constraint] += 1
        elif res.constraint == "VALIDATION_FAILED":
            rec.stage_reached = "REALIZATION"
            rec.validator_failed_checks = _validator_failures(res.detail)
            hist["VALIDATORS"]["+".join(rec.validator_failed_checks) or "VALIDATION_FAILED"] += 1
        else:
            rec.stage_reached = "SIZING"; hist["REALIZATION"][res.constraint] += 1
        records.append(rec)
    for idx, placement, rec, _sz in sizable[max_realizations:]:
        rec.stage_reached = "SIZING"; rec.refusal = "NOT_REALIZED_BUDGET"
        hist["REALIZATION"]["NOT_REALIZED_BUDGET"] += 1
        records.append(rec)

    # nothing passed: classify
    sized = [r for r in records if r.stage_reached != "EMBEDDING"]
    if not sized:
        # (rank-1 fallback mode refuses with GRID_INFEASIBLE too; the proof claim needs exact sizing)
        proven = emb.search_complete and all(r.refusal == "GRID_INFEASIBLE" for r in records)
        code = "BAND_GEOMETRY_LIMIT" if proven else "SIZING_INFEASIBLE"
        detail = (f"all {len(records)} band layouts (complete enumeration) are dimensionally infeasible "
                  f"under the rooms' own net bounds" if proven else
                  f"none of {len(records)} candidate placements could be sized "
                  f"(enumeration complete: {emb.search_complete})")
        stage = "SIZING"
    else:
        code, stage, detail = _downstream_code(records)
    return PipelineDiagnosis(code, stage, detail, len(records),
                             {s: dict(c) for s, c in hist.items() if c}, warnings, records,
                             round(time.monotonic() - t0, 4))


__all__ = ["PipelineInput", "PipelineSuccess", "PipelineDiagnosis", "CandidateRecord",
           "run_band_pipeline", "placement_flags", "input_warnings", "STAGES"]
