# Quickstart: verifying Hub Eligibility (008)

All commands from `backend/`, project venv. Baseline commit for every comparison: `30e2312`
(branch `007-wet-room-semantics`: hub v2 + the interim shared-bathroom guard). Measure in frozen
worktrees — the shared working tree is edited concurrently by other sessions.

## 1. Unit level (seconds)

```bash
.venv/bin/python3 -m pytest tests/vertical_slice/test_concept_generator.py -q -k "hub or eligib or twin"
```

Expected: the v2 hub tests still pass; the new tests pass —
- wide outline (e.g. 14.25 × 12.35, 3BR + safe + 2 wet): hub candidates present, `LAST_RESORT`,
  placed after every other candidate, forced before twin, rationale names the bound and the gate;
- narrow outline (12 × 18, same brief): `ELIGIBLE`, ordering identical to v2;
- 3-wet brief on any outline: `LAST_RESORT` with `gated_bedroom_aspect is None` (wet gate unreachable);
- cost: `hub_bound` on the wide outline evaluates within the FR-007 budget.

## 2. The bound agrees with the Phase 0 tool

```bash
.venv/bin/python3 spikes/failure_log_sweep/hub_topology_bound.py --only T1 --grid 0.25
```

Expected (2-wet): gated bed-class 1.65 / 2.38 / 1.32 / 1.27 / 1.27 / 1.42 on the six outlines —
the tool now imports the engine's `hub_bound`, so this is the same code path.

## 3. Sweep gates (≈ 45 min of machine time, two worktrees)

```bash
# baseline worktree at 30e2312 → R.json ; feature worktree → compare
.venv/bin/python3 spikes/failure_log_sweep/snapshot.py --save R.json        # in the baseline worktree
.venv/bin/python3 spikes/failure_log_sweep/snapshot.py --compare R.json     # in the feature worktree
.venv/bin/python3 spikes/failure_log_sweep/ab.py --toggle hub               # feature worktree
.venv/bin/python3 spikes/failure_log_sweep/quality_metrics.py --split-by-strategy
.venv/bin/python3 spikes/failure_log_sweep/hub_rooms.py
```

Expected against spec §Success Criteria:
- SC-001 the 88 hub-OFF plans byte-identical; SC-002 LOST 0, plans 107 → 107, the 10 hub-only
  rescues still `HUB_PRIVATE_WING`;
- SC-003 the remaining hub primaries (expected ≈ 10, the narrow-deep ones) pass all eight §6 gates
  in `quality_metrics.py --split-by-strategy`;
- SC-004 the displaced wide-shallow primaries equal their hub-OFF plans (`snapshot --compare` lists
  exactly those as changed, none other);
- SC-006 total sweep time within +5 %; full test suite: no failures beyond the baseline's 4.

## 4. Stop

Report the tables (RESULTS.md §8) and stop for review; no merge without it.
