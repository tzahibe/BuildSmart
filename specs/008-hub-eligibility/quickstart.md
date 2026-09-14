# Quickstart: verifying Hub Eligibility (008)

All commands from `backend/`, project venv. Baseline commit for every comparison: `30e2312`
(branch `007-wet-room-semantics`: hub v2 + the interim shared-bathroom guard). Measure in frozen
worktrees — the shared working tree is edited concurrently by other sessions — and copy
`app/data/failures.json` and `.env` into each (both are untracked).

## 1. Unit level (seconds)

```bash
.venv/bin/python3 -m pytest tests/vertical_slice/test_concept_generator.py -q -k "hub or eligib or demoted or twin or bounded"
```

Expected: the v2 hub tests still pass; the 008 tests pass —
- `hub_bound` on 12 × 18 (3BR + safe + 2 wet): `ELIGIBLE`, gated bedroom-class ≤ 1.35, 5/5 seats,
  wet 100 %; on 14.25 × 12.35: `LAST_RESORT`, gated 1.6–1.7, rationale names "gate 1.35";
- 3-wet brief: `gated_bedroom_aspect is None`, wet 67 %, `LAST_RESORT`;
- cost: 18 × 12 (the slowest, fails late) under 40 000 evaluations and 1 s, deterministic;
- ordering: on a demoted brief the last two candidates are the hub's forced tree then its twin, all
  peer twins precede them; on an eligible brief the v2 order is unchanged.

## 2. The bound agrees with the Phase 0 tool

```bash
.venv/bin/python3 spikes/failure_log_sweep/hub_topology_bound.py --only T1 --wet 2
```

Expected: gated bed-class 1.65 / 2.38 / 1.32 / 1.28 / 1.27 / 1.42 on the six outlines — T1 now
runs through the engine's `hub_bound`.

## 3. Sweep gates (≈ 45 min of machine time, two worktrees)

```bash
.venv/bin/python3 spikes/failure_log_sweep/snapshot.py --save R.json        # baseline worktree at 30e2312
.venv/bin/python3 spikes/failure_log_sweep/snapshot.py --compare R.json     # feature worktree
.venv/bin/python3 spikes/failure_log_sweep/ab.py --toggle hub               # feature worktree, alone (latency)
.venv/bin/python3 spikes/failure_log_sweep/quality_metrics.py --split-by-strategy
.venv/bin/python3 spikes/failure_log_sweep/hub_rooms.py                     # medians split by eligibility
```

Expected against spec §Success Criteria (measured values in RESULTS.md §8):
- SC-001 hub-OFF plans byte-identical; SC-002 LOST 0, plans 107 → 107, the 10 hub-only rescues
  still `HUB_PRIVATE_WING`;
- SC-003 the ELIGIBLE hub primaries pass the eight §6 gates — met once the eligible wing is
  sized by the bound's witness (RESULTS.md §9: bedroom 1.16, master 1.27);
- SC-004 the displaced primaries equal their hub-OFF plans (`snapshot --compare` lists exactly
  those as changed);
- SC-006 sweep time within +5 %; full test suite: no failures beyond the baseline's.

## 4. Stop

Report the tables (RESULTS.md §8) and stop for review; no merge without it.
