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
    RoomRelationship,
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


#: The demo setback assumptions these fixtures are sized against (app/demo/site_geometry.py).
_F, _S, _R = 5.5, 3.0, 4.0


def _create(client: TestClient, description: str, *, width=11.0, depth=13.5,
            plot_width_m: float | None = None, plot_depth_m: float | None = None,
            street_facing_side: str = "NORTH") -> str:
    """Creates a project on a parcel that GENUINELY holds the house.

    These used to declare a flat `plot_area_m2: 500` and no dimensions at all, which the planner
    then ignored — it synthesised its own site from the footprint. One fixture
    (15.5 x 15.5) needed 538 m² and declared 500, and nothing noticed. Now the plot is stated
    honestly: the footprint plus the setbacks plus a metre of slack, so each test is a person whose
    land really does fit their house. Callers that are testing the FIT RULE itself pass their own
    plot dimensions instead.
    """
    area = round(width * depth, 2)
    plot_w = plot_width_m if plot_width_m is not None else round(width + 2 * _S + 1.0, 2)
    plot_d = plot_depth_m if plot_depth_m is not None else round(depth + _F + _R + 1.0, 2)
    response = client.post("/projects", json={
        "city": "מודיעין-מכבים-רעות", "street": "עמק זבולון",
        "plot_area_m2": round(plot_w * plot_d, 2), "built_area_m2": area,
        "plot_width_m": plot_w, "plot_depth_m": plot_d,
        "street_facing_side": street_facing_side,
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


# ------------------------------------------------------------- room relationships, end to end
#
# "לא רוצה חדר שינה צמוד למטבח" used to be dropped as an unsupported request. Relationships now
# reach the planner as structure, decide WHICH realized candidate is chosen, and are checked (C15)
# against the walls and doors the plan actually has.

def _rel(source, target, relation, strength, text="בקשה", ambiguous=False) -> RoomRelationship:
    return RoomRelationship(source_role=source, target_role=target, relation=relation,
                            strength=strength, source_text=text, ambiguous=ambiguous)


def _rel_run(tmp_path, monkeypatch, *relations, side_m=14.14, brief=BRIEF_3BR_SAFE_OPEN):
    class _P(RequirementParser):
        def parse(self, description: str) -> RequirementExtraction:
            return CANNED[brief].model_copy(update={"room_relationships": list(relations)})

    repo = JsonFileProjectRepository(tmp_path / "projects.json")
    monkeypatch.setattr(project_base_routes, "repository", repo)
    monkeypatch.setattr(requirements_router, "parser", _P())
    client = TestClient(app)
    project_id = _create(client, brief, width=side_m, depth=side_m)
    client.post(f"/projects/{project_id}/requirements")
    review = client.get(f"/projects/{project_id}/review").json()
    return review, client.post(f"/projects/{project_id}/design/demo")


def _shared_boundary_m(design: dict, a_type: str, b_type: str) -> float:
    """Longest shared boundary between any room of each type, measured off the returned plan."""
    def rooms(t):
        return [r for r in design["rooms"] if r["type"] == t]
    best = 0.0
    for ra in rooms(a_type):
        for rb in rooms(b_type):
            x_overlap = min(ra["x"] + ra["width_m"], rb["x"] + rb["width_m"]) - max(ra["x"], rb["x"])
            y_overlap = min(ra["y"] + ra["depth_m"], rb["y"] + rb["depth_m"]) - max(ra["y"], rb["y"])
            if abs(x_overlap) < 1e-9 and y_overlap > 1e-9:
                best = max(best, y_overlap)
            elif abs(y_overlap) < 1e-9 and x_overlap > 1e-9:
                best = max(best, x_overlap)
    return best


def test_A_hard_adjacency_is_realized_in_the_geometry(tmp_path, monkeypatch):
    """"חדר ההורים חייב להיות צמוד לחדר הרחצה" — a real shared wall, not a declared edge."""
    review, design = _rel_run(tmp_path, monkeypatch,
                              _rel("MASTER_BEDROOM", "ENSUITE", "adjacent", "hard_requirement"))
    assert review["room_relationships"][0]["relation"] == "adjacent"
    assert design.status_code == 200, design.text
    body = design.json()
    assert body["validation"]["checks"]["C15"] is True
    assert body["relationships"][0]["satisfied"] is True
    assert _shared_boundary_m(body, "MASTER_BEDROOM", "BATHROOM") >= 0.9


def test_B_a_separation_leaves_no_shared_wall(tmp_path, monkeypatch):
    """"לא רוצה חדר שינה צמוד למטבח" — measured on the plan, not asserted by the concept."""
    _, design = _rel_run(tmp_path, monkeypatch,
                         _rel("BEDROOM", "KITCHEN", "not_adjacent", "hard_requirement"))
    assert design.status_code == 200, design.text
    body = design.json()
    assert body["validation"]["checks"]["C15"] is True
    assert _shared_boundary_m(body, "BEDROOM", "KITCHEN") == 0.0


def test_C_a_preference_is_reported_either_way(tmp_path, monkeypatch):
    """"עדיף שהממ״ד יהיה קרוב לחדרי הילדים" — never blocks, always reported."""
    _, design = _rel_run(tmp_path, monkeypatch,
                         _rel("SAFE_ROOM", "BEDROOM", "near", "preference"))
    assert design.status_code == 200, design.text
    body = design.json()
    outcome = body["relationships"][0]
    assert outcome["strength"] == "preference"
    if outcome["satisfied"]:
        assert outcome["statement"] in body["validation"]["statements"]
    else:
        assert any(outcome["statement"] in w for w in body["validation"]["warnings"])


def test_D_a_hard_relationship_that_cannot_be_realized_fails_explicitly(tmp_path, monkeypatch):
    """A kitchen against the safe room is not something this programme can arrange."""
    _, design = _rel_run(tmp_path, monkeypatch,
                         _rel("KITCHEN", "SAFE_ROOM", "adjacent", "hard_requirement"))
    assert design.status_code == 422, design.text
    body = design.json()["detail"]
    assert body["code"] == "ROOM_RELATIONSHIP_NOT_FEASIBLE"
    assert "impossible" not in body["message"].lower()
    assert "העדפה" in body["message"]      # offers the way forward


def test_E_the_same_relationship_as_a_preference_still_produces_a_plan(tmp_path, monkeypatch):
    _, design = _rel_run(tmp_path, monkeypatch,
                         _rel("KITCHEN", "SAFE_ROOM", "adjacent", "preference"))
    assert design.status_code == 200, design.text
    body = design.json()
    assert body["relationships"][0]["satisfied"] is False
    assert any("העדפה שלא התממשה" in w for w in body["validation"]["warnings"])
    assert body["validation"]["passed"] is True


def test_F_an_ambiguous_room_reference_asks_instead_of_guessing(tmp_path, monkeypatch):
    _, design = _rel_run(tmp_path, monkeypatch,
                         _rel("", "KITCHEN", "not_adjacent", "hard_requirement",
                              text="החדר הגדול לא ליד המטבח", ambiguous=True))
    assert design.status_code == 422, design.text
    body = design.json()["detail"]
    assert body["code"] == "AMBIGUOUS_ROOM_REFERENCE"
    assert "החדר הגדול" in body["message"]


def test_G_adjacency_alone_never_fabricates_a_door(tmp_path, monkeypatch):
    """ADJACENCY IS NOT ACCESS. Asking for a shared wall must not produce a door through it."""
    _, plain = _rel_run(tmp_path, monkeypatch)
    _, adjacent = _rel_run(tmp_path, monkeypatch,
                           _rel("MASTER_BEDROOM", "ENSUITE", "adjacent", "hard_requirement"))
    assert plain.status_code == 200 and adjacent.status_code == 200

    def door_pairs(response):
        return {frozenset((d["a"], d["b"])) for d in response.json()["doors"]}

    # the adjacency request adds no door that the same plan did not already have
    assert door_pairs(adjacent) - door_pairs(plain) == set()


def test_H_direct_access_uses_the_existing_topology(tmp_path, monkeypatch):
    """DIRECT_ACCESS is satisfied by a real door — the engine's own connection, not a new one."""
    _, design = _rel_run(tmp_path, monkeypatch,
                         _rel("MASTER_BEDROOM", "ENSUITE", "direct_access", "hard_requirement"))
    assert design.status_code == 200, design.text
    body = design.json()
    assert body["relationships"][0]["satisfied"] is True
    master = next(r["id"] for r in body["rooms"] if r["type"] == "MASTER_BEDROOM")
    bath_ids = {r["id"] for r in body["rooms"] if r["type"] == "BATHROOM"}
    assert any({d["a"], d["b"]} & bath_ids and master in {d["a"], d["b"]} for d in body["doors"])


def test_near_is_not_quietly_upgraded_to_adjacent(tmp_path, monkeypatch):
    """NEAR has its own measurable meaning and must not be satisfied only by a shared wall."""
    review, design = _rel_run(tmp_path, monkeypatch,
                              _rel("SAFE_ROOM", "BEDROOM", "near", "hard_requirement"))
    assert review["room_relationships"][0]["relation"] == "near"
    assert design.status_code == 200, design.text
    assert design.json()["relationships"][0]["satisfied"] is True


# --------------------------------------------------- the review must account for the whole brief
#
# Reported from the product. The brief was: 2 children's rooms, a large master with its own shower
# and toilet, a living room, a kitchen, A SMALL STUDY, and 2 parking spaces. The review came back as
# "3 bedrooms, 1 bathroom, 2 parking" — the study was neither planned nor reported as unplannable,
# and nothing on the screen said what the house would actually contain.

def test_the_review_says_what_the_house_will_actually_contain(client):
    project_id = _create(client, BRIEF_3BR_SAFE_OPEN, width=12.5, depth=14.5)
    client.post(f"/projects/{project_id}/requirements")
    review = client.get(f"/projects/{project_id}/review").json()

    rooms = review["planned_rooms"]
    assert rooms, "counts alone hide what is missing — the room list must be shown"
    # named rooms, not counts: a reader can see at a glance that no study is among them
    assert "סלון" in rooms and "מטבח" in rooms and "חדר הורים" in rooms
    assert any(r.startswith("חדר שינה") for r in rooms)
    assert not any("עבודה" in r for r in rooms)


def test_the_room_list_matches_the_plan_that_gets_built(client):
    """The list is built from the planner's own programme, so it cannot promise a room the drawing
    does not have."""
    project_id = _create(client, BRIEF_3BR_SAFE_OPEN, width=12.5, depth=14.5)
    client.post(f"/projects/{project_id}/requirements")
    listed = client.get(f"/projects/{project_id}/review").json()["planned_rooms"]
    design = client.post(f"/projects/{project_id}/design/demo")
    assert design.status_code == 200, design.text

    def counted(names):
        out = {}
        for name in names:
            base, _, mult = name.partition(" ×")
            out[base] = out.get(base, 0) + (int(mult) if mult else 1)
        return out

    assert counted(listed) == counted(r["name"] for r in design.json()["rooms"])


def test_the_room_list_follows_a_correction(client):
    """Correcting the review changes what will be built, so the list must change with it."""
    project_id = _create(client, BRIEF_3BR_SAFE_OPEN, width=12.5, depth=14.5)
    client.post(f"/projects/{project_id}/requirements")
    before = client.get(f"/projects/{project_id}/review").json()["planned_rooms"]
    after = client.put(f"/projects/{project_id}/review",
                       json={"bedrooms": 2}).json()["planned_rooms"]
    assert before != after
    assert "חדר שינה" in after      # one child's room now, so no "×2"


# ------------------------------------------------------------ authoritative site geometry (P0)
#
# The planner used to build the plot FROM the building — footprint + setbacks — so a person who
# entered a 300 m² parcel had their house laid out on a synthesised 517 m². The site is now the
# input and the buildable region is what is left after subtracting the demo setbacks from it.

def _create_raw(client, *, footprint, plot, street="NORTH", setbacks=None):
    """POST /projects WITHOUT asserting success — for the cases that are meant to be refused."""
    area = round(footprint[0] * footprint[1], 2)
    body = {
        "city": "מודיעין-מכבים-רעות", "street": "עמק זבולון",
        "plot_area_m2": round(plot[0] * plot[1], 2), "built_area_m2": area,
        "plot_width_m": plot[0], "plot_depth_m": plot[1], "street_facing_side": street,
        "description": BRIEF_2BR_COMPACT,
        "selected_footprint": {"source": "PRESET", "shape_type": "RECTANGLE",
                               "target_area_m2": area, "area_m2": area,
                               "width_m": footprint[0], "depth_m": footprint[1]},
    }
    if setbacks:
        body["setbacks"] = setbacks
    return client.post("/projects", json=body)


def _site_run(client, *, footprint=(11.0, 12.0), plot=(20.0, 20.0), street="NORTH"):
    project_id = _create(client, BRIEF_2BR_COMPACT, width=footprint[0], depth=footprint[1],
                         plot_width_m=plot[0], plot_depth_m=plot[1], street_facing_side=street)
    client.post(f"/projects/{project_id}/requirements")
    review = client.get(f"/projects/{project_id}/review").json()
    return project_id, review, client.post(f"/projects/{project_id}/design/demo")


def test_A_a_footprint_that_fits_the_real_site_is_planned(client):
    _, review, design = _site_run(client, footprint=(11.0, 12.0), plot=(20.0, 24.0))
    site = review["site"]
    assert (site["plot_width_m"], site["plot_depth_m"]) == (20.0, 24.0)
    # 20 - 2*3 wide, 24 - 5.5 - 4 deep — the parcel MINUS the setbacks, never more
    assert (site["buildable_width_m"], site["buildable_depth_m"]) == (14.0, 14.5)
    assert site["footprint_fits"] is True
    assert design.status_code == 200, design.text


def test_B_a_footprint_that_does_not_fit_is_refused_at_the_moment_it_is_chosen(client):
    """Refused at CREATION now, not at generation — the earliest point it can be known."""
    response = _create_raw(client, footprint=(11.0, 12.0), plot=(25.0, 16.0))
    assert response.status_code == 422, response.text
    body = response.json()["detail"]
    assert body["code"] == "FOOTPRINT_DOES_NOT_FIT_BUILDABLE_REGION"
    assert "19.00 × 6.50" in body["message"] or "19.00" in body["message"]
    assert "5.50 m too deep" in body["detail"]
    assert "impossible" not in body["message"].lower()


def test_C_the_same_plot_area_gives_different_answers_by_shape(client):
    """400 m² is not a site. 20x20 holds this house; 25x16 and 16x25 do not."""
    _, _, square = _site_run(client, footprint=(11.0, 10.0), plot=(20.0, 20.0))
    wide = _create_raw(client, footprint=(11.0, 10.0), plot=(25.0, 16.0))
    deep = _create_raw(client, footprint=(11.0, 10.0), plot=(16.0, 25.0))
    assert square.status_code == 200, square.text
    assert wide.status_code == 422 and deep.status_code == 422
    assert wide.json()["detail"]["code"] == "FOOTPRINT_DOES_NOT_FIT_BUILDABLE_REGION"


def test_D_the_street_facing_side_changes_the_buildable_rectangle(client):
    """Setbacks are edge-relative, so the frontage decides which dimension loses 9.5 m."""
    def options(street):
        return client.post("/projects/site/footprint-options", json={
            "plot_width_m": 25.0, "plot_depth_m": 16.0,
            "street_facing_side": street, "built_area_m2": 72.0}).json()

    north, east = options("NORTH"), options("EAST")
    assert (north["buildable_width_m"], north["buildable_depth_m"]) == (19.0, 6.5)
    assert (east["buildable_width_m"], east["buildable_depth_m"]) == (10.0, 15.5)

    # a 9 x 8 outline is offered on the east frontage and cannot be on the north one
    assert not any(abs(o["width_m"] - 9.0) < 0.3 and abs(o["depth_m"] - 8.0) < 0.3
                   for o in north["options"])
    assert _create_raw(client, footprint=(9.0, 8.0), plot=(25.0, 16.0),
                       street="NORTH").status_code == 422
    assert _create_raw(client, footprint=(9.0, 8.0), plot=(25.0, 16.0),
                       street="EAST").status_code == 201


def test_E_a_plot_area_that_contradicts_the_dimensions_is_refused(client):
    response = client.post("/projects", json={
        "city": "מודיעין-מכבים-רעות", "street": "עמק זבולון",
        "plot_area_m2": 300.0, "plot_width_m": 20.0, "plot_depth_m": 20.0,
        "street_facing_side": "NORTH", "built_area_m2": 120.0, "description": "x",
    })
    assert response.status_code == 422, response.text
    assert "does not match plot_width_m * plot_depth_m" in response.text


def test_F_a_project_without_site_dimensions_is_refused_not_invented(client):
    """The old fixtures declared an area and no dimensions, and the planner made a site up."""
    response = client.post("/projects", json={
        "city": "מודיעין-מכבים-רעות", "street": "עמק זבולון",
        "plot_area_m2": 500.0, "built_area_m2": 132.0, "description": BRIEF_2BR_COMPACT,
        "selected_footprint": {"source": "PRESET", "shape_type": "RECTANGLE",
                               "target_area_m2": 132.0, "area_m2": 132.0,
                               "width_m": 11.0, "depth_m": 12.0},
    })
    project_id = response.json()["project_id"]
    client.post(f"/projects/{project_id}/requirements")
    design = client.post(f"/projects/{project_id}/design/demo")
    assert design.status_code == 422
    assert design.json()["detail"]["code"] == "SITE_GEOMETRY_REQUIRED"


def test_G_no_code_path_reconstructs_a_site_from_the_footprint():
    """The defect itself, pinned at the source: the building may never generate the land."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    banned = ("footprint.width_m + 2 * SIDE_SETBACK", "footprint.depth_m + FRONT_SETBACK",
              "width_m=footprint.width_m + ", "depth_m=footprint.depth_m + ")
    offenders = []
    # The demo path only. `app/geometry` is the legacy solver, which has its own (already flagged)
    # square-site placeholder and is not what this rule is about.
    for path in list((root / "demo").rglob("*.py")) + list((root / "vertical_slice").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for phrase in banned:
            if phrase in text:
                offenders.append(f"{path.relative_to(root)}: {phrase}")
    assert not offenders, f"a site is being derived from a building: {offenders}"

    # and the derivation cannot even see a footprint
    import inspect
    from app.demo import site_geometry
    assert "footprint" not in inspect.signature(site_geometry.derive).parameters


def test_setbacks_are_assumptions_that_decide_what_can_be_chosen(client):
    """They are demo assumptions, labelled as such, and correcting them changes what is possible.

    They are supplied at CREATION as well as editable in review, because they decide which
    footprints exist to choose from — validating a choice against defaults the person had already
    corrected would refuse an outline that is fine under their own numbers.
    """
    # 11 x 12 does not fit 20 x 20 at the default 5.5 / 4
    assert _create_raw(client, footprint=(11.0, 12.0), plot=(20.0, 20.0)).status_code == 422

    relaxed = {"front_m": 3.0, "side_m": 3.0, "rear_m": 2.0}
    created = _create_raw(client, footprint=(11.0, 12.0), plot=(20.0, 20.0), setbacks=relaxed)
    assert created.status_code == 201, created.text

    project_id = created.json()["project_id"]
    client.post(f"/projects/{project_id}/requirements")
    review = client.get(f"/projects/{project_id}/review").json()
    assert review["site"]["front_setback_m"] == 3.0
    assert review["site"]["buildable_depth_m"] == 15.0     # 20 - 3 - 2
    assert review["site"]["footprint_fits"] is True
    assert review["site"]["setback_disclaimer"] == (
        "הנחות תכנון לדמו — אינן מידע תכנוני או רגולטורי מאומת.")
    assert client.post(f"/projects/{project_id}/design/demo").status_code == 200


# ------------------------------------------------- footprint options come FROM the site, not an area
#
# A 1440-scenario scan found 1032 FOOTPRINT_DOES_NOT_FIT refusals — 80% of every failure — each one
# a person choosing an outline the system had itself offered from `built_area_m2` alone, knowing
# nothing about the land. Options are now generated from the buildable region.

def _options(client, *, plot=(20.0, 24.0), area=120.0, street="NORTH", setbacks=None):
    body = {"plot_width_m": plot[0], "plot_depth_m": plot[1],
            "street_facing_side": street, "built_area_m2": area}
    if setbacks:
        body.update(setbacks)
    response = client.post("/projects/site/footprint-options", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_every_offered_option_fits_the_buildable_region(client):
    site = _options(client, plot=(20.0, 24.0), area=120.0)
    assert site["options"], "a site that can hold the area must offer something"
    for option in site["options"]:
        assert option["width_m"] <= site["buildable_width_m"] + 1e-9
        assert option["depth_m"] <= site["buildable_depth_m"] + 1e-9


def test_offered_options_never_reduce_the_requested_area(client):
    site = _options(client, plot=(20.0, 24.0), area=120.0)
    for option in site["options"]:
        assert abs(option["area_m2"] - 120.0) <= 0.6, option


def test_variety_is_preserved_where_the_site_allows_it(client):
    """A generous site still offers genuinely different proportions, not four near-identical ones."""
    site = _options(client, plot=(30.0, 34.0), area=120.0)
    ratios = sorted(o["width_m"] / o["depth_m"] for o in site["options"])
    assert len(site["options"]) >= 3
    assert ratios[-1] / ratios[0] > 1.5, ratios


def test_a_tight_site_offers_fewer_options_rather_than_impossible_ones(client):
    site = _options(client, plot=(15.0, 20.0), area=94.0)
    assert 1 <= len(site["options"]) <= 4
    for option in site["options"]:
        assert option["width_m"] <= site["buildable_width_m"] + 1e-9


def test_nothing_fits_is_said_before_choosing_with_the_capacity_named(client):
    site = _options(client, plot=(15.0, 20.0), area=220.0)
    assert site["options"] == []
    rejection = site["rejection"]
    assert rejection["code"] == "BUILT_AREA_EXCEEDS_ONE_STOREY_CAPACITY"
    assert site["one_storey_footprint_capacity_m2"] == 94.5
    for number in ("220", "15.00", "20.00", "9.00", "10.50", "94"):
        assert number in rejection["message"], f"{number} missing from: {rejection['message']}"
    # a GEOMETRIC ceiling, never described as the largest house that can be built
    assert "קיבולת מתאר גאומטרית" in rejection["message"]
    assert "בית מקסימלי" not in rejection["message"]


def test_the_capacity_is_geometric_and_the_programme_can_reduce_it_further(client):
    """The capacity is the buildable rectangle. A plan of exactly that area is not promised."""
    site = _options(client, plot=(15.0, 20.0), area=94.0)
    assert site["one_storey_footprint_capacity_m2"] == pytest.approx(
        site["buildable_width_m"] * site["buildable_depth_m"], abs=0.01)


def test_relaxing_the_assumptions_changes_which_options_exist(client):
    blocked = _options(client, plot=(15.0, 20.0), area=120.0)
    assert blocked["options"] == []
    relaxed = _options(client, plot=(15.0, 20.0), area=120.0,
                       setbacks={"front_setback_m": 3.0, "side_setback_m": 1.5,
                                 "rear_setback_m": 2.0})
    assert relaxed["options"], "correcting the assumptions must open real choices"


def test_the_backend_refuses_an_outline_it_never_offered(client):
    """Client-side filtering is not a guarantee: a stale page or a direct call must still be refused."""
    response = _create_raw(client, footprint=(14.0, 14.0), plot=(15.0, 20.0))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "FOOTPRINT_DOES_NOT_FIT_BUILDABLE_REGION"


def test_an_offered_option_is_always_accepted_end_to_end(client):
    """The contract that makes the refusal disappear from normal flows: offer it, and it works."""
    site = _options(client, plot=(20.0, 26.0), area=120.0)
    for option in site["options"]:
        created = _create_raw(client, footprint=(option["width_m"], option["depth_m"]),
                              plot=(20.0, 26.0))
        assert created.status_code == 201, f"{option} was offered but refused: {created.text}"
