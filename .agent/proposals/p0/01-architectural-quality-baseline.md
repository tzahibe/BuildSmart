# [agent] Architectural-quality baseline: M1–M6 as importable metrics, corpus regression signal, per-plan quality report

### Goal

The plans we already generate are held to measurable architectural quality — area use, room
proportions, dead space, wet-room adjacency, circulation share, public-zone contiguity, hall
compactness — with a frozen baseline over the real corpus so any future planner change that
quietly worsens them is caught deterministically, and each delivered plan reports its own
numbers instead of only "13/13 checks passed".

### Current behavior

Hard validation gates already enforce the structural basics per realized drawing
(`backend/app/vertical_slice/validation.py`): C1 no overlap, C2 no residual interior area (dead
space), C3/C20/C21 dimensions/aspect/area maxima from templates, C5 reachability from the
entrance, C13 declared access realized, C17 bathroom access. The architectural-quality metrics
M1 (habitable aspect), M2 (habitable rooms on the envelope), M3 (circulation share), M4 (hall door
count / aspect), M5 (wet-room adjacency), M6 (public-zone contiguity) exist only in the spike
`backend/spikes/failure_log_sweep/quality_metrics.py`, run by hand, not importable, not in pytest,
not in CI, with no baseline — the measured gaps vs 21 professional plans (spec 005 §1: hall spine
aspect 9.4 vs a compact lobby, wet adjacency 40% vs ~85–90%, strip-shaped public rooms) have no
regression signal today. `QualityOut` (`backend/app/demo/contract.py`) carries only the laundry
notice.

### Required behavior

1. `backend/app/vertical_slice/quality_metrics.py` — the M1–M6 computations moved (not
   duplicated) out of the spike into an importable, side-effect-free module with one function
   `measure_design(design) -> QualityMetrics` (per plan) and `summarize(list) -> dict` (corpus
   medians/shares). The spike script imports it; its printed report stays identical.
2. A REGRESSION-tier test `backend/tests/regression_corpus/test_quality_baseline.py` that computes
   the corpus summary over the frozen 432-context corpus (PLANNED contexts only, through
   `generate_demo_design`), compares it to a committed baseline
   `backend/tests/regression_corpus/quality_baseline.json` (produced by a re-runnable
   `freeze_quality_baseline.py`), and fails when any of M3 median, M5 share, M6 share, M4 hall
   aspect median regresses beyond a documented tolerance (start: 2 percentage points / 0.2 aspect).
   It passes unchanged on today's main. It is a no-regression bar, not a new absolute bar.
3. Each delivered plan's `QualityOut` gains an additive `metrics` object (M1–M6 for that plan,
   plus `dead_space_m2` = 0 by C2 and `wasted_circulation_share`), so the ReviewPage can show
   them later. No existing field changes.
4. The measured gaps and the proposed follow-ups (public-room strip fix through the quality tier;
   private-wing lobby topology, which the rejected spec 005 already tried) are written as
   PROPOSED FOLLOW-UP paragraphs in the PR description and in the Wiki page — not opened as Issues.

### Acceptance Criteria

- AC-1: `app/vertical_slice/quality_metrics.py` exposes `measure_design` and `summarize`, and the spike script imports it (no duplicated metric code)
- AC-2: `tests/regression_corpus/test_quality_baseline.py` exists, is `regression`-marked, reads `quality_baseline.json`, and passes on the current corpus
- AC-3: the baseline test fails when a metric regresses beyond tolerance (a unit test feeds a degraded summary and asserts the failure message names the metric)
- AC-4: `QualityOut.metrics` is present on every PLANNED demo design with the six M-values and is absent from no PLANNED result (fast-tier test on the demo contract)
- AC-5: the frozen-corpus outcomes and every primary design signature are unchanged (metrics are read-only)
- AC-6: the Wiki page for geometry/validation documents the metrics, the baseline, the tolerances and the follow-up proposals

### Out of scope

Changing any planner decision, template, aspect ratio or validation gate. Re-attempting the hub
parti (spec 005). ReviewPage UI. Any change to how plans are ranked.

### Affected domains

backend, geometry, qa, knowledge

### Risk

MEDIUM

### Resource class

HEAVY

### Dependencies

none

### Required locks

geometry-core (shared), knowledge-index (shared)

### Verification plan

- AC-1 -> grep:backend/app/vertical_slice/quality_metrics.py:def measure_design ; grep:backend/spikes/failure_log_sweep/quality_metrics.py:from app.vertical_slice.quality_metrics import
- AC-2 -> file:backend/tests/regression_corpus/quality_baseline.json ; grep:backend/tests/regression_corpus/test_quality_baseline.py:pytest.mark.regression ; regression:corpus
- AC-3 -> pytest:backend/tests/regression_corpus/test_quality_baseline.py::test_degraded_summary_fails_with_the_metric_named
- AC-4 -> pytest:backend/tests/test_demo_quality.py
- AC-5 -> regression:corpus
- AC-6 -> grep:docs/wiki/architecture/geometry-validation.md:quality_baseline

### Regression budget

LOST: 0
GAINED: 0
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/wiki/architecture/geometry-validation.md (metrics + baseline + tolerances + follow-ups); backend/spikes/failure_log_sweep/README.md (points to the module).

### Knowledge check

Consulted (Wiki-first, then RAG + code): `docs/wiki/architecture/geometry-validation.md`,
`docs/wiki/features/room-proportion-quality-tier.md`, `specs/005-hub-private-wing/spec.md` §1
(M1–M6 origin, 21-plan census), `docs/PRIVATE_HOUSE_V1_ENGINE_DECISION.md`,
`docs/ROOM_PROPORTION_QUALITY_TIER_REPORT.md`, `backend/spikes/failure_log_sweep/quality_metrics.py`,
`app/vertical_slice/validation.py` (C1–C22). What exists: hard structural gates + a manual
metrics spike. What remains (this Issue): importable metrics, a frozen corpus baseline as a
regression signal, per-plan metrics in the contract. Left as follow-ups: public-room strip fix,
private-wing lobby topology (spec 005 rejected three times).
