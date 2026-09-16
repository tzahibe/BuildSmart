# Multi-Level Homes and House Concepts — Architecture Research Report

**Date**: 2026-09-15 · **Status**: research and recommendation only; no code changed · **Base**: `main` at `19f53e9` (working tree carries the uncommitted two-level room-maxima work)

**Question**: how does BuildSmart grow from a single-level planning engine into one where a person chooses an architectural concept (one or two storeys, public below / private above, master downstairs, …), rooms are distributed between floors, a stair occupies real area on both, and the engine still searches, validates and offers alternatives — without the engine becoming a pile of special cases?

Everything below is read from the code or measured by running it. The four experiments in §0.2 were run against the frozen Geometry Core in this session (scratch scripts only, nothing committed).

---

## 0. Verdict up front

| | |
|---|---|
| **Can multi-level be added cleanly?** | **Yes, at the domain, pipeline, validator and contract layers — and NO at the concept generator, which needs a real second parti family, not a flag.** |
| **Geometry Core** | **UNCHANGED.** It is a per-`Wing` slicing solver with no notion of a floor, an entrance or a street. Two hand-authored levels, each with a `STAIRWELL` leaf, solve on the frozen engine (§0.2, E3). |
| **The hard problem** | **The stair seat.** The stair must be the same rectangle on both levels, but each level's programme dictates its own column widths (ground public column 6.6 m, upper bedroom column 4.2 m in the test case). In a 72-seat sweep exactly one shared seat solved both levels. This is a joint search over both floors, and it is where Phase 1's effort goes. |
| **What must never happen** | An example house concept becoming a hard geometric constraint. A concept is a *program allocation plus soft preferences*; the outline, the stair seat and the per-level footprint stay the engine's, exactly as feature 006 made the outline the engine's. |
| **Smallest architecture** | `Building = [Level]` where each `Level` is *today's pipeline run* over its own `LevelProgram`, plus one `VerticalCore` realized as a pinned leaf on every level it touches, plus one `BuildingValidator` above the per-level validators. One new stage (allocation) before geometry, one new coordinator (massing + seat search) around the existing `run_general`, nothing rewritten below it. |
| **Demand evidence** | **None in the log.** 740 failure-log entries, zero `FLOORS_UNSUPPORTED` (the parser defaults `floors=1` unless the brief says otherwise), one brief mentioning a floor count at all ("בקומה אחת"). This is a product bet, not a log-driven fix; Phase 0 should start collecting the signal. |

### 0.1 The one-paragraph recommendation

Model the building as a list of levels each planned by the **existing** `run_general`, with the level's program and a **pinned stair rectangle** as the only new inputs; add a **program-allocation stage** before geometry that turns `(ProgramSpec, HouseConcept)` into a bounded set of `LevelProgram` pairs; add a **massing coordinator** that chooses ground outline, upper outline (⊆ ground) and stair seat jointly by *planning both levels* for each candidate seat, exactly as feature 006 plans every outline; add a **BuildingValidator** that proves the four vertical invariants; keep the single-storey path as `Building` with one level and `alternatives` as it is today. Rank alternatives **grouped by concept first**, never in one pool by area proximity.

### 0.2 Evidence gathered by running the engine

All figures from this session, on the frozen `geometry_core` and the current `concept_generator`.

**Programme arithmetic** (today's `ROOM_TEMPLATES`, `target_gross_area_m2`, `minimum_footprint_width_m`):

| Programme | rooms | target gross m² | capacity m² | min. width m |
|---|---|---|---|---|
| Single storey, 3BR + ממ"ד + 2 wet (today) | 10 | 131.7 | 242.2 | 9.40 |
| **A** ground: LDK + hall + guest WC + ממ"ד + stair | 7 | 89.4 | 182.2 | 7.20 |
| **A** upper: hall + master + ensuite + 2BR + bath + stair | 7 | 72.2 | 126.7 | 6.40 |
| **B** ground: LDK + hall + WC + ממ"ד + master suite + stair | 9 | 112.2 | 217.8 | 9.40 |
| **B** upper: hall + 2BR + bath + stair | 5 | 49.4 | 91.1 | 4.40 |

The same programme on two levels wants ~161 m² of target gross against ~132 m² on one: a second hall (~11 m²) and the stair counted on both levels (~6 m² each). A two-storey house spends 15–20 m² more on circulation. This is real and must be shown, not hidden.

**E1 — today's partis on a bedrooms-only floor** (`_allocations` + `_build` with a 7-room upper programme, stair in `ZoneGroup.CIRCULATION`): `SPINE_PUBLIC_PRIVATE` → `INSUFFICIENT_WING_AREA: allocation left a column empty`; `SPINE_DOUBLE_LOADED` → `plan_layout` succeeds, then `_concept_from` raises `KeyError: 'STAIR'` because `_allocations` only distributes PUBLIC/PRIVATE/SERVICE rooms and never sizes the stair. The `STAIRWELL` vocabulary exists (`geometry_core/model.py:186`, `concept_generator.py:202`, `contract.py:33`) but nothing can place it — as its own comment says.

**E2 — stair as a service-group room**: `SPINE_DOUBLE_LOADED` planned *and solved* an upper floor at 9.9 × 9.1 m (in an 11 × 10 candidate) with `STAIR` realized at 2.90 × 1.80 m net; at 13 × 8 it produced 12.4 × 7.25 m with a 4.25 × 1.20 m stair. Every other strategy failed (empty public column, or `ROOM_ABOVE_MAXIMUM_AREA` on the "west column"). So the engine *can* tile a private-only floor today through one strategy — with the stair placed wherever the row order puts it, i.e. no positional intent and no alignment with anything below.

**E3 — two hand-authored levels with a pinned stair** (12 × 10.5 m ground; stair = the rear 4.8 m of the hall column; upper level `⊆` ground):
- Ground planned freely picks west 6.6 m / hall 1.9 m. Upper planned freely (11 × 10.5) picks west 4.2 m / hall 2.55 m. Pinning either level to the other's realized columns is infeasible: a 6.6 m bedroom column violates the bedroom aspect/area band; a 5.5 m service column cannot hold a laundry.
- Sweeping 72 shared seats (west 5.6–6.6 × hall 1.5–2.1 × upper width 12/11.5/11): **one pair solves both levels with an identical stair rectangle** — west 5.6, hall 2.1, upper 11 × 10.5 (1 m east retreat = a terrace strip). Stair 2.0 × 4.6 m net = 9.2 m² on both floors. Ground rooms: LIVING 24.6, DINING 16.2, KITCHEN 14.3, ממ"ד 14.0, WC 4.9, STUDY 13.5, LAUNDRY 6.2. Upper: MASTER 20.0, BEDROOM 17.3 / 16.7 (over the 14 m² *preferred* maximum, under the 18 m² hard one), two baths 11.2 / 11.5, dressing 8.4.

Three conclusions follow and drive the whole report: (i) Geometry Core needs nothing; (ii) with one-room-per-row columns the joint feasibility region for a shared stair seat is *narrow*, so the seat must be searched, not derived; (iii) the search is affordable only because each level is a ~165 ms solve — the same economics as the outline search in `demo/service.py`.

---

## 1. Current single-floor assumptions that block this

Ordered by how deep they sit. "Anchor" is where the assumption lives.

| # | Assumption | Anchor | Depth |
|---|---|---|---|
| 1 | **The scope gate refuses `floors != 1`.** | `demo/scope.py:49,154` (`SUPPORTED_FLOORS = 1`) | Shallow — one gate |
| 2 | **`ProgramSpec` has one room set and one `target_built_area_m2`**; no story count, no per-level intent. `build_room_program` emits one flat list. | `vertical_slice/spec.py` `ProgramSpec`; `concept_generator.py:432` | Shallow — additive fields |
| 3 | **`Concept` = one `Fixture` + one `entrance_zone_id` + one `street_side`.** A level with no street has no honest value for two of these. | `vertical_slice/concept.py` `Concept` | Shallow — needs a `LevelEntry` |
| 4 | **Every parti is `public column │ hall │ private column`.** `_allocations` puts `public` west unconditionally; `_build` refuses an empty column; `minimum_footprint_width_m` sums public + hall + private; front band and hub require ≥ 2 public rooms (hub also ≥ 3 bedrooms). A floor without public rooms has one strategy that happens to work (E2) and no parti designed for it. | `concept_generator.py:2277–2320, 2037, 657, 2360, 3222` | **Deep — a missing parti family** |
| 5 | **`_allocations` drops every CIRCULATION room except HALL**; `_concept_from` then indexes the dropped room and crashes. The stair has a template but no producer. | `concept_generator.py:2277, 2262` (E1) | Medium — allocator + tree synthesis |
| 6 | **Forced cuts stay forced only on the root→HALL path** (`_contains_hall`). The corridor is the one rectangle the solver may not move; the stair must become the second. | `concept_generator.py:2165–2215` | Shallow — extend a predicate |
| 7 | **Columns hold one room per row** (ensuite shares its bedroom's row; tier-2 repartition is the bounded exception). This is what makes a shared stair seat rare (E3: 1/72) — the two levels cannot both use a 5.6–6.6 m column well. | `concept_generator.py:719 _rows_of`, `1117 Repartition`; memory `strip-rooms-root-cause-and-fix-cost` | **Deep — the known row-sharing limit** |
| 8 | **The entrance is the street wall.** `resolve_entrance` accepts only zones with `rect.y == footprint.y`; `build_entrance_door` is seeded as `OUTSIDE → zone`. | `doors.py:146–216` | Medium — upper levels need a different entry |
| 9 | **Validation is one plan, one entrance, one site.** C5 seeds reachability from `"OUTSIDE"`; C2 measures against `site.footprint`; C10/C11/C16/C18 are street/parking checks; C8 uses one footprint for exposure. No check spans two rect sets. | `validation.py:151–470`, esp. `:267` | Medium — reuse per level, add a building layer |
| 10 | **`GeometricDesign` is one footprint, one entrance door, one parking set, one garden**, and `gross_area_m2 = fixture.footprint_area_m2()`. | `design_output.py:83–110, 162` | Shallow — becomes the *level* DTO |
| 11 | **`DemoDesign`/`DemoPlanSet` = one drawing with site**; alternatives are peer drawings. | `demo/contract.py:166–200` | Shallow — wrap, don't rewrite |
| 12 | **`built_area_m2` means one-storey footprint area everywhere**: `_outlines_for` feeds it to `feasible_options`; `one_storey_capacity_m2`; the form's capacity check; `effective_target_m2` compares a plan's gross to it; `_select_plans` sorts by `|used − target|`. The frontend comment at `types.ts:199` already names the four quantities this conflates. | `demo/service.py:340–360, 430–440, 519–530`; `site_geometry.py:338`; `App.tsx:261` | **Deep in semantics, shallow in code** — one number doing four jobs |
| 13 | **Ranking is a single pool by area proximity.** A 190 m² one-storey plan will always beat a 100 + 90 two-storey plan for a 200 m² request unless the pool is split. | `demo/service.py:_select_plans`, `concept_generator.py:3810` | Medium — selection policy |
| 14 | **The renderer draws one design with its site.** `planViewBox` frames footprint + walk + parking; no level tabs; thumbnails are whole designs. | `DemoPlan.tsx`, `DemoWorkspace.tsx` | Shallow — a level switcher |
| 15 | **Persistence and versioning belong to the legacy pipeline**, not the demo path. `generate_demo_design` stores nothing; `DesignVersion`, `apply_project_update`, chat proposals and `spatial_edit` all wrap `app/design` + `app/geometry`. | `demo/service.py`; `design/version.py`; `projects/update.py`; `geometry/spatial_edit.py` | **Deep for §11** — editing has no demo-side substrate yet |
| 16 | **Wing exposure = touches the wing rectangle.** Correct per level, but the ground floor's roof under an upper retreat is a terrace, and the upper's exterior over the ground is structural — none of which the 2D wall model knows. | `engine.py:_mark_exposure`, `geometry_adapter.envelope_sides` | Medium — accounting only, not geometry |

Already in place and helpful: `Project.floors` (`projects/models.py:409`) is extracted by the parser (`requirements/parser.py:26–32`), stored, editable through review (`demo/router.py`) and chat (`chat/intent.py:_UPDATABLE_FIELDS`), shown in `RequirementsReview.floors` — though `ReviewPage.tsx` does not render it. The legacy `design/generator.py` distributes bedrooms across floors (kept for tests only). `PRIVATE_HOUSE_V1_ENGINE_DECISION.md §6` already names the four vertical constraints V1–V4, two stair archetypes and `STAIR_VOID`; `SPATIAL_ENGINE_SPEC_V2.md` part ח specifies `Level`, per-level footprint, vertical alignment, adjacency with a vertical dimension, and `GFA = Σ level` vs coverage from the ground level only. This report keeps those decisions.

**Honest assessment of "cleanly vs deeply embedded"**: items 4, 7 and 12 are the embedded ones. 4 and 7 are the *same* limitation seen from two sides — the generator has one layout idea (columns of full-width rows beside a straight hall) and a two-storey house asks it to lay out two very different programmes with one shared rectangle. Everything else is contracts and orchestration, which this codebase changes routinely (006 and 008 are exactly such changes).

---

## 2. Proposed `HouseConcept` / preference model

### 2.1 What an example actually carries

For each candidate example, what is *semantic* (survives into a typed field), what is *visual inspiration only* (must not become a field), what becomes a *soft preference*, and what must *never* become a hard geometry constraint.

| Example concept | Semantic content → field | Visual only (discard) | Soft preference | Must never be hard |
|---|---|---|---|---|
| Single-storey family house | `stories = 1` | shape, roof, facade | — | outline |
| Two-storey, public ground / private upper | `stories = 2`, `public_private_strategy = PUBLIC_BELOW_PRIVATE_ABOVE`, `entrance_level = GROUND` | which bedroom is where, stair shape | all bedrooms up, all public down | exact split of unspecified rooms; upper footprint |
| Two-storey, master on the ground floor | `stories = 2`, `master_level = GROUND` | — | children's rooms up; shared bath up | master position within the floor |
| Bedrooms grouped in a private wing | `bedroom_grouping = WING` | wing direction | one hall serving all bedrooms | which side; wing depth |
| Living/kitchen facing the garden | `public_open_side = GARDEN` (rear) | window count | public band at the rear | **not producible today** — §1 of the layout UX report: every parti puts public west or front. Show only when the parti exists. |
| Central circulation / compact core | `circulation_style = HUB` | lobby shape | hub parti first | lobby size (008 gates decide) |
| Linear / spine organisation | `circulation_style = SPINE` | corridor length | spine parti first | corridor width (that is the *corridor requirement*, already binding on its own) |
| Wider public front, bedrooms behind/beside | `circulation_style = FRONT_BAND` | — | front band first | outline ratio |
| More open public area | `kitchen_living = OPEN` | furniture | — | already a *requirement* (`open_plan`), not a concept field — do not duplicate |
| More separated kitchen/living | `kitchen_living = CLOSED` | — | — | same: maps to `open_plan = false` |

Two rules fall out. **A concept never repeats a requirement** (`open_plan`, bedrooms, wet-room kinds, corridor width, relationships stay where they are — `Project` and `ProgramSpec`); it only adds fields that have no home today. **A concept never names a dimension** — no footprint, no ratio, no stair size. The one exception is `stories`, which is a *program* fact (how many `LevelProgram`s exist), not a geometric one.

### 2.2 The type

```
HouseConcept                                   # frozen dataclass beside ProgramSpec, in vertical_slice/spec.py
  stories:                  int = 1                              # 1 or 2 in Phase 1–3; the only field that changes the program's SHAPE
  public_private_strategy:  PUBLIC_BELOW_PRIVATE_ABOVE | MASTER_SUITE_BELOW | PUBLIC_PLUS_ONE_BEDROOM_BELOW | ENGINE   (= ENGINE when stories == 1)
  entrance_level:           GROUND                              # the only value until split-level / basement exist
  master_level:             GROUND | UPPER | ENGINE
  bedroom_grouping:         TOGETHER | ENGINE                   # Phase 3+: SPLIT (a guest room downstairs)
  circulation_style:        SPINE | FRONT_BAND | HUB | ENGINE   # maps onto ConceptStrategy families — ordering only
  public_open_side:         STREET | GARDEN | ENGINE            # GARDEN unsupported until the parti exists; refused as UNSUPPORTED_HARD_REQUIREMENT if bound
  level_area_preferences:   tuple[LevelAreaPreference, ...]     # optional "about 120 + 80"; see §7
  family:                   str | None                           # optional concept-card id, diagnostics only (like DemoDesign.family)
  source:                   USER_EXAMPLE | CHAT | ENGINE
  strength per field:       HARD | PREFERENCE                    # reuse RelationStrength; default PREFERENCE for everything but `stories`
```

Placement rationale: `ProgramSpec` is *what the house contains*; `HouseConcept` is *how it is organised*. They are siblings on `ArchitecturalSpec` (`spec.program`, `spec.concept`). `ArchitecturalSpec(plot, program)` keeps its two-field constructor working via `concept = HouseConcept()` default, so every existing test constructs the same object.

**Strength semantics** reuse the exact grammar the codebase already has for corridor width and relationships: `HARD_REQUIREMENT` gates (a plan violating it is not returned), `PREFERENCE` orders (tried first, reported when dropped — `_set_aside` and the "העדפה שלא התממשה" warning already exist). `stories` is always hard: a person who chose two storeys is not given one with a note. `master_level` from a user example defaults to PREFERENCE; "חדר ההורים חייב להיות למטה" in the brief makes it HARD through the same parser severity path (`RequestSeverity`) that grades unsupported requests today.

**Interaction with "user chooses plans, not footprints"**: the principle survives intact because `HouseConcept` carries no footprint. The one genuinely new pre-generation choice is `stories`, and it is legitimate for the same reason bedrooms are: it changes *what is planned*, not *how the rectangle is cut*. `public_private_strategy` and `master_level` are allocation facts (§4), also program-side. Everything in `circulation_style` is display/ordering — identical in kind to the `LayoutPreference` the layout UX report recommended, and should share its implementation.

### 2.3 What the concept must not mean

"Copy this plan": the example thumbnail is a *diagram of qualities* (§9), never a plan the engine reproduces. The concept's fields are either program allocation or search ordering; nothing in the geometry stack reads `HouseConcept` except through `LevelProgram`s and a strategy sort key.

---

## 3. Proposed multi-level domain model

### 3.1 Smallest clean change

```
Building                                      # NEW — vertical_slice/building.py
  levels:            tuple[LevelPlan, ...]     # index 0 = entrance level; ordered by elevation
  cores:             tuple[VerticalCore, ...]  # Phase 1: exactly one STAIR when stories == 2, none when 1
  massing:           Massing                   # ground outline, per-level outlines, terrace remainder (§7)
  total_gross_m2:    float                     # Σ level.design.gross_area_m2
  total_net_m2:      float
  validation:        BuildingValidationReport  # the V-checks (§6) — SEPARATE from each level's C-checks

LevelPlan
  level:             Level                     # id, index, elevation_m, floor_to_floor_m, kind = GROUND | UPPER
  program:           LevelProgram              # the rooms this level was given (§4)
  concept:           ConceptCandidate          # today's object, unchanged
  design:            GeometricDesign           # today's object, unchanged — plot/footprint/rooms/doors/windows/site
  validation:        ValidationReport          # today's C1–C21, run with a LevelContext (§3.3)
  safety:            SafetyReport
  entry:             LevelEntry                # how you arrive on this level (§3.3)

VerticalCore (§5)
  kind:              STAIR
  lower_level_id, upper_level_id
  footprint_u:       Rect                      # plot-absolute grid units; identical on both levels by construction, PROVEN by V1
  ...

Level                                          # the spec-V2 part-ח entity, minimal
  level_id: "L0" | "L1"; index: int; elevation_m: float; floor_to_floor_m: float (PARAMETER · UNVERIFIED); kind
```

**Why this and not a `Fixture` with two wings**: `Fixture.wings` already exists and the solver iterates wings, so "just make the upper floor a second wing" is tempting. It is wrong for three reasons: zone ids must be unique within a fixture (two `HALL`s), `_mark_exposure`/`seam_leaf_sides` model wings as *horizontally adjacent* rectangles that share a wall — an upper floor shares nothing horizontally — and every downstream stage (`doors`, `windows`, `validation`, `assemble`) reads `fixture.zones` as one flat set for one plan. Per-level fixtures keep every existing stage's contract literally unchanged; the coupling lives in the *inputs* (a pinned leaf) and in one new validator, not in the engine.

**Single-storey compatibility**: `Building(levels=(LevelPlan(design=today's GeometricDesign, ...),), cores=())`. The `DemoDesign` the screen shows today *is* `levels[0]`, byte for byte. `DemoPlanSet.plan` stays a `DemoDesign` in Phase 0 (a `DemoBuilding` wrapper is added beside it, §8), so no frontend change is forced by the domain change.

### 3.2 Can Geometry Core be reused independently per floor?

Yes, without modification — this is the strongest finding. `solve_fixture(fixture)` takes a `Fixture` whose `Wing` has an origin, size and slicing tree; wall typing derives exterior sides from the wing rectangle, RC from safe-room membership, OPEN from groups; nothing refers to a street, an entrance, a site or another plan. E3 solved a ground fixture and an upper fixture with a `STAIRWELL` leaf each and produced identical stair rectangles when the pinning cuts were identical. Exposure on the upper level is correct for its own outline: an upper wall over a ground retreat is exterior, exactly as it should be.

What Geometry Core does *not* give you: any relation between the two solves. Alignment is a property of the two trees' forced cuts, proven afterwards by V1 (§6). That is the right division — the engine tiles, the validator proves.

### 3.3 The level-scoped pieces that need a context object

Today's stages take `(fixture, rects, footprint / site)`. Three of them encode "this is the ground floor":

- **Entry.** `resolve_entrance` (street wall) and `build_entrance_door` (`OUTSIDE → zone`). Introduce `LevelEntry = STREET_DOOR(zone, door) | STAIR_ARRIVAL(core_id, zone)`. For an upper level the entry zone is the `STAIRWELL` leaf itself; the "door" that seeds C5 is the stair's arrival edge into the hall.
- **Site.** `_site_plan_for` builds parking, walk and garden for one footprint. Only the entrance level has a site plan; upper levels carry `site = None` and their C10/C11/C12/C16/C18 are **not run** (not "passed") — a `LevelContext(kind=UPPER)` makes `validate` skip them and the report says so.
- **C5 reachability.** Seed from the level's entry: `OUTSIDE` for the ground, `STAIR` for the upper. The *building* check V5 then proves the stair itself is reached from `OUTSIDE` on the ground and that every upper room is reached from the stair — the same BFS, one level up.

Everything else (C1–C4, C6–C9, C13–C15, C17, C20, C21) is already per-plan and runs unchanged per level.

---

## 4. Proposed level-program allocation stage

### 4.1 Where it belongs in the pipeline

```
today   Brief → parse → REVIEW → scope gate → spec_for → [outline search: run_general per outline] → select → contract
                                                              └ concept_generator → adapter → core → doors/windows → validate → assemble

proposed
Brief → parse → REVIEW (+ concept card) → scope gate → spec_for (+ HouseConcept)
      → ALLOCATE  (ProgramSpec, HouseConcept) → bounded set of LevelProgramSet            ← NEW STAGE, pure, no geometry
      → MASSING   per LevelProgramSet: ground outlines (existing feasible_options) × upper outline rule × stair seats   ← NEW COORDINATOR
      → per (outlines, seat): run_general(level 0) ; run_general(level 1)   ← EXISTING, called twice with a pinned leaf
      → BUILDING VALIDATOR (V1–V6)                                          ← NEW
      → select (grouped by concept)  → contract (DemoBuilding)
```

The brief's own sketch — *Brief → Semantic Architect → Level Program Allocation → Spatial Architect per level → Vertical Coordination → Geometry Solver per level → Building Validator → Renderer* — maps onto this one-to-one, with two corrections from the code:

- "Semantic Architect" is today `parser` + `spec_for` + `check_supported`; it stays before allocation and gains one field.
- "Vertical Coordination" is **not** a stage between the two spatial architects; it is the *outer loop* that chooses the seat and calls both. The two levels cannot be planned independently and reconciled afterwards (E3: independently planned levels pick 6.6 m and 4.2 m columns and never meet). Coordination is a search over shared parameters, which is exactly how `demo/service.py` already treats outlines.

### 4.2 Allocation rules

`allocate_levels(program: ProgramSpec, concept: HouseConcept) -> list[LevelProgramSet]` — deterministic, bounded (≤ 3 sets per concept), expressed in `ProgramRoom`s so every level program is something `build_room_program` could have produced.

| Class | Rule | Source |
|---|---|---|
| **HARD** | A room the brief placed on a floor is on that floor (`master_level = GROUND, HARD`). | brief / review |
| **HARD** | The entrance level holds the entrance hall and the public entrance sequence; `entrance_level = GROUND` until basements exist. | concept |
| **HARD** | Exactly one `VerticalCore` connects every pair of adjacent levels; the stair's `STAIRWELL` room appears in *both* level programs. | domain invariant |
| **HARD** | An ensuite is on its host bedroom's level (it already travels with its bedroom in `_allocations`). | existing wet-room semantics |
| **HARD** | Every level with a bedroom has a full bathroom reachable on that level, or the person is asked — the specs/007 access invariant, per level. | `check_wet_room_invariants` applied per `LevelProgram` |
| **PREFERENCE** | Bedrooms grouped on one level; public rooms on the entrance level; master downstairs when asked; guest WC on the entrance level; a shared bathroom on every bedroom level. | concept |
| **PREFERENCE** | Wet rooms vertically aligned (V3, §6) — a *seat* preference, not an allocation one. | engine decision §6.1 |
| **ENGINE** | Which unspecified rooms go where; FLEX per level; the split of `target_built_area_m2` (§7); per-level footprint; the stair seat. | — |

Where the **safe room** goes is deliberately **not** decided here from architectural taste. Its level is `ENGINE` by default with a strong preference for the entrance level (it is a bedroom-tier room and the census found it *is* one of the bedrooms), and the rules layer may later pin it: whether a ממ"ד may or must be on a particular floor is an authoritative-rule question (§6.3), not something to invent.

Worked sets for a 3BR + ממ"ד + ensuite + shared bath + guest WC brief:

- **A · PUBLIC_BELOW_PRIVATE_ABOVE**: L0 = LDK, hall, WC, ממ"ד, stair · L1 = hall, master + ensuite, 2 BR, bath, stair.
- **B · MASTER_SUITE_BELOW**: L0 = LDK, hall, WC, ממ"ד, master + ensuite, stair · L1 = hall, 2 BR, bath, stair.
- **C · PUBLIC_PLUS_ONE_BEDROOM_BELOW**: L0 = LDK, hall, WC, ממ"ד-as-bedroom or one BR, stair · L1 = the rest.

Each set is then checked for per-level plannability *before* geometry by the existing pre-checks (`minimum_footprint_width_m`, `target_gross_area_m2`), so an upper program that cannot fit any admissible outline is refused with a program-level reason, the way `FOOTPRINT_BELOW_MINIMUM_WIDTH` is today.

### 4.3 Why a dedicated stage and not a flag on the generator

Because `generate_concepts(spec, candidates)` is already 3 850 lines of *one* level's layout search, and every one of its partis is a public/private composition. Feeding it a `LevelProgram` (a list of `ProgramRoom`s, with or without public rooms) keeps it a function of *rooms in a rectangle*, which is what it is. The allocation stage is ~150 lines of pure Python with exhaustive tests; folding it into the generator would put allocation choices inside the proportion loop.

---

## 5. Stair / vertical-circulation model

### 5.1 What the planner needs, and what only the renderer needs

| Needed by the **planner** (Phase 1) | Needed only by the **renderer** / later phases |
|---|---|
| Footprint rectangle on each level (identical) | Treads, risers, nosing |
| Which edge is the entry (lower level) and the arrival (upper level) — both must face circulation | Handrail, balustrade |
| Direction of travel (which end is the bottom step) — one of the two long edges' ends | Headroom check (a *rule*, needs floor-to-floor + tread geometry) |
| Clear circulation at both ends: the hall must share ≥ the door-clearance length with the stair on both levels (reuse `min_clear_m = 0.9`) | Winders, landings inside the flight |
| The upper-level rectangle is a **void** for area accounting (counts to GFA as circulation on the lower level, as void/opening on the upper — SPEC V2 part ח №7) | 3D |
| Reserved vertical volume = the rectangle × both levels; no other room may overlap it on either level (C1 per level already proves this once the stair is a zone) | — |

### 5.2 The type

```
VerticalCore                                   # vertical_slice/vertical.py (NEW)
  core_id:        "STAIR_1"
  kind:           STAIR
  archetype:      STRAIGHT | L_SHAPED | U_HALF_LANDING           # Phase 1: STRAIGHT only
  lower_level_id, upper_level_id
  footprint_u:    Rect                                           # plot-absolute grid units, centerline; same on both levels
  entry_edge:     Side                                            # lower level: the edge the bottom step is entered from
  arrival_edge:   Side                                            # upper level: the edge you step off onto circulation
  direction:      Side                                            # travel direction from bottom step (N/S/E/W)
  going_m, width_m:  float                                        # derived from floor_to_floor and RuleSet riser/tread PARAMETERS — never literals
  rise_m:         float                                           # = floor_to_floor of the lower level
```

**Realization on each level**: one `ProgramRoom("STAIR_1", ProgramRole.STAIRWELL, ZoneGroup.CIRCULATION)` in the `LevelProgram`; one `ZoneSpec` with `net_area` = the flight's area ± tolerance and `min_short_side` = its width; one `Leaf("STAIR_1")` whose rectangle is fixed by forced cuts; `DesiredAccessEdge(HALL, STAIR_1, CASED_OPENING)` on both levels. The existing rule that keeps root→HALL cuts forced in the free twin (`_contains_hall`) becomes root→{HALL, STAIR_1}: the two rectangles the solver may not move are the corridor and the stair. C13 then proves the arrival connection is physically realized like any other declared edge.

### 5.3 Which archetype for Phase 1, and where it sits

**Straight flight.** The engine decision §6.3 sized it at ~1.1 × 4.8 m; E3 realized 2.0 × 4.6 m net with the template's bands (the width came from the hall column it shared — a *quality* concern, §12). Reasons: it is one rectangle with one aspect (the `STAIRWELL` template already allows aspect 4.0 for exactly this); its entry and arrival are the two short ends, which makes "faces circulation on both levels" a single shared-edge test; and it slots into the existing partis' geometry as **the rear (or front) segment of the hall column** — the seat E3 proved. An L or U stair is two rectangles or a near-square with an internal landing; its arrival edge depends on direction, and a near-square 2.5 × 2.8 m seat belongs beside the hub *lobby* — Phase 5, when the hub is the parti it sits in.

**Stair seats** are enumerated per parti like `_HUB_WIDTHS_M` or `_seam_options` — bounded, deterministic, nearest-preferred first:

| Seat | Parti | Consequence the planner must handle |
|---|---|---|
| Rear end of the hall column | spine (proven, E3) | Rooms alongside the stair segment border `STAIR`, not `HALL`; they need a door from the stair's landing zone or must be rooms that tolerate it (E3 gave them doors from `STAIR`; better: shorten the hall's row list so no room needs a door there). |
| Street end of the hall column, behind the entrance | spine | "Enter, stair ahead" — the entrance opens into a hall whose first 4.8 m is the flight; C16/C11 keep working because the entrance zone is still the hall. |
| A row in the column beside the hall | spine, front band | The row spans the column width (4–5 m), depth = flight width → a *transverse* straight flight; alignment needs the column x-range shared, which is the tight coupling of E3. |
| A band cell under the lobby | hub | U-stair territory — Phase 5. |

### 5.4 Effects, one line each

- **Usable area**: −(stair area) on both levels, −(second hall). Reported per level and in total (§7); never hidden in "gross".
- **Circulation**: the stair is circulation in the *program* (`ZoneGroup.CIRCULATION`) but its `ZoneSpec` roles must stay `(STAIRWELL,)` — `_roles_of` gives only HALL the `CIRCULATION` role, so C14's `realized_corridor_width_m` and the service's `realized_corridor_width_m_of` already skip it, and C20/C21 hold it to its own template (aspect 4.0, 12 m²). Giving the stair the `CIRCULATION` role would make C14 measure the flight width as the corridor; a test should pin this.
- **Adjacency**: the stair is a legitimate neighbour for ADJACENT/NEAR relationships; NEAR's graph steps cross levels only through the stair (§6 V5).
- **Doors**: a cased opening hall↔stair on both levels; no door leaf on a stair. Rooms bordering the stair segment need doors from circulation, not from the stair unless the seat says so.
- **Floor openings**: the upper level's stair rectangle is a `STAIR_VOID` for accounting; geometrically it is just the leaf (C2 "no residual area" still holds because the void is a zone).
- **Room placement**: rooms alongside the flight on the ground are the ones that do not need daylight or hall doors (laundry, store, WC) — a seat preference the allocation stage can honour.
- **Structural/RC walls**: a stair enclosure is not RC here; a ממ"ד beside a stair is an RC neighbour like any other (the bounded re-solve handles it). Whether a stair core must be structural is a rules question — not modelled.
- **Validation**: per-level C-checks unchanged; building V-checks new (§6).
- **Rendering**: a `STAIRWELL` room drawn as the flight symbol (arrow + tread lines) from `direction`/`entry_edge`; on the upper level the same rectangle drawn as a void with the arrival arrow. Both are read off `VerticalCore`, never inferred.
- **Alternatives**: the seat is a search variable; two buildings with different seats are different families (extend `family_signature` with the seat and the level index).

---

## 6. Cross-floor architectural rules

Three columns, deliberately kept apart. Nothing in the third column is stated as a rule here.

### 6.1 HARD geometric invariants — the `BuildingValidator`

| Code | Check | Evidence |
|---|---|---|
| **V1** | The core's rectangle is identical on every level it touches: `rects_L0["STAIR_1"] == rects_L1["STAIR_1"]` in plot units. | engine decision §6.1 V1; E3 |
| **V2** | `upper_footprint ⊆ lower_footprint` (Phase 1; cantilevers deferred). | engine decision §6.1 V2 |
| **V3** | No room on any level overlaps the core's rectangle other than the core's own zone — this is C1 per level once the stair is a zone; V3 asserts it explicitly in building terms so the invariant survives a future non-zone stair representation. | — |
| **V4** | Every room on every level is reachable from `OUTSIDE` over the *realized* connections of all levels joined by the core's realized entry (L0) and arrival (L1) openings. Same BFS as C5, one graph. | validation.py C5 |
| **V5** | The stair's entry edge on L0 and arrival edge on L1 both face a CIRCULATION zone (hall/lobby), with a realized cased opening — **never a bedroom, bathroom or the safe room**. | brief §E |
| **V6** | If a safe room exists on more than one level, their rectangles are vertically aligned (engine decision §6.1 V4). Phase 1 has one safe room, so V6 is vacuous but present. | engine decision |
| **V7** | Area accounting: `total_gross = Σ level gross`; `ground_coverage = L0 footprint / plot`; the upper void is counted once; the terrace remainder is classified (`OutdoorClassification.TERRACE`, correction 3 of the core model). | SPEC V2 part ח №7 |

### 6.2 Architectural quality preferences — ranking inputs, never gates

Wet rooms stacked (upper bath over lower wet room or kitchen/service — engine decision V3); public/private zoning may differ by level (the upper level is all-private in concept A, so "public west" is meaningless there — the generator must not require it); short vertical circulation (stair near the entrance hall, arrival near the upper hall's centre); exterior exposure per level (already 100 % on one level; the upper level's retreat adds facade); the entrance path applies to the ground only; parking relates to the entrance level only; balconies belong to upper levels (Phase 5); an upper footprint smaller than the ground is a *preference* for a terrace, not a requirement.

### 6.3 Regulation — must come from authoritative RAG/rules; nothing invented here

Stair riser/tread/width/headroom minimums; whether a dwelling's ממ"ד may be on any floor, must be on a particular one, or is required per floor; per-floor and total building rights (זכויות בנייה), coverage and height; balcony area accounting; parking counts. Every such value enters as a `RuleSet` PARAMETER · UNVERIFIED with provenance, exactly as `WALL_THICKNESS_M[RC_SAFE_ROOM]` does today, and the layer separation invariant from the general-geometry report holds: no function in the geometry stack takes a `municipality` or `plan_id`.

---

## 7. Site / massing impact

### 7.1 What "built area" means when there are two floors

`built_area_m2` currently does four jobs (`types.ts:199` names them). Split them explicitly:

```
ProgramSpec.total_built_area_m2       # what the person asked for — the sum over levels (today's built_area_m2, renamed at the boundary; the old name stays as the compatibility read)
HouseConcept.stories                  # how many levels
HouseConcept.level_area_preferences   # optional: [(L0, ~120), (L1, ~80)] as PREFERENCE; empty = engine decides
Massing.ground_outline                # the ONLY quantity the site limits (feasible_options against the buildable rectangle)
Massing.level_outlines[]              # L0 = ground outline; L1 ⊆ L0
Massing.max_ground_coverage           # None until a rule supplies it (validation, never geometry — general-geometry report §4)
Project.selected_footprint            # authoritative ground outline ONLY when the person fixed one under "advanced" (006 semantics unchanged)
```

Interpretation of "200 m² over 2 floors": the engine's default split is the *allocation's* target gross per level, normalised to the request — set A (§0.2) gives 89 : 72 ≈ 110 : 90 of 200; set B gives 112 : 49 ≈ 139 : 61. A person's "about 100 + 100" is a `level_area_preferences` preference, honoured by the proportion search on each level (the existing `_proportions` nearest-target-first rule, run with the level's own target).

### 7.2 What the outline search reuses

`site_geometry.feasible_options(site, area)` answers "which rectangles of area *A* fit the buildable rectangle" — reuse it unchanged for the **ground** outline with `A = L0 target`. The scope-gate capacity check (`one_storey_capacity_m2`, `App.tsx:261`) becomes a check on the *ground level's* area, and the `BUILT_AREA_EXCEEDS_ONE_STOREY_CAPACITY` refusal gains the one honest suggestion it lacks today: a second storey.

### 7.3 The `BuildingMassing` layer above it

Upper outline rule, Phase 1: **same as ground, or a single-side retreat** (E3 needed the 1 m east retreat to make the bedroom column feasible — the retreat is a search variable, not decoration). Rules: `L1.x, L1.y ≥ L0`; `L1 ⊆ L0`; the stair rectangle ⊆ both; the retreat strip becomes `OutdoorRegion(TERRACE)` on L1, contributing to coverage and not to GFA. Phase 5 adds a different upper outline and balconies (a cantilever violates V2 and is deferred with it).

The massing coordinator's loop, bounded like everything else here: `for ground outline in feasible_options(≤4) × for seat in seats(parti, ≤3) × for retreat in (0, 1.0, 2.0)` → plan L0 and L1 → keep pairs where both validate and V1–V7 pass. Worst case ~36 pairs × 2 solves × ~165 ms ≈ 12 s on the fast path; the survey/re-run split from 006 (`_plan_outlines_until_one_plans`) applies directly and should bring the common case to a few seconds.

---

## 8. Exact impact on every current engine layer

| Layer | Classification | Change |
|---|---|---|
| **Requirements** (`requirements/parser.py`, `Project`) | **UNCHANGED → EXTEND** | `floors` already parsed and stored. Add `house_concept` (structured, sourced like `wet_room_kinds`) and parse floor-placement phrases ("חדר הורים למטה") into `master_level` with the existing severity grading. `built_area_m2` keeps its name; its meaning becomes *total* and the review screen says so. |
| **Semantic Architect** (`demo/scope.py`, `requirements_view.py`) | **EXTEND** | `SUPPORTED_FLOORS` → `(1, 2)`; refuse unsupported concept fields as `UNSUPPORTED_HARD_REQUIREMENT` when bound (e.g. `public_open_side = GARDEN`); `spec_for` builds `HouseConcept`; review renders `floors` (it does not today) and the chosen concept card. Per-level wet-room invariant check. |
| **ArchitecturalConcept / spec** (`vertical_slice/spec.py`) | **EXTEND** | `HouseConcept`, `LevelAreaPreference`, `total_built_area_m2` alias. `ArchitecturalSpec.concept` with a default — every existing constructor call unchanged. |
| **Level-program allocation** | **NEW COMPONENT** (~150 lines) | `allocate_levels`; reuses `ProgramRoom`, `ROOM_TEMPLATES`, `resolve_wet_rooms`, `check_wet_room_invariants`. |
| **Outline search / massing** (`demo/service.py`, `site_geometry.py`) | **EXTEND + NEW COMPONENT** | `_outlines_for` takes the *ground* area. New `massing.py` coordinator (outline × seat × retreat) that calls `run_general` per level with a `PinnedLeaf`. Single-storey path is the coordinator with one level and no seats — same code, same numbers. |
| **concept_generator** | **MAJOR REWORK (bounded)** | (a) accept a `LevelProgram` instead of deriving rooms from `ProgramSpec` — `build_room_program` becomes one caller of the generator, not its only input; (b) `_allocations` must place CIRCULATION rooms (the stair) and offer a **private-only allocation family** (no public column: bedrooms │ hall │ bedrooms/wet — E2 shows one strategy already does this by accident; it needs a name, a minimum-width function and rejection reasons of its own); (c) accept a `pinned` leaf: forced cuts placing `STAIR_1` at a given rectangle, and `_contains_hall` → `_contains_pinned`; (d) `minimum_footprint_width_m` must not assume a public column. The seven partis, proportions, seams, tier 2, hub bound and guard are untouched. Honest size: this is the single largest item and the one with regression risk; it is why Phase 1 ships behind `stories == 1` byte-identity gates. |
| **Geometry Core** (`geometry_core/`) | **UNCHANGED** | Verified (E3). |
| **Safe adapter** (`safe_adapter.py`) | **UNCHANGED** | Run once for the ground buildable region; the upper level's "buildable region" is the ground outline (or its retreat), which is already a proven-safe rectangle. |
| **Access topology / doors / windows / furniture** | **EXTEND** | `LevelEntry`; `resolve_entrance` only for `kind == GROUND`; upper entry = stair arrival. `generate_windows` per level with the level's footprint — unchanged code. |
| **Validator** (`validation.py`) | **EXTEND + NEW COMPONENT** | `validate(..., context: LevelContext)` skips site checks on upper levels and seeds C5 from the level entry (`realized_corridor_width_m` already ignores a `(STAIRWELL,)`-role zone). New `building_validation.py` with V1–V7. |
| **Ranking / selection** (`service._select_plans`, generator sort) | **EXTEND** | Group by concept (story count, then strategy) first; area proximity *within* a group; one representative per group in the shown set (§10). `family_signature` gains level index and seat. |
| **Demo contract** (`demo/contract.py`) | **EXTEND** (additive) | `DemoBuilding { levels: [DemoDesign], cores: [DemoCoreOut], massing, totals, building_validation }`; `DemoPlanSet.plan` stays `DemoDesign` = `levels[0]` for compatibility; a `building` field is added beside it. The corridor-opening post-process runs per level. |
| **SVG renderer** (`DemoPlan.tsx`, `PlanLegend.tsx`) | **EXTEND** | A level switcher (tabs "קומת קרקע / קומה א׳"); the stair symbol from `DemoCoreOut`; the upper void; the terrace as a classified outdoor region; the legend adds two entries only when present (its own rule). Site context drawn only on the ground level; the upper level is framed on the ground footprint so the two align on screen. |
| **Project editing / spatial edit** (`projects/update.py`, `geometry/spatial_edit.py`) | **UNCHANGED in Phase 0–2; MAJOR REWORK later** | Both wrap the legacy pipeline. §11. |
| **Alternatives** (`general_pipeline._alternative_plans`) | **UNCHANGED per level; EXTEND at building level** | Per-level alternatives stay; a *building* alternative is a different (concept, seat, outline) tuple assembled by the coordinator. |
| **Frontend flow** (`App.tsx`, `ReviewPage.tsx`, `DemoWorkspace.tsx`) | **EXTEND** | Concept cards (§9); floors on review; level tabs on the workspace; per-level and total areas in the side panel; the capacity check on the form speaks of the ground level. |
| **Legacy** (`app/design`, `app/geometry`, `app/architect`) | **UNCHANGED** | `MultiFloorNotSupportedError` stays; nothing here should touch that path. |

**Is multi-level clean or embedded?** Clean everywhere except the generator, and the generator's difficulty is not "floors" — it is that its only layout idea is public-beside-private with one room per row. A private-only floor and a pinned rectangle are *new inputs to the same search*, not new special cases inside it, provided they enter as a `LevelProgram` and a `PinnedLeaf` and never as `if stories == 2` branches.

---

## 9. Proposed UX for visual house examples

### 9.1 Before or after generation?

**Both, split by what the choice changes.** The layout UX report's argument — the engine only knows what is feasible by planning, so choose from real plans — still holds for everything that is *discoverable by planning*: organisation, mirror, outline axis. It does **not** hold for `stories` and `public_private_strategy`, for two reasons: they change the *program* (a different set of rooms per level), so planning "every concept" doubles or triples the cost of a request; and they are choices about how the family lives, which a person knows before seeing a drawing. So:

- **Before generation (review screen, one row of cards)**: story count and the public/private strategy, as *concept cards* — "בית בקומה אחת", "שתי קומות — ציבורי למטה, שינה למעלה", "שתי קומות — חדר הורים למטה", and always **"המנוע יחליט"** as the first, default card. Cards are *gated by program-level feasibility* computed without geometry (§4.2 pre-checks: a two-storey card is not shown for a 1-bedroom brief; "master downstairs" is not shown without a master; a total area below the two-level programme's minimum hides the two-storey cards with the number). No card is shown that cannot produce a plan for *this* brief in principle — the 006 failure mode ("offering an option already known impossible") is the thing to avoid.
- **After generation (workspace chips, as the layout report specified)**: organisation, mirror, along/across the street, "bedrooms in their own wing", "more open living" — each swaps to a plan already in the validated pool or edits one field and regenerates. Add one chip: **"נסה בשתי קומות / בקומה אחת"**, which sets `stories` and regenerates — the recommendation path for a person who did not choose.

### 9.2 Cards, thumbnails, count

- **Thumbnail = a schematic diagram**, not a plan: two stacked boxes with coloured bands (public / private / stair), or one box. Drawing a real plan on the card promises geometry the engine has not proven; a diagram promises qualities, which is what the concept is.
- **Text = one line of qualities + one line of consequence**, both computed: "סלון, מטבח וממ"ד למטה; חדרי השינה למעלה" / "כ-110 + 90 מ"ר; המדרגות תופסות כ-9 מ"ר בכל קומה". The area line is the allocation's own numbers, so it is true before any geometry.
- **Count: three to four cards**, never a gallery. Concepts are shown only when they differ in *program allocation*; two cards that would produce the same level programs are one card. In Phase 1 the honest set is exactly three (engine decides / one storey / two storeys public-below), Phase 2 adds master-below, Phase 3 the organisation families as post-generation chips. Showing "linear" and "central core" as pre-generation cards would be fake choice: the engine decides that by planning, and most briefs get one family (memory: the generator's repetition root).
- **Provenance stays visible**: the chosen card is a `requested` requirement on the review screen with the same ביקשת/הנחנו tag as every other field; "המנוע יחליט" reads as הנחנו.

### 9.3 Recommendations after generation

When the request exceeds one-storey capacity or the programme's capacity note fires, the plan carries a *computed* suggestion: "בשתי קומות אפשר להגיע ל-… מ"ר על מגרש זה" — only when the allocation pre-checks say a two-level programme fits, and phrased as an offer (a chip), never as a silent regeneration. This is the same pattern as `outline_note` in 006.

---

## 10. Alternative generation and ranking

### 10.1 Grouping first

Alternatives are grouped by **concept** — story count, then `public_private_strategy`, then strategy family — and only *within* a group ranked by today's rule (nearest the requested total area, ties to the earlier outline/candidate). The shown set takes the primary from the chosen or engine-decided concept and fills the remaining slots with the best plan of each *other* concept before any second plan of the same concept — the same "family before repeat" pass `_select_plans` already runs, one level up. A large single-storey plan therefore never displaces a good two-storey plan by area proximity alone: they are in different groups and both are shown.

When the person chose a concept, the other concepts' plans are still computed only if the chip asks (cost), and the primary is theirs — the 006 rule for a person's outline, applied to concepts.

### 10.2 Metrics for comparing multi-level alternatives (reported, and used only within the rules above)

| Metric | Definition | Reuse |
|---|---|---|
| Delivered total vs request | `Σ level gross / total_built_area_m2` | `effective_target_m2`, `capacity_note` per building |
| Per-level fulfilment | each level's gross vs its allocation target | `_proportions` target logic |
| Circulation share incl. stair | (halls + stair on all levels) / total room area | quality metric M3 (`spikes/failure_log_sweep/quality_metrics.py`) |
| Room proportions | worst bedroom, master, safe-room aspect; wet adjacency | `hub_guard.PlanProportions` unchanged, per level |
| Vertical wet alignment | share of upper wet rooms over a lower wet/service room | new, trivial rect overlap |
| Stair–entrance distance | graph steps entrance hall → stair on L0; stair → upper hall centre | `relationships` BFS |
| Ground coverage / garden kept | L0 footprint / plot; garden area | `classify_garden` |
| Exposure | habitable rooms on an exterior wall, per level | M2 |

None of these becomes a scalar objective — the codebase's stance (008: compare on named quantities, not a score) is kept.

---

## 11. Editing after generation

| Command | Class | What it touches |
|---|---|---|
| "move the master bedroom downstairs" | **Level reallocation** → regenerate | `HouseConcept.master_level = GROUND (HARD)`; allocation set changes; both levels replanned |
| "put all children's rooms upstairs" | **Level reallocation** | `public_private_strategy = PUBLIC_BELOW_PRIVATE_ABOVE` or `bedroom_grouping = TOGETHER` on L1 |
| "make the kitchen and living room open" | **Requirement edit** (exists today) | `open_plan = true` → regenerate that level; the other level is unaffected but re-solved for the seat (cheap) |
| "add another bathroom upstairs" | **Program edit + reallocation** | `wet_rooms += 1` with a level hint → regenerate |
| "move the stairs closer to the entrance" | **Topology change** — seat preference | seat ordering (street end first) → replan both levels |
| "make the upper floor smaller" | **Massing edit** | retreat preference / `level_area_preferences` → replan L1, then V1–V7 |
| "turn this into a one-story house" | **Full regeneration** | `stories = 1` — a different building |
| Move one room within a level (drag) | **Local edit** | only class that is not a regeneration; today's `spatial_edit` idea, but on the demo geometry |

Every command but the last is a *typed field change followed by regeneration* — which is exactly what `apply_project_update` / `ProjectUpdateDiff` / chat proposals already model (`_REGENERATION_TRIGGERING_FIELDS` includes `floors`). The blocker is not the command model; it is that **the demo pipeline has no persistence or versioning**: `generate_demo_design` returns a `DemoPlanSet` and stores nothing, while `DesignVersion` snapshots the legacy request/spec/solver. Editing therefore needs, first, a `DemoDesignVersion` (or a `Building` snapshot on `DesignVersion.geometric_design`) written by the demo route, and a `regenerate` that reads the stored `HouseConcept` + `LayoutPreference`. Local edits (drag) on the demo geometry are a Phase 5+ question: `spatial_edit` validates against the legacy `_overlaps` and V1 topology, not against C1–C21, and a moved room in a slicing-tree plan is not a slicing-tree plan any more.

---

## 12. Risks and technical unknowns

1. **Seat feasibility is narrow** (E3: 1/72 with one-room-per-row columns). Risk: two-storey plans exist for few briefs, and the ones that exist share a column width neither level wants (bedrooms at 17 m², over preferred). Mitigations in order of cost: more seats per parti; the upper retreat as a search variable (already needed); the private-only allocation family with its own widths (E2 shows it plans); **row sharing** (the strip-rooms memory: the true fix for both this and the WC-strip problem, a Geometry Core representation change). Measure before choosing.
2. **Stair width comes from the hall column.** In the spine seat the flight is as wide as the corridor (2.0 m in E3) — architecturally too wide and area-costly. Fix: the stair leaf's own `max_short_side` (the templates have only a minimum) or a stair-plus-landing pair of leaves. Small, but a Geometry Core zone-spec extension if done in the engine.
3. **Regression surface in the generator.** Any change to `_allocations`, `minimum_footprint_width_m` or `_unforced` risks the 418-context sweep. Gate: `ab.py`-style byte-identity of every primary with `stories == 1` on every phase.
4. **Cost.** Two solves per seat × seats × outlines × retreats. The survey/re-run split and hard caps keep it bounded; the loading screen's `PIPELINE_STAGES` gains per-level stages so the percentage stays honest.
5. **Area semantics migration.** `built_area_m2` is read in the form, scope gate, outline search, capacity note, selection, tests and the frontend label. Renaming at the boundary (SPEC V2 part ט's rule: one translation point, compatibility field never read elsewhere) is the only safe way; a partial rename leaves two meanings live.
6. **Regulatory unknowns** (§6.3): stair dimensions, ממ"ד floor rules, per-floor rights, balcony accounting. None modelled; all parametrised. The product must label two-storey output a *study* until a rules source exists — the provenance gate the general-geometry report proposed.
7. **No demand signal.** The parser defaults `floors = 1` when unstated, so the log cannot tell how many people wanted two storeys. Phase 0 should surface `floors` on the review screen and log `FLOORS_UNSUPPORTED` with the brief so Phase 1 is sized by evidence.
8. **Editing substrate** (§11): the demo path has no versions. Not a blocker for Phases 0–3; a prerequisite for the editing commands.
9. **Terrace/void accounting** is new; the 2D wall model does not know the ground roof is outdoors on L1. Accounting only (V7), but it is where "gross" can quietly double-count.
10. **Front-band and hub partis with a stair** are unproven. E3 proved the spine seat only. The front band's hall borders three things already; a stair in it is a fourth. Phase 1 supports the spine seats and says so.

---

## 13. Phased roadmap

Regression gates common to every phase: `tests/vertical_slice/test_baseline_and_decoupling.py` (frozen numeric baseline: 170.4 / 153.83 m², 11 rooms, 7 doors, 9 windows, 18 checks), the four `architectural_concept_samples` and `spatial_v2_1_samples` report JSONs, `test_general_pipeline` (site-driven scenarios), `test_demo_p0`, `test_demo_outline_selection`, `test_outline_offer`, `test_strip_rooms` (79/110), `test_hub_guard` — all byte-identical; and the 418-context sweep (`spikes/failure_log_sweep/ab.py`): every `stories == 1` primary byte-identical, LOST = 0, latency for already-planning briefs flat.

### Phase 0 — domain and contracts only

- **Possible**: `HouseConcept`, `Level`, `Building`, `LevelPlan`, `VerticalCore`, `LevelEntry`, `LevelContext` exist; `ArchitecturalSpec.concept` defaults; `DemoBuilding` is emitted *beside* `DemoPlanSet.plan` with one level; `floors` renders on review; the form/review label built area as *total*; `FLOORS_UNSUPPORTED` refusals are logged with the brief; the renderer accepts a `levels[]` of length 1.
- **Unsupported**: any `stories != 1` (still refused, now with a computed "two storeys could reach … m²" line when the allocation pre-check says so).
- **Byte-identical**: everything above, including `DemoDesign` JSON.
- **New invariants**: V7 accounting on one level equals today's gross/net; `Building(levels=[x]).levels[0].design is x`.
- **Complexity**: low (dataclasses, one pydantic wrapper, one label). ~1 week.
- **Measure**: nothing moves; count `FLOORS_UNSUPPORTED` refusals from here on.

### Phase 1 — two floors, one straight stair, one fixed allocation

- **Possible**: `stories = 2` with `public_private_strategy = PUBLIC_BELOW_PRIVATE_ABOVE` only (allocation set A, hard-coded as the *first* allocation rule, not a special case: `allocate_levels` exists and returns one set). Spine partis on both levels; private-only allocation family for L1; stair pinned at the hall column's rear or street end; upper outline = ground or single-side retreat; V1–V7; level tabs and stair symbol in the UI; grouped selection with two groups.
- **Unsupported**: master downstairs, front-band/hub seats, L/U stairs, balconies, different upper outline, editing.
- **Byte-identical**: all Phase 0 gates; every `stories == 1` primary in the sweep.
- **New invariants**: V1 alignment, V2 containment, V4 cross-level reachability, V5 arrival faces circulation; the stair's roles stay `(STAIRWELL,)` so C14 keeps measuring the corridor and C20/C21 hold the flight to its template.
- **Complexity**: **high** — the generator items (a)–(d) in §8, the coordinator, the building validator, the contract and two UI components. 4–6 weeks; the generator half is the risk.
- **Measure**: on the sweep, for each brief with `built_area_m2 > one_storey_capacity` or with the capacity note: does a two-storey building plan, at what share of the request, with what stair area and circulation share, and how many seats were tried per success (the E3 1/72 number is the baseline to beat).

### Phase 2 — automatic room distribution between floors

- **Possible**: allocation sets A/B/C generated and pre-checked; `master_level`, `bedroom_grouping`, per-level wet-room invariants; FLEX per level; `level_area_preferences`; a per-brief choice of split by the engine when the concept says ENGINE; the "master downstairs" concept card.
- **Unsupported**: organisation preferences across levels, L/U stairs, balconies.
- **Byte-identical**: all Phase 1 gates plus every Phase 1 two-storey primary when the concept is fixed to A.
- **New invariants**: every level with a bedroom has a reachable full bathroom (per-level 007 invariant); a HARD level placement is honoured or refused with `ROOM_LEVEL_NOT_FEASIBLE`.
- **Complexity**: medium (pure allocation logic + tests; the coordinator loops over sets). 2 weeks.
- **Measure**: plans per brief across sets; how often set B beats A on delivered share; refusal codes by set.

### Phase 3 — multiple architectural concepts / examples

- **Possible**: concept cards on review with feasibility gating; `LayoutPreference`-style chips after generation (`circulation_style`, mirror, axis — the layout UX report's MVP) unified with `HouseConcept` ordering; "try in two storeys" chip; the concept's provenance on review; concept-grouped alternatives shown with labels.
- **Unsupported**: `public_open_side = GARDEN` (parti missing — stays hidden), L/U stairs, balconies, editing commands.
- **Byte-identical**: all prior gates; with no card chosen, output identical to Phase 2.
- **New invariants**: a card is shown only if its allocation pre-check passes; a chosen concept appears as a `requested` field; a PREFERENCE concept field that could not be honoured is reported in `unsupported`/warnings, never silently.
- **Complexity**: medium, mostly frontend + review contract. 2–3 weeks.
- **Measure**: card selection distribution; share of chosen concepts that planned; share of "engine decides" sessions where a chip was used afterwards.

### Phase 4 — cross-floor quality optimisation

- **Possible**: wet-stacking preference in seat ranking; stair-to-entrance distance; upper retreat placed for exposure; the §10.2 metrics reported per building; concept-grouped comparison in the UI ("שתי קומות: 96 % מהשטח, 14 % תנועה; קומה אחת: 78 %, 11 %").
- **Unsupported**: L/U stairs, balconies, editing.
- **Byte-identical**: all `stories == 1` gates; two-storey primaries may change *only* by the metrics' tie-break rule, and each change is listed in the phase report (the 008 discipline).
- **New invariants**: none hard; V3 wet-stacking is a preference and stays one.
- **Complexity**: medium. 2 weeks.
- **Measure**: quality metrics M1–M6 per level plus the vertical ones, on every two-storey plan in the sweep, before/after.

### Phase 5 — richer massing, balconies, terraces, advanced stairs

- **Possible**: different upper outline (still ⊆ ground); balconies as `OutdoorRegion(BALCONY)` on L1 with accounting; L/U stairs as a two-leaf or lobby-adjacent core for the hub parti; row sharing if Phase 1's measurement says the seat region is the bottleneck; a `DemoDesignVersion` and the §11 editing commands.
- **Unsupported**: cantilevers (V2 stays), basements/split levels, 3+ storeys unless the allocation generalises trivially (it should — `levels` is a list — but the massing and the stair pairs do not).
- **Byte-identical**: all earlier gates.
- **New invariants**: balcony ⊄ interior; `STAIR_VOID` accounting for L/U; V6 if a second safe room appears.
- **Complexity**: high, and each item is separable.
- **Measure**: as Phase 4, plus edit-command success/regeneration rates.

---

## 14. The smallest architecture, stated once

```
ArchitecturalSpec(plot, program, concept)
        │
        ▼
allocate_levels(program, concept) ──► [LevelProgramSet]          pure; HARD/PREF/ENGINE rules; ≤3 sets
        │
        ▼
massing coordinator: ground outline (feasible_options) × stair seat × upper retreat
        │      for each: run_general(L0 program, pinned STAIR_1) ; run_general(L1 program, pinned STAIR_1)
        │                └── EXISTING pipeline, unchanged below the generator's inputs
        ▼
BuildingValidator V1–V7  (per-level C1–C21 already ran inside run_general with a LevelContext)
        │
        ▼
Building{levels[], cores[], massing} ──► grouped selection ──► DemoBuilding (levels[0] == today's DemoDesign)
```

Three new things (an allocation function, a coordinator loop, a building validator), two extended inputs to the generator (a level's rooms instead of the whole programme; a pinned leaf), zero changes to Geometry Core, and a single-storey path that is literally the two-storey path with one level and no seats. The generator's real work — a private-only allocation family and a second forced rectangle — is a generalisation it already half-does (E2), not a branch. Everything that could have become a special case (`if stories == 2` in the validator, the renderer, the contract) is instead a list of levels of length one or two.

What this report recommends **not** doing: a second wing for the upper floor; a `floor` field on `ZoneSpec`; concept cards that promise geometry; a single ranking pool; L/U stairs before a straight one is measured; and any regulatory number in code.

---

*End of report. No implementation was started; the E1–E3 scripts were session scratch and are not in the repository.*
