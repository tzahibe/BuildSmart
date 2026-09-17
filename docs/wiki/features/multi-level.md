# Multi-Level

Status: IMPLEMENTED_MERGED (backend modules), not wired to the live product

## Current behavior

A two-storey building can be planned with a shared, pinned straight-stair `VerticalCore`, a
`SHRUNK` band on the ground floor / `FULL` on the upper, `ABSORBED` (V2) offered on the ground
floor only where eligible, two candidate allocation strategies (A and C, kept as separate
candidates with no ranking between them), a building-level wet-room invariant (a level-local
warning instead of a per-level refusal), total built area shared across both floors, and
building-level V validation kept separate from per-level C validation. Candidate selection across
buildings is lexicographic, not a weighted score.

**Not implemented**: A-vs-C ranking, `V5` (the shifted-flight band), `SHRUNK`/`ABSORBED` on the
upper level, L-shaped massing on a building, 3+ floors, other stair types, elevators.

**Not wired to the product**: `app/vertical_slice/concept_generator.py`, `general_pipeline.py`,
`app/demo/*`, and the frontend have zero diff from this work. Every new module is reached only by
calling it directly (as its own tests do) — nothing here is on the live single-request path yet.

## Authoritative implementation

- `app/vertical_slice/building.py`, `building_coordinator.py` (core-band coordinator, allocations
  A/C), `building_validation.py` (building-level V-checks).
- Domain/contracts foundation: Phase 0 (`app/vertical_slice/spec.py` additions, no behavior
  change) — commit `a235c37`, merge `b5c74fa`.
- Phase 1 backend: commit `4bdebd4`.
- Candidate primary selection (lexicographic): commit `3270063`.
- Tests: `tests/vertical_slice/test_building.py`, `test_building_coordinator.py`,
  `test_building_validation_phase1.py`.

## Current constraints/invariants

- The ordinary single-level planner path is untouched by this work — verify with `git diff
  --stat` against `concept_generator.py`/`general_pipeline.py` before assuming otherwise.
- Building-level wet-room invariant is a level-local **warning**, not a per-level refusal.
- No ranking exists yet between allocation A and allocation C — both are offered as candidates.

## Supersedes

`docs/MULTI_LEVEL_PHASE_1_INVESTIGATION_REPORT.md` and `docs/MULTI_LEVEL_PHASE_1_FOLLOWUP_REPORT.md`
(the pre-implementation design baseline — both research-only, no code).

## Known follow-ups

- A-vs-C ranking policy.
- Whether the stair-seat alignment gap measured during investigation (27/36 hand-built briefs,
  0/76 independently-generated) was closed by the implementation — check
  `docs/MULTI_LEVEL_PHASE_1_IMPLEMENTATION_REPORT.md` directly; not re-verified for this page.
- Wiring into the live product path (`concept_generator.py`/`general_pipeline.py`/`demo/*`).

## Evidence/history

`docs/MULTI_LEVEL_AND_HOUSE_CONCEPT_ARCHITECTURE_REPORT.md` (the approved architecture this
implements), `docs/MULTI_LEVEL_PHASE_0_REPORT.md`, `docs/MULTI_LEVEL_PHASE_1_IMPLEMENTATION_REPORT.md`,
`docs/MULTI_LEVEL_CANDIDATE_PRIMARY_SELECTION_IMPLEMENTATION_REPORT.md`, the two superseded
investigation/followup reports above (why allocation C was introduced, circulation-efficiency
trade-offs).

## Last verified against git

`1d648c3` (main HEAD at authoring time). Commits cited above independently confirmed via `git log
--oneline main` / `git branch --contains`.
