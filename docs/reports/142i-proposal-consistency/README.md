# #142I — Proposal consistency and policy alignment

**Final question.** How many of the remaining six failures are caused by invalid or internally
inconsistent proposals, and how many represent genuine missing geometric capability?

**Answer: six of six are invalid or inconsistent proposals; none is a proven missing geometric
capability.** A deterministic critic that runs before any embedding detects every one of the six
from the proposal alone (and raises nothing on the seven passing briefs). After minimal,
intent-preserving repairs — each one recorded — four of the six (B06, B07, B09, B12) pass the
unchanged production pipeline: **7/13 → 11/13**. The other two (B17, B20) become consistent
proposals that the band family still cannot size within the search bound; for both, another
proposal from the same LLM run is critic-clean and passes production, so even they are not evidence
of a missing representation. Across the whole LLM dataset, 19 of 20 briefs — including all six
"representation-limit" briefs and the non-planar B19 — have at least one critic-clean proposal that
passes production as it stands. The frozen suite selected the wrong proposals, not the wrong geometry.

Data: `data/critic_results.json` (critic + repair + pipeline, frozen suite and all 162 dataset
proposals), `data/b06_exposure_sat.json` (exact SAT proof), `figures/*_repaired_plan.png`.

## 1. Root causes, traced (task §1)

The frozen briefs are the top-scored, access-rules-valid proposal of an LLM Topology Proposer run
(`docs/reports/llm-topology-poc/generation-dataset.json`, 162 proposals over 20 briefs, 6–9 per
brief), reduced by `gap_closure_142a.best_policy_valid_proposal` with ROOM_TEMPLATES bounds. The
chain each proposal passes through, and where each defect first becomes knowable:

| layer | what it does | defect it introduces or lets through |
|---|---|---|
| **LLM proposer prompt** (`topology_poc/prompt.py`) | fixes the room vocabulary, asks for `spatial_adjacency` and a directed `access_graph` | (a) *"ADJACENCY IS NOT ACCESS: … or be joined by a door across a corridor (accessed but not touching)"* — this sentence licenses a door with no shared wall, which is physically impossible: a door across a corridor is two doors and a corridor. Every `ACCESS_WITHOUT_CONTACT` in the dataset (and the B07/B09/B12/B17 contradictions) follows from it. (b) every wet room is handed to the model as role `BATHROOM` (`build_brief_program_text`) — the brief's wet-room KINDS (ensuite / shared / guest WC) are discarded, so the model never states who a bathroom serves. (c) nothing says a wet room has exactly one door; the model freely proposes bathrooms with two or three doors (31 of 162 proposals). |
| **Harness translation** (`gap_closure_142a.resolve_wet_rooms`, `tests/vertical_slice/frozen_briefs.wet_rooms_of`) | infers a wet room's kind from its access graph: the FIRST bedroom entrant makes it an ENSUITE of that bedroom, else SHARED | a two- or three-door bathroom is silently read as "ensuite of bedroom X", and its other doors then surface downstream as "illegal door into an ensuite" (B07 BATHROOM_1: HALL + BEDROOM_1 + MASTER; B07 BATHROOM_2, B09 ×3, B20 BATHROOM_2). The kind was invented by the translation layer, never stated by the brief or the model. |
| **Policy table** (`access_rules.ALLOWED_ENTERED_FROM`, Issue #18) | the role-level "may A open into B" table; the only filter `best_policy_valid_proposal` applied | edge-wise only: it cannot see a room with several doors, so multi-door bathrooms pass as "policy-valid" (106 of 162 proposals pass it; only 59 are consistent). It already encodes specs/009 decision C — LIVING is a legal entry to a wet room. |
| **Duplicated rules** (C17 in `validation.py`, `rectilinear_realizer._wet_room_edge_allowed`) | the realized-door checks | written for specs/007 before 009: "a shared wet room only from HALL/CIRCULATION". Two answers for one door: the proposal layer and C24/C29 say LIVING is legal, C17 and the realizer's filter refused it → B12's `ACCESS_POLICY_CONFLICT`. |
| **POC critic score** (`topology_poc/critic.py`, priors) | ranks the proposals; the frozen one is the best-scored policy-valid proposal | its hard rules (`_hard_violations`) check zoning, entrance, raw reachability and bedroom-only access — none of the invariants below. For 14 of the 20 briefs the frozen choice is rank 0 and fails the critic, while a lower-ranked, consistent proposal passes production (§6). |
| **Exact embedding / selection** (#142E/#142H) | first place the contradiction is *computed* today | correct but late: the diagnosis is typed only after the whole pipeline ran. |

Per brief (fixture = `tests/fixtures/frozen_briefs_142.json`):

- **B06** (3 bedrooms, 2 wet rooms, 13×24 m). Access is clean. Spatial adjacency makes BATHROOM_2
  touch BATHROOM_1, BEDROOM_1, HALL **and LIVING** while no door uses any of those but HALL's.
  Exact SAT over *every* rectangular dissection (`data/b06_exposure_sat.json`, grid family
  W+H = P+1, UNSAT on all grids = proof): **no rectangular plan of any kind, band or not, exposes all
  five REQUIRED rooms** with this adjacency; dropping any one of BATHROOM_2–LIVING,
  BATHROOM_2–BEDROOM_1 or BATHROOM_1–BATHROOM_2 (none backed by a door) makes the band family
  exposure-feasible. Task §5: **(B) poor adjacency topology** — a wet-core clustering preference stated
  as a required contact — not (A) an over-strict exposure policy (the policy is the system's, and
  bedrooms/living/kitchen needing a window is not negotiable) and not (C) a representation limit.
- **B07** (3 bedrooms, 2 wet rooms, safe room). BATHROOM_1 has three doors (BEDROOM_1, HALL, MASTER),
  BATHROOM_2 two (BEDROOM_2, HALL); HALL→BATHROOM_1 and HALL→KITCHEN have no shared wall. Adding the
  two walls forces BATHROOM_2/BEDROOM_1/MASTER to touch both BATHROOM_1 and HALL — a triple lens, no
  rectangles. Knowable at the proposal: three-door bathroom + door without wall.
- **B09** (3 bedrooms, 3 wet rooms). Every bathroom has two doors (its bedroom + HALL);
  HALL→BATHROOM_3 has no wall (BATHROOM_3 touches BATHROOM_2 and MASTER only). Adding it gives
  BATHROOM_1/BATHROOM_3/BEDROOM_2 two common neighbours each with BATHROOM_2 and HALL — triple lens.
- **B12** (4 bedrooms, 3 wet rooms). LIVING→BATHROOM_3: legal under specs/009 (LIVING is the public
  fallback) — the `ACCESS_POLICY_CONFLICT` was the C17/realizer divergence, not the proposal.
  HALL→BATHROOM_2 has no wall (BATHROOM_2 touches BATHROOM_3, BEDROOM_1, BEDROOM_2). Once that
  contact is required, the complete band family (150 layouts) buries BEDROOM_1 in every one: the
  bathroom pair is wedged between the bedrooms and the living room.
- **B17** (6 bedrooms, 3 wet rooms, 18×12 m). HALL→BEDROOM_1/2/3/5 have no wall: the model placed
  BEDROOM_1/2/3 around BATHROOM_2 and BEDROOM_5 next to LIVING, with no contact to the hall they are
  entered from. Adding the four walls → BEDROOM_1/2/3 each touch both BATHROOM_2 and HALL — triple lens.
- **B20** (2 bedrooms, 3 wet rooms, safe room, open plan, 11×12 m). BATHROOM_2 has two doors
  (BEDROOM_1 + HALL); the loader read it as BEDROOM_1's ensuite, so the hall door became the
  "conflict". Also three full bathrooms for two bedrooms in 132 m² — the prompt's BATHROOM flattening
  (b) turned "ensuite + shared + guest WC" into three BATHROOM rooms with ROOM_TEMPLATES bathroom sizes.

## 2. Proposal invariants (task §2) — `ai_harness/topology_poc/proposal_critic.py`

Every proposal must satisfy, BEFORE embedding (HARD = the unchanged pipeline cannot pass it as written):

| | invariant | finding code | decided from |
|---|---|---|---|
| I1 | the house is entered through an ALLOWED_ENTRANCE role | `NO_ENTRANCE_ACCESS`, `ENTRANCE_INTO_NON_ENTRANCE_ROLE` | access graph |
| I2 | every direct-access pair is a legal door pair | `ILLEGAL_ACCESS_PAIR` | `access_rules.edge_role_pair_allowed` |
| I3 | a wet room has exactly ONE door | `WET_ROOM_MULTIPLE_ENTRANTS` | access graph (specs/007 FR-9) |
| I4 | that door comes from where the canonical wet-room policy allows | `WET_ROOM_ENTRY_POLICY` | `wet_room_policy.wet_room_entry_allowed` |
| I5 | a door needs a shared wall: access pairs are required contacts | `ACCESS_WITHOUT_CONTACT` (WARN, feeds I6/I8) | spatial vs access |
| I6 | spatial ∪ access is representable by rectangles (planar, no K4 / triple lens, has a band layout) | `ACCESS_SPATIAL_CONTRADICTION` (spatial alone embeds), `CONTACTS_NOT_REPRESENTABLE` | `representation_precheck` + exact embedder |
| I7 | every room is reachable from ENTRANCE through LEGAL doors | `UNREACHABLE_ROOM` | I2 + I4 |
| I8 | no REQUIRED-exposure room is buried in every band layout of the complete family | `EXPOSURE_INFEASIBLE` (HARD when complete, WARN within a bound) | embedder + `placement_flags` |
| I9 | every room has at least one door | `ROOM_WITHOUT_ACCESS` | access graph |

Not in the list yet (observed, not implemented): wet-room COUNT vs KIND consistency with the brief
(B20: three full bathrooms for two bedrooms, because kinds were flattened to BATHROOM); a room-count
vs footprint plausibility check (B17: 12 rooms in 216 m² sizes but never fits the band family).

## 3. The B12/B20 policy conflict, resolved (task §3) — `app/vertical_slice/wet_room_policy.py`

| source | said | since |
|---|---|---|
| `access_rules.ALLOWED_ENTERED_FROM` (C24 role table) | a wet room may be entered from HALL/CIRCULATION, its host bedroom, **or LIVING** | Issue #18, citing specs/009 decision C |
| `wet_privacy` C29 | fails closed only on KITCHEN/DINING; LIVING deliberately excluded "a legitimate corridor-class-adjacent entry (specs/009 §0 decision C)" | Issue #37 |
| specs/009 §0 decision C (owner decisions, 2026-09-14) | "foyer / hall → public circulation → living room. Never through a bedroom, never through the kitchen"; FR-4: "a public-access zone counts as circulation for this purpose even when it is the living room" | approved spec |
| **C17** (`validation.py`, specs/007 FR-9) | shared wet room "only from circulation" = HALL/CIRCULATION | 007, before 009 |
| **realizer `_wet_room_edge_allowed`** | copied C17 | #142A |

Why they differ: 009 refined 007's "from circulation" after 007 had been implemented; the role table
and C29 were written after 009 and followed it, C17 and the realizer filter were not revisited. The
intended architectural semantics is decision C: a shared wet room / guest WC is entered from the
public-access side, hall first, living room as the last fallback, never a bedroom (unless it is that
bedroom's ensuite) and never kitchen/dining; preference among the legal entries is a ranking concern
(`wet_privacy.candidate_privacy_key`), not a gate.

Resolution — one canonical source, both consumers derived (nothing weakened by hand):
`wet_room_policy.wet_room_entry_allowed(wet, entrant, roles)` and `entry_rank` (host/circulation 0,
LIVING fallback 1, forbidden 99). `access_rules` builds the wet roles' entry set from it; C17 holds a
realized wet room to **exactly one door** from an allowed entrant; the realizer's filter admits only
allowed entrants and, because C17 wants one door, only the best-ranked class among them (a shared
bathroom touching both hall and living gets its hall door, not two doors — without this, B13's three
bathrooms each got a hall AND a living door and failed C17); the band pipeline's legality and
`access_policy_conflicts` use the same function. `tests/vertical_slice/test_wet_room_policy.py` pins
the rule and that the four consumers agree; `test_c17_bathroom_access.py` is unchanged and green.

Effect on B12/B20: B12's LIVING door is legal; B12 then fails on its real defect (§1: the wall-less
hall door into BATHROOM_2 buries BEDROOM_1 in the complete family) — `EXPOSURE_INFEASIBLE`, repaired
to PASS in §5. B20 is unchanged: a two-door bathroom is a proposal defect under either policy.
**This changes C17's semantics (a shared bathroom entered from LIVING now passes) — an owner decision
to confirm at merge; the alternative (keep 007's strict reading) is one constant,
`PUBLIC_FALLBACK_ENTRY_ROLES = frozenset()`, and would turn the role table and C29 strict too.**

## 4. Critic results on the frozen suite (task §6, §8)

| Brief | Current diagnosis (#142H production) | Critic detects? | Minimal repair exists? | PASS after repair? |
|---|---|---|---|---|
| B06 | EXPOSURE_INFEASIBLE (complete family 58) | yes — EXPOSURE_INFEASIBLE (HARD, complete) | yes (1): demote BATHROOM_2–LIVING to preferred | **PASS** (access 7/7) |
| B07 | ACCESS_SPATIAL_CONTRADICTION | yes — MULTIPLE_ENTRANTS ×2, ENTRY_POLICY ×3, ACCESS_SPATIAL_CONTRADICTION (triple lens named) | yes (5): one door per bathroom (HALL kept; alternatives recorded), HALL→KITCHEN re-routed as LIVING→KITCHEN, HALL–BATHROOM_1 kept as contact, BATHROOM_1–BEDROOM_1 demoted | **PASS** (10/10) |
| B09 | ACCESS_SPATIAL_CONTRADICTION | yes — MULTIPLE_ENTRANTS ×3, ENTRY_POLICY ×3, CONTRADICTION | yes (5): one door per bathroom, HALL–BATHROOM_3 kept as contact, BATHROOM_2–BEDROOM_2 demoted | **PASS** (9/9) |
| B12 | ACCESS_POLICY_CONFLICT → EXPOSURE_INFEASIBLE under the aligned policy | yes — EXPOSURE_INFEASIBLE (complete 150) + ACCESS_WITHOUT_CONTACT | yes (2): HALL–BATHROOM_2 kept as contact, BATHROOM_2–BATHROOM_3 demoted | **PASS** (9/9) |
| B17 | ACCESS_SPATIAL_CONTRADICTION | yes — CONTRADICTION (lens named) + 4 wall-less doors | consistent after 6 repairs (4 contacts kept, BATHROOM_3–LIVING and BATHROOM_2–BEDROOM_1 demoted) | **no** — SIZING_INFEASIBLE: 54 HARD-feasible of 216 layouts (bound 800), none sizable; 12 rooms at template sizes in 18×12 m |
| B20 | ACCESS_POLICY_CONFLICT | yes — MULTIPLE_ENTRANTS + ENTRY_POLICY | consistent after 1 repair (either reading: shared from HALL, or ensuite of BEDROOM_1) | **no** — NO_ENTRANCE within 120 layouts, SIZING_INFEASIBLE with 800 (8 HARD-feasible, none sizable): 10 rooms incl. 3 full bathrooms + safe room in 11×12 m |
| B01 B04 B05 B08 B11 B13 B18 | PASS | **no HARD finding** (0 false positives) | — | PASS (unchanged) |
| B02 B03 B10 B14 B15 B16 | TOPOLOGY_REPRESENTATION_LIMIT | CONTACTS_NOT_REPRESENTABLE (+ multi-door bathrooms in B02/B10/B15/B16) | out of scope here; see §6 | — |
| B19 | TOPOLOGY_NON_PLANAR | CONTACTS_NOT_REPRESENTABLE (non-planar) | — | — |

Frozen suite: **7/13 before, 7/13 after the policy alignment alone (B12 re-typed), 11/13 after the
repair experiment.** Critic runtime per brief 0.0–1.1 s (embedding dominated).

## 5. Repair experiment (task §7) — `ai_harness/topology_poc/proposal_repair.py`

Clearly labelled, harness only, never wired into production. Rules, applied only when the critic
reports the matching finding, each recorded with original relation, changed relation, reason and
evidence: **R1** one door per wet room (keep the circulation door the proposal asked for — the room is
then the shared bathroom that door implies; each bedroom that lost its direct door still reaches it in
2 legal steps, recorded; the ensuite reading is recorded as an alternative, not applied);
**R2** an illegal single entrant is re-doored from a legal touching neighbour (never fired on this
suite); **R3** a wall-less door is re-routed through a legal touching neighbour reachable from the
source (B07: HALL→KITCHEN becomes LIVING→KITCHEN) or, when no legal entrant touches the target, kept
as a required contact (what production does); **R4** the smallest set of contacts NO door uses whose
demotion to "preferred" makes spatial ∪ access representable (wet↔public first, then wet↔bedroom,
wet↔wet); **R5** the same demotion for exposure. No rule invents a room, changes a role or adds a door
(pinned by `tests/ai_harness/test_proposal_critic_142i.py`). What the repairs touched: 7 doors removed
(all second/third doors of bathrooms), 1 door re-routed, 6 contacts kept as required, 6 contacts
demoted to preferred, 0 rooms, 0 roles. Figures: `figures/B06|B07|B09|B12_repaired_plan.png`.

On the architecturally correct correction (task §4): for B07/B09 the one-door rule is the fix and the
choice of WHICH door is a brief question (the brief says "3 bedrooms, 2 wet rooms" for B07 — at least
one bathroom must be shared, so keeping the hall doors is the reading that serves every bedroom;
"master ensuite + shared" is the recorded alternative and should be asked, not guessed). For B17 the
correct correction is upstream: a bedroom entered from the hall must touch the hall — the model's
adjacency put the bedrooms around a bathroom instead; demoting two bathroom contacts repairs the
contradiction but the 12-room programme still does not size in 18×12 m, so the right fix is a
different proposal (three exist, §6). For B06/B12 the correction is to state wet-core clustering as a
preference, not a required wall.

## 6. The dataset view: it is the selection, not the geometry

Over all 162 proposals (`data/critic_results.json`, `dataset`): 106 pass the edge-wise access-rules
filter the frozen set used; **59 are critic-clean; 51 of those pass production as they stand.**
HARD findings per code: ILLEGAL_ACCESS_PAIR 56, UNREACHABLE_ROOM 57, WET_ROOM_MULTIPLE_ENTRANTS 31,
WET_ROOM_ENTRY_POLICY 30, ACCESS_SPATIAL_CONTRADICTION 17, CONTACTS_NOT_REPRESENTABLE 15,
EXPOSURE_INFEASIBLE 6, ENTRANCE_INTO_NON_ENTRANCE_ROLE 1, ROOM_WITHOUT_ACCESS 1.

Per brief, the rank of the frozen choice vs the ranks of critic-clean proposals that PASS production:

| brief | frozen rank → critic | clean & PASS ranks | | brief | frozen rank → critic | clean & PASS ranks |
|---|---|---|---|---|---|---|
| B01 | 0 clean | 0, 1, 6 | | B11 | 2 clean | 2, 6, 7, 8 |
| B02 | 1 HARD | 3, 4, 5, 6, 7, 8 | | B12 | 0 HARD | **none** |
| B03 | 0 HARD | 4, 5 | | B13 | 0 clean | 0, 2, 5 |
| B04 | 0 clean | 0, 4, 5 | | B14 | 0 HARD | 1, 3, 5 |
| B05 | 0 clean | 0, 1, 4 | | B15 | 0 HARD | 7 |
| B06 | 0 HARD | 2, 3, 4, 5, 7 | | B16 | 0 HARD | 1 |
| B07 | 0 HARD | 1, 2, 6, 7 | | B17 | 1 HARD | 2, 6, 7 |
| B08 | 0 clean | 0, 1 | | B18 | 0 clean | 0 |
| B09 | 0 HARD | 2, 4, 5, 6 | | B19 | 0 HARD | 1 |
| B10 | 0 HARD | 6 | | B20 | 0 HARD | 7 |

**19 of 20 briefs already have a consistent proposal that the unchanged production pipeline realizes
and validates** — including the six briefs #142B classified as needing an L-shaped room and the
non-planar B19. Those classifications were true of the *chosen proposal*, not of the brief. Only B12
has no clean proposal in its eight (it passes after the two-step repair). The clean-but-failing cases
(8 of 59) are SIZING_INFEASIBLE / one SAFE_ROOM C4 (B11 rank 4) / one EXPOSURE within the bound.

## 7. Recommendation for the next bounded step

1. **Gate proposals with the critic before scoring** (deterministic, < 1 s): rank only critic-clean
   proposals; a brief with none gets the typed findings back to the proposer (regenerate with the
   findings in the prompt), never a repaired guess. Expected on this suite: 19/20 with existing
   proposals, no realizer change.
2. **Fix the prompt**: delete the "accessed but not touching" licence (a door needs a shared wall:
   `access ⊆ adjacency`), state "a wet room has exactly one door", and pass wet-room KINDS (ensuite /
   shared / guest WC, with hosts) instead of flat `BATHROOM_i`.
3. **Resolve kinds from the brief, not from the access graph**: `resolve_wet_rooms` in
   `gap_closure_142a`/`frozen_briefs` invents an ensuite from the first bedroom door; the programme's
   own `wet_rooms.resolve_wet_rooms` already carries kinds — use it, and report a mismatch as a finding.
4. **Owner decision on §3**: confirm specs/009 decision C as the canonical wet-room entry rule (this
   PR) or set `PUBLIC_FALLBACK_ENTRY_ROLES` empty — either way one source.
5. Only after 1–3: re-measure. The remaining geometric questions (B17/B20's sizing, L-shaped rooms)
   should be asked of consistent proposals; today none of the six needs them.

## 8. Regression

Full backend suite with the policy alignment (shared dev venv): 1938 passed, 883 skipped, 9 xfailed,
0 failures; `tests/ai_harness/test_proposal_critic_142i.py` 20 passed; `test_c17_bathroom_access.py`
unchanged and green; frozen suite 7/13 production, 11/13 with the (unwired) repair experiment.

## 9. Scope kept (task §9)

No L-shaped rooms, no realizer geometry change, no validator weakened (C17 now derives from the
canonical policy and additionally requires exactly one door), no access requirement dropped silently
(every repair is recorded and the repair module is not wired anywhere), no exposure relaxed, no
frozen brief special-cased, no LLM rewriting. Production changes in this PR: `wet_room_policy.py`
and its four consumers; the regression suite's typed expectation for B12 (EXPOSURE_INFEASIBLE under
the aligned policy); the SELECTION detail now names the family size, not the candidate cap.
