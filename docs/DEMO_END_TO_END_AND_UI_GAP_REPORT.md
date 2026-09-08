# Demo End-to-End & UI Gap Report

Audit only. Nothing implemented. Traced against real code, not against my own reports.

```
CURRENT_DEMO_READINESS = 40%
P0_BLOCKERS = 8
P1_BLOCKERS = 6
```

---

## 0. The finding everything else follows from

**The validated pipeline is not reachable from the API. At all.**

```
$ grep -rn "vertical_slice" app --include="*.py" | grep -v "^app/vertical_slice/"
app/geometry_domain/__init__.py:4:   (a comment)
app/geometry_domain/units.py:25:     (a comment)
```

Four matches, all of them prose in docstrings. No router, no service, no import. Nine phases of
work — concept generator, safe geometry adapter, geometry core, doors, windows, furniture,
13 validation checks, 636 tests — sit in a package that the running product never calls.

Meanwhile a **second, older planning system is live** and is what a user actually hits today.
There are two `ArchitecturalSpec` types and two `GeometricDesign` types, with the same names, in
the same codebase.

| | Live product path | Validated path |
|---|---|---|
| Spec type | `app.architect.models.ArchitecturalSpec` (rich Pydantic, LLM-produced) | `app.vertical_slice.spec.ArchitecturalSpec` (PlotSpec + ProgramSpec dataclass) |
| Engine | `app.geometry.solver.GeometrySolver` | concept generator → safe adapter → geometry core |
| Output | `app.geometry.geometric_design.GeometricDesign` (footprint, rooms, walls, doors, 2 areas) | `app.vertical_slice.design_output.GeometricDesign` (+ wall facts, windows, parking, garden, entrance, furniture) |
| Validation | none in the contract | C1–C13, incl. realized connectivity |
| Reachable from UI | **yes** | **no** |

So the demo is not an engine problem. **The engine is done; the product path is missing.** That
is why readiness is 40% rather than 10% — the hard, risky part is built and tested, and what
remains is integration, contract and UI work.

---

## 1. Stage-by-stage trace

| Stage | Implementation | Status | In → Out | Connected? |
|---|---|---|---|---|
| Brief input | `App.tsx` form: city, street, `description`, built area | **production** | form → `ProjectCreate` | yes |
| Footprint selection | `FootprintSelection.tsx` + `footprint.ts` | **production** | user pick → `SelectedFootprint` (rectangle) | yes |
| Requirements parser | `app/requirements/parser.py`, `OpenAIRequirementParser` (gpt-5-nano, structured output) | **production** | `description` → `floors, bedrooms, safe_room, parking_spaces, pool` | yes |
| Architect Model | `app/architect/gateway.py` → `ArchitecturalSpec` | **production** | Project → spec | yes, to the OLD solver |
| **General Concept Generator** | `app/vertical_slice/concept_generator.py` | **validated, unwired** | its own `ArchitecturalSpec` → `Concept` | **NO** |
| Site / BuildableRegion | `app/geometry_domain/`, `safe_adapter.build_buildable_region` | **validated, unwired** | Parcel+constraints → `BuildableRegion` | **NO** |
| Safe Geometry Adapter | `app/vertical_slice/safe_adapter.py` | **validated, unwired** | region → safe rects | **NO** |
| Geometry Core | `app/vertical_slice/geometry_core/` | **validated, unwired** | fixture → rects + walls | **NO** |
| Doors / Windows / Furniture | `doors.py`, `windows.py`, `furniture.py` | **validated, unwired** | — | **NO** |
| Validation | `validation.py` C1–C13 | **validated, unwired** | — | **NO** |
| GeometricDesign | `design_output.py` | **validated, unwired** | — | **NO** |
| API | `app/design/router.py` `POST /{id}/design` | **production** | calls the OLD pipeline | yes |
| Frontend renderer | `ArchitecturalFloorPlan.tsx` (authoritative) / `SketchSvg.tsx` (legacy, **infers**) | **production** | old `GeometricDesign` | yes |

**Legacy/duplicate paths found:** `app/design/generator.py` (old row-layout, deliberately dead),
`app/geometry/solver.py` + `spatial_v1_topology.py` + `spatial_v2/` (the live engine),
`SketchSvg.tsx`'s legacy branch. The vertical slice's own `renderer.py` is a **server-side
matplotlib PNG writer** — useful for my QA, a dead end for an interactive workspace, and it
should not be part of the demo path.

**Canonical fixtures in the path:** `concept.py`'s hand-authored 3BR concept is still called by
`pipeline.run_demo`. It must not be reachable from the product path. `geometry_fixtures.py` is
test-only. Neither is currently in the API path (because nothing is), but both are traps once
wiring starts.

---

## 2. Authoritative demo pipeline

```
AUTHORITATIVE_DEMO_PIPELINE =
  Brief (free text) + built area + selected footprint
    → app/requirements/parser.py            [EXTEND: + wet_rooms, + open_plan]
    → Project.requirements (TaggedInt/TaggedBool, editable in REVIEW)
    → NEW adapter: Project → vertical_slice.ArchitecturalSpec (PlotSpec + ProgramSpec)
    → concept_generator.generate_concepts()
    → safe_adapter.build_buildable_region() + adapt()
    → geometry_core.solve_fixture()
    → doors → windows → furniture
    → validation.validate()  (C1–C13, must pass)
    → design_output.GeometricDesign
    → NEW: DemoDesign API contract (superset of today's, see §5)
    → ArchitecturalFloorPlan.tsx  (authoritative renderer)
```

**Bypassed for the demo:** `app/architect/*` gateway, `app/geometry/solver.py`,
`app/geometry/geometric_design.py`, `app/design/generator.py`, `SketchSvg.tsx`'s legacy branch,
`vertical_slice/renderer.py`.

**Becomes authoritative:** `vertical_slice/` end-to-end, `geometry_domain/`,
`ArchitecturalFloorPlan.tsx`.

I am proposing a **new endpoint** (e.g. `POST /projects/{id}/design/v2`) rather than swapping the
existing one, so the old path keeps working while the demo path is built, and the switch is one
line at the end. That is not a second planning system — it is one new door onto the validated one.

```
PROPOSED_UI_FLOW = BRIEF → REVIEW → GENERATING → PLAN_WORKSPACE → MODIFY_OR_ALTERNATIVE
```

---

## 3. UI flow audit

**A — BRIEF.** Exists as a `description` textarea inside a form that also collects city, street,
built area, then a footprint-selection step. For the demo the brief should lead and the rest
should recede; city/street are only needed because `localities` validates them. **Minimal
change:** keep the form, promote the description, keep footprint selection (it is what gives us a
real rectangle to plan in).

**B — REVIEW.** **Does not exist.** Today parse and generate run back-to-back behind one loading
screen. This is a P0 build: a screen showing extracted requirements with the ability to correct
them before Generate. Smallest contract: the fields already on `Project`
(`bedrooms/safe_room/parking_spaces/floors` as `TaggedInt`/`TaggedBool` with their `source`) plus
the two new ones (`wet_rooms`, `open_plan`). `PATCH /projects/{id}` already exists via
`ProjectUpdate` — the edit path is largely there.

**C — GENERATING.** `LoadingScreen.tsx` exists but carries **no stage data**, and
`generate_design_via_solver` is a single synchronous call. **There is no real progress state to
report.** Honest options: (a) presentational stages, clearly not claiming backend truth, or
(b) split the endpoint into 2–3 real steps. I recommend (a) for the demo and saying so in this
report rather than dressing a spinner as telemetry.

**D — PLAN WORKSPACE.** `DesignPage` has the plan in a *card* with chat/menu/settings overlays.
For the demo the plan must dominate. `ArchitecturalFloorPlan.tsx` is the right renderer and is
already documented as authoritative-only.

**E — NEXT ACTION.** `SpatialEditControls` + `POST /design/spatial-edit` exist and work against
the OLD contract and OLD solver. **They do not work against the validated pipeline.** "Generate
alternative" is nearly free — `generate_concepts()` already returns a bounded ranked candidate
list and the pipeline currently just takes the first. Natural-language edits ("make the living
room larger") are **P2**: they would need the spatial-edit machinery re-pointed at the new engine.

---

## 4. Real brief → real pipeline: every transformation required

| # | Transformation | Category | Note |
|---|---|---|---|
| 1 | `description` → `wet_rooms` | parser extension | **not extracted today** — `ProgramSpec.wet_rooms` has no source |
| 2 | `description` → `open_plan_living` | parser extension | **not extracted today** |
| 3 | `Project` → `ProgramSpec` | new adapter | bedrooms/safe_room/parking map directly |
| 4 | `SelectedFootprint` (w×d) → `PlotSpec`/`Parcel` | new adapter | the rectangle exists; setbacks are placeholder constants |
| 5 | REVIEW edits → authoritative requirements | wiring | `ProjectUpdate` exists; must be the *only* source Generate reads |
| 6 | Unsupported program → explicit refusal | new | generator already returns structured `ConceptRejection`; needs an HTTP mapping |

**No hidden fixture** is acceptable at any of these points; `concept.py`'s canonical fixture and
`geometry_fixtures.py` must stay out of the product path.

---

## 5. Output contract audit

Against `app.vertical_slice.design_output.GeometricDesign`:

| UI need | Status | Class |
|---|---|---|
| footprint / buildable geometry | present (`footprint_m`, `plot_m`) | **A — expose** |
| rooms, names, areas | present (`RoomOut`) | **A** |
| wall construction + boundary context | present (`wall_facts`) | **A** |
| OPEN interfaces | present (`walls[side] == "OPEN"`) | **A** |
| doors (+ width, position) | present (`DoorOut`) | **A** |
| windows | present (`WindowOut`) | **A** |
| entrance | present (`entrance_door`, `entrance_walk_m`) | **A** |
| parking | present (`parking_m`) | **A** |
| garden | present (`garden`) | **A** |
| validation results | computed but **not on the DTO** | **A — attach the report** |
| **wall segments** (`orientation/coord/start/end`) | walls are per-room **side types**, not segments | **B — derive** |
| **door swings** (hinge side, direction) | only centre + orientation | **B — derive**, or accept a symmetric symbol |
| dimensions / dimension lines | not present | **B — derive from rects** |
| furniture geometry | only a **feasibility verdict**, no placed items | **C — do not build for the demo** |
| north / orientation | not modelled anywhere | **C — omit, or take it as a user input** |

The frontend's current `Wall` type is a segment; the validated output is per-room sides. That
derivation (B) is the single largest contract task and belongs in the backend, not the renderer.

---

## 6. Renderer audit

| Renderer | Verdict |
|---|---|
| `ArchitecturalFloorPlan.tsx` | **survives — becomes the demo renderer.** Already authoritative-only by design. |
| `SketchSvg.tsx` legacy branch | **must be bypassed.** It fabricates: `hasDoor = segmentLength > doorSpan + 0.2` — it invents doors from shared-wall length, the exact inference removed from the product once before. |
| `SketchSvg.tsx` dispatcher | keep only as long as legacy projects must still open; not on the demo path |
| `vertical_slice/renderer.py` (matplotlib PNG) | **not part of the demo.** QA tool only. |

**Currently fabricated by the frontend:** interior doors, door swings, and the exterior door
position in the legacy path. Everything in `ArchitecturalFloorPlan` comes from the backend.

**Missing rendering capability** for the demo: windows, OPEN interfaces (no wall drawn),
wall-thickness hierarchy by construction type, parking/entrance/garden context, dimension lines,
fit-to-plan zoom.

---

## 7. Supported demo scope

```
SUPPORTED_DEMO_SCOPE =
  Programme : 2–3 bedrooms; optional safe room; 1–3 wet rooms; optional open-plan LDK;
              0–2 parking spaces; single floor
  Site      : RECTANGULAR footprint only (the user-selected rectangle)
  Out       : 4+ bedrooms, multi-floor, L/curved/obstructed/disconnected sites,
              pools, multi-wing
```

Rectangle only, deliberately: it is the only geometry with **retention 1.000 and zero
approximation loss**, and it is what `SelectedFootprint` already produces. L/curved/obstacle all
pass tests, but exposing them buys nothing for the demo and adds the residual-area story to
explain. Everything outside the envelope must return an explicit refusal — the generator already
produces structured `ConceptRejection` reasons to translate.

---

## 8. Five demo briefs

Hebrew, since the parser prompt is Hebrew-first. All must enter through the same UI/API path.

**1 — 3BR + safe room + open plan (the flagship)**
> "בית פרטי בקומה אחת עם שלושה חדרי שינה, ממ״ד, מטבח פתוח לסלון ולפינת אוכל, שני חדרי רחצה ושתי חניות."

Expected: bedrooms 3, safe_room true, wet_rooms 2, open_plan true, parking 2, floors 1.
Hard: safe room exists and is RC on all sides; LDK physically OPEN; every room reachable.
Unacceptable even if valid: safe room not reachable from circulation; LDK drawn with walls.

**2 — 2BR, no safe room, compact**
> "בית קטן לזוג, שני חדרי שינה, חדר רחצה אחד, סלון ומטבח פתוחים, חניה אחת."

Expected: bedrooms 2, safe_room unknown/false, wet_rooms 1, open_plan true, parking 1.
Unacceptable: a safe room invented; bathroom under ~4.5 m².

**3 — 3BR + safe room + 3 wet rooms (upper end)**
> "שלושה חדרי שינה, ממ״ד, שלושה חדרי רחצה — אחד צמוד לחדר ההורים, מטבח פתוח, שתי חניות."

Expected: wet_rooms 3, ensuite relationship implied.
Inspect: the ensuite is entered **from the master**, not from the hall.

**4 — 2BR + safe room, closed kitchen**
> "שני חדרי שינה וממ״ד, מטבח נפרד וסגור, לא מטבח פתוח, חדר רחצה אחד, שתי חניות."

Expected: open_plan **false** — the negative case for parser extraction.
Unacceptable: an open-plan LDK generated despite an explicit refusal.

**5 — Out of envelope (must fail cleanly)**
> "בית עם ארבעה חדרי שינה, ממ״ד ושלושה חדרי רחצה."

Expected: explicit "not supported in the current demo yet." **Unacceptable:** silently planning
3 bedrooms, a 500, or an infinite spinner.

---

## 9. Visual quality classification

**P0 — misleading without it:** OPEN interfaces drawn as no wall (not a thin line); doors only
where the backend says; wall thickness reflecting construction type (RC vs partition vs
exterior); windows only where authoritative; no legacy inference anywhere.

**P1 — needed to convince:** room labels + m²; overall dimension lines; entrance marker; parking
and plot context; fit-to-plan zoom; the plan dominating the screen; validation stated in product
language.

**P2 — polish:** door swing arcs with correct hinge side; furniture symbols; north arrow;
hatching/poché; pan/zoom controls; dimension chains per room.

---

## 10. P0 tasks, in order

| # | Task | Type |
|---|---|---|
| 1 | Extend the requirements parser: `wet_rooms`, `open_plan` (+ `Project` fields, + tests) | BACKEND CONTRACT |
| 2 | Adapter `Project` → `vertical_slice.ArchitecturalSpec` (`ProgramSpec` + `PlotSpec` from `SelectedFootprint`) | INTEGRATION |
| 3 | Demo service: adapter → generator → adapter → core → doors/windows/furniture → validation, returning design + validation | INTEGRATION |
| 4 | Derive **wall segments** and attach the **validation report** to the output DTO | BACKEND CONTRACT |
| 5 | `POST /projects/{id}/design/v2` returning the new contract; structured refusal (422 + reason) for out-of-envelope | BACKEND CONTRACT |
| 6 | REVIEW screen + edit-before-generate, reading/writing the requirement fields | FRONTEND |
| 7 | Point `ArchitecturalFloorPlan` at the new contract; render windows + OPEN interfaces + wall hierarchy; bypass the legacy inference branch | VISUALIZATION |
| 8 | Explicit failure UI for unsupported briefs | FRONTEND |

None of these is NEW ARCHITECTURAL CAPABILITY. That is the point.

## 11. P1 tasks, in order

1. Plan-dominant workspace layout (FRONTEND)
2. Room labels + areas + total built area panel (VISUALIZATION)
3. Overall dimension lines (VISUALIZATION, derivation B)
4. Entrance + parking + plot context on the drawing (VISUALIZATION)
5. Validation → product language: "All rooms are physically accessible", "Required safe room included" — mapped from C5/C13/C4, never raw codes (FRONTEND)
6. Presentational GENERATING stages, explicitly not claimed as backend telemetry (FRONTEND)

## 12. P2 — deferred

4BR; multi-wing; L/curved/obstacle sites in the public demo; natural-language plan edits;
re-pointing spatial-edit at the new engine; furniture placement geometry; north/orientation;
door-swing hinge derivation; LLM architectural reasoning; regulation/GIS; diagonal optimization.

---

## 13. Demo gate

```
[ ] User enters a real natural-language brief
[ ] "What I understood" shows correctly extracted requirements (incl. wet rooms, open plan)
[ ] User can correct them before generating
[ ] The corrected requirements are the ONLY input Generate reads
[ ] No canonical fixture anywhere in the path (concept.py / geometry_fixtures.py unreachable)
[ ] General Concept Generator produced the concept
[ ] Safe Geometry Adapter + Geometry Core produced the geometry
[ ] Doors, windows and OPEN interfaces all come from the backend
[ ] C13 realized connectivity passes
[ ] C1–C13 all pass
[ ] Renderer displays the actual generated geometry, inferring nothing
[ ] The plan reads as an architectural drawing
[ ] All five briefs work through the identical path
[ ] Brief 5 fails explicitly, with a reason
[ ] `grep hasDoor` finds nothing on the demo path
```

## 14. Components likely involved

Backend: `app/requirements/parser.py`, `app/projects/models.py`, `app/design/router.py` (new
endpoint), a new `app/demo/` service, `app/vertical_slice/*`, `app/geometry_domain/*`.
Frontend: `App.tsx`, a new `ReviewPage`, `DesignPage.tsx`, `ArchitecturalFloorPlan.tsx`,
`geometricDesign.ts`, `api.ts`, `LoadingScreen.tsx`.

## 15. Risks that could still block the demo

1. **Parser reliability on `open_plan`/`wet_rooms`.** Brief 4 (explicit "not open plan") is the
   risky one — a negation the model must not flip. Mitigation: test all five briefs against the
   real parser early; it is cheap and it is P0 task 1.
2. **Wall-segment derivation** is the one genuinely fiddly contract task; per-room sides → merged
   segments has edge cases at T-junctions and OPEN gaps.
3. **Two `GeometricDesign` types with the same name** in one codebase is a live confusion hazard
   during wiring. Recommend renaming the new one at birth.
4. **The plan may be architecturally valid but visually plain.** All 13 checks passing does not
   make a drawing look designed; P1 is not optional for a demo.
5. **Scope creep back into the engine.** The moment a brief mentions four bedrooms, the pull will
   be to "just make 4BR work". It is P2. The refusal path is the demo feature.

---

Stopping for review. Nothing implemented; no spatial-engine research reopened.
