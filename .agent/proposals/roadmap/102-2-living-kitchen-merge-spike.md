# [agent] Non-rectangular geometry ROOT (2/3): 2-week spike — merge an adjacent LIVING+KITCHEN leaf pair into one L-shaped public room

### Goal

Prove or kill Architecture A (slicing tree + room merging) from Issue #102's investigation on the
single narrowest, highest-value case: let one zone own two adjacent slicing-tree leaves (LIVING +
KITCHEN, when they are adjacent leaves and the concept's `public_composition` would read
`CLOSED_ADJACENT`) by opening their shared seam — generalising the existing corridor-opening
precedent (`app/demo/contract.py`, hall↔LDK) — without touching the solver. Flagged off by default;
this is a spike, not a product rollout.

### Current behavior

`app/vertical_slice/geometry_core/engine.py` tiles every zone into its own separate rectangle; a
LIVING zone and an adjacent KITCHEN zone are always two separate rooms with a wall (or an
open-plan connection at the SAME leaf-boundary the tree already drew) between them — there is no
path today where two leaves become one room with an L-shaped OUTER boundary. `app/demo/contract.py`
already opens a wall at segment level for the hall↔LDK corridor case (a precedent for a
contract-layer post-process that does not touch the engine); nothing generalises it to "two rooms
become one non-rectangular room."

### Required behavior

1. In `app/demo/contract.py` (or a new, clearly-scoped sibling module — implementer's choice,
   documented), detect the ONE case this spike targets: a LIVING leaf and a KITCHEN leaf that are
   adjacent in the realized `dict[str, Rect]` AND whose concept would read `public_composition:
   CLOSED_ADJACENT` (mirroring the POC's own `patterns.py::_public_composition` rule, ported or
   reimplemented — this spike does not depend on the POC branch). When both hold, and ONLY then,
   merge the two into one room whose outer boundary is the union of their two rectangles (an L or
   a rectangle if they happen to align flush) and open the shared wall.
2. Gate this behind a flag (matching the `LAUNDRY_ROOM_ENABLED`/`CONCEPT_ENGINE_V2_ENABLED` pattern,
   default `False`).
3. Extend exactly the checks Issue #102's report names as needed for this merge (C1, C3, C6, C7,
   C8, C14, C16, C19, C20, C26 — NEEDS POLYGON VARIANT bucket; C2, C9, C27 — MUST BE REDESIGNED
   bucket, scoped to the merged room ONLY, every other room's checks unchanged) enough to validate
   the merged room; every other room in a plan keeps its existing rectangle-only checks unchanged.
4. Draw the merged room as an SVG polygon (backend `renderer.py` and/or the frontend
   `DemoPlan.tsx`) alongside every other room's existing rectangle — additive, not a renderer
   rewrite.
5. Measure: the 432-context regression corpus with the flag ON (LOST=0 required; report every
   primary-signature change, all of which must be attributable to a merge winning primary
   selection); M1's kitchen/dining aspect median before/after on the corpus subset where the merge
   fires.

### Acceptance Criteria

- AC-1: with the flag ON, a fixture with an adjacent LIVING/KITCHEN CLOSED_ADJACENT pair produces one merged L-shaped room that passes C1/C3/C6/C7/C8/C9/C14/C16/C19/C20/C26/C27 (redesigned/variant forms) and renders as a polygon
- AC-2: with the flag OFF, the 432-context corpus is byte-identical to today's baseline (LOST=0, GAINED=0, zero signature changes) — the flag-off path is provably untouched
- AC-3: with the flag ON, the 432-context corpus shows LOST=0; every primary-signature change is attributable to a merge candidate winning primary selection (named per-context in the spike report)
- AC-4: the spike report states M1's kitchen/dining aspect median before/after on the subset where a merge fired, and explicitly answers the investigation report's own kill criterion (whether the merged room's C9 furniture inscription validates across a representative footprint sweep, and whether the aspect move is worth generalising to more room-pairs)

### Out of scope

Any room-pair merge other than LIVING+KITCHEN; turning the flag on by default; any change to the
solver (`geometry_core/`) itself; Architecture B or C; the corpus signature's own format (a merge
collapsing two signature rows to one is the only change permitted).

### Affected domains

geometry, backend, validator, frontend, qa

### Risk

MEDIUM

### Resource class

HEAVY

### Dependencies

none

### Required locks

geometry-core (shared), validator-core (exclusive), frontend-review (shared)

### Verification plan

- AC-1 -> TEST:pytest:backend/tests/vertical_slice/test_living_kitchen_merge_spike.py::test_merged_room_passes_validation_and_renders_as_polygon
- AC-2 -> REGRESSION:regression:corpus
- AC-3 -> REGRESSION:regression:corpus
- AC-4 -> ARTIFACT:file:docs/reports/non-rectangular-geometry-architecture-a-spike.md

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: allowed

### Expected documentation changes

docs/reports/non-rectangular-geometry-architecture-a-spike.md (new),
docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md (cross-referenced, not rewritten).

### Knowledge check

Consulted: `docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md` §2, §4.A (Issue #102),
`docs/wiki/architecture/geometry-validation.md` ("Corridor opening is a contract post-process"),
`docs/wiki/features/l-massing.md` (the `l_massing_guard`-style eligibility-gate precedent for
which candidates earn a representation slot), `docs/reports/poc-architectural-brain/dataset.md`
(the `CLOSED_ADJACENT` rate, 8/199, this spike's own target case size). Depends on the ROOT
(`root-102-non-rectangular-geometry.md`) being queued.
