# Product Readiness Audit — evidence only

**Question.** What still prevents the selected BuildSmart plans from looking and functioning like
serious professional architectural concept plans that could credibly be shown to an architect or
client?

**Answer, from the evidence.** The plans themselves are architecturally competent. The product path
produces sensible houses: a hall arrival on 7 of 8 briefs, safe rooms correctly drawn in reinforced
concrete and on the envelope, doors with real leaves and swing arcs, windows on exterior walls, a
compass rose, a scale bar, overall dimensions, kitchen and bathroom fixtures and furniture. What
breaks the professional impression is not geometry and not missing architectural semantics. It is
**communication**: every single audited plan is unreadable in places because room names and
dimensions collide with furniture labels, fixtures are labelled with English identifiers in an
otherwise Hebrew drawing, and — on briefs whose requested area exceeds what the requested room
programme can hold — the plan contains a large unexplained grey "unassigned" block while the user is
told nothing.

**Three of my own candidate findings were withdrawn during this audit** after checking the data.
They are documented in §8 because the method matters more than the findings.

**No production code was changed.**

---

## 1. The eight audited briefs, and why

| brief | beds | wet | safe | open | requested | footprint | chosen because |
|---|---:|---:|---|---|---:|---|---|
| B08 | 3 | 1 | no | yes | 132 | 11×12 | smallest house; most retained alternatives |
| B20 | 2 | 3 | **yes** | yes | 132 | 11×12 | small, wet-heavy, safe room; #142O moved its winner |
| B02 | 1 | 1 | no | yes | 216 | 12×18 | simplest programme, narrow envelope; #142O moved its winner |
| B11 | 4 | 2 | **yes** | yes | 216 | 12×18 | dense programme, narrow envelope |
| B16 | 5 | 3 | **yes** | yes | 216 | 18×12 | wide envelope, dense |
| B19 | 6 | 2 | no | yes | 181 | 12.5×14.5 | most bedrooms; historically the non-planar brief |
| B06 | 3 | 2 | no | no | 312 | 13×24 | long narrow envelope, not open plan |
| B09 | 3 | 3 | no | no | 440 | 20×22 | largest house, not open plan |

Two small, four medium, two large; three with a safe room; one to six bedrooms; square, narrow and
wide envelopes; six open-plan and two not. Every one has at least one retained alternative.

## 2. What was rendered, and through what

28 plans were generated and rendered: the product winner and (where one exists) a product
alternative, plus the #142 winner and first alternative, for all eight briefs.

**Rendering used the real product renderer.** `DemoPlan` — the component the demo workspace ships —
was mounted on each payload and its SVG captured, then rasterised in a real browser with the
product's own stylesheets. Nothing was redrawn by a diagnostic renderer. Figures are in `figures/`.

There are **two** plan surfaces in the product and they are not equivalent:

| surface | fed by | door representation |
|---|---|---|
| `DesignPage → SketchCard → SketchSvg → ArchitecturalFloorPlan` | `project.geometric_design` | `DoorConnection`, an explicit **proxy** (`provenance: direct_access_proxy`, width is a fixed solver threshold, note says it is "not a modeled door swing/leaf/frame"). Draws jamb ticks only, deliberately. |
| `DemoWorkspace → DemoPlan` | `POST /projects/{id}/design/demo` | `DemoDoor` with `hinge_x`/`hinge_y`/`swing_deg`. Draws the leaf and the swing arc. |

The audit uses the second, because it is what the demo pipeline produces.

## 3. Finding E1 — the #142 chain is not reachable from the product *(Layer E)*

Searching the entire backend for `select_proposal` or `run_band_pipeline`, excluding the harness and
the two modules themselves, returns **nothing**. The product endpoint runs
`generate_demo_design → general_pipeline.run_general`. The band embedding, exact sizing, critic gate,
corrected proposer and the realized-plan selection merged as #142O are all outside the path that
produces what a client would be shown.

This is recorded as a **system/integration** finding, not automatically a defect.

## 4. The area question, traced end to end

### 4.1 What the number means
`built_area_m2` is a **requested gross built area target**. It is never a plot area and never a net
area. It flows: brief → `spec.program.target_built_area_m2` → outlines enumerated against it →
rooms sized within per-role caps in `ROOM_TEMPLATES` → `design.gross_area_m2` → `DemoDesign`. The
caps are deliberate; the code states that a generous house should get *more rooms* or a bigger hall
and living room rather than oversized bedrooms.

### 4.2 The area budget
`program_capacity_gross_m2` is the engine's own ceiling for a given room programme.

| brief | requested | programme capacity | over capacity? | product gross | % capacity | % request | #142 gross | % capacity |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| B08 | 132 | 213 | no | 129.6 | 61% | **98%** | 105.5 | 49% |
| B20 | 132 | 233 | no | 130.8 | 56% | **99%** | 129.8 | 56% |
| B02 | 216 | **182** | **yes** | 135.1 | 74% | 63% | 80.1 | 44% |
| B11 | 216 | 258 | no | 167.2 | 65% | 77% | 153.5 | 60% |
| B16 | 216 | 280 | no | 188.3 | 67% | 87% | 173.5 | 62% |
| B19 | 181 | 273 | no | 172.6 | 63% | **95%** | 184.4 | 67% |
| B06 | 312 | **193** | **yes** | 177.4 | **92%** | 57% | 96.5 | 50% |
| B09 | 440 | **200** | **yes** | 227.2 | **114%** | 52% | 101.0 | 50% |

### 4.3 Where the area goes — it is not lost
On B02, B06 and B09 the request exceeds the programme's own capacity. B09 asks for 440 m² from a
programme of living, kitchen, hall, master, two bedrooms, two bathrooms and a toilet whose
reasonable ceiling is 200 m². The product delivers 227 m² — **114% of capacity**. There is no
geometry defect. A candidate "Layer A area loss" finding was raised and is **withdrawn**.

### 4.4 What the user sees instead — the visual answer
The surplus is **not** an empty envelope, an oversized garden or a smaller outline. It appears as a
large, explicitly labelled, dashed-border room inside the building: **שטח גמיש (לא מוקצה)** —
"flexible area (unassigned)".

| brief | unassigned block | share of the house |
|---|---|---:|
| B09 | 8.55 × 6.35 m = **54.3 m²** | 24% |
| B06 | 8.50 × 3.25 m = 27.6 m² | 16% |
| B02 | 7.00 × 2.05 m = 14.3 m² | 11% |

For #142 the same surplus appears differently: a visibly **compact building inside a much larger
allowed footprint**, with a large empty site remainder.

### 4.5 No validator asserts the requested total area
`grep built_area backend/app/vertical_slice/validation.py` returns nothing. **Nothing anywhere
checks that a plan materially satisfies the requested house area.** Recorded as asked.

### 4.6 The defect is that none of this is disclosed
`service.py` already computes the capacity and already carries the exact message —
`TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY`: *"the programme you asked for can reasonably fill
about X m², and the target entered is Y m²; you can add rooms or reduce the built area."* It is
raised as a `DemoGenerationError`, so it fires **only when nothing plans at all**. When a plan
succeeds the user receives a 227 m² house for a 440 m² request, containing a 54 m² grey box, with no
explanation. Layer D, high severity, all data and wording already present.

## 5. Product versus #142, on architectural substance

Both paths reduced to the same `DemoDesign` contract, measured with production's own modules.

| dimension | product | #142 | better |
|---|---|---|---|
| validator status | all pass | all pass | tie |
| programme preserved | yes, all briefs | yes, all briefs | tie |
| area utilisation | 56–114% of capacity | 44–67% | **product** |
| entrance arrival | hall on **7/8** | hall on **2/8** | **product** |
| open-plan semantics | models open interfaces | **0** open interfaces; doors between living/dining/kitchen | **product** |
| corridor shape | long spine, aspect 7.9–11.9, 1.20–1.30 m wide | compact hall, aspect 1.0–3.4 | **#142** |
| corridor dead ends | **1 on every plan** | 0 on 7/8 | **#142** |
| worst habitable room aspect | 2.33–3.41 | 1.62–3.44 | tie |
| dead space share | 0.7–2.1% | 0.2–7.4% | product (except B02) |
| alternatives | same access graph | genuinely different | **#142** |
| runtime | 0.18–12.5 s | 0.6–8.1 s | tie |

**#142O's entrance result is within-pool only** and is not evidence that #142 beats the product on
entrance. Measured against the product it is the reverse.

## 6. Alternatives — are they genuinely different? *(audit §7)*

Access-graph Jaccard distance between a brief's winner and its first alternative:

| brief | #142 winner vs alt | product winner vs alt |
|---|---:|---:|
| B08 | **0.42** | 0.00 |
| B20 | **0.33** (different arrival room) | — |
| B06 | **0.30** | 0.00 |
| B02 | **0.25** | — |
| B16 | **0.19** | — |
| B11 | **0.15** | — |
| B19 | 0.00 | 0.00 |
| B09 | 0.00 | 0.00 |

**The product's "alternatives" are not alternatives.** In every case measured the access graph is
*identical*; rooms move and areas change, but the concept is the same. B09's alternative is 27 m²
smaller with the same connectivity. **#142's alternatives are genuinely different concepts in 6 of
8 briefs**, one of them even arriving through a different room.

## 7. Integration — case **B**, confirmed

`to_demo_design(realized.design, realized.report)` run on a #142 plan **succeeds** and returns every
field the renderer consumes, with doors carrying hinge and swing, windows, walls and interior layout
objects. Those payloads were then **rendered through the real `DemoPlan`**, which is the test that
decides this: 14 #142 plans rendered without inventing any architectural information.

Missing relative to a product call, all obtainable from the project and concept stages and none of
it invented:

| field | source | note |
|---|---|---|
| `outline` | footprint/outline stage | `None` on the direct conversion |
| `family` | concept stage signature | `None` |
| `garden`, `parking` | site context from the `Project` | empty |

So integration is **B — materially different capability, straightforward contract path** — not C.
What is *not* established is that #142 should be integrated; §5 shows it is behind the product on
area, entrance and open-plan semantics.

## 8. Three findings I withdrew — method note

1. **"Doors render without a swing arc."** True only of `ArchitecturalFloorPlan`, the other surface,
   which consumes a proxy contract and deliberately refuses to invent a swing. The product's
   `DoorSymbol` draws leaf and arc from engine data. My supporting count was also wrong:
   `swing_deg == 0.0` is a legitimate direction but reads as false.
2. **"The product produces strip rooms with aspect 9–12."** Every extreme value was the corridor,
   where a high aspect is normal. Worst habitable room is 2.33–3.41, unremarkable.
3. **"The compass renders as an opaque black disc."** My rasteriser inlined only `DemoPlan.css`; the
   compass is styled by `SketchSvg.css`. With the correct stylesheets it renders as a proper compass
   rose with needle and N/E/S/W letters.

Each was caught only by inspecting the underlying data or markup. None would have been caught by
reading code alone.

## 9. Deficiency matrix

| # | deficiency | layer | severity | frequency | backend data exists? | subsystem | correctness or presentation | scope | depends on |
|---|---|---|---|---|---|---|---|---|---|
| D1 | Requested area silently reduced to programme capacity; no notice on the success path | **D** | **high** | 3/8 briefs (all over-capacity ones) | **yes** — capacity + message already written | `demo/service` | communication of a correctness fact | small | none |
| D2 | Room name/dimension text collides with furniture labels | **C** | **high** | **16/16 plans** | yes | `DemoPlan` label layout | presentation | small–medium | none |
| D3 | Fixtures/furniture labelled with English identifiers in a Hebrew plan | **D** | medium | 16/16 plans | yes | `InteriorLayout` | presentation | small | none |
| D4 | #142 capability unreachable from any product endpoint | **E** | high | always | n/a | wiring | capability availability | medium | D5, D6 |
| D5 | #142 delivers 44–67% of programme capacity vs product 56–114% | **A** | medium–high | 7/8 briefs | yes | band sizing | correctness | large | — |
| D6 | #142 emits no open interfaces; doors between living/dining/kitchen on open-plan briefs | **A** | medium | all open-plan briefs | yes | band pipeline | correctness | medium | — |
| D7 | Product "alternatives" share an identical access graph | **A** | medium | 4/4 measured | yes | concept generator | usability | large | — |
| D8 | Product corridor is 1.2–1.3 m wide × 11–17 m, with one dead end on every plan | **A** | low–medium | 8/8 product plans | yes (`circulation_metrics`) | concept generator | correctness | large | — |
| D9 | No validator asserts the requested total area | **B/E** | medium | always | partially | validation | correctness | small | D1 |
| D10 | #142→`DemoDesign` lacks outline, family, garden | **E** | low | always | yes, elsewhere | `demo/contract` | completeness | small | D4 |

## 10. The five largest blockers

Ranked with correctness and usability above polish, from the audited plans.

1. **D2 — label collisions (Layer C).** Affects **every one of the sixteen plans**. Room names,
   dimensions and furniture labels overprint each other, so a reader cannot read what a room is or
   how big it is. Nothing is missing from the model; the drawing simply places text badly. This is
   the single most visible reason a plan does not read as professional.
2. **D1 — silent capacity shortfall (Layer D).** A client asking for 440 m² receives 227 m² with a
   54 m² unexplained grey block and no message, although the number and the sentence already exist.
3. **D7 — the product's alternatives are one concept re-proportioned (Layer A).** A client shown
   three "options" with an identical access graph has been shown one option.
4. **D5 + D6 — #142's area and open-plan deficits (Layer A).** These, not the contracts, are what
   currently block adopting the newer pipeline.
5. **D3 — English fixture tokens (Layer D).** Professional plans draw a symbol, not the word `SOFA`.

Not in the five: missing architectural semantics. The model already carries doors with swing, wall
construction, windows, fixtures, furniture, orientation and dimensions, and the renderer already
draws them.

## 11. Recommended next engineering milestone — one

> **A concept-plan communication pass: make the drawing legible and make the brief-versus-capacity
> gap explicit.** Concretely: resolve label placement so room names, areas and furniture never
> overprint (D2); render fixtures as symbols rather than English tokens, or label them in Hebrew
> (D3); and surface the already-computed programme-capacity gap on the **success** path, so an
> over-capacity brief is answered with the plan *and* the sentence the product has already written,
> instead of an unexplained unassigned block (D1).

**Why this and not something else.** It is the only candidate supported by all sixteen plans rather
than by a subset: D2 affects 16 of 16. Every input it needs already exists in the backend and in the
contract, so it touches no geometry, no validator, no solver and no new score. It is squarely what
the question asks — the plans already *function* like competent architecture, and what stops them
being credibly shown to an architect or client is that they cannot be read and that they quietly
misreport the brief. And it is bounded: label layout, fixture presentation, one disclosure path.

**The runner-up, and why the evidence does not support it yet.** Wiring #142 in to supply genuinely
different alternatives would fix D7, the one thing the product provably cannot do. The evidence
blocks it: #142 delivers less area on 7 of 8 briefs, reaches a hall arrival on 2 of 8 against the
product's 7, and ignores open-plan semantics entirely. Integration is cheap (case B); the plans are
not yet good enough to ship. D5 and D6 are the prerequisites.

## 12. Scope

No production code changed. No new scoring model, no validator change, no features added because
they were missing, no frontend redesign, no Geometry Core work. The audit worktree contains only the
harness (`backend/app/ai_harness/audit_readiness/`), one render helper in the frontend, this report
and its figures.

**Artefacts.** `figures/` (28 plans rendered through the product renderer, plus comparison sheets) ·
`data/measurements.json` (every measured quantity for every plan) · `reference-sources.md` (the
reference set and its sources).
