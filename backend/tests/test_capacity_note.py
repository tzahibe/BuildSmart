"""The capacity note on a DELIVERED plan (`service.capacity_note`).

Measured on the failure log (431 briefs, 2026-09-14): 117 of 261 delivered plans came in under 80 % of
the requested area, and 85+ of those were requests above the programme's own capacity, filling a
median 96 % of it. The plan was right and said nothing; the refusal path had the sentence all along.
"""
from __future__ import annotations

import pytest

from app.demo import service as svc
from app.vertical_slice.concept_generator import build_room_program, program_capacity_gross_m2
from tests.vertical_slice.test_hub_guard import WIDE_SQUARE, _project

#: A logged brief whose request (288 m²) exceeds what 2 bedrooms + safe room + 2 wet rooms can fill.
OVER_CAPACITY = dict(bedrooms=2, wet_rooms=2, safe_room=True, open_plan=False, built_area_m2=288.0,
                     footprint_width_m=16.0, footprint_depth_m=18.0, plot_width_m=23.0, plot_depth_m=28.5)


def test_a_delivered_plan_above_capacity_says_what_it_filled_and_why():
    result = svc.generate_demo_design(_project(OVER_CAPACITY))
    design = result.design
    assert design.validation.passed                       # a warning, never a refusal or a failed check
    spec = svc.spec_for(_project(OVER_CAPACITY))
    capacity = program_capacity_gross_m2(build_room_program(spec))
    assert 288.0 > capacity
    notes = [w for w in design.validation.warnings if "יכולים למלא בצורה סבירה" in w]
    assert len(notes) == 1, design.validation.warnings
    assert f"{design.gross_area_m2:.0f} מ\"ר" in notes[0]     # what THIS drawing delivers
    assert f"כ-{capacity:.0f} מ\"ר" in notes[0]               # what the rooms can fill
    assert "288 מ\"ר" in notes[0]                             # what was asked, unchanged
    # every alternative carries its own figure
    for alternative in result.alternatives:
        alt_notes = [w for w in alternative.validation.warnings if "יכולים למלא בצורה סבירה" in w]
        assert len(alt_notes) == 1 and f"{alternative.gross_area_m2:.0f} מ\"ר" in alt_notes[0]


def test_a_plan_within_capacity_carries_no_capacity_note():
    result = svc.generate_demo_design(_project(WIDE_SQUARE))
    assert result.design.validation.passed
    assert not [w for w in result.design.validation.warnings if "יכולים למלא" in w]


def test_the_note_is_a_pure_function_of_the_request_and_the_delivered_area():
    spec = svc.spec_for(_project(OVER_CAPACITY))
    capacity = program_capacity_gross_m2(build_room_program(spec))
    assert svc.capacity_note(spec, 180.7) is not None
    within = svc.spec_for(_project({**OVER_CAPACITY, "built_area_m2": capacity - 1}))
    assert svc.capacity_note(within, 180.7) is None
    no_target = svc.spec_for(_project(OVER_CAPACITY))
    from dataclasses import replace
    assert svc.capacity_note(replace(no_target, program=replace(no_target.program,
                                                                target_built_area_m2=None)), 180.7) is None
