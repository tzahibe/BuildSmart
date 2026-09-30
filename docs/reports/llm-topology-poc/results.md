# LLM Topology Proposer POC — PRIMARY run results (Issue #151)

This is the PRIMARY run: the frozen, committed generation dataset (`docs/reports/llm-topology-poc/generation-dataset.json`) scored against the current generator's own topology for the identical 20 frozen briefs, through the SAME deterministic, geometry-free critic, blind to source (AC-10). The worker made NO LLM call and NO network call to produce these numbers (AC-14) — every LLM proposal in this dataset was already generated, once, before this scoring run started.

Model: `gpt-5` — 20 briefs, 8 proposals requested per brief, total generation cost $2.8833, generated at 2026-09-30T17:42:33+0300 (controlled environment (owner decision 2026-09-29, option A)).

The FORCED LOCAL-MODEL CONTROL RUN (a small local model, `llama3.2:latest`) is a SEPARATE, non-primary run — see `docs/reports/llm-topology-poc/results-control-llama.md`. No number from that run enters this report's statistics or this run's GO/STOP verdict (AC-17).

## GO/STOP verdict (AC-18)

**The ONE primary decision rule** (owner-approved 2026-09-28, restored 2026-09-30 after a weaker gate was mistakenly substituted). GO requires ALL THREE of:
- wins on **>= 70%** of the 20 briefs (>= 14 of 20);
- median per-brief improvement **>= 0.137503** — one HOLDOUT standard deviation of the `spatial_touching` score distribution, from #149's own committed artifact (`docs/reports/real-plan-priors/adjacency-fullcorpus-diagnostic.md`, table `spatial_touching`, holdout median -0.128868, holdout stdev **0.137503**, 3459 holdout plans). `touching_without_door`'s stdev (0.058796) is explicitly FORBIDDEN as a substitute here — diagnostic only per the contract; substituting it would make the bar about 2.3x easier (AC-26).
- diversity: **>= 50%** of briefs with >= 3 materially distinct valid proposals.

A win counts only for an LLM proposal with ZERO hard-constraint violations, compared against the current generator's own best topology for the same brief, under the identical blind critic (AC-9, AC-10).

**Units (independent review fix, 2026-10-01)**: "wins" is decided on `total_score` (the full critic — adjacency + access + wet-core + entrance, less violations), but "median improvement" is measured on `adjacency_similarity` ALONE, for that SAME winning proposal — the one metric actually built from `spatial_touching` (AC-12) and therefore the one metric this threshold's holdout stdev is comparable to. `total_score`'s improvement is NOT used here: it mixes four differently-scaled components and is not in the threshold's units, so comparing it to 0.137503 would not test what this gate exists to test.

**Measured**: wins 20/20 (**100.0%**, beats the current generator), median improvement **1.585229**, average improvement **1.589542**, diversity 20/20 (100.0%) of briefs with >= 3 materially distinct proposals.

# VERDICT: GO

All three conditions of the primary gate are met, decisively. GO is never rounded down, exactly as STOP/INCONCLUSIVE are never rounded up.

### Policy note, carried regardless of this run's own verdict (AC-27)

Per the Issue's own contract: had this verdict been STOP or INCONCLUSIVE, it would reject ONLY "an LLM as the PRIMARY Concept Architect / Topology Proposer", never the architectural-planning direction — #155 (commit `713e3f2`) already proved non-rectangular expressiveness exists, and separately, that its 5/8 refusal rate is not pure realizer failure (placement there was the fixed gate-script heuristic, on briefs drawn from the shipping path's own PLANNED pool). The indicated next evaluation in that case would be a deterministic topology/placement search over the existing realizer. This run's own verdict is GO, so this paragraph documents policy, not this run's own finding.

## This result as an input to the #151 x #155 decision matrix (AC-21)

This run's verdict is ONE input to the #151 x #155 decision matrix, not a standalone authorization. It does not, by itself, recommend starting #142A or any successor — that remains the owner's decision, weighing this evidence together with #155's own capability snapshot and any other inputs the matrix names.

## Why best-of-8, and a diagnostic sensitivity check (AC-20)

This primary experiment is BEST-OF-8: 8 proposals were requested per brief — the pre-approved 5-10 band, pinned before any scoring ran. More proposals give the LLM more opportunities to produce its best idea, and 8 also yields a stronger diversity measurement; best-of-8 is NOT a harder or stronger test than a smaller count — if anything it is the more forgiving comparison. The table below recomputes the identical gate using only the first 4 or 6 proposals per brief; it is DIAGNOSTIC ONLY, appears here after the verdict above, and never affects the GO/STOP decision.

| best-of-N | wins | wins % | median improvement | diversity % | would-be verdict |
|---|---|---|---|---|---|
| 4 (diagnostic) | 20/20 | 100.0% | 1.612431 | 100.0% | GO |
| 6 (diagnostic) | 20/20 | 100.0% | 1.570753 | 100.0% | GO |
| 8 (PRIMARY — the verdict above) | 20/20 | 100.0% | 1.585229 | 100.0% | GO |

## Provenance (AC-13, AC-22)

- Adjacency/access artifact: `docs/reports/real-plan-priors/adjacency-fullcorpus.json`
- Room-proportions artifact: `docs/reports/real-plan-priors/room-proportions.json`
- Commit SHA this run's ground truth came from: `6a4aae74e6ab75fa12074e3d43fb9724575376e9`
- Artifact SHA-256: `23ee2b752f0fd33b018d2b76075d049353dbd3d6ad18d5826fc39b3e4b7819c5`
- Train count: **13648**, holdout count: **3459**
- Generated at (UTC): `2026-09-30T23:00:04Z`
- Generation dataset: `docs/reports/llm-topology-poc/generation-dataset.json` (`dataset_sha256` `03c52be5357ff41f30ee104cfd1ff0d2760bba0cf7f0576b64565767cb321598`)

**Frozen current-generator baseline (AC-22)**: commit `6a4aae7` (`6a4aae74e6ab75fa12074e3d43fb9724575376e9`, "#149 B — Full-corpus adjacency validation before the Topology Proposer"). The generator/validator/knowledge code that produced every current-generator topology in this report was BYTE-IDENTICAL to this commit at generation time — verified by two empty diffs (`git diff 6a4aae7 ef83707 -- backend/app/demo backend/app/vertical_slice backend/app/knowledge` and `git diff 6a4aae7 713e3f2 -- backend/app/demo backend/app/vertical_slice`), both recorded in `docs/reports/llm-topology-poc/baseline.json`.

## SECONDARY and diagnostic comparisons — never the verdict (AC-23, AC-25)

The 60%-wins / median-improvement-over-0 rule is a SECONDARY and diagnostic sensitivity analysis only — it never supplies the verdict, the headline, or a recommendation. This run would also pass it: **True**. The best-of-4/best-of-6 table above is the same kind of SECONDARY and diagnostic material. No post-#153 "LLM vs current main" comparison is included in this report — the verdict above is computed exclusively from the frozen baseline `6a4aae7`; any such comparison, if produced later, belongs in its own SECONDARY-headed section with its own baseline SHA, and must never rewrite this section's primary verdict.

## Realizability distribution (AC-6)

Across every proposal scored (current-generator + LLM, 181 total):

| label | count | share |
|---|---|---|
| REALIZABLE_BY_CURRENT_ENGINE | 80 | 44.2% |
| NOT_REALIZABLE_BY_CURRENT_ENGINE | 101 | 55.8% |
| UNKNOWN | 0 | 0.0% |

Realizability is METADATA ONLY (AC-9) — these counts never reduced any proposal's quality score; see `tests/ai_harness/test_topology_critic.py::test_score_is_independent_of_realizability_label`.

## Per-brief results (AC-5)

`best LLM` is the highest score among every kept LLM proposal for that brief, regardless of hard-constraint violations — direct comparison against the generator's own score. `beats generator` uses the GO/STOP gate's own WIN definition (best *zero-violation* LLM proposal vs generator, by `total_score`) — see "GO/STOP verdict" above. `improvement` is that SAME winning proposal's `adjacency_similarity` delta (not `total_score`'s) — the metric the 0.137503 gate threshold is actually calibrated against; `—` when either side has no eligible measurable-role pair for this brief.

| brief | generator score | best LLM | median LLM | LLM kept/raw | materially distinct | duplicate rate | beats generator (win def.) | improvement (adjacency_similarity delta) |
|---|---|---|---|---|---|---|---|---|
| B01 | -3.510232 | 0.651797 | -2.2674 | 7/8 | 7 | 0.0 | YES | 0.0 |
| B02 | -2.345585 | 0.651797 | -2.208 | 8/9 | 7 | 0.111 | YES | 2.0058 |
| B03 | -2.615718 | 0.271786 | -0.7198 | 8/8 | 7 | 0.0 | YES | 0.3107 |
| B04 | -2.615718 | -1.070773 | -1.2308 | 8/8 | 8 | 0.0 | YES | 0.5534 |
| B05 | -2.033395 | -0.038917 | -1.6494 | 8/8 | 8 | 0.0 | YES | 1.0029 |
| B06 | -2.615718 | -0.719786 | -2.2559 | 8/8 | 8 | 0.0 | YES | 0.3107 |
| B07 | -3.003497 | -0.642711 | -1.0075 | 8/8 | 8 | 0.0 | YES | 0.3878 |
| B08 | -2.033395 | 0.514455 | -1.6505 | 6/8 | 6 | 0.0 | YES | 1.5563 |
| B09 | -2.615718 | 0.298441 | -0.6027 | 8/8 | 8 | 0.0 | YES | 0.9412 |
| B10 | -2.615718 | 0.609144 | -1.6853 | 9/9 | 8 | 0.0 | YES | 1.2519 |
| B11 | -4.006402 | -1.00274 | -2.3905 | 9/9 | 9 | 0.0 | YES | 3.2866 |
| B12 | -3.003497 | 0.198735 | -1.3499 | 8/8 | 8 | 0.0 | YES | 1.6396 |
| B13 | -3.618623 | 0.825159 | -1.8305 | 8/8 | 8 | 0.0 | YES | 3.4522 |
| B14 | -3.259795 | -0.111968 | -1.5065 | 8/8 | 8 | 0.0 | YES | 1.8959 |
| B15 | -3.259795 | 0.902234 | -1.3911 | 8/8 | 8 | 0.0 | YES | 1.5852 |
| B16 | -2.033395 | 1.190307 | -2.3138 | 8/9 | 8 | 0.0 | YES | 2.2548 |
| B17 | -3.259795 | -1.649084 | -2.3702 | 9/9 | 9 | 0.0 | YES | 1.8959 |
| B18 | -2.268223 | -0.034893 | -1.3361 | 8/11 | 8 | 0.0 | YES | 1.5852 |
| B19 | -1.6859 | -0.372291 | -1.7142 | 8/9 | 8 | 0.0 | YES | 2.8988 |
| B20 | -4.006402 | 0.348861 | -1.6468 | 9/9 | 9 | 0.0 | YES | 2.9759 |

## Score component detail (AC-5)

| brief | side | adjacency_similarity | access_similarity | wet_core_similarity | entrance_relation_score | hard_violations |
|---|---|---|---|---|---|---|
| B01 | generator | -0.6702805332146903 | -3.8399513690541576 | 1.0 | None | 0 |
| B01 | best LLM | -0.6702805332146903 | -0.6694942150468344 | 1.0 | 0.991572 | 0 |
| B02 | generator | -2.676090888010677 | -0.6694942150468344 | 1.0 | None | 0 |
| B02 | best LLM | -0.6702805332146903 | -0.6694942150468344 | 1.0 | 0.991572 | 0 |
| B03 | generator | -1.2924152047498745 | -2.323302815631266 | 1.0 | None | 0 |
| B03 | best LLM | -0.9817119654865304 | -0.7380742386276046 | 1.0 | 0.991572 | 0 |
| B04 | generator | -1.2924152047498745 | -2.323302815631266 | 1.0 | None | 0 |
| B04 | best LLM | -0.7390422632099073 | -2.323302815631266 | 1.0 | 0.991572 | 0 |
| B05 | generator | -2.295320382147868 | -0.7380742386276046 | 1.0 | None | 0 |
| B05 | best LLM | -1.2924152047498745 | -0.7380742386276046 | 1.0 | 0.991572 | 0 |
| B06 | generator | -1.2924152047498745 | -2.323302815631266 | 1.0 | None | 0 |
| B06 | best LLM | -0.9817119654865304 | -0.7380742386276046 | 1.0 | None | 0 |
| B07 | generator | -1.6801937804606306 | -2.323302815631266 | 1.0 | None | 0 |
| B07 | best LLM | -1.2924152047498745 | -0.3502956629168488 | 1.0 | None | 0 |
| B08 | generator | -2.295320382147868 | -0.7380742386276046 | 1.0 | None | 0 |
| B08 | best LLM | -0.7390422632099073 | -0.7380742386276046 | 1.0 | 0.991572 | 0 |
| B09 | generator | -1.2924152047498745 | -2.323302815631266 | 1.0 | None | 0 |
| B09 | best LLM | -0.35126368749915154 | -0.3502956629168488 | 1.0 | None | 0 |
| B10 | generator | -1.2924152047498745 | -2.323302815631266 | 1.0 | None | 0 |
| B10 | best LLM | -0.04056044823580734 | -0.3502956629168488 | 1.0 | None | 0 |
| B11 | generator | -4.2683275348622844 | -0.7380742386276046 | 1.0 | None | 0 |
| B11 | best LLM | -0.9817119654865304 | -2.012599576367922 | 1.0 | 0.991572 | 0 |
| B12 | generator | -1.6801937804606306 | -2.323302815631266 | 1.0 | None | 0 |
| B12 | best LLM | -0.04056044823580734 | -0.4273709993642605 | 0.6666666666666666 | None | 0 |
| B13 | generator | -3.880548959151529 | -0.7380742386276046 | 1.0 | None | 0 |
| B13 | best LLM | -0.4283390239465632 | -0.7380742386276046 | 1.0 | 0.991572 | 0 |
| B14 | generator | -1.9364922645028129 | -2.323302815631266 | 1.0 | None | 0 |
| B14 | best LLM | -0.04056044823580734 | -0.7380742386276046 | 0.6666666666666666 | None | 0 |
| B15 | generator | -1.9364922645028129 | -2.323302815631266 | 1.0 | None | 0 |
| B15 | best LLM | -0.35126368749915154 | -0.7380742386276046 | 1.0 | 0.991572 | 0 |
| B16 | generator | -2.295320382147868 | -0.7380742386276046 | 1.0 | None | 0 |
| B16 | best LLM | -0.04056044823580734 | -0.4273709993642605 | 0.6666666666666666 | 0.991572 | 0 |
| B17 | generator | -1.9364922645028129 | -2.323302815631266 | 1.0 | None | 0 |
| B17 | best LLM | -0.04056044823580734 | -3.6000959287264642 | 1.0 | 0.991572 | 0 |
| B18 | generator | -1.9364922645028129 | -2.323302815631266 | 1.0 | 0.991572 | 0 |
| B18 | best LLM | -0.35126368749915154 | -0.3502956629168488 | 0.6666666666666666 | None | 0 |
| B19 | generator | -2.9393974419008058 | -0.7380742386276046 | 1.0 | 0.991572 | 0 |
| B19 | best LLM | -0.04056044823580734 | -2.323302815631266 | 1.0 | 0.991572 | 0 |
| B20 | generator | -4.2683275348622844 | -0.7380742386276046 | 1.0 | None | 0 |
| B20 | best LLM | -1.2924152047498745 | -0.3502956629168488 | 1.0 | 0.991572 | 0 |

## Worked examples (AC-7)

### B13 (4 bed, 2 wet room(s), safe_room=False, open_plan=True, small/square)

- Current generator score: **-3.618623** (0 hard violations)
- Best zero-violation LLM proposal score: **0.825159** (realizability=REALIZABLE_BY_CURRENT_ENGINE)
- Improvement: **3.4522099352049658**
- Why the critic preferred the LLM proposal: its adjacency/access graph sits closer to the corrected #149 corpus's own measured pattern (higher, less-negative log-likelihood) than the current generator's topology for this brief, with zero hard constraint violations — see the score component table above for the exact numbers.

### B11 (4 bed, 2 wet room(s), safe_room=True, open_plan=True, medium/narrow)

- Current generator score: **-4.006402** (0 hard violations)
- Best zero-violation LLM proposal score: **-1.00274** (realizability=NOT_REALIZABLE_BY_CURRENT_ENGINE)
- Improvement: **3.286615569375754**
- Why the critic preferred the LLM proposal: its adjacency/access graph sits closer to the corrected #149 corpus's own measured pattern (higher, less-negative log-likelihood) than the current generator's topology for this brief, with zero hard constraint violations — see the score component table above for the exact numbers.

### B20 (2 bed, 3 wet room(s), safe_room=True, open_plan=True, small/square)

- Current generator score: **-4.006402** (0 hard violations)
- Best zero-violation LLM proposal score: **0.348861** (realizability=REALIZABLE_BY_CURRENT_ENGINE)
- Improvement: **2.97591233011241**
- Why the critic preferred the LLM proposal: its adjacency/access graph sits closer to the corrected #149 corpus's own measured pattern (higher, less-negative log-likelihood) than the current generator's topology for this brief, with zero hard constraint violations — see the score component table above for the exact numbers.

### B19 (6 bed, 2 wet room(s), safe_room=False, open_plan=True, medium/square)

- Current generator score: **-1.6859** (0 hard violations)
- Best zero-violation LLM proposal score: **-0.372291** (realizability=REALIZABLE_BY_CURRENT_ENGINE)
- Improvement: **2.8988369936649985**
- Why the critic preferred the LLM proposal: its adjacency/access graph sits closer to the corrected #149 corpus's own measured pattern (higher, less-negative log-likelihood) than the current generator's topology for this brief, with zero hard constraint violations — see the score component table above for the exact numbers.

### B16 (5 bed, 3 wet room(s), safe_room=True, open_plan=True, medium/wide)

- Current generator score: **-2.033395** (0 hard violations)
- Best zero-violation LLM proposal score: **1.190307** (realizability=NOT_REALIZABLE_BY_CURRENT_ENGINE)
- Improvement: **2.2547599339120605**
- Why the critic preferred the LLM proposal: its adjacency/access graph sits closer to the corrected #149 corpus's own measured pattern (higher, less-negative log-likelihood) than the current generator's topology for this brief, with zero hard constraint violations — see the score component table above for the exact numbers.

### B02 (1 bed, 1 wet room(s), safe_room=False, open_plan=True, medium/narrow)

- Current generator score: **-2.345585** (0 hard violations)
- Best zero-violation LLM proposal score: **0.651797** (realizability=NOT_REALIZABLE_BY_CURRENT_ENGINE)
- Improvement: **2.0058103547959867**
- Why the critic preferred the LLM proposal: its adjacency/access graph sits closer to the corrected #149 corpus's own measured pattern (higher, less-negative log-likelihood) than the current generator's topology for this brief, with zero hard constraint violations — see the score component table above for the exact numbers.

### B14 (5 bed, 3 wet room(s), safe_room=False, open_plan=False, medium/narrow)

- Current generator score: **-3.259795** (0 hard violations)
- Best zero-violation LLM proposal score: **-0.111968** (realizability=NOT_REALIZABLE_BY_CURRENT_ENGINE)
- Improvement: **1.8959318162670056**
- Why the critic preferred the LLM proposal: its adjacency/access graph sits closer to the corrected #149 corpus's own measured pattern (higher, less-negative log-likelihood) than the current generator's topology for this brief, with zero hard constraint violations — see the score component table above for the exact numbers.

### B17 (6 bed, 3 wet room(s), safe_room=False, open_plan=False, medium/wide)

- Current generator score: **-3.259795** (0 hard violations)
- Best zero-violation LLM proposal score: **-1.649084** (realizability=NOT_REALIZABLE_BY_CURRENT_ENGINE)
- Improvement: **1.8959318162670056**
- Why the critic preferred the LLM proposal: its adjacency/access graph sits closer to the corrected #149 corpus's own measured pattern (higher, less-negative log-likelihood) than the current generator's topology for this brief, with zero hard constraint violations — see the score component table above for the exact numbers.

### B12 (4 bed, 3 wet room(s), safe_room=False, open_plan=False, large/square)

- Current generator score: **-3.003497** (0 hard violations)
- Best zero-violation LLM proposal score: **0.198735** (realizability=NOT_REALIZABLE_BY_CURRENT_ENGINE)
- Improvement: **1.6396333322248233**
- Why the critic preferred the LLM proposal: its adjacency/access graph sits closer to the corrected #149 corpus's own measured pattern (higher, less-negative log-likelihood) than the current generator's topology for this brief, with zero hard constraint violations — see the score component table above for the exact numbers.

### B15 (5 bed, 2 wet room(s), safe_room=True, open_plan=False, medium/square)

- Current generator score: **-3.259795** (0 hard violations)
- Best zero-violation LLM proposal score: **0.902234** (realizability=REALIZABLE_BY_CURRENT_ENGINE)
- Improvement: **1.5852285770036614**
- Why the critic preferred the LLM proposal: its adjacency/access graph sits closer to the corrected #149 corpus's own measured pattern (higher, less-negative log-likelihood) than the current generator's topology for this brief, with zero hard constraint violations — see the score component table above for the exact numbers.

## Known limitations

- `entrance_relation_score` is `None` whenever the entrance opens into a room whose role (e.g. HALL) the corrected #149 corpus cannot measure `front_door_direct_access` for — genuine unmeasurability, not a zero.
- `best LLM` (per-brief table) and the WIN definition (GO/STOP gate, headline, worked examples) differ deliberately: the first is a raw ceiling regardless of hard-constraint violations, the second requires zero violations, matching `baseline.json`'s own `win_definition`.
- `improvement` (per-brief table, worked examples, and the gate's own median/average) is the winning proposal's `adjacency_similarity` delta, not its `total_score` delta — see "GO/STOP verdict" above for why. It is `—`/absent whenever either side has zero eligible measurable-role pairs for that brief, most often because the current generator's own open-plan merge (`LIVING_KITCHEN_MERGE_ENABLED`) collapses LIVING and KITCHEN into one polygon — the adapter (`generator_adapter._expand_merged_rooms`) splits that back into measurable LIVING/KITCHEN room refs, but a brief can still lack any OTHER eligible measurable pair.
- This run's dataset carries `retry_count = 0` for every brief: the model produced at least one schema-valid proposal on its first attempt for all 20 briefs (unlike the control run below, where a small local model frequently produced none at all).
