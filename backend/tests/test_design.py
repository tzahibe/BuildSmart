from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.design.generator import FootprintTooSmallError, generate_design
from app.main import app
from app.projects.models import PoolField, Project, SourceTag, TaggedBool, TaggedFloat, TaggedInt
from app.projects.repository import JsonFileProjectRepository
from app.projects.routes import base_routes as project_base_routes

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
    built_area_m2: float = 100.0,
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


# --- generate_design(): pure function unit tests -----------------------------------------


def test_single_floor_known_bedrooms_and_safe_room():
    project = _project(
        built_area_m2=100.0,
        floors=1,
        bedrooms=TaggedInt(value=3, source=SourceTag.requested),
        safe_room=TaggedBool(value=True, source=SourceTag.requested),
    )

    design = generate_design(project)

    room_types = [room.type for room in design.rooms]
    assert room_types.count("kitchen") == 1
    assert room_types.count("bathroom") == 1
    assert room_types.count("safe_room") == 1
    assert room_types.count("living_room") == 1
    assert room_types.count("bedroom") == 3
    assert all(room.floor == 1 for room in design.rooms)
    assert all(room.area_m2 > 0 for room in design.rooms)
    # Rooms don't overlap in x: each starts where the previous one ended, and widths sum to the floor's
    # available area (area / depth) since every room on a floor shares the same depth.
    xs = [room.x for room in design.rooms]
    assert xs == sorted(xs)
    assert sum(room.width_m for room in design.rooms) == pytest.approx(100.0 / design.rooms[0].depth_m)
    assert design.design_notes == []


def test_two_floors_puts_all_bedrooms_upstairs():
    project = _project(
        built_area_m2=200.0,
        floors=2,
        bedrooms=TaggedInt(value=4, source=SourceTag.requested),
        safe_room=TaggedBool(value=False, source=SourceTag.requested),
    )

    design = generate_design(project)

    floor_1_rooms = [room for room in design.rooms if room.floor == 1]
    floor_2_rooms = [room for room in design.rooms if room.floor == 2]
    assert {room.type for room in floor_1_rooms} == {"kitchen", "bathroom", "living_room"}
    assert [room.type for room in floor_2_rooms] == ["bedroom"] * 4


def test_three_floors_odd_bedroom_count_splits_with_remainder_on_lower_floor():
    project = _project(
        built_area_m2=300.0,
        floors=3,
        bedrooms=TaggedInt(value=5, source=SourceTag.requested),
        safe_room=TaggedBool(value=False, source=SourceTag.requested),
    )

    design = generate_design(project)

    floor_2_bedrooms = [room for room in design.rooms if room.floor == 2 and room.type == "bedroom"]
    floor_3_bedrooms = [room for room in design.rooms if room.floor == 3 and room.type == "bedroom"]
    assert len(floor_2_bedrooms) == 3
    assert len(floor_3_bedrooms) == 2
    assert not any(room.floor == 1 and room.type == "bedroom" for room in design.rooms)


def test_unknown_bedrooms_excluded_with_note():
    project = _project(
        built_area_m2=100.0,
        floors=1,
        bedrooms=_UNKNOWN_INT,
        safe_room=TaggedBool(value=True, source=SourceTag.requested),
    )

    design = generate_design(project)

    assert all(room.type != "bedroom" for room in design.rooms)
    assert any("חדרי השינה" in note for note in design.design_notes)


def test_unknown_safe_room_excluded_with_note():
    project = _project(
        built_area_m2=100.0,
        floors=1,
        bedrooms=TaggedInt(value=2, source=SourceTag.requested),
        safe_room=_UNKNOWN_BOOL,
    )

    design = generate_design(project)

    assert all(room.type != "safe_room" for room in design.rooms)
    assert any('ממ"ד' in note for note in design.design_notes)


def test_footprint_too_small_raises():
    project = _project(
        built_area_m2=10.0,
        floors=1,
        bedrooms=_UNKNOWN_INT,
        safe_room=TaggedBool(value=True, source=SourceTag.requested),
    )

    with pytest.raises(FootprintTooSmallError):
        generate_design(project)


# --- POST /projects/{project_id}/design: endpoint tests ----------------------------------


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
        "built_area_m2": 120,
        "description": "בית עם 3 חדרי שינה, ממ\"ד",
    }
    payload.update(overrides)
    response = client.post("/projects", json=payload)
    assert response.status_code == 201
    project_id = response.json()["project_id"]

    # Bypasses the real parse endpoint (no LLM call needed) — this feature only cares that parsing
    # *happened*, not what was parsed, matching specs/003's own testing notes.
    repo.set_parsed_requirements(
        project_id,
        floors=TaggedInt(value=1, source=SourceTag.requested),
        bedrooms=TaggedInt(value=3, source=SourceTag.requested),
        safe_room=TaggedBool(value=True, source=SourceTag.requested),
        parking_spaces=_UNKNOWN_INT,
        pool=_UNKNOWN_POOL,
    )
    return project_id


def test_generate_design_full_flow_returns_200(client: TestClient, repo: JsonFileProjectRepository):
    project_id = _create_and_parse_project(client, repo)

    response = client.post(f"/projects/{project_id}/design")

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == project_id
    assert body["site_width_m"] == pytest.approx(500.0**0.5)
    assert body["site_depth_m"] == pytest.approx(500.0**0.5)
    assert len(body["rooms"]) > 0
    assert body["design_notes"] == []
    assert body["design_generated_at"]


def test_generate_design_unparsed_project_returns_422(client: TestClient):
    response = client.post(
        "/projects",
        json={
            "city": "מודיעין-מכבים-רעות",
            "street": "אגוז מכבים רעות",
            "plot_area_m2": 300,
            "built_area_m2": 90,
            "description": "בית קטן",
        },
    )
    project_id = response.json()["project_id"]

    response = client.post(f"/projects/{project_id}/design")

    assert response.status_code == 422


def test_generate_design_nonexistent_project_returns_404(client: TestClient):
    response = client.post("/projects/00000000-0000-0000-0000-000000000000/design")

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


def test_generate_design_footprint_too_small_returns_422(
    client: TestClient, repo: JsonFileProjectRepository
):
    project_id = _create_and_parse_project(client, repo, plot_area_m2=100, built_area_m2=10)

    response = client.post(f"/projects/{project_id}/design")

    assert response.status_code == 422
