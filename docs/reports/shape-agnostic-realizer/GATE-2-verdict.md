# Gate 2 — verdict: **PIVOT** (representation), with the evidence that decides it

Day 3 of the 5-day time-box. One IR, one algorithm (formulation A — a staircase of full-depth
bands inside an orthogonal envelope), the six frozen cases (v1.1, declared), no per-case branch.
Every number below is read off realized geometry through the **unchanged** `validate()`, or off
the MILP oracle's own status.

## 1. The six

| case | verdict | the decisive numbers |
|---|---|---|
| **F1** rectangle control | **SOLVED** | 5/5 plans count: contacts n/n, doors n/n, 28 validators, 80–83 % gross (`BELOW_TARGET_DISCLOSED`); flush 0..12 m rectangles; one run produced a genuine L on the rectangular plot when the rooms' maxima could not fill the width (`figures/F1-rect-control__BEDROOM_WING+FOYER__early-L.png`) |
| **F2** L envelope | **not solved** | oracle: **39 / 1920** band layouts feasible (all HALL_SPINE, embedder indices 6–31). Every one sizes exactly and realizes geometry; then **34 × NO_ENTRANCE, 4 × C22** |
| **F3** wide-shallow strip | **not solved** | oracle: **18 / 1920** feasible (3 bands along the street). All size; then **7 × NO_ENTRANCE, 5 × C19 exposure, 2 × C22** |
| **F4** street-side court | **not solved** | the building starts below the court (y = 5 m) as designed; the production SELECTION screen rejects **553 × exposure, 397 × entrance, 124 × safe room** before sizing; oracle: 2 feasible of 76 screened; both fail validators |
| **F5** garden court | **typed refusal, as declared** | `BAND_GAP` in 1.4 s, naming the depth of the split |
| **F6** K4 | **REFUSED correctly** | `TOPOLOGY_REPRESENTATION_LIMIT`, every parti, **0.0 s**, before any geometry |

**Tally: 2 of 6** against the Gate-2 bar of ≥ 4/6. The bar is not met, and the reason is now
specific enough to act on.

## 2. What was measured, and what each measurement ruled out

1. **Not the search.** The MILP oracle (formulation B as a question about A: heights from a grid by
   binaries, integer boundaries, every cell / contact / door / connectivity / envelope constraint
   linear; HiGHS, ~15 ms per candidate) agrees with the exact sizer wherever the sizer answers and
   finds feasible band layouts on F2, F3 and F4 that the height search could not. Seeded with the
   oracle's heights, the exact sizer realizes geometry for **every** oracle-feasible F2/F3
   candidate. I had first read 18 infeasible samples on F2 as "the family cannot do it"; the full
   sweep corrected me, and the correction is in the evidence files.
2. **Not alignment either, mostly.** The one-wall-type-per-side rule (C22 "PARTIAL seam") costs
   4–6 candidates per case; cell splitting as the alternative is rejected by C20/C9/C24/C31 — tried,
   measured, removed.
3. **It is entrance and exposure — the band family's own geometry.** A band holds one row of
   full-depth rooms, so for 12–13 rooms there are 3–4 bands, the hub hall sits in a middle band
   (the Part-3 fact again), the street band is whatever the embedder put there, and interior rooms
   have no exterior wall. On F2, 34 of 38 realized layouts have **no allowed arrival room
   fronting the street**; on F4, 950 of ~1150 candidate-orientations die at the production
   SELECTION step on exposure or entrance before any geometry. F1 passes because 10 rooms fit in
   3 bands with the hall adjacent to the street.
4. **The refusals are honest.** F5 and F6 are typed, instant, and name the reason; nothing was
   relaxed; `realize_layout` and every validator are byte-unchanged.

## 3. Why this is a PIVOT and not a STOP

The architecture of ADR-001 held: a shape-free IR, an envelope polygon, the downstream unchanged,
the product's `DemoPlan` drawing stepped and L footprints it was never handed before. What failed
is the **representation inside each wing** — one row of full-depth rooms — on exactly the
architectural constraints a real house carries most: an entrance on the street and a window in
every bedroom.

**The pivot: a 2D wing per band.** Each band becomes a `GridWing` — the carrier that already exists,
with the exact per-cell sizing that already exists (`band_sizing.solve_band_sizing`) — placed with
its own horizontal extent; the staircase stays *between* wings. Two rows inside a wing give the
hub hall a street-side neighbour and interior rooms a second exterior edge. Nothing names a shape;
`realize_cells`, the envelope, the oracle and the harness carry over. New work: the wing-grouping
decision (which rooms form which 2D wing — `graph_embedding` already produces GridWings) and
per-wing extents in the oracle and sizer.

## 4. What is committed (PR #198)

`app/vertical_slice/envelope.py`, `app/vertical_slice/staircase_sizing.py`, `realize_cells` in
`rectilinear_realizer.py` (`realize_layout` untouched), `app/ai_harness/shape_agnostic/`
(harness + MILP oracle — research tooling: `scipy` is **not** a declared production dependency,
it arrives transitively through the `knowledge-embeddings` extra, and the oracle test skips where
it is absent), 16 new tests, the frozen six v1.1 with its declared revision, renders in `figures/`,
every run's `results.json` and both oracle sweeps in `data/`.

## 5. Remaining effort, honestly

Two days remain. The 2D-wing pivot is a bounded change to two modules plus the oracle; the risk is
that exposure for 5-bedroom programmes needs more than two rows per wing on a shallow strip (F3),
in which case the right answer is a typed refusal, not a deeper grid. I recommend spending day 4
on the pivot and day 5 on Gate 3's quality axes with whatever the pivot reaches — and STOP at the
time-box regardless, with the evidence as it stands.
