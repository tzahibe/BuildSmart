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

Executed through child Issues on this ROOT's own integration branch (created from
`integration/rectilinear-realizer` with the POC's `RealizationIntent` work on it, so one branch finally
carries both the intent and the realizer). The owner set the execution ORDER explicitly (2026-09-23,
under a subscription quota limit — "do not burn quota on a broad run before there is one deep, complete
proof"); depth first, breadth only after each gate passes.

**Step 0 — one shared, explicit contract between every child, BEFORE any full implementation.** Written
once and used by all of them, never re-invented per child:
   - how a DONOR ROOM is identified (its stable id, and how that id survives retrieval, synthesis and adaptation);
   - how SEED GEOMETRY is represented (the donor's own partition carried as data, before any repair);
   - exactly what goes into `RealizationIntent` (which facts, in which units, in whose coordinate frame);
   - exactly what the non-guillotine realizer RECEIVES (the placed-layout structure, its invariants, its refusal contract);
   - how WET ROOMS and SAFE_ROOM are represented end to end (including what C17/C29 need to run);
   - how ROOM IDENTITY is preserved along the whole chain — donor room -> intent fact -> seed cell -> repaired cell -> realized zone.

**Milestone 1 (the first and only milestone until it passes) — ONE COMPLETE HOUSE, end to end.** One
representative brief, carried the whole way: donor -> `RealizationIntent` -> donor seed -> repair/adaptation
-> non-guillotine geometry -> validators -> preservation report. From the first day it must contain EVERY
room, the wet rooms, SAFE_ROOM where the brief asks for one, the entrance, adjacency/access, public/private
zoning and proportions, checked by the SAME validators including C17 and C29. Not three briefs. Not twenty.

   Its deliverable is the evidence set for that single case: the donor's own SVG; the seed BEFORE repair;
   the geometry AFTER repair; the final SVG; PRESERVED/LOST per fact; adjacency %; placement %;
   access / zoning / wet-core / proportions; EVERY repair that was applied and why; and whether there was a
   refusal — with its explicit reason.

**The first decision point (the owner's, on that evidence):**
   - the donor's structure is still clearly recognisable after repair AND the validators pass -> continue
     immediately to the three fixed benchmark briefs (Gate 2);
   - the repair distorts the plan until the donor structure has all but disappeared -> STOP, run no breadth,
     and first isolate WHICH step destroys the seed: envelope fitting, area re-targeting, room-count
     adaptation, entrance/exposure, rectilinear snapping, or a hard constraint.

**Gate 2 (only after Milestone 1 passes)**: the three fixed benchmark briefs with adjacency >= 50%,
placement >= 50%, zero `GUILLOTINE_IMPOSSIBLE`, zero hidden fallback, no validator relaxation.

**Gate 3 (only after Gate 2 passes)**: ~20 briefs with donor/result side by side, to test generalisation
and diversity.

**Two rules that hold at every step:**
   - **No guillotine fallback, ever.** When Stage 2 cannot realize, it returns a REFUSAL with its reason.
     Returning a result from the old path — or labelling one as a Stage 2 result — is a defect.
   - **Start from the donor's own partition and repair it; never search the layout space blind.** The donor
     plan is already a feasible arrangement of exactly these rooms, so the seed preserves adjacency,
     clusters and relative placement BY CONSTRUCTION and repair only has to keep them.

#79's HUB_LOBBY/BRANCHED compilers stay out of the main path: no generalisation, no new topologies. The
single thing this ROOT exists to prove: **a retrieved real plan can seed a new plan, survive adaptation to
new requirements, and still measurably preserve its architectural DNA.**

Nothing merges to `main` from this ROOT without the owner's explicit approval; with the flags OFF the frozen
432-context corpus stays byte-identical.

Gate 2 and Gate 3 are executed by their own child Issues, created only after the owner reads Milestone 1's
evidence and decides to continue — deliberately NOT acceptance criteria of this ROOT, so that no breadth work
can start before the deep proof exists.

### Acceptance Criteria

- AC-1: with every Stage 2 flag OFF the frozen 432-context corpus is byte-identical to the base (LOST 0, primary_signature_changes 0, refusal codes unchanged)
- AC-2: the shared contract (donor-room identity, seed geometry, RealizationIntent content, the realizer's input and refusal contract, wet-room/SAFE_ROOM representation, room-identity propagation) is committed and every child uses those types — no second representation of the same fact anywhere
- AC-3: ONE representative brief is carried donor -> intent -> seed -> repair -> non-guillotine geometry -> validators -> preservation report, and its evidence set is committed: donor SVG, seed before repair, geometry after repair, final SVG, PRESERVED/LOST per fact with adjacency and placement percentages, access/zoning/wet-core/proportions, every repair applied with its reason, and any refusal with its explicit reason
- AC-4: that plan contains every room the brief asks for including its wet rooms and, where required, SAFE_ROOM, with C17 and C29 among the checks that ran and passed
- AC-5: zero lost facts carry the reason GUILLOTINE_IMPOSSIBLE on the Stage 2 path, and zero carry DONOR_ROOM_NOT_REALIZED for a room the brief contains
- AC-6: a Stage 2 failure returns a refusal with its reason — a test proves no guillotine-path result is ever returned or labelled as a Stage 2 result
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
- AC-2 -> pytest:backend/tests/architectural_brain/test_stage2_contract.py
- AC-2 -> file:docs/stage2/CONTRACT.md
- AC-3 -> file:docs/reports/stage2-intent-realization/milestone-1.md
- AC-3 -> grep:docs/reports/stage2-intent-realization/milestone-1.md:placement
- AC-4 -> pytest:backend/tests/architectural_brain/test_stage2_wet_rooms_and_safe_room.py
- AC-5 -> pytest:backend/tests/architectural_brain/test_stage2_preservation.py
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
