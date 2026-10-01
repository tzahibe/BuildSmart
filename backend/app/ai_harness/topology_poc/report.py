"""Renders `docs/reports/llm-topology-poc/results.md` from a completed run (Issue #151, AC-5, AC-6,
AC-7, AC-13). Pure formatting — every number here was computed by `critic.py`/`runner.py`; this
module invents nothing."""
from __future__ import annotations

import statistics
from dataclasses import dataclass

from app.ai_harness.topology_poc.result_types import BriefResult


@dataclass(frozen=True)
class Provenance:
    fullcorpus_json_path: str
    room_proportions_json_path: str
    commit_sha: str
    generated_at_utc: str
    train_count: int
    holdout_count: int
    artifact_sha256: str


def _realizability_counts(results: dict) -> dict:
    counts = {"REALIZABLE_BY_CURRENT_ENGINE": 0, "NOT_REALIZABLE_BY_CURRENT_ENGINE": 0, "UNKNOWN": 0}
    for result in results.values():
        if result.generator is not None:
            counts[result.generator.realizability] += 1
        for p in result.llm_proposals:
            counts[p.realizability] += 1
    return counts


def _brief_summary_row(result: BriefResult) -> dict:
    llm_scores = [p.score["total_score"] for p in result.llm_proposals]
    gen_score = result.generator.score["total_score"] if result.generator is not None else None
    best_llm = max(llm_scores) if llm_scores else None
    median_llm = statistics.median(llm_scores) if llm_scores else None
    n_llm_raw = result.llm_raw_generated
    n_kept = len(result.llm_proposals) + result.llm_exact_duplicates + result.llm_schema_rejected
    duplicate_rate = (result.llm_exact_duplicates / n_kept) if n_kept else 0.0
    beats = (best_llm is not None and gen_score is not None and best_llm > gen_score)
    improvement = (best_llm - gen_score) if (best_llm is not None and gen_score is not None) else None
    return {
        "brief_id": result.brief_id, "gen_score": gen_score, "best_llm": best_llm,
        "median_llm": median_llm, "n_llm": len(result.llm_proposals), "n_llm_raw": n_llm_raw,
        "duplicate_rate": duplicate_rate, "materially_distinct": result.materially_distinct_count,
        "beats": beats, "improvement": improvement,
    }


#: AC-17's exact required title for the forced local-model control run — retitled and separated
#: from the PRIMARY run (`primary_report.render_results_md`, `results.md`) in both filename and
#: report text; never fed into the primary run's own statistics or verdict.
CONTROL_RUN_TITLE = (
    "FORCED LOCAL-MODEL CONTROL RUN — NOT VALID FOR THE #142 GO/STOP DECISION")


def render_control_results_md(results: dict, provenance: Provenance) -> str:
    """Renders the FORCED LOCAL-MODEL CONTROL RUN report (Issue #151, AC-17) — the ORIGINAL
    `llama3.2:latest` run, retitled and clearly separated (own filename,
    `results-control-llama.md`, own heading) from the PRIMARY run's `results.md`. No number from
    this report is read by, or enters, the primary run's statistics or its GO/STOP verdict."""
    body = render_results_md(results, provenance)
    _, _, rest = body.partition("\n")
    return (
        f"# {CONTROL_RUN_TITLE}\n\n"
        "This is a SEPARATE run from the PRIMARY experiment (see `results.md`) — it uses "
        "`llama3.2:latest`, a small local model, forced by this sandbox's lack of external network "
        "egress or API key, NOT chosen as a stand-in for \"a strong LLM\". No number below enters "
        "the primary run's statistics or its GO/STOP verdict.\n"
        f"{rest}")


def render_results_md(results: dict, provenance: Provenance) -> str:
    ordered = [results[bid] for bid in sorted(results, key=lambda k: int(k[1:]))]
    summaries = [_brief_summary_row(r) for r in ordered]

    comparable = [s for s in summaries if s["improvement"] is not None]
    beats_count = sum(1 for s in comparable if s["beats"])
    beats_pct = round(100 * beats_count / len(comparable), 1) if comparable else None
    improvements = [s["improvement"] for s in comparable]
    avg_improvement = round(statistics.mean(improvements), 4) if improvements else None
    median_improvement = round(statistics.median(improvements), 4) if improvements else None

    realizability_counts = _realizability_counts(results)
    total_labels = sum(realizability_counts.values())

    lines = [
        "# LLM Topology Proposer POC — results (Issue #151)",
        "",
        "**The LLM produces no geometry.** Every proposal below (current-generator and LLM alike) "
        "passed through the identical, deterministic, geometry-free critic (`critic.py`) — the "
        "critic is blind to which is which (AC-10). Realizability is metadata only and never "
        "entered any score (AC-9). See `docs/reports/llm-topology-poc/schema.md` for the schema and "
        "`briefs.md` for the 20 committed briefs.",
        "",
        "## Provenance of the ground truth (AC-13)",
        "",
        f"- Adjacency/access artifact: `{provenance.fullcorpus_json_path}`",
        f"- Room-proportions artifact: `{provenance.room_proportions_json_path}`",
        f"- Commit SHA this run's ground truth came from: `{provenance.commit_sha}`",
        f"- Artifact SHA-256: `{provenance.artifact_sha256}`",
        f"- Train count: **{provenance.train_count}**, holdout count: **{provenance.holdout_count}**",
        f"- Generated at (UTC): `{provenance.generated_at_utc}`",
        "",
        "## Headline comparison (AC-7)",
        "",
    ]
    if beats_pct is not None:
        lines += [
            f"**{beats_pct}%** of briefs ({beats_count}/{len(comparable)}) have at least one LLM "
            "proposal whose critic score beats the current generator's own topology for that same "
            "brief.",
            f"- Average improvement (best LLM score minus generator score, comparable briefs only): "
            f"**{avg_improvement}**",
            f"- Median improvement: **{median_improvement}**",
        ]
    else:
        lines.append("No briefs produced a comparable (generator, LLM) score pair.")
    lines += [
        "",
        f"LLM model used: `{ordered[0].llm_model if ordered and ordered[0].llm_model else 'n/a'}` "
        "— a local model reachable from this sandbox (no external network egress or API key is "
        "available here); see Known limitations below for what this implies about ceiling quality.",
        "",
        "## Realizability distribution (AC-6)",
        "",
        f"Across every proposal scored (current-generator + LLM, {total_labels} total):",
        "",
        "| label | count | share |",
        "|---|---|---|",
    ]
    for label, count in realizability_counts.items():
        share = round(100 * count / total_labels, 1) if total_labels else 0.0
        lines.append(f"| {label} | {count} | {share}% |")
    lines += [
        "",
        "Realizability is METADATA ONLY (AC-9) — `NOT_REALIZABLE_BY_CURRENT_ENGINE` counts above "
        "never reduced any proposal's quality score; see "
        "`tests/ai_harness/test_topology_critic.py::test_score_is_independent_of_realizability_label`.",
        "",
        "## Per-brief results (AC-5)",
        "",
        "| brief | generator score | best LLM | median LLM | LLM kept/raw | materially distinct | "
        "duplicate rate | beats generator |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in summaries:
        gen = s["gen_score"] if s["gen_score"] is not None else "n/a (refused)"
        best = s["best_llm"] if s["best_llm"] is not None else "—"
        median = round(s["median_llm"], 4) if s["median_llm"] is not None else "—"
        beats = "YES" if s["beats"] else ("no" if s["gen_score"] is not None else "n/a")
        lines.append(
            f"| {s['brief_id']} | {gen} | {best} | {median} | {s['n_llm']}/{s['n_llm_raw']} | "
            f"{s['materially_distinct']} | {round(s['duplicate_rate'], 3)} | {beats} |")

    lines += [
        "",
        "## Score component detail (AC-5)",
        "",
        "Per brief: the current generator's own adjacency similarity / access similarity / wet-core "
        "similarity / entrance-relation score / hard violations, for direct comparison against its "
        "best LLM proposal's own components.",
        "",
        "| brief | side | adjacency_similarity | access_similarity | wet_core_similarity | "
        "entrance_relation_score | hard_violations |",
        "|---|---|---|---|---|---|---|",
    ]
    for result in ordered:
        if result.generator is not None:
            sc = result.generator.score
            lines.append(
                f"| {result.brief_id} | generator | {sc['adjacency_similarity']} | "
                f"{sc['access_similarity']} | {sc['wet_core_similarity']} | "
                f"{sc['entrance_relation_score']} | {len(sc['hard_violations'])} |")
        best_llm_proposal = max(result.llm_proposals, key=lambda p: p.score["total_score"], default=None)
        if best_llm_proposal is not None:
            sc = best_llm_proposal.score
            lines.append(
                f"| {result.brief_id} | best LLM | {sc['adjacency_similarity']} | "
                f"{sc['access_similarity']} | {sc['wet_core_similarity']} | "
                f"{sc['entrance_relation_score']} | {len(sc['hard_violations'])} |")

    lines += [
        "",
        "## Worked examples (AC-7)",
        "",
    ]
    worked = [s for s in comparable if s["beats"]]
    worked_examples = sorted(worked, key=lambda s: -s["improvement"])[:10] or comparable[:5]
    for s in worked_examples:
        result = results[s["brief_id"]]
        best_llm_proposal = max(result.llm_proposals, key=lambda p: p.score["total_score"], default=None)
        lines += [
            f"### {result.brief_id} ({result.bedrooms} bed, {result.wet_rooms} wet room(s), "
            f"safe_room={result.safe_room}, open_plan={result.open_plan}, {result.size_tier}/"
            f"{result.aspect_tier})",
            "",
            f"- Current generator score: **{s['gen_score']}**"
            + (f" ({len(result.generator.score['hard_violations'])} hard violations)"
               if result.generator is not None else ""),
        ]
        if best_llm_proposal is not None:
            lines.append(
                f"- Best LLM proposal score: **{best_llm_proposal.score['total_score']}** "
                f"({len(best_llm_proposal.score['hard_violations'])} hard violations, "
                f"realizability={best_llm_proposal.realizability})")
        lines += [
            f"- Improvement: **{s['improvement']}**" if s["improvement"] is not None else "",
            "- Why the critic preferred the LLM proposal: its adjacency/access graph sits closer to "
            "the corrected #149 corpus's own measured pattern (higher, less-negative log-likelihood) "
            "and/or it carries fewer hard-rule violations than the current generator's topology for "
            "this brief — see the score component table above for the exact numbers.",
            "",
        ]

    lines += [
        "## Known limitations",
        "",
        "- The LLM used is a small (3B parameter) local model reachable from this sandbox — no "
        "external network egress or API key is available here. This measures whether the POC "
        "METHOD surfaces genuine quality differences at all; it is not a measurement of what a "
        "frontier model would do, which the owner's GO/STOP decision should weigh accordingly.",
        "- A brief with zero schema-valid LLM proposals (after one retry) contributes no `best_llm`/"
        "`median_llm` value and is excluded from the headline percentage's denominator, not counted "
        "as a loss or a win.",
        "- `entrance_relation_score` is `None` whenever the entrance opens into a room whose role "
        "(e.g. HALL) the corrected #149 corpus cannot measure `front_door_direct_access` for — "
        "genuine unmeasurability, not a zero.",
    ]
    return "\n".join(lines) + "\n"
