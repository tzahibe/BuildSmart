import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.projects.repository import JsonFileProjectRepository
from app.projects.routes import base_routes


@pytest.fixture
def repo(tmp_path):
    return JsonFileProjectRepository(tmp_path / "projects.json")


@pytest.fixture
def client(repo, monkeypatch):
    monkeypatch.setattr(base_routes, "repository", repo)
    return TestClient(app)


VALID_PAYLOAD = {
    "city": "מודיעין-מכבים-רעות",
    "street": "אגוז מכבים רעות",
    "plot_area_m2": 500,
    "description": 'בית בן קומתיים 220 מ"ר, 4 חדרי שינה',
}


# --- User Story 1: Create a new project -------------------------------------------------


def test_create_project_returns_201_with_generated_fields(client: TestClient):
    response = client.post("/projects", json=VALID_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert body["project_id"]
    assert body["status"] == "created"
    assert body["city"] == VALID_PAYLOAD["city"]
    assert body["street"] == VALID_PAYLOAD["street"]
    assert body["plot_area_m2"] == VALID_PAYLOAD["plot_area_m2"]
    assert body["description"] == VALID_PAYLOAD["description"]
    assert body["created_at"]
    assert body["updated_at"]


def test_create_project_missing_city_is_rejected(client: TestClient):
    payload = {**VALID_PAYLOAD, "city": ""}

    response = client.post("/projects", json=payload)

    assert response.status_code == 422


def test_create_project_missing_street_is_rejected(client: TestClient):
    payload = {**VALID_PAYLOAD, "street": "   "}

    response = client.post("/projects", json=payload)

    assert response.status_code == 422


def test_create_project_empty_description_is_rejected(client: TestClient):
    payload = {**VALID_PAYLOAD, "description": "   "}

    response = client.post("/projects", json=payload)

    assert response.status_code == 422


def test_create_project_non_positive_plot_area_is_rejected(client: TestClient):
    payload = {**VALID_PAYLOAD, "plot_area_m2": 0}

    response = client.post("/projects", json=payload)

    assert response.status_code == 422


def test_create_project_rejects_a_city_not_in_the_localities_list(client: TestClient):
    """City must be selected from the localities list (see app/localities/data.py) —
    this is a whitelist, not just an autocomplete suggestion."""
    payload = {**VALID_PAYLOAD, "city": "עיר שלא ברשימה"}

    response = client.post("/projects", json=payload)

    assert response.status_code == 422


def test_create_project_rejects_a_street_not_in_the_citys_street_list(client: TestClient):
    """street must be one of the streets returned by GET /localities/{city}/streets for the
    submitted city — not just any non-empty value, and not a street from a different city."""
    payload = {**VALID_PAYLOAD, "street": "רחוב שלא קיים בעיר הזו בכלל"}

    response = client.post("/projects", json=payload)

    assert response.status_code == 422


def test_create_project_rejects_a_street_that_belongs_to_a_different_city(client: TestClient):
    payload = {**VALID_PAYLOAD, "city": "ירושלים"}  # VALID_PAYLOAD's street belongs to a different city

    response = client.post("/projects", json=payload)

    assert response.status_code == 422


def test_rejected_creation_does_not_create_a_project(client: TestClient, repo: JsonFileProjectRepository):
    invalid_response = client.post("/projects", json={**VALID_PAYLOAD, "plot_area_m2": -10})
    assert invalid_response.status_code == 422

    valid_response = client.post("/projects", json=VALID_PAYLOAD)
    assert valid_response.status_code == 201

    # Only the valid submission should exist — the file store holds exactly 1 project.
    assert len(repo._load()) == 1


# --- User Story 2: Load an existing project ----------------------------------------------


def test_get_project_returns_exactly_what_was_submitted(client: TestClient):
    create_response = client.post("/projects", json=VALID_PAYLOAD)
    project_id = create_response.json()["project_id"]

    response = client.get(f"/projects/{project_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == project_id
    assert body["city"] == VALID_PAYLOAD["city"]
    assert body["street"] == VALID_PAYLOAD["street"]
    assert body["plot_area_m2"] == VALID_PAYLOAD["plot_area_m2"]
    assert body["description"] == VALID_PAYLOAD["description"]
    assert body["status"] == "created"


def test_get_nonexistent_project_returns_404(client: TestClient):
    response = client.get("/projects/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


# --- Localities autocomplete --------------------------------------------------------------


def test_list_localities_returns_a_sorted_non_empty_list_of_strings(client: TestClient):
    response = client.get("/localities")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) > 1000
    assert all(isinstance(item, str) for item in body)
    assert body == sorted(body)
    assert "ירושלים" in body
    assert VALID_PAYLOAD["city"] in body


def test_list_streets_returns_streets_for_a_known_city(client: TestClient):
    response = client.get(f"/localities/{VALID_PAYLOAD['city']}/streets")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) > 0
    assert body == sorted(body)


def test_list_streets_for_unknown_city_returns_404(client: TestClient):
    response = client.get("/localities/עיר שלא קיימת/streets")

    assert response.status_code == 404
