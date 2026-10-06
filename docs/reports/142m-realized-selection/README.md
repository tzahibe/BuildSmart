# #142M — Realized-plan selection

**Main question.** Does realizing clean candidates first and ranking only validator-PASS geometry using
existing production architectural preferences give us a more defensible selection than the current
proposal-level heuristic, at an acceptable runtime cost?

**Answer: partly, and the evidence stops short of a full yes.** Realizing every critic-clean candidate
instead of stopping at the first is cheap and safe — p50 0.20 s per realization, worst 1.7 s, worst
brief 12.6 s, and validity is preserved at 20/20 on the corrected dataset and 19/20 on the historical
one. One part of the ranking is strictly defensible and strictly better: **production's own
`_entrance_rank` is the only term that improves the choice without a judgement call** — it changes the
winner in 4 of 20 briefs (corrected) and 2 of 20 (historical), and in **every single change it replaces
a living-room arrival with a hall arrival and never degrades one**. Everything below that term is
**not** settled by the evidence. Applied faithfully in production's own precedence, the chain orders on
**area fidelity, not architecture**: `area_delta_m2` decides 64% of all ordered pairs while
`composition_prefers`, `wet_privacy` and `master_suite` decide **zero**. Promoting the architectural
terms is equally weight-free, but it changes the winner in **half the briefs** and the evidence cannot
say which precedence is right. And one currently-wired production term, `circulation_prefers`, is
**demonstrably intransitive on real data** (84 and 267 ordered 3-cycles), so it cannot be part of any
total order at all.

So the recommendation is deliberately smaller than the experiment: **adopt realize-all + `_entrance_rank`
+ the existing score as tiebreak, and return the alternatives. Do not adopt a full preference chain.**

Experiment code is isolated in `backend/app/ai_harness/selection_142m/` and wired into nothing.

---

## 1. What was compared

**Old selection** — today's production gate (`proposal_selection.select_proposal`, #142J): order the
critic-clean candidates by the geometry-free proposal score and take the **first** that realizes and
validates. Equivalently, the highest-scoring clean candidate that passes.

**New selection** — this experiment: realize **every** clean candidate within a deterministic bounded
budget (`MAX_REALIZATIONS_PER_BRIEF = 12`; the batches hold 8–9, so nothing was truncated), keep every
validator-PASS plan, rank those with production's own preference logic, keep the rest as alternatives.

**The ranking chain**, in `general_pipeline.run_general`'s own precedence, with no weights and nothing
invented. Each production `*_prefers` function compares exactly one scalar and returns "why not"
otherwise, so ordering by those scalars in that precedence reproduces the same decisions while
guaranteeing a total order:

| # | term | production source | direction |
|---:|---|---|---|
| 1 | `entrance_rank` | `general_pipeline._entrance_rank` (0 = HALL/CIRCULATION, 1 = LIVING, 2 = other) | lower |
| 2 | `area_delta_m2` | `demo.service._nearest_primary` (delivered vs requested area) | lower |
| 3 | `distance_to_public_m` | `entrance_sequence.entrance_sequence_prefers` | lower |
| 4 | `composition_score` | `public_composition.composition_prefers` | lower |
| — | *circulation* | `circulation_metrics.circulation_prefers` | **pairwise only — see §5** |
| 5 | `wet_privacy_key` | `wet_privacy.candidate_privacy_key` | lower |
| 6 | `dead_space_m2` | `dead_space.dead_space_prefers` | lower |
| 7 | `wet_core_key` | `wet_core.candidate_wet_core_key` | lower |
| 8 | `suite_key` | `master_suite.candidate_suite_key` | lower |
| 9 | proposal heuristic | `topology_poc.critic.score_topology` — **final tiebreak only** | higher |
| 10 | candidate index | determinism | lower |

Terms 5–8 are preference keys production already owns and has **never wired to a caller** (#142L's
audit finding).

## 2. Results

| | historical (#151 dataset) | corrected (#142K dataset) |
|---|---:|---:|
| candidates | 162 | 162 |
| critic-clean | 59 | 100 |
| realizations attempted | 59 | 100 |
| validator-PASS plans | 51 | 81 |
| briefs with a PASS plan | **19 / 20** | **20 / 20** |
| briefs with more than one PASS plan | 13 | 20 |
| winner changed vs the old gate | 10 / 20 | 14 / 20 |
| deciding term for those changes | area 7, entrance rank 2, entrance sequence 1 | area 10, entrance rank 4 |
| alternatives retained (different / variant / near-duplicate) | 20 / 4 / 8 | 39 / 14 / 8 |

**Validity is preserved.** 20/20 on the corrected dataset. The historical dataset reaches 19/20 because
B12 has **no critic-clean candidate at all** — a property of that dataset, identical to #142J's finding,
not a regression of this selection.

Per-brief matrices for both datasets, including every plan's term values, are in
`data/selection_142m.json`; the two tables are reproduced in `data/per_brief_tables.md`.

## 3. Runtime — clearly acceptable

| | per realization | per brief |
|---|---|---|
| historical | p50 0.243 s · p95 1.361 s · worst 1.538 s · 21.0 s total | p50 2.23 s · p95 6.93 s · worst 12.57 s |
| corrected | p50 0.198 s · p95 1.439 s · worst 1.683 s · 33.5 s total | p50 2.67 s · p95 9.98 s · worst 10.70 s |

Realizing **all** clean candidates rather than stopping at the first costs a few seconds per brief and
is bounded by construction. Runtime is not the obstacle.

## 4. The honest problem: the chain orders on area, not architecture

Across every ordered pair of PASS plans, which term **first separates** them:

| term | historical (63 pairs) | corrected (143 pairs) |
|---|---:|---:|
| `area_delta_m2` | **40 (63%)** | **91 (64%)** |
| proposal heuristic (last tiebreak) | 7 | 18 |
| `dead_space_m2` | 7 | 9 |
| `entrance_rank` | 3 | 19 |
| `distance_to_public_m` | 5 | 2 |
| `wet_core_key` | 0 | 2 |
| `composition_score` | **0** | **0** |
| `wet_privacy_key` | **0** | **0** |
| `suite_key` | **0** | **0** |

`composition_prefers` was consulted on 15 and 31 pairs and decided none of them. Wet privacy and the
master suite likewise never decided anything.

**Why.** Production's chain was calibrated for a candidate source where area proximity *ties often* —
the generator emits candidates at discrete area targets, which is exactly why `entrance_sequence_prefers`
and `composition_prefers` were written to act only "on exact ties". Band-pipeline proposals come from a
continuous solver whose delivered area essentially never ties, so the architectural tiebreaks are never
reached. The chain is faithful; the candidate source is different.

**What happens if the architectural terms are given the chance.** Two equally weight-free variants, same
terms, different precedence:

| variant | architectural terms decide | winner changed | agrees with V1 on the winner |
|---|---:|---:|---|
| **V1** faithful (area above the architectural tiebreaks) | 12/63 · 13/143 | 10/20 · 14/20 | — |
| **V2** architectural terms above area | 52/63 · 101/143 | 9/20 · 14/20 | 12/19 · 10/20 briefs |
| **V3** area removed entirely | 52/63 · 101/143 | 9/20 · 14/20 | 12/19 · 10/20 briefs |

So the precedence choice changes the winner in **7 of 19 and 10 of 20 briefs**. V1 is faithful to
production; V2 and V3 are no less principled. **Nothing in this experiment can decide between them** —
that is a product judgement about whether delivering the requested area outranks architectural quality,
and it is precisely the kind of call #142L showed we have no client-priority data to make. Note also
that when the architectural terms do get the chance, the one that dominates is `dead_space_m2`, whose
own production docstring says it is deliberately **not wired** and that wiring it as an active ranking
term needs a corpus sweep first.

## 5. A measured defect: `circulation_prefers` cannot be part of a total order

Every other production preference compares one scalar. `circulation_prefers` prefers a candidate that is
better on **at least one of** ratio, longest segment or dead ends while keeping 85% of the area. "Better
on at least one of three" is not transitive, so it was applied pairwise only, exactly where production
applies it, and tested:

| dataset | ordered 3-cycles found among PASS plans |
|---|---:|
| historical | **84** |
| corrected | **267** |

Those are ordered triples, so roughly 28 and 89 distinct cycles. **A term with cycles cannot order a set
of plans**, whichever direction you sort. It is currently wired into `general_pipeline` as a ranking
term (via `_guard_demoted_hub`), where it only ever compares two plans at a time and so the cycles are
invisible. This is a real finding about existing production code and deserves its own follow-up; it is
not something #142M should fix.

## 6. Alternatives are real

Classified with #142L's own diversity measure, against the chosen winner:

| | different concept | variant | near-duplicate |
|---|---:|---:|---:|
| historical | 20 | 4 | 8 |
| corrected | **39** | 14 | 8 |

So retaining the other PASS plans gives genuinely different alternatives in both datasets, not
permutations — the product shape "here are three valid alternatives" is supported by the data.

## 7. The recommended smallest productionization step

> **In `proposal_selection.select_proposal`: realize every critic-clean candidate within the existing
> bounded budget instead of returning at the first PASS; order the PASS plans by
> `general_pipeline._entrance_rank` and then by the existing proposal score; return the best plan plus
> the remaining PASS plans as alternatives.**

Why exactly this and nothing more:

- **It is strictly dominant.** On the corrected dataset it changes the winner in 4 of 20 briefs and on
  the historical in 2 of 20; **in every one of those changes the entrance rank improves** (living-room
  arrival → hall arrival) and **in none does it worsen**. Every other brief keeps today's plan, because
  the existing score still decides below the entrance term.
- **`_entrance_rank` is production's own highest-precedence rule**, strict, transitive, and already
  governs the general pipeline. It is also the one thing the old proposal score provably cannot express:
  #142L measured its entrance term as having zero within-brief variation, because the corpus prior gives
  the living room 0.99 and every other role 0.0.
- **It adds no weights and no new score**, and keeps the old heuristic for everything the evidence does
  not settle.
- **It is cheap**: a few seconds per brief, bounded, deterministic.
- **It unlocks the alternatives** at no extra cost, since all candidates are realized anyway.

Explicitly **not** recommended on this evidence: adopting the full chain (area versus architectural
precedence is an unsettled product judgement that moves the winner in half the briefs); wiring
`dead_space_prefers` (its own docstring asks for a corpus sweep first, and it would become the dominant
term); and any use of `circulation_prefers` as an ordering key (it cycles).

Two findings worth separate tasks: `circulation_prefers`'s intransitivity in currently-wired production
code, and the fact that production's tie-based tiebreaks never fire on a continuous candidate source.

## 8. Scope kept

No geometry, realizer or validator changed. No L-shapes. No new weighted quality score and no arbitrary
weights — every term is an existing production preference used in its own published direction. No LLM
judge. No ranking model. Concept Engine v2 untouched and still `CONCEPT_ENGINE_V2_ENABLED = False`. No
brief special-cased: the same chain ran over both datasets and all 40 brief-dataset pairs.

**Artefacts.** `data/selection_142m.json` (both datasets: per-brief rows, per-plan term values, deciding
terms, quality-vector differences, alternatives, circulation cycles, runtimes) ·
`data/per_brief_tables.md` (the two matrices) · `backend/app/ai_harness/selection_142m/` (ranking chain
and experiment driver).
