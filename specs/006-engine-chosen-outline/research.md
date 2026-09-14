# Research: Engine-Chosen Building Outline

Decisions taken against the code at `5fd9474`. Each records what was chosen, why, and what was
rejected. Measurements quoted are from the 424-brief outline sweep (spec §1).

---

## R1 — Where the outline loop lives

**Decision**: in `app/demo/service.py`, as a new `_plan_outlines(spec, project, outlines, on_stage)`
that calls the unchanged `run_general` once per outline (with `max_alternatives=ALTERNATIVE_PLAN_LIMIT`)
and returns a list of `OutlineResult`. `generate_demo_design` builds the outline list
(`_outlines_for(project)`), calls `_plan_outlines`, then `_select_plans`, then the existing
`_finish`-style gates per shown plan.

**Rationale**: the service already owns exactly this loop on the refusal path
(`_outline_that_plans`, [service.py:236](../../backend/app/demo/service.py#L236)) — same
`site_geometry.feasible_options`, same `project.model_copy(update={"selected_footprint": …})`, same
`run_general` call. Moving it before planning is a reordering, not new machinery. Keeping
`run_general` single-outline is what makes FR-012 and SC-005 hold by construction: a request with
an explicit outline runs the identical call it runs today.

**Alternatives rejected**:
- Teaching `run_general` to take several `BuildableRegion`s — would put outline policy inside the
  pipeline module and force the byte-identical gate to be argued rather than guaranteed.
- Keeping `_outline_that_plans` as a fallback beside the new loop — dead code: every outline it
  would try has already been tried. It is retired; its docstring's measurements move to this file.

## R2 — Selection rule across outlines

**Decision** (FR-004, FR-006, FR-007):
1. Pool = every validated plan from every outline (`primary` + `alternatives` of each
   `GeneralSliceResult`, each already past validation + safety).
2. If an explicit (person's) outline planned, its own primary is slot 1. Otherwise slot 1 is the
   pool entry minimising `(|gross − requested|, outline_order, candidate_index)`.
3. Remaining slots (≤ 2): walk the pool in that same order, take the first entry whose
   `family_signature` is not yet shown; when no unseen family remains, take the first entry whose
   `outline` is not yet shown; never take an entry whose `(outline, layout_signature)` is already
   shown.
4. Stop at 3 or when the pool is exhausted — never pad.

**Rationale**: (2) is today's rule (`generate_concepts` sorts by `|used − target|`, the pipeline
takes the first that validates) lifted one level; changing it here would confound the measurement
of this feature. (3) is the spec's "families before proportions" with the "different outline" fallback
from spec §2 Story 2. Measured effect: briefs showing ≥ 2 families 28 → 69 of 127.

**Alternatives rejected**:
- Quality-weighted primary (hall aspect, wet adjacency): deferred to its own feature, per spec §5.
- Filling remaining slots with same-outline proportion variants (today's behaviour): explicitly what
  the spec forbids (SC-006).

## R3 — Family signature: definition and placement

**Decision**: `RealizedPlan.family_signature` in `general_pipeline.py`, a read-only property next to
`layout_signature`, computed from `concept.fixture.wings[0].tree` and `fixture.access`:
- leaves → group letters: H hall · P public (LIVING/DINING/KITCHEN/FAMILY_ROOM) · F flex · M master ·
  B bedroom/study · S safe room · W wet room with a door to HALL · E wet room entered from a bedroom;
- nested splits of the same direction flattened into one node;
- children of every V node mirror-normalised (`min(seq, reversed(seq))` on the rendered strings);
- `fixed_at_u` ignored; rendered as a string, e.g. `V[H[B,B,S,W],H,H[P,P,M]]`;
- prefixed with the strategy family class: `HUB:` for `HUB_PRIVATE_WING` (its tree also has a public
  band at the root and would otherwise collapse into the band family).

**Rationale**: this is the exact signature the diagnostic used to produce the spec's numbers, so the
acceptance measurement and the product use one definition. It lives beside `layout_signature`
because it answers the sibling question ("same house?" vs "same drawing?"), and it is pure — no
behaviour of `run_general` depends on it.

**Alternatives rejected**:
- Strategy name as the family: `SPINE_DOUBLE_LOADED` and `SPINE_SERVICE_CLUSTER` produce identical
  trees in 66 of 77 co-occurrences; `SPINE_PUBLIC_PRIVATE` produces 87 distinct families. Names are
  neither necessary nor sufficient.
- Realized-geometry clustering: dimension-dependent, which is what the spec says to ignore.

## R4 — Sequential vs concurrent outline planning

**Decision**: sequential, in `PREFERRED_RATIOS` order after the explicit outline, v1.

**Rationale**: `solve_fixture` is pure-Python CPU work (measured 165 ms per candidate); threads gain
nothing under the GIL, and a process pool would cost pickling `Fixture`/`BuildableRegion` plus a
worker lifecycle for a saving of ~3 s worst case. Perceived latency is handled by R5 instead. SC-008
(≤ 4× median) is met sequentially by construction; the harness reports the actual figure.

**Alternatives rejected**: `concurrent.futures.ProcessPoolExecutor` — revisit only if SC-008's
measured median is unacceptable to the owner after R5.

## R5 — Progressive delivery over the stream

**Decision**: `POST /projects/{id}/design/demo/stream` gains one event type, `plan`, emitted the
moment an outline yields a validated plan (payload: that `DemoDesign` plus `outline`); `progress`
events become outline-major (`{"outline": k, "outlines": n, "step": s, "total": t, …}`); the final
`done` carries the complete, selected `DemoPlanSet` exactly as today. The non-streaming
`POST /design/demo` is unchanged in shape.

**Rationale**: the loading screen already consumes stage events from a worker-thread queue
([router.py:134](../../backend/app/demo/router.py#L134)); a `plan` event is the same mechanism
carrying a different payload. The frontend shows the first plan with a "בודקים עוד N מתארים" note
and swaps in the selected set on `done`. Because the primary may change on `done` (a later outline
can be nearer the requested area), the early plan is labelled provisional.

**Alternatives rejected**: emitting only `done` (4× perceived wait); making the early plan final
(would break FR-006).

## R6 — Scope with an optional footprint

**Decision**: in `scope.check_supported`, `selected_footprint is None` no longer refuses
(`FOOTPRINT_REQUIRED` stays for a non-RECTANGLE shape). The site requirement (`SITE_GEOMETRY_REQUIRED`)
stays. `feasible_options(site, built_area_m2)` returning `[]` becomes the "does not fit the plot"
refusal (`FOOTPRINT_DOES_NOT_FIT_BUILDABLE_REGION` reworded for "no outline of X m² fits", or
`NO_BUILDABLE_AREA` when there is no buildable rectangle at all). When a footprint *is* given, the
fit check runs exactly as today.

**Rationale**: `ProjectCreate.selected_footprint` is already `Optional` for legacy callers; the demo
path was the only place insisting on it. The two refusals that used to compare the person's
rectangle to the buildable area now compare the requested *area* to it, which is the honest question
once the shape is the engine's.

## R7 — Refusal semantics once every outline was tried

**Decision** (FR-009): when no outline yields a validated plan, raise one `DemoGenerationError`
chosen by this precedence, evaluated on the explicit outline's result if there was one, else on the
first engine outline's:
1. `TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY` (numbers-based check, as today);
2. `ROOM_RELATIONSHIP_NOT_FEASIBLE` if any outline's failure was a hard relationship;
3. `CORRIDOR_WIDTH_NOT_FEASIBLE` if binding corridor and every outline failed on it;
4. `PLAN_NOT_REALIZABLE` with the generic text — the "מתאר של X×Y כן מתאפשר" sentence is removed.

Diagnostics carry every outline's `RunMetrics` and rejection reasons (`outlines: [...]`), so the
failure log gains information rather than losing it.

**Rationale**: the suggestion sentence existed because the engine had *not* tried other outlines;
now it has. The precedence mirrors `_finish`'s current order so existing tests on refusal codes
keep their meaning.

## R8 — Contract additions (all additive, defaulted)

**Decision**:
- `DemoDesign.outline: OutlineOut | None` — `{width_m, depth_m, area_m2, origin: "ENGINE"|"PERSON"}`
  (the rectangle is already there as `footprint`; `outline` adds origin and keeps the person-facing
  label in one place).
- `DemoDesign.family: str | None` — the signature string, for diagnostics and tests; not rendered.
- `DemoPlanSet.search: SearchSummary | None` — `{outlines: [{width_m, depth_m, origin, planned,
  latency_ms, plans_found}], total_latency_ms}` (FR-010).
- SSE: new `plan` event; `progress` payload gains `outline`/`outlines` keys.

**Rationale**: every existing consumer (plain POST, tests, the review screen) reads `plan` and
`alternatives` and continues to; `None`/empty defaults keep serialisation identical for callers that
never see the new path.

## R9 — Non-regression and acceptance instrument

**Decision**: `spikes/failure_log_sweep/outline_ab.py` runs the 424 contexts twice through
`generate_demo_design`: (A) advanced path — `selected_footprint` as logged; (B) main flow —
`selected_footprint=None`. Reports: A's 127 primaries byte-identical to the frozen HEAD snapshot
(SC-005); B's planned count (SC-001), first-plan gross ÷ requested median (SC-002), briefs with
≥ 2 families shown (SC-003), same-family-same-outline pairs (SC-006), refusal texts containing an
outline suggestion (SC-007), latency medians A/B vs the HEAD snapshot (SC-008). `sweep.py`'s
`project_from_context` gains `with_footprint: bool = True`.

**Rationale**: the harness is the project's established gate (features 004–005); extending it keeps
the acceptance numbers comparable with `BASELINE.md` and RESULTS of 005.

---

## Measurements carried from the diagnostic (for reference during implementation)

| Fact | Value |
|---|---|
| Per-candidate solve cost | ~165 ms; stages after the solver ~17 ms per candidate |
| Today's median request time in the harness | ≈ 1.1 s |
| Outlines that de-duplicate to the person's own | 25 / 424 |
| Briefs planning only at the person's outline | 2 / 424 |
| Preferred-ratio success rates | 0.95: 43 % · 1.15: 45 % · 0.75: 35 % · 1.45: 40 % |
