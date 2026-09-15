# Footprint as a List of Rectangles — implementation record

**Date**: 2026-09-15 · **Branch**: `011-footprint-regions` (stacked on `010-multi-level-phase0`, worktree `sddproject-010`) · **Plan**: `BUILDING_SHAPE_MASSING_FAMILIES_REPORT.md` §2.2 / §4 — the generalisation both the L and an upper level with its own outline need, done once while the list is still of length 1.

**What this is**: every stage after Geometry Core that read the footprint as ONE rectangle now reads it as its **wings** (`tuple[Rect, ...]`), with the old rectangle kept as the **bounding box** under its old name. **What it is not**: an L. Nothing here makes the generator produce two wings; `_multi_wing_assessment` still declines them. The two-wing path is exercised by tests on the spike's F2 L-house, which the production core already solves.

## The rule

Byte-identical for one wing, real for two. The bounding box of one rectangle is that rectangle; `envelope_sides` against the room's own wing with no seams is `envelope_sides` against the footprint; the crook remainder of one wing is empty; C2's Σ wing area is the one area. Every field added is additive and defaulted.

## What changed, by anchor (the §2.2 table)

| Anchor | Was | Now |
|---|---|---|
| NEW `vertical_slice/footprint.py` | — | `bounding_box`, `area_u`, `wing_of`, `wing_on_street_line`, `subtract` (exact grid rectangle difference, deterministic), `remainder_within_bbox`, `covers`. Integer `Rect`s only; no polygon type. |
| `site.SitePlan` | `footprint: Rect` | `footprint` = bounding box; `wings: tuple[Rect, ...]` (defaults to `(footprint,)`). |
| `site.classify_garden` | bands around one rectangle | the same bands around the bounding box **plus** the crook (box − wings) as `GARDEN` regions after them. Classifying a crook as terrace/court is the L parti's decision, later; until then it is garden, said explicitly (Correction 3). |
| `geometry_adapter.envelope_sides` / `wall_facts_for_room` | side on the one footprint's edge | side on the room's **own wing's** edge and not a declared seam (`Wing.seam_leaf_sides`). |
| `windows.generate_windows` | one footprint | wings + `seam_sides_of(fixture)`; no window ever lands on a seam. |
| `doors.resolve_entrance` / `build_entrance_door` | street wall = the footprint's; corner clearance against the footprint | street line = bounding box's `y`; a zone fronts it when its own wing reaches it; clearance and `shared_length` against the **street wing's** wall (`wing_on_street_line`). |
| `validation` C2, C18 | `footprint.w * footprint.h`; bay overlap with the footprint | Σ wing area (the crook is not unassigned interior); bay overlap with any wing (a bay in the crook is not "inside the house"). C11 keeps the bounding box's building line, which is the street wing's line by construction. |
| `design_output.GeometricDesign` | `footprint_m` | `footprint_m` = bounding box; `footprints_m: tuple[RectM, ...]` (defaults to one). `assemble` passes wings and seams to the wall facts. |
| `renderer.py` | one white rectangle | one per wing. |
| `general_pipeline._realize` | `wings[0]` | `wings = tuple(w.rect() for w in fixture.wings)`; bounding box for the site plan; wings to entrance, site, door, windows. |
| `general_pipeline._family_signature` | `wings[0].tree` | one tree per wing, joined with `+`; one wing → the same string. |
| `demo/contract.DemoDesign` | `footprint` | `footprint` (box) + `footprints: list[RectOut]` (defaulted). `MassingOut.level_regions` beside `level_outlines`. |
| `building.Massing` | `level_outlines_m: tuple[RectM, ...]` | `level_regions_m: tuple[tuple[RectM, ...], ...]` — the `LevelMass.regions` of the shapes report §4; `level_outlines_m` derived as bounding boxes. `Building.single_level` uses `design.footprints_m`. |
| `building_validation` V2 / V7 | rect ⊆ rect; gross = outline area | every upper region ⊆ **union** of the level below (`regions_cover`, exact); gross = Σ regions; every ground region on the plot. |
| frontend `demoDesign.ts`, `DemoPlan.tsx` | `footprint` | `footprints?` + `footprintsOf()` (the one fallback); one `<rect>` per wing; `planViewBox` framed on the wings. `DemoMassing.level_regions?`. |

Left alone, deliberately: `concept_generator._hub_from_witness` (`wings[0]`, hub-specific), `Concept.footprint_width_m/depth_m` (the generator's one-wing dimensions), `pipeline.run_once` (the frozen slice; `SitePlan` defaults its wings), `windows._wall_length_u` (returns `rect.h` for a N/S wall — looks inverted, but it is existing behaviour the frozen baseline pins; not this branch's to change), `_multi_wing_assessment` (load-bearing until the L parti exists).

## Tests

- `tests/vertical_slice/test_footprint_wings.py` (12): the helpers (bounding box, exact subtraction, crook, union cover); envelope sides against a wing minus seams; the frozen slice's garden unchanged (4 regions, same ids); and the **F2 L-house through the generalised stages** — two wings + box, gross = Σ wings (134.25 m², not the box's 150), C2 passes, the crook is `garden_4`, the hall's seam side is INTERIOR while the dining wall facing the crook is EXTERIOR, no window on a seam, the entrance on the street wing with clearance against that wing, C5/C13 pass across the seam, family signature joins one tree per wing.
- `tests/vertical_slice/test_building.py` updated to regions (+2: V2 against the union of the wings below with an upper level over the bar vs over the crook; V7 against wings not the box).
- Frontend `DemoPlan.test.tsx` (+2): one wing renders the identical DOM with and without the wing list; an L renders two footprint rectangles and frames on them.

## Regression

- **Full-payload before/after snapshot** over the 432 distinct failure-log contexts, run through `generate_demo_design` on a detached worktree at `a235c37` (before) and on this branch (after). Compared: the whole `DemoPlanSet` JSON of the primary AND every alternative — rooms, walls, open interfaces, doors, windows, garden, parking, entrance walk, corridor, relationships, validation, outline, family, quality — with only the additive fields this branch introduces (`footprints`, `building`) stripped on both sides and the timing-only `search` dropped. **Planned before = after = 404; 404/404 payloads byte-identical; 0 status or refusal-code changes.** (1 context appears in one log copy only — the main checkout's log gained an entry between the two copies — and is reported as missing, not as a difference.)
- **Backend suite**: 1076 passed, 9 xfailed, 2 failed — the same two that fail on `main` @ `2a00c0f` (`test_the_design_request_offers_the_other_plans_it_proved`; `test_generator_produces_a_bounded_candidate_set[3BR]`), untouched.
- **Frontend**: 157 passed (2 new); `tsc` reports only the six errors already on `main`.
- Frozen baseline (`test_baseline_and_decoupling`), the `*_samples` reports, `test_general_pipeline`, `test_demo_p0`, `test_strip_rooms`, `test_hub_guard`: unchanged.

## Next (not started)

The L parti over the adapter's two candidates (shapes report §2.2 step 1), with `_multi_wing_assessment` replaced rather than deleted; the spike's seam proof P9 ported into `validation.py` as a C-check; crook classified as terrace/court by that parti. Independently: multi-level Phase 1 can now give an upper level its own regions without touching any of the anchors above.
