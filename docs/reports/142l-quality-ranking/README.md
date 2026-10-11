# #142L — Architectural quality ranking investigation

**Final question.** Now that BuildSmart can produce valid plans reliably, what measurable properties
actually distinguish a merely valid floor plan from a good architectural floor plan, and what is the
smallest evidence-backed change that would let production choose better plans without encoding
arbitrary taste?

**Answer, in one paragraph.** Validity has already eaten most of the easy quality signal: of 67
measured properties, 12 are *constant* across all 81 valid plans because the validators and the critic
already force them to their good value, so they cannot rank anything. Among the properties that do
vary, **no plan Pareto-dominates another — 0 of 143 pairs on raw metrics, 2 of 143 at dimension
level** — so there is no weight-free winner and 141 of 143 pairs are genuine trade-offs. An independent
architectural judge was run as the external check and **is not reliable enough to serve as ground
truth**: it names the same physical plan only 65% of the time when A and B are swapped, so only 15 of
30 pairs survive, and at that sample size no metric's agreement is distinguishable from chance. Two
things are nevertheless solid. First, **the current production heuristic is at chance (0.50, n=14)
against the judge and is demonstrably broken in a way that does not need the judge to show**: it is
scored before any geometry exists, its entrance term has *zero variation* within every brief, and it is
anti-correlated with zoning and exposure. Second, **one sentence added to the proposer prompt removed
the entire remaining validity failure mode** — on the six worst briefs, critic-clean proposals went
22/48 → 49/49 with zero new failure modes. The smallest evidence-backed production change is therefore
**not** a quality score: it is to stop ranking valid plans by a geometry-free score that measures
nothing, and to rank them instead by production's own already-merged realized-geometry preferences,
while surfacing the trade-off vector rather than collapsing it.

Everything below is measured. Experiment code is isolated in
`backend/app/ai_harness/quality_142l/` and is wired into nothing.

---

## 1. The baseline pool (task §1)

Same candidate pool as #142K — nothing regenerated for the ranking work.

| | |
|---|---:|
| proposals in the #142K corrected-prompt dataset | 162 |
| critic-clean | 100 |
| realized and passing the unchanged validators | **81** |
| briefs | 20 |
| valid alternatives per brief | min 2, max 6, mean 4.05 |
| comparable pairs | 143 |

Every brief has at least two valid alternatives, so the ranking question is live for all 20.
`data/baseline_pool.json` carries each plan's full realized geometry in metres plus the output of every
production quality module. Per-brief counts and the heuristic's own ordering are in the same file.

## 2. The quality taxonomy and the evaluator (task §2, §4)

`quality_142l/metrics.py` — **67 metrics across the 10 dimensions the task names**, each registered
with definition, inputs, unit, direction, architectural rationale, limitations and availability.
38 are `PRODUCTION` (this evaluator reads production's own number) and 29 are `DERIVED` (new here, from
existing data). 4 are deliberately `info`: reported, never ranked, because "lower is better" would be a
taste claim — `circulation_ratio`, `corridor_min_clear_m`, `entrance_to_bedroom_steps`,
`street_facade_public_share`.

| dimension | metrics | the ones that carry the dimension |
|---|---:|---|
| circulation_efficiency | 10 | production's ratio, longest segment, dead ends, turns, duplicated area, dead-space share; derived rooms-served, steps and walk from the entrance |
| public_private_separation | 6 | public/private shared wall and its share, bedrooms reachable only through the public zone, public and private component counts, front-to-back zone overlap |
| privacy | 8 | production's wet-room entered-from class, sight lines and privacy score; the master suite's sight line to bed and suite score; bedroom doors off public/arrival |
| entrance_quality | 6 | production's arrival class, pocket length, distance to public, private doors passed; derived fanout and steps to living |
| public_zone_quality | 7 | production's coherence, kitchen-dining relation, living exposure; derived cluster share, narrowest neck, compactness, worst aspect |
| bedroom_quality | 9 | production's bedroom/master aspect gates; derived min area, min short side, area consistency, master hierarchy, public wall, windows, entry class |
| wet_core_quality | 6 | production's plumbing complexity, shared wet wall, cluster count, wet adjacency share; derived window share and ensuite-to-host adjacency |
| exposure_quality | 7 | production's two-sided share; derived preferred-exposure satisfaction, facade shares, monopolisation, windowless rooms |
| proportion_quality | 6 | production's mean/max/worst-wet aspect, min short side, furniture fit; derived sliver count |
| soft_adjacency_quality | 2 | measured ResPlan adjacency lift over realized contacts, plus its own coverage term |

## 3. Audit: most of this already exists (task §3)

The repository already measures architectural quality on realized geometry far more than the product
uses. The evaluator reads these rather than inventing second definitions:

| module | measures | wired into production? |
|---|---|---|
| `circulation_metrics` | area, ratio, longest segment, narrowest width, dead ends, turns, duplicated segments | yes — C26 gate and `circulation_prefers` ranking |
| `entrance_sequence` | arrival zone/class, pocket length, distance to public, private doors passed, foyer, stray pockets | yes — C25 gate and `entrance_sequence_prefers` ranking |
| `dead_space` | STUB / SLIVER / CORNER / OVERSIZED_HALL regions, m² and share | partly — surfaced as a notice; `dead_space_prefers` **unwired** |
| `public_composition` | kitchen-dining and dining-living relation, zone coherence, living exposure | yes — C31 gate and `composition_prefers` |
| `wet_privacy` | per wet room: entered-from class, door facing, sight line, exposure and privacy score | yes — C29 gate; `candidate_privacy_key` used only in the L-massing tiebreak |
| `wet_core` | shared wet wall, clusters, plumbing complexity index | measured and surfaced; `candidate_wet_core_key` **has no caller** |
| `master_suite` | sight line to bed, sight line to ensuite door, routes crossing the bed, suite score | **no caller at all** — computed by nothing in production |
| `hub_guard`, `l_massing_guard` | bedroom/master/safe-room aspects, worst wet aspect, two-sided exposure, wet adjacency | yes — massing guards |

**Finding.** The gap is not measurement, it is *application*. Three of the most architecturally
pointed measures the codebase owns — the master suite's sight lines, the wet-core plumbing key and the
dead-space preference — are computed or computable and ranked on by nothing.

**MISSING INFORMATION (8 items, never faked).** Recorded in `metrics.MISSING_INFORMATION`:
sight lines for secondary bedrooms and public rooms (they exist only for wet rooms and the master);
**client priorities** (no brief field says whether this client values privacy over openness — the reason
no cross-dimension weighting can be justified); a **PREFERRED-adjacency channel** (the proposal schema
has one HARD `spatial_adjacency` list, so a proposer cannot state a soft preference, and the measured
priors cover only 5 roles and describe apartments); orientation, noise and views (the street side is
known but no room carries a solar or view requirement); furniture layout quality (C30 is fully defined
but not called by `validate` because it was measured to fail on real valid plans); circulation route
geometry (no route polyline, so walking distance is a Manhattan proxy); acoustic and thermal properties;
and area fidelity against what the person asked for (rubric section B has no signal merged at all).

## 4. Can one plan dominate another without weights? (task §5, §6)

| | result |
|---|---|
| **Pareto dominance, raw metrics (49 ranked)** | **0 of 143 pairs** |
| Pareto dominance, dimension level | 2 of 143 pairs |
| CLEAR / NEAR_CLEAR / TRADE_OFF | 0 / 2 / 141 |
| metrics that never vary inside any brief | **12 of 67** |
| weighting scenarios agreeing with equal weights | privacy-led 88%, openness-led 89%, efficiency-led 91%, bedroom-led 90% |
| briefs where all 5 scenarios pick the same plan | 10 of 20 (2 winners in 8 briefs, 3 in 2 briefs) |

**The 12 constant metrics are the headline of this section**, and they are exactly the ones HARD
validity already owns: every plan has zero bathroom doors onto public rooms, zero wet sight lines, an
identical worst wet-privacy score, a coherent public zone, an exposed living room, a window in every
bedroom, every bedroom entered from circulation, every ensuite adjacent to its host, no slivers and
full furniture fit. The task's own instruction — that HARD validity "should generally NOT dominate
quality ranking once all compared plans already PASS" — turns out to be empirically self-enforcing:
those dimensions are saturated and carry no ranking information at all.

What is left genuinely trades off. The most discriminating metrics are public-zone compactness (decides
86% of pairs), facade allocation (85%), walking distance (84%), public/private wall share (83%) and room
proportion (83%).

Figures: `figures/B*_c*_vs_c*.png` — 30 side-by-side comparison sheets, each captioned with the metric
split, the Pareto verdict and which plan the production heuristic preferred.

## 5. The independent judge, and why it is not ground truth (task §7)

100 judgements over 30 pairs, gpt-5 plus gpt-5-mini, $3.85, 0 failures. The judge saw only the brief and
two blind-rendered plans, never a candidate index, a score or production's choice.

| control | result | 95% CI |
|---|---|---|
| **order** — same physical plan with A and B swapped | **15 / 23 decided = 0.65** | 0.45 – 0.81 |
| repeat — identical call twice | 7 / 10 = 0.70 | 0.40 – 0.89 |
| config — drawings alone vs drawings + room schedule | 12 / 15 = 0.80 | 0.55 – 0.93 |
| cross-model — gpt-5 vs gpt-5-mini | 11 / 15 = 0.73 | 0.48 – 0.89 |

Choice distribution over all runs: A 38, B 53, EQUIVALENT 9, mean confidence 3.9/5.

**At 65% order consistency the judge is barely above the 50% floor of a binary choice.** Only 15 of 30
pairs are both decided and order-consistent, so every agreement number below rests on n = 8–13 and has a
confidence interval roughly ±0.25 wide. To show that an agreement of 0.75 is above chance would need at
least 16 order-consistent pairs; 0.70 would need 24; 0.65 would need 41. **This experiment does not have
the statistical power to validate a ranking rule, and no metric was tuned to agree with the judge.**

## 6. Metrics versus the judge (task §8)

Nothing predicts the judge's *overall* verdict above chance once intervals are honest:

| predictor | agreement | n | 95% CI |
|---|---:|---:|---|
| production heuristic (today's selector) | **0.50** | 14 | 0.27 – 0.73 |
| best single dimension (soft adjacency) | 0.62 | 13 | — |
| privacy dimension | 0.63 | 8 | — |
| equal-weight quality score | 0.33 | 12 | — |
| dimension-level Pareto dominance | — | 0 | never fired |

But the judge's *per-category* verdicts line up with the matching dimension far better than its overall
choice does:

| judge category | agreement with the matching dimension | n | 95% CI |
|---|---:|---:|---|
| **circulation** | **0.82** | 11 | **0.52 – 0.95** (excludes chance) |
| zoning and privacy | 0.70 | 10 | 0.40 – 0.89 |
| room proportion | 0.70 | 10 | 0.40 – 0.89 |
| bedrooms | 0.64 | 11 | 0.35 – 0.85 |
| wet rooms | 0.56 | 9 | 0.27 – 0.81 |
| public space | 0.33 | 12 | 0.14 – 0.61 |
| daylight and exposure | 0.20 | 10 | 0.06 – 0.51 |
| entrance | 0.20 | 5 | 0.04 – 0.62 |

**Reading.** The metrics capture what an architect sees *within* a category — circulation most clearly.
What they cannot do is reproduce how the architect *aggregates* categories into one verdict. That is the
same gap as the missing client priorities, seen from the other side.

**Three metrics are statistically anti-correlated with the judge** (CI excludes 0.5), which matters more
than the weak positives:

| metric | agreement | n | 95% CI |
|---|---:|---:|---|
| `public_private_wall_m` | 0.09 | 11 | 0.02 – 0.38 |
| `bedroom_public_wall_m` | 0.09 | 11 | 0.02 – 0.38 |
| `public_private_wall_share` | 0.17 | 12 | 0.05 – 0.45 |

In 10 of 11 pairs the judge preferred the plan with **more** shared wall between the living core and the
bedrooms. The most plausible reading, visible in the figures: penalising that wall penalises compactness,
and a compact plan with a coherent public zone reads better than a loosely packed one with long buffers.
**Shared-wall length is the wrong proxy for zoning quality** and should not be carried forward as written.
`two_sided_exposure_share` (0.20, n=10) is similarly suspect.

## 7. Why the current heuristic chooses weaker plans (task §9)

The selector is `topology_poc.critic.score_topology`, a geometry-free score over the proposal graph:
`adjacency_similarity + access_similarity + wet_core_similarity + entrance_relation_score − 10 × violations`.

| failure mode | evidence |
|---|---|
| **SCORED_BEFORE_REALIZATION** | the score sees no geometry at all, so corridor length, room shape, facade allocation and every realized property are invisible to it. It agrees with the judge at exactly chance (0.50, n=14) and picks the same plan as an equal-weight quality score in only **6 of 20 briefs**. |
| **INERT TERM** | `entrance_relation_score` has **zero within-brief variation in all 12 briefs where it is defined**. The ResPlan `front_door_direct_access` prior gives LIVING 0.9916 and *every other role 0.0*; HALL is not even a measurable role in that corpus. The term therefore cannot express a preference for a hall entrance, and never breaks a tie. |
| **ANTI-CORRELATED** | against realized quality the total score disagrees with `private_components` (0.16 — in 84% of decided pairs it prefers the more fragmented sleeping zone), with `arrival_is_circulation` (0.21) and with the exposure metrics (0.31). |
| **NOISE** | `adjacency_similarity` agrees with "less public/private wall" 0.51 of the time — pure noise on zoning. |
| **CORPUS MISMATCH** | the priors are measured on ResPlan **apartments**. BEDROOM–LIVING *touching* has lift 1.886 (near-universal in a flat) while the ACCESS table gives a BEDROOM–LIVING *door* lift 0.00024. The two tables disagree about the same pair, and the adjacency half rewards exactly the arrangement a detached house with a hall should avoid. |
| **DOUBLE COUNTING / PROXY** | `wet_core_similarity` reads the proposal's own declared `clusters["wet_core"]` field, not geometry: it scores what the model *said*, not what gets built. |

**A structural finding that is not the heuristic's fault.** The hall sits in the street band in only
**7 of 81 plans**, and in every one of those 7 the entrance uses it. In the other 74 the hall is a middle
band and arrival falls to the living room. Entrance quality is therefore decided almost entirely by
whether the proposal happens to put circulation against the street — `resolve_entrance` is already doing
the right thing with what it is given.

## 8. Diversity: are the alternatives real? (task §11)

| | pairs |
|---|---:|
| DIFFERENT_CONCEPT (contact-set Jaccard ≥ 0.5 or ≥ half the rooms change band) | **80** |
| VARIANT | 39 |
| MINOR_PERMUTATION | 24 |

The alternatives are mostly genuinely different ideas, not permutations — so "best N diverse plans" is a
viable product shape, not a fiction. The exception is instructive: **B03's four valid plans have zero
varying metrics** — four distinct proposals that realize to the same plan. A future selection step should
deduplicate on realized geometry, not on the proposal graph.

## 9. Can the vector explain options to a person? (task §12)

Partly, and the evidence sets the boundary. In **10 of 20 briefs all five weighting scenarios pick the
same plan**, so there is nothing to explain — one plan is simply the sensible choice. In the other 10 the
scenarios split (2 distinct winners in 8 briefs, 3 in 2 briefs), and the dimension vector does name why:
privacy-led, openness-led, efficiency-led and bedroom-led winners are recorded per brief in
`data/comparison.json`. So "Option A prioritises privacy, Option B open public space" is expressible
today for half the briefs. What is *not* available is any basis for ordering those options for a given
client — that is the missing `client_priorities` intent.

## 10. The private-room prompt clarification (task §10) — kept separate

The rule is unambiguously existing policy: `access_rules.ALLOWED_ENTERED_FROM` maps every role in
`PRIVATE_ROLES` (bedroom, master bedroom, safe room, study, dressing room) to `CIRCULATION_ROLES` only,
and C24 plus the production critic already fail closed on it. The prompt simply never said so. One
sentence was added:

> PRIVATE ROOMS: a bedroom, master bedroom, safe room, study or dressing room is entered ONLY from a hall
> or circulation space — never from the living room, the kitchen, the dining room, or another bedroom.

Controlled sample: the six briefs with the most `ILLEGAL_ACCESS_PAIR` findings in #142K, regenerated once
($0.88).

| | before (#142K) | after |
|---|---:|---:|
| candidates | 48 | 49 |
| critic-clean | 22 (45.8%) | **49 (100%)** |
| proposals with an illegal access pair | 26 | **0** |
| clean and passing production | 18 | **42** |
| new failure modes | — | **none** |

`UNREACHABLE_ROOM` disappeared with it, confirming #142K's reading that it was a consequence of the same
illegal door. One honest caveat: B18 went from 3 to 2 clean-and-passing plans — more proposals were clean
but one fewer survived band sizing, which is a geometry limit, not a new critic failure.

## 11. Answers to the eight success criteria (task §13)

1. **Measurable reliably today:** circulation (production's own module, and the only category whose
   agreement with an architect excludes chance), room proportion, bedroom size and shape, wet-core
   plumbing and clustering, dead space, entrance arrival class and pocket, exposure satisfaction.
2. **Needs missing intent/data:** the 8 items in §3 — above all client priorities, a preferred-adjacency
   channel, and sight lines outside wet rooms and the master.
3. **Actually distinguishes valid plans:** public-zone compactness, facade allocation, walking distance,
   room proportion and public/private wall share decide 83–86% of pairs; 12 metrics decide nothing at all.
4. **Dominance without weights:** essentially never — 0 of 143 raw, 2 of 143 at dimension level.
5. **Agreement with an independent judge:** not establishable at this power. The judge is 65%
   self-consistent; per-category agreement reaches 0.82 for circulation, but no overall predictor beats
   chance, and three zoning/exposure metrics are significantly *anti*-correlated.
6. **Why the heuristic picks weaker plans:** it is scored before geometry exists, one term is provably
   inert, another is noise on zoning, and its priors come from apartments. Chance-level against the judge,
   6/20 agreement with an equal-weight quality score.
7. **Are the alternatives diverse:** yes — 80 of 143 pairs are different concepts.
8. **Minimum justified production change:** §12.

## 12. The one recommended bounded production step

> **Stop ranking critic-clean candidates by the geometry-free proposal score. Realize them all, then
> order them with production's own already-merged realized-geometry preference chain — `_entrance_rank`,
> `entrance_sequence_prefers`, `circulation_prefers`, `composition_prefers` — keeping the proposal score
> only as a last tiebreak, and return the whole passing set with its quality vector instead of silently
> discarding it.**

Why this and nothing larger:

- It **removes** a signal measured to be at chance against an architect, with an inert entrance term and
  an anti-correlated zoning term. That removal is justified by this report alone.
- It **adds no new weights and no new policy**: every function in that chain is already merged, already
  owner-approved, and already ranks delivered plans in `general_pipeline`. The one category where metrics
  and an architect demonstrably agree — circulation — is exactly what `circulation_prefers` ranks on.
- It **does not** claim a quality score. Building one now would mean choosing cross-dimension weights
  that this experiment showed cannot be justified: no dominance, no reliable judge, no client priorities.
- Returning the set rather than one plan is what makes the later product behaviour ("three valid
  alternatives") possible, and §8 shows the alternatives are genuinely different.

Explicitly **not** recommended yet: a weighted quality score; an LLM judge anywhere near production;
carrying `public_private_wall_m` forward as a zoning metric (it is anti-correlated); and any ranking
claim resting on the n = 15 judge subset.

Two findings worth their own future tasks, not folded in here: the hall reaches the street band in only
7 of 81 plans, which caps entrance quality structurally; and `master_suite`, `wet_core`'s ranking key and
`dead_space_prefers` are computed but wired to nothing.

## 13. Scope kept

No geometry, realizer, embedder or validator was modified. No arbitrary production weights, no ranking
model, no fine-tuning, no LLM in production, no frozen brief special-cased, no metric tuned to agree
with the judge, no UI. The only production-path edit is the single prompt sentence in §10, which states
an existing rule. Everything else lives in `backend/app/ai_harness/quality_142l/` and is called by
nothing.

**Artefacts.** `data/baseline_pool.json` (81 plans with full realized geometry and every production
quality record) · `data/comparison.json` (vectors, dimensions, scenarios, Pareto, diversity, 143 pairs) ·
`data/judgements.json` (100 judgements with controls) · `data/agreement.json` (consistency and agreement)
· `data/heuristic_analysis.json` (score decomposition per plan and pair) · `data/prompt_experiment.json`
(§10) · `figures/` (30 captioned comparison sheets).
