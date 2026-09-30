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

**Measured**: wins 19/20 (**95.0%**, beats the current generator), median improvement **2.177717**, average improvement **2.251006**, diversity 20/20 (100.0%) of briefs with >= 3 materially distinct proposals.

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
| 4 (diagnostic) | 19/20 | 95.0% | 2.009038 | 100.0% | GO |
| 6 (diagnostic) | 19/20 | 95.0% | 2.058291 | 100.0% | GO |
| 8 (PRIMARY — the verdict above) | 19/20 | 95.0% | 2.177717 | 100.0% | GO |

## Provenance (AC-13, AC-22)

- Adjacency/access artifact: `docs/reports/real-plan-priors/adjacency-fullcorpus.json`
- Room-proportions artifact: `docs/reports/real-plan-priors/room-proportions.json`
- Commit SHA this run's ground truth came from: `6a4aae74e6ab75fa12074e3d43fb9724575376e9`
- Artifact SHA-256: `23ee2b752f0fd33b018d2b76075d049353dbd3d6ad18d5826fc39b3e4b7819c5`
- Train count: **13648**, holdout count: **3459**
- Generated at (UTC): `2026-09-30T20:34:42Z`
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

`best LLM` is the highest score among every kept LLM proposal for that brief, regardless of hard-constraint violations — direct comparison against the generator's own score. `beats generator`/`improvement` instead use the GO/STOP gate's own WIN definition (best *zero-violation* LLM proposal vs generator) — see "GO/STOP verdict" above.

| brief | generator score | best LLM | median LLM | LLM kept/raw | materially distinct | duplicate rate | beats generator (win def.) | improvement (win def.) |
|---|---|---|---|---|---|---|---|---|
| B01 | -0.386294 | 0.651797 | -2.2674 | 7/8 | 7 | 0.0 | YES | 1.0381 |
| B02 | -2.345585 | 0.651797 | -2.208 | 8/9 | 7 | 0.111 | YES | 2.9974 |
| B03 | -1.51296 | 0.271786 | -0.7198 | 8/8 | 7 | 0.0 | YES | 1.7847 |
| B04 | -1.51296 | -1.070773 | -1.2308 | 8/8 | 8 | 0.0 | YES | 0.4422 |
| B05 | -2.033395 | -0.038917 | -1.6494 | 8/8 | 8 | 0.0 | YES | 1.9945 |
| B06 | -1.51296 | -0.719786 | -2.2559 | 8/8 | 8 | 0.0 | YES | 0.7932 |
| B07 | -3.839632 | -0.642711 | -1.0075 | 8/8 | 8 | 0.0 | YES | 3.1969 |
| B08 | -2.033395 | 0.514455 | -1.6505 | 6/8 | 6 | 0.0 | YES | 2.5478 |
| B09 | -1.51296 | 0.298441 | -0.6027 | 8/8 | 8 | 0.0 | YES | 1.8114 |
| B10 | -1.51296 | 0.609144 | -1.6853 | 9/9 | 8 | 0.0 | YES | 2.1221 |
| B11 | -4.006402 | -1.00274 | -2.3905 | 9/9 | 9 | 0.0 | YES | 3.0037 |
| B12 | -3.839632 | 0.198735 | -1.3499 | 8/8 | 8 | 0.0 | YES | 4.0384 |
| B13 | -3.618623 | 0.825159 | -1.8305 | 8/8 | 8 | 0.0 | YES | 4.4438 |
| B14 | -1.51296 | -0.111968 | -1.5065 | 8/8 | 8 | 0.0 | YES | 1.401 |
| B15 | -1.51296 | 0.902234 | -1.3911 | 8/8 | 8 | 0.0 | YES | 2.4152 |
| B16 | -2.033395 | 1.190307 | -2.3138 | 8/9 | 8 | 0.0 | YES | 3.2237 |
| B17 | -1.51296 | -1.649084 | -2.3702 | 9/9 | 9 | 0.0 | no | -0.1361 |
| B18 | -2.268223 | -0.034893 | -1.3361 | 8/11 | 8 | 0.0 | YES | 2.2333 |
| B19 | -1.6859 | -0.372291 | -1.7142 | 8/9 | 8 | 0.0 | YES | 1.3136 |
| B20 | -4.006402 | 0.348861 | -1.6468 | 9/9 | 9 | 0.0 | YES | 4.3553 |

## Score component detail (AC-5)

| brief | side | adjacency_similarity | access_similarity | wet_core_similarity | entrance_relation_score | hard_violations |
|---|---|---|---|---|---|---|
| B01 | generator | None | None | 1.0 | None | 0 |
| B01 | best LLM | -0.6702805332146903 | -0.6694942150468344 | 1.0 | 0.991572 | 0 |
| B02 | generator | -2.676090888010677 | -0.6694942150468344 | 1.0 | None | 0 |
| B02 | best LLM | -0.6702805332146903 | -0.6694942150468344 | 1.0 | 0.991572 | 0 |
| B03 | generator | -0.09314432695782497 | -2.41981578122236 | 1.0 | None | 0 |
| B03 | best LLM | -0.9817119654865304 | -0.7380742386276046 | 1.0 | 0.991572 | 0 |
| B04 | generator | -0.09314432695782497 | -2.41981578122236 | 1.0 | None | 0 |
| B04 | best LLM | -0.7390422632099073 | -2.323302815631266 | 1.0 | 0.991572 | 0 |
| B05 | generator | -2.295320382147868 | -0.7380742386276046 | 1.0 | None | 0 |
| B05 | best LLM | -1.2924152047498745 | -0.7380742386276046 | 1.0 | 0.991572 | 0 |
| B06 | generator | -0.09314432695782497 | -2.41981578122236 | 1.0 | None | 0 |
| B06 | best LLM | -0.9817119654865304 | -0.7380742386276046 | 1.0 | None | 0 |
| B07 | generator | -2.41981578122236 | -2.41981578122236 | 1.0 | None | 0 |
| B07 | best LLM | -1.2924152047498745 | -0.3502956629168488 | 1.0 | None | 0 |
| B08 | generator | -2.295320382147868 | -0.7380742386276046 | 1.0 | None | 0 |
| B08 | best LLM | -0.7390422632099073 | -0.7380742386276046 | 1.0 | 0.991572 | 0 |
| B09 | generator | -0.09314432695782497 | -2.41981578122236 | 1.0 | None | 0 |
| B09 | best LLM | -0.35126368749915154 | -0.3502956629168488 | 1.0 | None | 0 |
| B10 | generator | -0.09314432695782497 | -2.41981578122236 | 1.0 | None | 0 |
| B10 | best LLM | -0.04056044823580734 | -0.3502956629168488 | 1.0 | None | 0 |
| B11 | generator | -4.2683275348622844 | -0.7380742386276046 | 1.0 | None | 0 |
| B11 | best LLM | -0.9817119654865304 | -2.012599576367922 | 1.0 | 0.991572 | 0 |
| B12 | generator | -2.41981578122236 | -2.41981578122236 | 1.0 | None | 0 |
| B12 | best LLM | -0.04056044823580734 | -0.4273709993642605 | 0.6666666666666666 | None | 0 |
| B13 | generator | -3.880548959151529 | -0.7380742386276046 | 1.0 | None | 0 |
| B13 | best LLM | -0.4283390239465632 | -0.7380742386276046 | 1.0 | 0.991572 | 0 |
| B14 | generator | -0.09314432695782497 | -2.41981578122236 | 1.0 | None | 0 |
| B14 | best LLM | -0.04056044823580734 | -0.7380742386276046 | 0.6666666666666666 | None | 0 |
| B15 | generator | -0.09314432695782497 | -2.41981578122236 | 1.0 | None | 0 |
| B15 | best LLM | -0.35126368749915154 | -0.7380742386276046 | 1.0 | 0.991572 | 0 |
| B16 | generator | -2.295320382147868 | -0.7380742386276046 | 1.0 | None | 0 |
| B16 | best LLM | -0.04056044823580734 | -0.4273709993642605 | 0.6666666666666666 | 0.991572 | 0 |
| B17 | generator | -0.09314432695782497 | -2.41981578122236 | 1.0 | None | 0 |
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
- Improvement: **4.443782**
- Why the critic preferred the LLM proposal: its adjacency/access graph sits closer to the corrected #149 corpus's own measured pattern (higher, less-negative log-likelihood) than the current generator's topology for this brief, with zero hard constraint violations — see the score component table above for the exact numbers.

### B20 (2 bed, 3 wet room(s), safe_room=True, open_plan=True, small/square)

- Current generator score: **-4.006402** (0 hard violations)
- Best zero-violation LLM proposal score: **0.348861** (realizability=REALIZABLE_BY_CURRENT_ENGINE)
- Improvement: **4.355263**
- Why the critic preferred the LLM proposal: its adjacency/access graph sits closer to the corrected #149 corpus's own measured pattern (higher, less-negative log-likelihood) than the current generator's topology for this brief, with zero hard constraint violations — see the score component table above for the exact numbers.

### B12 (4 bed, 3 wet room(s), safe_room=False, open_plan=False, large/square)

- Current generator score: **-3.839632** (0 hard violations)
- Best zero-violation LLM proposal score: **0.198735** (realizability=NOT_REALIZABLE_BY_CURRENT_ENGINE)
- Improvement: **4.038367**
- Why the critic preferred the LLM proposal: its adjacency/access graph sits closer to the corrected #149 corpus's own measured pattern (higher, less-negative log-likelihood) than the current generator's topology for this brief, with zero hard constraint violations — see the score component table above for the exact numbers.

### B16 (5 bed, 3 wet room(s), safe_room=True, open_plan=True, medium/wide)

- Current generator score: **-2.033395** (0 hard violations)
- Best zero-violation LLM proposal score: **1.190307** (realizability=NOT_REALIZABLE_BY_CURRENT_ENGINE)
- Improvement: **3.2237020000000003**
- Why the critic preferred the LLM proposal: its adjacency/access graph sits closer to the corrected #149 corpus's own measured pattern (higher, less-negative log-likelihood) than the current generator's topology for this brief, with zero hard constraint violations — see the score component table above for the exact numbers.

### B07 (3 bed, 2 wet room(s), safe_room=True, open_plan=False, large/square)

- Current generator score: **-3.839632** (0 hard violations)
- Best zero-violation LLM proposal score: **-0.642711** (realizability=REALIZABLE_BY_CURRENT_ENGINE)
- Improvement: **3.1969209999999997**
- Why the critic preferred the LLM proposal: its adjacency/access graph sits closer to the corrected #149 corpus's own measured pattern (higher, less-negative log-likelihood) than the current generator's topology for this brief, with zero hard constraint violations — see the score component table above for the exact numbers.

### B11 (4 bed, 2 wet room(s), safe_room=True, open_plan=True, medium/narrow)

- Current generator score: **-4.006402** (0 hard violations)
- Best zero-violation LLM proposal score: **-1.00274** (realizability=NOT_REALIZABLE_BY_CURRENT_ENGINE)
- Improvement: **3.0036619999999994**
- Why the critic preferred the LLM proposal: its adjacency/access graph sits closer to the corrected #149 corpus's own measured pattern (higher, less-negative log-likelihood) than the current generator's topology for this brief, with zero hard constraint violations — see the score component table above for the exact numbers.

### B02 (1 bed, 1 wet room(s), safe_room=False, open_plan=True, medium/narrow)

- Current generator score: **-2.345585** (0 hard violations)
- Best zero-violation LLM proposal score: **0.651797** (realizability=NOT_REALIZABLE_BY_CURRENT_ENGINE)
- Improvement: **2.997382**
- Why the critic preferred the LLM proposal: its adjacency/access graph sits closer to the corrected #149 corpus's own measured pattern (higher, less-negative log-likelihood) than the current generator's topology for this brief, with zero hard constraint violations — see the score component table above for the exact numbers.

### B08 (3 bed, 1 wet room(s), safe_room=False, open_plan=True, small/square)

- Current generator score: **-2.033395** (0 hard violations)
- Best zero-violation LLM proposal score: **0.514455** (realizability=REALIZABLE_BY_CURRENT_ENGINE)
- Improvement: **2.54785**
- Why the critic preferred the LLM proposal: its adjacency/access graph sits closer to the corrected #149 corpus's own measured pattern (higher, less-negative log-likelihood) than the current generator's topology for this brief, with zero hard constraint violations — see the score component table above for the exact numbers.

### B15 (5 bed, 2 wet room(s), safe_room=True, open_plan=False, medium/square)

- Current generator score: **-1.51296** (0 hard violations)
- Best zero-violation LLM proposal score: **0.902234** (realizability=REALIZABLE_BY_CURRENT_ENGINE)
- Improvement: **2.415194**
- Why the critic preferred the LLM proposal: its adjacency/access graph sits closer to the corrected #149 corpus's own measured pattern (higher, less-negative log-likelihood) than the current generator's topology for this brief, with zero hard constraint violations — see the score component table above for the exact numbers.

### B18 (6 bed, 3 wet room(s), safe_room=True, open_plan=False, medium/square)

- Current generator score: **-2.268223** (0 hard violations)
- Best zero-violation LLM proposal score: **-0.034893** (realizability=NOT_REALIZABLE_BY_CURRENT_ENGINE)
- Improvement: **2.23333**
- Why the critic preferred the LLM proposal: its adjacency/access graph sits closer to the corrected #149 corpus's own measured pattern (higher, less-negative log-likelihood) than the current generator's topology for this brief, with zero hard constraint violations — see the score component table above for the exact numbers.

## Known limitations

- `entrance_relation_score` is `None` whenever the entrance opens into a room whose role (e.g. HALL) the corrected #149 corpus cannot measure `front_door_direct_access` for — genuine unmeasurability, not a zero.
- `best LLM` (per-brief table) and the WIN definition (GO/STOP gate, headline, worked examples) differ deliberately: the first is a raw ceiling regardless of hard-constraint violations, the second requires zero violations, matching `baseline.json`'s own `win_definition`.
- This run's dataset carries `retry_count = 0` for every brief: the model produced at least one schema-valid proposal on its first attempt for all 20 briefs (unlike the control run below, where a small local model frequently produced none at all).
