# CORRIDOR_WIDTH_IMPLEMENTATION_REPORT

```
STATUS = DONE
TESTS  = 699 backend (was 690, +9), 67 frontend (was 64, +3), tsc clean
SCOPE  = corridor width only
```

`"מסדרון ברוחב 5 מטר"` used to be planned as 1.4 m in silence. It now reaches the planner as a
number, decides the geometry, is verified against the **realized** plan, and is refused rather than
violated when it does not fit.

---

## The table

| brief | requested | generated | result |
|---|---|---|---|
| (no corridor mentioned) | — | 1.55 m | default preserved |
| "המסדרון חייב להיות לפחות 1.6 מטר" | 1.60 m (minimum) | **1.60 m** | met, C14 pass |
| "מסדרון ברוחב 1.8 מטר" | 1.80 m (exact) | **1.80 m** | met, C14 pass |
| "המסדרון חייב להיות לפחות 1.8 מטר" | 1.80 m (minimum) | **1.80 m** | met, C14 pass |
| "אני רוצה מסדרון של 2 מטר" | 2.00 m (exact) | **2.00 m** | met, C14 pass |
| "אני מעדיף מסדרון של 2.5 מטר" | 2.50 m (preference) | 1.20 m | preference dropped, **warned** |
| "המסדרון חייב להיות לפחות 2.5 מטר" | 2.50 m (minimum) | — | `CORRIDOR_WIDTH_NOT_FEASIBLE` |
| "מסדרון ברוחב 5 מטר" | 5.00 m (exact) | — | `CORRIDOR_WIDTH_NOT_FEASIBLE` |

Rows 2–5 use whichever programme has the width to spare — a 2-bedroom house reaches 2.0 m at 200 m²,
a 3-bedroom + safe room reaches 1.6 m at 200 m² and 1.8 m at 240 m². The frontier is real, not a
limitation of the plumbing.

---

## PARSER_RESULT

`CorridorWidth { value_m: float|None, mode: exact|minimum|preference, source }` on
`RequirementExtraction`. The prompt requires a **number** for the corridor specifically, converts
centimetres to metres, and states the modality cues: לפחות / לא פחות מ / מינימום → `minimum`;
a plain stated width → `exact`; עדיף / רצוי / אשמח → `preference`.

Two rules keep it clean: *"המסדרון חייב להיות לפחות 1.6 מטר" is a MINIMUM of 1.6, NOT exactly 1.6*,
and a numeric corridor width **must not also appear in `other_requests`** — it is supported now. A
corridor mentioned without a number ("מסדרון רחב") still goes to `other_requests`, because there is
nothing to plan from. Pinned by `test_a_supported_corridor_width_is_not_left_in_other_requests`.

## AUTHORITATIVE_FIELD

`ProgramSpec.corridor: CorridorRequirement | None` — `width_m` plus `mode`, built by
`requirements_view._corridor_of` from the stored `Project.corridor_width`. The mode is carried
through unchanged and is never flattened
(`test_a_minimum_is_never_reinterpreted_as_an_exact_width`).

## DEFAULT_BEHAVIOR

**Unchanged when no width is asked for.** `_hall_width_m` returns exactly what the code did before —
the derived width clamped by the parti's own cap — and C14 does not run at all. The 9 site-driven
baselines and the canonical fixture are numerically identical; the whole 699-test suite passes.

## CONCEPT_PROPAGATION

Both constants are gone:

- `min(hall_w, 2.4)` in `plan_layout` — the column partis' ceiling
- a fixed `1.4` in `_plan_front_band` — the front-band parti's hall

Both now call `_hall_width_m(corridor, derived, cap_m=…, has_safe_room=…)`. **With a requirement the
cap does not apply** — it exists to stop an area-derived hall from ballooning, not to overrule the
person. `MINIMUM` and `PREFERENCE` act as floors (`max(derived, required)`), so a hall the layout
wants wider stays wider; `EXACT` is planned to the stated width.

**Gross vs net.** The person means the width they can walk, so the requirement is a NET dimension
and the planner has to add the wall insets back. The allowance budgets for the **worst wall the hall
can touch**: two partition-halves normally, and a partition-half plus an RC half where the programme
has a safe room, because the safe-room envelope may abut the hall. Getting this wrong was visible in
both directions during implementation — over-granting realized an exact 2.00 m request as 2.10 m and
rejected it for being *too wide*; under-granting realized a requested 1.60 m as 1.50 m.

## REALIZED_WIDTH_VALIDATION

**C14 — "corridor meets the requested width"**, in `validation.py`. It does not read `ProgramSpec`:
`realized_corridor_width_m` measures the **net short side of the realized circulation rectangle**,
after wall insets, and takes the narrowest where several exist — that is what a person actually
walks through. `MINIMUM`/`PREFERENCE` are one-sided (wider passes). `EXACT` is strict downward and
tolerates up to one partition-half upward, because the planner fixes the width before wall types are
known and must budget for the thickest abutting wall; rejecting a corridor for landing 5 cm generous
would send the person to change a request that was met.

C14 is skipped entirely when no width was requested, so it cannot affect the default path.

## FEASIBILITY_BEHAVIOR

Feasibility comes **before** forcing geometry, and the corridor is never narrowed to make a plan fit.

| Situation | Outcome |
|---|---|
| binding width, no concept plans with it | `CORRIDOR_WIDTH_NOT_FEASIBLE` |
| binding width, plan realized but too narrow (C14 the only failure) | `CORRIDOR_WIDTH_NOT_FEASIBLE`, quoting requested vs realized |
| preferred width that does not fit | one retry without it; plan returned, `warnings` names the dropped preference |

The message names both numbers, offers the three real levers (more built area, one fewer room, a
narrower corridor), and **never says the house cannot be built**.

One misattribution was found and fixed while testing: a target area exceeding the programme's
capacity was being reported as a corridor failure, which would have sent the person to shrink a
corridor that was never the obstacle. The corridor branch now stands aside when the capacity
rejection is present.

## UI_REVIEW_BEHAVIOR

The review screen shows the understood requirement above the editable fields:

```
רוחב מסדרון מינימלי: 1.80 מ׳
```

The label follows the mode — מינימלי / (exact) / מועדף — so a misread modality is visible before
Generate. Nothing is shown when no width was asked for.

`DemoDesign.corridor` carries `requested_width_m`, `requested_mode`, `realized_width_m` and
`satisfied`, with the realized figure measured off the plan rather than echoed from the request.

## TEST_RESULTS

**699 backend, 67 frontend, tsc clean.** Nine new backend tests, all through the real
parser → `POST /projects` → `/requirements` → `/review` → `/design/demo` path:

| Test | Case |
|---|---|
| `test_no_corridor_width_keeps_the_existing_default` | no width → no C14, default corridor |
| `test_a_minimum_corridor_width_is_met_or_exceeded` ×2 | 1.6 m and 1.8 m minimums |
| `test_a_minimum_is_never_reinterpreted_as_an_exact_width` | the mode survives the whole path |
| `test_a_two_metre_request_is_planned_to_two_metres` | a 2.0 m request realized at 2.0 m |
| `test_a_width_the_geometry_cannot_hold_fails_explicitly` | structured refusal, never "impossible" |
| `test_a_preferred_width_gives_way_rather_than_blocking` | dropped, warned, plan still produced |
| `test_a_hard_width_request_blocks_where_a_preference_would_not` | same number, two wordings, two endings |
| `test_a_supported_corridor_width_is_not_left_in_other_requests` | no double-reporting |

Three frontend tests cover the minimum label, an exact width not being labelled a minimum, and
silence when nothing was asked for.

---

## Not done, by instruction

No adjacency/separation, no Concept Generator redesign, no new room types, no 4BR, no change to the
general geometry architecture, no new heuristics. The pre-existing C8 residue and the C11
entrance-walk/parking overlap are untouched.

Stopping for review.
