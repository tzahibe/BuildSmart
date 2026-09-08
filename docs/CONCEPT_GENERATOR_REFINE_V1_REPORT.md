# Concept Generator — Refine Pass 1

```
GENERAL_CONCEPT_GENERATOR = PARTIAL (unchanged)
NEXT_STEP                 = REFINE_CONCEPT_GENERATOR (continue)
```

**618 tests pass** (615 before, +3). No regressions: every scenario that solved before still
solves at 12/12. The canonical baseline is untouched. Geometry Core and the Safe Geometry
Adapter were not modified.

I made the four decisions you left open, and say so plainly: **4BR treated as a real
requirement**, **scoring deferred**, **multi-wing deferred**, **canonical baseline stays
frozen**.

---

## What landed

### 1. A genuinely different parti: `FRONT_PUBLIC_BAND`

Public zones as a full-width band across the front; corridor and bedrooms behind it. The hall
now borders the public band to the north **and** both bedroom columns east and west — three
neighbours instead of two. This addresses item 3 from the previous report (the four strategies
were near-duplicates) as well as being the intended fix for large programmes.

**It is not dead code — it wins the 2BR programme outright** (`FRONT_PUBLIC_BAND`, 104.5 m²,
12/12), pinned by a test.

### 2. Three real bugs found and fixed

| Bug | Effect | Fix |
|---|---|---|
| Shared rows split by **area alone** | An ensuite got 30% of a 5 m column = 1.39 m, under a bathroom's 1.6 m minimum | `_row_widths()` allocates every member its minimum first, then shares the surplus by area |
| Rear split fixed at the **midpoint** | 4 rows needing 11.6 m of depth where 9.95 m existed, while a 3/4 split of the same rows fits | The balance point is now a searched variable, nearest-balanced first |
| `rear_depth` **rounded to nearest** | Landed centimetres *below* the requirement it was derived from, so the row planner rejected its own input | Rounds up |

### 3. An ordering inversion that mattered

Sizing rooms from the whole footprint first **inflates the bedrooms** when the footprint is
generous, and inflated bedrooms need more rear depth than exists. The rear is now sized from the
bedrooms' own programme, takes exactly the depth it needs, and the public band absorbs whatever
depth is left — which is what a living room's elasticity is for.

---

## What did NOT land: 4BR still does not complete

The failure **moved but did not close**. Previously 4BR was rejected by every strategy
*pre-solver*. Now the front-band concept is generated and passes the capacity pre-check, and
Geometry Core rejects its forced cuts:

```
no V split of Rect(w=238, h=236) for [MASTER, BATH_1, BEDROOM_1, HALL, ...] at forced position 96
```

That is progress in the sense that the layout reasoning is now right and the disagreement is
between my computed forced cuts and the shape curves they must satisfy — but it is not a
result, and I am not going to describe it as one. It is pinned by
`test_four_bedroom_programme_still_does_not_complete_end_to_end` so it cannot regress silently
in either direction.

**Why I stopped here rather than continuing:** this pass went through five design iterations on
the programme/geometry coupling, and each fix revealed the next constraint one layer down. The
remaining gap is a mismatch between forced cut positions and derived area bands, which is the
same class of problem — and I would rather hand you an honest boundary than keep grinding.

---

## The finding that matters most for the next pass

While implementing the front band I established something that constrains every future
circulation design:

> **A genuinely bent (L- or T-shaped) corridor cannot be one open-plan space in this engine.**
> Open-marking requires the group's leaves to be siblings in the slicing tree, and two siblings
> are always aligned rectangles. Declaring a bent hall as an open group would leave a real
> partition wall between its arms while the access graph claimed they were joined — connected
> on paper, walled in fact, with `C5` passing because it reads the declared graph.

This is why the front-band parti changes the shape of the **plan** rather than the shape of the
**corridor**, and it is the same wall that blocks multi-wing allocation (a partial seam needs a
hall that is part-exterior, part-seam). Both items therefore depend on one thing: either a
validation check that a declared `OPEN_CONNECTION` is actually realized as an `OPEN` wall, plus
an engine capable of non-sibling open groups — or a decision that corridors stay straight and
the parti carries the variety.

**That is the question I would want answered before the next pass**, because it determines
whether multi-wing is reachable at all or should be closed as out of scope.

---

## Status

| Programme | Result |
|---|---|
| 2BR, 2BR+safe room | **SOLVED** 12/12 (2BR now via the new parti) |
| 3BR, 3BR+safe room, 3BR+safe room+3 wet | **SOLVED** 12/12 |
| 4BR + safe room + 3 wet | **still fails**, now at the solver rather than the pre-check |

All five geometries (rectangle, L, curved, obstacle, disconnected) still run end-to-end at 12/12
with every room inside the buildable region.

Stopping for review.
