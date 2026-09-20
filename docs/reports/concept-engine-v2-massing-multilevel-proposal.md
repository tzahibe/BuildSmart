# Concept Engine v2 — massing and multi-level integration proposal (Issue #78)

A proposal only, per the ROOT Issue's second deliverable — no implementation here. Grounded in
what exists today: `docs/wiki/features/l-massing.md`, `docs/wiki/features/multi-level.md`,
`app/vertical_slice/concept_spec.py` (`ConceptSpec`, `CirculationClass`, `MasterPlacement`,
`EntranceSide`), `app/vertical_slice/concept_patterns.py` (`Pattern`, `PATTERNS`).

## What Concept Engine v2 (CE2-1..4) actually operates on

`concept_engine_v2.plans_per_class` runs INSIDE `general_pipeline.run_general` — one outline, one
buildable region, one call to `concept_generator.generate_concepts`. It compiles/realizes/scores
candidates the generator already produced FOR THAT OUTLINE. It never chooses BETWEEN outlines
(rectangle vs L vs a different size) — that survey is `app/demo/service.py`'s own layer
(`_outlines_for`, `_plan_outlines_until_one_plans`, `_select_plans`), untouched by this Issue.

This is the key fact the proposal below is built on: **CE2's "concept" is a within-outline
organisation (a parti); massing (which outline/footprint shape) and multi-level (how many storeys)
are both ABOVE it, in `demo/service.py` and above `run_general` respectively.**

## 1. Rectangle / L / Irregular massing

**Today**: `ConceptSpec.massing` already carries a coarse `"1W"`/`"2W"` field (wing count), and
`concept_patterns.PATTERNS` already has three `"irregular"`-family entries
(`RING_IRREGULAR`/`BRANCHED_IRREGULAR`/`TWO_WING_IRREGULAR`) with real citations — written and
ready, but reachable only once `reference_benchmark.classify_footprint_family` can return
`"irregular"`, which it cannot today (no massing capability produces one — see that function's own
docstring). `CirculationClass.BRANCHED`/`RING` are the same story: declared, labelled
(`concept_engine_v2.concept_label` already covers them), never produced by any builder.

**Proposal**: when an Irregular-massing capability is eventually built (a generator/geometry
change, explicitly out of scope for CE2), it needs NO new work in `concept_patterns.py` or
`concept_engine_v2.py` — the pattern table and the label vocabulary already anticipate it. The one
real integration point is `concept_engine_v2.brief_and_outline_of`'s `outline.shape`: today it only
distinguishes `"RECTANGLE"`/`"L"` (from `len(fixture.wings) > 1`); it would need a third value once
an irregular fixture exists, so `patterns_for`'s footprint-family classification sees it.

**Massing SELECTION** (choosing which outline — a rectangle, an L, or in future an irregular shape
— becomes the primary) is `demo/service.py`'s question, not CE2's, and should stay that way: CE2's
per-outline diversity and cross-outline massing selection are genuinely different problems (one is
"which organisation, holding the footprint fixed," the other is "which footprint"). Merging them
would mean `plans_per_class` reaching outside `run_general` into a multi-outline survey it does not
own — a bigger architecture change than this proposal recommends taking on. `_massing_representation_
plans` already bridges the two cleanly at the point where they need to meet (guaranteeing a slot for
a massing CE2's own class-search did not happen to produce) — worth keeping as the seam.

## 2. Multi-Level Phase 2

**Today** (per `docs/wiki/features/multi-level.md`): a `Building` composes TWO independently
realized `GeometricDesign`s (ground + upper) through `building_coordinator.py`'s core-band
allocations (A/C, unranked), validated by `building_validation.py` — a layer ABOVE `run_general`,
entirely unwired from `concept_generator.py`/`general_pipeline.py`/`demo/*`. `ConceptSpec` already
has a `MasterPlacement.UPPER_LEVEL` value ("on its own storey in a multi-level concept") — metadata
only, unused by any generator today, but evidence this module's authors already anticipated the
fit.

**Proposal**: do NOT fold multi-level into CE2-4/5. The unit `concept_score.concept_score` scores
and `concept_score.adapt` adapts is a single-level `RealizedPlan` (M3/M4/M5, entrance rank, wet-core
— all single-storey facts read off one `GeometricDesign`). Scoring a BUILDING would need a distinct
function reading building-level facts (core-band efficiency, the A/C allocation choice, whether the
stair seat aligns between levels — the "one parti idea" and "stair seat coupling" findings already
on record for multi-level) — a real new module, not a small extension of `concept_score.py`. Given
multi-level is itself not wired to the product yet, sequencing matters: wiring multi-level to
`demo/*` first (its own, already-scoped follow-up per its wiki page) gives CE2's eventual multi-
level extension a live single-level product to extend FROM, rather than building two unproven
integrations at once. Recommend: multi-level product wiring first, a CE2 "building-level concept"
extension only after, as its own future child Issue — not CE2-5.

## 3. Stairs / vertical core

**Today**: one `VerticalCore` type — a shared, pinned straight stair — per `Building`; no stair-type
or position CHOICE exists to be a "concept" over. `CirculationClass` is deliberately a GROUND-FLOOR
organisation vocabulary (the parti a person reads walking in); it says nothing about vertical
circulation, and should not be extended to.

**Proposal**: when stair-type/position choice is eventually built, model it as an ORTHOGONAL axis
alongside `circulation_class`, not a value within it — the same pattern `ConceptSpec` already uses
for `zoning`/`wet_core_grouping` (independent classifications of one candidate, not folded into
`CirculationClass` itself). A future `VerticalCoreStrategy` enum, scored by its own small function
(seat alignment, run length, daylight to the stair), composed alongside — never inside —
`concept_score.concept_score`'s ground-floor weights. This keeps the single-level scoring weights
(calibrated, if informally, against M1-M6) untouched by an unrelated vertical-circulation concern.

## Summary recommendation

Ship CE2-4 exactly as scoped (single-level, one-outline-at-a-time). The two multi-outline concerns
(massing selection, multi-level) belong to `demo/service.py` and `building_coordinator.py`
respectively, both already structurally separate from `run_general`/`concept_engine_v2.py` — keep
them that way rather than widening CE2's own scope to reach them. The pattern-table and label
groundwork for Irregular/BRANCHED/RING already exists and needs no CE2 change once a generator
capability produces them. None of this needs to be decided before the owner reviews the CE2-4
benchmark (`concept-engine-v2-owner-benchmark.md`) — it is independent of whether the flag itself
is turned on.
