# Interior Layout

Status: IMPLEMENTED_MERGED

## Current behavior

Before this Issue, Stage 6 "furniture" was a bounding-box INSCRIBE TEST only
(`furniture.py::check_furniture_feasibility`, over the frozen Geometry Core's own
`min_furniture_envelope_m`, C9) — no placement, no objects on the drawing. Plans read as room
outlines plus doors/windows, never as architectural interiors.

`app/vertical_slice/interior_layout.py` (Issue #39) places typed, per-role semantic objects —
`LayoutObject(kind, room_id, rect_m, rotation, clearance_rect_m)` — off the FINAL realized design,
deterministically:

| Role | Items placed, in order |
|---|---|
| BEDROOM | BED, WARDROBE |
| MASTER_BEDROOM | BED, WARDROBE (larger than BEDROOM's own) |
| LIVING | SOFA, COFFEE_TABLE, FOCAL_WALL |
| DINING | DINING_TABLE (freestanding, centred — never wall-anchored) |
| KITCHEN | REFRIGERATOR, COUNTER_RUN, SINK, COUNTER_RUN, COOKTOP (one adjacent run along one
  wall), plus ISLAND only when the room is deep enough to leave both the counter's own working
  clearance and the island's own clearance free at once |
| BATHROOM | TOILET, SINK, SHOWER |
| TOILET (WC-only) | TOILET, SINK — no bathing fixture, matching the room's own domain meaning |

Every other role (FAMILY_ROOM, STUDY, DRESSING_ROOM, a SAFE_ROOM-only zone, HALL/CIRCULATION,
FLEX, ...) gets no layout objects — additive, out of scope, never a regression.

**Placement policy**: each item is offered a wall in priority order — the longest usable run first
(deterministic N/E/S/W tie-break), never a wall carrying a door (matched by orientation+coordinate
against every interior AND entrance door, whichever side of the door this room is on — not just the
side the leaf swings into), and — only for an item that would BLOCK a window (a wardrobe) — never a
wall carrying a placeable window either. The item is placed FLUSH against the chosen wall; its
`clearance_rect_m` extends from the wall into the room by the item's own required clearance depth,
clipped to the room's own NET rectangle — "never overlaps a wall" holds by construction, since the
net rectangle already excludes every wall's own thickness. An item is reported `unplaceable` (a
reason string, in `RoomLayout.unplaceable` — never raised, never forced) when no wall/position
clears the room, every already-placed item's own clearance in this room, and every swing envelope
of a door that opens INTO this room.

**One documented exception**: LIVING's `COFFEE_TABLE` is placed INSIDE the `SOFA`'s own clearance
rectangle — that zone IS the seating/conversation area a coffee table belongs in. Physical
FOOTPRINTS (`rect_m`) never overlap regardless; only the two CLEARANCE rectangles are allowed to,
and only for this one pair.

**Item sizes are PARAMETER · UNVERIFIED placeholders** — a single conservative footprint plus
clearance per item, not a sourced furniture catalogue, the same disclosure discipline as
`geometry_core.model.MIN_FURNITURE_ENVELOPE_M`/`windows.py`'s glazing fractions. The kitchen run's
minimum total width (2.4 m, fixed segments plus two minimum counter runs) matches
`MIN_FURNITURE_ENVELOPE_M[KITCHEN]`'s own (2.4, 1.8) screen exactly by design, so a kitchen that
already passes C9 always has enough wall length for this run too.

**No "island requested" input exists** in this engine's domain model (`ProgramSpec`/`ZoneSpec`
carry no such flag) — an island is added only when the room is genuinely deep enough, never because
someone asked for one. "Only when requested/appropriate" (the Issue's own wording) therefore reduces
to appropriateness alone here.

**The contract**: `app.demo.contract.DemoDesign.layout: list[LayoutObjectOut]` — one entry per
PLACED object (never one per requested item; an unplaceable item is simply absent), computed in
`to_demo_design` for every delivered plan (primary, every alternative, every level of a building).
`LayoutObjectOut` carries the object's footprint (`x`/`y`/`width_m`/`depth_m`), `rotation_deg`, and
its clearance rectangle (`clearance_x`/`clearance_y`/`clearance_width_m`/`clearance_depth_m`) —
`clearance` always contains the footprint. The frontend (`InteriorLayout.tsx`, used by
`DemoPlan.tsx`) draws these AS-IS, one rectangle per object labelled with its own `kind` — no
decorative invention on either side, the same boundary `DoorSymbol.tsx` already holds for doors.

**Placement failures are data, not refusals** (Issue #39 requirement 3): `RoomLayout.unplaceable`
is an internal diagnostic (proven directly by `test_interior_layout.py`, not part of the wire
contract) — a plan with every bedroom's wardrobe unplaceable still delivers normally; nothing in
`interior_layout.py` can fail a validation check or change a plan's status/primary signature.

## Authoritative implementation

- `app/vertical_slice/interior_layout.py` (`LayoutObject`, `UnplaceableItem`, `RoomLayout`,
  `layout_for_room`, `compute_layout`) — reads only `design_output.GeometricDesign` (rooms/doors/
  windows, already in metres), the same decoupling `circulation_metrics.py` and the renderer itself
  rely on. Never touches `geometry_core` (frozen) beyond two read-only constants
  (`WallType`/`WALL_THICKNESS_M`) needed to recover a room's net-rect ORIGIN — `RoomOut` only
  carried net WIDTH/HEIGHT before this Issue, never the origin.
- `app.demo.contract.LayoutObjectOut`, `_layout_out`, `DemoDesign.layout` — wired into
  `to_demo_design`, called once per delivered plan (never during candidate search/generation, so it
  costs nothing there — the same reasoning `validation.py`'s C26 comment gives for keeping
  `assemble()` itself cheap; `interior_layout.py` is deliberately NOT called from `assemble()`).
- `frontend/src/design/demoDesign.ts` (`DemoLayoutObject`, `DemoDesign.layout`),
  `frontend/src/components/plan/InteriorLayout.tsx`, wired into `frontend/src/design/DemoPlan.tsx`
  (drawn under the doors/windows layer so a door's swing arc always stays legible over any
  furniture near it), `frontend/src/design/DemoPlan.css` (`.demo-layout-object*`).
- Tests: `backend/tests/vertical_slice/test_interior_layout.py` (AC-1: every role placer on a
  hand-built generous fixture and a deliberately too-small one; AC-2: walls/door-swing/each-other
  non-overlap, checked directly on the geometry), `backend/tests/test_demo_quality.py::
  test_layout_objects_present_for_planned_designs` (AC-3, the real service entry point),
  `frontend/src/components/plan/InteriorLayout.test.tsx` (AC-3, the frontend draws the contract
  as-is), `frontend/src/components/plan/__snapshots__/PlanCanvas.test.tsx.snap` (the new, empty-by-
  default `<g class="demo-layout">` group in the drawn SVG).

## Current constraints/invariants

- Additive only: `interior_layout.py` never touches `Fixture`/rects/walls/doors/windows/validation/
  ranking — it reads the FINAL assembled design and adds a brand-new field. LOST/status/primary-
  signature changes are impossible by construction, not merely unmeasured.
- Never raises: every placement failure is `RoomLayout.unplaceable` data; `compute_layout` is pure
  and side-effect-free.
- Door-vs-wet-fixture swing avoidance (C28, `door_clearance.py`) still uses ITS OWN conservative
  placeholder fixture footprint (`WET_FIXTURE_FOOTPRINT_M`) independently of this module's real
  bathroom/WC placements — the two were not reconciled by this Issue (see Known follow-ups).

## Furnishability / usability validation (Issue #40)

`app/vertical_slice/furnishability.py` reads the layout objects this module already placed —
never re-placing anything itself — and computes a `Usability` record per room: whether every
REQUIRED object for the role got placed at all (`REQUIRED_ITEMS`, a deliberately narrow subset —
BED for BEDROOM/MASTER_BEDROOM, not WARDROBE; SOFA for LIVING; DINING_TABLE; the kitchen's
REFRIGERATOR/SINK/COOKTOP; TOILET/SINK for BATHROOM/TOILET), whether the door has a clear straight
line to each placed object without crossing another object's footprint, whether a placed object
blocks a window, and a diagnostic "usable wall length" figure — rolled up into one tier: GOOD /
ACCEPTABLE / POOR / UNUSABLE.

**`validation.check_furnishability` (C30) exists, is fully tested, and is NOT called from
`validate()`** — the one deliberate deviation from the Issue's own "fails closed via C30" wording,
made after measuring rather than assuming: wiring it into the same per-candidate `validate()` C26/
C29 already live in (at search time), or as a final-only gate mirroring C27's own precedent, was
each tried and MEASURED to fail closed on real, otherwise-fully-valid plans this codebase already
accepts — ordinary 2BR/3BR end-to-end briefs among them, not just synthetic edge cases (29 new
failures across the backend test suite with either wiring, even with `REQUIRED_ITEMS` narrowed to
BED alone). The root cause is `interior_layout.py`'s own placement algorithm: a single independent
pass per item, per wall, with no packing two items onto the same wall and no rotation search — a
real, already-documented gap (this page's own "Known follow-ups" below), and closing it is Issue
9's placement scope, explicitly out of bounds here. `check_furnishability` is defined, tested
(`test_furnishability.py`) and ready for a caller once that gap closes — the same "available, not
wired" precedent `wet_core.candidate_wet_core_key`/`better_candidate` already sets in this
codebase. `usability_key`/`better_candidate` (`furnishability.py`) are the equivalent, similarly
unwired, ranking-preference functions for POOR/UNUSABLE counts.

POOR (required objects placed, but no clear access path from the door, or one blocks a window) is
disclosure-only, additive, and safe regardless: `app.demo.contract.QualityOut.usability` (one
`UsabilityOut` per room, on every delivered plan) and one aggregated Hebrew notice on
`QualityOut.notices` when a plan has a POOR room — never a gate, never able to change which
candidate is chosen.

## Out of scope (deliberately untouched)

Public-zone composition (Issue 11), decorative furniture, DXF symbols, a real furniture/fixture
size catalogue (every item size here is a placeholder, see above), improving `interior_layout.py`'s
own placement algorithm (Issue 9's scope — see the furnishability section above for why this
matters to C30 specifically).

## Known follow-ups

**PROPOSED, not scheduled:**

- Reconcile C28's placeholder wet-fixture footprint (`door_clearance.WET_FIXTURE_FOOTPRINT_M`) with
  this module's REAL bathroom/WC placements, so the door-clearance check and the drawn fixture agree
  with each other instead of each using its own conservative approximation.
- Pack multiple items onto the SAME wall (side by side) when one is centred and leaves usable
  leftover width — today each item picks its OWN best wall independently, which under-uses a wide,
  shallow room (a "strip" bedroom, door at one end and window at the other, can legitimately report
  a wardrobe unplaceable even though the wall has unused width beside the bed) rather than a bug;
  see the module's own placement-policy docstring. **This is now also the blocker for wiring C30
  (Issue #40) into any live acceptance gate — see that section above.**
- A real furniture/fixture size catalogue, once one exists for this codebase (today's item sizes are
  PARAMETER · UNVERIFIED, same discipline as `MIN_FURNITURE_ENVELOPE_M`).

## Evidence/history

Issue #39 contract and acceptance criteria; `docs/architecture_reference/quality_rubric.md` section
N ("Fixture & Clearance Awareness") — this Issue delivers that section's first deterministic signal.
Issue #40 (furnishability/usability, `furnishability.py`) extends the same section with the tiered
usability signal, and documents (`validation.check_furnishability`'s own docstring) the measured
reason C30 stays defined-but-unwired.

## Last verified against git

Branch `agent/40-furnishability-usability-validation-room`, based on `origin/main` at `42f558b`:
verified against this session's own implementation and test runs (`test_furnishability.py`,
`test_demo_p0.py`, `test_baseline_and_decoupling.py` — 138 tests, 0 failures — and a full,
single-process replay of the 432-context regression corpus via `furnishability_corpus_check.py`:
LOST 0, status_changed 0, tier distribution GOOD 67.6% / ACCEPTABLE 0.0% / POOR 29.4% / UNUSABLE
3.0% over 3822 rooms).
