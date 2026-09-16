# Room Proportions and Decomposition — investigation record

**Date**: 2026-09-16 · **State measured**: `main` @ `518e133`, frozen in a detached worktree (the log copy and `.env` copied in; nothing in the repo changed) · **Scope**: investigation only, no implementation.

**Corpus**: the 432 distinct failure-log contexts through the real service (`generate_demo_design`, the person's outline plus the engine's survey; 404 planned, 28 refused), every plan the pipeline realized captured with its concept candidate; plus the five L sites × six programmes of the L parti report. Aspect = long/short of the **net** rectangle, as validation C20 measures it (the Stage-0 census figures were centerline; do not compare them 1:1). Every room is tagged with its place in the parti, read off the fixture tree: *band* (subtree hanging off the root→HALL path through an H cut), *column* (through a V cut), *arm* (the L wing without a hall); and its row kind: *lone full-width row*, *pair* (V-split row: host / dependent), *side-by-side* or *stacked* band member.

Two replay experiments run the delivered spine primaries back through the planner's own functions (`_seam_options`, `_columns_at_seam`, `_dependent_pairings`, `_pair_with_open_member`, `_access_intact`, `_row_depths`) at the same footprint, to ask whether a different seam or a legal row pairing gives better rooms. They are planner-level (shape and area maxima hold through `_row_depths`); Geometry Core was not re-run on them.

---

## 0. Verdict up front

1. **Yes — proportions can be improved by decomposition, at the same footprint and area, without shrinking rooms or relaxing maxima.** The pairing the tier-2 machinery already knows (a lone room takes the master's corridor-facing slot beside the ensuite; the master goes full-width) applied as a *quality* move rather than a *shape-refusal repair* brings the worst bedroom-class aspect of a plan from a median 1.98 to 1.56 in 132 of the 350 replayed spine primaries (38 %); 70 plans come under 1.6, 46 under 1.5. At the delivered seam alone (no seam search) 100 plans improve and 37 come under 1.6. The typical gain is a 5.0 × 2.7 m bedroom or a 5.0 × 2.4 m safe room becoming 2.8–2.9 × 3.4–3.8 m, and the 2.15 × 6.3 m ensuite strip beside it becoming ~2.3 × 2.9 m.
2. **The ceiling is topology, not sizing.** A shared row in every parti (spine columns, front-band rear columns, L arm) has exactly one corridor-facing slot; the far slot can only hold a dependent (an ensuite) or an open-plan neighbour. Every programme in the log has at most **one** ensuite, so at most one lone row per programme can ever be paired; 149 of the 432 briefs (one wet room) have none. Of the 741 poorly shaped lone bedroom-class rooms in the primaries, 251 (34 %) sit in a column that has a host slot at all. Beyond that one slot the fix is a second dependent (a shared bath made an ensuite — `programme_variants`, only for flexible wet rooms, none in this log) or a corridor that turns (front band, hub foot band) — not row sharing.
3. **The fallback ladder, not the normal path, produces most of the elongation.** Bedroom-class aspect: normal plans median 1.32 (27 % over 1.6); shrunk 1.67 (57 %); shrunk + hard 1.84 (72 %); solver-cut twins 1.86 (73 %); tier-2 1.90 (82 %). Deficit distribution shrinks a row's *depth* inside a column whose *width* is fixed by the seam — it trades area for shape by construction. 300 of 404 primaries are shrunk.
4. **Seam position is a minor lever.** At the delivered footprint only 1 seam is feasible at the median (p90 3, max 7 of ~18 searched); the first feasible seam reproduces the delivered shapes in 290/350 plans. Re-selecting among feasible seams by shape improves the worst bedroom-class room by a median 0.12 in 96 plans. Only 62 of 571 wide lone bedroom-class rooms have a deep lone room across the hall — both columns are wide-and-shallow because the *footprint* is, for the row count.
5. **L**: the arm's problem is proportions, not refusals. Secondary bedrooms alone across the 4.8 m net arm sit at 1.78–1.85 (416 of 426 arm bedrooms are lone wide rows), safe rooms at 1.96–2.0, shared baths at 3.0; across the 5.8 m arm 2.47 (hard tier). The same host-slot pairing brings 4.8 m arm plans from 1.68–1.85 to 1.33–1.48 and 5.8 m 2BR plans from 2.47 to 1.73 — and fixes exactly one lone row per arm, for the same reason. No L-specific rule is needed: `_plan_l` already routes rows through `_rows_for_width`.
6. **Runtime**: the planner is now the cost — `plan_layout` is 70 % of a brief's time at the median (85 % at p90); 34 % of its calls are tier-2 with the unbounded seam window, and the front band's tier-2 rear-seam search reached 76,870 `_plan_front_band_at` calls in one brief. A quality tier is cheap (5 ms median, 39 ms max per plan for *every* pairing at *every* seam) only if it keeps the bounded seam window and a pairing cap.

---

## 1. Measured distributions — 404 primaries (net aspect)

| role | n | p50 | p90 | p95 | max | > 1.4 | > 1.6 | > 1.8 | > 2.0 | within 10 % of hard max | wide / deep |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BEDROOM | 746 | 1.70 | 2.06 | 2.15 | 2.43 | 525 | 430 | 266 | 100 | 11 (1 %) | 614 / 132 |
| MASTER | 404 | 1.63 | 2.12 | 2.28 | 2.43 | 273 | 209 | 151 | 68 | 31 (8 %) | 192 / 212 |
| SAFE_ROOM | 246 | 1.73 | 2.21 | 2.29 | 2.38 | 186 | 160 | 113 | 74 | 20 (8 %) | 202 / 44 |
| BATHROOM | 659 | 2.14 | 2.95 | 2.97 | 3.00 | 492 | 435 | 388 | 354 | 187 (28 %) | 352 / 307 |
| TOILET | 103 | 2.96 | 3.46 | 3.48 | 3.50 | 92 | 80 | 77 | 71 | 40 (39 %) | 82 / 21 |
| KITCHEN | 404 | 2.64 | 2.95 | 2.98 | 3.00 | 375 | 360 | 334 | 294 | 184 (46 %) | 355 / 49 |
| LIVING | 404 | 1.60 | 2.33 | 2.39 | 2.48 | 253 | 204 | 145 | 96 | 54 (13 %) | 347 / 57 |
| DINING | 213 | 2.32 | 2.79 | 2.80 | 2.81 | 193 | 177 | 158 | 138 | 55 (26 %) | 185 / 28 |

No room exceeds its template aspect (C20 holds: 0 of 3,179). 342 of 404 primaries (85 %) have a bedroom-class room over 1.6; 163 (40 %) over 2.0. All shown plans (primary + alternatives, 770 plans) and all 1,273 realized-valid candidates the pipeline touched have the same medians within 0.05 — the shapes are a property of the generator, not of the selection. No hub primary exists in this corpus.

**Share of rooms at or under each aspect** (the knee search):

| role | ≤1.2 | ≤1.3 | ≤1.4 | ≤1.5 | ≤1.6 | ≤1.7 | ≤1.8 | ≤2.0 | ≤2.2 | ≤2.5 |
|---|---|---|---|---|---|---|---|---|---|---|
| BEDROOM | 14 | 23 | 30 | 37 | 42 | 50 | 64 | 87 | 97 | 100 |
| MASTER | 16 | 24 | 32 | 39 | 48 | 56 | 63 | 83 | 92 | 100 |
| SAFE_ROOM | 13 | 18 | 24 | 33 | 35 | 48 | 54 | 70 | 90 | 100 |
| BATHROOM | 15 | 21 | 25 | 31 | 34 | 38 | 41 | 46 | 52 | 62 |
| TOILET | 4 | 6 | 11 | 18 | 22 | 24 | 25 | 31 | 36 | 42 |
| KITCHEN | 4 | 5 | 7 | 8 | 11 | 14 | 17 | 27 | 36 | 45 |
| LIVING | 21 | 28 | 37 | 43 | 50 | 58 | 64 | 76 | 86 | 100 |
| DINING | 3 | 7 | 9 | 13 | 17 | 19 | 26 | 35 | 45 | 61 |

Bedroom-class rooms are **bimodal**: a well-shaped mode up to ~1.5 (bedrooms with short side ≥ 3.0 m: n = 251, median 1.28, p90 1.70 — the census range) and a strip mode at 1.7–2.1 (short side < 3.0 m: n = 495, median 1.81). The trough between them is the 1.5–1.6 bin (+5 % of rooms, against +7–9 % per bin below and +8–14 % above). The strip mode is the floor-bound row: a 4.8–5.6 m column with the bedroom at its 2.6 m short side (5.0 × 2.6 = 1.92), the safe room at its 2.4 m (5.0 × 2.4 = 2.08).

**By plan class** (bedroom-class rooms in primaries):

| class | plans | rooms | p50 | p90 | > 1.6 | lone wide row at its shape floor |
|---|---|---|---|---|---|---|
| normal (neither shrunk nor hard) | 59 | 226 | 1.32 | 1.85 | 27 % | 31 % |
| shrunk | 167 | 558 | 1.67 | 1.98 | 57 % | 36 % |
| shrunk + over-preferred | 133 | 391 | 1.84 | 2.27 | 72 % | 34 % |
| over-preferred only | 45 | 221 | 1.74 | 2.19 | 64 % | 46 % |
| tier-2 (22) | 22 | 102 | 1.90 | 2.29 | 82 % | 51 % |
| solver-cut twin (50) | 50 | 263 | 1.86 | 2.27 | 73 % | 59 % |

By programme size: 1 BR median 1.97 (77 % over 1.6 — a lone master across a wide column), 2–3 BR 1.58 (48–49 %), 4–6 BR 1.68–1.71 (59–65 %). Front band vs spine: 1.74 (64 %) vs 1.66 (55 %).

## 2. Root causes, per role (rooms over 1.6 in primaries)

| role | over 1.6 | cause (count) |
|---|---|---|
| BEDROOM | 430 | lone full-width row in a wide column, depth at its shape floor **239**; same, depth set by area **139**; lone row deep (narrow column + surplus) 49; pair host 3 |
| MASTER | 209 | pair host narrowed by the ensuite, deep **69**; lone row deep 54; pair host wide 52; lone wide at floor 21; lone wide by area 13 |
| SAFE_ROOM | 160 | lone full-width row at its 2.4 m floor **159**; deep 1 |
| BATHROOM | 435 | pair dependent stood on end (row depth = the master's) **145**; lone wide by area **145**; lone wide at its 1.6 m floor **136**; deep 8 |
| TOILET | 80 | lone wide at floor 52; lone wide by area 21; pair host narrowed 7 |
| KITCHEN | 360 | lone wide by area **201**; lone wide at floor 123; band width-share (front band) 33 |
| LIVING | 204 | lone wide by area **162**; at floor 20; band shallow 14; deep 8 |
| DINING | 177 | lone wide by area **157**; band width-share 18 |

What the columns look like: the wide lone bedrooms over 1.5 (n = 418) sit in columns of net width **5.05 m** (p90 5.65) at **2.70 m** deep; a 1.5-aspect room of that depth is 4.05 m wide — the column is ~1.0 m too wide for the room, and it holds 3–6 rows (mode 4). Masters: 5.85 m vs 4.65 m; safe rooms: 4.75 m vs 3.60 m. The width is the *column's*, set by the seam from area share and the other column's floors; the depth is the row's, set by the floor (deficit) or the area quotient. A lone room can never be narrower than its column — that is the whole mechanism.

Attribution the brief asked for:
- **Full-width (lone) rows**: the dominant cause in every role — 1,790 wide lone rooms over 1.6 in the primaries.
- **Column width**: the lone room inherits it; see the 1.0–1.2 m excess above.
- **Seam position**: rarely the cause — 62/571 wide lone bedroom-class rooms have a deep lone room across the hall; seam re-selection helps 96/350 plans by a median 0.12 (§6).
- **Single-room rows** deepened by surplus (the "column narrow" case): 49 bedrooms, 54 masters, 8 baths — the narrow column of a double-loaded split, or a 1 BR master alone.
- **Arm width in the L**: §7 — 416/426 arm bedrooms are lone wide rows at 1.78–1.85 (4.8 m) or 2.47 (5.8 m).
- **Wet-room adjacency**: the planner enforces no adjacency; the only wet coupling is the ensuite pairing, and it produces the 145 dependents stood on end (2.15 × 6.3 m) and the 69 masters narrowed to 3.45 m: the pair row's depth is the *combined* area over the column width, so the master's row is deeper than the master wants and the ensuite runs its full length. A separate mechanism (the dependent slot as a sub-row of its own, or an ensuite + WC stacked in the slot) — not covered by row sharing.

## 3. Preferred aspect per role (a target, never a gate)

Chosen at the knee of each distribution against what the role's shape means, not at round numbers:

| role | hard (unchanged) | **preferred** | why here |
|---|---|---|---|
| BEDROOM | 2.5 | **1.5** | trough between the two modes (§1); rooms with short side ≥ 3.0 m sit at median 1.28, p90 1.70; census 1.0–1.35 |
| MASTER | 2.5 | **1.5** | same bimodality (39 % ≤ 1.5, then the 1.7–2.0 mass); short ≥ 3.2 m: median 1.32 |
| SAFE_ROOM | 2.5 | **1.5** | it is one of the bedrooms (census); short ≥ 2.8 m: median 1.10; at the regulated 2.4 m short side a 10.5 m² room is 1.82 by arithmetic, so the target implies short side ≥ ~2.7 m, which is the pairing's effect |
| LIVING | 2.5 | **1.6** | 50 % ≤ 1.6; short ≥ 3.6 m: median 1.47; a 4 × 6.4 m room |
| DINING | 3.0 | **1.8** | a 3 × 5.4 m room; as an open-plan zone up to 2.2 is a table bay, not a strip |
| KITCHEN | 3.0 | **2.0**, galley-exempt | a closed kitchen 2.7–3.0 m wide is a galley up to 2.5 legitimately (short ≥ 2.7 m); an open-plan kitchen zone is a counter along one edge of the volume and should carry no aspect penalty at all |
| BATHROOM | 3.0 | **2.0** | 1.8 × 3.0–3.6 m (5.4–6.5 m²) is a normal bathroom at 1.7–2.0; short ≥ 1.8 m: median 1.70 |
| TOILET | 3.5 | **2.5** | 1.2 × 2.4–3.0 m is 2.0–2.5; the 1.25 × 4.3 m rows at 3.4 are the strips |

These would flag, in the primaries today: 63 % of bedrooms, 61 % of masters, 67 % of safe rooms, 54 % of bathrooms, 50 % of living rooms, 74 % of dining rooms — too many to "repair" and exactly why the preferred aspect must be a *quality target for a search tier*, not a refusal.

## 4. Repartition opportunities — what a shared row can legally hold

A shared row is a V-split beside the corridor: **one member touches the hall, the other touches only the exterior, its partner and the rows above and below**. `_access_intact` encodes this. Applying it to the combinations asked about:

| combination in one row | access | wet semantics | open plan | safe room | verdict |
|---|---|---|---|---|---|
| bedroom + its ensuite | host near, ensuite far | unchanged | — | — | exists (`_rows_of`) |
| **lone room X + ensuite, host in the adjacent full-width row** (`[MASTER, ENS] + [X]` → `[MASTER] + [X, ENS]`) | X near, ensuite reaches its host across the row edge | unchanged | — | X may be the safe room (near slot, RC walls fine) | **legal — exists as `_dependent_pairings`, used only on shape refusal** |
| bedroom + shared bathroom | the bathroom needs the hall | — | — | — | **illegal** as is; legal only if the bathroom becomes that bedroom's ensuite = `programme_variants` (flexible shared bath only; 0 briefs in this log) |
| two bedrooms | both need the hall | — | — | — | **illegal** in a column; only where the corridor turns (front band, hub foot band) |
| bedroom + WC / service room | WC needs the hall | — | — | — | **illegal**; a WC beside the *ensuite* (the WC takes the host slot) is the existing `_share_wc_row` |
| kitchen + dining, open plan | wall-less, either side | — | open chain kept (`open_chain` neighbours only) | — | exists (`_pair_with_open_member`); in the replay the DINING pairing "fixed" 26 plans — by shortening the public column so the seam could narrow the private one |
| kitchen + dining, closed | dining needs a door | — | — | — | illegal (no door-through-kitchen in the model) |
| safe room in the far slot | needs the hall | — | — | RC on all sides regardless | illegal |

So within the row vocabulary the generic opportunity is one: **`[host, ensuite] + [lone] → [host] + [lone, ensuite]`**, with the lone room being any corridor-served room (bedroom, safe room, shared bath, WC, closed kitchen). Its capacity is the number of ensuites — one per programme in this log. Everything else the brief lists (two bedrooms, bedroom + bathroom, service beside another room) needs either a wet-semantics change or a corridor turn.

Static limit over the 432 briefs: 1,770 lone private/service rows; at most 283 (16 %) can take a host slot; 149 briefs have no ensuite at all.

## 5. Can the tier-2 machinery be generalised? Yes — the generators are reusable as they stand; the trigger, the acceptance and the gate are what change

`_repartition_rows` today: for each lone row whose `room_depth_band_m(...) is None` (a strip or oversized — a hard refusal), take the **first** legal candidate from `_pair_with_open_member` + `_dependent_pairings` (checked by `_access_intact` after `_daylight_order`/`_orient_row`), greedily. It runs only when the normal attempt at a (strategy, proportion) **failed** with a shape reason (`_FallbackAsks.shape`, in `_build`; the same ladder in `l_concepts`), and its candidates are ordered after every tier-1 candidate and twin.

For a quality tier:
- **Reusable unchanged**: `_dependent_pairings`, `_pair_with_open_member`, `_access_intact`, the `finished()` re-ordering, `Repartition` (open chain, hall public, never-shared FLEX), `_columns_at_seam`/`_row_depths` (floors, ceilings, shape verification), `_forced_chain`'s `open_block`, and the `_rows_for_width(fallback=...)` hook that `plan_layout`, `_plan_front_band_at` and `_plan_l` all pass through.
- **Changes**: (a) trigger — a lone row's *planned* aspect at the column width (`width / max(area / width, floor)`) above the role's preferred, not band-is-None; (b) selection — try each legal candidate (p50 2, p90 7, max 10 per plan) and keep the best by planned shape, not the first; (c) gate — run when the normal attempt **succeeded** but is poor, as an *additional* candidate, never replacing it; (d) `already_found` dedupe and a per-class budget as `_build` already has for the fallback classes.
- **Not reusable**: the `limit=None` seam window — it is the cost driver (§9). The quality tier should search the normal nine seams.

## 6. Expected improvement — rectangular plans (350 spine primaries replayed at their own footprint)

| experiment | result |
|---|---|
| A. seam re-selection (normal rows, every feasible seam, choose by shape) | feasible seams p50 1 / p90 3 / max 7 of ~18 searched; first feasible = delivered in 290/350; worst bedroom-class aspect improves by > 0.1 in **96** plans (median +0.12); 26 of the 290 poor plans reach ≤ 1.6. Cost 3 ms per plan. |
| B. legal row pairing for poorly shaped lone rooms (every legal pairing, every seam) | 306/350 plans have a bedroom-class room > 1.5; **218** have ≥ 1 legal pairing; **132** improve by > 0.1 (median +0.34; worst room p50 1.98 → 1.56); **70** reach ≤ 1.6, **46** ≤ 1.5. At the delivered seam alone: 100 improve, 37 reach ≤ 1.6. Who took the host slot: safe room 47, dining (open pair) 26, shared bath 23, living 19, bedroom 17. Cost p50 5 ms, p90 16 ms, max 39 ms per plan (unbounded seams). |
| the limit | 270 poor plans have a poorly shaped **lone bedroom-class** row; only **81** of them have a legal pairing for a bedroom-class room (the other 170 need the semantics variant or a corridor turn). 88 poor plans have no legal pairing at all. |

Example, brief 10.9 × 8.95 m, 1 BR + 2 wet: delivered MASTER 3.1 × 6.3 (2.03) beside BATH_1 2.15 × 6.3 (2.93), BATH_2 5.35 × 2.25 (2.38); with `[MASTER] + [BATH_2, BATH_1]` at seam 4.6: MASTER 1.08, both baths ~1.2 — same footprint, same area.

Also measured on the shown plans: in 96 of the 261 briefs with alternatives, an alternative is clearly better shaped than the primary at no median area cost (p90 +14.6 % further from the request) — the ranking question (deferred by scope) is real but secondary to generation.

## 7. L parti (5 sites × 6 programmes; wet rooms assumed 2 for 2–3 BR, 3 for 4 BR)

- **Valid L plans** in 19 of 30 briefs (410 candidates, 384 solved, 384 valid — the unsolved are forced trees on the 6 m arm and hard-tier trees on the deep primary; every solved one passed C1–C22). Refusals: 3 BR open on the 5 m arms (the column beside the hall cannot fill the 9.5 m seam within hard maxima by 5 cm), 4 BR open on the 5 m arms (floors 9.50 vs 9.50 — a grid-exact miss), long-arm 4 BR open (ceilings again), 4 BR closed everywhere (FLEX). **None is a lone-room shape refusal**; the earlier "6 m arm too wide for a lone bedroom" now plans, at the hard tier, with 5.8 × 2.35 m rooms (2.47).
- **Arm rooms across all valid L plans**: BEDROOM n = 426, median 1.81, 416 lone wide rows; SAFE_ROOM 109, median 1.96, all lone wide; BATHROOM 473, median 2.50 (360 ensuites stood on end beside the master, 113 lone shared baths at 3.0); MASTER 360, median 1.29 (paired, fine). Column beside the hall: bedrooms 1.55, safe rooms 1.79, baths 2.25. Band: kitchen 1.31, living 1.16, dining 1.78 — much better than the one-wing primaries for the same briefs (kitchen 2.81, living 1.42, dining 2.34), while arm bedrooms are worse (1.78 vs 1.60) and baths worse (2.38 vs 1.65).
- **Lone-row arithmetic at the arm's net width**: 4.8 m — bedroom at its floor is 1.85, safe room 2.0, master 1.6, bath 3.0, WC impossible under preferred; 5.8 m — bedroom has no preferred band (hard: 2.23), safe room 2.42 (band [2.40, 2.41]), WC impossible even hard. Any arm wider than ~4.2 m makes a lone secondary bedroom exceed 1.5.
- **Row sharing in the arm** (82 distinct arm row-sets replayed through `_row_depths`): 4.8 m arm — worst bedroom-class 1.68–1.85 → **1.33–1.48** where the lone room (shared bath, safe room, bedroom) takes the master's slot; ensuite 2.4–2.8 → 1.2–1.9; where the arm has two lone rows (3 BR + safe room, or BEDROOM_1 + BEDROOM_2) one is fixed and the other stays at 1.78. 5.8 m arm — 2 BR 2.47 → 1.73 (master full-width 5.8 × 3.35); 3 BR: one lone row fixed to 1.0–1.2, the others stay 2.47. Proportions **improve** and nothing gets worse than the delivered shape in any replayed set; the unpaired rows are unchanged.
- **Public/private semantics**: no effect on legality. The arm's rows face the seam exactly as column rows face the hall; the closed-plan kitchen in the column is a hall-served room like any other; the open band is never split. The generic quality tier reaches the arm through the `_rows_for_width(fallback=...)` call `_plan_l` already makes — one argument, no L-specific patch. What the L *would* need separately is a second pairing slot for 3 BR + safe-room arms (a semantics variant, or two-room arm rows served by a spur — new vocabulary).

## 8. Room-shape quality metric (proposal, not wired to ranking)

Per room, a penalty in [0, 1], the maximum of two terms, each **zero inside the preferred range and rising quadratically to 1 at the hard limit**:
- aspect term: 0 for `a ≤ preferred(role)`; `((a − preferred) / (hard − preferred))²` above;
- short-side (usability) term: 0 for `short ≥ comfortable(role)` (bedroom 3.0, master 3.2, safe room 2.8, living 3.6, dining 3.0, kitchen 2.7, bath 1.8, WC 1.2), rising to 1 at the template's `min_short_side_m`;
- exemptions: a closed kitchen with short side ≥ 2.7 m carries no aspect penalty up to 2.5 (a galley); an **open-plan** kitchen or dining zone carries none (it is an edge of one volume — the Stage-0 finding that zones of an open plan are not room shapes);
- area term (already exists as `over_preferred_ratio`): 0 inside [target, preferred max], rising to 1 at the hard max; and below target toward the minimum for shrunk rooms.

Roll-up to a plan: weights bedroom-class and living 1.0, dining 0.7, kitchen and bathroom 0.5, WC 0.3; plan score = 0.6 × worst weighted room + 0.4 × weighted mean — the worst room is what a person sees first, the mean stops one bad WC from dominating. Measured on today's primaries the score is 0.76 at the median (0 = every room inside its preferred shape); 3 of 404 primaries score 0. Recommended use in order: (1) per-room metadata on the contract beside `over_preferred_ratio`; (2) the acceptance test of the quality tier (a candidate is offered only if its planned score beats the normal candidate's by a margin); (3) later, the ranking input — with the same two-level policy the area maxima use (signal / notice), not a refusal.

## 9. Search cost and a bounded policy

**Where the time goes now** (432 briefs, 2,285 s CPU, per brief p50 2.6 s, p90 12.8 s, max 24 s): `plan_layout` is 70 % of a brief at the median and 85 % at p90 — p50 1,950 calls per brief, p90 8,800, max 14,966, at ~1 ms each; `_row_depths` p50 27,800 calls. **34 % of `plan_layout` calls are tier-2** (`limit=None` seams); the front band's tier-2 rear-seam search is 94 % of all `_plan_front_band_at` calls (76,870 in one brief). Solves: p50 13 per brief, max 405. Candidates per outline p50 36; outlines per brief p50 4; realizations per brief p50 3, max 8.

**Quality-tier cost, measured in the replay**: every legal pairing (p50 2, p90 7, max 10) at every seam (p50 40, max 234 `_columns_at_seam` calls) is 5 ms median, 16 ms p90, 39 ms max per plan. Bounded to the normal nine seams and three pairings that is ~3–10 ms per poor normal candidate. With ≤ 3 normal candidates per strategy × 5 strategies per outline (front band included) and 4 outlines, the worst case is ~0.2–0.6 s per brief (+8–23 % of the median brief; +2–5 % at p90) if *every* normal candidate is poor and pairable; the expected case is a third of that (218/350 have a pairing). Solver cost is zero as long as quality candidates are ordered after the normal ones and realized only within the existing `ALTERNATIVE_ATTEMPT_LIMIT`; one promoted candidate costs one solve (~150 ms).

**Bounded policy**:
1. Trigger only where a **normal** candidate was found at (strategy, proportion) *and* its planned worst bedroom-class aspect exceeds the preferred *and* `_dependent_pairings`/`_pair_with_open_member` yield ≥ 1 legal pairing for a poorly shaped lone row. No trigger on shrunk/hard/tier-2 attempts in phase 1 (they are already fallbacks; the ladder would multiply).
2. One extra `plan_layout(fallback=quality)` per trigger: **nine seams** (`_MAX_SEAM_OPTIONS`, not `None`), ≤ 3 pairings ordered bedroom-class dependents first, open-chain pairs second; keep the best by planned shape; `already_found` dedupe.
3. Budget: ≤ 1 quality candidate per (strategy, proportion), ≤ `_MAX_PROPORTIONS_PER_STRATEGY` per strategy (the existing per-class budget pattern in `_build`).
4. Acceptance: the quality candidate's planned worst bedroom-class aspect improves by ≥ 0.1 and no room leaves its preferred band that was inside it; otherwise drop it.
5. Ordering: after every normal candidate and twin, with tier 2 — primaries byte-identical by construction; the effect is measured on alternatives and on the 431-context snapshot before any ranking decision.
6. Not to repeat: no `limit=None` seam window, no hard-tier pass inside the quality tier, no re-run when the normal attempt already failed (that is tier 2's job).

## 10. Smallest implementation phase

1. `RoomTemplate.preferred_aspect_ratio` (values of §3) — no validator reads it; `_zone_spec` unchanged.
2. A planned-shape reader on `LayoutPlan` / the L plan: worst bedroom-class planned aspect from rows, widths and depths (the replay's `aspects_of`).
3. `_quality_repartition_rows(rows, net_width, areas, options, corridor_on_east)`: the tier-2 generators + `_access_intact`, trigger = planned aspect > preferred, returns up to 3 candidates best-first — beside `_repartition_rows`, not replacing it; `_rows_for_width` takes it through the same `fallback` hook (the `Repartition` carries a `quality=True` flag and the areas).
4. In `_build`: after a normal `found`, the bounded extra `plan_layout` of §9; `ConceptCandidate.requality` flag and rationale marker; ordered with tier 2 in `generate_concepts`. `l_concepts`: pass the same fallback in its ladder's first rung (one line).
5. Contract: per-room aspect vs preferred as metadata (like `over_preferred_ratio`); nothing in `validation.warnings`.
6. Tests: the 10.9 × 8.95 brief above (master 2.03 → ~1.1 at the same footprint); a 4.8 m L arm (BEDROOM_1 1.78 → ≤ 1.5); the L closed 3 BR arm keeps one lone row unchanged; 431-context snapshot: 404/404 primaries byte-identical; alternatives report the count of requality plans shown; runtime p50/p90 within +10 %.

Deliberately **not** in phase 1: ranking changes; the semantics variant for non-flexible shared baths; the ensuite-slot sub-row (the 145 stood-on-end ensuites and 69 narrowed masters); front-band band-share shapes (kitchen/dining strips in the band); the hub.

---

## Appendix — method and caveats

- Scripts (session scratchpad, not committed): `measure_shapes.py` (sweep with `_realize` capture and planner call counters), `shape_common.py` (tree classifier), `analyze_shapes.py`, `measure_l.py` + `analyze_l.py` (L matrix), `repartition_experiment.py` + `summarize_rep.py` (seam and pairing replay of spine primaries), `l_pairing_experiment.py` (arm replay).
- The replays use the delivered plan's shrunk/hard flags for `_row_depths` and rebuild the programme variant from the plan's zones (FLEX added where present); 54 front-band primaries were not replayed (a different sizing path; its rear columns would use the same pairing).
- Planned aspects in the replay are pre-solver (net widths from `_row_widths`, depths from `_row_depths`); the realized rectangles differ by the wall insets only (≤ 0.1 m).
- The L matrix's programmes assumed 2 wet rooms (2–3 BR) and 3 (4 BR); the L parti report did not state them, and one brief (long-arm 2 BR open) now plans where that report recorded a refusal.
- Stage-0 (2026-09-11) measured bedroom proportions at 1.26 on centerline rectangles of 85 plans before deficit distribution and the hard tier existed; today's 1.70 net median is mostly the fallback ladder's doing (§1, by plan class), not a like-for-like regression figure.
