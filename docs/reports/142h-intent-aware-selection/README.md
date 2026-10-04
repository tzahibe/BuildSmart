# #142H — Productionize proven architectural candidate selection

**Goal.** Make the normal production pipeline (`band_pipeline.run_band_pipeline`) reproduce the
7/13 result that #142F's selection path + #142G's RC walls had already demonstrated — without new
geometric representation and without touching the six remaining briefs.

**Result: 7/13 in production** (B01, B04, B05, B08, B11, B13, B18), up from 5/13; the same seven
briefs the selection path passed, B18 on the same candidate (#40). Every direct-access edge of every
passing brief is realized as a placeable door (access n/n, nothing lost). B01/B04/B05/B08/B13 keep
passing; no validator, access rule, room bound or realizer policy changed. The six remaining briefs
are now typed as input problems before any geometry: B06 `EXPOSURE_INFEASIBLE` (complete family),
B07/B09/B17 `ACCESS_SPATIAL_CONTRADICTION`, B12/B20 `ACCESS_POLICY_CONFLICT`. Full backend suite
green (see §6). Worst brief 1.3 s.

## 1. What moved into production (§1–§5 of the task)

The pipeline is now: required contacts → exact band embedding → **SELECTION** → door-aware exact
sizing → unchanged `realize_layout` → unchanged validators. Everything in SELECTION is decided from
the band placement alone, before any geometry.

| task § | capability | where |
|---|---|---|
| 1 | **Entrance-aware orientation.** A band layout carries the same contacts either way up; the street is row 0 (`resolve_entrance` reads the footprint's y = min edge). A candidate whose entrance-eligible rooms (`ALLOWED_ENTRANCE_ROLES`) sit only in the last band is flipped (`BandPlacement.flipped`, `band_pipeline.orient`) — never rejected, never given a fake entrance after geometry exists. A candidate with no entrance room in either end band is rejected; a brief with none anywhere is `NO_ENTRANCE` at SELECTION. | `band_embedding.BandPlacement.flipped`, `band_pipeline.orient` |
| 2 | **Door-width-aware sizing.** `band_sizing.contact_requirements` gives each direct-access pair the realizer's own door rule (door width + 2 × 0.10 m corner margin: 1.10 m room door, 1.00 m service door; spatial-only pairs keep "any positive contact"). Both exact solvers take it: the free-interleaving `solve_band_layout` (cross-band overlap ≥ need; a same-band consecutive pair bounds the band depth) and the fixed-column `solve_band_sizing` (difference constraints on prefix sums). The realized `GridWing` carries `access_pairs`, so `_solve_grid`'s own re-solve honours the same doors — the #142F harness's `mock.patch` injection is gone. Room bounds, aspect, RC insets and the safe-room net minimum are unchanged. | `band_sizing` (`door_contact_u`, `contact_requirements`, `_grid_contact_constraints`, `_layout_system`), `rectilinear_realizer.GridWing.access_pairs`, `_solve_grid` |
| 3 | **Physical support for direct access.** `required contacts = spatial ∪ direct-access pairs` (`required_contacts`), surfaced as an `ACCESS_CONTACTS_REQUIRED` warning listing every added pair — never silent. If the union has no band layout while the spatial graph alone has one → `ACCESS_SPATIAL_CONTRADICTION` (stage EMBEDDING, 0 candidates, the union refusal quoted). Pairs no layout can carry as a legal door (role table or the realizer's wet-room filter) → `ACCESS_POLICY_CONFLICT`. Per candidate, `access_contact_ok` (touch + legal) and `reachable_from_entrance` are HARD. | `band_pipeline.required_contacts`, `access_policy_conflicts`, `placement_flags` |
| 4 | **Mandatory-exposure filtering.** `exposure_ok` (every `REQUIRED_EXTERIOR_ROLES` room on the envelope) and `safe_room_on_envelope` are HARD; a brief whose whole family fails it → `EXPOSURE_INFEASIBLE` ("complete family of N" when the enumeration completed). PREFERRED exposure (`DRESSING_ROOM`, `BATHROOM`, `TOILET`) is recorded in the flags (`preferred_on_envelope`/`preferred_total`) and never enforced. No window is ever added after realization (`windows.py` untouched). | `band_pipeline.placement_flags`, `HARD_FLAGS`, `_selection_code` |
| 5 | **SAFE_ROOM preserved.** RC walls, RC insets, net minimum, door and window all come from #142G unchanged; the door-aware sizing adds the 1.10 m HALL↔SAFE_ROOM boundary. B04/B11/B18 pass with RC on all four sides and C4 PASS (`figures/*_selected_plan.png`). | — |

`HARD_FLAGS = (entrance_feasible, access_contact_ok, exposure_ok, reachable_from_entrance, safe_room_on_envelope)`
— exactly the #142F HARD set. Candidates are still tried in the embedder's plausibility order; SOFT
properties (band count, public front share, bedroom spread, preferred exposure) are recorded only.

## 2. Frozen suite, before / after

`data/production_before_142h.json` (= #142G's production run) vs `data/production_after_142h.json`.

| brief | before (#142G production) | after (#142H production) | selection funnel after: layouts → HARD-feasible (flipped) → door-sized → candidate |
|---|---|---|---|
| B01 | PASS | PASS 4/4 access | 34 → 22 (4) → 16 → #0 |
| B04 | PASS | PASS 7/7 | 120 → 33 (15) → 25 → #0 |
| B05 | PASS | PASS 6/6 | 120 → 67 (38) → 42 → #8 |
| B08 | PASS | PASS 7/7 | 120 → 32 (20) → 17 → #0 |
| B11 | ACCESS_SPATIAL_MISMATCH (validators) | **PASS 10/10** | 120 → 10 (3) → 2 → #3 |
| B13 | PASS | PASS 9/9 | 120 → 3 (0) → 3 → #20 |
| B18 | SIZING_INFEASIBLE | **PASS 12/12** | 120 → 60 (56) → 1 → #40 |
| B06 | BAND_GEOMETRY_LIMIT | EXPOSURE_INFEASIBLE (complete family of 58, 58/58 bury a REQUIRED room) | 58 → 0 |
| B07 | ACCESS_SPATIAL_MISMATCH (validators) | ACCESS_SPATIAL_CONTRADICTION (embedding) | — |
| B09 | NO_ENTRANCE (realization) | ACCESS_SPATIAL_CONTRADICTION (embedding) | — |
| B17 | NO_ENTRANCE (realization) | ACCESS_SPATIAL_CONTRADICTION (embedding) | — |
| B12 | ACCESS_SPATIAL_MISMATCH (validators) | ACCESS_POLICY_CONFLICT (LIVING→BATHROOM_3, shared wet room) | 120 → 0 |
| B20 | NO_ENTRANCE (realization) | ACCESS_POLICY_CONFLICT (HALL→BATHROOM_2, ENSUITE of BEDROOM_1) | 120 → 0 |
| **PASS** | **5/13** | **7/13** | |

Six representation-limit briefs and B19 (non-planar) are unchanged (`TOPOLOGY_*`, 0 candidates).

Why B11/B18 needed this and not more: both already had HARD-feasible, validator-acceptable layouts in
the family; production failed them because (B11) the plain sizing gave a declared access pair a
boundary too short for its door and the realizer then found "no legal door partner" (C5/C24), and
(B18) only one layout of the 120 is sizable at all once doors and RC insets are counted, and the old
flow never reached it with the right widths. Neither needed a flip in the end (every first pass has
`oriented=False`), but 3 (B11) and 56 (B18) of their HARD-feasible candidates were only feasible
flipped — the orientation step is what keeps those in the pool.

## 3. Controls (never weakened)

- **HARD never rejects a validator-passing candidate.** `data/control_hard_vs_validators.json`:
  for every band brief, every sizable candidate was realized WITHOUT selection (old flow); of the
  validator-passing ones (B01 14, B04 3, B05 7, B08 2, B13 1; 0 elsewhere) **none** fails any HARD
  flag, on either the spatial or the union embedding. The filter only removes candidates the
  unchanged validators would have refused anyway, or that lose a declared door.
- **Door-aware sizing is exact.** Infeasibility is a proof in both solvers (`test_door_aware_sizing_refuses_when_no_sizing_can_host_the_doors`);
  the realizer's re-solve agrees with the layout solver (B11's candidates that the layout solver
  sized without doors were refused by the door-aware re-solve during development — the two now
  share one requirement set, `test_realizer_resolve_honours_the_same_doors_and_places_them`).
- **No fake entrance.** `test_entrance_band_in_the_last_row_is_flipped_before_realization`: the
  un-flipped layout refuses `NO_ENTRANCE`; the flipped one realizes with its front door in LIVING/HALL.
  `test_entrance_is_chosen_by_orientation_never_invented` checks every frozen pass.
- **Nothing silent.** Added contacts and policy conflicts are warnings on every result; a
  contradiction is a typed diagnosis with 0 candidates.
- B01 (6/6, 4/4), B13 (12/12, LIVING aspect ≤ 2.5), B04/B11/B18 (RC + C4), determinism (B01, B18
  twice → identical rects), runtime ≤ 8 s per brief (measured worst 1.3 s).

## 4. Tests

- `tests/vertical_slice/test_band_selection.py` (14): orientation (flip, keep, NO_ENTRANCE typed);
  door rule (22 / 20 units), door-aware layout sizing gives every access pair ≥ its door, refuses with
  a proof when no sizing can host the doors, the realizer re-solve places every declared door, a
  same-band door bounds the band depth; union contacts + explicit warning, K4-by-access →
  `ACCESS_SPATIAL_CONTRADICTION` with 0 candidates, shared bathroom off LIVING →
  `ACCESS_POLICY_CONFLICT` with nothing sized; REQUIRED exposure hard / PREFERRED and NONE not;
  HARD set pinned; SAFE_ROOM brief passes through selection with RC walls, C4, door ≥ 1.10 m, window;
  funnel accounting + determinism.
- `tests/vertical_slice/test_band_pipeline_regression.py`: proven passes now
  {B01, B04, B05, B08, B11, B13, B18}, ≥ 7; every pass preserves every access edge as a placeable
  door; safe-room briefs (3) RC + C4; entrance by orientation; input problems typed (B07/B09/B17,
  B12/B20, B06); codes/stages extended; determinism on B01 and B18.
- Unchanged: `test_band_sizing.py`, `test_safe_room_rc_walls.py`, `test_band_embedding.py`,
  realizer suites — all green.

## 5. Evidence

`figures/B01|B04|B05|B08|B11|B13|B18_selected_plan.png`: the production plan per brief — walls by
type (RC thick red), every placed door labelled with its shared boundary vs the door need
(e.g. `HALL↔SAFE_ROOM (1.40≥1.10)`), windows, entrance (★), the candidate index, whether it was
flipped, and the selection funnel in the title. `figures/selection_evidence.json`: per brief the
funnel, entrance room and street band, per access edge `shared_u / need_u / door_placed`, the safe
room's wall types, net area and window, and the (empty) failed-check list.

## 6. Regression

Full backend suite (shared dev venv): 1920 passed, 883 skipped, 9 xfailed, 0 failures. Focused: 15 selection +
regression suite green.

## 7. Out of scope, intentionally

B06 (exposure: its complete band family buries a REQUIRED-exposure room — a representation question),
B07/B09/B17 (proposals whose access contradicts their adjacency under rectangles), B12/B20 (proposals
asking for a door the wet-room policy forbids), SOFT scoring among HARD-feasible candidates, L-shaped
rooms, B18's search space. The #142F harness (`ai_harness/topology_poc/intent_142f.py`) remains as the
measurement tool that produced the reference; production no longer needs its injection.
