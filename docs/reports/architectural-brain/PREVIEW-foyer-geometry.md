# Minimum foyer/hall geometry in the exact sizer — the front door's room is a room (#205, 2026-10-17)

Branch `feature/foyer-geometry`, on top of #204 (`b460a42`). One constraint group, `"foyer"`, in the
three exact oracles (`exact/milp_oracle.py` band `milp_heights` and spine `_spine_once`,
`exact/milp_cells.py`), applied to the single-row circulation cell in the street band — the cell
`doors.resolve_entrance` hands the front door to. `_skip={"foyer"}` reproduces the previous sizing
exactly (pinned per oracle in `tests/vertical_slice/test_foyer_geometry.py`); the production sizer
(`band_sizing`), the validators, the critic, the preference and the ranking are untouched;
`run_brain(sizer="production")` is byte-identical per parti (existing test).

Same harness as #204 (`PREVIEW-rank-then-size.md`): eight real briefs, four configurations, the plan
the product shows first, drawn by `DemoPlan`. Data `data/preview-foyer-geometry/` (metrics, designs,
`run.log`), figures `figures/preview-foyer-geometry/<brief>__<config>.png` (`…-bydev.png` is the
lowest-deviation plan, kept for comparison). The placement-level before/after (every street-fronting
exact placement the budget sized, realized or failed, with the validator code) was measured by the
same `run_brain` calls instrumented at `realize_cells`, once with `_skip={"foyer"}` (before) and
once without (after).

## Gate verdict: **STOP**

| criterion | result |
|---|---|
| ≥ 2 of the street-fronting exact placements that failed C25/C28/C26 now realize and pass the unchanged validators | **met**: 2 (B06 `TWO_HALL+FOYER`, band, H rung 0.5 — C25 4.33 m pocket beyond the door → realized, 2.15 × 3.20 m foyer, 3.8 % deviation). Every "pocket beyond the entrance door" failure is gone (B02 4.08 m, B06 4.33 m, B08 4.15 m); what remains are the other shapes (below). |
| no brief loses: every brief's shown-first plan rank key no worse than #204's | **FAILED**: B08 (band 3 → 5 % deviation, all families 1 → 5 %) and B11 (all families 17 → 23 %) rank below #204's plans. B06 (all) and B11 (band) and B02 (all) rank better; the other 11 brief/configuration cells are identical. |
| request time max ≤ 31.4 s | **met**: 31.1 s (B20 all families). |

The gate says STOP, so this stops here: no second mechanism, no retuning of the constants to buy B08
back. The branch is delivered as a measured, reversible change for the owner to weigh — what it
buys and what it costs are both in the tables below.

## What the group is

Constants in one place (`milp_oracle.py`, next to `SPINE_MIN_WIDTH_M`), the derivation in the
comment there; `milp_cells` imports them.

* **`FOYER_MIN_NET_M = 1.9`** — net width at the entrance wall AND net depth. Derived from the swing
  geometry C28 measures (`door_clearance.swing_envelope_m`, `_door_wall_defects`): a leaf sweeps a
  quarter-disc of its own width from its hinge; the arrival room holds the front door's leaf
  (1.0 m, swinging in) and the onward door's (0.9 m — between two circulation zones `doors._swing`
  hangs the door into the smaller, i.e. the foyer). With the onward door opposite, the two discs lie
  in series along the depth; on a side wall, side by side along the entrance wall; either way they
  touch without overlapping at exactly `DOOR_WIDTH_M[ENTRANCE_DOOR] + DOOR_WIDTH_M[ROOM_DOOR]`.
  Below that the envelopes overlap for some door position and C28 fails (#204's cells plans: a
  1.6 m-deep foyer). A test pins the constant to the two door widths.
* **`FOYER_MAX_DEPTH_TO_WIDTH = 1.5`** — the strip cap, one-sided: net depth ≤ 1.5 × net width.
  The measured strip (B08 1.50 × 3.05 m, B11 1.70 × 4.25) is a slot entered lengthwise through its
  narrow wall — C25's pocket runs along that depth (the onward door on the far wall: the pocket IS
  the band's depth, 4.15 m failed on B08) and C28's leaves stack along it. A hall that is wide along
  the street and shallow (B02: 6.15 × 2.35, entered through its long wall) is not that defect, and
  the zone's own `max_aspect_ratio` bounds it the other way. The value is production's own line
  between a lobby and a corridor — `concept_spec._COMPACT_HALL_ASPECT_MAX` /
  `quality_metrics.COMPACT_HALL_ASPECT_MAX` / `HUB_TEMPLATE`'s `max_aspect_ratio`, all 1.5 — over
  the brain's own foyer bound (2.5) and hall bound (3.0), which both admit the measured strips.
* **net depth > net width for the foyer proper** (role CIRCULATION, degree two). Derived from C26:
  `circulation_metrics._end_sides` counts dead ends at the two ends of the room's longer axis, and a
  foyer's doors are on its street wall and its far wall — wider than deep it has two dead ends of
  its own, plus the hall's accepted one is three, past `EXTREME_DEAD_END_COUNT`. A HALL (a hub with
  doors on several walls) is not held to this.
* **Where it applies**: the single-row circulation cell in row 0 of the oracle's own frame, the
  same convention the existing entrance rule and the SELECTION screen use. The spine itself is
  exempt (a declared corridor, `SPINE_MAX_ASPECT`); a circulation cell spanning rows in the cells
  family is a corridor (`HALL_MIN_WIDTH_M`). In the V orientation the oracle's row 0 is the west
  side, so the group — like the entrance rule before it — does not reach the cells that actually
  front the street there (4 fronting V placements before and after, all failing C26 as well).

Two facts found on the way, stated because the issue text assumed otherwise: the band oracle
`milp_heights` had **no** entrance rule at all (the "three door widths" lives only in `_spine_once`
and `milp_cells`), which is why every band-family foyer came out 1.50–1.70 m wide; and in the cells
family that 3.0 m gross rule, together with the foyer's 9 m² ceiling, forbids a street band deeper
than ~3.3 m — the H-orientation cells foyers were 3.00 × 2.80 for that reason, and the test fixture
for the cells oracle needs a 10 m² foyer to be feasible at all.

### C25 (item 3): covered by bounds 1+2, by measurement — for the pocket that is the foyer's own

Every C25 failure of the "unserved corridor **beyond** the entrance door" kind (the pocket along the
foyer's depth: B08 4.15 m, B02 4.08 m, B06 4.33 m ×2) is gone after: with net depth ≤ 1.5 × net width
and the foyer's own area ceiling, the depth is bounded (≤ 3.67 m net at the loosest rung) and the
realizer puts the entrance door at the foyer's span midpoint and the hall door at the shared edge's
midpoint, so the pocket is the band's depth plus a small offset. No width bound was added.

What remains under C25 is a different shape — "unserved corridor **beside** the entrance in ENTRY"
(`entrance_sequence._stray_pockets`, > 0.6 m): the HALL also fronts the street and wins the door
(HALL outranks CIRCULATION in `ENTRANCE_ZONE_PRIORITY`), leaving the foyer as a second street-fronting
circulation zone with a blind stub. B02 `HALL_SPINE+FOYER` (3 placements), B02 and B06 V
placements. That is the candidate's topology (a +FOYER parti whose hall reaches the street makes the
foyer pointless), not the foyer's shape; a screen on such candidates is a separate, small change.

## Results — the plan the product shows first

Room deviation from target % / circulation share % · arrival room · seconds for the whole request ·
sizer/family. `CIRC` = the parti's entry foyer (`ENTRY`, role CIRCULATION). Bold = changed from #204.

| brief | production | brain · production sizer | brain · exact, band | brain · exact, all families |
|---|---|---|---|---|
| B08 | 3.9 / 12.7 · HALL · 0.3 s | 9.0 / 9.0 · HALL · 1.7 s | **5.1 / 14.1** · CIRC · 30.3 s exact (was 3.1 / 12.5) | **5.1 / 14.1** · CIRC · 25.1 s exact (was 1.4 / 12.8 stack) |
| B20 | 12.5 / 12.0 · HALL · 0.2 s | 22.2 / 15.8 · CIRC · 7.3 s | 16.2 / 23.7 · HALL · 22.4 s exact | 22.2 / 15.8 · CIRC · 31.1 s (production) |
| B02 | 23.6 / 11.5 · HALL · 3.1 s | 7.4 / 10.3 · HALL · 0.5 s | 7.4 / 10.3 · HALL · 16.1 s (production) | 2.0 / **9.4** · HALL · 30.1 s exact/stack |
| B11 | 22.0 / 10.9 · HALL · 10.2 s | 28.4 / 19.4 · CIRC · 17.2 s | **22.9 / 13.8** · CIRC · 26.3 s exact (was 28.4 / 19.4 production) | **22.9 / 13.8** · CIRC · 30.9 s exact (was 16.6 / 14.3) |
| B16 | 14.4 / 10.1 · HALL · 10.0 s | 21.4 / 13.5 · LIVING · 26.3 s | 21.4 … · 30.2 s (production) | 21.4 … · 30.0 s (production) |
| B19 | 21.8 / 8.4 · LIVING · 0.8 s | 19.9 / 12.8 · LIVING · 20.3 s | 19.9 … · 26.9 s (production) | 19.9 … · 30.1 s (production) |
| B06 | 18.1 / 10.7 · HALL · 0.7 s | 8.6 / 12.1 · CIRC · 1.9 s | 8.6 / 12.1 · CIRC · 30.1 s (production) | **3.8 / 10.7** · CIRC · 30.7 s exact (was 8.6 / 12.1 production) |
| B09 | 9.8 / 8.9 · HALL · 1.2 s | 13.1 / 14.9 · CIRC · 5.2 s | 13.1 … · 30.0 s (production) | 13.1 … · 30.0 s (production) |
| **mean** | 15.8 / 10.7 · 3.3 s | 16.2 / 13.5 · 10.1 s | 14.3 / 14.4 · 26.5 s (max 30.3) | **13.8** / 13.1 · 29.8 s (max 31.1) |

#204: 15.8 / 16.2 / 14.8 / 13.2, max 31.4 s. The means move by 0.5 points either way; the gate is
per brief, and B08 pays.

### The rank keys, per brief and configuration (the "no brief loses" criterion)

Lower is better, lexicographic: (arrival ok, street ok, area in tolerance, room deviation %,
circulation %, −garden rooms, |gross − requested|, circulation m², worst wet aspect).

| brief | config | #204 | #205 | |
|---|---|---|---|---|
| B08 | band | (0,0,0,**3**,13,−3,1.1,16.3,1.04) PUBLIC_BAND+FOYER exact | (0,0,0,**5**,14,−3,0.6,18.3,1.04) PUBLIC_BAND+FOYER exact | **worse** |
| B08 | all | (0,0,0,**1**,13,−2,0.0,16.8,1.09) HALL_SPINE+FOYER exact/stack | (0,0,0,**5**,14,−3,0.6,18.3,1.04) PUBLIC_BAND+FOYER exact | **worse** |
| B20 | band | (0,0,0,16,24,…) PUBLIC_BAND exact | same | same |
| B20 | all | (0,0,0,22,16,…) SERVICE_CORE+FOYER production | same | same |
| B02 | band | (0,0,1,7,10,…) HALL_SPINE production | same | same |
| B02 | all | (0,0,1,2,**10**,−1,53.6,16.2,2.02) HALL_SPINE exact/stack | (0,0,1,2,**9**,−1,56.7,15.6,2.1) | better |
| B11 | band | (0,0,1,**28**,19,0,45.6,32.3,2.13) HALL_SPINE+FOYER production | (0,0,1,**23**,14,−1,33.6,25.1,2.1) HALL_SPINE+FOYER exact | better |
| B11 | all | (0,0,1,**17**,14,−1,27.9,26.8,2.1) HALL_SPINE+FOYER exact | (0,0,1,**23**,14,−1,33.6,25.1,2.1) HALL_SPINE+FOYER exact | **worse** |
| B16 | band, all | (1,1,0,21,13,…) SERVICE_CORE production | same | same |
| B19 | band, all | (1,1,0,20,13,…) BEDROOM_WING production | same | same |
| B06 | band | (0,0,1,9,12,…) BEDROOM_WING+FOYER production | same | same |
| B06 | all | (0,0,1,**9**,12,0,146.9,19.9,1.16) BEDROOM_WING+FOYER production | (0,0,1,**4**,11,−1,132.3,19.1,1.76) TWO_HALL+FOYER exact | better |
| B09 | band, all | (0,0,1,13,15,…) BEDROOM_WING+FOYER production | same | same |

### Street-fronting exact placements: realized vs failed on C25 / C26 / C28, before and after

Every placement the exact pipeline realized whose street band holds a circulation cell, over the
two exact configurations (`band` = band family only, `all` = band + spine + stack + cells). "before"
is `_skip={"foyer"}` on this branch; #204's own measurement of this kind was B08-only and
pre-dated its ordering change (8 fronting, 3 realized, 5 failed), so its five placements are not
individually recoverable — the re-measurement is the comparable baseline. n / realized / failed on
C25 / C26 / C28.

| brief | config | before | after | foyer (arrival room) net, before → after |
|---|---|---|---|---|
| B02 | band | 14 / 8 / 4 / 2 / 0 | 14 / 8 / 3 / 2 / 0 | ENTRY 1.50 × 3.35, 1.50 × 3.70 → 2.00 × 3.00, 2.15 × 3.00 |
| B02 | all | 17 / 7 / 3 / 7 / 0 | 16 / 7 / 2 / 6 / 0 | HALL 2.05 × 5.10 … → HALL 3.05 × 4.55 … |
| B06 | band | 5 / 2 / 3 / 0 / 0 | 7 / 5 / 2 / 0 / 0 | ENTRY 1.50 × 2.60, 1.65 × 2.60 → 1.90 × 2.60, 2.00 × 3.00, 2.15 × 3.20 |
| B06 | all | 5 / 2 / 3 / 0 / 0 | 6 / 4 / 2 / 0 / 0 | same |
| B08 | band | 9 / 8 / 1 / 0 / 0 | 7 / 7 / 0 / 0 / 0 | ENTRY 1.50 × 2.60, 1.50 × 3.05, 1.50 × 3.35 → 1.90 × 2.60, 1.90 × 2.80, 2.00 × 3.00 |
| B08 | all | 22 / 16 / 1 / 5 / 3 | 17 / 12 / 0 / 5 / 3 | same; the C26/C28 failures are the four V-orientation cells placements (2.40 × 1.80, out of the group's reach) and the cells family's dead ends |
| B11 | band, all | 1 / 1 / 0 / 0 / 0 | 1 / 1 / 0 / 0 / 0 | ENTRY 1.50 × 3.50 → 1.95 × 2.90 |
| B20 | band | 1 / 1 / 0 / 0 / 0 | 1 / 1 / 0 / 0 / 0 | HALL 3.40 × 8.15 (a hub hall, not held to the cap; unchanged) |
| B16, B19, B09, B20 all | — | 0 fronting | 0 fronting | every exact placement INFEASIBLE / UNKNOWN (the #200 limit), production shown |

Fate of the 16 distinct failing placements (brief / parti : family / orientation, rung) before:
B06 `TWO_HALL+FOYER:band H 0.5` (C25 4.33 m) → **realizes and passes** in both configurations;
B08 `HALL_SPINE+FOYER:band H 0.3` (C25 4.15 m) and B02 `HALL_SPINE+FOYER:band H 0.15` (C25 4.08 m)
→ the pocket is gone (the rung-0.15 solve now realizes a different, passing placement; the 0.3 solve
is never reached / the 0.15 one fails C3 on the hall's band instead); B02's three "beside the
entrance" C25s and the V-orientation ones remain; B08's four V cells placements remain (C26 + C28);
B02 `HALL_SPINE:spine` and `PUBLIC_BAND+FOYER` C26 (circulation ratio 25–26 %) remain — not a
foyer-shape matter.

### The foyer's net dimensions on the shown-first exact plans

| brief | #204 | #205 |
|---|---|---|
| B08 band | ENTRY 1.50 × 3.05 (4.6 m²) | ENTRY 2.00 × 3.00 (6.0 m²) |
| B08 all | ENTRY 1.50 × 3.05 (stack plan) | ENTRY 2.00 × 3.00 (6.0 m²) |
| B11 band | production 1.70 × 4.25 (7.2) | ENTRY 1.95 × 2.90 (5.7 m²) |
| B11 all | ENTRY 1.50 × 3.50 (5.2) | ENTRY 1.95 × 2.90 (5.7 m²) |
| B06 all | production 1.60 × 3.15 | ENTRY 2.00 × 3.00 (6.0 m²) |
| B02 all | HALL 6.15 × 2.35 | HALL 6.15 × 2.25 |
| B02 band, B20 band | HALL 4.90 × 3.00 / 3.40 × 8.15 | unchanged |

The strips that remain in the table are production-sizer plans (B06 band 1.60 × 3.15, B09
1.95 × 2.60, B20 all 1.50 × 3.40): the production sizer is untouched by design.

## What the drawings show

* **B08** (`B08__brain-exact-band.png`): the foyer is now a 2.00 × 3.00 m room with the front door
  on its 2 m wall and the hall door opposite; the price is the street band's other rooms — the
  foyer sits at +20 % of its 5 m² target, bedroom −17 %, master −10 % (before: −8 / −13 / −1).
  Measured directly (`_one` on the parti with the group on and off): any version of the group that
  makes the foyer ≥ 1.9 m wide costs this parti the same two points; the cap value (1.5 / 1.75 / 2.0)
  does not change it. The 1.4 % stack plan of #204 (`HALL_SPINE+FOYER`) no longer ranks first: its
  foyer, reshaped, loses the deviation lead to the band plan.
* **B06** (`B06__brain-exact-all.png`): the `TWO_HALL+FOYER` plan the group rescued — 3.8 % against
  production's 8.6 % — arrives in a 2.00 × 3.00 m foyer that opens into a 2.50 × 4.65 m hall; but
  the living room is a 5.00 × 9.20 m strip (46 m²) and the second corridor is 1.60 × 4.55 m. The
  key ranks it first; the drawing is a fact for the owner to weigh (the preference's proportion
  keys are room-deviation means, and the strip-shaped public room is the limit the frozen-six work
  already named).
* **B11**: 22.9 / 13.8 with a 1.95 × 2.90 foyer on both exact configurations — better than #204's
  band column (production, 28.4) and worse than its all-families column (16.6, whose foyer was
  1.50 × 3.50).
* **B02 / B20**: unchanged — their arrival rooms are HALLs the cap does not bind (B02's 6.15 × 2.25
  gallery hall; B20's 3.40 × 8.15 hub is wider than 1.9 and not CIRCULATION).

## Where this sits on the path to execution

This is row 1 of the #197 execution-plan table ("exact sizer: foyer geometry — the door's room is
a usable room; gate ≥ 2/5 pass, no brief loses"). The measurement moves that row to **decided:
STOP** — the door's room is now a room wherever the exact sizer wins (every exact-plan foyer is
≥ 1.9 m wide and deeper than wide, and the "pocket beyond the door" C25 failure is gone), but the
gate's second clause fails: B08 and B11 (all families) rank below #204's plans by two to six
points of room deviation. The branch is a reversible, measured option; it does not move the brain
closer to replacing production on its own.

**The next execution blocker is unchanged: row 2, the #200 limit** — B16, B19 and B09 (three of the
eight briefs) still get no exact plan at all (every band placement INFEASIBLE, every solve UNKNOWN
within its share), and no foyer rule reaches a brief with no exact plan. After that, row 3, the
request-time budget (31 s vs production's 10 s), is an owner decision before any deploy.

Two smaller facts for whoever picks this up: (1) the C25 failures that remain on the foyer partis
are "beside the entrance" stubs — a +FOYER candidate whose hall also reaches the street — a screen
in `exact_pipeline` (or the proposer) rather than a sizer bound; (2) the V orientation's fronting
cells are the band-start cells, which none of the oracle's street rules (entrance or foyer) see.

## Changes

* `exact/milp_oracle.py` — `FOYER_MIN_NET_M`, `FOYER_MAX_DEPTH_TO_WIDTH`, `_foyer_constraints`
  (grid big-M form, used by `milp_heights` and `_spine_once`); `_skip` on `milp_heights`,
  `milp_placement`, `milp_spine_placement`.
* `exact/milp_cells.py` — the same three bounds as plain rows (H is linear there); `_skip` on
  `cells_placement`.
* Tests: `tests/vertical_slice/test_foyer_geometry.py` (5: a fronting foyer is never a strip per
  oracle, `_skip={"foyer"}` reproduces b460a42's sizing — pinned — per oracle, the constants are
  the door widths and the compact-hall threshold); `test_brain.py`'s never-ranks-below test carries
  #204's measured B08 keys (`MEASURED_204_KEYS`) — that assertion is the gate's second clause and
  is marked `xfail(strict=True)` with this report as the reason, so the measured loss is on record
  in the suite and cannot be silently "fixed" by timing.
