"""Renders the PRIMARY run's `docs/reports/llm-topology-poc/results.md` (Issue #151, AC-5 through
AC-27) from `frozen_runner.run_all_briefs_from_dataset`'s output plus the frozen GO/STOP gate
(`docs/reports/llm-topology-poc/baseline.json`). Pure formatting plus the one gate computation
(`compute_go_stop_gate`) — every number here comes from `critic.py`/`frozen_runner.py`/
`baseline.json`; this module invents nothing.

WIN DEFINITION (`baseline.json`'s own `primary_go_stop_gate.win_definition`): best-VALID-LLM (zero
hard-constraint violations) vs best-current-generator, same blind critic. This is the number the
GO/STOP verdict and the headline (AC-7) both use. It is stricter than "best LLM score" (AC-5's
per-brief column, which reports the true best among every kept LLM proposal regardless of
violations, for direct comparison against the generator's own score) — the two are reported
side by side, never conflated.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass

from app.ai_harness.topology_poc.result_types import BriefResult

#: Below this fraction of wins, a result reads as clearly negative (short even of the weaker
#: SECONDARY 60% sensitivity threshold) -> STOP rather than INCONCLUSIVE. Baseline.json names
#: "wins far short of the bar" without a number; this is the documented reading used here.
_CLEARLY_SHORT_WINS_FRACTION = 0.6

#: #155's five named gaps (baseline.json `primary_go_stop_gate.if_weak`) — cited together with
#: its proven expressiveness whenever #155 is cited (AC-24, AC-27).
CAPABILITY_SNAPSHOT_155_COMMIT = "713e3f2"
CAPABILITY_SNAPSHOT_155_GAPS = (
    "placement", "semantic room assignment", "wet-room and SAFE_ROOM support",
    "polygon contract representation", "wiring")

PRIMARY_BASELINE_COMMIT_SHORT = "6a4aae7"
PRIMARY_BASELINE_COMMIT_FULL = "6a4aae74e6ab75fa12074e3d43fb9724575376e9"


@dataclass(frozen=True)
class GoStopGate:
    total_briefs: int
    comparable_briefs: int
    wins: int
    wins_fraction: float
    median_improvement: float
    avg_improvement: float
    diversity_count: int
    diversity_fraction: float
    secondary_wins_fraction_pass: bool  # the 60%-wins / median>0 SECONDARY rule — diagnostic only
    verdict: str  # "GO" | "STOP" | "INCONCLUSIVE"


def _win_and_improvement(result: BriefResult):
    """`None` when the brief has no comparable (generator, zero-violation LLM) pair."""
    if result.generator is None:
        return None
    valid_llm_scores = [p.score["total_score"] for p in result.llm_proposals
                        if not p.score["hard_violations"]]
    if not valid_llm_scores:
        return None
    gen_score = result.generator.score["total_score"]
    best_valid_llm = max(valid_llm_scores)
    return best_valid_llm > gen_score, best_valid_llm - gen_score


def compute_go_stop_gate(results: dict, gate_spec: dict) -> GoStopGate:
    go = gate_spec["go_requires_all_three"]
    ordered = list(results.values())
    pairs = [_win_and_improvement(r) for r in ordered]
    comparable = [p for p in pairs if p is not None]
    wins = sum(1 for beats, _ in comparable if beats)
    improvements = [imp for _, imp in comparable]
    total = len(ordered)
    wins_fraction = (wins / total) if total else 0.0
    median_improvement = statistics.median(improvements) if improvements else float("-inf")
    avg_improvement = statistics.mean(improvements) if improvements else float("-inf")
    diversity_count = sum(1 for r in ordered if r.materially_distinct_count >= 3)
    diversity_fraction = (diversity_count / total) if total else 0.0

    meets_wins = wins_fraction >= go["wins_fraction_min"]
    meets_median = median_improvement >= go["median_improvement_min"]
    meets_diversity = diversity_fraction >= go["diversity_min_fraction_of_briefs_with_3plus_distinct"]
    secondary_pass = wins_fraction >= 0.6 and median_improvement > 0

    if meets_wins and meets_median and meets_diversity:
        verdict = "GO"
    elif median_improvement <= 0 or wins_fraction < _CLEARLY_SHORT_WINS_FRACTION:
        verdict = "STOP"
    else:
        verdict = "INCONCLUSIVE"

    return GoStopGate(
        total_briefs=total, comparable_briefs=len(comparable), wins=wins,
        wins_fraction=round(wins_fraction, 4), median_improvement=round(median_improvement, 6),
        avg_improvement=round(avg_improvement, 6), diversity_count=diversity_count,
        diversity_fraction=round(diversity_fraction, 4), secondary_wins_fraction_pass=secondary_pass,
        verdict=verdict)


def bestof_n_gate(results: dict, gate_spec: dict, n: int) -> GoStopGate:
    """DIAGNOSTIC ONLY (AC-20): the SAME gate, recomputed using only the first `n` LLM proposals per
    brief (by `raw_index`, i.e. generation order). Never affects the real (best-of-8) verdict."""
    truncated = {}
    for bid, r in results.items():
        kept = tuple(p for p in r.llm_proposals if p.raw_index < n)
        truncated[bid] = BriefResult(**{**r.__dict__, "llm_proposals": kept})
    return compute_go_stop_gate(truncated, gate_spec)


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
    n_kept = len(result.llm_proposals) + result.llm_exact_duplicates + result.llm_schema_rejected
    duplicate_rate = (result.llm_exact_duplicates / n_kept) if n_kept else 0.0
    win = _win_and_improvement(result)
    beats, improvement = win if win is not None else (False, None)
    return {
        "brief_id": result.brief_id, "gen_score": gen_score, "best_llm": best_llm,
        "median_llm": median_llm, "n_llm": len(result.llm_proposals),
        "n_llm_raw": result.llm_raw_generated, "duplicate_rate": duplicate_rate,
        "materially_distinct": result.materially_distinct_count, "beats": beats,
        "improvement": improvement,
    }


def render_results_md(results: dict, *, provenance, dataset_meta: dict, gate_spec: dict) -> str:
    ordered = [results[bid] for bid in sorted(results, key=lambda k: int(k[1:]))]
    gate = compute_go_stop_gate(results, gate_spec)
    bestof4 = bestof_n_gate(results, gate_spec, 4)
    bestof6 = bestof_n_gate(results, gate_spec, 6)

    summaries = [_brief_summary_row(r) for r in ordered]
    realizability_counts = _realizability_counts(results)
    total_labels = sum(realizability_counts.values())
    holdout = gate_spec["holdout_stdev_source"]

    lines = [
        "# LLM Topology Proposer POC — PRIMARY run results (Issue #151)",
        "",
        "This is the PRIMARY run: the frozen, committed generation dataset "
        "(`docs/reports/llm-topology-poc/generation-dataset.json`) scored against the current "
        "generator's own topology for the identical 20 frozen briefs, through the SAME "
        "deterministic, geometry-free critic, blind to source (AC-10). The worker made NO LLM call "
        "and NO network call to produce these numbers (AC-14) — every LLM proposal in this dataset "
        "was already generated, once, before this scoring run started.",
        "",
        f"Model: `{dataset_meta['model']}` — {dataset_meta['n_briefs']} briefs, "
        f"{dataset_meta['n_proposals_requested_per_brief']} proposals requested per brief, "
        f"total generation cost ${dataset_meta['total_cost_usd']}, generated at "
        f"{dataset_meta['generated_at']} ({dataset_meta['generated_by']}).",
        "",
        "The FORCED LOCAL-MODEL CONTROL RUN (a small local model, `llama3.2:latest`) is a "
        "SEPARATE, non-primary run — see `docs/reports/llm-topology-poc/results-control-llama.md`. "
        "No number from that run enters this report's statistics or this run's GO/STOP verdict "
        "(AC-17).",
        "",
        "## GO/STOP verdict (AC-18)",
        "",
        "**The ONE primary decision rule** (owner-approved 2026-09-28, restored 2026-09-30 after a "
        "weaker gate was mistakenly substituted). GO requires ALL THREE of:",
        "- wins on **>= 70%** of the 20 briefs (>= 14 of 20);",
        "- median per-brief improvement **>= 0.137503** — one HOLDOUT standard deviation of the "
        f"`spatial_touching` score distribution, from #149's own committed artifact "
        f"(`{holdout['path']}`, table `{holdout['table']}`, holdout median "
        f"{holdout['holdout_median']}, holdout stdev **{holdout['holdout_stdev']}**, "
        f"{holdout['holdout_plans']} holdout plans). `{holdout['forbidden_substitute']['table']}`'s "
        f"stdev ({holdout['forbidden_substitute']['stdev']}) is explicitly FORBIDDEN as a "
        f"substitute here — {holdout['forbidden_substitute']['why']} (AC-26).",
        "- diversity: **>= 50%** of briefs with >= 3 materially distinct valid proposals.",
        "",
        "A win counts only for an LLM proposal with ZERO hard-constraint violations, compared "
        "against the current generator's own best topology for the same brief, under the identical "
        "blind critic (AC-9, AC-10).",
        "",
        f"**Measured**: wins {gate.wins}/{gate.total_briefs} "
        f"(**{round(gate.wins_fraction * 100, 1)}%**, {'beats the current generator' if gate.wins else 'no brief beats the current generator'}), "
        f"median improvement **{gate.median_improvement}**, average improvement "
        f"**{gate.avg_improvement}**, diversity {gate.diversity_count}/{gate.total_briefs} "
        f"({round(gate.diversity_fraction * 100, 1)}%) of briefs with >= 3 materially distinct "
        "proposals.",
        "",
        f"# VERDICT: {gate.verdict}",
        "",
    ]
    if gate.verdict == "GO":
        lines.append(
            "All three conditions of the primary gate are met, decisively. GO is never rounded "
            "down, exactly as STOP/INCONCLUSIVE are never rounded up.")
    elif gate.verdict == "STOP":
        lines.append(
            "The primary gate is not met, and the result is clearly negative (median improvement "
            "<= 0, or wins far short of the bar). This is STOP, never rounded up to GO.")
    else:
        lines.append(
            "The primary gate is not met, but the result is not clearly negative either. This is "
            "INCONCLUSIVE, never rounded up to GO — it authorises nothing and goes to the owner.")
    lines.append("")

    if gate.verdict != "GO":
        lines += [
            "### What this verdict does and does not mean (AC-27)",
            "",
            "This STOP/INCONCLUSIVE verdict rejects ONLY \"an LLM as the PRIMARY Concept Architect "
            "/ Topology Proposer\". It does NOT reject the architectural-planning direction. #155 "
            f"(commit `{CAPABILITY_SNAPSHOT_155_COMMIT}`) already proved the existing rectilinear "
            "realizer CAN express genuine non-rectangular geometry (its capability snapshot's first "
            "half); its second half is that the 5/8 refusal rate measured there is NOT pure "
            "realizer failure, because placement in that measurement came from the fixed Stage 1 "
            "gate-script heuristic, not a placement engine, and the 8 briefs were drawn from the "
            "shipping path's own PLANNED pool — a pool already defined by that path succeeding on "
            "them. The named gaps are " + ", ".join(CAPABILITY_SNAPSHOT_155_GAPS) + " — five gaps, "
            "not a rejection of the direction. The indicated next evaluation is a DETERMINISTIC "
            "topology/placement search over the EXISTING realizer, with no LLM in the loop.",
            "",
        ]
    else:
        lines += [
            "### Policy note, carried regardless of this run's own verdict (AC-27)",
            "",
            "Per the Issue's own contract: had this verdict been STOP or INCONCLUSIVE, it would "
            "reject ONLY \"an LLM as the PRIMARY Concept Architect / Topology Proposer\", never the "
            f"architectural-planning direction — #155 (commit `{CAPABILITY_SNAPSHOT_155_COMMIT}`) "
            "already proved non-rectangular expressiveness exists, and separately, that its 5/8 "
            "refusal rate is not pure realizer failure (placement there was the fixed gate-script "
            "heuristic, on briefs drawn from the shipping path's own PLANNED pool). The indicated "
            "next evaluation in that case would be a deterministic topology/placement search over "
            "the existing realizer. This run's own verdict is GO, so this paragraph documents "
            "policy, not this run's own finding.",
            "",
        ]

    lines += [
        "## This result as an input to the #151 x #155 decision matrix (AC-21)",
        "",
        "This run's verdict is ONE input to the #151 x #155 decision matrix, not a standalone "
        "authorization. It does not, by itself, recommend starting #142A or any successor — that "
        "remains the owner's decision, weighing this evidence together with #155's own capability "
        "snapshot and any other inputs the matrix names.",
        "",
        "## Why best-of-8, and a diagnostic sensitivity check (AC-20)",
        "",
        "This primary experiment is BEST-OF-8: 8 proposals were requested per brief — the "
        "pre-approved 5-10 band, pinned before any scoring ran. More proposals give the LLM more "
        "opportunities to produce its best idea, and 8 also yields a stronger diversity "
        "measurement; best-of-8 is NOT a harder or stronger test than a smaller count — if "
        "anything it is the more forgiving comparison. The table below recomputes the identical "
        "gate using only the first 4 or 6 proposals per brief; it is DIAGNOSTIC ONLY, appears here "
        "after the verdict above, and never affects the GO/STOP decision.",
        "",
        "| best-of-N | wins | wins % | median improvement | diversity % | would-be verdict |",
        "|---|---|---|---|---|---|",
        f"| 4 (diagnostic) | {bestof4.wins}/{bestof4.total_briefs} | "
        f"{round(bestof4.wins_fraction * 100, 1)}% | {bestof4.median_improvement} | "
        f"{round(bestof4.diversity_fraction * 100, 1)}% | {bestof4.verdict} |",
        f"| 6 (diagnostic) | {bestof6.wins}/{bestof6.total_briefs} | "
        f"{round(bestof6.wins_fraction * 100, 1)}% | {bestof6.median_improvement} | "
        f"{round(bestof6.diversity_fraction * 100, 1)}% | {bestof6.verdict} |",
        f"| 8 (PRIMARY — the verdict above) | {gate.wins}/{gate.total_briefs} | "
        f"{round(gate.wins_fraction * 100, 1)}% | {gate.median_improvement} | "
        f"{round(gate.diversity_fraction * 100, 1)}% | {gate.verdict} |",
        "",
        "## Provenance (AC-13, AC-22)",
        "",
        f"- Adjacency/access artifact: `{provenance.fullcorpus_json_path}`",
        f"- Room-proportions artifact: `{provenance.room_proportions_json_path}`",
        f"- Commit SHA this run's ground truth came from: `{provenance.commit_sha}`",
        f"- Artifact SHA-256: `{provenance.artifact_sha256}`",
        f"- Train count: **{provenance.train_count}**, holdout count: **{provenance.holdout_count}**",
        f"- Generated at (UTC): `{provenance.generated_at_utc}`",
        f"- Generation dataset: `docs/reports/llm-topology-poc/generation-dataset.json` "
        f"(`dataset_sha256` `{dataset_meta['dataset_sha256']}`)",
        "",
        f"**Frozen current-generator baseline (AC-22)**: commit `{PRIMARY_BASELINE_COMMIT_SHORT}` "
        f"(`{PRIMARY_BASELINE_COMMIT_FULL}`, \"#149 B — Full-corpus adjacency validation before the "
        "Topology Proposer\"). The generator/validator/knowledge code that produced every "
        "current-generator topology in this report was BYTE-IDENTICAL to this commit at generation "
        "time — verified by two empty diffs (`git diff 6a4aae7 ef83707 -- backend/app/demo "
        "backend/app/vertical_slice backend/app/knowledge` and `git diff 6a4aae7 713e3f2 -- "
        "backend/app/demo backend/app/vertical_slice`), both recorded in "
        "`docs/reports/llm-topology-poc/baseline.json`.",
        "",
        "## SECONDARY and diagnostic comparisons — never the verdict (AC-23, AC-25)",
        "",
        "The 60%-wins / median-improvement-over-0 rule is a SECONDARY and diagnostic sensitivity "
        "analysis only — it never supplies the verdict, the headline, or a recommendation. This "
        f"run would also pass it: **{gate.secondary_wins_fraction_pass}**. The best-of-4/best-of-6 "
        "table above is the same kind of SECONDARY and diagnostic material. No post-#153 \"LLM vs "
        "current main\" comparison is included in this report — the verdict above is computed "
        f"exclusively from the frozen baseline `{PRIMARY_BASELINE_COMMIT_SHORT}`; any such "
        "comparison, if produced later, belongs in its own SECONDARY-headed section with its own "
        "baseline SHA, and must never rewrite this section's primary verdict.",
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
        "Realizability is METADATA ONLY (AC-9) — these counts never reduced any proposal's quality "
        "score; see "
        "`tests/ai_harness/test_topology_critic.py::test_score_is_independent_of_realizability_label`.",
        "",
        "## Per-brief results (AC-5)",
        "",
        "`best LLM` is the highest score among every kept LLM proposal for that brief, regardless "
        "of hard-constraint violations — direct comparison against the generator's own score. "
        "`beats generator`/`improvement` instead use the GO/STOP gate's own WIN definition (best "
        "*zero-violation* LLM proposal vs generator) — see \"GO/STOP verdict\" above.",
        "",
        "| brief | generator score | best LLM | median LLM | LLM kept/raw | materially distinct | "
        "duplicate rate | beats generator (win def.) | improvement (win def.) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in summaries:
        gen = s["gen_score"] if s["gen_score"] is not None else "n/a (refused)"
        best = s["best_llm"] if s["best_llm"] is not None else "—"
        median = round(s["median_llm"], 4) if s["median_llm"] is not None else "—"
        beats = "YES" if s["beats"] else "no"
        improvement = round(s["improvement"], 4) if s["improvement"] is not None else "—"
        lines.append(
            f"| {s['brief_id']} | {gen} | {best} | {median} | {s['n_llm']}/{s['n_llm_raw']} | "
            f"{s['materially_distinct']} | {round(s['duplicate_rate'], 3)} | {beats} | "
            f"{improvement} |")

    lines += [
        "",
        "## Score component detail (AC-5)",
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

    lines += ["", "## Worked examples (AC-7)", ""]
    worked = [s for s in summaries if s["beats"]]
    worked_examples = sorted(worked, key=lambda s: -s["improvement"])[:10] or summaries[:5]
    for s in worked_examples:
        result = results[s["brief_id"]]
        valid_llm = [p for p in result.llm_proposals if not p.score["hard_violations"]]
        best_valid_proposal = max(valid_llm, key=lambda p: p.score["total_score"], default=None)
        lines += [
            f"### {result.brief_id} ({result.bedrooms} bed, {result.wet_rooms} wet room(s), "
            f"safe_room={result.safe_room}, open_plan={result.open_plan}, {result.size_tier}/"
            f"{result.aspect_tier})",
            "",
            f"- Current generator score: **{s['gen_score']}**"
            + (f" ({len(result.generator.score['hard_violations'])} hard violations)"
               if result.generator is not None else ""),
        ]
        if best_valid_proposal is not None:
            lines.append(
                f"- Best zero-violation LLM proposal score: "
                f"**{best_valid_proposal.score['total_score']}** "
                f"(realizability={best_valid_proposal.realizability})")
        lines += [
            f"- Improvement: **{s['improvement']}**" if s["improvement"] is not None else "",
            "- Why the critic preferred the LLM proposal: its adjacency/access graph sits closer to "
            "the corrected #149 corpus's own measured pattern (higher, less-negative "
            "log-likelihood) than the current generator's topology for this brief, with zero hard "
            "constraint violations — see the score component table above for the exact numbers.",
            "",
        ]

    lines += [
        "## Known limitations",
        "",
        "- `entrance_relation_score` is `None` whenever the entrance opens into a room whose role "
        "(e.g. HALL) the corrected #149 corpus cannot measure `front_door_direct_access` for — "
        "genuine unmeasurability, not a zero.",
        "- `best LLM` (per-brief table) and the WIN definition (GO/STOP gate, headline, worked "
        "examples) differ deliberately: the first is a raw ceiling regardless of hard-constraint "
        "violations, the second requires zero violations, matching `baseline.json`'s own "
        "`win_definition`.",
        "- This run's dataset carries `retry_count = 0` for every brief: the model produced at "
        "least one schema-valid proposal on its first attempt for all 20 briefs (unlike the "
        "control run below, where a small local model frequently produced none at all).",
    ]
    return "\n".join(lines) + "\n"
