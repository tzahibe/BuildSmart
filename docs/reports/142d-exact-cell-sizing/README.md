# #142D — Exact per-cell band sizing POC: result, attribution and the gross/net finding

**Question.** With band topology fixed and valid, can an independent per-cell sizing replace
`_solve_grid`'s rank-1 proportional fit and materially unlock the existing realization pipeline?

**Answer (one paragraph).** Yes for sizing, and it moves the measured wall one stage further. Under
production semantics the exact oracle finds a feasible per-cell sizing for 11/13 band-representable
briefs (vs. 4/13 sized by the rank-1 fit in #142C), the realizer's own `_build_grid_wing` accepts
those sizings for 11/13, realization passes for 10/13, and the **unchanged validators pass for 4/13
(B01, B05, B08, B13)** — up from 1/13. Both controls hold: B13 (positive) reproduces cleanly (12/12
topology, 220/750 witnesses sizable, 200 sized, 145 realized, **21 validator PASS**, LIVING net
aspect 2.50); B01 (regression) keeps 6/6 spatial, 4/4 access and validator PASS (12 witnesses). Every
other brief is now blocked by something that is **not sizing**, and each block is measured and
classified: B06 and B07 are proven `BAND_GEOMETRY_LIMIT` (complete families of 156 and 4,752
layouts, every one infeasible with a certificate); B09 is sizable (4/180) but every band layout
buries a daylight room (C19/C8 impossible in the family); B04/B11/B18/B20 (and B07) contain a
SAFE_ROOM, and the rectilinear realizer never assigns RC walls, so C4 fails by construction;
B12/B17 carry a proposal-level inconsistency (rooms whose only required neighbours are rooms they may
not legally be entered from) so no band layout gives them a door; and across every brief the largest
single downstream rejection is `NO_ENTRANCE`, which the §9 flags predict exactly (witnesses with an
entrance-role cell in the street band realize at ~100%). The gross/net gate inconsistency is real
and bites both ways (§2): ~90% of witnesses that pass the gross gate fail C3 on net area, and ~97%
of net-correct sizings are refused by the gross gate; a clearly labelled counterfactual with a
net-consistent gate (B) is reported separately — with a net-consistent gate the same four briefs pass, with 2–3× more passing witnesses (B01 18, B05 18, B08 23, B13 38), 12/13 briefs realize, and C3 all but disappears from the rejection list; the remaining walls are `NO_ENTRANCE`, C4, C24/C5 and C19/C8 — none of them sizing. Nothing in production changed; the
oracle is an isolated prototype.

Generated companions: `results.md` (stage counts per brief for all three result sets, the §9 flag
table, realized geometry of every first success), `results.json.gz` (every witness outcome, trimmed, gzipped),
`certificates.md` (per-witness infeasibility proofs). Code: oracle
`backend/spikes/topology_representation/cell_sizing_oracle.py` (experimental; `scipy` only, already a
transitive dependency), driver `backend/app/ai_harness/topology_poc/exact_sizing_142d.py` (harness;
injects a sizing by replacing `_solve_grid` for one call via `unittest.mock.patch.object`; nothing
under `app/vertical_slice` changed), witness artifacts from the #142C embedder (`band_witnesses.py`,
isolated `python-sat` venv; complete families where finite).

## 1. The oracle (§1)

For a band witness the geometry is fully determined by band heights `h[r]` and column widths `w[c]`;
every cell is `h[r] × Σ w[c0:c1]`. The oracle decides, per witness, whether ANY `(h, w)` satisfies:

| constraint | modelled | how |
|---|---|---|
| cell area within the zone's `[min, max]` (±0.02 m², as `_build_grid_wing`) | exactly | bilinear `h·w` |
| both cell dimensions ≥ `min_short_side + 0.3 m` (`_build_grid_wing`'s short-side gate) | exactly | linear |
| max aspect ratio (validators C3/C20) | corrected semantics only | linear |
| net area / net short side with the witness's own per-side insets (C3: EXTERIOR 0.15 m, PARTITION 0.05 m per side) | corrected semantics only | linear in `(h, w, h·w)` |
| envelope ≤ brief footprint + 4 m (`ENVELOPE_TOO_LARGE`) | exactly | linear |
| shared boundaries implied by the embedding, non-overlap, complete coverage | structural (every band tiles all columns; each witness verified with the realizer's `Rect.shared_edge_len_u`) | — |
| door width on shared walls, entrance frontage, exposure/windows (C19/C8), circulation ratio (C26), furniture (C9/C30), wet-room access (C17), safe-room RC walls (C4), door reachability (C5/C24) | **not modelled — downstream checks**, measured after realization | — |

Three tools in order: (1) closed-form **necessary conditions** (width / depth / total-area interval
bounds — a violation is a human-readable proof), (2) an **alternating LP** existence search, (3) an
exact **spatial branch-and-bound** over band heights with McCormick relaxations of `h·w` (LP per
node). INFEASIBLE from (1) or (3) is a proof on the continuous model, a superset of the realizer's 5 cm
unit model, so it transfers. FEASIBLE points are rounded to units and then re-checked by the real
`_build_grid_wing` — that is the "sizing pass" column. Node/time limits would yield UNKNOWN; none
occurred (0 UNKNOWN over 15,648 witness decisions).

## 2. Gross vs net area — the latent inconsistency (§2)

Investigated first; nothing changed in either behaviour.

1. **Where gross is used.** `rectilinear_realizer._build_grid_wing` (lines 703–706) gates every cell
   with `r.area_m2()` — centerline/gross (`geometry_core/model.py:67`) — against
   `zi.min_area_m2 − 0.02 ≤ area ≤ zi.max_area_m2 + 0.02`. Its short-side gate compensates with
   `+ _INSET_MARGIN_M` (0.30 m, "twice the heaviest single-side inset"); the area gate has no such
   padding.
2. **Where net is used.** `validation.py` C3 (net area within the ZoneSpec bounds ±0.01, net short
   side, net aspect), C20/C21 (net vs `ROOM_TEMPLATES`), C26 (net areas), C27 — all through
   `engine.net_rect_m`, which removes half the wall thickness per side (EXTERIOR 0.15 m, PARTITION
   0.05 m, OPEN 0, RC 0.15 m).
3. **What the domain intends.** `ZoneSpec` (`model.py:199`): "Areas/dims are NET (clear internal),
   never centerline"; `ZoneIntent` mirrors ZoneSpec's net fields; `ROOM_TEMPLATES` are written
   against net areas (`concept_generator.py:757`; C21's docstring); the Geometry Core inflates net to
   centerline in `leaf_shapes`. **The bounds are net; the grid gate measures gross.**
4. **Does it cause false acceptance / rejection?** Both, heavily:
   - *False acceptance* (gross gate passes, C3 net fails) — production semantics, witnesses that
     reached the validators and failed C3: B01 15/22, B04 79/90, B05 248/253, B08 46/56, B09 2/2,
     B12 4/4, B13 102/124, B17 2/2, B18 162/163, B20 9/9. Typical detail: "LIVING net 14.62 m²
     outside [16.0, 46.0]" for a room the gate accepted at gross 16+ m². The gate is lenient at the
     min end by the insets (up to 0.30 m per axis).
   - *False rejection* (net-correct sizing, gross gate refuses) — corrected semantics A, oracle
     FEASIBLE witnesses refused by `_build_grid_wing`: B04 331→0 sized, B05 501→0, B07 24→0, B09
     28→0, B11 80→0, B12 179→0, B17 51→0, B20 292→0, B01 56→4, B08 277→6, B13 193→15 (refusals split
     ~70% `AREA_INFEASIBLE` at the max end, ~30% `SHORT_SIDE_INFEASIBLE` because the 0.30 m margin is
     stricter than the real 0.10–0.30 m insets).
   - Net effect: the two checks disagree on almost every room; a sizing that satisfies one fails the
     other. This is a correctness defect in `_build_grid_wing`'s gate, not in C3.

Primary results are under **production semantics** (oracle enforces the gross gate as it exists).
**Counterfactual A** (oracle enforces net semantics, production gate left in place) measures the
false rejections. **Counterfactual B** (A, plus the gate made net-consistent for the experiment only —
bounds widened for the gate call, true ZoneSpecs restored for every downstream check) measures what
the pipeline does once the inconsistency is removed. All three are separate tables in `results.md`.
No production policy change.

## 3. Results, all 13 band-representable briefs — production semantics (§3)

| brief | n | family | witnesses examined | oracle feasible | sizing pass (realizer gate) | realization pass | validator PASS | category | dominant rejections after sizing |
|---|---|---|---|---|---|---|---|---|---|
| B01 | 5 | complete (68) | 68 | 48 | 46 | 34 | **12** | PASS | NO_ENTRANCE 12; C26, C3 (net), C20 |
| B04 | 8 | capped | 904 | 272 | 178 | 90 | 0 | DOWNSTREAM_CONSTRAINT | NO_ENTRANCE 88; C4 (SAFE_ROOM, 90/90), C3, C26, C5 |
| B05 | 7 | capped | 679 | 506 | 406 | 255 | **2** | PASS | NO_ENTRANCE 151; C3, C17+C24+C5 (wet-room door), C26 |
| B06 | 8 | complete (156) | 156 | 0 | 0 | 0 | 0 | **BAND_GEOMETRY_LIMIT** (proof, §6) | — |
| B07 | 9 | complete (4,752) | 4,752 | 0 | 0 | 0 | 0 | **BAND_GEOMETRY_LIMIT** (proof, §7) | — |
| B08 | 8 | capped | 694 | 238 | 159 | 66 | **10** | PASS | NO_ENTRANCE 93; C3, C5 |
| B09 | 9 | complete (180) | 180 | 4 | 4 | 2 | 0 | DOWNSTREAM_CONSTRAINT (exposure impossible in the family, §6) | NO_ENTRANCE 2; C19+C8+C3+C20+C5 (2) |
| B11 | 11 | capped | 816 | 88 | 61 | 0 | 0 | DOWNSTREAM_CONSTRAINT | NO_ENTRANCE 61/61 |
| B12 | 10 | capped | 750 | 110 | 32 | 4 | 0 | DOWNSTREAM_CONSTRAINT (door-ability impossible: proposal inconsistency, §8) | NO_ENTRANCE 28; C24+C5, C19, C3 |
| B13 | 10 | capped | 750 | 220 | 200 | 145 | **21** | PASS | NO_ENTRANCE 55; C19+C8 (exposure) 71, C3, C20 |
| B17 | 12 | capped | 1,000 | 17 | 2 | 2 | 0 | DOWNSTREAM_CONSTRAINT (door-ability impossible, §8) | C24+C5, C3 |
| B18 | 13 | NOT exhaustible (>100,000; 3,000 examined) | 3,000 | 760 | 299 | 163 | 0 | DOWNSTREAM_CONSTRAINT within search bound | NO_ENTRANCE 136; C4 (SAFE_ROOM, 163/163), C24+C5, C3 |
| B20 | 10 | capped | 900 | 288 | 213 | 9 | 0 | DOWNSTREAM_CONSTRAINT | NO_ENTRANCE 204; C4 (SAFE_ROOM), C20, C5 |

| stage | briefs (of 13) | #142C (rank-1 fit) |
|---|---|---|
| exact band embedding | 13 | 13 |
| oracle: ≥ 1 feasible per-cell sizing | 11 | — |
| realizer sizing gate accepts ≥ 1 | 11 | 4 |
| realization | 10 | 3 |
| **validators PASS (unchanged)** | **4** (B01, B05, B08, B13) | 1 |

Witness totals: 15,648 examined, 2,551 oracle-feasible, 1,600 accepted by the realizer gate, 970
realized, 45 validator PASS.

## 4. Controls

- **B13 (positive control, §4).** 12/12 required adjacencies verified on all 750 witnesses before
  sizing; 220 sizable; 200 accepted by `_build_grid_wing`; 145 realized; **21 pass every validator**.
  First passing witness: #7, 4 bands × 4 columns, envelope 12.96 × 12.99 m, spatial 12/12, access
  9/9; LIVING 9.20 × 3.80 m gross → 9.00 × 3.60 m net, **aspect 2.50 ≤ 2.5**; HALL a 12.95 × 2.00 m
  band (25.9 m² gross). The #142C stub result is reproduced and exceeded (2 → 21 witnesses).
- **B01 (regression control, §5).** Exact topology; 48 sizable; 46 accepted; 34 realized; **12 pass**;
  first: witness #0, 10.34 × 7.31 m, **spatial 6/6, access 4/4**, full validator PASS. The 12 witnesses
  that fail after sizing are `NO_ENTRANCE` (MASTER/LIVING band not in row 0), the 22 that reach the
  validators fail C26 (hall band > 24 % of net area) and C3 (net).

## 5. Failure categories (§6)

| category | briefs | evidence |
|---|---|---|
| PASS | B01, B05, B08, B13 | §3 |
| SIZING_MODEL_LIMIT | **none** | 0 UNKNOWN oracle decisions; every oracle-feasible point that the realizer gate rejected was rejected on the 5 cm rounding of a tight bound (counted inside "sizing pass" vs "oracle feasible", e.g. B13 220 → 200), never for lack of a sizing |
| BAND_GEOMETRY_LIMIT | B06, B07 | complete families, every witness INFEASIBLE with a certificate (§6, §7) |
| DOWNSTREAM_CONSTRAINT | B04, B09, B11, B12, B17, B18, B20 | sizing accepted for ≥ 1 witness; blocked by NO_ENTRANCE / C4 / C19+C8 / C24+C5 / C3 — see §8 for which |
| UNKNOWN_WITHIN_SEARCH_BOUND | B18 for any claim stronger than "3,000 of >100,000 layouts examined" | §7 |

## 6. B06 / B09 — from observation to proof (§7)

**B06 (8 rooms, footprint 13 × 24 m): `BAND_GEOMETRY_LIMIT`, proven.** The band family is finite and
fully enumerated: 156 layouts (3 or 4 bands). All 156 are infeasible under the realizer's own checks:

- 124 by the closed-form **width certificate**: in those layouts a bathroom is a single-cell band.
  A full-width cell of a room with `max_area = 12 m²` and minimum depth `1.6 + 0.3 = 1.9 m` caps the
  wing width at `12 / 1.9 = 6.33 m`; but the band holding MASTER + BEDROOM_1 + BATHROOM_2 needs at
  least `3.3 + 2.9 + 1.9 = 8.1 m` (each cell's own minimum width). `6.33 < 8.1` — no heights/widths
  exist. (Certificate text per witness in `certificates.md`.)
- 32 by exhaustive branch-and-bound (the McCormick relaxation is already infeasible at the root
  box, i.e. the problem is infeasible even after relaxing `h·w` to its convex hull).

Why every B06 band layout runs into this: B06's graph forces its two bathrooms and the hub into
contact patterns that only a 3–4 band layout carries, and in every such layout some wet room spans
the full width or a bedroom band outgrows the width a wet band allows. The mechanism is the
`ROOM_TEMPLATES` bounds interacting with the band family: *a band is as wide as its widest member
needs and as narrow as its tightest member allows*. Additionally, **0/156 layouts give every
daylight room an exterior wall** (exposure_ok = 0), so even a sizable layout would fail C19/C8.

**B09 (9 rooms, 20 × 22 m): NOT a geometry limit — a downstream limit with a certificate.** Complete
family of 180 layouts: 176 infeasible (certificates), **4 sizable** (the #142C LP had missed them;
the exact oracle finds them). All 4 die downstream: 2 `NO_ENTRANCE`, 2 reach the validators and fail
C19+C8 (a daylight room with no exterior wall), C3 (net: LIVING 14.62 < 16, BEDROOM 8.4 < 9 — false
acceptance by the gross gate), C20 (bathroom aspect 3.56), C5. And **0/180 layouts satisfy
exposure_ok**: in B09's band family a REQUIRED_EXTERIOR room is always interior, so C19 cannot pass
for any sizing. That is a topological certificate for the downstream failure — "topology-representable
≠ geometrically realizable" holds for B09 through exposure, not through area.

## 7. B07 / B18 (§8)

- **B07 (9 rooms, SAFE_ROOM, 18 × 20 m): exhausted — 4,752 layouts, all infeasible** (4,368 width
  certificates: a full-width bathroom band caps the wing at 6.33 m while the bedroom band needs
  ≥ 11.0 m; 384 by B&B). `BAND_GEOMETRY_LIMIT` under production semantics is proven. Under corrected
  (net) semantics 24 layouts ARE sizable and are refused only by the gross gate (counterfactual A);
  in counterfactual B all 24 are accepted by the net-consistent gate, 6 realize (18 `NO_ENTRANCE`) and all 6 fail the validators on C19+C24+C3+C4+C5 (exposure, door-ability, safe-room RC) — so B07 stays unrealizable in the band family for reasons beyond area. B07 also contains a SAFE_ROOM
  (C4, §8) and has exposure_ok = 0/4,752.
- **B18 (13 rooms, SAFE_ROOM): `UNKNOWN_WITHIN_SEARCH_BOUND`.** The first grid shape alone yields
  100,000 distinct band layouts before the enumeration cap; the family is not exhaustible this way.
  Of the 3,000 best-ranked layouts: 760 sizable, 299 accepted by the gate, 163 realized, 0 pass (C4
  163/163, C24+C5, C3). No impossibility claim is made for B18.

## 8. Entrance and access, measured separately (§9)

Per-witness topology flags (never enforced): `entrance_ok` (a HALL/CIRCULATION/LIVING cell in the
street band — row 0, because `resolve_entrance` reads the footprint's y = min edge), `access_ok`
(every room touches ≥ 1 room it may legally be entered from, wet rooms as `_filter_wet_room_access`),
`exposure_ok` (every REQUIRED_EXTERIOR role touches the envelope). Full table in `results.md`.

Findings:
- **`NO_ENTRANCE` is exactly predicted by `entrance_ok`.** Among witnesses with all three flags,
  realization succeeds for every witness the gate accepted (B01 34/34, B04 89/89, B05 238/238, B08
  59/59, B13 43/43, B18 32/32); `NO_ENTRANCE` disappears. The embedder can enforce this at zero
  representation cost (one constraint: an entrance-role room in row 0).
- **Every validator-passing witness satisfies all three flags** (B01 12/12, B05 2/2, B08 10/10, B13
  21/21) — they are necessary conditions.
- **`access_ok` exposes a proposal-level inconsistency, not a band limit.** B12 and B17 have
  `access_ok = 0` on every witness because the proposal's `access_graph` enters a room from HALL (or
  LIVING) while its `spatial_adjacency` never requires that room to touch HALL: B12 BATHROOM_2's
  required neighbours are BATHROOM_3/BEDROOM_1/BEDROOM_2 (none a legal door partner for a shared
  bathroom), BATHROOM_3's are BATHROOM_2/LIVING; B17 BEDROOM_1/2/3 touch only BATHROOM_2 and BEDROOM_5
  only LIVING, yet all are "entered from HALL". A door needs a shared wall, so **the embedder must take
  `spatial_adjacency ∪ access_graph` as required contacts** (today it takes `spatial_adjacency`
  only). The same gap explains C17+C24+C5 in B05 (110 witnesses) and C24+C5 in B18 (163). The
  critic/proposer should flag such proposals.
- **`exposure_ok = 0` for B06, B07, B09, B12**: in those band families a daylight room is always
  interior. For the others it is a selection criterion the embedder can enforce (B13: 98/750, and 21
  of those 43 sized pass).
- **SAFE_ROOM briefs (B04, B07, B11, B18, B20) cannot pass C4 through this realizer**: it types walls
  EXTERIOR/PARTITION/OPEN only and never `RC_SAFE_ROOM` (the Geometry Core path does). This is a
  realizer gap, not a validator problem; it caps this experiment's reachable set at 8/13 before any
  other constraint.

Reachable-set accounting under production semantics: 13 − 5 (SAFE_ROOM/C4) − 2 (B06/B07 geometry)
− 1 (B09 exposure) − 2 (B12/B17 proposal inconsistency) = **3 briefs could pass by construction,
and 4 did** (B05 is a SAFE-free brief whose two passing witnesses avoid the wet-room door problem).
In other words, exact sizing reaches every brief the band family, the realizer's own gaps and the
proposals allow.

## 9. Counterfactual B — net-consistent gate (separate result set)

Counterfactual B = corrected (net) semantics in the oracle **and** `_build_grid_wing`'s area and short-side gates
skipped for the gate call only (bounds widened for that call; the true ZoneSpecs are restored for every downstream
check, so C3/C20/C21 still judge each room on its real net bounds). Validators unchanged. Full table in `results.md`.

| brief | oracle feasible | gate accepts | realization | validator PASS | dominant rejections |
|---|---|---|---|---|---|
| B01 | 56 | 56 | 34 | **18** (was 12) | NO_ENTRANCE 22; C26 |
| B04 | 331 | 331 | 158 | 0 | NO_ENTRANCE 173; C4 (SAFE_ROOM) on every reached witness, C26 |
| B05 | 501 | 501 | 297 | **18** (was 2) | NO_ENTRANCE 204; C17+C24+C5 (wet-room door), C26 |
| B06 | 0 | 0 | 0 | 0 | BAND_GEOMETRY_LIMIT (unchanged) |
| B07 | 24 | 24 | 6 | 0 | NO_ENTRANCE 18; C19+C24+C3+C4+C5 |
| B08 | 277 | 277 | 80 | **23** (was 10) | NO_ENTRANCE 197; C5, C24 |
| B09 | 28 | 28 | 4 | 0 | NO_ENTRANCE 24; C19+C8 (exposure), C5 |
| B11 | 80 | 80 | 2 | 0 | NO_ENTRANCE 78; C24+C4+C5 |
| B12 | 179 | 179 | 32 | 0 | NO_ENTRANCE 147; C17/C19/C24/C5/C8 |
| B13 | 193 | 193 | 111 | **38** (was 21) | NO_ENTRANCE 82; C19+C8 (exposure), C5 |
| B17 | 51 | 51 | 38 | 0 | NO_ENTRANCE 13; C24+C5 (door-ability), C17 |
| B18 (3,000 of >100k) | 1,440 | 1,440 | 646 | 0 | NO_ENTRANCE 794; C24+C4+C5, C3 |
| B20 | 292 | 292 | 36 | 0 | NO_ENTRANCE 256; C19+C24+C4+C5+C8 |

Briefs: oracle feasible 12/13, gate accepts 12/13, realization 12/13, **validators PASS 4/13** — the same four as
production, with 97 passing witnesses instead of 45. Removing the gate inconsistency therefore does not change
which briefs pass; it removes C3 as a rejection reason (residual C3 hits are 5 cm-rounding cases) and leaves the
non-sizing blockers of §8 standing alone: `NO_ENTRANCE` (2,208 of 3,452 gate-accepted witnesses that did not
realize), C4 for the five SAFE_ROOM briefs, C24/C5 door-ability, C19/C8 exposure, C26 for hub-band layouts.

## 10. Comparison with #142C and recommendation

| | #142C (rank-1 `_solve_grid`) | #142D (exact per-cell oracle) |
|---|---|---|
| briefs with ≥ 1 sized witness | 4/13 | 11/13 |
| realization | 3/13 | 10/13 |
| validators PASS | 1/13 (B01) | **4/13** (B01, B05, B08, B13) |
| B13 | 5 witnesses sized, 0 pass (LIVING aspect) | 200 sized, 21 pass |
| dominant blocker | rank-1 sizing (0/207 feasible sizings found) | `NO_ENTRANCE`, then C4 (SAFE_ROOM RC), C3 (gross/net gate), C24/C5 (door-ability), C19/C8 |

Recommendation (measured, in priority order; none implemented here):
1. **Productionize a per-cell band sizing solver** (replace `_solve_grid`'s rank-1 fit with an
   exact `(h, w)` solve — the alternating LP found 95 % of the oracle's feasible points in
   milliseconds; B&B only served proofs). This is now justified: it is the difference between 1/13
   and 4/13 with nothing else changed.
2. **Fix `_build_grid_wing`'s area gate to net semantics** (the bounds are net by the domain model);
   until then any sizing solver is judged by two contradicting gates. Counterfactual B is the
   measurement of what that fix alone buys.
3. **Give the embedder three topology-side constraints**: entrance-role room in the street band;
   required contacts = `spatial_adjacency ∪ access_graph`; REQUIRED_EXTERIOR rooms on the envelope.
   All three are exact, zero representation cost, and each was shown above to be necessary.
4. **RC walls for SAFE_ROOM in the rectilinear realizer** (5/13 briefs are C4-blocked by construction).
5. Flag proposals whose access graph is not supported by their spatial adjacency (B12, B17) at the
   critic.
Not recommended: L-shaped rooms, a second realizer, GridWing rewrites — nothing measured here needs
them; B06/B07 are the only genuine band-geometry limits and they are also exposure-impossible.

## Reproducing

```
# witnesses (isolated venv with python-sat): complete families where finite, capped otherwise
python backend/spikes/topology_representation/band_witnesses.py briefs_142c.json witnesses_main.json 1500 120 B01,B04,B05,B06,B08,B09,B11,B12,B13,B17,B20
python backend/spikes/topology_representation/band_witnesses.py briefs_142c.json witnesses_B07.json 100000 900 B07 100000
# passes (dev venv, PYTHONPATH=backend): production | corrected | corrected_netgate
python backend/spikes/topology_representation/run_142d.py production results_production.json witnesses_main.json,witnesses_B07.json
python backend/spikes/topology_representation/build_142d_report.py <worktree> <scratch>
```
`briefs_142c.json` (zones, graph, footprint per brief) is in `../142c-exact-band-embedding/`.
