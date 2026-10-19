"""EVERY TYPED FAILURE AND FALLBACK ON THE BRAIN PREVIEW PATH, CONSTRUCTED (#214, ROOT #211 §4).

The preview is about to be judged by an owner, so the question this file answers is not "does the
brain plan?" (the brain suite's job) but: when it does NOT, what does the caller see, what is
written down, and does the plan say which sizer and which family made it?

Each test constructs ONE path and records all three answers. Nothing here measures time: the
latency, CPU, concurrency and failure-isolation measurements are #226's, which runs alone on an
idle machine. Where a path's trigger IS the wall clock, the trigger is constructed (a deadline in
the past, a hand-built `PipelineSuccess` carrying the budget warning) rather than raced for, so
these tests are deterministic on a loaded machine.

The paths, and where each is proven here:

| typed outcome                      | trigger                                   |
| ---------------------------------- | ----------------------------------------- |
| `EXACT_SIZER_UNAVAILABLE`          | the solver import fails (scipy absent)    |
| `EXACT_SIZER_UNKNOWN`              | every solve returns UNKNOWN               |
| `NO_EXACT_PLAN` / SIZING           | no solve could run inside the budget      |
| `NO_EXACT_PLAN` / REALIZATION      | placements realized, none kept            |
| `TOPOLOGY_REPRESENTATION_LIMIT`    | a K4 in the required contacts             |
| band-embedding refusals            | passed through verbatim, stage EMBEDDING  |
| production-sizer fallback          | any of the above, inside `run_brain`      |
| the exact plan is not kept         | it does not count / it ranks below        |
| `CRITIC`                           | a parti with a HARD critic finding        |
| `BRAIN_NO_PLAN`                    | no parti produced a distinct plan         |

`EXACT_SIZER_UNAVAILABLE` is additionally proven for real, not simulated, in a scratch virtualenv
with `scipy` uninstalled — see `docs/reports/architectural-brain/PREVIEW-operational-readiness.md`.
"""
from __future__ import annotations

import logging
import sys
from dataclasses import replace

import pytest

from app.demo import preview_gate, service as svc
from app.observability import failure_log, preview_log
from app.vertical_slice.band_embedding import BandEmbeddingRefusal
from app.vertical_slice.band_pipeline import (
    PipelineDiagnosis,
    PipelineInput,
    PipelineSuccess,
)
from app.vertical_slice.brain import exact_pipeline, runner as brain_runner
from app.vertical_slice.brain.proposer import (
    DeterministicProposer,
    TopologyProposal,
    programme_from_spec,
)
from app.vertical_slice.brain.runner import (
    SIZER_EXACT,
    BrainPlan,
    BrainResult,
    _exact_counters,
    _one,
    run_brain,
)

SMALL = "B08"


# ----------------------------------------------------------------------------- the brief, once

def _spec_and_footprint():
    from app.ai_harness.topology_poc import briefs as briefs_mod
    from tests.vertical_slice.test_hub_guard import _project
    b = {x.brief_id: x for x in briefs_mod.select_briefs()}[SMALL]
    project = _project(dict(bedrooms=b.bedrooms, wet_rooms=b.wet_rooms, safe_room=b.safe_room,
                            open_plan=b.open_plan, built_area_m2=b.built_area_m2,
                            footprint_width_m=b.footprint_width_m,
                            footprint_depth_m=b.footprint_depth_m,
                            plot_width_m=b.footprint_width_m + 8,
                            plot_depth_m=b.footprint_depth_m + 8))
    return svc.spec_for(project), (b.footprint_width_m, b.footprint_depth_m)


@pytest.fixture(scope="module")
def brief():
    return _spec_and_footprint()


def _pipeline_input(spec, fp, *, spatial=None):
    """`run_exact_pipeline`'s input for the first parti of the brief, so a refusal can be
    constructed without going through `run_brain`'s whole budget."""
    programme = programme_from_spec(spec, fp)
    prop = DeterministicProposer().propose(programme)[0]
    zones = {z: programme.zones[z] for z in prop.rooms if z in programme.zones}
    return prop, programme, PipelineInput(
        name=prop.name, zones=zones,
        required_edges=tuple(spatial if spatial is not None else prop.spatial),
        footprint_m=fp, wet_rooms=programme.resolved_wet,
        access_edges=tuple((a, b) for a, b in prop.access if a != "ENTRANCE"))


def _run_exact(inp, programme, prop, **kw):
    return exact_pipeline.run_exact_pipeline(
        inp, prefer=lambda *a: (), ladder=brain_runner.AREA_BAND_LADDER,
        rebanded=lambda zs, rung: brain_runner._rebanded(zs, programme, rung),
        arrival=prop.arrival, **kw)


# ======================================================= 1. EXACT_SIZER_UNAVAILABLE (no solver)

def test_without_the_solver_the_exact_pipeline_refuses_typed_and_names_scipy(brief, monkeypatch):
    """The only refusal whose cause is a DEPLOYMENT fact rather than a brief. `milp_cells` and
    `milp_oracle` both import `scipy.optimize`, so blocking `scipy` is what an un-synced image
    does — and the detail has to name it, or the operator debugs the brief instead of the image."""
    spec, fp = brief
    prop, programme, inp = _pipeline_input(spec, fp)
    for name in [m for m in list(sys.modules) if m.startswith("app.vertical_slice.exact.milp")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "scipy", None)
    monkeypatch.setitem(sys.modules, "scipy.optimize", None)
    out = _run_exact(inp, programme, prop)
    assert isinstance(out, PipelineDiagnosis)
    assert (out.code, out.stage) == ("EXACT_SIZER_UNAVAILABLE", "SIZING")
    assert "scipy" in out.detail


def test_without_the_solver_every_parti_falls_back_to_production_and_says_so(brief, monkeypatch):
    """What the CALLER sees: plans, not an error — and every one of them names the production
    sizer and carries the typed reason. #214 measured this for real in a scipy-less virtualenv:
    8 of 8 partis realized, 200 OK, the note on every plan."""
    spec, fp = brief
    monkeypatch.setattr(exact_pipeline, "run_exact_pipeline",
                        lambda *a, **k: PipelineDiagnosis("EXACT_SIZER_UNAVAILABLE", "SIZING",
                                                          "scipy is not installed (No module named 'scipy')"))
    res = run_brain(spec, fp, brief=SMALL, sizer=SIZER_EXACT, families=("band", "spine"))
    assert res.accepted, "the preview must never lose a parti production can plan"
    assert {p.sizer for p in res.accepted} == {"production"}
    assert all(any("EXACT_SIZER_UNAVAILABLE" in n for n in p.notes) for p in res.accepted)
    # AND it is a typed field now, not only prose an operator has to grep
    assert res.exact_refusals == ("EXACT_SIZER_UNAVAILABLE",)
    assert res.solves == 0


def test_the_unavailable_refusal_stops_the_request_rather_than_retrying_every_parti(brief, monkeypatch):
    """A missing solver is a fact about the PROCESS, so trying the next parti cannot change it.
    `_improve_exactly` returns after the first one and copies the note onto every other plan —
    which is what makes a wholly degraded request visible on every plan, not just the first."""
    spec, fp = brief
    calls: list = []

    def refuse(*a, **k):
        calls.append(1)
        return PipelineDiagnosis("EXACT_SIZER_UNAVAILABLE", "SIZING", "scipy is not installed")

    monkeypatch.setattr(exact_pipeline, "run_exact_pipeline", refuse)
    res = run_brain(spec, fp, brief=SMALL, sizer=SIZER_EXACT)
    assert len(calls) == 1, "the exact sizer must be asked once, not once per parti"
    planned = [p for p in res.plans if p.stage != "CRITIC"]
    assert all(p.exact_refusal == "EXACT_SIZER_UNAVAILABLE" for p in planned)


def test_fallback_false_returns_the_refusal_as_a_plan_that_did_not_realize(brief, monkeypatch):
    """`_improve_exactly` already holds production's plan, so there the exact sizer's refusal is
    returned AS a plan (stage UNAVAILABLE), never silently re-run through production twice."""
    spec, fp = brief
    prop, programme, _ = _pipeline_input(spec, fp)
    monkeypatch.setattr(exact_pipeline, "run_exact_pipeline",
                        lambda *a, **k: PipelineDiagnosis("EXACT_SIZER_UNAVAILABLE", "SIZING", "scipy missing"))
    plan = _one(prop, programme, 80, 12, sizer=SIZER_EXACT, fallback=False)
    assert (plan.ok, plan.stage, plan.sizer) == (False, "UNAVAILABLE", "production")
    assert plan.reason.startswith("EXACT_SIZER_UNAVAILABLE")
    assert plan.exact_refusal == "EXACT_SIZER_UNAVAILABLE"
    assert not plan.counts


# ======================================================= 2. EXACT_SIZER_UNKNOWN (every solve timed out)

def test_when_every_solve_returns_unknown_the_refusal_is_its_own_code(brief, monkeypatch):
    """Distinguished from `NO_EXACT_PLAN` on purpose: UNKNOWN means the solver ran out of time and
    the answer is unknown, which is an operational fact (too little budget for this brief), while
    NO_EXACT_PLAN is a geometric one. Constructed by making every solve answer UNKNOWN, not by
    shortening the clock, so the test cannot flake on a busy machine."""
    pytest.importorskip("scipy")
    spec, fp = brief
    prop, programme, inp = _pipeline_input(spec, fp)
    from app.vertical_slice.exact import milp_oracle

    class _Unknown:
        status = "UNKNOWN"

    monkeypatch.setattr(milp_oracle, "milp_placement", lambda *a, **k: _Unknown())
    out = _run_exact(inp, programme, prop, families=("band",))
    assert isinstance(out, PipelineDiagnosis)
    assert (out.code, out.stage) == ("EXACT_SIZER_UNKNOWN", "SIZING")
    assert out.candidates_tried == 0
    assert out.stage_histogram["SIZING"] == {"band:UNKNOWN": sum(out.stage_histogram["SIZING"].values())}


def test_the_unknown_refusal_also_falls_back_to_production(brief, monkeypatch):
    spec, fp = brief
    monkeypatch.setattr(exact_pipeline, "run_exact_pipeline",
                        lambda *a, **k: PipelineDiagnosis("EXACT_SIZER_UNKNOWN", "SIZING",
                                                          "every exact solve hit its time limit"))
    res = run_brain(spec, fp, brief=SMALL, sizer=SIZER_EXACT)
    assert res.accepted and {p.sizer for p in res.accepted} == {"production"}
    assert res.exact_refusals == ("EXACT_SIZER_UNKNOWN",)


# ======================================================= 3. NO_EXACT_PLAN

def test_a_budget_that_has_already_expired_refuses_without_sizing_anything(brief):
    """stage SIZING, `candidates_tried` 0: a deadline in the past is the degenerate case of the
    one wall-clock budget, and it must refuse rather than size one candidate anyway."""
    pytest.importorskip("scipy")
    spec, fp = brief
    prop, programme, inp = _pipeline_input(spec, fp)
    out = _run_exact(inp, programme, prop, families=("band", "spine", "stack", "cells"), deadline=0.0)
    assert isinstance(out, PipelineDiagnosis)
    assert (out.code, out.stage, out.candidates_tried) == ("NO_EXACT_PLAN", "SIZING", 0)
    assert any("request budget reached" in w for w in out.warnings)


def test_when_placements_realize_but_none_is_kept_the_stage_is_realization(brief, monkeypatch):
    """stage REALIZATION, `candidates_tried` > 0 — the geometric refusal, and the histogram says
    which validator constraint refused each one."""
    pytest.importorskip("scipy")
    spec, fp = brief
    prop, programme, inp = _pipeline_input(spec, fp)

    class _Refused:
        constraint = "C9"

    monkeypatch.setattr(exact_pipeline, "realize_cells", lambda *a, **k: _Refused())
    out = _run_exact(inp, programme, prop, families=("band",))
    assert isinstance(out, PipelineDiagnosis)
    assert (out.code, out.stage) == ("NO_EXACT_PLAN", "REALIZATION")
    assert out.candidates_tried > 0
    assert out.stage_histogram["REALIZATION"] == {"C9": out.candidates_tried}


# ======================================================= 4. the band-embedding refusals

def test_an_unrepresentable_parti_is_refused_by_the_embedder_and_passed_through_verbatim(brief):
    """`run_exact_pipeline` does NOT re-label an embedding refusal: the code and the detail are the
    embedder's own, at stage EMBEDDING, because "this topology cannot be drawn with rectangles" is
    a different fact from "the sizer could not place it" and the operator needs to tell them
    apart. A K4 — four mutually touching rooms — is the exact, proven obstruction."""
    spec, fp = brief
    prop, programme, _ = _pipeline_input(spec, fp)
    rooms = list(dict.fromkeys(prop.rooms))[:4]
    k4 = tuple((a, b) for i, a in enumerate(rooms) for b in rooms[i + 1:])
    _p, _g, inp = _pipeline_input(spec, fp, spatial=k4)
    out = _run_exact(inp, programme, prop, families=("band",))
    assert isinstance(out, PipelineDiagnosis)
    assert (out.code, out.stage) == ("TOPOLOGY_REPRESENTATION_LIMIT", "EMBEDDING")
    assert "mutually adjacent" in out.detail


@pytest.mark.parametrize("code", ["TOPOLOGY_NON_PLANAR", "TOPOLOGY_REPRESENTATION_LIMIT",
                                  "BAND_UNSAT", "EMBEDDING_SEARCH_EXHAUSTED", "INVALID_INPUT"])
def test_every_embedding_refusal_code_travels_to_the_plan_untranslated(brief, monkeypatch, code):
    """All five of `BandEmbeddingRefusal`'s codes, each one reaching `BrainPlan.exact_refusal` and
    the plan's notes with its own name. A refusal flattened into a generic "could not plan" is how
    an operator ends up with nothing to act on."""
    spec, fp = brief
    monkeypatch.setattr(exact_pipeline, "embed_band",
                        lambda *a, **k: BandEmbeddingRefusal(code, f"{code} detail", True))
    prop, programme, _ = _pipeline_input(spec, fp)
    plan = _one(prop, programme, 80, 12, sizer=SIZER_EXACT, fallback=False)
    assert (plan.exact_refusal, plan.stage) == (code, "EMBEDDING")
    assert plan.reason.startswith(code)
    assert any(code in n for n in plan.notes)


# ======================================================= 5. the production sizer's own refusal

def test_a_production_pipeline_refusal_becomes_a_plan_that_did_not_realize(brief, monkeypatch):
    """The fallback's fallback: when the PRODUCTION sizer also refuses, the parti's plan carries
    that code and stage, and `counts` is False — so `run_brain` can offer nothing and the service
    reaches `BRAIN_NO_PLAN`."""
    spec, fp = brief
    monkeypatch.setattr(brain_runner, "_pipeline",
                        lambda *a, **k: PipelineDiagnosis("BAND_UNSAT", "EMBEDDING", "no band layout"))
    res = run_brain(spec, fp, brief=SMALL)
    assert res.plans and not res.accepted and not res.distinct
    planned = [p for p in res.plans if p.stage != "CRITIC"]
    assert planned and all(p.reason.startswith("BAND_UNSAT") and p.stage == "EMBEDDING"
                           for p in planned)


# ======================================================= 6. the critic, before any placement

class _CriticFailingProposer:
    """One parti with no ENTRANCE edge — a HARD `NO_ENTRANCE_ACCESS` finding, which the critic
    reports BEFORE any placement is attempted, so the refusal costs no solver time at all."""

    def propose(self, programme):
        real = DeterministicProposer().propose(programme)[0]
        return [TopologyProposal(name="NO_FRONT_DOOR", rationale="a house with no way in",
                                 spatial=real.spatial,
                                 access=tuple((a, b) for a, b in real.access if a != "ENTRANCE"),
                                 arrival=real.arrival)]


def test_a_parti_the_critic_rejects_never_reaches_the_sizer(brief, monkeypatch):
    spec, fp = brief
    called: list = []
    monkeypatch.setattr(exact_pipeline, "run_exact_pipeline",
                        lambda *a, **k: called.append(1))
    res = run_brain(spec, fp, brief=SMALL, sizer=SIZER_EXACT,
                    proposer=_CriticFailingProposer())
    assert [p.stage for p in res.plans] == ["CRITIC"]
    assert "NO_ENTRANCE_ACCESS" in res.plans[0].critic_findings
    assert not res.accepted and called == [], "the critic runs before any placement"
    assert res.plans[0].solves == 0


# ======================================================= 7. the exact plan is made but NOT kept

def _exact_attempt(res: BrainResult, **over) -> BrainPlan:
    """A crafted exact-sizer plan carrying a REAL realized layout (production's, for the same
    parti), so `_improve_exactly`'s three decline branches can be constructed without a solver."""
    base = res.accepted[0]
    return replace(base, sizer=SIZER_EXACT, family="spine", notes=(), solves=4, **over)


def _patched_exact(monkeypatch, attempt: BrainPlan):
    real_one = brain_runner._one

    def one(prop, p, mc, mr, *, sizer="production", **kw):
        if sizer == SIZER_EXACT:
            return replace(attempt, parti=prop.name, rationale=prop.rationale)
        return real_one(prop, p, mc, mr, sizer=sizer, **kw)

    monkeypatch.setattr(brain_runner, "_one", one)


def test_an_exact_plan_that_does_not_count_is_declined_with_the_reason_in_the_notes(brief, monkeypatch):
    """Not kept, and the note says WHY — area or preservation. The production plan stays, which is
    the promise that the exact sizer can only improve a parti, never worsen it."""
    spec, fp = brief
    res = run_brain(spec, fp, brief=SMALL)
    attempt = _exact_attempt(res, spatial_preserved="7/8")
    assert not attempt.counts
    _patched_exact(monkeypatch, attempt)
    out = run_brain(spec, fp, brief=SMALL, sizer=SIZER_EXACT)
    kept = out.distinct[0]
    assert kept.sizer == "production"
    assert any("did not count (preservation)" in n for n in kept.notes), kept.notes
    assert kept.solves >= 4, "the declined attempt's solves still reach the log"


def test_an_exact_plan_ranked_below_production_is_declined_with_both_keys_named(brief, monkeypatch):
    spec, fp = brief
    res = run_brain(spec, fp, brief=SMALL)
    _patched_exact(monkeypatch, _exact_attempt(res))
    real_key = brain_runner._plan_key
    monkeypatch.setattr(brain_runner, "_plan_key",
                        lambda plan, prop, p: (9, 9, 9, 9, 9) if plan.sizer == SIZER_EXACT else real_key(plan, prop, p))
    out = run_brain(spec, fp, brief=SMALL, sizer=SIZER_EXACT)
    kept = out.distinct[0]
    assert kept.sizer == "production"
    assert any("ranked below production" in n for n in kept.notes), kept.notes


def test_an_exact_plan_that_wins_replaces_production_and_the_plan_names_its_maker(brief, monkeypatch):
    spec, fp = brief
    res = run_brain(spec, fp, brief=SMALL)
    _patched_exact(monkeypatch, _exact_attempt(res))
    monkeypatch.setattr(brain_runner, "_plan_key",
                        lambda plan, prop, p: (0, 0, 0, 0, 0) if plan.sizer == SIZER_EXACT else (1, 1, 1, 1, 1))
    out = run_brain(spec, fp, brief=SMALL, sizer=SIZER_EXACT)
    kept = out.distinct[0]
    assert (kept.sizer, kept.family) == (SIZER_EXACT, "spine")
    assert any("exact sizer improved" in n or "planned what production could not" in n
               for n in kept.notes), kept.notes


# ======================================================= 8. the observability counters

def test_the_solve_count_and_budget_flag_are_read_off_what_the_pipeline_already_returned():
    """#214's counters are not a new measurement — they are the SIZING tallies the pipeline always
    built and the caller always discarded. Checked on both result shapes, with no clock involved."""
    diag = PipelineDiagnosis("NO_EXACT_PLAN", "SIZING", "none",
                             stage_histogram={"SIZING": {"band:INFEASIBLE": 3, "spine:UNKNOWN": 2},
                                              "SELECTION": {"wet": 7}},
                             warnings=("request budget reached after 30.1 s; later candidates and "
                                       "families were not sized",))
    assert _exact_counters(diag) == (5, True)
    success = PipelineSuccess(realized=None, placement=None, candidate_index=0, candidates_tried=1,
                              spatial_preserved="8/8", access_preserved="8/8", access_lost=(),
                              selection={"histogram": {"SIZING": {"band:FEASIBLE": 1}}})
    assert _exact_counters(success) == (1, False)
    assert _exact_counters(PipelineDiagnosis("X", "Y", "z")) == (0, False)


def test_a_declined_attempts_counters_are_carried_onto_the_plan_that_was_kept():
    """`_carry`: a log line built from the kept plans must not under-report the work the exact
    sizer did for a parti whose production plan stayed."""
    kept = BrainPlan("P", "r", True, solves=0)
    brain_runner._carry(kept, BrainPlan("P", "r", False, solves=6, budget_expired=True,
                                        exact_refusal="EXACT_SIZER_UNKNOWN"))
    assert (kept.solves, kept.budget_expired, kept.exact_refusal) == (6, True, "EXACT_SIZER_UNKNOWN")
    brain_runner._carry(kept, BrainPlan("P", "r", False, solves=2, exact_refusal="NO_EXACT_PLAN"))
    assert (kept.solves, kept.exact_refusal) == (8, "EXACT_SIZER_UNKNOWN"), "the FIRST code stands"


def test_the_request_aggregate_sums_the_partis():
    res = BrainResult(brief="b", plans=[
        BrainPlan("A", "", True, solves=3, exact_refusal="NO_EXACT_PLAN"),
        BrainPlan("B", "", True, solves=4, budget_expired=True, exact_refusal="EXACT_SIZER_UNKNOWN"),
        BrainPlan("C", "", False, stage="CRITIC"),
    ])
    assert res.solves == 7
    assert res.budget_expired is True
    assert res.exact_refusals == ("EXACT_SIZER_UNKNOWN", "NO_EXACT_PLAN")


def test_a_preview_line_names_the_engine_the_sizer_and_what_actually_made_the_plan(caplog):
    """The gap #214 closed: which engine served the request, which sizer and family made the plan
    that was SHOWN, whether the budget expired, how many solves ran, and the typed refusal."""
    with caplog.at_level(logging.INFO, logger=preview_log.LOGGER_NAME):
        line = preview_log.brain_request(
            engine="brain", sizer="exact", families=("band", "spine"), plan_sizer="production",
            plan_family="band", exact_refusal="EXACT_SIZER_UNAVAILABLE", budget_expired=False,
            solves=0, plans=3, partis=8, seconds=1.9)
    assert line == ("engine=brain sizer=exact families=band,spine plan_sizer=production "
                    "plan_family=band exact_refusal=EXACT_SIZER_UNAVAILABLE budget_expired=false "
                    "solves=0 plans=3 partis=8 seconds=1.9")
    assert caplog.records[-1].levelno == logging.INFO
    with caplog.at_level(logging.INFO, logger=preview_log.LOGGER_NAME):
        preview_log.brain_request(engine="brain", sizer="exact", families=(), code="BRAIN_NO_PLAN")
    assert caplog.records[-1].levelno == logging.WARNING, "a request with no plan is not INFO"
    assert "code=BRAIN_NO_PLAN" in caplog.records[-1].message


# ======================================================= 9. the service: BRAIN_NO_PLAN and the log

@pytest.fixture()
def log_file(tmp_path):
    original = failure_log.current_path()
    failure_log.set_path(tmp_path / "failures.json")
    yield failure_log
    failure_log.set_path(original)


def test_brain_no_plan_names_the_exact_sizers_refusal_in_the_detail(brief, monkeypatch, caplog):
    """Before #214 a `BRAIN_NO_PLAN` entry built its detail from each parti's PRODUCTION reason,
    so a request that had no solver at all was recorded as "could not plan" with the real cause —
    `EXACT_SIZER_UNAVAILABLE` — nowhere in the log. It is now the first thing the detail says."""
    spec, fp = brief
    plans = [BrainPlan("P1", "r", False, reason="BAND_UNSAT: no band layout", stage="EMBEDDING",
                       exact_refusal="EXACT_SIZER_UNAVAILABLE", solves=0)]
    monkeypatch.setattr(svc, "run_brain", lambda *a, **k: BrainResult(brief="b", plans=plans))
    monkeypatch.setenv(preview_gate.SIZER_ENV, "exact")
    with caplog.at_level(logging.INFO, logger=preview_log.LOGGER_NAME):
        with pytest.raises(svc.DemoGenerationError) as raised:
            svc.generate_demo_design(_demo_project(), brain=True)
    error = raised.value
    assert error.code == "BRAIN_NO_PLAN"
    assert error.detail.startswith("exact sizer: EXACT_SIZER_UNAVAILABLE | ")
    assert "P1 [EMBEDDING]: BAND_UNSAT" in error.detail
    assert error.message  # the Hebrew sentence the person sees, which names no cause
    assert "code=BRAIN_NO_PLAN" in caplog.text
    assert "exact_refusal=EXACT_SIZER_UNAVAILABLE" in caplog.text


# `generate_demo_design(..., brain=True)` is the real caller of `_brain_result`, so these tests
# build the production selection the honest way instead of faking one. The route, the gate and the
# refusal SHAPE are `tests/demo/test_brain_preview_gate.py`'s subject, not this file's.
def _demo_project():
    from tests.vertical_slice.test_hub_guard import _project
    return _project(dict(bedrooms=3, wet_rooms=1, safe_room=False, open_plan=True,
                         built_area_m2=132.0, footprint_width_m=11.0, footprint_depth_m=12.0,
                         plot_width_m=19.0, plot_depth_m=20.0))


def test_a_served_brain_request_logs_which_sizer_and_family_made_the_shown_plan(brief, caplog, monkeypatch):
    """The healthy case, which emitted NOTHING before #214: a 200 whose plan was made by the
    production sizer looked, from every log the server keeps, exactly like one made by the brain's
    own exact sizer."""
    spec, fp = brief
    monkeypatch.setattr(exact_pipeline, "run_exact_pipeline",
                        lambda *a, **k: PipelineDiagnosis("EXACT_SIZER_UNAVAILABLE", "SIZING",
                                                          "scipy is not installed"))
    monkeypatch.setenv(preview_gate.SIZER_ENV, "exact")
    with caplog.at_level(logging.INFO, logger=preview_log.LOGGER_NAME):
        out = svc.generate_demo_design(_demo_project(), brain=True)
    assert out.design is not None
    assert "plan_sizer=production" in caplog.text
    assert "plan_family=band" in caplog.text
    assert "exact_refusal=EXACT_SIZER_UNAVAILABLE" in caplog.text
    assert "engine=brain" in caplog.text
    # and the same fact reaches the caller, in the plan's own notes
    assert any("sized by the production sizer (band layout)" in w
               for w in out.design.validation.warnings)


def test_no_preview_secret_reaches_any_log_line_on_either_path(brief, caplog, monkeypatch, log_file):
    """AC-4 at the service layer. `preview_log` is not given the token and `_brain_result` never
    receives it, so the assertion is on the whole captured output rather than on one line."""
    spec, fp = brief
    secret = "s3cret-preview-token-value"
    monkeypatch.setenv(preview_gate.FLAG_ENV, "1")
    monkeypatch.setenv(preview_gate.TOKEN_ENV, secret)
    monkeypatch.setenv(preview_gate.SIZER_ENV, "exact")
    with caplog.at_level(logging.DEBUG):
        out = svc.generate_demo_design(_demo_project(), brain=True)
    assert secret not in caplog.text
    assert secret not in repr(out.design.validation.warnings)
    assert secret not in str(log_file.read_all())
