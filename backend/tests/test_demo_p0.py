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
from app.requirements.parser import (
    CorridorWidth,
    CorridorWidthMode,
    RequestSeverity,
    RequirementExtraction,
    RequirementParser,
    UnsupportedRequest,
)

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


# ------------------------------------------------------------------ review edits (PUT)

def test_user_correction_becomes_authoritative_and_drives_generation(client):
    """The REVIEW screen's whole purpose: what the user corrects is what gets built."""
    project_id = _create(client, BRIEF_3BR_SAFE_OPEN, width=12.5, depth=14.5)
    client.post(f"/projects/{project_id}/requirements")

    before = client.post(f"/projects/{project_id}/design/demo").json()
    assert sum(1 for r in before["rooms"] if r["type"] in ("BEDROOM", "MASTER_BEDROOM")) == 3

    edited = client.put(f"/projects/{project_id}/review", json={"bedrooms": 2})
    assert edited.status_code == 200
    assert edited.json()["bedrooms"] == {"value": 2, "source": "requested"}

    after = client.post(f"/projects/{project_id}/design/demo").json()
    assert sum(1 for r in after["rooms"] if r["type"] in ("BEDROOM", "MASTER_BEDROOM")) == 2


def test_review_edit_leaves_untouched_fields_alone(client):
    project_id = _create(client, BRIEF_3BR_SAFE_OPEN, width=12.5, depth=14.5)
    client.post(f"/projects/{project_id}/requirements")
    original = client.get(f"/projects/{project_id}/review").json()

    updated = client.put(f"/projects/{project_id}/review", json={"wet_rooms": 3}).json()
    assert updated["wet_rooms"]["value"] == 3
    assert updated["bedrooms"] == original["bedrooms"]
    assert updated["open_plan"] == original["open_plan"]


def test_correcting_into_unsupported_scope_is_refused_not_planned(client):
    project_id = _create(client, BRIEF_3BR_SAFE_OPEN, width=12.5, depth=14.5)
    client.post(f"/projects/{project_id}/requirements")
    client.put(f"/projects/{project_id}/review", json={"bedrooms": 4})
    response = client.post(f"/projects/{project_id}/design/demo")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "BEDROOMS_UNSUPPORTED"


def test_turning_off_open_plan_in_review_changes_the_built_plan(client):
    project_id = _create(client, BRIEF_3BR_SAFE_OPEN, width=12.5, depth=14.5)
    client.post(f"/projects/{project_id}/requirements")
    open_plan = client.post(f"/projects/{project_id}/design/demo").json()
    assert [i for i in open_plan["open_interfaces"] if len(i["room_ids"]) > 1]

    client.put(f"/projects/{project_id}/review", json={"open_plan": False})
    closed = client.post(f"/projects/{project_id}/design/demo").json()
    public = {r["id"] for r in closed["rooms"] if r["type"] in ("LIVING", "KITCHEN", "DINING")}
    assert not [i for i in closed["open_interfaces"]
                if len(i["room_ids"]) > 1 and set(i["room_ids"]) <= public]


# --------------------------------------------- requirements we cannot plan, graded by how they were asked
#
# Reported from the product: a brief asking for non-adjacent bathrooms and a 5 m corridor produced a
# plan with adjacent bathrooms and a 1.4 m corridor, silently. Disclosure alone is not enough — the
# WORDING decides what may happen next. "עדיף מסדרון רחב" can be set aside with a visible warning;
# "המסדרון חייב להיות לפחות 1.8 מטר" cannot, because planning around it overrules a point the person
# made binding; and wording that settles neither is not ours to decide.

PREFERENCE = "אני מעדיף מסדרון רחב"
HARD = "המסדרון חייב להיות לפחות 1.8 מטר"
AMBIGUOUS = "מסדרון רחב"


def _parser_reporting(*requests: UnsupportedRequest) -> RequirementParser:
    """A parser whose structured half is always the 3BR + safe room + 2 wet + open-plan extraction —
    these tests are only about what it reports ALONGSIDE that."""

    class _P(RequirementParser):
        def parse(self, description: str) -> RequirementExtraction:
            return CANNED[BRIEF_3BR_SAFE_OPEN].model_copy(
                update={"other_requests": list(requests)})

    return _P()


def _client_reporting(tmp_path, monkeypatch, *requests: UnsupportedRequest) -> TestClient:
    repo = JsonFileProjectRepository(tmp_path / "projects.json")
    monkeypatch.setattr(project_base_routes, "repository", repo)
    monkeypatch.setattr(requirements_router, "parser", _parser_reporting(*requests))
    return TestClient(app)


def _run_with(tmp_path, monkeypatch, *requests: UnsupportedRequest):
    client = _client_reporting(tmp_path, monkeypatch, *requests)
    project_id = _create(client, BRIEF_3BR_SAFE_OPEN, width=13.0, depth=15.0)
    client.post(f"/projects/{project_id}/requirements")
    review = client.get(f"/projects/{project_id}/review").json()
    design = client.post(f"/projects/{project_id}/design/demo")
    return review, design


def _req(text: str, severity: RequestSeverity, topic: str = "corridor_width") -> UnsupportedRequest:
    return UnsupportedRequest(text=text, topic=topic, severity=severity)


def test_a_preference_we_cannot_honour_warns_but_still_plans(tmp_path, monkeypatch):
    review, design = _run_with(tmp_path, monkeypatch,
                               _req(PREFERENCE, RequestSeverity.PREFERENCE))

    assert [r["severity"] for r in review["unsupported_requests"]] == ["preference"]
    assert design.status_code == 200, design.text
    assert design.json()["validation"]["passed"] is True
    assert any(PREFERENCE in w for w in design.json()["validation"]["warnings"])
    # the checks that passed still describe only what WAS done
    assert all("לא נכלל" not in st for st in design.json()["validation"]["statements"])


def test_a_hard_requirement_we_cannot_honour_stops_generation(tmp_path, monkeypatch):
    review, design = _run_with(tmp_path, monkeypatch,
                               _req(HARD, RequestSeverity.HARD_REQUIREMENT))

    assert [r["severity"] for r in review["unsupported_requests"]] == ["hard_requirement"]
    assert design.status_code == 422, design.text
    body = design.json()["detail"]
    assert body["code"] == "UNSUPPORTED_HARD_REQUIREMENT"
    assert HARD in body["message"]
    # it must offer a way forward, and must not pretend the house cannot be built
    assert "העדפה" in body["message"]
    assert "impossible" not in body["message"].lower()


def test_wording_that_settles_neither_asks_before_planning(tmp_path, monkeypatch):
    review, design = _run_with(tmp_path, monkeypatch,
                               _req(AMBIGUOUS, RequestSeverity.AMBIGUOUS))

    assert [r["severity"] for r in review["unsupported_requests"]] == ["ambiguous"]
    assert design.status_code == 422, design.text
    body = design.json()["detail"]
    assert body["code"] == "CLARIFICATION_REQUIRED"
    assert AMBIGUOUS in body["message"]


def test_mixed_severities_are_judged_by_the_most_binding_one(tmp_path, monkeypatch):
    review, design = _run_with(
        tmp_path, monkeypatch,
        _req(PREFERENCE, RequestSeverity.PREFERENCE),
        _req(AMBIGUOUS, RequestSeverity.AMBIGUOUS),
        _req(HARD, RequestSeverity.HARD_REQUIREMENT),
        _req("2 חדרי רחצה שלא יהיו צמודים זה לזה", RequestSeverity.AMBIGUOUS, "room_adjacency"),
    )

    assert len(review["unsupported_requests"]) == 4
    assert {r["severity"] for r in review["unsupported_requests"]} == {
        "preference", "ambiguous", "hard_requirement"}

    assert design.status_code == 422
    body = design.json()["detail"]
    # the hard requirement is the blocker, and it is named — an unclear one is less useful to hear
    assert body["code"] == "UNSUPPORTED_HARD_REQUIREMENT"
    assert HARD in body["message"]
    assert PREFERENCE not in body["message"]


def test_an_unclassified_request_fails_closed(tmp_path, monkeypatch):
    """A request with no severity must not be quietly treated as a preference and planned around."""
    review, design = _run_with(tmp_path, monkeypatch,
                               UnsupportedRequest(text=AMBIGUOUS, topic="corridor_width"))
    assert review["unsupported_requests"][0]["severity"] == "ambiguous"
    assert design.status_code == 422
    assert design.json()["detail"]["code"] == "CLARIFICATION_REQUIRED"


def test_a_brief_with_nothing_extra_reports_nothing(client):
    project_id = _create(client, BRIEF_3BR_SAFE_OPEN, width=12.5, depth=14.5)
    client.post(f"/projects/{project_id}/requirements")
    review = client.get(f"/projects/{project_id}/review").json()
    assert review["unsupported_requests"] == []


# ------------------------------------------------------------------ corridor width, end to end
#
# Reported from the product: "מסדרון ברוחב 5 מטר" was silently planned as 1.4 m. Two constants made
# that unavoidable even had the number been extracted — a 2.4 m ceiling in the column partis and a
# fixed 1.4 m in the front-band parti. Both are gone; the requirement now decides the width, and
# C14 checks the REALIZED geometry rather than trusting the spec.

def _corridor_parser(value_m, mode, brief) -> RequirementParser:
    class _P(RequirementParser):
        def parse(self, description: str) -> RequirementExtraction:
            update = {"corridor_width": CorridorWidth(
                value_m=value_m, mode=mode, source="requested" if value_m else "unknown")}
            return CANNED[brief].model_copy(update=update)
    return _P()


def _corridor_run(tmp_path, monkeypatch, value_m, mode, *, side_m=15.5,
                  brief=BRIEF_3BR_SAFE_OPEN):
    repo = JsonFileProjectRepository(tmp_path / "projects.json")
    monkeypatch.setattr(project_base_routes, "repository", repo)
    monkeypatch.setattr(requirements_router, "parser", _corridor_parser(value_m, mode, brief))
    client = TestClient(app)
    project_id = _create(client, brief, width=side_m, depth=side_m)
    client.post(f"/projects/{project_id}/requirements")
    review = client.get(f"/projects/{project_id}/review").json()
    return review, client.post(f"/projects/{project_id}/design/demo")


def test_no_corridor_width_keeps_the_existing_default(tmp_path, monkeypatch):
    review, design = _corridor_run(tmp_path, monkeypatch, None, CorridorWidthMode.MINIMUM)
    assert review["corridor_width"] is None
    assert design.status_code == 200, design.text
    body = design.json()
    # the default path is untouched: no requirement, no C14, and a corridor the planner derived
    assert body["corridor"]["requested_width_m"] is None
    assert "C14" not in body["validation"]["checks"]
    assert body["corridor"]["realized_width_m"] > 0


@pytest.mark.parametrize("requested", [1.6, 1.8])
def test_a_minimum_corridor_width_is_met_or_exceeded(tmp_path, monkeypatch, requested):
    review, design = _corridor_run(tmp_path, monkeypatch, requested, CorridorWidthMode.MINIMUM)

    assert review["corridor_width"]["value_m"] == requested
    assert review["corridor_width"]["mode"] == "minimum"

    assert design.status_code == 200, design.text
    body = design.json()
    assert body["validation"]["checks"]["C14"] is True
    # MINIMUM is one-sided: wider is a pass, narrower is not
    assert body["corridor"]["realized_width_m"] >= requested
    assert body["corridor"]["satisfied"] is True


def test_a_minimum_is_never_reinterpreted_as_an_exact_width(tmp_path, monkeypatch):
    """"לפחות 1.6" must not become "exactly 1.6" — the mode survives the whole path."""
    review, design = _corridor_run(tmp_path, monkeypatch, 1.6, CorridorWidthMode.MINIMUM)
    assert review["corridor_width"]["mode"] == "minimum"
    assert design.json()["corridor"]["requested_mode"] == "minimum"


def test_a_two_metre_request_is_planned_to_two_metres(tmp_path, monkeypatch):
    # A 2 m corridor needs room to exist: the 3-bedroom + safe-room programme cannot spare the
    # width at these sizes (see `test_a_width_the_geometry_cannot_hold_fails_explicitly`), so this
    # uses the two-bedroom brief, where it fits.
    _, design = _corridor_run(tmp_path, monkeypatch, 2.0, CorridorWidthMode.EXACT,
                              side_m=14.14, brief=BRIEF_2BR_COMPACT)
    assert design.status_code == 200, design.text
    body = design.json()
    assert body["corridor"]["requested_mode"] == "exact"
    assert abs(body["corridor"]["realized_width_m"] - 2.0) <= 0.05
    assert body["validation"]["checks"]["C14"] is True


def test_a_width_the_geometry_cannot_hold_fails_explicitly(tmp_path, monkeypatch):
    """Not shrunk, not violated, and not called impossible — a structured planning outcome."""
    _, design = _corridor_run(tmp_path, monkeypatch, 6.0, CorridorWidthMode.MINIMUM)
    assert design.status_code == 422, design.text
    body = design.json()["detail"]
    assert body["code"] == "CORRIDOR_WIDTH_NOT_FEASIBLE"
    assert "6.00" in body["message"]
    assert "impossible" not in body["message"].lower()


def test_a_preferred_width_gives_way_rather_than_blocking(tmp_path, monkeypatch):
    """A preference may be dropped — but never in silence."""
    _, design = _corridor_run(tmp_path, monkeypatch, 6.0, CorridorWidthMode.PREFERENCE)
    assert design.status_code == 200, design.text
    body = design.json()
    assert body["corridor"]["requested_mode"] == "preference"
    assert body["corridor"]["satisfied"] is False
    assert any("מסדרון" in w for w in body["validation"]["warnings"]), body["validation"]["warnings"]


def test_a_hard_width_request_blocks_where_a_preference_would_not(tmp_path, monkeypatch):
    """The same impossible number, worded two ways, must end differently."""
    _, hard = _corridor_run(tmp_path, monkeypatch, 6.0, CorridorWidthMode.MINIMUM)
    _, soft = _corridor_run(tmp_path, monkeypatch, 6.0, CorridorWidthMode.PREFERENCE)
    assert hard.status_code == 422
    assert soft.status_code == 200


def test_a_supported_corridor_width_is_not_left_in_other_requests(tmp_path, monkeypatch):
    review, _ = _corridor_run(tmp_path, monkeypatch, 1.8, CorridorWidthMode.MINIMUM)
    assert review["corridor_width"]["value_m"] == 1.8
    assert all("מסדרון" not in r["text"] for r in review["unsupported_requests"])
