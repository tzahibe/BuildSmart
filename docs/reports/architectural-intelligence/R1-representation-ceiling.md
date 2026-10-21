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

*Not yet run.* This section, the per-plan table, the aggregated blocking checks and the verdict are
added in the commit that follows the run.
