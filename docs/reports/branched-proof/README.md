# #185 — BRANCHED end-to-end proof: **not achieved**, and exactly where it stops

**Acceptance was one complete, validator-PASS BRANCHED plan. I did not reach it.** This reports
what the attempt did establish, what blocks it, and the one thing I would change next.

**No production file was touched.** Everything is in `backend/app/ai_harness/branched_proof/`.

---

## 1. The brief, and why it was chosen

**B06** — 3 bedrooms, 2 wet rooms, no safe room, not open plan, footprint **13 × 24 m**.

- its programme is inside #185's bounded 3–4 bedroom scope;
- 2 wet rooms is the simplest case: one ensuite, one shared;
- no safe room, so the simpler variant of the parti;
- #184 measured the production branched tree's envelope at **8.20 × 16.50 m**, and 13 × 24 m hosts
  that comfortably — it was the deepest frozen site available;
- production delivers **177 m²** on B06 (92% of its 193 m² programme capacity), a clear baseline.

## 2. What the attempt achieved

### The C26 blocker from #184 is solved
#184's single finding was that the production tree leaves three corridor ends at a blank wall. The
redesigned tree terminates each end at a destination:

```
            LIVING   |   KITCHEN                 public band, north
   -------------------------------------------
     MASTER  |      HALL_A      |  <room>        a room at EACH end of the entry hall
   -------------------------------------------
     HALL_B  |        BEDROOM_1                  HALL_B under HALL_A: the junction serves its north
     BATH_2  |        BEDROOM_2                  a wet room serves its south end
```

Measured on the realized plan: **dead ends 3 → 1**, and `classify_extreme` returns clean. **C26
passes.** Nothing was relabelled and `circulation_metrics` was left to do the counting.

### Area and programme are not the problem
| | production primary | this attempt |
|---|---:|---:|
| gross area | 177.4 m² | **166.3 m²** (94%) |
| programme capacity | 193 m² | — |
| rooms | all | **all 8 preserved** — LIVING, KITCHEN, HALL, MASTER, BEDROOM_1, BEDROOM_2, BATH_1, BATH_2 |

Room areas were LIVING 44.6, KITCHEN 25.6, MASTER 13.0, BEDROOM_1 14.0, BEDROOM_2 13.5, BATH_1 5.8,
BATH_2 6.6, plus two halls at 13.9 and 16.6 m². No oversizing: every room sits inside its own
template band, and the house is **smaller** than production's, not larger.

## 3. Why it still fails — four checks, two causes

```
C7   HALL_A-HALL_B shared 0.60 m too short for a 0.9 m door
C13  HALL_A-HALL_B (CASED_OPENING): shares 0.60 m of wall but no placeable opening was generated
C5   BATH_2; BEDROOM_1; BEDROOM_2; HALL_B          <- the whole wing, cut off by the above
C17  BATH_1 (ensuite): entered from HALL_A, required only from MASTER
```

- **The junction is too narrow.** `HALL_A` begins at the master's width; `HALL_B` sits below it but
  reaches only 0.60 m past that, so the two corridors share too little wall for a door and the
  entire bedroom wing is disconnected. C5 is a consequence, not a separate defect.
- **The ensuite was placed off the hall.** C17 requires an ensuite to be entered from its host, so
  `BATH_1` must sit with the master, not terminate the entry hall.

## 4. The wall I hit when fixing them — and it is a real one

Fixing C17 means stacking the ensuite behind the master, which makes the entry row as deep as the
two of them together (~6 m). For that hall to have ends at its **west and east** it must be wider
than it is deep — `circulation_metrics._end_sides` takes a room's ends to be the two sides of its
own long axis, so a hall narrower than deep has its ends at the north and south and the rooms I put
beside it serve nothing. So the hall must exceed ~6 m wide, which makes the plan

> master (3.75) + hall (>6) + end room (2.8) ≈ **12.5 m wide**,

while the wing below must be the same width as a corridor plus a bedroom — and a bedroom's own
template caps its long side at 18 ÷ 2.6 ≈ **6.9 m**, so the wing can only reach about 8.2 m unless
the corridor is made implausibly wide. On B06's 13 m site the three requirements cannot hold at
once: **ensuite with its host, a horizontal entry hall with rooms at both ends, and bedrooms inside
their size caps.**

That is a genuine geometric conflict in this tree, not an iteration I ran out of patience with.

## 5. Answer

**A fully valid BRANCHED plan was not produced.** The single blocker #184 identified — C26 — is
solved and stays solved. What replaced it is an access-topology conflict: a two-corridor plan needs
its corridors to overlap by a door's width, and a horizontal entry hall with served ends forces a
width the bedroom templates will not accept on a 13 m site.

## 6. Recommended next step — one

> **Move the master and its ensuite into the wing, and let the entry hall be short.**
> The entry hall then only has to serve the public band and the wing corridor, so it need not be
> wide enough for rooms at both ends; the wing carries the master with its ensuite at one end and
> the other bedrooms along it, and the wing corridor terminates at the master's door.

Why this one: it removes the width conflict at its source rather than trading one check for
another. It keeps the ensuite with its host (C17), gives both corridors a served end (C26), and
makes the junction a simple overlap of two corridors of similar width (C7/C13). It is still a
hand-authored tree change in the experimental path, with no validator, Geometry Core or production
change.

**Not recommended:** widening the bedroom template caps, relaxing C17, or allowing a corridor wide
enough to bridge the width gap. Each buys a PASS by breaking something the checks exist to protect.

## 7. Scope kept

No production code changed. No validator or Geometry Core change, no L-shapes, no new planner, no
5–6 bedroom support, BRANCHED not enabled anywhere, production default untouched, and the house was
never enlarged to make the experiment pass — it came out **smaller** than the production primary.
