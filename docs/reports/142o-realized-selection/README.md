# #142O — Realized-plan selection, productionized

The narrow, evidence-backed step #142M recommended, implemented in production and verified against
the measurement that justified it.

**What changed.** `proposal_selection.select_proposal` no longer returns at the first candidate that
validates. It realizes every critic-clean candidate inside the **same, unchanged** budget, keeps
every validator-PASS plan, and picks the winner by

| # | term | source | direction |
|---:|---|---|---|
| 1 | arrival rank | `arrival_policy.arrival_rank` — 0 hall/circulation, 1 living, 2 other | lower |
| 2 | proposal score | the existing geometry-free heuristic | higher |
| 3 | candidate index | stable identity | lower |

The remaining PASS plans are returned as `alternatives`. Only term 1 is new. No weights, no new
score, no geometry or validator change.

**Result, from the shipped function at its production default:**

| | historical (#151) | corrected (#142K) |
|---|---:|---:|
| briefs with a PASS plan | 19 / 20 | **20 / 20** |
| PASS plans kept | 51 | 81 |
| alternatives retained | 32 | 61 |
| winner changed vs the old rule | **2** | **4** |
| entrance improved / degraded | **2 / 0** | **4 / 0** |
| seconds per brief, p50 · worst | 1.76 · 10.06 | 2.11 · 8.41 |

Every changed brief moved a living-room arrival to a hall arrival. None moved the other way.
Changed briefs: B05 and B08 (historical), B01, B02, B05 and B20 (corrected).

---

## 1. The gating measurement came first

The instruction was not to raise `max_realizations` arbitrarily, so the first question was whether
the existing budget could reproduce #142M at all.

**Two nested budgets share the name, and only the outer one was ever at issue.**

| | what it bounds | default | changed? |
|---|---|---|---|
| `select_proposal(max_realizations=...)` | how many critic-clean **proposals** are pushed through the pipeline | **`None` — unbounded** (`ordered[: max_realizations or len(ordered)]`) | no |
| `run_band_pipeline(max_realizations=...)` | how many **band layouts of one proposal** are realized | 150 | no |

So the production default was already unbounded, and the early `return` — not the budget — was what
stopped the loop. **Realizing every clean candidate is not a budget increase.** It is the removal of
an early return inside a budget that never bound anything. Measured: at the default, truncation is
**0 clean candidates in 0 briefs** on both datasets, and the reproduction is exact.

The cost is real and is the honest reason the measurement was needed. Per-brief work rises from
"candidates until the first PASS" to "every clean candidate" — 59 and 100 realizations across the two
datasets, at a measured p50 of 0.19 s and 0.16 s each. In wall-clock, the selection loop over the
whole dataset goes from 6.5 s to 16.4 s (historical) and from 7.2 s to 26.6 s (corrected): about
2.5x and 3.7x, for a bounded few seconds per brief.

## 2. What a cap would cost, if one is ever wanted

Measured so the default can be revisited with data rather than a guess. **No cap is proposed.**

**Corrected dataset** (20 briefs, 100 clean candidates):

| budget | briefs with a PASS | alternatives | winner changes | clean truncated | total s | worst brief s |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | **18** | 0 | 0 | 80 | 5.4 | 1.31 |
| 2 | **19** | 14 | 1 | 60 | 10.1 | 1.57 |
| 3 | 20 | 30 | 1 | 41 | 16.4 | 1.91 |
| 4 | 20 | 43 | 3 | 22 | 21.7 | 2.94 |
| 5 | 20 | 55 | **4** | 9 | 24.9 | 3.38 |
| 6 | 20 | **61** | **4** | 1 | 26.1 | 3.53 |
| **None** | **20** | **61** | **4** | **0** | 26.6 | 4.07 |

**Historical dataset** (19 briefs with a clean candidate, 59 clean):

| budget | briefs with a PASS | alternatives | winner changes | clean truncated | total s |
|---:|---:|---:|---:|---:|---:|
| 1 | 19 | 0 | 0 | 40 | 6.5 |
| 3 | 19 | 21 | **2** | 12 | 14.3 |
| 5 | 19 | 31 | **2** | 1 | 16.4 |
| **None** | **19** | **32** | **2** | **0** | 16.4 |

Three things the table settles:

- **A cap below 3 loses validity outright.** At a budget of 1 only 18 of 20 corrected briefs produce
  any plan at all, and at 2 only 19. Today's gate already needs up to 3 attempts for full coverage,
  so a small cap would be a regression against current production, not a saving.
- **The winner changes are not cheap to reach.** All 4 corrected changes need a budget of 5; at 4
  only 3 of them appear, and at 3 only 1.
- **Alternatives keep accruing to the end.** 61 at budget 6 and at the default, 55 at 5, 43 at 4.

Since the default already costs a bounded few seconds per brief and truncates nothing, there is no
evidence for introducing a cap and none is introduced.

## 3. One definition of the arrival rank

The rule previously lived in `general_pipeline._entrance_rank`, which only the general pipeline could
reach. It now lives in a new `arrival_policy.py` and `_entrance_rank` delegates to it: identical
behaviour, one definition, reachable from both selection paths — the same single-source discipline
`wet_room_policy.py` exists for. A test asserts the two agree on every arrival class, so they cannot
drift.

It deliberately does **not** live in `entrance_sequence.py`, which was the first and more obvious
home. That module is barred from branching on a role name by its own guard test
(`test_no_coordinate_literal_or_fixture_name_branch_in_the_module`, which bans the literal
`"LIVING"` among others), and naming the living room is the entire content of this policy. The guard
caught the first attempt; a separate policy module is the right answer rather than a weakened guard.

## 4. Circulation is carried, never ranked

Each `PlanOption` carries its plan's `CirculationMetrics` so a caller can explain how two
alternatives differ. It is deliberately absent from `sort_key`. #142N measured
`circulation_metrics.circulation_prefers` to be non-transitive **and not even antisymmetric** — on
roughly half of all pairs each plan beats the other — so it cannot order a set of plans at all.
`circulation_prefers` and `_guard_demoted_hub` are untouched by this task.

## 5. Verification

- **The shipped function reproduces the measurement exactly.** `selection_142o.verify` calls the
  production entry point at its production default and compares six totals per dataset against the
  budget measurement: all 12 agree (`shipped_matches_measurement: true`).
- **It reproduces #142M**, which reported 4/20 and 2/20 winner changes with the entrance improving in
  every one and degrading in none.
- **#142J's guarantees still hold**, re-run on the frozen dataset: at least 19 of 20 briefs select an
  existing clean passing proposal, B12 still fails honestly with `NO_VALID_PROPOSAL`, a HARD-invalid
  candidate never wins, the former representation-limit briefs still pass, and selection is still
  deterministic across processes and `PYTHONHASHSEED` values.

Two #142J tests encoded the rule this task supersedes — "the winner is always the top-scored clean
candidate". They now assert the rule that actually holds (the winner is the minimum of arrival rank,
then score, then index, over the real options) plus the stronger property that matters: the winner's
arrival is never worse than what the old rule would have returned. The two briefs whose winner moves
are named and required to move to a hall arrival.

## 6. Scope

No geometry change, no realizer change, no validator change. No L-shapes. No new weighted score and
no arbitrary weights. No LLM judge. No ranking model. No brief special-cased. Concept Engine v2
untouched and still `CONCEPT_ENGINE_V2_ENABLED = False`. `circulation_prefers` and
`_guard_demoted_hub` unmodified — #142N's follow-up remains a separate future task.

**Production files changed:** `proposal_selection.py` (the loop, `PlanOption`, `alternatives`),
`arrival_policy.py` (new — the arrival rank), `general_pipeline.py` (`_entrance_rank` delegates).

**Artefacts.** `data/budget_measurement.json` (every budget, per brief, both datasets) ·
`data/shipped_verification.json` (the shipped function vs the measurement) ·
`backend/app/ai_harness/selection_142o/` (measurement and verification drivers) ·
`backend/tests/vertical_slice/test_realized_selection_142o.py` (16 tests on the rule and the budget).

**Reproduce.**

```
PYTHONPATH=backend python -m app.ai_harness.selection_142o.budget docs/reports/142o-realized-selection/data/budget_measurement.json
PYTHONPATH=backend python -m app.ai_harness.selection_142o.verify docs/reports/142o-realized-selection/data/budget_measurement.json docs/reports/142o-realized-selection/data/shipped_verification.json
```
