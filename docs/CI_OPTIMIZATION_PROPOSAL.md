# CI Optimization Proposal — gate-4 corpus regression cost

Owner-approved 2026-09-19: a risk-tier policy plus three optimizations to gate-4
(`agent-regression.yml`), landed in order **O1 -> O3 -> O2**, each shipped additively (old path
kept, a comparison step catches any divergence) so coverage and the regression budget are never
weakened. This is a proposal-tracking document, not a spec — the authoritative behavior is always
the workflow file and the code it runs; see `docs/wiki/architecture/agent-team-workflow.md`
(gate-4 section) for the current, canonical description.

## Why

Gate-4 replays the frozen 432-context corpus at the merge-base and at the head
(`corpus_snapshot.py`, ~23 min each), then re-ran the whole corpus a *third* time so
`tests/regression_corpus` could assert per-context outcome/quality invariants — three full passes
for data two of them had already computed. `docs/wiki/architecture/agent-team-workflow.md`'s
Issue #17 note records the first fix in this family (the architectural-quality tier reading the
head snapshot instead of replaying for its own metrics).

## O1 — gate-4 corpus outcome invariants from the head snapshot (Issue #66)

**Status: shipped in shadow mode**, not yet the removal. `test_frozen_context_reproduces_expected_outcome`
gained a `CORPUS_SNAPSHOT` mode (fails loudly on a stale/short snapshot, never silently skips);
`backend/spikes/failure_log_sweep/snapshot_invariants.py` evaluates the same status/refusal-code
invariants straight from `corpus_snapshot.py`'s head snapshot. CI runs both the old
`TEST_MODE=REGRESSION` replay (kept as ground truth) *and* the new snapshot-based evaluation, and
fails the job if the two verdicts (or the replay itself) disagree. **Removal criterion**: the old
replay step is only deleted after several real PRs show identical verdicts between the two paths —
not scheduled by this Issue.

## O3 — sharding (not started)

Not yet proposed as an Issue.

## O2 — the snapshot store (not started)

Not yet proposed as an Issue.

## Regression budget policy

Every optimization here must leave the Issue-declared regression budget (LOST/GAINED/crashes/status
changes/refusal-code changes/primary-signature changes) exactly as strict as before — an
optimization is a cost change, never a coverage change.
