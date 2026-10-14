# [agent] Stage 2 (B/2): ONE complete house end to end — donor → intent → seed → repair → non-guillotine geometry → validators → preservation report

### Goal

Owner instruction 2026-09-23: the first milestone is **not 20 briefs and not even 3 — it is one complete
house**. Take one representative brief and carry it the whole way: donor → `RealizationIntent` → donor seed
→ repair/adaptation → non-guillotine geometry → validators → preservation report. The single thing being
proved: **a retrieved real plan can seed a new plan, survive adaptation to new requirements, and still
measurably preserve its architectural DNA.** No breadth work starts until the owner has read this one case.

### Current behavior

Measured on the POC's own three briefs (#109/#110/#111): adjacency preservation 2/14 and 2/12, relative
placement 0/10 and 0/8, and of 136 lost donor facts 89 are `GUILLOTINE_IMPOSSIBLE` and 38
`DONOR_ROOM_NOT_REALIZED`. Placement is zero because nothing searches for a layout honouring the donor —
`realize.py` compiles a fixed parti and measures what survived by accident. The non-guillotine realizer
(#117) reaches 9/10 real corpus layouts through the UNCHANGED validator chain, but its placement is chosen
by its gate script and it excludes wet rooms and SAFE_ROOM. Child A of this ROOT defines the shared types
this Issue implements against.

### Required behavior

1. **Seed, do not search.** Build the seed from the donor's OWN partition (Child A's seed-geometry type):
   its cells, its adjacency, its room identities. Adjacency, clusters and relative placement are preserved
   by construction; the work is to keep them through repair.
2. **Repair to the brief**: fit the seed to the buildable region, re-target room areas to the programme,
   apply room-count adaptation, honour the site's entrance side and exposure, and snap to the rectilinear
   grid the realizer needs. **Every repair applied is recorded with the reason it was applied** — the repair
   log is a deliverable, not a debug aid, because it is what tells the owner which step damages the seed.
3. **Realize through the non-guillotine realizer** (#117's `rectilinear_realizer`), never the guillotine
   path. A layout that cannot be realized returns a REFUSAL with its reason; returning a guillotine result,
   or labelling one as a Stage 2 result, is a defect this Issue must make impossible.
4. **A real house, from the first run**: every room the brief asks for, the wet rooms, SAFE_ROOM where
   required, the entrance, adjacency/access, public/private zoning and proportions — validated by the SAME
   chain, with C17 and C29 among the checks that ran.
5. **The evidence set** (committed under `docs/reports/stage2-intent-realization/`): the donor's own SVG;
   the seed BEFORE repair; the geometry AFTER repair; the final SVG; PRESERVED/LOST per fact with adjacency
   % and placement %; access / zoning / wet-core / proportions; every repair with its reason; and the
   refusal with its explicit reason if there was one.
6. **State the decision honestly.** The report ends with the evidence for the owner's decision point: is the
   donor's structure still clearly recognisable after repair, with the validators passing? If it is not, the
   report must say WHICH step destroyed it — envelope fitting, area re-targeting, room-count adaptation,
   entrance/exposure, snapping or a hard constraint — and recommend stopping breadth until that is fixed.
   A partially-preserved honest result is the expected outcome of a first end-to-end run; an overstated one
   is the only failure mode that matters here.

Behind its own flag, additive, production path untouched. Do not run the three benchmark briefs or any
corpus-wide sweep in this Issue — the owner has explicitly ruled that out until this case is read.

### Acceptance Criteria

- AC-1: one representative brief is carried donor → intent → seed → repair → non-guillotine geometry → validators → preservation report, and the run is reproducible by a single documented command
- AC-2: the realized plan contains every room the brief asks for including its wet rooms and, where the brief requires one, SAFE_ROOM, with C17 and C29 among the checks that ran and passed
- AC-3: the committed report holds the whole evidence set — donor SVG, seed before repair, geometry after repair, final SVG, PRESERVED/LOST per fact class with adjacency and placement percentages, access/zoning/wet-core/proportions, every repair with its reason, and any refusal with its reason
- AC-4: zero lost facts carry the reason GUILLOTINE_IMPOSSIBLE, and zero carry DONOR_ROOM_NOT_REALIZED for a room the brief contains
- AC-5: a test proves that when the Stage 2 path cannot realize, the caller receives a refusal carrying its reason and never a result produced by the guillotine path
- AC-6: with the Stage 2 flag OFF the frozen 432-context corpus is byte-identical to the base, and no validator, hard limit or production path is relaxed

### Out of scope

The three benchmark briefs and any broad run (Gate 2 and Gate 3, their own Issues, only after the owner
reads this case); generalizing #79's HUB_LOBBY/BRANCHED compilers or adding topologies; switching any flag on
by default; merging to main.

### Affected domains

backend, geometry, validator, qa, knowledge

### Risk

HIGH

### Resource class

HEAVY

### Dependencies

#133

### Required locks

geometry-core (shared), validator-core (shared), planner-core (shared), knowledge-index (shared)

### Verification plan

- AC-1 -> pytest:backend/tests/architectural_brain/test_stage2_end_to_end.py
- AC-2 -> pytest:backend/tests/architectural_brain/test_stage2_wet_rooms_and_safe_room.py
- AC-3 -> file:docs/reports/stage2-intent-realization/milestone-1.md
- AC-3 -> grep:docs/reports/stage2-intent-realization/milestone-1.md:placement
- AC-4 -> pytest:backend/tests/architectural_brain/test_stage2_preservation.py
- AC-5 -> pytest:backend/tests/architectural_brain/test_stage2_no_guillotine_fallback.py
- AC-6 -> regression:corpus
- AC-6 -> pytest:backend/tests/architectural_brain/test_stage2_flags_default_off.py

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 0

### Expected documentation changes

docs/reports/stage2-intent-realization/milestone-1.md and its SVGs (new), docs/stage2/CONTRACT.md (only if implementing reveals a gap in it), docs/wiki/architecture/geometry-validation.md (once Stage 2 lands).

### Knowledge check

Consulted: ROOT #127 and the owner's execution order and decision point (2026-09-23); Child A's shared
contract; #109's `realization_intent.py`/`preservation.py` and the measured preservation baseline; #117's
`rectilinear_realizer.py` and `docs/reports/rectilinear-realizer/stage1-gate.md` (9/10 realized, unchanged
validators, and the placement gap this Issue closes); #111's decision-gate report (GO-B) and its loss-reason
tally; `validation.py` C17/C29 and the wet-room resolution the Stage 1 gate skipped; `adaptation.py` (the
room-count and area re-targeting whose effect on the seed this Issue must record).
