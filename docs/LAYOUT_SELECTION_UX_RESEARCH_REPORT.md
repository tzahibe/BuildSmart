# Layout Selection UX — research and recommendation

**Date**: 2026-09-14 · **Status**: recommendation only, nothing implemented · **Base**: `main` at `c3b1c96` (feature 006 merged, hub parti present)

**Question**: what is the simplest flow in which a person enters site and building data, chooses a preferred house shape or layout, can rotate it, and the generated sketch respects that choice?

---

## 0. The constraints the engine actually imposes

Everything below is read from the code, not assumed. These six facts decide the design.

| # | Fact | Where | Consequence for this feature |
|---|---|---|---|
| 1 | **The drawing frame is street-up, not north-up.** The street is always the `y = 0` edge; parking bays, the entrance walk and the front door all live on that edge; C10/C11/C16 check exactly that. An EAST/WEST street is handled by swapping the plot's width and depth before planning. Nothing in the pipeline rotates or flips anything. | `demo/site_geometry.py` (`SiteGeometry`, `derive`), `vertical_slice/site.py` | "Rotate the house" cannot mean turning it away from the street. The only real orientation inputs are: which plot edge is the street (already a site fact), whether the house's long axis runs along or across the street (the outline), and left/right handedness (mirror). |
| 2 | **The compass on the drawing is a constant "N".** Both renderers draw a needle labelled `N` pointing up, regardless of `street_facing_side`. | `design/SketchSvg.tsx:250`, `design/ArchitecturalFloorPlan.tsx:194` | For a SOUTH, EAST or WEST street the compass is wrong today. This is a live defect and the first thing any "rotation" work must fix. |
| 3 | **Outlines are rectangles.** `SelectedFootprint.shape_type` is `Literal["RECTANGLE"]`; the `polygon` field exists and is unused. The engine offers four proportions (`PREFERRED_RATIOS = 0.95, 1.15, 0.75, 1.45`) clipped into the setbacks; since 006 it plans all four and shows up to three plans chosen by architectural family. | `projects/models.py`, `demo/site_geometry.py`, `demo/service.py` | The outline vocabulary is already three shapes (near-square, wide, deep) plus a second near-square. There is no L or U outline for the UI to offer honestly. |
| 4 | **Internal organisation is a separate, small vocabulary.** Six `ConceptStrategy` values collapse into three tree shapes: *spine* (public column · hall · private column; five strategies share `V[col, HALL, col]`), *front band* (public zones across the street front, corridor and two bedroom columns behind), *hub* (public band in front, compact room lobby with bedrooms on its flanks; ≥ 3 bedrooms). `MULTI_WING_SPLIT` (an L) is assessed and always declined because a hall against a partial seam would route circulation through a bedroom. | `vertical_slice/concept_generator.py` (`_allocations`, `_front_band_concept`, `_hub_concept`, `_multi_wing_assessment`) | "Public/private wing layout" is not a footprint; it is one of these three organisations. Outline shape does not switch organisation (006 §1: family mix is the same at every ratio). |
| 5 | **The public zone is always on the left or on the street front.** Every spine allocation puts `public` in the *west* column; the band and hub partis put it across the *front*. No parti puts the living room across the rear (garden) side, and no mirrored candidate is ever generated. `family_signature` deliberately mirror-normalises, so a mirror is "the same house". | `concept_generator.py:1306-1352`, `general_pipeline.py:163-212` | Left/right mirror is a free, validation-preserving transform the engine never produces — the cheapest real variation available. "Living to the garden" is a missing parti, not a preference the engine can honour. |
| 6 | **The entrance is resolved from the realised plan, on the street wall only.** `resolve_entrance` picks the best zone that touches `y = footprint.y` by role priority, then the door is moved clear of the bays. | `vertical_slice/doors.py:146`, `general_pipeline.py:235-276` | "Move the entrance" has exactly two honest meanings: mirror (left ↔ right) or a different organisation (door into the hall vs into the living space). A free door position is not supported. |

Two measured facts from 006 frame the product decision:

- A person's own outline planned in **30 %** of the 424 logged briefs; each of the engine's four proportions planned in **35–45 %**; the engine's search lifted plans-per-brief to **61 %** and delivered area from 79 % to 98 % of the request. Making any pre-generation shape choice *authoritative* would reintroduce the refusal path 006 removed.
- Family repetition is a **generator** property (two tree shapes), not a ranking or outline property. A layout picker cannot manufacture diversity; it can only expose what the search already found.

---

## A. Product recommendation

**Choose from real plans, not from abstract shapes. Treat the choice as a preference the search honours first, never as a constraint it must satisfy.**

1. **No new pre-generation shape screen in the MVP.** Feature 006 removed the outline screen for a measured reason. The engine already plans every feasible outline in one request (3–6 s); the "3–4 recommended layouts" the brief asks for *are* the validated plans that request returns. Recommending shapes before planning would mean recommending things the engine has not yet checked.
2. **The layout choice lives on the results screen, as chips over labelled thumbnails.** Flip, turn along/across the street, another arrangement, bedrooms in their own wing, more open living. Each chip either swaps to a plan already in the validated pool (instant) or edits one stored field and regenerates.
3. **The picked layout is saved as a structured `LayoutPreference` on the project** (shape, organisation, mirrored). Every later regeneration — after a review edit, a chat change, a settings change — plans the preferred outline first and shows the preferred family first when it exists, with the existing FR-008-style note when it does not.
4. **Rotation is split in two and neither is a free angle.** Planning orientation = street side (site fact) + outline axis (along/across the street) + mirror. Visual orientation = a north-up/street-up view toggle that never reaches the engine. The constant "N" compass is fixed as part of this.
5. **Authoritative stays where it is**: only the advanced explicit outline (`selected_footprint`) binds the engine, exactly as 006 left it.

---

## B. Recommended layout families

Two small vocabularies, both already in the engine, presented to the person as one row of labelled cards. Site proportions below use `A` = requested built area, `BW`/`BD` = buildable width/depth after setbacks (and after the 5 m parking band when parking > 0, which comes off the depth — `site.py:front_band_m`).

### B.1 Outline shape (how the house sits on the plot)

| Family | Engine today | When it fits | Site proportions | Pros | Cons | Offered automatically? |
|---|---|---|---|---|---|---|
| **Compact** (near-square, ratio 0.95–1.15) | Yes — two of the four preferred ratios | Almost always; the default | `BW ≥ 0.97√A` and `BD ≥ 0.97√A` | Highest planning rate in the engine (74.5 % at ratio 0.9–1.1 in the 1440-scenario scan), shortest corridors, cheapest envelope | Least frontage; least differentiated from the alternatives | Yes — whenever it fits. It is the engine's first choice (`PREFERRED_RATIOS[0]`). |
| **Along the street** (wide, ratio ≈ 1.45) | Yes | Wide, shallow plots; deep front setback or parking band eating the depth; a person who wants a long street facade | `BW ≥ 1.2√A`, `BD ≥ 0.83√A` | Front-band and hub organisations need width, so this shape is where those partis appear; every room can reach the front or rear envelope | Planning rate drops above ratio 1.3 (the scan's 3-bed + safe-room briefs failed 66/66 above it); bedrooms get shallow rows | Yes when feasible; hidden (not greyed) when `feasible_options` clips it onto the compact shape. |
| **Deep** (narrow, ratio ≈ 0.75) | Yes | Narrow plots and semi-detached lots; a person who wants a rear garden the full plot width | `BW ≥ 0.87√A`, `BD ≥ 1.16√A` | Fits the commonest narrow parcel; long garden edge | Only the spine organisation works at this ratio — one long corridor, the measured #1 quality gap (hall long/short median 9.4) | Yes when feasible; same clipping rule. |
| **L-shape** | **No** — the safe adapter decomposes an L region and Geometry Core supports two wings with seams, but the generator cannot author a two-wing fixture (`MULTI_WING_SPLIT` is always declined) | Corner or wide plots; a person who wants an entry court or a sheltered terrace; 13 of the 21 professional reference plans are non-rectangular | Needs the plot to hold a rectangle of ≈ 0.6 A *plus* a second wing sharing a full side | Real architectural variety; front court for parking and entrance; bedrooms in their own arm | Circulation must cross the seam through a hall, not a bedroom (the L2 finding); entrance/parking rules assume one straight street wall; ~2× the engine surface | **Not in the UI until the generator produces it** (Phase 3). Showing an L card that always fails is the 006 failure mode again. |
| **U / courtyard** | No | Large plots (frontage ≳ 20 m), three wings, a ring corridor | — | Privacy, an inner garden | Rare for the private-house sizes in the log; 2 of 21 references; needs ring circulation the engine has no representation for | **Not recommended.** Revisit only with demand evidence. |

### B.2 Organisation (how the rooms are grouped inside the outline)

| Family | Engine today | When it fits | Pros | Cons | Offered automatically? |
|---|---|---|---|---|---|
| **Public wing beside the bedroom wing** (spine: public column · hall · private column) | Yes — `SPINE_*`, `BRANCHED_TWO_STACK` | Any shape; the only organisation that plans at the deep ratio | Clear public/private split; living room gets a side and one end of the envelope | Long straight corridor; public rooms come out as strips (kitchen aspect 2.75 median) | Yes; it is what most plans are today. |
| **Living across the front, bedrooms behind** (front band) | Yes — `FRONT_PUBLIC_BAND` (≥ 2 public rooms, ≥ 3 private rows) | Compact and wide shapes; larger programmes (this is the parti that unblocks 4–5 bedrooms) | Whole rear depth for bedrooms; front door opens into the living space | Living room faces the street, not the garden; needs width | Yes when it plans. |
| **Bedrooms around a compact lobby** (hub) | Yes — `HUB_PRIVATE_WING`, ≥ 3 bedrooms | Compact and wide shapes, 3+ bedrooms | The reference-plan topology (18/21): short circulation, wet rooms clustered at the lobby head | Loses the area-proximity sort in some briefs (a live product decision, 005 §11c); bedroom proportions miss the gate narrowly on wide-shallow outlines | Yes when it plans. |
| **Living to the garden** (public band at the rear) | **No** — every parti puts the public zone left or front | Deep plots with a good rear garden; the commonest client wish | — | Front door must reach a hall that passes the bedroom wing — a new parti | Not in the UI until it exists. Reserve `preferred_open_side` for it. |

**Why not more**: five of the six spine strategies realise to the same tree; naming them separately to the person would be offering one house under five names (memory: `SPINE_SERVICE_CLUSTER` is byte-identical to `SPINE_DOUBLE_LOADED` in 66/77 co-occurrences). Three shapes × three organisations is the whole honest vocabulary, and the person sees only the combinations that actually planned for their brief.

---

## C. Exact UX flow

Screens are named as they exist in `frontend/src`.

```
1  Brief form (App.tsx)                          unchanged inputs: city/street, plot w×d,
   ─ site facts + free text                      street side, setbacks, built area, description
   ─ [advanced ▸ manual outline]                 unchanged (authoritative when used)

2  Review (ReviewPage.tsx)                       unchanged; shows "מתאר: ייקבע אוטומטית"
                                                 + one line: "פריסה: אוטומטית" (or the saved pick)

3  Generate                                      engine plans every feasible outline (as today),
   ─ progress per outline                        PREFERRED outline first when a preference exists

4  Results (DemoWorkspace.tsx)                   large plan + up to 3 labelled thumbnails (as today)
   ─ each card labelled twice:                   "קומפקטי · 12.95 × 13.59 מ׳" and
                                                 "סלון לחזית / אגף שינה בצד / מבואת חדרים"
   ─ chip row above the drawing:
       [↔ הפוך צד]            mirror — instant, client transform of the whole site plan
       [⟲ סובב לאורך/לרוחב הרחוב]  swap to the perpendicular outline's plan from the pool — instant;
                              disabled with a reason when no plan exists on that outline
       [סידור אחר]             next family in the pool — instant; disabled when the pool has one
       [אגף שינה נפרד]         prefer organisation = spine or hub → swap if present, else regenerate
       [סלון פתוח יותר]        sets open_plan = true (a requirement edit, existing field) → regenerate
   ─ [✓ בחר/י פריסה זו]        saves LayoutPreference {shape, organisation, mirrored} + creates the
                              active design version (existing versioning) — this is the "select one"
   ─ compass now shows the real north from street_facing_side; street edge labelled "רחוב"
   ─ view toggle [צפון למעלה / רחוב למעלה]  visual only, never sent

5  Later edits (chat, settings, review)          regenerate → the saved preference orders the search
                                                 and the display; if the preferred family/outline no
                                                 longer plans, the FR-008 note pattern says so once
```

What is deliberately **not** in the flow: an abstract shape picker before generation (Phase 2 option, see E), drag or resize of rooms, a free rotation handle, a door-position tool, a polygon editor.

**Why "select after generation" and not "select, then generate"**: the brief's proposed order (site → recommend 3–4 → select → generate) requires the engine to know which layouts are feasible *before* planning, and this engine only knows by planning. Since it already plans all outlines in one request and shows three by family, the recommendation step and the generation step are the same step. The person still gets exactly the interaction asked for — choose one, flip it, turn it — but on plans that are already proven.

---

## D. Technical architecture and data model

### D.1 Where each piece belongs

| Layer | Change | Not changed |
|---|---|---|
| **UI** (`DemoWorkspace`, `SketchSvg`/`ArchitecturalFloorPlan`, `ReviewPage`, `App`) | Chip row; family/shape labels on cards; mirror rendering (transform on the whole site plan, including parking and the entrance walk); compass from `street_facing_side`; view-rotation toggle; the pick action | `FootprintSelection` (advanced path) stays as is |
| **API** (`projects/models.py`, `demo/contract.py`, `demo/router.py`, `chat/intent.py`) | `Project.layout_preference` (create / update / review-edit); `DemoDesign.shape`, `DemoDesign.organisation`, `DemoDesign.plan_key`; the full validated `pool` (or a server cache keyed by project + request) so chips are instant; chat intent `SET_LAYOUT_PREFERENCE` → proposal → the existing `apply_project_update` | The `selected_footprint` contract and its authoritative semantics |
| **Demo service** (`demo/service.py`) — *this is where the feature lives* | `_outlines_for`: preferred shape first (order 0 after any PERSON outline); `_select_plans`: preferred `(shape, organisation)` first when present, then today's family-diversity rule; mirror applied in `_result_from`; the "preferred could not be planned" note | The per-outline `run_general` call and everything below it (006 FR-012 spirit) |
| **Concept / massing** (`concept_generator.py`) | **Nothing in the MVP.** Phase 2 may pass a `prefer_strategy` that only re-orders `accepted` (a sort key) so a hub or band candidate that loses the area-proximity sort by a few m² can still surface — this is the 005 §11(c) decision, taken deliberately, not as a side effect | Partis, forced cuts, room templates |
| **Geometry solver / validation** | Nothing. Mirror is a transform on realised rectangles; because the plot is a rectangle with equal side setbacks, mirroring the whole site plan preserves every check (C1–C18). Re-run `validate` on the mirrored design anyway — it is cheap and makes the invariant a test rather than an argument | — |
| **Semantic / Spatial Architect** (`app/architect`, `projects/preferences.py`) | The layout preference is a *structured* field beside `Preference`, not a free-text preference; chat maps phrases onto it ("put the bedrooms on the other side" → `mirrored`, "I want the living room along the street" → `organisation = PUBLIC_FRONT`, "turn the house" → `shape` axis swap) | The advisory `Preference` model stays advisory |

### D.2 Authoritative, preference, or "try first"?

**Preference, implemented as "try first, then offer alternatives".** Concretely:

- The preferred outline is planned first (and streamed first once the deferred SSE preview lands), but every feasible outline is still planned — the 142 rescues in 006 came from planning everything.
- The preferred family/outline is shown first *when it produced a validated plan*; otherwise the primary is today's nearest-area plan and one note says the preference could not be met. No refusal is ever caused by a preference.
- The only authoritative input stays the advanced explicit outline. If a person truly must have a 15 m frontage, that path exists and is byte-identical to today.

Why not authoritative: the measured 30 % vs 35–45 % planning rate for person-chosen outlines, and the fact that organisation choice is bounded by the programme (hub needs ≥ 3 bedrooms, band needs ≥ 2 public rooms and ≥ 3 private rows) — a binding choice would refuse briefs that plan fine.

### D.3 Minimal data model

```
LayoutPreference                      # Project.layout_preference: LayoutPreference | None
  shape:        AUTO | COMPACT | ALONG_STREET | DEEP      # maps to PREFERRED_RATIOS bands via shape_name()
  organisation: AUTO | PUBLIC_SIDE | PUBLIC_FRONT | HUB   # maps to ConceptStrategy groups
  mirrored:     bool = false                              # left/right flip of the whole site plan
  source:       PICKER | CHAT | SETTINGS                  # provenance, like every other field
  chosen_plan_key: str | None                             # the exact plan the person picked, if any

DemoDesign (+)                        # response, all optional and defaulted
  shape:        COMPACT | ALONG_STREET | DEEP             # derived from outline via shape_name()
  organisation: PUBLIC_SIDE | PUBLIC_FRONT | HUB          # derived from ConceptStrategy
  mirrored:     bool
  plan_key:     str                                       # hash(outline w×d, layout_signature)

DemoPlanSet (+)
  pool: list[DemoDesign]                                  # every validated plan of every outline,
                                                          # so "turn"/"another arrangement" are swaps
```

Fields from the brief that are **deliberately rejected or deferred**:

| Proposed field | Decision | Why |
|---|---|---|
| `rotation` (degrees) | **Rejected as a planning input.** Replaced by `shape` axis + `mirrored`; a `view_rotation` lives in UI state only | The street wall fixes the front; 90° = the other outline axis (already a shape), 180° = entrance at the rear (forbidden by C10/C11/C16), other angles = no representation |
| `entry_side` | **Deferred**, implicitly `STREET` | One street side per plot today; becomes real with corner plots |
| `public_private_orientation` | **Kept as `organisation`** (PUBLIC_SIDE / PUBLIC_FRONT / HUB) | Names the three partis the engine has; left/right is `mirrored` |
| `preferred_open_side` | **Deferred** | Garden is always the rear yard and no parti faces it; the field would be a promise the engine cannot keep until a "living to the garden" parti exists |
| `layout_family` | **Split into `shape` + `organisation`** | Outline shape and internal organisation are independent in this engine (006 §1) and the person can want either |

---

## E. MVP vs later phases

### MVP — no concept-generator change, measured on the failure-log sweep before and after

1. Fix the compass and label the street edge (`street_facing_side` → true north on the drawing). A defect, independent of the rest.
2. `LayoutPreference` on the project; `shape`/`organisation`/`mirrored`/`plan_key` on the response; full `pool` in the plan set.
3. Results-screen chips: flip, turn, another arrangement, pick. Disabled chips carry the reason ("no plan exists on the wide outline for this brief").
4. Service-side ordering: preferred outline planned first, preferred family shown first, the note when it cannot be.
5. Mirror as a whole-site-plan transform with validation re-run.

Gates, on the 426-brief log with `outline_ab.py`: 0 primaries change when no preference is set; 0 plans shown that fail validation; the share of briefs where "turn" has a target and where "another arrangement" has a target — both must be *measured and reported*, since they bound how often the chips do anything.

### Phase 2 — steer the search, with the generator still frozen

- Optional preference chips on the brief form, driven by `feasible_options` (instant, geometric — never a promise that the shape will plan). Default "let the engine choose".
- `organisation` chips ("bedrooms in their own wing", "living across the front") and the chat intent that sets them.
- `prefer_strategy` sort key in `generate_concepts` so a preferred parti that lost the area sort by a small margin surfaces — the 005 §11(c) decision made explicitly.
- The deferred 006 Part C SSE preview, so the preferred plan appears in ~1.5 s while the rest are planned.

### Phase 3 — new engine vocabulary (each its own spec, measured like 005/006)

- **L-shape**: the generator authors a two-wing fixture on the safe adapter's L decomposition; entrance and parking rules extended to a front court. Only then does an L card appear.
- **Living to the garden**: a rear public band parti; unlocks `preferred_open_side`.
- **Corner plots**: two street sides; `entry_side` becomes a real field.

### Not planned

U/courtyard outlines; free-angle rotation; drag/resize editing; polygon outlines in the main flow.

---

## F. Risks and trade-offs

1. **The chips can only expose what the search found.** Each preferred ratio plans in 35–45 % of briefs, so "turn along the street" will often have no target; the generator's two tree shapes mean "another arrangement" will often be disabled. Mitigation: disabled with a reason, never silent; and say plainly that diversity is generator work (hub, forced cuts), not picker work.
2. **Mirror moves the driveway.** Bays sit at the west side setback today; a whole-plan mirror puts them on the east. That is precisely what makes mirror useful (the kerb cut is usually fixed by the street), but a house-only mirror would put the entrance walk over the bays and fail C11 — the transform must include the site plan.
3. **Preference vs the nearest-area rule.** Showing a preferred family first can show a smaller house first. Recommendation: when the person picked explicitly, show it first and label its area; in AUTO the 006 rule (nearest area, ≥ 0.95 median) stands untouched.
4. **Latency**: unchanged at 3–6 s per request; preferred-first ordering plus the SSE preview is what makes it feel fast. Pool-in-response grows the payload (4 outlines × up to 4 plans); a server cache keyed by project and request hash is the alternative if it matters.
5. **Labels the person can read**: `family_signature` is an internal string. The user-facing `organisation` must be derived from `ConceptStrategy`, and thumbnails need the public zone tinted or the labels will not be believable.
6. **A saved pick can go stale**: after "change 3 bedrooms to 4" the picked family may no longer plan. Handled by the same note pattern, but it must be tested with the log, not assumed.
7. **Scope pressure toward an editor.** Every chip here maps to one stored field or one swap. The moment a request needs a coordinate (move this wall 40 cm), it is out of scope for this feature and belongs to the spatial-edit path that already exists (`MOVE_ROOM`), which is a different product surface.
8. **The compass defect is shipping today** for three of the four street sides. It should be fixed regardless of whether the rest of this proposal proceeds.
