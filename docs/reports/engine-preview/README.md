# Engine Preview — see Concept Engine output in the existing UI

A bounded development seam so the project owner can generate a brief through **Concept Engine v2**
and inspect its actual plan in the existing demo workspace, rendered by the same `DemoPlan`
component production uses. **This is not a rollout.** Concept Engine v2 remains globally OFF.

## How to run it

```
# backend  (from the repo root)
cd backend && uv run uvicorn app.main:app --reload --port 8000

# frontend (second terminal)
cd frontend && npm run dev
```

Then in the browser:

1. open the dev server URL Vite prints (normally **http://localhost:5173**);
2. enter a brief and go through the requirements review as usual;
3. press **Generate** — this runs **Current Production**, exactly as before;
4. on the plan screen, the side panel now has **תצוגת פיתוח — מנוע** with two choices:
   **ייצור נוכחי** (Current Production) and **Concept Engine v2**;
5. select **Concept Engine v2**. The same stored brief is re-generated through that engine —
   nothing has to be re-entered — and the resulting plan is drawn by `DemoPlan`.

The API seam directly, if you prefer curl:

```
POST /projects/{id}/design/demo                              # production (unchanged)
POST /projects/{id}/design/demo?engine=production            # production, explicitly
POST /projects/{id}/design/demo?engine=concept_engine_v2     # the preview
POST /projects/{id}/design/demo?engine=nonsense              # 422, never silently production
```

## What the panel shows

| field | source |
|---|---|
| Engine | the choice the last generation actually ran |
| Generation time | measured in the client around the request |
| Validity | `design.validation.passed` |
| Concept family | `design.concept.label`, or **לא זמין** when the engine attached none |
| Alternatives | `plans.alternatives.length` — never padded |
| Built / net area | `gross_area_m2` / `net_area_m2` |

A failure shows the backend's typed code and message on the review screen. There is **no fallback**
to production: a preview that fails shows its own failure.

## What you will see today

Measured on the audit briefs, Concept Engine v2 **returns a valid primary plan and zero
alternatives**, and attaches no concept family, so the panel reads `Alternatives: 0` and
`Concept family: לא זמין`. That is the honest current state and the baseline this preview exists to
make observable — not a broken preview. If the engine starts returning alternatives, the same UI
exposes them automatically as **קונספט 1 / קונספט 2 / קונספט 3**, with no further integration work.

| brief | production alternatives | Concept Engine v2 alternatives |
|---|---:|---:|
| B08 | 2 | 0 |
| B06 | 2 | 0 |
| B09 | 1 | 0 |
| B19 | 1 | 0 |

## The seam

`general_pipeline.CONCEPT_ENGINE_V2_ENABLED` is read in exactly three functional places. Each now
resolves a **per-request** value instead, defaulting to the module flag:

```
run_general(..., concept_engine_v2_enabled: bool | None = None)
  -> use_concept_engine_v2 = CONCEPT_ENGINE_V2_ENABLED if None else the override
```

threaded as `concept_engine_v2: bool | None = None` through `generate_demo_design`,
`_generate_demo_design`, `_plan_outlines_until_one_plans`, `_plan_outlines` and `_plan`, plus the
service's own two reads (`_augment_cross_outline_classes`'s gate and `_concept_of`'s label). The
router turns `?engine=` into that value. **The flag is never written**, so two requests in flight
cannot see each other's choice.

## Guarantees, tested

`backend/tests/test_engine_preview.py` (13) and `frontend/src/api.engine.test.ts` (4) plus 7 UI
tests in `DemoPlan.test.tsx`:

1. no override → the payload is identical to production's;
2. explicit `production` → identical again, not a third behaviour;
3. explicit `concept_engine_v2` → observably a different path;
4. the global flag is `False` before and after every variant;
5. a preview run does not change the next production run;
6. zero alternatives is returned and displayed as zero, never padded;
7. alternatives become selectable as קונספט 1..N the moment the engine returns any;
8. a missing concept family displays as **לא זמין** and is never invented;
9. an unknown engine is a 422, and both stream fallbacks carry the engine so a fallback can cost
   the percentage but never change which engine ran.

Suites: backend 2337 passed, frontend 242 passed.

## Scope

No engine change, no fix to its alternative generation, no generation/scoring/validator/geometry
change, no #142, no second renderer, no fabricated concept-family information, and no change to the
production default.
