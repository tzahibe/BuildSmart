# #142N — Why `circulation_prefers` is non-transitive

**Final question.** Why is `circulation_metrics.circulation_prefers` non-transitive, and what is the
smallest mathematically sound representation of circulation quality that preserves its architectural
meaning without introducing arbitrary weights?

**Answer.** It is non-transitive because it is not a preference at all — it is a *veto* that was
reused as one. Its rule is "the candidate is better on **at least one** measure", which is the exact
logical complement of Pareto dominance and is therefore neither antisymmetric nor transitive by
construction. Two separate defects produce the measured cycles. The first is an **implementation
bug**: the code compares a fourth quantity, `area`, that its own docstring does not mention and that
is not a circulation measure at all; removing it alone drops the ordered 3-cycles from 267 to 24 on
the corrected pool. The second survives that fix and is **structural**: three measures that disagree
with each other, combined disjunctively, cycle whatever the tolerances are. The tolerance is not a
cause (a strict comparison on one scalar provably cannot cycle, and zero of the 117 measured cycles
is carried by a single measure), though the one shared `_EPS = 0.02` is separately wrong — it covers
16% of the observed range of a dimensionless ratio and 0.2% of the range of a length in metres.

The smallest sound representation is **not a total order**, and the task's own stop rule is the
correct outcome. Of the three measures, only `dead_end_count` has a direction that is defensible on
its own. `ratio` and `longest_segment_m` are **bounded, not optimised**: production already bounds
both from above in C26, bounds neither from below, and on this pool every validator-PASS plan is
already inside those bounds, so neither carries any further validated signal. So:

> **Circulation quality is a screen plus a two-element Pareto vector, not a winner.** Keep
> `classify_extreme` as the bound it already is, expose the measured quantities as reported
> dimensions, and compare plans only by Pareto dominance on the measures whose direction is
> monotone — dead ends and duplicated segments. That relation is transitive, antisymmetric,
> weight-free, and deliberately silent: it overrides the current selection in **1 of 20** briefs.

**Nothing in production was modified.** `circulation_metrics` is imported and called throughout.

---

## 1. What the comparator actually compares

`circulation_prefers(current, current_area_m2, candidate, candidate_area_m2)` returns `None` when
the candidate wins. Reading `None` as "y beats x":

> **y ≻ x** iff `better_on(x, y)` is non-empty **and** `area(y) ≥ 0.85 × area(x)`

and `better_on` fires on **any one** of four disjuncts:

| disjunct | condition | in the docstring? | a circulation measure? |
|---|---|---|---|
| `ratio` | `y.ratio < x.ratio − 0.02` | yes | partly — see §5 |
| `longest_segment` | `y.longest < x.longest − 0.02` | yes | partly — see §5 |
| `dead_end_count` | `y.dead_ends < x.dead_ends` | yes | **yes** |
| `area` | `area(y) > area(x) + 0.05` | **no** | **no** |

Two things follow immediately and are confirmed on every pair of both pools (0 mismatches between
this decomposition and production's own return value, 132 plans, 206 within-brief pairs):

- **The relation is not antisymmetric.** Plan A better on ratio and plan B better on dead ends means
  each beats the other. That happens on **31 of 63** within-brief pairs (historical) and **75 of
  143** (corrected) — roughly half of every comparison production could make.
- **`area` is counted twice, in opposite roles.** It is the floor in rule 2 and simultaneously a
  reason to win in rule 1. A plan with strictly worse circulation on all three real measures still
  "wins on circulation" for being 5 cm² bigger.

## 2. Reproduced: the smallest concrete cycle

**Corrected pool, brief B19.** Three validator-PASS plans, all with zero dead ends and all three
ratios within 0.009 of each other (so `ratio` is silent under the 0.02 tolerance):

| plan | circulation ratio | longest segment | dead ends | plan area |
|---|---:|---:|---:|---:|
| B19#0 | 0.1455 | 7.70 m | 0 | 184.44 m² |
| B19#4 | 0.1365 | 6.85 m | 0 | 175.33 m² |
| B19#7 | 0.1431 | 7.50 m | 0 | 177.29 m² |

- **#4 ≻ #0** — its corridor is 0.85 m shorter.
- **#7 ≻ #4** — it is 1.96 m² bigger.
- **#0 ≻ #7** — it is 7.15 m² bigger.

Every area floor is satisfied (all three are within 5% of each other), so all three edges are real.
`figures/corrected-smallest-cycle.png`.

**A cycle with no area edge at all** — historical, brief B09, the three circulation measures alone:

| plan | ratio | longest segment | dead ends |
|---|---:|---:|---:|
| B09#1 | 0.0847 | 3.45 m | 1 |
| B09#2 | 0.1350 | 5.50 m | 0 |
| B09#4 | 0.1423 | 4.35 m | 1 |

#2 ≻ #1 on dead ends, #4 ≻ #2 on longest segment, #1 ≻ #4 on ratio and longest segment.
`figures/historical-cycle-without-area.png` — three visibly different plans, same brief.

**Totals.** Reproduces #142M exactly: **84 ordered / 28 distinct** 3-cycles (historical) and
**267 / 89** (corrected).

## 3. Root cause, adjudicated against the four candidate explanations

| candidate cause | verdict | evidence |
|---|---|---|
| implementation bug | **yes, and it is the larger share** | Removing only the undocumented `area` disjunct takes ordered 3-cycles from 84 → 9 (historical) and 267 → 24 (corrected), mutual pairs from 31 → 7 and 75 → 16. **81 of 89** corrected cycles have at least one edge carried by `area` alone. |
| inevitable consequence of the comparison shape | **yes, and it is the deeper one** | 3 and 8 distinct cycles survive with `area` removed. "Better on at least one of N" is the complement of Pareto dominance; with two measures that disagree it cycles for arithmetic reasons, and the unit test `test_three_plans_cycle_on_the_circulation_measures_alone` builds one from equal-area plans where each edge is carried by exactly one distinct measure. |
| tolerances | **no** | A strict comparison on one scalar is transitive: i<j−ε, j<k−ε, k<i−ε sums to 0 < −3ε. Measured: **0 of 117** distinct cycles is carried by a single measure. (The shared ε is wrong for a different reason — §5.) |
| pair-relative normalisation | **contributing, not causal** | The 0.85 floor is relative to whichever plan is `current`, so the same candidate clears it against one reference and not another. It removes edges rather than creating them, and no cycle in either pool is blocked by it. A second, subtler instance is inside `ratio` itself, which is circulation area ÷ *plan* area, so a plan lowers its ratio by growing the house (§5). |
| conflicting circulation objectives | **yes — this is what the disjunction is hiding** | Every pair of measures ranks some pairs in opposite directions. Conflict share among the pairs each can decide: ratio vs dead ends **0.56** (historical) / 0.20 (corrected); dead ends vs area **0.53** / 0.47; longest segment vs area **0.35** / 0.35; ratio vs longest segment 0.12 / 0.22. |

So the honest answer to "bug or inevitable" is **both, and they are separable**: the `area` disjunct
is a bug that accounts for about 90% of the measured cycles, and the disjunctive rule underneath is
a category error that accounts for the rest.

## 4. What the cycles cost, and where production is actually exposed

Production's ranking pattern is a greedy fold — keep `current`, replace it when the next candidate
is preferred. Run over **every** arrival order of the same plan set, that fold lands on:

| | briefs whose winner depends on arrival order | worst case |
|---|---:|---:|
| historical | 11 of the 13 with more than one plan | 4 different winners |
| corrected | 16 of the 20 with more than one plan | **6 different winners** |

Six distinct "best" plans from the same six plans, with nothing changing but the order they arrive
in. That is what "cannot define an ordering" means in practice.

**Today's exposure is narrower than that.** `circulation_prefers` has exactly one production caller,
`general_pipeline._guard_demoted_hub`, which compares exactly **two** plans once. A set is never
ordered, so no cycle can fire. What *is* live is the non-antisymmetry: on roughly half of all pairs
both directions return `None`, and the guard's outcome is then decided purely by which plan is
passed as `current`. That is latent arbitrariness in shipped code, not a wrong plan today — and it
is the reason #142M kept this term out of its total order.

## 5. Which circulation properties are architecturally meaningful

| property | measured today | direction | verdict |
|---|---|---|---|
| circulation area | `area_m2` | none | A quantity, not a quality. Useful as the denominator-free version of `ratio`. |
| circulation ratio | `ratio` | **bounded, not monotone** | C26 bounds it above at 0.24. Nothing bounds it below, and nothing should rank on it: it is circulation area ÷ *plan* area, so a plan improves it by getting bigger. Zero dedicated circulation means private rooms are entered through other rooms — the defect the corrected proposer prompt exists to forbid. |
| corridor length | `longest_segment_m`, `total_length_m` | **bounded, not monotone** | C26 bounds the longest segment above at 20 m. A spine that spans the house's depth is the intended parti, not a defect. `total_length_m` is never read at all. |
| corridor width | `narrowest_width_m` | threshold | Higher is better only up to a code minimum; a threshold, not a ranking key. Never read. |
| dead ends | `dead_end_count` | **monotone, lower better** | An un-served corridor end is waste with no compensating benefit. The one term whose direction needs no judgement. |
| duplicated segments | `duplicated_segment_count`, `duplicated_area_m2` | **monotone, lower better** | Two corridors doing the same job. Measured, never read. |
| unnecessary branching / turns | `turn_count` | **none** | Production's own docstring already refuses to score it, correctly: fewer turns would bias the ranking back toward the straight spine the hub parti exists to move away from. |
| dead space | `dead_space.dead_space_m2` | monotone, lower better | A finer measure of the same waste `dead_end_count` reports as a boolean. Exists, exported, never wired. |
| path efficiency, entrance-to-room travel | not in this module | — | `entrance_sequence.distance_to_public_m` is the nearest existing measure. |
| privacy provided by circulation | not in this module | — | `wet_privacy` covers wet rooms only, and is empty on every band-pipeline plan (a known realizer gap, #142L §3). |

### Where more circulation is better — measured

Grouped by dead-end count, the plans that spend **more** on circulation are the ones whose corridor
reaches both ends:

| dead ends | historical plans / mean circulation area | corrected plans / mean circulation area |
|---:|---|---|
| 0 | 28 · **17.17 m²** | 62 · **16.28 m²** |
| 1 | 20 · 14.87 m² | 18 · 13.12 m² |
| 2 | 3 · 11.52 m² | 1 · 10.41 m² |

Monotone in both pools: stopping the corridor short is the cheapest way to spend less on
circulation, and it buys a dead end. Within a brief, the comparator prefers a plan **for its lower
ratio while that plan has strictly more dead ends** on 5 ordered pairs (historical) and 3
(corrected) — the rule contradicting itself on its own measures. The B09 figure shows it directly:
B09#1 has the smallest hall in the brief (7.8 m², ratio 0.085) and is the only one of the three
whose corridor dead-ends.

Lower ratio also buys a narrower corridor. By ratio quartile on the corrected pool, mean narrowest
width runs 2.87 → 2.93 → 3.01 → 3.17 m and mean circulation area 11.9 → 15.0 → 15.9 → 19.0 m². On
this pool the floor never binds (minimum 1.75 m), so that harm is latent rather than realised.

### What this pool cannot answer

Honest limits. Every one of the 132 plans enters **every** private room from a hall or circulation
room, and every plan has exactly **one** circulation room. So this pool contains no plan whose
zoning is worse for having less circulation, and none with a bedroom-wing spur whose extra arm could
be shown to buy separation. The non-monotonicity argument for `ratio` and `longest_segment_m` rests
on the structure and on production's own asymmetric bounds, not on a measured counterexample within
these two sets.

## 6. Audit — what already exists, and what is computed and never read

`CirculationMetrics` carries nine fields. All nine are serialised to the API by
`demo.contract._metrics_out`; **three** reach any decision:

| field | reaches a decision? | where |
|---|---|---|
| `ratio` | yes | C26 `classify_extreme` (upper bound 0.24); `circulation_prefers` |
| `longest_segment_m` | yes | C26 `classify_extreme` (upper bound 20 m); `circulation_prefers` |
| `dead_end_count` | yes | C26 `classify_extreme` (upper bound 2); `circulation_prefers`; `concept_compilers` imports the constant |
| `area_m2` | **no** | reported only |
| `total_length_m` | **no** | reported only |
| `narrowest_width_m` | **no** | reported only |
| `turn_count` | **no** | reported only — deliberately, see §5 |
| `duplicated_segment_count` | **no** | reported only |
| `duplicated_area_m2` | **no** | reported only |

No new measurement was invented for this investigation. `duplicated_segment_count` is the one
unused field a corrected formulation uses, and it is already computed on every plan.

## 7. Candidate formulations, compared

Every formulation below is weight-free except F3, which is included to be measured and rejected.

| | F0 current | F0b no `area` | F1 Pareto on the 3 | F2 Pareto on waste | F3 lexicographic | F4 bounds then waste |
|---|---|---|---|---|---|---|
| rule | better on ≥1 of 4 | better on ≥1 of 3 | no worse on any of the 3, better on ≥1 | same, on dead ends + duplicated segments | dead ends, then duplicated, then ratio | `classify_extreme` screen, then F2 |
| **antisymmetric** | 3/13 · 3/20 briefs | 9/13 · 16/20 | **all** | **all** | **all** | **all** |
| **transitive** | 8/13 · 10/20 briefs | 11/13 · 16/20 | **all** | **all** | **all** | **all** |
| ordered 3-cycles | 84 · 267 | 9 · 24 | **0 · 0** | **0 · 0** | 0 · 0 | 0 · 0 |
| comparable pairs | 52/63 · 115/143 | 50 · 112 | 45 · 97 | 24 · 27 | 63 · 143 | 24 · 27 |
| incomparable (ties) | 11 · 28 | 13 · 31 | 18 · 46 | **39 · 116** | 0 · 0 | 39 · 116 |
| briefs with a unique maximum | 2/13 · 4/20 | 7 · 14 | 8 · **15** | 0 · 2 | 13 · 20 | 0 · 2 |
| fold depends on arrival order | 11 · 16 briefs | 6 · 6 | 5 · 5 | 13 · 18 | **0 · 0** | 13 · 18 |

*(each cell is historical · corrected)*

**F3 is rejected on principle, not on its numbers.** A lexicographic order is the only one here that
always produces a unique winner, but precedence *is* a weight — an infinite one on its first term.
Nothing in this evidence justifies ranking dead ends infinitely above duplicated segments.

**F2 = F4 on every plan in both pools**, because C26 has already rejected every extreme plan before
validation. The bounds screen is therefore redundant *after* the validators, which is also the
cleanest proof that `ratio` and `longest_segment_m` have done their job by the time a plan is a
selection candidate.

**Note the trap in F1 and F2.** Both are proper strict partial orders, yet the greedy fold is still
arrival-order dependent on 5 and 18 briefs. A partial order with no unique maximum cannot be used in
production's "keep current, replace when preferred" pattern either. Any wiring must take the maximal
*set* and hand ties to the next term, never fold.

## 8. How often a corrected formulation would change selection

A weight-free formulation may override the current winner only when another plan **strictly
dominates** it. Against the two selections that matter — today's #142J gate (highest-scoring clean
candidate that passes) and #142M's recommended step (entrance rank, then that score):

| formulation | overrides today's gate | overrides #142M's step |
|---|---|---|
| F0 current | 10/13 · 17/20 | 10/13 · 17/20 |
| F1 Pareto on the three | 4/13 · 13/20 | 5/13 · 14/20 |
| **F2 Pareto on waste** | **3/13 · 1/20** | **2/13 · 1/20** |

The spread between F1 and F2 is the whole architectural question in one number. If a lower
circulation ratio and a shorter corridor are genuinely better, circulation overrides the selection
in most briefs; if they are bounds rather than goals — which §5 argues and C26 already assumes —
circulation has almost nothing to say, and says it on 1 brief in 20.

## 9. The stop rule applies

Circulation quality does contain competing objectives that cannot be reduced to one weight-free
ordering. Ratio trades against dead ends on more than half the pairs either can decide; length
trades against both; and two of the three have no defensible direction at all once production's own
upper bounds are satisfied. The correct result is the one the task anticipated:

> **Circulation should be exposed as several quality dimensions rather than used to select one
> winner.** The only ordering it can soundly contribute is Pareto dominance on dead ends and
> duplicated segments, which is transitive, antisymmetric, weight-free, and nearly always silent.

## 10. For the follow-up that fixes production

Stated, not done — this task does not modify production.

1. **The `area` disjunct is a bug**, not a design choice: it is absent from the function's own
   docstring, it is not a circulation measure, and it double-counts a quantity rule 2 already uses
   in the opposite direction. Removing it is a behaviour change at the one call site and needs its
   own measurement there.
2. **Make the shape honest.** The function is a veto, used once, on two plans. Either keep it as a
   veto and rename it so it is never reused as a preference, or replace it with Pareto dominance.
3. **Never fold.** Even the repaired partial orders are arrival-order dependent under
   "keep current, replace when preferred". Take the maximal set.
4. **Split `_EPS`.** One constant for a dimensionless ratio and a length in metres covers 16% of one
   range and 0.2% of the other.
5. **`ratio` is not a pure circulation measure** — it divides by plan area, so a bigger house scores
   better. `area_m2` is already measured and has no such confound.

## 11. Scope

No production file changed. No geometry, realizer or validator touched. No L-shapes. No weighted
score, no weights, no LLM judge, no ranking model, no brief special-cased: the same analysis ran
over both datasets and all 39 brief-dataset pairs with a PASS plan. Concept Engine v2 untouched.
The LLM judge was not used as ground truth and was not run.

**Artefacts.** `data/analysis.json` (every measurement, per brief and per formulation) ·
`data/circulation_values.json` (all 132 plans' circulation values and areas) · `figures/` (four
cycle sheets) · `backend/app/ai_harness/circulation_142n/` (pool, relation, formulations, zoning,
driver, renderer) · `backend/tests/ai_harness/test_circulation_142n.py` (17 tests pinning the
claims about production's comparator).

**Reproduce.**

```
PYTHONPATH=backend python -m app.ai_harness.circulation_142n.pool       /tmp/142n_pool.json
PYTHONPATH=backend python -m app.ai_harness.circulation_142n.experiment /tmp/142n_pool.json docs/reports/142n-circulation-preference/data/analysis.json
PYTHONPATH=backend python -m app.ai_harness.circulation_142n.renders    /tmp/142n_pool.json docs/reports/142n-circulation-preference/data/analysis.json docs/reports/142n-circulation-preference/figures
```
