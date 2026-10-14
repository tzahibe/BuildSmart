# [agent] Stage 0 (1/2): ship the merged public room — the L-shaped LIVING+KITCHEN room becomes a supported feature, measured on the 432-context corpus, default flipped only if the measurement says so

### Goal

Turn spike #107's room merge into a real, owner-visible feature: a public zone that comes out as one L-shaped
room instead of two strips, reported honestly in the quality metrics, measured over the whole frozen corpus,
with the default flipped ON only when the measurement meets its stated rule. This is the first thing the owner
will SEE from the geometry programme.

### Current behavior

`app/vertical_slice/room_merge.py` (spike #107, on this ROOT's base branch): `find_merge_candidate` /
`compute_geometry` / `validate_merged_room` merge an adjacent LIVING+KITCHEN leaf pair into one L-shaped room
behind `LIVING_KITCHEN_MERGE_ENABLED = False`; `RoomOut.shape` ("RECTANGLE" | "L"), the SVG renderer and
`DemoPlan.tsx` already draw it. Measured flag-on over 432 contexts: 191 candidates found, 168 applied (88 %),
23 rejected by their own checks, LOST 0, crashes 0, 168/404 primary signatures changed. What is missing: the
quality metrics still treat the merged room as its two source rectangles (M1's aspect ratio and the strip
signal), there is no committed A/B report in the ROOT's own report directory, and nothing decides the flip.

### Required behavior

1. `quality_metrics.py` and the per-plan quality report read a merged room as ONE room: its own aspect ratio
   (the L's bounding box and its two arms), its own area, and no strip penalty for the arm that would have been
   a strip on its own; `reference_benchmark`'s public-composition section counts it as one contiguous public
   room. Additive, shape-aware, no threshold changed.
2. `docs/reports/rectilinear-realizer/stage0-merge-ab.md`: the 432-context A/B — candidates found/applied/
   rejected with reasons, LOST, crashes, status and refusal-code changes, primary-signature changes, and the
   M1–M6 deltas flag-off vs flag-on, produced by the committed script.
3. The flip rule, stated and applied: default ON only if LOST 0, crashes 0, status and refusal-code changes 0,
   and no M1–M6 corpus statistic regresses beyond its existing tolerance; otherwise the flag stays OFF and the
   report says which condition failed.
4. Three before/after SVG pairs (briefs where a merge applied) committed beside the report, so the change is
   judgeable by eye.

### Acceptance Criteria

- AC-1: a merged room is measured as one room by `quality_metrics` (aspect from the L's own geometry, no strip penalty for its arms) and by the reference benchmark's public-composition check, with unit tests on a merged-room fixture
- AC-2: the committed A/B report carries candidates found/applied/rejected, LOST, crashes, status/refusal changes, signature changes and the M1–M6 deltas over all 432 contexts
- AC-3: the flag's default follows the stated rule — ON only if every condition holds, and the report names the deciding numbers
- AC-4: three before/after SVG pairs are committed and referenced from the report

### Out of scope

The Stage 1 realizer; merging anything but an adjacent LIVING+KITCHEN pair; changing any validator, threshold or
hard limit; merging to main.

### Affected domains

geometry, backend, validator, frontend, qa

### Risk

MEDIUM

### Resource class

HEAVY

### Dependencies

none

### Required locks

geometry-core, validator-core, planner-core (shared), frontend-review (shared)

### Verification plan

- AC-1 -> pytest:backend/tests/vertical_slice/test_living_kitchen_merge_spike.py
- AC-2 -> file:docs/reports/rectilinear-realizer/stage0-merge-ab.md ; grep:docs/reports/rectilinear-realizer/stage0-merge-ab.md:LOST
- AC-3 -> pytest:backend/tests/vertical_slice/test_rectilinear_realizer_flags.py
- AC-3 -> regression:corpus
- AC-4 -> grep:docs/reports/rectilinear-realizer/stage0-merge-ab.md:before/after

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 200

### Expected documentation changes

docs/reports/rectilinear-realizer/stage0-merge-ab.md (new, with the SVG pairs), docs/wiki/architecture/geometry-validation.md (the merged public room, once the flag flips).

### Knowledge check

Consulted: `docs/reports/non-rectangular-geometry-architecture-a-spike.md` (the 432-context measurement and the two bugs it
found), `room_merge.py`, `quality_metrics.py` (M1, the strip signal), `reference_benchmark.py` (public composition),
`contract.py::RoomOut.shape`, `DemoPlan.tsx`, `spikes/failure_log_sweep/living_kitchen_merge_ab.py`.
