# General Concept Generator V1 — Implementation Report

```
GENERAL_CONCEPT_GENERATOR = PARTIAL
NEXT_STEP                 = REFINE_CONCEPT_GENERATOR
```

**615 tests pass** (578 before, +37 new). The canonical vertical slice is numerically untouched.
Geometry Core and the Safe Geometry Adapter were not modified.

PARTIAL, not READY, for two honest reasons: the largest programme (4BR + safe room + 3 wet
rooms) is rejected by every strategy, and multi-wing allocation is *evaluated and declined* on
every fixture rather than ever being used.

---

## 1. Audit of the canonical concept

| Assumption | Classification | Fate |
|---|---|---|
| `bedrooms == 3 and safe_room and wet_rooms == 2` guard | canonical-program-specific | **discarded** |
| The fixed 11-zone list with literal area bands | canonical-program-specific | **discarded** |
| The fixed access-edge list | canonical-program-specific | **discarded** |
| `FOOTPRINT_WIDTH_M = 12.0`, `FOOTPRINT_DEPTH_M = 14.2` | fixed-dimension | **discarded** — searched now |
| Cuts 4.7 / 1.6 / 3.45 / 5.0 / 4.5 / 3.8 | fixed-dimension | **discarded** — computed now |
| Single `Wing`, no `seam_leaf_sides` | single-wing | **discarded** (multi-wing evaluated) |
| Two-segment hall (`HALL_MAIN`/`HALL_SPUR`) | canonical accident | **discarded** — one spine borders every room |
| Open-plan LDK as one open group, no doors inside it | **architectural** | **kept**, re-derived generically |
| Circulation borders every private room (no room is transit) | **architectural** | **kept** |
| Safe room entered from circulation, never a bedroom | **architectural** | **kept** |
| Ensuite entered from its bedroom, not the hall | **architectural** | **kept** |
| Force cuts ONLY where sibling subtrees must align | **solver-mechanical** | **kept** |

## 2. ArchitecturalSpec → room groups

`build_room_program` reads `ProgramSpec` only — no scenario names anywhere. It emits public
zones (three if open-plan, otherwise living + kitchen), one hall, a master plus `bedrooms-1`
bedrooms, a safe room if requested, and `wet_rooms` bathrooms of which the first becomes an
**ensuite** when there are ≥2 wet rooms and a master exists. Each room carries a `RoomTemplate`
(area band, min short side, aspect, and an **elasticity** saying how much of a larger house that
role should absorb — a living room grows, a safe room and a bathroom do not).

## 3. Multiple wings

The adapter's candidates are consumed with their areas, dimensions and seam adjacency. The
primary (largest) wing hosts the programme. `_multi_wing_assessment` then evaluates the second
wing explicitly.

## 4. Does the generator ever ignore a useful wing?

**No — it declines them with a stated reason, which is the compliant outcome, but it never yet
uses one.** On the L-shape it reports:

> seam covers 9.5 m of the primary wing's 16.0 m side, so a hall column against it would be part
> exterior and part seam; reaching wing 1 (47.5 m²) would route circulation through a private
> room

That is a real architectural finding, not an evasion: an L decomposition always produces a
*partial* seam on the larger wing, so a hall placed against it would need a single leaf side to
be simultaneously exterior and interior — the spike's L2 finding. Reaching the wing without
splitting the hall means entering it through a bedroom, which the priorities forbid. Metrics
report the unused wing area (48 m² on the L-shape, 42 m² on the obstacle case).

## 5. Access topology

`_build_access` derives the graph from the **programme**, before any rectangle exists:
circulation reaches every private and service room directly; ensuites are entered from their
bedroom; open-plan zones are joined by `OPEN_CONNECTION` and therefore produce no doors. A test
(`test_topology_does_not_depend_on_the_wing_rectangle`) runs the same programme on two different
safe geometries and asserts the access graphs are **identical** — dimensions cannot redefine
topology.

## 6. How many candidates are needed?

2–5 generated per scenario; the first valid one is index **0** in 8 of 9 solved cases and index
1 once (rect + 3BR). Pre-solver rejection does most of the work: 0–4 rejected per scenario, and
the solver is invoked 1–2 times, never wastefully.

## 7. Which programmes work?

| Programme | Result | Strategy | Gross | Rooms |
|---|---|---|---|---|
| 2BR, 1 wet | **SOLVED** | public/private spine | 104.6 m² | 7 |
| 2BR + safe room, 1 wet | **SOLVED** | public/private spine | 128.8 m² | 8 |
| 3BR, 2 wet | **SOLVED** | double-loaded | 152.6 m² | 9 |
| 3BR + safe room, 2 wet | **SOLVED** | double-loaded | 154.8 m² | 10 |
| 3BR + safe room, 3 wet | **SOLVED** | double-loaded | 149.9 m² | 11 |
| **4BR + safe room, 3 wet** | **REJECTED** | — | — | — |

All solved cases pass **12/12** slice checks with every room inside the buildable geometry.

## 8. Which geometries work end-to-end?

| Geometry | Result | Gross | Checks | Unused wing |
|---|---|---|---|---|
| rectangle | SOLVED | 154.8 m² | 12/12 | 0 |
| L-shaped | SOLVED | 149.9 m² | 12/12 | 48 m² |
| curved (concave) façade | SOLVED | 149.9 m² | 12/12 | 0 |
| obstacle / exclusion | SOLVED | 149.9 m² | 12/12 | 42 m² |
| disconnected components | SOLVED | 150.4 m² | 12/12 | 48 m² |

Latency 149–468 ms end-to-end including adapter, solver and render.

## 9. Did the canonical regression survive?

**Yes, numerically identical**: `run_demo` still yields gross **170.4 m²**, net **153.83 m²**,
**2** iterations, **12/12** — asserted by the untouched baseline tests. `concept.py`'s
hand-authored fixture is retained *solely* as that frozen baseline; nothing on the general path
calls it.

**Four tests were intentionally changed.** `test_geometry_core_output_is_identical_across_all_
geometry_cases` asserted that every general-geometry case reproduced the canonical 170.4 m²
design. That was only true while the general path *reused* the hand-authored concept. The
generator now sizes the house to the programme and the available wing, so the geometry
legitimately differs per site; the test was replaced by
`test_design_is_generated_not_the_canonical_fixture`, which asserts the design is real, complete,
generated, and explicitly **not** the canonical one.

## 10. Did Geometry Core require changes?

**No.** `geometry_core/` and `safe_adapter.py` are unchanged. One small change was needed in
`doors.py`: `build_entrance_door` hard-coded the zone id `"HALL_MAIN"`, so the generator's
`HALL` was never seeded into the accessibility graph and every room reported unreachable. It now
takes the entrance zone id, defaulting to the canonical name so the baseline is unaffected.

## 11. Concept-level failures that remain

1. **4BR + safe room + 3 wet rooms is rejected by every strategy.** With 11 rooms the private
   side needs 7 stack rows; at their minimum depths those exceed even a 16 m deep envelope. The
   layout supports exactly **two** room columns plus a hall, and an 11-room programme needs a
   third. This is the clearest limit and the first thing to fix.
2. **Multi-wing allocation is never used** (§4). It needs a hall that splits at the seam — the
   generated branched-hall pattern applied across wings.
3. **The strategies are near-duplicates.** All four differ only in the west/east allocation;
   there is no genuinely different parti (courtyard, front-to-back, entry vestibule).
4. **No scoring.** Candidates are ordered by construction, not ranked by quality.

## 12. Geometry-representation-level failures

Unchanged from the adapter phase and explicitly *not* addressed here: the **diagonal polygon
retains only ~0.798** of its area under axis-aligned decomposition. That is a solver-
representation limit (it needs a rotated frame or a richer solver), not a concept-generator
limit, and is carried forward as a future richer-solver case.

## 13. Is the pipeline general enough for a real demo?

**For a 2–3 bedroom house with or without a safe room, on rectangular, L-shaped, curved,
obstructed or disconnected sites: yes.** Five programmes × five geometries run end-to-end from
an `ArchitecturalSpec` to a rendered, validated plan with every room provably inside the legal
buildable region. The rendered L-shape output reads as a real house: a double-loaded corridor,
open-plan LDK with no internal walls, a master-plus-ensuite pair, and bedrooms and the safe room
off the hall.

**Not yet for 4+ bedroom houses, and not yet using more than one wing.**

---

### What the implementation actually taught

The hardest part was not the tree synthesis but the coupling between programme and geometry.
Three designs failed before the fourth worked:

1. **Width by area share** — a column runs the full depth, so its width is forced by
   `area / depth`; splitting the width by share then made small rooms too shallow (a 6.5 m²
   bathroom across a 5 m column is 1.3 m deep, under its 1.6 m minimum).
2. **Area-driven depth with geometry-derived floors** — an unstable fixed point: raising a
   room's area to fix its depth moved the column width, which moved the requirement again.
3. **Depth chosen directly, areas derived from `width × depth`** — stable, and feasible by
   construction. This is the design that shipped.
4. **A single aspect constant for the footprint could not work at all.** Widen it and the
   columns fit but the rows go shallow; deepen it and the reverse. The generator now runs a
   bounded deterministic search over footprint width *and* depth, because the minimum-dimension
   floors make the programme genuinely need more gross area than its template estimate.

---

## Verdict

```
GENERAL_CONCEPT_GENERATOR = PARTIAL
NEXT_STEP                 = REFINE_CONCEPT_GENERATOR
```

The hard-coded canonical concept is gone from the product path; programmes and topology are
generated from the spec; five programmes and five geometries run end-to-end at 12/12. What
holds it back from READY is concrete and bounded: a third room column for large programmes, and
turning the multi-wing assessment from a reasoned decline into a working allocation.

Stopping here for review.
