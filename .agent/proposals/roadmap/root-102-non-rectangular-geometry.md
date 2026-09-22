# [agent] ROOT — Non-rectangular geometry: close the guillotine-partition gap for public rooms, and prove/kill non-guillotine rectangular layout

### Goal

Follow up on Issue #102's investigation (`docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md`): give the
owner a real, measured answer on the two most promising candidate architectures for real-plan shapes
— **A** (slicing tree + room merging, the cheapest step that produces real L-shaped public rooms) and
**B** (non-guillotine rectangular layout, the architecture that actually closes the measured 0/19
guillotine-separability gap) — via two bounded 2-week spikes, before any commitment to full
implementation. Executed through child Issues: a full-corpus remeasurement, the A spike, the B
spike. Architecture C (polygonal layout) is deliberately NOT a child here — Issue #102 recorded it
as a longer-horizon option, not scheduled, given its effort/risk profile and its dependency on
shape-adaptation work no POC branch has yet solved.

### Current behavior

`app/vertical_slice/geometry_core/` tiles every rectangular wing with a binary slicing tree
(`Rect`/`Leaf`/`Split`/`Cut`, `model.py:50-81,373-400`); every `ZoneSpec` becomes an axis-aligned
rectangle; almost every downstream module (doors, windows, validators C1-C29, M1-M6, hub/L-massing/
wet-core guards, the demo contract, both renderers, the corpus regression signature) is typed
against that rectangle. Issue #102's measurement (20-plan real-ResPlan fixture,
`backend/spikes/geometry_shapes/measure_real_plan_shapes.py`): 41.9% of real rooms are rectangles,
19.6% simple L-shapes; **0/19 real plans' room layouts are guillotine-separable**. No architecture
has been chosen; nothing beyond the investigation and its script exists yet.

### Required behavior

1. Child 1 re-runs Issue #102's measurement script against the POC's full 199-plan corpus (once an
   integration branch carries both this ROOT's work and `integration/poc-architectural-brain`) to
   firm up the investigation's directional numbers — particularly the envelope-shape share, flagged
   in the report as likely undercounting near-rectangular envelopes on the 19-plan sample.
2. Child 2 runs Architecture A's 2-week spike exactly as scoped in the investigation report §4.A:
   ONE merge case only (LIVING+KITCHEN, adjacent leaves, `CLOSED_ADJACENT` composition), flagged
   off by default, through the contract + renderer layer only, measured against the 432-context
   regression corpus (LOST=0 required) and M1 (kitchen/dining aspect) before/after.
3. Child 3 runs Architecture B's 2-week spike exactly as scoped in the investigation report §4.B:
   ONE hand-encoded non-guillotine rectangular layout (from a reference archetype already flagged
   non-rectangular envelope) proving or disproving whether the existing C1/C3/C9/C20/C27/M1-M6/
   renderer/frontend pipeline truly accepts a non-tree `dict[str, Rect]` unchanged.
4. Each spike reports its own kill/proceed criterion (stated in the investigation report) back to
   this ROOT; no further Architecture A/B implementation work is authorized by this ROOT alone —
   the owner decides which (if either) proceeds based on the spike results.

### Acceptance Criteria

- AC-1: child 1's remeasurement report is committed with the full-corpus shares, explicitly comparing them against Issue #102's 19-plan sample
- AC-2: child 2's spike report states whether the merge candidate validates on the 432-context corpus at LOST=0 and whether it moved M1's kitchen/dining aspect toward the reference gap
- AC-3: child 3's spike report states, for the hand-encoded layout, exactly which "reused unchanged" modules from Issue #102's inventory in fact required a change, and which did not
- AC-4: this ROOT's own closing summary compares all three results against the investigation report's recommendation and states explicitly whether it still holds

### Out of scope

Architecture C (polygonal layout) in any form; any product-facing rollout of A or B (both children
are spikes/flagged-off only); Multi-Level/Massing-selection integration; anything the Issue #102
report itself marks out of scope (fine-tuning, product code beyond the two scoped spikes).

### Affected domains

geometry, backend, validator, knowledge, qa

### Risk

MEDIUM

### Resource class

MEDIUM

### Dependencies

none

### Required locks

geometry-core (shared), validator-core (shared), knowledge-index (shared)

### Verification plan

- AC-1 -> regression:corpus
- AC-2 -> regression:corpus
- AC-3 -> ARTIFACT:file:docs/reports/root-102-non-rectangular-geometry-closing-summary.md
- AC-4 -> ARTIFACT:file:docs/reports/root-102-non-rectangular-geometry-closing-summary.md

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: allowed

### Expected documentation changes

docs/reports/root-102-non-rectangular-geometry-closing-summary.md (new, closing summary),
docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md (cross-referenced, not rewritten),
docs/PROJECT_STATE.md (this ROOT's status once scheduled).

### Knowledge check

Consulted: `docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md` (Issue #102, this ROOT's own source),
`docs/wiki/architecture/geometry-validation.md`, `docs/wiki/features/concept-engine-v2.md`,
`docs/wiki/features/l-massing.md`. Depends on nothing merged yet; not queued until the owner
reviews Issue #102's investigation.
