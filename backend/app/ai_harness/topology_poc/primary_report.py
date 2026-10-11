"""Renders the PRIMARY run's `docs/reports/llm-topology-poc/results.md` (Issue #151, AC-5 through
AC-27) from `frozen_runner.run_all_briefs_from_dataset`'s output plus the frozen GO/STOP gate
(`docs/reports/llm-topology-poc/baseline.json`). Pure formatting plus the one gate computation
(`compute_go_stop_gate`) — every number here comes from `critic.py`/`frozen_runner.py`/
`baseline.json`; this module invents nothing.

WIN DEFINITION (`baseline.json`'s own `primary_go_stop_gate.win_definition`): best-VALID-LLM (zero
hard-constraint violations) vs best-current-generator, same blind critic (`total_score`, `_win`
below). This is the number the GO/STOP verdict's wins-fraction and the headline (AC-7) both use. It
is stricter than "best LLM score" (AC-5's per-brief column, which reports the true best among every
kept LLM proposal regardless of violations, for direct comparison against the generator's own
score) — the two are reported side by side, never conflated.

IMPROVEMENT MAGNITUDE vs WIN (independent review fix, 2026-10-01): the gate's median/average
IMPROVEMENT number (compared against the 0.137503 threshold, AC-18/AC-26) is measured on
`adjacency_similarity` ALONE (`_adjacency_improvement` below) for the SAME winning proposal
`_win` selects — never on `total_score`. `total_score` sums four differently-scaled components (a
-10-per-violation penalty among them) and is not in the units the threshold is a holdout standard
deviation OF (`baseline.json`'s own `median_improvement_unit`: "one holdout standard deviation of
the spatial_touching score distribution") — comparing it to 0.137503 would compare incommensurate
quantities and make the bar trivially easy to clear regardless of the LLM's actual adjacency
signal. "Which proposal wins" (the full critic, `total_score`) and "how big is the effect on the
one axis we have a calibrated noise floor for" (`adjacency_similarity` alone) are deliberately two
different questions, answered by two different fields of the SAME `GoStopGate`.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass

from app.ai_harness.topology_poc.result_types import BriefResult, ScoredProposal

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


def _win(result: BriefResult):
    """The best ZERO-VIOLATION LLM proposal, ranked by `total_score` (`baseline.json`'s own
    `win_definition`: "best-valid-LLM vs best-current-generator under the same blind critic").
    `None` when the brief has no comparable (generator, zero-violation LLM) pair."""
    if result.generator is None:
        return None
    valid = [p for p in result.llm_proposals if not p.score["hard_violations"]]
    if not valid:
        return None
    best = max(valid, key=lambda p: p.score["total_score"])
    gen_score = result.generator.score["total_score"]
    return best.score["total_score"] > gen_score, best


def _adjacency_improvement(result: BriefResult, best_llm: ScoredProposal) -> "float | None":
    """The gate's own improvement MAGNITUDE (AC-18, AC-26) — `adjacency_similarity` alone, built
    ONLY from `spatial_touching` (`critic._adjacency_similarity`, AC-12), the SAME metric the
    0.137503 threshold is itself a holdout standard deviation of (`baseline.json`'s own
    `median_improvement_unit`). `total_score` sums four differently-scaled components (plus a
    -10-per-violation term) and is NOT in the units that threshold was calibrated against —
    comparing it to 0.137503 would make the bar trivially easy regardless of whether the LLM's
    actual adjacency signal exceeds the corpus's own measured noise floor (independent review
    finding, 2026-10-01). `None` when either side has zero eligible measurable-role pairs for this
    brief — a genuine "no evidence" (AC-12's own "contributes to neither the sum nor the count"),
    never a fabricated 0.0."""
    gen_adjacency = result.generator.score["adjacency_similarity"]
    llm_adjacency = best_llm.score["adjacency_similarity"]
    if gen_adjacency is None or llm_adjacency is None:
        return None
    return llm_adjacency - gen_adjacency


def compute_go_stop_gate(results: dict, gate_spec: dict) -> GoStopGate:
    go = gate_spec["go_requires_all_three"]
    ordered = list(results.values())
    win_pairs = [_win(r) for r in ordered]
    comparable = [w for w in win_pairs if w is not None]
    wins = sum(1 for beats, _ in comparable if beats)
    improvements = [imp for r, w in zip(ordered, win_pairs) if w is not None
                    for imp in [_adjacency_improvement(r, w[1])] if imp is not None]
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


def _declaration_vs_measurement_caveat(realizability_counts: dict, total_labels: int) -> str:
    """The GO verdict's own limitation (owner correction, 2026-10-01): the LLM's graph is a
    DECLARATION, the current generator's is a MEASUREMENT of a plan it actually realized — GO says
    better topologies are CONCEIVABLE, never that they are BUILDABLE. The NOT_REALIZABLE share is
    computed here from the SAME `realizability_counts` the distribution table above renders from,
    so this sentence can never drift out of sync with that table the way a hand-typed figure did."""
    not_realizable = realizability_counts["NOT_REALIZABLE_BY_CURRENT_ENGINE"]
    share = round(100 * not_realizable / total_labels, 1) if total_labels else 0.0
    return (
        "- **The two sides of this comparison are not the same KIND of object, and that is by "
        "design.** The LLM's `spatial_adjacency` is a **declaration** — a list of room-id pairs it "
        "asserts, constrained by nothing but the schema. The current generator's graph is a "
        "**measurement** — derived by `generator_adapter` from a plan it actually realized and "
        "that actually passed the validators, using the same "
        "`shared_boundary_m(...) >= MIN_MEANINGFUL_SHARED_BOUNDARY_M` test the ranking path uses. "
        "So the LLM is scored on an intention and the generator on an achievement. This is "
        "deliberate: the Issue's own Goal states \"The LLM produces no geometry... It produces a "
        "STRUCTURED SPATIAL IDEA only\", and the whole point is to ask whether better ideas are "
        "conceivable at all. But it means the verdict must be read precisely: **GO says a strong "
        "LLM can propose topologies our own critic scores far better than anything our generator "
        "currently realizes. It does NOT say those topologies are buildable.** The realizability "
        f"distribution is where that gap is visible and is reported above — **{share}% of "
        "proposals are NOT_REALIZABLE_BY_CURRENT_ENGINE** — and per AC-9 that label never touched "
        "a score. This is precisely why the verdict is an INPUT to the #151 x #155 decision matrix "
        "rather than an authorization: #155 measures the hand, this measures the idea.")


def _median_is_not_the_story_caveat(summaries: list) -> str:
    """The gate's own win definition is best-of-8 (AC-20); this caveat states the OTHER number —
    where the model's typical (median) output actually falls — computed here from the SAME
    per-brief rows the table above renders from, never a hand-typed snapshot."""
    median_llms = [s["median_llm"] for s in summaries if s["median_llm"] is not None]
    gen_scores = [s["gen_score"] for s in summaries if s["gen_score"] is not None]
    worse_briefs = [
        s["brief_id"] for s in summaries
        if s["median_llm"] is not None and s["gen_score"] is not None
        and s["median_llm"] < s["gen_score"]]
    median_band = f"{round(min(median_llms), 2)} and {round(max(median_llms), 2)}" if median_llms else "n/a"
    gen_band = f"{round(min(gen_scores), 2)} and {round(max(gen_scores), 2)}" if gen_scores else "n/a"
    if worse_briefs:
        worse_note = f", and {', '.join(worse_briefs)}'s median is slightly worse"
    else:
        worse_note = ""
    return (
        "- **The median LLM proposal is not the story; the best one is.** Per-brief median LLM "
        f"scores sit between {median_band}, in the same band as the generator's between {gen_band} — "
        "several briefs' median proposal is only marginally better than the generator's single "
        f"topology{worse_note}. The gate is a best-of-8 comparison by design (see AC-20), so the "
        "headline reflects the model's ceiling, not its typical output.")


def _brief_summary_row(result: BriefResult) -> dict:
    llm_scores = [p.score["total_score"] for p in result.llm_proposals]
    gen_score = result.generator.score["total_score"] if result.generator is not None else None
    best_llm = max(llm_scores) if llm_scores else None
    median_llm = statistics.median(llm_scores) if llm_scores else None
    n_kept = len(result.llm_proposals) + result.llm_exact_duplicates + result.llm_schema_rejected
    duplicate_rate = (result.llm_exact_duplicates / n_kept) if n_kept else 0.0
    win = _win(result)
    if win is None:
        beats, improvement = False, None
    else:
        beats, best_proposal = win
        improvement = _adjacency_improvement(result, best_proposal)
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
        "**Units (independent review fix, 2026-10-01)**: \"wins\" is decided on `total_score` (the "
        "full critic — adjacency + access + wet-core + entrance, less violations), but \"median "
        "improvement\" is measured on `adjacency_similarity` ALONE, for that SAME winning proposal "
        "— the one metric actually built from `spatial_touching` (AC-12) and therefore the one "
        "metric this threshold's holdout stdev is comparable to. `total_score`'s improvement is NOT "
        "used here: it mixes four differently-scaled components and is not in the threshold's "
        "units, so comparing it to 0.137503 would not test what this gate exists to test.",
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
        "## Briefs stratification (AC-19)",
        "",
        "The 20 frozen briefs this run scored, restated in full here (the complete selection "
        "method and rationale live in `docs/reports/llm-topology-poc/briefs.md`):",
        "",
        "| brief | bedrooms | wet_rooms | safe_room | open_plan | size_tier | aspect_tier |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in ordered:
        lines.append(
            f"| {r.brief_id} | {r.bedrooms} | {r.wet_rooms} | {r.safe_room} | {r.open_plan} | "
            f"{r.size_tier} | {r.aspect_tier} |")
    lines += [
        "",
        "## Per-brief results (AC-5)",
        "",
        "`best LLM` is the highest score among every kept LLM proposal for that brief, regardless "
        "of hard-constraint violations — direct comparison against the generator's own score. "
        "`beats generator` uses the GO/STOP gate's own WIN definition (best *zero-violation* LLM "
        "proposal vs generator, by `total_score`) — see \"GO/STOP verdict\" above. `improvement` is "
        "that SAME winning proposal's `adjacency_similarity` delta (not `total_score`'s) — the "
        "metric the 0.137503 gate threshold is actually calibrated against; `—` when either side "
        "has no eligible measurable-role pair for this brief.",
        "",
        "| brief | generator score | best LLM | median LLM | LLM kept/raw | materially distinct | "
        "duplicate rate | beats generator (win def.) | improvement (adjacency_similarity delta) |",
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
    # `improvement` (adjacency_similarity delta, AC-26) is `None` for a brief with no eligible
    # measurable-role pair on either side — sorts last, never crashes the comparison.
    worked_examples = sorted(
        worked, key=lambda s: s["improvement"] if s["improvement"] is not None else float("-inf"),
        reverse=True)[:10] or summaries[:5]
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
        _declaration_vs_measurement_caveat(realizability_counts, total_labels),
        "",
        _median_is_not_the_story_caveat(summaries),
        "",
        "- `entrance_relation_score` is `None` whenever the entrance opens into a room whose role "
        "(e.g. HALL) the corrected #149 corpus cannot measure `front_door_direct_access` for — "
        "genuine unmeasurability, not a zero.",
        "- `best LLM` (per-brief table) and the WIN definition (GO/STOP gate, headline, worked "
        "examples) differ deliberately: the first is a raw ceiling regardless of hard-constraint "
        "violations, the second requires zero violations, matching `baseline.json`'s own "
        "`win_definition`.",
        "- `improvement` (per-brief table, worked examples, and the gate's own median/average) is "
        "the winning proposal's `adjacency_similarity` delta, not its `total_score` delta — see "
        "\"GO/STOP verdict\" above for why. It is `—`/absent whenever either side has zero eligible "
        "measurable-role pairs for that brief, most often because the current generator's own "
        "open-plan merge (`LIVING_KITCHEN_MERGE_ENABLED`) collapses LIVING and KITCHEN into one "
        "polygon — the adapter (`generator_adapter._expand_merged_rooms`) splits that back into "
        "measurable LIVING/KITCHEN room refs, but a brief can still lack any OTHER eligible "
        "measurable pair.",
        "- This run's dataset carries `retry_count = 0` for every brief: the model produced at "
        "least one schema-valid proposal on its first attempt for all 20 briefs (unlike the "
        "control run below, where a small local model frequently produced none at all).",
    ]
    return "\n".join(lines) + "\n"
