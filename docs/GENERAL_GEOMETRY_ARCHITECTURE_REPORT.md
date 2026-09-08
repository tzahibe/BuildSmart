# General Geometry & Site Constraints — Architecture Report

**Status:** research only. No code was written or modified for this report.
**Reviewed against:** `backend/app/vertical_slice/` (the passing First Vertical Slice) and
`backend/app/vertical_slice/geometry_core/` (the frozen engine).

---

## 0. Verdict up front

| | |
|---|---|
| **GENERAL_GEOMETRY_DIRECTION** | **VALIDATED_WITH_CHANGES** |
| **CURRENT_VERTICAL_SLICE_REUSE** | **HIGH** |
| **NEXT_STEP** | **IMPLEMENT_GENERAL_GEOMETRY_DOMAIN** |

The proposed direction is sound. Three changes are required before it is safe:

1. **The arc representation must be bulge, not three-point and not center+radius+angles** (§2).
   The endpoints must be the single source of truth for boundary continuity; curvature must be
   one transformation-invariant scalar that cannot desynchronize from them.
2. **The boundary primitive must be a region (rings with holes), not a ring** (§1). Setbacks and
   exclusions routinely produce holes and disconnected components; a single ordered vertex loop
   cannot express either, and that is not an edge case.
3. **Chord substitution is unsafe for concave arcs — always, not sometimes** (§3). The safe
   construction for a concave arc is a *circumscribing tangent chain*, not a finer chord chain.
   Adding more chords to a concave arc makes the error smaller but keeps it on the wrong side.

The reason reuse is HIGH and not MEDIUM is specific and checkable: the geometry-dependent
surface of the vertical slice is **seven identifiable functions and one DTO field** (§13).
Everything else is topology, program, rules, or reporting, none of which knows what a rectangle
is.

---

## 1. Is vertex+edge the right long-term abstraction? (Q1)

**Yes as the edge model, no as the region model.** "Ordered vertices and edges" describes one
closed ring. Real sites need two things a ring cannot express:

- **Holes.** A protected tree with a clearance radius, a shaft, an easement crossing the middle
  of a parcel — these punch a hole in the buildable region. A hole is a second ring with
  opposite winding, not a feature of the outer ring.
- **Disconnected components.** A 3 m setback applied to an hourglass-shaped parcel *splits it in
  two*. An exclusion strip across a plot does the same. This is not exotic; it is the normal
  behaviour of inward offsetting on any pinched shape.

Recommended model, three levels:

```
Vertex      : (x, y) in a declared coordinate frame
Edge        : references two vertex INDICES + curvature (see §2)
Ring        : ordered edges, closed, oriented (CCW = material, CW = hole)
Region      : one outer ring + zero or more hole rings
MultiRegion : one or more disjoint Regions
```

Two properties matter more than the schema:

- **Edges reference vertex indices, they do not store their own endpoints.** If an edge stores
  its own start/end, every vertex edit must update two edges, and the first time one path
  forgets, the ring develops a sub-millimetre gap. A gap is not a cosmetic problem: it silently
  breaks point-in-region, area, and every boolean operation, and it will not reproduce
  deterministically. Shared indices make the gap unrepresentable.
- **Every boolean output is a MultiRegion.** Not "usually a Region, sometimes a list". If the
  return type of "apply setback" is `Region`, the disconnection case has nowhere to go and will
  be handled by whichever caller notices first. Make it `MultiRegion` everywhere and force
  callers to decide.

---

## 2. How exactly should arcs be represented? (Q2)

**Recommendation: `bulge` (the DXF convention). Store `Edge{v_start, v_end, bulge: float}`.**
`bulge = tan(θ/4)`, where θ is the signed included angle of the arc.

The premise in the task is correct — two endpoints do not determine how strongly an arc bends.
The useful sharpening is: **you need exactly one more number, not one more point.**

### Why bulge beats the two proposed alternatives

| Property | center+radius+angles | three-point (start/mid/end) | **bulge** |
|---|---|---|---|
| Endpoint continuity | **Broken by design** — endpoints are *derived*, so they compete with the stored ring vertices | Preserved | **Preserved** |
| Degenerate straight edge | Radius → ∞, must special-case | Collinear mid, must special-case | **bulge = 0, no special case at all** |
| Shallow-arc conditioning | Center flies to infinity; ill-conditioned | Center ill-conditioned if computed | **Perfectly conditioned; bulge → 0 smoothly** |
| Transform (translate/rotate/uniform scale) | Must recompute center | Must transform the mid point too | **Invariant — transform vertices only** |
| Mirror | Recompute | Transform mid point | **Negate bulge** |
| Storage | 4 floats, redundant | 2 floats + shared endpoints | **1 float** |
| DXF interop | Conversion | Conversion | **Native (LWPOLYLINE)** |
| SVG interop | Conversion | Conversion | Conversion (mechanical) |

The transformation row is the decisive one. With center+radius+angles or three-point, curvature
data lives in a *second place* that every transform must remember to update. With bulge, there is
nothing to forget: translating, rotating or uniformly scaling a shape touches only the vertex
list, and every arc stays exactly consistent with its endpoints. That eliminates an entire class
of silent corruption rather than requiring discipline to avoid it.

The degenerate-case row is the second. `bulge = 0` *is* a straight line — LINE and ARC are not two
primitives with a branch between them, they are one primitive with a parameter. Code that
iterates edges does not need `if edge.kind == ARC`. Every simplification, offset and clipping
routine gets shorter and has fewer untested branches.

### The properties that make bulge operationally excellent

For chord length `d` and bulge `b`, without ever computing the centre:

- **Sagitta** (maximum deviation of the arc from its chord): `s = |b| · d / 2`
- **Radius**: `R = d(1 + b²) / (4|b|)`
- **Segment area** (shallow-arc approximation): `A ≈ (2/3) · s · d`
- **Major arc**: `|b| > 1` ⟺ `θ > 180°`

The first and third are exactly the two numbers the conservative-simplification decision in §3
needs — *how deep* and *how much area* a chord substitution loses. Both are available in one
multiply, with no trigonometry and no ill-conditioned centre computation. This is not a
coincidence; it is why the format survives in CAD.

### Accepted limitations, stated explicitly

- **Circular only.** Elliptical façades and splines are not representable. Recommendation:
  do not add them as primitives. Require ingest to approximate them as circular-arc chains
  (biarc fitting) or polylines, and record the approximation tolerance in provenance. Exact
  offsetting of splines is a substantially harder problem and would infect every downstream
  algorithm; the ability to represent a spline is not worth that cost at this stage.
- **Non-uniform scaling breaks arcs** (a circle becomes an ellipse). This is true of every
  circular-arc representation, not a bulge weakness. Forbid non-uniform scaling on authoritative
  geometry.
- **Three-point remains the right *input* form.** Surveyors and CAD exports frequently give three
  points. Accept it at the boundary and convert to bulge immediately on ingest — never store it.

### One mandatory splitting rule

**Split every arc at `|bulge| = 1` (θ = 180°) before any simplification or offsetting.** For a
major arc the chord no longer separates interior from exterior in a locally meaningful way, and
the convexity test in §3 becomes ambiguous. Splitting is exact (each half gets a computable
bulge) and removes the pathology at the source rather than guarding against it in five places.

---

## 3. Can curves safely be hidden from the solver? When is a chord unsafe? (Q3, Q4, Q5)

**Yes, hiding curves works — but the rule is asymmetric, and the asymmetry is the whole answer.**

Define the buildable region **R**. For a boundary arc, the only question that matters is which
side of the chord the region's interior lies on.

### Case A — arc bulges *outward*, away from R's interior (locally convex)

The arc encloses more area than its chord. The chord therefore lies **inside** R. Substituting
the chord yields `R' ⊂ R`.

**Safe. A single chord is sufficient**, regardless of how strong the curvature is. The lost area
is the circular segment (`≈ (2/3)·s·d`), which becomes a `ResidualRegion` along the façade — often
the most architecturally valuable residual in the whole plan, since it is exterior-exposed by
definition (§10).

### Case B — arc bulges *inward*, into R's interior (locally concave)

The arc takes a bite out of R. R is locally the region *outside* the circle. The chord spans
across the bite, so the chord lies **outside** R. Substituting it hands the solver area that does
not exist.

**Unsafe. Always. And — this is the important part — refining does not fix it.** Sampling more
points *on the arc* and connecting them with chords produces a finer inscribed polyline, but
every one of those chords still cuts through the excluded disc. The error shrinks; it never
changes sign. A tolerance-based chord chain on a concave arc is a bug that gets quieter as you
tighten the tolerance, which is the worst possible failure mode.

**The correct construction for a concave arc is a circumscribing tangent chain:** a chain of
segments each *tangent* to the circle, joined at their intersection points. Every tangent line
lies outside the disc, hence inside R. This over-removes rather than under-removes — conservative
in the right direction.

Segment count for a tolerance `tol` over angular span θ:

```
extra depth removed per segment ≈ R · θ² / (8n²)   ⟹   n ≈ θ · √( R / (8·tol) )
```

So a 90° concave arc of R = 6 m at 5 cm tolerance needs `n ≈ 1.57 · √(6/0.4) ≈ 6` segments. Cheap.

### Summary table

| Boundary feature | Safe simplification | Single chord? |
|---|---|---|
| Convex arc (bulges away from interior) | chord | **Yes** |
| Concave arc (bulges into interior) | tangent chain, n from tolerance | **Never** |
| Convex polygon corner | keep | n/a |
| Reflex (concave) polygon corner | keep — cutting it adds nonexistent area | **Never** |
| Hole boundary (exclusion disc) | **convexity flips** — see below | — |

### The trap: convexity is relative to the region, not to the arc

An exclusion disc's boundary is convex as a circle but, viewed from R (which is *outside* the
disc), it is concave. If the simplifier tests "is this arc convex" using the arc's own bulge sign
without reference to ring orientation, it will chord-substitute every exclusion zone and design
buildings into protected clearance areas. **The test must be `bulge sign × ring orientation`**,
evaluated against the material side, and it must be one function used everywhere — never
re-derived locally.

### The other five unsafe conditions

1. **Concave arcs** (above).
2. **Reflex vertices** — the polygonal analogue; a chord across a reflex corner adds area.
3. **Hole/exclusion boundaries** — orientation flip (above).
4. **Major arcs** (`|b| > 1`) before splitting — chord does not separate sides meaningfully.
5. **Grid rounding.** `m_to_u()` in `geometry_core/model.py` is
   `int(round(metres / UNIT_M))` — **round-to-nearest**. Conservative approximation must round
   *inward* (toward the interior) at every boundary, or each edge can gain up to 2.5 cm of
   nonexistent space, and a footprint can gain ~10 cm of perimeter it does not own. `m_to_u` is
   correct for its current use (dimensioning) and must not change; the adapter needs a separate
   direction-aware quantizer. This is a small, concrete, easily-missed requirement.
6. **Offsetting a concave arc by more than its radius** — the arc inverts and the offset
   self-intersects. Naive per-edge offsetting produces a garbage ring here. Setbacks must go
   through a real polygon-offset routine with self-intersection cleanup, not per-edge
   displacement.

### The part the "hide the curve" framing understates

The solver is not a general polygon solver — it is a **rectangular slicing engine**. So
simplification is two conservative steps, not one:

```
curved region ──(§3 rules)──▶ conservative polygon ──(harder)──▶ conservative ORTHOGONAL cover
```

Step 2 is where the real area loss lives. A 45° angled façade loses roughly half its triangle to
an inscribed axis-aligned rectangle; a curve loses its segment *plus* whatever the orthogonal
inscription loses. **Curve-hiding is necessary but is not the expensive part.** Any estimate of
"how much buildable area we forfeit by keeping the rectangular core" must be measured after step
2, not step 1.

---

## 4. Obstacles, exclusions, setbacks — the domain model (Q6, Q7)

### Do not create six sibling classes

`BUILDABLE_REGION / EXCLUSION_REGION / OBSTACLE / SETBACK_REGION / ACCESS_REQUIRED_REGION /
NO_BUILD_REGION` all participate in the same boolean algebra over the same `Region` type. Six
classes means six copies of that algebra and six chances for them to diverge.

**Recommended: one constraint type with a role, plus one computed output.**

```
GeometricConstraint
  role       : NO_BUILD | OBSTACLE | ACCESS_REQUIRED | CLEARANCE | BUILDABLE_HINT
  shape      : Region | ParametricRule      (a setback is a rule, not a stored region)
  provenance : Provenance                    (§6)

BuildableRegion        ← computed, not authored
  regions      : MultiRegion
  derived_from : [constraint ids]            (so "why is this line here?" is answerable)
  status       : COMPUTED | UNKNOWN | EMPTY
```

Two distinctions inside that model genuinely matter and must not be flattened:

- **NO_BUILD vs OBSTACLE.** NO_BUILD *shrinks* the envelope (a setback strip at the edge).
  OBSTACLE *punches a hole inside* it (a column, a shaft). They are different because a hole is
  something the rectangular core **cannot represent at all** — see §7, failure case 3. Collapsing
  them hides the hardest case behind the easiest one.
- **Domain constraints vs solution constraints.** A setback shrinks the region (domain). A
  maximum coverage ratio of 40% does *not* shrink any region — it limits what may be placed in
  it (solution). Coverage, FAR, height and unit-count rules are **not geometry** and must never
  be converted into geometry. They belong in validation, checked against the produced design.
  Modelling coverage as a shrunken region would be wrong in a way that produces plausible,
  quietly incorrect plans.

Circles need no special case: a clearance disc is a Region whose ring is two arcs of `bulge = 1`.
"Protected tree with 5 m clearance" is `buffer(point, 5.0)` → Region → constraint with role
CLEARANCE. This is a direct payoff of putting arcs in the primitive set.

### The legal/geometry separation (Q7) — endorsed, with one testable invariant

The proposed layering is correct:

```
parcel / survey / user input
    ↓
regulation + authoritative data layer     ← knows Israeli planning law
    ↓
ConstraintSet (with provenance)           ← the interface
    ↓
buildable-region computation              ← pure geometry, knows no law
    ↓
architectural planning → Geometry Core
```

Make it enforceable rather than aspirational:

> **Invariant:** the geometry layer's public functions take no `municipality`, `zone_code`,
> `plan_id` or similar parameter. If one is ever needed, the separation has leaked.

That is a lint rule, not a principle, and it is the difference between a separation that holds
and one that erodes. The current `PlotSpec` already violates the spirit — it carries
`front_setback_m / side_setback_m / rear_setback_m` as scalar fields on the *plot*, mixing a
regulatory output into the site input. That is fine for one hard-coded slice and must be moved
into `ConstraintSet` during migration.

Regulations are also not always offsets. At least three shapes exist: **offset setbacks**
(derivable), **absolute building lines** (given by a plan; must be ingested as geometry, not
derived), and **non-geometric ratios** (validation). A `ConstraintSet` that can only express
offsets will force the other two to be faked.

---

## 5. Parcel vs buildable geometry, and provenance (Q8, Q9)

### They must be different types, not one type with a flag (Q8)

```
Parcel          : legal identity (גוש/חלקה), survey geometry, authoritative, stable
BuildableRegion : derived, may be multi-component, may be EMPTY, may be UNKNOWN
```

The single most important property: **`BuildableRegion` must be able to say UNKNOWN**, and the
pipeline must refuse to plan on an UNKNOWN region. The failure mode to design against is a
system that, lacking setback data, quietly falls back to the parcel boundary — which produces a
confident, renderable, legally impossible building. A missing-data path that defaults to
"buildable = parcel" is worse than a crash.

### Provenance (Q9)

The proposed source list is right but is one axis short. Source and *authority* are independent:
publicly available GIS parcel geometry has source `GIS` and is explicitly **not** legally
authoritative. Keep them separate:

```
Provenance
  source    : USER | SURVEY | CAD | GIS | REGULATION | INFERRED | MANUAL_OVERRIDE
  authority : AUTHORITATIVE | INDICATIVE | ASSUMED
  as_of     : date            (cadastral and planning data change)
  ref       : free text / document id / plan number
```

Two rules give this teeth:

- **Provenance attaches per geometric element, not per object.** A boundary can have three
  surveyed edges and one edge the user dragged. Per-object provenance would report the whole
  parcel as SURVEY.
- **Authority propagates pessimistically and gates the output.** Any region derived from an
  ASSUMED input is ASSUMED. A design whose buildable region is not AUTHORITATIVE may be produced
  and rendered, but must be labelled a **study**, never a submission-grade output. This is where
  the product consequence of provenance actually lands; without it provenance is decoration.

---

## 6. Israeli data flow — what can and cannot be automated (Q7 research)

Research-level only; no integration is proposed.

| Step | Realistic automation | Notes |
|---|---|---|
| גוש + חלקה → parcel geometry | **Mostly automatable** | Cadastral/GIS sources can yield a polygon. Treat as `GIS / INDICATIVE` — useful for massing studies, not for submission. |
| Parcel → applicable plans | **Partially automatable** | Which plans apply is often discoverable; *what they say* usually is not machine-readable. |
| Plans → setbacks / building lines | **Largely not automatable** | Building lines frequently live in plan drawings and text. This is document interpretation, not data retrieval. Highest-risk step to over-promise. |
| Infrastructure clearances | **Not automatable initially** | Requires utility data plus interpretation; must be manually marked. |
| Authoritative boundary | **Requires a licensed surveyor (מדידה)** | No public dataset substitutes for it. |
| Candidate buildable region | **Automatable *given* the above** | Pure geometry once constraints exist. |

**Architectural consequence:** the system must be fully usable with **zero** external data — every
constraint enterable manually with `source = USER/MANUAL_OVERRIDE`. Automation then fills the
same slots with better provenance. If instead the pipeline is designed around GIS ingestion and
manual entry is bolted on, the product cannot function for the majority of real cases where the
authoritative input is a surveyor's PDF. **Manual is the primary path; automation is an
accelerator.**

---

## 7. Critical failure cases and where each is caught (Q15)

| # | Case | Rejecting / repairing layer | Notes |
|---|---|---|---|
| 1 | Very deep concave façade | Buildable-region validation | Tangent chain (§3); if MIR then falls below program minimum, reject **before** the solver. |
| 2 | Thin crescent region | Region analysis | MIR tiny ⟹ whole region classified residual/unusable. Reject with the measurement, not "infeasible". |
| 3 | **Interior exclusion (hole) inside the envelope** | **Decomposition layer — hardest case** | The rectangular core cannot represent a hole. Decomposition must cut the region into wings *around* the hole. This is the primary structural limitation of keeping the rectangular core. |
| 4 | L-shaped buildable region | Already solved | Multi-wing + `seam_leaf_sides`; known caveat L2 (seam must align to a leaf boundary via forced cuts). |
| 5 | Narrow connecting neck | Buildable-region computation | Inward offset can *disconnect* the region. Requires a post-offset connectivity check and an explicit multi-component decision — never silently pick the biggest piece. |
| 6 | Curved façade + setback | Offsetting engine | Concave arc with R < setback self-intersects; needs real offset + cleanup, not per-edge displacement. |
| 7 | Obstacle splits region in two | Buildable-region computation | Same machinery as 5. Product decision must be surfaced, not defaulted. |
| 8 | Area large enough, geometry unusable | Pre-solve feasibility screen | Area is necessary, never sufficient. Gate on MIR + per-room fit before solving. |
| 9 | Room area fits numerically, furniture does not | **Already handled** | Exactly the SAFE_ROOM 2.20 m defect the furniture-envelope check (patch 4) caught in the spike. |
| 10 | Safe room constrained by construction *and* exterior/opening rules | **Already hit** | The vertical slice's window bug (§8). Fixed by keeping the facts orthogonal. |

Cases 9 and 10 are worth noting as evidence rather than risk: both were *predicted* by this
architecture's reasoning and both were *actually caught* by the existing pipeline before this
report was written.

---

## 8. The wall model — keeping orthogonal facts orthogonal (Q12)

The vertical slice produced a concrete, non-hypothetical failure: `SAFE_ROOM`'s envelope wall was
simultaneously RC construction *and* on the building exterior, but `WallType`'s precedence chain
(`OPEN > RC_SAFE_ROOM > EXTERIOR > PARTITION`) stores only the winner. The exterior fact was
destroyed, so window placement — which looked for `WallType.EXTERIOR` — found no eligible side and
the safe room silently got no window. It was worked around in `windows.py` by recomputing
exposure geometrically; the underlying model is still lossy.

### Minimum clean separation

```
BoundarySegment
  geometry         : Edge            (LINE or ARC — bulge; §2)
  boundary_context : EXTERIOR | INTERIOR | PARTY        ← exposure, a geometric fact
  construction     : STANDARD_PARTITION | RC_SAFE_ROOM | STRUCTURAL | NONE(open)
  opening_policy   : derived — what may be cut into it, given construction + context
```

Three fields, not one enum. The rules that matter:

- `boundary_context` is a **geometric** fact (is this segment on the envelope?) and must be
  derived from geometry, never from construction type. It is already computed correctly in two
  places — `_mark_exposure()` in the engine and `_envelope_sides()` in `windows.py` — but the
  engine's copy is discarded before it reaches the returned `WallMap`. Surfacing it is a small
  change with a large payoff.
- `construction` is a **program/regulation** fact. RC because it is a ממ״ד, structural because it
  carries load. Independent of where the wall sits.
- `NONE` (open-plan) is a construction value, not a context value — and the existing hard
  invariant "a safe room may never be open" (rejected eagerly since patch 2) becomes a plain
  cross-field validation rather than a precedence accident.
- **`opening_policy` is derived, never stored.** A ממ״ד exterior wall may take a blast-rated
  window; a ממ״ד interior wall may not take an ordinary door. That is a function of (context,
  construction), and storing it would allow it to disagree with its own inputs.

Explicitly **not** now: thermal, acoustic, fire, U-value, finish. Leave the struct extensible and
add them when a consumer exists. Adding them speculatively creates fields nothing validates.

---

## 9. Residual space as a first-class concept (Q10, Q11)

### The discipline already exists — extend it, do not invent it

`OutdoorRegion` already carries an explicit `OutdoorClassification` with
`UNCLASSIFIED_REMAINDER`, and Correction 3 already forbids auto-promoting leftovers to "garden".
`ResidualRegion` is the same rule applied indoors: default `UNCLASSIFIED`, **never**
auto-promoted, classification is always a recorded decision.

### Every signal needed already exists in the vertical slice

This is the most reusable finding in this report. The classification inputs are:

| Signal | Where it already exists |
|---|---|
| net width / depth | `net_rect_m()` |
| area | `Rect.area_m2()` |
| exterior exposure | `_envelope_sides()` in `windows.py` |
| adjacency to rooms | `Rect.shared_edge_len_u()` |
| accessibility | the BFS reachability check (validation C5) |
| furniture fit | `furniture_envelope_fits()` |
| door capability | `doors.py` placeability (shared length ≥ width + 2×margin) |

**The residual classifier is mostly assembly of existing measurements, not new geometry work** —
with one genuine addition: **maximum inscribed rectangle (MIR)** of an arbitrary polygon, needed
because a non-rectangular residual has no "net rect".

### MIR is the highest-leverage primitive to build

One implementation, three consumers: furniture feasibility in non-rectangular rooms (§10),
residual classification (here), and conservative orthogonal simplification (§3 step 2). If only
one geometric algorithm gets built well, it should be this one.

### Classification (deterministic, thresholds are PRODUCT POLICY — tag them as such)

| Class | Rough signature |
|---|---|
| `SERVICE_SPACE` (storage, pantry, laundry) | MIR width ≥ 0.6 m, area ≥ ~0.9 m², door-capable adjacency |
| `CIRCULATION` | MIR width ≥ ~1.0 m and connects two nodes already in the access graph |
| `USEFUL_RESIDUAL` (nook, seating, built-in) | exterior exposure present and MIR depth ≥ ~1.5 m |
| `ARCHITECTURAL_BUFFER` | below usable width — absorbed into wall thickening or a deliberate void |
| `UNUSABLE_RESIDUAL` | fails all of the above — **recorded, not hidden** |

The thresholds above are placeholders in the same sense as `WALL_THICKNESS_M[RC_SAFE_ROOM]`: they
must be tagged PRODUCT POLICY and must not be presented as regulatory values.

### One pipeline-ordering consequence

Absorbing a residual into a room **changes that room's net area**, which is an input to area
validation. So residual analysis must run *before* final validation, or validation must run
twice. Getting this order wrong produces designs that validate on pre-absorption numbers.

### Curved façades, windows and doors (Q11)

Do **not** encode "curved wall ⟹ window". The correct chain is that a curved or angled façade
tends to produce a residual that is *exterior-exposed by construction* — and exterior exposure is
already an input to the existing window stage. So the connection to the working pipeline is:

```
Geometry Core → residual analysis → residual classified & (maybe) absorbed
             → Doors → Windows → Furniture feasibility → Validation
```

Residual analysis slots in as a new stage *between* the core and the existing opening stages,
and the opening stages need no rule change — they need a richer notion of "boundary segment"
(§8) instead of "one of four sides". The opening stage should weigh exterior exposure,
orientation, room type, daylight need, privacy, furniture clearance and construction restriction
— all of which are inputs it can be given without changing its logic.

### Furniture as a feasibility signal (Q12 of the brief)

Furniture must stay a **signal**, and it should gain one new job: **gating residual absorption**.
The question "can this curved sliver be absorbed into the bedroom?" is answerable only as "does
the bedroom still inscribe its furniture envelope afterwards?" — which is exactly the check that
already exists, applied to a new decision.

The one ordering change worth flagging (and deferring): today doors and windows are placed
*without* consulting furniture, so a door can legitimately land on the only wall a bed fits
against. Making furniture a *constraint provider* to the opening stage rather than a downstream
check is a real improvement and a real change; it should not be bundled into the geometry
migration.

---

## 10. Geometry Core strategy (Q14, Q15, Q16)

### Evaluation

| Option | Complexity | Robustness | Arch. quality | Reuse | Curves | Obstacles (holes) | Verdict |
|---|---|---|---|---|---|---|---|
| **A** rect core + pre/post layer | Low | High (core untouched) | Good, area loss on non-orthogonal sites | **Total** | via §3 | **Cannot do interior holes** | Right first increment |
| **B** orthogonal polygons / rect decomposition | Medium–High | Medium (touches shape curves) | Better | High | via §3 | Yes | Right medium-term |
| **C** general polygon solver | **Very high** | Unproven | Potentially best | Low | Native | Yes | Research project, not a plan |
| **D** hybrid behind one contract | Medium | High | Best available per case | **Total** | via §3 or native | Yes | **Recommended target** |

Option C deserves an explicit rejection rather than a shrug: partitioning an arbitrary polygon
into rooms with area, aspect and adjacency targets is not a solved problem, and the shape-curve
machinery that makes the current core *exact and fast* is fundamentally rectangular. Replacing a
validated engine with an unproven one to gain generality that preprocessing can supply is the
wrong trade at this stage.

### Recommendation: **D — hybrid, first increment A**

This is not a hedge. D's defining property is not "two engines"; it is **one stable contract**
(`ArchitecturalSpec` / `DesiredAccessTopology` / `GeometricDesign`) with the engine behind it
swappable. That contract must be established **now, while there is exactly one engine**, because
it is the only thing that prevents a future rewrite. Establishing it later means retrofitting it
against two engines at once.

Note also that **option B is already partially built**: the core supports *multiple wings* joined
by declared seams (`seam_leaf_sides`, used by the L-house fixture). An L-shaped buildable region
is coverable today by two wings. Multi-wing decomposition is orthogonal-polygon support in
disguise, and it is the natural growth path from A into B without touching the shape curves.

### Falsifiable trigger for building the richer engine

Do not decide by taste. Instrument the adapter and build the richer solver when, over a real plot
corpus, **either**:

- \> 20% of plots fail conservative orthogonal decomposition outright (holes, disconnection), **or**
- median buildable-area loss from step-2 orthogonal inscription exceeds ~10%.

Until one of those fires, preprocessing is the better investment.

---

## 11. The future GeometricDesign contract (Q16)

The proposed schema is close. Recommended trims and additions:

**Keep:** `site_geometry`, `buildable_regions`, `building_envelope`, `spaces`, `walls`,
`openings`, `access_topology`, `residual_regions`, `provenance`.

**Drop as separate fields:**

- `circulation` — circulation is a *space with a role* (already true today via
  `ProgramRole.CIRCULATION`). A parallel list can disagree with `spaces`, and eventually will.
- `obstacles` — obstacles are constraints in `site_geometry` and are already subtracted from
  `buildable_regions`. A third copy is a third thing to keep in sync.
- `dimensions` — an annotation/rendering concern, derivable from geometry. Storing it invites
  stale dimensions.

**Add:**

- `frame` — explicit coordinate frame + units. Cheap, and it prevents an entire class of bug
  the moment a second engine or a CAD import feeds this structure.
- `engine_provenance` — which engine produced this, for debugging. Explicitly **not** readable by
  the renderer.

**The renderer-independence invariant, made testable:**

> The renderer imports nothing from any engine module.

This is currently violated in a small, easily fixed way: `renderer.py` imports `u_to_m` from
`geometry_core.model` in three places (lines 46, 60, 77). Unit conversion belongs in the contract
(emit metres) or in a shared units module — not in the engine the renderer is supposed to be
ignorant of. Worth fixing early precisely because it is trivial now and load-bearing later.

---

## 12. Component audit — what survives, concretely (Q13)

Not "most of it". Here is every component with its boundary.

| Component | Verdict | Precise boundary |
|---|---|---|
| `ArchitecturalSpec` (`spec.py`) | **EXTEND** | `ProgramSpec` survives untouched. `PlotSpec(width_m, depth_m, *_setback_m)` is replaced by `Parcel(Region)` + `ConstraintSet` — setbacks leave the plot object entirely (§4). |
| `Concept` (`concept.py`) | **REPLACE EVENTUALLY** | The `Concept` *dataclass shape* (fixture + entrance zone + street side + footprint size) survives. Its *contents* — a hand-authored tree that raises `NotImplementedError` for any other program — are a demo scaffold, not an asset. |
| `DesiredAccessTopology` | **KEEP AS-IS** | Pure topology; contains zero geometry. The strongest survivor in the codebase. Unchanged by everything in this report. |
| `site.py` | **EXTEND / partly REPLACE** | `translate_rects` survives as a transform. `place_footprint` (centred rect in rect) → region-based placement. `classify_garden`'s hand-rolled rectangle decomposition → proper region boolean; but its *discipline* (explicit classification, never implicit remainder) survives intact. |
| **Geometry Core** — `model.py` (`Rect`, integer 5 cm grid, exact tiling) | **KEEP AS-IS** | Correct and valuable *as solver geometry*. Its only required change of status: it stops being the **authoritative** geometry. |
| **Geometry Core** — `engine.py` | **KEEP, one surgical extension** | `_mark_exposure()` infers EXTERIOR from tree position — valid only when the wing rectangle's boundary *is* the true envelope. Under general geometry, exposure must be **injected**, not derived. The hook already exists: `derive_wall_types()` already accepts injected `safe_room_neighbours`, and `seam_leaf_sides` already overrides exposure for the L-house (engine.py:127). Generalising that to an `exposure_override` map is roughly ten lines, in a function that already does exactly this for two other cases. **No change to shape curves, assignment, or the bounded re-solve loop.** |
| `doors.py` | **EXTEND** | The *rule* (openings only from `DesiredAccessTopology`; OPEN_CONNECTION never yields a door) is geometry-independent — keep. `_side_between()` assumes axis-aligned rect adjacency — replace with shared-boundary-segment computation. |
| `windows.py` | **KEEP pattern, EXTEND geometry** | `_envelope_sides()` already does the conceptually right thing (geometric exposure, independent of `WallType`) and generalises directly to "which boundary segments lie on the envelope". The daylight-role rule is unchanged. |
| `furniture.py` | **EXTEND** | Rect inscribe → MIR inscribe (§9). Envelope table and per-role semantics unchanged. |
| `validation.py` | **KEEP AS-IS (mostly)** | C5 (BFS reachability) is pure graph — untouched. C6 (open-plan doors) untouched. C1/C2 become region-based but ask the identical questions. C10/C11 become region-based. Second-strongest survivor. |
| `design_output.py` | **EXTEND** | Exactly **one** field is geometry-bound: `RoomOut.rect_m: (x,y,w,h)` → boundary. `roles`, `net_*`, `walls`, doors, windows, parking, garden, areas all survive as-is. |
| `renderer.py` | **EXTEND (cheap)** | Already draws *per-side* segments with *per-side* types; generalising to per-*edge* is the same loop over a different container. Rect patches → paths. Plus the `u_to_m` decoupling (§11). |

**The concrete boundary:** the geometry-dependent surface is
`Rect` (as an authoritative type), `RoomOut.rect_m`, `_side_between`, `_envelope_sides`,
`_mark_exposure`, `place_footprint`, `classify_garden`, and `net_rect_m`. That is **seven
functions and one DTO field** — a small fraction of the code and essentially all of the risk.
Everything else is topology, program rules, validation logic, or reporting.

---

## 13. Migration plan (Q17)

The proposed sequence is broadly right; two changes improve it materially.

**Stage 0 — Freeze the slice as a *numeric* regression baseline.**
Not just "keep the test". Pin the exact outputs: gross **170.4 m²**, net **153.83 m²**, wall
re-solve **2 iterations**, 11 rooms, 8 interior doors + 1 entrance, 7 windows, all 12 checks
green. Any refactor that changes a number must do so deliberately. This makes the whole migration
provably behaviour-preserving rather than hopefully so.

**Stage 1 — Geometry domain model + provenance, together.**
`Vertex/Edge(bulge)/Ring/Region/MultiRegion` + `Provenance` + `GeometricConstraint`. Provenance
must land *with* the model, not after it — retrofitting per-element provenance later means
touching every construction site of every geometry object.

**Stage 2 — The contract (`GeometricDesign` v2) and renderer decoupling.**
Moved earlier than proposed, deliberately. Establish the solver-independent contract while there
is still exactly one engine; that is what prevents the future rewrite. Cheap now, expensive later.

**Stage 3 — Buildable-region computation:** offsets with self-intersection cleanup, boolean
subtraction of exclusions, connectivity/multi-component detection, UNKNOWN handling.

**Stage 4 — The safe adapter:** conservative simplification (§3) + direction-aware inward
quantiser + MIR + orthogonal decomposition into wings, feeding the *unchanged* Geometry Core.
Ships with an area-loss metric, which is also the instrumentation for the §10 trigger.

**Stage 5 — Residual regions:** analysis, classification, absorption; validation re-ordered to
run after absorption.

**Stage 6 — Wall/opening model orthogonality (§8)** and openings adapted to boundary segments.

**Stage 7 — Complex-shape validation:** the §7 failure corpus as tests.

**Stage 8 — (Conditional) richer solver**, only if the Stage-4 metric fires.

Throughout: the 3BR + safe-room slice runs green at every stage, with its numbers pinned.

---

## 14. Explicit answers (Q1–Q19)

1. **Is vertex+edge the right long-term abstraction?** Yes for edges; insufficient for regions —
   you need rings with holes and multi-component regions (§1).
2. **How should arcs be represented?** **Bulge** (`tan(θ/4)`), one scalar per edge, endpoints
   authoritative, transformation-invariant, `bulge=0` *is* a line, native DXF (§2).
3. **Can curves be hidden from the solver?** Yes — with an asymmetric rule, and remembering that
   the orthogonal step, not the curve step, is where area is actually lost (§3).
4. **When is chord simplification unsafe?** Concave arcs (always), reflex corners, hole
   boundaries (orientation flips), major arcs before splitting, and round-to-nearest grid
   quantisation (§3).
5. **How should concave curves be handled?** Circumscribing **tangent chain**, `n ≈ θ√(R/8·tol)`.
   Never a chord chain — refinement shrinks that error without ever correcting its sign (§3).
6. **Obstacles / exclusion zones?** One `GeometricConstraint` with a role over a shared `Region`
   algebra; keep NO_BUILD (shrinks) distinct from OBSTACLE (holes) (§4).
7. **Can setbacks/regulations become geometric constraints cleanly?** Yes for offsets and
   building lines; **no** for ratios (coverage/FAR/height) — those are solution constraints and
   belong in validation, never in geometry (§4).
8. **Parcel vs buildable geometry?** Different types. `BuildableRegion` must support UNKNOWN and
   the pipeline must refuse to plan on it (§5).
9. **Provenance?** Per-element; `source` and `authority` as independent axes; pessimistic
   propagation; non-authoritative input ⟹ output labelled a study (§5).
10. **Residual spaces?** Same explicit-classification discipline as `OutdoorRegion`; every needed
    signal already exists except MIR; absorption must precede final validation (§9).
11. **Curved façades vs windows/doors/furniture?** No "curve ⟹ window" rule. Curves produce
    exterior-exposed residuals; exposure is already a window-stage input. Insert residual
    analysis between the core and the existing opening stages (§9).
12. **What changes in the Wall model?** Split `WallType` into `boundary_context` (geometric) ×
    `construction` (program) with derived `opening_policy`. Three fields, not one enum (§8).
13. **Which slice components survive unchanged?** `DesiredAccessTopology`, validation C5/C6, the
    grid/`Rect` solver geometry, furniture envelope semantics, the opening-generation *rules*,
    `ProgramSpec`, and the whole shape-curve/assignment/re-solve engine (§12).
14. **Which need replacement?** `PlotSpec`'s scalar setbacks, `concept.py`'s hand-authored tree,
    `place_footprint`, `classify_garden`, `_side_between`, and `RoomOut.rect_m` (§12).
15. **Can the rectangular Geometry Core remain useful long-term?** **Yes** — as one realization
    engine behind a stable contract. Its exact integer tiling is an asset, not a liability. Its
    hard limit is interior holes (§10, §7 case 3).
16. **Preprocessing, polygon solving, or hybrid?** **Hybrid (D)**, first increment = preprocessing
    (A), with multi-wing decomposition as the built-in path toward (B) (§10).
17. **Does this avoid a future rewrite?** Yes — *if* the contract lands early (Stage 2) and the
    engine stays behind it. If the contract slips until a second engine exists, it does not.
18. **Top 5 risks.**
    1. **Silent non-conservative simplification** — concave chords and round-to-nearest
       quantisation both hand the solver space that does not exist, and both produce plausible
       output. Mitigate with a machine-checked "solver region ⊆ authoritative region" assertion
       on every adapter run.
    2. **Interior holes** (columns/shafts) — the one case option A structurally cannot express.
    3. **Offsetting robustness** — self-intersection, disconnection and vanishing arcs are normal,
       not exceptional; naive per-edge offsetting will produce garbage rings.
    4. **Legal/authority leakage** — non-authoritative GIS geometry being treated as buildable
       truth. Guarded by provenance + the study/submission distinction, not by good intentions.
    5. **Contract slippage** — postponing `GeometricDesign` v2 until a second engine exists,
       which is exactly the scenario that forces the rewrite this architecture exists to avoid.
19. **What to implement first?** **The general geometry domain model + provenance** (Stage 1),
    immediately after pinning the slice's numbers as a regression baseline (Stage 0). Everything
    else in this report depends on that type layer existing; nothing else can be built cleanly
    before it.

---

## 15. Final verdict

```
GENERAL_GEOMETRY_DIRECTION   = VALIDATED_WITH_CHANGES
CURRENT_VERTICAL_SLICE_REUSE = HIGH
NEXT_STEP                    = IMPLEMENT_GENERAL_GEOMETRY_DOMAIN
```

Required changes to the proposal, restated compactly:

1. Arcs as **bulge**, not three-point and not center+radius+angles.
2. Regions with **holes and multiple components**, not a single vertex ring.
3. **Concave arcs get tangent chains, never chords** — and the convexity test must be relative to
   the region's material side, not the arc's own bulge sign.
4. **Coverage/FAR/height are not geometry.** They are solution constraints; converting them into
   regions would produce plausible, quietly wrong plans.
5. **`BuildableRegion` must support UNKNOWN**, and planning on UNKNOWN must be refused rather
   than defaulted to the parcel boundary.

Stopping here for review. No implementation performed.
