"""Concept Plan Communication Pass — the programme-capacity disclosure.

The audit (PR #179) measured that on 3 of 8 briefs the requested built area materially exceeds what
the requested ROOM PROGRAMME can reasonably fill, the delivered concept is 52-74% of the request,
and the person is told nothing: the sentence that explains it exists, but it is raised as a refusal
and so only ever fires when NOTHING plans. These tests pin the disclosure on the SUCCESS path, and
pin that it stays a notice rather than becoming a validation failure.
"""
from __future__ import annotations

import pytest

from app.demo import service as svc
from app.demo.contract import capacity_notice_text
from app.vertical_slice.concept_generator import build_room_program, program_capacity_gross_m2
from tests.vertical_slice.test_hub_guard import _project

#: Audited briefs: the three whose request exceeds the programme capacity, and two that fit.
OVER_CAPACITY = {
    "B02": dict(bedrooms=1, wet_rooms=1, safe_room=False, open_plan=True, built_area_m2=216.0,
                footprint_width_m=12.0, footprint_depth_m=18.0, plot_width_m=20.0, plot_depth_m=26.0),
    "B09": dict(bedrooms=3, wet_rooms=3, safe_room=False, open_plan=False, built_area_m2=440.0,
                footprint_width_m=20.0, footprint_depth_m=22.0, plot_width_m=28.0, plot_depth_m=30.0),
}
WITHIN_CAPACITY = {
    "B08": dict(bedrooms=3, wet_rooms=1, safe_room=False, open_plan=True, built_area_m2=132.0,
                footprint_width_m=11.0, footprint_depth_m=12.0, plot_width_m=19.0, plot_depth_m=20.0),
    "B11": dict(bedrooms=4, wet_rooms=2, safe_room=True, open_plan=True, built_area_m2=216.0,
                footprint_width_m=12.0, footprint_depth_m=18.0, plot_width_m=20.0, plot_depth_m=26.0),
}


# ------------------------------------------------------------------ the wording, in one place

def test_no_notice_when_the_request_fits():
    assert capacity_notice_text(180.0, 200.0) is None
    assert capacity_notice_text(200.0, 200.0) is None, "equal is not over capacity"


def test_no_notice_without_a_target():
    assert capacity_notice_text(None, 200.0) is None


def test_the_notice_names_both_numbers_and_what_to_do():
    text = capacity_notice_text(440.0, 200.0)
    assert text is not None
    assert "200" in text and "440" in text
    assert "להוסיף חדרים" in text and "להקטין" in text, text


def test_the_refusal_and_the_notice_share_one_sentence():
    """`demo.service` must not keep its own copy of the wording — the refusal that fires when
    nothing plans and the notice attached when a plan succeeds are the same words."""
    import inspect
    source = inspect.getsource(svc)
    assert "capacity_notice_text" in source
    assert source.count("יכולה למלא עד כ-") == 0, "the sentence must live only in contract.py"


# ------------------------------------------------------------------ on the real success path

@pytest.mark.parametrize("brief", sorted(OVER_CAPACITY))
def test_an_over_capacity_brief_is_disclosed_on_the_success_path(brief):
    project = _project(OVER_CAPACITY[brief])
    result = svc.generate_demo_design(project)
    notice = result.design.quality.capacity_notice
    assert notice, f"{brief} is over capacity and said nothing"

    spec = svc.spec_for(project)
    capacity = program_capacity_gross_m2(build_room_program(spec))
    assert spec.program.target_built_area_m2 > capacity
    assert f"{capacity:.0f}" in notice and f"{spec.program.target_built_area_m2:.0f}" in notice


@pytest.mark.parametrize("brief", sorted(WITHIN_CAPACITY))
def test_a_brief_that_fits_says_nothing(brief):
    result = svc.generate_demo_design(_project(WITHIN_CAPACITY[brief]))
    assert result.design.quality.capacity_notice is None


def test_the_disclosure_is_never_a_validation_failure():
    """The plan is correct; the brief is simply over capacity. The notice must not fail the plan,
    and must not appear in the validation warnings either."""
    result = svc.generate_demo_design(_project(OVER_CAPACITY["B09"]))
    design = result.design
    assert design.quality.capacity_notice
    assert design.validation.passed is True
    for warning in design.validation.warnings:
        assert "יכולה למלא" not in str(warning)


def test_every_alternative_carries_the_same_disclosure():
    """The condition is a property of the BRIEF, not of one plan, so every plan in the response
    discloses it — otherwise the notice would appear and vanish as the person switches plans."""
    result = svc.generate_demo_design(_project(OVER_CAPACITY["B09"]))
    expected = result.design.quality.capacity_notice
    assert expected
    for alternative in result.alternatives:
        assert alternative.quality.capacity_notice == expected
