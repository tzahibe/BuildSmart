"""The parking bays and the house share the street-side band — and the house must yield.

`site.build_parking` draws the bays perpendicular to the street at y=0, 5 m deep. The house used to
be placed at the front setback regardless, and "the bays are in front of the house" held only while
the default setback (5.5 m) happened to exceed a bay. When the default became 0 — asserting no
planning determination — the house moved to the street line and both bays were drawn UNDER it. The
plan showed no parking, C10 still passed (a bay inside the house touches the street too), and
nothing said a word. These tests pin the three parts of the fix: the house is placed behind the
band, a house that cannot fit behind it is refused before planning, and a delivered plan proves the
bays clear of the footprint (C18).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.projects.repository import JsonFileProjectRepository
from app.projects.routes import base_routes as project_base_routes
from app.requirements import router as requirements_router
from app.vertical_slice.site import PARKING_BAY_DEPTH_M

from .test_demo_p0 import BRIEF_3BR_SAFE_OPEN, CANNED, FakeParser, _extraction

BRIEF_NO_PARKING = "בית פרטי עם שלושה חדרי שינה, ממ\"ד, מטבח פתוח, שני חדרי רחצה, בלי חניה."
CANNED[BRIEF_NO_PARKING] = _extraction(bedrooms=3, safe_room=True, wet_rooms=2,
                                       open_plan=True, parking=0)

ZERO = {"front_m": 0.0, "side_m": 0.0, "rear_m": 0.0}
FOOTPRINT = (12.5, 14.5)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    repo = JsonFileProjectRepository(tmp_path / "projects.json")
    monkeypatch.setattr(project_base_routes, "repository", repo)
    monkeypatch.setattr(requirements_router, "parser", FakeParser())
    return TestClient(app)


def _create(client, brief, *, plot, setbacks=ZERO, footprint=FOOTPRINT):
    w, d = footprint
    response = client.post("/projects", json={
        "city": "מודיעין-מכבים-רעות", "street": "עמק זבולון",
        "plot_area_m2": round(plot[0] * plot[1], 2), "built_area_m2": round(w * d, 2),
        "plot_width_m": plot[0], "plot_depth_m": plot[1],
        "street_facing_side": "NORTH", "setbacks": setbacks,
        "description": brief,
        "selected_footprint": {"source": "PRESET", "shape_type": "RECTANGLE",
                               "target_area_m2": round(w * d, 2), "area_m2": round(w * d, 2),
                               "width_m": w, "depth_m": d},
    })
    assert response.status_code == 201, response.text
    project_id = response.json()["project_id"]
    assert client.post(f"/projects/{project_id}/requirements").status_code == 200
    return project_id


def _overlap(a, b):
    ox = min(a["x"] + a["width_m"], b["x"] + b["width_m"]) - max(a["x"], b["x"])
    oy = min(a["y"] + a["depth_m"], b["y"] + b["depth_m"]) - max(a["y"], b["y"])
    return max(ox, 0.0) * max(oy, 0.0)


def test_with_zero_setbacks_the_house_stands_behind_the_parking_bays(client):
    """The product default. Before the fix both bays lay entirely inside the footprint."""
    project_id = _create(client, BRIEF_3BR_SAFE_OPEN, plot=(20.0, 26.0))
    response = client.post(f"/projects/{project_id}/design/demo")
    assert response.status_code == 200, response.text
    plan = response.json()["plan"]

    assert len(plan["parking"]) == 2
    assert plan["footprint"]["y"] == pytest.approx(PARKING_BAY_DEPTH_M)
    for bay in plan["parking"]:
        assert bay["y"] == 0.0, "the bays still front the street"
        assert _overlap(bay, plan["footprint"]) == 0.0, f"bay {bay} is drawn under the house"
    walk = plan["entrance_walk"]
    assert walk["depth_m"] == pytest.approx(PARKING_BAY_DEPTH_M), "the walk crosses the band"
    assert plan["validation"]["checks"]["C18"] is True
    assert plan["validation"]["checks"]["C10"] is True
    assert plan["validation"]["checks"]["C11"] is True


def test_without_parking_a_zero_setback_still_puts_the_house_on_the_street_line(client):
    """The band is the bay depth only when there are bays: no parking, no band, no change."""
    project_id = _create(client, BRIEF_NO_PARKING, plot=(20.0, 26.0))
    response = client.post(f"/projects/{project_id}/design/demo")
    assert response.status_code == 200, response.text
    plan = response.json()["plan"]
    assert plan["parking"] == []
    assert plan["footprint"]["y"] == 0.0
    assert plan["validation"]["checks"]["C18"] is True


def test_a_front_setback_deeper_than_a_bay_is_left_alone(client):
    """5.5 m was always enough for a 5 m bay; the fix must not move those houses."""
    project_id = _create(client, BRIEF_3BR_SAFE_OPEN, plot=(20.0, 26.0),
                         setbacks={"front_m": 5.5, "side_m": 3.0, "rear_m": 4.0})
    plan = client.post(f"/projects/{project_id}/design/demo").json()["plan"]
    assert plan["footprint"]["y"] == pytest.approx(5.5)
    assert all(_overlap(bay, plan["footprint"]) == 0.0 for bay in plan["parking"])


def test_a_house_that_cannot_fit_behind_the_bays_is_refused_before_planning(client):
    """14.5 m of house + 5 m of parking on an 18 m deep parcel: the outline passed the setback fit
    (zero setbacks leave the whole parcel), but there is no plan that has both. Refused with a code
    that names parking, not the setbacks — lowering those any further cannot help."""
    project_id = _create(client, BRIEF_3BR_SAFE_OPEN, plot=(20.0, 18.0))
    response = client.post(f"/projects/{project_id}/design/demo")
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "FOOTPRINT_LEAVES_NO_ROOM_FOR_PARKING"
    assert "חניה" in detail["message"]
    assert "13.00" in detail["message"], "the message states the depth actually left for the house"


def test_the_same_house_with_no_parking_is_planned_on_that_parcel(client):
    """The refusal above is about the cars, and only the cars."""
    project_id = _create(client, BRIEF_NO_PARKING, plot=(20.0, 18.0))
    response = client.post(f"/projects/{project_id}/design/demo")
    assert response.status_code == 200, response.text


def _create_without_outline(client, brief, *, plot, area_m2):
    """Feature 006: no outline chosen — the engine plans its own feasible shapes."""
    response = client.post("/projects", json={
        "city": "מודיעין-מכבים-רעות", "street": "עמק זבולון",
        "plot_area_m2": round(plot[0] * plot[1], 2), "built_area_m2": area_m2,
        "plot_width_m": plot[0], "plot_depth_m": plot[1],
        "street_facing_side": "NORTH", "setbacks": ZERO,
        "description": brief,
    })
    assert response.status_code == 201, response.text
    project_id = response.json()["project_id"]
    assert client.post(f"/projects/{project_id}/requirements").status_code == 200
    return project_id


def test_engine_outlines_stay_inside_the_parcel_behind_the_parking_band(client):
    """An engine-chosen outline gets no scope check of its own, so the band must bound the
    shapes it is offered. Before: on this parcel the engine planned a 13.8 m deep outline at
    y=5 — ending 0.8 m past the rear boundary — while the person's 14.5 m outline was refused."""
    project_id = _create_without_outline(client, BRIEF_3BR_SAFE_OPEN, plot=(20.0, 18.0),
                                         area_m2=181.25)
    response = client.post(f"/projects/{project_id}/design/demo")
    assert response.status_code == 200, response.text
    body = response.json()
    for plan in [body["plan"], *body.get("alternatives", [])]:
        fp = plan["footprint"]
        assert fp["y"] == pytest.approx(PARKING_BAY_DEPTH_M)
        assert fp["y"] + fp["depth_m"] <= 18.0 + 1e-9, f"outline ends outside the parcel: {fp}"
        assert all(_overlap(bay, fp) == 0.0 for bay in plan["parking"])
        assert plan["validation"]["checks"]["C18"] is True


def test_a_parcel_with_room_for_the_house_or_the_cars_but_not_both_is_refused_without_an_outline(client):
    """181 m² needs ≥ 9.1 m of depth at the widest engine shape; 13 m deep parcel minus the 5 m band
    leaves 8 m. No outline exists, and the refusal says so before planning."""
    project_id = _create_without_outline(client, BRIEF_3BR_SAFE_OPEN, plot=(20.0, 13.0),
                                         area_m2=181.25)
    response = client.post(f"/projects/{project_id}/design/demo")
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "FOOTPRINT_DOES_NOT_FIT_BUILDABLE_REGION"


# ---------------------------------------------------------------------- the street is y=0, always

@pytest.mark.parametrize("street", ["NORTH", "EAST", "SOUTH", "WEST"])
def test_the_front_setback_is_at_the_street_for_every_frontage(client, street):
    """The engine draws every parcel street-at-top (y=0): bays, walk and front door all sit there,
    and the drawing carries no compass. `near_setback_m` used to hand SOUTH/WEST parcels the REAR
    setback at that edge, so the house stood 4.0 m from the street instead of 5.5 m with the front
    yard at the back — and, before `front_band_m`, the 5 m bays 1 m inside the house."""
    w, d = FOOTPRINT
    plot = (26.0, 20.0) if street in ("EAST", "WEST") else (20.0, 26.0)  # same parcel, rotated
    response = client.post("/projects", json={
        "city": "מודיעין-מכבים-רעות", "street": "עמק זבולון",
        "plot_area_m2": 520.0, "built_area_m2": round(w * d, 2),
        "plot_width_m": plot[0], "plot_depth_m": plot[1],
        "street_facing_side": street,
        "setbacks": {"front_m": 5.5, "side_m": 3.0, "rear_m": 4.0},
        "description": BRIEF_3BR_SAFE_OPEN,
        "selected_footprint": {"source": "PRESET", "shape_type": "RECTANGLE",
                               "target_area_m2": round(w * d, 2), "area_m2": round(w * d, 2),
                               "width_m": w, "depth_m": d},
    })
    assert response.status_code == 201, response.text
    project_id = response.json()["project_id"]
    client.post(f"/projects/{project_id}/requirements")
    plan = client.post(f"/projects/{project_id}/design/demo").json()["plan"]

    fp = plan["footprint"]
    assert fp["y"] == pytest.approx(5.5), f"{street}: house is {fp['y']} m from the street, not 5.5"
    assert fp["y"] + fp["depth_m"] <= 26.0 - 4.0 + 1e-9, f"{street}: house enters the rear setback"
    for bay in plan["parking"]:
        assert bay["y"] == 0.0
        assert _overlap(bay, fp) == 0.0, f"{street}: bay {bay} inside the house"
    assert plan["entrance_walk"]["depth_m"] == pytest.approx(5.5)
    assert plan["validation"]["checks"]["C18"] is True
