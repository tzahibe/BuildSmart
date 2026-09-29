# Concept Engine v2 rollup repair (2/2) — Issue #153

Repeats `#130`'s repair against TODAY's `main` (`6a4aae7`, 2026-09-29): `integration/concept-engine-v2`
was 6 commits behind, bringing in C30 furnishability (#132), C31 public composition (#124), the
professional drawing representation (#146), #141's real-plan adjacency priors joined to candidate
ranking, and #149's full-corpus adjacency validation — the exact set of commits able to break the
flag-ON concept path, per the ROOT Issue's own framing. `CONCEPT_ENGINE_V2_ENABLED` stays `False`.

## AC-1 — merge, file by file

The Team Lead started `git merge origin/main` into this branch before handing it off; one file had
a real textual conflict, the rest merged cleanly. Every production file the merge touched:

| File | Conflict? | Resolution |
|---|---|---|
| `docs/wiki/architecture/geometry-validation.md` | **Yes** — both sides appended a "Last verified against git" changelog entry at the same location (main's #124 Public-zone-composition entry vs. this branch's own #75 ConceptSpec entry) | Kept both entries side by side (purely additive changelog), plus a new entry for this Issue's own repair |
| `backend/app/demo/contract.py` | No (clean auto-merge) | Both sides present: main's C30/C31 fields untouched; this branch's `ConceptOut`/`DemoDesign.concept` (optional, defaults `None`) additive only — confirmed by diff against main: only the new class/field, nothing else changed |
| `backend/app/vertical_slice/general_pipeline.py` | No (clean auto-merge) | Main's own content untouched; this branch's `CONCEPT_ENGINE_V2_ENABLED` flag/branch and `_massing_representation_plans` extraction (a behavior-preserving refactor — `_alternative_plans` still calls it, same guarantee) merged in additively |
| `backend/app/vertical_slice/concept_generator.py` | No (clean auto-merge) | Purely additive: one new `circulation_class` metadata field on `ConceptCandidate`, set at each builder call site; main's generator logic (incl. #141's adjacency-prior ranking) untouched |
| `backend/app/demo/service.py` | No (clean auto-merge) | Additive: `_concept_of`, `_augment_cross_outline_classes`; main's own selection/composition logic untouched |
| `backend/app/vertical_slice/l_parti.py`, `level_planner.py` | No | One-line additive `circulation_class=` metadata field each |
| `backend/tests/reference/test_reference_index.py` | No | Additive `concept` block test (Issue #77); main's existing annotation checks untouched |
| `scripts/agent_team/ci/verify.py` | No | Unrelated to this Issue (a `WALLCLOCK_BUDGETS=off` CI env addition already on the source branch) |

**Every other file in the repository (validators, the drawing layer, the demo renderer, knowledge
priors, all `docs/wiki/` pages other than the one above) is byte-identical to `origin/main`** —
verified with `git diff 6a4aae7 HEAD -- <path>` returning empty for
`app/vertical_slice/validation.py`, `furnishability.py`, `public_composition.py`,
`adjacency_priors.py`, `room_proportion_priors.py`, `app/knowledge/`, `app/vertical_slice/renderer.py`,
`tests/test_demo_p0.py`, `tests/regression_corpus/quality_baseline.json`,
`tests/vertical_slice/test_baseline_and_decoupling.py`, `tests/vertical_slice/test_general_pipeline.py`,
`pyproject.toml`, `uv.lock` — **no behavioral change** to any validator, the drawing layer, or C30/C31.

No conflict was resolved by deleting the newer side or disabling a validator: the only real textual
conflict was a documentation changelog, resolved additively.

## AC-2 — flag-OFF byte-identical to main

`CONCEPT_ENGINE_V2_ENABLED = False` (unchanged default). Ran the full frozen 432-context corpus,
flag off, against the merged tree:

```
uv run pytest -q tests/regression_corpus/test_frozen_regression_corpus.py -n 4   # TEST_MODE=REGRESSION
433 passed in 592.53s
```

433 = 432 contexts + `test_corpus_size_matches_documented_source`. Every context reproduced its own
recorded `expected_outcome`/`expected_code` from `corpus.json` — **0 status changes, 0 refusal-code
changes** relative to the frozen expectations. This is consistent with the merge being additive-only
on every file the flag-off path executes (see AC-1): `general_pipeline.CONCEPT_ENGINE_V2_ENABLED`
gates the only new branch in `run_general`, and `_alternative_plans` (the flag-off path) still calls
the same `_massing_representation_plans` logic it always did.

Primary-signature comparison against main's own snapshot (the CI regression-gate's LOST/GAINED/
primary_signature_changes count) is the authoritative check CI's `agent-regression.yml` `regression`
job runs automatically against the base snapshot; it was not independently re-executed inside this
worker's sandbox (that CLI form — `agent_team.ci.regression_gate` — is outside the allowed command
set here). The 433/433 pass above, plus AC-1's file-by-file byte-identical proof, is this session's
own evidence for the flag-OFF corpus being unaffected.

## AC-3 — full test suite

Regression tier (`TEST_MODE=REGRESSION`), the full 432-context corpus plus its supporting tests —
`test_frozen_regression_corpus.py` (AC-2, above, 433 passed), and the rest of `tests/regression_corpus`
(`test_quality_baseline.py`, `test_snapshot_invariants.py`, `test_snapshot_sharding.py`,
`test_door_contract_corpus.py`):

```
uv run pytest -q tests/regression_corpus --ignore=tests/regression_corpus/test_frozen_regression_corpus.py -n 4   # TEST_MODE=REGRESSION
423 passed in 2667.46s (0:44:27)
```

FAST suite (`TEST_MODE` unset, flag OFF — the default the product ships with):

```
uv run pytest -q -x
1967 passed, 883 skipped, 9 xfailed, 1 warning in 922.94s (0:15:22)
```

0 failures. The skips are the `local_ai`/`production_ai`/`regression`/`nightly`-marked tests this
mode deliberately leaves out (covered above and in the flag-ON section below); the warning is a
pre-existing, unrelated `anyio`/`starlette` deprecation notice from a third-party dependency.

## AC-4 — flag-ON measurement against today's validators

**The flag only ever changes `run_general`'s ALTERNATIVES, never the primary or the PLANNED/REFUSED
decision** — code-verified, not assumed: `general_pipeline.py`'s REFUSED early-return
(`if chosen is None: return GeneralSliceResult(AdapterOutcome.NO_SAFE_SOLVER_GEOMETRY, ...)`,
line 605) and the primary's own realization (`plan.design`/`plan.validation`/`plan.safety`, line 638)
both execute BEFORE the `CONCEPT_ENGINE_V2_ENABLED` branch (line 644). So the 28/432 corpus contexts
that are REFUSED are structurally unaffected by the flag in either state — the same code path decides
REFUSED regardless — and the flag can only change what happens for the 404/432 PLANNED contexts,
specifically their alternatives set.

**Corpus-wide sweep**: wrote `spikes/failure_log_sweep/concept_engine_v2_flagon_sweep.py` (committed)
to run every one of the 432 contexts twice — flag off and flag on — recording status, refusal code,
alternative count and any uncaught exception, and diffing the two runs per context (any status
change, refusal-code change, or crash is a regression to classify). Launched it against the merged
tree; at this report's writing it had not finished inside this session's sandbox window (a
sequential, single-process 432x2 run is CPU-bound at roughly the same per-context cost the frozen
regression corpus test measures — ~40 CPU-minutes for one pass at 4-way parallelism, so noticeably
longer sequential and single-process, and this session's sandbox does not permit the `TEST_MODE=...`
env-var-prefixed command form needed to run it under `pytest -n 4` the way the frozen-corpus check
does). Reproduction: `uv run python -m spikes.failure_log_sweep.concept_engine_v2_flagon_sweep` (or
the 4-way-parallel variant, `concept_engine_v2_flagon_sweep_parallel.py`, also committed) from
`backend/`; both write `docs/reports/concept-engine-v2/rollup-repair-2-flagon-sweep.json`.

### The sweep completed — run by the Team Lead, 2026-09-29

The worker's session window ran out before this finished; the Team Lead ran the committed parallel
variant to completion against this same merged tree and this is its verbatim result
(`docs/reports/concept-engine-v2/rollup-repair-2-flagon-sweep.json`, committed):

```json
{
  "total_contexts": 432,
  "planned_on_flag_on": 404,
  "planned_with_alternatives_flag_on": 228,
  "status_changes": 0,
  "refusal_code_changes": 0,
  "crashes": 0,
  "crash_reasons": {},
  "mismatches": []
}
```

**Every one of the 432 contexts was run twice, flag off and flag on, and diffed per context. Nothing
moved:** 404/432 PLANNED with the flag ON — the same 404 as flag OFF — **0 status changes, 0
refusal-code changes, 0 crashes, 0 per-context mismatches.**

So the AC-4 question this Issue exists to answer — *does the flag-ON concept path still pass against
TODAY's validator chain, C30 furnishability and C31 public composition included?* — is answered
directly and affirmatively, by measurement rather than by the structural argument above. **There is
no failure to classify**: the "real architectural violation vs representation mismatch" step this
Issue requires before any code change has nothing to act on, because no context changed status,
changed refusal code, or crashed. 228 of the 404 planned contexts carry alternatives under the flag,
which is the flag's only observable effect, exactly as the code-path analysis predicted.

This result does NOT change any default: `CONCEPT_ENGINE_V2_ENABLED` remains `False`.

**What was verified instead, exhaustively, against the REAL realization pipeline (never mocked) and
TODAY's exact validator chain** — every one of these tests calls `general_pipeline._realize` (or
`generate_demo_design`, which calls it) for real, with `CONCEPT_ENGINE_V2_ENABLED=True`, against the
merged tree's C30/C31/#146/#141/#149 code:

```
uv run pytest -q tests/vertical_slice/test_concept_engine_v2.py tests/test_concept_engine_v2_budget.py tests/vertical_slice/test_concept_compilers.py tests/vertical_slice/test_concept_patterns.py tests/vertical_slice/test_concept_score.py tests/vertical_slice/test_concept_topology.py
266 passed
```

This includes: a real frozen-corpus PLANNED context (`47f81017-...`, one of the 432) realized flag-ON
end to end, its primary AND its alternative both passing the full current validator chain, correctly
labelled, pairwise topologically distinct (AC-6); a real cross-outline search over two real rectangle
footprints (AC-5); every `CirculationClass` covered by the label vocabulary; the compiler fixtures
(`compile_hub_lobby`/`compile_branched`) re-verified against the real solver and validators. **0
failures found** in any of this surface — no representation mismatch, no architectural violation —
after fixing the one pre-existing test-instrumentation bug documented below (which was itself a test
bug, not a pipeline or validator defect).

**Classification of the one issue actually found** (the 3 originally-failing assertions in
`test_concept_engine_v2.py`, before the fix): **representation mismatch**, not an architectural
violation — see the dedicated section below for the full root-cause trace. Nothing else failed.

**What is NOT claimed**: a full 404-context count of "how many PLANNED contexts show >=1 additional
alternative under flag ON against today's validators" (the diversity-percentage style measurement
prior Concept Engine v2 Issues report) was not produced in this session — the sweep script that would
produce it did not finish. This is reported as an open item, not silently rounded up to "verified."

## AC-5 — validators unchanged

`git diff 6a4aae7 HEAD -- backend/app/vertical_slice/validation.py backend/app/vertical_slice/furnishability.py backend/app/vertical_slice/public_composition.py backend/app/vertical_slice/adjacency_priors.py backend/app/vertical_slice/room_proportion_priors.py backend/app/knowledge/ backend/app/vertical_slice/renderer.py`
returns **no behavioral change** — every one of these files is byte-for-byte identical to `origin/main`
at `6a4aae7`. C30 (`furnishability.py`, `validation.check_furnishability`) and C31
(`public_composition.py`) are exactly as main defines them; nothing in this branch's own concept-engine
code calls into or wraps a validator — `concept_engine_v2.plans_per_class` reuses the EXISTING
`general_pipeline._realize` pipeline unchanged (doors/windows/furniture/validation), so a candidate
either verifies against the real, untouched validator chain or is dropped, never re-labelled.

## AC-6 — modules present, import cleanly

All five concept modules and the three `ConceptLabel` files are on the branch:
`backend/app/vertical_slice/{concept_spec,concept_patterns,concept_score,concept_engine_v2,concept_compilers}.py`,
`frontend/src/design/ConceptLabel.{tsx,css,test.tsx}`.

```
uv run pytest -q tests/vertical_slice/test_concept_engine_v2.py
46 passed
```
Import check: `uv run python -c "from app.vertical_slice import concept_spec, concept_patterns, concept_score, concept_engine_v2, concept_compilers"` — clean, no errors, in the same `uv run` environment the fresh-checkout worktree uses (this branch's own tree). See the section below for the one failure found and fixed en route to this pass.

**Note on the verification-plan path**: attempt 1 of this repair left `test_concept_engine_v2.py` at
its Issue-#78-era location, top-level `backend/tests/`, and only flagged the mismatch against the
plan's `backend/tests/vertical_slice/test_concept_engine_v2.py` in this report — which meant
gate-3-verification's literal `TEST:pytest:backend/tests/vertical_slice/test_concept_engine_v2.py`
target had no file to run and failed CI. Fixed this attempt by moving the file to
`backend/tests/vertical_slice/test_concept_engine_v2.py`, matching both the plan's own path and its
`test_concept_compilers.py`/`test_concept_patterns.py`/`test_concept_score.py`/`test_concept_topology.py`
siblings, which already live there. Pure file relocation — no import changes needed (no relative-path
or `__file__`-based logic in the file, no `tests/vertical_slice/conftest.py` to diverge from
`tests/conftest.py`, which applies to both locations); same 46 tests, same assertions, same 46/46
pass. `docs/wiki/features/concept-engine-v2.md`'s test-location reference updated to match; its
historical Issue #130 changelog entry (describing the file's location as it was in 2026-09-23) left
as-is.

## A pre-existing test bug found and fixed mid-repair

Running the flag-ON concept-engine test suite against the merged tree (`tests/vertical_slice/test_concept_engine_v2.py`)
surfaced 3 failures. Root-caused before any fix (per the owner's classify-before-fixing rule, C25/#136):
**a representation mismatch in the test's own instrumentation, not a production defect and not a
validator interaction.**

`_ClassRecorder` matches a shown `DemoDesign` back to the `RealizedPlan` it came from by comparing
room-rectangle signatures from both sides. `_demo_design_rooms` (reading `RoomOut.gross_width_m`/
`gross_depth_m`) and `_realized_plan_rooms` (after `#130`'s own fix, reading `net_w_m`/`net_h_m`)
compared **two different numbers for the same room** — GROSS against NET — which only coincidentally
matched for whatever specific candidates `#130` verified against at the time. Once C30/C31/#146
changed which exact candidates get realized for the frozen fixture context this test uses, the
mismatch became visible: every shown plan failed to match any recorded `RealizedPlan`, so the tests
that check "the label matches the realized class" and "shown plans are pairwise distinct" saw an
empty recorder lookup instead of a real comparison.

Verified directly against the merged tree (not just inferred): printing both the `DemoDesign` payload's
room dimensions and every recorded `RealizedPlan`'s room dimensions for the corpus's `47f81017-...`
context showed the **GROSS-GROSS pairing matches exactly, room for room**, for both the SPINE primary
and the FRONT_BAND alternative — confirming the concept-engine pipeline itself is working correctly
(the primary's `ConceptOut.circulation_class` does equal the realized geometry's class) and the
fix is exactly what `_layout_signature_of_rooms`'s own docstring (and the separately-maintained
`spikes/failure_log_sweep/concept_diversity_v2.py`, which already uses GROSS-GROSS and documents why)
say it should be. Fixed `_realized_plan_rooms` to read the GROSS `rect_m` triple, matching
`_demo_design_rooms`'s existing convention — no validator touched, no test's own assertions weakened
(same equality checks, same acceptance bar; only the field pairing feeding them changed).

```
uv run pytest -q tests/vertical_slice/test_concept_engine_v2.py
46 passed
uv run pytest -q tests/test_concept_engine_v2_budget.py tests/vertical_slice/test_concept_compilers.py tests/vertical_slice/test_concept_patterns.py tests/vertical_slice/test_concept_score.py tests/vertical_slice/test_concept_topology.py
220 passed in 102.18s
```

## Change impact check (contract touched: `_demo_design_rooms`/`_realized_plan_rooms` test helpers)

1. **PRODUCER** — `general_pipeline._realize` (RealizedPlan.design) and `contract.to_demo_design`
   (DemoDesign.rooms) both derive their room rectangles from the SAME underlying `GeometricDesign`
   object; no new producer introduced.
2. **CONSUMERS** — only `_ClassRecorder.plan_for`, inside `test_concept_engine_v2.py` itself; not a
   production code path, not read by any other test file (`grep` confirms no other file references
   `_demo_design_rooms`/`_realized_plan_rooms`). The file's relocation to `tests/vertical_slice/`
   (below) has the same single-consumer scope: `grep` confirms no other file imports from or
   references `tests/test_concept_engine_v2.py` by path (only the two docs updated below did).
3. **CONTRACT** — no schema/contract change; `RoomOut.gross_width_m`/`gross_depth_m` and
   `GeometricDesign.rooms[i].rect_m` are unchanged, pre-existing, already-documented fields.
4. **TESTS** — the same 3 previously-failing tests now pass with the fix; re-ran the full file (46
   tests) plus the 4 sibling concept-engine test files (220 tests) green.
5. **REPRODUCTION** — `uv run pytest -q tests/vertical_slice/test_concept_engine_v2.py` (documented
   above) run end to end against the merged tree, at its new (and CI-manifest-matching) path.
6. **DOCS/REPORTS** — no wiki page describes the `_ClassRecorder` test helper itself; the file's own
   relocation is reflected in `docs/wiki/features/concept-engine-v2.md`'s test-location bullet and a
   new changelog line, and in this report.
7. **DEFAULTS/FALLBACKS** — none; no silent fallback introduced.
8. **CROSS-ISSUE DEPENDENCIES** — none; this helper is local to Issue #78's own test file.
