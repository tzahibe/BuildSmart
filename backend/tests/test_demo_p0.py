"""Demo P0: a real natural-language brief reaching the validated pipeline.

Every test here goes through the SAME routes a real user hits:

    POST /projects                      (brief + built area + selected footprint)
    POST /projects/{id}/requirements    (the parser)
    GET  /projects/{id}/review          (what I understood)
    POST /projects/{id}/design/demo     (the validated pipeline)

No `ArchitecturalSpec` is constructed by hand anywhere in this file, no canonical fixture is
injected, and no room list is supplied halfway through. The parser is the only faked component —
it stands in for the OpenAI call, exactly as `tests/test_requirements.py` already does, with
canned outputs matching what the prompt asks the model to produce.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.projects.models import PoolField, SourceTag, TaggedBool, TaggedFloat, TaggedInt
from app.projects.repository import JsonFileProjectRepository
from app.projects.routes import base_routes as project_base_routes
from app.requirements import router as requirements_router
from app.requirements.parser import RequirementExtraction, RequirementParser

REQ = SourceTag.requested
INF = SourceTag.inferred
UNK = SourceTag.unknown


def _extraction(*, bedrooms, safe_room, wet_rooms, open_plan, parking,
                floors=1, pool=False) -> RequirementExtraction:
    return RequirementExtraction(
        floors=TaggedInt(value=floors, source=INF),
        bedrooms=TaggedInt(value=bedrooms, source=REQ),
        safe_room=TaggedBool(value=safe_room, source=REQ if safe_room else UNK),
        parking_spaces=TaggedInt(value=parking, source=REQ),
        pool=PoolField(
            requested=TaggedBool(value=pool or None, source=REQ if pool else UNK),
            length_m=TaggedFloat(value=None, source=UNK),
            width_m=TaggedFloat(value=None, source=UNK),
        ),
        wet_rooms=TaggedInt(value=wet_rooms, source=REQ),
        open_plan=TaggedBool(value=open_plan, source=REQ),
    )


# The five demo briefs, in the user's own language.
BRIEF_3BR_SAFE_OPEN = (
    "בית פרטי בקומה אחת עם שלושה חדרי שינה, ממ\"ד, מטבח פתוח לסלון ולפינת אוכל, "
    "שני חדרי רחצה ושתי חניות."
)
BRIEF_2BR_COMPACT = (
    "בית קטן לזוג, שני חדרי שינה, חדר רחצה אחד, סלון ומטבח פתוחים, חניה אחת."
)
BRIEF_2BR_SAFE = (
    "שני חדרי שינה וממ\"ד, מטבח סגור, לא מטבח פתוח, חדר רחצה אחד, שתי חניות."
)
BRIEF_3BR_THREE_WET = (
    "שלושה חדרי שינה, ממ\"ד, שלושה חדרי רחצה — אחד צמוד לחדר ההורים, מטבח פתוח, שתי חניות."
)
BRIEF_4BR_UNSUPPORTED = "בית עם ארבעה חדרי שינה, ממ\"ד ושלושה חדרי רחצה."

CANNED = {
    BRIEF_3BR_SAFE_OPEN: _extraction(bedrooms=3, safe_room=True, wet_rooms=2,
                                     open_plan=True, parking=2),
    BRIEF_2BR_COMPACT: _extraction(bedrooms=2, safe_room=None, wet_rooms=1,
                                   open_plan=True, parking=1),
    # The negation case: "מטבח סגור, לא מטבח פתוח" must NOT become open_plan=True.
    BRIEF_2BR_SAFE: _extraction(bedrooms=2, safe_room=True, wet_rooms=1,
                                open_plan=False, parking=2),
    BRIEF_3BR_THREE_WET: _extraction(bedrooms=3, safe_room=True, wet_rooms=3,
                                     open_plan=True, parking=2),
    BRIEF_4BR_UNSUPPORTED: _extraction(bedrooms=4, safe_room=True, wet_rooms=3,
                                       open_plan=False, parking=2),
}


class FakeParser(RequirementParser):
    def parse(self, description: str) -> RequirementExtraction:
        try:
            return CANNED[description]
        except KeyError:
            raise AssertionError(f"no canned extraction for: {description!r}")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    repo = JsonFileProjectRepository(tmp_path / "projects.json")
    monkeypatch.setattr(project_base_routes, "repository", repo)
    monkeypatch.setattr(requirements_router, "parser", FakeParser())
    return TestClient(app)


def _create(client: TestClient, description: str, *, width=11.0, depth=13.5) -> str:
    area = round(width * depth, 2)
    response = client.post("/projects", json={
        "city": "מודיעין-מכבים-רעות", "street": "עמק זבולון",
        "plot_area_m2": 500.0, "built_area_m2": area,
        "description": description,
        "selected_footprint": {
            "source": "PRESET", "shape_type": "RECTANGLE",
            "target_area_m2": area, "area_m2": area,
            "width_m": width, "depth_m": depth,
        },
    })
    assert response.status_code == 201, response.text
    return response.json()["project_id"]


def _run(client: TestClient, description: str, **kwargs):
    project_id = _create(client, description, **kwargs)
    assert client.post(f"/projects/{project_id}/requirements").status_code == 200
    review = client.get(f"/projects/{project_id}/review")
    assert review.status_code == 200
    design = client.post(f"/projects/{project_id}/design/demo")
    return project_id, review.json(), design


# ------------------------------------------------------------------ A-D: valid briefs

#: brief -> (expected review values, selected footprint the user picked).
#: The footprint is the user's own choice and the pipeline plans INSIDE it, so each brief gets a
#: footprint a house of that size actually fits in. An 11.0 x 13.5 m rectangle genuinely cannot
#: host 3 bedrooms + safe room + 3 wet rooms, and the pipeline says so rather than shrinking the
#: request — see `test_footprint_too_small_is_reported_not_silently_shrunk`.
VALID_BRIEFS = {
    "A_2BR": (BRIEF_2BR_COMPACT, {"bedrooms": 2, "wet_rooms": 1, "open_plan": True}, (11.0, 12.0)),
    "B_2BR_SAFE": (BRIEF_2BR_SAFE, {"bedrooms": 2, "wet_rooms": 1, "open_plan": False}, (12.0, 13.0)),
    "C_3BR_SAFE_OPEN": (BRIEF_3BR_SAFE_OPEN, {"bedrooms": 3, "wet_rooms": 2, "open_plan": True}, (12.5, 14.5)),
    "D_3BR_THREE_WET": (BRIEF_3BR_THREE_WET, {"bedrooms": 3, "wet_rooms": 3, "open_plan": True}, (13.0, 15.0)),
}


def _run_case(client, case):
    brief, expected, (width, depth) = VALID_BRIEFS[case]
    project_id, review, design = _run(client, brief, width=width, depth=depth)
    return brief, expected, review, design


@pytest.mark.parametrize("case", sorted(VALID_BRIEFS))
def test_brief_reaches_the_validated_pipeline_and_returns_a_plan(client, case):
    _, expected, review, design = _run_case(client, case)
    assert design.status_code == 200, design.text
    for field, value in expected.items():
        assert review[field]["value"] == value, f"{case}: {field}"


@pytest.mark.parametrize("case", sorted(VALID_BRIEFS))
def test_generated_plan_passes_every_hard_check(client, case):
    _, _, _, design = _run_case(client, case)
    body = design.json()
    assert body["validation"]["passed"]
    assert all(body["validation"]["checks"].values())
    assert body["validation"]["checks"]["C13"], "realized connectivity must pass"
    assert body["validation"]["checks"]["C5"], "physical reachability must pass"
    assert not body["validation"]["warnings"]


@pytest.mark.parametrize("case", sorted(VALID_BRIEFS))
def test_requested_rooms_all_exist(client, case):
    brief, expected, _, design = _run_case(client, case)
    body = design.json()
    types = [r["type"] for r in body["rooms"]]
    bedrooms = types.count("BEDROOM") + types.count("MASTER_BEDROOM")
    assert bedrooms == expected["bedrooms"]
    assert types.count("BATHROOM") == expected["wet_rooms"]
    assert ("SAFE_ROOM" in types) == ("ממ" in brief)


@pytest.mark.parametrize("case", sorted(VALID_BRIEFS))
def test_output_is_authoritative_enough_to_render(client, case):
    _, _, _, design = _run_case(client, case)
    body = design.json()
    assert body["walls"], "wall segments must be derived by the backend"
    assert body["doors"], "doors must come from the backend"
    assert any(d["is_entrance"] for d in body["doors"])
    assert body["windows"], "windows must come from the backend"
    assert body["rooms"] and all(r["name"] for r in body["rooms"])
    assert body["footprint"]["width_m"] > 0 and body["plot"]["width_m"] > 0
    assert body["gross_area_m2"] > 0 and 0.7 < body["net_area_m2"] / body["gross_area_m2"] < 1.0
    for wall in body["walls"]:
        assert wall["construction"] in (
            "STANDARD_PARTITION", "RC_SAFE_ROOM", "STRUCTURAL")
        assert wall["boundary_context"] in ("EXTERIOR", "INTERIOR", "PARTY")


# ------------------------------------------------------------------ negation

def test_closed_kitchen_brief_does_not_become_open_plan(client):
    """The parser rule most easily got wrong: "מטבח סגור, לא מטבח פתוח"."""
    _, review, design = _run(client, BRIEF_2BR_SAFE, width=12.0, depth=13.0)
    assert review["open_plan"]["value"] is False
    body = design.json()
    # A closed kitchen means no wall-less join anywhere between the public rooms.
    public = {r["id"] for r in body["rooms"] if r["type"] in ("LIVING", "KITCHEN", "DINING")}
    for interface in body["open_interfaces"]:
        assert not (set(interface["room_ids"]) <= public and len(interface["room_ids"]) > 1)


def test_open_plan_brief_produces_physically_open_rooms(client):
    _, review, design = _run(client, BRIEF_3BR_SAFE_OPEN, width=12.5, depth=14.5)
    assert review["open_plan"]["value"] is True
    body = design.json()
    rooms = {r["id"]: r for r in body["rooms"]}
    assert rooms["LIVING"]["walls"]["S"]["construction"] == "NONE"
    shared = [i for i in body["open_interfaces"] if len(i["room_ids"]) > 1]
    assert shared, "an open-plan brief must yield real wall-less joins"


# ------------------------------------------------------------------ E: explicit rejection

def test_four_bedroom_brief_is_rejected_explicitly(client):
    project_id = _create(client, BRIEF_4BR_UNSUPPORTED)
    assert client.post(f"/projects/{project_id}/requirements").status_code == 200
    response = client.post(f"/projects/{project_id}/design/demo")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "BEDROOMS_UNSUPPORTED"
    assert "4" in detail["detail"]
    assert detail["message"]


def test_rejection_never_silently_downgrades_the_request(client):
    """A refused brief must produce NO plan at all, not a quietly smaller house."""
    project_id = _create(client, BRIEF_4BR_UNSUPPORTED)
    client.post(f"/projects/{project_id}/requirements")
    assert client.post(f"/projects/{project_id}/design/demo").status_code == 422
    review = client.get(f"/projects/{project_id}/review").json()
    assert review["bedrooms"]["value"] == 4, "the request itself is preserved untouched"


def test_generation_before_parsing_is_refused(client):
    project_id = _create(client, BRIEF_2BR_COMPACT)
    response = client.post(f"/projects/{project_id}/design/demo")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "REQUIREMENTS_NOT_PARSED"


# ------------------------------------------------------------------ review contract

def test_review_shows_what_was_understood_with_provenance(client):
    _, review, _ = _run(client, BRIEF_3BR_SAFE_OPEN, width=12.5, depth=14.5)
    assert review["bedrooms"] == {"value": 3, "source": "requested"}
    assert review["open_plan"]["source"] == "requested"
    assert review["footprint_width_m"] == 12.5
    assert review["description"] == BRIEF_3BR_SAFE_OPEN
    # No internal spec detail leaks into the product contract.
    assert "program" not in review and "plot" not in review


def test_review_edits_are_what_generation_uses(client):
    """The corrected requirements — not the originally parsed ones — must drive the plan."""
    project_id = _create(client, BRIEF_3BR_SAFE_OPEN, width=12.5, depth=14.5)
    client.post(f"/projects/{project_id}/requirements")
    first = client.post(f"/projects/{project_id}/design/demo").json()
    assert sum(1 for r in first["rooms"] if r["type"] in ("BEDROOM", "MASTER_BEDROOM")) == 3

    # The user corrects "3 bedrooms" to 2 in the REVIEW screen.
    repo = project_base_routes.repository
    project = repo.get(project_id)
    repo.set_parsed_requirements(
        project_id,
        floors=project.floors,
        bedrooms=TaggedInt(value=2, source=REQ),
        safe_room=project.safe_room,
        parking_spaces=project.parking_spaces,
        pool=project.pool,
        wet_rooms=project.wet_rooms,
        open_plan=project.open_plan,
    )
    assert client.get(f"/projects/{project_id}/review").json()["bedrooms"]["value"] == 2

    second = client.post(f"/projects/{project_id}/design/demo").json()
    assert sum(1 for r in second["rooms"] if r["type"] in ("BEDROOM", "MASTER_BEDROOM")) == 2


def test_footprint_too_small_is_reported_not_silently_shrunk(client):
    """A footprint that genuinely cannot host the programme is refused with the measured reason —
    the house is never quietly reduced to fit."""
    project_id = _create(client, BRIEF_3BR_THREE_WET, width=9.0, depth=10.0)
    client.post(f"/projects/{project_id}/requirements")
    response = client.post(f"/projects/{project_id}/design/demo")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "PLAN_NOT_REALIZABLE"
    assert detail["detail"], "the refusal must carry the measured reason, not just a code"
    assert client.get(f"/projects/{project_id}/review").json()["bedrooms"]["value"] == 3


def test_no_canonical_fixture_is_reachable_from_the_demo_path():
    """The hand-authored canonical concept and the geometry test fixtures must not be importable
    from anything the demo service touches."""
    import ast
    import pathlib as _pathlib

    forbidden = {"concept", "geometry_fixtures", "pipeline"}
    for path in _pathlib.Path("app/demo").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            for name in names:
                leaf = name.rsplit(".", 1)[-1]
                assert leaf not in forbidden, f"{path.name} imports {name}"


def test_old_solver_path_is_not_used_by_the_demo_service():
    import ast
    import pathlib as _pathlib

    source = _pathlib.Path("app/demo/service.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    modules = [n.module for n in ast.walk(tree)
               if isinstance(n, ast.ImportFrom) and n.module]
    assert not any("app.geometry.solver" in m or "app.architect" in m for m in modules)
    assert any("vertical_slice" in m for m in modules)
