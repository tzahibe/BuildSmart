# Quickstart: proving the hub-organised private wing

All commands run from `backend/` with the project venv (`.venv/bin/python3`). Baseline before this
feature (commit `2e19d89`): tests 763 passed / 7 skipped / 0 failed; 418-scenario sweep through the
real service = 111 plans, 85 of them from forced trees; Stage-0 metrics on the 85 pre-twin plans:
hall long/short 9.4, wet adjacency 40 %, bedroom aspect 1.26, master 1.57, exposure 100 %,
circulation share 11 %.

## Prerequisites

- `backend/.venv` present (`uv sync` if not).
- `backend/app/data/failures.json` (the production failure log the 418 scenarios come from).
- The sweep harness under `backend/spikes/failure_log_sweep/` (task T0 promotes it from the session
  scratch directory; until then the scratch copies in
  `/private/tmp/claude-501/…/scratchpad/{sweep,free_twin_ab,quality_metrics}.py` are the reference).

## 1. Unit level — the parti exists, is additive and is ordered correctly

```bash
.venv/bin/python3 -m pytest tests/vertical_slice/test_concept_generator.py -q -k "hub or bounded or deterministic"
```

Expected: every hub test passes; `test_generator_produces_a_bounded_candidate_set` still holds
(twins == half the list, all after the forced trees); `test_candidates_are_deterministic` unchanged.

## 2. User Story 1 — a ≥ 3-bedroom brief gets a hub

```bash
.venv/bin/python3 - <<'EOF'
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec
from tests.vertical_slice.test_concept_generator import run_general_from_site, F
r = run_general_from_site(F.exact_rectangle(), plot_size_m=(20.0, 24.0),
                          program=ProgramSpec(bedrooms=3, safe_room=True, wet_rooms=2, open_plan_living=True,
                                              target_built_area_m2=170.0))
assert r.design is not None and r.validation.ok
assert r.concept.strategy.value == "HUB_PRIVATE_WING", r.concept.strategy
hall = next(x for x in r.design.rooms if x.zone_id == "HALL")
print("hub", hall.net_w_m, "x", hall.net_h_m, "doors on hub:",
      sum(1 for d in r.design.doors if "HALL" in (d.a, d.b) and not d.is_entrance))
EOF
```

Expected: a design, all validators pass, strategy `HUB_PRIVATE_WING`, hub short side ≥ 2.4 m,
long/short ≤ 1.5, 4–5 doors on the hub.

## 3. Full suite — the hard gate

```bash
.venv/bin/python3 -m pytest tests/ -q
```

Expected: **≥ 763 passed (plus the new hub tests), 7 skipped, 0 failed.**

## 4. 418-scenario A/B through the real service — non-regression and gains

```bash
.venv/bin/python3 spikes/failure_log_sweep/ab.py --toggle hub   # hub parti enabled vs disabled
```

Expected report lines and gates:
- `primary design identical` = **111/111** of the plans that existed before (full room signature).
- `LOST` = 0; `crashes` = 0.
- Every `GAINED` scenario listed with requested area, delivered area, %, validators; only rows
  ≥ 80 % count as gains.
- `hub selected` = how many of the 111 + gained plans have `strategy == HUB_PRIVATE_WING`;
  `hub candidate but another parti won` count; `hub rejections by reason` table.
- Latency: per-scenario median OFF vs ON, worst regression among scenarios that already planned.

## 5. Stage-0 architectural-quality metrics — the acceptance targets (spec §6)

```bash
.venv/bin/python3 spikes/failure_log_sweep/quality_metrics.py --split-by-strategy
```

Expected, on hub plans specifically (and reported side by side with non-hub plans):
hall long/short ≤ 1.5 in 100 %; doors on hall 4–7; wet adjacency ≥ 80 %; bedroom aspect median
≤ 1.35; master ≤ 1.40; habitable exposure 100 %; circulation share ≤ 14 %.

## 6. What "done" looks like

Steps 3–5 green, the before/after table in the final report, one commit containing
`concept_generator.py`, the tests and the promoted
harness, and the spec's §6 numbers updated to the measured values.
