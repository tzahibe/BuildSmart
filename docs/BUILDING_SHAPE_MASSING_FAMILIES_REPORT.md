# Building Shape / Massing Families — Architecture and Engine Impact

**Date**: 2026-09-15 · **Status**: research only; nothing implemented · **Base**: `main` @ `2a00c0f`; companion to `MULTI_LEVEL_AND_HOUSE_CONCEPT_ARCHITECTURE_REPORT.md` (whose Phase 0 is on branch `010-multi-level-phase0`) and `LAYOUT_SELECTION_UX_RESEARCH_REPORT.md` §B.1.

**Question**: how should the engine support genuinely different building *shapes* — not only different room arrangements inside one rectangle — without turning shape into a hard user-selected enum that forces geometry?

Everything below is read from the code or measured by running it this session (E1–E3).

---

## 0. Verdict up front

| | |
|---|---|
| **Honestly supported today** | Three rectangle proportions (compact ≈ 0.95–1.15, wide ≈ 1.45, deep ≈ 0.75), chosen by the engine from `PREFERRED_RATIOS` and planned with three internal organisations. That is the whole shape vocabulary the product can show without lying. |
| **Producible by the core, not by the generator** | **The L (two wings).** The adapter already decomposes an L region into two adjacent rectangles with 100 % retention (E1); the frozen Geometry Core solves a two-wing fixture with a declared seam in one iteration (E2, the spike's F2 pattern re-run on production types); the generator then declines every L with `CIRCULATION_WOULD_CROSS_PRIVATE` — an objection F2 answered in 2026-09-08 with a forced cut (E3). The gap is one parti plus the single-footprint assumptions downstream (§3.3), not the solver. |
| **Needs new representation** | T / three-wing (two seams, a junction hub), stepped massing in plan (offset rectangles = wings again), and every shape whose circulation is a *ring* (U, courtyard): the open-marking mechanism joins only tree siblings, so a bent or closed corridor is not representable — the spike's L1 limitation, still true. Irregular footprints are already *decomposed* by the adapter; what is missing is planning across ≥ 3 pieces and classifying the residuals. |
| **The architecture** | Shape is **never an input to geometry**. `MassingPreference` (soft) → **massing candidates** (rectangle proportions today; primary + arm tomorrow) → **decomposition** into wings (the adapter, already) → **per-wing, per-level planning** (today's `run_general` with a wing list and seams) → **building validation** → **ranking grouped by massing family**. The only authoritative geometry stays the "advanced" outline. |
| **Multi-level** | Yes: `Massing.level_outlines_m: tuple[RectM, ...]` (one rectangle per level, Phase 0) should become `LevelMass.regions: tuple[RectM, ...]` — one rectangle per **wing** per level — *before* a second level or a second wing exists, so the two features do not fight over the same field. Rectangle lists, not polygons: Geometry Core consumes rectangles and the adapter produces them. |
| **UX** | Shapes are *labels the engine attaches to plans it produced*, plus an optional soft preference that orders the massing candidates. Show a shape before generation only when a geometry-free pre-check says a candidate of that family exists for this site and program — never an L card that always fails (the 006 failure mode). |

### 0.1 Evidence (this session)

- **E1 — adapter on the L site** (`geometry_fixtures.l_shaped_site`, 18 × 16 m envelope with a 5 × 6.5 m notch): outcome SOLVED, authoritative 255.5 m², solver 255.5 m² (retention 1.0), candidates `0: 13.0 × 16.0 m (208 m²) adjacent=(1,)`, `1: 5.0 × 9.5 m (47.5 m²) adjacent=(0,)`. The decomposition and the adjacency the generator would need already exist.
- **E2 — the production core solves two wings with a seam.** The spike's F2 L-house (wing A 8 × 12 with `HALL` against the seam over a forced 8.5 m cut and `DINING` below it; wing B 4.5 × 8.5 with `seam_leaf_sides` on every west side) re-expressed in `app.vertical_slice.geometry_core.model` types: solved in **1** wall iteration, footprint 134.25 m²; `HALL` E = `PARTITION` (seam, not exterior), `MASTER` W = `PARTITION`, `DINING` E = `EXTERIOR` below the arm. Nothing in the engine stops an L.
- **E3 — the generator's refusal is the objection F2 already answered.** `_multi_wing_assessment` on E1's candidates: `CIRCULATION_WOULD_CROSS_PRIVATE: seam covers 9.5 m of the primary wing's 16.0 m side, so a hall column against it would be part exterior and part seam`. That is the L2 finding verbatim — and L2's resolution (spike README) is a forced cut so the hall spans *exactly* the seam and a full-width room takes the rest of the depth, which is what F2's `fixed_m=8.5` does. The assessment is conservative to the point of declining the proven pattern.
- From the earlier reports, kept as inputs: 13 of the 21 professional reference plans are non-rectangular (L/T/cross/angled); each rectangle ratio's planning rate (74.5 % at 0.9–1.1, 52.5 % at 1.1–1.3, 16–19 % at the extremes; 3BR + ממ"ד failed 66/66 above ratio 1.3); outline choice does not switch parti — the generator does.

---

## 1. Shape catalogue

Legend for "requires": **outline** = a different rectangle only · **parti** = a new internal organisation inside one rectangle · **wings** = ≥ 2 connected rectangles with seams · **massing** = a decomposition decision above the wing level.

| Shape | Architectural situations | Producible today? | Requires |
|---|---|---|---|
| **Compact rectangle / square** (ratio ≈ 1) | Default; small and medium plots; shortest circulation; cheapest envelope | **Yes** — `PREFERRED_RATIOS[0]`, highest planning rate | outline (exists) |
| **Wide rectangle** (along the street, ≈ 1.45) | Wide shallow plots; deep front setback or parking band eating the depth; long street facade; where the front-band and hub partis appear | **Yes** — clipped by `feasible_options` where it does not fit | outline (exists) |
| **Deep / narrow rectangle** (≈ 0.75) | Narrow and semi-detached lots; a rear garden the full plot width | **Yes** — only the spine parti plans it (one long corridor: the measured #1 quality gap) | outline (exists) |
| **L-shaped** | Corner plots; a notched/irregular buildable region (E1); an entry court with parking in the crook; a sheltered terrace; **living to the garden** (the commonest client wish, unreachable inside one rectangle because every parti puts public west or front); bedrooms in their own arm | **Core yes, generator no** (E2/E3) | wings (2, one seam) + one parti (hall against the seam) + downstream footprint generalisation |
| **T-shaped / three-wing** | Large programmes (5–6 BR); two private arms off a public bar; a hub where the arms meet | No | wings (3, two seams) + a junction parti (the hub lobby *is* the junction) + massing |
| **Stepped massing** | In plan: a public bar stepped forward of the bedroom bar (a front court beside the entrance); in section: an upper level retreating from the ground (terrace) | In section **already modelled** in Phase 0 (`Massing.retreat_m2`, V2); in plan **no** — two offset rectangles are two wings | plan: wings; section: per-level outline (exists as a type) |
| **Courtyard / U** | Large plots (frontage ≳ 20 m); privacy; an inner garden; three wings and a ring or double-bent corridor | No, and not soon | ring circulation the tree cannot express (spike L1) — a Geometry Core representation change |
| **Irregular polygonal buildable footprint** | Real parcels (13/21 references); curved or angled facades; obstacles | **Decomposed yes, planned no**: the adapter yields up to 4 rectangles + classified residuals and the pipeline plans the largest (`test_l_shape_used_a_wing_rather_than_the_whole_bounding_box`) | massing across ≥ 2 candidates (the L/T machinery), plus residuals classified as terrace/garden |

### 1.1 Per-shape effects on the ten aspects

Read across: what changes in each planning concern when the shape changes. "—" = same as one rectangle.

| Aspect | Wide / deep rectangle | **L (two wings)** | T / three-wing | Stepped (plan) | U / courtyard |
|---|---|---|---|---|---|
| **Room allocation** | — (columns get shallower/deeper; wide unblocks the band and hub) | Rooms are allocated to *wings* first, then to columns inside a wing: the arm is a natural bedroom wing (F2) or the public wing turned to the garden | Public bar + two private arms; one arm can be the master suite | Public bar forward, private bar behind, offset | Three wings around a court; allocation by side |
| **Public/private zoning** | — | Zoning becomes a wing property: public wing / private wing, with the seam as the threshold — cleaner than a column boundary | The junction is the public/private threshold | The step is the threshold | Court-facing vs street-facing |
| **Circulation** | Deep = one long spine (aspect ~9); wide = band/hub possible | The hall must **span exactly the seam** (L2) and end there; rooms beyond the seam's length in the primary wing are reached from the hall's end. A *bent* corridor across the crook is not representable (L1); the F2 pattern avoids it | Two seams need either two hall segments joined as an open group (F4's `HALL_MAIN`/`HALL_SPUR` mechanism, proven) or a lobby at the junction (the hub) | Same as L | Ring — not representable |
| **Entrance** | — (street wall) | In the crook when the arm is at the front (an entry court, parking in the court); `resolve_entrance` must accept the primary wing's street wall *or* the arm's — today it reads one footprint rect | At the bar's centre or the junction | In the re-entrant corner | Through the court |
| **Stairs** | — | The stair belongs in the wing that has the hall — the seat search of the multi-level report is unchanged, per wing | Beside the junction hub — the U-stair's natural place | As L | — |
| **Wet rooms** | Wide: wet cluster at the lobby head (hub) | An arm of bedrooms puts the shared bath at the arm's end or next to the seam; the ensuite stays with its bedroom; a service wing (laundry/store) is the classic short arm | Wet rooms cluster at the junction (one plumbing core for two arms) | — | — |
| **Daylight / windows** | Deep: rooms at the column ends only | **Every room gains a second exterior wall** (the arm has three exposed sides); this is the strongest argument for the L | As L, more so | Re-entrant corners give two-sided rooms | Court-facing windows |
| **Garden relationship** | Deep: full-width rear garden | The crook is a sheltered terrace/garden; a public wing turned to the rear gives *living to the garden* | Two crooks: front court + rear terrace | Front court | The garden IS the court |
| **Multi-level alignment** | — | Upper level may be the bar only (arm single-storey = a roof terrace over the arm), or both; the stair must be in a wing present on both levels | The upper level is usually the bar or one arm | — | — |
| **Upper-floor retreat** | Per level, one rectangle (Phase 0) | Per **wing** per level: retreat the arm, keep the bar — needs `LevelMass.regions` (§4) | Same | Same | — |

---

## 2. What each shape requires of the engine

### 2.1 Rectangles — outline only, already done

All three are `feasible_options` clipping `PREFERRED_RATIOS` into the buildable rectangle; the demo already plans all that fit and shows up to three by family. Nothing to build; two things to *expose*: the shape label on each plan (`shape_name` exists in `site_geometry`) and an optional `MassingPreference.family` that moves one ratio to the front of the order (the `LayoutPreference` the layout UX report specified). No new geometry.

### 2.2 L — two wings, one seam: a parti plus a footprint generalisation

What the generator needs (all inside `concept_generator`, additive):

1. **Accept two candidates.** `generate_concepts` plans `usable[0]` only; `_multi_wing_assessment` declines the pair. Replace the blanket refusal by a **seam-hall parti** with F2's construction: primary wing tree `H( V(public, HALL), rest )` with the H cut *forced at the seam length* so `HALL`'s seam side is entirely seam; arm tree = a room stack whose every seam side is declared in `seam_leaf_sides`; access edges `HALL → arm rooms` cross the seam. The existing L2 machinery (`Split.fixed_at_u`, `Wing.seam_leaf_sides` in the core) does the rest; the spike's seam proof P9 (`spikes/geometry_core/validate.py`) is NOT in production `validation.py` and must be ported as a C-check. Two allocations, mirroring today's: arm = private (F2) and arm = public turned to the rear (living to the garden).
2. **Minimum-width and area accounting per wing**, not per building: `minimum_footprint_width_m` sums public + hall + private for one rectangle; a wing has its own.
3. **Rejection reasons of its own** (`ARM_TOO_NARROW`, `SEAM_TOO_SHORT_FOR_HALL`, …) so refusals name the wing.

What the **downstream** single-footprint assumptions need — this is the larger half, and it is the same list an upper level with a different outline would hit:

| Anchor | Assumes | Becomes |
|---|---|---|
| `general_pipeline._realize` — `wing = concept.fixture.wings[0]`; `footprint = Rect(wing…)` | one wing | the union of wing rects (`MultiRect`) |
| `site.SitePlan.footprint: Rect`; `classify_garden(plot, footprint, parking)` bands around one rectangle | one rectangle | garden = plot − Σ wings − parking (the adapter's boolean machinery already does region differences) |
| `doors.resolve_entrance` — `rect.y == footprint.y` | one street wall | any wing's street-side wall; the crook when the arm is forward |
| `geometry_adapter.envelope_sides(rect, footprint)`; `windows._widest_exterior_side` | exposure = touches the one footprint rect | exposure = touches *any* wing's outer side and is not a seam (the core's `WallMap` already knows: read `EXTERIOR` from the solved walls, or test against the union) |
| `validation` C2 `site.footprint.w * site.footprint.h` | one rectangle's area | Σ wing areas |
| `design_output.GeometricDesign.footprint_m`, `gross_area_m2 = fixture.footprint_area_m2()` (already sums wings) | one rect | `footprint_m` → `footprints_m: tuple[RectM, ...]` (keep `footprint_m` as the bounding box for compatibility) |
| `demo/contract.DemoDesign.footprint`, `_wall_segments` (per-room-side; general) | one rect for the drawing | `footprints[]`; segments unchanged |
| `frontend DemoPlan.planViewBox`, `<rect className="demo-footprint">` | one rect | frame on the union; draw each wing |
| `general_pipeline._family_signature` — `fixture.wings[0].tree` | one tree | one signature per wing joined |
| `demo/service._outlines_for`, `site_geometry.feasible_options` | rectangles of area A | massing candidates (§3.2) — this is where the new layer sits |

None of these is deep; each is a `Rect → tuple[Rect, ...]` generalisation with the single-rect case as `len == 1`. Their number is the cost. The renderer decoupling test and the "no canonical fixture reachable" test constrain how, not whether.

### 2.3 T / three wings, stepped in plan — wings again, plus a junction

Two seams on the bar. Either two hall leaves joined as one open group (F4's proven branching-hall mechanism — `HALL_MAIN`/`HALL_SPUR` are siblings, so the joint is straight, not bent) or the hub lobby *at the junction* with the arms as its flanks — which is the hub parti's own topology (public band in front, lobby, rooms on the flanks), so the T is closer to what exists than it looks. Stepped massing in plan is the L with the arm on the street side; no new mechanism. Cost above the L: a third candidate from the adapter (it yields up to `DEFAULT_MAX_CANDIDATES = 4`), two seams to align by forced cuts, and the allocation of a programme across three wings — the allocation stage the multi-level report proposes, extended from levels to wings.

### 2.4 U / courtyard, irregular — representation limits

A U needs circulation that turns two corners and (usually) closes; the open-marking mechanism recognises a wall-less boundary only between direct tree siblings, which are always axis-aligned rectangles of equal width/height (spike L1 and F4's honest limitation). Three straight hall segments meeting at two corners are *not* siblings. Two options, both Geometry Core changes: geometric open-interface discovery already exists for *non-sibling* zones that share a full edge (`_discover_open_interfaces`, iteration 2 of the bounded re-solve) — a corner joint shares only a partial edge; or a `CirculationNetwork` above the tree. Defer; revisit with demand (2/21 references).

Irregular footprints: the adapter's job is done — inner linearisation, rectangles per component, residuals with exposure flags. What is missing is planning across the candidates (§2.2–2.3) and *classifying* residuals: a residual with `has_exterior_exposure` beside the public wing is a terrace, beside the entrance a porch, elsewhere garden — a site-stage decision, never "leftover".

---

## 3. The architecture: preference → candidates → decomposition → planning → validation → ranking

### 3.1 Not an enum that forces geometry

A `shape: L` field that makes the generator draw an L is the footprint-selector failure in a new coat: it offers a shape before knowing it plans, and it turns an aesthetic wish into a hard constraint. The only geometry a person may fix stays the advanced outline (`selected_footprint`, 006 semantics). Everything else is a **preference that orders candidates** and a **label on results**.

```
MassingPreference (soft, on HouseConcept)         family: COMPACT | ALONG_STREET | DEEP | WITH_WING | ENGINE
                                                   garden_side: REAR | COURT | ENGINE      entry_court: bool | ENGINE
        │                                          arm_use: PRIVATE | PUBLIC | SERVICE | ENGINE
        ▼
massing candidates                                 rectangles: feasible_options (today)
                                                   L: primary rect + arm from the adapter's second candidate,
                                                      or an arm CARVED from a rectangular buildable region
                                                      (a rectangle minus a notch is still ⊆ the region — safe)
        │
        ▼
decomposition                                      the adapter: rectangles + seams (adjacent_orders) + residuals
        │
        ▼
per-wing, per-level planning                       run_general over a WING LIST with seam_leaf_sides and forced
                                                   seam cuts; the stair pinned in one wing (multi-level report)
        │
        ▼
building validation                                per-wing C1–C21 (as per level); seam realised (P9, already);
                                                   V-checks across levels; residuals classified (C12 already)
        │
        ▼
ranking grouped by massing family                  never one pool: an L that delivers 92 % with two-sided rooms
                                                   must not lose to a rectangle at 95 % on area proximity alone
```

`MassingPreference` belongs *on* `HouseConcept` (multi-level report §2.2): it is the same kind of thing — organisation, not requirement — and `public_open_side = GARDEN` is already there waiting for the parti that can honour it.

### 3.2 The massing candidate stage — where it sits

Exactly where `_outlines_for` is today (`demo/service.py`), generalised from "rectangles of area A that fit" to "massings of area A that fit": each candidate is a tuple of rectangles with seams. For a rectangular buildable region the candidates are today's four proportions **plus** (Phase 2) L massings *carved* from it: primary `w1 × d1` and an arm `w2 × d2` sharing a full side, with `w1·d1 + w2·d2 = A`. Carving an L from a rectangle is always safe (the union is inside the region) and is the honest way to offer an L on an ordinary plot — the notch becomes the entry court or terrace. For a non-rectangular region the adapter's own candidates are the massing. The survey/re-run split of 006 (`_plan_outlines_until_one_plans`) applies unchanged: survey each massing on the fast path, re-run the chosen one with alternatives.

### 3.3 Ranking

Group by `(massing family, story count)`, then by organisation family; area proximity *within* a group; one representative per group in the shown set before any repeat — the same pass `_select_plans` runs today for organisation families, one level up. Metrics reported per building (the multi-level report §10.2 list plus): two-sided habitable rooms (share with ≥ 2 exterior walls), exterior wall length per m² (envelope cost), garden contiguity, entry-court presence. None becomes a scalar objective.

---

## 4. Multi-level on `BuildingMassing → LevelMass[] → Wings/Regions[]`

Yes — and the time to change the type is **now**, before either a second level or a second wing exists. Phase 0 committed `Massing.level_outlines_m: tuple[RectM, ...]` — one rectangle per level. A second wing on one level has nowhere to go in that field, and a retreat that removes an *arm* but keeps the *bar* cannot be said as "one rectangle got smaller".

```
BuildingMassing
  plot_m
  levels: tuple[LevelMass, ...]                 index-aligned with Building.levels
LevelMass
  regions: tuple[RectM, ...]                    one per wing on this level; len == 1 today
  seams:   tuple[Seam, ...]                     (region_i, side, region_j) — the adapter's adjacent_orders, kept
  @property outline_m  -> bounding box          compatibility: what `level_outlines_m[i]` returns today
  @property area_m2    -> Σ regions             what V7 checks gross against (NOT the bounding box)
```

Consequences, each small: **V2** containment becomes "every upper region is inside the union of the level below" (per-rect containment in a union of rects); **V7** compares gross to Σ regions; **stair alignment (V1)** is unchanged (one rectangle, in one wing, present on both levels — now also "the wing it sits in exists on both levels"); **retreat** becomes per wing (drop the arm on L1: `retreat_m2` = the arm's area, classified terrace); **the site limits only `levels[0].regions`**. Rectangle lists rather than polygons because Geometry Core consumes rectangles, the adapter emits rectangles, and every check above is a rect-set operation; a polygon would have to be re-decomposed to be planned.

`Massing` as committed can gain `regions` without breaking anything: `level_outlines_m` stays as the bounding-box view. Recommended as the first commit of the L work *or* of multi-level Phase 1, whichever starts first.

---

## 5. What can honestly be shown today vs what needs new capability

| Claim on a card / label | Honest today? | Because |
|---|---|---|
| "קומפקטי" / "לאורך הרחוב" / "עמוק" (with the plan's real dimensions) | **Yes** — as labels on generated plans; as a *preference* that orders `feasible_options` | shapes already planned per request |
| "בית עם אגף" (L) | **No** | generator declines; downstream assumes one footprint |
| "סלון לגינה" | **No** | needs the L with a rear public wing, or a rear-band parti |
| "חצר כניסה" (entry court) | **No** | needs the L with the arm forward |
| "בית T / שני אגפי שינה" | **No** | three wings |
| "בית חצר / U" | **No**, and not planned | ring circulation |
| "מגרש לא מלבני" | **Partially**: the plan is placed in the largest safe rectangle and the rest is residual | planning across candidates missing |

---

## 6. Phased vocabulary

Regression gate for every phase: the 418-context sweep's `stories == 1`, single-wing primaries byte-identical; the frozen baseline and sample reports unchanged; the layout-report rule that no card is shown whose family cannot plan for this brief.

### Phase 1 — shapes already representable (labels + a soft preference)
- **Possible**: every plan labelled with its shape family and dimensions; `MassingPreference.family ∈ {COMPACT, ALONG_STREET, DEEP}` orders `feasible_options` and the shown set; the chip row of the layout UX report (turn along/across the street = swap to the perpendicular outline's plan). `LevelMass.regions` introduced with `len == 1` (§4) — a type change only.
- **Unsupported**: any non-rectangle; "living to the garden".
- **Byte-identical**: everything, when no preference is set.
- **New invariants**: a preferred family that did not plan is reported, never silently replaced.
- **Complexity**: low (service ordering + contract labels + UI). 1–2 weeks.
- **Measure**: how often a preferred family plans; delivered share by family.

### Phase 2 — L / two wings
- **Possible**: two-wing massings — from a non-rectangular buildable region (adapter candidates) and carved from a rectangular one; the seam-hall parti with two allocations (private arm; public arm to the rear = living to the garden); entry in the crook when the arm is forward; residual/crook classified as terrace or court; L plans in the pool, grouped as their own family.
- **Unsupported**: three wings; bent corridors; an arm on an upper level different from the ground's (until Phase 3 massing per level).
- **Byte-identical**: all single-wing primaries.
- **New invariants**: seam realised on both sides (the spike's P9, ported into `validation.py` — it is not there today); no leaf side part-exterior part-seam (the L2 forced cut, checked not assumed); every arm room reachable over the seam (C5 with cross-seam realized connections — already how `realized_connections` works since it reads rects, not trees); garden = plot − wings − parking with no overlap.
- **Complexity**: **medium–high** — the parti is a week; the `Rect → tuple[Rect]` generalisation across the ten anchors in §2.2 is the rest, and it is exactly the generalisation multi-level's upper outline needs, so do it once. 4–5 weeks.
- **Measure**: L candidates offered / planned / selected on the sweep; two-sided-room share and exposure on L plans vs the rectangle they replaced; delivered share (≥ 80 % of ask, as always).

### Phase 3 — T / stepped / multi-wing
- **Possible**: three-wing massings (bar + two arms) with the hub lobby at the junction or two hall leaves as one open group; stepped plan massing (= L with the arm forward, already) named as such; allocation of the programme across wings by the allocation stage; per-wing upper retreat (`LevelMass.regions` per level).
- **Unsupported**: rings; more than three wings; non-orthogonal wings.
- **New invariants**: two seams aligned; junction hub degree bound (the 008 gates, per junction).
- **Complexity**: medium once Phase 2 exists (the third candidate and the second seam reuse everything). 3 weeks.

### Phase 4 — courtyard / U / irregular
- **Possible**: only after a circulation representation that joins non-sibling hall leaves at corners (Geometry Core change: extend `_discover_open_interfaces` to partial-edge circulation joints, or a `CirculationNetwork` over the tree); irregular regions planned across ≥ 3 adapter candidates with residuals as terraces/porches.
- **Complexity**: high; demand evidence first (2/21 references for U; 13/21 non-rectangular overall, most of them L/T).

---

## 7. Showing shapes to the person

Two places, split by what the choice changes — the same rule as the multi-level report §9:

- **Before generation, as a soft preference (Phase 1+)**: one row of massing cards on the review screen — "קומפקטי", "לאורך הרחוב", "עמוק", and from Phase 2 "עם אגף" (with the two sub-wishes it exists for: "סלון לגינה", "חצר כניסה") — each a **schematic diagram** (site rectangle + a footprint blob), never a plan; each shown **only when a geometry-free pre-check passes** (the family's candidate fits the buildable region and the programme's minimum widths per wing — `feasible_options` and `minimum_footprint_width_m` per wing, no solving); "המנוע יחליט" first and default. The pick is a `MassingPreference`, recorded with provenance like every requirement, honoured by ordering, reported when it could not be planned. It is *not* a footprint: the advanced outline stays the only authoritative geometry, and choosing "עם אגף" never draws an L the engine did not prove.
- **After generation, as real plans**: every shown plan carries its shape family and dimensions ("עם אגף · 13.0 × 16.0 + 5.0 × 9.5 מ׳"); alternatives are grouped so a rectangle and an L for the same brief both appear; chips swap between families already in the pool. Recommendations ("על מגרש זה אפשר גם בית עם אגף — סלון לגינה") appear only when a candidate of that family *planned*, phrased as an offer.

What not to do: a pre-generation shape picker whose cards are not gated (006's 80 % of refusals); shape as a hard field; L thumbnails drawn as plans; a single ranking pool.

---

## 8. Risks and unknowns

1. **The `Rect → tuple[Rect]` generalisation** touches ten anchors and the frontend; it is the same generalisation multi-level's upper outline needs — do it once, with `len == 1` byte-identical, before either feature adds a second rectangle.
2. **Seam-hall geometry is tight**: the hall must span exactly the seam, so the arm's depth *is* the hall's length; a short arm (a 4.5 m service wing) gives a 4.5 m hall — fine for three doors, not for six. The parti needs arm-length bounds tied to the door count (the hub's degree logic).
3. **Carved L on a rectangular plot competes with the rectangle for area**: at equal area the L has more envelope and a shorter hall; ranking must not let area proximity decide (§3.3).
4. **Entrance in the crook** and parking in the court interact with the parking band (`front_band_m`, C10/C11/C18) which assumes bays along the street edge in front of one footprint.
5. **The `_multi_wing_assessment` refusal is load-bearing** in the sweep: removing it without the parti would push briefs into a candidate that cannot be planned; replace, do not delete.
6. **No demand signal in the log for shapes either** — the form has no shape field. The reference census (13/21 non-rectangular) is the only evidence; Phase 1's preference card is how the signal starts.

---

## 9. Recommendation

Treat shape as a **massing family the engine produces and labels**, ordered by a soft `MassingPreference` on `HouseConcept`, never as an input to geometry. Ship the rectangle labels and preference now (Phase 1, cheap, no geometry). Then build the **L as a parti over the adapter's two candidates** — the core already proves it (E2) and the generator's refusal is the one objection the spike solved (E3) — together with the single-footprint → rectangle-list generalisation that multi-level's upper outline needs anyway, introduced through `LevelMass.regions`. T follows from L with the hub as the junction. U/courtyard and irregular-region planning wait for a circulation representation and for demand.

*No implementation was started for this report; the E1–E3 scripts were session scratch and are not in the repository.*
