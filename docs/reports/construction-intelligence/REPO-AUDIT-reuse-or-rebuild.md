# Repository audit — reuse or rebuild for a plan-understanding and measurement engine

**Issue #257, first child of ROOT #256 (owner directive 2026-10-26, P0). READ-ONLY: no product
code changed, no dependency added, no model call, no paid service, no deploy.**

Every claim below was read from the code in worktree `/Users/mymacbook/projects/sddproject-e1`,
branch `investigate/construction-intelligence`, at `c07bf71` (`origin/main`), or is cited to an
existing report with its file, or is labelled **unverified** with what would settle it (§11). The
only command run against the product was the static import check
(`OPENAI_API_KEY=not-a-real-key-ci-only python -c "import app.main"` → `STATIC-IMPORT-OK`). No
solver, no corpus suite, no benchmark: the audit needed reading, not running.

ROOT #256 names three findings as already established and instructs that they be cited rather than
re-derived. §12 does that. Everything else is new.

---

## 0. The answer, in one page

**The question the owner is actually asking** is not "what code exists" but **where the current
structures carry a real dimension someone would spend money on, and where they carry only a
drawing's geometry.** §1 states the test used throughout, and here is the result.

**The line, in one sentence.** This repository carries **plan-view length and area to
construction-grade discipline, and nothing else a bill of quantities multiplies them by.** Every
room, wall, door and window is metric, closed, and internally cross-checked
(`validation.py` C2 proves the rooms' area sums to the footprint's as an **exact integer identity**
in 5 cm grid units, `:327`; C27 proves every displayed width x depth equals its own declared area
within 0.05 m², `:159-199`). But there is **no third dimension anywhere in the product** — no
ceiling height, no wall height, no window sill or head, no storey height; the only `height_m` in
`app/` is a plan-view y-extent in a harness (`ai_harness/topology_poc/placement_bridge.py:178`) —
and **no material**: a repo-wide grep for a construction material in `backend/app/` returns zero
(every "material" hit is the adverb "materially"). A wall is `(orientation, coord, start, end,
thickness_m, wall_class)` (`vertical_slice/walls.py:70-94`). That is a complete linear-metre
schedule and **half** of a square-metre one.

**The second line, which matters more.** The numbers are **real in unit and closed in arithmetic,
but they are the engine's own invention, not a measurement of anything.** Wall thickness is a
two-value constant table — `EXTERIOR 0.30`, `PARTITION 0.10`, `RC_SAFE_ROOM 0.30`
(`geometry_core/model.py:104-109`), the last one carrying the comment `PARAMETER · UNVERIFIED
(regulation)`. Every room size in `ROOM_TEMPLATES` is labelled by its own code as
`DEMO PRODUCT POLICY placeholder, NOT verified regulation` (`concept_generator.py:142+`). Setbacks
default to `0.0` because, in the module's own words, *"any non-zero default is a planning
determination this project has not made"* (`demo/site_geometry.py:38-41`). Doors are 0.8 / 0.9 /
1.0 m by role (`access_rules.py:44-48`); windows 0.5–2.0 m by room class (`windows.py:43-67`). A
quantity surveyor can use the **arithmetic**; he cannot use the **figures**, because nothing
measured produced them.

**The third line, which is the good news.** The repository already contains the two things a
measurement engine is hardest to retrofit with — built for the general-geometry architecture
report's own concerns, and reading now exactly as a measurement engine's:
**element-level provenance** (`geometry_domain/provenance.py` — `Source` already enumerates
`SURVEY`, `CAD`, `GIS`, `REGULATION`, `INFERRED`; `Authority` separates
`AUTHORITATIVE / INDICATIVE / ASSUMED`; `weakest_of` propagates pessimistically and treats an
absent provenance as `ASSUMED`), and **direction-aware quantization** (`geometry_domain/units.py` —
`length_units_no_overstate`, `clearance_units_no_understate`, a required keyword-only `rounding`
argument and an unsafe mode spelled `NEAREST_UNSAFE` so it cannot be chosen quietly). Those two
files, 158 lines together, are the measurement engine's ethics already written down. Both are live
and imported by production (`demo/service.py:32-33,245-251`).

**The AI layer is three text calls and a gateway pattern** (§6). Exactly three model integrations
are unconditionally live in production — `OpenAIRequirementParser` (`requirements/parser.py:422`)
and the two chat calls (`chat/intent.py:182`, `chat/assistant.py:65`), all `gpt-5-nano`, all
**unstructured language in, typed structure out with a provenance tag per field**. That is the right
shape for reading a plan's *words*, and nothing in production has ever been handed an image.
`app/architect/`'s gateway is a reusable three-provider pattern whose default (`mock`) makes no model
call at all; `app/vertical_slice/brain/` is production-reachable and contains **no model whatsoever**;
`app/knowledge/`'s genuine hybrid-retrieval stack has **no production importer** and indexes the
repository's own markdown with a non-semantic `hash` provider by default. #245's warning is
confirmed concretely: the wiring table's guard is a hardcoded list of 89 paths with **zero** entries
under `brain/` (§6.1), so every reachability claim here was read from imports.

**Import paths for PDF, image or CAD: there are none, and none ever existed** (§5). Zero
dependency, zero import, zero route, on any of the repository's 71 branches and nowhere in git
history. `python-multipart` is absent from `backend/uv.lock`, so the FastAPI backend physically
cannot accept a multipart upload; `backend/app/projects/routes/media_routes.py` is a mounted router
with zero routes and a comment saying so. The frontend has no `type="file"`, no `FormData`, no
`FileReader`, no drop handler. **The repository has never read a drawing.**

**What the repository does read** is one already-vectorised dataset. `ResPlan → PlanReference`
(#94/#95) is real, and it is the most pivot-relevant asset here — but with two corrections to how
ROOT #256 frames it. First, the **producer is not on `main`**: `plan_reference.py`,
`resplan_ingest.py`, `retrieval.py`, `patterns.py`, `synthesis.py` and `adaptation.py` exist only
in git on `agent/110-...` (§2.4), and `backend/spikes/architectural_brain/` does not exist at
`c07bf71`. What is on `main` is the **output**: 20 JSON fixtures and two priors readers. Second,
its input is a **vector dataset with a stated real area**, not a drawing: *"ResPlan geometry is in
PIXEL coordinates on a plan-specific grid; `plan["area"]` is the real gross area in m²"*
(`resplan_ingest.py:5-6` on that branch). Normalising a vector dataset is not reading a plan.

**The central question (§9), answered directly.** **No — not the engine. Yes — most of the
geometry layer underneath it, and only as a library.** The strongest evidence against is measured,
not argued: **#242's R1 experiment pushed the 19 real plans through `realize_cells` and the
unchanged validators and carried 0 of 19, in both arms and all four pipelines**, with a verdict of
STOP against thresholds frozen before the run; an exhaustive oracle showed **54 of 55 furnished
non-rectangular rooms admit no rectangle partition at all** that passes C20 and C9. The measurement
is real; the PR carrying it (#254) was **closed unmerged**, so it is cited here as measured-but-not-
on-`main` (§12.3). The strongest evidence for is also measured: the same validators already
compute, per plan, every linear and areal quantity a take-off starts from, and the payload already
ships them to a renderer that draws nothing it was not given.

**What must be built from nothing: roughly 8–11k lines of new code plus two data assets the
repository has no analogue of** (§10). The largest single item is not the geometry — it is that
**the arithmetic runs in the wrong direction**: today a validator *decides* whether a number is
acceptable, and a measurement engine must *report* the number with an uncertainty and refuse to
decide. §8.3 says what *isolate* means for the generator concretely, without deleting or disabling
anything.

---

## 1. The test used for every verdict below

A measurement engine produces numbers somebody will spend money on. Four properties decide whether
a number survives contact with a quantity surveyor. Each component in §8 is scored against them.

| # | property | what it means here |
|---|---|---|
| **P1 closure** | the parts sum to the whole, provably | room areas sum to the footprint; wall runs tile the envelope; nothing is lost or double-counted |
| **P2 unit discipline** | a unit, a precision, and a rounding *direction* | a length may never be rounded up; a clearance may never be rounded down |
| **P3 provenance** | where the number came from, and whether it may be relied on | surveyed vs inferred vs assumed, per element, not per object |
| **P4 dimensional completeness** | every dimension the priced item needs | a wall = length x height x thickness x construction; a door = width x height x leaf/frame; a finish = area x specification |

**P1 and P2 are present and strong. P3 has its type and its algebra, but almost no real instances.
P4 is absent: there is no vertical dimension and no material anywhere in the product.** That
single sentence is the audit's result, and the per-component verdicts in §8 are the elaboration of
it.

Where a verdict says a structure carries *only a drawing's geometry*, it means the structure is
sufficient to draw the plan correctly and insufficient to price what it draws.

---

## 2. What a plan *is* at each layer, and which layer a reader would target

### 2.1 The layers, bottom of the stack upward

#238's §1.2 gives the generator's stage-by-stage vocabulary and is not repeated. The table below is
the different cut this Issue needs: for each representation, **what it would mean to a reader**, and
whether its numbers are measurement-bearing.

| layer | type, file:line | numbers it carries | P1 | P2 | P3 | P4 | a reader's view |
|---|---|---|---|---|---|---|---|
| grid solver | `Rect(x,y,w,h: int)`, `geometry_core/model.py:39` (`UNIT_M = 0.05`) | integer 5 cm units; `area_m2()` at `:68` | exact (integer) | round-to-nearest by design | none | 2D only | **too coarse and too internal.** 5 cm quantization is the generator's own search grid; a surveyed plan is not on it |
| authoritative geometry | `Region` / `MultiRegion` / `Ring` / `Vertex` / `BoundaryEdge`, `geometry_domain/primitives.py` (492 L) | float metres, **arcs** (`arc_radius`, `arc_sagitta`, `arc_segment_area`, `bulge_from_three_points`) | boolean algebra in `booleans.py` (GEOS/shapely) | `units.py`, direction-aware | `provenance.py`, **per element** | 2D only | **this is the layer a reader should target.** It is the only one with provenance, curves and a boolean algebra, and it deliberately knows no solver (`geometry_domain/__init__.py:1-14`) |
| realized design | `GeometricDesign`, `vertical_slice/design_output.py:87-122` | metres; per room **both** a centerline `rect_m` and a net `(net_w_m, net_h_m, net_area_m2)`; `gross_area_m2` / `net_area_m2` for the building | C2/C27 | metres, 4 dp | none | 2D only | **the richest measurement payload in the repo.** Gross-vs-net at both room and building level is quantity-surveyor language |
| wall schedule | `Wall`, `vertical_slice/walls.py:81-94` | `thickness_m`, a straight `segment` (so length), `wall_class`, `zones`, `hosts` (door/window ids on this wall) | tiles the envelope | metres | none | no height, no material | **a real wall schedule, missing one axis.** See §3.2 |
| API payload | `DemoDesign`, `demo/contract.py:617-662` | everything above plus `thickness_m` per segment (`:139`), `shared_wall_length_m` (`:185`), `circulation_total_length_m` (`:223`), `usable_wall_length_m` (`:265`), `window_width_m` (`:279`) | C27 re-checked on displayed numbers | metres | `ConstraintOut.authoritative` (`:331`) | 2D only | **already a take-off feed**, for the quantities it has |
| normalised real plan | `PlanReference`, fixtures at `backend/tests/spikes/fixtures/geometry_shapes/plans/*.json` | per-room **polygon** in metres + `area_m2` + bbox `width_m`/`depth_m`; wall polygons; door/window polygons; `derived.wall_thickness_m`; `derived.scale_m_per_px`; `provenance{source_dataset, citation, licence, unit_type}` | footprint ring given, rooms do not provably tile it | metres, 4 dp | dataset-level, not per element | 2D only | **the only representation in the repo built to describe a plan somebody else drew** |

### 2.2 Which one a reader would target, and why

**`geometry_domain` is the target; `PlanReference` is the schema to extend.** The reasoning is
structural, not aesthetic:

* `geometry_domain` is the only layer with **per-element provenance** (`provenance.py:40-53`), which
  P3 requires and which cannot be retrofitted onto a tuple of floats later — a parcel with three
  surveyed edges and one edge a user dragged is the case that module's docstring exists to handle
  (`:1-8`).
* It is the only layer that can represent a **curve**: `BoundaryEdge` carries a DXF-convention
  bulge, and `arc_segment_area` exists (`primitives.py`). Real plans have curved walls; the grid
  solver cannot hold one.
* It **knows no solver and no law, by construction** (`__init__.py:5-9`, `constraints.py:11-18`), so
  pointing a reader at it does not drag the generator in.
* `PlanReference` already carries metric room polygons, wall polygons, opening polygons and a
  licence/citation — the schema shape a reader needs — and its own docstring states the discipline a
  measurement engine needs: *"Anything not measurably derivable from the source geometry is `None` /
  `"UNKNOWN"` — never guessed"* (`plan_reference.py:9-11`, on `agent/110-...`).

**What a reader must not target:** `Fixture` / `Concept` / `Cut.V|Cut.H` (`geometry_core/model.py:424`,
`vertical_slice/concept.py:76`). A slicing tree is guillotine by definition and #238 §7.2 item 3
records that **0 of 19 real plans are guillotine-separable**. A reader that goes through a slicing
tree has already thrown the plan away.

### 2.3 What the `PlanReference` fixtures actually contain

Read from `backend/tests/spikes/fixtures/geometry_shapes/plans/14.json` (schema identical across
the 20):

```
plan_reference.rooms[]    id, type, polygon (metric ring), area_m2, width_m, depth_m,
                          exterior_exposure[], exposure_known
plan_reference.walls[]    id, polygon              (5 connected components in this plan)
plan_reference.doors[]    id, polygon, room_ids[], is_exterior
plan_reference.windows[]  id, polygon, room_id, side
plan_reference.footprint  one metric ring (25 vertices in this plan)
plan_reference.entrance   room_id, side
plan_reference.derived    footprint_area_m2, scale_m_per_px, wall_thickness_m, room_type_counts
plan_reference.provenance source_dataset, source_plan_id, citation, licence, unit_type
plan_reference.access_edges[] / adjacency_edges[]  room_a, room_b (+ kind for access)
architectural_pattern     13 derived semantic fields (zoning, circulation_class, wet_core_strategy, ...)
```

**Measurement verdict.** Room polygons, wall polygons and opening polygons in metres are
genuinely measurement-bearing: a wall-run length and a room area come straight off them. Three
gaps matter. (a) `wall_thickness_m` is **one plan-wide scalar** in `derived`, not per wall — so
every partition in a plan gets the same thickness whatever it is. (b) `scale_m_per_px` records that
the metric frame was **inferred from a stated gross area**, not surveyed: `resplan_ingest.py:5-8`
computes `sqrt(area / inner.area_px)` and rejects a plan whose implied thickness falls outside
0.08–0.45 m. That is a careful inference and it is still an inference — in P3 terms every number in
these fixtures is `INDICATIVE` at best, and nothing records that. (c) There is no height, no
material, no construction type — P4 fails here exactly as it does in the generator.

### 2.4 Correction to ROOT #256's framing of `ResPlan → PlanReference`

| claim | status |
|---|---|
| 20 plan fixtures at `backend/tests/spikes/fixtures/geometry_shapes/plans/` (19 real + 1 synthetic) | **verified.** `synthetic-spine-01.json` is the synthetic one, by name |
| `ResPlan → PlanReference` "already normalises real residential plans" | **verified as having been done; not verified as present on `main`.** The normaliser is not in the tree at `c07bf71`: `backend/spikes/architectural_brain/` does not exist. `git ls-tree -r d285358 backend/spikes/architectural_brain/` lists `plan_reference.py` (283 L), `resplan_ingest.py`, `patterns.py`, `retrieval.py`, `synthesis.py`, `adaptation.py`, `preservation.py`, `realization_intent.py`, `realize.py`, `corpus_io.py`, `build_corpus.py`, `build_fixtures.py`, `demo.py` and a **~200-plan `corpus/resplan_*.json`**. `git merge-base --is-ancestor d285358 origin/main` → **NO** |
| it is "plan-reading infrastructure that exists today" | **partly.** The fixtures and two readers are on `main` (`knowledge/room_proportion_priors.py:151-186`, `knowledge/adjacency_priors.py:136-187`, both `json.load` + dict access). The **ingest** is one `git checkout` away, not one import away |
| it reads plans | **no — it reads a vector dataset.** See §5.4 |

This is the same pattern memory records as *"shipped but wired to nothing"*, one step worse: here
the capability is not even on `main`. Recovering it is cheap (§10, item 1) but it must be *planned*,
not assumed.

---

## 3. Room, wall, door, window and dimension structures, field by field

### 3.1 Rooms

| field | file:line | real dimension, or drawing geometry? |
|---|---|---|
| `RoomOut.rect_m` | `design_output.py:43` | **real** — the **centerline** rectangle, plot-absolute, metres. The comment names it as centerline, which is the distinction a take-off depends on |
| `RoomOut.net_w_m` / `net_h_m` / `net_area_m2` | `:44-46` | **real** — net of every wall's own half-thickness, computed together by `net_rect_m` so they cannot disagree |
| `GeometricDesign.gross_area_m2` / `net_area_m2` | `:101-102` | **real** — building-level gross and net, the two numbers a quantity surveyor asks for first |
| `RoomOut.walls` (side → raw `WallType`) and `wall_facts` (side → `WallFacts`) | `:47-48` | **real but thin** — `WallFacts` keeps `boundary_context` and `construction` orthogonal (`geometry_domain/walls.py`), which is what stops an exterior safe-room wall reporting only `RC_SAFE_ROOM`. Still a type, never a specification |
| payload `RoomOut.gross_width_m` / `gross_depth_m` / `gross_area_m2` vs net triple | `demo/contract.py:88-98` | **real, and cross-checked** — C27 proves `w*d == area` for both, and that net never exceeds gross |
| payload `RoomOut.shape` / `polygon_m` | `:111-118` | **real for the one mechanism that produces them** — `RECTANGLE` or `L`; `polygon_m` is populated only by `room_merge.py` (LIVING+KITCHEN) and the single-row notch carve. Arbitrary polygons are not produced, though the renderer draws them (§4) |
| `area_m2` of a `PlanReference` room | fixtures, §2.3 | **real** — shoelace area of a measured ring. `width_m`/`depth_m` are explicitly *bbox extents, never a claim about which axis reads as width* (`plan_reference.py:38-41`) |

**Missing for P4:** floor finish, ceiling finish, ceiling height, floor level, skirting length (the
perimeter is derivable; it is not stored). Nothing in the repo computes a room perimeter in
production — the only `perimeter` in `app/` is a harness ratio
(`ai_harness/quality_142l/metrics.py:574`).

### 3.2 Walls — the strongest and the most incomplete structure in the repository

`vertical_slice/walls.py` (248 L) is a **wall schedule**, and it is wired: `validation.py:53` imports
`derive_walls` and calls it at `:798` on the final design of every plan, feeding check C33 ("every
door/window hosted on a wall; safe-room walls PROTECTED", `:817`).

```
Wall(id, wall_class, thickness_m, segment: WallSegmentM(orientation, coord, start, end),
     zones: tuple[str,...], hosts: tuple[str,...], structural_candidate: bool = False)
```

| property | verdict |
|---|---|
| **length** | **real** — `end - start` in metres, per connected straight run, derived from realized geometry rather than solved a second time (`walls.py:5-8`) |
| **thickness** | **real as a number, invented as a value** — `WALL_THICKNESS_M = {EXTERIOR: 0.30, PARTITION: 0.10, RC_SAFE_ROOM: 0.30, OPEN: 0.0}` (`geometry_core/model.py:104-109`). Two distinct thicknesses for an entire building, one of them carrying `PARAMETER · UNVERIFIED (regulation)`. A real plan has exterior 0.20–0.35, blockwork partitions 0.07–0.12, RC 0.20–0.40 and a dozen build-ups between |
| **classification** | **real, and the precedence is deliberate** — `EXTERIOR > PROTECTED > WET_SERVICE > INTERIOR`, one pure function (`classify`, `:96-110`), reused by the drawing layer so the two can never disagree. `WET_SERVICE` exists precisely because *"a plumbing stack, a waterproofing membrane or a fixture schedule cares about [it] differently"* (`:20-23`) — that is BoQ reasoning, already in the code |
| **openings hosted** | **real** — `hosts` carries the door/window ids on this wall's own segment, matched by position (`:36-40`). An opening deduction per wall is therefore already computable in plan |
| **height** | **absent.** There is no wall height anywhere in `backend/app/` |
| **material / construction build-up** | **absent.** `WallType` has four members and none is a material. `Construction` in `geometry_domain/walls.py` is `STANDARD_PARTITION | RC_SAFE_ROOM`-shaped, a structural-role flag, not a specification |
| **structural role** | **declared absent, honestly** — `structural_candidate` is always `False`, and the docstring says *"NOTHING in this codebase performs structural engineering … no caller should read `False` as 'verified non-structural'"* (`:27-32`) |

**So a wall yields `length x thickness` — an area in plan — and cannot yield the `length x height`
a blockwork or plaster item is priced by.** That is the single sharpest instance of the P4 gap.

### 3.3 Doors

`DoorOut(a, b, kind, width_m, center_m, orientation, placeable, shared_length_m, swings_into,
hinge_m, swing_deg)` (`design_output.py:51-64`), payload equivalent at `demo/contract.py:152-172`
with `wall_id`.

* **real:** `width_m` (0.9 `ROOM_DOOR`, 0.8 `SERVICE_DOOR`, 1.0 `ENTRANCE_DOOR` —
  `access_rules.py:44-48`), position, orientation, hinge point, swing angle, which side it opens
  into, and `wall_id`. A door schedule by width class and location is already producible.
* **a product policy, not a measurement:** the three widths are role-derived constants, chosen by
  `door_kind_for_zones`. They are plausible and they are not measured.
* **absent:** height, leaf material, frame, ironmongery, fire rating, threshold. A door cannot be
  priced from this.
* **in `PlanReference`:** a door is a polygon plus `room_ids` plus `is_exterior` — so width and
  position are measurable from a real plan, and nothing else is.

### 3.4 Windows

`WindowOut(zone_id, side, width_m, center_m, placeable, ..., ventilation_status)`
(`design_output.py:67-77`); payload adds `wall_id` (`contract.py:408-417`).

* **real:** width and position; width bands are per room class — habitable 0.9–2.0 m, laundry
  0.6–1.2 m, wet room 0.5–1.0 m (`windows.py:43-67`) — plus a wall-fraction rule.
* **absent:** **height, sill height, head height, glazing, frame, opening type, U-value.** A window
  is the clearest case in the repo of a structure that carries exactly what a drawing needs and
  exactly nothing a quantity needs: the one number it has (width) is the one a glazier needs
  *second*.
* `ventilation_status` is a compliance-flavoured field, but it is a status string from the
  generator's own rule set, not a measured ventilation area.

### 3.5 Dimensions as a first-class thing

There is **no dimension entity** — no `Dimension`, no witness line, no tolerance, no dimension
chain — in the backend. What exists instead is better than nothing and different in kind:

* **C27 `check_realized_dimensions`** (`validation.py:159-199`) — runs on *the numbers a person
  actually sees*, not on solver internals, and asserts three identities within 0.05 m²: net
  `w*d == area`, gross `w*d == area`, net never exceeding gross, and building gross equal to the
  sum of room gross. Its docstring names the bug class it exists to catch: *"NET area labelled onto
  a GROSS rectangle"*. **This is a measurement-integrity check and it is the single most reusable
  idea in the repository for this pivot.**
* **C2** (`:322-328`) — `covered == footprint_area_u` as **exact integer equality** in 5 cm units,
  over the *wings'* area rather than the bounding box. Perfect P1 closure.
* **`geometry_domain/units.py`** (84 L) — P2 in one file: `rounding` keyword-only with no default,
  `Rounding.NEAREST_UNSAFE` named so it cannot be picked quietly,
  `length_units_no_overstate` / `clearance_units_no_understate`, `lower_bound_units` /
  `upper_bound_units`, and a 1e-9 epsilon so an exact grid value is never bumped a unit.
* **`geometry_domain/provenance.py`** (74 L) — P3 in one file. `Source` already names `SURVEY`,
  `CAD`, `GIS`, `REGULATION`, `INFERRED`, `MANUAL_OVERRIDE`; `Authority` separates
  `AUTHORITATIVE / INDICATIVE / ASSUMED` with the comment *"knowing where a fact came from does not
  tell you whether it may be relied on legally"*; `weakest_of` propagates pessimistically and counts
  a missing provenance as `ASSUMED`.

**The gap:** `Provenance` is constructed in exactly one production place, for the parcel —
`demo/service.py:246-251` sets `Source.INFERRED, Authority.AUTHORITATIVE` for an engine-derived
buildable region and `Source.USER, Authority.AUTHORITATIVE` for a user-entered one. Every geometric
number the engine produces downstream carries **no** provenance, which `weakest_of` correctly reads
as `ASSUMED`. So the mechanism exists at full strength and is used at about 2 % of its surface.

### 3.6 Quantities the repository already computes, in the right units

These are not incidental; each is a named field on the API payload.

| quantity | where | unit |
|---|---|---|
| room net area, room gross area | `contract.py:88-98` | m² |
| building gross area, net area | `design_output.py:101-102` | m² |
| per-wall thickness and run | `walls.py:81-94`, payload `contract.py:121-139` | m, m |
| wet-wet shared wall length | `wet_core.py:9-11`, payload `:185` | m |
| plumbing complexity index (independent supply/drain runs) | `wet_core.py:18-25` | count |
| circulation total length, longest segment, narrowest width, dead ends, turns | `circulation_metrics.py`, payload `contract.py:221-227` | m, m, m, counts |
| usable wall length per room | payload `contract.py:265` | m |
| window width per room | payload `contract.py:279` | m |
| dead space m² (four kinds) | `dead_space.py:251,297-316` | m² |
| door swing envelope / clearance rectangles | `interior_layout.py`, payload `contract.py:439-442` | m, m² |
| kitchen counter run (depth 0.6 m, min run 0.3 m) | `interior_layout.py:396-398` | m |
| placed fixtures per room (13 kinds incl. TOILET, SINK, SHOWER, COOKTOP, COUNTER_RUN) | `interior_layout.py`, payload `LayoutObjectOut:427-442` | count + m |

A take-off of **masonry area in plan, plaster area in plan, floor area, door and window counts by
width class, sanitary-fixture counts, kitchen counter linear metres and plumbing-run counts** is
derivable from the payload that ships today. Everything needing a height, a material or a rate is
not.

---

## 4. Rendering and visualisation, and what the renderer proves

`frontend/src/design/DemoPlan.tsx` (275 L) plus `components/plan/{Walls,DoorSymbol,InteriorLayout,
fixtureSymbols}.tsx` (~350 L) and an **870-line** characterization test (`DemoPlan.test.tsx`, the
largest file in the frontend).

**What it proves about the geometry.** Three things, each load-bearing for the pivot.

1. **The drawing is in real-world metres with no scale factor at all.** The SVG `viewBox` is
   computed in metres (`DemoPlan.tsx:43-61`) and every coordinate is the raw metre value off the
   payload. A renderer with no pixel scale cannot silently misreport a dimension — the geometry
   *is* the drawing.
2. **It draws nothing it was not given, and that is enforced.** *"This component decides NOTHING
   architectural … If a fact is not on the object, it is not drawn"* (`:11-16`), restated in
   `Walls.tsx:3-9`, `InteriorLayout.tsx:4-9` and `QualityPanel.tsx:6-7` (*"Every number here is READ
   off `quality.metrics`, never recomputed"*). For a measurement product this is the correct
   contract already in force: the display may not invent a number.
3. **Wall stroke width is the real solved thickness.** `Walls.tsx` sets `stroke-width` from the
   backend's `thickness_m` and colours by `wall_class`. The drawing is therefore already a scaled
   representation of a physical thickness, not a line weight.

**What it already draws:** plot, garden regions, entrance walk, parking bays, **one rect per wing**
(so an L is two rects and the crook stays garden), FLEX remainder rooms, **genuine
`<svg:polygon>` rooms from `room.polygon_m` with no vertex-count assumption and a shoelace centroid
for the label** (`:130-139`, `:67-82`), 13 fixture symbols, walls as thickness-weighted lines by
class, doors as a wall interruption + leaf + swing arc from the backend's own hinge and swing angle,
windows **with their width printed to 2 dp**, a compass rose, and a **conventional 1-2-5 scale bar**
(`ScaleBar.tsx`, 34 L, with `niceScaleLengthM`).

**Measurement-flavoured UI that already exists:** a **room schedule** sorted largest-first with each
room's area (`DemoWorkspace.tsx:150,233-251`); per-room `W x D` and area printed on the drawing
(`demoRoomLabel.ts:72-79`, RTL bidi-isolated); building gross/net in the header and side panel
(`:98`, `:222-230`); dead space in m² with a corpus-median comparison (`QualityPanel.tsx:105`); plot
and buildable area (`ReviewPage.tsx:262,291`); and a **legend** that shows a swatch per wall class
only for classes present in this design (`PlanLegend.tsx`, 192 L).

**Dimension lines with witness lines and ticks already exist in this codebase** — but on the *older*
contract: `ArchitecturalFloorPlan.tsx:168-185` and `SketchSvg.tsx:195-210` draw an overall width line
at `y = -0.55` and an overall depth line at `x = maxX + 0.55`, with a `tickAt` helper
(`ArchitecturalFloorPlan.tsx:243`). Porting them to `DemoDesign` is a port, not an invention.

**The two limits.** (a) The wall/door/window model is hard-committed to
`orientation: 'horizontal' | 'vertical'` (`demoDesign.ts:57-68,79-110`), so a read-in plan with a
non-orthogonal wall cannot be drawn by `Walls.tsx` without a model change — room *outlines* are
polygon-capable, room *boundaries* are not. (b) Payload types are **hand-mirrored** from
`demo/contract.py` into `demoDesign.ts` (546 L) with no codegen, no zod and no runtime validation;
`response.json()` is cast `as Promise<T>` (`api.ts:106-116`). Any producer-side change is an
unguarded two-place edit.

**Zero cost, price, currency, material, quantity, unit-rate or totals UI exists** — and there is not
a single HTML `<table>` in the frontend; every tabular display is a `<dl>` or `<ul>`.

---

## 5. Import paths for PDF, image and CAD — stated plainly

### 5.1 There are none

Verified by exhaustive grep over `backend/`, `frontend/`, `scripts/`, every dependency manifest and
lockfile, **all 71 branch tips**, and git history by pickaxe.

| category | patterns searched | result |
|---|---|---|
| **PDF** | `pypdf, PyPDF2, pdfplumber, pdf2image, pdfminer, fitz, PyMuPDF, reportlab, poppler, ghostscript, weasyprint` | **0 code hits. 0 commits in history. 0 tracked `.pdf` files.** Only prose, all naming PDF as a future *output* (`docs/ROADMAP.md:126,177`) |
| **image / raster** | `Pillow, from PIL, import PIL, cv2, opencv, skimage, imageio, np.imread/load/fromfile/frombuffer` | **0 imports.** Pillow is in `backend/uv.lock:1532` only as a transitive matplotlib dependency and is never imported. `git log -S'cv2'` finds 2 commits, both **false positives** — the byte sequence occurs inside committed PNGs (confirmed: `git grep -n 'cv2' beb9546` → `Binary file … matches`) |
| **OCR** | `tesseract, pytesseract, easyocr, paddleocr` | **0 hits anywhere, any branch, any file type** |
| **CAD / BIM** | `ezdxf, dxf, dwg, ifcopenshell, ifc, .rvt, autocad, revit` | **0 code hits. 0 commits. 0 tracked `.dxf/.dwg/.ifc/.rvt` files in the tree or anywhere in history.** All documentation hits say "DXF output: out of scope". `GENERAL_GEOMETRY_ARCHITECTURE_REPORT.md:74,90,663` borrows the DXF **bulge convention** for an internal edge type — a convention, not I/O |
| **SVG parsing** | `svgelements, svgpathtools, cairosvg, svglib, DOMParser` | **0.** SVG is **write-only** (React components; `ai_harness/arch_direction/parti_diagrams.py:104-257` writes strings). `rectilinear_realizer.py:324`'s `svg_path` is an output path |
| **file upload, backend** | `UploadFile, File(, request.FILES, aiofiles, python-multipart, multipart` | **0 occurrences, 0 commits.** All 22 FastAPI routes are JSON. **`python-multipart` is absent from `backend/uv.lock` entirely**, so FastAPI physically cannot accept a multipart body. `backend/app/projects/routes/media_routes.py` is 6 lines: a mounted `APIRouter` with **zero routes** and a comment saying no feature has specified this |
| **file upload, frontend** | `type="file", accept=, FormData, FileReader, readAsDataURL, onDrop, dragover, createObjectURL` | **0.** All 24 inputs are number/checkbox/text/radio; every `api.ts` call sends `JSON.stringify` with `Content-Type: application/json` |
| **system packages** | `apt-get, brew install, poppler, tesseract, ghostscript, libgl` in `.github/`, `scripts/` | **0** (sole hit: a `brew install gh` hint string in `scripts/agent_team/github_client.py:44`) |

### 5.2 The audit-ready sentence

> The system has no drawing or document ingestion of any kind. There is no PDF, image, raster, OCR,
> DXF, DWG, IFC or SVG-parsing dependency in any manifest or lockfile, on any of the repository's 71
> branches, and none has ever existed in git history. There are no file-upload endpoints: the backend
> exposes 22 JSON-only FastAPI routes, never imports `UploadFile` or `File`, and `python-multipart`
> is absent from the lockfile. The frontend has no file input, no `FormData`, no `FileReader` and no
> drag-and-drop handler.

### 5.3 The one vision-model call, and why it is not an import path

`backend/app/ai_harness/quality_142l/judge.py:84-94` base64-encodes a PNG and sends it as an
`image_url` content part. The image is **self-produced**: `image_path` is a pair-sheet rendered
seconds earlier by `ai_harness/quality_142l/render.py:85,99` (`fig.savefig`, matplotlib Agg) from
the engine's own plan JSON. `ai_harness/__init__.py:1-7` states that nothing under the package is
imported by `app.demo`, `app.vertical_slice`, `app.requirements`, `app.geometry*` or any router, and
a grep confirms it: the only references to `ai_harness` from production are two **comments**
(`wet_room_policy.py:8`, `local_models/discovery.py:99`). **It is nevertheless the only place in the
repository where a plan image reaches a model, and so the only existing precedent for a
vision-based reader.**

The closest inbound-media path anywhere is `scripts/agent_team/remote/` — the dev orchestrator's
Telegram channel, which accepts **voice/audio only** (`service.py:245-256` → Whisper, `voice.py:40-56`)
and never reads a photo or document; `send_photo` is strictly outbound. That is tooling, not product.

### 5.4 So what does the repository read?

One already-vectorised dataset, on a branch. `resplan_ingest.normalise(plan_dict)` imports **only
shapely** and takes a Python dict; the "pixel coordinates" in its docstring are the **published
dataset's own grid units**, not pixels decoded from an image, and the metric scale is inferred from
the dataset's stated `area` (§2.3). **Reading an existing plan — the first verb in the proposed
product — has no implementation anywhere, in any form, and never has.**

---

## 6. Model integrations, retrieval infrastructure and APIs

Wiring here is established **by reading imports**, not from any capability table: #245 found the
wiring table's own scan blind to `app/vertical_slice/brain/`.

### 6.1 Every model integration, with its importer chain

**Exactly three model call sites are unconditionally live in production, and all three read words,
not drawings.** Each is constructed as a module-level singleton at router import time, so it exists
on every startup whether or not `OPENAI_API_KEY` is set (the key is only needed at call time —
`requirements/parser.py:444-446`).

| # | integration | file:line | importer chain, terminating at a route | reachability |
|---|---|---|---|---|
| A | `OpenAIRequirementParser` (`gpt-5-nano`, `chat.completions.parse`) | `app/requirements/parser.py:422,435,453`; `_SYSTEM_PROMPT` `:11` | `requirements/router.py:22` (singleton) → `:25` `POST /{id}/requirements` → `:32` `parser.parse(project.description)` → `main.py:37` | **LIVE.** Sends the user's free-text brief |
| B | `OpenAIChatIntentExtractor` (`gpt-5-nano`) | `app/chat/intent.py:182,198`; prompt `:130` | `chat/router.py:30` → `:56` `POST /{id}/chat/messages` → `:66` | **LIVE.** Free text |
| C | `OpenAIChatAssistant` (`gpt-5-nano`) | `app/chat/assistant.py:65,84`; prompt `:9` | `chat/router.py:29` → `:74`, same route | **LIVE.** Free text |
| D | `ArchitectModelGateway` (ABC) + `MockArchitectModelGateway` + `get_architect_model_gateway()` | `app/architect/gateway.py:28,95,204,217-219` | `design/pipeline.py:63,215` → `design/router.py:72` (`POST /{id}/design`) **and** `projects/update.py:301` → `projects/routes/base_routes.py:75` (`PATCH /projects/{id}`) | **LIVE, but the default provider is `mock` and makes no model call.** The shipped design path ships model-free |
| E | `RealArchitectModelGateway` (httpx + bearer token) | `app/architect/real_gateway.py:78,83,87-88,93` | lazily imported at `gateway.py:229` only when `ARCHITECT_MODEL_PROVIDER=remote`; then chain D | **env-gated.** Its own docstring `:3-13` declares the wire protocol an **unconfirmed placeholder, never verified against a real endpoint** |
| F | `LocalArchitectModelGateway` (Qwen2.5-Coder-7B + LoRA, in-process torch/transformers/peft) | `app/architect/local_gateway.py:199,222-224,233-246`; prompt `:41` | lazily imported at `gateway.py:224` when `ARCHITECT_MODEL_PROVIDER=local`; then chain D | **env-gated**, needs the `local-model` extra |
| G | `app/vertical_slice/brain/` — `runner.run_brain:349`, `DeterministicProposer:423`, `exact_pipeline.run_exact_pipeline:93` | `brain/` | `demo/service.py:40` (import) → `:327-329` → `:929 run_brain(...)`; authorized at `demo/router.py:241` → `demo/preview_gate.py:88` (`BRAIN_PREVIEW_ENABLED` + `X-Brain-Preview-Token`, `hmac.compare_digest`) | **production-reachable, and contains no model at all.** Zero imports of `openai`, `anthropic`, `httpx`, `urllib`, `transformers` or `torch` across all four files |
| H | `ai_harness/topology_poc/llm_client.py` (Ollama via **`urllib.request`**, `:15,34,44,47`) | — | only `topology_poc/runner.py:24`, itself a `main()` CLI | **dead to production.** Note the transport: a grep for provider libraries misses it |
| I | `ai_harness/topology_poc/regen_142k.py` (`gpt-5`, `:46,59,67`) | — | 8 importers, every one a harness/report/spike CLI | **dead** |
| J | `ai_harness/quality_142l/judge.py` (vision, `gpt-5`/`gpt-5-mini`, `:88-96`) | — | **zero importers repo-wide** | **dead — and the only vision call in the repository** (§5.3) |
| K | `local_models/discovery.py` (httpx → Ollama `/api/tags`, `/api/show`) | `:60,74` | `knowledge/embeddings/factory.py:55`, `knowledge/cli.py:26` | **no route.** Capability discovery only; never loads a model |

**Verified, per #245's warning.** `backend/tests/knowledge/test_capability_wiring_table.py:24-28` says
of itself that `_CANDIDATE_CALLER_PATHS` is *"an explicit list (not a live tree walk)"*; it
enumerates **89** `backend/app/...` paths and `grep -n "brain"` over the file returns **nothing**. So
`brain/{__init__,area,exact_pipeline,proposer,runner}.py` are invisible to the only automated guard
on `docs/PROJECT_STATE.md`'s wiring table, even though `demo/service.py:40` imports `brain.runner`
directly. **Every reachability claim in this audit was established by reading imports, not that
table.**

**What this means for the pivot.** The three live integrations all do the same job —
**unstructured natural language in, typed structure out, with a provenance tag per field**
(`projects/models.py:11-30` `SourceTag.requested|inferred|unknown`, rendered by
`TechnicalDetailsPage.tsx`). That is *exactly* the shape a document reader needs for the non-graphic
half of a plan: a title block, a room-label legend, a dimension string, a specification note. It is
**not** the shape a drawing reader needs, and nothing in production has ever been handed an image.

### 6.2 Retrieval infrastructure

`app/knowledge/` is a real hybrid-retrieval stack: incremental checksum indexer
(`indexer.py:37,50,69`), heading-path-aware markdown chunking (`chunking.py:63`), a SQLite store with
an **FTS5** virtual table and cosine over TEXT-stored vectors (`store/sqlite_store.py:1-25,47,54,61`,
WAL), two-channel retrieval with each channel min-max normalised **before** combination and then
reranked by a bounded document-status weight (`retrieval.py:22,36,50,77,82` — *"raw FTS5 bm25 scores
and raw cosine-similarity scores are on incomparable scales, so they are never combined directly"*),
a token-budgeted context pack (`context_pack.py:36`, `tokens.py:8`), a single-writer index lock
(`lock.py:72`), and **four** embedding providers behind a lazy factory —
openai `text-embedding-3-small`, ollama (which *refuses* a model that does not declare the embedding
capability, `ollama_provider.py:23-30`), huggingface sentence-transformers, and a hash fallback.

Three facts decide its verdict:

1. **It indexes the repository's own documentation, not product data.**
   `config.py:34-39`: `docs/**/*.md`, `specs/*/{spec,plan,research}.md`.
2. **It has no production importer at all.** The only importers are `knowledge/cli.py` and
   `knowledge/tool.py`; `tool.py` itself has **zero Python importers** and is invoked by the
   `knowledge-refresh` agent skill. No router, no handler, no request path touches any of it. The
   index file (`app/knowledge/data/`) does not even exist in this worktree.
3. **The default embedding provider is `hash`** — `embeddings/factory.py:70` falls back to it because
   neither installed Ollama model declares the embedding capability (`config.py:9-15`). So the
   semantic channel is, by default, not semantic. The code logs this rather than pretending.

**Priors tables (retrieval-like lookups over the real-plan corpus), and their flags.** Both are
genuinely wired into the production sort key and both are **off**:

* `knowledge/adjacency_priors.py` → `vertical_slice/adjacency_priors.py:27` →
  `concept_generator.py:58`, used at `:4733-4746` → `demo/service.py:37` → the demo routes.
  **`ADJACENCY_PRIORS_ENABLED = False` (`vertical_slice/adjacency_priors.py:39`)** — returns a
  constant `0.0`, a provable no-op on a stable sort.
* `knowledge/room_proportion_priors.py` → `vertical_slice/room_proportion_priors.py:23` →
  `concept_generator.py:59`, same route chain. **`ROOM_PROPORTION_PRIORS_ENABLED = False` (`:32`)**.
* `knowledge/adjacency_priors_fullcorpus.py` (a 17,107-plan re-measurement, `_TrainTable:297`) has
  **no production importer**; its JSON artefact at
  `docs/reports/real-plan-priors/adjacency-fullcorpus.json` is read only by
  `ai_harness/topology_poc/priors.py` and a spike.
* `vertical_slice/reference_benchmark.benchmark()` is reached only from
  `scripts/reference_benchmark.py:43` and tests; its `classify_footprint_family` **is** live via
  `concept_patterns.py:31,58-62`.

**One naming trap, stated so it is not mis-triaged later.** `vertical_slice/band_embedding.py`,
`graph_embedding.py` and `exact/spine.py` are **combinatorial graph-into-geometry embeddings**
(rooms into slots) — no vectors, no similarity search. `app/knowledge/embeddings/` is the only
vector-embedding code in the repository.

### 6.3 The HTTP API surface

**23 routes, all JSON, zero uploads.** FastAPI only — one app at `main.py:34`, six routers at
`:35-40`; no Django, no DRF, no `urls.py`.

| group | routes |
|---|---|
| projects | `POST /projects` (`projects/routes/base_routes.py:19`), `GET /projects/{id}` (`:66`), `PATCH /projects/{id}` (`:74`, may regenerate via the architect gateway + solver), `GET /projects/{id}/design-versions` (`:96`), `POST …/design-versions/{v}/activate` (`:103`) |
| requirements | `POST /projects/{id}/requirements` (`requirements/router.py:25`) — **the one route whose body reaches a model by design** |
| legacy design | `POST /projects/{id}/design` (`design/router.py:52`), `POST …/design/spatial-edit` (`:89`) |
| review | `GET /projects/{id}/review` (`demo/router.py:50`), `PUT …/review` (`:56`) — the `PUT` body `ReviewEdit` is **fully structured, no free text** |
| the generator | `POST /projects/{id}/design/demo/stream` (`demo/router.py:260`, **SSE**: one `progress` per stage then `done`/`error`), `POST …/design/demo` (`:341`, returns `DemoPlanSet`), `POST /projects/site/footprint-options` (`:419`) |
| chat | `GET /projects/{id}/chat` (`chat/router.py:47`), `POST …/chat/messages` (`:56`, two model calls), proposal `confirm` (`:108`) / `cancel` (`:150`) |
| reference data | `GET /localities` (`localities/router.py:8`), `GET /localities/{city}/streets` (`:14`) |
| ops | `GET /failures` (`main.py:88`), `POST /failures` (`:95`), `GET /health` (`:108`), plus three global exception handlers that write the failure log (`:50,68,77`) |

* **`media_routes.py` and `analytics_routes.py` are mounted and declare zero routes**
  (`projects/routes/__init__.py:9-10`). The one suggestively named "media" router has no upload path
  and says so in a comment.
* **Free-text sinks:** `description` on `POST /projects`, `content` on `POST …/chat/messages`,
  and `POST /failures`. Only the first two reach a model.
* **Incidental, out of scope here:** `POST /failures` is unauthenticated and accepts
  caller-supplied strings plus an untyped `context: dict` (`main.py:25-32`) which is persisted to
  disk. Worth its own Issue before anything is exposed publicly; **not** touched by this audit.

### 6.4 Prompt assets

**There are no prompt template files.** No `.txt`, `.j2`, `.jinja` or `.tmpl` asset is loaded and
sent to a model anywhere; every prompt is an inline Python string. Production:
`requirements/parser.py:11`, `chat/assistant.py:9` (+ `_build_project_context` `:22`),
`chat/intent.py:130` (+ `_build_context` `:92`), `architect/local_gateway.py:41,144`. Note that
`architect/real_gateway.py:42` `_build_payload` has **no prompt at all** — it posts
`ArchitectModelRequest.model_dump()` raw. Harness prompts: `topology_poc/prompt.py:14,93`,
`topology_poc/context.py` (prior-grounding block), `quality_142l/judge.py:38,88`,
`quality_142l/prompt_experiment.py:148` (with a sha256 per variant), `regen_142k.py:248` (critic
retry).

### 6.5 Verdicts for this section

| component | verdict | why |
|---|---|---|
| `architect/gateway.py` — the ABC + env-switched provider factory + a **deterministic Mock default** | **adapt — keep the pattern** | this is the right shape for a reader's extraction model: one interface, three providers (remote/local/mock), default to the one that cannot spend money or fail. A measurement product needs exactly this for a vision or OCR provider |
| `architect/real_gateway.py` + `local_gateway.py` + `model_schema.py` + `models.py` (the `ArchitecturalSpec` payload) | **deprecate** | the payload is "produce an architectural spec", the generator's problem. The remote protocol is additionally self-declared unverified |
| `requirements/parser.py` (free text → typed fields + `SourceTag`) | **adapt** | the only "unstructured in, typed + provenance out" machinery in the repo; a plan's title block and notes need precisely it |
| `chat/intent.py`, `chat/assistant.py`, `app/chat/` | **deprecate** | a conversation that mutates a generation brief |
| `app/knowledge/` (indexer, chunking, hybrid FTS5+cosine retrieval, 4 providers, SQLite store, context pack, lock) | **adapt — keep the machinery, replace the corpus** | the retrieval design (independent normalisation per channel, bounded status rerank, single-writer lock, honest hash fallback) transfers directly to a materials/rates/supplier corpus. Its content does not transfer at all |
| `knowledge/{adjacency,room_proportion}_priors.py` + the fullcorpus table | **preserve as corpus readers** | they are the only code on `main` that reads a `PlanReference`. Both feature flags are **off**, so nothing in production depends on their output today |
| `vertical_slice/reference_benchmark.py` + `docs/architecture_reference/references/index.json` | **adapt** | a curated real-plan reference index already exists — but **metadata-only**: every entry is `rights: "metadata-only"` and carries no geometry (`reference_benchmark.py:15-19`) |
| `local_models/discovery.py` | **preserve** | capability-verified provider discovery that refuses to repurpose a completion model as an embedder |
| `brain/` + `exact_pipeline` + `preview_gate`-gated previews | **isolate** (§8.3) | production-reachable, model-free, and solving the generator's problem |

---

## 7. Frontend and backend architecture

### 7.1 Backend

* **FastAPI only** — no Django, no Flask (0 grep hits in `*.py`/`*.toml`/`*.md`). 22 routes across
  `app/main.py`, `app/demo/router.py`, `app/design/router.py`, `app/chat/router.py`,
  `app/projects/routes/*`, `app/requirements/router.py`, `app/localities/router.py`. All JSON.
* **Persistence is one JSON file.** `app/projects/repository.py:80` `JsonFileProjectRepository`
  `json.dump`s the whole store (`:102`); the abstract base is at `:25`. There is **no database**:
  no SQLAlchemy, no migrations, no ORM. `app/data/design_versions.json` is the only other store.
  The knowledge RAG index has its own SQLite file, unrelated to product data.
* **Declared production dependencies** (`backend/pyproject.toml:7-24`): `fastapi`, `uvicorn`,
  `openai`, `python-dotenv`, `httpx`, `matplotlib`, **`shapely>=2.0`** (declared for
  `geometry_domain.booleans` — *"robust boolean geometry is where hand-rolled code fails silently,
  and it is not the problem this product exists to solve"*), **`scipy>=1.11,<2`** (declared for
  `vertical_slice/exact`, the MILP sizer). Optional extras: `local-model` (torch/transformers/peft),
  `knowledge-embeddings` (sentence-transformers/torch). Dev group: `networkx`.
* **Incidental finding, not acted on (read-only Issue):** **`numpy` is imported by three production
  modules** — `vertical_slice/safe_adapter.py:29`, `vertical_slice/exact/milp_cells.py:19`,
  `vertical_slice/exact/milp_oracle.py:24` — and is **not declared** in `backend/pyproject.toml`;
  it is only transitively available via matplotlib/scipy/shapely. That is the exact failure mode the
  inline comments at `pyproject.toml:13-14,20-22` were added to prevent for matplotlib and scipy.
  Worth its own Issue; **out of scope here.**
* **Module map and what a different product keeps:**

| package | what it is | keep for a measurement product? |
|---|---|---|
| `app/geometry_domain/` (1441 L) | authoritative geometry kernel: `Region`/`MultiRegion`/`Ring` with **arcs**, booleans over GEOS, direction-aware units, **per-element provenance**, typed site constraints, `WallFacts` | **keep, as the foundation** |
| `app/vertical_slice/` (the engine) | concept generation, solver, realizer, 32 validators, doors/windows/walls/furniture/metrics, `design_output` | **keep ~a third as a library** (§8), isolate the rest |
| `app/demo/` | the delivery layer: `scope`, `site_geometry`, `requirements_view`, `service`, `router`, `contract`, `preview_gate` | **keep `contract`'s payload discipline and `preview_gate`; the rest is generator plumbing** |
| `app/projects/` | `Project` pydantic model with `SourceTag` provenance per field (`requested`/`inferred`/`unknown`), JSON-file repository, routes | **keep the tagged-field pattern; replace the store** |
| `app/knowledge/` | the project's own docs RAG — hybrid FTS5+cosine, 4 embedding providers, **no production importer** (§6.2) | **adapt the machinery, replace the corpus** |
| `app/architect/` | the model gateway (3 providers, default `mock` = no model call) and area budget (§6.1) | **adapt the gateway pattern, deprecate its payload** |
| `app/ai_harness/` (17 sub-packages) | measurement harnesses, provably not imported by production | **keep as the evaluation culture; nothing product-facing** |
| `app/geometry/`, `app/design/`, `app/chat/` | the older solver path, its router and the chat/proposal flow | **deprecate** |
| `app/localities/` | `streets_by_city.json`, city/street lookup | **keep** — a real product needs an address; this already is one |
| `app/local_models/` | Ollama capability discovery | keep, incidental |
| `app/observability/` | logging/metrics | keep |
| `app/requirements/` | natural-language brief parsing | generator-specific |

### 7.2 Frontend

React 19 + Vite 8, **no router, no state library, no HTTP client library** — `type View = 'form' |
'loading' | 'review' | 'generating' | 'plan' | 'design'` in `App.tsx:29` and 16 `useState` calls are
the whole navigation and state model; `api.ts` (464 L) is hand-written `fetch`. Plain CSS, one file
per component, tokens in `index.css`. Hebrew strings inline with `dir="rtl"` and a dedicated `Dim`
component for bidi-safe dimension pairs (`design/Dim.tsx`). Vitest + jsdom (25 test files, ~4,400
test LOC against ~6,000 source LOC), Playwright for 4 e2e specs, oxlint.

**No auth, no login, no session, no project list, no 404, no persistence across a reload** — a
project lives in one tab's memory. The genuinely product-agnostic shell is small:
`Autocomplete.tsx`, `Dim.tsx`, `Menu.tsx`, `LoadingScreen.tsx`, `RefusalNotice.tsx`, `index.css`
tokens and `api.ts`'s typed-error-class pattern.

Two standalone Playwright scripts at the frontend root, `audit-measure.mjs` and `audit-shot.mjs`,
screenshot and measure rendered plans — a drawing-quality audit harness, not app code.

---

## 8. Verdict per component

**Scale.** `preserve` = usable as it stands. `adapt` = the structure is right, the content or the
direction of use must change. `deprecate` = a different product would not carry it. `isolate` = keep
running, unchanged, behind a boundary (§8.3).

### 8.1 The table

| # | component | file | P1 | P2 | P3 | P4 | verdict | why |
|---|---|---|---|---|---|---|---|---|
| 1 | `geometry_domain/provenance.py` | `backend/app/geometry_domain/provenance.py` | – | – | **yes** | – | **preserve** | P3, complete, with `SURVEY`/`CAD`/`GIS` already named and pessimistic propagation. Irreplaceable and 74 lines |
| 2 | `geometry_domain/units.py` | `…/units.py` | – | **yes** | – | – | **preserve** | P2, complete. No default rounding, unsafe mode named to be noticed |
| 3 | `geometry_domain/primitives.py` + `booleans.py` + `transforms.py` | `…/primitives.py` (492 L) etc. | yes | yes | yes | 2D | **preserve** | metric, arc-capable, GEOS booleans, per-element provenance, solver-free by construction |
| 4 | `geometry_domain/constraints.py` | `…/constraints.py` | – | – | yes | – | **adapt** | `Parcel`/`BuildableRegion`/`SiteConstraints` are right; it deliberately excludes coverage/FAR/height (`:14-18`), which the regulatory half of the pivot needs |
| 5 | `GeometricDesign` + `RoomOut`/`DoorOut`/`WindowOut` | `vertical_slice/design_output.py` | **yes** | yes | no | **no** | **adapt** | centerline + net + gross is exactly right; add height, material, provenance; stop deriving it only from a `Fixture` |
| 6 | **the wall schedule** | `vertical_slice/walls.py` (248 L) | yes | yes | no | **no** | **adapt** | id/class/thickness/segment/zones/hosts is a BoQ wall line already. Needs per-wall thickness from measurement and a height |
| 7 | **C27 dimension consistency** | `vertical_slice/validation.py:159-199` | **yes** | yes | – | – | **preserve** | a measurement-integrity check in the right place: on the displayed numbers |
| 8 | **C2 area closure** | `validation.py:322-328` | **yes** | – | – | – | **adapt** | exact integer equality is right for a generator and impossible for a surveyed plan. Keep the invariant, replace `==` with a declared tolerance and a residual report |
| 9 | the other 30 validators (C1–C31, C33; `validation.py` 887 L) | `validation.py` | yes | yes | no | no | **adapt (the arithmetic) / isolate (the policy)** | they compute the right quantities and then **gate** on product policy. #242 measured that the policy refuses something non-representational in **18 of 19** real plans. A reader must report, not refuse |
| 10 | `wet_core.py` | `vertical_slice/wet_core.py` | yes | yes | no | no | **preserve** | `shared_wall_length_m` and `plumbing_complexity_index` ("how many independent supply/drain runs a plumber would need") are already BoQ-adjacent and read off realized geometry |
| 11 | `circulation_metrics.py`, `dead_space.py` | `vertical_slice/` | yes | yes | no | no | **preserve** | total/longest/narrowest circulation, dead space in m² — measured, in metres, off realized geometry |
| 12 | `interior_layout.py` (505 L) + `fixtureSymbols` | `vertical_slice/interior_layout.py` | – | yes | no | partial | **adapt** | 13 typed objects with real metric footprints and clearances. Sanitary-fixture counts and kitchen counter linear metres are genuine quantity lines; the placement is invented, not read |
| 13 | `furniture.py` + `MIN_FURNITURE_ENVELOPE_M` | `furniture.py:38`, `geometry_core/model.py:235` | – | yes | no | no | **isolate** | a bounding-box screen that #242 measured as the **top blocker** (C9, 19/19 plans, 364 cells). Useful to a generator, fatal to a reader |
| 14 | `ROOM_TEMPLATES` + `scale_program` + the elasticity/quality tier | `concept_generator.py:142+` | – | yes | **no** | no | **isolate** | #238 §7.1 item 4 calls it the strongest component — for *generating*. Every figure is self-labelled `DEMO PRODUCT POLICY placeholder, NOT verified regulation`. A measurement engine must never compare a measured room to it |
| 15 | `demo/contract.py` payload (`DemoDesign`, 1500+ L) | `demo/contract.py` | yes | yes | partial | no | **adapt** | the quantity feed already exists (§3.6). Strip `search`/`outline`/`family`/`concept`/`merge`; keep `walls[].thickness_m`, the length metrics, `ConstraintOut.authoritative` |
| 16 | `demo/scope.py` + typed refusals + `capacity_notice_text` | `demo/scope.py` | – | – | – | – | **preserve** | refuse-never-downgrade is the right culture for a product that reports measurements |
| 17 | `demo/preview_gate.py` | `demo/preview_gate.py` | – | – | – | – | **preserve** | the per-request, fail-closed flag + token mechanism (#212, `c07bf71`) is **exactly the isolation primitive §8.3 needs** |
| 18 | `demo/site_geometry.py` | `demo/site_geometry.py` | yes | yes | partial | – | **adapt** | site-minus-setbacks is the only correct direction and it is implemented. Rectangular parcels only, no GIS, no regulation lookup (`:20-23`); setbacks default `0.0` by deliberate honesty |
| 19 | `app/localities/` | `localities/data.py`, `streets_by_city.json` | – | – | – | – | **preserve** | an address lookup a product needs on day one |
| 20 | `projects/models.py` tagged fields (`SourceTag`) | `projects/models.py:11-30` | – | – | **yes** | – | **preserve** | per-field `requested`/`inferred`/`unknown` is `Provenance` for scalars, and the UI already renders it (`TechnicalDetailsPage.tsx`) |
| 21 | `projects/repository.py` | `:80` | – | – | – | – | **deprecate** | one JSON file. A product storing plans, quantities, prices and suppliers needs a database |
| 22 | `PlanReference` fixtures (20) + priors readers | `backend/tests/spikes/fixtures/geometry_shapes/plans/`, `knowledge/{room_proportion,adjacency}_priors.py` | partial | yes | dataset-level | no | **preserve the fixtures, adapt the schema** | the only representation built to describe someone else's plan |
| 23 | the `PlanReference` **ingest** (`plan_reference.py`, `resplan_ingest.py`, ~200-plan corpus) | **not on `main`** — `d285358:backend/spikes/architectural_brain/` | partial | yes | dataset-level | no | **adapt, and first recover** | §2.4. Shapely-only, dict in, metric out, never guesses |
| 24 | `rectilinear_realizer.realize_cells` | `vertical_slice/rectilinear_realizer.py:1222` | yes | yes | no | no | **isolate** | genuinely shape-free and the best thing in the engine — but it **synthesises** geometry from intent. A reader has the geometry already. #242: 0/19 |
| 25 | `band_embedding` + `band_sizing` + `exact/milp_*` | `vertical_slice/`, `vertical_slice/exact/` | yes | yes | – | – | **isolate** | an exact decision procedure with proof-carrying refusals, for a problem a reader does not have |
| 26 | `concept_generator`, `concept.py`, `Fixture`, `Cut.V|Cut.H`, `brain/`, `proposal_critic`, `primary_selection`, rank keys | `vertical_slice/` | – | – | – | – | **isolate** | the generator proper. #238 §7.2 found it fundamentally limiting *for architecture*; for measurement it is simply a different product |
| 27 | `DemoPlan.tsx` + `Walls`/`DoorSymbol`/`InteriorLayout`/`fixtureSymbols` | `frontend/src/design/`, `components/plan/` | – | yes | – | – | **preserve** | metre-native, zero scale factor, draws-only-what-it-is-given (enforced), thickness-weighted walls, 870 L of characterization tests. It does not care who produced the geometry |
| 28 | `ScaleBar.tsx`, `demoRoomLabel.ts`, `PlanLegend.tsx`, `QualityPanel.tsx`, `RoomDetails.tsx` | `frontend/src/design/`, `components/review/` | – | yes | – | – | **preserve** | the "show a measurement" layer, already conventional and tested; panels never recompute |
| 29 | dimension lines + witness ticks | `ArchitecturalFloorPlan.tsx:168-185`, `SketchSvg.tsx:195-210` | – | yes | – | – | **adapt** | drafting convention already implemented, on the older contract. A port |
| 30 | `App.tsx` brief form, `FootprintSelection.tsx`, `ReviewPage.tsx`, `SettingsPage.tsx`, `ChatPanel.tsx`, `SpatialEditControls.tsx` | `frontend/src/` | – | – | – | – | **deprecate** | ~1,900 L of generator requirements capture |
| 31 | the legacy path: `DesignPage`, `SketchCard`, `SketchSvg`, `ArchitecturalFloorPlan`, `geometricDesign.ts`, `app/geometry/`, `app/design/`, `app/chat/` | both tiers | – | – | – | – | **deprecate** | a second, older generator contract kept in parallel |
| 32 | `app/knowledge/` RAG (indexer, chunking, hybrid FTS5+cosine retrieval, 4 embedding providers, SQLite store) | `app/knowledge/` | – | – | **yes** (`doc_status`) | – | **adapt** | §6.2. Real retrieval machinery pointed at the project's own markdown, with **no production importer at all** and a non-semantic `hash` provider by default |
| 33 | `app/architect/gateway.py` — ABC + env-switched provider factory + deterministic Mock default | `app/architect/gateway.py:28,95,204` | – | – | – | – | **adapt** | §6.5. The right shape for a reader's extraction/vision provider: one interface, three providers, default to the one that cannot spend money |
| 33b | `architect/real_gateway.py`, `local_gateway.py`, `model_schema.py`, `models.py`, `app/chat/` | `app/architect/`, `app/chat/` | – | – | – | – | **deprecate** | §6.5. The payload is "produce an architectural spec"; the remote wire protocol is self-declared unverified (`real_gateway.py:3-13`) |
| 33c | `requirements/parser.py` — free text → typed fields + `SourceTag` | `app/requirements/parser.py:422` | – | – | **yes** (via `SourceTag`) | – | **adapt** | §6.1. The only "unstructured in, typed + provenance out" machinery in the repo. A plan's title block, room legend and notes need exactly it |
| 34 | `app/ai_harness/` (17 packages, provably import-isolated) | `app/ai_harness/__init__.py:1-7` | – | – | – | – | **preserve as culture** | pre-registered expectations, frozen constants, sensitivity arms, positive controls (#242 is the model). Nothing product-facing |
| 35 | `app/observability/`, `app/local_models/` | both | – | – | – | – | **preserve** | incidental infrastructure |

### 8.2 Count

**preserve 14 · adapt 13 · isolate 5 · deprecate 4**, with three rows split between two verdicts
(9, 22, 33 group). The preserved set
is concentrated in two places: **`geometry_domain` and the renderer** — the bottom and the top of
the stack. The isolated set is the middle: everything that *invents* geometry.

### 8.3 What *isolate* means concretely, given that the generator may not be deleted or disabled

The directive forbids deleting, disabling or degrading the generator. Isolation here means **the
generator keeps running exactly as it does today, and stops being on the new product's dependency
path.** Four concrete steps, each already precedented in this repository:

1. **Leave `?engine=` and the production path untouched.** The generator is already reached only
   through `demo/router.py` and `demo/service.py`. A measurement product adds routes; it changes
   none. This is the same shape #212 shipped at `c07bf71`: a second engine behind a request-time,
   fail-closed gate (`demo/preview_gate.py`) whose refusal is indistinguishable from an unknown
   engine's. **Reuse that mechanism rather than inventing a second one.**
2. **Make the dependency direction one-way, and test it.** The new reader may import
   `geometry_domain` (which imports no solver by construction) and must not import
   `vertical_slice.concept_generator`, `concept.py`, `geometry_core.Fixture`, `brain/` or
   `rectilinear_realizer`. The enforcement pattern already exists twice:
   `ai_harness/__init__.py:1-7` plus the test `test_nothing_outside_the_harness_directory_imports_it`
   (#242), and `geometry_domain`'s own solver-free rule. **One import test is the whole isolation
   mechanism.**
3. **Copy, never fork, the shared tables.** `ROOM_TEMPLATES`, `MIN_FURNITURE_ENVELOPE_M`,
   `WALL_THICKNESS_M`, `DOOR_WIDTH_M` and the window bands are the generator's **product policy**.
   A measurement engine must not compare a measured room against a generator's target, or it will
   report a real house as wrong. Where the reader needs a default it declares its own, with a
   `Provenance` of `ASSUMED`, and says so on the output.
4. **Keep the corpus regression as the generator's contract.** The 432-context corpus snapshot is
   what proves the generator undegraded. A reader that shares no module with the generator cannot
   move it, and the snapshot proves that per PR. Note the standing hazard in memory: `corpus_snapshot`
   records `git rev-parse HEAD`, so no commit may land mid-run.

**What isolation is not:** a flag that turns the generator off, a deleted module, or a shared
"common" package that quietly couples the two. A shared `common/` would recreate the coupling under
a different name; `geometry_domain` is already that package and already has the right rule.

---

## 9. The central question, answered

> **Can the existing geometric engine serve as a plan-understanding and measurement engine?**

**No for the engine. Yes for the geometry layer underneath it, as a library — and the measurement
half of the answer is more encouraging than the understanding half.**

The engine is a **synthesis** machine with a **fail-closed acceptance gate**. A reader needs an
**analysis** machine with a **tolerance-bearing report**. Those are not the same program, and the
gate is the specific thing that cannot be reused: #242 measured `realize_cells` plus the unchanged
validators against the 19 real plans and carried **0 of 19** in every arm and pipeline. But the
*arithmetic* inside that gate — areas, lengths, closure, gross-vs-net, wall runs, opening widths,
plumbing runs — is exactly what a take-off starts from, it is already computed per plan, and it is
already shipped on the payload. The pivot keeps the arithmetic and discards the verdict.

### 9.1 The strongest evidence **for**

1. **The measurement arithmetic exists, in the right units, and is already delivered.** §3.6 lists
   twelve named quantity fields on the API payload today: room net and gross area, building gross
   and net, per-wall thickness and run, wet-wet shared wall length, plumbing complexity index,
   circulation total/longest/narrowest length, usable wall length per room, window width, dead space
   in m², door swing envelopes, kitchen counter runs, and 13 kinds of placed fixture. A plan-view
   take-off is derivable from the response the product returns right now.
2. **Closure is proved, not assumed.** C2 asserts `covered == footprint_area_u` as an **exact
   integer identity** over the wings' area (`validation.py:327`), and C27 independently re-checks
   every **displayed** dimension against its own area and the building total (`:159-199`). A
   measurement engine's hardest property — the parts sum to the whole — is the property this
   codebase is strictest about.
3. **P2 and P3 are already written, correctly, and nobody has to argue for them.**
   `geometry_domain/units.py` makes it impossible to quantize by accident and names the unsafe mode
   `NEAREST_UNSAFE`; `geometry_domain/provenance.py` already enumerates `SURVEY`, `CAD`, `GIS`,
   `REGULATION` as sources, separates "where it came from" from "may it be relied on", and
   propagates pessimistically. 158 lines that a greenfield measurement product would spend a month
   getting wrong.
4. **The renderer proves the geometry is displayable and honest.** `DemoPlan.tsx` draws in real
   metres with **no scale factor**, sets wall stroke width from the backend's own `thickness_m`,
   draws arbitrary room polygons with a shoelace centroid, prints `W x D` and area per room and
   window widths to 2 dp, carries a conventional scale bar, and is contractually forbidden from
   drawing a fact it was not given — with 870 lines of characterization tests holding that. It does
   not care who produced the geometry.
5. **The repository already holds, and has already normalised, real professional plans.** 20 metric
   `PlanReference` fixtures with room polygons, wall polygons, opening polygons, a citation and a
   licence; the normaliser is one `git checkout` away (§2.4) and never guesses.
6. **The culture is right for a product that sells numbers.** Typed refusals that never downgrade
   (`demo/scope.py:1-8`), proof-carrying refusals that name the failing check, product figures
   self-labelled as unverified rather than passed off as regulation, and a harness practice of
   pre-registering expectations before measuring (#242). A measurement product's liability is a
   wrong number stated confidently, and this codebase's strongest habit is refusing to state one.

### 9.2 The strongest evidence **against**

1. **Measured: 0 of 19 real plans survive the engine.** #242's R1 pushed the 19 real fixtures
   through `realize_cells` plus the unchanged validators. Arm 1 (one rectangle per room): **0**. Arm
   2 (same-zone `OPEN` cells through the existing `_group_checks`): **0**. Pipelines B, C and D
   (progressively more generous door extraction and wall-face snapping at 2x and 3x the frozen
   tolerance): **0, 0, 0**. Verdict **STOP** against thresholds frozen before the run. Under
   pipeline D the plans were pushed so far toward rectangles that only 30 rooms were still
   non-rectangular, and still none was carried. A positive control proves the harness can carry a
   plan. (PR #254, closed unmerged — §12.3.)
2. **Measured: the obstruction is not the choice of cut.** An exhaustive oracle over each room's own
   coordinate grid found that of **55 furnished non-rectangular rooms, 1** admits *any* rectangle
   partition passing C20's aspect bound and C9's furniture envelope — 0 of 21 bedrooms, 0 of 11
   master bedrooms, 0 of 3 kitchens, 0 of 2 bathrooms, 1 of 18 livings. Most are a rectangle with a
   0.3–0.9 m notch (a duct, a column, a jog), and every partition of such a room contains a strip no
   bed or sofa fits in. A reader cannot be built by picking better cells.
3. **Measured: the *policy* refuses real plans independently of the representation.** In **18 of 19**
   plans something that is not a fragment also failed: C24 refuses a bedroom door opening onto the
   living room; C3/C21/GROUP-C3 refuse bedrooms of 5.1 m² or 24–28 m², a bathroom of 3.7–4.4 m² and
   a 66 m² living room against `ROOM_TEMPLATES`; C17 refuses a bathroom between two bedrooms; C26
   refuses 7–40 corridor dead ends. **The validators encode what the generator may build, not what a
   building is.** Point them at reality and reality fails.
4. **P4 is absent, and P4 is most of a bill of quantities.** No height anywhere in the product; no
   material anywhere in the product. A wall yields `length x thickness`, never `length x height`.
   A window yields width and not height, sill, glazing or frame. Concrete, blockwork, plaster,
   screed, tiling, paint, glazing and roofing are all priced by a dimension this repository does not
   possess. The strongest structure in the audit — the wall schedule — is missing exactly one axis,
   and that axis is the one the money is in.
5. **Every figure that looks like domain knowledge is self-declared as not.** `WALL_THICKNESS_M`'s
   RC value carries `PARAMETER · UNVERIFIED (regulation)`; every `ROOM_TEMPLATES` row says
   `DEMO PRODUCT POLICY placeholder, NOT verified regulation`; setbacks default to `0.0` because any
   other default *"is a planning determination this project has not made"*;
   `geometry_domain/constraints.py:14-18` deliberately excludes coverage, FAR and height ratios
   because *"turning them into geometry would produce plausible, quietly incorrect plans"*. The
   honesty is an asset. The consequence is that **the repository contains no authoritative
   construction knowledge of any kind** — and a cost engine is mostly authoritative knowledge.
6. **The first verb of the new product has no implementation.** §5: no PDF, no image, no OCR, no
   CAD, no SVG parsing, no upload route, no file input, `python-multipart` not even in the lockfile,
   on any branch, ever. "Reads existing plans" is 100 % new, and it is the step every later step
   depends on.
7. **The direction of the arithmetic is inverted.** A validator takes geometry and a policy and
   returns a boolean. A measurement engine takes geometry and returns a number with an uncertainty
   and refuses to judge it. C2's `covered == footprint_area_u` — exact integer equality — is the
   emblem: correct for a generator that controls its own grid, and guaranteed to fail on any
   surveyed plan, where digitisation slivers are normal (`resplan_ingest.py` keeps a
   `MIN_CIRCULATION_AREA_M2 = 2.0` rule precisely because real data has them). Reusing the check
   means rewriting its comparison, its tolerance and its output type — which is to say writing a
   new check with the old invariant.
8. **The product has no place to put a plan.** Persistence is a single JSON file
   (`projects/repository.py:80,102`); there is no database, no auth, no session, no project list, no
   router in the frontend, and a reload loses everything.

### 9.3 The judgement

Reuse is **real but lower in the stack than the question implies**. `geometry_domain` (1,441 L) plus
`design_output`'s gross/net discipline plus the wall schedule plus C27's integrity idea plus the
renderer and its panels is a genuine head start — call it **a third of the geometry tier and most of
the drawing tier**. The generator's concept, embedding, sizing, realization and validation-as-gate —
the large majority of `vertical_slice/` by volume — is a different product and should be isolated,
not adapted. And the things that make a measurement product *sellable* — an import path,
authoritative construction knowledge, a vertical dimension, materials, rates, suppliers — are
**absent, not weak**.

So the asset is **the geometry underneath**, as the owner's framing suspected. But note the sharpest
limit, and it is not a geometry limit: **BuildSmart has never possessed a measured number.** Every
dimension in the repository was chosen by the engine or declared as a placeholder. The pivot's first
real engineering problem is not reading a drawing — it is being able to say, of any number it
reports, where it came from and whether a surveyor may rely on it. That machinery
(`provenance.py`, `units.py`) is already here, unused at 98 % of its surface, and pointing it at
measured inputs is the whole of the new product's credibility.

---

## 10. Rebuild: what must be built from nothing, with size estimates

This is the **rebuild** half of the reuse-versus-rebuild assessment; §8 is the reuse half.
Sizes are backend Python LOC unless stated, estimated against comparable existing modules in this
repository (named for calibration). They are **estimates, labelled unverified**, and they exclude
tests, which run ~0.7–1.5x source here.

| # | must be built | size | calibration / note |
|---|---|---|---|
| 1 | **Recover and productionise the `PlanReference` ingest** — `plan_reference.py` (283 L) + `resplan_ingest.py` from `d285358` into `app/`, with provenance per element and a schema version bump | **0.6–1.0k** (mostly recovered, ~0.3k new) | the one item that is a *move*, not an invention (§2.4) |
| 2 | **An import path for a drawing.** PDF/image → vector, or DXF → geometry. **100 % new**, including the first new dependency the repo would take for ingestion, a file-upload route (needs `python-multipart`, absent from the lockfile), and an upload UI (no `type="file"` exists) | **2.5–4k** + 1 to 3 dependencies | the dominant item. A vision-assisted route has a single precedent in the repo, harness-only: `ai_harness/quality_142l/judge.py:84-94` |
| 3 | **Scale and georeference resolution** — establish metres from a drawing: a stated scale, a dimension string, a known door width, or a user-placed reference, each with a different `Authority`, plus the uncertainty that follows | **0.6–1.0k** | `resplan_ingest.py`'s `sqrt(area/area_px)` with an 0.08–0.45 m wall-thickness sanity band is the only prior art and it needs a stated area to work |
| 4 | **A measurement model with a third dimension and a material** — `Wall(length, height, thickness, construction, finishes)`, `Opening(width, height, sill, type)`, `Slab`, `Roof`, storeys, levels, finishes | **1.0–1.5k** | §3.2/§3.4. `walls.py` (248 L) and `design_output.py` are the shape to extend, not replace |
| 5 | **A quantity take-off engine** — measured geometry → BoQ lines, each carrying its formula, its inputs, their provenance and a tolerance | **1.5–2.5k** | the right precedent is `wet_core.py` and `circulation_metrics.py`: read off realized geometry, never re-derive |
| 6 | **A measurement-report layer to replace validation-as-gate** — the C27 idea generalised: every reported number with a tolerance, a residual and a confidence, and nothing refused | **0.8–1.2k** | `validation.py` is 887 L of the inverse. §9.2 item 7 |
| 7 | **A materials / assemblies / rates data asset** — build-ups, units, wastage, labour, regional rates | **not code: a data and sourcing problem** | the repository contains **zero** authoritative construction knowledge (§9.2 item 5). This is the commercial core and the largest non-engineering risk |
| 8 | **A supplier / professional directory and matching** | **1.0–1.5k** + a data asset | `app/localities/` (`streets_by_city.json`) is the only existing precedent for product reference data |
| 9 | **Regulatory / planning data** — coverage, FAR, height, setbacks by jurisdiction | **0.5–0.8k** + a data asset | `geometry_domain/constraints.py:14-18` deliberately excludes these ratios, and `site_geometry.py:20-23` has no regulation lookup. Both exclusions were reasoned and both must now be reversed deliberately |
| 10 | **Persistence** — a real database, migrations, a plan/document store, project ownership | **0.8–1.2k** | replaces `projects/repository.py:80`'s single JSON file |
| 11 | **Auth, sessions, project list, routing, file-upload UI, table components** (frontend) | **1.5–2.5k TS** | none exists: no router, no auth, no `<table>` anywhere, no state library |
| 12 | **A BoQ / cost UI** — tables, currency, totals, per-line provenance disclosure | **0.8–1.2k TS** | the panel-over-a-payload pattern is reusable (`QualityPanel`, `PlanLegend`); every component is new |
| 13 | **A reader accuracy benchmark** — ground-truth plans with known quantities, and a pre-registered error budget per quantity | **0.5–0.8k** + a data asset | `ai_harness/` is the right shape; #242 is the model. **Without this the product cannot claim an accuracy figure, and a measurement product that cannot state its error is unsellable** |

**Totals (estimates, unverified): ~11–17k backend LOC, ~2.3–3.7k frontend TS, plus three data assets
the repository has no analogue of (rates, suppliers, regulation) and one benchmark corpus.** Taking
the midpoints and allowing for the recovered and adapted parts, the honest headline is **roughly
8–11k lines of genuinely new code before anything is reusable end to end**, dominated by items 2, 5
and 7 — and item 7 is not a coding problem at all.

**The reuse/rebuild split, stated once.** Reuse is concentrated at the bottom of the stack
(`geometry_domain`) and the top (the renderer and its panels); rebuild is concentrated in the
middle, where the generator lives, plus the entire ingestion and commercial front of the product.

**What that buys in reuse:** `geometry_domain` (1,441 L), the renderer tier (~670 L TS + ~243 L
label placer + panels), `design_output`'s gross/net model, the wall schedule, the quantity
calculators (`wet_core`, `circulation_metrics`, `dead_space`), the payload discipline, the RAG
machinery, `localities`, and the harness culture. Not nothing — and not an engine.

---

## 11. Unverified, and what would settle each

| # | claim / gap | what would settle it |
|---|---|---|
| U1 | **The LOC estimates in §10.** Every figure is an engineering estimate calibrated against existing modules; none is a measured plan | a spike that builds item 4 (the measurement model) end to end against three fixtures, then a re-estimate |
| U2 | **Whether a measured plan's quantities can be produced at a credible accuracy.** Nothing in the repository has ever compared a computed quantity to a surveyed one | item 13: a ground-truth corpus with known quantities, and a pre-registered error budget. **This is the gate on the whole pivot, and it is cheap** |
| U3 | **Whether the `PlanReference` schema is sufficient for a take-off.** It carries no height, no material, no per-wall thickness; `derived.wall_thickness_m` is one plan-wide scalar | map one real plan's full BoQ by hand and list every field the schema cannot supply |
| U4 | **Whether `realize_cells` could carry real plans with the validators *relaxed*.** #242 deliberately ran the validators **unchanged** and says so: *"That a different representation … would carry these plans — nothing here ran one"* | a second arm with the per-cell checks replaced by per-room ones. #242's own §8.6 scopes it |
| U5 | **Whether the ~200-plan `resplan_*.json` corpus on `d285358` is still usable** — licence (CC BY 4.0 recorded), completeness, and whether the ingest still runs against today's shapely | check out the branch into a scratch worktree and run `build_fixtures.py`. Not done here: out of scope for a read-only audit, and it would need a dependency resolve |
| U6 | **Whether `WALL_THICKNESS_M`'s 0.10 m partition and 0.30 m exterior are near any real build-up.** The code labels the RC value unverified and is silent on the other two | a quantity surveyor's review of the four constants. Cheap and it should precede any quantity claim |
| U7 | **Whether `geometry_domain`'s arc support actually works.** `arc_radius`/`arc_sagitta`/`arc_segment_area`/`bulge_from_three_points` exist and `BoundaryEdge` carries a bulge, but no production caller was found that constructs a curved edge — every observed construction is `Ring.rectangle` or a rect conversion | grep the tests for a non-zero bulge and run them; if none exists, the curve support is untested |
| U8 | **Whether `architect/real_gateway.py`'s wire protocol works at all.** Its own docstring `:3-13` declares it an unconfirmed placeholder never verified against a real endpoint, and the default provider is `mock`, so no production run has ever exercised it | point it at a real endpoint in a scratch environment. Needs spend; **not done here** |
| U8b | **Whether the `app/knowledge/` retrieval stack performs well with a real semantic provider.** The default is the `hash` provider (`embeddings/factory.py:70`), so the vector channel has, in effect, never been evaluated on this corpus | build the index with `KNOWLEDGE_EMBEDDING_PROVIDER=openai` or `huggingface` and compare recall. Needs a model call or the optional extra |
| U9 | **Whether the exact-integer closure in C2 can be given a tolerance without losing its proof value.** Argued in §9.2 item 7, not demonstrated | implement the tolerant variant and run it against the 19 fixtures, reporting the residual per plan |
| U10 | **Courtyards and holes.** #238 §3 left this unverified and nothing here changes that: a hole in a footprint is representable as a union in principle, and `remainder_within_bbox` would classify it as garden | real plans with a courtyard through the reader path, once one exists |
| U11 | **The `polygon` field on `SelectedFootprint`** (`projects/models.py:266-269`) is stored and, per its own comment, *"read by NOTHING downstream today"*. Whether it is a usable inbound polygon channel is unverified | trace one request with a polygon set and see where it stops |
| U12 | **Whether the frontend's `orientation: 'horizontal' \| 'vertical'` wall model is the binding limit for drawing a read-in plan** | one real plan with a non-orthogonal wall through `DemoPlan.tsx` |

---

## 12. What this audit cites rather than re-derives

### 12.1 #238's diagnosis — merged, `main`

`docs/reports/architectural-intelligence/ROOT-CAUSE-diagnosis.md` (PR #241, merged at `e379855`).
Cited for: the stage-by-stage vocabulary (§1.2), the four seams where intent is lost (§1.3), what
the representation can and cannot express (§3), and the ten reusable / ten limiting components
(§7.1, §7.2). **This audit extends it to a different product rather than repeating it:** #238 asked
whether the representation can express architecture; §1 here asks whether the structures carry a
priceable dimension. The two agree on which half of the system is sound and disagree about what
that is worth: #238 preserves the geometry tier *for generating*; this audit preserves a third of it
*as a library* and finds the validation tier reusable only with its direction reversed.

### 12.2 `ResPlan → PlanReference` (#94, #95)

Cited in §2.3, §2.4, §5.4 and §10 item 1, **with the two corrections in §2.4**: the ingest is not on
`main`, and its input is a vector dataset with a stated area, not a drawing.

### 12.3 #242's R1 — measured, **not merged**

`docs/reports/architectural-intelligence/R1-representation-ceiling.md` on
`origin/agent/242-r1-the-representation-ceiling-can-realiz`; harness at
`backend/app/ai_harness/representation_ceiling/`. **PR #254 was closed on 2026-10-24 without being
merged** (`mergedAt: null`), and neither the report nor the harness exists at `c07bf71`
(`git ls-tree -r origin/main | grep representation_ceiling` → 0). Issue #242 is still open and
labelled `agent:blocked`; the blocker is the known platform-dependent
`test_skipping_the_group_reproduces_the_previous_band_sizing_exactly`, which #255 is fixing.

The evidence is nevertheless **measured, pre-registered and reproducible**: sections 1–7 of the
report and the frozen thresholds in `representation_ceiling/frozen.py` were committed at `bbffde3`
**before the first run on any real plan**, the verdict is computed by `frozen.verdict`, and the
committed data is checked against it by `test_the_committed_results_are_consistent`. §9.2 items 1–3
rest on it, and this is the honest status: **the strongest single piece of evidence in this audit
sits on a closed PR's branch and is not on `main`.** Landing it — in whatever form, under ROOT #237
or this one — is the cheapest way to make the pivot decision defensible.

### 12.4 The 32 validators

Enumerated from `validation.py`: C1–C31 and C33 (C32 absent) — **32 distinct checks**, 887 lines.
Cited in §3.5, §8.1 rows 7–9 and §9. The audit's own contribution is the distinction between the
**arithmetic** they compute (reusable, in the right units, already on the payload) and the **gate**
they apply (product policy, measured by #242 to refuse 18 of 19 real plans for reasons unrelated to
geometry).

---

## 13. Method, and what no claim here rests on

Read in this worktree at `c07bf71`. The only product command run was the static import check
(`STATIC-IMPORT-OK`). No solver, no corpus suite, no benchmark, no model call, no network, no
dependency, no spend. The generator is untouched: `git diff origin/main` for this Issue adds exactly
one file, this report.

**No claim here rests on:** any wiring or capability table (§6 verifies by imports, per #245's
finding); #213's "19 payloads, 2–12 wings" (#238 §7.3 found it not reproducible); any figure in
`ROOM_TEMPLATES`, `WALL_THICKNESS_M`, `DOOR_WIDTH_M` or the setback defaults being a real-world
value — each is cited as a self-declared product-policy placeholder and used only as evidence of
what the repository does *not* know; or on #242's result being on `main`, which §12.3 states it is
not.

**Not designed here, deliberately.** ROOT #256 §2 arrived truncated — a heading with no content —
and the directive says to audit before designing. §10 says what is missing and how big; it does not
say how to build it, and nothing here proposes a module layout, a schema or a sequence for the new
product.
