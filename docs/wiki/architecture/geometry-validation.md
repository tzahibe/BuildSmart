# Geometry / Validation

Status: IMPLEMENTED_MERGED

## Current behavior

`app/geometry_domain/` provides Shapely-backed booleans/offsetting, primitives, transforms, walls,
and linearization — used instead of hand-rolled polygon math because robust boolean geometry is
exactly where hand-rolled code fails silently. `app/geometry/spatial_v2/` holds the frozen
domain-model foundation (`SPATIAL_ENGINE_SPEC_V2_1.md`). Realized-plan validation runs a family of
lettered checks (referenced throughout other Wiki pages as e.g. C17, C20, C21, C22) that hold a
drawing to hard limits (aspect ratio, area maxima, seam/access correctness) regardless of which
planner path produced the candidate — a quality-tier or repartition candidate is never exempt from
them (see Room Proportion / Quality Tier). Building-level checks (the "V" family, e.g. V2, V7) are
kept separate from per-level "C" checks for multi-level buildings.

Open interfaces (doors/openings between rooms) are derived from the realized geometry itself
(`GEOMETRY_DERIVED_OPEN_INTERFACES_REPORT.md`, 636 tests) rather than declared separately —
superseding an earlier declared-interface architecture.

## Authoritative implementation

- `app/geometry_domain/{booleans,primitives,transforms,walls,linearize,constraints,provenance,
  units}.py`.
- `app/geometry/spatial_v2/` (the frozen domain model).
- `app/vertical_slice/validation.py`, `building_validation.py` (the C/V check families).
- `app/vertical_slice/access_rules.py` (door-rule table, door kinds/widths, C24 — Issue #18).
- `app/vertical_slice/exposure_policy.py` (per-role exposure policy table, C19 — Issue #19),
  `app/vertical_slice/windows.py` (`generate_windows`, derives `DAYLIGHT_ROLES`/
  `WET_ROOM_PREFERRED_ROLES` from that table), `app.demo.contract.QualityOut.exposure`.
- `docs/GEOMETRY_DERIVED_OPEN_INTERFACES_REPORT.md` (derived-interfaces architecture, 636 tests).
- `app/vertical_slice/quality_metrics.py` (M1–M6, Issue #17), `app/demo/contract.py`'s
  `QualityOut.metrics`, `tests/regression_corpus/{quality_baseline.json,test_quality_baseline.py,
  freeze_quality_baseline.py}` — see the dedicated section below.
- `app/vertical_slice/validation.py`'s `check_realized_dimensions` (C27, Issue #34),
  `app/demo/contract.py`'s `RoomOut`/`InconsistentGeometryError`/`to_demo_design` — see the
  dedicated section below.

## Current constraints/invariants

- Hard limits (max aspect ratio, area maxima) are enforced identically regardless of which planner
  mechanism produced a candidate — quality-tier/repartition candidates get no exemption.
- Per-level "C" validation and building-level "V" validation are kept separate for multi-level
  buildings (see Multi-Level).
- Open interfaces are derived from realized geometry, never declared as a separate, potentially
  inconsistent source of truth.

## Supersedes

`docs/BRANCHED_CIRCULATION_ARCHITECTURE_REPORT.md` (superseded once open-interface derivation
landed); `docs/GENERAL_GEOMETRY_ARCHITECTURE_REPORT.md` (research-only, superseded by
`GENERAL_GEOMETRY_DOMAIN_V1_REPORT.md`); `docs/SPATIAL_ENGINE_RESEARCH.md` and
`docs/SPATIAL_ENGINE_SPEC_V2.md` (both explicitly superseded by `SPATIAL_ENGINE_SPEC_V2_1.md`).

## Access topology and door rules (C24)

Issue #18 (2026-09-18). Interior doors were previously placed for every non-OPEN_CONNECTION edge
declared in a fixture's `DesiredAccessTopology` with no rule saying which role pairs a door may
legitimately connect — correct only because the planner (`concept_generator.py`) happened to
never emit a PRIVATE-to-PRIVATE edge, with nothing to catch it if a future planner path did.
`app/vertical_slice/access_rules.py` makes the rule explicit and machine-checked:

- **`ALLOWED_ENTERED_FROM`**: for every `ProgramRole`, the roles a room of that role may be
  entered FROM. PRIVATE rooms (BEDROOM, MASTER_BEDROOM, SAFE_ROOM, STUDY, DRESSING_ROOM): only
  HALL/CIRCULATION — never another PRIVATE room. Wet rooms (BATHROOM, TOILET): HALL/CIRCULATION,
  the hosting bedroom for an ensuite, or **LIVING** — the last public-access fallback per
  `specs/009-guest-wc-placement` decision C (Issue #69); KITCHEN and DINING stay disallowed.
  Narrow service rooms (LAUNDRY, STORAGE):
  HALL/CIRCULATION, plus the KITCHEN they serve. Public/circulation rooms
  (ENTRANCE/LIVING/DINING/KITCHEN/FAMILY_ROOM/FLEX/HALL/CIRCULATION/STAIRWELL): any other
  public-or-circulation room. `edge_role_pair_allowed` checks one edge's two zone role-sets
  against the table (a zone can carry more than one role); this is what rules out a
  bedroom-to-bedroom door — that pair is simply never in either room's allowed set — without the
  code naming that pair specially.
- **Door kinds/widths**: `DoorKind.ROOM_DOOR` (0.9 m, unchanged historic width), `SERVICE_DOOR`
  (0.8 m, new — LAUNDRY/STORAGE/TOILET only; BATHROOM keeps ROOM_DOOR width), `ENTRANCE_DOOR`
  (1.0 m, unchanged). `door_kind_for_zones` picks the class for one edge from its two zones'
  roles. `doors.py::generate_interior_doors` now reads the width for each edge from
  `access_rules.DOOR_WIDTH_M[door_kind_for_zones(...)]` instead of a single hard-coded constant —
  realized door geometry is otherwise unchanged (same placement/swing logic, only the width value
  for TOILET/LAUNDRY/STORAGE edges is narrower).
- **C24 "access topology obeys the door rules"** (`check_access_topology`, wired into
  `validation.py` next to C5): three defects, checked together, fail closed. (1) every enclosed
  (non-open-plan) room has at least one DOOR/CASED_OPENING edge. (2) every such edge's role pair
  is one `ALLOWED_ENTERED_FROM` permits — this alone also covers "no PRIVATE-to-PRIVATE door
  except the ensuite host," since that pair is never allowed. (3) no room is reachable from the
  entrance only by continuing on past another PRIVATE room (a private-room chain), walked over the
  same REALIZED access graph C5 already builds — not the declared topology — so a wall accidentally
  typed OPEN between two rooms cannot create a silent chain either. C24 is additive: it passes on
  every existing corpus context and canonical fixture without changing any of them; it exists to
  catch a FUTURE planner path that would otherwise silently emit a disallowed edge.

## Entrance / arrival-room policy (C23)

Issue #20 (2026-09-18). The front door has to open into a room a visitor may actually arrive
in — a hall, a circulation zone, or the living room — never a kitchen, a dining room, a private
room (bedroom, master bedroom, safe room, study, dressing room) or a wet/service room. Before this
Issue, `resolve_entrance`'s priority order also included DINING and KITCHEN, so a plan whose only
street-fronting public room was the dining room got its front door there — geometrically correct
(C16 passed: the door genuinely sat on that room's own wall) but architecturally a random room,
not an entrance.

- **`doors.py::ENTRANCE_ZONE_PRIORITY`** is now exactly `(HALL, CIRCULATION, LIVING)` —
  `ALLOWED_ENTRANCE_ROLES` is the same set. `resolve_entrance` is unchanged in mechanism (it still
  reads the realized geometry: the street-fronting zone with the best rank in this tuple) but
  returns `None` whenever nothing in the narrower tuple fronts the street with enough frontage for
  a door — including a plan whose only street-fronting rooms are DINING/KITCHEN, which used to
  resolve. `doors.py::street_fronting_roles` reports what WAS there (allowed or not), so a refusal
  can name it.
- **Candidate ranking** (`general_pipeline.run_general`'s main loop, the non-relationships path):
  among candidates that realize and validate, one whose entrance rank
  (`general_pipeline._entrance_rank`: 0 for HALL/CIRCULATION, 1 for LIVING) is better than the
  best found so far replaces the current choice; `fast_path` still stops the instant rank 0 is
  reached, so a brief whose first valid candidate already has a HALL/CIRCULATION entrance costs
  exactly what it did before this Issue. Untouched for the `relationships` path and for the
  hub-guard/quality-twin passes that run after selection — those stay governed by full validation
  (C23 is defense-in-depth there too) but are not entrance-rank-aware; out of scope for #20.
- **`ENTRANCE_NO_ARRIVAL_ROOM`** (`app/demo/service.py::_finish`): the specific refusal when a
  plan's front door has nowhere legitimate to open into. Gated on an entrance-related check
  actually failing (C16/C23/C7/C11) AND none of the realized plan's street-fronting rooms having
  an allowed role, so an unrelated validation failure is never misdiagnosed as an entrance
  problem; the message names whatever WAS found fronting the street (e.g. "המטבח, פינת האוכל").
  Listed in `_FEASIBILITY_CODES`.
- **C23 "entrance opens into an allowed arrival room"** (`validation.py`, next to C16, under the
  same `skip_site_checks` gate — a multi-level upper storey has no street door, so it is not held
  to this check): fails closed whenever the entrance door's named zone carries no role in
  `ALLOWED_ENTRANCE_ROLES`, independent of HOW that zone name was chosen. Defense in depth for
  every path that draws a front door, including the frozen pipeline (`pipeline.py::run_once`),
  which now calls `resolve_entrance` at its one call site instead of hardcoding `HALL_MAIN` —
  the frozen baseline's own HALL fronts the street, so its own behaviour is unchanged.
- **Corpus effect**: measured on the frozen 432-context corpus (before/after `corpus_snapshot.py`
  compare, 8 workers): LOST=0, GAINED=0, refusal-code changes=0, primary-signature changes=19 (the
  40-context budget). No corpus context's PRIMARY was ever actually a kitchen/dining entrance —
  the pre-existing C16 check ("the entrance opens into the room it names") already kept a
  hardcoded-fallback entrance off a room that does not front the street, so a dining/kitchen-only
  candidate never validated to begin with, in either the pre- or post-#20 code. All 19 changes are
  the RANKING taking effect among candidates that already validate: 17 contexts' primary moved
  from a LIVING entrance to a HALL/CIRCULATION one; 2 contexts kept a LIVING entrance (no better
  candidate exists) but the same ranking mechanism still changed which validating candidate is
  first-found, so their geometry signature differs too. The full per-context before/after list
  is committed at `docs/reports/issue-20-entrance-signature-changes.md`.

**PROPOSED, not scheduled — foyer synthesis.** A context whose EVERY candidate's only
street-fronting public room is the kitchen or dining room (none measured in the frozen corpus, but
not provable impossible for an arbitrary brief/parcel) would refuse with `ENTRANCE_NO_ARRIVAL_ROOM`
rather than fabricate an entrance. The fix is a small street-side foyer the planner adds within the
existing area budget — a new zone, which is planner/generator work, not a validation or ranking
change — deliberately left for a future Issue rather than attempted here.

## Windows and exterior exposure (C19/C8)

Issue #19 (2026-09-18). A room's relationship to the building envelope is two separate questions
that used to be conflated into one gate (C8 alone): must it TOUCH an exterior wall at all (a
planning-TOPOLOGY fact), and does it need a WINDOW once it does (a sizing fact — does a window of
at least the minimum width actually fit on that wall). An interior bedroom and an exterior
bedroom whose only exterior wall is too short for a window both used to fail C8 identically, with
no way to tell which defect a refusal names. Before this Issue only `DAYLIGHT_ROLES` — a
hand-maintained, six-role subset (LIVING, DINING, KITCHEN, BEDROOM, MASTER_BEDROOM, SAFE_ROOM) —
had any exposure rule at all; FAMILY_ROOM, STUDY, DRESSING_ROOM, LAUNDRY, STORAGE, CIRCULATION had
none.

**The policy table** (`app/vertical_slice/exposure_policy.py`, `EXPOSURE_POLICY`): one
`ExposurePolicy(exterior_wall, window)` per `ProgramRole`, each field `REQUIRED | PREFERRED |
NONE`. Every role has an entry — the policy covers every room type, not a subset. The owner's
decision, recorded in the Issue #19 contract:

| Tier | Roles |
|---|---|
| REQUIRED / REQUIRED | LIVING, DINING, KITCHEN, BEDROOM, MASTER_BEDROOM, SAFE_ROOM, FAMILY_ROOM, STUDY |
| PREFERRED / PREFERRED | BATHROOM, TOILET, DRESSING_ROOM |
| NONE / NONE | HALL, CIRCULATION, STORAGE, ENTRANCE, STAIRWELL, FLEX, LAUNDRY |

LAUNDRY is deliberately NONE here — its own Issue owns that decision; NONE only preserves
today's behaviour (skipped by `generate_windows` entirely) until it does. FAMILY_ROOM and STUDY
moving from "no rule at all" to REQUIRED/REQUIRED is the one behaviour change with corpus
consequences — see below.

`windows.py`'s `DAYLIGHT_ROLES` (roles whose `window` policy is REQUIRED — what C8 gates on) and
`WET_ROOM_PREFERRED_ROLES` (roles whose `window` policy is PREFERRED — attempted best-effort,
never gating) are now DERIVED from this table rather than hand-maintained; `REQUIRED_EXTERIOR_ROLES`
(what C19 gates on) is exported from `exposure_policy.py` directly.

**C19 "required rooms touch an exterior wall"** (`validation.py`, runs immediately before C8):
a purely GEOMETRIC check, via `envelope_sides` only (the same geometry-derived function
`wall_facts_for_room` uses for `boundary_context` — never the raw solver `WallType`, which is
also EXTERIOR-when-safe-room-precedence and would be wrong for that case). Fails closed on any
`REQUIRED_EXTERIOR_ROLES` zone with no exterior side at all. **C8** keeps its original meaning
unchanged — "a window of at least `WINDOW_MIN_WIDTH_M` is placed where the policy's `window` tier
is REQUIRED" — so an exterior bedroom whose only exterior wall is shorter than the minimum window
still fails C8 (not C19): the two checks name the topology defect and the sizing defect
separately, and C19 running first means a refusal on an interior room always names the real
cause.

**The sizing constants are unchanged and still PARAMETER · UNVERIFIED**: `WINDOW_WALL_FRACTION`
(0.4), `WINDOW_MIN_WIDTH_M` (0.9 m), `WINDOW_MAX_WIDTH_M` (2.0 m) for `DAYLIGHT_ROLES`;
`WET_ROOM_WINDOW_WALL_FRACTION` (0.25), `WET_ROOM_WINDOW_MIN_WIDTH_M` (0.5 m),
`WET_ROOM_WINDOW_MAX_WIDTH_M` (1.0 m) for `WET_ROOM_PREFERRED_ROLES` — plausible placeholders,
not sourced from a specific glazing-ratio code requirement, same disclosure discipline as
`geometry_core.model.WALL_THICKNESS_M`'s RC_SAFE_ROOM entry. This Issue only decoupled which
rooms the constants apply to from what fact each check enforces; it did not touch the constants
themselves.

**Exposure report** (`app.demo.contract.QualityOut.exposure`, additive): one `ExposureOut` per
room on every delivered `DemoDesign` — `exterior_sides`, and either the window that was placed
(`window_side`/`window_width_m`) or `no_window_reason`: `NO_EXTERIOR_WALL` (C19's defect on this
room, when its policy requires an exterior wall), `EXTERIOR_WALL_TOO_SHORT` (C8's defect, when its
policy requires a window), or `WINDOW_NOT_REQUIRED` (the role's window policy is NONE). Computed
in `contract.to_demo_design` off the raw solver output (`room.wall_facts`, `design.windows`), the
same pattern M1–M6 uses for needing the fully-assembled shape.

**Corpus impact measured**: the frozen 432-context regression corpus (`tests/regression_corpus/
corpus.json`) has no request path that produces a FAMILY_ROOM or STUDY zone at all (its contexts
vary only `bedrooms`/`wet_rooms`/`safe_room`/`open_plan`/plot and footprint dimensions) — so
promoting those two roles to REQUIRED/REQUIRED changes zero corpus outcomes; LOST/GAINED/
primary-signature stayed at 0 on the frozen corpus by construction, not by a planner-side fix.
FAMILY_ROOM/STUDY REQUIRED/REQUIRED is proven instead by a dedicated fixture test
(`test_exposure_policy.py::test_family_room_and_study_get_windows`). If a FUTURE corpus or a real
request ever plans one of these roles fully interior, C19 will refuse it where nothing did
before — the planner-side placement fix for that case is explicitly not this Issue's scope.

## Architectural-quality metrics (M1–M6) and the corpus baseline

Issue #17 (2026-09-17). Hard validation (above) enforces the structural basics — no overlap, no
dead space, dimension/aspect/area maxima, reachability, declared access, bathroom access — but says
nothing about architectural QUALITY: room proportions, wet-room adjacency, circulation share,
public-zone contiguity. Six metrics, M1–M6, measure that on realized geometry:

- **M1** habitable-room aspect (long/short), median and worst, by room type.
- **M2** share of habitable rooms touching the exterior envelope.
- **M3** circulation (hall) share of total room area.
- **M4** doors opening onto the hall, and the hall's own long/short aspect.
- **M5** share of wet rooms (bathroom/toilet) sharing an interior wall with another wet room,
  the kitchen, or the laundry.
- **M6** whether the public zone (living/dining/kitchen) is one contiguous open-plan group.

**Authoritative implementation**: `app/vertical_slice/quality_metrics.py` —
`measure_design(design) -> QualityMetrics` for one plan, `summarize(designs) -> dict` for a
corpus-level report (medians/shares/by-type breakdowns). Side-effect-free, no planner/validation
coupling — read-only off a realized `app.demo.contract.DemoDesign`.
`spikes/failure_log_sweep/quality_metrics.py` is now just the corpus driver and printed report
around this module (previously it computed M1–M6 itself).

**Per-plan reporting**: `app.demo.contract.QualityOut.metrics` (a `QualityMetricsOut`) carries
M1–M6 for that one plan on every delivered `DemoDesign`, plus `dead_space_m2` (always `0.0` —
validation C2 already gates every delivered plan to zero residual interior area) and
`wasted_circulation_share` (the share of M3's circulation area sitting in a hall past the compact
threshold below — the portion of circulation that reads as a spine rather than a lobby, and so is
plausibly recoverable). Computed once, in `contract.to_demo_design`, from the same flattened
walls/open-interfaces/doors that function already builds.

**Corpus regression signal**: `tests/regression_corpus/test_quality_baseline.py` (REGRESSION tier,
`tests/conftest.py`'s shared TEST_MODE gating) recomputes `summarize()` over the 404 PLANNED cases
of the frozen 432-context corpus (`corpus.json`) and compares four load-bearing stats against a
committed baseline, `tests/regression_corpus/quality_baseline.json` — produced by the re-runnable
`tests/regression_corpus/freeze_quality_baseline.py`. Tolerances (percentage points for a share,
aspect-ratio units for M4; a metric moving in the IMPROVING direction never regresses):

| Metric | Tolerance |
|---|---|
| M3 circulation-share median | 2 pp |
| M4 hall aspect median | 0.2 |
| M5 wet-adjacency share | 2 pp |
| M6 public-contiguity share | 2 pp |

This is a **no-regression bar, not a new absolute one** — it passes unchanged on today's main and
exists only to catch a FUTURE planner/template change quietly making one of these four worse.

**CI cost (Issue #17 repair, 2026-09-18)**: gate-4 (`agent-regression.yml`) already replays the
whole corpus twice — merge-base and head, via `spikes/failure_log_sweep/corpus_snapshot.py` — to
check outcome/signature invariants; the test above replaying it a THIRD time, sequentially, in one
pytest process blew the 120-minute CI budget. `corpus_snapshot.py` now also records each PLANNED
context's `measure_design` output under `"metrics"` (plus two raw counts,
`m5_wet_adjacent_count`/`m5_wet_total_count`, folded into that same dict — not part of
`QualityMetrics`/`QualityOut`, only the snapshot's own copy, needed because M5's per-plan RATIO
alone cannot be pooled back into a corpus-level share: plans have different wet-room counts, so an
unweighted mean of per-plan ratios is a different number — 11.7 pp off on this corpus, ~6x the
tolerance — from `summarize()`'s pooled adjacent/total share). When gate-4's `CORPUS_SNAPSHOT` env
var points at that snapshot, `test_quality_baseline.py` reads the stored `"metrics"` and computes
the same four stats via `quality_metrics.baseline_summary_from_metrics` WITHOUT calling
`generate_demo_design` again; without the env var (developer runs), it replays the corpus exactly
as before. M3/M6 reproduce `summarize()`'s aggregation exactly either way (both are already
per-plan values there); M4 does too on today's corpus (every plan has at most one hall room) but
would only approximate on a future corpus with multi-hall plans, the same way a naive M5 does.
`freeze_quality_baseline.py --from-snapshot SNAPSHOT.json` freezes the baseline from a snapshot
the same way, with no corpus replay.

**Measured gaps against 21 professional Israeli plans** (visual census, 2026-09-11 —
memory `architectural-quality-gaps-measured`; the same figures Issue #17's own "Current behavior"
cites): exposure (~100%, M2) and circulation share (median ~11% vs reference 8–14%, M3) are
already at reference level — NOT gaps. Three real gaps, ranked:

1. **Circulation topology**: one hall spine, long/short median 9.4, 0% compact, vs ~18/21
   reference plans having a compact "room lobby" hub (~2.5–3.5 m square, 4–7 doors) bedrooms wrap
   on up to 3 sides. The structural change spec 005 (hub parti) attempted and was rejected —
   see below.
2. **Wet-room adjacency**: 40% of bathrooms share a wall with a wet room/kitchen/laundry vs
   ~85–90% in the reference set (M5).
3. **Public rooms come out as strips**: KITCHEN median aspect 2.75, DINING 2.35, vs reference
   kitchens as an L-counter inside one open volume, not a room with its own shape (M1, public
   rooms).

## Realized dimensions: gross vs net, and C27 (Issue #34)

Every width/depth/area shown to a person derives from ONE realized geometry, with each
user-facing number's definition documented here rather than left to be inferred from a field name:

- **`gross_rect`** (`x`, `y`, `gross_width_m`, `gross_depth_m` on `app.demo.contract.RoomOut`):
  the room's CENTERLINE allocation — `app.vertical_slice.design_output.RoomOut.rect_m` — plot-
  absolute, extending to the centerline of every bounding wall. This is what the drawing draws:
  wall segments (`_wall_segments` in `contract.py`) are derived from this same rectangle, so a
  room's drawn box and its walls can never disagree.
- **`net_rect`** (`width_m`, `depth_m` on `RoomOut`): the USABLE rectangle — `gross_rect` minus
  each side's own wall INSET, where the inset is half that side's wall thickness (the room's own
  share of a shared wall; `geometry_core.engine.net_rect_m`, `geometry_core.model.inset_u`). A
  0.30 m exterior wall costs the room 0.15 m off that side; a shared 0.10 m partition costs each
  neighbour 0.05 m.
- **`net_area_m2`** (`area_m2` on `RoomOut`): `net_width × net_depth`, exactly — never a
  separately-tracked number, so it can never drift from the net rectangle it describes.
- **`gross_area_m2`** (on `RoomOut` and on `DemoDesign`): `gross_width × gross_depth` per room;
  at the building level, `fixture.footprint_area_m2()` — equal to the SUM of every room's own
  `gross_area_m2`, because centerline allocation is an exact tiling of the footprint (no double-
  counted or missing wall area).
- **Wall treatment**: a wall's full thickness is drawn once (as a segment at the shared
  centerline); each of the two rooms it separates loses only ITS HALF from `net_rect` — so
  `net_area_m2` is genuinely "what this room can put furniture in," not the room's share of the
  wall counted twice or not at all.

**Before Issue #34**: `RoomOut.width_m`/`depth_m` were the GROSS dimensions while `area_m2` was
`net_area_m2` — so `width_m × depth_m` did not equal `area_m2` on virtually every room (the
displayed rectangle was bigger than the displayed area it was labelled with). Fixed by making
`width_m`/`depth_m` the NET pair `area_m2` was already reporting, and adding `gross_width_m`/
`gross_depth_m`/`gross_area_m2` so the drawing (which must stay aligned with the wall segments,
themselves derived from the gross rect) keeps its own consistent numbers alongside.

**C27** ("displayed dimensions consistent with realized geometry",
`app.vertical_slice.validation.check_realized_dimensions`) checks, on the final `RoomOut` list a
product path is about to show: `|net_width_m × net_depth_m − net_area_m2| ≤ 0.05 m²` and
`|gross_width_m × gross_depth_m − gross_area_m2| ≤ 0.05 m²` per room, the net rectangle never
exceeds its own declared gross rectangle, and the building's `gross_area_m2` equals the sum of
every room's `gross_area_m2` within the same tolerance. It runs inside
`app.demo.contract.to_demo_design` — the one place the authoritative payload is assembled — and
raises `InconsistentGeometryError` there, which `app.demo.service` turns into a
`DemoGenerationError("INCONSISTENT_GEOMETRY", ...)`: the product refuses rather than shows a
self-contradictory plan. C27 duck-types its input (no import of `contract.RoomOut` into the
validation layer) so it can run on demo contract objects without a layering cycle. On a real
solved design this check passes by construction — `net_rect_m` computes net width/height/area
together — so it costs no regression risk and exists specifically to catch a FUTURE seam between
the solver and this contract (or, in a test, a deliberately tampered fixture) before it reaches a
person.

## Architectural quality rubric and anti-pattern library

The measured gaps above (circulation topology, wet-room adjacency, public-room strips) are three
entries in the canonical, repo-wide quality rubric and anti-pattern library:
`docs/architecture_reference/quality_rubric.md` (sections A–O) and
`docs/architecture_reference/anti_patterns.md`. Every later geometry/circulation/interior Issue and
every reviewer should consult those files rather than re-deriving quality judgments from this page
alone.

## Reference benchmark against curated plans (Issue #32)

2026-09-18. `app/vertical_slice/reference_benchmark.py`'s `benchmark(design, references) ->
BenchmarkReport` reports one deterministic `SectionFinding` per rubric section
(`docs/architecture_reference/quality_rubric.md`) for a realized plan, comparing six of them
(entrance, circulation, zoning, exposure, dead space, and a room-area consistency fact — see that
module's own docstring for its own section-lettering, which does not match the rubric's A–O)
against `docs/architecture_reference/references/index.json` entries of the same `footprint_family`
— metadata and derived ratios only, never a reference plan's own geometry. The other nine rubric
sections come back `not_measured`. `backend/scripts/reference_benchmark.py --context <id>` prints
the report for one `tests/regression_corpus/corpus.json` context; not wired into
`agentctl`/the corpus sweep yet (out of scope for Issue #32 — see the Issue's own scope note).

## Known follow-ups

**PROPOSED, not scheduled — Issue #17 explicitly keeps these as write-ups, not new Issues:**

- **Public-room strip fix through the quality tier.** Gap 3 above (KITCHEN/DINING strips) is the
  same shape the room-proportion quality tier (see that Wiki page) already re-proportions bedrooms
  away from — extending that tier's row-sharing/re-proportioning logic to the public band's rooms
  is a plausible, incremental fix that does not touch the planner's topology. Not designed or
  measured yet; the quality tier's own known limits (row-sharing topology ceiling) would need
  re-checking against public-band rows specifically.
- **Private-wing lobby topology** (gap 1, the largest measured gap). Spec 005 (hub-private-wing)
  already tried this — v1 through v2.1, `specs/005-hub-private-wing/` — and was rejected on two
  hard acceptance gates (see `specs/005-hub-private-wing/RESULTS.md` and the
  `row-sharing-topology-limit-and-quality-tier` / `seam-shape-selection-investigation` memories for
  what was tried since and why it did not close the gap). Re-attempting the hub parti is
  explicitly OUT OF SCOPE for Issue #17; any future attempt should start from why v1–v2.1 failed,
  not repeat the same seat count.

Beyond these two: none currently tracked at the Wiki level from the pre-#17 state of this page.
A third, from Issue #20: **foyer synthesis** — see the Entrance / arrival-room policy section
above.

## Evidence/history

`docs/SPATIAL_ENGINE_SPEC_V2_1.md` (the frozen domain model), `docs/GENERAL_GEOMETRY_DOMAIN_V1_REPORT.md`,
`docs/SAFE_GEOMETRY_ADAPTER_V1_REPORT.md`, `docs/REALIZED_CONNECTIVITY_INVARIANT_REPORT.md`,
`docs/GEOMETRY_DERIVED_OPEN_INTERFACES_REPORT.md`, `docs/AUTHORITATIVE_SITE_GEOMETRY_P0_REPORT.md`,
`docs/SITE_AWARE_FOOTPRINT_OPTIONS_REPORT.md`, `specs/005-hub-private-wing/spec.md` §1 (the 21
professional plans' reference values) and `RESULTS.md` (why the hub parti was rejected).

## Last verified against git

`bffd624` (branch `agent/18-door-and-access-topology-rules-every-enc`, based on `origin/main`);
the Access topology and door rules (C24) section above documents work landing on this branch
(Issue #18), verified against this session's own implementation and test runs. The M1–M6 section
documents Issue #17, verified against that session's implementation and test runs, not
independently re-verified beyond that.

`36b27e8` (branch `agent/19-windows-and-exterior-exposure-exposure-c`, based on
`origin/integration/holiday-yom-kippur-2026`); the Windows and exterior exposure (C19/C8) section
above documents work landing on this branch (Issue #19), verified against this session's own
implementation and test runs.

Branch `agent/20-entrance-policy-the-front-door-opens-int`, based on
`origin/integration/holiday-yom-kippur-2026` (merged forward to include #19/#21/#37 and the infra
merge): the Entrance / arrival-room policy (C23) section above documents Issue #20, verified
against this session's own implementation and test runs, including this merge's conflict
resolution (combined check count, both new-section additions kept intact).

Branch `agent/34-realized-area-and-dimension-consistency`, based on `origin/main` after PR #62's
squash-merge of the integration branch (#18/#19/#20/#21/#24/#25/#29–#33/#37/#44/#63/#69): the
Realized dimensions: gross vs net, and C27 (Issue #34) section above documents this branch's own
work, verified against this session's own implementation and test runs, including this merge's
conflict resolution (main's version of every shared/foreign section kept intact, this Issue's own
section re-applied on top unchanged).
