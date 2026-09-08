# Safe Geometry Adapter V1 — Implementation Report

```
SAFE_GEOMETRY_ADAPTER = READY
NEXT_STEP             = INTEGRATE_GENERAL_GEOMETRY_WITH_VERTICAL_SLICE
```

**The question this task existed to answer** — *can arbitrary authoritative geometry be
transformed conservatively into solver-compatible geometry while preserving the existing
engine?* — **is answered yes**, across 11 shape fixtures and 4 end-to-end runs, with the subset
invariant verified against exact arc-aware geometry rather than against the adapter's own
approximation. Geometry Core is still byte-for-byte unchanged.

---

## 1. Which boolean/offset operations were required?

Five, and no more: `difference`, `union`, `intersection`, `offset_inward`, `offset_outward`,
plus a `contains_region` predicate. `difference` and `union` carry the real work
(`parcel − setback − exclusions − obstacles`); `offset_inward` exists because a uniform setback
is an offset and because it is the operation that can **disconnect** a region. No CAD kernel was
built: there is no arc-preserving boolean, no trimming, no filleting, no sweeps.

## 2. In-house or library, and why?

**Library: Shapely 2.1 (GEOS)**, declared in `pyproject.toml`. Robust polygon booleans are a
genuinely hard numerical problem — self-intersection, collinear overlap, near-degenerate slivers
and the topology repair they require are where hand-rolled implementations fail, usually
silently and non-reproducibly. GEOS is the engine under PostGIS. Hand-writing a Weiler–Atherton
would have been the single riskiest thing in this task and is not the problem BuildSmart exists
to solve.

Two containment rules keep the dependency from spreading:

- **No Shapely type appears in any public signature.** Everything converts back to domain
  `Region`/`MultiRegion`; `app/geometry_domain/booleans.py` is the only module that imports it,
  plus the adapter's rasterizer.
- **No library internals reach product callers.** GEOS exceptions become
  `BooleanOperationError`, and the adapter converts those into structured outcomes. A test
  asserts no outcome value mentions GEOS or Shapely.

Shapely has no arcs, so `_require_linear` refuses curved input rather than silently discarding
curvature — and that guard re-raises unwrapped, because "you forgot to linearize" is an
actionable caller error, not a library failure. (That masking bug was caught by its own test.)

## 3. How are arcs conservatively linearized?

`app/geometry_domain/linearize.py`. Every ring is first **normalized so the material is on the
left** (outer CCW, holes CW). After that one step the classification is uniform, because the
apex sits at `−bulge·d/2` along the left normal:

- `bulge > 0` → apex on the right → the arc bulges **away** from the material (convex)
- `bulge < 0` → apex on the left → the arc **bites into** the material (concave)

Then a two-by-two table with no exceptions:

| | convex arc | concave arc |
|---|---|---|
| **INNER** (subset — for KEPT regions) | inscribed chords | circumscribing tangent chain |
| **OUTER** (superset — for SUBTRACTED regions) | circumscribing tangent chain | inscribed chords |

Segment counts come from the tolerance: `R(1−cos(Δ/2)) ≤ tol` for inscribed,
`R(1/cos(Δ/2)−1) ≤ tol` for tangent chains. A test asserts the realized deviation is within
tolerance for bulges of 0.3, −0.3, 0.9 and 1.6, in both constructions.

**One research recommendation was dropped as unnecessary.** The architecture report said to split
arcs at `|bulge| = 1` before simplification. This implementation parameterizes by **angle**, not
by chord, so a 300° arc subdivides like any other and needs no special case. `is_major_arc`
remains available; nothing uses it. The split rule was an artifact of chord-based reasoning.

## 4. How is inside/outside orientation determined?

By ring orientation, never by bulge sign alone — the trap the architecture report flagged. A
circular hole is convex *as a circle* and concave *with respect to the material*; reading the
sign directly would chord-substitute every exclusion zone and design buildings into protected
clearances. Normalization makes the material's side canonical, and only then is the sign read.
Two tests pin this: the INNER approximation of a curved hole must **grow** the hole, and the
hole's centre must still be excluded afterwards.

## 5. Can subset containment be guaranteed?

**Test-wise, strongly; formally, by composition.**

The formal argument is that `P_inner \ (S_outer ∪ E_outer) ⊆ P \ (S ∪ E)` — an inner
approximation of what is kept, minus an outer approximation of everything removed, is a subset
of the truth.

The empirical guarantee is stronger than re-checking the approximation against itself:
`verify_candidate_within()` samples a 25×25 lattice over each candidate and tests every point
with the **exact arc-aware** `Region.contains_point`. Every one of the 11 shapes is verified this
way, and the 4 end-to-end runs additionally re-verify every solved **room** the same way.

Three mechanisms enforce it in the pipeline: directional linearization (above), a rasterizer that
marks a grid cell usable only when the cell is **entirely** covered (exact per-cell test near the
boundary, not a centre sample), and candidates built from whole grid cells.

## 6. How are holes handled?

Natively. `difference` of an interior obstacle produces a `Region` with a hole; the rasterizer
sees hole cells as unusable and the maximal-rectangle scan simply routes around them. Verified on
a circular clearance, a rectangular shaft, and three simultaneous holes. In the obstacle case the
four extracted rectangles tile the region around the shaft **exactly** — retention 1.000.

## 7. How are disconnected components handled?

Each component is rasterized and decomposed independently, and candidates carry
`component_index`. **Components are never merged to simplify solving.** The disconnected fixture
yields candidates in components 0 and 1; `offset_inward` on the narrow-neck hourglass splits one
component into two, which is exactly why every boolean returns a `MultiRegion`.

## 8. Which rectangularization strategy worked best?

**Greedy maximal-rectangle extraction on the quantized grid**, bounded to 4 candidates.

The grid is rasterized to 5 cm cells (a cell is free only if fully inside), then the classic
largest-rectangle-in-a-histogram scan runs in O(rows × cols). It subsumes all four strategies the
brief asked to compare: the first extraction **is** the maximum inscribed rectangle (A); repeated
extraction is the decomposition (B) and the candidate set (C); and the cell grid is itself the
orthogonal-cell decomposition (D), with the rectangles being its useful consumable form.

It won on three counts: it is exact on the grid rather than an optimization heuristic; it is
conservative by construction with no separate quantization step to get wrong; and it handles
holes and disconnection for free because those are simply False cells.

## 9. Does the L-shape retain useful structure?

**Yes — this is the clearest result in the task.** The L decomposes into `13.00 × 16.00` +
`5.00 × 9.50`, retention **1.000**: nothing is lost, and it does *not* collapse to its single
largest rectangle. Candidates record `adjacent_orders`, so the two wings know they share a
boundary — precisely the seam information a future concept generator needs to emit Geometry
Core `seam_leaf_sides` and treat the decomposition as wings. The existing engine already supports
multi-wing fixtures, so the structure survives all the way to something the solver can consume.

## 10. How much area is typically lost?

| Shape | Authoritative | Solver | Retention | Candidates | Residuals | Curve loss |
|---|---|---|---|---|---|---|
| exact rectangle | 203.00 | 203.00 | **1.000** | 1 | 0 | 0.000 |
| L-shaped | 255.50 | 255.50 | **1.000** | 2 | 0 | 0.000 |
| rectangular obstacle | 276.00 | 276.00 | **1.000** | 4 | 0 | 0.000 |
| disconnected | 258.00 | 258.00 | **1.000** | 2 | 0 | 0.000 |
| curved hole | 279.96 | 277.27 | 0.990 | 4 | 1 | 0.083 |
| concave facade | 277.73 | 272.00 | 0.979 | 1 | 1 | 0.106 |
| convex facade | 312.26 | 302.06 | 0.967 | 2 | 1 | 0.257 |
| multiple holes | 277.92 | 257.33 | 0.926 | 4 | 5 | 0.080 |
| mixed lines + arcs | 283.51 | 262.38 | 0.925 | 3 | 1 | 0.357 |
| strongly concave | 248.09 | 229.60 | 0.925 | 1 | 1 | 0.137 |
| **diagonal polygon** | 272.00 | 217.13 | **0.798** | 4 | 1 | 0.000 |

Orthogonal shapes lose **nothing**. Curved shapes lose 1–8%. The worst case is the **diagonal
polygon at 0.798**, and its curve loss is *zero* — every one of those 55 m² is lost to
axis-aligned fitting, not to arcs. This confirms the architecture report's prediction precisely:
**the orthogonal step, not the curve step, is where area actually goes.** Curve linearization
never exceeded 0.36 m² anywhere.

## 11. Are residual regions accurate?

Yes, and provably complete: `accounted_area_m2` = solver area + every listed residual + curve
loss + dropped slivers, and a test asserts it equals the authoritative area for all 11 shapes
(±0.02 m²). Nothing is silently lost — sub-threshold slivers are summed into
`dropped_residual_area_m2` rather than discarded.

Each residual carries area, thickness estimate (2× largest inscribed circle, by bisection on
erosion), max extent, adjacency to solver geometry, exterior exposure, and a source
(`CURVE_APPROXIMATION` / `RECTANGULARIZATION` / `EXCLUSION` / `DECOMPOSITION` / `OTHER`). **No
architectural use is assigned** — a test asserts residuals have no `suggested_use` attribute.

One deliberate choice: curve loss is reported as an exact **scalar**, not as residual geometry.
Emitting the band between the inner and outer linearizations produced 10–17 fragmented slivers
that both overstated the true loss and told a reader nothing. The scalar is exact
(arc-aware area minus linear area).

## 12. Does quantization ever expand geometry?

**No, and there is no quantization step to get wrong.** Candidates are assembled from whole grid
cells that were already proven fully inside, so they are grid-aligned by construction — strictly
stronger than converting metres to units with direction-aware rounding. The direction-aware
quantizers from the previous phase therefore appear nowhere in the adapter. A test on an
off-grid region (`0.02, 0.03, 5.11 × 4.07`) confirms every candidate stays strictly inside, and a
sub-cell region yields `NO_SAFE_SOLVER_GEOMETRY` rather than a rounded-up rectangle.

## 13. Did the original vertical slice remain numerically identical?

**Yes.** `run_demo` still produces gross **170.4 m²**, net **153.83 m²**, **2** iterations,
**12/12** checks — asserted both by the frozen baseline test from the previous phase and again
from within this task's suite. For an exact rectangular authoritative region the adapter is a
**no-op**: retention 1.000, zero residuals, zero curve loss, one candidate.

## 14. Did all four end-to-end cases run safely?

Yes. Each ran `general geometry → adapter → Geometry Core → doors → windows → furniture →
validation → GeometricDesign → renderer`:

| Case | Outcome | Rooms inside buildable | Clear of exclusions | Slice checks | Retention |
|---|---|---|---|---|---|
| A canonical rectangle | SOLVED | yes | yes | 12/12 | 1.000 |
| B L-shaped region | SOLVED | yes | yes | 12/12 | 1.000 |
| C concave curved facade | SOLVED | yes | yes | 12/12 | 0.979 |
| D one exclusion obstacle | SOLVED | yes | yes | 12/12 | 1.000 |

All four produce identical gross/net/iterations, because the same concept is realized by the same
untouched engine — only the **placement** differs. Case D's footprint is asserted to stop short
of the shaft at x = 17.6. Failure modes were exercised too: UNKNOWN returns
`BUILDABLE_REGION_UNKNOWN` with no design and no render file; an undersized region returns
`INSUFFICIENT_RECTANGULAR_CAPACITY`.

Renders were produced for all four. The renderer draws the design, not the site constraints — it
does not visualize the buildable boundary or obstacles, since extending it was out of scope.

## 15. Did Geometry Core require modification?

**No.** `geometry_core/model.py` and `engine.py` are unchanged, as is `concept.py`,
`doors.py`, `furniture.py`, `validation.py`, `design_output.py` and `renderer.py`. No adapter
hook was needed inside the solver. New modules only: `geometry_domain/linearize.py`,
`geometry_domain/booleans.py`, `vertical_slice/safe_adapter.py`,
`vertical_slice/geometry_fixtures.py`, `vertical_slice/general_pipeline.py`. `windows.py` was
untouched this phase. `pyproject.toml` gained the Shapely declaration.

**Tests: 578 passed** (459 before this task, +119 new). Nothing regressed.

## 16. What is the next real limitation?

**The concept, not the geometry.** The adapter now hands over safe rectangles — including
multi-wing decompositions with seam adjacency — but `concept.py` is still hand-authored for a
single `12.0 × 14.2` footprint and raises `NotImplementedError` for any other programme. So
every case above solves the *same house*, merely placed in a different legal envelope. The
L-shape's second wing is produced, verified and then **ignored**, because nothing can author a
two-wing fixture.

Concretely, in priority order:

1. **A concept generator that consumes a candidate set** — sizes the slicing tree to the given
   rectangle instead of hard-coded forced cuts, and emits `seam_leaf_sides` for multi-wing
   candidates. Without this the adapter's best output cannot be used.
2. **Diagonal/rotated sites lose ~20%** to axis-aligned fitting. The fix is not a better
   rectangularizer; it is allowing a rotated solver frame (solve in the site's own axis and
   rotate the result), which the domain's transform layer already supports.
3. **Residual classification** — the geometric facts are all present and unused.
4. **The renderer cannot draw general geometry**, so visual review of buildable boundaries,
   obstacles and residuals is currently impossible.

---

## Verdict

```
SAFE_GEOMETRY_ADAPTER = READY
NEXT_STEP             = INTEGRATE_GENERAL_GEOMETRY_WITH_VERTICAL_SLICE
```

The conservative-transformation question is settled: arbitrary authoritative geometry — arcs,
holes, disconnected components, obstacles — converts into solver-safe rectangles with the subset
invariant verified against exact geometry, zero loss on orthogonal shapes, and the existing
engine untouched. What now blocks progress is not geometry but the concept layer's inability to
consume more than one hard-coded footprint.

Stopping here for review.
