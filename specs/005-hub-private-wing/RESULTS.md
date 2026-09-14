# Results: Hub-Organised Private Wing — v1 implementation, measured

**Date**: 2026-09-11 · **Code**: implemented in the working tree on top of `c7216e0`, **not committed** — two hard acceptance gates failed (see §3). Harness: `backend/spikes/failure_log_sweep/` (commit `c7216e0`).

## 1. Non-regression gates — all pass

Through the real service, 420 distinct failure-log scenarios, hub parti disabled (OFF) vs shipped (ON):

| Gate | Result |
|---|---|
| Test suite | **768 passed, 7 skipped, 0 failed** (763 + `test_vocabulary_is_additive` + 4 hub tests) |
| Pre-existing primary designs byte-identical | **112/112** (primary + alternatives: 111/112 — one alternatives list changed) |
| Lost / crashes | 0 / 0 |
| Newly planning scenarios | 0 (the hub is a quality feature; none expected) |
| Refusal codes | unchanged in every bucket (15 / 26 / 87 / 180) |
| Latency, scenarios that already planned | median 1.11 s → 1.11 s, worst regression +0.02 s |
| Latency, total sweep | 531 s → 532 s |
| Existing partis / ROOM_TEMPLATES / Geometry Core | untouched (`test_vocabulary_is_additive` snapshots every existing template row) |
| Forced-first / unforced twin | hub candidates go through `generate_concepts`; `test_hub_root_to_hall_cuts_stay_forced_in_the_twin` pins that only root→HALL cuts stay forced |

## 2. Applicability on the failure log

| | count |
|---|---|
| Scenarios with a hub candidate in `generate_concepts` | **6 / 420** |
| Hub plan realized when the hub is the only candidate offered (`quality_metrics.py --hub-only`) | **2** |
| Hub selected as the delivered plan in production | **0** (area-proximity sort out-ranks it; research R2) |
| Hub appears among a plan's alternatives | 1 |
| Hub rejections — `INSUFFICIENT_WING_AREA` (bedrooms < 3, FLEX/over-capacity, < 2 public rooms) | 287 |
| Hub rejections — `ACCESS_DEGREE_EXCEEDED` (more than 4 rooms need a lobby door) | **124** |
| Hub rejections — `ROW_WIDTH_EXCEEDED` / `COLUMN_DEPTH_EXCEEDED` | 4 / 3 |

The ≥ 3-bedroom briefs in this log almost all carry a safe room and 2–3 wet rooms: 5–7 rooms that need a door on the lobby, against the 4 seats v1's single-lobby tree offers (two flanks + two rooms in the foot band). Research R8 predicted this for the 4BR+safe+3wet case; the sweep shows it is the rule, not the exception.

## 3. Architectural-quality acceptance (spec §6) on the 2 hub plans

| Metric | Target | Hub v1 (2 plans) | All 112 plans after twins | 85 plans before twins |
|---|---|---|---|---|
| Hall long/short ≤ 1.5 | 100 % | **1.1 — 100 %** ✓ | 9.3 — 0 % | 9.4 — 0 % |
| Doors on hall | 4–7 | **5** ✓ | 7 (4–9) | 7 |
| Habitable rooms on envelope | 100 % | **100 %** ✓ | 100 % | 100 % |
| Circulation share | ≤ 14 % | **7 %** ✓ | 10 % (max 14 %) | 11 % |
| Bedroom aspect median | ≤ 1.35 | **1.21** ✓ | 1.41 | 1.26 |
| Master aspect median | ≤ 1.40 | **1.59** ✗ | 1.56 | 1.57 |
| Wet-room adjacency | ≥ 80 % | **0 %** ✗ | 36 % | 40 % |
| Public zone contiguous | (informational) | 0 % (closed-plan briefs) | 36 % | 31 % |

Two gates fail; per the acceptance rule the hub is **not committed**.

### Root causes — structural, not tuning

1. **Wet adjacency 0 %.** The v1 tree (public band in front, lobby wing behind) has no head band: the only band that touches the lobby besides the flanks is the foot band, which seats two rooms. With a master suite the foot reads `[ensuite | master | shared bath]` — the two wet rooms are separated by the master by construction. The references put the wet cluster at the lobby's head; that needs the side-by-side regime (public column beside the wing), deferred in the spec.
2. **Master aspect 1.59.** The foot band's two door-needing rooms meet under the lobby's centre line (so each overlaps it by ≥ 1.2 m). The master therefore spans from its ensuite to the centre line — wide and, at the foot band's ~3.4 m depth, shallow. A third foot seat or a two-room flank would let the master keep its own width; both are v2 changes.
3. **Applicability.** 4 seats. Two-room flanks (bedroom over a bathroom, lobby depth ≈ 4.4 m) would give 6–7 seats and are the smallest v2 step; they push the lobby's area past `HUB_TEMPLATE.max_area_m2` at aspect ≤ 1.5, so that template figure needs re-deriving from the census (TV-room hubs are larger).

### Side observation (twins, not hub)

The 112-plan population after the unforced-twin change is less square than the 85 before it (bedroom 1.41 vs 1.26, wet 36 % vs 40 %): the solver's area-ratio splits produce the rescued plans, and they are proportioned worse than the forced ones. A shape-aware objective for the released cuts is a candidate follow-up.

## 4. Decision

- `HUB_PRIVATE_WING` v1: **not committed**. Left in the working tree (`concept_generator.py`, `test_concept_generator.py`) for the owner to keep on a branch or drop; the harness, plan, research, data model, quickstart, tasks and this report are committed so v2 starts from measured ground.
- Recommended v2 scope, in order: (a) two-room flanks with a re-derived hub max area; (b) the side-by-side regime with a head band for the wet cluster; (c) only then revisit the area-proximity ordering so a hub plan can win when it exists.
