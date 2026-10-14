# [agent] CI O3: corpus snapshot sharded across matrix jobs (shadow mode: merged shards must equal the single-node snapshot)

### Goal

Cut gate-4's wall time by computing each corpus snapshot in N parallel runner jobs (shards) and merging
the shard results into one snapshot that is byte-for-byte equivalent to today's single-node snapshot.
Shipped additively: the single-node snapshot still runs and a comparison step fails the job on any
difference; the single-node path is removed only after ≥ 3 real PRs agree.

### Current behavior

`.github/workflows/agent-regression.yml` computes the base and head snapshots with
`corpus_snapshot.py --save FILE --workers 4` on one 4-vCPU runner: 23 min per snapshot (measured
2026-09-18). `corpus_snapshot.py` replays all 432 contexts with a multiprocessing pool and writes one JSON
(`results` keyed by context key, plus `head_sha`, counts, timing).

### Required behavior

1. `corpus_snapshot.py` gains `--shard I/N` (deterministic partition of the corpus by sorted context key:
   index % N == I) and `--merge OUT.json IN1.json IN2.json …` (union of shard results; asserts every context
   key appears exactly once, the total equals the corpus size, and every shard carries the same `head_sha`
   and corpus hash; writes the same document shape as `--save`, with per-shard timings preserved).
2. Workflow: a reusable job `snapshot` (matrix `shard: [0..N-1]`, N = 4) runs `--shard i/N --save shard-i.json`
   and uploads it; a `merge` job downloads the shards and produces `head_snapshot.json`; the existing single-
   node "Head snapshot" step stays as `head_snapshot_single.json`; a "Compare head snapshots" step fails the
   job when the two documents differ after normalising volatile fields (`ms` timings, `written_at`) — the
   per-context `status`, `code`, `sig`, `area` and `metrics` must be identical. Same treatment for the base
   snapshot on a cache miss.
3. Budget evaluation and every existing assertion consume the merged snapshot only after the compare step
   passed; on a difference the job is red and the artifact carries both documents.
4. No product code changes; the shard count is a workflow constant documented in the Wiki.

### Acceptance Criteria

- AC-1: `--shard I/N` partitions the corpus deterministically: the N shards are disjoint, their union is exactly the 432 keys, and the same key always lands in the same shard (unit test on the corpus index)
- AC-2: `--merge` refuses a missing shard, a duplicated key, a `head_sha` mismatch and a corpus-hash mismatch, each with a message naming the problem (unit test)
- AC-3: merging the N shards of a small fixture corpus yields a document equal (after normalising `ms`/`written_at`) to `--save` on the same corpus (unit test)
- AC-4: the regression workflow contains the matrix shard job, the merge job, the single-node step and the compare step, and the compare fails on a difference (workflow grep + orchestrator CI-gate unit test)
- AC-5: on this PR's own gate-4 run the merged and single-node head snapshots are identical (compare step passed; evidence in the `agent-regression` artifact) and the wall time of the sharded path is recorded in the step summary

### Out of scope

Removing the single-node path (follow-up after ≥ 3 identical real runs), the trusted snapshot store (O2),
changing the corpus, workers per shard beyond the runner's vCPUs.

### Affected domains

infra, qa, backend

### Risk

LOW

### Resource class

MEDIUM

### Dependencies

#66

### Required locks

ci-infra (exclusive)

### Verification plan

- AC-1 -> pytest:backend/tests/regression_corpus/test_snapshot_sharding.py::test_shards_are_disjoint_complete_and_stable
- AC-2 -> pytest:backend/tests/regression_corpus/test_snapshot_sharding.py::test_merge_refuses_missing_duplicate_and_mismatched_shards
- AC-3 -> pytest:backend/tests/regression_corpus/test_snapshot_sharding.py::test_merged_shards_equal_single_node_snapshot
- AC-4 -> grep:.github/workflows/agent-regression.yml:Compare head snapshots ; grep:.github/workflows/agent-regression.yml:--shard ; pytest:scripts/agent_team/tests/test_ci_gates.py
- AC-5 -> regression:corpus ; review:the PR's gate-4 artifact shows head_snapshot.json (merged) and head_snapshot_single.json identical after normalisation, with the sharded wall time in the summary

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/wiki/architecture/agent-team-workflow.md (gate-4: sharding, shadow mode, removal criterion), docs/CI_OPTIMIZATION_PROPOSAL.md (O3 status).

### Knowledge check

Consulted: `spikes/failure_log_sweep/corpus_snapshot.py` (`run_all(workers)`, `save`, `compare`, `_run_one`),
`.github/workflows/agent-regression.yml`, measured 23-min snapshots (proposal §1), O1 contract (#66: the
invariants read the merged head snapshot). What exists: single-node snapshot + compare. What remains:
shard/merge modes, matrix jobs, shadow compare.
