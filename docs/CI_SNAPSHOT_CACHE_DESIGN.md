# O2 design — a trusted, shared corpus-snapshot store (gate-4 base snapshots)

Status: **implemented in shadow mode** (Issue #68, 2026-09-22). Follows the CI optimization
proposal (`docs/CI_OPTIMIZATION_PROPOSAL.md`, O2). The old fallback (compute locally) is kept and
run unconditionally alongside a trusted-store hit — see "Rollout" below — until several real PRs
show the two always agree; the authoritative current behavior is always the workflow files
(`agent-snapshot.yml`, `agent-regression.yml`) and `scripts/agent_team/ci/snapshot_store.py`, not
this document.

## 1. The problem, verified

GitHub's cache access rules (docs, "Restrictions for accessing a cache"):

- a cache created by a `pull_request` run is created for the merge ref `refs/pull/N/merge` and
  "can only be restored by re-runs of the pull request";
- a PR run *can* restore caches created **in its base branch** (and the default branch);
- only trusted triggers (`push`, `workflow_dispatch`, `schedule`, …) running **on a branch** create
  caches in that branch's scope.

Our repository confirms it: every `corpus-snapshot-v1-*` cache entry was scoped to
`refs/pull/N/merge`; the same base SHA `f0487088` was recomputed by PRs #56, #58 and #59
(23 min each), `1031418c` by #55 and #65. The v1 cache only ever helped a re-run of the same PR;
"save the head snapshot under its own SHA's key" as first proposed would have changed nothing for
the next PR.

## 2. Mechanism: snapshots of SHAs that reached `main` / `integration/**` are produced by a trusted trigger

Two layers, both trusted, both keyed by immutable content:

**Layer A — `push`-triggered snapshot workflow (`agent-snapshot.yml`).**
`on: push: branches: [main, "integration/**"]`. For the pushed SHA it computes the corpus snapshot
(same `corpus_snapshot.py --save --workers 4`, sharded — see O3) and:

1. validates it (`scripts/agent_team/ci/snapshot_store.py validate`: exactly 432 contexts,
   `head_sha` == the pushed SHA, `corpus_hash` matches the corpus file on disk) — an invalid
   snapshot is never saved or uploaded;
2. saves it to the Actions cache under `corpus-snapshot-v2-<sha>-<corpus-hash>` — a `push` run on
   `main` creates the entry in `main`'s scope, on `integration/x` in that branch's scope; a PR whose
   base is that branch **restores it by the documented base-branch rule**;
3. uploads the same JSON as a workflow artifact `corpus-snapshot-<sha>` (retention 30 days) —
   independent of cache eviction (7 days unused / 10 GB repo cap).

Every merge into `main` or an integration branch is a `push`, so **the merge-base of every later PR
already has a trusted snapshot by the time that PR opens**. The same workflow also ends the "cold
cache" case for the rollup PR: the `main` merge-base is snapshotted the moment it lands. A
`pull_request` run never triggers this workflow and never writes the v2 key — it cannot (GitHub
forbids writing to a scope it does not own).

**Layer B — gate-4 lookup order** (`agent-regression.yml`, `resolve` + `regression` jobs):

1. `actions/cache/restore` with the v2 key (base-branch scope → hit for any PR whose merge-base was
   pushed to its base);
2. on a miss: the `corpus-snapshot-<sha>` artifact of the `push` run for that SHA, found via
   `gh api …/actions/runs?head_sha=…&event=push` filtered to `agent-snapshot` runs on
   `main`/`integration/**`;
3. on a miss (or an invalid candidate at step 1/2): the base is still computed locally — this never
   blocks the PR, it only changes whether the local computation's result is also compared against a
   trusted candidate.

**Trust boundary.** `scripts/agent_team/ci/snapshot_store.py`'s `validate_snapshot` is the single
place both the writer (`agent-snapshot.yml`) and the reader (gate-4) check a candidate: its
`head_sha` must equal the SHA it claims to be a snapshot of, its `results` must cover exactly 432
contexts, and its `corpus_hash` must equal the current corpus file's hash. `select_base_snapshot`
implements the (a) → (b) → (c) order above, rejecting an invalid/missing candidate with a named
reason (recorded in the job summary) rather than silently falling through. A PR run never writes to
the base-branch cache scope (it cannot), so a PR cannot poison the store; the artifact route
additionally only considers runs with `event == "push"` and `head_branch` ∈ {main, integration/*}.

**Cache hygiene.** The v2 key is per SHA; old entries expire unused after 7 days and cost nothing
after that. Each snapshot is ~55 KB; even 1 000 entries are 55 MB — far under the 10 GB cap. The v1
key/steps are removed now that v2 is in place (v1 entries simply expire on their own schedule).

## 3. Coverage and correctness guarantees

- No sampling anywhere: a snapshot is always the full 432-context replay on the exact SHA.
- The gate-4 comparison keeps its existing assertions (`corpus replayed: N contexts`, budget rules)
  and, on a trusted-store hit, additionally asserts the trusted candidate is byte-identical
  (after normalising volatile fields) to the freshly computed `base_snapshot.json`.
- The `push` snapshot of `main` is also the natural baseline for the frozen-corpus invariants (O1).
- Developer runs are unaffected (they never used the cache).

## 4. Rollout with old-vs-new verdict comparison (the owner's requirement)

Before removing any old path, both paths run side by side and must agree:

1. O1 (invariants from snapshot) — **shipped in shadow mode** (Issue #66): the old replay stays in
   place; the new evaluation runs first and its verdict is written to the report; a `compare` step
   fails the job if the two verdicts differ. Not yet removed.
2. O3 (sharding) — **shipped in shadow mode** (Issue #67): sharded snapshot **and** the single-node
   snapshot both run; the merged shard JSON must be byte-identical (after key sort) to the
   single-node JSON. Not yet removed.
3. O2 (trusted store) — **shipped in shadow mode** (Issue #68, this document): on a cache/artifact
   hit, gate-4 still computes the base snapshot once more and asserts equality with the restored
   one; the local computation is skipped only once ≥ 3 real PRs show it and the trusted store
   always agree — not scheduled by this Issue.

Each step is its own Issue (infra, LOW risk, deterministic ACs) and its own PR to `main`, merged by the
owner. The comparison evidence (per-PR verdict pairs) is attached to the PR as the `agent-regression`
artifact plus a summary table in the PR body.
