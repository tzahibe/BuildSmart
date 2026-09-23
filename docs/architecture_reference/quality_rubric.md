# Architectural Quality Rubric (A–O)

Status: reference document, not a Wiki page — see `docs/wiki/architecture/knowledge-system.md` for
how this file relates to the authority hierarchy. This is the canonical list every later
geometry/circulation/interior Issue and every reviewer points at when judging "is this plan
architecturally good", not just "does it pass hard validation".

Hard validation (`app/vertical_slice/validation.py`'s C-checks, `building_validation.py`'s
V-checks) answers "is this plan structurally legal": no overlap, no dead space, declared access
realized, dimensions within template maxima. Every section below is about the layer above that —
whether a structurally legal plan reads as a *good* plan. Signals are measured on **realized
geometry** (the delivered `DemoDesign`/`GeometricDesign`), never on the planner's intent, exactly
the way M1–M6 (`app/vertical_slice/quality_metrics.py`) already work — a plan that says it will
build 12 m² and builds 9 m² is judged on the 9 m².

For each section: the principle, the **deterministic signal** that exists today (a check id or
metric) or is planned (an Issue reference), what a **reference comparison** against real
professional plans adds beyond a synthetic threshold, what only **semantic review** (a person, or
an LLM reviewer prompt) can judge, and a one-line "how a reviewer applies it."

## Reference benchmark (Issue #32)

`app.vertical_slice.reference_benchmark.benchmark(design, references) -> BenchmarkReport`
(`backend/scripts/reference_benchmark.py --context <id>` prints it) produces one machine-generated
`SectionFinding` per rubric section for a realized plan, six of them with a real deterministic
value today, compared against the curated reference-plan index
(`docs/architecture_reference/references/index.json`) filtered to entries of the same
`footprint_family` — metadata and ratios derived from that index only, never a reference plan's own
geometry (the V1 set carries none on disk; every entry is `rights: "metadata-only"`).

The benchmark's own six section codes are lettered exactly as Issue #32's contract named them —
A, B, C, H, K, L — which does **not** line up with this rubric's own A–O lettering for the same or
adjacent topics (this rubric's A is Room Proportion, not Entrance; its H is Entrance, not Exposure;
and so on). Content mapping, this rubric's section -> the benchmark's own letter:

| This rubric's section | Benchmark's own letter | What the benchmark measures |
|---|---|---|
| H. Entrance & Arrival Sequence | **A** | does the entrance open into a public/circulation room |
| D. Circulation Efficiency & Compactness | **B** | dedicated circulation m², its share of the plan, corridor length. Its `reference_range` is the matching-family entries' own `total_area_sqm` (min, max) — genuinely computed from `index.json`, since the index carries no circulation field itself; the "high relative dedicated circulation" wording instead compares the plan's own circulation SHARE against a fixed 8-14% engineering floor (the documented census band), disclosed as fixed rather than claimed to vary by family. |
| J. Adjacency & Privacy Zoning | **C** | is each of PUBLIC/PRIVATE/SERVICE a spatially contiguous group |
| C. Exterior Exposure & Daylight | **H** | share of daylight-required rooms with a window (C8 data) |
| K. Dead Space & Structural Validity | **K** (same letter, same topic) | residual interior area (C2; always 0 — a floor, not a band) |
| — (no existing rubric section; a new data-integrity fact) | **L** | how far a room's declared area sits from its own width×depth |

Every other rubric section (A, B, E, F, G, I, L, M, N, O in this document's own lettering) has no
signal wired into the benchmark yet and comes back `not_measured` from `benchmark()`.

## A. Room Proportion & Aspect Ratio

A habitable room should read as a room, not a corridor with a bed in it — its long/short ratio
should sit near what a person would draw by hand for that room type, not merely under the legal
ceiling. The hard ceiling (`max_aspect_ratio`) prevents the worst case; it says nothing about
whether a 2.4-aspect bedroom that legally passes is actually a pleasant room.

- **Deterministic signal**: M1 (habitable-room aspect, median/worst by room type,
  `quality_metrics.py`); hard gate C20/C21 (template aspect/area maxima, `validation.py`); the
  room-proportion quality tier's `preferred_aspect_ratio` soft target (commit `be8c0ca`, see
  `docs/wiki/features/room-proportion-quality-tier.md`).
- **Reference comparison**: the 21-plan professional census (`specs/005-hub-private-wing/spec.md`
  §1) gives the target band the hard ceiling doesn't — e.g. bedrooms cluster near 1.2–1.5, not the
  2.5 legal maximum.
- **Semantic review**: whether a specific room's proportion, in context (its furniture layout, its
  role), reads as awkward even inside the numeric band — a 1.4-aspect room with a door and window
  on the same short wall can still feel wrong in a way M1 alone won't catch.
- **How a reviewer applies it**: check M1's worst-case value against the reference band first;
  only escalate to visual/semantic judgment when a room sits inside the band but still looks off in
  the drawing.

## B. Area Fidelity

When a person asks for a room of a given size, the realized room should honor that request within a
disclosed tolerance — silent shrinkage to fit the plan is a defect, not a feature, even if the
final drawing is otherwise legal.

- **Deterministic signal**: none merged yet. `dead_space_m2` (always 0 by C2) and the built-vs-
  requested area comparison exist only as manual review today; planned as the ROADMAP P0 item
  "Exact Area / Room Area Fidelity" (no Issue number assigned yet — see `docs/ROADMAP.md`).
- **Reference comparison**: professional plans rarely deliver a room more than ~10–15% off a
  stated target without calling it out; that gap is the working tolerance band once a check exists.
- **Semantic review**: whether an area shortfall was disclosed to the user in a way they'd actually
  notice (a review-page warning vs. a number buried in a table), and whether the shortfall changes
  how the room can be furnished/used, not just its raw m².
- **How a reviewer applies it**: until the deterministic check lands, manually diff each named
  room's target area (from the parsed brief) against its realized area and flag any silent
  reduction beyond ~10%.

## C. Exterior Exposure & Daylight

A habitable room needs a real relationship to the outside — an exterior wall at minimum, a window
where the room's use requires one. Exposure without a window is not the same guarantee as exposure
with one; today's metric only measures the former.

- **Deterministic signal**: M2 (share of habitable rooms touching the exterior envelope,
  `quality_metrics.py`) — already near 100% and measured as NOT a gap (see
  `docs/wiki/architecture/geometry-validation.md`). Window presence/placement itself has no
  deterministic check yet; planned as ROADMAP P0 "Windows + Exterior Exposure" (no Issue number
  assigned yet).
- **Reference comparison**: the 21-plan census confirms near-universal exterior contact for
  habitable rooms; it does not yet carry window-count/size data to compare against.
- **Semantic review**: whether a window's size and placement actually deliver usable daylight and
  ventilation for the room's function (a bedroom's one window in a corner vs. centered on its long
  wall), which no envelope-contact metric captures.
- **How a reviewer applies it**: confirm M2 first (rooms touch the envelope); until the window
  check exists, manually confirm every bedroom/living/kitchen has at least one exterior-wall
  opening drawn, not just an exterior-adjacent wall.

## D. Circulation Efficiency & Compactness

Circulation (hall/corridor) area should be small relative to the whole plan, and the hall itself
should read as a compact space rather than a long spine — both are measurable on the realized
drawing.

- **Deterministic signal**: M3 (circulation share of total area) and M4 (hall long/short aspect,
  `COMPACT_HALL_ASPECT_MAX = 1.5`, `quality_metrics.py`); `wasted_circulation_share`
  (`app.demo.contract.QualityOut.metrics`) for the portion of circulation past the compact
  threshold. **Issue #36** (`circulation_metrics.py`) adds, from realized geometry: dedicated
  circulation area/ratio, per-segment length (`longest_segment_m`, `total_length_m`,
  `narrowest_width_m`), and — with topology, section E — dead-end/turn/duplication counts, all
  carried as `QualityOut.metrics.circulation_*`. **C26 "no extreme dedicated circulation"**
  (`validation.py`) fails closed only when ratio, longest segment or dead-end count exceed the
  calibrated `EXTREME_*` constants (`circulation_metrics.py`) — an ordinary long corridor still
  passes; only a genuinely disproportionate one fails.
- **Reference comparison**: M3's median (~11%) is already at the 21-plan reference band (8–14%) —
  NOT a gap (`architectural-quality-gaps-measured` memory, `docs/wiki/architecture/geometry-
  validation.md`). M4 is the real gap: hall long/short median 9.4 vs. ~18/21 reference plans having
  a compact hub (~2.5–3.5 m square, 0% compact today). The `EXTREME_*` thresholds are calibrated so
  today's plans pass with headroom (worst measured: ratio 0.18, longest segment 17.3 m on an 8 x
  28 m footprint — deeper than the frozen corpus's own deepest footprint, 24 m) — they catch a
  future regression, not today's median.
- **Semantic review**: whether a corridor that measures compact on M4 also *functions* as a hub
  (do the rooms it serves actually cluster around it, or does a short-but-isolated hall still read
  as a dead appendage).
- **How a reviewer applies it**: M3 alone rarely flags a real plan; M4 near or above ~2 is the
  actionable signal — check whether the hall reads as a spine on the drawing before accepting it.
  A C26 failure names which of ratio/longest-segment/dead-ends it is — check that reason against
  the drawing, not just the number.

## E. Circulation Topology & Access Sequence

Beyond raw compactness, circulation should form a sensible topology: a small number of junctions
that rooms genuinely branch from, an entrance sequence that leads somewhere, and no chain of rooms
serving as the only route between unrelated parts of the house.

- **Deterministic signal**: C5 (reachability from the entrance, `validation.py`) covers the legal
  minimum (every room is reachable at all). **Issue #36** (P2 "Hallways / Circulation Quality",
  `circulation_metrics.py`) adds dead-end count (a circulation-room end with neither a placeable
  door nor an open-plan join), turn count (direction changes along the realized entrance →
  farthest-room BFS path) and duplicated-segment count (circulation rooms not directly joined but
  serving an overlapping set of rooms) — all reported on `QualityOut.metrics`, and dead-end count
  additionally gates C26 (section D). Chained-access (a room reachable only by passing through an
  unrelated one) and the entrance sequence itself remain uncovered — ROADMAP P0 "Entrance-to-
  Circulation Integration" (Issue #22, depends on #20).
- **Reference comparison**: the same 21-plan census that grounds M4 shows the hub-parti topology
  professional plans converge on; spec 005 (hub-private-wing) attempted to reproduce it and was
  rejected on two hard acceptance gates (`specs/005-hub-private-wing/RESULTS.md`) — the gap is
  real and the naive structural fix did not close it.
- **Semantic review**: whether the *sequence* of spaces a person actually walks through (front
  door → hall → living → private wing) makes narrative sense, which no single junction-count
  metric captures.
- **How a reviewer applies it**: trace the path from the entrance to each room by hand; flag any
  room reachable only by passing through an unrelated room, and any hall segment that terminates at
  a blank wall with nothing behind it.

## F. Wet-Room Adjacency & Plumbing Efficiency

Bathrooms, toilets, kitchens and the laundry should cluster near each other where possible — shared
walls mean shorter plumbing runs and is what professional plans consistently do; isolated wet rooms
are a measured, real gap.

- **Deterministic signal**: M5 (share of wet rooms sharing an interior wall with another wet room,
  the kitchen, or the laundry, `quality_metrics.py`); C17 (bathroom access matches requirements,
  `validation.py`) covers legal access only, not adjacency quality.
- **Reference comparison**: 40% wet-adjacency on the current corpus vs. ~85–90% on the 21-plan
  reference set (`docs/wiki/architecture/geometry-validation.md`) — the single largest measured
  quality gap after circulation topology. The wet-room quality-tier extension (commit `f2092af`)
  improves proportion but was not designed to close this adjacency gap.
- **Semantic review**: whether an adjacency that passes M5 is also a *sensible* one (a bathroom
  backing onto the kitchen's sink wall reads differently than backing onto its stove wall, though
  both count as "shares a wall with the kitchen").
- **How a reviewer applies it**: for every wet room, check whether at least one interior wall is
  shared with another wet room/kitchen/laundry; treat isolated wet rooms as a quality flag even
  when every hard check passes.

## G. Public-Zone Contiguity & Open-Plan Coherence

Living, dining and kitchen should read as one connected, open volume when the brief calls for open
plan — not as three separate rooms that happen to be adjacent, and not as elongated strips that
merely satisfy an area target.

- **Deterministic signal**: M6 (whether the public zone is one contiguous group,
  `quality_metrics.py`); no shape-quality check on individual public rooms yet beyond M1's generic
  aspect measurement.
- **Reference comparison**: professional kitchens realize as an L-counter inside one open volume,
  not a room with its own rectangular shape; measured gap: KITCHEN median aspect 2.75, DINING 2.35
  on the current corpus (`docs/wiki/architecture/geometry-validation.md`) — both read as strips.
  This is a PROPOSED follow-up (extend the room-proportion quality tier to the public band), not
  designed or measured yet.
- **Semantic review**: whether an open-plan group that passes M6 (topologically contiguous) also
  *feels* like one room in the drawing — a contiguous but visually segmented L-shaped party wall
  can pass M6 while still reading as three rooms.
- **How a reviewer applies it**: confirm M6 first (public zone is one group); then eyeball whether
  KITCHEN/DINING individually read as strips (aspect noticeably above ~2.0) even when the group as
  a whole is contiguous.

## H. Entrance & Arrival Sequence

The front door should open onto a real arrival space (a foyer, hall, or the public zone's entrance
corner) that leads clearly into the house's circulation — not directly into a bedroom, not against
a blank wall, and not into a room that has no other function than being walked through.

- **Deterministic signal**: `is_entrance` on doors (`app.demo.contract`) and C5 (reachability)
  cover only "a door exists and the house is reachable from it." No deterministic entrance-quality
  or dead-wall check exists yet. Planned: ROADMAP P0 "Entrance / Exterior Door" and "Entrance-to-
  Circulation Integration" (Issue #22).
- **Reference comparison**: the guest-WC spec's `EntranceZone` vocabulary
  (`specs/009-guest-wc-placement/spec.md`) already names "the zone the front door opens into" as a
  first-class concept for a different purpose (guest-WC placement); the same zone is the natural
  unit for measuring arrival-sequence quality once a check is built.
- **Semantic review**: whether the first impression on entry — what a person sees and where they
  can go — communicates the house's organization, which is inherently a walk-through judgment, not
  a single geometric measurement.
- **How a reviewer applies it**: stand (on the drawing) at the front door and ask what's directly
  ahead; a blank wall, a bedroom door, or a service room in the sightline is a flag even if C5
  passes.

## I. Doors & Access Topology

Every room needs the *right kind* of access, not just *some* access: no bedroom should be the sole
route to another bedroom, service rooms should have their own doors rather than borrowing a
bedroom's, and every door's swing and position should make physical sense in the room it opens
into.

- **Deterministic signal**: C13 (declared access topology is physically realized) and C17
  (bathroom access matches requirements) cover declared-vs-realized correctness; no check exists
  yet specifically for the bedroom-to-bedroom anti-pattern or general door-topology quality.
  Planned: ROADMAP P0 "Doors + Access Topology" (no Issue number assigned yet). **Wet-room privacy
  and access quality (Issue #37, `wet_privacy.py`)**: per wet room, a `WetPrivacy` record —
  entered-from zone class (private/circulation/public), door facing, a real segment test for a
  direct sight line from a facing public room, `public_exposure_score`, `circulation_obstruction`
  (door leaf vs. corridor width) and `adjacency_quality` (F's own relation, read per-room). C29
  fails closed only on a wet room entered directly from KITCHEN or DINING; a corridor-access wet
  room, however its facing geometry scores, is never refused — that score joins ranking
  (`candidate_privacy_key`) as a soft signal instead, on `QualityOut.wet_privacy`.
- **Reference comparison**: none of the 21 reference plans route through a bedroom to reach another
  room; this is a hard convention in professional practice, not merely a preference.
- **Semantic review**: whether a door's swing direction and hardware side make sense for the room
  (does it block a fixture or a wardrobe when open) — see also anti-pattern "door-fixture clash" in
  `anti_patterns.md`.
- **How a reviewer applies it**: for every private room, list what other rooms are reachable only
  by passing through it; any non-empty list for a bedroom is a flag. For every wet room, read its
  `WetPrivacy` record before judging the drawing by eye: a high `public_exposure_score` on a
  corridor-access room (never refused by C29) is exactly the case worth a second look.

## J. Adjacency & Privacy Zoning

Public rooms (living/dining/kitchen), private rooms (bedrooms) and service rooms (wet rooms,
laundry, storage) should each cluster into a coherent zone, with the transition between zones
happening at a clear boundary (a hall, a hub) rather than interleaved room by room.

- **Deterministic signal**: `ZoneGroup` (`PUBLIC`/`SERVICE`/private, `concept_generator.py`)
  already exists as a planner-side concept; no deterministic realized-geometry check measures
  whether the *delivered* zoning stayed coherent (as opposed to what the planner intended). **Wet-
  core / plumbing efficiency (Issue #44, `wet_core.py`)** covers the SERVICE half of this section
  for wet rooms specifically: `shared_wall_length_m` (total interior wall shared between two wet
  rooms), `clusters`/`cluster_count` (every group of wet rooms connected wall-to-wall through other
  wet rooms — a coherent SERVICE sub-zone reads as one cluster, a scattered one as several),
  `kitchen_adjacent_count` (wet rooms sharing a wall with the kitchen, this section's PUBLIC/
  SERVICE boundary case) and `plumbing_complexity_index` (an estimate of independent plumbing
  stacks/runs — connected components over wet rooms *and* the kitchen; lower is better). A soft
  ranking preference only (`candidate_wet_core_key`/`better_candidate`), never a gate — no plan is
  refused for a low cluster count. `wet_core_alignment` extends the same idea across levels: how
  many of an upper level's wet rooms sit directly over a wet room below (a real vertical-stack
  check on the REALIZED footprints of two levels), read-only data, not wired into any single-level
  pipeline call. On `QualityOut.metrics.wet_core` (`app.demo.contract`).
- **Reference comparison**: the guest-WC spec's `PublicAccess` vocabulary
  (`specs/009-guest-wc-placement/spec.md`) already encodes an ordered zone-access preference
  (foyer/hall → public circulation → living room, never through a bedroom or kitchen) for one
  specific room kind; the same ordering generalizes to judging any room's zone placement.
- **Semantic review**: whether a room that is topologically in the "right" zone also reads that way
  visually — e.g. a bedroom placed adjacent to the public zone with no buffering hall between them.
- **How a reviewer applies it**: partition the realized rooms into public/private/service by eye
  and check the partition is spatially contiguous, not interleaved; flag any private room directly
  adjacent to a public room with no hall/buffer between them.

## K. Dead Space & Structural Validity

Every square meter inside the footprint must belong to a named room or a declared circulation
space — no unassigned residual area, and no room nested inside another room with no independent
access of its own.

- **Deterministic signal**: C1 (no overlap) and C2 (no residual interior area, `validation.py`) —
  both hard gates, already enforced on every delivered plan (`dead_space_m2` always 0.0).
- **Reference comparison**: not applicable — this is a correctness floor every professional and
  generated plan must clear identically; there is no "better" beyond zero.
- **Semantic review**: whether a room that legally has its own footprint and one door still
  functions as an independent room (see anti-pattern "room-in-a-room" in `anti_patterns.md`) — a
  case C1/C2 alone cannot distinguish from a genuinely separate room.
- **How a reviewer applies it**: trust C1/C2 as already-enforced; the only manual check needed is
  whether a room's sole access reads as incidental (through another room's corner) rather than a
  real doorway.

## L. Massing & Footprint Shape Quality

The overall building footprint (rectangle, L, or other massing) should be chosen because it
produces a *better realized plan*, not merely because a more complex shape was available — an L
massing that produces a worse plan than the rectangle alternative should not win a representation
slot by default.

- **Deterministic signal**: the L-massing realized-quality eligibility gate (`l_massing_guard.py`,
  commit `9ae6893`) — `worst_wet_aspect` and `two_sided_share` (`ExposureProportions`) gate whether
  an engine-generated L earns its slot over the next-best rectangle.
- **Reference comparison**: the gate is corpus-measured (14/16 previously-unconditional L slots
  lost their slot after the gate landed, 0 primary changes — `docs/wiki/features/l-massing.md`);
  there is no external professional-plan reference specifically for massing-choice frequency yet.
- **Semantic review**: the entrance-sequence quality of an L massing is explicitly untouched by the
  quality gate (a deliberate, deferred scope decision, `docs/wiki/features/l-massing.md`) — judging
  whether an L's entrance still makes sense remains a semantic-review task, not a gated one.
- **How a reviewer applies it**: when an L massing is offered, confirm it earned its slot on the
  guard's own terms (not merely "L is more interesting"); separately eyeball its entrance sequence
  since the gate does not check it.

## M. Multi-Level Vertical Coherence

On a multi-level building, the two (or more) floors must share a real, structurally coherent
vertical core — a stair/core position that lands in a sensible place on both levels, not two
independently-planned floors stacked without regard for each other.

- **Deterministic signal**: building-level V-checks (`building_validation.py`, V1–V5/V7/V8) and
  the shared, pinned `VerticalCore` (`app/vertical_slice/building.py`) enforce structural coupling
  today; Multi-Level Phase 1 is IMPLEMENTED_MERGED at the module level but not wired into the live
  product path (`docs/wiki/features/multi-level.md`).
- **Reference comparison**: the stair-seat investigation found only one seat topology that works on
  both levels across the measured briefs (27/36 hand-built, 0/76 independently generated —
  `multi-level-phase1-core-band-seat` memory) — a concrete, measured bound on how much freedom the
  planner has, not a synthetic assumption.
- **Semantic review**: whether the resulting stair placement, once structurally valid, is also a
  *good* circulation choice on both floors (does it land in a hallway on one level and inside a
  room's footprint-adjacent corner on the other in a way that still reads well).
- **How a reviewer applies it**: for any multi-level plan, confirm the V-checks passed first (a
  hard floor), then separately judge whether the stair's position reads as a natural circulation
  element on each level rather than a structural afterthought.

## N. Fixture & Clearance Awareness

Rooms with fixtures (bathrooms, toilets, kitchens, laundry) need real clearance around each fixture
— a door should not swing into a toilet or sink, a room should not be sized to its template band
while ignoring what has to physically fit inside it.

- **Deterministic signal (partial — Issue #39, 2026-09-23; Issue #40, 2026-09-23)**:
  `app/vertical_slice/interior_layout.py` places typed `LayoutObject`s per room role (bed/wardrobe,
  sofa/coffee table/focal wall, dining table, kitchen counter run, bathroom/WC fixtures) off the
  realized geometry, deterministically, with each object's own required clearance rectangle — and
  reports an item `unplaceable` (never forcing it) when the room's geometry, a door's swing
  envelope, or another object leaves no room for it. `app.demo.contract.QualityOut`'s
  `DemoDesign.layout` exposes every PLACED object; the frontend (`InteriorLayout.tsx`) draws them
  as-is. Issue #40 (`app/vertical_slice/furnishability.py`) reads those placed objects and rolls
  them into a per-room `Usability` tier (GOOD/ACCEPTABLE/POOR/UNUSABLE) — required object placed,
  a clear straight access path from the door, a blocked window, a usable-wall-length figure — on
  `QualityOut.usability`, additive and disclosure-only. `validation.check_furnishability` (C30) is
  the fail-closed check for the UNUSABLE tier the Issue asked for, fully defined and tested, but
  **NOT called from `validate()`**: MEASURED (not assumed) to fail closed on real, otherwise-valid
  plans this codebase already accepts — the root cause is `interior_layout.py`'s own placement gap
  this same section's "one item, one wall, independently" limitation already names — so it stays
  available for a caller (the same "defined, not wired" precedent `wet_core.
  candidate_wet_core_key`/`better_candidate` already sets here) rather than shipped as a live gate
  that would change which candidate wins. Furnishability SCORING for RANKING (`usability_key`/
  `better_candidate`, mirroring `wet_core`'s own pair) is similarly defined, similarly unwired.
  Door-vs-wet-fixture swing avoidance (C28, `door_clearance.py`) still uses its own conservative
  placeholder fixture footprint independently, not this module's real placements — reconciling the
  two is a future follow-up, not attempted here.
- **Reference comparison**: the guest-WC spec's size band (1.5–3.0 m² net, short side 0.9–1.2 m,
  aspect ≤ 2.2, `specs/009-guest-wc-placement/spec.md` decision D) is the first place this repo
  ties a room's dimensions to what a fixture actually needs, even without simulating the fixture
  itself — a useful reference point independent of the placement above.
- **Semantic review**: whether kitchen counter-run/island proportions and bedroom furniture reads
  as architecturally plausible (not merely non-overlapping) remains a semantic/visual judgment —
  `interior_layout.py`'s item sizes are PARAMETER · UNVERIFIED placeholders, the same disclosure
  discipline as `MIN_FURNITURE_ENVELOPE_M`/`WINDOW_MIN_WIDTH_M`, not a sourced furniture catalogue.
- **How a reviewer applies it**: check `DemoDesign.layout` for a plan's furnished rooms against the
  drawing — an object's rect should read as sitting flush against its own wall, clear of the door's
  swing arc; a room with no `layout` entries for a role this Issue covers (bedroom/master/living/
  dining/kitchen/bathroom/WC) is either an out-of-scope role or every item reported unplaceable —
  check the room's own proportions before assuming a bug. `QualityOut.usability`'s tier per room is
  the rolled-up signal; a POOR tier is worth a second look at the door-to-object sightline even when
  every hard check (including C30, if a future caller wires it) passes.

## O. Site & Orientation Fit

The building's footprint and orientation should respond to the actual site — setbacks, buildable
polygon, solar orientation — rather than being planned inside an abstract rectangle with no
relationship to where it will actually sit.

- **Deterministic signal**: `app/geometry_domain` and the authoritative site-geometry work
  (`docs/AUTHORITATIVE_SITE_GEOMETRY_P0_REPORT.md`, `docs/SITE_AWARE_FOOTPRINT_OPTIONS_REPORT.md`)
  provide setback/buildable-polygon primitives already used by outline search; solar/orientation
  reasoning itself has no deterministic check yet. Planned: ROADMAP P0 "Buildable Region / Site
  Constraints" and P2 "North / Orientation / Solar reasoning" (no Issue numbers assigned yet).
- **Reference comparison**: not yet established — no corpus of site-fitted reference plans exists
  the way the 21-plan interior census does.
- **Semantic review**: whether a plan's orientation choice (which rooms face which direction) makes
  sense for the site without inventing a user preference that was never stated — an explicit
  guardrail already called out in the roadmap item itself.
- **How a reviewer applies it**: confirm the footprint respects known setbacks/buildable polygon
  (deterministic, already available); treat orientation/solar judgment as advisory only until a
  check exists, and never invent a stated orientation preference the user didn't give.
