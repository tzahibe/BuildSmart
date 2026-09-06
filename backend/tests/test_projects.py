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
    "built_area_m2": 220,
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
    assert body["built_area_m2"] == VALID_PAYLOAD["built_area_m2"]
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


def test_create_project_non_positive_built_area_is_rejected(client: TestClient):
    payload = {**VALID_PAYLOAD, "built_area_m2": 0}

    response = client.post("/projects", json=payload)

    assert response.status_code == 422


def test_create_project_built_area_equal_to_plot_area_is_rejected(client: TestClient):
    """built_area_m2 must be strictly smaller than plot_area_m2, not merely <=."""
    payload = {**VALID_PAYLOAD, "plot_area_m2": 300, "built_area_m2": 300}

    response = client.post("/projects", json=payload)

    assert response.status_code == 422


def test_create_project_built_area_larger_than_plot_area_is_rejected(client: TestClient):
    payload = {**VALID_PAYLOAD, "plot_area_m2": 300, "built_area_m2": 400}

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
    assert body["built_area_m2"] == VALID_PAYLOAD["built_area_m2"]
    assert body["description"] == VALID_PAYLOAD["description"]
    assert body["status"] == "created"


def test_get_nonexistent_project_returns_404(client: TestClient):
    response = client.get("/projects/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


# --- User Story 3: Update an existing project's requirements -----------------------------

# A second real city/street pair, distinct from VALID_PAYLOAD's, for cross-city checks.
OTHER_CITY = "ירושלים"
OTHER_CITY_STREET = "א דרג'י"


def test_update_project_partial_update_changes_only_given_fields(client: TestClient):
    create_response = client.post("/projects", json=VALID_PAYLOAD)
    project_id = create_response.json()["project_id"]
    created_updated_at = create_response.json()["updated_at"]

    response = client.patch(f"/projects/{project_id}", json={"source": "SETTINGS", "diff": {"plot_area_m2": 250}})

    assert response.status_code == 200
    body = response.json()
    assert body["plot_area_m2"] == 250
    assert body["city"] == VALID_PAYLOAD["city"]
    assert body["street"] == VALID_PAYLOAD["street"]
    assert body["description"] == VALID_PAYLOAD["description"]
    assert body["updated_at"] >= created_updated_at


def test_update_project_invalid_value_is_rejected_and_applies_no_changes(client: TestClient):
    create_response = client.post("/projects", json=VALID_PAYLOAD)
    project_id = create_response.json()["project_id"]

    response = client.patch(f"/projects/{project_id}", json={"source": "SETTINGS", "diff": {"plot_area_m2": -5}})
    assert response.status_code == 422

    unchanged = client.get(f"/projects/{project_id}").json()
    assert unchanged["plot_area_m2"] == VALID_PAYLOAD["plot_area_m2"]


def test_update_nonexistent_project_returns_404(client: TestClient):
    response = client.patch(
        "/projects/00000000-0000-0000-0000-000000000000", json={"source": "SETTINGS", "diff": {"plot_area_m2": 100}}
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


def test_update_project_city_and_street_together_to_a_valid_pair_succeeds(client: TestClient):
    create_response = client.post("/projects", json=VALID_PAYLOAD)
    project_id = create_response.json()["project_id"]

    response = client.patch(
        f"/projects/{project_id}", json={"source": "SETTINGS", "diff": {"city": OTHER_CITY, "street": OTHER_CITY_STREET}}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["city"] == OTHER_CITY
    assert body["street"] == OTHER_CITY_STREET


def test_update_project_city_and_street_together_mismatched_is_rejected(client: TestClient):
    create_response = client.post("/projects", json=VALID_PAYLOAD)
    project_id = create_response.json()["project_id"]

    # OTHER_CITY paired with VALID_PAYLOAD's street, which belongs to a different city.
    response = client.patch(
        f"/projects/{project_id}",
        json={"source": "SETTINGS", "diff": {"city": OTHER_CITY, "street": VALID_PAYLOAD["street"]}},
    )

    assert response.status_code == 422


def test_update_project_street_only_not_matching_existing_city_is_rejected(client: TestClient):
    create_response = client.post("/projects", json=VALID_PAYLOAD)
    project_id = create_response.json()["project_id"]

    # Updating only `street` to one that belongs to a different city than the project's
    # existing (unchanged) city — the router must re-check against the merged pair.
    response = client.patch(f"/projects/{project_id}", json={"source": "SETTINGS", "diff": {"street": OTHER_CITY_STREET}})

    assert response.status_code == 422
    unchanged = client.get(f"/projects/{project_id}").json()
    assert unchanged["street"] == VALID_PAYLOAD["street"]


def test_update_project_city_only_invalidating_existing_street_is_rejected(client: TestClient):
    create_response = client.post("/projects", json=VALID_PAYLOAD)
    project_id = create_response.json()["project_id"]

    # Updating only `city` — the project's existing (unchanged) street doesn't belong to it.
    response = client.patch(f"/projects/{project_id}", json={"source": "SETTINGS", "diff": {"city": OTHER_CITY}})

    assert response.status_code == 422
    unchanged = client.get(f"/projects/{project_id}").json()
    assert unchanged["city"] == VALID_PAYLOAD["city"]


def test_update_project_street_only_still_matching_existing_city_succeeds(client: TestClient):
    create_response = client.post("/projects", json=VALID_PAYLOAD)
    project_id = create_response.json()["project_id"]

    response = client.patch(f"/projects/{project_id}", json={"source": "SETTINGS", "diff": {"street": "אבני החושן"}})

    assert response.status_code == 200
    assert response.json()["street"] == "אבני החושן"


def test_update_project_plot_and_built_area_together_valid_succeeds(client: TestClient):
    create_response = client.post("/projects", json=VALID_PAYLOAD)
    project_id = create_response.json()["project_id"]

    response = client.patch(
        f"/projects/{project_id}", json={"source": "SETTINGS", "diff": {"plot_area_m2": 300, "built_area_m2": 250}}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["plot_area_m2"] == 300
    assert body["built_area_m2"] == 250


def test_update_project_plot_and_built_area_together_mismatched_is_rejected(client: TestClient):
    create_response = client.post("/projects", json=VALID_PAYLOAD)
    project_id = create_response.json()["project_id"]

    response = client.patch(
        f"/projects/{project_id}", json={"source": "SETTINGS", "diff": {"plot_area_m2": 200, "built_area_m2": 220}}
    )

    assert response.status_code == 422


def test_update_project_built_area_only_not_smaller_than_existing_plot_is_rejected(client: TestClient):
    create_response = client.post("/projects", json=VALID_PAYLOAD)
    project_id = create_response.json()["project_id"]

    # VALID_PAYLOAD's plot_area_m2 is 500 — updating built_area_m2 alone to >= that must fail.
    response = client.patch(f"/projects/{project_id}", json={"source": "SETTINGS", "diff": {"built_area_m2": 500}})

    assert response.status_code == 422
    unchanged = client.get(f"/projects/{project_id}").json()
    assert unchanged["built_area_m2"] == VALID_PAYLOAD["built_area_m2"]


def test_update_project_plot_area_only_invalidating_existing_built_area_is_rejected(client: TestClient):
    create_response = client.post("/projects", json=VALID_PAYLOAD)
    project_id = create_response.json()["project_id"]

    # VALID_PAYLOAD's built_area_m2 is 220 — shrinking plot_area_m2 below that must fail.
    response = client.patch(f"/projects/{project_id}", json={"source": "SETTINGS", "diff": {"plot_area_m2": 100}})

    assert response.status_code == 422
    unchanged = client.get(f"/projects/{project_id}").json()
    assert unchanged["plot_area_m2"] == VALID_PAYLOAD["plot_area_m2"]


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
