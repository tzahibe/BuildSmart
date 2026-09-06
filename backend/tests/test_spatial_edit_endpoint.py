"""Integration tests for POST /projects/{project_id}/design/spatial-edit.

Two fixtures are used, matching test_design.py's own testing convention (repo/client fixtures,
real HTTP calls via TestClient against the real `app`):

  _generate_real_design(): creates a project and runs the REAL design pipeline (real
    MockArchitectModelGateway + real GeometrySolver, same as test_design_pipeline.py's own
    convention) -- used for every test that doesn't specifically need directional slack the real
    solver's edge-packed output doesn't have.

  _seed_design_with_slack(): writes a small, hand-built but contract-valid GeometricDesign
    directly via the repository (bypassing the solver) for exactly two tests -- WEST and NORTH.
    Verified empirically (not assumed) that the real generated 3BR+safe_room design has ZERO
    slack in the NORTH or WEST direction for any room at all (GeometrySolver packs every room
    flush against x=0/y=0, pushing all unused footprint area to the south/east) -- so a real
    generated layout cannot exercise a successful WEST/NORTH move. This is a property of the
    existing production solver's packing strategy, not of the spatial-edit endpoint.
"""
import pytest
from fastapi.testclient import TestClient

from app.geometry.geometric_design import GeometricDesign
from app.main import app
from app.projects.models import PoolField, Room, SourceTag, TaggedBool, TaggedFloat, TaggedInt
from app.projects.repository import JsonFileProjectRepository
from app.projects.routes import base_routes as project_base_routes

_UNKNOWN_INT = TaggedInt(value=None, source=SourceTag.unknown)
_UNKNOWN_BOOL = TaggedBool(value=None, source=SourceTag.unknown)
_UNKNOWN_POOL = PoolField(
    requested=_UNKNOWN_BOOL,
    length_m=TaggedFloat(value=None, source=SourceTag.unknown),
    width_m=TaggedFloat(value=None, source=SourceTag.unknown),
)


@pytest.fixture
def repo(tmp_path):
    return JsonFileProjectRepository(tmp_path / "projects.json")


@pytest.fixture
def client(repo, monkeypatch):
    monkeypatch.setattr(project_base_routes, "repository", repo)
    return TestClient(app)


def _create_project(client: TestClient) -> str:
    payload = {
        "city": "מודיעין-מכבים-רעות",
        "street": "אגוז מכבים רעות",
        "plot_area_m2": 500,
        "built_area_m2": 120,
        "description": 'בית עם 3 חדרי שינה, ממ"ד',
    }
    response = client.post("/projects", json=payload)
    assert response.status_code == 201
    return response.json()["project_id"]


def _generate_real_design(client: TestClient, repo: JsonFileProjectRepository) -> tuple[str, dict]:
    project_id = _create_project(client)
    repo.set_parsed_requirements(
        project_id,
        floors=TaggedInt(value=1, source=SourceTag.requested),
        bedrooms=TaggedInt(value=3, source=SourceTag.requested),
        safe_room=TaggedBool(value=True, source=SourceTag.requested),
        parking_spaces=_UNKNOWN_INT,
        pool=_UNKNOWN_POOL,
    )
    response = client.post(f"/projects/{project_id}/design")
    assert response.status_code == 200
    return project_id, response.json()["geometric_design"]


def _seed_design_with_slack(client: TestClient, repo: JsonFileProjectRepository) -> tuple[str, dict]:
    project_id = _create_project(client)
    design = GeometricDesign.model_validate(
        {
            "footprint": {"width_m": 10.0, "depth_m": 10.0, "floor": 1},
            "rooms": [
                {
                    "id": "TEST_ROOM", "type": "bedroom", "floor": 1,
                    "x": 4.0, "y": 4.0, "width_m": 2.0, "depth_m": 2.0, "area_m2": 4.0,
                    "is_circulation": False, "source": "USER_REQUIREMENT",
                },
                {
                    "id": "ANCHOR_ROOM", "type": "living_room", "floor": 1,
                    "x": 0.0, "y": 0.0, "width_m": 2.0, "depth_m": 2.0, "area_m2": 4.0,
                    "is_circulation": False, "source": None,
                },
            ],
            "walls": [], "doors": [],
            "programmed_area_m2": 8.0, "circulation_area_m2": 0.0,
        }
    )
    rooms = [
        Room(type=r.type, floor=r.floor, area_m2=r.area_m2, x=r.x, y=r.y, width_m=r.width_m, depth_m=r.depth_m, source=r.source)
        for r in design.rooms
    ]
    updated = repo.set_design_model(
        project_id, site_width_m=10.0, site_depth_m=10.0, rooms=rooms, design_notes=[],
        geometric_design=design.model_dump(mode="json"),
    )
    assert updated is not None
    return project_id, design.model_dump(mode="json")


def _room(geometric_design: dict, room_id: str) -> dict:
    return next(r for r in geometric_design["rooms"] if r["id"] == room_id)


def _edit(client: TestClient, project_id: str, room_id: str, direction: str, distance_m: float | None = None):
    body = {"room_id": room_id, "direction": direction}
    if distance_m is not None:
        body["distance_m"] = distance_m
    return client.post(f"/projects/{project_id}/design/spatial-edit", json=body)


def _edit_vector(client: TestClient, project_id: str, room_id: str, dx_m: float, dy_m: float):
    body = {"type": "MOVE_ROOM_BY_VECTOR", "room_id": room_id, "dx_m": dx_m, "dy_m": dy_m}
    return client.post(f"/projects/{project_id}/design/spatial-edit", json=body)


# --- directional correctness -------------------------------------------------------------


def test_west_decreases_x(client: TestClient, repo: JsonFileProjectRepository):
    project_id, design = _seed_design_with_slack(client, repo)
    original_x = _room(design, "TEST_ROOM")["x"]
    response = _edit(client, project_id, "TEST_ROOM", "WEST", 1.0)
    assert response.status_code == 200
    assert _room(response.json(), "TEST_ROOM")["x"] == pytest.approx(original_x - 1.0)


def test_north_decreases_y(client: TestClient, repo: JsonFileProjectRepository):
    project_id, design = _seed_design_with_slack(client, repo)
    original_y = _room(design, "TEST_ROOM")["y"]
    response = _edit(client, project_id, "TEST_ROOM", "NORTH", 1.0)
    assert response.status_code == 200
    assert _room(response.json(), "TEST_ROOM")["y"] == pytest.approx(original_y - 1.0)


def test_east_increases_x(client: TestClient, repo: JsonFileProjectRepository):
    project_id, design = _generate_real_design(client, repo)
    original_x = _room(design, "KITCHEN")["x"]
    response = _edit(client, project_id, "KITCHEN", "EAST", 1.0)
    assert response.status_code == 200
    assert _room(response.json(), "KITCHEN")["x"] == pytest.approx(original_x + 1.0)


def test_south_increases_y(client: TestClient, repo: JsonFileProjectRepository):
    project_id, design = _generate_real_design(client, repo)
    original_y = _room(design, "BEDROOM_2")["y"]
    response = _edit(client, project_id, "BEDROOM_2", "SOUTH", 0.3)
    assert response.status_code == 200
    assert _room(response.json(), "BEDROOM_2")["y"] == pytest.approx(original_y + 0.3)


# --- distance handling ---------------------------------------------------------------------


def test_explicit_distance_respected(client: TestClient, repo: JsonFileProjectRepository):
    project_id, design = _generate_real_design(client, repo)
    original_x = _room(design, "KITCHEN")["x"]
    response = _edit(client, project_id, "KITCHEN", "EAST", 2.0)
    assert response.status_code == 200
    assert _room(response.json(), "KITCHEN")["x"] == pytest.approx(original_x + 2.0)


def test_default_distance_is_deterministic(client: TestClient, repo: JsonFileProjectRepository):
    from app.geometry.spatial_edit_types import DEFAULT_EDIT_STEP_M

    project_id, design = _generate_real_design(client, repo)
    original_x = _room(design, "KITCHEN")["x"]
    response = _edit(client, project_id, "KITCHEN", "EAST")  # no distance_m
    assert response.status_code == 200
    assert _room(response.json(), "KITCHEN")["x"] == pytest.approx(original_x + DEFAULT_EDIT_STEP_M)


# --- rejection mapping -----------------------------------------------------------------------


def test_room_not_found_returns_404(client: TestClient, repo: JsonFileProjectRepository):
    project_id, _ = _generate_real_design(client, repo)
    response = _edit(client, project_id, "NOT_A_ROOM", "WEST", 1.0)
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "ROOM_NOT_FOUND"


def test_out_of_bounds_rejected(client: TestClient, repo: JsonFileProjectRepository):
    project_id, _ = _generate_real_design(client, repo)
    response = _edit(client, project_id, "KITCHEN", "EAST", 10.0)
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "OUT_OF_BOUNDS"


def test_overlap_rejected(client: TestClient, repo: JsonFileProjectRepository):
    project_id, _ = _generate_real_design(client, repo)
    response = _edit(client, project_id, "SAFE_ROOM", "EAST", 0.3)
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "OVERLAP"


def test_constraint_violation_rejected(client: TestClient, repo: JsonFileProjectRepository):
    project_id, _ = _generate_real_design(client, repo)
    response = _edit(client, project_id, "SAFE_ROOM", "SOUTH", 0.5)
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "CONSTRAINT_VIOLATION"


# --- atomicity + sequential edits ---------------------------------------------------------


def test_rejected_edit_does_not_mutate_current_design(client: TestClient, repo: JsonFileProjectRepository):
    project_id, design_before = _generate_real_design(client, repo)

    response = _edit(client, project_id, "SAFE_ROOM", "EAST", 0.3)  # OVERLAP
    assert response.status_code == 422

    project = repo.get(project_id)
    assert project.geometric_design == design_before


def test_unrelated_rooms_unchanged_after_applied_edit(client: TestClient, repo: JsonFileProjectRepository):
    project_id, design_before = _generate_real_design(client, repo)
    other_rooms_before = {r["id"]: r for r in design_before["rooms"] if r["id"] != "KITCHEN"}

    response = _edit(client, project_id, "KITCHEN", "EAST", 1.0)
    assert response.status_code == 200

    other_rooms_after = {r["id"]: r for r in response.json()["rooms"] if r["id"] != "KITCHEN"}
    assert other_rooms_after == other_rooms_before


def test_sequential_accepted_edits_use_latest_geometry(client: TestClient, repo: JsonFileProjectRepository):
    project_id, design_before = _generate_real_design(client, repo)
    original_x = _room(design_before, "KITCHEN")["x"]

    first = _edit(client, project_id, "KITCHEN", "EAST", 1.0)
    assert first.status_code == 200
    assert _room(first.json(), "KITCHEN")["x"] == pytest.approx(original_x + 1.0)

    second = _edit(client, project_id, "KITCHEN", "EAST", 1.0)
    assert second.status_code == 200
    # if the second edit had (incorrectly) started from the ORIGINAL design instead of the first
    # edit's result, this would also be original_x + 1.0 instead of + 2.0
    assert _room(second.json(), "KITCHEN")["x"] == pytest.approx(original_x + 2.0)

    project = repo.get(project_id)
    assert _room(project.geometric_design, "KITCHEN")["x"] == pytest.approx(original_x + 2.0)


# --- response contract ----------------------------------------------------------------------


def test_response_matches_geometric_design_contract(client: TestClient, repo: JsonFileProjectRepository):
    project_id, _ = _generate_real_design(client, repo)
    response = _edit(client, project_id, "KITCHEN", "EAST", 1.0)
    assert response.status_code == 200

    # round-trips through the real GeometricDesign model with no validation error, and has every
    # field the contract requires (footprint/rooms/walls/doors/programmed_area_m2/circulation_area_m2)
    validated = GeometricDesign.model_validate(response.json())
    assert validated.footprint.width_m > 0
    assert len(validated.rooms) == 7
    assert all(isinstance(w.coord, float) for w in validated.walls)


# --- MOVE_ROOM_BY_VECTOR (additive; prepared for a future drag-to-move UI, not yet wired to any
# frontend code) -- same validation path, same atomicity, exercised with an arbitrary (dx, dy)
# instead of a cardinal direction + distance. -------------------------------------------------


def test_vector_move_applies_exact_dx_dy(client: TestClient, repo: JsonFileProjectRepository):
    project_id, design = _generate_real_design(client, repo)
    original = _room(design, "KITCHEN")
    response = _edit_vector(client, project_id, "KITCHEN", dx_m=1.3, dy_m=0.4)
    assert response.status_code == 200
    moved = _room(response.json(), "KITCHEN")
    assert moved["x"] == pytest.approx(original["x"] + 1.3)
    assert moved["y"] == pytest.approx(original["y"] + 0.4)


def test_vector_move_unrelated_rooms_unchanged(client: TestClient, repo: JsonFileProjectRepository):
    project_id, design = _generate_real_design(client, repo)
    other_rooms_before = {r["id"]: r for r in design["rooms"] if r["id"] != "KITCHEN"}
    response = _edit_vector(client, project_id, "KITCHEN", dx_m=1.0, dy_m=0.0)
    assert response.status_code == 200
    other_rooms_after = {r["id"]: r for r in response.json()["rooms"] if r["id"] != "KITCHEN"}
    assert other_rooms_after == other_rooms_before


def test_vector_move_rejections_use_same_reasons(client: TestClient, repo: JsonFileProjectRepository):
    project_id, _ = _generate_real_design(client, repo)

    response = _edit_vector(client, project_id, "NOT_A_ROOM", dx_m=1.0, dy_m=0.0)
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "ROOM_NOT_FOUND"

    response = _edit_vector(client, project_id, "KITCHEN", dx_m=10.0, dy_m=0.0)
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "OUT_OF_BOUNDS"

    response = _edit_vector(client, project_id, "SAFE_ROOM", dx_m=0.3, dy_m=0.0)
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "OVERLAP"


def test_vector_move_missing_dx_dy_is_rejected_as_bad_request(client: TestClient, repo: JsonFileProjectRepository):
    project_id, _ = _generate_real_design(client, repo)
    response = client.post(
        f"/projects/{project_id}/design/spatial-edit",
        json={"type": "MOVE_ROOM_BY_VECTOR", "room_id": "KITCHEN"},
    )
    assert response.status_code == 422


def test_existing_move_room_flow_unaffected_by_vector_addition(client: TestClient, repo: JsonFileProjectRepository):
    """Regression check: the original MOVE_ROOM request shape (no `type` field at all, exactly what
    the committed frontend sends) still works identically after adding MOVE_ROOM_BY_VECTOR."""
    project_id, design = _generate_real_design(client, repo)
    original_x = _room(design, "KITCHEN")["x"]
    response = client.post(
        f"/projects/{project_id}/design/spatial-edit",
        json={"room_id": "KITCHEN", "direction": "EAST", "distance_m": 1.0},
    )
    assert response.status_code == 200
    assert _room(response.json(), "KITCHEN")["x"] == pytest.approx(original_x + 1.0)
