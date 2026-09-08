# General Geometry Domain V1 — Implementation Report

**Scope executed:** the authoritative geometry domain foundation only. Geometry Core was not
replaced, the solver was not generalized, topology generation was not touched, no GIS /
gush-helka / regulation retrieval was implemented, and no curve simplification was built.

```
GENERAL_GEOMETRY_DOMAIN = READY
NEXT_STEP               = IMPLEMENT_SAFE_GEOMETRY_ADAPTER
```

---

## 1. Domain types introduced

New package `backend/app/geometry_domain/` — **imports nothing from any solver**, enforced by a
test (§9).

| Module | Types |
|---|---|
| `primitives.py` | `Vertex`, `BoundaryEdge`, `Ring`, `Region`, `MultiRegion`, `GeometryValidationError`, plus arc functions (`included_angle`, `arc_radius`, `arc_sagitta`, `arc_apex`, `arc_center`, `arc_segment_area`, `arc_bounds`, `bulge_from_three_points`) |
| `provenance.py` | `Source`, `Authority`, `Provenance`, `weakest_of` |
| `constraints.py` | `ConstraintRole`, `GeometricConstraint`, `Parcel`, `Knowledge`, `BuildableRegion`, `UnknownBuildableRegionError`, `SiteConstraints` |
| `walls.py` | `BoundaryContext`, `Construction`, `OpeningPolicy`, `WallFacts` |
| `transforms.py` | `translate`, `rotate`, `scale_uniform`, `mirror_x`, `mirror_y` |
| `units.py` | `Rounding`, `quantize_m`, `lower_bound_units`, `upper_bound_units`, `length_units_no_overstate`, `clearance_units_no_understate` |

One adapter module: `backend/app/vertical_slice/geometry_adapter.py`.

---

## 2. How LINE and ARC are represented

`BoundaryEdge{start: vertex_id, end: vertex_id, bulge: float, provenance}` — **bulge only**, per
the architecture report's recommendation. `bulge = tan(theta/4)`.

- `bulge == 0` **is** a straight line. LINE and ARC are one primitive with a parameter, not two
  cases; no algorithm in the package branches on edge kind.
- **Endpoints are authoritative.** Edges reference vertex *ids*, never their own coordinates, so
  a gap between adjacent edges is unrepresentable rather than merely discouraged. No
  center/radius/angle form is stored anywhere — `arc_center()` derives it on demand and is
  documented as ill-conditioned for shallow arcs, which is precisely why nothing routes a
  shallow-arc computation through it.
- **Sagitta and segment area are computed without the centre** (`s = |b|·d/2`), so the two
  quantities the future adapter needs in order to price a chord substitution are always
  well-conditioned.
- `is_major_arc` flags `|bulge| > 1`, so the adapter can find the arcs that must be split at
  180° before any simplification.
- `bulge_from_three_points()` exists as an **ingest-only** convenience (surveyor/CAD input) and
  converts immediately; three-point is never a storage form.

Supported and tested: straight, diagonal, convex arc, concave arc, mixed line+arc boundaries.

---

## 3. Region: holes and disconnected components

Three levels, as recommended: `Ring` (closed, oriented — CCW material / CW hole) →
`Region` (one outer ring + N holes) → `MultiRegion` (N disjoint regions).

- **Holes are first-class.** `Region(outer, holes)`; area subtracts them; `contains_point`
  excludes them; `validate()` rejects a hole whose vertices fall outside the outer boundary.
- **Disconnection is representable.** `MultiRegion` exposes `component_count`, `is_connected`,
  `is_empty`. This is the type an inward setback offset must return, because offsetting a
  pinched parcel genuinely splits it.
- A **circle needs no new primitive** — `Ring.circle()` is two `bulge=1` edges — so a protected
  tree or column with a clearance radius is an ordinary region.
- `Ring.rectangle()` makes a rectangle one representable special case of the general model,
  which is the concrete form of "Rect is not the authoritative language".
- `bounds()` includes arc extremes, not just vertices (a vertex-only box would report a circle
  as a degenerate line).

---

## 4. Provenance

`Provenance{source, authority, as_of, ref}` attached **per `BoundaryEdge`** (element level, not
object level) and on every constraint, parcel and buildable region.

`source` and `authority` are independent axes: public GIS geometry is `source=GIS,
authority=INDICATIVE` — knowing where a fact came from does not say whether it may be relied on.
`weakest_of()` propagates pessimistically, and an **unrecorded provenance counts as ASSUMED**, so
missing metadata degrades trust rather than silently passing as trustworthy.
`SiteConstraints.effective_authority()` reports the weakest input for the whole site.

Provenance survives every transform (tested for translate/rotate/scale/mirror).

---

## 5. UNKNOWN

`BuildableRegion` carries `Knowledge.KNOWN | UNKNOWN`, and the type makes the dangerous state
unrepresentable rather than merely discouraged:

- `KNOWN` without geometry raises at construction.
- `UNKNOWN` **with** geometry raises at construction — partial knowledge must be modelled as
  KNOWN with weaker provenance, never as UNKNOWN plus a guess parked in the geometry field.
- `require_known()` is the **only** accessor. Downstream code cannot reach the geometry without
  passing through it, so "we did not know" can never be silently read as "there was nothing
  there". The error names the recorded reason.

This directly blocks the failure the architecture report called out: lacking setback data,
quietly falling back to the parcel boundary and producing a confident, renderable, illegal
building.

---

## 6. Parcel vs BuildableRegion

Two distinct types, not one type with a flag.

- `Parcel{id, geometry, provenance, legal_ref}` — a survey/cadastral fact with a legal identity
  (`legal_ref` is free text; **no** Israeli data integration exists in this layer).
- `BuildableRegion` — derived, may be multi-component, may be UNKNOWN, records `derived_from`
  constraint ids so "why is this line here?" stays answerable.
- `SiteConstraints{parcel, constraints, buildable}` is the interface between the regulation/data
  layer above and the geometry layer below, and **defaults `buildable` to UNKNOWN** — you have
  to establish buildability, you do not get it by owning a parcel.

No `municipality`, `zone_code` or `plan_id` parameter appears anywhere in `geometry_domain`. That
was the report's testable invariant for the legal/geometry separation, and it holds. Coverage /
FAR / height ratios are deliberately **not** representable here: they constrain the produced
design, not the domain.

---

## 7. Wall-model change

`WallFacts{boundary_context, construction}` + derived `opening_policy`.

- `boundary_context` (EXTERIOR / INTERIOR / PARTY) is a **geometric** fact.
- `construction` (NONE / STANDARD_PARTITION / RC_SAFE_ROOM / STRUCTURAL) is a **program** fact.
- `opening_policy` is **derived, never stored** (FREE / RESTRICTED / NONE_PERMITTED), so it
  cannot disagree with its own inputs. An exterior ממ״ד wall is RESTRICTED (a blast-rated window
  is possible); an interior one is NONE_PERMITTED. That distinction is only *expressible* because
  the two facts stayed separate.

Geometry Core's `WallType` precedence chain is untouched — it is correct for choosing wall
*thickness*, which is its job. The adapter recovers the lost fact instead:
`wall_facts_for_side(wall_type, on_envelope)` takes exposure from **geometry**
(`envelope_sides()`), never from the enum, because `WallType.EXTERIOR` implies exposure but the
converse fails exactly where it matters.

Verified end-to-end on the real design: `SAFE_ROOM`'s east wall now reports
`boundary_context=EXTERIOR` **and** `construction=RC_SAFE_ROOM` **and** `can_take_a_window=True`,
while its west wall reports INTERIOR + RC_SAFE_ROOM + no window. Not modelled yet, on purpose:
thermal, acoustic, fire, U-value, finish.

---

## 8. Quantization

`geometry_core.model.m_to_u()` (round-to-nearest) is **unchanged** — it is correct for
dimensioning and is load-bearing for the frozen baseline.

New in `geometry_domain/units.py`, additive:

- `quantize_m(value, *, rounding)` — `rounding` is **keyword-only with no default**, so
  quantizing by accident is a `TypeError`, not a silent nearest-round.
- The unsafe mode is spelled `Rounding.NEAREST_UNSAFE` so it cannot be chosen quietly.
- Intent-named helpers read as the guarantee they give: `lower_bound_units` (ceil),
  `upper_bound_units` (floor), `length_units_no_overstate` (floor),
  `clearance_units_no_understate` (ceil).
- All of them absorb float representation error, so an exact grid value is never bumped a unit
  (`0.30 / 0.05` is `5.999999999999999` in IEEE-754; naive floor would return 5 — tested).

---

## 9. Renderer decoupling

`renderer.py` previously imported `u_to_m` from `geometry_core.model` in three places. Fixed at
the contract rather than by moving the import: **`GeometricDesign` now carries every geometric
quantity in metres.** New output types `DoorOut`, `WindowOut`, `OutdoorOut` mirror the existing
`RoomOut` pattern and convert once, in `design_output.assemble()`.

The renderer now imports only `design_output`. Two layering rules are enforced by tests that
parse the module source rather than trusting convention:

- `renderer.py` imports nothing matching `geometry_core`.
- no module in `geometry_domain/` imports `geometry_core` or `vertical_slice`.

Renderer *behaviour* was not redesigned — same drawing, same output.

---

## 10. Where Rect assumptions remain

All of them are now reachable through one module, `vertical_slice/geometry_adapter.py`:

| Location | Assumption | Status |
|---|---|---|
| `geometry_adapter.rect_to_region/ rect_to_ring` | Rect → Region | Exact, lossless |
| `geometry_adapter.region_to_rect` | Region → Rect | **Refuses** holes, arcs, non-axis-aligned, off-grid — returns `None` rather than approximating |
| `geometry_adapter.envelope_sides` | 4-sided exposure | Moved here from `windows.py`, behaviour identical |
| `geometry_adapter.wall_facts_for_room` | per-Side wall facts | The `Side` enum is still 4-valued |
| `geometry_core/*` | the whole solver | Frozen, unchanged |
| `concept.py`, `site.py`, `doors.py`, `windows.py`, `furniture.py`, `validation.py`, `design_output.RoomOut.rect_m` | Rect / 4-sided geometry | Unchanged this phase; these are the Safe Geometry Adapter's targets |

`region_to_rect` refusing rather than approximating is deliberate: a silent approximation in that
direction is exactly the "hand the solver space that does not exist" bug the architecture exists
to prevent. Approximation belongs to the next stage, where it must be provably conservative.

---

## 11. Did Geometry Core require modification?

**No.** `app/vertical_slice/geometry_core/model.py` and `engine.py` are byte-for-byte unchanged
this phase. The wall-model defect was fixed *around* the engine (adapter + domain types), not
inside it, and `m_to_u` was left exactly as it was.

Files changed outside the new packages: `windows.py` (one import — `envelope_sides` moved to the
adapter), `design_output.py` (metre-based DTOs + `wall_facts`), `renderer.py` (consumes the
contract).

---

## 12. Regression results

| Suite | Result |
|---|---|
| Full production suite (`pytest -q`) | **459 passed** |
| Previous total before this task | 365 |
| New tests added | **94** |
| Spike suite isolation | unchanged (`testpaths = ["tests"]`) |

New test files: `tests/geometry_domain/test_primitives.py`, `test_regions.py`,
`test_transforms.py`, `test_constraints_and_units.py`;
`tests/vertical_slice/test_geometry_adapter.py`, `test_baseline_and_decoupling.py`.

Every category required by task §12 is covered: rectangle via general geometry, arbitrary
straight polygon, diagonal edge, convex arc, concave arc, mixed lines+arcs, region with a hole,
multiple disconnected components, exclusion region, UNKNOWN buildable region, provenance
preservation, transforms, bulge invariance, closed-boundary validation, invalid-topology
rejection (5 distinct rejections), conservative quantization, and the exterior RC safe-room wall
preserving both facts.

**One real defect was found and fixed during implementation.** The first containment
implementation ray-cast against the chord polygon and flipped once per circular segment. That is
wrong for any point lying exactly on a chord — a circle expressed as two semicircles puts its own
centre on both chords, so the two flips cancelled and *the centre of a circle reported as outside
it*. Three tests caught it. Replaced with true ray casting that splits each arc at its y-extremes
into y-monotone pieces, each obeying the same half-open crossing rule as a straight edge.

---

## 13. Numerical baseline: before / after

| Quantity | Before | After |
|---|---|---|
| Gross area | 170.4 m² | **170.4 m²** |
| Net area | 153.83 m² | **153.83 m²** |
| Wall re-solve iterations | 2 | **2** |
| Validation checks passing | 12 / 12 | **12 / 12** |
| Rooms / interior doors / windows | 11 / 7 / 7 | **11 / 7 / 7** |

Frozen in `tests/vertical_slice/test_baseline_and_decoupling.py`, including **per-room net areas**
(a total-only check would pass on a compensating pair of errors). Behaviourally unchanged.

---

## 14. Remaining blockers before the Safe Geometry Adapter

1. **No boolean operations.** There is no union / intersection / difference over `Region`. The
   adapter needs difference (subtract exclusions) and offset (setbacks) before it can compute a
   buildable region from constraints. This is the single largest missing piece.
2. **No polygon offsetting.** Setbacks are `SETBACK_REGION` geometry today — nothing *derives*
   that geometry from a distance. Offsetting needs self-intersection cleanup and must return a
   `MultiRegion` because it can disconnect.
3. **No maximum inscribed rectangle (MIR).** The architecture report identified this as the
   highest-leverage primitive (one implementation, three consumers: conservative orthogonal
   simplification, furniture feasibility in non-rectangular rooms, residual classification).
   Not built — it belongs with the adapter that consumes it.
4. **No arc splitting at |bulge| = 1.** `is_major_arc` flags them; nothing splits them yet.
5. **Interior holes still cannot reach the solver.** `Region` can express them; the rectangular
   core cannot consume them. This is the known structural limit, not a regression.
6. **`Side` is still 4-valued** throughout doors/windows/validation. Generalizing to boundary
   segments is adapter-stage work.

None of these blocks the domain layer itself; they are precisely the next stage's contents.

---

## 15. Verdict

```
GENERAL_GEOMETRY_DOMAIN = READY
NEXT_STEP               = IMPLEMENT_SAFE_GEOMETRY_ADAPTER
```

The authoritative geometry model exists, is tested, knows no law and no solver, and the
rectangular engine now sits behind a single adapter seam without having been modified. The
canonical vertical slice is numerically identical and frozen as a regression fixture.

Stopping here for review.
