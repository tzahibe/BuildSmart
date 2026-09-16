# The First Production L Parti — implementation record

**Date**: 2026-09-16 · **Branch**: `012-l-parti` (stacked on `011-footprint-regions` → `010-multi-level-phase0`, worktree `sddproject-010`) · **Plan**: `BUILDING_SHAPE_MASSING_FAMILIES_REPORT.md` §2.2, Phase 2

**Scope as given**: exactly two connected rectangular wings with one declared seam, using the adapter's existing adjacent candidates; a public/main wing and a private/bedroom wing; access between wings realized through the seam; the spike's P9 seam proof in production; one-wing behaviour byte-identical; no shape UI. Not a T, U, courtyard or irregular plan; not a ranking change.

## What was built

| Where | What |
|---|---|
| NEW `vertical_slice/l_parti.py` | The parti. Primary wing = the front-band structure `H(band, V(column, HALL))` with the **hall pinned to exactly the seam** by forced cuts (the spike's L2 resolution); arm = a second `Wing` of stacked private rows whose seam-facing members are declared in `seam_leaf_sides`. `seam_geometry` classifies the pair (arm east/west; flush with the street → band to the garden; flush with the rear → band on the street; floating → primary trimmed to make it rear-flush) and refuses an arm north/south of the primary, one that extends past it, and a pair that forms a rectangle — each with its reason. |
| allocation (`_l_allocations`) | Arm = bedrooms with their ensuites (+ shared baths, or + the safe room); column beside the hall = the rest (safe room + WC, or the wet cluster); band = the public group **whole** (never split — an open group across two subtrees would be walled). **Overflow**: an arm too short for its rows keeps the rows that fit (master first) and the rest joins the column — or, alternatively, the last secondary bedroom(s) move beside the hall (an elastic row the column can fill its length with). A one-row column also gets the bedroom-beside-the-hall variant proactively. Closed plan only: the kitchen may sit beside the hall with its own door. Every move is in the rationale. |
| sizing (`_plan_l`) | Bounded search: arm length from the candidate's full length down in 0.5 m steps to the rows' floors (≤ 12); column widths from the narrowest (the column must FILL the hall's length, and ceilings fall with width) through the seam-option neighbourhood; band side by side (front-band widths by area share) or stacked (one open subtree). Band depth tracks the request within the rooms' shape bands. Every sizing rule is the existing one — `_rows_for_width`, tier-2 `Repartition`, `_row_depths` with deficit/hard tiers, `room_depth_band_m`, `_seam_options`, `_hall_width_m`, `_zone_spec`, `_build_access` (front-band form), `_forced_chain`. Up to 3 sizings per allocation-and-band form, nearest the target. |
| `concept_generator.generate_concepts` | `_multi_wing_assessment` → `_two_wing_pair`: a non-adjacent second wing is still declined with `NO_SEAM_ALIGNMENT`; an adjacent one reaches the parti. The L is appended after the hub per variant; **without a target it is moved to the very end** (after every one-wing candidate, twin, tier 2 and last-resort hub) so it never displaces the plan a brief already had; with a target it competes under the area sort like every other candidate. A single candidate never reaches it. |
| `validation.py` C22 | **P9 ported**, multi-wing fixtures only (a one-wing house has no seam to prove — and one-wing reports stay identical): every declared seam side lies on its wing's boundary and is abutted by the *other* wing along its whole length (a partial abutment is the L2 defect); is not typed `EXTERIOR` and carries no window; every side that abuts the other wing IS declared; every room lies inside its wing; and at least one **realized** connection joins zones of different wings — two buildings that touch are not one house. |
| `demo/contract.py` | `_STATEMENTS["C22"]`. |
| `geometry_fixtures.py` | Four more L sites (`front_arm`, `long_arm`, `deep_primary`, `west_arm`) via one `_l_site` helper — the measurement matrix. |

## Measured

### 432-context regression (the demo path)

Full-payload snapshot (whole `DemoPlanSet` JSON, primary + every alternative, additive fields stripped), this branch against branch `011`, over the 431 distinct failure-log contexts in the worktree's log copy: **planned before = after = 404; 404/404 payloads byte-identical; 0 status or refusal-code changes; 0 missing.** The demo path plans a single rectangle, so no pair reaches the parti — as expected.

### The L fixtures — plans, refusals, and the one-wing plan for the same brief

`eff` = effective target (request capped at the programme's capacity). "1-wing" = the pipeline's primary for that brief. "L" = the nearest-target **valid** L candidate (all L candidates were realized independently of ranking). `2side` = share of habitable rooms with ≥ 2 exterior walls. `cross` = realized doors across the seam. Runtimes: `t_pipe` the full pipeline run (L candidates in the pool), `t_L` generation plus solving and realizing every L candidate.

```
site         programme              eff | 1-wing gross    %  circ priv≤ 2side | L cands/valid  L gross   %  circ priv≤ pub≤ 2side cross C17/20/21/22 t_pipe  t_L  L-primary?
E1 rear-arm  2BR+MMD open t150      150 |       151.0  101   11%  1.58   50% |     12/12       123.6  82    6%  1.73 2.13   83%    2   TTTT          2.5  2.6  no
E1 rear-arm  3BR+MMD open t200      200 |       181.2   91   10%  1.65   29% |      0/0           refused: column beside the hall cannot fill the 9.5 m seam           2.2  0.9  no
E1 rear-arm  3BR+MMD closed t200    200 |       198.4   99   13%  2.12   33% |     56/56       150.7  75    8%  1.98 1.31   33%    3   TTTT          1.1  4.3  no
E1 rear-arm  3BR noMMD open t180    180 |       178.5   99   12%  1.98   33% |      6/6        130.2  72    7%  1.85 2.22   83%    2   TTTT          1.1  1.2  no
E1 rear-arm  4BR+MMD open t240      240 |     refused                        |      0/0           refused: column rows' floors exceed the seam                          5.3  2.0  no
front-arm    2BR+MMD open t150      150 |       151.0  101   11%  1.58   50% |     12/12       129.9  87    5%  1.96 2.22   83%    2   TTTT          2.5  2.8  no
front-arm    3BR+MMD open t200      200 |       181.2   91   10%  1.65   29% |      0/0           refused (as E1)                                                         2.2  0.9  no
front-arm    3BR+MMD closed t200    200 |       198.4   99   13%  2.12   33% |     56/56       151.6  76    9%  1.96 1.04   50%    3   TTTT          1.1  4.2  no
front-arm    3BR noMMD open t180    180 |       178.5   99   12%  1.98   33% |      6/6        130.2  72    7%  1.85 2.31   67%    2   TTTT          1.1  1.2  no
long-arm     2BR+MMD open t150      150 |       148.8   99   13%  2.08   50% |      0/0           refused: 6 m arm too wide for a lone bedroom / safe room row            2.4  1.8  no
long-arm     3BR+MMD open t200      200 |       181.9   91   10%  1.65   29% |      8/4         143.1  72    8%  2.38 1.82   71%    3   TTTT          3.2  1.5  no
long-arm     3BR+MMD closed t200    200 |       198.1   99   13%  1.44   33% |     36/18        159.0  80    9%  2.38 2.26   33%    4   TTTT          1.3  2.4  no
long-arm     3BR noMMD open t180    180 |       182.7  101   12%  2.04   33% |      6/6        137.1  76    7%  1.81 1.78   83%    2   TTTT          1.6  1.3  no
west-arm     (mirrors E1 exactly: same figures with the arm west)
deep-primary 2BR+MMD open t150      150 |       150.3  100   11%  1.41   50% |     12/12       147.0  98    5%  1.73 1.68   83%    2   TTTT          2.1  3.1  no
deep-primary 3BR+MMD open t200      200 |       170.5   85   10%  1.53   29% |     16/12       141.5  71    9%  1.96 1.60   71%    3   TTTT          3.9  2.0  no
deep-primary 3BR+MMD closed t200    200 |       197.5   99   13%  1.43   33% |     60/56       156.9  78    8%  1.96 1.31   50%    3   TTTT          1.8  4.6  no
deep-primary 3BR noMMD open t180    180 |       179.1   99   12%  1.98   33% |      6/6        136.5  76    8%  1.75 1.50   83%    2   TTTT          1.4  1.3  no
deep-primary 4BR+MMD open t240      240 |       165.5   69    8%  1.85   50% |     18/18       165.5  69    8%  1.85 2.07   50%    3   TTTT          4.4  4.9  YES
4BR closed t240 (every site)            |  refused by the L: the request is over capacity and carries FLEX, which the band does not combine with
```

What the numbers say:

- **Correctness.** Of 384 L candidates generated across the matrix, 354 solved, and every solved one passed C1–C21 and C22 — 100 % valid/solved (the 50 % solve rate on the 6 m arm is the unforced twins and the hard tier meeting the solver, as for one-wing candidates). Every seam is real: 2–4 realized doors cross it per plan, no window and no exterior wall on it, every room inside its wing.
- **The advantage the L was expected to give, it gives.** Two-sided habitable rooms 67–83 % on open plans against 29–50 % for the one-wing plan of the same brief; circulation share 5–9 % against 10–13 % (the hall is the seam's length, not the house's).
- **The cost.** Delivered area 71–98 % of the effective target against 85–101 % — the L's primary is a bar of `column + hall` (4.2–6.5 m) and the arm is what the adapter offered; both are honest, and under the existing area-proximity rule the L becomes the primary only where the one-wing partis fail (deep-primary 4BR: 165.5 m² L against a refusal). Private-room proportions are slightly worse (max long/short 1.7–2.4 vs 1.4–2.1): a 5 m arm makes 4.8 × 2.6–3.0 m bedrooms. Neither is tuned here — ranking is the next review's question, as scoped.
- **Refusals name what bound.** Open-plan 3BR on a 5 m × 9.5 m arm beside a 16 m primary: the column beside the hall must fill 9.5 m and the band must hold LDK in `column + hall` width or the primary's 6.5 m of free depth — neither is possible, and the deep-primary site (20 m) shows the same programme planning once the depth exists. A 6 m arm is too wide for a lone bedroom or safe-room row within the maxima (row sharing, again). 2BR has too few rooms for `column + arm` on the long arm. A request over capacity carries FLEX, which the band does not combine with (the front band's rule).
- **Runtime.** Generation plus solving every L candidate: 0.9–4.9 s per brief; the pipeline run 1.1–5.4 s (one-wing only, before: 1.6–3.3 s on the same sites).

### Where the L should help, checked

- **Public zone facing the garden**: the `front_arm` site puts the arm at the street and the band at the rear — planned for 2BR open, 3BR closed, 3BR noMMD open; the hall fronts the street and takes the entrance (priority HALL), the LDK band faces the garden.
- **Bedroom/private wing**: every L plan's arm holds only bedroom-tier rooms and their bathrooms (asserted by test); the safe room joins them in the "wet cluster beside the hall" allocation.
- **3–4 BR family house**: 3BR plans on every site (closed) and on the deep primary (open); 4BR open plans on the deep primary and is the pipeline's primary there.

## Tests

`tests/vertical_slice/test_l_parti.py` (19): seam geometry classification and refusals; the pair gate; real L plans on two sites (two wings, one declared seam per arm row, `+` in the family signature, every check incl. C22, realized doors across the seam for every arm room, no exterior/window semantics on the seam, crook as garden, private arm, whole open group, closed-plan kitchen beside the hall with its own door, overflow named); refusals name the binding wing; a single candidate never reaches the parti; without a target the L is after every other candidate; the B_l_shape baseline primary unchanged (`SPINE_DOUBLE_LOADED`, 161.245 m², one wing). C22 negatives on the spike's F2: undeclared abutment, partial seam (hall longer than the arm), window on the seam, two buildings that only touch; C22 absent on the frozen slice. `test_concept_generator::test_a_second_wing_is_considered_…` rewritten to the new contract (planned, or declined with the parti's own reason — never the blanket refusal).

## Regression

- **432-context demo snapshot**: 404/404 planned payloads byte-identical against branch `011` (above).
- **Backend suite**: 1095 passed, 9 xfailed, 2 failed — the same two that fail on `main` @ `2a00c0f` (`test_the_design_request_offers_the_other_plans_it_proved`; `test_generator_produces_a_bounded_candidate_set[3BR]`), untouched. `BASELINE_CHECK_COUNT` stays 18: C22 is not emitted for a one-wing fixture.
- **Frontend**: 157 passed (no frontend change on this branch).
- Frozen baseline, the `*_samples` reports, `test_general_pipeline` (including the B_l_shape one-wing primary), `test_demo_p0`, `test_strip_rooms`, `test_hub_guard`: unchanged.

## Left for the next review (not done here, by scope)

Ranking: the L loses on area proximity while winning on exposure and circulation — the shapes report's "group by massing family" (§3.3). Row sharing in the arm (the 6 m arm). Classifying the crook as terrace/court. The `_wall_length_u` inversion in `windows.py` (pre-existing). A hall along the street axis (arm north/south).
