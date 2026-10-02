# FORCED LOCAL-MODEL CONTROL RUN — NOT VALID FOR THE #142 GO/STOP DECISION

This is a SEPARATE run from the PRIMARY experiment (see `results.md`) — it uses `llama3.2:latest`, a small local model, forced by this sandbox's lack of external network egress or API key, NOT chosen as a stand-in for "a strong LLM". No number below enters the primary run's statistics or its GO/STOP verdict.

**The LLM produces no geometry.** Every proposal below (current-generator and LLM alike) passed through the identical, deterministic, geometry-free critic (`critic.py`) — the critic is blind to which is which (AC-10). Realizability is metadata only and never entered any score (AC-9). See `docs/reports/llm-topology-poc/schema.md` for the schema and `briefs.md` for the 20 committed briefs.

## Provenance of the ground truth (AC-13)

- Adjacency/access artifact: `docs/reports/real-plan-priors/adjacency-fullcorpus.json`
- Room-proportions artifact: `docs/reports/real-plan-priors/room-proportions.json`
- Commit SHA this run's ground truth came from: `6a4aae74e6ab75fa12074e3d43fb9724575376e9`
- Artifact SHA-256: `23ee2b752f0fd33b018d2b76075d049353dbd3d6ad18d5826fc39b3e4b7819c5`
- Train count: **13648**, holdout count: **3459**
- Generated at (UTC): `2026-09-29T04:41:18Z`

## Headline comparison (AC-7)

**22.2%** of briefs (2/9) have at least one LLM proposal whose critic score beats the current generator's own topology for that same brief.
- Average improvement (best LLM score minus generator score, comparable briefs only): **-10.4198**
- Median improvement: **-11.6917**

LLM model used: `llama3.2:latest` — a local model reachable from this sandbox (no external network egress or API key is available here); see Known limitations below for what this implies about ceiling quality.

## Realizability distribution (AC-6)

Across every proposal scored (current-generator + LLM, 49 total):

| label | count | share |
|---|---|---|
| REALIZABLE_BY_CURRENT_ENGINE | 32 | 65.3% |
| NOT_REALIZABLE_BY_CURRENT_ENGINE | 12 | 24.5% |
| UNKNOWN | 5 | 10.2% |

Realizability is METADATA ONLY (AC-9) — `NOT_REALIZABLE_BY_CURRENT_ENGINE` counts above never reduced any proposal's quality score; see `tests/ai_harness/test_topology_critic.py::test_score_is_independent_of_realizability_label`.

## Per-brief results (AC-5)

| brief | generator score | best LLM | median LLM | LLM kept/raw | materially distinct | duplicate rate | beats generator |
|---|---|---|---|---|---|---|---|
| B01 | -0.386294 | -7.694927 | -8.8596 | 5/8 | 5 | 0.375 | no |
| B02 | -2.345585 | -0.186289 | -0.1863 | 3/7 | 3 | 0.0 | YES |
| B03 | -1.51296 | -20.186289 | -20.1863 | 3/18 | 3 | 0.111 | no |
| B04 | -1.51296 | -2.15245 | -11.3863 | 3/7 | 3 | 0.0 | no |
| B05 | -2.033395 | -19.28823 | -19.2882 | 1/17 | 1 | 0.176 | no |
| B06 | -1.51296 | — | — | 0/0 | 0 | 0.0 | no |
| B07 | -3.839632 | -15.531309 | -15.5313 | 3/7 | 3 | 0.286 | no |
| B08 | -2.033395 | -1.386294 | -8.4588 | 2/14 | 2 | 0.0 | YES |
| B09 | -1.51296 | -15.531309 | -21.3863 | 5/7 | 5 | 0.143 | no |
| B10 | -1.51296 | — | — | 0/15 | 0 | 0.0 | no |
| B11 | -4.006402 | — | — | 0/7 | 0 | 0.0 | no |
| B12 | -3.839632 | — | — | 0/0 | 0 | 0.0 | no |
| B13 | -3.618623 | — | — | 0/16 | 0 | 0.0 | no |
| B14 | -1.51296 | -28.511519 | -57.6571 | 4/7 | 4 | 0.0 | no |
| B15 | -1.51296 | — | — | 0/17 | 0 | 0.0 | no |
| B16 | -2.033395 | — | — | 0/14 | 0 | 0.0 | no |
| B17 | -1.51296 | — | — | 0/0 | 0 | 0.0 | no |
| B18 | -2.268223 | — | — | 0/9 | 0 | 0.0 | no |
| B19 | -1.6859 | — | — | 0/0 | 0 | 0.0 | no |
| B20 | -4.006402 | — | — | 0/7 | 0 | 0.0 | no |

## Score component detail (AC-5)

Per brief: the current generator's own adjacency similarity / access similarity / wet-core similarity / entrance-relation score / hard violations, for direct comparison against its best LLM proposal's own components.

| brief | side | adjacency_similarity | access_similarity | wet_core_similarity | entrance_relation_score | hard_violations |
|---|---|---|---|---|---|---|
| B01 | generator | None | None | 1.0 | None | 0 |
| B01 | best LLM | -5.846548042018 | -3.839951369054157 | 1.0 | 0.991572 | 0 |
| B02 | generator | -2.676090888010677 | -0.6694942150468344 | 1.0 | None | 0 |
| B02 | best LLM | -0.09314432695782497 | -0.09314432695782497 | 0.0 | None | 0 |
| B03 | generator | -0.09314432695782497 | -2.41981578122236 | 1.0 | None | 0 |
| B03 | best LLM | -0.09314432695782497 | -0.09314432695782497 | 0.0 | 0.0 | 2 |
| B04 | generator | -0.09314432695782497 | -2.41981578122236 | 1.0 | None | 0 |
| B04 | best LLM | -2.0083346396642328 | -0.14411520408416775 | 0.0 | None | 0 |
| B05 | generator | -2.295320382147868 | -0.7380742386276046 | 1.0 | None | 0 |
| B05 | best LLM | -0.14411520408416775 | -0.14411520408416775 | 1.0 | None | 2 |
| B06 | generator | -0.09314432695782497 | -2.41981578122236 | 1.0 | None | 0 |
| B07 | generator | -2.41981578122236 | -2.41981578122236 | 1.0 | None | 0 |
| B07 | best LLM | -6.019864021629663 | -9.511445464760104 | None | None | 0 |
| B08 | generator | -2.295320382147868 | -0.7380742386276046 | 1.0 | None | 0 |
| B08 | best LLM | None | None | None | None | 0 |
| B09 | generator | -0.09314432695782497 | -2.41981578122236 | 1.0 | None | 0 |
| B09 | best LLM | -6.019864021629663 | -9.511445464760104 | None | None | 0 |
| B10 | generator | -0.09314432695782497 | -2.41981578122236 | 1.0 | None | 0 |
| B11 | generator | -4.2683275348622844 | -0.7380742386276046 | 1.0 | None | 0 |
| B12 | generator | -2.41981578122236 | -2.41981578122236 | 1.0 | None | 0 |
| B13 | generator | -3.880548959151529 | -0.7380742386276046 | 1.0 | None | 0 |
| B14 | generator | -0.09314432695782497 | -2.41981578122236 | 1.0 | None | 0 |
| B14 | best LLM | -7.400273813510066e-05 | -9.511445464760104 | 1.0 | 0.0 | 2 |
| B15 | generator | -0.09314432695782497 | -2.41981578122236 | 1.0 | None | 0 |
| B16 | generator | -2.295320382147868 | -0.7380742386276046 | 1.0 | None | 0 |
| B17 | generator | -0.09314432695782497 | -2.41981578122236 | 1.0 | None | 0 |
| B18 | generator | -1.9364922645028129 | -2.323302815631266 | 1.0 | 0.991572 | 0 |
| B19 | generator | -2.9393974419008058 | -0.7380742386276046 | 1.0 | 0.991572 | 0 |
| B20 | generator | -4.2683275348622844 | -0.7380742386276046 | 1.0 | None | 0 |

## Worked examples (AC-7)

### B02 (1 bed, 1 wet room(s), safe_room=False, open_plan=True, medium/narrow)

- Current generator score: **-2.345585** (0 hard violations)
- Best LLM proposal score: **-0.186289** (0 hard violations, realizability=NOT_REALIZABLE_BY_CURRENT_ENGINE)
- Improvement: **2.159296**
- Why the critic preferred the LLM proposal: its adjacency/access graph sits closer to the corrected #149 corpus's own measured pattern (higher, less-negative log-likelihood) and/or it carries fewer hard-rule violations than the current generator's topology for this brief — see the score component table above for the exact numbers.

### B08 (3 bed, 1 wet room(s), safe_room=False, open_plan=True, small/square)

- Current generator score: **-2.033395** (0 hard violations)
- Best LLM proposal score: **-1.386294** (0 hard violations, realizability=REALIZABLE_BY_CURRENT_ENGINE)
- Improvement: **0.6471010000000001**
- Why the critic preferred the LLM proposal: its adjacency/access graph sits closer to the corrected #149 corpus's own measured pattern (higher, less-negative log-likelihood) and/or it carries fewer hard-rule violations than the current generator's topology for this brief — see the score component table above for the exact numbers.

## Known limitations

- The LLM used is a small (3B parameter) local model reachable from this sandbox — no external network egress or API key is available here. This measures whether the POC METHOD surfaces genuine quality differences at all; it is not a measurement of what a frontier model would do, which the owner's GO/STOP decision should weigh accordingly.
- A brief with zero schema-valid LLM proposals (after one retry) contributes no `best_llm`/`median_llm` value and is excluded from the headline percentage's denominator, not counted as a loss or a win.
- `entrance_relation_score` is `None` whenever the entrance opens into a room whose role (e.g. HALL) the corrected #149 corpus cannot measure `front_door_direct_access` for — genuine unmeasurability, not a zero.
