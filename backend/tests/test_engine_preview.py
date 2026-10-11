"""The owner-facing ENGINE PREVIEW seam: `POST /design/demo?engine=...`.

The purpose is to make engine progress visually observable during development — including its
current limitations — without Concept Engine v2 becoming the production default. These tests pin
the two things that makes safe: production behaviour is unchanged when nothing is passed, and the
global flag is never written, whatever a preview asks for.
"""
from __future__ import annotations

import pytest

from app.demo import service as svc
from app.demo.router import ENGINE_CONCEPT_V2, ENGINE_PRODUCTION, _engine_override
from app.vertical_slice import general_pipeline as gp
from tests.vertical_slice.test_hub_guard import _project

BRIEF = dict(bedrooms=3, wet_rooms=1, safe_room=False, open_plan=True, built_area_m2=132.0,
             footprint_width_m=11.0, footprint_depth_m=12.0, plot_width_m=19.0, plot_depth_m=20.0)


def _payload(**kwargs):
    return svc.generate_demo_design(_project(BRIEF), **kwargs).design.model_dump()


# ------------------------------------------------------------------ the override, resolved

def test_no_engine_parameter_means_no_override_at_all():
    assert _engine_override(None) is None
    assert _engine_override(ENGINE_PRODUCTION) is None


def test_the_concept_engine_is_an_explicit_true():
    assert _engine_override(ENGINE_CONCEPT_V2) is True


def test_an_unknown_engine_is_refused_rather_than_treated_as_production():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as caught:
        _engine_override("something_else")
    assert caught.value.status_code == 422
    assert "something_else" in str(caught.value.detail)


# ------------------------------------------------------------------ production is untouched

def test_no_override_reproduces_production_byte_for_byte():
    """Requirement 1: a request that passes nothing must be the request that always went out."""
    assert _payload() == _payload(concept_engine_v2=None)


def test_explicitly_asking_for_production_is_the_same_plan():
    """Requirement 2: `?engine=production` is production, not a third behaviour."""
    assert _payload() == _payload(concept_engine_v2=False)


def test_the_concept_engine_actually_takes_a_different_path():
    """Requirement 3: the override reaches the engine — the two paths differ observably."""
    production = svc.generate_demo_design(_project(BRIEF))
    preview = svc.generate_demo_design(_project(BRIEF), concept_engine_v2=True)
    assert len(preview.alternatives) != len(production.alternatives), (
        "the preview produced the same alternatives as production — the override did not reach "
        "run_general")


@pytest.mark.parametrize("override", [None, False, True])
def test_the_global_flag_is_never_written(override):
    """Requirement 4: a preview is per-request. Concept Engine v2 stays globally OFF."""
    assert gp.CONCEPT_ENGINE_V2_ENABLED is False
    svc.generate_demo_design(_project(BRIEF), concept_engine_v2=override)
    assert gp.CONCEPT_ENGINE_V2_ENABLED is False


def test_a_preview_run_does_not_change_the_next_production_run():
    """Two requests in flight cannot see each other's choice."""
    before = _payload()
    svc.generate_demo_design(_project(BRIEF), concept_engine_v2=True)
    assert _payload() == before


# ------------------------------------------------------------------ honest about limitations

def test_the_preview_reports_its_real_alternative_count_without_padding():
    """Requirement 5: zero alternatives is the truth today, and must be returned as zero rather
    than topped up from the production path."""
    preview = svc.generate_demo_design(_project(BRIEF), concept_engine_v2=True)
    assert isinstance(preview.alternatives, tuple)
    assert len(preview.alternatives) == 0, (
        "this test documents the engine's CURRENT behaviour; if it starts returning alternatives "
        "the preview UI exposes them with no further work — update this expectation then")


def test_a_concept_family_is_never_invented():
    """Requirement 7: the label is attached only when the plan genuinely carries a class."""
    preview = svc.generate_demo_design(_project(BRIEF), concept_engine_v2=True)
    plan = preview.design
    assert plan.concept is None or getattr(plan.concept, "label", None)


def test_production_still_carries_no_concept_label():
    assert svc.generate_demo_design(_project(BRIEF)).design.concept is None
