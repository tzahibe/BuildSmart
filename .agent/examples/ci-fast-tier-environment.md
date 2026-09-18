# [agent] Make the CI fast tier match the developer environment: CPU torch, wall-clock test policy, docs-only skips

### Goal

gate-2-static's backend fast tier passes for a correct change on a GitHub runner exactly as it
does on the developer machine, and a documentation-only backend change no longer pays for the
fast tier at all.

### Current behavior

The pilot PR #7 (docs only) failed gate-2-static twice for environment reasons (job
105213930461): `tests/test_local_gateway.py::test_generate_end_to_end_returns_an_adapted_architectural_spec`
imports `torch`, which `uv sync --group dev` does not install (the `local-model` extra; on Linux
the lockfile resolves torch to the full CUDA stack), and
`tests/test_architectural_concepts.py::test_scenario_plans_before_geometry_and_realizes_it`
asserts a wall-clock budget (`_MAX_RUNTIME_S = 8.0`, calibrated on the developer's M1 Pro) that a
shared 4-vCPU runner under `-n 4` misses (9.66 s). `ci/plan.py` marks any `backend/` path as
`backend_changed`, so `backend/README.md` alone triggers the full fast tier. Agent worktrees are
set up without torch, so a worker cannot run that test either.

### Required behavior

gate-2-static installs CPU-only torch from the PyTorch CPU index after `uv sync --group dev`
(uv cache enabled so later runs are fast) and runs the fast tier with the wall-clock budget test
deselected under a written reason (a shared runner is not a performance reference; the test stays
in the developer fast tier untouched). `ci/plan.py` treats only backend code/tests/deps
(`backend/app/`, `backend/tests/`, `backend/spikes/`, `backend/pyproject.toml`, `backend/uv.lock`)
as `backend_changed`; backend docs alone do not run the fast tier. Agent worktrees and the smoke
worktree are set up with `uv sync --group dev --extra local-model`. Product code and product tests
are untouched.

### Acceptance Criteria

- AC-1: gate-2-static installs CPU-only torch via the PyTorch CPU index after uv sync, with the uv cache enabled
- AC-2: gate-2-static runs the fast tier with tests/test_architectural_concepts.py::test_scenario_plans_before_geometry_and_realizes_it deselected and a comment stating why
- AC-3: ci/plan.py reports backend_changed only for backend code/tests/deps, not for backend documentation
- AC-4: worktree setup installs the local-model extra so workers and the smoke worktree match the developer environment
- AC-5: the orchestrator test suite passes with the new plan test
- AC-6: the Wiki page documents the CI fast-tier environment policy (CPU torch, wall-clock deselect, docs-only skip)

### Out of scope

Any file under backend/app, backend/tests, backend/spikes, frontend. Changing the runtime budget
or the torch import in product tests. CUDA in CI.

### Affected domains

infra

### Risk

MEDIUM

### Resource class

LIGHT

### Dependencies

#8

### Required locks

ci-infra (exclusive)

### Verification plan

- AC-1 -> grep:.github/workflows/agent-ci.yml:download\.pytorch\.org/whl/cpu ; grep:.github/workflows/agent-ci.yml:enable-cache: true
- AC-2 -> grep:.github/workflows/agent-ci.yml:--deselect tests/test_architectural_concepts\.py::test_scenario_plans_before_geometry_and_realizes_it ; grep:.github/workflows/agent-ci.yml:wall-clock
- AC-3 -> grep:scripts/agent_team/ci/plan.py:BACKEND_CODE ; grep:scripts/agent_team/tests/test_ci_gates.py:test_backend_docs_alone_do_not_trigger_the_fast_tier
- AC-4 -> grep:.agent/config.yaml:uv sync --group dev --extra local-model
- AC-5 -> cmd:scripts/agent_team/ci/run_orchestrator_tests.sh
- AC-6 -> grep:docs/wiki/architecture/agent-team-workflow.md:CI fast-tier environment

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/wiki/architecture/agent-team-workflow.md ("Isolated environments" — CI fast-tier environment policy); .agent/config.yaml comments.
