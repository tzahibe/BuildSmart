# ROOM_CAPACITY_CONSTRAINT_REPORT

**You are right, and the constraint is not area.**

A 3-bedroom house does fit in about 90 m² of rooms. The planner needs **149 m²** to produce one —
and the reason has nothing to do with the rooms not fitting.

---

## What the rooms actually need

| programme | rooms | area at minimum sizes | minimum **box** (W × D) |
|---|---|---|---|
| 2BR / 1 wet | 7 | 73.3 m² | 7.80 × 8.60 = **67.1 m²** |
| 2BR / 2 wet | 8 | 78.3 m² | 9.40 × 8.60 = **80.8 m²** |
| 3BR / 1 wet | 8 | 83.9 m² | 7.80 × 10.60 = **82.7 m²** |
| **3BR / 2 wet** | 9 | **88.9 m²** | 9.40 × 10.60 = **99.6 m²** |
| 3BR / 2 wet + ממ״ד | 10 | 98.9 m² | 9.40 × 13.20 = **124.1 m²** |
| 4BR / 2 wet | 10 | 99.4 m² | 9.40 × 13.40 = **126.0 m²** |

Your instinct is almost exactly right: **3 bedrooms + 2 bathrooms sum to 88.9 m² at their minimum
sizes.** So from ~90 m² of *area*, the rooms are there.

But a footprint is not an area — it is a width and a depth, and both have floors. The programme
needs **at least 9.40 m of width and at least 10.60 m of depth simultaneously**. That is a 99.6 m²
box, and only in one shape.

**This is why 100 m² does not work.** At 100 m² the widths that satisfy both floors are

```
width ≥ 9.40      (the three columns at their minimum widths)
depth = 100/width ≥ 10.60   →   width ≤ 9.43
```

a feasible band **3 centimetres wide**. Nothing in the product will ever land inside it.

## Where the depth goes

The private column stacks **one room per row**. Only an ensuite shares its bedroom's row; everything
else gets its own:

| programme | private rows | minimum depth |
|---|---|---|
| 2BR / 1 wet | 3 — MASTER, BEDROOM, BATH | 8.60 m |
| 3BR / 2 wet | 4 — [MASTER+ensuite], BEDROOM, BEDROOM, BATH | 10.60 m |
| 3BR / 2 wet + ממ״ד | 5 | 13.20 m |
| 4BR / 2 wet + ממ״ד | 6 | 16.00 m |

Each row costs its own minimum short side plus a wall allowance — **2.6 to 3.2 m of depth for a
room that may only be 9.5 m²**. Rooms are added to the *depth*, never to the *width*, because a
column is one room wide by construction.

## And the engine needs half as much again

Sweeping every feasible proportion at each area, the first area that actually produces a plan:

| programme | minimum box | first area that plans | shape that did it | overhead |
|---|---|---|---|---|
| 2BR / 1 wet | 67.1 m² | **102 m²** | 10.80 × 9.44 | +52% |
| 2BR / 2 wet | 80.8 m² | **115 m²** | 13.00 × 8.85 | +42% |
| 3BR / 1 wet | 82.7 m² | **142 m²** | 11.40 × 12.46 | +72% |
| 3BR / 2 wet | 99.6 m² | **149 m²** | 11.00 × 13.55 | +50% |
| 3BR / 2 wet + ממ״ד | 124.1 m² | **154 m²** | 11.20 × 13.75 | +24% |
| 4BR / 2 wet | 126.0 m² | **155 m²** | 11.00 × 14.09 | +23% |

At 3BR / 2 wet I swept **every** width in the feasible band at 100, 110, 120, 130 and 140 m². Not
one proportion planned, and the rejection was the same sentence every single time:

> *west column needs more than N m of depth for its N rows at their minimum dimensions*

Note the shape that finally worked at 149 m²: **10.90 × 13.67**. The depth is 13.67 m, not the
10.60 m the minimum short sides call for. The extra ~3 m is the second rule in `_row_depths`: a row
must be deep enough to hold its **area** at the column's width, not merely to clear its short side.
The private column is narrow — the public column and the corridor take the width first — so every
private row needs depth to hold its area, and four of them stack.

## The three constraints, in order of how much they cost

1. **One room per row in the private column.** Rooms buy depth, never width. Going from 3 private
   rows to 4 moves the working area from ~102 m² to ~142 m² — **a single extra row costs about
   40 m²**. This is the dominant cost and it is a limitation of how the generator builds a column,
   not of the rooms.
2. **Row depth is driven by area, not by the short side.** A narrow column forces deep rows. This
   is the ~50% overhead between the minimum box and what plans.
3. **Minimum short sides.** MASTER 3.0 m, BEDROOM 2.6 m, LIVING 3.0 m — these set the 9.40 m width
   floor and part of the depth floor. The smallest real constraint of the three, and the only one
   that is genuinely architectural.

## What would change it

**Let a private row hold two rooms.** The mechanism already exists — an ensuite shares its
bedroom's row today — but it is applied only to that one case. A bathroom or a WC beside a bedroom,
or two small rooms side by side, would take 3BR / 2 wet from 4 rows to 3: minimum depth 10.60 → 8.80 m,
minimum box **99.6 → 82.7 m²**, and by the row-cost measured above, the working area from ~149 m²
to roughly ~110.

That is one change in `_rows_of`, the same function that already pairs the ensuite. It is the
Concept Generator change the earlier diagnostic identified as cluster 2 (~144 cases), and this
analysis says it is also what stands between a 100 m² plot and a 3-bedroom house.

**A small WC is worth its own row far less than a bathroom.** A 1.5 m² WC still costs a full row —
1.8 m of depth — under today's structure. Adding the room type without also allowing shared rows
would make the constraint *worse*, not better.

---

## Also in this pass

- **Default setbacks are now 0.** Any non-zero default is a planning determination this project has
  not made, and 5.5 / 3 / 4 consumed 68% of a 300 m² plot. Zero asserts nothing; the buildable
  region is the parcel until real setbacks are entered, and the fields are on the form.
- **The logged crash is fixed.** `SetbackAssumptions` required `gt=0`, so typing 0 in the review
  raised a 500. Zero is a legal assumption — a building on the street line — and is now accepted
  everywhere. The failure log caught this exactly as intended: one `CRASH` entry with the
  traceback, `PUT /review`, `ValidationError`.
- **Offered footprint proportions are now plannability-aware.** Even spread across the geometric
  band put 39% of options in ratios that succeed 16–19% of the time; they now cluster where the
  parti works. Scan: reaching a drawing **448 → 511** when cycling all four cards, and **608** when
  taking the first (best) card — 42% of 1440.
- 747 backend tests pass. 14 tests that read the old non-zero defaults implicitly now state their
  setbacks explicitly, so they test the behaviour rather than the default.

Stopping for review.
