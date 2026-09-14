# Data Model: Engine-Chosen Building Outline

Entities introduced or extended, with invariants. Nothing below the service layer gains state; the
only pipeline-level addition is a derived, read-only signature.

## Outline

One rectangle the engine plans the brief into.

| Field | Type | Notes |
|---|---|---|
| `width_m`, `depth_m` | float > 0 | rounded to 0.05 m as `feasible_options` already does |
| `area_m2` | float | `width_m × depth_m`; equals the requested built area within the existing 0.5 % tolerance |
| `origin` | `PERSON` \| `ENGINE` | `PERSON` only when the request carried `selected_footprint` |
| `order` | int ≥ 0 | 0 for the person's outline; engine outlines numbered in `PREFERRED_RATIOS` order |

**Invariants**
- Fits inside the buildable rectangle (`check_footprint_fits`) — guaranteed by construction for
  `ENGINE`, checked in scope for `PERSON`.
- The list for a request is de-duplicated on `(round(width_m, 2), round(depth_m, 2))`; the person's
  outline wins a tie with an engine one and keeps `origin = PERSON`.
- Deterministic: same project → same list, same order.

## OutlineResult

What one outline produced.

| Field | Type | Notes |
|---|---|---|
| `outline` | Outline | |
| `result` | `GeneralSliceResult` | exactly what `run_general` returns today |
| `plans` | list[`RealizedPlan`] | `[chosen] + alternatives` **only if** `result.ok`; else `[]` |
| `latency_ms` | float | wall time of this outline's `run_general` |
| `refusal_hint` | enum | derived: `CAPACITY` / `RELATIONSHIP` / `CORRIDOR` / `NONE`, from the result's notes and validation, using `_finish`'s existing predicates |

**Invariants**
- Every entry in `plans` has `validation.ok and safety.ok` (the same predicate `_alternative_plans`
  uses). A plan that fails any check never enters `plans`.
- `plans[0]`, when present, is the outline's own primary — byte-identical to what today's request
  with this outline returns.

## RealizedPlan.family_signature *(pipeline, derived)*

A string computed from the plan's concept tree. Definition in research R3.

**Invariants**
- Independent of `fixed_at_u`, of realized dimensions, and of left/right mirroring.
- Identical for a forced tree and its unforced twin.
- `SPINE_DOUBLE_LOADED` and `SPINE_SERVICE_CLUSTER` with the same allocation yield the same signature.
- Two plans with different `family_signature` differ in at least one of: root organisation
  (band-over-spine / column-hall-column / hub), which group occupies which column or band, or
  which wet room is entered from a bedroom.
- Prefix `HUB:` for `HUB_PRIVATE_WING`.

## PlanSelection

The cross-outline choice (research R2), computed in the service.

| Field | Type | Notes |
|---|---|---|
| `pool` | list[(OutlineResult, RealizedPlan)] | all validated plans of all outlines, ordered by `(|gross − requested|, outline.order, plan.index)` |
| `primary` | (OutlineResult, RealizedPlan) | the person's outline's `plans[0]` if it exists; else `pool[0]` |
| `alternatives` | list, len ≤ 2 | filled by the rule: unseen family first; then unseen outline; never same `(outline, layout_signature)` |

**Invariants** (each is a test)
- `len(shown) ≤ 3`; `shown` never contains two plans with the same `(outline, layout_signature)`.
- If `≥ 3` distinct families exist in `pool`, `shown` has 3 distinct families.
- If exactly 2 families exist, both are shown.
- No two shown plans share both `family_signature` and `outline` (SC-006).
- With a `PERSON` outline that planned, `shown[0]` is its `plans[0]`.

## Contract additions (all optional, defaulted — see [contracts/demo-plan-set.md](./contracts/demo-plan-set.md))

- `DemoDesign.outline: OutlineOut | None` — `{width_m, depth_m, area_m2, origin}`.
- `DemoDesign.family: str | None`.
- `DemoPlanSet.search: SearchSummary | None` — `{outlines: [OutlineTried], total_latency_ms}`
  where `OutlineTried = {width_m, depth_m, origin, planned: bool, plans_found: int, latency_ms}`.

## Request model

`Project.selected_footprint` — already `Optional[SelectedFootprint]`; semantics change only in the
demo scope check: `None` now means "engine chooses", not "refuse". `FootprintSource` keeps
`PRESET | CUSTOM`; both map to `origin = PERSON` (the person confirmed a rectangle either way).

## State transitions (request lifecycle)

```
received ─► scope ok ─► outlines built (n ≥ 1) ─► outline k planned … ─► selection ─► shown (1–3)
                │               │                        │
                │               └─ n = 0 ──────────────► refused: does-not-fit / no-buildable-area
                │                                        │
                └─ refused (site missing, shape, fit)    └─ all outlines empty ─► refused (R7 precedence)
```

The streaming endpoint emits `progress` at each stage of each outline, `plan` the first time an
outline's `plans` is non-empty, and `done` after selection.
