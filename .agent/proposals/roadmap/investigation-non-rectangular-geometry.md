# [agent] Investigation — non-rectangular geometry: what it takes for BuildSmart to realize real-plan shapes (L-shaped rooms, non-guillotine partitions, free envelopes), what is reusable, the cost, and how it fits the Concept Engine

### Goal

The owner looked at the POC Architectural Brain demo (2026-09-22) and saw rectangles inside rectangles: every plan
BuildSmart produces is a slicing-tree (guillotine) partition of rectangular wings into rectangular rooms, so the
"architectural brain" can change organisation (hub / branched / wings / zoning) but never the shape language of the
plans in the real corpus (ResPlan: L-shaped living rooms, non-guillotine layouts, free envelopes). Owner decision
(2026-09-22, "תבצע על פי המלצתך"): a short investigation — NO implementation — that gives the owner the numbers to
decide the next big step: what it takes to realize non-rectangular plans, what of the engine / validators / metrics /
renderer survives, three candidate architectures with effort and risk, and how each plugs into Concept Engine v2's
`ConceptSpec → realization` seam. Deliverable: `docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md` + a deterministic
measurement script + proposed ROOT/children (proposal only).

### Current behavior

`geometry_core` (`model.py`: `Fixture / Wing / Split / Leaf / Cut`, `engine.py`: `solve_fixture`, `_mark_open_interfaces`)
tiles each rectangular wing by a binary slicing tree; every `ZoneSpec` becomes an axis-aligned rectangle (`rect_m`);
walls are the split lines; `doors.py` / `windows.py` place openings on rectangle sides; `validation.py` (C1–C29),
`building_validation.py`, `quality_metrics.py` (M1–M6), `hub_guard.py`, `l_massing_guard.py`, `wet_core.py`,
`design_output.assemble`, `app/demo/contract.py` (`RoomOut.x/y/width_m/depth_m`, gross/net), the SVG renderer and
`frontend/src/design/DemoPlan.tsx` all assume rectangular rooms. The only non-rectangle today is the massing: an L of
two rectangular wings (`l_parti.py`, feature 006). The ResPlan corpus (17,107 real plans, polygons in
`/Users/mymacbook/projects/datasets/resplan/ResPlan.pkl`; the POC's normalised 199-plan corpus on branch
`integration/poc-architectural-brain`, `backend/spikes/architectural_brain/corpus/`) shows what real plans look like.

### Required behavior

1. **Inventory of the rectangle assumption**, module by module, with file:line evidence: Geometry Core types and
   solver, doors / windows / entrance placement, each validator C1–C29 and V-check (which would break on a polygon,
   which are shape-agnostic), M1–M6 and the quality tier, `hub_guard` / `l_massing_guard` / `wet_core`, the demo
   contract (`RoomOut`, `WallOut`, `DoorOut`), the SVG renderer, the frontend plan canvas, the corpus snapshot
   signature. Classify each as SHAPE-AGNOSTIC / NEEDS POLYGON VARIANT / MUST BE REDESIGNED.
2. **Measurement, deterministic** (`backend/spikes/geometry_shapes/measure_real_plan_shapes.py`, reads the POC corpus
   JSON and, when present, the raw pickle; committed results as a table in the report): share of rooms that are
   rectangles (after 10 cm vertex simplification), L-shaped (6 vertices, one notch), other polygons; share of plans
   whose room layout is guillotine-separable (a recursive straight cut exists that does not cross a room) vs
   non-guillotine; share of non-rectangular envelopes; the same for the 3–5-bedroom subset; and, for the 36 reference
   archetypes and the census aggregates, what is stated about shapes. Mark UNKNOWN explicitly.
3. **Three candidate architectures**, each with: what it produces (room shapes, envelope), what is reused unchanged,
   what needs a polygon variant, what must be redesigned, how Concept Engine v2's `ConceptSpec` feeds it, how the
   corpus regression (432 contexts, byte-identical primaries) is protected, effort in engineer-weeks and agent-days,
   the main risks, and a 2-week spike that would prove or kill it:
   - **A — slicing tree + room merging**: keep the engine; let one zone own two adjacent leaves (an L-shaped living /
     kitchen, a bent corridor) by opening their shared seam — the `contract.py` corridor-opening precedent generalised;
     polygon rooms appear in the contract and renderer while the solver stays rectangular.
   - **B — non-guillotine rectangular layout**: rooms stay rectangles but the partition is a general rectangular
     dissection (pinwheel / floorplan graph, e.g. a sequence-pair or O-tree representation with a constraint solver);
     gives real-plan room arrangements without polygon rooms.
   - **C — polygonal layout**: rooms as simple polygons inside a free envelope (constraint / optimisation based, e.g.
     the adapted reference polygons from the POC as initial layouts), polygonal walls / doors / windows / validators.
4. **Fit with the Concept Engine and the POC**: which architecture lets a retrieved ResPlan reference's topology AND
   shape be adapted (the POC's `adaptation.py` operations), and what the POC demo would look like under each.
5. **Recommendation** with a proposed ROOT + 2–5 children (contracts as proposal files under
   `.agent/proposals/roadmap/`), the order, and the first measurable milestone — proposal only, nothing implemented.

### Acceptance Criteria

- AC-1: the report exists with the module-by-module rectangle-assumption inventory carrying file:line evidence and a SHAPE-AGNOSTIC / NEEDS POLYGON VARIANT / MUST BE REDESIGNED classification for every validator C1–C29
- AC-2: the measurement script runs deterministically on the committed POC corpus fixture and the report states the measured shares (rectangular / L-shaped / other rooms; guillotine vs non-guillotine layouts; non-rectangular envelopes) with UNKNOWN marked where not derivable
- AC-3: the report compares the three architectures on reuse, redesign, effort, risk, regression protection and Concept Engine fit, each with a 2-week spike definition
- AC-4: the report ends with a recommendation and proposed ROOT + child contracts under `.agent/proposals/roadmap/` that render with `agentctl issue render`; no product code changes in the PR

### Out of scope

Any change to `app/` (product code), Geometry Core, validators, the Concept Engine or the POC branches; implementation of any candidate; fine-tuning.

### Affected domains

geometry, backend, validator, knowledge, qa

### Risk

LOW

### Resource class

MEDIUM

### Dependencies

none

### Required locks

docs (shared)

### Verification plan

- AC-1 -> file:docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md ; grep:docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md:MUST BE REDESIGNED
- AC-2 -> pytest:backend/tests/spikes/test_measure_real_plan_shapes.py ; grep:docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md:non-guillotine
- AC-3 -> grep:docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md:2-week spike
- AC-4 -> grep:docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md:Recommendation ; review:the PR changes only docs/, backend/spikes/geometry_shapes/, backend/tests/spikes/ and .agent/proposals/ — no product code

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md (new), docs/PROJECT_STATE.md (open investigations), .agent/proposals/roadmap/ (proposed ROOT + children).

### Knowledge check

Consulted: `docs/PROJECT_STATE.md`, `docs/wiki/architecture/geometry-validation.md`, `docs/wiki/features/l-massing.md`,
`geometry_core/{model,engine}.py`, `validation.py`, `contract.py`, `docs/SPATIAL_ENGINE_SPEC_V2_1.md`, `docs/GENERAL_GEOMETRY_DOMAIN_V1_REPORT.md`,
`docs/CONCEPT_ENGINE_V2_INVESTIGATION.md` §3.4 (bent corridor limit), the POC report `docs/reports/poc-architectural-brain/README.md`
(branch `integration/poc-architectural-brain`), memory `corridor-opening-is-a-contract-post-process`, the owner's observation of
2026-09-22 ("עדיין עיצובים מלבניים").
