# Wall Semantic Model

Status: IMPLEMENTED_MERGED

## Current behavior

A realized plan's walls carry a single semantic class — `EXTERIOR`, `INTERIOR`, `WET_SERVICE` or
`PROTECTED` — as the base for compliance, fixtures and technical drawing output, WITHOUT claiming
structural engineering the system does not perform (Issue #45). Before this, a wall existed only
as per-room-side facts (`WallMap`, `RoomOut.walls`/`wall_facts`) — no single list a door, window or
fixture could reference by id, and no class distinguishing a wet room's own wall or a safe room's
from an ordinary partition.

`app/vertical_slice/walls.py`'s `derive_walls` builds one `Wall` per physical segment of the
REALIZED geometry (never a second, independently-solved source of truth): `id`, `wall_class`,
`thickness_m` (the solver's own `WALL_THICKNESS_M`, not a new constant), `segment`, `zones` (every
room the segment borders), `hosts` (the door/window ids realized on it), and `structural_candidate`
(always `False` — a placeholder for a future structural engine, not computed here). See the
Geometry / Validation page's own "Wall semantic model and C33" section for the exact classification
precedence and why EXTERIOR wins over PROTECTED for a safe room's own outward wall.

**C33** (`validation.py`) fails closed on any real (placeable, real-width) door or window with no
hosting wall, and on any safe-room wall not itself on the envelope that is classified anything
other than PROTECTED.

**The contract and renderer**: `DemoDesign.walls` (`WallSegment`) gains `id`/`wall_class`/
`thickness_m`; `DoorOut`/`WindowOut` gain `wall_id`, resolved against the final, drawing-adjusted
wall list. The frontend's wall drawing moved into its own `components/plan/Walls.tsx`, which draws
colour/width from `wall_class`/`thickness_m` when present, falling back to the legacy
`construction`/`boundary_context` styling for anything built before this Issue. `RoomOut.walls`
(the per-room side dict) is unchanged, kept for compatibility.

## Authoritative implementation

- `app/vertical_slice/walls.py` (`Wall`, `WallClass`, `classify`, `derive_walls`, `door_id`,
  `window_id`).
- `app/vertical_slice/validation.py`'s C33.
- `app/demo/contract.py`'s `WallSegment`/`DoorOut`/`WindowOut` extensions, `_wall_segments`'s
  inline `wall_class`/`thickness_m` computation, `_wall_id_for_door`/`_wall_id_for_window`.
- `frontend/src/components/plan/Walls.tsx`, wired into `frontend/src/design/DemoPlan.tsx`.
- `backend/tests/vertical_slice/test_walls.py`,
  `backend/tests/test_demo_quality.py::test_every_door_and_window_hosts_on_a_wall`,
  `frontend/src/components/plan/Walls.test.tsx`.

## Current constraints/invariants

- `WallClass` is a single-value collapse of `WallFacts`'s orthogonal `boundary_context`/
  `construction` — EXTERIOR always wins over PROTECTED for a wall on the building envelope,
  matching the reason `WallFacts` was made orthogonal in the first place (Issue #19).
- `hosts` never carries fixture ids: no fixture-placement engine exists in this codebase yet
  (`furniture.py` is a bounding-box feasibility screen only, with no fixture position).
- `structural_candidate` is always `False` here — never computed, inferred or defaulted from
  geometry by this module. Reading `False` as "verified non-structural" is a misuse of the field.
- Out of scope, deliberately untouched: structural engineering of any kind, DXF output, compliance
  rules keyed on wall class.

## Known follow-ups

**PROPOSED, not scheduled.** A fixture-placement engine, once one exists, would populate `hosts`
with real fixture ids and could set `structural_candidate` from an actual structural pass — neither
is designed or scheduled here.

## Evidence/history

See the Geometry / Validation Wiki page's "Wall semantic model and C33 (Issue #45)" section for the
full classification rationale and the corpus/test evidence.

## Last verified against git

`aadba01` (branch `agent/45-wall-semantic-model-exterior-interior-we`, based on `origin/main`):
this page documents Issue #45's own implementation, verified against this session's own test runs.
