# Demo P0 — Implementation Report

```
P0_STATUS = READY
NEXT_STEP = IMPLEMENT_DEMO_P1_UI_AND_RENDERING
```

**Backend 666 passed. Frontend 53 passed. `tsc --noEmit` clean.**

A real natural-language brief typed into the existing frontend now reaches the validated
planning pipeline and comes back as an authoritative, validated plan on screen.

---

## REAL_PRODUCT_PATH

```
BRIEF (free text + built area + selected rectangular footprint)
  POST /projects
  POST /projects/{id}/requirements     app/requirements/parser.py  (now extracts wet_rooms + open_plan)
REVIEW  "זה מה שהבנתי"
  GET  /projects/{id}/review           app/demo/requirements_view.py
  PUT  /projects/{id}/review           user corrections become AUTHORITATIVE
GENERATE
  POST /projects/{id}/design/demo      app/demo/service.py
     -> scope.check_supported          explicit refusal, never a silent downgrade
     -> requirements_view.spec_for     Project -> vertical_slice.ArchitecturalSpec
     -> concept_generator              DesiredAccessTopology + bounded concept candidates
     -> safe_adapter                   BuildableRegion -> proven-safe rectangles
     -> geometry_core                  realization
     -> doors -> windows -> furniture
     -> validation                     C1-C13, HARD GATE
     -> contract.to_demo_design        DemoDesign
PLAN WORKSPACE
  DemoPlan.tsx + DemoWorkspace.tsx     authoritative rendering only
```

## OLD_SOLVER_PATH_STATUS

**Bypassed on the demo path; still live on its own route.** `POST /projects/{id}/design` and
`app/geometry/solver.py` are untouched and still serve legacy projects. The demo path never calls
them — asserted by a test that parses `app/demo/service.py`'s imports and fails if
`app.geometry.solver` or `app.architect` appear. A second test asserts no canonical fixture
(`concept.py`, `geometry_fixtures.py`, `pipeline.py`) is importable from anything in `app/demo/`.

I chose a **new endpoint** rather than swapping the existing one, so the old path keeps working
while the demo is built; switching the product over is now a one-line change.

## AUTHORITATIVE_ARCHITECTURAL_SPEC

`app/vertical_slice/spec.py::ArchitecturalSpec` (PlotSpec + ProgramSpec).

`app/architect/models.py::ArchitecturalSpec` (the LLM gateway's output) is **not on the demo
path**. Both still exist; the adapter boundary is `app/demo/requirements_view.py::spec_for`.

## AUTHORITATIVE_GEOMETRIC_DESIGN

- **Internal:** `app/vertical_slice/design_output.py::GeometricDesign`
- **API-facing:** `app/demo/contract.py::DemoDesign` → `frontend/src/design/demoDesign.ts`

Named `DemoDesign` deliberately: two types called `GeometricDesign` already exist in this
codebase, and a third would have been a live confusion hazard during wiring.

## SUPPORTED_SCOPE / UNSUPPORTED_SCOPE

| Supported | Unsupported (explicitly refused) |
|---|---|
| 2–3 bedrooms | 4+ bedrooms (`BEDROOMS_UNSUPPORTED`) |
| optional safe room | more than one floor (`FLOORS_UNSUPPORTED`) |
| 1–3 wet rooms | 4+ wet rooms (`WET_ROOMS_UNSUPPORTED`) |
| open-plan true **or** false | pool (`POOL_UNSUPPORTED`) |
| 0–2 parking spaces | 3+ parking (`PARKING_UNSUPPORTED`) |
| rectangular footprint | non-rectangular / missing footprint (`FOOTPRINT_REQUIRED`) |
| single floor | unparsed requirements (`REQUIREMENTS_NOT_PARSED`) |

Plus two runtime refusals: `PLAN_NOT_REALIZABLE` (the programme does not fit the chosen
footprint) and `PLAN_FAILED_VALIDATION` / `PLAN_OUTSIDE_BUILDABLE`.

## TEST_COUNTS

| Suite | Result |
|---|---|
| Backend (`pytest -q`) | **666 passed** |
| — of which demo end-to-end (`tests/test_demo_p0.py`) | **30 passed** |
| Frontend (`vitest --run`) | **53 passed** |
| — of which new renderer-boundary tests | **8** |
| `tsc --noEmit` | clean |

Every demo test enters through the same routes a user does. No `ArchitecturalSpec` is built by
hand, no canonical fixture is injected, no room list is supplied mid-pipeline. The parser is the
only faked component, exactly as `tests/test_requirements.py` already does.

## FILES_CHANGED

**Backend** (committed by you in `99849a6`): `app/demo/{scope,requirements_view,contract,service,router}.py`
(new), `app/requirements/parser.py`, `app/requirements/router.py`, `app/projects/models.py`,
`app/projects/repository.py`, `app/main.py`, `tests/test_demo_p0.py` (new).

**Frontend** (uncommitted): `src/design/demoDesign.ts`, `DemoPlan.tsx/.css`,
`DemoWorkspace.tsx/.css`, `ReviewPage.tsx/.css`, `DemoPlan.test.tsx` (all new);
`src/App.tsx`, `src/App.css`, `src/api.ts`, `src/design/SketchSvg.tsx`,
`src/design/SketchSvg.test.tsx` (modified).

## FRONTEND_INFERENCE_REMOVED

Two inferences, both deleted from `SketchSvg.tsx`:

1. **Interior doors.** `hasDoor = segmentLength > doorSpan + 0.2` — a door invented wherever two
   rooms shared a long enough wall, with a swing drawn for it. The legacy path now draws
   **unbroken partitions and no doors**, because a legacy design carries no authoritative door
   data and the honest rendering is absence, not invention.
2. **The entrance.** The exterior wall was broken to make a gap wherever the living room happened
   to touch an outer edge. Also removed; the envelope is drawn closed.

`grep hasDoor` now matches only the comment explaining the removal. The existing test that
asserted "the legacy renderer still infers 2 doors" was replaced by one asserting it draws
**zero**, on the exact input that previously produced two.

`DemoPlan.tsx` decides nothing architectural: walls, doors, windows, open interfaces, names and
areas are all read off `DemoDesign`. Wall weight follows the backend's own construction/context
facts rather than a guess. Its tests pin the boundary — line counts that would change if a door
were invented, zero doors when the backend supplies none, and no wall where the backend reports
an OPEN interface.

## REVIEW_FLOW_STATUS

**Working.** `GET /review` returns each requirement with its provenance (`requested` / `inferred`
/ `unknown`), which the screen shows as a badge so a wrong assumption is easy to spot.
`PUT /review` writes corrections back and marks them `requested`, because the person asked for
them explicitly. Fields left absent keep their parsed value.

Four backend tests pin that the correction is what actually gets built: changing bedrooms 3 → 2
produces a two-bedroom plan; turning open-plan off removes every wall-less join between the
public rooms; untouched fields are preserved; and correcting *into* unsupported scope is refused
rather than planned.

The old flow jumped straight from parsing to solving behind one loading screen. That jump is gone
— generation only happens after the user confirms.

## VALIDATION_BEHAVIOR

**Hard gate.** `app/demo/service.py` raises rather than returning a plan when any of C1–C13 fails,
including C13 (realized connectivity) and C5 (physical reachability). It also refuses when the
safety check reports a room outside the buildable region. A plan is never returned as successful
with a failing check.

The API exposes `validation.statements` — product language derived only from checks that actually
passed ("כל החדרים נגישים פיזית מהכניסה") — plus `warnings` and the raw `checks` map for support.
The workspace shows statements and warnings; a test asserts raw codes like `C13` never reach the
user.

Failures surface as `422` with `{code, message, detail}`: `message` is written for a person and
shown as-is above the REVIEW screen; `detail` carries the measured reason. **The requirements are
never adjusted for the user** — a refused 4-bedroom brief still reads 4 bedrooms in review.

## KNOWN_P0_LIMITATIONS

1. **The GENERATING screen is presentational.** `generate_demo_design` is one synchronous call,
   so there is no real per-stage backend progress to report. I reused the existing
   `LoadingScreen` rather than dress a spinner as telemetry. Real stages are P1.
2. **`ArchitecturalFloorPlan.tsx` is superseded, not deleted.** `DemoPlan` is the surviving demo
   renderer; `ArchitecturalFloorPlan` and `SketchSvg` remain for legacy projects on the old route.
3. **Furniture is a feasibility verdict, not placed geometry** — nothing to draw yet (was
   classified C, correctly out of P0).
4. **No dimensions, north arrow, or door swings** — P1/P2 by classification.
5. **The footprint must be chosen before the brief is generated**, so the flow is still
   form → footprint → brief → review → plan rather than brief-first.
6. **`built_area_m2` is not enforced against the produced plan.** The generator sizes the house to
   the programme inside the chosen footprint; a user asking for 150 m² may get 168 m². Worth a
   decision before the demo.

---

One thing to flag, not act on: commit `99849a6` is titled *"Add Domain Model V2.1 Specification
Document"* but contains the backend demo implementation. I have not touched it.

Stopping for review. P1 not started.
