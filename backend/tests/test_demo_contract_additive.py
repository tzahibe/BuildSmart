"""Feature 006 adds fields to the demo contract. Every one is optional and defaulted, so a payload
that predates them — and every client that reads only `plan`/`alternatives` — is unaffected."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.demo.contract import (
    DemoDesign,
    DemoPlanSet,
    OutlineOut,
    OutlineTried,
    RectOut,
    SearchSummary,
    ValidationSummary,
)


def _minimal_design(**extra) -> DemoDesign:
    rect = RectOut(x=0.0, y=0.0, width_m=1.0, depth_m=1.0)
    return DemoDesign(
        plot=rect, footprint=rect, rooms=[], walls=[], open_interfaces=[], doors=[], windows=[],
        parking=[], garden=[], entrance_walk=rect, gross_area_m2=1.0, net_area_m2=1.0,
        validation=ValidationSummary(passed=True, statements=[], warnings=[], checks={}),
        **extra,
    )


def test_a_design_without_the_new_fields_still_validates():
    design = _minimal_design()
    assert design.outline is None
    assert design.family is None
    assert "outline" in design.model_dump()


def test_a_plan_set_serialises_with_search_absent():
    plan_set = DemoPlanSet(plan=_minimal_design(), alternatives=[])
    assert plan_set.search is None
    assert plan_set.model_dump()["search"] is None


def test_outline_origin_is_engine_or_person_only():
    OutlineOut(width_m=12.35, depth_m=14.25, area_m2=175.99, origin="ENGINE")
    OutlineOut(width_m=12.35, depth_m=14.25, area_m2=175.99, origin="PERSON")
    with pytest.raises(ValidationError):
        OutlineOut(width_m=12.35, depth_m=14.25, area_m2=175.99, origin="PRESET")


def test_search_summary_carries_every_outline_tried():
    tried = OutlineTried(width_m=12.35, depth_m=14.25, origin="ENGINE", planned=True,
                         plans_found=3, latency_ms=1180.4)
    summary = SearchSummary(outlines=[tried], total_latency_ms=1180.4)
    dumped = summary.model_dump()
    assert set(dumped["outlines"][0]) == {"width_m", "depth_m", "origin", "planned",
                                          "plans_found", "latency_ms", "shape"}
    assert dumped["outlines"][0]["shape"] == "RECTANGLE", "additive: a rectangle unless said"


def test_a_design_carries_its_outline_and_family_when_given():
    design = _minimal_design(
        outline=OutlineOut(width_m=12.35, depth_m=14.25, area_m2=175.99, origin="PERSON"),
        family="V[H[B,B,S,W],H,H[P,P,M]]")
    assert design.outline.origin == "PERSON"
    assert design.family.startswith("V[")


# ------------------------------------------------------------------ multi-level Phase 0

def test_a_plan_set_without_a_building_still_validates():
    """`building` is additive. A payload that predates it, and a client that reads only
    `plan`/`alternatives`, are unaffected."""
    plan_set = DemoPlanSet(plan=_minimal_design(), alternatives=[])
    assert plan_set.building is None
    assert plan_set.model_dump()["building"] is None


def test_a_building_payload_lists_only_the_checks_that_ran():
    from app.demo.contract import BuildingValidationOut, summarize_building
    from app.vertical_slice.building_validation import BuildingValidationReport

    report = BuildingValidationReport()
    report.add("V2", "containment", True, "single level")
    report.add("V7", "accounting", False, "L1 gross 126.0 m2 is not its outline's 115.5 m2")
    out = summarize_building(report)
    assert isinstance(out, BuildingValidationOut)
    assert not out.passed
    assert out.statements == ["כל קומה עליונה נמצאת בתוך המתאר של הקומה שמתחתיה"]
    assert out.warnings == ["חשבון השטחים תקין: שטח כל קומה שווה למתאר שלה: "
                            "L1 gross 126.0 m2 is not its outline's 115.5 m2"]
    assert out.checks == {"V2": True, "V7": False}


def test_an_outline_is_a_rectangle_unless_it_says_it_is_an_l():
    rect = OutlineOut(width_m=12.35, depth_m=14.25, area_m2=175.99, origin="ENGINE")
    assert rect.shape == "RECTANGLE" and rect.wing_dims_m == []
    l = OutlineOut(width_m=13.25, depth_m=18.5, area_m2=200.1, origin="ENGINE", shape="L",
                   wing_dims_m=[(8.25, 18.5), (5.0, 9.5)])
    assert l.model_dump()["wing_dims_m"] == [(8.25, 18.5), (5.0, 9.5)]

