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
- `app/vertical_slice/circulation_metrics.py` (dedicated-circulation metrics, C26, the ranking
  term — Issue #36), wired into `app/vertical_slice/validation.py` (C26) and
  `app/vertical_slice/general_pipeline.py`'s `_guard_demoted_hub` — see the dedicated section
  below.

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

## Entrance-to-circulation integration (C25)

Issue #22 (2026-09-20). C23 above decides WHICH room the door opens into; it says nothing about
whether that room actually LEADS anywhere, or whether a different circulation zone happens to
touch the street uselessly beside it. `app.vertical_slice.entrance_sequence` measures the entrance
SEQUENCE off realized geometry (`GeometricDesign`, the same input `circulation_metrics.py`/C26
reads), the same "measure real plans, then set the limit with headroom above them" discipline C26
uses:

- **POCKET** (blocking): the walking distance from the entrance door to the NEAREST other opening
  (a door, or an open-plan join) reachable from the arrival zone — dead space directly behind the
  front door with no function. Measured "nearest in any direction", not "the far wall straight
  ahead": an ordinary spine hall's own far end (opposite the entrance) is a KNOWN, ACCEPTED dead
  end by construction (`circulation_metrics.dead_end_count` tolerates exactly one), and a compact
  hub with doors branching off near the entrance is the architecturally preferred topology
  (specs/005) — neither is a pocket.
- **STRAY POCKET** (blocking, the OTHER shape the Issue's "Current behavior" names: "leaving the
  corridor's street-facing end as a blind pocket beside the entrance"): any OTHER circulation zone
  (not the arrival zone) that independently fronts the street with more than
  `ENTRANCE_STRAY_POCKET_MAX_M` of unserved depth before its own first opening, measured from its
  own street-wall midpoint.
- **NO PUBLIC OPENING** (blocking): no PUBLIC-group room is reachable from the arrival zone at all,
  through further circulation.
- **TUNNEL** (`classify_tunnel`, NON-BLOCKING): the walking distance from the entrance to the
  first PUBLIC-group room reached, threading only through further circulation, plus how many
  PRIVATE rooms' doors were passed on the way. Reported and available as a candidate tiebreak
  (`entrance_sequence_prefers`, `hub_guard`/`circulation_prefers`-style, tested directly), never a
  gate — fixing a genuine tunnel is a parti change (a future "Entrance Sequence Quality" Issue),
  and a blocking check there would violate LOST = 0. NOT wired into
  `general_pipeline._guard_demoted_hub`: that function's own existing test mocks `plan.design` as
  a bare `SimpleNamespace(gross_area_m2=...)`, which `entrance_sequence.measure` cannot read
  (`.entrance_door` missing) — wiring it there means editing Issue #36's own test fixture for a
  hub-only path already unreachable on the corpus (`row-sharing-topology-limit` memory), not worth
  the risk. The ranking function itself is real and tested
  (`test_tunnel_sequence_is_reported_and_ranked_down_but_not_refused`); wiring it into a live
  candidate-selection path is left for whichever future Issue makes a hub candidate reachable
  again.

**`ENTRANCE_POCKET_MAX_M` (4.0 m), `ENTRANCE_STRAY_POCKET_MAX_M` (0.6 m) and
`ENTRANCE_TUNNEL_MAX_M` (4.0 m)** are all PARAMETER · UNVERIFIED, calibrated on
`scripts/entrance_sequence_sweep.py`'s sweep of the full 432-context frozen regression corpus plus
geometry fixtures (`docs/ENTRANCE_CIRCULATION_SWEEP.md`) — not a code minimum, the same discipline
`circulation_metrics.EXTREME_RATIO`/`EXTREME_LONGEST_SEGMENT_M` use. These are two DIFFERENT
real-world distributions, so they get two DIFFERENT constants rather than sharing one:

- `ENTRANCE_POCKET_MAX_M` governs the ARRIVAL zone's own pocket (`_pocket_length_m`). The Issue's
  own illustrative default (0.6 m) does not survive contact with real plans here: `pocket_length_m`
  measures 0.00-3.28 m across the corpus's 404 PLANNED contexts (mean 1.82 m — an ordinary hall's
  own width plus jamb clearance before the first room off it, a normal architectural fact, not
  wasted space), so 0.6 m would refuse most plans in the corpus. 4.0 m sits with real headroom
  above every measured NORMAL plan while still catching a genuinely dead stub (0 pocket failures
  on the full corpus, 0 "no public opening" failures) — a decision the owner may revisit.
- `ENTRANCE_STRAY_POCKET_MAX_M` governs `_stray_pockets` — a SEPARATE circulation zone beside the
  entrance. This shape needs no headroom: every real spine candidate has exactly one `HALL` leaf
  (`concept_generator.py`'s `_concept_from`), so the sweep found ZERO PLANNED contexts with a
  second circulation zone at all. The constant therefore carries the Issue's own literal 0.6 m
  default unchanged, giving it a genuine protective margin (AC-5's fixture, a 1.5 m stub, fails it
  directly — no adversarial scaling needed) rather than one backed into just above the corpus's
  own observed maximum.

342/404 contexts DO show a TUNNEL signal — a real, common, non-blocking fact about this
generator's spine parti, not a defect.

**C25 "no dead-space pocket at the entrance"** (`validation.py`, next to C23, under the same
`skip_site_checks` gate): fails closed on either blocking condition above, reusing the SAME minimal
`GeometricDesign` C26 already assembles for this plan (never a second build). The demo path refuses
with **`ENTRANCE_DEAD_END`** (`app.demo.service._finish`) when C25 is the ONLY failing check — the
same "one specific reason at a time" discipline `ENTRANCE_NO_ARRIVAL_ROOM`/`LAUNDRY_UNPLACEABLE`
follow.

**The engine topology invariant (AC-3), verified rather than newly enforced.** The Issue's
"required behavior" asks that the corridor's endpoint be derived from the last door it serves,
never the footprint boundary, as an ENGINE change (`concept_generator.py`/`l_parti.py`). The sweep
found this already holds today for every real candidate measured (spine and L parti): a spine
column's rows sum to exactly the wing's own depth by construction (`_row_depths`), so the hall's
far end always coincides with the last row's own boundary; the L parti's hall sits inside
`H(band, V(column, HALL))`, never touching the street independently of the band. No context in the
432-context corpus, the canonical baseline, or a real L-massing candidate
(`l_shaped_site_front_arm`) shows a stub, matching `circulation_metrics.py`'s own C26 EXTREME-case
precedent (a fixture that codebase's generator does not currently produce by accident). No
`concept_generator.py`/`l_parti.py` code change was made; `test_entrance_circulation.py`'s
`test_corridor_ends_at_the_last_served_door_not_at_the_boundary` proves the invariant against REAL
realized spine and L candidates so a FUTURE regression is caught — the same additive,
defense-in-depth spirit C24/C25/C26 all follow.

**`QualityOut.entrance_sequence`** (additive): arrival zone, pocket length, whether a public
opening exists, distance to it, private doors passed, the foyer heuristic, and the tunnel text —
computed in `contract.to_demo_design` off the same raw `SolvedDesign` C25/M1–M6 already read.

**Intentional foyer.** A HALL zone with its own program area and a nearby opening onward passes
C25 cleanly and is reported `foyer=True` — never flagged as a pocket; `foyer` is a reporting-only
heuristic (HALL role + a clean sequence), never a gate.

**Out of scope, deliberately** (per the Issue): the arrival-room policy itself (#20, C23 above),
furniture/decorative foyer design, and fixing a genuine tunnel by changing the parti (a future
Issue) — a blocking check for the tunnel would violate LOST = 0.

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

## Typed constraints and the SAFE_ROOM/MAMAD refusal (Issue #35)

Before this, "is there a safe room" was a single `bool` (`ProgramSpec.safe_room`) read
independently by `concept_generator.py`, C4, the contract and the hub/L-massing guards — nothing
carried WHY the room exists and nothing PROVED it was still there by the time C4 ran; a fallback
ladder, a candidate swap or an alternative selection could in principle drop the room and C4's own
loop (only ever looking at zones that ARE safe rooms) would find nothing to check and report "safe
room compliant" — a false pass, not a caught defect.

`app/vertical_slice/constraints.py` now derives one `TypedConstraint(kind=SAFE_ROOM,
source=USER|COMPLIANCE|NONE, authoritative, min_area_m2)` per spec, ONCE, from the resolved
requirement bool (`ArchitecturalSpec.safe_room_constraint`, derived from `program.safe_room`, never
stored so it cannot drift). `ConstraintSource.COMPLIANCE` is reserved for a future legal-
applicability rule — nothing in this codebase derives it today, and a brief without a safe-room
requirement always resolves to `NONE`/not-authoritative, never inventing the room or a compliance
warning.

**Checked, not merely carried**, at two stages:

1. **After concept generation** — `generate_concepts` asserts the room programme it is about to
   build candidates from still carries SAFE_ROOM whenever the constraint is authoritative
   (`assert_realized`, raising `SafeRoomDropped`).
2. **In the validator** — C4 ("safe room valid ... an authoritative SAFE_ROOM constraint is
   realized") additionally fails, independent of its existing RC-envelope/regulated-minimum checks,
   when an authoritative constraint has no zone that is both a safe room AND has a REALIZED rect
   (`zone_id in rects` — a zone the concept declared but the solver never gave a rectangle to is
   exactly as dropped as one never declared). This is what actually gates delivery: every plan
   `app/demo/service.py` delivers (primary and every alternative) is asserted `validation.ok`, so a
   candidate or alternative that lost the room during geometry realization or a repartition/quality-
   tier swap never reaches the screen — it simply fails C4 like any other hard check.

`app/demo/service.py` turns both signals into the same product refusal, code `SAFE_ROOM_DROPPED`,
never a plan without the room: `generate_demo_design` catches `SafeRoomDropped` from the concept
stage directly; `_finish` (the terminal refusal once every outline has been tried) checks first,
before its other check-specific diagnoses, whether the final result's C4 failure names the same
detail string (`SAFE_ROOM_NOT_REALIZED_DETAIL`) and raises the same code if so.

`app/demo/contract.py`'s `QualityOut.constraints` (a `list[ConstraintOut]`, `kind`/`source`/
`authoritative`/`min_area_m2`) carries the constraint through to the contract whenever the brief's
source is not `NONE` — attached in `to_demo_design` via a new, additive `constraint` parameter — so
the screen/support tooling can show WHERE the requirement came from (a person asked vs. a future
compliance rule), never an empty guess. A brief without one gets an empty list, never a `NONE`-
source entry.

**Authoritative implementation**: `app/vertical_slice/constraints.py` (`TypedConstraint`,
`derive_safe_room_constraint`, `assert_realized`, `SafeRoomDropped`,
`SAFE_ROOM_NOT_REALIZED_DETAIL`), `app/vertical_slice/spec.py`
(`ArchitecturalSpec.safe_room_constraint`), `app/vertical_slice/concept_generator.py`
(`generate_concepts`'s stage-1 assertion, `GenerationResult.constraints`),
`app/vertical_slice/validation.py` (C4's `constraint` parameter),
`app/vertical_slice/general_pipeline.py` (`_realize` passes `spec.safe_room_constraint` into
`validate`), `app/demo/service.py` (`generate_demo_design`'s `SafeRoomDropped` catch, `_finish`'s
C4-detail escalation, both to code `SAFE_ROOM_DROPPED`), `app/demo/contract.py` (`ConstraintOut`,
`QualityOut.constraints`, `to_demo_design`'s `constraint` parameter).
`backend/tests/vertical_slice/test_safe_room_constraint.py`,
`backend/tests/test_demo_quality.py::test_safe_room_constraint_survives_to_the_contract`.

**Out of scope, deliberately untouched**: legal applicability (whether the law requires a safe room
for a given brief — `ConstraintSource.COMPLIANCE` stays unused), RC envelope sizing, multi-level
safe-room placement policy, the hub/L-massing guards' existing safe-room aspect term.

## Dedicated circulation metrics and C26 (Issue #36)

Issue #36 (2026-09-18). M3/M4 above measure a plan's circulation SHARE and the hall's own
long/short ratio; nothing measured a corridor's LENGTH, its dead ends, how many turns a person
walks through it, or whether two segments duplicate each other — so nothing could tell an ordinary
long corridor (the spine parti's, by construction — `concept_generator._concept_from`) apart from
an EXTREME one.

**Measurement**: `app/vertical_slice/circulation_metrics.py`, `measure(design) -> CirculationMetrics`
— pure and deterministic, reading a realized `GeometricDesign` (`design_output.py`) alone (rooms'
roles/`rect_m`/`wall_facts`, doors, `open_groups`), never a fixture, a zone_id or a coordinate
literal. Circulation rooms are every room whose roles include `HALL`/`CIRCULATION` (mirrors
`quality_metrics.HALL`). Per plan:

- **area/ratio**: total circulation NET area, and its share of the plan's total room NET area.
- **longest_segment_m/total_length_m/narrowest_width_m**: each circulation room's own long
  (walking) dimension — the longest across the plan, the sum across every circulation room (a
  branching hub sums both arms), and the narrowest short dimension.
- **dead_end_count**: circulation-room ends (the two faces along a room's own long axis) with
  neither a placeable door nor an open-plan join (`WallFacts.construction is Construction.NONE`)
  at that end — space that leads nowhere.
- **turn_count**: direction changes (long/short axis of the center-to-center vector) along the
  realized entrance → farthest-room path, walked over doors/open-plan joins with a deterministic
  BFS (sorted-neighbour order; farthest = greatest hop count).
- **duplicated_segment_count/duplicated_area_m2**: circulation-room pairs that are NOT directly
  joined to each other (so not one branching hub's own arms) but serve an overlapping set of
  non-circulation rooms — two parallel corridors doing the same job.

**C26 "no extreme dedicated circulation"** (`validation.py`, next to C9): fails closed only when
ratio, longest segment or dead-end count exceed the calibrated `EXTREME_RATIO` (0.24),
`EXTREME_LONGEST_SEGMENT_M` (20.0 m) or `EXTREME_DEAD_END_COUNT` (2) constants — turn/duplication
are reported, never gated. Calibrated on a sweep through `generate_demo_design` (varied
footprints/bedroom/wet-room counts, including narrow-deep footprints down to 8 x 28 m — deeper than
the frozen regression corpus's own deepest footprint, 24 m): worst measured ratio 0.180, worst
measured longest segment 17.3 m; both constants sit with real headroom above every measured plan.
C26 runs on a `GeometricDesign` `validate()` assembles ONLY for this measurement
(`design_output.assemble`, `wall_iterations=0` — unused by circulation) since `validate()` itself
runs before the pipeline's own `assemble()` call; the design measured and the design drawn are
built by the identical function, so a check and the drawing can never disagree about the geometry,
only about when it was built.

**The ranking term** (`circulation_prefers(current, current_area_m2, candidate, candidate_area_m2)`,
hub_guard-style): `None` when `candidate`'s circulation earns it the primary over `current` — better
on at least one of ratio/longest-segment/dead-ends and not under `hub_guard.AREA_KEEP_RATIO` (0.85)
of `current`'s area, the identical correctness-then-area-floor pattern `hub_guard.hub_keeps_primary`
and `l_massing_guard.l_earns_representation_slot` already use. Turn count is deliberately never
compared: a turn is how a branching/compact hub reads on this measure (specs/005), and scoring
"fewer turns" as better would bias the ranking term back toward the straight spine the hub parti
exists to move away from.

**Wired into `general_pipeline._guard_demoted_hub`**: when `hub_guard.hub_keeps_primary` says a
demoted hub's bedroom/wet proportions earn it the stay, `circulation_prefers` additionally requires
the hub's own circulation not be beaten by the replacement's — a hub that wins on proportions but
delivers worse circulation than the replacement still loses. This only NARROWS `hub_guard`'s
decision (a hub is never handed the primary FOR its circulation when `hub_guard` already said the
replacement wins on proportions) and costs nothing extra to solve (reuses the same realized
`hub_plan`/`plan` the existing comparison already built). **Corpus impact today: none by
construction** — on this branch every swept brief's `HUB_PRIVATE_WING` candidate is rejected before
solving (`ROOM_ABOVE_MAXIMUM_AREA`/`FOOTPRINT_BELOW_MINIMUM_WIDTH`, the room-area two-level maxima
work, 2026-09-15 — the same pre-existing state `test_hub_guard.py::NARROW_DEEP`'s own `xfail`
documents), so `_guard_demoted_hub`'s `demoted` list is always empty on the corpus and this new
branch is never reached; the wiring is real and tested (fixture-level and a mocked
`_guard_demoted_hub` call), ready for whenever a hub candidate is reachable again.

**Additive to `QualityOut.metrics`**: `QualityMetricsOut` gains `circulation_area_m2`,
`circulation_ratio`, `circulation_longest_segment_m`, `circulation_total_length_m`,
`circulation_narrowest_width_m`, `circulation_dead_end_count`, `circulation_turn_count`,
`circulation_duplicated_segment_count`, `circulation_duplicated_area_m2` — computed in
`contract.to_demo_design` off the same raw `SolvedDesign` M1–M6 and C26 already read, independently
of M3 (`quality_metrics.py` itself is untouched).

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
above. A fourth, from Issue #22: **Entrance Sequence Quality** — fixing a genuine TUNNEL (a long
walk past bedroom doors before the first public room, measured on 342/404 corpus contexts today,
see the Entrance-to-circulation integration section above) is a parti change, not a validation
change; `entrance_sequence_prefers` exists and is tested but is not wired into a live
candidate-selection path yet.

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

The Typed constraints / SAFE_ROOM_DROPPED section documents Issue #35, landed on branch
`agent/35-safe-room-mamad-requirement-preservation` (based on `4aade91`), verified against this
session's own implementation and test runs (`test_safe_room_constraint.py`,
`test_demo_quality.py::test_safe_room_constraint_survives_to_the_contract`, the FAST suite, and the
432-context regression corpus), not independently re-verified beyond that.

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
work, verified against this session's own implementation and test runs, including a second merge of
`origin/main` (bringing in Issue #36's C26 work below) whose conflict resolution kept both sections
intact side by side, and a third merge of `origin/integration/holiday-yom-kippur-2026` (bringing in
Issue #35's SAFE_ROOM constraint work) whose conflict resolution again kept both sections intact.

Branch `agent/35-safe-room-mamad-requirement-preservation` merged `origin/main` at `648292f`
(the Yom Kippur integration rollup, 2026-09-20): resolved textual conflicts in this page,
`contract.py`, `validation.py`, `test_demo_p0.py` and `test_demo_quality.py` by keeping both
sides' additive sections/fields (Issue #35 alongside #19/#20/#32/#37/#69); the fast tier and this
Issue's own targets were re-run against the merged tree.

Branch `agent/36-circulation-efficiency-dedicated-circula`, based on
`origin/integration/holiday-yom-kippur-2026` (merged forward to `main` at `648292f` after the
integration branch's squash-merge, #18/#19/#20/#21/#24/#25/#29–#33/#37/#44/#63/#69 all already
landed): the Dedicated circulation metrics and C26 section above documents Issue #36, verified
against this session's own implementation and test runs (full `vertical_slice`/fast-tier suites
green; the 432-context regression corpus was run separately — see the Issue's own PR for the
outcome), including this merge's own conflict resolution (main's version taken for every
shared/unrelated file; C26 and the circulation fields re-applied on top of C23/C29/wet-core exactly
as they existed pre-merge; combined check count).

`14d94d9` (branch `agent/35-safe-room-mamad-requirement-preservation`, based on `dac6c41`): merged
`origin/main` a second time to pick up `6d18c1f` (Issue #36, circulation metrics); resolved textual
conflicts in this page, `contract.py` and `validation.py` by keeping both sides' additive
sections/fields, then re-ran this Issue's own targets against the merged tree.

`6d18c1f` (branch `agent/22-entrance-to-circulation-integration-the`, based on `origin/main`); the
Entrance-to-circulation integration (C25) section above documents Issue #22, verified against this
session's own implementation, the full 432-context corpus sweep (`docs/ENTRANCE_CIRCULATION_SWEEP.md`)
and test runs (`test_entrance_circulation.py`, targeted AC-8 suites green). Branch merged
`origin/integration/holiday-yom-kippur-2026` (bringing in Issue #34's dimension-consistency work
and Issue #35's SAFE_ROOM typed-constraint work) to resolve a PR conflict: resolved textual
conflicts in this page, `contract.py`, `test_demo_p0.py` and `docs/PROJECT_STATE.md` by keeping
both sides' additive sections/fields, then re-ran this Issue's own targets against the merged tree.
