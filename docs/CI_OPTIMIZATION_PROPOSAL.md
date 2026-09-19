# CI optimization proposal — agent-ci (gates 1–5)

Status: **PROPOSAL, nothing changed yet.** Written by the Team Lead on 2026-09-19 at the owner's request:
"optimize CI without lowering safety". Every number below is measured on real runs of 2026-09-18/19
(GitHub-hosted `ubuntu-latest`, 4 vCPU).

## 1. What a PR costs today (measured)

| Gate / step | Wall time | Runs when | Notes |
|---|---|---|---|
| gate-1 contract | < 1 min | always | contract + PR-body checks, manifest |
| gate-2 backend fast tier | **3.3–5.4 min** | any backend code change | `uv sync` ~1 min · CPU torch install **4 s** (wheel cached; 187 MiB) · compileall + import ~10 s · pytest `-n 4`: 1409 passed / 478 skipped in 197 s |
| gate-2 frontend | ~2 min | any frontend change | npm ci + lint + build + vitest |
| gate-2 orchestrator tests | ~6 min | scripts/agent_team change | 232 tests (the git-heavy lifecycle tests dominate) |
| gate-3 verification | **< 1 min** typical | always | runs only the manifest's targets; 2 of 20 contracts use `static:` targets (duplicating gate-2's compile/import) |
| gate-4 regression — base snapshot | **23 min** on a cache miss, 0 s on a hit | `regression_required` | cached by merge-base SHA + corpus hash; hit rate on the integration branch was ~50 % (the base moves after every integration) |
| gate-4 regression — head snapshot | **23 min** | `regression_required` | 432 contexts, `--workers 4` |
| gate-4 regression — corpus outcome invariants | **24 min** | `regression_required` | `pytest tests/regression_corpus -n 4` — **replays all 432 contexts a third time** and checks only status + refusal code, which the head snapshot already records |
| gate-5 independent review | 5–15 min | after CI green | orchestrator-side (Sonnet), not GitHub |

Typical backend PR today: **50–75 min** (43–72 measured), of which gate-4 is 45–70. A docs/frontend/infra PR: **< 3 min**.

`regression_required` today = manifest says so (regression domains `backend/geometry/validator` or a
`regression:corpus` target) AND `backend/app/**` (or spikes/lock) changed, OR risk HIGH and backend changed.
In practice **every P0 Issue** (all have domains backend+geometry+validator and LOST budgets) pays the full
corpus twice, plus the invariants replay.

## 2. Findings

F1. **The invariants step is a pure duplicate.** `test_frozen_context_reproduces_expected_outcome` re-runs
`generate_demo_design` for all 432 contexts and asserts status == expected / refusal code == expected. The
head snapshot (`corpus_snapshot.py --save`) already holds `status` and `code` per context from the same
function on the same commit. Evaluating the invariants **from the snapshot** removes 24 min with zero
coverage loss — same inputs, same code path, same assertions. (Issue #17's baseline test already moved
to reading `CORPUS_SNAPSHOT`; the frozen-outcome test never did.)

F2. **The base snapshot is recomputed far too often.** The cache key is the merge-base SHA; on the
integration branch the base changes after each integration, so half the runs pay 23 min to snapshot a
commit that a previous run's *head* snapshot already measured. A head snapshot of commit X is exactly the
base snapshot of any later PR whose merge-base is X: **saving every head snapshot under the base-cache key
of its own SHA** turns most misses into hits. Zero coverage change.

F3. **The corpus replay is single-node.** `--workers 4` on a 4-vCPU runner = 23 min. Sharding the 432
contexts over N runner jobs (matrix) and merging the shard JSONs gives ~23/N min wall time for the same
compute (Actions minutes are unchanged, wall time drops). With 4 shards: **~6 min** per snapshot.

F4. **Torch (CPU, 187 MiB) is installed on every backend run** but only `tests/test_local_gateway.py`
(fake-model path still executes `import torch` inside `generate()`) and `tests/knowledge/
test_huggingface_provider.py` need it importable. Measured cost with the warm uv cache: **~4 s**; on a cold
cache ~40–60 s. Real saving is small; the cleaner fix is to skip those two test files (`--deselect`/marker)
unless `app/architect/local_gateway.py`, `app/knowledge/embeddings/` or the two tests changed, and not
install torch otherwise. Coverage: unchanged for every PR that touches those paths; for other PRs the two
files are skipped (they cannot detect anything about untouched code).

F5. **Gate-3 vs gate-2 duplication is small.** Gate 3 runs only the manifest targets — for most contracts
a few `pytest::node` targets that gate 2 already executed inside the full fast tier (seconds each), plus
`static:backend-compile/backend-import` in 2 of 20 contracts (~10 s, duplicate of gate-2's own step) and
`uv sync` (~1 min) to reach them. The evidence *per AC* is what gate 3 is for; the re-run is cheap and
gives a per-target verdict the summary can name. Recommended: keep gate 3, but let it **reuse gate-2's
result for a `static:` target when gate 2 ran the same check on the same head** (recorded in a small
artifact) — saves the duplicate `uv sync` + checks (~1–1.5 min) only on those PRs. Not worth more.

F6. **Risk tiers are not used by CI today** beyond `risk == HIGH ⇒ regression`. The proposal below maps
the owner's tiers to gates deterministically, from data the manifest already carries (risk, domains,
budget) plus the changed paths.

## 3. Proposed policy (deterministic, from manifest + changed paths)

| Risk / PR kind | gate-1 | gate-2 static/build/fast tests | gate-3 AC verification | gate-4 corpus | gate-5 review |
|---|---|---|---|---|---|
| **LOW** | ✓ | ✓ (paths-scoped as today) | ✓ | **no** by default — unless the contract carries a `regression:corpus` target or a non-default LOST/primary budget (a LOW Issue that *declares* corpus evidence still gets it) | ✓ (unchanged) |
| **MEDIUM** | ✓ | ✓ | ✓ | **only if planner/geometry/validator/requirements logic changed**: `backend/app/vertical_slice/**`, `backend/app/geometry/**`, `backend/app/demo/**`, `backend/app/requirements/**`, `backend/app/architect/authoritative_merge.py`, the corpus files, `backend/pyproject.toml`/`uv.lock`. A MEDIUM PR touching only `app/knowledge/**`, docs, tests, spikes or the frontend skips it | ✓ |
| **HIGH** | ✓ | ✓ | ✓ | **always** when any `backend/**` code changed | ✓ + the reviewer prompt asks for the architecture questions (already the case since #33) |
| **rollup → main** (head `integration/**`) | ✓ | ✓ full (all three suites, not paths-scoped) | ✓ | **always**, against the `main` merge-base | ✓ combined-diff review (unchanged) |

Safety invariants that stay exactly as they are: `agent-ci-result` remains the single required status
(fails on any required gate, passes on a *legitimate* skip and records the reason); the skip decision is
written to the manifest/summary so the reviewer and the owner see *why* the corpus did not run; gate-5
never overrides a red deterministic gate; the frozen corpus is never sampled — when it runs, it runs whole.

Optimizations inside the gates (no policy change):

| # | Change | Saves per affected PR | Coverage impact |
|---|---|---|---|
| O1 | Invariants from the head snapshot (F1) — `test_frozen_context_reproduces_expected_outcome` reads `CORPUS_SNAPSHOT` when set, else replays as today (developer runs unchanged) | **−24 min** | none: same assertions on the same data |
| O2 | Save each head snapshot under its own SHA's base-cache key (F2) | **−23 min on ~50 % of runs** | none |
| O3 | Shard the corpus snapshot across 4 matrix jobs and merge (F3) | **−17 min per snapshot** (23 → ~6) | none (same contexts, same code; merge is a dict union) |
| O4 | Torch only when `local_gateway`/embeddings/their tests changed; otherwise deselect those two test files (F4) | −4 s warm / −1 min cold | those two files are skipped on unrelated PRs (they cannot fail on untouched code) |
| O5 | Gate 3 reuses gate-2's static results on the same head (F5) | −1–1.5 min on 10 % of PRs | none |
| O6 | Corpus cache key also includes a hash of `backend/app/**` at the merge-base — no: the SHA already pins it. (Considered, rejected.) | — | — |

## 4. Expected effect

| PR profile | Today | After O1–O3 | After policy + O1–O5 |
|---|---|---|---|
| HIGH backend (e.g. #20 entrance policy) | 65–72 min | **~14–20 min** (6+6 snapshots on a miss, 6 on a hit; no invariants replay) | same |
| MEDIUM planner change (e.g. #36 circulation) | 55–70 min | ~14–20 min | same |
| MEDIUM non-planner backend (knowledge/spikes/tests only) | 50–55 min | ~14 min | **~4 min** (no corpus) |
| LOW (docs, infra, frontend) | < 3 min | < 3 min | < 3 min |
| rollup → main | 61 min | ~14–20 min | same (always full) |

Actions minutes: O1 removes 24 compute-min per corpus run; O2 removes 23 on half the runs; O3 keeps
compute constant but cuts wall time 4×. Over the P0 wave (≈ 20 corpus runs) that is roughly
**−15 hours of wall time and −12 hours of billed minutes**, with identical verdicts.

## 5. Risks and how each is closed

| Risk | Mitigation |
|---|---|
| O1: the snapshot and the invariants test could diverge (different exception handling, different corpus loading) | keep ONE code path: the test's `CORPUS_SNAPSHOT` branch asserts on the snapshot entries and **also** asserts the snapshot's `head_sha` == `git rev-parse HEAD` and its context count == corpus size; a mismatch fails the gate instead of trusting a stale file. Developer runs (no env var) still replay. |
| O3: shard merge could silently drop contexts | the merge step asserts `len(merged) == 432` and every context key unique; gate-4's own "corpus replayed: N contexts" check already fails on a short snapshot. |
| Policy: a MEDIUM PR mis-classified as "non-planner" skips the corpus | the path list is an allow-list of everything that can change plan output (whole `vertical_slice`, `geometry`, `demo`, `requirements`, the merge, corpus files, deps); anything under `backend/app/**` **not** on the list still triggers the corpus when the contract declares a LOST/primary budget ≠ default — i.e. the contract can always force it. The skip reason is printed in the summary and the READY report, so the reviewer/owner see it. |
| Policy: LOW without corpus | LOW is defined in the label catalogue as docs/isolated tests/cosmetic UI; the contract loader already refuses a LOW Issue with a LOST allowance (`a non-zero LOST allowance requires Risk MEDIUM or HIGH`). A LOW Issue that touches planner paths still gets the corpus by the path rule. |
| O4: a change that breaks the torch-dependent modules without touching them | those modules are only reachable via `local_gateway`/embeddings; the path rule includes the whole `app/architect/` and `app/knowledge/embeddings/` trees plus both test files. |
| Cache poisoning (a wrong snapshot under a SHA key) | keys include the corpus hash and the SHA; snapshots record `head_sha`; gate-4 validates `before.head_sha == merge-base` before comparing. |

## 6. What I need from you

- Approve the **policy** (§3 table) — this is the product decision (LOW without corpus; MEDIUM only on
  planner paths). O1–O5 are engineering and carry no coverage change; I can start them on your "go".
- Order: O1 → O2 → O3 first (biggest, zero-risk), then the policy, then O4/O5. Each as its own PR to
  `main` (infra Issue with the deterministic checks above as ACs), gated by the current CI, reviewed by you.
