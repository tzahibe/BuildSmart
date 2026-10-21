# Root-cause diagnosis — why the plans still read as room packing, and whether this representation can evolve

**Issue #238, first child of ROOT #237. Read-only: no product code, no dependency, no model call, no
paid service.** Every claim below was read from the code in this worktree at
`5b155d1` (`#205 — minimum foyer/hall geometry in the exact sizer`), branch
`investigate/architectural-intelligence`, or is cited from an existing merged report with its file.
Nothing was solved, benchmarked or re-measured: #226's quiet measurement window was open throughout,
so the only command run was the static import check (`python -c "import app.main"` → ok). Where a
claim could not be settled by reading, it is labelled **unverified** and §11 says what would settle
it.

ROOT #237 names four findings as already measured and instructs that they be consolidated rather
than re-derived. §9 does that, with citations. The new work is §1–§8.

---

## 0. The answer, in one page

**The seven questions, compressed.**

1. **Where architectural intent first exists.** In `HouseConcept` (`vertical_slice/spec.py:318`) —
   six enum fields, five of which default to `ENGINE`, and *one* of which the product can set
   (`requirements_view.spec_for:490` sets only `public_open_side`). `spec.py:260-263` says of its own
   type: *"Nothing in the geometry stack reads `HouseConcept`."* Intent is **created** there and in
   `brain/proposer.PARTIS:411`; it is **transformed** into a contact graph, then into band rows, then
   into rectangles; it is **lost** at four named seams (§1.3).
2. **Does the concept stage reason about composition?** No. A production concept is
   `Concept(fixture, entrance_zone_id, street_side, footprint_width_m, footprint_depth_m)`
   (`concept.py:76`) — a slicing tree plus two floats. A brain parti is
   `TopologyProposal(name, rationale, spatial, access, arrival)` (`brain/proposer.py:92`) — two lists
   of room-id pairs and one room id. Both are **named topologies over a row grid**, not spatial
   compositions. The five production "strategies" that matter re-label **two tree shapes** (§2).
3. **What the representation can express.** Non-rectangular *building outlines*: **yes** (unions of
   wings, already shipped as the 2-wing L). Non-rectangular *rooms*: **no** on the shape-agnostic
   path — `realize_cells` hard-codes one cell per zone (`rectilinear_realizer.py:1257-1258`).
   Courtyards: **unverified**, representable in principle, never tested. Spatial hierarchy: **no** —
   there is no type for it. Full verdicts in §3.
4. **Does realization destroy intent?** Mostly it **refuses** it, loudly and with proofs — and that
   is the system's best property. But it **destroys** four things silently, including the compass and
   the parcel (§4). Destroyed and refused need different fixes and §4 gives examples of each.
5. **Does ranking favour the measurable?** Yes — exclusively. The full term lists are in §5: nine
   terms in the brain's rank key, seven in `primary_selection._lex_key` (which has **no production caller**), seven in
   the generator's pre-order (two of them disabled no-ops). **No term anywhere for**: sun, view,
   noise, per-room daylight, open-vs-closed plan, massing quality, spatial hierarchy, privacy, or
   arrival-room usability.
6. **Site conditions.** #223's finding holds at this head, and the mechanism is one line:
   `rectilinear_realizer._build_site:1379-1389` sets `plot = footprint + 2 m` and `parking=()`. The
   site data the concept would need **already exists** in `demo/site_geometry.SiteGeometry` and is
   thrown away by the type that replaces it (§6).
7. **Reusable versus limiting.** Two lists in §7 — ten reusable components and ten limiting ones. The rectangle-only claim is **verified** for the
   site input, placement-and-sizing-in-one-rectangle and the x-stacked wing composition;
   **partly verified** for the downstream, which is union-of-rects for its geometry carriers but
   still holds four rectangle *formulas* (C27, C9, C30, C14) and a bounding-box street line.
   #213's specific numbers ("19 payloads, 2–12 wings") are **not reproducible in this worktree**
   (§7.3) — the mechanism is corroborated by code, the count is not.

**The architecture decision (§10), stated plainly.** The geometry half does **not** need redesign and
should be preserved almost unchanged. The concept half should be **replaced, not extended**, and the
pipeline order inverted: today the footprint is committed by area arithmetic before any room exists,
the entrance is discovered after the geometry, the garden is whatever is left over, and the compass
is discarded at the first stage boundary. No amount of extra scoring, extra compilers, extra MILP
constraints or a stronger model reaches those four facts — they are ordering and vocabulary, not
search. That is an evolution of the lower half and a redesign of the upper half, and the one thing
that would falsify it is the representation ceiling, which has never been measured.

**The one next experiment (§11).** Measure that ceiling: push the 19 real professional plans already
committed in this repo through `realize_cells` and the **unchanged** validators, and report what the
representation can and cannot carry, with the failing check named per plan. Harness-only, no solver,
no model, no dependency, deleted on STOP. GO and STOP numbers are fixed in §11.2 before it runs.

---

## 1. Question 1 — where architectural intent first exists, and the vocabulary of each stage

### 1.1 The real pipeline at this head

Two paths leave the same request. `demo/router.py:306` `generate_demo_plan(project_id, engine=...)`
dispatches on `?engine=`: `_engine_override:202`, `_brain_requested:214`, `_rear_band_requested:220`.
`ENGINE_BRAIN = "brain"` (`router.py:193`) and `ENGINE_E1_REAR_BAND` are **development previews**;
the default is production. `general_pipeline.CONCEPT_ENGINE_V2_ENABLED = False` at `:120`, so
Concept Engine v2 is inert unless asked for by name.

```
projects.models.Project                  person's words: plot w/d, street_facing_side (COMPASS),
                                         built_area_m2, bedrooms, parking_spaces, free text,
                                         selected_footprint(shape_type Literal["RECTANGLE"])
  -> demo/scope.check_supported          refuses outside scope, never downgrades (scope.py:1-8)
  -> demo/site_geometry.derive:158       SiteGeometry: parcel + compass + setbacks  [RICHEST POINT]
  -> demo/requirements_view.spec_for:447 ArchitecturalSpec = PlotSpec + ProgramSpec + HouseConcept
  -> demo/service._outlines_for:438      Outline(width_m, depth_m, origin, massing)  [MASSING DECIDED]
  -> demo/service._plan_outlines_until_one_plans:549
  -> vertical_slice/general_pipeline.run_general
       concept_generator.generate_concepts:4556  -> ConceptCandidate / Concept / Fixture
       geometry_core.engine.solve_fixture        -> dict[zone_id, Rect] + WallMap
       _realize:840                              -> doors, windows, furniture, validate(), assemble
  -> demo/contract.to_demo_design        the API payload
```

and, only for `?engine=brain` (`service.py:327-332`, `_brain_result:920`):

```
  selection.primary (PRODUCTION already chose the outline)
  -> run_brain(spec, (outline.width_m, outline.depth_m))        service.py:925
       brain/proposer.programme_from_spec:172  -> Programme (rooms + zone area bands)
       brain/proposer.DeterministicProposer.propose:429 -> up to 10 TopologyProposal
       proposal_critic                          -> typed HARD/WARN findings, no repair
       brain/exact_pipeline.run:                 families ("band","spine","stack","cells")  :44
         band_embedding.embed_band:519          -> BandPlacement rows/spans | typed refusal
         exact/milp_oracle, exact/milp_cells    -> cell rectangles (scipy HiGHS)
         rectilinear_realizer.realize_cells:1222-> RealizedLayout | Refusal(check named)
       brain/runner._plan_key:376               -> the 9-term preference
  -> demo/contract.to_demo_design
```

### 1.2 The vocabulary each stage speaks

| stage | file:line | its vocabulary — the actual field names |
|---|---|---|
| person | `projects/models.py:256,303,409` | `plot_width_m`, `plot_depth_m`, `street_facing_side`, `built_area_m2`, `bedrooms`, `parking_spaces`, `selected_footprint.shape_type: Literal["RECTANGLE"]`, `polygon` (stored, **read by nothing** — `models.py:266-269`) |
| site | `demo/site_geometry.py:61` | `SiteGeometry(plot_width_m, plot_depth_m, street_facing_side, canonical_width_m, canonical_depth_m, front/side/rear_setback_m)` + `behind_parking_band`, `feasible_options:384`, `l_massings:484` |
| spec | `vertical_slice/spec.py:19,199,318` | `PlotSpec(width_m, depth_m, 3 setbacks)`; `ProgramSpec(bedrooms, safe_room, open_plan_living, wet_rooms, parking_spaces, corridor, relationships, wet_room_kinds, laundry, target_built_area_m2)`; `HouseConcept(stories, public_private_strategy, entrance_level, master_level, bedroom_grouping, circulation_style, public_open_side, level_area_preferences, family, source, hard_fields)` |
| outline | `demo/service.py:364` | `Outline(width_m, depth_m, origin, index, massing)` — the whole massing vocabulary |
| production concept | `vertical_slice/concept.py:76` | `Concept(fixture, entrance_zone_id, street_side, footprint_width_m, footprint_depth_m)` |
| fixture | `geometry_core/model.py:424` | `Fixture(name, wings, zones, access, open_groups, outdoor)`; `Wing(origin, w_u, h_u, tree, seam_leaf_sides)`; `Node = Leaf | Split(Cut.V|Cut.H, …)`; `ZoneSpec(zone_id, roles, 3 areas, min_short_side_m, max_aspect_ratio)` |
| brain programme | `brain/proposer.py:119` | `Programme(public, bedrooms, ensuites, shared_wet, safe_room, flex, zones, footprint_m, net_available_m2, capacity_m2, requested_m2, full_bounds)` |
| brain concept | `brain/proposer.py:92` | `TopologyProposal(name, rationale, spatial, access, arrival)` |
| embedding | `band_embedding.py:78` | `BandPlacement(rows: tuple[tuple[(zone_id, col_span)]], n_cols, score, bands, flags)` |
| realization | `rectilinear_realizer.py:259,307` | `RealizationIntent(name, wings, entrance_hint_zone_id, declared_adjacency, declared_exposure, wet_rooms)`; `RealizedLayout(rects, walls, site, doors, windows, furniture, report, design)` |
| payload | `design_output.py:114`, `demo/contract.py:719,748` | `footprints_m: tuple[RectM, ...]`, `RoomOut.shape: Literal["RECTANGLE","L"]`, `RoomOut.polygon_m` |

Read down that column and the diagnosis is already visible. The richest architectural vocabulary in
the whole chain is at the **top** (a parcel with a compass bearing) and at the **bottom** (per-room
polygons and per-wing footprints in the payload). The middle — where design would happen — speaks
`Cut.V | Cut.H`, `(zone_id, zone_id)` pairs and `(zone_id, col_span)`.

### 1.3 The four seams where intent is lost

| seam | file:line | what is lost |
|---|---|---|
| `site_geometry.derive` → `spec_for` | `site_geometry.py:63-69`, `requirements_view.py:466-472` | **the compass.** `street_facing_side` is used only to rotate the parcel into a canonical frame where "the street lies along the y=0 edge", then dropped. `PlotSpec` has no orientation field. Outside `app/demo/` the only occurrence of `street_facing_side` in `app/` is a *disclosure string* in `ai_harness/quality_142l/metrics.py:451`. A north-facing and a south-facing plot of the same size produce the same spec. |
| `spec_for` → everything | `spec.py:260-263` | **the concept.** `HouseConcept` carries six intent fields; its own comment states *"Nothing in the geometry stack reads `HouseConcept`"*. `spec_for:490` can only ever set one of them. |
| `_outlines_for` → `generate_concepts` | `service.py:438-469`, `concept_generator.py:4556` | **the parcel.** `generate_concepts(spec, candidates, *, public_orientation)` receives rectangles from `safe_adapter`, and `grep "spec.plot" concept_generator.py` returns **zero hits**. The footprint's size, proportion and position are already fixed. |
| `generate_concepts` → `solve_fixture` | `general_pipeline.py:946` | **the reason.** `solve = solve_fixture(candidate.concept.fixture)` — one argument. `street_side`, `entrance_zone_id`, the strategy, the rationale, the spec and the whole site are invisible to the solver; the entrance is then *recomputed* and overwritten at `general_pipeline.py:862-863`. |

The brain path adds a fifth: `programme_from_spec(spec, footprint_m)` (`brain/proposer.py:172`) reads
`spec.program.*` only — `spec.plot` is never touched, and `footprint_m` is *"a bare (w, d) pair — a
size, not a place."*

---

## 2. Question 2 — does the concept stage reason about spatial composition?

### 2.1 The brain's parti set, enumerated, with the architectural idea each encodes

`brain/proposer.PARTIS:411`, five builders; `_with_and_without_foyer:452` doubles each where
`net_available_m2 >= FOYER_MIN_NET_M2 = 85.0` (`:58`), so at most **10 proposals per brief**.

| parti | builder | the architectural idea, as the code encodes it |
|---|---|---|
| `HALL_SPINE` | `:338` | one hall serves everything; only the **first** public room touches it — the classic corridor house |
| `PUBLIC_BAND` | `:347` (needs ≥2 public) | every public room meets the hall, so the public rooms read as one band with circulation behind |
| `BEDROOM_WING` | `:359` (needs ≥3 bedrooms) | `_chain(p.bedrooms)` added to **contacts only** — the bedrooms group into a block; doors stay on the hall (C24) |
| `TWO_HALL` | `:372` (needs ≥3 bedrooms) | an entry hall for the public half, a second quieter corridor for the bedrooms |
| `SERVICE_CORE` | `:394` (needs ≥2 shared wet) | the shared wet rooms touch each other as one plumbing core |
| `+FOYER` ×5 | `:452` | `ENTRY` as a degree-2 room between street and arrival: `street → foyer → hall` |

These are real architectural ideas, honestly named — and the entire representation of each is
`spatial: tuple[tuple[str,str],...]`, `access: tuple[tuple[str,str],...]`, `arrival: str`. There is
no dimension, no side, no orientation, no outdoor space and no massing in a parti. The module's own
docstring (`:11-24`) states the design constraint: *"Every parti below is a TREE of contacts (a hub,
or two hubs joined) optionally plus ONE path through the public rooms"* — chosen so that
`band_embedding` can always carry it. The concept space was deliberately narrowed to what the
existing geometry family can represent. That is good engineering and it is also exactly why the
output converges.

### 2.2 Production's concept space is two tree shapes

`concept_generator.ConceptStrategy` has eight values (`:325`) and `concept_spec.CirculationClass`
six (`:48`), but the geometry behind them is:

| tree shape | built at | shape |
|---|---|---|
| **spine** | `concept_generator.py:2976` | `Split(Cut.V, west_tree, Split(Cut.V, Leaf("HALL"), east_tree, hall_w), west_w)` |
| **front/rear band** | `concept_generator.py:3310` | `Split(Cut.H, band_tree, rear, band_depth)` — where `rear` is the spine tree above |
| (hub) | `_hub_concept:4070` | measured **0 of 60 briefs** offered a hub candidate (`docs/CONCEPT_ENGINE_V2_INVESTIGATION.md:97`) |
| (L / two-wing) | `l_parti.py:735` | only when `_two_wing_pair:4530` finds two adjacent safe wings — 7 of 60 briefs |

All five `_allocations` entries (`:3003-3047`) differ **only in which rooms go west versus east**.
`docs/CONCEPT_ENGINE_V2_INVESTIGATION.md:116-118` states it in the project's own words: *"Routinely
only two tree shapes exist (spine and front band). Five strategy names re-label one tree."*

The compilers do not widen it. `concept_compilers.compile:114` for `SPINE`/`FRONT_BAND`/`TWO_WING`
calls the same generator and **filters** its output by declared class (`:130`) — no new geometry.
`compile_hub_lobby:429` is a single hand-authored tree emitting exactly one candidate, gated to
2 bedrooms and 2–3 wet rooms (`:303-305`). `compile_branched:673` **declines unconditionally** since
#130 (`:652-658`): three corridor dead ends against C26's limit of two.

And the vocabulary that *could* name composition is inert. `concept_spec.MasterPlacement:98` and
`EntranceSide:113` are annotated in the source as *"not read by any generator today"*.
`concept_spec.py:28-30`: *"Nothing in `general_pipeline.py`'s selection, ranking or the shown set
reads any of this."* `Fixture.outdoor` exists (`model.py:431`) and `grep "outdoor=" vertical_slice/*.py`
returns **zero hits** — no concept builder has ever set it.

### 2.3 Verdict

**Named topologies over a row grid.** Both concept stages reason about *which room touches which*
and nothing else. Neither reasons about where the building sits, which way it faces, what it is
shaped like, what is outside it, or what a person walking through it experiences. The brain's partis
are the better of the two — they are at least named for architectural ideas and they do change the
contact graph — but E1's own review of a successfully flipped plan is the measured verdict on what
that buys: *"It is a reversed room-packing pattern. … the circulation is bit-for-bit the same …
nothing about the organisation of the plan is different. One axis was flipped."*
(`docs/reports/e1-orientation/README.md:319-327`).

---

## 3. Question 3 — what the representation can and cannot express

Each verdict is about the **shape-agnostic path** (`realize_cells` + the unchanged validators +
payload + renderer), which is the most capable path in the system, unless stated otherwise.

| dimension | verdict | the code that proves it |
|---|---|---|
| **Massing — a non-rectangular building outline** | **YES, and already shipped** | the footprint primitive is `tuple[Rect, ...]` (`footprint.py:1,21`); `SitePlan.wings` (`site.py:62`); exposure is per-wing (`geometry_adapter.envelope_sides:91,104`); C2 measures *"the WINGS' area, not the bounding box"* (`validation.py:323-326`); the payload carries `footprints_m` (`design_output.py:114`) and `DemoPlan.tsx:115-119` draws one `<rect>` per wing. The product's own outline menu already contains a 2-wing L (`site_geometry.l_massings:484` → `service.py:468` → `l_parti.py:702`). |
| **Massing — chosen by the concept** | **NO** | the outline is picked from a menu of ≤4 rectangles at `PREFERRED_RATIOS = (0.95, 1.15, 0.75, 1.45)` (`site_geometry.py:381,384`) plus fixed-arm L massings (`:489-491`), before any room exists; then `choose_footprint` applies a single constant `_FOOTPRINT_ASPECT_PREF = 0.82` (`concept_generator.py:315`). |
| **Wings** | **YES as geometry, NO as composition** | `realize_cells:1222` accepts *"any arrangement of non-overlapping cells whose union is the union of `wing_rects`"*. But the composing entry `realize_layout:1407-1418` places wings with `cursor_x += wb.size[0]` at a **fixed `origin[1]`** — wings can only be stepped along x. |
| **Stepped footprints** | **YES** | the same loop: differing wing heights at a shared base line give a histogram/staircase outline, and `_build_site`'s `remainder_within_bbox` classifies the step as garden (`rectilinear_realizer.py:1385-1388`). Gate 3 realized stepped plans (`docs/reports/shape-agnostic-realizer/GATE-3-verdict.md:52-64`). |
| **Courtyards (a hole in the footprint)** | **UNVERIFIED — representable in principle, never tested** | ADR-001 reasons it through and names it a Gate-3 *question*, not a result: *"A courtyard (a hole) is representable as a union too, but the hole would be classified by `remainder_within_bbox` as garden and its walls as exterior by `envelope_sides` — plausible, **untested**"* (`ADR-001-shape-agnostic-realization.md:50-54`). Gate 3's F5 case is named "garden-court" and solved (`GATE-3-verdict.md:21-23`), but that is a court **beside** the house, not enclosed. There is no outdoor-room type a courtyard could consume area as: `Fixture.outdoor` is never populated. |
| **Non-rectangular rooms** | **NO on the shape-agnostic path** | `realize_cells` sets `zone_of_cell = {z: z for z in rects}`, `groups = {}` and `open_pairs = set()` and never changes them (`rectilinear_realizer.py:1253-1264`) — one cell is one zone with its own `ZoneSpec`. Its own comment records the attempt and the result: *"Splitting a partially-abutted cell into same-zone fragments was tried here and measured: C20/C9/C24/C31 run per cell and reject the fragments. Steps must land on cell boundaries"* (`:1245-1249`). Polygon rooms exist only via two narrow mechanisms: `room_merge.py` (LIVING+KITCHEN, 2-way, live in the product) and `ShapeGroupIntent` notch-carve L/U/T confined to *"a SINGLE ROW spanning the full envelope depth"* (`:33-37`). Against the corpus: 41.9 % of real rooms are rectangles and 19.6 % simple L's (`docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md`). |
| **Spatial hierarchy (public→private gradient, a room that is the house's centre)** | **NO** | there is no type for it. `ZoneGroup` (`concept_generator.py:318`) has `PUBLIC/PRIVATE/SERVICE/CIRCULATION` and is a *label on a room*, not a relation. The nearest ranking term is a label-match flag, `_strategy_preference_violated` (`primary_selection.py:116-119`), in a function with no production caller. `concept_spec.ZoningSplit:71` (`SIDE_BY_SIDE/FRONT_REAR/WRAPPED`) is read by nothing (`concept_spec.py:28-30`). |
| **Circulation as a place rather than a residue** | **NO** | C20's aspect cap excludes circulation deliberately (*"a corridor is a strip by definition"*), C14 measures a width, and the hall is the loosest-bounded cell in a grid that tiles exactly — so surplus lands there. `brain/proposer.py:56-73` documents this as a measured allocation defect, and that capping the hall made it worse (B16: three plans → one). |
| **Where the house sits on its parcel** | **NO** | §6. |

**Where the representation already does more than the product allows.** Verified: the geometry
carriers (footprint, site, exposure, windows, doors, C2/C8/C13/C19/C22, payload, renderer) all take
unions of rectangles, and the orthogonal-polygon envelope type **already exists** —
`envelope.py:1-10` describes itself as *"the one input the shape-agnostic realizer needs that nothing
in the pipeline had"* — while `brain/exact_pipeline.py:128` feeds it `Envelope.rectangle(*inp.footprint_m)`.
The product's input contract is rectangle-only by **type**: `SelectedFootprint.shape_type:
Literal["RECTANGLE"]` (`projects/models.py:273`), refused again at `demo/scope.py:362`, and
`site_geometry.py:20-23` scopes the parcel to *"Rectangular parcels only … No polygons"*.
So for **outlines** this is a plumbing problem, not a representation problem. For **rooms** it is a
representation problem, and the blocking checks are named: C27 (`validation.py:159`, width × depth ==
area), C9/C30 (`:518,202`, inscribed rectangle), C14 (`:269,685`, corridor width = short axis).

---

## 4. Question 4 — destroyed intent versus refused intent

The distinction matters because the fixes differ: a *refusal* needs a wider representation or a
better explanation; a *destruction* needs a seam repaired and, usually, a disclosure.

### 4.1 Refused — intent rejected with a reason (this is the system at its best)

- **`band_embedding` representation pre-checks.** `representation_precheck:166` returns
  `TOPOLOGY_NON_PLANAR` (`:174`) or `TOPOLOGY_REPRESENTATION_LIMIT` (`:180`, `:188`) for a K4, a
  non-planar graph, or an edge whose endpoints share ≥3 neighbours — each forcing a separating
  triangle no rectangle dissection can carry (Koźmiński–Kinnen 1985, cited in the module docstring).
  `BandEmbeddingRefusal` carries `proof_complete` (`:118-129`): the refusal states whether it is a
  **proof** or a budget exhaustion (`EMBEDDING_SEARCH_EXHAUSTED`, `BAND_UNSAT` at `:735,739`).
  *"Partial topology is never returned."*
- **The #160 topology→placement bridge.** `docs/reports/topology-placement-bridge/results.md`: 0 of
  5 representative briefs realized, 4 refused as `ROW_CAPACITY_EXCEEDED` with the arithmetic in the
  message (*"needs 14 spatial-adjacency relationships among 9 rooms; a single row can realize at
  most 8 (n-1)"*), 1 as `SHORT_SIDE_INFEASIBLE` with the measured millimetres. A refusal that names
  its own bound is what let the band family be built next.
- **`PublicOpenSide.GARDEN`.** `spec.py:292-299`: *"`GARDEN` names a parti the generator does not
  have yet … a concept that BINDS it is refused as an unsupported hard requirement rather than
  quietly honoured as `STREET`."*
- **`realize_cells` validation.** `rectilinear_realizer.py:1363-1366` returns
  `Refusal("VALIDATION_FAILED", …)` listing the failing check ids rather than a plan.
- **Scope.** `demo/scope.py:1-8`: *"Everything outside the envelope is REFUSED with a product-level
  reason. Nothing is silently downgraded: a four-bedroom brief never becomes a three-bedroom house."*
- **The subtree open-group limit.** `geometry_core/engine.py:97-114` `_mark_open_interfaces` opens a
  split boundary only when `inside_one_group = any(subtree <= set(g) for g in open_groups)` (`:103`),
  because *"the structural marking can only open the CUT LINES of the slicing tree … and every
  subtree occupies a rectangle"* (`:126-131`). The generator surfaces it as
  `RejectionReason.OPEN_GROUP_INCOMPATIBLE` (`concept_generator.py:377`). This is the mechanism
  behind Concept Engine v2's inability to express branched or ring circulation as *"one more
  strategy"* (`docs/CONCEPT_ENGINE_V2_INVESTIGATION.md:127-132`).

### 4.2 Destroyed — intent silently changed

- **The compass.** `street_facing_side` is consumed by `site_geometry.derive:172-183` to rotate the
  parcel and never appears again in planning. No warning, no payload field, no disclosure. The
  project's own metrics register already states the consequence:
  *"The brief carries `street_facing_side` (e.g. NORTH) so facade orientation is KNOWN, but no room
  carries a solar, view or noise requirement … Facade metrics therefore treat every side as equal"*
  (`ai_harness/quality_142l/metrics.py:451`).
- **The parcel, in the brain path.** `rectilinear_realizer._build_site:1379-1389` builds the site
  **from the building**: `plot = Rect(0, 0, footprint.x2 + 2 m, footprint.y2 + 2 m)`, the entrance at
  the footprint's x midpoint, garden = only `remainder_within_bbox(wings)` (nothing at all for a
  rectangular footprint). This is precisely the defect `site_geometry.py:1-19` was written to
  eliminate — its docstring calls it *"the honest relationship run backwards"* and shows the same
  `plot = footprint + setbacks` formula — reintroduced one layer down. `realize_cells` calls it at
  `:1334`, so every brain-preview plan has a synthesised plot.
- **Parking, in the brain path, with a validator that passes by absence.** `_build_site` sets
  `parking=()`. The checks that exist for parking then pass vacuously: C10 (`validation.py:552-555`)
  and C18 (`:557-563`) both test *the bays that are present*, so with none they report
  `"0 bays front the street"` and PASS. Contrast C17, where the codebase applies the opposite rule on
  purpose: *"a wet zone the requirements do not cover … is a failure, never a pass by absence."*
  A brief asking for two parking spaces gets a plan with none, and no check and no notice says so.
- **The entrance.** `general_pipeline.py:862-863` overwrites `concept.entrance_zone_id` with
  `doors_stage.resolve_entrance`'s answer — whichever room already happens to touch the bounding
  box's `y = min` line, in role priority order. The concept's own nomination is discarded without a
  note. (`docs/reports/architecture-direction/README.md:165-172` measured the same thing.)

### 4.3 Between the two: disclosed degradation

`realize_cells:1234-1236` — *"a pair that does not actually touch is dropped here and will be
reported missing by `topology_preservation` — never patched."* Intent is lost, but it is counted and
reported (`plan.spatial_preserved` / `access_preserved` reach the plan notes at `service.py:941-943`).
This is the pattern the destroyed cases in §4.2 should be converted to, and it already exists.

---

## 5. Question 5 — both rank keys, every term, and the qualities with no term

There are two rank keys that matter (the brain's and production's) plus one weighted scalar in
Concept Engine v2. Every term of each is listed below.

### 5.1 The brain's key — `brain/runner._plan_key:376`

`_plan_key` is not a key of its own: it re-applies the candidate preference to a finished plan.
`_preference:262` dispatches on `SELECTION = "proportion"` (`:222`) → `_proportion_preference:241`,
which wraps `_entrance_preference:154` and splices two terms in at indices 3–4 (`:257`). Nine terms,
lexicographic, all ascending:

| # | term | file:line | measures |
|---|---|---|---|
| 0 | `0 if arrived == intent else 1` | `:205` | the front door opens into the parti's declared arrival room |
| 1 | `0 if target.y == fp.y else 1` | `:206` | that room reaches the street elevation, so it *can* hold a front door |
| 2 | `0 if lo <= gross <= hi else 1` | `:207` (`AREA_TOLERANCE = 0.10`, `brain/area.py:33`) | gross area within ±10 % of the request — in/out only |
| 3 | `round(dev)` | `:256`, `proportion_metrics:225` | mean relative deviation of habitable rooms from target area, % |
| 4 | `round(circ)` | `:256`, `:234` | circulation's share of net floor, % |
| 5 | `-on_garden` | `:200,208` | count of public rooms on the garden (south) elevation — **the only outdoor-relationship term in the system** |
| 6 | `round(abs(gross - requested), 1)` | `:209` | fine-grained area distance, m² |
| 7 | `round(circ_area, 1)` | `:210` | absolute circulation area, m² |
| 8 | `round(worst_wet, 2)` | `:211` | worst wet-room aspect ratio |

Partis are ranked by the same key — `BrainResult.distinct:122` sorts on `rank_key`, and
`_improve_exactly:398` orders partis for the exact sizer by it, replacing a plan only when the exact
key is not worse (`:427-429`). The only other brain-side ordering is a single-term pre-sort,
"does the arrival room front the street" (`exact_pipeline.py:181,264`).

### 5.2 Production's keys

**`primary_selection._lex_key:149-153`** — seven terms: `preference_violations` (`:122`, the sum of
two booleans: open-plan preference violated, strategy label mismatched), `worst_bed_aspect`,
`master_aspect`, `quality_warning_count`, `total_circ_core_pct`, `delivered_dist`, `index`.
**`select_primary` has no production caller** — only `building_coordinator.py` comments and its own
tests.

**The live production order** is two stages. The generator's pre-order,
`concept_generator.py:4730-4733`: `|used_area − target|`, is-fallback, `over_preferred`, used area,
`strategy.value` (alphabetical), `priors_score`, `adjacency_score` — and the last two are **no-ops at
default config** (`ROOM_PROPORTION_PRIORS_ENABLED = False`, `ADJACENCY_PRIORS_ENABLED = False`), so
the key effectively ends at the **alphabetical strategy name**. Then the realize loop,
`general_pipeline.py:522-570`: `arrival_policy.arrival_rank` (0 hall/circulation, 1 living, 2 other),
area equality, `entrance_sequence_prefers` (which compares only `distance_to_public_m`),
`composition_prefers`. `circulation_metrics` is excluded on purpose (#142N: non-transitive).

**Concept Engine v2** is the one weighted scalar: `ConceptScore.key():151` = `(rejected, -total, index)`
with `total` (`concept_score.py:212-230`) summing bedroom aspect ×4, master aspect ×4, circulation
share ×20, hall aspect ×6, hall door count ×0.5 (**more doors scores better**), wet adjacency ×10,
plumbing complexity ×1, entrance rank ×3 — and **no area term at all**.

### 5.3 The architectural qualities with no term

| quality | verdict |
|---|---|
| sun / solar orientation | **no term anywhere.** No `sun`/`solar` identifier in any key. `concept_generator`'s `north_is_envelope` is an envelope-contact test, and its callers pass `True` as a literal (`:2307,2309,2605`). |
| view, outlook, noise | **no term, and no field to carry one.** `quality_142l/metrics.py:451` records this as a known measurement gap. |
| per-room daylight / window exposure | **no ranking term.** Daylight exists only as a hard gate (C19/C8, `exposure_policy.REQUIRED_EXTERIOR_ROLES`). The single window-ish score is `living_has_window` → `+0.5` in `public_composition.py:398`, LIVING only, reached as a 4th-precedence tiebreak. |
| open plan vs closed plan | **no term.** `public_composition`'s own docstring (`:24-25`) forbids one; `public_zone_coherent` is measured and deliberately excluded from `composition_score`. #221 measured the consequence: 4 of 9 briefs showed a closed plan with an open one on the board. |
| garden / outdoor relationship | **one term, brain only** (`runner.py:208`). Nothing in production. |
| massing / footprint quality | **no term.** `massing_of` is used only for alternative enumeration and reporting; `primary_selection.py:23-25` explicitly forbids a bonus for any strategy or form. |
| spatial hierarchy | **no measured term** (§3). |
| privacy | **no term.** `wet_privacy.privacy_score`, `master_suite.better_candidate` and `furnishability.better_candidate` all exist with **no caller in any key**. |
| arrival-room usability | **no term at this head.** #207 built `arrival_usability` and its gate verdict was **STOP**; the identifier is absent from `backend/app` on this branch. |
| circulation as experience (light, width, destination) | **no term.** Only share and area. |
| room proportion, circulation share, area fidelity | **present** — these are the measurables, and they are what the keys are made of. |

That table is the answer to the ROOT's §3.5, stated structurally rather than anecdotally: every term
in every key is a **scalar read off a finished rectangle**. A key made only of such terms cannot
express a preference between two buildings; it can only express a preference between two packings.

---

## 6. Question 6 — site conditions

### 6.1 #223's finding, confirmed at this head, with the line

`rectilinear_realizer._build_site:1379-1389`, called from `realize_cells:1334` and
`realize_layout:1518`:

```python
plot = Rect(0, 0, footprint.x2 + m_to_u(2.0), footprint.y2 + m_to_u(2.0))
entrance_x = footprint.x + footprint.w // 2
crook = [r for r in footprint_module.remainder_within_bbox(wing_rects) if r.w > 0 and r.h > 0]
return SitePlan(plot=plot, footprint=footprint, footprint_offset_u=(0, 0), parking=(), ...)
```

A 2 m skirt, no parking, and a garden that is only the crook of a multi-wing footprint — empty for a
rectangle. `realize_layout`'s own docstring says `programme` *"is accepted but not read"* and
`buildable`, if given, is *"a sanity check … rather than a second source of truth"*.
`brain/proposer.programme_from_spec:172` never reads `spec.plot`, and `service.py:925` hands the
brain `(outline.width_m, outline.depth_m)` — a size, not a place.

### 6.2 What exists already, to give a concept stage the site

Everything needed is one module up and is thrown away by the type below it.

| already exists | file:line | what it would give the concept |
|---|---|---|
| `SiteGeometry` | `demo/site_geometry.py:61` | the parcel as entered, the **compass bearing** of the street edge, three setbacks, `plot_area_m2`, `buildable_width_m`/`buildable_depth_m`, `has_buildable_area` |
| `behind_parking_band` | `demo/site_geometry.py` (used `service.py:462`) | the depth actually available behind the parking band |
| `feasible_options`, `l_massings`, `one_storey_capacity_m2` | `:384,484`, `router.py:407` | the candidate massings and the plot's one-storey capacity |
| `Envelope` | `envelope.py:1-10,41` | an **orthogonal-polygon** buildable region; `Envelope.rectangle` is explicitly its *degenerate case* |
| `BuildableRegion` / `Ring` | `demo/service._buildable_from:217-243` | the real buildable region, including an L massing's ring |
| `footprint.subtract` / `remainder_within_bbox` | `footprint.py:57,84` | outdoor area as geometry, already computed — just never as programme |
| `OutdoorRegion` / `OutdoorClassification` | `geometry_core/model.py:351-360`, `Fixture.outdoor:431` | a typed slot for garden / terrace / balcony that **no builder has ever filled** |

So the answer to "what would the concept stage need to receive" is short: the `SiteGeometry` it
already has, un-rotated (keep `street_facing_side` as data, not as a frame transform), the
`Envelope` polygon instead of a `(w, d)` pair, and an `outdoor` programme the concept populates
before the footprint is chosen. None of that is new machinery. What is new is that the footprint
would then be an **output** of the concept rather than an input to it — and that is the ordering
change, not a type change.

---

## 7. Question 7 — reusable versus fundamentally limiting

### 7.1 Reusable, essentially unchanged

Each of these is reusable as it stands under any of the directions §10 considers.

1. **The whole post-placement geometry chain.** `footprint.py` (`tuple[Rect,...]`), `site.py`
   (`SitePlan.wings`), `geometry_adapter.envelope_sides:91`, `windows.py:110`, `doors.py:202`,
   `topology_preservation.py` (graph-level, zero footprint references),
   `design_output.py:114` and `demo/contract.py:719,748`.
2. **`rectilinear_realizer.realize_cells:1222`** — genuinely shape-free: *"any arrangement of
   non-overlapping cells whose union is the union of `wing_rects`"*, with the identical downstream
   and typed refusals naming the failing check.
3. **The validators as a fail-closed correctness system.** 32 checks, with none asserting
   architectural quality — which is correct, and is why a validator PASS must never be read as
   quality (`docs/reports/architecture-direction/README.md:229-246`).
4. **`ROOM_TEMPLATES`, `scale_program`, the elasticity/quality tier.** The strongest component:
   real size knowledge, elasticity, preferred aspect, hard maxima. The brain reuses production's own
   (`brain/proposer.py:204`) rather than a second opinion.
5. **`band_embedding` + `band_sizing` + the exact MILP oracles.** An *exact, complete* decision
   procedure with proof-carrying refusals. The right shape for a concept→geometry stage even if the
   band family itself is replaced.
6. **`proposal_critic`** — pre-geometry invariants, typed HARD/WARN findings, no repair.
7. **`Envelope`** — the orthogonal-polygon type, already written, currently fed a rectangle.
8. **`room_merge.py` + `_group_checks`** — the only working polygon-room mechanism, live in the
   product, with C1/C2/C3/C20/C27 already redesigned per group.
9. **`DemoPlan.tsx` + `ScaleBar`** — the owner-visible evidence surface; draws per-wing outlines and
   arbitrary room polygons today.
10. **The typed-refusal and disclosure culture** (`scope.py`, `capacity_notice_text`,
    `BandEmbeddingRefusal.proof_complete`). This is an asset, not plumbing.

### 7.2 Fundamentally limiting

1. **`HouseConcept` as the intent type** (`spec.py:318`) — six enums, one settable, read by nothing
   in the geometry stack. It cannot carry a site, an orientation, an outdoor room or a sequence.
2. **`TopologyProposal`** (`brain/proposer.py:92`) — a contact graph is not a composition, and the
   parti set is narrowed *by construction* to what `band_embedding` can carry.
3. **`Concept` + `Fixture` + `Cut.V|Cut.H`** — a slicing tree is guillotine by definition
   (0 of 19 real plans separable), and `Fixture` is the only thing that crosses `solve_fixture`.
4. **The ordering.** `_outlines_for:438` → `_plan_outlines_until_one_plans:549` commits the footprint
   from `PREFERRED_RATIOS` before a room exists; `resolve_entrance` decides the entrance after the
   geometry; `classify_garden` decides the garden after the footprint; `_build_site` invents the plot.
5. **`realize_layout`'s wing composition** (`:1407-1418`) — `cursor_x` with a fixed `origin[1]`: one
   histogram of wings, never a two-dimensional massing.
6. **One cell per zone in `realize_cells`** (`:1253-1264`) — no non-rectangular rooms on the
   shape-agnostic path; the blocking checks are C27 (`:159`), C9/C30 (`:518,202`), C14 (`:269,685`).
7. **The street as the bounding box's `y = min` line** (`doors.py:229,284,310`,
   `validation.py:573`) — a wing set back from that line can never hold the front door, which is
   why a hub hall cannot take the entrance.
8. **The subtree open-group rule** (`geometry_core/engine.py:97-114`) — branched and ring
   circulation cannot be expressed as one more strategy.
9. **Rank keys made only of scalars read off finished rectangles** (§5).
10. **The rectangle-only input contract** (`projects/models.py:273`, `demo/scope.py:362`,
    `site_geometry.py:20-23`) — and its dead `polygon` field, *"read by NOTHING downstream today"*.

### 7.3 The rectangle-only claim: verified, refuted and corrected

- **"Site input, placement-and-sizing-in-one-rectangle, and x-stacked wings are rectangle-only" —
  VERIFIED**, with the lines in §7.2 items 4–5 and §3. ADR-001 is the source and every line
  reference in its table resolves at this head, except the realizer's wing/composition lines, which
  have drifted ~160 lines down (now `:156-256` and `:1407-1418`).
- **"Validators, doors, windows, payload and renderer already take unions of rectangles" — PARTLY
  VERIFIED.** True for the geometry carriers (§7.1 item 1, with C2/C8/C13/C19/C22 verified
  wings-aware). **Not** true unqualified: four rectangle *formulas* remain (C27, C9, C30, C14) and
  the street line is bounding-box-bound.
- **#213's "19 payloads, 2 to 12 wings" — NOT REPRODUCIBLE in this worktree.** The sentence exists
  verbatim in the git object store on branch `investigate/preview-comparison`
  (`git show 8ebe01c:docs/reports/architectural-brain/COMPARISON-preview-corpus.md`), but neither
  the report, the figures, the payload directory nor the harness modules it names exist at this
  head; `find . -iname "*213*"` returns nothing and the string "19 payloads" appears nowhere in the
  tree. The strongest on-disk evidence is weaker: `docs/reports/two-path-demo/results.md:102` records
  *one* plan with a genuinely non-rectangular 2-wing envelope, and all 11 committed payloads there
  carry a single-entry `footprints` array. **The mechanism is independently corroborated by code**
  (§3, §7.1) **and the input-contract half of the claim is verified by type** — so the conclusion
  #213 drew stands, but on code evidence, not on that count.
- **One correction to the framing.** "The product produces no polygon plans" is too strong: the
  engine's own outline menu ships a fixed-arm 2-wing L (`site_geometry.l_massings:484` →
  `l_parti.py:702` → `OutlineOut.shape="L"` → two `footprints` → `DemoPlan.tsx:117`). What is
  rectangle-only is the **user-supplied** footprint and the **parcel**.

**So: non-rectangular *homes* are a plumbing problem. Non-rectangular *rooms* are a representation
problem. Those are different problems and §11 measures which one actually binds.**

---

## 8. One update to a prior report, at this head

`docs/reports/architecture-direction/README.md:247-258` lists **H2** as an explicit unproven
hypothesis: *"`rectilinear_realizer` can carry a real brief end to end. It is gate-passed on its own
constructions and on hand-encoded layouts; **no brief has ever been realized through it**."* Its
asset table (`:367`) records *"on `main`, gate-passed, **zero callers**"*, and
`docs/PROJECT_STATE.md`'s wiring table says the same.

**That is stale at `5b155d1`.** `brain/exact_pipeline.py:38` imports `realize_cells` and every
brain-preview plan is realized through it (`service.py:925` → `run_brain(sizer="exact")`), reachable
from the product by `?engine=brain`. `RECTILINEAR_REALIZER_ENABLED = False` (`:101`) gates nothing:
it is read by no code outside tests and one spike's force-on context manager, while the *unflagged*
`realize_cells` carries real briefs. **H2 is falsified: the non-guillotine realizer does carry real
briefs, on real envelopes, through the unchanged validators.**

This matters for the decision, because it moves the binding constraint. P1 (the guillotine) is no
longer what bounds the brain path. What bounds it now is, in the spike's own words,
*"layout generation vs room bounds"* — and Gate 3's verdict is the honest statement of where that
leaves quality: *"valid, graph-preserving, rendered plans on rectangles, strips and courts … It is
**not** a customer-credible planner yet: area 66–83 %, circulation 8–23 %, bedrooms at minimum"*
(`GATE-3-verdict.md:66-73`). The flag table in `docs/PROJECT_STATE.md` should be corrected by
whoever next edits it; this report changes no code.

---

## 9. The four findings ROOT #237 already measured, consolidated

Not re-derived. Cited, with the mechanism confirmed in code at this head.

| ROOT §    | finding | mechanism at `5b155d1` |
|---|---|---|
| §3.6, #223 | the site does not reach the concept; the site was drawn around the finished building in 25 of 25 brain plans | `rectilinear_realizer._build_site:1379-1389` (§6.1); `programme_from_spec:172` never reads `spec.plot`; `service.py:925` passes `(width, depth)` |
| §3.5, #207/#221 | the ranking cannot see architecture the system already produces — arrival-room usability absent, the open plan absent, 4 of 9 briefs showed a closed plan with an open one on the board | `arrival_usability` is absent from `backend/app` at this head (#207's gate verdict was STOP); `public_composition.py:24-25` forbids an open-plan term by design; full term lists in §5 |
| §3.3 | four gates stopped while extending the grid: wing stacks, cross-band cells (#200), the screen-aware generator (#208), hub v2.1 | `docs/reports/shape-agnostic-realizer/WING-DAY-2-gate.md`, `CELLS-DAY-2-gate.md`, `GATE-3-verdict.md`; hub reach 0 of 60 briefs (`CONCEPT_ENGINE_V2_INVESTIGATION.md:97`) |
| §3.3 | the band grid tiles exactly, so circulation is the elastic filler — a hall with no exterior wall in 19 of 25 plans, up to 29.6 m² | `brain/proposer.py:56-73` documents it as an allocation defect and records that capping the hall took B16 from three plans to one; `ENTRY:47-55` exists because a hub hall cannot reach the street band |

One more prior result belongs here because it is the strongest evidence *against* a representation
diagnosis, and it was tested. `docs/reports/product-readiness-audit/README.md:7-18` concluded:
*"The plans themselves are architecturally competent … What breaks the professional impression is not
geometry and not missing architectural semantics. It is **communication**."* That hypothesis was then
acted on and verified — 280 text collisions to 0, 438 English tokens to 0, the capacity mismatch
disclosed (`b4c0bef`, #180). The owner inspected the gallery **after** that and said the plans still
look algorithmically assembled. The communication hypothesis is therefore not available as an
explanation any more; it was the cheapest candidate and it has been spent.

---

## 10. The architecture decision

**Can this architecture evolve to meet the product vision, or does it need redesign? Both, in
different halves — and the halves must not be confused.**

The geometry half — `realize_cells`, the 32 validators, the room templates and elasticity layer, the
exact embedding and sizing with proof-carrying refusals, the per-wing footprint/exposure/window/door
chain, the payload and the renderer — **does not need redesign and should be preserved almost
unchanged.** It is exact, deterministic, honest about what it cannot do, and already more capable
than the product lets it be: it carries non-rectangular outlines, it realizes real briefs through a
non-guillotine path today, and the one thing standing between it and an orthogonal-polygon envelope
is a single call that hands it a rectangle.

The concept half — `HouseConcept`, `Concept`/`Fixture`, `TopologyProposal`, and the order in which
massing, entrance and outdoor space are decided — **needs redesign, not extension.** Not because it
is badly built; it is carefully built. Because its vocabulary cannot *name* the things the owner is
asking for, and because the pipeline decides them in the wrong order. A type with six enum fields
that the geometry stack does not read cannot hold an architectural concept. A footprint chosen from
four fixed aspect ratios by area arithmetic before any room exists cannot be a design decision. An
entrance discovered after the geometry is a consequence of row ordering. A garden that is the plot's
leftover cannot be a room. A compass bearing thrown away at the first stage boundary cannot orient
anything. Each of those is a **sequencing and vocabulary** fact, and none of them is reachable by
another topology compiler, more scoring weights, another MILP constraint or a stronger model — which
is why the four gates that tried to reach them from inside the grid all stopped, and why E1, which
proved the mechanism works, still produced *"a reversed room-packing pattern"*.

Concretely, the shape of the redesign is: a typed design intent that includes the parcel and its
compass, outdoor space as programme with area, the entrance as a sequence, and the massing as an
**output**; the existing exact machinery underneath it, unchanged, realizing it; selection over a
profile rather than a scalar. That is close to what `docs/reports/architecture-direction/README.md:345`
already drew, and this report's contribution is to say which half is which and to name what has
changed since: the guillotine is no longer the binding constraint, so the concept-first direction can
now be tried on a realizer that does not fight it.

**The strongest evidence for this decision.** Every seam where intent dies is a *type* or an *order*,
not a search: the compass dropped in `site_geometry.derive`; `HouseConcept` read by nothing
(`spec.py:260-263`); `Fixture.outdoor` never once assigned (`grep "outdoor=" → 0 hits`);
`solve_fixture(candidate.concept.fixture)` taking one argument; the footprint fixed at
`service.py:438` before `generate_concepts` is called; the plot invented at
`rectilinear_realizer.py:1379`. And the counter-experiments have been run: four grid-extension gates
stopped, E1 reached 1 of 8 and its own author called the result a reversed packing, and the
communication hypothesis was fixed and did not resolve the complaint.

**The strongest evidence against it.** Nobody has shown that inverting the order produces better
plans. Gate 3 removed the shape constraint and the plans came out *"valid, not credible"* — area
66–83 %, circulation 8–23 %, bedrooms at minimum. E1 propagated a real concept dimension correctly
through sizing, realization and validation, and the circulation came out bit-for-bit identical. And
one prior audit, measured on real plans, concluded the plans were *architecturally competent* and the
defect was communication. It is entirely possible that the binding constraint is neither the
representation nor the ordering but the **objective** — that these plans are what you get when the
only thing anything optimises is area, and that a concept layer on top of an area objective will
produce correctly-oriented packings forever. I cannot rule that out from code, and §11 does not test
it. It is the second experiment, not the first.

**What I am not claiming.** That a concept-first pipeline is proven better (it is not). That
courtyards are realizable (unverified). That the representation can carry professional plans (never
measured — which is exactly why §11 measures it before anything is built).

---

## 11. The one next experiment — R1, the representation ceiling

**Why this one and not a concept experiment.** Every path forward in §10 assumes the geometry half is
good enough to be worth building on. That assumption has never been tested against real
architecture. It is the single claim whose failure would invalidate the whole plan, it can be tested
with data already committed to this repo, and it needs no solver, no model, no dependency and no
production code. A concept experiment run before it risks building a concept layer on a
representation that cannot draw the result.

### 11.1 The experiment

**Hypothesis (exactly one).** The existing shape-agnostic representation — `realize_cells` plus the
**unchanged** validators — can carry real professional residential plans.

**Data, already on disk.** `backend/tests/spikes/fixtures/geometry_shapes/plans/` — 20 committed
JSON plans, 19 real ResPlan plans and 1 hand-built synthetic (CC BY 4.0, `ATTRIBUTION.md` beside
them). **The synthetic `synthetic-spine-01.json` is excluded and named**; n = 19. Each plan carries
room polygons, areas, a footprint, adjacency and access edges.

**Procedure.** A new directory under `backend/app/ai_harness/` (no production file touched):
decompose each room polygon into axis-aligned rectangles; map each room's `type` to a `ProgramRole`
through a table **committed before the run**; build `ZoneIntent`s from each room's own measured area
with permissive bounds; call `realize_cells(name, rects, intents, wing_rects, access_pairs, wet_rooms)`
and record the outcome. Two arms, both run, both reported:

- **Arm 1 — as-is.** Every room must be one rectangle. A room that is not is recorded as
  NOT EXPRESSIBLE, naming the room and its vertex count.
- **Arm 2 — the one-change probe.** Rooms decomposed into same-zone cells with `OPEN` walls between
  them and validated on their union by the existing `_group_checks` — a harness-side composition of
  two mechanisms the realizer already has (`room_merge` and `ShapeGroupIntent`), not new product
  behaviour.

**Measured, per plan, per arm.** Carried (a `RealizedLayout`, which at `:1363` means every validator
passed) or refused; the refusal's constraint and the failing check ids; cells needed per room.
Reported as a check-id histogram over the 19 plans.

**Pre-registered expectation** (so the result cannot be re-interpreted after the fact): Arm 1 fails
on most plans — 41.9 % of real rooms are rectangles. Arm 2's likely blockers are the checks that have
**no group form**: C9 (inscribed-rectangle furniture), C24 (bedroom access) and C31, since
`_group_checks` generalizes only C1/C2/C3/C20/C27. If that is what the histogram shows, the result is
a named, ordered work list rather than a verdict.

### 11.2 GO and STOP, fixed before the run

| outcome | criterion | what it authorizes |
|---|---|---|
| **GO** | Arm 2 carries **≥ 13 of 19**, and Arm 2 − Arm 1 **≥ 6** plans | the representation can evolve. The one named change (N-cell room groups on the shape-agnostic path) becomes the next build, and the concept-layer inversion of §10 is authorized on top of it. |
| **PIVOT** | Arm 2 carries **7–12 of 19** | neither conclusion may be claimed. The histogram's top blocking check is the next single piece of work, scoped on its own evidence. No concept-layer work starts. |
| **STOP** | Arm 2 carries **≤ 6 of 19**, or ≥ 3 of {C27, C9, C14, C30} fail on more than half the plans | the representation itself is the blocker. No further concept-layer work is authorized until a room/validator geometry model (polygon-aware C27/C9/C14) is designed. §10's decision is revised: the redesign is in the lower half too. |

Additional hard conditions, any one of which voids the run: a validator was modified; a production
file was modified; a dependency was added; the role-mapping table was changed after the first plan
was scored.

**Reversible.** One new directory under `backend/app/ai_harness/`; no production file, no flag, no
default, no dependency (`shapely` and `scipy` are already declared in `backend/pyproject.toml:19,23`
and `scipy` is not needed — `realize_cells` takes geometry as given and solves nothing). Deleting the
directory restores the tree exactly.

**Cost and timing.** No solver, no MILP, no LLM, no network, no spend. `realize_cells` types walls,
places doors/windows/furniture and validates — milliseconds per plan. **It must still run after
#226's quiet measurement window closes**, because no claim in this report is worth perturbing
someone else's wall-clock numbers.

**Why it is not one of the four things the owner ruled out.** It is not a topology compiler (it
generates no layouts — it reads them from real plans). It is not a scoring weight (it ranks nothing).
It is not a MILP constraint (it solves nothing). It is not a stronger model (no model is called).

---

## 12. Unverified — and what would settle each

| # | unverified claim | what would settle it |
|---|---|---|
| 1 | **A courtyard is representable.** A hole in the wing union would be classified as garden by `remainder_within_bbox` and its walls as exterior by `envelope_sides` — reasoned in `ADR-001:50-54`, never tested. | one hand-encoded 4-wing ring through `realize_cells` + `validate()`, reading the C19/C8/C22 outcome. Cheap; deliberately not run here (read-only Issue). |
| 2 | **#213's "19 payloads, 2–12 wings"** is not reproducible at this head (§7.3). | re-running #213's harness from `investigate/preview-comparison`, or re-deriving the count. The conclusion it supports is independently established by code, so this is provenance, not substance. |
| 3 | **Whether the representation can carry real professional plans** — never measured. | exactly §11. |
| 4 | **Whether the ordering inversion improves plans** — E1 proved propagation, not quality; Gate 3 proved shape freedom, not credibility. | a concept-first experiment, after §11, with a quality rubric from #240 rather than a validator PASS. |
| 5 | **Whether the objective, not the representation, is the binding constraint** (§10, evidence against). | hold the representation fixed and change only what is optimised, measured against #240's rubric. Explicitly the *second* experiment. |
| 6 | **The hub gate arithmetic** (`concept_generator.py:3563+`, `hub_guard.py`) was read only at call-site level. | reading the gate; it bears on why hub reach is 0 of 60, not on this report's verdicts. |
| 7 | **Diversity figures** (0/60 hub, 7/60 L, 25.7 % ≥2 classes, median hall aspect 9.07) are quoted from `docs/CONCEPT_ENGINE_V2_INVESTIGATION.md:94-112`, measured at an older commit; **not re-measured** (no solver run). | a re-measurement after #226's window. |
| 8 | **Whether `select_primary` is reached by any non-Python caller.** Verified: no Python caller outside tests and comments. The API layer was not grepped. | a frontend/API grep. |
| 9 | **`l_parti.py`'s tree shape** beyond `circulation_class = TWO_WING` (`:735`) was not read. | reading it; bears on how much the shipped L actually differs. |

---

## 13. Method, and what no claim here rests on

Read-only throughout. No product code, test, fixture, flag or document outside this file was changed.
No solver, benchmark, corpus suite or heavy test was run — #226's measurement window was open and its
numbers are wall-clock sensitive. The only command executed was
`OPENAI_API_KEY=not-a-real-key-ci-only python -c "import app.main"` → `import ok`
(AC-1's static check). Every file:line was read in this worktree at `5b155d1`; prior reports are cited
by path and line and were not taken on trust where the code could be read instead. Where a prior
report and the code disagreed, the code won and the disagreement is written down (§8, §7.3).
