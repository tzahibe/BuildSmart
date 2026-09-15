# Multi-Level — Phase 0: domain and contracts

**Date**: 2026-09-15 · **Branch**: `010-multi-level-phase0` (worktree `sddproject-010`, from `main` @ `2a00c0f`) · **Plan**: `MULTI_LEVEL_AND_HOUSE_CONCEPT_ARCHITECTURE_REPORT.md` §13, Phase 0

**What this phase is**: the types the multi-level work will be written against, emitted beside today's payload, with zero change to what is planned or drawn. **What it is not**: a second storey. `SUPPORTED_FLOORS` is still 1 and the refusal is unchanged.

## What was added

| Where | What |
|---|---|
| `vertical_slice/spec.py` | `HouseConcept` (stories, public/private strategy, entrance/master level, bedroom grouping, circulation style, public open side, per-level area preferences, source, `hard_fields`) and its enums; `ArchitecturalSpec.concept` with a default that is exactly today's house, so every two-field constructor builds the same spec; `ProgramSpec.total_built_area_m2` as the name for the TOTAL (alias of `target_built_area_m2` today). |
| `vertical_slice/vertical.py` | `VerticalCore` — the stair as one rectangle on both levels, with entry/arrival edges and direction; archetypes `STRAIGHT / L_SHAPED / U_HALF_LANDING`. Nothing produces one yet (the generator cannot seat a stair — report §1 items 4–5). |
| `vertical_slice/building.py` | `Level`, `LevelEntry` (street door / stair arrival), `LevelPlan` (today's `GeometricDesign` + `ValidationReport`, carried as-is), `Massing` (plot + one outline per level, coverage, retreat), `Building` (levels, cores, totals) with construction invariants, and `Building.single_level(design, validation)`. |
| `vertical_slice/building_validation.py` | V-checks between levels. **V2** (upper outline inside the one below) and **V7** (each level's gross = its outline's area; ground outline on the plot; coverage a ratio) run; V1/V3–V6 are numbered and described but NOT emitted until a real core exists — only checks that ran appear. |
| `demo/contract.py` | `DemoBuilding { story_count, levels[], cores[], massing, totals, validation }` and `DemoPlanSet.building` (defaulted `None`). `to_demo_building` takes the ALREADY-BUILT `DemoDesign`s so `levels[0].design` is `plan` byte for byte. Hebrew level names and V-statements live here, like `_ROOM_NAMES` and `_STATEMENTS`. |
| `demo/service.py`, `demo/router.py` | The primary is wrapped as a one-level `Building` after every gate; both routes return it. The failure context now carries `floors`, so `FLOORS_UNSUPPORTED` refusals are countable — the parser defaults to one storey when the brief says nothing, so the log is the only place the demand for a second one can be read. |
| `frontend/src/design/demoDesign.ts` | TS mirror of the building contract; `DemoPlanSet.building?`. |
| `frontend/src/design/ReviewPage.tsx` | The storey count is shown with its provenance (it was the one parsed field the review screen did not render), bounded by `limits.floors`, and blocks Generate here — where it can be corrected — instead of after the loading screen. Sent back in `ReviewEdit.floors`. |

## Deliberate deviations from the §13 Phase 0 list

- **`LevelContext` not added.** It has no consumer until `validate` takes a per-level context (Phase 1); an unused type is speculation. `LevelEntry` carries the entry seed it would have carried.
- **Built-area label left as "one-storey footprint area."** The engine still plans one storey, so the label is still true; renaming it "total" now would contradict `App.test.tsx`'s measured reason for the current wording. The domain-side name (`total_built_area_m2`) exists; the UI rename comes with Phase 1.
- **`FLOORS_UNSUPPORTED` message unchanged.** The computed "two storeys could reach … m²" line needs the allocation pre-check (Phase 2).
- **Workspace rendering unchanged.** `DemoWorkspace` accepts a plan set with `building` and draws exactly what it drew without it (tested by innerHTML equality); level tabs appear when a second level can.

## Regression

- Backend: **1062 passed, 9 xfailed, 2 failed** — both failures pre-exist on `main` @ `2a00c0f` and are unrelated: `test_demo_p0::test_the_design_request_offers_the_other_plans_it_proved` (fails on `main` with and without the working tree's uncommitted changes) and `test_concept_generator::test_generator_produces_a_bounded_candidate_set[3BR]` (26 > 24; the main checkout's uncommitted edit raises the bound to 48). Not touched here.
- Frozen baseline (`test_baseline_and_decoupling`), the `*_samples` reports, `test_general_pipeline`, `test_demo_p0` route tests, `test_demo_outline_selection`, `test_strip_rooms`, `test_hub_guard`: unchanged and passing. `DemoDesign` JSON is byte-identical (`building.levels[0].design == plan` is asserted through the route).
- Frontend: **155 passed** (4 new); `tsc` reports only the six errors already present on `main`.

## New tests

`tests/vertical_slice/test_house_concept.py` (10), `tests/vertical_slice/test_building.py` (12: the frozen slice as a building — 170.4 / 153.83, entry `HALL_MAIN`, V2 + V7 only; synthetic two-level buildings for V2 cantilever, V7 wrong gross, V7 off-plot; construction invariants), `test_demo_contract_additive.py` (+2), `test_demo_p0.py` (+2: the building on the route; a two-storey brief refused and logged with `floors=2`), `ReviewLimits.test.tsx` (+3), `DemoPlan.test.tsx` (+1).

## Next (Phase 1, not started)

The generator: a private-only allocation family, a pinned `STAIR` leaf (`_contains_hall` → a pinned set), and the seat search around `run_general` — see the architecture report §8 and §13.
