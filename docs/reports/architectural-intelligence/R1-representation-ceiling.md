# R1 — the representation ceiling (Issue #242, ROOT #237)

**Question.** Can `realize_cells` plus the **unchanged** validators carry 19 real professional
residential plans? If yes, the representation may evolve and the concept layer is what needs
redesign. If no, the representation is the blocker and #238's decision is revised. This is §8.6's
single measurable, reversible experiment.

**Status of this document.** Sections 1–7 are the **pre-registered** design: they were committed,
together with the frozen constants in `backend/app/ai_harness/representation_ceiling/frozen.py`,
**before the first realizer run on any real plan**. Section 8 (results) and the verdict were added
afterwards, in a later commit; the git history shows the order. Nothing in 1–7 was edited after the
run.

Harness only: `backend/app/ai_harness/representation_ceiling/` (self-contained; nothing outside
`ai_harness/` imports it), its test `backend/tests/ai_harness/test_representation_ceiling.py`, and
this report. No production file, no flag, no dependency, no solver, no model, no network. Deleting
those three paths restores the tree.

Reproduce: `cd backend && uv run python -m app.ai_harness.representation_ceiling.run <out_dir>`
(single process, deterministic).

---

## 1. The fixtures (AC-2)

`backend/tests/spikes/fixtures/geometry_shapes/plans/` holds **20** plan fixtures. Exactly one is
**synthetic**: `synthetic-spine-01.json` (`provenance.source_dataset = "SYNTHETIC"`, 4 rooms, 18 m²).
It is identified **by name and, independently, by provenance**; the loader raises if the two
disagree, and raises unless exactly 19 remain. The 19 real plans (ResPlan, Abouagour & Garyfallidis
2025, CC BY 4.0) are: `0, 1, 6, 7, 10, 14, 17, 18, 19, 24, 25, 29, 30, 31, 47, 1080, 1110, 1263,
13578`.

## 2. The role-mapping table (AC-1)

ResPlan room label → `ProgramRole`; complete over every label that occurs in the 19 plans
(BEDROOM 55, BATHROOM 44, LIVING 39, KITCHEN 17, CIRCULATION 16, TOILET 10, STORAGE 2 in the 20
fixtures).

| ResPlan label | `ProgramRole` | note |
|---|---|---|
| LIVING | LIVING | |
| KITCHEN | KITCHEN | |
| BEDROOM | BEDROOM | the **largest** bedroom of a plan with ≥ 2 bedrooms is MASTER_BEDROOM (ResPlan has no master label; ties → smallest id) |
| BATHROOM | BATHROOM | kind declared from the plan's door graph, §5 |
| TOILET | TOILET | declared GUEST_WC |
| STORAGE | STORAGE | |
| CIRCULATION | HALL | the product's own circulation role; the arrival-room policy ranks HALL first and C20/C21/C26 treat it as circulation |

Each zone's bounds are the **product's** for that role: its `ROOM_TEMPLATES` row — minimum area,
the template's target, the **hard** maximum C21 gates on, minimum short side, maximum aspect. No
bound is loosened and none is derived from the plan being tested.

## 3. Conversion — one code path, no per-plan branch

ResPlan rooms are interior regions separated by wall thickness (0.15–0.23 m), so they do not tile.
The frozen conversion:

1. **Drop slivers.** A ResPlan "room" under **1.5 m²** (the smallest role minimum in
   `ROOM_TEMPLATES`, STORAGE) is a segmentation artefact — the 0.02–0.4 m² `LIVING_1`/`LIVING_2`
   fragments — and is not in the plan.
2. **Snap wall faces onto shared lines.** All vertex coordinates of the kept rooms are clustered per
   axis (greedy from the low end; a cluster takes a value within 0.30 m of its last member and
   0.60 m of its first); every member moves to the cluster mean rounded to the 0.05 m grid. The two
   faces of one wall land on one line.
3. **Make a tiling.** A room that still overlaps an earlier one (id order) loses the overlap; a
   room in several parts keeps its largest; a room under 1.5 m² afterwards is dropped; a
   non-axis-parallel edge refuses the plan (`REPR-RECTILINEAR`). Every such event is recorded per
   plan. The footprint is the **union of the snapped rooms**; holes (unlabelled space) stay holes.
4. **Wings.** The union is cut at every y where its horizontal profile can change and vertically
   adjacent slabs of equal x-extent are merged: a rectangle is one wing.
5. **Orientation.** The plan's declared entrance side is unknown for 5 of 19 plans and a coarse
   position (not a wall) for the rest, so it is **not used**. The street is the realizer's own
   y-min wall; each plan is tried at 0, 90, 180 and 270° (no mirror) and is **carried when any
   rotation carries**. A refused plan reports the rotation with the fewest failing checks (a run in
   which the validators ran ranks before one that stopped earlier; ties → smallest rotation).
6. **Doors.** The plan's own `access_edges` (every one is of kind `DOOR`) between kept rooms.
   A pair that does not touch after conversion is dropped by the realizer and is not patched.

## 4. The two arms (AC-3) and one diagnostic

* **Arm 1 — each room a single rectangle.** The room itself when it is a rectangle; otherwise its
  **largest inscribed axis-aligned rectangle** inside one wing. Whatever the rectangle does not
  cover is residual interior area, which C2 judges. Same wings as arm 2.
* **Arm 2 — each room a group of same-zone `OPEN`-walled cells.** A room is the cells of its slab
  decomposition per wing; more than one cell is a group: ids `ZONE__c0…`, role = the zone's role,
  a permissive per-cell `ZoneSpec` (exactly as `realize_layout` gives a notch-carve zone's cells),
  an `OPEN` wall between touching fragments, and the zone's **real** bounds checked on the union by
  the existing `_group_checks` (GROUP-C2/C3/C20) and the polygon-room C27′. Cells on a wing boundary
  are additionally split where the facing wing starts and stops, so every seam side is abutted
  along its whole length or not at all (C22 rejects a partial seam). Geometry does not move.
* **Arm 2R — diagnostic, not scored, cannot change the verdict.** Arm 2 plus a refinement that
  splits cells until every cell side is fully shared or fully exterior (the realizer types a side
  with one wall type). It exists so that a STOP cannot be mistaken for a conversion artefact.

**Why arm 2 does not call `realize_cells` directly.** `realize_cells` declares `groups = {}` and
`open_pairs = set()` and says so in its docstring ("No groups, so no polygon rooms"). The group
mechanism lives in `realize_layout`'s notch-carve path, which only builds L/U/T. `realize.py` is
`realize_cells` with groups and nothing else: the same private helpers, the same `validate`,
`generate_interior_doors`, `resolve_entrance`, `generate_windows`, `check_furniture_feasibility`,
`assemble`, and the same gate (`report.ok and c27.passed and all group checks`). It returns every
failing check id (the original joins the first five into a string). With no groups it must agree
with `realize_cells`: `test_wrapper_agrees_with_realize_cells_when_there_are_no_groups`.

## 5. Wet rooms

C17 fails closed on any BATHROOM/TOILET zone that no `ResolvedWetRoom` covers ("kind unknown — no
requirement covers it"), so leaving them undeclared would refuse every plan on C17 and measure
nothing about the representation (found on a synthetic layout, before any real plan was run).
ResPlan carries no kind, so it is read off the plan's own door graph: a BATHROOM whose every door
leads to exactly one bedroom is an ENSUITE of that bedroom; a TOILET is a GUEST_WC; any other
BATHROOM is a SHARED_BATHROOM. Strength REQUIRED. A wet room that is several cells declares each
cell with the zone's kind.

## 6. Validators and the thresholds (AC-5, AC-6)

**Validators exactly as they are.** `validate()` (C1–C33 as it runs), C27 via
`check_realized_dimensions`, `_group_checks`. A refusal is the result. No check, bound, tolerance,
wall rule or threshold is relaxed to carry a plan; if a check cannot be satisfied the plan is
refused and the check id recorded. A **plan is carried** only when `validate` passes in full.

**Thresholds, fixed now and not reinterpretable** (`frozen.verdict`):

| verdict | condition |
|---|---|
| **GO** | arm 2 carries **≥ 13 of 19** *and* gains **≥ 6** plans over arm 1. The representation can evolve; the concept-layer inversion is authorized. |
| **PIVOT** | arm 2 carries **7 to 12**. Neither conclusion is claimable; the top blocking check becomes the next single piece of work; no concept work starts. |
| **STOP** | arm 2 carries **≤ 6**, *or* at least **3 of C27, C9, C14, C30** each fail on **more than half** the plans (≥ 10 of 19; per plan, on the reported rotation, refused plans only). The representation is the blocker; #238's decision is revised. |

Order: STOP, then GO, then PIVOT. Arm 2 is the deciding arm; arm 2R never enters. One case the
Issue leaves open — arm 2 carries ≥ 13 but gains fewer than 6 over arm 1 — is classified **PIVOT in
advance** (GO's conditions are not met; no concept work may start).

The **top blocking check** is the check id that fails on the most refused plans in arm 2 (ties:
reported with the count of plans where it is the *only* failing check).

## 7. The pre-registered expectation

Written before any real plan was realized. What I expect, with the evidence it rests on:

* **Arm 1: 0 of 19** (0–1). Every one of the 19 converted plans has at least one non-rectangular
  room (1–6 per plan, 59 of 158 rooms), and one rectangle per room leaves residual area, which
  is C2. The residual also starves C3/C13/C5 on the rooms it shrinks.
* **Arm 2: about 2 of 19** (0–5). The realizer's own comment records that splitting a cell into
  same-zone fragments "was tried and measured: C20/C9/C24/C31 run per cell and reject the
  fragments". Real footprints are ragged (3–15 wings per plan after the slab cut), so I expect
  C22 (seams) and C20/C9 (thin fragments) to dominate, with C17 on wet rooms that arrive as
  several cells and C5/C13 where the plan's own doors do not survive the conversion. Plan `1263`
  has **no door edges at all** in the fixture and will fail C5 whatever the representation does.
* **Verdict: STOP most likely (~75 %), PIVOT (~20 %), GO (< 5 %).**
* **Top blocker:** one of C22, C20, C9; C22 my first guess.
* **What would surprise me:** arm 2 ≥ 7; C27 or C14 among the top three; arm 2R carrying markedly
  more than arm 2 (that would say the verdict is sensitive to how finely I cut, not to the
  representation).

**Known limits of the design, stated in advance.** The conversion is a choice (snapping tolerance,
sliver threshold, slab wings, master rule, wet-kind inference); a different conversion could carry
more or fewer plans. The product's templates are *product policy*, not regulation, so "refused"
means "refused by this product's validators", which is exactly the question. Plan `1263` is refused
by its data, not by the representation. Rotations (4) give each plan four attempts; mirrors are not
tried. One run, one machine, no timing is claimed.

---

## 8. Results

Everything below is from `uv run python -m app.ai_harness.representation_ceiling.run <dir> A`
(pipeline A, the pre-registered one) unless a pipeline letter says otherwise. Data:
`data/R1-results.json` and `data/R1-tables.md` (A); `-B`, `-C`, `-D` for the sensitivity runs.

### 8.0 What happened between the freeze and the numbers (deviations, in order)

1. **`realize_cells` raises `IndexError` on a wing that holds no cell** (`_leaf_chain` of an empty
   tuple). Arm 1 produces such wings: its inscribed rectangle sits in one wing and the footprint of
   another is left uncovered. The wrapper now refuses before any validator runs, with the code
   `EMPTY_WING` ("footprint no room covers" — the residual interior area C2 judges). Arm 1's
   refusals on 17 plans carry this code instead of a C-number; the two plans where it did not
   occur show the validators' own answer (C2 among them). No other behaviour changed.
2. **Pipeline A has a conversion defect, found by reading the first run's C5 details.** The
   fixture's `access_edges` holds only two-room doors; a wide opening that lists LIVING, KITCHEN
   and the sliver rooms (`doors[].room_ids` of length 3–4, in plans 0, 24 and others) contributes no
   edge, so the kitchen is unreachable. **Pipeline B** reads every `doors[].room_ids` as well. A is
   kept as the pre-registered run and carries the verdict; B is reported beside it.
3. **Added after seeing A, none of them able to change the verdict** — arm 2R's thin-cell and
   per-check "rooms/cells it names" counts, the fragment oracle (§8.5), and pipelines C and D (wider
   wall-face snapping). They are in the table because a STOP on 0 of 19 invites the question
   whether it is an artefact of how this harness cuts rooms.
4. **Erratum to §7.** It says 59 of 158 rooms are non-rectangular; the correct count in the
   converted tiling is **63 of 158** (an arithmetic slip; no threshold uses it). §7's guess that
   C22 would be the top blocker was wrong (§8.3).

### 8.1 Per plan, per arm (AC-3) — pipeline A

"Carried" needs `validate` to pass in full; the reported rotation is the one with the fewest
failing checks. No plan was carried by any rotation in any arm. Non-rect = rooms of the converted
tiling that are not a rectangle.

| plan | rooms kept / dropped | non-rect | arm 1 — one rectangle per room | arm 2 — same-zone OPEN cells, group-checked |
|---|---|---|---|---|
| 0 | 8 / 2 | 3 | refused: EMPTY_WING | refused: C17, C19, C20, C24, C28, C31, C5, C8, C9 |
| 1 | 8 / 2 | 3 | refused: EMPTY_WING | refused: C13, C17, C19, C20, C24, C28, C3, C31, C5, C7, C8, C9 |
| 10 | 6 / 0 | 4 | refused: EMPTY_WING | refused: C17, C19, C20, C24, C28, C8, C9, GROUP-C3 |
| 1080 | 9 / 3 | 4 | refused: EMPTY_WING | refused: C19, C20, C24, C25, C26, C28, C31, C5, C8, C9, GROUP-C3 |
| 1110 | 11 / 2 | 4 | refused: EMPTY_WING | refused: C17, C19, C20, C24, C25, C26, C5, C8, C9, GROUP-C3 |
| 1263 | 10 / 2 | 5 | refused: EMPTY_WING | refused: C17, C19, C20, C24, C25, C26, C3, C5, C8, C9, GROUP-C3 |
| 13578 | 8 / 0 | 3 | refused: EMPTY_WING | refused: C17, C19, C20, C24, C25, C26, C5, C8, C9, GROUP-C3 |
| 14 | 6 / 0 | 4 | refused: EMPTY_WING | refused: C17, C19, C20, C24, C31, C8, C9, GROUP-C3 |
| 17 | 8 / 1 | 4 | refused: EMPTY_WING | refused: C13, C17, C19, C20, C24, C3, C31, C5, C7, C8, C9, GROUP-C3 |
| 18 | 9 / 1 | 3 | refused: C17, C2, C21, C22, C24, C3, C5 | refused: C19, C20, C21, C24, C28, C3, C31, C5, C8, C9, GROUP-C3 |
| 19 | 8 / 1 | 4 | refused: C17, C2, C22, C24, C3, C5, C9 | refused: C19, C20, C24, C31, C5, C8, C9, GROUP-C3 |
| 24 | 8 / 2 | 1 | refused: EMPTY_WING | refused: C17, C19, C20, C24, C28, C31, C5, C8, C9 |
| 25 | 8 / 2 | 2 | refused: EMPTY_WING | refused: C17, C19, C20, C24, C31, C5, C8, C9 |
| 29 | 8 / 0 | 3 | refused: EMPTY_WING | refused: C17, C19, C20, C24, C28, C31, C5, C8, C9, GROUP-C3 |
| 30 | 8 / 0 | 3 | refused: EMPTY_WING | refused: C17, C19, C20, C21, C24, C28, C31, C5, C8, C9, GROUP-C3 |
| 31 | 8 / 2 | 1 | refused: EMPTY_WING | refused: C17, C19, C20, C24, C28, C31, C5, C8, C9, GROUP-C3 |
| 47 | 9 / 1 | 2 | refused: EMPTY_WING | refused: C19, C20, C24, C3, C31, C5, C8, C9, GROUP-C3 |
| 6 | 10 / 0 | 4 | refused: EMPTY_WING | refused: C17, C19, C20, C21, C24, C28, C3, C31, C5, C8, C9, GROUP-C3 |
| 7 | 8 / 0 | 6 | refused: EMPTY_WING | refused: C19, C20, C24, C26, C31, C5, C8, C9, GROUP-C3 |

**Carried: arm 1 = 0 of 19, arm 2 = 0 of 19, arm 2R (diagnostic) = 0 of 19.** The per-check
detail text of every refusal (which room, which dimension) is in `data/R1-results.json`.

### 8.2 The blocking checks, aggregated (AC-4) — arm 2, pipeline A

| check | refused plans failing it | of which it is the only failure | rooms/cells it names | of which cells of a multi-cell room |
|---|---|---|---|---|
| **C9** furniture envelope | **19** | 0 | **364** | 361 |
| C20 template aspect | 19 | 0 | 196 | 196 |
| C24 access-rules table | 19 | 0 | 227 | 207 |
| C8 daylight | 19 | 0 | 103 | 103 |
| C19 exterior wall | 19 | 0 | 94 | 94 |
| C5 reachability | 17 | 0 | 146 | 132 |
| C31 public-zone path | 15 | 0 | 68 | 68 |
| GROUP-C3 merged-zone area | 15 | 0 | 15 | 0 |
| C17 wet-room access | 14 | 0 | 52 | 47 |
| C28 door clearance | 10 | 0 | 20 | 20 |
| C3 area/short side | 6 | 0 | 9 | 0 |
| C26 corridor | 5 | 0 | 8 | 0 |
| C25 entrance pocket | 4 | 0 | 4 | 4 |
| C21 / C13 / C7 | 3 / 2 / 2 | 0 | 3 / 3 / 3 | 2 / 3 / 3 |

**Top blocking check: C9.** Five checks tie at 19 of 19 plans, and the pre-registered tie-break
(plans where the check is the *only* failure) is 0 for every check, because no plan fails fewer
than eight checks. The tie is therefore broken by a secondary key chosen after the run and disclosed
here: the number of rooms/cells the check names. C9 names 364, C24 227, C20 196, C8 103, C19 94.
C20, C8, C19, C31 and C28 name **only** cells of multi-cell rooms; C9 names them in 361 of 364
cases; C24, C5 and C17 name both cells and whole rooms. Arm 1's blocking check is `EMPTY_WING` (17 plans, the only failure on each); on the two
plans where the validators ran, C2, C22, C24, C3, C5 and C17 fail.

Of the four checks in the STOP clause, C9 fails on 19 plans (> half); **C27, C14 and C30 fail on
none.** The clause "at least 3 of C27, C9, C14, C30" is therefore **not** what produces the STOP.

### 8.3 The verdict (AC-5)

> **verdict: STOP.** Arm 2 carries **0 of 19** (threshold: 6 or fewer). Arm 1 carries 0. Gain 0.
> By the thresholds fixed in §6 the representation is the blocker and #238's decision is revised.

No threshold, check or bound was reinterpreted after the run. The verdict is computed by
`frozen.verdict`, covered by `test_the_verdict_applies_the_frozen_thresholds`, and the committed
data is checked against it by `test_the_committed_results_are_consistent`.

**Against the pre-registered expectation (§7):** arm 1 = 0 (predicted 0–1) ✓; arm 2 = 0 (predicted
about 2, range 0–5) ✓ within range; verdict STOP (predicted most likely) ✓; top blocker: predicted
"one of C22, C20, C9, C22 first" — C9/C20 are in the list, **C22 was wrong** (it fails only in arm 1,
on two plans). Nothing on the "would surprise me" list happened: arm 2 did not reach 7, C27 and C14
did not appear, and arm 2R did not carry more than arm 2.

### 8.4 Is the STOP an artefact of this harness? Sensitivity (not scored)

| pipeline | what differs from A | arm 1 | arm 2 | arm 2R | verdict | top check | refused arm-2 plans that also fail on something that is not a cell of a multi-cell room |
|---|---|---|---|---|---|---|---|
| **A** (pre-registered) | — | 0 | 0 | 0 | **STOP** | C9 (19) | 18 of 19 |
| B | + doors from every `doors[].room_ids` | 0 | 0 | 0 | STOP | C9 (19) | 18 of 19 |
| C | B + wall-face snapping 0.60 / 1.20 m (twice the frozen) | 0 | 0 | 0 | STOP | C9 (19) | 19 of 19 |
| D | B + snapping 0.90 / 1.80 m (three times) | 0 | 0 | 0 | STOP | C9 (19) | 19 of 19 |

Under D the plans have been pushed so far toward rectangles that only 30 rooms are still
non-rectangular (A: 63), and still no plan is carried. A positive control shows the harness
can carry a plan: the six-room synthetic house in
`test_wrapper_agrees_with_realize_cells_when_there_are_no_groups` is carried by the wrapper and by
the product's own `realize_cells`, and a variant with a 1 m bathroom is refused by both.

### 8.5 The fragment oracle (post-run, not scored): is fragmenting the blocker whatever the cut?

C9, C20, C19, C8 run on **every cell as if it were a room**; the group checks add a union check
but do not replace them. So a room that is not a rectangle must be judged cell by cell. This asks,
optimistically (gross dimensions, no wall insets, nothing about neighbours or the exterior), whether
**any** rectangle partition of a non-rectangular room passes C20's aspect bound and C9's envelope
(exhaustive over the room's own coordinate grid; `oracle.py`).

| role (pipeline A) | non-rectangular rooms | some partition passes |
|---|---|---|
| BEDROOM | 21 | **0** |
| MASTER_BEDROOM | 11 | **0** |
| KITCHEN | 3 | **0** |
| BATHROOM | 2 | **0** |
| LIVING | 18 | 1 |
| HALL (circulation, exempt from both) | 8 | 8 |

Of the 55 furnished non-rectangular rooms, **1** admits any partition at all — under any wing
choice, cut order or refinement. Most of them are a rectangle with a notch of 0.3–0.9 m (a duct, a
column, a jog), and every partition of such a room contains a strip no bed or sofa fits in. (With
the snapping of C/D the counts are 50 and 25 furnished rooms, of which 2 and 4 pass.)

### 8.6 What the data supports, and what it does not

* **Supported.** Under the unchanged validators, the cell representation with same-zone groups
  carries none of the 19 real plans, in any arm, rotation or pipeline run here. The cause is not
  the choice of cut: for 54 of 55 furnished non-rectangular rooms no rectangle partition can pass
  the per-cell aspect and envelope checks even optimistically. `_group_checks` validates the union
  of a group but C9, C20, C19, C8, C31 and C28 still judge each fragment as a room.
* **Also supported, and not the representation's doing.** In 18 of 19 plans (arm 2, A) something
  that is not a fragment also fails: C24 refuses a bedroom door opening straight onto the living
  room (the access-rules table), GROUP-C3/C3/C21 refuse bedrooms of 5.1 m² or 24–28 m², a
  bathroom of 3.7–4.4 m² and a 66 m² living room against `ROOM_TEMPLATES`, C17 refuses a
  bathroom between two bedrooms and a WC off a bedroom, C26 refuses 7–40 corridor dead ends in
  five plans. So "validators unchanged" is itself a strong condition: independent of the
  representation, today's policy tables refuse something in 18 of these 19 plans (a count of
  plans with at least one non-fragment finding, not a count of plans a perfect representation
  would still lose). That is a statement about the policy, not about whether it is right.
* **Not supported.** That a different representation (a polygon room, a room that owns its cells'
  checks) would carry these plans — nothing here ran one. That the product's policy tables are
  wrong for real plans — they encode product decisions and were applied as written. That 19 plans
  from one dataset, one conversion and one machine are representative; plan `1263` has no door
  edges in its fixture and is refused for that reason in A.
* **Not claimed.** No timing, no quality score (that is #240), no concept generation (that is
  #239).

### 8.7 Reproduce and verify (change-impact check)

```
cd backend
uv run python -m app.ai_harness.representation_ceiling.run <out_dir> A   # the verdict; B, C, D: sensitivity
uv run pytest -q tests/ai_harness/test_representation_ceiling.py
uv run pytest -q tests/ai_harness                                         # AC-7: 233 passed, 44 skipped
```

* **Producer / consumers.** The harness produces `data/R1-results*.json` and `R1-tables*.md`; the
  only reader is `test_the_committed_results_are_consistent`, which loads the real files the way a
  consumer would and recomputes the verdict with `frozen.verdict`. Nothing in `backend/app/`
  outside the harness imports it (`test_nothing_outside_the_harness_directory_imports_it`).
* **Contract.** Issue #242's ACs; the thresholds in §6 are `frozen.py`'s, unedited since the
  freeze commit `bbffde3`.
* **Defaults / fallbacks.** No silent fallback: a conversion that cannot state a plan returns a
  typed `REPR-*` refusal (none occurred); an empty wing is a named refusal; the sensitivity
  pipelines are opt-in letters, and `PIPELINES["A"]` is pinned by
  `test_the_default_pipeline_is_the_pre_registered_one`.
* **Cross-issue.** #239 (concepts) and #240 (blind review) start from this verdict; the lead
  decides what STOP revises in #238. The product's validators, safety rules and compliance
  constraints were imported, never modified (`test_the_harness_modifies_no_validator_or_production_module`).
