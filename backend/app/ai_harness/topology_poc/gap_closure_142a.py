"""Issue #162 (#142A) — realizability gap closure, end-to-end driver and report writer.

Runs #160's own 5 selected frozen cases (B01, B10, B13, B15, B16 — unchanged, same dataset, same
selection method: the best policy-valid proposal in each brief's own top-8 by `total_score`)
through the GENERALIZED `rectilinear_realizer` (`GridWing`, Issue #162) via the embedding decision
layer (`graph_embedding.embed_adjacency_graph`), and reports Gate A (can the n>5 topologies be
STRUCTURALLY placed at all) and Gate B (can every placed case be DIMENSIONED) separately, with
every refusal classified into exactly one of TOPOLOGY_EMBEDDING / PLACEMENT / DIMENSION_SOLVER /
FOOTPRINT_INFEASIBLE / REALIZER_INTERNAL / VALIDATOR.

No validator, access rule, room minimum, wet-core rule, critic or proposal datum changes anywhere
in this module (AC-8) — it only calls the EXISTING (now generalized) realizer and the EXISTING
critic/priors/dataset-loading infrastructure #151/#160 already established.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from app.vertical_slice import access_rules
from app.vertical_slice.concept_generator import ROOM_TEMPLATES
from app.vertical_slice.geometry_core.model import ProgramRole, Rect, m_to_u
from app.vertical_slice.graph_embedding import EmbeddingRefusal, embed_adjacency_graph
from app.vertical_slice.rectilinear_realizer import (
    GridWing,
    PinwheelWing,
    RealizationIntent,
    RealizedLayout,
    Refusal,
    RowWing,
    ZoneIntent,
    realize_layout,
)
from app.vertical_slice.spec import WetRoomKind, WetRoomStrength
from app.vertical_slice.topology_preservation import (
    measure_access_graph,
    measure_spatial_adjacency,
)
from app.vertical_slice.topology_preservation import verdict as preservation_verdict
from app.vertical_slice.wet_rooms import ResolvedWetRoom

from . import critic, generation_dataset
from . import priors as priors_mod
from . import schema

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_REPO_ROOT = os.path.dirname(_BACKEND_DIR)
DEFAULT_RESULTS_MD = os.path.join(
    _REPO_ROOT, "docs", "reports", "142a-realizability-gap-closure", "results.md")

#: #160's own selection — frozen, unchanged (Issue #162's own "FROZEN ACCEPTANCE CORPUS").
SELECTED_BRIEF_IDS = ("B01", "B10", "B13", "B15", "B16")
#: The 4 n>5 cases Gate A reports on (Issue's own "Required behavior" §8, Gate A).
GATE_A_BRIEF_IDS = ("B10", "B13", "B15", "B16")

#: A caller-side retry ladder (never inside the realizer itself — it never approximates): the SAME
#: chosen placement, at a different envelope scale, matching `spikes/geometry_shapes/
#: stage1_gate.py`'s own disclosed policy.
_ENVELOPE_RETRY_SCALES = (1.0, 0.9, 0.85, 0.8, 0.78, 0.76, 0.75, 0.72, 0.7, 1.1, 1.2, 1.3, 0.6, 1.4,
                           1.5, 0.5)

_FALLBACK_TEMPLATE_BOUNDS = (6.0, 10.0, 40.0, 1.2, 4.0)  # min, target, max, min_short, max_aspect

#: Refusal constraints originating from `realize_layout`'s own SIZING solvers — Issue #162's
#: DIMENSION_SOLVER bucket (AC-6).
_DIMENSION_SOLVER_CONSTRAINTS = frozenset({
    "AREA_INFEASIBLE", "SHORT_SIDE_INFEASIBLE", "ASPECT_INFEASIBLE", "PINWHEEL_INFEASIBLE",
    "GRID_INFEASIBLE", "NOTCH_INFEASIBLE",
})
#: Genuine internal construction defects, never a sizing or topology question — REALIZER_INTERNAL.
_REALIZER_INTERNAL_CONSTRAINTS = frozenset({
    "SLOTS_DO_NOT_TOUCH", "UNKNOWN_SLOT", "EMPTY_ROW", "EMPTY_GRID", "GRID_ROW_SPAN_MISMATCH",
    "NOT_ONE_POLYGON", "UNKNOWN_FAMILY", "NO_ENTRANCE", "EMPTY_LAYOUT",
})


def is_access_policy_valid(proposal: "schema.TopologyProposal") -> bool:
    """Every `access_graph` edge accepted by the REAL `access_rules.ALLOWED_ENTERED_FROM` table —
    never the ai_harness's own separate critic-side heuristic (#160's own precedent)."""
    role_lookup = {rid: ProgramRole(role) for rid, role in proposal.role_by_id.items()}
    role_lookup[schema.ENTRANCE_ID] = ProgramRole.ENTRANCE
    for a, b in proposal.access_graph:
        if not access_rules.edge_role_pair_allowed((role_lookup[a],), (role_lookup[b],)):
            return False
    return True


def room_area_intent(room_id: str, role_value: str) -> ZoneIntent:
    """This room's own `ZoneIntent`, sized from `concept_generator.ROOM_TEMPLATES[role]` — the
    engine's own program table, never an invented number (#160's own precedent)."""
    role = ProgramRole(role_value)
    template = ROOM_TEMPLATES.get(role)
    if template is None:
        min_m2, target_m2, max_m2, min_short_m, max_aspect = _FALLBACK_TEMPLATE_BOUNDS
        return ZoneIntent(room_id, role, target_m2, min_m2, max_m2, min_short_m, max_aspect)
    return ZoneIntent(room_id, role, template.target_area_m2, template.min_area_m2,
                       template.max_area_m2, template.min_short_side_m, template.max_aspect_ratio)


def resolve_wet_rooms(proposal: "schema.TopologyProposal") -> tuple[ResolvedWetRoom, ...]:
    """Every BATHROOM/TOILET room's own kind, derived from the proposal's OWN `access_graph` — an
    incoming edge from a BEDROOM/MASTER_BEDROOM names an ENSUITE (that bedroom is the host);
    otherwise the room is a SHARED_BATHROOM (BATHROOM) or GUEST_WC (TOILET) entered from
    circulation. A wet room with no declared incoming edge at all defaults to the circulation case
    — a disclosed assumption, never a silent drop (every BATHROOM/TOILET gets exactly one entry
    here, which `validation.py`'s C17 then holds the realized geometry to)."""
    role_by_id = proposal.role_by_id
    incoming: dict[str, list[str]] = {}
    for a, b in proposal.access_graph:
        incoming.setdefault(b, []).append(a)
    out = []
    for room_id, role_value in role_by_id.items():
        role = ProgramRole(role_value)
        if role not in (ProgramRole.BATHROOM, ProgramRole.TOILET):
            continue
        hosts = [a for a in incoming.get(room_id, ())
                 if ProgramRole(role_by_id.get(a, "")) in
                 (ProgramRole.BEDROOM, ProgramRole.MASTER_BEDROOM)]
        if hosts:
            out.append(ResolvedWetRoom(room_id, WetRoomKind.ENSUITE, hosts[0],
                                        WetRoomStrength.REQUIRED, True))
        else:
            kind = WetRoomKind.GUEST_WC if role is ProgramRole.TOILET else WetRoomKind.SHARED_BATHROOM
            out.append(ResolvedWetRoom(room_id, kind, None, WetRoomStrength.REQUIRED, True))
    return tuple(out)


def _scored_proposals(record: dict, pri: "priors_mod.Priors"
                       ) -> list[tuple[float, "schema.TopologyProposal"]]:
    for attempt in record["attempts"]:
        raws = attempt["parsed_json"].get("proposals", [])
        scored = []
        for raw in raws:
            try:
                p = schema.proposal_from_dict(raw)
            except schema.SchemaViolationError:
                continue
            sb = critic.score_topology(p, pri)
            scored.append((sb.total_score, p))
        if scored:
            scored.sort(key=lambda t: -t[0])
            return scored
    return []


def best_policy_valid_proposal(record: dict, pri: "priors_mod.Priors") -> "schema.TopologyProposal":
    scored = _scored_proposals(record, pri)
    for _score, p in scored[:8]:
        if is_access_policy_valid(p):
            return p
    raise AssertionError(f"{record['brief_id']}: no policy-valid proposal in top-8")


def classify_refusal(constraint: str) -> str:
    """Maps a `Refusal.constraint` from `realize_layout` onto exactly one of the 6 AC-6 buckets.
    `TOPOLOGY_EMBEDDING` is decided by the EMBEDDING step, before `realize_layout` ever runs, so it
    never reaches this function. `PLACEMENT` is a DEFINED bucket in the AC-6 taxonomy that no code
    path in this implementation currently produces: `graph_embedding.embed_adjacency_graph`
    searches "is there a structure AND an assignment of it that carries the full graph" as one
    combined step and reports every shortfall as `TOPOLOGY_EMBEDDING` (the best structure/
    assignment pair found), never distinguishing "no structure could ever fit" from "a structure
    was selected but its own assignment search fell short" — so `PLACEMENT` is honestly disclosed
    here as currently unreachable, not demonstrated by a constructed example."""
    if constraint == "VALIDATION_FAILED":
        return "VALIDATOR"
    if constraint == "ENVELOPE_TOO_LARGE":
        return "FOOTPRINT_INFEASIBLE"
    if constraint in _DIMENSION_SOLVER_CONSTRAINTS:
        return "DIMENSION_SOLVER"
    if constraint in _REALIZER_INTERNAL_CONSTRAINTS:
        return "REALIZER_INTERNAL"
    return "REALIZER_INTERNAL"


@dataclass(frozen=True)
class GateAResult:
    brief_id: str
    n_rooms: int
    required_edges: int
    structurally_preserved: int
    lost_edges: int
    extra_edges: int
    placement_form: str
    embeddable: bool


@dataclass(frozen=True)
class GateBResult:
    brief_id: str
    dimensioned: bool
    envelope_used: "str | None"
    footprint_m: "tuple[float, float] | None"
    refusal_constraint: "str | None"
    refusal_detail: "str | None"
    failure_class: "str | None"


@dataclass(frozen=True)
class CaseReport:
    brief_id: str
    proposal: "schema.TopologyProposal"
    gate_a: "GateAResult | None"
    gate_b: GateBResult
    realized: "RealizedLayout | None"
    spatial_preservation: "object | None"
    access_preservation: "object | None"
    final_status: str  # REALIZED | REFUSED
    final_failure_class: "str | None"
    final_reason: "str | None"


def _zones_for(proposal: "schema.TopologyProposal") -> dict[str, ZoneIntent]:
    return {r.id: room_area_intent(r.id, r.role) for r in proposal.rooms}


def run_gate_a(brief_id: str, proposal: "schema.TopologyProposal") -> GateAResult:
    zones = _zones_for(proposal)
    required_edges = tuple(tuple(e) for e in proposal.spatial_adjacency)
    result = embed_adjacency_graph(zones, required_edges, wing_id=brief_id)
    n = len(zones)
    if isinstance(result, EmbeddingRefusal):
        return GateAResult(brief_id, n, result.required_edges, result.best_edges_achieved,
                            result.required_edges - result.best_edges_achieved, 0,
                            result.best_form, False)
    form = ("PINWHEEL" if isinstance(result, PinwheelWing) else
            "ROW" if isinstance(result, RowWing) else
            f"GRID {len(result.rows)}x{result.n_cols}" if isinstance(result, GridWing) else "?")
    return GateAResult(brief_id, n, len(required_edges), len(required_edges), 0, 0, form, True)


def run_gate_b(brief_id: str, proposal: "schema.TopologyProposal",
                brief_footprint_m: "tuple[float, float] | None") -> tuple[GateBResult, "RealizedLayout | None"]:
    zones = _zones_for(proposal)
    required_edges = tuple(tuple(e) for e in proposal.spatial_adjacency)
    wet_rooms = resolve_wet_rooms(proposal)
    buildable = None
    if brief_footprint_m is not None:
        fw, fd = brief_footprint_m
        buildable = Rect(0, 0, m_to_u(fw) + m_to_u(4.0), m_to_u(fd) + m_to_u(4.0))

    embedded = embed_adjacency_graph(zones, required_edges, wing_id=brief_id)
    if isinstance(embedded, EmbeddingRefusal):
        return GateBResult(brief_id, False, None, brief_footprint_m, embedded.constraint,
                            embedded.detail, "TOPOLOGY_EMBEDDING"), None

    last_refusal: "Refusal | None" = None
    #: A `PinwheelWing` has 2 INDEPENDENT degrees of freedom (width_m, height_m) that a single
    #: uniform scale factor cannot explore — an exhaustive 2D grid over both, same chosen
    #: placement throughout, matching #160's own `_PINWHEEL_GRID_M` discipline (and
    #: `spikes/geometry_shapes/stage1_gate.py`'s own retry policy before it): the realizer itself
    #: never approximates, only this loop tries a different, still fully-specified envelope next.
    if isinstance(embedded, PinwheelWing):
        grid_m = tuple(round(5.0 + 0.3 * i, 2) for i in range(31))  # 5.0 .. 14.0 m, step 0.3
        for width_m in grid_m:
            for height_m in grid_m:
                scaled = embed_adjacency_graph(zones, required_edges, wing_id=brief_id,
                                                envelope_override=(width_m, height_m))
                assert not isinstance(scaled, EmbeddingRefusal)
                wet_rooms_local = wet_rooms
                intent = RealizationIntent(name=brief_id, wings=(scaled,), wet_rooms=wet_rooms_local)
                result = realize_layout(intent, buildable=buildable)
                if isinstance(result, RealizedLayout):
                    return GateBResult(brief_id, True, f"{width_m}x{height_m} m",
                                        brief_footprint_m, None, None, None), result
                last_refusal = result
        assert last_refusal is not None
        return GateBResult(
            brief_id, False, None, brief_footprint_m, last_refusal.constraint,
            f"{last_refusal.detail} (exhaustive {len(grid_m)}x{len(grid_m)} width/height grid "
            f"search over this SAME placement found zero feasible envelopes)",
            classify_refusal(last_refusal.constraint)), None

    for scale in _ENVELOPE_RETRY_SCALES:
        scaled = embed_adjacency_graph(zones, required_edges, wing_id=brief_id,
                                        envelope_scale=scale)
        assert not isinstance(scaled, EmbeddingRefusal)
        intent = RealizationIntent(name=brief_id, wings=(scaled,), wet_rooms=wet_rooms)
        result = realize_layout(intent, buildable=buildable)
        if isinstance(result, RealizedLayout):
            w = scaled.width_m if not isinstance(scaled, PinwheelWing) else scaled.width_m
            return GateBResult(brief_id, True, f"scale {scale}", brief_footprint_m, None, None,
                                None), result
        last_refusal = result
        if result.constraint not in _DIMENSION_SOLVER_CONSTRAINTS:
            break

    assert last_refusal is not None
    return GateBResult(brief_id, False, None, brief_footprint_m, last_refusal.constraint,
                        last_refusal.detail, classify_refusal(last_refusal.constraint)), None


def run_selected_cases(dataset_path: str = generation_dataset.DEFAULT_GENERATION_DATASET_JSON
                        ) -> tuple[list[CaseReport], dict]:
    dataset = generation_dataset.load_dataset(dataset_path)
    pri = priors_mod.load_priors()
    by_id = {r["brief_id"]: r for r in dataset["records"]}
    cases = []
    for brief_id in SELECTED_BRIEF_IDS:
        record = by_id[brief_id]
        proposal = best_policy_valid_proposal(record, pri)
        brief_footprint = (record["brief"]["footprint_width_m"], record["brief"]["footprint_depth_m"])

        gate_a = run_gate_a(brief_id, proposal) if brief_id in GATE_A_BRIEF_IDS else None
        gate_b, realized = run_gate_b(brief_id, proposal, brief_footprint)

        spatial_pres = access_pres = None
        if realized is not None:
            spatial_pres = measure_spatial_adjacency(realized.rects, proposal.spatial_adjacency)
            room_access_edges = [(a, b) for a, b in proposal.access_graph if a != schema.ENTRANCE_ID]
            access_pres = measure_access_graph(realized.fixture.access.edges, room_access_edges)

        if gate_b.dimensioned:
            final_status, final_class, final_reason = "REALIZED", None, None
        else:
            final_status = "REFUSED"
            final_class = gate_b.failure_class
            final_reason = f"{gate_b.refusal_constraint}: {gate_b.refusal_detail}"

        cases.append(CaseReport(brief_id, proposal, gate_a, gate_b, realized, spatial_pres,
                                 access_pres, final_status, final_class, final_reason))
    return cases, dataset


def _fmt_envelope(gb: GateBResult) -> str:
    return gb.envelope_used or "—"


def render_results_md(cases: list[CaseReport], dataset: dict) -> str:
    lines: list[str] = []
    lines.append("# Realizability gap closure (Issue #162 / #142A)")
    lines.append("")
    lines.append(
        "Generalizes `app.vertical_slice.rectilinear_realizer` beyond the fixed 5-room pinwheel "
        "with a genuine 2D structural carrier (`GridWing`) and a matching dimension solver "
        "(`_solve_grid`), and runs #160's own frozen 5 selected cases (B01, B10, B13, B15, B16) "
        "through it via the new embedding decision layer (`graph_embedding."
        "embed_adjacency_graph`). No validator, access rule, room minimum, wet-core rule, critic "
        "or proposal datum changes anywhere in this work (AC-8)."
    )
    lines.append("")
    lines.append("## STOP RULE (AC-10)")
    lines.append("")
    lines.append(
        "**Did not fire.** The extension stayed bounded: one new `Wing` variant (`GridWing`) "
        "following the EXACT same pattern `PinwheelWing`/`RowWing` already establish (a dataclass "
        "+ a `_build_*_wing` function + a sizing solver), one new decision module "
        "(`graph_embedding.py`) that searches among the THREE existing wing shapes and refuses "
        "explicitly when none fits, and one small, central, additive fix "
        "(`_filter_wet_room_access`) for a pre-existing gap (no wing ever passed `wet_rooms` to "
        "`validate()`) that would otherwise have misclassified every wet-room-bearing case as a "
        "VALIDATOR failure regardless of this Issue's own structural work. No second realization "
        "engine, no change to `geometry_core`, no change to any validator/access rule/room minimum."
    )
    lines.append("")
    lines.append(
        f"**Frozen dataset (AC-7)**: `docs/reports/llm-topology-poc/generation-dataset.json`, "
        f"`dataset_sha256` `{dataset['dataset_sha256']}` — verified via "
        f"`generation_dataset.load_dataset()` (the SAME preflight #151 established: a canonical "
        f"re-hash of the file's own body, raising rather than silently proceeding on any "
        f"mismatch). No new LLM call, no change to any proposal, no case substituted after seeing "
        f"a failure (AC-7)."
    )
    lines.append("")

    lines.append("## Gate A — can the n>5 topologies be structurally PLACED? (AC-3)")
    lines.append("")
    lines.append(
        "Before any dimensioning: required spatial-adjacency edges, how many of them the chosen "
        "placement structurally achieves (geometric touching, verified against the real built "
        "rects whenever the case later reaches Gate B successfully), lost, extra, and which "
        "placement form (ROW / PINWHEEL / GRID RxC) the embedding search chose — or, when no "
        "available structure reaches full coverage, the honest best found."
    )
    lines.append("")
    lines.append("| brief | n rooms | required edges | structurally preserved | lost | extra | "
                  "placement form | embeddable |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for c in cases:
        if c.gate_a is None:
            continue
        ga = c.gate_a
        lines.append(f"| {ga.brief_id} | {ga.n_rooms} | {ga.required_edges} | "
                      f"{ga.structurally_preserved} | {ga.lost_edges} | {ga.extra_edges} | "
                      f"{ga.placement_form} | {ga.embeddable} |")
    n_embeddable = sum(1 for c in cases if c.gate_a is not None and c.gate_a.embeddable)
    lines.append("")
    lines.append(f"**{n_embeddable}/{len(GATE_A_BRIEF_IDS)} of the n>5 cases are structurally "
                  f"embeddable** by the generalized realizer (row/pinwheel/grid) — the measured "
                  f"answer to Gate A, before any sizing is attempted.")
    lines.append("")

    lines.append("## Gate B — can every placed case be DIMENSIONED? (AC-4)")
    lines.append("")
    lines.append(
        "All 5 cases, B01 included (never assumed feasible). No room minimum is weakened "
        "anywhere in this diff — every refusal below is `realize_layout`'s own, unmodified "
        "area/short-side/aspect check, or the embedding step's own honest TOPOLOGY_EMBEDDING "
        "refusal when Gate A itself already failed."
    )
    lines.append("")
    lines.append("| brief | dimensioned | envelope used | brief footprint (m) | refusal | "
                  "failure class |")
    lines.append("|---|---|---|---|---|---|")
    for c in cases:
        gb = c.gate_b
        fp = f"{gb.footprint_m[0]}x{gb.footprint_m[1]}" if gb.footprint_m else "—"
        refusal = f"{gb.refusal_constraint}" if gb.refusal_constraint else "—"
        lines.append(f"| {c.brief_id} | {gb.dimensioned} | {_fmt_envelope(gb)} | {fp} | "
                      f"{refusal} | {gb.failure_class or '—'} |")
    n_dimensioned = sum(1 for c in cases if c.gate_b.dimensioned)
    lines.append("")
    lines.append(f"**{n_dimensioned}/5 cases can be dimensioned** while preserving the structure "
                  f"and every hard room minimum.")
    lines.append("")

    lines.append("## Per-case final result (AC-9)")
    lines.append("")
    lines.append("| brief | topology (rooms/edges) | placement | adjacency preserved | access "
                  "preserved | dimension result | validator result | final status | reason |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for c in cases:
        n = len(c.proposal.rooms)
        edges = len(c.proposal.spatial_adjacency)
        placement = c.gate_a.placement_form if c.gate_a else (
            "PINWHEEL" if n == 5 else "—")
        adj = f"{c.spatial_preservation.preserved}/{c.spatial_preservation.requested}" \
            if c.spatial_preservation else "—"
        acc = f"{c.access_preservation.preserved}/{c.access_preservation.requested}" \
            if c.access_preservation else "—"
        dim_result = "OK" if c.gate_b.dimensioned else (c.gate_b.failure_class or "FAILED")
        validator_result = "PASS" if c.realized is not None else "NOT REACHED"
        reason = c.final_reason or "—"
        lines.append(f"| {c.brief_id} | {n}/{edges} | {placement} | {adj} | {acc} | {dim_result} "
                      f"| {validator_result} | {c.final_status} | {reason} |")
    lines.append("")

    n_realized = sum(1 for c in cases if c.final_status == "REALIZED")
    n_topology_preserving = sum(
        1 for c in cases if c.spatial_preservation is not None
        and preservation_verdict(c.spatial_preservation) == "PASS")
    n_validator_passing = sum(1 for c in cases if c.realized is not None and c.realized.report.ok)
    lines.append(f"**realized/5: {n_realized}** · **topology-preserving/5: "
                  f"{n_topology_preserving}** · **validator-passing/5: {n_validator_passing}**")
    lines.append("")

    lines.append("## Preservation detail, per realized case (AC-5)")
    lines.append("")
    realized_cases = [c for c in cases if c.realized is not None]
    if not realized_cases:
        lines.append("No selected case realized in this run — nothing to measure preservation on.")
    else:
        for c in realized_cases:
            sp, ap = c.spatial_preservation, c.access_preservation
            v = preservation_verdict(sp)
            lines.append(f"- **{c.brief_id}** — spatial adjacency {sp.preserved}/{sp.requested} "
                          f"(verdict {v}), access graph {ap.preserved}/{ap.requested}"
                          + (f"; lost: {', '.join(sp.lost)}" if sp.lost else "; nothing lost") + ".")
    lines.append("")

    lines.append("## Failure classification (AC-6)")
    lines.append("")
    lines.append(
        "Every refusal above is exactly one of **TOPOLOGY_EMBEDDING** (Gate A itself could not "
        "embed the requested graph in any available structure), **PLACEMENT** (a structure was "
        "selected but no room-to-slot assignment of it could satisfy the request), "
        "**DIMENSION_SOLVER** (structure embedded, but no envelope this run's retry "
        "ladder tried could size every room within its own hard minimum), "
        "**FOOTPRINT_INFEASIBLE** (the realized footprint exceeds the brief's own stated "
        "footprint), **REALIZER_INTERNAL** (a construction defect unrelated to sizing or "
        "topology), or **VALIDATOR** (`validation.validate` rejected the realized geometry) — "
        "never a generic \"cannot realize\". **Disclosed gap**: `PLACEMENT` is not produced by "
        "any code path in this implementation — `graph_embedding.embed_adjacency_graph` decides "
        "\"which structure\" and \"which assignment of it\" together in one search and reports "
        "every shortfall as `TOPOLOGY_EMBEDDING` (the best structure/assignment pair found), "
        "never distinguishing \"no structure could ever fit\" from \"a structure was selected "
        "but its own assignment search fell short\". This is honestly reported as an unreached "
        "bucket, not demonstrated by a constructed example."
    )
    lines.append("")

    lines.append("## Remaining measured capability gaps")
    lines.append("")
    gaps = []
    for c in cases:
        if c.final_status == "REFUSED":
            gaps.append(f"- **{c.brief_id}**: {c.final_failure_class} — {c.final_reason}")
    if gaps:
        lines.extend(gaps)
    else:
        lines.append("- None of the 5 selected cases refused in this run.")
    lines.append("")

    lines.append("## Reproducing this report")
    lines.append("")
    lines.append("```")
    lines.append("cd backend")
    lines.append("uv run python -m app.ai_harness.topology_poc.gap_closure_142a")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=generation_dataset.DEFAULT_GENERATION_DATASET_JSON)
    parser.add_argument("--write-report", default=DEFAULT_RESULTS_MD)
    args = parser.parse_args(argv)

    cases, dataset = run_selected_cases(args.dataset)
    text = render_results_md(cases, dataset)

    os.makedirs(os.path.dirname(args.write_report), exist_ok=True)
    with open(args.write_report, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"wrote {args.write_report}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
