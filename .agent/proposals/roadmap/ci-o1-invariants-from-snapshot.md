# [agent] CI O1: gate-4 corpus outcome invariants evaluated from the head snapshot (shadow mode, verdict comparison, old replay kept)

### Goal

Remove the third full corpus replay from gate-4 without changing what is checked: the frozen-corpus
outcome invariants (status and refusal code per context) are evaluated from the head snapshot that gate-4
already computes. Shipped additively — the old replay still runs and a deterministic comparison step fails
the job if the two verdicts ever differ — so the old path is removed only after real PRs prove equality.

### Current behavior

`.github/workflows/agent-regression.yml` runs `pytest tests/regression_corpus -n 4` after the head
snapshot. `tests/regression_corpus/test_frozen_regression_corpus.py::test_frozen_context_reproduces_expected_outcome`
re-runs `generate_demo_design` for all 432 contexts (24 min measured on 2026-09-18) and asserts
`status == expected_outcome` and, for refusals, `code == expected_code`. The head snapshot
(`backend/spikes/failure_log_sweep/corpus_snapshot.py --save`) already records `status` and `code` per context
from the same function on the same commit; `test_quality_baseline.py` already reads it via `CORPUS_SNAPSHOT`.

### Required behavior

1. `test_frozen_context_reproduces_expected_outcome` gains a snapshot mode: when `CORPUS_SNAPSHOT` names a
   file, the test asserts the same two facts from the snapshot entry of that context; it FAILS (does not
   skip) when the snapshot's `head_sha` is not the current `git rev-parse HEAD`, when its context count is not
   the corpus size, or when the context key is missing. Without the env var it replays exactly as today.
2. A new module `backend/spikes/failure_log_sweep/snapshot_invariants.py` with `evaluate(corpus, snapshot) ->
   InvariantsReport` (per-context verdicts, mismatches listed) used by the test and by CI, and a CLI
   `--corpus --snapshot --report OUT.json`.
3. Workflow: a new step "Corpus outcome invariants (from snapshot)" runs the CLI on the head snapshot and
   uploads `invariants_from_snapshot.json`; the existing replay step stays and now also writes its verdict
   (`invariants_replay.json` — pass/fail + the ids of failing contexts, via pytest's `--junitxml` or a small
   plugin); a "Compare invariants verdicts" step fails the job when pass/fail or the failing-context sets
   differ. The step summary prints both verdicts and their durations.
4. Nothing else in gate-4 changes: base/head snapshots, the budget evaluation and `agent-ci-result` are
   untouched. No product code changes.

### Acceptance Criteria

- AC-1: with `CORPUS_SNAPSHOT` set, the frozen-outcome test evaluates from the snapshot and never calls `generate_demo_design` (unit test with a small fake snapshot + monkeypatched generator that raises)
- AC-2: a snapshot whose `head_sha` mismatches HEAD, or whose context count is not the corpus size, makes the test FAIL with a message naming the mismatch (unit test)
- AC-3: `snapshot_invariants.evaluate` reproduces the replay verdict on a fixture (planned/refused/crash cases, code mismatch case) and lists mismatches by context key
- AC-4: the regression workflow runs the snapshot evaluation, keeps the replay, and fails when the two verdicts differ (workflow file contains all three steps; orchestrator CI-gate unit test parses the compare rule)
- AC-5: on this PR's own gate-4 run both verdicts are recorded and identical (the compare step passed; evidence in the `agent-regression` artifact)

### Out of scope

Removing the replay step (follow-up after ≥ 5 real PRs with identical verdicts), sharding (O3), the
snapshot store (O2), any change to the corpus or the budget rules.

### Affected domains

infra, qa, backend

### Risk

LOW

### Resource class

MEDIUM

### Dependencies

none

### Required locks

ci-infra (exclusive)

### Verification plan

- AC-1 -> pytest:backend/tests/regression_corpus/test_snapshot_invariants.py::test_snapshot_mode_never_regenerates
- AC-2 -> pytest:backend/tests/regression_corpus/test_snapshot_invariants.py::test_stale_or_short_snapshot_fails_loudly
- AC-3 -> pytest:backend/tests/regression_corpus/test_snapshot_invariants.py::test_evaluate_matches_replay_verdict_on_fixture
- AC-4 -> grep:.github/workflows/agent-regression.yml:Compare invariants verdicts ; grep:.github/workflows/agent-regression.yml:snapshot_invariants ; pytest:scripts/agent_team/tests/test_ci_gates.py
- AC-5 -> regression:corpus ; review:the PR's gate-4 artifact shows invariants_from_snapshot.json and invariants_replay.json with identical verdicts

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/wiki/architecture/agent-team-workflow.md (gate-4 section: shadow mode and the removal criterion), docs/CI_OPTIMIZATION_PROPOSAL.md (O1 status).

### Knowledge check

Consulted: `.github/workflows/agent-regression.yml`, `tests/regression_corpus/test_frozen_regression_corpus.py`,
`spikes/failure_log_sweep/corpus_snapshot.py` (`_run_one` records status/code), `test_quality_baseline.py`
(already snapshot-driven since #17), measured step timings of runs 35370903409 / 35362582233
(`docs/CI_OPTIMIZATION_PROPOSAL.md`). What exists: the snapshot with the needed facts. What remains: the
snapshot-mode test, the evaluator, the shadow steps and the comparison.
