# BUILT_AREA_TARGET_FIX_REPORT

```
STATUS  = DONE
TESTS   = 684 passed (675 before, +9 new)
OUTCOME = generated built area now tracks the requested target
          median gap  -37.0%  ->  -2.7%
```

The objective implemented is **track the target**, not maximise. A proportion 5 m² over the target
is preferred to one 40 m² under it, and the search stops at the closest feasible concept — not the
largest.

---

## 8 · Results

### 2BR + 1 wet + open plan — programme capacity 213.3 m²

| requested | footprint | gross | net | gap | unused | room areas |
|---|---|---|---|---|---|---|
| 120 | 10.95×10.95 = 119.9 | — | — | — | — | **PLAN_FAILED_VALIDATION** (C11, pre-existing) |
| 150 | 12.25×12.25 = 150.1 | 144.6 | 134.8 | **−3.6%** | 5.5 | סלון 43.6; פינת אוכל 22.4; מטבח 19.7; חדר הורים 19.4; חדר שינה 15.1; חדר רחצה 9.0; מסדרון 5.7 |
| 180 | 13.42×13.42 = 180.1 | 178.2 | 166.9 | **−1.0%** | 1.9 | סלון 48.4; פינת אוכל 28.1; חדר הורים 24.1; מטבח 21.8; מסדרון 19.0; חדר שינה 17.9; חדר רחצה 7.7 |
| 200 | 14.14×14.14 = 199.9 | 194.6 | 182.4 | **−2.7%** | 5.4 | סלון 46.2; פינת אוכל 30.7; חדר הורים 26.5; מטבח 24.4; מסדרון 21.4; חדר שינה 19.4; חדר רחצה 13.9 |

Before the fix these three rows all read **104.5 m²**.

### 3BR + safe room + 2 wet + open plan — programme capacity 266.7 m²

| requested | footprint | gross | net | gap | unused | room areas |
|---|---|---|---|---|---|---|
| 120 | 10.95×10.95 = 119.9 | — | — | — | — | **PLAN_NOT_REALIZABLE** (genuinely too small) |
| 150 | 12.25×12.25 = 150.1 | — | — | — | — | **PLAN_NOT_REALIZABLE** |
| 180 | 13.42×13.42 = 180.1 | 179.6 | 163.7 | **−0.2%** | 0.5 | סלון 34.4; פינת אוכל 22.5; מטבח 20.5; חדר הורים 17.0; מסדרון 15.7; חדר שינה 15.0; חדר שינה 15.0; ממ״ד 9.4; חדר רחצה 8.0; חדר רחצה 6.3 |
| 200 | 14.14×14.14 = 199.9 | 196.0 | 179.5 | **−2.0%** | 3.9 | סלון 40.7; פינת אוכל 24.4; מטבח 22.3; חדר הורים 18.6; מסדרון 16.6; חדר שינה 16.1; חדר שינה 16.1; ממ״ד 9.4; חדר רחצה 8.7; חדר רחצה 6.7 |

**Selected concept:** `FRONT_PUBLIC_BAND` in every successful row above. Across the wider sweep the
spine strategies still win where the band is rejected; selection is now ordered by closeness to the
target, so which concept wins is decided by fit to the request rather than by generation order.

**Above capacity** — 2BR asked for 240 or 300 m²:

```
TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY
התוכנית שביקשת יכולה למלא עד כ-213 מ"ר בצורה סבירה, והיעד שהוזן הוא 240 מ"ר.
אפשר להוסיף חדרים או להקטין את שטח הבנייה — הדרישות שלך נשמרו כפי שהזנת.
```

Nothing in that message calls the house impossible to build, and the requested target is left
exactly as entered.

---

## What changed

**1 · The target reaches the generator.** `ProgramSpec.target_built_area_m2: float | None`, set by
`spec_for` from `project.built_area_m2`. Optional on purpose: the site-driven runs (L-shape, curved
façade, obstacle, disconnected) have no user target, keep `None`, and keep their original sizing —
which is what leaves those baselines numerically untouched.

**2 · The search visits proportions nearest-target-first.** New `_proportions()` builds exactly the
same candidate (width, depth) pairs as before — verified as an identical *set* — and only changes
their **order**. With no target the original order is reproduced exactly. This is the whole
correctness fix; everything else supports it.

**3 · A strategy offers up to 3 proportions instead of 1.** `plan_layout` is a pre-check, and a
proportion it accepts can still be rejected by Geometry Core. Committing each strategy to one
proportion meant that when the nearest-target one failed in the solver the strategy was lost
entirely — this is what broke `D_3BR_THREE_WET` on the first attempt. `_build` now returns a list,
`_concept_from` was split out unchanged to build each, and `_MAX_PROPORTIONS_PER_STRATEGY = 3`
keeps solver attempts bounded.

**4 · Candidate selection prefers the closest to the target.** `generate_concepts` sorts accepted
concepts by `|used_area_m2 − target|`. "Best first" now means best *for the request*.

**5 · The front band no longer absorbs unlimited leftover depth.** The band used to take whatever
depth the rear did not need, which is where surplus was being dumped: a 2BR house asked for 220 m²
came back with an **81.5 m² living room against its own 46 m² maximum**. The band depth is now
bounded by the *binding* room — the one that reaches its own maximum first, in practice the living
room, whose width is forced to span the hall. A proportion that would exceed it is rejected and the
search falls to a smaller one.

**6 · `scale_program` no longer sets a max above the template maximum.**

**7 · The capacity gate.** `program_capacity_gross_m2(rooms) = Σ max_area_m2 ÷ 0.90`. When the
target exceeds it, `generate_concepts` returns
`RejectionReason.TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY` before building anything, and
`app/demo/service.py` turns it into its own error code with a product message.

---

## Tests

9 new, in `tests/vertical_slice/test_concept_generator.py`:

| Test | Pins |
|---|---|
| `test_generated_area_tracks_the_requested_target` ×4 | 120 / 150 / 180 / 200 m² each within 10% |
| `test_generated_area_is_no_longer_pinned_to_the_template_fixed_point` | three requests → three different sizes, none near 104.5, monotonic |
| `test_rooms_are_not_inflated_to_fill_space` | no room past its maximum by more than the measured residue |
| `test_target_above_the_programme_capacity_is_reported_not_silently_shrunk` | the structured outcome, and that it never says "impossible" |
| `test_a_bigger_programme_can_absorb_what_a_smaller_one_cannot` | the ceiling belongs to the programme, not the engine |
| `test_without_a_target_the_original_programme_minimum_sizing_is_kept` | site-driven baselines unmoved |

---

## Honest residue

**Room maximums are respected in sizing, and overshoot by up to 5.75 m² in realization.** Geometry
Core tiles the footprint *exactly*, so the last few m² of residue must land somewhere. Bounding the
front band brought the worst case from **35.50 m² → 5.75 m²** (measured over 67 plans spanning
2–3 bedrooms × safe room × 1–3 wet rooms × open/closed × 150–220 m²). Closing the rest means
bounding every column and row site the same way, which is the Concept Generator redesign this task
excluded — so it is pinned by `MAX_TEMPLATE_OVERSHOOT_M2 = 6.0` and left visible rather than hidden.
I spent too long chasing this before stopping; the main objective was met well before that point.

**Some proportions are now rejected that previously produced a plan**, because they could only be
filled by inflating a room. Across the sweep this cost 5 of 72 plans (72 → 67) and moved the worst
individual gap to −30.2% while the median improved to −2.7%. That is the intended trade: a smaller
honest house rather than a ballooned one.

**Not addressed, as instructed:** the C11 entrance-walk/parking overlap that still fails 2BR at
120 m², the residual C8 case, 4-bedroom support, and Intake/Capability work.

No new room types. No new architectural heuristics. Stopping for review.
