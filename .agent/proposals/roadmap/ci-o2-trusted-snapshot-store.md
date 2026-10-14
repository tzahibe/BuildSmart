# [agent] CI O2: trusted corpus-snapshot store — push-built snapshots of main / integration/** shared with later PRs (shadow mode)

### Goal

Stop recomputing the merge-base snapshot in gate-4: every commit that lands on `main` or an
`integration/**` branch gets its corpus snapshot computed by a trusted `push`-triggered workflow and
stored where later PRs can read it (branch-scoped Actions cache + artifact backup). Gate-4 restores it
after verifying it is the right, complete snapshot, and — in shadow mode — still computes the base
snapshot itself and fails on any difference.

### Current behavior

Gate-4 restores the base snapshot with `actions/cache/restore` keyed by merge-base SHA + corpus hash. A cache
created in a `pull_request` run is scoped to `refs/pull/N/merge` and is restorable only by re-runs of that
PR (GitHub docs, "Restrictions for accessing a cache"); the repository's cache list confirms every
`corpus-snapshot-v1-*` entry is on a `refs/pull/N/merge` ref, and the same base SHA (`f0487088`) was
recomputed by PRs #56, #58 and #59 — 23 min each. Design: `docs/CI_SNAPSHOT_CACHE_DESIGN.md`.

### Required behavior

1. New workflow `.github/workflows/agent-snapshot.yml`, `on: push: branches: [main, "integration/**"]`:
   computes the snapshot of the pushed SHA (sharded per O3), validates it (exactly 432 contexts, `head_sha`
   == the pushed SHA, corpus hash recorded), saves it with `actions/cache/save` under
   `corpus-snapshot-v2-<sha>-<corpus-hash>` (the branch's scope) and uploads it as artifact
   `corpus-snapshot-<sha>` (retention 30 days). Concurrency per branch, no cancellation of an in-flight
   snapshot for an older SHA.
2. Gate-4 lookup order for the base snapshot: (a) `actions/cache/restore` with the v2 key; (b) on a miss, the
   artifact of the `push` run for that SHA (`actions/runs?head_sha=…&event=push`, branch ∈ {main,
   integration/*}); (c) compute as today. A restored/downloaded snapshot is used only if its `head_sha`
   equals the merge-base, its context count is exactly 432 and its corpus hash matches; otherwise it is
   discarded (reason in the summary) and (c) runs.
3. Shadow mode: when (a) or (b) hit, gate-4 STILL computes the base snapshot and a "Compare base snapshots"
   step fails the job on any difference after normalising volatile fields. The old path is removed only after
   ≥ 3 real PRs with identical documents.
4. Cache hygiene: the v1 restore/save steps are removed once v2 is in place (v1 entries expire on their own);
   a `pull_request` run never writes the v2 key (it cannot reach the branch scope; the workflow does not try).

### Acceptance Criteria

- AC-1: `agent-snapshot.yml` triggers on push to main and integration/**, validates count/head_sha/hash before saving, and saves under the v2 key plus an artifact (workflow grep + orchestrator CI-gate unit test of the validation helper)
- AC-2: gate-4 prefers the v2 cache, then the push artifact, then computes; a restored snapshot with a wrong `head_sha` or count is rejected with a named reason (unit test of the selection helper with fake inputs)
- AC-3: in shadow mode a hit still triggers the local computation and the compare step; a difference fails the job (workflow grep + unit test)
- AC-4: on this PR's own gate-4 run the base snapshot came from the trusted store OR the summary states why not (cold store), and when it did the compare step passed (evidence in the `agent-regression` artifact)

### Out of scope

Removing the local base computation (follow-up after ≥ 3 identical real runs), any change to what a
snapshot contains, sampling of any kind.

### Affected domains

infra, qa

### Risk

LOW

### Resource class

MEDIUM

### Dependencies

#66, #67

### Required locks

ci-infra (exclusive)

### Verification plan

- AC-1 -> grep:.github/workflows/agent-snapshot.yml:corpus-snapshot-v2 ; grep:.github/workflows/agent-snapshot.yml:integration/\*\* ; pytest:scripts/agent_team/tests/test_ci_gates.py::test_snapshot_validation_rejects_wrong_sha_and_count
- AC-2 -> pytest:scripts/agent_team/tests/test_ci_gates.py::test_base_snapshot_source_order_and_rejection
- AC-3 -> grep:.github/workflows/agent-regression.yml:Compare base snapshots ; pytest:scripts/agent_team/tests/test_ci_gates.py::test_shadow_compare_fails_on_difference
- AC-4 -> regression:corpus ; review:the PR's gate-4 summary names the base snapshot source and, when restored, the compare step passed

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/wiki/architecture/agent-team-workflow.md (gate-4: trusted store, lookup order, trust checks, shadow mode), docs/CI_SNAPSHOT_CACHE_DESIGN.md (status), docs/CI_OPTIMIZATION_PROPOSAL.md (O2 status).

### Knowledge check

Consulted: GitHub Actions cache access restrictions (docs; verified against this repository's cache list on
2026-09-19), `.github/workflows/agent-regression.yml`, `docs/CI_SNAPSHOT_CACHE_DESIGN.md`, O3 contract (#67:
sharded snapshot reused here). What exists: PR-scoped v1 cache (helps re-runs only). What remains: the push
workflow, v2 keys, lookup order with trust checks, shadow compare.
