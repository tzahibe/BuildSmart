"""SELECTED_FOOTPRINT_E2E: proves a user-selected rectangular footprint becomes AUTHORITATIVE
planning geometry end to end --

    Frontend BuildingFootprint -> POST /projects -> ProjectCreate -> Project (persisted)
    -> generate_design_via_solver -> _derive_footprint -> GeometrySolver / concept-first planner
    -> GeometricDesign

-- and that the backend does NOT silently recompute a square from area once an explicit selection
exists (the confirmed problem this task starts from). Covers cases A-E from the task spec plus the
"geometry authority" trace (requirement 7): once `_derive_footprint` returns a non-square
`BuildingFootprintSpec`, both the legacy `GeometrySolver` and the concept-first `plan_with_concepts`
already respect it generically (they take `footprint` as a parameter and read only its
`width_m`/`depth_m`/`available_area_m2` -- confirmed by direct trace, not assumed), so no separate
fix was needed in either.
"""

import math
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.architect.authoritative_merge import merge_authoritative_requirements
from app.architect.gateway import MockArchitectModelGateway
from app.design.pipeline import _build_request, _derive_footprint, _FOOTPRINT_EFFICIENCY, generate_design_via_solver
from app.geometry.models import SolverStatus
from app.geometry.planning.planner import plan_with_concepts
from app.geometry.solver import GeometrySolver
from app.main import app
from app.projects.models import (
    FootprintSource,
    PoolField,
    Project,
    ProjectCreate,
    SelectedFootprint,
    SourceTag,
    TaggedBool,
    TaggedFloat,
    TaggedInt,
)
from app.projects.repository import JsonFileProjectRepository
from app.projects.routes import base_routes as project_base_routes

_CITY = "מודיעין-מכבים-רעות"
_STREET = "אגוז מכבים רעות"

_UNKNOWN_INT = TaggedInt(value=None, source=SourceTag.unknown)
_UNKNOWN_BOOL = TaggedBool(value=None, source=SourceTag.unknown)
_UNKNOWN_POOL = PoolField(
    requested=_UNKNOWN_BOOL,
    length_m=TaggedFloat(value=None, source=SourceTag.unknown),
    width_m=TaggedFloat(value=None, source=SourceTag.unknown),
)
_BEDROOMS_3 = TaggedInt(value=3, source=SourceTag.requested)
_SAFE_ROOM_YES = TaggedBool(value=True, source=SourceTag.requested)


def _footprint(
    *, width_m: float, depth_m: float, source: FootprintSource = FootprintSource.preset,
    target_area_m2: float | None = None, area_m2: float | None = None, shape_type: str = "RECTANGLE",
) -> SelectedFootprint:
    return SelectedFootprint(
        source=source,
        shape_type=shape_type,
        target_area_m2=target_area_m2 if target_area_m2 is not None else round(width_m * depth_m, 2),
        width_m=width_m,
        depth_m=depth_m,
        area_m2=area_m2 if area_m2 is not None else round(width_m * depth_m, 2),
    )


def _project(
    *, built_area_m2: float = 200.0, plot_area_m2: float = 500.0,
    bedrooms: TaggedInt = _BEDROOMS_3, safe_room: TaggedBool = _SAFE_ROOM_YES,
    selected_footprint: SelectedFootprint | None = None,
) -> Project:
    now = datetime.now(UTC)
    return Project(
        project_id="test-project", city=_CITY, street=_STREET,
        plot_area_m2=plot_area_m2, built_area_m2=built_area_m2, description="test",
        status="created", created_at=now, updated_at=now,
        floors=TaggedInt(value=1, source=SourceTag.requested), bedrooms=bedrooms, safe_room=safe_room,
        parking_spaces=_UNKNOWN_INT, pool=_UNKNOWN_POOL, requirements_parsed_at=now,
        selected_footprint=selected_footprint,
    )


def _room_fits(room, width_m: float, depth_m: float) -> bool:
    return room.x >= -1e-6 and room.y >= -1e-6 and room.x + room.width_m <= width_m + 1e-6 and room.y + room.depth_m <= depth_m + 1e-6


# --- Case A: rectangular selection (10x20 for a 200 m2 target) survives the whole pipeline --------


def test_derive_footprint_uses_the_exact_selected_rectangle_not_a_derived_square():
    project = _project(built_area_m2=200.0, selected_footprint=_footprint(width_m=10, depth_m=20))

    spec = _derive_footprint(project)

    assert spec.width_m == 10
    assert spec.depth_m == 20
    # never sqrt(area) x sqrt(area)
    assert spec.width_m != pytest.approx(math.sqrt(200.0), rel=1e-3)


def test_case_a_10x20_survives_derive_footprint_through_geometric_design():
    project = _project(built_area_m2=200.0, selected_footprint=_footprint(width_m=10, depth_m=20))

    design = generate_design_via_solver(project)

    footprint = design.geometric_design["footprint"]
    assert footprint["width_m"] == 10
    assert footprint["depth_m"] == 20
    assert len(design.rooms) > 0
    for room in design.rooms:
        assert _room_fits(room, 10, 20), f"{room.type} at ({room.x},{room.y}) {room.width_m}x{room.depth_m} escapes 10x20"


def test_case_a_via_the_real_http_api_create_then_design(client, repo):
    footprint_payload = {
        "source": "CUSTOM", "shape_type": "RECTANGLE",
        "target_area_m2": 200, "width_m": 10, "depth_m": 20, "area_m2": 200,
    }
    project_id = _create_and_parse_project(client, repo, selected_footprint=footprint_payload, built_area_m2=200)

    created = client.get(f"/projects/{project_id}").json()
    assert created["selected_footprint"]["width_m"] == 10
    assert created["selected_footprint"]["depth_m"] == 20

    response = client.post(f"/projects/{project_id}/design")
    assert response.status_code == 200
    footprint = response.json()["geometric_design"]["footprint"]
    assert footprint["width_m"] == 10
    assert footprint["depth_m"] == 20


# --- Case B: equal area, different shape -- must never converge -----------------------------------


def test_case_b_equal_area_different_shape_never_converge():
    square_side = math.sqrt(200.0)
    square = _project(built_area_m2=200.0, selected_footprint=_footprint(width_m=square_side, depth_m=square_side))
    rect = _project(built_area_m2=200.0, selected_footprint=_footprint(width_m=10, depth_m=20))

    square_spec = _derive_footprint(square)
    rect_spec = _derive_footprint(rect)

    assert (round(square_spec.width_m, 3), round(square_spec.depth_m, 3)) != (rect_spec.width_m, rect_spec.depth_m)
    assert rect_spec.width_m == 10 and rect_spec.depth_m == 20  # the 10x20 selection is untouched

    square_design = generate_design_via_solver(square)
    rect_design = generate_design_via_solver(rect)
    square_fp = square_design.geometric_design["footprint"]
    rect_fp = rect_design.geometric_design["footprint"]

    assert (round(square_fp["width_m"], 3), round(square_fp["depth_m"], 3)) != (rect_fp["width_m"], rect_fp["depth_m"])
    assert rect_fp["width_m"] == 10 and rect_fp["depth_m"] == 20  # STILL never collapsed to the square


# --- Case C: CUSTOM travels exactly the same path as PRESET ---------------------------------------


def test_case_c_custom_produces_the_exact_selected_dimensions():
    project = _project(
        built_area_m2=200.0,
        selected_footprint=_footprint(source=FootprintSource.custom, width_m=8, depth_m=25),
    )

    spec = _derive_footprint(project)
    assert spec.width_m == 8 and spec.depth_m == 25

    design = generate_design_via_solver(project)
    footprint = design.geometric_design["footprint"]
    assert footprint["width_m"] == 8 and footprint["depth_m"] == 25
    for room in design.rooms:
        assert _room_fits(room, 8, 25)


def test_preset_and_custom_with_identical_dimensions_produce_identical_footprint_spec():
    """PRESET vs CUSTOM must be indistinguishable to the planning path -- `source` is provenance
    metadata only, never a branch in `_derive_footprint` or anything downstream of it."""
    preset = _project(built_area_m2=200.0, selected_footprint=_footprint(source=FootprintSource.preset, width_m=8, depth_m=25))
    custom = _project(built_area_m2=200.0, selected_footprint=_footprint(source=FootprintSource.custom, width_m=8, depth_m=25))

    assert _derive_footprint(preset) == _derive_footprint(custom)


# --- Case D: invalid selected footprints are rejected, never silently repaired --------------------


def test_case_d_non_positive_dimensions_rejected():
    with pytest.raises(ValidationError):
        SelectedFootprint(source=FootprintSource.custom, shape_type="RECTANGLE", target_area_m2=200, width_m=0, depth_m=20, area_m2=0)
    with pytest.raises(ValidationError):
        SelectedFootprint(source=FootprintSource.custom, shape_type="RECTANGLE", target_area_m2=200, width_m=10, depth_m=-5, area_m2=-50)


def test_case_d_unsupported_shape_type_rejected():
    with pytest.raises(ValidationError):
        SelectedFootprint(source=FootprintSource.custom, shape_type="L_SHAPE", target_area_m2=200, width_m=10, depth_m=20, area_m2=200)


def test_case_d_area_field_inconsistent_with_dimensions_rejected_never_repaired():
    # width*depth=180, but area_m2 CLAIMS 200 -- a malformed/tampered payload, must be rejected
    with pytest.raises(ValidationError):
        SelectedFootprint(source=FootprintSource.custom, shape_type="RECTANGLE", target_area_m2=200, width_m=9, depth_m=20, area_m2=200)


def test_case_d_footprint_area_materially_mismatched_with_built_area_rejected_at_project_create():
    # task's own worked example: 9x20 = 180 m2, but the project's built_area_m2 is 200 -- rejected at
    # ProjectCreate, never silently accepted or normalized
    footprint = _footprint(width_m=9, depth_m=20)  # internally self-consistent (area_m2=180)
    with pytest.raises(ValidationError):
        ProjectCreate(
            city=_CITY, street=_STREET, plot_area_m2=500, built_area_m2=200,
            description="d", selected_footprint=footprint,
        )


def test_case_d_invalid_footprint_rejected_via_the_real_http_api(client):
    payload = {
        "city": _CITY, "street": _STREET, "plot_area_m2": 500, "built_area_m2": 200, "description": "d",
        "selected_footprint": {
            "source": "CUSTOM", "shape_type": "RECTANGLE",
            "target_area_m2": 200, "width_m": -1, "depth_m": 20, "area_m2": 200,
        },
    }
    response = client.post("/projects", json=payload)
    assert response.status_code == 422


def test_case_d_material_area_mismatch_rejected_via_the_real_http_api(client):
    payload = {
        "city": _CITY, "street": _STREET, "plot_area_m2": 500, "built_area_m2": 200, "description": "d",
        "selected_footprint": {
            "source": "CUSTOM", "shape_type": "RECTANGLE",
            "target_area_m2": 200, "width_m": 9, "depth_m": 20, "area_m2": 180,
        },
    }
    response = client.post("/projects", json=payload)
    assert response.status_code == 422


# --- Case E: legacy caller (selected_footprint absent) ---------------------------------------------


def test_case_e_legacy_caller_without_selected_footprint_keeps_the_old_square_derivation():
    project = _project(built_area_m2=200.0, selected_footprint=None)

    spec = _derive_footprint(project)

    expected_side = math.sqrt(200.0 / _FOOTPRINT_EFFICIENCY)
    assert spec.width_m == pytest.approx(expected_side)
    assert spec.depth_m == pytest.approx(expected_side)
    assert spec.available_area_m2 == 200.0  # unchanged: built_area_m2 flows straight through


def test_case_e_legacy_http_caller_without_selected_footprint_still_creates_and_designs(client, repo):
    project_id = _create_and_parse_project(client, repo, selected_footprint=None, built_area_m2=200)

    created = client.get(f"/projects/{project_id}").json()
    assert created["selected_footprint"] is None

    response = client.post(f"/projects/{project_id}/design")
    assert response.status_code == 200
    footprint = response.json()["geometric_design"]["footprint"]
    expected_side = math.sqrt(200.0 / _FOOTPRINT_EFFICIENCY)
    assert footprint["width_m"] == pytest.approx(expected_side)
    assert footprint["depth_m"] == pytest.approx(expected_side)


# --- Requirement 8: area semantics -- the 0.85 factor must never touch an explicit selection -------


def test_selected_footprint_area_is_never_inflated_by_the_legacy_0_85_factor():
    project = _project(built_area_m2=200.0, selected_footprint=_footprint(width_m=10, depth_m=20))
    spec = _derive_footprint(project)
    naive_inflated_side = math.sqrt(200.0 / _FOOTPRINT_EFFICIENCY)  # ~15.34, the old bug's behavior

    assert spec.width_m * spec.depth_m == pytest.approx(200.0, abs=0.5)
    assert spec.width_m != pytest.approx(naive_inflated_side, rel=1e-2)
    assert spec.depth_m != pytest.approx(naive_inflated_side, rel=1e-2)


def test_selected_footprint_available_area_never_exceeds_its_own_bounding_rectangle():
    """A PRESET's displayed dimensions are rounded to 2 decimals, so its true area can differ from
    the nominal target area by a sub-percent rounding gap -- `available_area_m2` must be capped so
    `BuildingFootprintSpec`'s own bounding-rectangle validator can never be violated by that gap
    (this is NOT the 15% circulation-margin heuristic; see pipeline.py's own docstring)."""
    # 120 m2 COMPACT preset rounds to 10.95 x 10.95 = 119.9025 m2, fractionally under 120
    footprint = _footprint(width_m=10.95, depth_m=10.95, target_area_m2=120.0, area_m2=119.9)
    project = _project(built_area_m2=120.0, selected_footprint=footprint)

    spec = _derive_footprint(project)  # must not raise BuildingFootprintSpec's own validator

    assert spec.available_area_m2 <= spec.width_m * spec.depth_m + 1e-9
    assert spec.available_area_m2 == pytest.approx(119.9, abs=0.01)  # NOT silently inflated to 120


# --- Requirement 7: geometry authority -- both the legacy solver and concept-first planner honor ---
# --- a non-square selected footprint, without any change to either --------------------------------


def test_legacy_solver_and_concept_first_planner_both_honor_a_selected_non_square_footprint():
    project = _project(built_area_m2=200.0, selected_footprint=_footprint(width_m=10, depth_m=20))
    footprint_spec = _derive_footprint(project)
    assert (footprint_spec.width_m, footprint_spec.depth_m) == (10, 20)

    request, _budget = _build_request(project, math.sqrt(project.plot_area_m2))
    spec = merge_authoritative_requirements(MockArchitectModelGateway().generate(request), request)

    legacy_result = GeometrySolver().solve(spec, footprint_spec)
    assert legacy_result.status == SolverStatus.satisfied
    for room in legacy_result.instances:
        assert room.x + room.width <= 10 + 1e-6
        assert room.y + room.height <= 20 + 1e-6

    concept_result = plan_with_concepts(spec, footprint_spec)
    assert concept_result.status == SolverStatus.satisfied
    for room in concept_result.instances:
        assert room.x + room.width <= 10 + 1e-6
        assert room.y + room.height <= 20 + 1e-6


# --- HTTP fixtures/helpers -------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path):
    return JsonFileProjectRepository(tmp_path / "projects.json")


@pytest.fixture
def client(repo, monkeypatch):
    monkeypatch.setattr(project_base_routes, "repository", repo)
    return TestClient(app)


def _create_and_parse_project(
    client: TestClient, repo: JsonFileProjectRepository, *, selected_footprint: dict | None, built_area_m2: float = 200,
) -> str:
    payload = {
        "city": _CITY, "street": _STREET, "plot_area_m2": 500, "built_area_m2": built_area_m2,
        "description": 'בית עם 3 חדרי שינה, ממ"ד',
    }
    if selected_footprint is not None:
        payload["selected_footprint"] = selected_footprint
    response = client.post("/projects", json=payload)
    assert response.status_code == 201, response.text
    project_id = response.json()["project_id"]

    repo.set_parsed_requirements(
        project_id,
        floors=TaggedInt(value=1, source=SourceTag.requested),
        bedrooms=_BEDROOMS_3,
        safe_room=_SAFE_ROOM_YES,
        parking_spaces=_UNKNOWN_INT,
        pool=_UNKNOWN_POOL,
    )
    return project_id
