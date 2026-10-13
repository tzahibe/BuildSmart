# ADR-001 — A shape-agnostic realization architecture (Gate 1, #197)

**Status:** proposed — Gate 1 deliverable, day 1 of the 5-day time-box.
**Decision owner:** product owner (GO / PIVOT / STOP at each gate).
**Supersedes:** the L-shape checkpoint of 2026-10-13 10:41 (owner correction 11:24).

Every claim about the current code below was read from the code on `main` today, with the file
and line it comes from, not from memory or from a report.

---

## 1. The question

Translate an Architectural Brain's design intent — programme, contacts, doors, zoning, exposure,
frontage, area — into geometrically valid, editable floor plans **across broad classes of
building footprints**, with the footprint either an input constraint (buildable envelope) or a
design variable, **without a realizer per shape**, and without weakening a single validator.

## 2. Where the rectangular / band assumptions actually are

The expected answer was "everywhere". It is not. Read layer by layer:

| layer | module : line | what it assumes | shape-agnostic today? |
|---|---|---|---|
| **site input** | `app/demo/site_geometry.py:22` | *"Rectangular parcels only, with one of the four cardinal edges facing the street. No polygons"*; setbacks → a buildable **rectangle** | **no** |
| **outline search** | `site_geometry.feasible_options:384`, `l_massings:484`; `demo/service.py:444` | ≤4 (width, depth) rectangles of the requested area + 2 fixed-arm L massings, enumerated, chosen by plannability | **no** — the footprint is picked from a menu, never designed |
| **production placement** | `geometry_core/model.py:373-400` (`Leaf`/`Split`/`Cut`), `engine.solve_fixture` | a binary slicing tree per wing → **guillotine only** | **no** — 0/19 real plans are guillotine-separable (`docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md:29`) |
| **brain placement** | `band_embedding.embed_band` (exact, complete for the band family), `graph_embedding` | rooms in horizontal bands, every room spanning its band's full depth, **inside one rectangle** → one `GridWing` | **no** — one rectangle |
| **brain sizing** | `band_sizing.solve_band_layout` | R band heights × C column widths; `sum(w) ≤ w_max, sum(h) ≤ h_max`; per-cell `[min,max]` **bounds only, no target** | **no** — tiles one rectangle |
| **realizer composition** | `rectilinear_realizer.realize_layout:1246-1258` | wings placed **side by side along x at a shared top line** (`cursor_x`; `origin[1]` fixed); `buildable` is a `Rect` sanity check; seam doors only for left/right seams (`seam_left_ids`/`seam_right_ids`, :1330-1340) | **partly** — multi-wing exists, but only horizontally stepped unions |
| **realizer wings** | `PinwheelWing` / `RowWing` / `GridWing` (:154-256) | each wing is a **rectangle** tiled by rect cells; polygon rooms only as a `ShapeGroupIntent` (notch-carve L/U/T) inside a `RowWing` | **partly** |
| **footprint primitive** | `footprint.py:1-15` | footprint = `tuple[Rect, ...]` of non-overlapping wings; bbox = "the building line"; `remainder_within_bbox` → crook/notch as GARDEN; *"any polygon type — deliberately not here"* | **yes, for unions of rectangles** |
| **walls** | `realize_layout:1270-1300` | PARTITION/EXTERIOR/OPEN/RC derived from rect touching, any arrangement | **yes** |
| **entrance** | `doors.resolve_entrance:201-258` | street = bbox **y = min** line; a room fronts it when its **own wing** reaches that line | **yes** (wing-aware), street fixed to one bbox edge |
| **exposure / windows** | `geometry_adapter.envelope_sides:91-103`, `windows.py:112` | a side is exterior when on the room's **own wing's** edge and not a declared seam | **yes** |
| **validators** | `validation.py` C2 (:323 — *wings' area, not the bounding box*), C19/C8 (:503, wings), C22 (:776, seams) | consume `dict[str, Rect]` + `site.wings` | **yes** — with rect-formula leftovers: **C27** `width × depth == area` (:159), **C9/C30** inscribed rectangle, **C14** corridor width = short axis |
| **polygon rooms** | `room_merge.py` (LIVING+KITCHEN, **live in the product**), `rectilinear_realizer._group_checks:1075` | an N-cell union with OPEN internal walls, validated by redesigned C1/C2/C3/C20/C27 per group | **yes, via cell groups** |
| **preservation / critic** | `topology_preservation.py` (0 references to wing/footprint), `proposal_critic.py` | graph-level | **yes** |
| **payload / renderer** | `design_output.py:116` `footprints_m: tuple[RectM,...]`, `RoomOut.polygon_m`; `DemoPlan.tsx:117` draws every wing, `:135` draws polygon rooms | | **yes** |
| **IR precedent** | `stage2/contract.py:137` `SeedCell.polygon_m`, `SeedGeometry` | polygon cells, donor frame — **types only, no caller** | n/a |

**The diagnosis, precisely:** the rectangle assumption is concentrated in **three places** —
(1) the site input, (2) placement + sizing inside one rectangle, (3) the realizer's x-stacked
wing composition. Everything downstream of a placed `dict[str, Rect]` + `wings` is already
wing-aware, and Issue #108's spike proved the whole downstream accepts a non-tree `dict[str, Rect]`
with **zero code changes**. The general realizer is therefore a **placement-and-composition
problem over a union-of-rectangles footprint**, not a rewrite of thirty validators.

### Exterior shape vs room shape — distinguished

- **Exterior shape** = the union of wing rectangles. Any orthogonal polygon **without holes** is a
  finite union of non-overlapping rectangles, so the primitive already covers L, T, U, Z, stepped
  and offset wings. A **courtyard** (a hole) is representable as a union too, but the hole would be
  classified by `remainder_within_bbox` as garden and its walls as exterior by `envelope_sides` —
  plausible, **untested**, and named as a Gate-3 question, not assumed.
- **Room shape** = rectangular cells; non-rectangular rooms exist only as cell groups with OPEN
  internal walls (`room_merge`, notch-carve), and C27/C9/C14 are rectangle formulas. The corpus says
  41.9 % of real rooms are rectangles and 19.6 % simple L's. **Decision: orthogonal footprints
  first, rectangular rooms, polygon rooms only through the existing group mechanism.** General
  polygon rooms are a later, separate decision with their own validator redesign (C9/C14/C27), and
  nothing in this ADR depends on them.

## 3. The common spatial IR

One intent object in, one placement object out. Both are **shape-free**: nothing in either names
a parti, a band, or a letter.

```
SpatialIntent                                   (all of this exists today, scattered)
  programme   : {room_id → role, net area target/min/max, min short side, max aspect}   ZoneIntent
  contacts    : undirected pairs that must share a wall                                  spatial
  access      : directed pairs that must carry a door, incl. ENTRANCE → entry room       access
  zoning      : public / private / wet / circulation sets                                derived from roles
  exposure    : REQUIRED / PREFERRED / NONE per room                                     exposure_policy
  frontage    : which envelope edge is the street; the room that receives arrival        E1 / ENTRY
  envelope    : an ORTHOGONAL POLYGON the building must lie inside            ← NEW (today: a Rect)
  footprint   : FIXED (a given union of rectangles)  |  FREE (gross area ± tolerance)   ← NEW
  hard / soft : hard = non-overlap, inside envelope, every contact, every door with its
                width, REQUIRED exposure, every bound, area tolerance, wet-room entry policy;
                soft = circulation share and proportion, garden frontage, zoning compactness
Placement                                        (what the downstream already consumes)
  cells   : {cell_id → Rect}, cell → zone, optional cell groups (OPEN walls)
  wings   : tuple[Rect, ...]  — the realized footprint, non-overlapping
```

Verification is the **unchanged** chain: walls → doors → windows → `validate()` (30 checks) →
`topology_preservation`. Refusals are typed at the stage that failed: `REPRESENTATION` (a graph no
rectangle dissection can carry — K4, triple-lens; decidable before any geometry),
`ENVELOPE_INFEASIBLE`, `SIZING_INFEASIBLE`, `NO_ENTRANCE`, `VALIDATION_FAILED`, and the area
verdicts from Stage 3.

## 4. Candidate general formulations

### A — Band embedding generalized to a *staircase* of bands inside an orthogonal polygon

Keep `band_embedding` exactly as it is (it decides *which rooms share which band and in what
order*; it is exact and complete for its family and knows nothing about the envelope). Change the
**sizing**: instead of every band spanning one common width, each band gets its **own width and
its own horizontal offset**, constrained to lie inside the envelope polygon at that depth. Change
the **composition**: wings carry explicit `(x, y)` origins (today `realize_layout` forces a shared
top line and x-stacking — a dozen lines), and seam-door discovery works on any axis (today
left/right only).

- *Covers:* every **horizontally convex** orthogonal polygon — every horizontal line meets the
  building in one segment: rectangles, L, T, Z, stepped, offset wings, and U/C/H when the opening
  faces east or west (or the whole thing transposed). With a FREE footprint, non-rectangular
  shapes emerge from the exposure and contact constraints themselves, not from a template.
- *Does not cover:* a band with a gap (U opening north/south, courtyard). That is a declared
  extension (a row = several intervals, with the gap classified), not a Gate-2 claim.
- *Exact:* yes — band embedding is complete; sizing is an exact difference-constraint system
  (`band_sizing`'s own Bellman–Ford over column prefix sums, per band).
- *Reuse:* highest — `band_embedding`, `band_sizing`'s solver core, `realize_layout`'s wall /
  door / window / validator chain, `footprint.py`, the renderer. New code is the per-band
  width/offset constraint and explicit wing origins.
- *Limits, stated:* the band family is a strict subset of rectangular dissections, so some
  contact graphs that *are* rectangle-realizable are refused as `EMBEDDING` rather than solved;
  and K4 / triple-lens graphs are refused by representation — a true limit of rectangles, not of
  this method.

### B — Exact MILP over rectangle cells inside an orthogonal polygon

Variables x, y, w, h per room; relative-position binaries (left/right/above/below) for
non-overlap; a contact is a shared boundary ≥ its door width expressed with the same binaries;
"inside the polygon" is a disjunction over the polygon's rectangle decomposition. Solver:
`scipy.optimize.milp` (HiGHS) — **already installed**; `python-sat` is banned in production and
nothing new is procured.

- *Covers:* any orthogonal polygon **including holes**, and any rectangle dissection — strictly
  more than A.
- *Costs:* area is bilinear (w·h) — needs linearization (a fixed grid of admissible widths, or
  piecewise bounds), O(n²) binaries, and a search budget; 10–15 rooms is tractable, runtime is
  the risk. Not a product path on its own.
- *Reuse:* same IR, same output, same downstream. The right **oracle**: when A refuses, B decides
  whether the case is infeasible or merely outside A's family — which is exactly the
  "unsatisfiable input vs solver failure" distinction the gates demand.

### C — Topology-first continuous placement + repair

Place rooms by force/gradient from the contact graph, snap to the grid, repair violations.
Flexible for any polygon; **heuristic, no completeness, and repair loops are the #127/#134
failure mode this project already stopped once**. Not recommended as primary; useful later as a
diversity source feeding A/B's exact check.

### D — Guillotine partition of a polygon — **rejected**

Slicing a polygon hierarchically reintroduces the structure that 0/19 real plans have.

### Recommendation

**A as the spike's single algorithm, B as the exact oracle beside it**, one IR, one output,
unchanged downstream. A is the smallest change that turns the footprint into a design variable
and reuses the most proven code; B keeps the project honest about *why* a case failed. Rooms stay
rectangles; polygon rooms stay a cell-group mechanism; courtyards and north/south-opening U's are
named extensions, not claimed.

Unavoidable limits I will not paper over: rectangle dissections cannot carry K4 or triple-lens
contact graphs (any method); A's family is narrower than all dissections; C27/C9/C14 remain
rectangle formulas until a separate polygon-room decision.

## 5. The spike (Gate 2 design)

Same IR, same algorithm (A), the six frozen cases in `cases/frozen-six.json` — declared **before**
any code and never edited to flatter a result. Per case: input, hard constraints, expected verdict,
and the current rectangular baseline. Harness: `backend/app/ai_harness/shape_agnostic/`,
reproducible by one command; output per case: placement, realized geometry through the unchanged
validator chain, preservation n/n, exposure, area verdict, runtime, typed refusal, and a real
`DemoPlan` render.

Smallest decisive code changes, none shape-specific:
1. `SpatialIntent.envelope` as an orthogonal polygon (a rectangle is the degenerate case).
2. `band_sizing`: per-band width/offset bounded by the envelope's horizontal extent at that depth.
3. `realize_layout`: wings with explicit origins; seam-door discovery on both axes.
4. Nothing in `validation.py`, `doors.py`, `windows.py`, `exposure_policy.py`, `footprint.py`.

**Gate-2 NO-GO conditions I accept:** success requiring a per-case branch; any relaxed
constraint; a render that does not match the validated geometry.

## 6. Roadmap with gates

| gate | evidence required | verdict rule |
|---|---|---|
| **1 — architecture** (day 1, this ADR) | the table in §2, the IR in §3, ≥3 formulations in §4, frozen six | NO-GO if no reusable formulation with a testable path |
| **2 — algorithm** (day 3) | ≥4/6 frozen cases solved by A under the same code path, all hard constraints, real geometry + renders, runtime and refusals recorded; B used only to classify A's refusals | NO-GO on per-shape branches, silent relaxation, misleading renders; partial → documented PIVOT |
| **3 — product potential** (day 5) | ≥5/6 usable, unchanged validators, no invalid door / unreachable room / extreme corridor, legible renders, typed failures, ≤30 s per case, materially different alternatives where feasible | GO only with evidence on every axis; math-passes-quality-fails → PIVOT to objectives/search |
| **after GO** | wire the general placement behind `?engine=brain`; `envelope` from the real site (setbacks → polygon) ; polygon-room decision as its own ADR | owner approval for any rollout |

## 7. What user inputs decide the footprint, and what the planner decides

**Inputs (the customer's, never invented):** the plot polygon and its street edge; setbacks →
the **buildable envelope** (today a rectangle; the IR takes a polygon); the requested **gross
built area** with a stated tolerance; orientation / street-vs-garden preference; any fixed
features. **Not an input:** the building footprint. Plot size is not building size — Stage 3's
area verdict exists precisely because B09 asked for 440 m² on a 440 m² footprint that its own
room list could not fill.

**Design freedom (the planner's):** which wings, where, how deep; which rooms front the street and
which the garden; where the entrance and circulation go — all chosen to satisfy the hard
constraints and score the soft ones. When the owner *wants* a shape, that is `footprint: FIXED`;
when the owner wants a good house, `footprint: FREE` and the shape is an outcome.

## 8. What this ADR does not claim

No arbitrary-polygon geometry. No polygon rooms beyond the existing group mechanism. No
courtyards until the hole question is tested. No change to any validator, access rule, exposure
policy or room bound. Production stays byte-unchanged behind the default-off flag.
