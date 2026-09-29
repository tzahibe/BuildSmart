# Two-path demo — what main can draw today, beside the non-guillotine realizer (Issue #155)

## What this comparison does and does not prove

**Path B (the rectilinear realizer) refuses MORE OFTEN than path A on these 8 real briefs: 5/8 refused vs 0/8 for path A.** The realizer is a proof of geometric feasibility on a hand-tuned placement heuristic (`spikes/geometry_shapes/stage1_gate.py`'s own intent-builders, reused here unchanged), not a placement engine — most of its refusals below are this script's own placement guess missing a real room's actual size or role mix, not a fact about the architecture. Path A never refuses on these 8 briefs because they were drawn from the corpus's own PLANNED pool — a pool defined by path A already succeeding on them.

**What this DOES prove**: for every brief below, both plans were produced by the SAME shipping contract-building entry point, `app.demo.contract.to_demo_design` — the one function that turns a validated, realized geometry into the `DemoDesign` JSON Issue #146's drawing layer (`DemoPlan.tsx`) draws, and draws NOTHING that is not on that object (that component's own docstring: "This component decides NOTHING architectural... If a fact is not on the object, it is not drawn"). Every REALIZED path-B plan passed the UNCHANGED validator chain, C31 included, plus C30 run and disclosed (see "C30/C31" below). No refused plan was ever replaced by a different, easier brief or a silently-approximated pass.

**What this does NOT prove**: that the realizer is ready to wire into the product (#142A, explicitly out of scope here); that path B's placement heuristic is any good — it is this script's own deterministic, un-optimized guess reused from the Stage 1 gate, never the subject of this Issue; that the M1-M6 numbers below are comparable in the usual sense — path B's rooms are a synthetic re-placement of the SAME real room roles/areas, not the same floor plan redrawn, so a metric moving is a fact about this script's placement choice, not about the realizer's own geometric capability. And it does not prove the realizer draws MORE non-rectangular shapes than it actually does: the contract-level non-rectangular room count below undercounts path B on purpose-built L/U notch-carve rooms — see "Non-rectangular counts" for why, and the separate construction-level ground truth that fills the gap.

## Per-brief results

| # | brief (short id) | path B family | path A | path B |
|---|---|---|---|---|
| 0 | brief-00 | PINWHEEL | REALIZED (validated) | REALIZED (validated) |
| 1 | brief-01 | TWO_WING | REALIZED (validated) | REALIZED (validated) |
| 2 | brief-02 | L | REALIZED (validated) | REFUSED — SHORT_SIDE_INFEASIBLE |
| 3 | brief-03 | TWO_WING | REALIZED (validated) | REFUSED — NO_USABLE_ROOMS |
| 4 | brief-04 | L | REALIZED (validated) | REFUSED — VALIDATION_FAILED |
| 5 | brief-05 | PINWHEEL | REALIZED (validated) | REFUSED — SHORT_SIDE_INFEASIBLE |
| 6 | brief-06 | L | REALIZED (validated) | REFUSED — SHORT_SIDE_INFEASIBLE |
| 7 | brief-07 | PINWHEEL | REALIZED (validated) | REALIZED (validated) |

A brief's own numeric context (bedrooms, SAFE_ROOM, built area, plot dimensions) is in `selected_briefs.json`; its full `DemoDesign` JSON for whichever path(s) realized is in `contracts/<short>-A.json`/`contracts/<short>-B.json`. **Visual composite generation could not be run or verified in this session** — `frontend/node_modules` is not installed anywhere in this repo checkout and `npm install` requires an approval this headless session has no surface for (see "Reproducing this report"); the composite step (`frontend/src/design/twoPathDemoComposites.test.tsx`, real `DemoPlan` renders through React Testing Library, one `composites/<short>.html` per brief) is written and reproducible in a normal frontend environment/CI, but no `composites/*.html` file is committed by this change — do not treat their absence as evidence the realizer draws nothing; the `contracts/*.json` files above are the real, unrendered contract for both paths, and the section below is the same per-brief content in textual form.

## Per-brief composite (AC-4)

A TEXTUAL side-by-side composite, one per brief — each side (path A / path B) labelled with its path, its validator verdict, and its M1-M6 (read off the SAME `demo_design.quality.metrics` object `to_demo_design` produced for that side; "—" means that side never realized, so there is no plan to measure). This is the same content the visual composite above would show, without the rendered image.

| brief | side | path | verdict | M1 habitable aspect (median) | M2 habitable-on-envelope ratio | M3 circulation share | M4 hall door count | M4 hall aspect (median) | M5 wet adjacency ratio | M6 public zone contiguous |
|---|---|---|---|---|---|---|---|---|---|---|
| brief-00 | A | app.demo.service (path A) | REALIZED (validated) | 1.857 | 1.000 | 0.101 | 5 | 10.321 | 0.000 | yes |
| brief-00 | B | rectilinear_realizer, PINWHEEL (path B) | REALIZED (validated) | 1.676 | 1.000 | 0.227 | 6 | 3.001 | — | no |
| brief-01 | A | app.demo.service (path A) | REALIZED (validated) | 1.600 | 1.000 | 0.143 | 3 | 10.000 | 0.000 | yes |
| brief-01 | B | rectilinear_realizer, TWO_WING (path B) | REALIZED (validated) | 1.589 | 1.000 | 0.169 | 7 | 2.678 | — | no |
| brief-02 | A | app.demo.service (path A) | REALIZED (validated) | 1.136 | 1.000 | 0.113 | 9 | 9.179 | 0.667 | yes |
| brief-02 | B | rectilinear_realizer, L (path B) | REFUSED — SHORT_SIDE_INFEASIBLE | — | — | — | — | — | — | — |
| brief-03 | A | app.demo.service (path A) | REALIZED (validated) | 1.348 | 1.000 | 0.114 | 9 | 11.286 | 0.000 | yes |
| brief-03 | B | rectilinear_realizer, TWO_WING (path B) | REFUSED — NO_USABLE_ROOMS | — | — | — | — | — | — | — |
| brief-04 | A | app.demo.service (path A) | REALIZED (validated) | 1.201 | 1.000 | 0.109 | 7 | 9.571 | 0.000 | yes |
| brief-04 | B | rectilinear_realizer, L (path B) | REFUSED — VALIDATION_FAILED | — | — | — | — | — | — | — |
| brief-05 | A | app.demo.service (path A) | REALIZED (validated) | 1.709 | 1.000 | 0.113 | 6 | 10.714 | 0.667 | yes |
| brief-05 | B | rectilinear_realizer, PINWHEEL (path B) | REFUSED — SHORT_SIDE_INFEASIBLE | — | — | — | — | — | — | — |
| brief-06 | A | app.demo.service (path A) | REALIZED (validated) | 2.143 | 1.000 | 0.073 | 6 | 7.536 | 0.000 | yes |
| brief-06 | B | rectilinear_realizer, L (path B) | REFUSED — SHORT_SIDE_INFEASIBLE | — | — | — | — | — | — | — |
| brief-07 | A | app.demo.service (path A) | REALIZED (validated) | 1.764 | 1.000 | 0.113 | 6 | 9.286 | 0.000 | yes |
| brief-07 | B | rectilinear_realizer, PINWHEEL (path B) | REALIZED (validated) | 1.534 | 1.000 | 0.213 | 6 | 2.678 | — | no |

## Refusal detail (AC-3)

- **brief-02, path B** (L) — refusal code `SHORT_SIDE_INFEASIBLE`: HALL: row-realized short side 1.20 m (gross) < 1.0 m (net) + 0.3 m inset margin
- **brief-03, path B** (TWO_WING) — refusal code `NO_USABLE_ROOMS`: not enough usable real rooms in this context to build a TWO_WING layout at any of this script's retry scales
- **brief-04, path B** (L) — refusal code `VALIDATION_FAILED`: C31: BIG_LIVING_KITCHEN__c2: only realized path to it is blocked by furniture in an intermediate room, no way around it
- **brief-05, path B** (PINWHEEL) — refusal code `SHORT_SIDE_INFEASIBLE`: N_MASTER_BEDROOM: pinwheel-realized short side 3.10 m (gross) < 3.0 m (net) + 0.3 m inset margin
- **brief-06, path B** (L) — refusal code `SHORT_SIDE_INFEASIBLE`: HALL: row-realized short side 1.20 m (gross) < 1.0 m (net) + 0.3 m inset margin

Every refusal above is the REAL outcome for that brief on that path — no refusal here was retried past this script's own disclosed scale ladder (`run_demo._RETRY_SCALES`, up to 9 attempts) and no refused plan was substituted for a different, easier brief.

## C30/C31 — the unchanged validator chain, including furnishability (AC-3)

C31 ("public rooms reachable without crossing a furniture-blocked path") is already wired into `validate()` and ran, unchanged, for every path-B REALIZED attempt above (one brief's own path-B attempt refused specifically ON C31 — see "Refusal detail"). C30 ("rooms are furnishable") is NOT wired into `validate()` — a standalone, documented maintainer scope decision (`app.vertical_slice.validation.check_furnishability`'s own docstring: disclosure-only, not a hard gate, pending an `interior_layout.py` placement fix out of this Issue's scope) — so it is called directly here and disclosed, never silently skipped:

| # | brief | path B C30 (furnishable) | detail |
|---|---|---|---|
| 0 | brief-00 | DISCLOSED — not all rooms furnishable | S_DINING: DINING_TABLE |
| 1 | brief-01 | DISCLOSED — not all rooms furnishable | S_MASTER_BEDROOM: BED |
| 7 | brief-07 | DISCLOSED — not all rooms furnishable | S_DINING: DINING_TABLE |

## Aggregate numbers (AC-5)

- **Path A**: 8/8 realized, 0/8 refused.
- **Path B**: 3/8 realized, 5/8 refused.

Path B refusal codes: `NO_USABLE_ROOMS` x1, `SHORT_SIDE_INFEASIBLE` x3, `VALIDATION_FAILED` x1

### M1-M6, median over REALIZED plans per path

| metric | path A (n=8) | path B (n=3) |
|---|---|---|
| M1 habitable aspect (median) | 1.655 | 1.589 |
| M2 habitable-on-envelope ratio | 1.000 | 1.000 |
| M3 circulation share | 0.113 | 0.213 |
| M4 hall door count | 6.000 | 6 |
| M4 hall aspect (median) | 9.786 | 2.678 |
| M5 wet adjacency ratio | 0.000 | — |
| M6 public zone contiguous (count) | 8/8 | 0/3 |

These are the SAME `QualityMetrics` fields (`app.vertical_slice.quality_metrics`) `to_demo_design` computes for every plan on main today — read here off the identical `quality.metrics` object the shipping API already returns, never recomputed.

Two patterns in this table are disclosed limitations of THIS SCRIPT's own placement heuristic, not a fact about the realizer's geometric capability: **M5 is always "—" for path B** because wet rooms (BATHROOM/TOILET) and SAFE_ROOM are deliberately excluded from every path-B construction (`stage1_gate.py`'s own disclosed simplification, reused here — C17/C29 need a `ResolvedWetRoom` list this script does not reconstruct), so there is never a wet room to measure adjacency for. **M6 (public zone contiguous) is 0/3 for path B vs 8/8 for path A** because this script's PINWHEEL/TWO_WING placement picks the N/S/W arms by real room AREA alone, with no notion of "public zone" semantics at all — an unrelated bedroom can as easily land in the arm next to LIVING as DINING can. This is a placement-heuristic gap, not a claim that the realizer's geometry cannot host a contiguous public zone.

### Non-rectangular counts (AC-5)

**Contract-level** (a room whose `DemoDesign.rooms[].shape` is not `RECTANGLE`/unset, or a plan whose `DemoDesign.footprints` has more than one wing — the SAME predicate applied to the SAME `DemoDesign` shape both paths produce):

- Path A: 3 non-rectangular room(s) across 8 realized plans; 0 plan(s) with a non-rectangular envelope.
- Path B: 0 non-rectangular room(s) across 3 realized plans; 1 plan(s) with a non-rectangular envelope.

**Construction-level ground truth, path B only** (disclosed separately because `to_demo_design` only recognises the LIVING+KITCHEN 2-way merge's own `shape='L'` convention — it does not yet expose the realizer's general N-way notch-carve group as a single polygon room in the contract, so the contract-level room count above UNDERCOUNTS an L/U family's real, validated, non-rectangular room; visually the plan still draws correctly, since the notch's own cell boundary is a real `WallType.OPEN` interface, not a missing wall):

- 0 genuinely-merged notch-carve room(s) (`RealizedLayout.groups`, non-empty means a true L/U/T polygon, not a placeholder) across the 3 realized path-B plans.
- 1 plan(s) with a genuinely non-rectangular TWO_WING envelope (2 wings of different heights, a real seam — already visible at the contract level above via `footprints`).
- PINWHEEL (its own family, 3 of the 8 path-B attempts) contributes ZERO to either count on purpose: every pinwheel arm is an ordinary rectangle tiling a rectangular envelope — its non-guillotine fact is about internal wall TOPOLOGY (it cannot be built by straight full-width/full-height cuts), not about room or envelope SHAPE, which is what this Issue's AC-5 asks for.

## Reproducing this report

The first command below (backend) was run to produce this exact file and IS verified end to end in this session. The second command (frontend) was NOT run or verified in this session — this worktree has no `frontend/node_modules` installed and `npm install` is outside this headless session's approved command surface; it needs a normal frontend environment/CI to confirm.

```
cd backend
uv run python -m spikes.two_path_demo.run_demo
cd ../frontend
npm test -- twoPathDemoComposites
```
