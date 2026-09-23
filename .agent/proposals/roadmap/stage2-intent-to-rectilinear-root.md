# [agent] ROOT — Stage 2: the retrieved plan's own structure drives the non-guillotine realizer (donor → RealizationIntent → realized geometry)

### Goal

Owner decision 2026-09-23, after #111's GO-B: **connect the `RealizationIntent` derived from the retrieved
`PlanReference` to the non-guillotine geometry path already proven in Stage 1 (#117)**. The goal is explicitly
NOT more topologies and NOT more templates — topology on the main path is DERIVED from the real plan that was
retrieved, never chosen from a catalogue. Wet rooms and SAFE_ROOM are inside this ROOT's scope, not a later
phase. #79's HUB_LOBBY/BRANCHED compilers stay as reference/tests/fallback candidates only and are not
generalized. Stage 2 succeeds only if donor → intent → realized geometry shows a MEASURED improvement in
preserving adjacency, access, placement, zoning and proportions, with no hidden guillotine fallback and no
validation regression.

### Current behavior

Three parts exist and each works alone; nothing connects them.

- **The intent exists** (#109): `realization_intent.py` carries every structural fact of the donor plan —
  adjacency, access, exterior exposure, relative placement, public/private clusters, wet-core groups, the
  entrance relationship, room proportions, footprint relationships — and `preservation.py` measures, per fact,
  what reached the realized geometry.
- **It is fed to the wrong realizer**: `spikes/architectural_brain/realize.py` compiles a FIXED parti
  (SPINE/TWO_WING) and then measures how much of the donor survived by accident. Measured on the three fixed
  briefs (#109/#110/#111, the pinned baseline for this ROOT): adjacency 2/14 and 2/12, access 4/8 and 3/4,
  relative placement **0/10 and 0/8**, clusters 1/2, wet-core 2/4 and 0/2, proportions 6/7. Of the 136 lost
  facts, **89 (65%) are `GUILLOTINE_IMPOSSIBLE`**, 38 (28%) `DONOR_ROOM_NOT_REALIZED` (the donor room has no
  realized counterpart at all — DINING/SAFE_ROOM/TOILET have no per-instance match and `BEDROOM_COUNT_ADJUST`
  drops rooms silently), 9 (7%) area `BUDGET`. Placement is 0% because nothing searches for a layout that
  honours the donor — `realize.py` says so itself.
- **The realizer that can express it exists** (#117, `integration/rectilinear-realizer`): a non-guillotine
  rectilinear realizer reached 9/10 real corpus layouts across PINWHEEL/L/U/TWO_WING, every realized layout
  passing the UNCHANGED validator chain (23-26 checks), one refusal on a measured `SHORT_SIDE_INFEASIBLE`.
  Its own gap is placement: which room goes where is chosen by the gate script, not derived from a real plan.
  Wet rooms and SAFE_ROOM are excluded there (C17/C29 need a `ResolvedWetRoom` list it does not build).

#106 measured why this matters structurally: **0/199 real reference plans are guillotine-separable** and 95.5%
of real envelopes are irregular polygons — the current solver's output space cannot represent what real plans are.

### Required behavior

Executed through child Issues, all on this ROOT's own integration branch (created from
`integration/rectilinear-realizer` with `integration/poc-architectural-brain` merged into it, so one branch
finally carries both the intent and the realizer):

1. **Placement derived from the donor, not chosen**: the `RealizationIntent` (adjacency, access, relative
   placement, exposure, clusters, wet-core groups, entrance relationship) plus the brief's programme and
   buildable region produce the PLACED layout the Stage 1 realizer consumes. The donor's own structure is the
   objective; no topology catalogue, no template table, no parti list.

   **Start from the donor's own partition and repair it — do not search the layout space blind.** The donor
   plan is already a feasible arrangement of exactly these rooms: normalise its own room polygons onto the
   brief's buildable region, then repair that seed to the brief (per-type target areas, the programme's room
   counts, the site's own exposure and entrance side, rectilinear snapping) and hand the repaired placement to
   the realizer. A blind search over placements is both unnecessary and the likeliest way to lose the very
   facts this ROOT is measured on — the seed preserves adjacency, clusters and relative placement BY
   CONSTRUCTION, and repair only has to keep them.
2. **Wet rooms and SAFE_ROOM are realized on this path**, with `ResolvedWetRoom` reconstructed so C17/C29 run
   like they do on the production path — a plan without bathrooms and a MAMAD is not a result.
3. **Donor-room correspondence is kept**: every room the brief actually contains maps to a realized zone, so a
   fact is never lost merely because the pipeline forgot which donor room it came from
   (`DONOR_ROOM_NOT_REALIZED` -> 0 for rooms in the brief; a room legitimately dropped by adaptation is
   reported as adapted, not as lost).
4. **No hidden guillotine fallback**: when the rectilinear path cannot realize a layout it REFUSES with a
   stated reason and the refusal is what the caller sees. Falling back to the guillotine realizer silently —
   or labelling a guillotine result as a Stage 2 result — is a defect, not a safety net. #79's
   HUB_LOBBY/BRANCHED compilers may be kept as reference/test/fallback CANDIDATES but must not run on the main
   path and must not be generalized.
5. **The measurement is the deliverable**: the same three fixed benchmark briefs, the same
   `preservation.py` fact taxonomy, three columns (current engine / Phase 2 baseline / Stage 2) with the
   per-fact PRESERVED/LOST table and every refusal reason, plus the realized SVGs.
6. Nothing merges to `main` from this ROOT without the owner's explicit approval; with the flags OFF the
   frozen 432-context corpus stays byte-identical.

### Acceptance Criteria

- AC-1: with every Stage 2 flag OFF the frozen 432-context corpus is byte-identical to the base (LOST 0, primary_signature_changes 0, refusal codes unchanged)
- AC-2: on the three fixed briefs, aggregate adjacency preservation is at least 50% and relative placement at least 50%, against the pinned Phase 2 baseline of 14-17% and 0%
- AC-3: access, public/private clusters, wet-core groups and room proportions are each no worse than the pinned Phase 2 baseline, and the committed report states every one of them per brief and per donor
- AC-4: zero lost facts carry the reason GUILLOTINE_IMPOSSIBLE on the Stage 2 path, and zero carry DONOR_ROOM_NOT_REALIZED for a room the brief contains; every remaining loss carries its own stated reason
- AC-5: every realized Stage 2 plan contains its wet rooms and, where the brief asks for one, its SAFE_ROOM, with C17/C29 among the checks that ran and passed
- AC-6: a refusal on the Stage 2 path surfaces as a refusal with its reason — a test proves no guillotine result is ever returned or labelled in its place
- AC-7: no validator, hard limit or production code path is relaxed or bypassed, and every new behaviour sits behind its own flag

### Out of scope

Generalizing #79's HUB_LOBBY/BRANCHED compilers; new topology families or templates of any kind; making the
rectilinear realizer the production default (a later stage, after this measurement); courtyard envelopes with
holes; diagonal or curved walls; merging anything to main.

### Affected domains

geometry, backend, validator, frontend, qa, knowledge, ai

### Risk

HIGH

### Resource class

HEAVY

### Dependencies

none

### Required locks

geometry-core (shared), validator-core (shared), planner-core (shared), knowledge-index (shared), frontend-review (shared)

### Verification plan

- AC-1 -> regression:corpus
- AC-2 -> file:docs/reports/stage2-intent-realization/measurement.md ; grep:docs/reports/stage2-intent-realization/measurement.md:adjacency
- AC-3 -> grep:docs/reports/stage2-intent-realization/measurement.md:room_proportions
- AC-4 -> pytest:backend/tests/architectural_brain/test_stage2_preservation.py
- AC-5 -> pytest:backend/tests/architectural_brain/test_stage2_wet_rooms_and_safe_room.py
- AC-6 -> pytest:backend/tests/architectural_brain/test_stage2_no_guillotine_fallback.py
- AC-7 -> pytest:backend/tests/architectural_brain/test_stage2_flags_default_off.py
- AC-7 -> review:no validator, hard limit or production path is relaxed or bypassed, and every new behaviour is flag-gated and OFF by default

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 0

### Expected documentation changes

docs/reports/stage2-intent-realization/ (measurement.md and the per-brief SVGs), docs/wiki/architecture/geometry-validation.md (the intent-driven realization path once it lands), docs/ROADMAP.md (Stage 2 in the staged programme).

### Knowledge check

Consulted: the owner's Stage 2 decision (2026-09-23 — connect intent to the non-guillotine path, wet rooms and
SAFE_ROOM in scope, no compiler generalization, no hidden guillotine fallback, measured preservation as the bar);
#111's decision-gate report `docs/reports/poc-architectural-brain/phase2.md` (GO-B) and its per-brief
PRESERVED/LOST tables; #109's `realization_intent.py`/`preservation.py` and `preservation.md`; #110's compiler
probes (REFUSED on 3/3 briefs); #117's `rectilinear_realizer.py` and `docs/reports/rectilinear-realizer/stage1-gate.md`
(9/10, unchanged validators); #106's full-corpus re-measurement (0/199 guillotine-separable, 95.5% irregular
envelopes); #107's merged-room A/B; `validation.py` (C17/C29 and the wet-room resolution the Stage 1 gate skipped).
