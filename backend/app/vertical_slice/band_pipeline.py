"""Band pipeline — required contacts -> exact band embedding -> architectural SELECTION -> exact
door-aware per-cell sizing -> existing realization -> unchanged validators, with a TYPED diagnosis of
where a proposal dies (Issues #142E, #142G, #142H).

This is the production counterpart of the #142C/#142D/#142F harness drivers. It changes no validator,
access rule, room bound or realizer policy: the embedding is exact (`band_embedding`), the sizing is
exact on NET semantics (`band_sizing`, wired into `rectilinear_realizer._build_grid_wing`), and every
candidate placement is handed to the unchanged `realize_layout`.

Selection (Issue #142H — the proven #142F findings, productionized). A band layout that the
validators would accept can still be realized wrongly if the pipeline picks the wrong candidate or
the wrong orientation, so BEFORE any geometry is sized:

  contacts     required contacts = spatial adjacency ∪ direct-access pairs: a door needs a shared
               wall, so an access pair is a contact requirement too (made explicit, never silent —
               `input_warnings`). If the union has no band layout while the spatial graph alone has
               one, the proposal's access requirements contradict its adjacency under rectangles:
               `ACCESS_SPATIAL_CONTRADICTION`, an input/proposer problem, not a realizer one.
  orientation  a band layout carries the same contacts either way up; the street is row 0
               (`resolve_entrance` reads the footprint's y = min edge). A candidate whose only
               entrance-eligible room (`ALLOWED_ENTRANCE_ROLES`) sits in the last band is flipped,
               never rejected — and never given a fake entrance after geometry exists.
  HARD filter  a candidate is realized only if, decided from the placement alone: an entrance room
               fronts the street in some orientation; every direct-access pair touches and is a
               legal door pair (`access_rules` + the realizer's own wet-room filter); every room
               whose exposure policy is REQUIRED lies on the envelope (PREFERRED exposure is
               recorded, never enforced — a future scoring concern); every room is reachable from
               the entrance room through legal contacts; a SAFE_ROOM lies on the envelope.
  door widths  the sizing receives each direct-access pair's minimum shared boundary (door width +
               corner margins, `band_sizing.contact_requirements`) and the realized GridWing carries
               the same pairs, so its own re-solve honours them too. Room bounds, aspect, RC insets
               and the safe room's net minimum are unchanged (#142G).

Candidates are tried in the embedder's plausibility order among the HARD-feasible ones until one
realizes and passes `validate`; if none does, the result is a `PipelineDiagnosis` naming the
furthest stage reached and the dominant reason, with the per-stage histogram the next experiment needs.

Diagnosis codes (stage order):
  TOPOLOGY_NON_PLANAR            the required graph is not planar (no partition of the plane carries it)
  TOPOLOGY_REPRESENTATION_LIMIT  K4 / triple-lens: no dissection into rectangles carries it
  BAND_UNSAT                     planar, unobstructed, but no band layout exists (search complete)
  EMBEDDING_SEARCH_EXHAUSTED     no band layout found within the search bound (not a proof)
  ACCESS_SPATIAL_CONTRADICTION   the spatial adjacency embeds but spatial ∪ direct access does not
  ACCESS_POLICY_CONFLICT         a direct-access pair no layout can carry as a door (role pair or
                                 wet-room policy) — the proposal, not the geometry
  NO_ENTRANCE                    no band layout puts an ALLOWED_ENTRANCE room in the street band
                                 in either orientation
  EXPOSURE_INFEASIBLE            no band layout keeps every REQUIRED-exposure room on the envelope
                                 (a proof when the enumeration was complete)
  ACCESS_SPATIAL_MISMATCH        selection: a direct-access pair has no legal contact / a room is
                                 unreachable; or validators: C5/C24 fail on realized geometry
  BAND_GEOMETRY_LIMIT            every HARD-feasible band layout is dimensionally infeasible (proofs)
                                 and the enumeration was complete
  SIZING_INFEASIBLE              every candidate tried is infeasible/unknown but the family was
                                 not exhausted (or some decisions hit the budget)
  SAFE_ROOM_RC_MISSING           reached the validators; C4 fails
  VALIDATION_FAILED              reached the validators; other checks fail
  REALIZATION_FAILED             a realization refusal other than NO_ENTRANCE
"""
from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field

from . import access_rules, wet_room_policy
from .band_embedding import BandEmbedding, BandEmbeddingRefusal, BandPlacement, embed_band
from .band_sizing import contact_requirements, solve_band_layout
from .doors import ALLOWED_ENTRANCE_ROLES
from .exposure_policy import EXPOSURE_POLICY, REQUIRED_EXTERIOR_ROLES, ExposureRequirement
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
STAGES = ("EMBEDDING", "SELECTION", "SIZING", "REALIZATION", "VALIDATORS")
#: The HARD selection flags (Issue #142H). Each is decided from the band placement alone; a
#: candidate failing any of them is never sized or realized. `None` (not applicable) never rejects.
HARD_FLAGS = ("entrance_feasible", "access_contact_ok", "exposure_ok", "reachable_from_entrance",
              "safe_room_on_envelope")
_SIZING_REFUSALS = frozenset({"GRID_INFEASIBLE", "GRID_SIZING_UNKNOWN", "AREA_INFEASIBLE",
                              "SHORT_SIDE_INFEASIBLE", "GRID_ROW_SPAN_MISMATCH", "EMPTY_GRID"})


@dataclass(frozen=True)
class PipelineInput:
    name: str
    zones: dict[str, ZoneIntent]
    required_edges: tuple[tuple[str, str], ...]          # undirected spatial-adjacency pairs
    footprint_m: tuple[float, float]                      # (width, depth) of the brief's footprint
    wet_rooms: tuple[ResolvedWetRoom, ...] = ()
    #: directed (from, to) room pairs that must carry a DOOR. Issue #142H: a required contact
    #: (a door needs a shared wall), a door-width sizing requirement, and a legality requirement —
    #: no longer diagnostics only.
    access_edges: tuple[tuple[str, str], ...] = ()


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
    oriented: bool = False                # flipped top/bottom so the entrance band fronts the street
    rejected_by: tuple[str, ...] = ()     # HARD flags that rejected it at SELECTION


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
    selection: dict = field(default_factory=dict)         # candidate funnel counts


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
    oriented: bool = False
    selection: dict = field(default_factory=dict)


# ----------------------------------------------------------------------------- contacts / policy

def required_contacts(inp: PipelineInput) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    """(spatial ∪ direct-access contacts as sorted undirected pairs, the access pairs that were not
    already spatial). Edges naming a non-zone endpoint (e.g. ENTRANCE) are not contacts."""
    spatial = {frozenset(e) for e in inp.required_edges}
    access = [(a, b) for a, b in inp.access_edges if a in inp.zones and b in inp.zones and a != b]
    extra = tuple((a, b) for a, b in access if frozenset((a, b)) not in spatial)
    union = sorted({tuple(sorted(e)) for e in spatial} | {tuple(sorted(e)) for e in access})
    return tuple(union), extra


def access_policy_conflicts(inp: PipelineInput) -> list[tuple[str, str, str]]:
    """Direct-access pairs NO layout can carry as a door: illegal under `edge_role_pair_allowed`,
    or forbidden by the canonical wet-room entry policy (`wet_room_policy`, Issue #142I — the one
    rule C17 and the realizer's door filter also derive from). Decided from the proposal alone — the
    proposal, not the geometry, has to change."""
    roles = {z: zi.role for z, zi in inp.zones.items()}
    wet = {w.zone_id: w for w in inp.wet_rooms}
    out = []
    for a, b in inp.access_edges:
        if a not in roles or b not in roles:
            continue
        if not access_rules.edge_role_pair_allowed((roles[a],), (roles[b],)):
            out.append((a, b, "edge_role_pair_allowed forbids this role pair"))
            continue
        for x, y in ((a, b), (b, a)):
            if x in wet and not wet_room_policy.wet_room_entry_allowed(wet[x], y, (roles[y],)):
                out.append((a, b, f"{x}: {wet_room_policy.describe_rule(wet[x])}"))
                break
    return out


def input_warnings(inp: PipelineInput) -> tuple[str, ...]:
    """Proposal-level facts worth surfacing before any geometry — nothing here is silent."""
    out = []
    _union, extra = required_contacts(inp)
    if extra:
        out.append("ACCESS_CONTACTS_REQUIRED: direct-access pairs not in the spatial adjacency are required "
                   "as contacts (a door needs a shared wall): " + ", ".join(f"{a}->{b}" for a, b in extra))
    conflicts = access_policy_conflicts(inp)
    if conflicts:
        out.append("ACCESS_POLICY_CONFLICT: " + "; ".join(f"{a}->{b}: {why}" for a, b, why in conflicts))
    return tuple(out)


# ----------------------------------------------------------------------------- selection flags

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
    """A door may exist between a and b: the access-rules role table and the canonical wet-room
    entry policy (`wet_room_policy`, the rule C17 and the realizer's door filter derive from)."""
    if not access_rules.edge_role_pair_allowed((roles[a],), (roles[b],)):
        return False
    for x, y in ((a, b), (b, a)):
        if x in wet and not wet_room_policy.wet_room_entry_allowed(wet[x], y, (roles[y],)):
            return False
    return True


def placement_flags(p: BandPlacement, zones: dict[str, ZoneIntent],
                    wet_rooms: tuple[ResolvedWetRoom, ...],
                    access_edges: tuple[tuple[str, str], ...] = ()) -> dict:
    """Everything decidable from the band placement alone (no sizing, no realization).

    HARD (see `HARD_FLAGS`): entrance_feasible — an ALLOWED_ENTRANCE role in the street band
    (row 0) or in the last band (`entrance_flip`: a free top/bottom flip puts it on the street);
    access_contact_ok — every direct-access pair touches and is a legal door pair; exposure_ok —
    every REQUIRED_EXTERIOR role lies on the envelope; reachable_from_entrance — every room is
    reachable from an entrance room through legal contacts; safe_room_on_envelope — None without a
    SAFE_ROOM. SOFT (recorded, never enforced): preferred exposure counts, band count, public
    front share, bedroom spread. `entrance_ok`/`access_ok` are the #142E names."""
    cells = _cells(p); R = len(p.rows)
    roles = {z: zi.role for z, zi in zones.items()}
    wet = {w.zone_id: w for w in wet_rooms}
    ids = list(cells)
    on_env = {z: (r == 0 or r == R - 1 or c0 == 0 or c1 == p.n_cols) for z, (r, c0, c1) in cells.items()}
    entrance_rows = sorted({cells[z][0] for z in ids if roles[z] in ALLOWED_ENTRANCE_ROLES})
    entrance_now = 0 in entrance_rows
    entrance_flip = (R - 1) in entrance_rows
    access = [(a, b) for a, b in access_edges if a in cells and b in cells and a != b]
    missing_contact = [(a, b) for a, b in access if not _touch(cells, a, b)]
    illegal = [(a, b) for a, b in access if _touch(cells, a, b) and not _legal(roles, wet, a, b)]
    has_partner = {a: any(_touch(cells, a, b) and _legal(roles, wet, a, b) for b in ids if b != a) for a in ids}
    entrance_rooms = [z for z in ids if roles[z] in ALLOWED_ENTRANCE_ROLES]
    reach: set[str] = set()
    if entrance_rooms:
        start = sorted(entrance_rooms, key=lambda z: (cells[z][0], z))[0]
        reach = {start}; stack = [start]
        while stack:
            x = stack.pop()
            for y in ids:
                if y not in reach and _touch(cells, x, y) and _legal(roles, wet, x, y):
                    reach.add(y); stack.append(y)
    buried_required = [z for z in ids if roles[z] in REQUIRED_EXTERIOR_ROLES and not on_env[z]]
    preferred = [z for z in ids if EXPOSURE_POLICY[roles[z]].exterior_wall is ExposureRequirement.PREFERRED]
    safe = [z for z in ids if roles[z] is ProgramRole.SAFE_ROOM]
    street_width = sum(span for _, span in p.rows[0]) or 1
    public_front = sum(span for z, span in p.rows[0]
                       if roles[z] in (ProgramRole.LIVING, ProgramRole.DINING, ProgramRole.KITCHEN, ProgramRole.HALL))
    return {
        # HARD
        "entrance_now": entrance_now, "entrance_flip": entrance_flip,
        "entrance_feasible": entrance_now or entrance_flip, "entrance_rows": entrance_rows,
        "access_contact_ok": not missing_contact and not illegal,
        "access_missing_contact": missing_contact, "access_illegal_pair": illegal,
        "exposure_ok": not buried_required, "buried_required": buried_required,
        "reachable_from_entrance": len(reach) == len(ids) if entrance_rooms else False,
        "unreachable": sorted(set(ids) - reach),
        "safe_room_on_envelope": all(on_env[z] for z in safe) if safe else None,
        # #142E names (instrumentation)
        "entrance_ok": entrance_now, "access_ok": all(has_partner.values()),
        # SOFT
        "n_bands": R, "preferred_on_envelope": sum(1 for z in preferred if on_env[z]),
        "preferred_total": len(preferred),
        "public_front_share": round(public_front / street_width, 2),
        "bedrooms_bands": len({cells[z][0] for z in ids if roles[z] in (ProgramRole.BEDROOM, ProgramRole.MASTER_BEDROOM)}),
    }


def hard_rejections(flags: dict) -> tuple[str, ...]:
    """The HARD flags this placement fails (`None` = not applicable, never a rejection)."""
    return tuple(k for k in HARD_FLAGS if flags.get(k) is False)


def orient(p: BandPlacement, flags: dict) -> tuple[BandPlacement, bool]:
    """Entrance-aware orientation: keep the layout if an entrance room already fronts the street
    (row 0); flip it if the only entrance rooms sit in the last band. Never invents an entrance."""
    if flags["entrance_now"] or not flags["entrance_flip"]:
        return p, False
    return p.flipped(), True


# ----------------------------------------------------------------------------- diagnostics

def _validator_failures(detail: str) -> tuple[str, ...]:
    import re
    return tuple(sorted(set(re.findall(r"\b(C\d+)\b", detail))))


_SELECTION_CODE = (          # priority among HARD kills when none survives (ties broken in this order)
    ("exposure_ok", "EXPOSURE_INFEASIBLE"), ("safe_room_on_envelope", "EXPOSURE_INFEASIBLE"),
    ("entrance_feasible", "NO_ENTRANCE"), ("access_contact_ok", "ACCESS_SPATIAL_MISMATCH"),
    ("reachable_from_entrance", "ACCESS_SPATIAL_MISMATCH"))


def _selection_code(kills: Counter, n: int, complete: bool, conflicts, family: int | None = None) -> tuple[str, str, str]:
    if conflicts:
        return ("ACCESS_POLICY_CONFLICT", "SELECTION",
                "no band layout can carry every direct-access pair as a legal door: "
                + "; ".join(f"{a}->{b}: {why}" for a, b, why in conflicts))
    prio = {k: i for i, (k, _) in enumerate(_SELECTION_CODE)}
    flag = max(kills, key=lambda k: (kills[k], -prio.get(k, 99)))
    code = dict(_SELECTION_CODE)[flag]
    family = f"complete family of {family or n}" if complete else f"{n} found within the search bound"
    if code == "EXPOSURE_INFEASIBLE":
        detail = (f"no band layout ({family}) keeps every REQUIRED-exposure room on the envelope "
                  f"({kills[flag]} of {n} rejected by {flag})")
    elif code == "NO_ENTRANCE":
        detail = (f"no band layout ({family}) puts an ALLOWED_ENTRANCE room in the street band in either "
                  f"orientation ({kills[flag]} of {n})")
    else:
        detail = (f"no band layout ({family}) gives every direct-access pair a legal contact with every "
                  f"room reachable from the entrance ({flag}: {kills[flag]} of {n})")
    return code, "SELECTION", detail


def _downstream_code(records: list[CandidateRecord]) -> tuple[str, str, str]:
    """(code, stage, detail) from the furthest stage any candidate passed and the dominant reason."""
    order = {s: i for i, s in enumerate(STAGES)}
    furthest = max((order[r.stage_reached] for r in records), default=0)
    if furthest <= order["SIZING"]:
        reasons = Counter(r.refusal for r in records
                          if r.stage_reached == "SIZING" and r.refusal != "NOT_REALIZED_BUDGET")
        top = reasons.most_common(1)[0][0] if reasons else "REALIZATION"
        if top == "NO_ENTRANCE":
            return "NO_ENTRANCE", "REALIZATION", "sized candidates have no ALLOWED_ENTRANCE role fronting the street band"
        return "REALIZATION_FAILED", "REALIZATION", f"dominant realization refusal: {top}"
    checks: Counter = Counter()
    for r in records:
        if r.stage_reached == "REALIZATION":
            for c in r.validator_failed_checks:
                checks[c] += 1
    if checks.get("C4"):
        return "SAFE_ROOM_RC_MISSING", "VALIDATORS", f"C4 failed on {checks['C4']} candidate(s)"
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
    union, extra = required_contacts(inp)
    access = tuple((a, b) for a, b in inp.access_edges if a in inp.zones and b in inp.zones and a != b)
    emb = embed_band(inp.zones, union, **kwargs)
    if isinstance(emb, BandEmbeddingRefusal):
        if extra:
            emb_s = embed_band(inp.zones, inp.required_edges, **kwargs)
            if isinstance(emb_s, BandEmbedding):
                detail = (f"the spatial adjacency alone has a band layout ({len(emb_s.candidates)} candidate(s)) "
                          f"but spatial ∪ direct-access does not ({emb.code}: {emb.detail}); the proposal's "
                          f"access requirements contradict its adjacency under rectangles — fix the proposal")
                return PipelineDiagnosis("ACCESS_SPATIAL_CONTRADICTION", "EMBEDDING", detail, 0,
                                         {"EMBEDDING": {emb.code: 1}}, warnings, [],
                                         round(time.monotonic() - t0, 4))
            emb = emb_s                      # the spatial graph itself is refused: report that
        return PipelineDiagnosis(emb.code, "EMBEDDING", emb.detail, 0, {"EMBEDDING": {emb.code: 1}},
                                 warnings, [], round(time.monotonic() - t0, 4))

    fw, fd = inp.footprint_m
    bw, bd = fw + BUILDABLE_MARGIN_M, fd + BUILDABLE_MARGIN_M
    buildable = Rect(0, 0, m_to_u(bw), m_to_u(bd))
    contacts = contact_requirements(inp.zones, union, access)
    conflicts = access_policy_conflicts(inp)
    records: list[CandidateRecord] = []
    hist: dict[str, Counter] = {s: Counter() for s in STAGES}
    funnel: Counter = Counter(candidates=len(emb.candidates))
    # stage 1 — SELECTION (placement only) + door-aware exact sizing; stage 2 — realize in order
    sizable: list[tuple[int, BandPlacement, CandidateRecord, object]] = []
    for idx, placement in enumerate(emb.candidates):
        flags = placement_flags(placement, inp.zones, inp.wet_rooms, access)
        rec = CandidateRecord(idx, len(placement.rows), placement.n_cols, "EMBEDDING", flags=flags)
        rejected = hard_rejections(flags)
        if rejected:
            rec.refusal, rec.refusal_detail, rec.rejected_by = "SELECTION_REJECTED", ",".join(rejected), rejected
            for k in rejected:
                hist["SELECTION"][k] += 1
            records.append(rec)
            continue
        funnel["hard_feasible"] += 1
        placement, rec.oriented = orient(placement, flags)
        if rec.oriented:
            rec.flags = placement_flags(placement, inp.zones, inp.wet_rooms, access)
            funnel["oriented"] += 1
        rec.stage_reached = "SELECTION"
        sz = solve_band_layout(placement.bands, inp.zones, union, w_max_m=bw, h_max_m=bd,
                               min_contact_u=contacts)
        if sz.status != "FEASIBLE":
            rec.refusal = "GRID_INFEASIBLE" if sz.status == "INFEASIBLE" else "GRID_SIZING_UNKNOWN"
            rec.refusal_detail = sz.detail
            hist["SIZING"][rec.refusal] += 1
            records.append(rec)
            continue
        funnel["sized"] += 1
        sizable.append((idx, placement, rec, sz))
    for idx, placement, rec, sz in sizable[:max_realizations]:
        # the solved interleaving becomes the GridWing's columns; the wing tiles exactly the solved size
        W_m = round(sum(sz.col_w_u) * 0.05, 2); H_m = round(sum(sz.row_h_u) * 0.05, 2)
        sized = BandPlacement(sz.rows, sz.n_cols, placement.score, placement.bands)
        wing = sized.to_grid_wing(inp.name, W_m, H_m, inp.zones, envelope_is_bound=False, access_pairs=access)
        res = realize_layout(RealizationIntent(name=inp.name, wings=(wing,), wet_rooms=inp.wet_rooms),
                             buildable=buildable)
        if isinstance(res, RealizedLayout):
            funnel["realized"] += 1; funnel["passed"] += 1
            rec.stage_reached = "VALIDATORS"
            records.append(rec)
            sp = measure_spatial_adjacency(res.rects, frozenset(frozenset(e) for e in inp.required_edges))
            ac = measure_access_graph(res.fixture.access.edges, list(inp.access_edges))
            return PipelineSuccess(res, sized, idx, len(records), f"{sp.preserved}/{sp.requested}",
                                   f"{ac.preserved}/{ac.requested}", tuple(sorted(str(e) for e in ac.lost)),
                                   warnings, records, round(time.monotonic() - t0, 4),
                                   oriented=rec.oriented, selection=dict(funnel))
        assert isinstance(res, Refusal)
        rec.refusal, rec.refusal_detail = res.constraint, res.detail[:300]
        if res.constraint in _SIZING_REFUSALS:
            rec.stage_reached = "SELECTION"; hist["SIZING"][res.constraint] += 1
        elif res.constraint == "VALIDATION_FAILED":
            funnel["realized"] += 1
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

    # nothing passed: classify by the furthest stage reached
    order = {s: i for i, s in enumerate(STAGES)}
    selected = [r for r in records if order[r.stage_reached] >= order["SELECTION"]]
    sized_recs = [r for r in records if order[r.stage_reached] >= order["SIZING"]]
    if not selected:
        code, stage, detail = _selection_code(hist["SELECTION"], len(records), emb.search_complete, conflicts, emb.layouts_found)
    elif not sized_recs:
        proven = emb.search_complete and all(r.refusal == "GRID_INFEASIBLE" for r in selected)
        code = "BAND_GEOMETRY_LIMIT" if proven else "SIZING_INFEASIBLE"
        detail = (f"all {len(selected)} HARD-feasible band layouts (complete enumeration of {len(records)}) are "
                  f"dimensionally infeasible under the rooms' own net bounds and door widths" if proven else
                  f"none of {len(selected)} HARD-feasible candidate placements could be sized "
                  f"(enumeration complete: {emb.search_complete})")
        stage = "SIZING"
    else:
        code, stage, detail = _downstream_code(records)
    return PipelineDiagnosis(code, stage, detail, len(records),
                             {s: dict(c) for s, c in hist.items() if c}, warnings, records,
                             round(time.monotonic() - t0, 4), dict(funnel))


__all__ = ["PipelineInput", "PipelineSuccess", "PipelineDiagnosis", "CandidateRecord",
           "run_band_pipeline", "placement_flags", "hard_rejections", "orient", "required_contacts",
           "access_policy_conflicts", "input_warnings", "STAGES", "HARD_FLAGS"]
