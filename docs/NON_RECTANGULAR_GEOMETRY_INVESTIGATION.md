# Non-rectangular geometry investigation (Issue #102)

**Investigation only — no implementation, no product code changed.** Owner decision 2026-09-22
("תבצע על פי המלצתך") after the POC Architectural Brain demo: every plan BuildSmart produces today
is a slicing-tree (guillotine) partition of rectangular wings into rectangular rooms, so the engine
can change organisation (hub / branched / wings / zoning) but never the SHAPE language of the plans
in the real corpus. This report gives the numbers to decide the next step.

## 1. Summary

- The Geometry Core (`app/vertical_slice/geometry_core/`) is a **binary slicing tree over
  axis-aligned rectangles** — `Rect`, `Leaf`/`Split`/`Cut`, one rectangular `Wing` per footprint
  piece. Every zone becomes a rectangle by construction; there is no code path that can produce an
  L-shaped room or a non-guillotine layout today (only the massing ENVELOPE can be an L of two
  rectangular wings — `l_parti.py`, feature 006).
- Almost every downstream module — doors, windows, entrance, hub/L-massing/wet-core guards, M1-M6
  quality metrics, the demo contract, the SVG renderer, the frontend canvas, the corpus regression
  signature — is typed against `Rect`/`x, y, width_m, depth_m`, not against a general polygon. Most
  of this is a **NEEDS POLYGON VARIANT** rewrite (the check's own PURPOSE survives, its
  implementation does not); a smaller, load-bearing set — the solver itself, C2 ("no residual
  area"), C9 (furniture-envelope inscribing), C22 (wing-seam proof), C27 (gross = width × depth),
  the corpus signature, the demo contract's room shape, the renderers — is **MUST BE REDESIGNED**:
  the check's own DEFINITION assumes a rectangle or a slicing-tree partition, not merely its data
  type.
- **Measured** (deterministic script, 20-plan committed fixture — 19 real ResPlan plans + 1
  synthetic control; see §3 for sample-size caveats): **41.9% of real rooms are rectangles**
  (44.2% in the 3–5-bedroom subset) after 10 cm vertex simplification, **19.6% are simple
  L-shapes**, the rest (38.5%, or 27.4% once digitisation-artefact slivers are excluded) are more
  complex polygons. **0/19 plans have a rectangular building envelope** and **0/19 plans' room
  layouts are guillotine-separable** — every real plan measured needs at least one cut that would
  cross a room to separate its rooms with straight lines. This is the sharpest, most load-bearing
  number in this report: it means architecture B (still-rectangular rooms, but a general
  dissection) is a genuine, non-trivial step up from today, not a formality.
- **Recommendation**: pursue **A (slicing tree + room merging)** first — it is the cheapest,
  lowest-risk step that produces real L-shaped PUBLIC rooms (the architecturally highest-value case:
  §5's gap 3, "public rooms come out as strips") while reusing the entire rectangular solver,
  validator suite and corpus-regression signature unchanged. Propose it as the first child of a new
  ROOT; **B is the honest fix for the 0% guillotine-separability finding** and is proposed as
  ROOT-level research to run in parallel, not blocked on A; **C is out of reach at V1's resourcing**
  and is recorded as a longer-horizon option only. See §6.

## 2. Module-by-module rectangle-assumption inventory

Classification: **SHAPE-AGNOSTIC** (works unchanged on a polygon room today, or would if the input
type were swapped for a polygon with no logic change) · **NEEDS POLYGON VARIANT** (the check's
purpose is shape-independent but its current implementation is typed/computed against a rectangle
and needs a genuine rewrite) · **MUST BE REDESIGNED** (the check's own definition assumes a
rectangle or a guillotine partition — a data-type swap is not enough, the algorithm itself changes).

### 2.1 Geometry Core (solver)

| Module | Evidence | Classification |
|---|---|---|
| `Rect` (axis-aligned rectangle, grid units) | `app/vertical_slice/geometry_core/model.py:50-81` | MUST BE REDESIGNED — the one geometric primitive every downstream module reads |
| `Leaf`/`Split`/`Cut` (binary slicing tree) | `model.py:373-400` | MUST BE REDESIGNED — this IS the guillotine-partition architecture |
| `Wing` (one rectangular wing, own tree) | `model.py:405-421` | MUST BE REDESIGNED for a free envelope; already generalises to 2 rectangular wings for an L massing (`l_parti.py`) |
| `assign()` (recursive Rect → Rect tiling) | `app/vertical_slice/geometry_core/engine.py:247-291` | MUST BE REDESIGNED — the actual tiling algorithm |
| `net_rect_m()` (net width/height/area from a Rect + wall insets) | `engine.py:536` | MUST BE REDESIGNED — width × height net-area math assumes a rectangle |
| `solve_fixture()` | `engine.py:498` | MUST BE REDESIGNED — the solver entry point, typed `Fixture → dict[str, Rect]` |

### 2.2 Doors / windows / entrance

| Module | Evidence | Classification |
|---|---|---|
| `generate_interior_doors`, `_side_between`, `_swing` | `app/vertical_slice/doors.py:35-167` (`a: Rect, b: Rect`) | NEEDS POLYGON VARIANT — "a door where two rooms touch" is shape-agnostic in principle; every function here is 100% `Rect`/`Side` (N/S/E/W) typed, the most extensive rewrite in this bucket (swing arc, hinge point, shared-edge length all need a general polygon-edge replacement for the `Side` enum) |
| `resolve_entrance`, `street_fronting_roles`, `build_entrance_door` | `doors.py:167-282` | NEEDS POLYGON VARIANT — same `Rect`/`Side` typing |
| `generate_windows`, `_widest_exterior_side`, `seam_sides_of` | `app/vertical_slice/windows.py:75-150` | NEEDS POLYGON VARIANT |
| `access_rules.py` (door role-pair rules, C24) | role-pair table over `ProgramRole`, graph-based | SHAPE-AGNOSTIC |
| `exposure_policy.py` (window/exterior-wall policy table, C19/C8 input) | role → tier table | SHAPE-AGNOSTIC (the POLICY; the geometric test it feeds is NEEDS POLYGON VARIANT — see C19/C8 below) |

### 2.3 Validators — every check in `validate()` (C1-C29)

All inline in one function typed `validate(fixture: Fixture, rects: dict[str, Rect], walls:
WallMap, ...)` — `app/vertical_slice/validation.py:223` — so the ENTRY POINT itself is
rectangle-typed regardless of any individual check's own logic.

| Check | What it holds | Evidence | Classification |
|---|---|---|---|
| C1 | no overlap between rooms | `validation.py:248-256` (`Rect.overlap_area_u`) | NEEDS POLYGON VARIANT — polygon-intersection is a standard Shapely op |
| C2 | no residual interior area | `validation.py:258-264` | MUST BE REDESIGNED — true by construction of the exact rectangle tiling today; for a general partition this becomes a real coverage proof (room-polygon union == footprint, no gaps/double-counted area) |
| C3 | room areas/dims valid vs `ZoneSpec` (net area, min short side, aspect) | `validation.py:266-279` (`net_rect_m`) | NEEDS POLYGON VARIANT — "narrowest inscribed width" and oriented aspect both have well-defined polygon equivalents (the POC's `patterns.py::_oriented_long_short` is a working precedent) |
| C4 | safe room valid (RC envelope, authoritative constraint realized) | `validation.py:333` | NEEDS POLYGON VARIANT — "sealed on every side" generalises to every polygon edge being RC |
| C5 | all required spaces accessible (realized graph) | `validation.py:357` | SHAPE-AGNOSTIC — pure graph reachability |
| C6 | no artificial doors in open-plan | `validation.py:397` | NEEDS POLYGON VARIANT — reads `WallFacts.construction` per rectangle side |
| C7 | doors physically placeable | `validation.py:408` (`Rect.shared_edge_len_u`) | NEEDS POLYGON VARIANT — shared-boundary length is a standard polygon op |
| C8 | daylight/window exposure present where required | `validation.py:435` | NEEDS POLYGON VARIANT |
| C9 | furniture-envelope feasibility (inscribe a bounding rectangle) | `validation.py:442` | MUST BE REDESIGNED — inscribing a fixed rectangle in an L-shaped room's *usable* sub-area is a materially harder geometric problem (packing/inscribed-rectangle-in-polygon), not a data-type swap |
| C10 | parking connected to street | `validation.py:467` | NEEDS POLYGON VARIANT |
| C11 | pedestrian entrance connected to house | `validation.py:481` | SHAPE-AGNOSTIC — graph/site reachability |
| C12 | garden explicitly classified | `validation.py:495` | SHAPE-AGNOSTIC — a classification tag, not a shape fact |
| C13 | every declared access edge is physically realized | `validation.py:537` | SHAPE-AGNOSTIC — graph |
| C14 | realized corridor meets requested width | `validation.py:569` | NEEDS POLYGON VARIANT, bordering MUST BE REDESIGNED — "width" of a bent/non-rectangular corridor needs a genuinely new definition (e.g. minimum inscribed width along the walking path), not just the short axis of a rectangle |
| C15 | requested room relationships (realized) | `validation.py:586` | SHAPE-AGNOSTIC — adjacency/access graph |
| C16 | front door on the wall of the room it names | `validation.py:500` | NEEDS POLYGON VARIANT — rectangle wall side today |
| C17 | realized bathroom access (specs/007 FR-9) | `validation.py:604` | SHAPE-AGNOSTIC — role/graph based |
| C18 | parking bays clear of the house | `validation.py:472` | NEEDS POLYGON VARIANT |
| C19 | required rooms touch an exterior wall (`envelope_sides`) | `validation.py:415` | NEEDS POLYGON VARIANT |
| C20 | realized rooms within their template's aspect ratio | `validation.py:281-306` (`net_rect_m` aspect) | NEEDS POLYGON VARIANT — same oriented-aspect generalisation as C3 |
| C21 | realized rooms within their template's max area | `validation.py:308` | SHAPE-AGNOSTIC — a pure area comparison, independent of how the area was computed |
| C22 | declared wing seams are real (proof P9) | `validation.py:654` | MUST BE REDESIGNED — "a wing seam is a leaf-boundary alignment fact" only exists because of the slicing-tree/`Wing` architecture; a free envelope has no seam concept in this form |
| C23 | entrance opens into an allowed arrival room | `validation.py:523` | SHAPE-AGNOSTIC — role check on the resolved entrance zone |
| C24 | access topology obeys the door rules | `validation.py:386` | SHAPE-AGNOSTIC — graph/role-pair check over the realized access graph |
| C25 | entrance-to-circulation dead-end rule | **not yet on `main`** — owned by Issue #22, branch `agent/22-entrance-to-circulation-integration-the`, not merged into this branch's base | NEEDS POLYGON VARIANT (prospective, from its proposal contract — a wall-adjacency/dead-end graph rule) |
| C26 | no extreme dedicated circulation | `validation.py:447`, `app/vertical_slice/circulation_metrics.py` | NEEDS POLYGON VARIANT — longest-segment/dead-end/turn-count all read `rect_m`/`WallFacts` today but generalise to polygon adjacency and a walked path |
| C27 | displayed dimensions consistent (`width_m × depth_m == area_m2`) | `validation.py:149` (`check_realized_dimensions`) | MUST BE REDESIGNED — the check's own FORMULA (`width × depth == area`) is only true for a rectangle; an L-shaped room's area is not its bounding-box product |
| C28 | doors usable (no door/door, door/wall, door/fixture collision) | **not yet on `main`** — proposed only, `.agent/proposals/roadmap/issue4-door-swing-clearance.md` | NEEDS POLYGON VARIANT (prospective) |
| C29 | wet-room privacy (who may enter) | `validation.py:641` | SHAPE-AGNOSTIC — role/graph based |

**Tally among the 27 checks implemented on `main` today**: 10 SHAPE-AGNOSTIC (C5, C11, C12, C13,
C15, C17, C21, C23, C24, C29), 13 NEEDS POLYGON VARIANT (C1, C3, C4, C6, C7, C8, C10, C14, C16,
C18, C19, C20, C26), 4 MUST BE REDESIGNED (C2, C9, C22, C27). C25/C28 are not yet implemented on
this branch and are classified prospectively above.

### 2.4 Building-level checks (multi-level, the "V" family)

| Check | Evidence | Classification |
|---|---|---|
| V2 — upper-level containment in the union of the level below | `app/vertical_slice/building_validation.py:105` | NEEDS POLYGON VARIANT — polygon containment/union is a standard Shapely op; today's implementation is rectangle-region based |
| V7 — per-level gross-area accounting | `building_validation.py:119` | SHAPE-AGNOSTIC — a pure area sum |

### 2.5 M1-M6 quality metrics and the corpus baseline

| Metric | Evidence | Classification |
|---|---|---|
| M1 habitable-room aspect (long/short) | `app/vertical_slice/quality_metrics.py:89` (`_habitable_aspects`) | NEEDS POLYGON VARIANT — oriented-bbox aspect, same precedent as C3/C20 |
| M2 share touching exterior envelope | `quality_metrics.py:94` (`_exterior_room_ids`) | NEEDS POLYGON VARIANT |
| M3 circulation share of total area | `quality_metrics.py` (`measure_design`, area ratio) | SHAPE-AGNOSTIC — pure area ratio |
| M4 doors onto hall / hall aspect | `quality_metrics.py:106` (`_hall_stats`) | door count: SHAPE-AGNOSTIC; hall aspect: NEEDS POLYGON VARIANT |
| M5 wet-room adjacency | `quality_metrics.py:127-152` (`_interior_adjacency`) | NEEDS POLYGON VARIANT — boundary-touching test, same as `wet_core.py` below |
| M6 public-zone contiguity | `quality_metrics.py:164` (`_public_zone_contiguous`) | SHAPE-AGNOSTIC — graph connectivity over declared open groups |
| `quality_baseline.json` corpus regression | `tests/regression_corpus/test_quality_baseline.py` | inherits whichever of the above changes; itself SHAPE-AGNOSTIC as a comparison harness |

### 2.6 `hub_guard.py` / `l_massing_guard.py` / `wet_core.py`

| Module | Evidence | Classification |
|---|---|---|
| `hub_guard.PlanProportions`, `_aspect`, `_touching` | `app/vertical_slice/hub_guard.py:40-83` (`tuple[float,float,float,float]` bounds) | NEEDS POLYGON VARIANT — bounding-box proportions generalise from a polygon's own bounds without a conceptual change |
| `l_massing_guard.ExposureProportions`, `l_earns_representation_slot` | `app/vertical_slice/l_massing_guard.py:41-122` | NEEDS POLYGON VARIANT; its own PURPOSE (deciding whether an L envelope earns its representation slot) is partly subsumed by architecture C's free envelope, where every envelope needs this kind of quality gate, not just the L case |
| `wet_core._side_between`, `_shares_interior_wall`, `compute_wet_core` | `app/vertical_slice/wet_core.py:77-162` (`Rect`) | NEEDS POLYGON VARIANT — the POC's own `resplan_ingest.py` adjacency computation (`room_polys[a].distance(room_polys[b]) <= gap`) is a working polygon-based precedent for exactly this test |
| `l_parti.py` (two-rectangular-wing L massing, feature 006) | `l_parti.py:138,603,610` (`Rect(...)`) | NEEDS POLYGON VARIANT for a genuinely free (non-two-wing) envelope; already proves the multi-`Wing`/`Fixture` model can represent an L-shaped ENVELOPE (not room) today |

### 2.7 Demo contract, renderers, corpus signature

| Item | Evidence | Classification |
|---|---|---|
| `design_output.RoomOut.rect_m`, `GeometricDesign` | `app/vertical_slice/design_output.py:40-43,87` | MUST BE REDESIGNED — the solver's own output type is a rectangle |
| `contract.RoomOut` (`x, y, width_m, depth_m, gross_width_m, gross_depth_m`) | `app/demo/contract.py:74-95` | MUST BE REDESIGNED — the authoritative payload every consumer (renderer, frontend, quality metrics, C27) reads |
| `contract.DoorOut`, `WindowOut` (`x, y, width_m`) | `contract.py:128-140,288-297` | NEEDS POLYGON VARIANT — a door/window is a point + width on SOME boundary edge; the edge no longer has a fixed N/S/E/W identity |
| Backend SVG renderer | `app/vertical_slice/renderer.py:15,36,96` (`room.rect_m`; the module's own docstring already names "a future polygon solver") | MUST BE REDESIGNED — draws every room as an axis-aligned box |
| Frontend plan canvas | `frontend/src/design/DemoPlan.tsx:94-206` (`<rect x={room.x} y={room.y} width={room.width_m} height={room.depth_m} />`) | MUST BE REDESIGNED — every room, wing, parking bay and garden is an SVG `<rect>`; a polygon room needs `<polygon>` |
| Corpus regression signature | `backend/spikes/failure_log_sweep/sweep.py:71-81` (`signature()`: `(type, x, y, gross_width_m, gross_depth_m)` per room) | MUST BE REDESIGNED for a polygon room's own signature — directly gates the 432-context corpus regression budget every Issue in this repo must protect; see §5 per architecture |

## 3. Measurement

**Script**: `backend/spikes/geometry_shapes/measure_real_plan_shapes.py`. Deterministic; no network,
no randomness. Reads `*.json` files shaped `{"plan_reference": {...}, "architectural_pattern":
{...}}` — the schema `spikes.architectural_brain.plan_reference.PlanReference.to_dict()` produces
on branch `integration/poc-architectural-brain` (`docs/reports/poc-architectural-brain/dataset.md`)
— with **no import dependency on that branch's code**, so it runs standalone here.

**Corpus fixture used**: `backend/tests/spikes/fixtures/geometry_shapes/plans/` — **20 plans (19
real ResPlan plans + 1 hand-built synthetic control)**, copied byte-for-byte from the same 20-plan
fixture already curated and licensed (CC BY 4.0, ResPlan — Abouagour & Garyfallidis 2025,
arXiv:2508.14006) on the POC branch for its own AC-2 (`backend/tests/architectural_brain/fixtures/`
there). Chosen deliberately over the POC's full 199-plan corpus (also on that branch, not this one)
because it is small enough to commit directly into THIS branch without depending on the unmerged
POC branches, while still being real, licensed, geometry — not a synthetic stand-in. **Sample-size
caveat, stated plainly**: n=19 real plans is a real but small sample, drawn for CIRCULATION-CLASS
diversity (FRONT_BAND/TWO_WING/BRANCHED/HUB_LOBBY/OTHER coverage per `build_fixtures.py`), not for
representativeness of footprint regularity — the fixture's own footprint fill-ratio distribution
(0.57-0.96, computed during this investigation) sits somewhat below the full 199-plan corpus's own
documented median (~0.82, `patterns.py`'s `L_FOOTPRINT_FILL_RATIO_MAX` comment), so this
investigation's envelope-shape share should be read as directional, not final. **First child of the
proposed ROOT (§6) is to re-run this exact script against the full 199-plan corpus once it is
reachable from an integration branch that includes both #102's work and the POC's** — that is the
natural, cheap way to firm these numbers up before committing to an architecture.

### 3.1 Room shapes (10 cm Douglas-Peucker vertex simplification, then classified)

- **RECTANGLE**: 4 vertices after simplification, area ≥ 97% of its own minimum rotated rectangle.
- **L_SHAPED**: 6 vertices, all edges axis-aligned (±5°), exactly one reflex (concave) vertex —
  a single notch removed from a rectangle.
- **OTHER**: everything else (more notches, non-orthogonal, or residual `CIRCULATION` shapes).
- **ARTIFACT** (this investigation's own robustness filter, not part of the POC's ingest):
  20/179 rooms (11.2%) — all `LIVING`-typed — are digitisation slivers under 1.0 m² (median
  0.18 m²). The POC's own ingest floors `CIRCULATION` components at 2.0 m² but applies no
  equivalent floor to `LIVING`/`KITCHEN`/`BEDROOM`/`BATHROOM` (`resplan_ingest.py`'s
  `MIN_CIRCULATION_AREA_M2` comment); these are excluded from the guillotine test below (an
  unfiltered sliver almost always defeats every candidate cut in its own plan) and reported as
  their own bucket here rather than silently dropped.

| | all real rooms (n=179) | 3-5 bedroom subset (n=154) |
|---|---|---|
| RECTANGLE | 75 (41.9%) | 68 (44.2%) |
| L_SHAPED | 35 (19.6%) | 32 (20.8%) |
| OTHER | 49 (27.4%) | 38 (24.7%) |
| ARTIFACT (< 1 m², excluded from guillotine test) | 20 (11.2%) | 16 (10.4%) |
| DEGENERATE | 0 | — |

17/19 real fixture plans have 3-5 bedrooms (the other 2 have 6+, since the POC corpus filter is
"≥3 bedrooms" for houses, uncapped) — the 3-5-bedroom subset is nearly the whole sample, consistent
with the POC's own corpus-level count (162+27+10 = 199/199 in the 3-5 range for the full corpus per
`dataset.md`).

### 3.2 Envelope shapes and guillotine-separability (n=19 real plans)

| | count |
|---|---|
| Rectangular envelope | 0/19 (0.0%) |
| L-shaped envelope (6 vertices, one notch) | 0/19 (0.0%) |
| Other/irregular envelope | 19/19 (100.0%) |
| **Guillotine-separable room layout** | **0/19 (0.0%)** |
| Non-guillotine room layout | 19/19 (100.0%) |
| UNKNOWN (no room geometry) | 0/19 |

**Guillotine-separability method**: a room set is guillotine-separable when a straight, full-length
cut (horizontal or vertical) exists that crosses no room's interior (tested against each room's own
non-simplified polygon, buffered −1 cm so a merely-touching boundary is never mistaken for a
crossing) and splits the rooms into two non-empty groups, recursively, down to singletons — the
standard slicing-tree recognition test, evaluated deterministically against every candidate cut
coordinate drawn from the rooms' own bounding-box edges. **Validated against a known-positive
control**: the fixture's one synthetic plan (`synthetic-spine-01`, a corridor with three bedrooms in
a straight row — trivially guillotine-separable by construction) correctly returns `True`, so the
0/19 result on the real plans is not an artefact of an always-False implementation.

**Envelope-shape caveat**: footprint vertex counts on this sample range 10-38 even after
simplification (median area-weighted fill-ratio ~0.74 on this sample) — real building envelopes
here have genuine multi-corner outlines (balcony steps, staircase notches), not merely digitisation
noise; a 4-vertex or 6-vertex simplified footprint never appeared on this sample. This is directional
(§3's caveat applies) but consistent with the POC's own full-corpus finding that the median footprint
fill-ratio is ~0.82 with no natural rectangle/non-rectangle gap in the distribution
(`patterns.py`'s `L_FOOTPRINT_FILL_RATIO_MAX` comment) — i.e. the full corpus likely shows some
share of near-rectangular envelopes this 19-plan sample happens not to include, but genuinely
rectangular building envelopes are not the norm either way.

### 3.3 Reference archetypes and census aggregates

The 36 curated reference archetypes (`docs/architecture_reference/references/index.json`, Issue
#30) carry a `footprint_family` enum — `rectangle` / `wide-rectangle` / `narrow-deep` / `L` /
`irregular` — at METADATA level only (`schema.json`'s `entry.footprint_family`); most entries are
`rights: metadata-only` with no copied geometry file at all. **No per-room polygon or per-room
shape data exists for these 36 archetypes — UNKNOWN by design**, not by omission: the collection's
own schema only ever intended an envelope-family label, never room-level geometry. Naming
convention alone (8 `l-*`, 4 `irr-*`, 8 `deep-*`/`wide-*`, 16 `rect-*` ids) suggests the curated set
already spans all five families, but this is a label the curator chose, not a measurement — also
UNKNOWN in the sense this report cares about (real polygon evidence). No separate "census
aggregates" document exists on `main` beyond this index and the POC's own `dataset.md` (§3.1's
source) — treated as the same UNKNOWN.

### 3.4 Reproducing this measurement

```
cd backend
uv run python spikes/geometry_shapes/measure_real_plan_shapes.py            # default: committed 20-plan fixture, 1.0 m^2 artefact filter
uv run python spikes/geometry_shapes/measure_real_plan_shapes.py --min-room-area-m2 0   # raw, no artefact filter
uv run python spikes/geometry_shapes/measure_real_plan_shapes.py --corpus-dir <path> --json  # any other PlanReference-shaped corpus
uv run pytest -q tests/spikes/test_measure_real_plan_shapes.py              # AC-2's frozen determinism test
```

## 4. Three candidate architectures

Each compared on: what it produces, what is reused unchanged, what needs a polygon variant, what
must be redesigned, its Concept Engine v2 fit (§5), corpus-regression protection, effort, risk, and
a 2-week spike that would prove or kill it.

### A — Slicing tree + room merging

**What it produces**: the engine stays exactly as it is; ONE zone is allowed to own TWO adjacent
leaves of the existing slicing tree (e.g. an L-shaped LIVING/KITCHEN, a bent corridor) by opening
their shared seam — a direct generalisation of the existing `contract.py` corridor-opening
precedent (`docs/wiki/architecture/geometry-validation.md`'s "Corridor opening is a contract
post-process" section — hall↔LDK wall opened at segment level, engine untouched). The merged
zone's OUTER boundary (union of its two rectangles) is a simple orthogonal polygon (an L, or a
longer bent shape for 3+ leaves) computed in the contract/renderer layer; the SOLVER still only
ever sees and tiles rectangles.

- **Reused unchanged**: the entire solver (`geometry_core/engine.py`), every SHAPE-AGNOSTIC check
  (§2.3), the corpus regression signature (rooms whose merge doesn't change their own
  `gross_width_m`/`gross_depth_m`/`x`/`y` keep an identical signature entry; a merged pair's two
  rows collapse to one — a small, controlled, and fully visible signature change, not a silent one).
- **Needs a polygon variant**: doors/windows on the new non-rectangular boundary (NEEDS POLYGON
  VARIANT bucket in §2.2), the NEEDS POLYGON VARIANT checks in §2.3 that read the merged zone's
  shape (C1, C3, C6, C7, C8, C14, C16, C19, C20, C26), M1/M2/M4/M5 for the merged room, `wet_core`
  adjacency if a merged room touches a wet room.
- **Must be redesigned**: C2 (residual-area proof, now a real union-coverage check for the merged
  pair only — every other room stays exactly as it is today), C9 (furniture inscription in the
  merged L — but only for the SPECIFIC rooms chosen for merging, which can be restricted to ones
  where a rectangular inscribed sub-area is trivially known: e.g. the union's larger rectangle),
  C27 (the merged room's own gross/net formula), the renderer's room-drawing primitive for exactly
  the merged rooms (an SVG `<polygon>` alongside every other room's existing `<rect>` — additive,
  not a rewrite of the whole renderer), the corpus signature's per-room tuple for merged rooms only.
- **Corpus regression protection**: strongest of the three — every plan that never triggers a merge
  (the overwhelming majority of the 432-context corpus today, since merging is a NEW, opt-in
  candidate path) produces byte-identical signatures; only contexts where a merge candidate wins
  primary selection would show a (visible, reviewable) signature change, exactly like the corridor-
  opening precedent's own regression discipline.
- **Concept Engine v2 fit**: plugs in cleanly at the realization seam — `concept_engine_v2.py`
  already filters `concept_generator.generate_concepts`'s candidates by `circulation_class` and
  realizes the first/best match through the existing `_realize` pipeline (`concept_spec.py:213`,
  `:354`); a merge candidate is simply another candidate the SAME filter can select, adding no new
  `ConceptSpec` field for V1 (later, a `merged_public_zone: bool` flag on `ConceptSpec` would let
  `patterns_for` prefer it for footprint families where the POC corpus shows a closed-adjacent
  kitchen/living, i.e. most of it — §3 of `dataset.md`).
- **Effort**: ~2-3 engineer-weeks / ~6-10 agent-days (one child Issue for the seam-opening/merge
  mechanism generalised from corridor-opening, one for the renderer's polygon-room primitive, one
  for the C2/C9/C27 redesigns scoped to merged rooms only).
- **Risk**: LOW-MEDIUM. The failure mode is architectural (a merge that produces an ugly L, not a
  crash) — the existing `l_massing_guard`-style realized-quality eligibility gate
  (`l_massing_guard.py:64`) is a direct precedent for gating which merge candidates earn a slot.
- **2-week spike**: implement ONE merge case only — LIVING+KITCHEN when they are adjacent leaves and
  `public_composition` would read `CLOSED_ADJACENT` (§3.1's own `dataset.md` evidence: this is 8/199
  in the POC corpus, small but real, and directly targets gap 3, "public rooms come out as strips",
  `docs/wiki/architecture/geometry-validation.md`'s measured-gaps section) — through contract +
  renderer only, gated behind a flag, measured against the 432-context corpus (LOST=0 required) and
  M1 (kitchen/dining aspect) before/after. Kill criterion: if the merge candidate never validates a
  merged room's C9 furniture inscription across a representative footprint sweep, or moves M1's
  kitchen median aspect by less than the reference gap it targets (2.75 → reference L-counter shape),
  the generalisation to more room-pairs is not worth pursuing.

### B — Non-guillotine rectangular layout

**What it produces**: rooms stay simple rectangles, but the PARTITION is a general rectangular
dissection (not a binary slicing tree) — e.g. a pinwheel/floorplan-graph representation (sequence-
pair, or an O-tree/B*-tree from the VLSI-floorplanning literature) with a constraint solver for
areas/adjacencies. This directly answers §3.2's sharpest finding: **0/19 real plans are
guillotine-separable**, so this is the architecture that closes THAT specific, measured gap without
touching room shape at all.

- **Reused unchanged**: every rectangle-typed downstream module needs no data-type change at all —
  `RoomOut`, the renderer, the corpus signature format, M1-M6's rectangle math, C3/C9/C20/C27 all
  keep working exactly as written, since every room is still `(x, y, width_m, depth_m)`.
- **Needs a polygon variant**: none, in the room sense — but doors/windows/entrance and every check
  that currently ASSUMES a room has exactly 2-4 straight-line neighbours via a leaf-boundary
  relationship (the slicing tree's own adjacency guarantee) need a general rectangle-adjacency graph
  instead — closer to a genuine algorithm change than a type swap.
- **Must be redesigned**: the solver itself (a fundamentally different search/optimisation problem —
  not tiling a tree, but placing N rectangles under area/adjacency/aspect constraints with no
  guillotine guarantee), C2 (coverage is no longer free by construction — every rectangular
  dissection must be proven gap-free and non-overlapping as a genuine geometric fact, same
  redesign shape as architecture A's C2 but applied to EVERY room, not just merged ones), C22 (wing
  seams have no meaning without a slicing tree — this check is simply retired, not ported), the
  corpus regression signature is at risk of a MUCH LARGER set of primary-signature changes than
  architecture A (a different partition algorithm can plausibly choose different room positions for
  many/most contexts, not just merge candidates) — the single biggest regression-protection risk of
  the three.
- **Concept Engine v2 fit**: same seam as A in principle — `ConceptSpec`/`circulation_class`
  (`concept_spec.py:48`) is a topology label, independent of how the topology is realized — but B's
  realizer is a genuinely new module behind that seam, not a small extension of the existing one;
  `realized_circulation_class` (`concept_spec.py:354`, currently `Rect`-typed) would need its own
  polygon-adjacency-graph rewrite regardless of room shape, since it reads Rect positions directly.
- **Effort**: ~8-14 engineer-weeks / ~25-40 agent-days (new solver, new adjacency-graph-based
  validator layer, corpus re-baselining work given the expected large signature churn, quality-tier
  and hub/L-massing guard rewrites since their own inputs — `PlanProportions` bounds tuples — would
  now come from an unfamiliar layout algorithm rather than a known tree).
- **Risk**: MEDIUM-HIGH. The solver itself is a genuinely different, harder combinatorial-
  optimisation problem (floorplanning is NP-hard in general; VLSI floorplanning tooling exists but
  adapting it to architectural constraints — access topology, exterior-wall requirements, wet-room
  adjacency — is unproven in this codebase); the corpus-regression risk above is real, not
  theoretical, given how much of this repo's own process (the Fixer loop, CI gates 4/#66/#67) is
  built around a stable, mostly-unchanging corpus signature.
- **2-week spike**: pick ONE reference archetype family (e.g. `l-3br-corner` or `irr-4br-courtyard`
  — already flagged non-rectangular envelope in `references/index.json`) and hand-encode its known
  real layout as a rectangular dissection (not solver-generated); prove ONLY that the existing C1/C3/
  C9/C20/C27/M1-M6/renderer/frontend pipeline accepts it with ZERO code changes once given a
  `dict[str, Rect]` that is not a slicing-tree output — i.e. prove the REUSE claim in the table above
  before investing in a real solver. Kill criterion: if any "reused unchanged" module in fact
  silently assumes tree adjacency (not just a `Rect` type) and needs a change to accept the
  hand-encoded layout, the reuse estimate above is wrong and B's effort number needs revising upward
  before further investment.

### C — Polygonal layout

**What it produces**: rooms as simple polygons inside a free (non-rectangular) envelope —
constraint/optimisation-based, seeded from adapted reference polygons (the POC's own normalised
`PlanReference.rooms[].polygon` geometry, `plan_reference.py:36-74`, is a ready-made source of real
starting layouts). Polygonal walls, doors, windows, validators throughout.

- **Reused unchanged**: role/graph-based checks only (the 10 SHAPE-AGNOSTIC checks in §2.3, plus
  M3/M6, C11-C13/C15/C17/C21/C23/C24/C29) — everything else needs at minimum a polygon variant.
- **Needs a polygon variant**: every NEEDS POLYGON VARIANT item in §2 (the largest count of the
  three architectures, since room shape itself is now free, not just the envelope or the partition).
- **Must be redesigned**: every MUST BE REDESIGNED item in §2 PLUS the entire solver (a genuinely
  new polygon-packing/constraint-optimisation engine — the hardest of the three problems: placing
  arbitrary simple polygons under area/adjacency/access/exposure constraints with no rectangle
  scaffolding at all), doors/windows placement on arbitrary polygon edges, furniture inscription in
  an arbitrary polygon (C9, now unbounded rather than "just the merged rooms" as in A), the
  renderer/frontend (full polygon rendering, not an additive `<polygon>` beside existing `<rect>`s),
  the corpus signature (a polygon fingerprint has no natural analogue to `(x, y, w, h)` — likely a
  simplified/hashed vertex list, itself a new design decision with its own tolerance questions).
- **Concept Engine v2 fit**: the POC's OWN `adaptation.py` (`RESIZE_ROOMS`/`BEDROOM_COUNT_ADJUST`/
  `WET_ZONE_ADJUST`, `adaptation.py:1-28`) already operates ONLY on room TYPE and AREA, never on
  shape — the POC's `ConceptSpec.baseline_rooms` carries no polygon field at all
  (`synthesis.py`/`adaptation.py`'s `AdaptedRoom(id, room_type, area_m2)`). This means **even the
  POC itself has not solved "adapt a retrieved reference's shape to a brief" — only its topology and
  areas** — so C's own realization step (turning an adapted room-area list back into real polygon
  geometry) is genuinely new work, not something the POC branches already provide a working
  precedent for. Agent 96 ("POC C/3: realization", branch `agent/96-poc-architectural-brain-c-3-
  realization`) exists but has not merged as of this investigation and was not read for this report
  (out of scope — implementation, not this Issue's own evidence gathering) — its content should be
  the FIRST thing read before any C spike, since it may already contain a partial answer.
- **Effort**: ~20-30+ engineer-weeks / ~60-100+ agent-days — the full rewrite of the geometry stack,
  every validator, both renderers, and the corpus-regression methodology.
- **Risk**: HIGH. This is a research-grade generative-layout problem (polygon packing +
  architectural constraint satisfaction) that BuildSmart's current codebase has no working
  precedent for at all (not even the POC — see above); the corpus-regression budget this repo relies
  on (432 contexts, byte-identical primaries, enforced by CI gates #66/#67/#71/#82) has no
  transferable meaning under architecture C without first defining what "the same plan" even means
  for two polygon layouts — a genuinely open design question, not an engineering task.
- **2-week spike**: take ONE already-adapted `ConceptSpec` from the POC's own `adaptation.py` output
  (room types + target areas, e.g. from `test_adaptation.py`'s fixtures) and attempt to place its
  rooms as simple rectangles-only (not yet polygons) inside ONE real ResPlan footprint polygon (from
  the committed fixture corpus) using an off-the-shelf constraint solver, with NO validator/renderer/
  contract integration — pure feasibility: can rooms of the adapted areas even be placed, at all,
  inside a real non-rectangular envelope without overlapping and touching the required exterior
  walls. Kill criterion: if this bare placement problem (rectangles in a free envelope, ignoring
  every other constraint) cannot be solved reliably in the spike's timebox for a representative
  sample of real envelopes, the full polygon version (harder in every dimension) is not worth
  pursuing before dramatically more research investment.

### Comparison at a glance

| | A — room merging | B — non-guillotine rect | C — polygonal |
|---|---|---|---|
| Closes the 0% guillotine-separability gap (§3.2) | No (only for merged pairs' own seam) | **Yes** | Yes |
| Produces real L-shaped rooms | **Yes** (merged pairs only) | No (rooms stay rectangles) | Yes |
| Corpus-regression risk | Low (opt-in, additive) | **High** (broad signature churn) | Unmeasurable without a new signature definition |
| Reuses the existing solver | **Yes, entirely** | No (new solver) | No (new solver) |
| Effort | ~2-3 eng-wk / 6-10 agent-days | ~8-14 eng-wk / 25-40 agent-days | ~20-30+ eng-wk / 60-100+ agent-days |
| Concept Engine v2 seam | Clean, no new field needed for V1 | Clean in principle, realizer is new | Clean in principle, realizer is new AND unsolved by the POC itself |

## 5. Fit with the Concept Engine and the POC

Concept Engine v2 (`docs/wiki/features/concept-engine-v2.md`, flag `CONCEPT_ENGINE_V2_ENABLED`,
default `False`) already separates TOPOLOGY from REALIZATION: `ConceptSpec`
(`app/vertical_slice/concept_spec.py:213`) carries `circulation_class`/`zoning`/`wet_core_grouping`
— the SAME vocabulary (`CirculationClass`, `concept_spec.py:48`) the POC's own `patterns.py`
measures on real ResPlan plans (`SPINE`/`HUB_LOBBY`/`BRANCHED`/`TWO_WING`/`FRONT_BAND`/`OTHER`) —
and `plans_per_class` (`concept_engine_v2.py`) filters the EXISTING rectangular generator's
candidates by that label, realizing the first/best match through the unchanged `_realize` pipeline.
This is exactly the `ConceptSpec → realization` seam the Issue asks each architecture to plug into:

- **Architecture A** needs no new `ConceptSpec` field for its first spike — a merge candidate is
  just another candidate `plans_per_class` can pick among. A `merged_public_zone` hint could be
  added later so `concept_patterns.patterns_for` (Issue #77) can PREFER it for footprint families
  where the POC corpus shows `CLOSED_ADJACENT` kitchens (`dataset.md` §3, 8/199 plans) — small but
  real signal, not invented.
- **Architectures B and C** plug into the SAME seam in principle (a new realizer registered where
  `_realize` is called today), but `realized_circulation_class`
  (`concept_spec.py:354`, currently reads `fixture`/`rects: dict[str, Rect]`/`walls` directly) would
  need its own polygon/rectangle-dissection-adjacency rewrite regardless of which architecture wins,
  since it verifies the realized geometry actually matches its intended concept — this work is
  common to B and C and should be scoped once, not duplicated per architecture.
- **The POC's own reference-adaptation operations** (`adaptation.py`) only ever touch room TYPE and
  AREA — `RESIZE_ROOMS`/`BEDROOM_COUNT_ADJUST`/`WET_ZONE_ADJUST` never read or write a room's shape.
  This means a retrieved ResPlan reference's TOPOLOGY is already adaptable (that is what Concept
  Engine v2 + the POC's synthesis/adaptation stage together do today); its SHAPE is not — none of
  A/B/C get shape-adaptation "for free" from the POC's existing code. Architecture A comes closest
  to needing none (it only opens a seam between two already-rectangular leaves); B needs a new
  layout-adaptation step from a reference's topology to a rectangle dissection; C would need the
  POC's own room polygons adapted in shape, which is unsolved by any POC branch read for this
  report (agent 96/"C-realization" may address this — unread, see §4.C).
- **What the POC demo would look like under each**: under A, the demo shows real L-shaped public
  rooms for a bounded set of footprint families, everything else unchanged — the smallest visible
  jump from today. Under B, every room in the demo stays a rectangle but their ARRANGEMENT can look
  like a genuine non-guillotine real plan (a bedroom wrapped on three sides by other rooms, matching
  gap 1 in the measured architectural-quality gaps — `docs/wiki/architecture/geometry-validation.md`
  — "one hall spine ... vs ~18/21 reference plans having a compact room lobby hub"). Under C, the
  demo could in principle show a genuinely retrieved-and-adapted ResPlan SHAPE, closest to the
  owner's original "why does everything look like rectangles inside rectangles" observation — at
  the cost and risk in §4.C.

## 6. Recommendation

**Pursue Architecture A first**, as the next ROOT's first 1-2 children — cheapest, lowest-risk,
reuses the entire existing solver/validator/corpus-regression machinery, and targets the
ALREADY-MEASURED, ALREADY-RANKED gap 3 ("public rooms come out as strips",
`docs/wiki/architecture/geometry-validation.md`'s measured-gaps section) directly. **In parallel,
not blocked on A**, run Architecture B's 2-week spike as ROOT-level research: §3.2's 0%
guillotine-separability finding is the single sharpest number in this report and deserves a real
answer about whether B's reuse claims hold before committing engineering weeks to a new solver.
**Architecture C is recorded as a longer-horizon option, not scheduled**: its effort/risk profile
and its dependency on unsolved shape-adaptation work (§5) make it a poor next step regardless of
how compelling the owner's original observation is.

**First measurable milestone** (before any of A/B/C's own spikes): re-run
`measure_real_plan_shapes.py` against the POC's full 199-plan corpus once an integration branch
carries both this Issue's script and `integration/poc-architectural-brain`'s corpus — firms up §3's
directional numbers (particularly the envelope-shape share, flagged as likely undercounting
near-rectangular envelopes on this 19-plan sample) before either spike reports its own result.

Proposed ROOT + children, contracts under `.agent/proposals/roadmap/`:

- **ROOT** `.agent/proposals/roadmap/root-102-non-rectangular-geometry.md` — "Non-rectangular
  geometry: close the guillotine-partition gap for public rooms (A) and prove/kill non-guillotine
  rectangular layout (B)".
- **Child 1** `.agent/proposals/roadmap/102-1-full-corpus-remeasurement.md` — re-run this Issue's
  script against the POC's full 199-plan corpus; firm up §3's numbers; no product code.
- **Child 2** `.agent/proposals/roadmap/102-2-living-kitchen-merge-spike.md` — Architecture A's
  2-week spike exactly as scoped in §4.A (LIVING+KITCHEN merge only, flagged off by default,
  432-context corpus regression required at LOST=0).
- **Child 3** `.agent/proposals/roadmap/102-3-non-guillotine-reuse-spike.md` — Architecture B's
  2-week spike exactly as scoped in §4.B (hand-encoded non-guillotine layout through the unchanged
  pipeline, proving or disproving the reuse claim).
- Both spikes report back to the ROOT before any further Architecture A/B work is authorized; the
  owner decides which (if either) proceeds to real implementation based on their results — this
  Issue makes no implementation commitment beyond the two spikes.

## 7. Out of scope, deliberately untouched

Per the Issue's own scope: no change to `app/` (product code), Geometry Core, validators, the
Concept Engine, or the POC branches; no implementation of any candidate architecture; no fine-
tuning. Agent 96's "POC C/3: realization" branch content was not read (see §4.C's note on why it
should be the first thing read before any Architecture C spike). This report and its script are the
only artefacts this Issue produces.
