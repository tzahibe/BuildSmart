# #142J — Production proposal quality gate

**Final question.** Can we make the system choose an already-existing valid proposal for at least 19
of the 20 briefs simply by fixing proposal semantics and rejecting inconsistent candidates before
scoring, without changing the geometric engine?

**Answer: yes — 19/20, with the geometric engine, the validators and the realizer untouched.** The
production flow is now `brief → candidates → critic → keep clean → score → select → realizer`. On the
frozen LLM dataset (162 proposals, 20 briefs, generated under the OLD prompt) the gate selects a
critic-clean proposal that the unchanged pipeline realizes and validates for 19 briefs, up from 7 with
the old `score → first access-rules-valid → realizer` flow. In every one of the 19 the **best-scored
clean candidate** realized at the first attempt. B12, whose eight candidates all carry HARD findings,
returns the typed `NO_VALID_PROPOSAL` with every finding attached — the honest negative control. The
six briefs #142B classified as "needs an L-shaped room" and the non-planar B19 pass because a different,
consistent proposal from the same candidate set is chosen.

Data: `data/selection_matrix.json` (per brief: every candidate's verdict, scores, old/new selection,
pipeline result, quality metrics). Figures: `figures/B*_gate_plan.png` (the 19 selected plans).

## 1. What is production now (task §1, §2, §5, §6, §7)

| | module | behaviour |
|---|---|---|
| critic | `app/vertical_slice/proposal_critic.py` | invariants I1–I9 on the proposal alone, before any embedding: entrance role; legal door pairs (`access_rules`); **one door per wet room**; door from where the canonical `wet_room_policy` allows; **wet-room kinds from the brief** (I4b, below); a door needs a wall (`ACCESS_WITHOUT_CONTACT` → required contact); representability of spatial ∪ access (K4 / triple lens / non-planar / BAND_UNSAT are HARD; a search bound hit is WARN `REPRESENTABILITY_UNKNOWN`); reachability through legal doors; exposure (`EXPOSURE_INFEASIBLE` only for a complete family, else WARN `EXPOSURE_UNKNOWN`); every room has a door. UNKNOWN never rejects. |
| selection | `app/vertical_slice/proposal_selection.py` | `select_proposal(candidates, score, footprint)`: criticize all → clean set → score ONLY the clean ones → order by (score desc, index) → run the unchanged `run_band_pipeline` on them in order → first PASS wins (`ProposalSelection`, with `clean_rank`, the verdicts of every candidate and the candidates tried before). No clean candidate → `NoValidProposal` (every candidate's findings, never the least-bad). Clean but none realizes → `NoRealizableProposal` with the typed pipeline diagnoses. Nothing is repaired anywhere. |
| wet-room policy | `app/vertical_slice/wet_room_policy.py` (#142I) | the one rule every consumer derives from — access table, C17, realizer door filter (best-ranked door class), band pipeline legality, critic. ENSUITE: one door from its host. SHARED_BATHROOM / GUEST_WC: one door, HALL/CIRCULATION first, LIVING as the public fallback; never a non-host bedroom, KITCHEN, DINING. |
| declared doors | `rectilinear_realizer._filter_wet_room_access` | a DECLARED legal wet-room door (`GridWing.access_pairs`, #142H) is the one door built; only when the layout declares none does the best-ranked class (#142I) decide. Found on B10: the proposal's LIVING→BATHROOM door (a legal fallback) was being replaced by the hall the bathroom also touched — 7 of 8 declared doors preserved; now 8/8. Door selection policy, not geometry. |
| brief kinds | `ai_harness/topology_poc/briefs.brief_wet_room_kinds` | the brief's declared kinds (`WetRoomRequirement`): stated kinds from the context are EXPLICIT; otherwise the programme's own count-derived defaults (`wet_rooms.default_wet_room_kinds`) with origin COUNT_DERIVED. |

**I4b — the brief is the source of truth.** `assign_wet_room_kinds` matches the declared kinds to the
proposal's wet rooms deterministically, specified kinds first: a SPECIFIED ensuite must exist with its
declared host, a specified shared bathroom / guest WC with public access, else HARD
`WET_ROOM_KIND_MISSING`; more wet rooms than counted → HARD `WET_ROOM_COUNT_MISMATCH`. A COUNT-DERIVED
default the person never stated is a class hint: the proposal's reading is adopted (recorded
`specified=False`, origin COUNT_DERIVED) and a WARN `WET_ROOM_KIND_DIFFERS_FROM_DEFAULT` notes the
difference. The matched `ResolvedWetRoom`s are what the pipeline hands to the realizer and C17 — the
harness's old "ensuite of whichever bedroom has a door" inference is gone from the production path
(kept only in the harness shim for the #142I repair experiment).

## 2. The proposer prompt (task §3, §4) — `ai_harness/topology_poc/prompt.py`

Removed: *"or be joined by a door across a corridor (accessed but not touching)"*. Added, in the system
prompt: a direct door REQUIRES a shared wall and every access pair must appear in `spatial_adjacency`;
a corridor between A and B is A→corridor and corridor→B, never A→B; every wet room has EXACTLY ONE
door; an ENSUITE is entered only from its one host bedroom; SHARED_BATHROOM / GUEST_WC from the public
side (hall/circulation, living as fallback), never bedroom/kitchen/dining; `spatial_adjacency` is a HARD
requirement, "near / clustered / wet core" preferences go to `clusters` and `relative_position`. The
room programme now carries the brief's kinds and hosts —
`BATHROOM_1(BATHROOM, ENSUITE of MASTER: exactly one door, from MASTER only)`,
`TOILET_1(TOILET, GUEST_WC: exactly one door, from HALL/circulation or LIVING)`,
`BATHROOM_2(BATHROOM, SHARED_BATHROOM: …)` — instead of a flat list of BATHROOMs. The corpus-facts
preamble (`context.py`) keeps "adjacency is not access" and now adds "(but a door needs a wall)".
Pinned by `tests/ai_harness/test_topology_prompt_142j.py`. The frozen dataset was generated under the
old prompt; §3 below is therefore a measurement of the GATE, not of the new prompt.

## 3. The 20-brief matrix (task §9)

Old = `gap_closure_142a.best_policy_valid_proposal` (best POC score among access-rules-valid
candidates) + harness wet-room inference + the unchanged pipeline. New = the production gate. Ranks are
positions in the POC score order (0 = best score). Scores are the POC critic's `total_score`.

| brief | generated | HARD-invalid | clean | clean & PASS ranks | old rank → result | new rank (clean rank) → result | score old → new |
|---|---:|---:|---:|---|---|---|---|
| B01 | 7 | 4 | 3 | 0, 1, 6 | #0 → PASS | #0 (0) → PASS | 0.652 → 0.652 |
| B02 | 9 | 3 | 6 | 3, 4, 5, 6, 7, 8 | #1 → TOPOLOGY_REPRESENTATION_LIMIT | #3 (0) → **PASS** | −1.897 → −1.897 |
| B03 | 8 | 6 | 2 | 4, 5 | #0 → TOPOLOGY_REPRESENTATION_LIMIT | #4 (0) → **PASS** | 0.272 → −0.720 |
| B04 | 8 | 5 | 3 | 0, 4, 5 | #0 → PASS | #0 (0) → PASS | −1.071 → −1.071 |
| B05 | 8 | 5 | 3 | 0, 1, 4 | #0 → PASS | #0 (0) → PASS | −0.039 → −0.039 |
| B06 | 8 | 3 | 5 | 2, 3, 4, 5, 7 | #0 → EXPOSURE_INFEASIBLE | #2 (0) → **PASS** | −0.720 → −1.480 |
| B07 | 8 | 4 | 4 | 1, 2, 6, 7 | #0 → ACCESS_SPATIAL_CONTRADICTION | #1 (0) → **PASS** | −0.643 → −0.643 |
| B08 | 6 | 4 | 2 | 0, 1 | #0 → PASS | #0 (0) → PASS | 0.515 → 0.515 |
| B09 | 8 | 4 | 4 | 2, 4, 5, 6 | #0 → ACCESS_SPATIAL_CONTRADICTION | #2 (0) → **PASS** | 0.298 → −0.395 |
| B10 | 9 | 8 | 1 | 6 | #0 → TOPOLOGY_REPRESENTATION_LIMIT | #6 (0) → **PASS** | 0.609 → −2.994 |
| B11 | 9 | 4 | 5 | 2, 6, 7, 8 | #2 → PASS | #2 (0) → PASS | −1.624 → −1.624 |
| B12 | 8 | 8 | 0 | — | #0 → EXPOSURE_INFEASIBLE | — → **NO_VALID_PROPOSAL** | 0.199 → — |
| B13 | 8 | 3 | 5 | 0, 2, 5 | #0 → PASS | #0 (0) → PASS | 0.825 → 0.825 |
| B14 | 8 | 5 | 3 | 1, 3, 5 | #0 → TOPOLOGY_REPRESENTATION_LIMIT | #1 (0) → **PASS** | −0.112 → −0.372 |
| B15 | 8 | 7 | 1 | 7 | #0 → TOPOLOGY_REPRESENTATION_LIMIT | #7 (0) → **PASS** | 0.902 → −3.033 |
| B16 | 8 | 6 | 2 | 1 | #0 → TOPOLOGY_REPRESENTATION_LIMIT | #1 (0) → **PASS** | 1.190 → −1.683 |
| B17 | 9 | 5 | 4 | 2, 6, 7 | #1 → ACCESS_SPATIAL_CONTRADICTION | #2 (0) → **PASS** | −1.697 → −1.724 |
| B18 | 8 | 5 | 3 | 0 | #0 → PASS | #0 (0) → PASS | −0.035 → −0.035 |
| B19 | 8 | 6 | 2 | 1 | #0 → TOPOLOGY_NON_PLANAR | #1 (0) → **PASS** | −0.372 → −0.728 |
| B20 | 9 | 8 | 1 | 7 | #0 → ACCESS_POLICY_CONFLICT | #7 (0) → **PASS** | 0.349 → −2.616 |
| **total** | **162** | **103** | **59** | **51 clean & PASS** | **7/20 PASS** | **19/20 PASS** | |

HARD findings over the 162 candidates: UNREACHABLE_ROOM 57, ILLEGAL_ACCESS_PAIR 56,
WET_ROOM_MULTIPLE_ENTRANTS 31, WET_ROOM_ENTRY_POLICY 30, ACCESS_SPATIAL_CONTRADICTION 17,
CONTACTS_NOT_REPRESENTABLE 15, EXPOSURE_INFEASIBLE 6, ENTRANCE_INTO_NON_ENTRANCE_ROLE 1,
ROOM_WITHOUT_ACCESS 1. WARNs: WET_ROOM_KIND_DIFFERS_FROM_DEFAULT 94 (the briefs state no kinds; the
defaults are hints), ACCESS_WITHOUT_CONTACT 39, EXPOSURE_UNKNOWN 4 (bounded, never a rejection).
No candidate was rejected on an UNKNOWN. Every selected candidate was the top-scored clean one
(`tried_before` empty for all 19); the fall-through to the next clean candidate never fired.

Reproduces the #142I evidence exactly (59 clean, 51 clean & PASS, 19/20 with a clean passing
candidate) — now from the production modules, with the brief's wet-room kinds instead of the harness
inference, and with the realizer deciding.

## 4. The surprising cases (task §10)

B02, B03, B10, B14, B15, B16 (formerly `TOPOLOGY_REPRESENTATION_LIMIT`: K4 / triple-lens
obstructions, "one L-shaped room fixes each" in #142B) and B19 (formerly `TOPOLOGY_NON_PLANAR`) pass.
In each case the OLD selection (rank 0 or 1 by score) still carries its obstruction — the critic reports
`CONTACTS_NOT_REPRESENTABLE` on it, usually together with multi-door bathrooms — and the gate picks a
LOWER-scored candidate from the same set whose contacts are representable by plain rectangular bands.
No L-shaped room, no new embedding family, no relaxed contact: every one of the 19 passes preserves every
declared door (`access n/n`) and every required contact (`spatial n/n`), through the unchanged `embed_band`,
`solve_band_layout`, `realize_layout` and `validate` (`test_former_representation_limit_briefs_pass_by_choosing_another_proposal`).
The #142B classification was correct for the proposal it looked at; the brief never needed richer geometry.

## 5. Quality, not only PASS count (task §12)

Existing metrics only, read off the realized plans (`quality` in the matrix): the 7 briefs that passed
before select the SAME proposal as before (identical plans, identical scores). For the 12 newly passing
briefs versus those 7:

| group | circulation share (median) | mean net aspect (median) | max net aspect (median) | PREFERRED-exposure rooms on the envelope |
|---|---:|---:|---:|---|
| same as old (7) | 0.152 | 1.64 | 2.40 | 11 / 12 |
| newly selected (12) | 0.142 | 1.63 | 2.96 | 26 / 27 |

Circulation share, average room proportion and preferred exposure are the same or better; the worst
single room is somewhat more elongated (max 4.4 in B16's hall, within its own template bound — C3
bounds every room). The POC score of the selected candidate is lower than the old choice's for 11 of the
12 (the old score rewarded the inconsistent proposals); whether that score should be re-weighted is a
separate question — this task did not touch it. Visual check: `figures/*_gate_plan.png`, 19 plans, none
degenerate (hall hub, bedrooms on the envelope, one door per wet room).

## 6. Determinism (task §11)

Criticism, scoring order (score desc, then candidate index) and selection are pure functions of the
candidate list. `test_selection_is_deterministic_across_processes_and_hash_seeds` runs the gate on
B02/B19/B12 in three separate interpreters with `PYTHONHASHSEED` 1, 2 and random and compares the
selected index, clean rank and every realized rectangle; `test_selection_is_deterministic` repeats in
process with tied scores (lowest index wins).

## 7. Tests and regression

- `tests/vertical_slice/test_proposal_selection.py` (7): clean proposal + brief kinds assigned; two-door
  bathroom / wall-less door are HARD; a HARD-invalid candidate with score 10 loses to a clean one with
  score 1 and is never scored; all-invalid → `NO_VALID_PROPOSAL` with findings; specified kinds are the
  source of truth (`WET_ROOM_KIND_MISSING`) while count-derived defaults only WARN; count mismatch is
  HARD; determinism.
- `tests/ai_harness/test_proposal_quality_gate_142j.py` (12): ≥ 19/20, selected candidates clean and
  best-scored among the clean, B12 negative control, the seven former-limit briefs pass by a different
  rank with every door realized, old passes keep their proposal, quality bounds, cross-process
  determinism.
- `tests/ai_harness/test_topology_prompt_142j.py` (4): the prompt rules and the kinds in the programme.
- #142I's critic/repair tests (20) keep passing through the harness shim; `test_wet_room_policy.py`,
  `test_c17_bathroom_access.py`, the band and realizer suites unchanged.
- Full backend suite (shared dev venv): 1953 passed, 883 skipped, 9 xfailed, 0 failures; the gate test file (12,
  ~100 s incl. three subprocess runs) and the band-selection tests (16) green separately.

## 8. Scope kept (task §13)

No L-shaped rooms, no realizer or embedder change, no validator weakened (C17 derives from the one
policy and requires exactly one door, as in #142I), no automatic repair (the #142I repair module is
harness-only and not called), no LLM rewriting, no adjacency or access requirement dropped (a wall-less
door becomes a REQUIRED contact), no frozen brief special-cased, no scoring change — the POC score is
used as-is on the clean candidates. B12 stays unrepaired. The frozen-brief regression suite
(`test_band_pipeline_regression.py`, the OLD selections) is unchanged at 7/13: it measures the pipeline,
not the gate.

## 9. Next bounded step

Regenerate the 20 briefs with the corrected prompt (kinds and hosts in the programme, door-needs-wall,
one door per wet room) and measure the critic-clean rate per brief; wire `NoValidProposal`'s findings
into a controlled regeneration prompt; decide whether the POC score should be re-weighted now that only
consistent candidates reach it.
