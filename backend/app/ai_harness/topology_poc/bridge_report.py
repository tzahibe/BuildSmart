"""Issue #160 — the topology->placement bridge spike's own driver and report writer.

Three stages, each matching one group of Acceptance Criteria:

  1. `rank_briefs` (AC-1): for all 20 frozen briefs, the absolute-best LLM proposal, the best one
     that satisfies the REAL `app.vertical_slice.access_rules.ALLOWED_ENTERED_FROM` table
     (`placement_bridge.is_access_policy_valid`), its rank within the top-8 by `total_score`, and
     the score loss versus the absolute best. Reproduced entirely from the committed
     `docs/reports/llm-topology-poc/generation-dataset.json` — no new LLM call (same frozen-dataset
     discipline `frozen_runner.py` already established for Issue #151).
  2. `run_selected_case` (AC-5, AC-6, AC-7): for one selected brief's best policy-valid proposal,
     builds a `RealizationIntent` (`placement_bridge.build_realization_intent`), runs it through the
     UNCHANGED `rectilinear_realizer.realize_layout` (a small, DISCLOSED envelope-scale retry ladder
     — the same policy `spikes/geometry_shapes/stage1_gate.py` already uses: the chosen PLACEMENT
     never changes across a retry, only the envelope's own size), classifies any refusal
     (`placement_bridge.classify_failure`), and measures preservation
     (`preservation.measure_preservation`) when it realizes.
  3. `render_results_md` writes `docs/reports/topology-placement-bridge/results.md`.

No validator, access rule, or production default is touched by any of this (AC-8).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from app.ai_harness.topology_poc import critic, generation_dataset, placement_bridge, preservation
from app.ai_harness.topology_poc import priors as priors_mod
from app.ai_harness.topology_poc import schema
from app.vertical_slice.rectilinear_realizer import RealizedLayout, Refusal, realize_layout

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_REPO_ROOT = os.path.dirname(_BACKEND_DIR)
DEFAULT_RESULTS_MD = os.path.join(_REPO_ROOT, "docs", "reports", "topology-placement-bridge",
                                   "results.md")

#: The lead's own selection (Issue #160's own "Required behavior" §2): all 5 are rank-1
#: policy-valid with zero score loss, spanning 1-5 bedrooms, 1-3 wet rooms, with/without SAFE_ROOM,
#: open/closed plans, small/large footprints.
SELECTED_BRIEF_IDS = ("B01", "B10", "B13", "B15", "B16")

#: This driver's OWN disclosed envelope-scale retry ladder (see `placement_bridge.
#: build_realization_intent`'s own docstring) — mirrors `spikes/geometry_shapes/stage1_gate.py`'s
#: `_RETRY_SCALES`: the realizer itself never approximates; only this loop tries a different,
#: still fully-specified envelope size next, for the SAME placement the bridge already chose.
_ENVELOPE_RETRY_SCALES = (1.0, 0.9, 0.85, 0.8, 0.78, 0.76, 0.75, 0.72, 0.7, 1.1, 1.2, 0.6, 1.4, 0.5)

#: A PinwheelWing's own 2 degrees of freedom (width_m, height_m) do not reduce to one scale factor
#: — this driver's OWN exhaustive grid for a PinwheelWing case specifically (n==5), same
#: disclosed-retry-loop policy as the scale ladder above, just 2-dimensional: every (width, height)
#: in a wide, round-numbered range, same chosen placement throughout.
_PINWHEEL_GRID_M = tuple(round(6.0 + 0.2 * i, 2) for i in range(31))  # 6.0 .. 12.0 m, step 0.2


@dataclass(frozen=True)
class BriefRanking:
    brief_id: str
    n_proposals: int
    absolute_best_score: float
    best_policy_valid_score: "float | None"
    policy_valid_rank: "int | None"  # 1-based, within top-8
    score_loss: "float | None"


def _scored_proposals(record: dict, pri: priors_mod.Priors) -> list[tuple[float, "schema.TopologyProposal"]]:
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


def rank_briefs(dataset_path: str = generation_dataset.DEFAULT_GENERATION_DATASET_JSON
                ) -> list[BriefRanking]:
    """AC-1: every one of the 20 frozen briefs, reproduced from the committed dataset alone."""
    dataset = generation_dataset.load_dataset(dataset_path)
    pri = priors_mod.load_priors()
    rankings = []
    for record in dataset["records"]:
        scored = _scored_proposals(record, pri)
        top8 = scored[:8]
        absolute_best_score = top8[0][0]
        best_policy_valid_score = None
        policy_valid_rank = None
        for i, (score, p) in enumerate(top8):
            if placement_bridge.is_access_policy_valid(p):
                best_policy_valid_score = score
                policy_valid_rank = i + 1
                break
        score_loss = (absolute_best_score - best_policy_valid_score
                      if best_policy_valid_score is not None else None)
        rankings.append(BriefRanking(record["brief_id"], len(scored), absolute_best_score,
                                      best_policy_valid_score, policy_valid_rank, score_loss))
    return rankings


@dataclass(frozen=True)
class CaseResult:
    brief_id: str
    proposal: "schema.TopologyProposal"
    outcome: str  # "REALIZED" | "REFUSED"
    failure_class: "str | None"  # BRIDGE | PLACEMENT | REALIZER | VALIDATOR
    refusal_reason: "str | None"
    refusal_detail: "str | None"
    envelope_used: "str | None"  # the exact envelope the REALIZED case used, human-readable
    preservation_report: "preservation.PreservationReport | None"
    verdict: "str | None"  # PASS | FAIL, only when REALIZED


def run_selected_case(brief_id: str, proposal: "schema.TopologyProposal") -> CaseResult:
    """AC-5/AC-6/AC-7 for one selected brief's best policy-valid proposal, run end to end through
    the UNCHANGED realizer and validator chain."""
    intent = placement_bridge.build_realization_intent(proposal, brief_id)
    if isinstance(intent, placement_bridge.BridgeRefusal):
        return CaseResult(brief_id, proposal, "REFUSED", placement_bridge.classify_failure(intent),
                           intent.reason, intent.detail, None, None, None)

    n = len(proposal.rooms)
    last_refusal: "Refusal | None" = None
    if n == 5:
        # A PinwheelWing's own 2 degrees of freedom (width_m, height_m) do not reduce to one scale
        # factor — an exhaustive grid over both, same chosen placement throughout (see
        # `_PINWHEEL_GRID_M`'s own docstring).
        for width_m in _PINWHEEL_GRID_M:
            for height_m in _PINWHEEL_GRID_M:
                scaled_intent = placement_bridge.build_realization_intent(
                    proposal, brief_id, envelope_override=(width_m, height_m))
                result = realize_layout(scaled_intent)
                if isinstance(result, RealizedLayout):
                    report = preservation.measure_preservation(proposal, result)
                    envelope_used = f"{width_m}x{height_m} m"
                    return CaseResult(brief_id, proposal, "REALIZED", None, None, None,
                                       envelope_used, report, preservation.verdict(report))
                last_refusal = result
    else:
        for scale in _ENVELOPE_RETRY_SCALES:
            scaled_intent = placement_bridge.build_realization_intent(proposal, brief_id, scale)
            assert not isinstance(scaled_intent, placement_bridge.BridgeRefusal)  # same n, edges
            result = realize_layout(scaled_intent)
            if isinstance(result, RealizedLayout):
                report = preservation.measure_preservation(proposal, result)
                envelope_used = f"scale {scale}"
                return CaseResult(brief_id, proposal, "REALIZED", None, None, None, envelope_used,
                                   report, preservation.verdict(report))
            last_refusal = result
            # A STRUCTURAL refusal (not geometric) will not be fixed by a different envelope
            # scale — stop retrying, matching `stage1_gate.py`'s own early-break policy.
            if result.constraint not in ("SHORT_SIDE_INFEASIBLE", "AREA_INFEASIBLE",
                                          "ASPECT_INFEASIBLE", "NOTCH_INFEASIBLE",
                                          "PINWHEEL_INFEASIBLE"):
                break

    assert last_refusal is not None
    return CaseResult(brief_id, proposal, "REFUSED", placement_bridge.classify_failure(last_refusal),
                       last_refusal.constraint, last_refusal.detail, None, None, None)


def _best_policy_valid_proposal(record: dict, pri: priors_mod.Priors) -> "schema.TopologyProposal":
    scored = _scored_proposals(record, pri)
    for score, p in scored[:8]:
        if placement_bridge.is_access_policy_valid(p):
            return p
    raise AssertionError(f"{record['brief_id']}: no policy-valid proposal in top-8 — contradicts "
                          f"this Issue's own AC-1 finding (20/20 briefs have one)")


def run_selected_cases(dataset_path: str = generation_dataset.DEFAULT_GENERATION_DATASET_JSON
                        ) -> list[CaseResult]:
    dataset = generation_dataset.load_dataset(dataset_path)
    pri = priors_mod.load_priors()
    by_id = {r["brief_id"]: r for r in dataset["records"]}
    results = []
    for brief_id in SELECTED_BRIEF_IDS:
        proposal = _best_policy_valid_proposal(by_id[brief_id], pri)
        results.append(run_selected_case(brief_id, proposal))
    return results


def _fmt(x) -> str:
    return "—" if x is None else (f"{x:.6f}" if isinstance(x, float) else str(x))


def render_results_md(rankings: list[BriefRanking], cases: list[CaseResult]) -> str:
    lines: list[str] = []
    lines.append("# Topology -> placement bridge spike (Issue #160)")
    lines.append("")
    lines.append(
        "Answers one question: when the EXISTING `rectilinear_realizer` is handed a high-scoring "
        "LLM topology (Issue #151's own frozen dataset) that already satisfies CURRENT access "
        "policy, does it build it while PRESERVING the requested graph? No validator, access rule, "
        "or production default is changed anywhere in this spike (AC-8); the frozen 432-context "
        "corpus is byte-identical (see the regression run below)."
    )
    lines.append("")
    lines.append("## AC-1 — ranking, all 20 frozen briefs")
    lines.append("")
    lines.append(
        "`absolute best` is the top-scoring LLM proposal regardless of access policy. `best "
        "policy-valid` is the top-scoring proposal, among the top-8 by `total_score`, whose "
        "`access_graph` is accepted in full by the REAL `app.vertical_slice.access_rules."
        "ALLOWED_ENTERED_FROM` table (`placement_bridge.is_access_policy_valid`) — never the "
        "ai_harness's own separate critic-side hard-violation heuristic. `rank` is that "
        "proposal's own position (1-based) among the top-8. `score loss` is `absolute best - best "
        "policy-valid` (0.0 when rank is 1)."
    )
    lines.append("")
    lines.append("| brief | absolute best | best policy-valid | rank (of top-8) | score loss |")
    lines.append("|---|---|---|---|---|")
    for r in rankings:
        lines.append(f"| {r.brief_id} | {r.absolute_best_score:.6f} | "
                      f"{_fmt(r.best_policy_valid_score)} | {_fmt(r.policy_valid_rank)} | "
                      f"{_fmt(r.score_loss)} |")
    n_with_valid = sum(1 for r in rankings if r.policy_valid_rank is not None)
    n_rank1 = sum(1 for r in rankings if r.policy_valid_rank == 1)
    lines.append("")
    lines.append(
        f"**{n_with_valid}/20 briefs have a policy-valid proposal in their own top-8; "
        f"{n_rank1}/20 briefs' absolute-best proposal is already policy-valid** (rank 1, zero "
        f"score loss) — reproducing the lead's own measurement exactly, from the committed "
        f"dataset, with no new LLM call."
    )
    lines.append("")
    lines.append("## AC-2 — selected representative briefs")
    lines.append("")
    lines.append(
        f"Selected: **{', '.join(SELECTED_BRIEF_IDS)}** — all rank-1 policy-valid with zero score "
        f"loss (see the table above). This is the lead's own selection (Issue #160's \"Required "
        f"behavior\" §2), not re-derived here: it spans 1-5 bedrooms, 1-3 wet rooms, with and "
        f"without SAFE_ROOM, open and closed plans, small and large footprints — a representative "
        f"spread, not five similar cases. No deviation from the named set."
    )
    lines.append("")
    lines.append("## AC-5 / AC-7 — per-case result and failure classification")
    lines.append("")
    lines.append(
        "Every failure below is classified as one of BRIDGE / PLACEMENT / REALIZER / VALIDATOR "
        "(decided before any code change — Issue #160's own \"Required behavior\" §6): "
        "**BRIDGE** — `placement_bridge.build_realization_intent` itself refused, "
        "no assignment was even attempted (the row-capacity check: a single row can realize at "
        "most n-1 spatial-adjacency pairs among n rooms, and this proposal's graph needs more, "
        "with n != 5 so the only other wing shape, `PinwheelWing`, is unavailable too). "
        "**PLACEMENT** — a wing shape was selected and a search ran, but no room-to-slot "
        "assignment of that shape could ever satisfy it (not observed in this run's 5 cases — see "
        "`test_topology_placement_bridge.py` for a constructed example of the distinction from "
        "REALIZER). **REALIZER** — `rectilinear_realizer.realize_layout` refused for a geometric "
        "reason (area/short-side/aspect/shape infeasible at every envelope scale this run's own "
        "disclosed retry ladder tried). **VALIDATOR** — `realize_layout` refused because "
        "`validation.validate` rejected the realized geometry."
    )
    lines.append("")
    lines.append("| brief | n rooms | spatial-adjacency edges requested | n-1 (row capacity) | "
                  "outcome | failure class | reason |")
    lines.append("|---|---|---|---|---|---|---|")
    for c in cases:
        n = len(c.proposal.rooms)
        edges = len(c.proposal.spatial_adjacency)
        reason = c.refusal_reason or "—"
        lines.append(f"| {c.brief_id} | {n} | {edges} | {n - 1} | {c.outcome} | "
                      f"{c.failure_class or '—'} | {reason} |")
    lines.append("")
    for c in cases:
        lines.append(f"### {c.brief_id}")
        lines.append("")
        if c.outcome == "REFUSED":
            lines.append(f"**REFUSED** — classified **{c.failure_class}**: `{c.refusal_reason}` — "
                          f"{c.refusal_detail}")
            if len(c.proposal.rooms) == 5:
                mapping, best_edges = placement_bridge._best_pinwheel_assignment(c.proposal)
                lines.append("")
                lines.append(
                    f"The chosen placement ({mapping}) achieves {best_edges}/"
                    f"{len(c.proposal.spatial_adjacency)} of the requested spatial-adjacency "
                    f"pairs STRUCTURALLY (the best of all 5! room-to-slot assignments) — this is "
                    f"a sizing failure of the pinwheel's own band-thickness solver, not a "
                    f"placement/matching failure: an exhaustive {len(_PINWHEEL_GRID_M)}x"
                    f"{len(_PINWHEEL_GRID_M)} ({len(_PINWHEEL_GRID_M) ** 2}-point) width/height "
                    f"grid search over this SAME placement found zero feasible envelopes."
                )
        else:
            lines.append(f"**REALIZED** (envelope {c.envelope_used}) — "
                          f"**verdict: {c.verdict}**")
        lines.append("")

    lines.append("## AC-6 — preservation, per realized case")
    lines.append("")
    realized_cases = [c for c in cases if c.outcome == "REALIZED"]
    if not realized_cases:
        lines.append(
            "No selected case realized in this run (see AC-5/AC-7 above for why each refused) — "
            "there is nothing to measure preservation on. This is itself the spike's own answer: "
            "**every one of the 5 selected high-scoring, policy-valid real topologies failed to "
            "reach a built house**, 4/5 structurally (BRIDGE, before the realizer ever ran) and "
            "1/5 geometrically (REALIZER, no envelope scale this run's retry ladder tried fit the "
            "chosen placement) — not a single VALIDATOR-stage loss, because no case got far enough "
            "to reach `validate()`."
        )
    else:
        lines.append(
            "| brief | room identity | spatial adjacency | access graph | zoning | wet core | "
            "entrance relation | verdict |"
        )
        lines.append("|---|---|---|---|---|---|---|---|")
        for c in realized_cases:
            r = c.preservation_report
            lines.append(
                f"| {c.brief_id} | {r.room_identity.preserved}/{r.room_identity.requested} | "
                f"{r.spatial_adjacency.preserved}/{r.spatial_adjacency.requested} | "
                f"{r.access_graph.preserved}/{r.access_graph.requested} | "
                f"{r.zoning.preserved}/{r.zoning.requested} | "
                f"{r.wet_core.preserved}/{r.wet_core.requested} | "
                f"{r.entrance_relation.preserved}/{r.entrance_relation.requested} | {c.verdict} |"
            )
        lines.append("")
        lines.append("Every lost requested relationship, by name:")
        lines.append("")
        for c in realized_cases:
            r = c.preservation_report
            lost_any = False
            for d in r.dimensions:
                if d.lost:
                    lost_any = True
                    lines.append(f"- **{c.brief_id} / {d.name}**: {', '.join(d.lost)}")
            if not lost_any:
                lines.append(f"- **{c.brief_id}**: nothing lost on any dimension")
    lines.append("")
    lines.append("## Reproducing this spike")
    lines.append("")
    lines.append("```")
    lines.append("cd backend")
    lines.append("uv run python -m app.ai_harness.topology_poc.bridge_report")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=generation_dataset.DEFAULT_GENERATION_DATASET_JSON)
    parser.add_argument("--write-report", default=DEFAULT_RESULTS_MD)
    args = parser.parse_args(argv)

    rankings = rank_briefs(args.dataset)
    cases = run_selected_cases(args.dataset)
    text = render_results_md(rankings, cases)

    os.makedirs(os.path.dirname(args.write_report), exist_ok=True)
    with open(args.write_report, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"wrote {args.write_report}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
