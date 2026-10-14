# E1 — Orientation as an explicit architectural concept dimension

**Hypothesis.** Architectural intent can influence geometry *before* room placement, rather than
being inferred after realization. Concretely: making the public zone's orientation an explicit
concept dimension, decided before any room is placed, changes the delivered building and raises
public-room garden frontage without weakening any validator.

**Result.** The hypothesis is **demonstrated, on one brief**. On B19 the rear-band plan passes all
27 validators, delivers the same 12 rooms, and moves public garden frontage from **0.0 m to
12.4 m** while moving wet-room garden frontage from **7.5 m to 0.0 m** and the arrival from the
living room to the hall.

**The acceptance criterion is not met.** It asked for ≥ 3 of 8 briefs. E1 reaches **1 of 8** — and
not because of orientation. The front-public-band parti, which E1 was scoped to mirror, **itself
plans on only 1 of 8 briefs**. The rear band produces a candidate exactly when the front band does:
8 candidates on B19, 0 on the other seven, with byte-identical refusal reasons. E1's reach is the
band parti's reach.

**Recommendation: conditional GO for Phase 1** — the direction is validated, the carrier is not.
See §8.

---

## 1. Requirement 5 first — where the garden actually is

The owner's instruction was explicit: *"Use the actual site geometry and garden orientation. Do not
assume that the rear of every building automatically represents the desired garden relationship."*

So this was measured before anything was implemented, from the real `SitePlan` of each delivered
plan (`site.classify_garden`'s own bands, classified by which side of the building they lie on):

| brief | plot | footprint | REAR band | side yards | dominant usable outdoor space |
|---|---|---|---:|---|---|
| B08 | 19 × 20 | 10.8 × 12.0 | 8.00 m / 152.0 m² | 4.10 m each | **REAR** |
| B20 | 19 × 20 | 10.9 × 12.0 | 8.00 m / 152.0 m² | 4.05 m each | **REAR** |
| B02 | 20 × 26 | 11.8 × 11.45 | 14.55 m / 291.0 m² | 4.10 m each | **REAR** |
| B11 | 20 × 26 | 11.9 × 14.05 | 11.95 m / 239.0 m² | 4.05 m each | **REAR** |
| B16 | 26 × 20 | 12.9 × 14.6 | 5.40 m / 140.4 m² | **6.50 / 6.60 m** | **REAR** (by area, not by depth) |
| B19 | 20.5 × 22.5 | 11.9 × 14.5 | 8.00 m / 164.0 m² | 4.30 m each | **REAR** |
| B06 | 21 × 32 | 12.9 × 13.75 | 18.25 m / 383.25 m² | 4.05 m each | **REAR** |
| B09 | 28 × 30 | 15.4 × 14.75 | 15.25 m / 427.0 m² | 6.30 m each | **REAR** |

The rear is the dominant outdoor space on 8/8 — so for this brief set "GARDEN" does mean the rear,
and that is a measurement, not an assumption. **B16 is the one caveat**: its rear yard is the
shallowest (5.40 m) and its *side* yards are actually deeper (6.50 / 6.60 m). It wins on area only.
On a plot like B16's, a side-facing public zone would be the better architectural answer, and E1's
two-value `STREET`/`GARDEN` vocabulary cannot express it.

The code reflects this: `PublicOrientation.GARDEN` names *the dominant outdoor space*, and the
implementation never hard-codes "south". Data: `data/garden-geometry.json`.

---

## 2. What was built

### 2.1 The dimension

`concept_spec.PublicOrientation` — `STREET` / `GARDEN` — plus a `public_orientation` field on
`ConceptSpec` and on `ConceptCandidate`, read by `concept_spec_of`. It is the first dimension in
that module that a builder actually reads (`EntranceSide` and `MasterPlacement` remain enums with
no field, as #186 measured).

### 2.2 `REAR_PUBLIC_BAND`

A new `ConceptStrategy`, produced by the *same* `_front_band_concept` function under
`orientation=GARDEN`. Not a copy: every sizing rule, access edge, zone spec, seam search, fallback
tier, quality tier and refusal is shared code. That is deliberate — it is what makes the two plans
comparable, and it is also why they refuse together (§6).

### 2.3 Why there is no `*_ENABLED` constant

The owner asked for "a default-OFF flag". It is a **parameter**, not a module constant:
`generate_concepts(..., public_orientation=PublicOrientation.STREET)`.

`tests/knowledge/test_capability_wiring_table.py` reads every module-level `*_ENABLED` constant off
**`origin/main`** and requires a matching row in `docs/PROJECT_STATE.md`. A branch cannot satisfy
that before it merges — add the row and the branch is red; omit it and `main` goes red on merge.
That tripwire is exactly what turned `main` red in #176. A default-off parameter is strictly more
reversible (it cannot be flipped globally at all), is invisible to production by construction, and
is the same shape `run_general`'s own `concept_engine_v2_enabled` override already uses.

### 2.4 The four orientation-dependent locations

#186 named three. There are **four**; the fourth was found during implementation.

| # | location | STREET | GARDEN |
|---|---|---|---|
| 1 | `_front_band_candidate`: the top split | `Split(Cut.H, band, rear, band_depth)` | `Split(Cut.H, rear, band, fh − band_depth)` |
| 2 | `_plan_front_band_at`: `_row_wall_allowances_m(rws, …)` | `(False, True)` | `(True, False)` |
| 3 | `_plan_front_band_at`: `_row_depths(… ends_exterior=…)` | `(False, True)` | `(True, False)` |
| 4 | `_daylight_order` / `_repartition_for` | `north_is_envelope=False` | `north_is_envelope=True`, **`south_is_envelope=False`** |

**#2 and #3 are the ones #186 missed**, and they matter: they decide whether each rear row's north
and south walls are exterior (0.25 m) or partition (0.10 m) thickness. Getting them wrong does not
crash — it silently mis-sizes every row in the rear columns.

**#4 is the one #186 flagged as the real work, and it was.** `_daylight_order` hard-coded that a
column's south end is always exterior (`i == last`). That is true of every parti on `main` and false
for a rear band. It is now a parameter defaulting to `True`. The fact that an *orientation*
assumption was baked into a *daylight rescue heuristic* is itself a small confirmation of #186's
diagnosis: this engine has no place to put an orientation decision, so one ended up here.

### 2.5 The preview

`?engine=e1_rear_band` on both demo endpoints, beside #181's existing `?engine=` values. It shows
the rear-band plan as the primary and the production plan as the first alternative, both drawn by
the real `DemoPlan`. There is **no silent fallback**: a brief whose band parti cannot be planned
returns `E1_REAR_BAND_NOT_PLANNABLE` carrying the generator's own refusal text (demonstrated below).

---

## 3. Regression tests

`backend/tests/vertical_slice/test_e1_public_orientation.py`, 9 tests:

| what it holds | how |
|---|---|
| the default generates no rear-band candidate | on a brief where the band plans and one where it does not |
| **asking for GARDEN leaves every existing candidate exactly as it was** | full identity tuple (strategy, class, rationale, areas, every tier flag, zone set) compared element-wise against the default run |
| `_daylight_order` is unchanged at its default | both `north_is_envelope` values, against the explicit `south_is_envelope=True` |
| the new parameter does the one thing it claims | with no south envelope, an at-risk row takes the north end; no row is lost or duplicated |
| the rear band realizes and validates | every public room's south edge is the building's south edge; the hall reaches the street; 27/27 validators and safety pass |
| the orientation reaches `ConceptSpec` | `GARDEN` for the rear band, `STREET` for the front band, same run |
| **the two orientations refuse together** | on B06 the recorded `(reason, detail)` for `FRONT_PUBLIC_BAND` and `REAR_PUBLIC_BAND` are asserted *equal* |

The second row is the acceptance criterion "byte-identical with the flag OFF", pinned where it could
actually leak.

---

## 4. Eight-brief before/after

`data/e1-measurements.json`. Production via `generate_demo_design`; E1 via the same entry point with
`rear_band_preview=True`. Both realized by the unchanged `_realize` and judged by the unchanged
validators.

| brief | rear candidates | result |
|---|---:|---|
| B08 | 0 | no rear-band plan |
| B20 | 0 | no rear-band plan |
| B02 | 0 | no rear-band plan |
| B11 | 0 | no rear-band plan |
| B16 | 0 | no rear-band plan |
| **B19** | **8** | **PASS — 27/27 validators, safety clean** |
| B06 | 0 | no rear-band plan |
| B09 | 0 | no rear-band plan |

### B19 — the comparison

| measure | production | E1 rear band | |
|---|---:|---:|---|
| validators | 27/27 | **27/27** | unchanged |
| rooms delivered | 12 | **12** | identical set — nothing lost |
| gross area | 172.55 m² | **179.80 m²** | 95.3 % → **99.3 %** of the 181 m² requested |
| **public-room garden frontage** | **0.00 m** | **12.40 m** | LIVING 7.05 + DINING 2.80 + KITCHEN 2.55 |
| **wet-room garden frontage** | **7.50 m** | **0.00 m** | both bathrooms off the garden |
| private-room garden frontage | 3.00 m | 0.00 m | |
| public-room street frontage | 11.90 m | 0.00 m | |
| **arrival room** | LIVING | **HALL** | entrance rank 1 → **0**, by production's own `_entrance_rank` |
| circulation area | 13.26 m² | 13.26 m² | **identical** |
| circulation aspect | 7.85 : 1 | **7.85 : 1** | **identical** |
| worst bedroom aspect | 2.04 | 2.04 | identical |
| rooms with no window | none | none | |
| **public rooms with a window ON the garden** | 0 | **2 of 3** (DINING, KITCHEN) | see §7.2 |

Room by room, E1:

| room | m² | garden frontage | street frontage | window side |
|---|---:|---:|---:|---|
| LIVING | 26.91 | **7.05** | 0.00 | **W — not the garden** |
| DINING | 10.92 | 2.80 | 0.00 | **S (garden)** |
| KITCHEN | 9.36 | 2.55 | 0.00 | **S (garden)** |
| HALL | 13.26 | 0.00 | 1.40 | — (entrance) |
| MASTER | 16.56 | 0.00 | **3.55** | N (street) |
| BEDROOM_1…5 | 13.78 ea. | 0.00 | 0.00 / 5.50 | W / E |
| BATH_1 | 8.40 | 0.00 | 1.95 | N |
| BATH_2 | 11.13 | 0.00 | 0.00 | E |

---

## 5. Visual comparison — the real `DemoPlan`

Rendered by mounting the product's own `DemoPlan` component on the real payload
(`frontend/src/design/audit-render.test.tsx`) and rasterising in Chrome with the product's own
stylesheets — the same method as the #179 audit. Nothing redrawn by a diagnostic renderer.

| figure | |
|---|---|
| `figures/B19__production.png` | public band on the **street**; entrance into the living room; both bathrooms on the garden |
| `figures/B19__e1-rear-band.png` | public band on the **garden**; entrance into the corridor; bathrooms off the garden |
| `figures/B06__production.png`, `B16__production.png`, `B09__production.png` | production only — E1 refuses on these three (§6), so there is no E1 plan to draw and none is invented |

The owner asked for B06, B16 and B09 side by side "wherever E1 is feasible". It is feasible on none
of them, and the refusals are reported rather than worked around.

---

## 6. Every refusal, precisely

Each is the generator's own recorded reason for the `REAR_PUBLIC_BAND` strategy, and in every case
it is **character-for-character identical** to the `FRONT_PUBLIC_BAND` refusal on the same brief.

### 6.1 Three briefs: an explicit guard (`INSUFFICIENT_WING_AREA`)

> `front band already absorbs surplus through its own elasticity; not combined with FLEX`

**B02, B06, B09.** These are exactly the three briefs whose requested area exceeds the programme's
own capacity (216 > 182, 312 > 193, 440 > 200 — #179's table), so `generate_concepts` adds a `FLEX`
zone. `_front_band_concept` refuses outright to plan with `FLEX`, with a reasoned comment: the band
already absorbs surplus through the public rooms' elasticity, and doing both once inflated a living
room to 59 m² against its 46 m² cap.

This is a **deliberate, defensible guard**, not a bug — and it is unrelated to orientation. It also
means the three briefs where the architecture report found the *worst* indoor/outdoor defect (B06's
master on the garden, B09's 54 m² unassigned block on the garden) are precisely the three E1 cannot
reach.

### 6.2 Three briefs: room shape (`ROOM_SHAPE_INFEASIBLE`)

> `BEDROOM_1 at 7.40 m wide in the rear west column has no depth that keeps its 2.5 aspect ratio and
> 2.6 m short side under its 14 m² preferred maximum`

**B20** (7.40 m), **B11** (6.10 m), **B16** (7.60 m). A full-width bedroom in a wide rear column
cannot simultaneously satisfy aspect ≤ 2.5, short side ≥ 2.6 m and area ≤ 14 m². Geometric, and
orientation-independent.

### 6.3 One brief: band width (`BAND_WIDTH_BELOW_MINIMUM`)

> `DINING would be 2.00 m wide in the front band, below its 2.6 m minimum`

**B08.** Three public rooms across a 10.8 m footprint leave DINING 2.00 m. Orientation-independent.

### 6.4 The preview refuses the same way

```
B19: preview OK — primary gross 179.8 m², public on garden ['LIVING','DINING','KITCHEN'], alternatives 2
B06: refused E1_REAR_BAND_NOT_PLANNABLE —
     REAR_PUBLIC_BAND/INSUFFICIENT_WING_AREA: front band already absorbs surplus through its own
     elasticity; not combined with FLEX
```

No silent fallback to the production plan, as required.

---

## 7. Architectural review — is it actually better?

The owner asked to be critical, and warned that a mirrored rectangular plan is not automatically a
good architectural concept. It is not. Taking the five questions in order:

### 7.1 Is the living area meaningfully connected to the garden?

**Partly — and less than the frontage number suggests.** The three public rooms hold 12.40 m of
garden wall, but only DINING and KITCHEN (5.35 m) have a window on it. **The living room has
7.05 m of garden wall and no opening on it at all** — its single window is on the 4.10 m west wall.

The cause is a **pre-existing production defect, found by this experiment**:

```python
# app/vertical_slice/windows.py:84
def _wall_length_u(rect: Rect, side: Side) -> int:
    return rect.h if side in (Side.N, Side.S) else rect.w
```

The axes are swapped. A north/south wall's length is the room's **width** (`rect.w`), not its height.
`_widest_exterior_side` then puts the room's one window on the *narrowest* exterior wall whenever a
room is wider than it is deep. Reproduced exactly:

```
room w = 7.05 m   h = 4.10 m
its SOUTH wall physically runs along x, so it is 7.05 m long
its WEST  wall physically runs along y, so it is 4.10 m long
_wall_length_u(S) = 4.10   <-- should be 7.05
_wall_length_u(W) = 7.05   <-- should be 4.10
=> widest exterior side chosen: W (the 4.10 m wall), not S (the 7.05 m garden wall)
```

This affects **every plan on `main`**, not just E1 — in B19's production plan the living room's
window is on the west wall for the same reason. It also mis-sizes every window, since the opening
width is computed as a fraction of the same wrong length.

**Not fixed here.** Fixing it changes window geometry on every plan, which would break E1's
"production byte-identical with the flag OFF" criterion. It is a one-line change that deserves its
own change, its own snapshot diff and its own review.

**So the honest answer to the owner's question is: E1 gives the public rooms the garden wall; a
separate one-line defect is what currently stops the biggest of them from having a window on it.**

### 7.2 Is the entrance sequence logical?

**Yes, and measurably better.** Production arrives directly into the living room (entrance rank 1).
E1 arrives into the hall (rank 0) — the rank production's own `_entrance_rank` prefers, and the one
#142O shipped a whole selection change to obtain. Here it falls out of the concept for free, because
a rear band puts the circulation column on the street elevation.

This is the strongest *structural* result in E1: the concept decision produced a better arrival
without anything downstream optimising for it.

### 7.3 Are bedrooms private and appropriately exposed?

**Mixed — a real trade-off, not a win.** Every bedroom keeps a window; none is landlocked. But:

- the **master bedroom moves to the street** (3.55 m of street frontage, its window facing N). In
  production it sat mid-plan with a west window. Trading a quiet interior position for a street-
  facing one is not obviously an improvement, and for a master bedroom it is arguably a regression;
- **BEDROOM_3 gains 5.50 m of street frontage**;
- the worst bedroom aspect is 2.04 in both plans — unchanged.

E1 improves the *public* side of the indoor/outdoor relationship by pushing the private side toward
the street. On a quiet plot that is the right trade; on a busy road it is not. **The system cannot
represent that distinction**, which is the same gap in a new place.

### 7.4 Are bathrooms still consuming valuable garden frontage?

**No — and this is a clean win.** 7.50 m → 0.00 m. Both bathrooms move off the garden elevation
entirely; BATH_1 takes the street, BATH_2 goes interior-east. This is the single defect #186 called
"architecturally backwards", and on this brief E1 removes it completely.

### 7.5 Does the layout feel deliberately organized, or is it merely a reversed room-packing pattern?

**It is a reversed room-packing pattern.** This must be said plainly:

- the circulation is **bit-for-bit the same**: 13.26 m², 1.30 × 10.20 m, aspect 7.85 : 1. The house's
  entire circulation system is still one full-depth slot;
- the room set, the row structure, the column seam and the worst bedroom proportion are unchanged;
- nothing about the *organisation* of the plan is different. One axis was flipped.

What E1 proves is narrower and more important than "better plans": **an explicit concept dimension,
decided before room placement, propagated correctly through sizing, realization and validation and
changed the building in the way it was supposed to.** That is the hypothesis, and it holds. It is
not a claim that the resulting plan is architecturally strong. It is the same packing, oriented
correctly — which is worth having, and is not the same thing as architectural intelligence.

---

## 8. Recommendation — conditional GO

**Against the stated acceptance criteria:**

| criterion | result |
|---|---|
| ≥ 3 of 8 briefs produce a valid REAR_PUBLIC_BAND plan | ❌ **1 of 8** |
| all existing validators pass for those plans | ✅ 27/27, safety clean |
| public-room garden frontage > 0 | ✅ 12.40 m |
| no requested rooms lost | ✅ same 12 rooms |
| no invalid entrance, daylight or access relationships | ✅ arrival improves; every room keeps a window |
| production byte-identical with the flag OFF | ✅ pinned by test |
| owner-visible comparison through DemoPlan | ✅ `?engine=e1_rear_band`, real renders in `figures/` |

One criterion fails, and it is the headline one. But **it fails for a reason the experiment was not
testing**: E1 was scoped to mirror the front-public-band parti, and that parti reaches 1 of 8 briefs
on its own. Orientation cost nothing in reach — the rear band plans exactly where the front band
plans. Had E1 been attached to a parti that reaches 7 of 8, the criterion would have been a fair
test; attached to this one, 3 of 8 was unreachable from the start.

### The recommendation

> **GO on the hypothesis. NO-GO on the carrier. Phase 1 is approved only with its first child fixed.**

Concretely:

1. **Do not invest further in the band parti as the orientation vehicle.** Its reach is 1/8 and the
   refusals (§6) are about FLEX and bedroom shape, neither of which orientation work can address.
2. **Before Phase 1 proper, run one more bounded experiment (E1b): attach `public_orientation` to
   the SPINE partis**, which plan on 7 of 8 briefs and produce every plan the product actually
   ships. In a spine parti the public rooms occupy rows at one end of a column, so orientation there
   is a row-order decision — cheaper than this one, and reusing everything E1 built (the dimension,
   `south_is_envelope`, the preview seam, the measurement harness, the figures pipeline).
   **E1b is the real test of whether a concept dimension can reach users.**
3. **Phase 1 ("concept as input") is the right direction** — E1's evidence supports it directly: an
   explicit dimension set before room placement did change the building, and did so through code
   that was already there. But Phase 1 built on carriers that reach 1/8 of briefs would produce a
   concept vocabulary that refuses most of the time. **Approve Phase 1's direction; gate its start
   on E1b's reach number.**
4. **If E1b also reaches ~1/8**, the blocker is not the concept layer at all — it is the geometry
   family, and the next investment is the report's Phase 3 (wiring `GridWing`/pinwheel), not more
   concept work.

### Two separate, small follow-ups this experiment surfaced

- **The window-axis defect (§7.1)** — one line in `windows.py`, affecting every plan on `main`.
  Its own change, its own snapshot diff. It is also a precondition for *any* orientation work to
  deliver a real indoor/outdoor connection rather than a correctly-oriented blank wall.
- **`PublicOrientation` needs more than two values** (§1) — B16's deepest outdoor space is a side
  yard, which `STREET`/`GARDEN` cannot express.

---

## 9. Scope

No Geometry Core change. No validator weakened or modified. No new HUB/BRANCHED compiler. No change
to production candidate ranking — the rear band is an additional candidate the existing ranking
judges, and it is generated only when a caller asks for `GARDEN` by name. Nothing globally enabled;
there is no new `*_ENABLED` constant at all (§2.3). No courtyard, no L-massing, no non-guillotine
realization. Phase 1 not begun.

**Files**: `concept_spec.py` (+enum, +field), `concept_generator.py` (+strategy, +field, four
orientation locations parameterised), `demo/service.py` + `demo/router.py` (the preview seam),
`tests/vertical_slice/test_e1_public_orientation.py`, and the harness under
`backend/app/ai_harness/e1_orientation/` which production imports nowhere.
