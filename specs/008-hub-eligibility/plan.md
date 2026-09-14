# Implementation Plan: Hub Eligibility by Computed Feasibility

**Branch**: `008-hub-eligibility` | **Date**: 2026-09-14 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/008-hub-eligibility/spec.md`

## Summary

The v2 hub parti is kept exactly as it is, but it is *selected* by whether it can be a good hub on the outline in front of it. `generate_concepts` computes, per hub candidate, the best reachable bedroom-class aspect of the v2 tree under the access and wet-adjacency rules (the Phase 0 bound, on the engine's own `_hub_allocation`, restricted to the lobby widths `_hub_concept` would try); a hub whose bound passes the §6 gates keeps today's ordering, one that fails is appended after every other candidate — forced tree then twin — as the last resort. Nothing in sizing, templates or Geometry Core changes; the measured effect is that the wide-shallow hub primaries revert to the front-band/spine plans that already existed, the narrow-deep ones stay, and no rescued brief becomes a refusal.

## Technical Context

**Language/Version**: Python 3.11 (backend)

**Primary Dependencies**: none new — `concept_generator.py` (pure Python), the sweep harness under `backend/spikes/failure_log_sweep/`

**Storage**: N/A

**Testing**: pytest (`backend/tests/vertical_slice/test_concept_generator.py`); measurement with `ab.py --toggle hub`, `snapshot.py`, `quality_metrics.py --split-by-strategy`, `hub_rooms.py`

**Target Platform**: backend service, in-process

**Project Type**: web application (backend change only)

**Performance Goals**: eligibility bound ≤ 50 ms per brief at the sweep's median; sweep total within +5 % of baseline `30e2312`

**Constraints**: concept stage only; `_plan_hub_wing`, `HUB_TEMPLATE`, `ROOM_TEMPLATES`, Geometry Core untouched; no new thresholds — the gates are §6's (1.35 / 1.40 / 80 %); deterministic and bounded search (0.25 m grid); forced-before-twin order preserved; non-hub candidates and their order untouched

**Scale/Scope**: one module (`concept_generator.py`: one new pure function + the ordering step in `generate_concepts`), five tests, RESULTS write-up

## Constitution Check

`.specify/memory/constitution.md` is the unfilled template; the project's operative rules are the standing constraints of feature 005 (additive parti, no Geometry Core change, measured not tuned, forced-before-twin, existing plans remain available). Checked against those:

| Rule | Status |
|---|---|
| Geometry Core, templates, `_plan_hub_wing` untouched | ✅ by design (FR-005) |
| No tuned numbers | ✅ gates reused from §6; grid step is the harness's |
| Existing successful plans remain available | ✅ SC-002 (LOST = 0, plans 107 → 107) |
| Forced candidates before their twins | ✅ FR-004 keeps forced → twin within the last-resort block |
| Measured with the harness in frozen worktrees | ✅ SC-001…SC-006 |

Post-design re-check: unchanged — the design adds one pure function and one ordering rule.

## Project Structure

### Documentation (this feature)

```text
specs/008-hub-eligibility/
├── plan.md              # This file
├── research.md          # Phase 0: decisions on where the bound lives and how ordering is expressed
├── data-model.md        # Phase 1: HubBound / HubEligibility
├── quickstart.md        # Phase 1: how to verify (tests + harness)
└── tasks.md             # Phase 2
```

### Source Code (repository root)

```text
backend/
├── app/vertical_slice/
│   └── concept_generator.py        # + HUB_GATES, HubBound, HubEligibility, hub_bound() (pure),
│                                   #   _hub_widths() (extracted), eligibility ordering in generate_concepts
├── spikes/failure_log_sweep/
│   ├── hub_topology_bound.py       # Phase 0 tool; its T1 now runs through the engine's hub_bound
│   ├── hub_rooms.py                # room dump, now split by eligibility
│   ├── sweep.py                    # StrategyRecorder also keeps the chosen rationale
│   └── README.md
└── tests/vertical_slice/
    └── test_concept_generator.py   # + 5 eligibility tests; ordering tests updated for the last-resort block
specs/005-hub-private-wing/RESULTS.md   # §8: 008 measurement
```

**Structure Decision**: single backend module change; the bound is a pure function next to `_hub_concept` so the harness tool and the engine share one model (the tool's T1 imports it — research R2).

## Complexity Tracking

No constitution violations; nothing to justify.
