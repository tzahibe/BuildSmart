# Real-plan adjacency priors — A/B + decision-relevance report (Issue #141, Steps 3/4/6)

`ADJACENCY_PRIORS_ENABLED = False` (shipped default, "OFF") vs `ADJACENCY_PRIORS_ENABLED = True`
("ON"), over the frozen, committed **432-context** regression corpus
(`backend/tests/regression_corpus/corpus.json`), via
`backend/spikes/failure_log_sweep/adjacency_priors_ab.py` (sharded 2-way, 8 workers each half — see
that script's own header for the exact commands run).

**#140 taught the lesson this Issue is built around**: a prior can be statistically correct and
still move nothing if it is wired where it has no deciding power. This report answers BOTH of the
Issue's questions — does the prior improve the measured metrics, and does the engine even produce a
candidate pool in which it COULD — and the second answer is the more important finding here.

## Headline result — flag OFF vs ON (AC-7: byte-identical)

| metric | OFF | ON |
|---|---|---|
| planned | 404 | 404 |
| refused | 28 | 28 |
| crashes | 0 | 0 |
| validity / refusal rate | 93.5% / 6.5% | 93.5% / 6.5% (identical) |
| byte-identical primaries | — | **404/404 (100%)** |
| M5 — wet-adjacency ratio, median (`app.vertical_slice.quality_metrics`, unchanged, read only) | 0.0 | 0.0 |
| M6 — public-zone contiguous share (unchanged, read only) | 1.0 | 1.0 |
| adjacency similarity to the real distribution, median (this Issue's own metric — see "Method") | -1.4342 | -1.4342 (identical — see below) |
| LOST | — | 0 |
| GAINED | — | 0 |
| new crashes | — | 0 |
| status changes | — | 0 |
| refusal-code changes | — | 0 |
| **primary_signature_changes** | — | **0** |

`adjacency_similarity_score_median` is identical OFF vs ON because `primary_signature_changes == 0`
proves the exact same geometry is delivered both times — there is nothing left to re-score.

**AC-7 holds**: no validator, threshold or hard limit was touched, and the flag-OFF corpus is
byte-identical to what it was before this Issue (the sort-key argument below, plus this A/B, are the
two independent proofs).

## Decision relevance (Step 3/4) — the finding that matters more

Measured on the OFF run's own candidate sets (candidate identity is independent of the flag; see
"Method"), restricted to the 404 PLANNED contexts (28 REFUSED contexts never reached a candidate
set at all, and are reported separately, never folded into "no candidate near real" below):

| | value |
|---|---|
| analyzable candidate sets | 404 |
| % of candidate sets where the adjacency score **VARIES** (`score_spread >= 1e-6`) | **31.9%** (129/404) |
| % where the prior **COULD** have changed the winner (varies AND the winner is genuinely tied on every existing criterion) | **0.0%** (0/404) |
| % where the prior **ACTUALLY** changed the winner (flag ON re-run, signature comparison) | **0.0%** (0/404) |
| candidate sets with a completely INERT prior (`score_spread == 0`) | 275 (68.1%) |
| candidate sets with real variance but the existing ranking blocked it (varies, could not change) | 129 (31.9%) |

**Why 0% could ever change the winner, even where the score varies**: `generate_concepts` only ever
lets this term matter between candidates that already tie on every earlier criterion (area-diff,
`over_preferred`/`shrunk`, area, strategy, and #140's own room-proportion prior). Measured directly
on this corpus, the ONLY structural tie the generator ever produces is a forced tree and its own
"free twin" (`_free_twin` — the same tree with cut positions left to the solver, see
`concept_generator.py`'s own comment on why twins are appended last). Every one of the 404 contexts'
`tied_count` is exactly 2 — a forced candidate and its twin, nothing else ties. And a forced tree and
its free twin overwhelmingly solve to the SAME (or adjacency-identical) geometry — so even where
`score_spread` is non-zero across the WHOLE candidate set (from candidates in a DIFFERENT, non-tied
position), the two candidates that are actually tied with the winner always score identically. This
is a **RANKING ARCHITECTURE** finding: the tie structure itself, not the prior's own quality, is what
makes this term structurally unable to matter on this corpus — the same root cause #140 already
found for its own, unrelated prior.

## Four-state classification (Step 4)

| state | count | share of 404 |
|---|---|---|
| 1. VARIES_AND_CHANGES_WINNER (ranking + prior work together) | 0 | 0.0% |
| 2. VARIES_BUT_WINNER_UNCHANGED (ranking architecture is the ceiling) | 0 | 0.0% |
| 3. NO_REAL_VARIANCE (candidate/topology diversity is the ceiling) | 0 | 0.0% |
| 4. **NO_CANDIDATE_NEAR_REAL** (candidate generation/expressiveness is the ceiling) | **404** | **100.0%** |

Every single PLANNED context lands in state 4. "Near the real distribution" is calibrated against
the SAME 19-plan corpus `adjacency.json` was measured from: each real plan is scored against its own
table (in-sample — an honestly-acknowledged optimism, since the real corpus IS the population the
table was built from), giving `real_median_score = -0.3253` and a population stdev of `0.1455`. A
context is state 4 when its BEST-scoring candidate still falls more than one stdev below that
median (`< -0.4708`). Measured: **the single best candidate score anywhere in the entire 432-context
corpus is -0.6270** — worse than the threshold by a comfortable margin, not a borderline call. States
1-3 are structurally impossible to reach while state 4 holds for every context, since state 4 is
checked first (see the script's own module docstring for the priority order and its justification).

**What this means, honestly**: given the Issue's own framing — "does the engine even produce a
candidate pool in which an adjacency prior could pick something better?" — the measured answer here
is **no**, and the reason is legible. `BEDROOM`-`LIVING` has `lift=1.34` in the real corpus
(`p_adjacent=0.94` — real plans overwhelmingly put a bedroom directly against the living room, no
intervening room). This engine's own massing families route every bedroom off a `HALL`/corridor
instead — `BEDROOM`-`LIVING` is essentially never realized as touching in ANY candidate this corpus
produces (verified directly: e.g. context `bedrooms=1, built_area_m2=132.0` realizes `MASTER_BEDROOM`
at x=[9.65,14.45] and `LIVING_KITCHEN` at x=[3.55,8.25], separated by the `HALL` at x=[8.25,9.65] —
a `HALL`-mediated topology, in every candidate the generator offers for that brief). That single
mismatched pair alone (`y=0` against a real `p=0.94`) contributes `log(1-0.9444) ≈ -2.89` to every
affected candidate's score — enough on its own to explain the gap. This is a **CANDIDATE
GENERATION / EXPRESSIVENESS** finding: no ranking or selection change over the existing candidate
pool can produce a plan closer to real adjacency patterns, because none of the pool's own massing
families ever try the corridor-free, direct-bedroom-to-living topology real plans commonly use.

## 5-10 worked examples where the winner changed

**None exist in this corpus — reported honestly, not fabricated.** `pct_did_change_winner = 0.0%`
(0/404) and `pct_could_change_winner = 0.0%` (0/404): see "Decision relevance" above for the
mechanical reason (every tie is a forced-tree/free-twin pair that scores identically). This is the
expected, structurally-explained result given how the signal is wired (`adjacency_score(c)` appended
as the LAST element of every sort key, strictly after area-budget, `over_preferred`/shrunk, strategy
and #140's own prior — see `app/vertical_slice/adjacency_priors.py`'s module docstring) — it can
only ever reorder candidates that already tie on every existing criterion, and this corpus's own tie
structure never gives it the chance. `test_adjacency_score_only_breaks_a_genuine_tie` and
`test_adjacency_score_cannot_outrank_area_budget_or_strategy_tiebreak`
(`tests/vertical_slice/test_adjacency_priors_ranking.py`) prove the mechanism DOES reorder a
constructed genuine tie and never anything else — this is not dead code, it is a real, bounded
mechanism that this corpus's own candidate diversity never exercises.

## Examples where no good candidate existed at all

Ten representative contexts (diverse bedroom counts and footprints), each showing every candidate's
own adjacency score, `score_spread` within that tier, and the winner's score against the real
threshold (`-0.4708`):

| context | candidate_count | scored | score_spread | winner_score | margin |
|---|---|---|---|---|---|
| bedrooms=4, built_area=132.0m2, footprint=11.0x12.0 | 28 | 24 | 0.979186 | -1.099189 | tied |
| bedrooms=5, built_area=181.25m2, footprint=12.5x14.5 | 30 | 24 | 0.979186 | -1.099189 | tied |
| bedrooms=3, built_area=181.25m2, footprint=12.5x14.5, open_plan | 58 | 40 | 0.979186 | -1.470367 | tied |
| bedrooms=6, built_area=181.25m2, footprint=12.5x14.5, safe_room | 18 | 5 | 0.472201 | -1.561286 | tied |
| bedrooms=2, built_area=200.0m2, footprint=20.0x10.0 | 24 | 19 | 0.462097 | -0.998166 | tied |
| bedrooms=1, built_area=132.0m2, footprint=11.0x12.0, wet_rooms=2 | 8 | 8 | 0.0 | -0.998166 | tied |
| bedrooms=1, built_area=132.0m2, footprint=11.0x12.0, open_plan, wet_rooms=1 | 12 | 12 | 0.0 | -1.470367 | tied |
| bedrooms=1, built_area=181.25m2, footprint=12.5x14.5, wet_rooms=2 | 12 | 12 | 0.0 | -0.998166 | tied |
| bedrooms=1, built_area=200.0m2, footprint=20.0x10.0, safe_room, wet_rooms=1 | 24 | 20 | 0.0 | -1.460263 | tied |
| bedrooms=1, built_area=200.0m2, footprint=20.0x10.0, open_plan, safe_room, wet_rooms=1 | 10 | 10 | 0.0 | -1.932500 | tied |

Every row's `winner_score` sits well below the real-corpus threshold of `-0.4708` — the best any
candidate reaches anywhere in the corpus is `-0.6270` (see "Four-state classification" above).

## One fully detailed candidate set (every candidate's own score, not just the winner's)

Context `bedrooms=4, built_area_m2=132.0, footprint=11.0x12.0, safe_room=False, wet_rooms=1`: 28
candidates in the winner's tier, 24 with a scored adjacency pattern (4 have no eligible pair with a
supported artifact row and are excluded, never scored as a fabricated 0.0):

    -0.626988, -1.099189, -1.099189, -1.606174, -1.099189, -1.099189, -1.606174, -1.099189,
    -1.099189, -1.606174, -0.626988, -1.099189, -1.099189, -1.606174, -1.099189, -1.099189,
    -1.099189, -1.606174, -1.099189, -1.099189, -1.606174, -1.099189, -1.099189, -1.099189

`score_spread = 0.979186` (max `-0.626988` - min `-1.606174`) — real variance across the tier. The
**winner's own score is `-1.099189`** (the modal value, 14/24 candidates), and its `tied_count` is
`2`: only ONE other candidate shares its exact existing-key tuple (area-diff, `over_preferred`-or-
`shrunk`, `over_preferred`, area, strategy — the criteria that decide ranking BEFORE this term is
ever read), and that one candidate is its own free twin, which also scores `-1.099189`. The two
candidates that scored `-0.626988` (the best in the whole tier) are NOT tied with the winner on any
existing criterion — the adjacency term never even gets to compare against them, however much
better they score. This is `margin: "tied"`, `could_change_winner: False` — the concrete mechanics
behind the 0%/0% headline above, shown on one real candidate set rather than only asserted.

## Method

`adjacency_priors_ab.py` replays every context through `app.demo.service.generate_demo_design`.
The OFF run is instrumented (`generate_concepts` and `_select_plans` are wrapped, never their
behaviour changed) to capture the exact candidate set `concept_generator.generate_concepts`
produced for the outline that won — identified by OBJECT IDENTITY (`_select_plans`'s own return
value names the winning `ConceptCandidate`; the `generate_concepts` call whose returned list
literally contains that object, by `is`, is the winner's candidate set), robust regardless of how
many outlines `service.py`'s own search tries or in what order. The ON run is a second, plain
`generate_demo_design` call with the flag set, compared by realized-plan signature — the same
signature `corpus_snapshot.py`'s own byte-identical-primary check uses.

Within the winner's own TIER (`accepted`/`tier2`/`quality` — `generate_concepts` never compares
candidates across tiers), every candidate's own adjacency score is computed via
`app.vertical_slice.adjacency_priors.candidate_eligible_pair_outcomes` (solved on that candidate's
OWN Rect geometry, exactly as the runtime signal does) fed through
`app.knowledge.adjacency_priors.plan_log_likelihood` — called directly and unconditionally, not
gated by `ADJACENCY_PRIORS_ENABLED`, since this is a measurement of what the score WOULD be, not the
ranking decision itself. `score_spread` is `max - min` of every scored candidate's own value in that
tier. `margin` is `"tied"` when at least one OTHER candidate shares the winner's exact "existing
key" (the sort-key tuple `generate_concepts` ranks that tier by, EXCLUDING the room-proportion and
adjacency terms) — the only condition under which a lower-precedence term can matter at all — else
`"decisive"`. `could_change_winner` is `margin == "tied"` AND the tied group's own scores are not
all equal.

`compare()` reuses the exact LOST/GAINED/status-change/refusal-code-change/primary-signature-change
definitions `spikes/failure_log_sweep/corpus_snapshot.py`'s own `compare()` uses, so these numbers
are directly comparable to any other flag/toggle A/B in this repo (including #140's own).

## Reproduce

From `backend/`:

    uv run python spikes/failure_log_sweep/adjacency_priors_ab.py --save-off off-0.json --shard 0/2 --workers 8
    uv run python spikes/failure_log_sweep/adjacency_priors_ab.py --save-off off-1.json --shard 1/2 --workers 8
    uv run python spikes/failure_log_sweep/adjacency_priors_ab.py --merge-off merged.json off-0.json off-1.json
    uv run python spikes/failure_log_sweep/adjacency_priors_ab.py --compare merged.json --report report.json

(run sharded — `--shard I/N` — to fit each half inside a bounded wall-clock budget; every number
above was produced that way, 2-way, 8 workers each side, ~8-10 minutes per shard.)
