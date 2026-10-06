# #142F — Architectural intent-aware selection among valid band layouts (experiment, not productionized)

**Question.** How much of the remaining gap from 4/13 can be closed simply by choosing geometrically
valid layouts that already respect architectural intent, before any new geometric representation or
realizer capability?

**Answer.** Under the unchanged validators: **none of it — 4/13 stays 4/13.** Selection does change what
the pipeline *knows*: with entrance orientation, physically supported access, mandatory exposure and
SAFE_ROOM placement applied as HARD filters on the embedding, every remaining failure becomes a
specific, proposal- or capability-level diagnosis, and three briefs (B04, B11, B18) reach layouts
whose only failing check is C4, the safe-room RC wall the realizer cannot build. The RC-wall
counterfactual is therefore **7/13**, and that single realizer capability is the recommended next
bounded step. The other five non-passing band briefs are not selection problems: three proposals
(B07, B09, B17) require access through walls that their own adjacency plus rectangles cannot provide
(a triple-lens obstruction appears the moment access pairs are added to the required contacts), two
proposals (B12, B20) require a door the realizer's wet-room policy forbids regardless of layout, and
one family (B06) buries a daylight room in every one of its 58 layouts.

Side finding, fixed in its own PR (#165): the merged #142E embedder seeded its sampler from Python's
per-process string hash, so the same proposal could produce different candidates in different
processes; the baselines below are measured with the fixed, process-independent seed.

Code: `backend/app/ai_harness/topology_poc/intent_142f.py` (harness only; nothing under
`app/vertical_slice` changed except the seed fix). Evidence: `data/results.json` (production candidate
pool: 150 candidates from ≤ 800 layouts) and `data/results_big.json` (600 from ≤ 3,000).

## 1. What is knowable from the embedding, and what needs realized geometry

| property | decidable from the band placement | needs sizing / realized geometry |
|---|---|---|
| entrance | which band holds an ALLOWED_ENTRANCE room (HALL/CIRCULATION/LIVING); the street is the top band by the realizer's convention, and a layout can be flipped for free, so "entrance-eligible room in the first OR last band" is exact | frontage ≥ 1.0 m plus 1.0 m clearance from each wing corner — a cell narrower than ~2 m at a corner can still fail; never seen in this run |
| access | whether each access pair touches, and whether the pair is legal (`edge_role_pair_allowed` plus the realizer's wet-room filter) | the shared wall must be ≥ door width + margins (1.10 m room / 1.00 m service): a sizing constraint. **The production realizer re-solves the sizing from the GridWing's columns and knows nothing of door widths**, so door-width feasibility is not reliable until it lives in production sizing (it was injected for this experiment) |
| exposure | REQUIRED rooms (LIVING, DINING, KITCHEN, FAMILY_ROOM, BEDROOM, MASTER_BEDROOM, STUDY, SAFE_ROOM, LAUNDRY) must touch the envelope: exact from the placement | the exterior wall must be ≥ 0.9 m for a habitable window (0.5 m wet room, 0.6 m laundry): sizing; never binding here |
| circulation | reachability of every room from the entrance room through legal contacts: exact | door swings (C28), furniture-blocked paths (C31), circulation ratio (C26): realized |
| SAFE_ROOM | on the envelope (REQUIRED exposure) and a legal partner (HALL/CIRCULATION): exact | RC walls on all four sides (C4): a realizer capability, not a placement property |

## 2. Before / after funnel (13 band-representable briefs)

| stage | #142E (merged, fixed seed) | #142F default pool | #142F large pool |
|---|---:|---:|---:|
| band representable (spatial adjacency) | 13 | 13 | 13 |
| band representable (spatial ∪ access) | — | 10 | 10 |
| ≥ 1 HARD-feasible candidate | — | 7 | 6 |
| sizable | 11 | 7 | 6 |
| realized | 8 | 7 | 6 |
| validators PASS (unchanged) | **4** | **4** | **4** |
| PASS or fails only C4 (RC counterfactual) | 4 | **7** | 6 |

Per brief (default pool; E = merged pipeline, F = intent-aware selection):

| brief | E outcome | F outcome | why it changed |
|---|---|---|---|
| B01 | PASS | PASS (16/16 realized pass) | selection only raised the pass rate per candidate |
| B04 | SAFE_ROOM_RC_MISSING | FAILS_ONLY_C4 (29/29) | door-aware sizing removed the C24/C5 door failures; every realized candidate now fails C4 alone |
| B05 | PASS | PASS (43/50) | — ; residual non-passes: C28 door-swing overlaps, C31 furniture-blocked path |
| B06 | BAND_GEOMETRY_LIMIT | NO_HARD_FEASIBLE_CANDIDATE | complete family (58): every layout buries a REQUIRED room (exposure 0/58) — EXPOSURE_INFEASIBLE in the band family, on top of the geometry limit |
| B07 | SAFE_ROOM_RC_MISSING | ACCESS_SPATIAL_CONTRADICTION | access pairs HALL→BATHROOM_1, HALL→KITCHEN are not in the spatial adjacency; adding them creates a triple lens (BATHROOM_2/BEDROOM_1/MASTER each touching BATHROOM_1 and HALL): no rectangles |
| B08 | PASS | PASS (19/19) | — |
| B09 | NO_ENTRANCE | ACCESS_SPATIAL_CONTRADICTION | HALL→BATHROOM_3 added to contacts → triple lens on BATHROOM_2–HALL |
| B11 | SAFE_ROOM_RC_MISSING | FAILS_ONLY_C4 (3/3) | as B04 |
| B12 | ACCESS_SPATIAL_MISMATCH | ACCESS_POLICY_CONFLICT | LIVING→BATHROOM_3: a shared bathroom may only be entered from HALL/CIRCULATION under the realizer's wet-room filter (`ALLOWED_ENTERED_FROM` would admit LIVING) — illegal in every layout; also exposure 0/150 |
| B13 | PASS | PASS (3/3; 17/17 in the large pool) | exposure is the binding filter (10/150 candidates keep every daylight room on the envelope) |
| B17 | NO_ENTRANCE | ACCESS_SPATIAL_CONTRADICTION | four HALL→BEDROOM access pairs not in the adjacency → triple lens (BEDROOM_1/2/3 each touching BATHROOM_2 and HALL) |
| B18 | SIZING_INFEASIBLE | FAILS_ONLY_C4 (1/1) | 77 HARD-feasible candidates (95 of them only after flipping), one sizable with door widths; fails C4 only (net 8.99 vs 9.0 also reported) |
| B20 | NO_ENTRANCE | ACCESS_POLICY_CONFLICT | HALL→BATHROOM_2 while BATHROOM_2 is BEDROOM_1's ensuite: the filter admits no second door; additionally no candidate (0/150, 0/600) has an entrance-eligible room in an end band |

## 3. Entrance feasibility (§2)

- Orientation is the only entrance lever at the embedding level and it is free: a band layout flipped
  top/bottom is the same family member. Counting candidates with an entrance-eligible room in the
  street band directly vs. after flipping: B01 20→24 of 34, B04 38→66 of 150, B05 60→106, B08 36→78,
  B11 28→70, B13 122→127, B18 6→101, B12 15→65, B06 2→40, B20 0→0.
- Of the four #142E `NO_ENTRANCE` briefs: **B18 is solved by orientation** (and then fails only C4);
  B09 and B17 were never entrance problems (their access requirements are unembeddable); B20 has no
  entrance-feasible layout in 600 candidates from 3,000 layouts — its HALL and LIVING always sit in
  the middle bands because both are hubs of the required graph — reported within the search bound,
  not proven.
- Among candidates that pass the other HARD filters, NO_ENTRANCE never occurred downstream: the
  embedding-level test is exact for this realizer.

## 4. Access / spatial consistency (§3)

Invariant tested: required contacts = spatial_adjacency ∪ direct access pairs. The proposal is never
changed; its union graph is embedded as-is.

- 7/13 band briefs have access pairs outside their spatial adjacency (B03 1, B07 2, B09 1, B12 1, B15 1,
  B17 4, B18 1). For **B07, B09, B17** the union is a triple-lens obstruction: the proposals ask for
  doors their own adjacency cannot host under rectangles — `ACCESS_SPATIAL_CONTRADICTION`, a proposer
  defect to surface at the critic. For B12/B18 the union still embeds.
- A second, policy-level inconsistency: **B12 (LIVING→BATHROOM_3) and B20 (HALL→BATHROOM_2)** request
  doors the realizer's `_filter_wet_room_access` forbids (shared bathroom only from circulation;
  ensuite only from its host) although `access_rules.ALLOWED_ENTERED_FROM` admits them. No layout can
  satisfy these — `ACCESS_POLICY_CONFLICT`. Either the proposer must be told the realizer's rule, or
  the two rule sets must be reconciled (not done here).
- With contacts guaranteed and door widths enforced in sizing (experiment injection), C24/C5
  disappeared from every realized candidate of B04/B11/B18 — the door failures of #142E were
  sizing-level (no wall long enough), not topology-level.

## 5. Exposure (§4)

Classification from `exposure_policy`: REQUIRED (LIVING, DINING, KITCHEN, FAMILY_ROOM, BEDROOM,
MASTER_BEDROOM, STUDY, SAFE_ROOM, LAUNDRY), PREFERRED (BATHROOM, TOILET, DRESSING_ROOM), NONE (HALL,
CIRCULATION, STORAGE, FLEX, STAIRWELL). The exact band-level test "every REQUIRED room touches the
envelope" is the most selective HARD filter: B13 keeps 10/150 (20/600), B11 31/150, B08 75/150, B05
102/150, B04 107/150; **B06 0/58 (complete family) and B12 0/150** — explicit `EXPOSURE_INFEASIBLE`
within the band representation for B06 (proof) and B12 (within bound). No window was faked; C19/C8
untouched — and after the filter, C19/C8 never failed downstream.

## 6. SAFE_ROOM placement, geometry only (§5)

SAFE_ROOM is REQUIRED-exposure and PRIVATE (entered from circulation). Candidates with the safe room
on the envelope: B04 138/150, B11 117/150, B18 129/150, B20 140/150; with a legal partner: all of
those that are HARD-feasible. Placement is therefore **not** the problem for any SAFE_ROOM brief: every
realized B04/B11/B18 candidate has its safe room on the envelope, reachable, correctly sized, and
fails **only C4** (RC walls on all four sides). B07 and B20 never reach realization for the access
reasons above.

## 7. HARD vs SOFT (§6)

HARD (used as filters): entrance-eligible room in an end band; every access pair in contact and legal;
every REQUIRED-exposure room on the envelope; every room reachable from the entrance room through
legal contacts; SAFE_ROOM on the envelope. SOFT (recorded only, `flags` per candidate): number of
bands, hub band in the middle, number of bands holding bedrooms (zoning), share of the street band
held by public rooms, PREFERRED-exposure rooms on the envelope. Among the candidates that pass or
fail only C4, the dominant soft profile is 3–4 bands, hub band in the middle, bedrooms in 1–2 bands —
a reasonable house, by inspection of `first_pass` geometry in the data files.

## 8. Unchanged-validator results (§7, §9)

PASS 4/13 (B01, B05, B08, B13) in both pools — the same four as #142E, with far higher pass rates per
candidate (B01 16/16, B05 43/50, B08 19/19, B13 3/3 → 17/17 in the large pool). Residual validator
failures after the HARD filters are realized-geometry properties: C28 (door-swing overlap) and C31
(furniture-blocked path) in B05, C4 everywhere a SAFE_ROOM exists. Topology and sizing correctness
preserved: every realized candidate reports spatial preservation 100 % and access preservation 100 %.

## 9. RC-wall counterfactual (§8)

"Fails only C4" counts: B04 29 (120 in the large pool), B11 3 (13), B18 1 (0 in the large pool — its
HARD-feasible candidates are pool-dependent). **If RC-wall construction were the only missing SAFE_ROOM
capability, 7/13 would pass** (default pool; 6/13 with the large pool, where B18's top-600-by-plausibility
cut contains no exposure-feasible layout — a ranking issue noted below).

## 10. Recommendation — exactly one next bounded step

**Implement RC_SAFE_ROOM wall assignment in the rectilinear realizer** (the Geometry Core path already
does it: `engine._mark_exposure` marks a safe room's own sides and its neighbours' facing sides
RC_SAFE_ROOM). It is a realizer capability, it is the only failing check on 33 realized candidates
across three briefs, and it is the single change that moves the measured pass count (4 → 7 of 13).
Everything else measured here is either a proposal defect to surface earlier (B07/B09/B17
contradiction, B12/B20 policy conflict), a representation limit (B06 exposure), or already solved by
selection (B18's entrance).

Two productionization notes for whoever picks up selection itself (not asked for here): (a) apply the
HARD flags inside the embedder before the plausibility cut — the large pool shows the rank-1 score can
rank every exposure-feasible B18 layout out of the top 600; (b) door-width overlap must become a
constraint of production sizing (`solve_band_layout`), since the realizer re-solves widths and
otherwise drops the shared wall below door width.
