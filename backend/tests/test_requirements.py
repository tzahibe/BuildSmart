import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.projects.models import PoolField, SourceTag, TaggedBool, TaggedFloat, TaggedInt
from app.projects.repository import JsonFileProjectRepository
from app.projects.routes import base_routes as project_base_routes
from app.requirements import router as requirements_router
from app.requirements.parser import (
    _SYSTEM_PROMPT,
    BriefExtraction,
    LaundryRoomDemand,
    OpenAIRequirementParser,
    RequirementExtraction,
    RequirementParser,
)


class FakeRequirementParser(RequirementParser):
    """Deterministic test double — no real OpenAI calls (see research.md's hermeticity decision).
    Canned outputs below are copied verbatim from real gpt-5-nano responses captured during planning."""

    def __init__(self, canned: dict[str, RequirementExtraction]):
        self._canned = canned

    def parse(self, description: str) -> RequirementExtraction:
        try:
            return self._canned[description]
        except KeyError:
            raise AssertionError(f"FakeRequirementParser has no canned result for: {description!r}")


FULL_DESCRIPTION = (
    'אני רוצה בית בן קומתיים בשטח 220 מ"ר, 4 חדרי שינה, ממ"ד, חניה ל-2 עם בריכה 8 על 4 בחצר האחורית'
)
FULL_EXTRACTION = RequirementExtraction(
    floors=TaggedInt(value=2, source=SourceTag.requested),
    bedrooms=TaggedInt(value=4, source=SourceTag.requested),
    safe_room=TaggedBool(value=True, source=SourceTag.requested),
    parking_spaces=TaggedInt(value=2, source=SourceTag.requested),
    pool=PoolField(
        requested=TaggedBool(value=True, source=SourceTag.requested),
        length_m=TaggedFloat(value=8.0, source=SourceTag.requested),
        width_m=TaggedFloat(value=4.0, source=SourceTag.requested),
    ),
)

POOL_NO_DIMS_DESCRIPTION = "בית עם בריכה"
POOL_NO_DIMS_EXTRACTION = RequirementExtraction(
    floors=TaggedInt(value=1, source=SourceTag.inferred),
    bedrooms=TaggedInt(value=None, source=SourceTag.unknown),
    safe_room=TaggedBool(value=None, source=SourceTag.unknown),
    parking_spaces=TaggedInt(value=None, source=SourceTag.unknown),
    pool=PoolField(
        requested=TaggedBool(value=True, source=SourceTag.requested),
        length_m=TaggedFloat(value=None, source=SourceTag.unknown),
        width_m=TaggedFloat(value=None, source=SourceTag.unknown),
    ),
)

CONFLICT_DESCRIPTION = 'בית בן 2 קומות בשטח 150 מ"ר, למעשה יש בו 3 קומות'
CONFLICT_EXTRACTION = RequirementExtraction(
    floors=TaggedInt(value=None, source=SourceTag.unknown),
    bedrooms=TaggedInt(value=None, source=SourceTag.unknown),
    safe_room=TaggedBool(value=None, source=SourceTag.unknown),
    parking_spaces=TaggedInt(value=None, source=SourceTag.unknown),
    pool=PoolField(
        requested=TaggedBool(value=None, source=SourceTag.unknown),
        length_m=TaggedFloat(value=None, source=SourceTag.unknown),
        width_m=TaggedFloat(value=None, source=SourceTag.unknown),
    ),
)

LAUNDRY_DESCRIPTION = 'בית עם 3 חדרי שינה וחדר כביסה נפרד'
LAUNDRY_EXTRACTION = RequirementExtraction(
    floors=TaggedInt(value=1, source=SourceTag.inferred),
    bedrooms=TaggedInt(value=3, source=SourceTag.requested),
    safe_room=TaggedBool(value=None, source=SourceTag.unknown),
    parking_spaces=TaggedInt(value=None, source=SourceTag.unknown),
    pool=PoolField(
        requested=TaggedBool(value=None, source=SourceTag.unknown),
        length_m=TaggedFloat(value=None, source=SourceTag.unknown),
        width_m=TaggedFloat(value=None, source=SourceTag.unknown),
    ),
    laundry=LaundryRoomDemand(requested=TaggedBool(value=True, source=SourceTag.requested),
                              source_text="חדר כביסה נפרד"),
)

#: An appliance mention, deliberately NOT a room request — the negative case the parser's
#: `laundry` rule exists for. See requirements/parser.py's system prompt.
LAUNDRY_APPLIANCE_ONLY_DESCRIPTION = 'בית עם 3 חדרי שינה, יש לי מכונת כביסה במטבח'
LAUNDRY_APPLIANCE_ONLY_EXTRACTION = RequirementExtraction(
    floors=TaggedInt(value=1, source=SourceTag.inferred),
    bedrooms=TaggedInt(value=3, source=SourceTag.requested),
    safe_room=TaggedBool(value=None, source=SourceTag.unknown),
    parking_spaces=TaggedInt(value=None, source=SourceTag.unknown),
    pool=PoolField(
        requested=TaggedBool(value=None, source=SourceTag.unknown),
        length_m=TaggedFloat(value=None, source=SourceTag.unknown),
        width_m=TaggedFloat(value=None, source=SourceTag.unknown),
    ),
    # requested stays False/"inferred" — the model default; no `laundry=` override here.
)

CANNED = {
    FULL_DESCRIPTION: FULL_EXTRACTION,
    POOL_NO_DIMS_DESCRIPTION: POOL_NO_DIMS_EXTRACTION,
    CONFLICT_DESCRIPTION: CONFLICT_EXTRACTION,
    LAUNDRY_DESCRIPTION: LAUNDRY_EXTRACTION,
    LAUNDRY_APPLIANCE_ONLY_DESCRIPTION: LAUNDRY_APPLIANCE_ONLY_EXTRACTION,
}

PROJECT_PAYLOAD_TEMPLATE = {
    "city": "מודיעין-מכבים-רעות",
    "street": "אגוז מכבים רעות",
    "plot_area_m2": 500,
    "built_area_m2": 220,
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    project_repo = JsonFileProjectRepository(tmp_path / "projects.json")
    monkeypatch.setattr(project_base_routes, "repository", project_repo)
    monkeypatch.setattr(requirements_router, "parser", FakeRequirementParser(CANNED))

    return TestClient(app)


def _create_project(client: TestClient, description: str) -> str:
    response = client.post("/projects", json={**PROJECT_PAYLOAD_TEMPLATE, "description": description})
    assert response.status_code == 201
    return response.json()["project_id"]


# --- Parsing merges results directly into the Project -------------------------------------


def test_new_project_has_no_parsed_requirements_yet(client: TestClient):
    project_id = _create_project(client, FULL_DESCRIPTION)

    response = client.get(f"/projects/{project_id}")

    body = response.json()
    assert body["floors"] is None
    assert body["bedrooms"] is None
    assert body["safe_room"] is None
    assert body["parking_spaces"] is None
    assert body["pool"] is None
    assert body["requirements_parsed_at"] is None


def test_parse_fully_specified_description_merges_into_the_project(client: TestClient):
    project_id = _create_project(client, FULL_DESCRIPTION)

    response = client.post(f"/projects/{project_id}/requirements")

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == project_id
    # Structured fields from Feature 01 are untouched by parsing.
    assert body["city"] == PROJECT_PAYLOAD_TEMPLATE["city"]
    assert body["built_area_m2"] == PROJECT_PAYLOAD_TEMPLATE["built_area_m2"]
    # Parsed fields now live directly on the project.
    assert body["floors"] == {"value": 2, "source": "requested"}
    assert body["bedrooms"] == {"value": 4, "source": "requested"}
    assert body["safe_room"] == {"value": True, "source": "requested"}
    assert body["parking_spaces"] == {"value": 2, "source": "requested"}
    assert body["pool"] == {
        "requested": {"value": True, "source": "requested"},
        "length_m": {"value": 8, "source": "requested"},
        "width_m": {"value": 4, "source": "requested"},
    }
    assert body["requirements_parsed_at"]
    # target_built_area_m2 is never extracted — built_area_m2 is the single source of truth.
    assert "target_built_area_m2" not in body


def test_parse_pool_without_dimensions_leaves_unmentioned_fields_unknown(client: TestClient):
    project_id = _create_project(client, POOL_NO_DIMS_DESCRIPTION)

    response = client.post(f"/projects/{project_id}/requirements")

    body = response.json()
    assert body["parking_spaces"]["source"] == "unknown"
    assert body["pool"]["requested"] == {"value": True, "source": "requested"}
    assert body["pool"]["length_m"]["source"] == "unknown"
    assert body["pool"]["width_m"]["source"] == "unknown"


def test_parse_unstated_floors_defaults_to_one_inferred(client: TestClient):
    project_id = _create_project(client, POOL_NO_DIMS_DESCRIPTION)

    response = client.post(f"/projects/{project_id}/requirements")

    assert response.json()["floors"] == {"value": 1, "source": "inferred"}


def test_parse_conflicting_floors_stays_unknown(client: TestClient):
    project_id = _create_project(client, CONFLICT_DESCRIPTION)

    response = client.post(f"/projects/{project_id}/requirements")

    assert response.json()["floors"] == {"value": None, "source": "unknown"}


def test_parse_named_laundry_room_merges_into_the_project(client: TestClient):
    """2026-09-16, phase 1: a named laundry room is a structured field, not an unsupported
    request — see docs/LAUNDRY_ROOM_OPTION_REVIEW.md."""
    project_id = _create_project(client, LAUNDRY_DESCRIPTION)

    response = client.post(f"/projects/{project_id}/requirements")

    body = response.json()
    assert body["laundry_requested"] == {"value": True, "source": "requested"}
    assert body["laundry_source_text"] == "חדר כביסה נפרד"
    # A named room is NOT also reported as an unsupported request.
    assert not any("כביסה" in r["text"] for r in body["unsupported_requests"])


def test_parse_laundry_appliance_mention_does_not_become_a_room_request(client: TestClient):
    """The negative case: a washing machine mentioned in passing must not silently become a
    requested laundry room."""
    project_id = _create_project(client, LAUNDRY_APPLIANCE_ONLY_DESCRIPTION)

    response = client.post(f"/projects/{project_id}/requirements")

    body = response.json()
    assert body["laundry_requested"] == {"value": False, "source": "inferred"}
    assert body["laundry_source_text"] == ""


def test_new_project_has_no_laundry_requirement_yet(client: TestClient):
    project_id = _create_project(client, LAUNDRY_DESCRIPTION)

    response = client.get(f"/projects/{project_id}")

    body = response.json()
    assert body["laundry_requested"] is None
    assert body["laundry_source_text"] == ""


def test_parse_nonexistent_project_returns_404(client: TestClient):
    response = client.post("/projects/00000000-0000-0000-0000-000000000000/requirements")

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


def test_reparse_after_description_update_replaces_the_previous_result(client: TestClient):
    project_id = _create_project(client, POOL_NO_DIMS_DESCRIPTION)
    first = client.post(f"/projects/{project_id}/requirements").json()
    assert first["pool"]["requested"]["value"] is True

    patch_response = client.patch(
        f"/projects/{project_id}", json={"source": "SETTINGS", "diff": {"description": CONFLICT_DESCRIPTION}}
    )
    assert patch_response.status_code == 200

    second = client.post(f"/projects/{project_id}/requirements").json()

    assert second["floors"] == {"value": None, "source": "unknown"}
    assert second["pool"]["requested"]["source"] == "unknown"
    assert second["requirements_parsed_at"] >= first["requirements_parsed_at"]

    # GET now returns the new result, not the original.
    get_response = client.get(f"/projects/{project_id}")
    assert get_response.json() == second


def test_parsing_does_not_change_updated_at(client: TestClient):
    """requirements_parsed_at tracks parses; updated_at tracks the user's own structured edits."""
    project_id = _create_project(client, FULL_DESCRIPTION)
    created_updated_at = client.get(f"/projects/{project_id}").json()["updated_at"]

    response = client.post(f"/projects/{project_id}/requirements")

    assert response.json()["updated_at"] == created_updated_at


_FAKE_BRIEF_EXTRACTION = BriefExtraction(
    floors=TaggedInt(value=1, source=SourceTag.inferred),
    bedrooms=TaggedInt(value=None, source=SourceTag.unknown),
    safe_room=TaggedBool(value=None, source=SourceTag.unknown),
    parking_spaces=TaggedInt(value=None, source=SourceTag.unknown),
    pool=PoolField(
        requested=TaggedBool(value=None, source=SourceTag.unknown),
        length_m=TaggedFloat(value=None, source=SourceTag.unknown),
        width_m=TaggedFloat(value=None, source=SourceTag.unknown),
    ),
)


class _FakeCompletions:
    """Records every call so tests can assert on the exact kwargs sent to the real SDK method."""

    def __init__(self, parsed: BriefExtraction):
        self._parsed = parsed
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        message = type("Message", (), {"parsed": self._parsed})()
        choice = type("Choice", (), {"message": message})()
        return type("Response", (), {"choices": [choice]})()


class _FakeOpenAIClient:
    def __init__(self, parsed: BriefExtraction = _FAKE_BRIEF_EXTRACTION):
        self.completions = _FakeCompletions(parsed)
        self.chat = type("Chat", (), {"completions": self.completions})()


def test_openai_parser_requests_minimal_reasoning_effort_by_default_and_honours_the_env_override(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("REQUIREMENTS_REASONING_EFFORT", raising=False)
    default_parser = OpenAIRequirementParser()
    default_client = _FakeOpenAIClient()
    default_parser._client = default_client

    default_parser.extract("תיאור הבית")

    call = default_client.completions.calls[0]
    assert call["reasoning_effort"] == "minimal"
    assert call["model"] == "gpt-5-nano"
    assert call["response_format"] is BriefExtraction
    assert call["messages"] == [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": "תיאור הבית"},
    ]

    monkeypatch.setenv("REQUIREMENTS_REASONING_EFFORT", "low")
    overridden_parser = OpenAIRequirementParser()
    overridden_client = _FakeOpenAIClient()
    overridden_parser._client = overridden_client

    overridden_parser.extract("תיאור הבית")

    overridden_call = overridden_client.completions.calls[0]
    assert overridden_call["reasoning_effort"] == "low"
    assert overridden_call["model"] == call["model"]
    assert overridden_call["messages"] == call["messages"]
    assert overridden_call["response_format"] is BriefExtraction


def test_openai_parser_rejects_an_unknown_reasoning_effort(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("REQUIREMENTS_REASONING_EFFORT", raising=False)
    with pytest.raises(ValueError):
        OpenAIRequirementParser(reasoning_effort="extreme")

    monkeypatch.setenv("REQUIREMENTS_REASONING_EFFORT", "extreme")
    with pytest.raises(ValueError):
        OpenAIRequirementParser()
