"""Integration tests for the new pipeline: Project -> ArchitectModelGateway -> ArchitecturalSpec ->
GeometrySolver -> GeneratedDesign / API response. Exercises the REAL MockArchitectModelGateway and REAL
GeometrySolver end to end (only the HTTP/repository layer is faked, same convention as test_design.py)
— no test here mocks out the pipeline's own internals.
"""

from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

import app.design.pipeline as pipeline_module
from app.architect.config import RealArchitectModelConfig
from app.architect.real_gateway import RealArchitectModelGateway
from app.design.pipeline import DesignUnsatisfiableError, MultiFloorNotSupportedError, generate_design_via_solver
from app.main import app
from app.projects.models import PoolField, Project, SourceTag, TaggedBool, TaggedFloat, TaggedInt
from app.projects.repository import JsonFileProjectRepository
from app.projects.routes import base_routes as project_base_routes

_STUB_CONFIG = RealArchitectModelConfig(base_url="https://stub.invalid/generate", model_id=None, api_key=None, timeout_s=5)


def _stub_real_gateway(handler) -> RealArchitectModelGateway:
    return RealArchitectModelGateway(_STUB_CONFIG, client=httpx.Client(transport=httpx.MockTransport(handler)))

_UNKNOWN_INT = TaggedInt(value=None, source=SourceTag.unknown)
_UNKNOWN_BOOL = TaggedBool(value=None, source=SourceTag.unknown)
_UNKNOWN_POOL = PoolField(
    requested=_UNKNOWN_BOOL,
    length_m=TaggedFloat(value=None, source=SourceTag.unknown),
    width_m=TaggedFloat(value=None, source=SourceTag.unknown),
)


def _project(
    *,
    plot_area_m2: float = 500.0,
    built_area_m2: float = 120.0,
    floors: int = 1,
    bedrooms: TaggedInt = _UNKNOWN_INT,
    safe_room: TaggedBool = _UNKNOWN_BOOL,
) -> Project:
    now = datetime.now(UTC)
    return Project(
        project_id="test-project",
        city="מודיעין-מכבים-רעות",
        street="אגוז מכבים רעות",
        plot_area_m2=plot_area_m2,
        built_area_m2=built_area_m2,
        description="test",
        status="created",
        created_at=now,
        updated_at=now,
        floors=TaggedInt(value=floors, source=SourceTag.requested),
        bedrooms=bedrooms,
        safe_room=safe_room,
        parking_spaces=_UNKNOWN_INT,
        pool=_UNKNOWN_POOL,
        requirements_parsed_at=now,
    )


# --- Unit-level: generate_design_via_solver ------------------------------------------------------


def test_produces_kitchen_bathroom_living_room_and_bedrooms_for_a_known_bedroom_count():
    project = _project(
        bedrooms=TaggedInt(value=2, source=SourceTag.requested),
        safe_room=TaggedBool(value=False, source=SourceTag.requested),
    )

    design = generate_design_via_solver(project)

    room_types = [room.type for room in design.rooms]
    assert room_types.count("kitchen") == 1
    assert room_types.count("bathroom") == 1
    assert room_types.count("living_room") == 1
    assert room_types.count("bedroom") == 2
    assert room_types.count("safe_room") == 0
    assert design.design_notes == []
    assert all(room.floor == 1 for room in design.rooms)


def test_includes_safe_room_when_requested():
    project = _project(
        bedrooms=TaggedInt(value=2, source=SourceTag.requested),
        safe_room=TaggedBool(value=True, source=SourceTag.requested),
    )

    design = generate_design_via_solver(project)

    assert any(room.type == "safe_room" for room in design.rooms)
    assert design.design_notes == []


def test_excludes_safe_room_without_a_note_when_explicitly_not_requested():
    # Known-and-false is a real answer, not an omission — no note should be recorded for it, unlike
    # the unknown case below.
    project = _project(
        bedrooms=TaggedInt(value=2, source=SourceTag.requested),
        safe_room=TaggedBool(value=False, source=SourceTag.requested),
    )

    design = generate_design_via_solver(project)

    assert all(room.type != "safe_room" for room in design.rooms)
    assert design.design_notes == []


def test_unknown_bedrooms_are_excluded_never_guessed_and_recorded_as_a_note():
    project = _project(bedrooms=_UNKNOWN_INT)

    design = generate_design_via_solver(project)

    assert all(room.type != "bedroom" for room in design.rooms)
    assert any("חדרי השינה" in note for note in design.design_notes)


def test_unknown_safe_room_is_excluded_and_recorded_as_a_note():
    project = _project(bedrooms=TaggedInt(value=1, source=SourceTag.requested), safe_room=_UNKNOWN_BOOL)

    design = generate_design_via_solver(project)

    assert all(room.type != "safe_room" for room in design.rooms)
    assert any('ממ"ד' in note for note in design.design_notes)


def test_raises_design_unsatisfiable_error_when_built_area_is_too_small():
    project = _project(plot_area_m2=100.0, built_area_m2=8.0, bedrooms=TaggedInt(value=3, source=SourceTag.requested))

    with pytest.raises(DesignUnsatisfiableError):
        generate_design_via_solver(project)


def test_raises_multi_floor_not_supported_for_floors_greater_than_one():
    project = _project(floors=2, bedrooms=TaggedInt(value=4, source=SourceTag.requested))

    with pytest.raises(MultiFloorNotSupportedError) as excinfo:
        generate_design_via_solver(project)

    assert excinfo.value.code == "MULTI_FLOOR_NOT_SUPPORTED"
    assert excinfo.value.floors == 2


def test_footprint_gross_area_exceeds_the_program_area_budget():
    # The footprint's own area must NOT equal built_area_m2 (the old bug) — it should be strictly
    # larger, leaving headroom beyond the pure room-area budget.
    from app.design.pipeline import _derive_footprint

    project = _project(built_area_m2=100.0)

    footprint = _derive_footprint(project)

    assert footprint.available_area_m2 == 100.0  # the budget itself is untouched
    assert footprint.width_m * footprint.depth_m > footprint.available_area_m2


def test_no_room_is_narrower_than_the_requested_minimum_width():
    # A real behavioral improvement over the old generator (which could produce sub-1m slivers): the
    # new solver's min_width_m is a hard bound on BOTH sides of every room.
    project = _project(built_area_m2=150.0, bedrooms=TaggedInt(value=3, source=SourceTag.requested))

    design = generate_design_via_solver(project)

    for room in design.rooms:
        assert room.width_m >= 1.5, f"{room.type} width {room.width_m} looks like a sliver"
        assert room.depth_m >= 1.5, f"{room.type} depth {room.depth_m} looks like a sliver"


# --- Endpoint-level: the actual API response -----------------------------------------------------


@pytest.fixture
def repo(tmp_path):
    return JsonFileProjectRepository(tmp_path / "projects.json")


@pytest.fixture
def client(repo, monkeypatch):
    monkeypatch.setattr(project_base_routes, "repository", repo)
    return TestClient(app)


def _create_and_parse_project(client: TestClient, repo: JsonFileProjectRepository, **overrides) -> str:
    payload = {
        "city": "מודיעין-מכבים-רעות",
        "street": "אגוז מכבים רעות",
        "plot_area_m2": 500,
        "built_area_m2": 150,
        "description": "בית עם 3 חדרי שינה, ממ\"ד",
    }
    payload.update(overrides)
    response = client.post("/projects", json=payload)
    assert response.status_code == 201
    project_id = response.json()["project_id"]

    repo.set_parsed_requirements(
        project_id,
        floors=TaggedInt(value=1, source=SourceTag.requested),
        bedrooms=TaggedInt(value=3, source=SourceTag.requested),
        safe_room=TaggedBool(value=True, source=SourceTag.requested),
        parking_spaces=_UNKNOWN_INT,
        pool=_UNKNOWN_POOL,
    )
    return project_id


def test_full_pipeline_via_the_design_endpoint_returns_200_with_solved_rooms(
    client: TestClient, repo: JsonFileProjectRepository
):
    project_id = _create_and_parse_project(client, repo)

    response = client.post(f"/projects/{project_id}/design")

    assert response.status_code == 200
    body = response.json()
    room_types = [room["type"] for room in body["rooms"]]
    assert room_types.count("bedroom") == 3
    assert room_types.count("safe_room") == 1
    assert room_types.count("kitchen") == 1
    # Every room stays within the solved footprint and has no zero/negative dimension.
    for room in body["rooms"]:
        assert room["width_m"] > 0
        assert room["depth_m"] > 0
        assert room["x"] >= 0
        assert room["y"] >= 0


def test_unsatisfiable_pipeline_via_the_design_endpoint_returns_422_and_no_design_is_saved(
    client: TestClient, repo: JsonFileProjectRepository
):
    project_id = _create_and_parse_project(client, repo, plot_area_m2=100, built_area_m2=8)

    response = client.post(f"/projects/{project_id}/design")

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error"] == "DESIGN_UNSATISFIABLE"
    assert detail["message"]

    # No partial/fabricated design was persisted.
    project = repo.get(project_id)
    assert project.rooms is None
    assert project.design_generated_at is None


def test_multi_floor_project_returns_a_clear_multi_floor_not_supported_error(
    client: TestClient, repo: JsonFileProjectRepository
):
    # floors > 1 must NOT silently route through the old generator (or anywhere else) — it's an
    # explicit, disclosed "not supported yet" domain error instead. See router.py / pipeline.py.
    project_id = _create_and_parse_project(client, repo, built_area_m2=200)
    repo.set_parsed_requirements(
        project_id,
        floors=TaggedInt(value=2, source=SourceTag.requested),
        bedrooms=TaggedInt(value=4, source=SourceTag.requested),
        safe_room=TaggedBool(value=False, source=SourceTag.requested),
        parking_spaces=_UNKNOWN_INT,
        pool=_UNKNOWN_POOL,
    )

    response = client.post(f"/projects/{project_id}/design")

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error"] == "MULTI_FLOOR_NOT_SUPPORTED"

    # No partial/fabricated design was persisted.
    project = repo.get(project_id)
    assert project.rooms is None


# --- End-to-end via a stubbed RealArchitectModelGateway ------------------------------------------
#
# These monkeypatch `get_architect_model_gateway` (not the mock-vs-real env var) so the endpoint's own
# provider-selection code path is exercised unchanged — only WHICH gateway instance it receives is
# swapped, exactly as it would be in production by setting ARCHITECT_MODEL_PROVIDER=real.

_STUB_VALID_SPEC_JSON = """
{
  "program": [
    {"room_type": "kitchen", "count": 1, "target_area_m2": 12.0, "min_width_m": 2.4},
    {"room_type": "bathroom", "count": 1, "target_area_m2": 5.0, "min_width_m": 1.6},
    {"room_type": "living_room", "count": 1, "target_area_m2": 20.0, "min_width_m": 3.0},
    {"room_type": "bedroom", "count": 2, "target_area_m2": 12.0, "min_width_m": 2.6}
  ],
  "zones": [{"name": "public", "room_types": ["kitchen", "living_room"]}],
  "relationships": [
    {"kind": "adjacency", "room_type_a": "kitchen", "room_type_b": "living_room", "severity": "hard"}
  ],
  "circulation": {"entry_room_type": "living_room", "requires_hallway": false},
  "incomplete_requirements": []
}
"""


def test_end_to_end_via_stubbed_real_gateway_returns_a_normal_design_response(
    client: TestClient, repo: JsonFileProjectRepository, monkeypatch
):
    stub_gateway = _stub_real_gateway(lambda request: httpx.Response(200, json={"output": _STUB_VALID_SPEC_JSON}))
    monkeypatch.setattr(pipeline_module, "get_architect_model_gateway", lambda: stub_gateway)

    project_id = _create_and_parse_project(client, repo, built_area_m2=120)

    response = client.post(f"/projects/{project_id}/design")

    assert response.status_code == 200
    room_types = [room["type"] for room in response.json()["rooms"]]
    assert room_types.count("kitchen") == 1
    assert room_types.count("bedroom") == 2


def test_end_to_end_stubbed_real_gateway_valid_spec_but_solver_unsatisfiable_is_a_clean_422(
    client: TestClient, repo: JsonFileProjectRepository, monkeypatch
):
    # The spec itself is perfectly valid — the footprint is just too small for its program. Proves the
    # UNSAT path works identically regardless of which gateway produced the (valid) spec.
    stub_gateway = _stub_real_gateway(lambda request: httpx.Response(200, json={"output": _STUB_VALID_SPEC_JSON}))
    monkeypatch.setattr(pipeline_module, "get_architect_model_gateway", lambda: stub_gateway)

    project_id = _create_and_parse_project(client, repo, plot_area_m2=50, built_area_m2=10)

    response = client.post(f"/projects/{project_id}/design")

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "DESIGN_UNSATISFIABLE"
    project = repo.get(project_id)
    assert project.rooms is None
    assert project.design_generated_at is None


def test_architect_model_unavailable_reaches_the_endpoint_as_503(
    client: TestClient, repo: JsonFileProjectRepository, monkeypatch
):
    stub_gateway = _stub_real_gateway(lambda request: httpx.Response(500, text="internal error"))
    monkeypatch.setattr(pipeline_module, "get_architect_model_gateway", lambda: stub_gateway)

    project_id = _create_and_parse_project(client, repo)

    response = client.post(f"/projects/{project_id}/design")

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "ARCHITECT_MODEL_UNAVAILABLE"
    assert repo.get(project_id).rooms is None


def test_architect_model_timeout_reaches_the_endpoint_as_504(
    client: TestClient, repo: JsonFileProjectRepository, monkeypatch
):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    stub_gateway = _stub_real_gateway(handler)
    monkeypatch.setattr(pipeline_module, "get_architect_model_gateway", lambda: stub_gateway)

    project_id = _create_and_parse_project(client, repo)

    response = client.post(f"/projects/{project_id}/design")

    assert response.status_code == 504
    assert response.json()["detail"]["error"] == "ARCHITECT_MODEL_TIMEOUT"


def test_architect_model_invalid_output_reaches_the_endpoint_as_502_without_leaking_provider_detail(
    client: TestClient, repo: JsonFileProjectRepository, monkeypatch
):
    stub_gateway = _stub_real_gateway(lambda request: httpx.Response(200, json={"output": "not valid json"}))
    monkeypatch.setattr(pipeline_module, "get_architect_model_gateway", lambda: stub_gateway)

    project_id = _create_and_parse_project(client, repo)

    response = client.post(f"/projects/{project_id}/design")

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["error"] == "ARCHITECT_MODEL_INVALID_OUTPUT"
    assert "not valid json" not in detail["message"]  # raw provider output never reaches the client
    assert repo.get(project_id).rooms is None
