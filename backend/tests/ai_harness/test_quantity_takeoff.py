"""#265 (ROOT #262) — tests for the quantity-takeoff harness.

**Read this before reading a number out of this file.** Every test here that builds a rectangle or
an L-shape establishes **CORRECTNESS**: that a formula computes the quantity it documents, with the
deductions and conventions it documents. It establishes **nothing about accuracy** against a real
building and no figure from a synthetic fixture may appear in comparison A (ROOT #262 AC-2).
`frozen.SYNTHETIC_TESTS_ARE_CORRECTNESS_ONLY` says the same thing in the module the report cites.

The accuracy-shaped tests are the refusals: AC-5's demonstration on the repository's own 19 real
plans and on the 1923 Fletcher takeoff, where the right answer is that the harness declines.
"""
from __future__ import annotations

import ast
import json
import math
import re
import subprocess
from pathlib import Path

import pytest

from app.ai_harness.quantity_takeoff import fletcher as FL
from app.ai_harness.quantity_takeoff import formulas as FO
from app.ai_harness.quantity_takeoff import frozen as F
from app.ai_harness.quantity_takeoff import harness as H
from app.ai_harness.quantity_takeoff import resplan as RP
from app.ai_harness.quantity_takeoff import run as RUN
from app.ai_harness.quantity_takeoff import selfcheck as SC
from app.ai_harness.quantity_takeoff.frozen import (
    AbstentionReason as A,
)
from app.ai_harness.quantity_takeoff.frozen import (
    Material,
    MeasurementConvention,
    MeasurementMethod,
    RefusalReason,
    Reliability,
)
from app.ai_harness.quantity_takeoff.schema import (
    Measured,
    OpeningKind,
    OpeningRecord,
    ProductSpec,
    Provenance,
    ReferenceProject,
    ReferenceValue,
    RoomGeometry,
    RoomRecord,
    Surface,
)

PKG = Path(FO.__file__).resolve().parent
BACKEND = PKG.parents[2]
REPO = BACKEND.parent


def prov(units="m2", method=MeasurementMethod.AS_BUILT_PHYSICAL_SURVEY,
         reliability=Reliability.VERIFIED, independence="measured by a third party on site"):
    return Provenance(source="A Surveyor", citation="https://example.invalid/report.pdf",
                      method=method, units=units, revision="rev C 2026-01-01",
                      reliability=reliability, independence=independence)


def rect(w, d):
    return ((0.0, 0.0), (w, 0.0), (w, d), (0.0, d))


def simple_project(**kw):
    defaults = dict(project_id="synthetic", publisher="tests", licence="N/A (synthetic fixture)",
                    convention=MeasurementConvention.INTERNAL_CLEAR,
                    wall_thickness=Measured(0.1, prov("m")))
    defaults.update(kw)
    return ReferenceProject(**defaults)


# =========================================================================== AC-1 — the schema

def test_a_provenance_needs_all_six_fields():
    for missing in ("source", "citation", "units", "revision", "independence"):
        kw = dict(source="s", citation="c", method=MeasurementMethod.PROFESSIONAL_TAKEOFF,
                  units="m2", revision="r", reliability=Reliability.STATED, independence="i")
        kw[missing] = "   "
        with pytest.raises(ValueError, match="#263 1.2"):
            Provenance(**kw)


def test_a_weaker_method_cannot_grade_verified():
    for m in F.WEAKER_METHODS:
        with pytest.raises(ValueError, match="WEAKER"):
            prov(method=m, reliability=Reliability.VERIFIED)
    # ...but it may grade STATED, which is what Fletcher's professional takeoff is not far from.
    assert prov(method=MeasurementMethod.DESIGN_DRAWING_DIMENSION,
                reliability=Reliability.STATED).reliability is Reliability.STATED


def test_measured_cannot_be_built_without_a_provenance():
    with pytest.raises(TypeError):
        Measured(2.5)                       # type: ignore[call-arg]
    with pytest.raises(ValueError, match="promoted default is not a provenance"):
        Measured(2.5, None)                 # type: ignore[arg-type]
    with pytest.raises(ValueError, match="not a measurement"):
        Measured(float("nan"), prov("m"))


def test_the_schema_has_no_way_to_express_a_typical_value():
    """AC-1's teeth. Three AST checks over every module in the package."""
    banned_members = {"ASSUMED", "TYPICAL", "DEFAULT", "INDUSTRY_STANDARD", "COMPUTED_FROM_VOLUME",
                      "SCALED_FROM_RASTER", "INFERRED", "ESTIMATED"}
    banned_names = re.compile(r"(DEFAULT|TYPICAL|ASSUMED)_|_(DEFAULT|TYPICAL|ASSUMED)$"
                              r"|^(WALL_HEIGHT|CEILING_HEIGHT|PACK_COVERAGE|WASTAGE)")
    for path in sorted(PKG.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            # (1) no enum member an inference could declare itself under
            if isinstance(node, ast.ClassDef):
                for stmt in node.body:
                    if isinstance(stmt, ast.Assign):
                        for t in stmt.targets:
                            if isinstance(t, ast.Name):
                                assert t.id not in banned_members, f"{path.name}: {t.id}"
            # (2) no module-level constant that is a promoted default: a NUMBER bound to a name
            #     that reads like one. (An abstention reason code is a string and is the opposite
            #     of a default, so the check is on the VALUE as well as on the name.)
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                numeric = (isinstance(node.value, ast.Constant)
                           and isinstance(node.value.value, (int, float))
                           and not isinstance(node.value.value, bool))
                for t in targets:
                    if isinstance(t, ast.Name) and numeric and banned_names.search(t.id):
                        raise AssertionError(f"{path.name}: {t.id} looks like a promoted default")
            # (3) a field that carries a measurement may default to ABSENCE and to nothing else:
            #     None for a single measurement, an empty mapping for a collection of them.
            if isinstance(node, ast.AnnAssign) and node.value is not None:
                ann = ast.unparse(node.annotation)
                if "Measured" in ann:
                    assert ast.unparse(node.value) in ("None", "field(default_factory=dict)"), \
                        f"{path.name}: {ast.unparse(node.target)} defaults to a value, not absence"


def test_no_quotient_or_assumption_can_enter_as_a_measurement_method():
    names = {m.name for m in MeasurementMethod}
    assert names == {"AS_BUILT_PHYSICAL_SURVEY", "INSTRUMENTED_SURVEY", "PROFESSIONAL_TAKEOFF",
                     "DESIGN_DRAWING_DIMENSION", "PUBLISHER_COMPUTED"}
    assert F.NO_HEIGHT_FROM_VOLUME is True
    assert F.OBSERVED_VOLUME_OVER_AREA_SPAN_M == (2.045, 4.225)


def test_the_grade_ladder_has_no_rung_for_a_promoted_default():
    assert {r.name for r in Reliability} == {"VERIFIED", "STATED", "DERIVED", "UNVERIFIED"}
    assert F.ACCURACY_BEARING == frozenset({Reliability.VERIFIED, Reliability.STATED})


def test_units_must_match_the_material_and_a_licence_is_required():
    with pytest.raises(ValueError, match="#263 V3"):
        ReferenceValue(material=Material.BASEBOARD_LENGTH, scope="R1", value=1.0,
                       provenance=prov("m2"))
    with pytest.raises(ValueError, match="#263 P2"):
        ReferenceProject(project_id="x", publisher="y", licence="  ")


# =============================================== AC-2 — the formulas (CORRECTNESS, not accuracy)

def test_layer_3_geometry_is_exact_on_a_rectangle_and_an_l():
    assert RoomGeometry(rect(4.0, 3.0)).area_m2() == pytest.approx(12.0)
    assert RoomGeometry(rect(4.0, 3.0)).perimeter_m() == pytest.approx(14.0)
    ell = ((0.0, 0.0), (6.0, 0.0), (6.0, 2.0), (3.0, 2.0), (3.0, 5.0), (0.0, 5.0))
    assert RoomGeometry(ell).area_m2() == pytest.approx(6 * 2 + 3 * 3)
    assert RoomGeometry(ell).perimeter_m() == pytest.approx(6 + 2 + 3 + 3 + 3 + 5)


def test_f1_flooring_area_is_the_net_plan_area_with_no_deduction():
    room = RoomRecord(id="R1", polygon=rect(4.0, 3.0))
    q = FO.flooring_area(simple_project(rooms=(room,)), room)
    assert q.computed and q.value == pytest.approx(12.0) and q.unit == "m2"
    assert q.workings["net_floor_area_m2"] == pytest.approx(12.0)
    assert any("FLOORING_DEDUCTS_FIXTURE_FOOTPRINT=False" in c for c in q.conventions)
    assert q.assumptions


def test_f1_purchase_quantity_rounds_up_and_applies_the_stated_wastage():
    room = RoomRecord(id="R1", polygon=rect(4.0, 3.0),
                      finishes={Surface.FLOOR: Measured("oak-board", prov("m2"))})
    p = simple_project(rooms=(room,), distinguishes_finishes=True, product_specs={
        "oak-board": ProductSpec("oak-board", Measured(2.0, prov("m2")),
                                 Measured(0.10, prov("m2")))})
    q = FO.flooring_purchase(p, room)
    # 12.0 m2 x 1.10 = 13.2 m2 ; 13.2 / 2.0 = 6.6 -> 7 packs
    assert q.computed and q.value == 7.0 and q.unit == "pack"
    assert q.workings["area_with_wastage_m2"] == pytest.approx(13.2)


def test_f2_wall_paint_is_perimeter_times_stated_height_less_stated_openings():
    room = RoomRecord(id="R1", polygon=rect(4.0, 3.0), wall_height=Measured(2.5, prov("m")))
    op = OpeningRecord(id="D1", kind=OpeningKind.DOOR, room_ids=("R1",),
                       width=Measured(0.9, prov("m")), area=Measured(1.8, prov("m2")))
    p = simple_project(rooms=(room,), openings=(op,), opening_schedule_complete=True)
    q = FO.wall_paint_area(p, room)
    assert q.computed and q.value == pytest.approx(14.0 * 2.5 - 1.8)
    assert q.workings["gross_wall_area_m2"] == pytest.approx(35.0)
    assert q.workings["opening_deduction_m2"] == pytest.approx(1.8)
    assert any("WALL_PAINT_DEDUCTS_SKIRTING_BAND=False" in c for c in q.conventions)
    assert any("NEVER INFERRED" in a for a in q.assumptions)


def test_f3_ceiling_is_the_plan_area_less_stated_ceiling_openings():
    room = RoomRecord(id="R1", polygon=rect(4.0, 3.0))
    sky = OpeningRecord(id="S1", kind=OpeningKind.CEILING_OPENING, room_ids=("R1",),
                        surface=Surface.CEILING, area=Measured(0.6, prov("m2")))
    q = FO.ceiling_paint_area(simple_project(rooms=(room,), openings=(sky,)), room)
    assert q.computed and q.value == pytest.approx(12.0 - 0.6)
    assert any("NOT CHECKABLE" in a for a in q.assumptions)


def test_f4_baseboard_breaks_at_every_stated_door_opening():
    room = RoomRecord(id="R1", polygon=rect(4.0, 3.0))
    d1 = OpeningRecord(id="D1", kind=OpeningKind.DOOR, room_ids=("R1",),
                       width=Measured(0.9, prov("m")))
    arch = OpeningRecord(id="D2", kind=OpeningKind.CASED_OPENING, room_ids=("R1",),
                         width=Measured(1.4, prov("m")))
    win = OpeningRecord(id="W1", kind=OpeningKind.WINDOW, room_ids=("R1",),
                        width=Measured(1.2, prov("m")))
    q = FO.baseboard_length(simple_project(rooms=(room,), openings=(d1, arch, win)), room)
    assert q.computed and q.value == pytest.approx(14.0 - 0.9 - 1.4)      # the window is not a break
    assert q.workings["doors"] == 2.0
    assert any("BASEBOARD_DEDUCTS_BUILT_IN_FURNITURE=False" in c for c in q.conventions)


@pytest.mark.parametrize("material", list(Material))
def test_every_result_carries_the_conventions_and_assumptions_that_produced_it(material):
    room = RoomRecord(id="R1", polygon=rect(4.0, 3.0), wall_height=Measured(2.5, prov("m")),
                      finishes={Surface.FLOOR: Measured("tile", prov("m2"))})
    p = simple_project(rooms=(room,), opening_schedule_complete=True, product_specs={
        "tile": ProductSpec("tile", Measured(1.5, prov("m2")), Measured(0.08, prov("m2")))})
    q = FO.compute_all(p, room)[material]
    assert q.outcome is FO.Outcome.COMPUTED, q.reason_detail
    assert q.conventions or q.assumptions
    assert q.inputs_used


# =========================================================================== AC-3 — abstention

def test_a_missing_height_abstains_with_a_reason_and_does_not_raise():
    room = RoomRecord(id="R1", polygon=rect(4.0, 3.0))                # no P8
    q = FO.wall_paint_area(simple_project(rooms=(room,), opening_schedule_complete=True), room)
    assert q.outcome is FO.Outcome.ABSTAINED
    assert q.reason is A.WALL_HEIGHT_NOT_STATED
    assert q.value is None and q.missing_field == "rooms[R1].wall_height"
    assert "2.045" in q.reason_detail and "4.225" in q.reason_detail


def test_a_missing_door_width_abstains_rather_than_treat_the_opening_as_solid_wall():
    room = RoomRecord(id="R1", polygon=rect(4.0, 3.0))
    d = OpeningRecord(id="D1", kind=OpeningKind.DOOR, room_ids=("R1",))     # no P6
    q = FO.baseboard_length(simple_project(rooms=(room,), openings=(d,)), room)
    assert q.outcome is FO.Outcome.ABSTAINED and q.reason is A.DOOR_WIDTH_NOT_STATED


def test_an_incomplete_opening_schedule_abstains_instead_of_deducting_zero():
    room = RoomRecord(id="R1", polygon=rect(4.0, 3.0), wall_height=Measured(2.5, prov("m")))
    p = simple_project(rooms=(room,), opening_schedule_complete=False)
    q = FO.wall_paint_area(p, room)
    assert q.outcome is FO.Outcome.ABSTAINED and q.reason is A.OPENING_SCHEDULE_NOT_COMPLETE


def test_a_missing_wastage_allowance_costs_the_pack_count_and_not_the_area():
    room = RoomRecord(id="R1", polygon=rect(4.0, 3.0),
                      finishes={Surface.FLOOR: Measured("tile", prov("m2"))})
    p = simple_project(rooms=(room,), distinguishes_finishes=True, product_specs={
        "tile": ProductSpec("tile", Measured(1.5, prov("m2")), None)})
    qs = FO.compute_all(p, room)
    assert qs[Material.FLOORING_AREA].computed
    assert qs[Material.FLOORING_PURCHASE].reason is A.WASTAGE_ALLOWANCE_NOT_STATED
    assert "not a guess" in qs[Material.FLOORING_PURCHASE].reason_detail


def test_an_unsupported_finish_category_is_its_own_outcome():
    room = RoomRecord(id="R1", polygon=rect(4.0, 3.0),
                      finishes={Surface.FLOOR: Measured("terrazzo", prov("m2"))})
    q = FO.flooring_purchase(simple_project(rooms=(room,), product_specs={}), room)
    assert q.reason is A.UNSUPPORTED_FINISH_CATEGORY


def test_no_formula_raises_on_an_empty_room_and_failure_is_separate_from_abstention():
    room = RoomRecord(id="R1")                              # no polygon, no area, nothing
    qs = FO.compute_all(simple_project(rooms=(room,)), room)
    assert {q.outcome for q in qs.values()} == {FO.Outcome.ABSTAINED}
    assert all(q.reason is not None and q.reason_detail for q in qs.values())
    assert FO.Outcome.FAILED not in {q.outcome for q in qs.values()}


def test_every_abstention_reason_names_one_field_a_human_could_supply():
    """The manual-correction-effort metric is a count of these, so each must name a field."""
    room = RoomRecord(id="R1")
    for q in FO.compute_all(simple_project(rooms=(room,)), room).values():
        assert q.missing_field, q.material


# =========================================================================== AC-4 — the harness

def test_the_harness_emits_every_metric_the_directive_lists():
    room = RoomRecord(id="R1", polygon=rect(4.0, 3.0), wall_height=Measured(2.5, prov("m")))
    p = simple_project(rooms=(room,), opening_schedule_complete=True)
    js = H.to_json(H.evaluate([p]))
    for m in Material:
        mm = js["comparison_a"]["per_material"][m.value]
        for key in ("mean_absolute_error", "max_absolute_error", "mean_percentage_error",
                    "missing_measurements", "unsupported_categories",
                    "manual_correction_effort", "manual_correction_effort_total",
                    "provenance_completeness", "failure_rate", "abstention_rate",
                    "within_tolerance_rate", "passes"):
            assert key in mm, (m, key)


def test_comparison_b_is_a_separate_output_that_is_not_applicable_and_carries_no_number():
    js = H.to_json(H.evaluate([simple_project()]))
    a, b = js["comparison_a"], js["comparison_b"]
    assert a["label"] == "A" and b["label"] == "B"
    assert b["applicable"] is False
    assert b["status"] == "NOT APPLICABLE" and F.COMPARISON_B_STATUS == "NOT APPLICABLE"
    assert "#257" in b["reason"] and "python-multipart" in b["reason"]
    assert not any(isinstance(v, (int, float)) and not isinstance(v, bool) for v in b.values())
    assert "per_material" not in b
    # and B is a different TYPE from A, so it cannot be folded into it
    assert type(H.ComparisonB()) is not type(H.ComparisonA())


def test_a_percentage_error_is_omitted_where_the_denominator_makes_it_meaningless():
    assert F.percentage_error(Material.FLOORING_AREA, 1.0, 0.4) is None
    assert F.percentage_error(Material.FLOORING_AREA, 10.2, 10.0) == pytest.approx(2.0)


def test_a_material_with_no_accuracy_bearing_comparison_passes_nothing_and_fails_nothing():
    js = H.to_json(H.evaluate([simple_project()]))
    assert all(mm["passes"] is None for mm in js["comparison_a"]["per_material"].values())
    assert js["verdict"] == "NOT_EVALUABLE"
    assert "NOT TESTABLE" in js["layer_1_source_measurement_accuracy"]


# ======================================================== AC-5 — the self-validation guard

def test_the_identity_band_sits_far_above_the_observed_residual_of_the_19_plans():
    ev = RUN.identity_evidence()
    assert ev["plans"] == F.RESPLAN_PLANS == 19
    assert ev["rooms"] == F.RESPLAN_ROOMS == 179
    assert ev["max_residual_m2"] == pytest.approx(F.RESPLAN_MAX_AREA_RESIDUAL_M2, abs=1e-9)
    assert ev["inside_band"] == 179 and ev["outside_band"] == 0
    assert ev["headroom_at_worst_room"] > 30


@pytest.mark.parametrize("arm", RP.ARMS)
def test_the_19_plans_are_refused_as_a_reference_for_their_own_area_field(arm):
    """AC-5's demonstration. 19 plans x 179 rooms x 2 area materials = 358 offered references, and
    not one of them may be scored."""
    projects = RP.projects(arm)
    assert len(projects) == 19
    assert sum(len(p.rooms) for p in projects) == 179
    js = H.to_json(H.evaluate(projects))
    per = js["comparison_a"]["per_material"]
    assert sum(mm["accuracy_comparisons"] for mm in per.values()) == 0
    assert sum(mm["cross_check_comparisons"] for mm in per.values()) == 0
    assert sum(mm["refused_comparisons"] for mm in per.values()) == 358
    reasons: dict[str, int] = {}
    for mm in per.values():
        for k, v in mm["refusal_reasons"].items():
            reasons[k] = reasons.get(k, 0) + v
    assert reasons[RefusalReason.GEOMETRIC_IDENTITY.value] == 358


def test_the_optimistic_arm_is_refused_by_the_identity_guard_alone():
    """The arm that matters: the same number offered in the strongest form an advocate could claim.
    R1 finds nothing wrong with it. R2 must refuse it anyway, on the residual alone."""
    js = H.to_json(H.evaluate(RP.projects(RP.OPTIMISTIC)))
    reasons: dict[str, int] = {}
    for mm in js["comparison_a"]["per_material"].values():
        for k, v in mm["refusal_reasons"].items():
            reasons[k] = reasons.get(k, 0) + v
    assert reasons == {RefusalReason.GEOMETRIC_IDENTITY.value: 358}


def test_a_reference_that_is_genuinely_different_is_not_refused_by_the_identity_guard():
    """CORRECTNESS, on synthetic geometry: the guard must not simply refuse everything. A reference
    1.5% away from the computed figure is outside the identity band and inside the frozen flooring
    tolerance, so it is scored."""
    ref = 12.0 * 1.015
    assert SC.refuse_identity(Material.FLOORING_AREA, ref, 12.0) is None
    assert F.within_tolerance(Material.FLOORING_AREA, 12.0, ref)
    # and one 0.03% away is inside the band, so it is refused
    assert SC.refuse_identity(Material.FLOORING_AREA, 12.0 * 1.0003, 12.0) is not None


def test_a_zero_residual_is_refused_under_any_band():
    r = SC.refuse_identity(Material.BASEBOARD_LENGTH, 7.0, 7.0)
    assert r is not None and "any band" in r.detail


def test_r1_refuses_a_publisher_computed_figure_of_the_same_class():
    room = RoomRecord(id="R1", polygon=rect(4.0, 3.0))
    p = simple_project(rooms=(room,))
    ref = ReferenceValue(material=Material.FLOORING_AREA, scope="R1", value=99.0,
                         provenance=prov("m2", method=MeasurementMethod.PUBLISHER_COMPUTED,
                                         reliability=Reliability.DERIVED))
    reasons = {r.reason for r in SC.refuse_declared(p, ref)}
    assert RefusalReason.SAME_CALCULATION_CLASS in reasons
    assert RefusalReason.NOT_ACCURACY_BEARING in reasons


def test_r1_refuses_a_value_that_names_this_system_in_its_independence_statement():
    p = simple_project()
    ref = ReferenceValue(material=Material.FLOORING_AREA, scope="R1", value=99.0,
                         provenance=prov("m2", independence="computed by BuildSmart's own engine"))
    assert RefusalReason.NOT_INDEPENDENT in {r.reason for r in SC.refuse_declared(p, ref)}


def test_r1_refuses_the_accuracy_claim_when_the_measurement_convention_is_unstated():
    p = simple_project(convention=MeasurementConvention.UNSTATED)
    ref = ReferenceValue(material=Material.FLOORING_AREA, scope="R1", value=99.0, provenance=prov())
    rs = SC.refuse_declared(p, ref)
    assert RefusalReason.CONVENTION_UNSTATED in {r.reason for r in rs}
    assert SC.worst(rs) is SC.Severity.CROSS_CHECK_ONLY       # reportable, never aggregated


def test_r1_refuses_a_value_declared_as_computed_from_the_supplied_geometry():
    ref = ReferenceValue(material=Material.FLOORING_AREA, scope="R1", value=99.0, provenance=prov(),
                         computed_from_supplied_geometry=True)
    assert RefusalReason.DERIVED_FROM_SUPPLIED_GEOMETRY in {
        r.reason for r in SC.refuse_declared(simple_project(), ref)}


def test_every_refusal_reason_has_a_severity():
    assert set(SC.SEVERITY) == set(RefusalReason)


# ============================================ the 1923 Fletcher takeoff: a real reference quantity

def test_the_fletcher_licence_is_the_verified_public_domain_mark():
    d = FL.load()
    assert d["source"]["licenseurl"] == "http://creativecommons.org/publicdomain/mark/1.0/"
    assert d["source"]["date"] == 1923
    assert "metadata API" in d["source"]["licence_verified"]


def test_the_fletcher_transcription_reproduces_the_books_own_printed_totals():
    """The transcription's integrity check: a girth must equal the sum of its own waste column and a
    squaring must equal the product of its own dimension pair, as printed. A reading that did not
    reproduce the book's own arithmetic was not recorded."""
    d = FL.load()
    for r in d["rooms"]:
        w, l = r["ceiling_dimensions_ft"]
        if not r.get("ceiling_is_not_a_rectangle"):
            assert r["ceiling_area_ft2"] == pytest.approx(w * l), r["id"]
        if "wall_gross_ft2" in r:
            assert r["wall_gross_ft2"] == pytest.approx(r["wall_girth_ft"] * r["wall_height_ft"])
        if "wall_deductions_ft2" in r:
            tot = sum(x["n"] * x["w_ft"] * x["h_ft"] for x in r["wall_deductions_ft2"])
            assert tot == pytest.approx(r["wall_deductions_total_ft2"]), r["id"]
            assert r["wall_net_ft2"] == pytest.approx(r["wall_gross_ft2"] - tot)
    assert len(d["transcription_verification"]["checks_passed"]) >= 8


def test_the_fletcher_project_fits_the_schema_without_inventing_a_field():
    p = FL.project()
    assert p.convention is MeasurementConvention.INTERNAL_CLEAR     # P11, cited to p.128
    assert p.wall_thickness is not None                            # P11a, from Plate 8
    assert p.scale is not None                                     # P3, a figured drawing
    assert all(r.wall_height is not None for r in p.rooms)          # P8, stated, never a quotient
    assert all(ref.provenance.method is MeasurementMethod.PROFESSIONAL_TAKEOFF
               and ref.provenance.reliability is Reliability.STATED for ref in p.references)
    # The Scullery's 20'9" is a partial girth, so it is NOT offered as a perimeter.
    scullery = p.room("SCULLERY")
    assert scullery is not None and scullery.stated_perimeter is None


def test_fletcher_ceiling_references_are_refused_as_a_geometric_identity():
    """The same guard, on a real professional takeoff. When the geometry comes from the dimension
    columns the quantity was squared from, recomputing it is arithmetic, not accuracy -- and the
    harness says so instead of reporting a perfect score."""
    js = H.to_json(H.evaluate([FL.project()]))
    ceiling = [c for q in js["quantities"] for c in q.get("comparisons", [])
               if c["material"] == Material.CEILING_PAINT_AREA.value]
    assert len(ceiling) == 3
    for c in ceiling:
        assert c["status"] == "REFUSED"
        assert c["identity_residual"] == pytest.approx(0.0, abs=1e-12)
        assert RefusalReason.GEOMETRIC_IDENTITY.value in {r["reason"] for r in c["refusals"]}
    assert sum(mm["accuracy_comparisons"]
               for mm in js["comparison_a"]["per_material"].values()) == 0


def test_fletcher_wall_paint_abstains_because_its_opening_schedule_is_not_complete():
    js = H.to_json(H.evaluate([FL.project()]))
    walls = [q for q in js["quantities"] if q["material"] == Material.WALL_PAINT_AREA.value]
    assert {q["reason"] for q in walls} == {A.OPENING_SCHEDULE_NOT_COMPLETE.value,
                                            A.PERIMETER_NOT_AVAILABLE.value}


def test_the_convention_audit_measures_the_divergence_and_calls_it_a_convention():
    a = FL.convention_audit()
    f4 = [d for d in a["measured_divergences"] if d["formula"].startswith("F4")]
    assert f4, "the skirting convention divergence must be measured, not described"
    d = f4[0]
    assert d["divergence_pct"] == pytest.approx(-23.943661971830984, abs=1e-9)
    assert d["exceeds_tolerance"] is True
    assert "same work under two conventions" in d["this_is_not_an_error"]
    # every contested convention of the four formulas has the source's own rule beside it
    rules = {r["formula"].split()[0] for r in a["rules"]}
    assert {"F1", "F2", "F3", "F4"} <= rules
    assert any(r["agrees"] is False for r in a["rules"])


def test_the_relayed_nichols_arithmetic_checks_out():
    """The one cross-check that can be verified without fetching the source: a HALF deduction for
    openings is a third convention, and the relayed figures are arithmetically consistent."""
    d = FL.load()
    n = [c for c in d["cross_checks_not_transcribed"] if c["source"].startswith("Nichols")][0]
    assert 13141 - (32 * 40 + 34 * 15) / 2 == 12246
    assert "NOT fetched" in n["status"]


# =========================================================================== AC-6 — commit order

def test_the_acceptance_thresholds_are_exactly_what_was_frozen():
    """If this test has to be edited to make a result pass, the result is invalid."""
    assert F.TOLERANCE_REL == {
        Material.FLOORING_AREA: 0.020, Material.CEILING_PAINT_AREA: 0.020,
        Material.BASEBOARD_LENGTH: 0.025, Material.WALL_PAINT_AREA: 0.030,
        Material.FLOORING_PURCHASE: 0.0}
    assert F.TOLERANCE_ABS == {
        Material.FLOORING_AREA: 0.10, Material.CEILING_PAINT_AREA: 0.10,
        Material.BASEBOARD_LENGTH: 0.10, Material.WALL_PAINT_AREA: 0.10,
        Material.FLOORING_PURCHASE: 0.0}
    assert (F.MIN_WITHIN_TOLERANCE_RATE, F.MAX_ABSTENTION_RATE, F.MAX_FAILURE_RATE) == (0.90, 0.25, 0.0)
    assert (F.IDENTITY_ABS_M2, F.IDENTITY_ABS_M, F.IDENTITY_REL) == (0.01, 0.01, 0.0005)
    assert (F.MIN_PROJECTS_WITH_HEIGHT, F.MIN_PROJECTS_WITHOUT_HEIGHT,
            F.MIN_DISTINCT_PUBLISHERS) == (3, 5, 2)


def test_the_within_tolerance_rule_uses_the_absolute_floor_for_a_small_scope():
    assert F.within_tolerance(Material.FLOORING_AREA, 1.05, 1.0)       # 0.05 <= 0.10 floor
    assert not F.within_tolerance(Material.FLOORING_AREA, 1.2, 1.0)
    assert F.within_tolerance(Material.FLOORING_PURCHASE, 7.0, 7.0)
    assert not F.within_tolerance(Material.FLOORING_PURCHASE, 8.0, 7.0)   # exact match required


def test_the_verdict_function_refuses_to_evaluate_without_an_accuracy_bearing_reference():
    v, why = F.verdict(projects_with_height=99, projects_without_height=99,
                       distinct_publishers=9, materials_passing=0, materials_evaluated=0)
    assert v is F.Verdict.NOT_EVALUABLE and "#263 acquired none" in why
    assert F.verdict(projects_with_height=3, projects_without_height=5, distinct_publishers=2,
                     materials_passing=4, materials_evaluated=4)[0] is F.Verdict.GO
    assert F.verdict(projects_with_height=0, projects_without_height=5, distinct_publishers=2,
                     materials_passing=3, materials_evaluated=4)[0] is F.Verdict.CONDITIONAL_GO
    assert F.verdict(projects_with_height=3, projects_without_height=5, distinct_publishers=2,
                     materials_passing=0, materials_evaluated=4)[0] is F.Verdict.NO_GO


def test_git_history_shows_the_thresholds_were_committed_before_any_result():
    """AC-6 is an ordering claim, so it is tested against the ordering."""
    def first_commit(path: str) -> str | None:
        out = subprocess.run(["git", "log", "--follow", "--format=%H", "--reverse", "--", path],
                             cwd=REPO, capture_output=True, text=True)
        lines = [x for x in out.stdout.split() if x]
        return lines[0] if lines else None

    frozen_commit = first_commit("backend/app/ai_harness/quantity_takeoff/frozen.py")
    if frozen_commit is None:
        pytest.skip("frozen.py is not committed yet")
    results = REPO / "docs/reports/construction-intelligence/data/QUANTITY-harness-results.json"
    results_commit = first_commit(str(results.relative_to(REPO)))
    if results_commit is None:
        pytest.skip("no results commit exists yet, which also satisfies the ordering")
    order = subprocess.run(["git", "rev-list", "--count", f"{frozen_commit}..{results_commit}"],
                           cwd=REPO, capture_output=True, text=True)
    assert order.returncode == 0 and int(order.stdout.strip()) >= 1, (
        "the results commit must be a descendant of the freeze commit")


# ====================================================================== AC-7 — isolation

def test_nothing_outside_the_harness_directory_imports_it():
    app = BACKEND / "app"
    offenders = [str(p.relative_to(REPO)) for p in app.rglob("*.py")
                 if PKG not in p.parents and "quantity_takeoff" in p.read_text()]
    assert offenders == []


def test_the_harness_imports_no_generator_validator_and_no_production_module():
    """#242's R1 measured why: the generator's validators refused a POLICY condition unrelated to
    geometry in 18 of 19 real plans, so they encode what the generator may build, not what a
    building is. ROOT #262 AC-3 forbids their use as a building-validity check here."""
    forbidden = ("validation", "rectilinear_realizer", "concept_generator", "geometry_core",
                 "vertical_slice", "demo", "app.ai_harness.topology_poc")
    for path in sorted(PKG.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            for m in mods:
                assert not any(f in m for f in forbidden), f"{path.name} imports {m}"


def test_the_harness_rebinds_nothing_and_patches_nothing():
    """It may READ anything it imports; it may rebind nothing in it."""
    for path in sorted(PKG.glob("*.py")):
        text = path.read_text()
        assert "monkeypatch" not in text and "setattr(" not in text, path.name
        tree = ast.parse(text)
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules |= {(a.asname or a.name.split(".")[0]) for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                modules |= {(a.asname or a.name) for a in node.names}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name):
                        assert t.value.id not in modules, f"{path.name} rebinds {ast.unparse(t)}"


def test_deleting_the_directory_would_restore_the_tree():
    """Everything this package owns lives under its own directory, its own test file, and its own
    report/data files. Nothing else in the repository names it."""
    out = subprocess.run(["git", "diff", "--name-only", "origin/main...HEAD"],
                         cwd=REPO, capture_output=True, text=True)
    if out.returncode != 0:
        pytest.skip("no origin/main to diff against")
    changed = [p for p in out.stdout.split() if p]
    allowed = ("backend/app/ai_harness/quantity_takeoff/",
               "backend/tests/ai_harness/test_quantity_takeoff.py",
               "docs/reports/construction-intelligence/")
    assert [p for p in changed if not p.startswith(allowed)] == []


def test_no_price_or_rate_appears_anywhere_in_the_harness():
    """Layer 6, pricing, is out of this ROOT's scope and is absent rather than stubbed. The scan is
    over IDENTIFIERS, because the modules are allowed to say in prose that pricing is absent."""
    banned = ("price", "cost", "rate_per", "currency", "gbp", "usd", "tender", "quote")
    for path in sorted(PKG.glob("*.py")):
        tree = ast.parse(path.read_text())
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
            elif isinstance(node, ast.arg):
                names.add(node.arg)
        for n in names:
            low = n.lower()
            assert not any(b in low for b in banned), f"{path.name} defines/uses {n}"


# ====================================================================== the results, when they exist

def test_the_committed_results_are_consistent_with_the_frozen_module():
    path = REPO / "docs/reports/construction-intelligence/data/QUANTITY-harness-results.json"
    if not path.exists():
        pytest.skip("the harness has not been run into a results file yet")
    data = json.loads(path.read_text())
    assert data["identity_evidence"]["rooms"] == 179
    assert data["identity_evidence"]["outside_band"] == 0
    for arm in RP.ARMS:
        s = data["arms"][arm]["summary"]
        assert s["reference_values_offered"] == 358
        assert s["comparisons_refused"] == 358
        assert s["comparisons_scored_as_accuracy"] == 0
        assert s["verdict"] == "NOT_EVALUABLE"
    fl = data["fletcher_1923"]
    assert fl["summary"]["comparisons_scored_as_accuracy"] == 0
    assert "AXIS 1" in fl["what_it_does_not_validate"]
    assert math.isclose(data["identity_evidence"]["max_residual_m2"],
                        F.RESPLAN_MAX_AREA_RESIDUAL_M2, abs_tol=1e-9)
