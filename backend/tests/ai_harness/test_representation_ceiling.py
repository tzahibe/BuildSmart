"""R1 (#242) — the representation-ceiling harness: what was frozen, how a plan is converted, and
that the realizer entry it drives is the product's own (`realize_cells`) plus groups, nothing else.

Nothing here asserts a RESULT of the experiment except `test_the_committed_results_are_consistent`,
which holds the committed data file to the frozen verdict function.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from shapely.ops import unary_union

from app.ai_harness.representation_ceiling import frozen
from app.ai_harness.representation_ceiling.convert import (
    ConvertedPlan,
    Layout,
    ReprRefusal,
    build_layout,
    convert,
    rotate,
)
from app.ai_harness.representation_ceiling.realize import realize
from app.vertical_slice.geometry_core.model import ProgramRole as R
from app.vertical_slice.geometry_core.model import Rect, m_to_u
from app.vertical_slice.rectilinear_realizer import RealizedLayout, realize_cells
from app.vertical_slice.spec import WetRoomKind, WetRoomStrength
from app.vertical_slice.wet_rooms import ResolvedWetRoom

REPO = Path(__file__).resolve().parents[3]
REPORT_DIR = REPO / "docs" / "reports" / "architectural-intelligence"


# --------------------------------------------------------------------------- AC-2: the fixtures

def test_the_synthetic_fixture_is_excluded_by_name_and_19_real_plans_remain():
    plans = frozen.load_real_plans()
    assert len(plans) == 19
    assert "synthetic-spine-01" not in plans
    on_disk = sorted(p.stem for p in frozen.PLANS_DIR.glob("*.json"))
    assert len(on_disk) == 20 and set(on_disk) - set(plans) == {"synthetic-spine-01"}
    assert all(p["provenance"]["source_dataset"] == "ResPlan" for p in plans.values())


def test_the_role_map_covers_every_label_in_the_real_plans():
    labels = {r["type"] for p in frozen.load_real_plans().values() for r in p["rooms"]}
    assert labels <= set(frozen.ROLE_MAP), labels - set(frozen.ROLE_MAP)
    assert frozen.ROLE_MAP["CIRCULATION"] is R.HALL
    for role in frozen.ROLE_MAP.values():
        frozen.zone_intent("Z", role)            # every mapped role has a product template row


# --------------------------------------------------------------------------- AC-5: the thresholds

@pytest.mark.parametrize("c1,c2,fails,expected", [
    (0, 13, {}, "GO"),
    (7, 13, {}, "GO"),
    (8, 13, {}, "PIVOT"),                          # >= 13 but gains 5: GO not met, classified PIVOT
    (0, 19, {}, "GO"),
    (0, 12, {}, "PIVOT"),
    (0, 7, {}, "PIVOT"),
    (0, 6, {}, "STOP"),
    (0, 0, {}, "STOP"),
    (0, 13, {"C27": 10, "C9": 10, "C14": 10}, "STOP"),   # 3 of the 4 on more than half beats GO
    (0, 13, {"C27": 10, "C9": 10, "C14": 9}, "GO"),      # exactly half is not "more than half"
    (0, 9, {"C27": 10, "C9": 10, "C30": 11, "C14": 1}, "STOP"),
])
def test_the_verdict_applies_the_frozen_thresholds(c1, c2, fails, expected):
    assert frozen.verdict(c1, c2, fails)[0] == expected


# --------------------------------------------------------------------------- the conversion

def _converted() -> dict[str, ConvertedPlan | ReprRefusal]:
    return {pid: convert(pid, ref) for pid, ref in frozen.load_real_plans().items()}


def test_every_real_plan_converts_to_a_rectilinear_tiling():
    for pid, c in _converted().items():
        assert isinstance(c, ConvertedPlan), (pid, c)
        polys = list(c.rooms.values())
        for i, a in enumerate(polys):
            assert a.is_valid and a.geom_type == "Polygon"
            for b in polys[i + 1:]:
                assert a.intersection(b).area < 1e-6, pid
        assert set(c.roles) == set(c.rooms)
        assert all(a in c.rooms and b in c.rooms for a, b in c.access)
        n_bed = sum(1 for r in c.roles.values() if r in (R.BEDROOM, R.MASTER_BEDROOM))
        assert sum(1 for r in c.roles.values() if r is R.MASTER_BEDROOM) == (1 if n_bed >= 2 else 0), pid


@pytest.mark.parametrize("arm", [frozen.ARM_1, frozen.ARM_2, frozen.ARM_2R])
def test_cells_tile_the_rooms_and_sit_inside_wings(arm):
    for pid, c in _converted().items():
        for deg in frozen.ROTATIONS_DEG:
            rooms = rotate(c.rooms, deg)
            lay = build_layout(c, rooms, arm)
            assert isinstance(lay, Layout), (pid, deg, lay)
            cells = lay.cells
            for cid, r in cells.items():
                assert any(w.x <= r.x and w.y <= r.y and r.x2 <= w.x2 and r.y2 <= w.y2 for w in lay.wings), (pid, cid)
            rs = list(cells.values())
            for i, a in enumerate(rs):
                for b in rs[i + 1:]:
                    assert a.overlap_area_u(b) == 0, (pid, deg, arm)
            area_u = sum(r.w * r.h for r in rs)
            if arm == frozen.ARM_1:
                assert len(cells) == len(rooms) and not lay.groups
                assert area_u <= sum(p.area for p in rooms.values()) / 0.05 ** 2 + 1
            else:
                # the cells of every room rebuild it exactly, so the union is the footprint
                total = sum(p.area for p in rooms.values()) / 0.05 ** 2
                assert abs(area_u - total) < 2, (pid, deg, arm, area_u, total)
                for z, ids in lay.groups.items():
                    assert len(ids) > 1 and all(lay.zone_of_cell[i] == z for i in ids)
                wing_u = sum(w.w * w.h for w in lay.wings)
                assert abs(wing_u - total) < 2, (pid, deg, arm)
    # rotation is a rigid motion
    c = next(iter(_converted().values()))
    base = sum(p.area for p in c.rooms.values())
    for deg in frozen.ROTATIONS_DEG:
        assert abs(sum(p.area for p in rotate(c.rooms, deg).values()) - base) < 1e-6


def test_wet_room_kinds_are_read_off_the_plans_own_doors():
    c = convert("0", frozen.load_real_plans()["0"])
    assert isinstance(c, ConvertedPlan)
    # plan 0: BATHROOM_1 opens only to BEDROOM_0 and BATHROOM_2 only to BEDROOM_2 (ensuites);
    # BATHROOM_0 opens to the living room (shared)
    assert c.wet["BATHROOM_1"] == (WetRoomKind.ENSUITE, "BEDROOM_0")
    assert c.wet["BATHROOM_2"] == (WetRoomKind.ENSUITE, "BEDROOM_2")
    assert c.wet["BATHROOM_0"] == (WetRoomKind.SHARED_BATHROOM, None)
    assert set(c.dropped) == {"LIVING_1", "LIVING_2"}          # 0.27 and 0.13 m2 segmentation artefacts


# --------------------------------------------------------------------------- the realizer entry

def _rect(x0, y0, x1, y1):
    return Rect(m_to_u(x0), m_to_u(y0), m_to_u(x1) - m_to_u(x0), m_to_u(y1) - m_to_u(y0))


_ROLES = {"LIVING": R.LIVING, "KITCHEN": R.KITCHEN, "HALL": R.HALL, "BED1": R.MASTER_BEDROOM,
          "BED2": R.BEDROOM, "BATH": R.BATHROOM}
_ACCESS = [("LIVING", "KITCHEN"), ("LIVING", "HALL"), ("HALL", "BED1"), ("HALL", "BED2"), ("HALL", "BATH")]
_WET = {"BATH": (WetRoomKind.SHARED_BATHROOM, None)}


def _house(bed2_right: float, bath_left: float) -> dict[str, Rect]:
    return {"LIVING": _rect(0, 0, 6, 4.5), "KITCHEN": _rect(6, 0, 10, 4.5), "HALL": _rect(0, 4.5, 10, 6.0),
            "BED1": _rect(0, 6.0, 4, 10), "BED2": _rect(4, 6.0, bed2_right, 10),
            "BATH": _rect(bath_left, 6.0, 10, 10)}


@pytest.mark.parametrize("bed2_right,bath_left,carried", [(8.0, 8.0, True), (9.0, 9.0, False)])
def test_wrapper_agrees_with_realize_cells_when_there_are_no_groups(bed2_right, bath_left, carried):
    cells = _house(bed2_right, bath_left)
    wings = (_rect(0, 0, 10, 10),)
    intents = {z: frozen.zone_intent(z, r) for z, r in _ROLES.items()}
    mine = realize("t", Layout(cells, wings, {z: z for z in cells}, {}, dict(_ROLES), _ACCESS, _WET), intents)
    wet = tuple(ResolvedWetRoom(z, k, h, WetRoomStrength.REQUIRED, True) for z, (k, h) in _WET.items())
    ref = realize_cells("t", cells, intents, wings, _ACCESS, wet_rooms=wet)
    assert mine.carried is carried and isinstance(ref, RealizedLayout) is carried
    if not carried:
        # `realize_cells` reports the first five failing checks as text; the wrapper reports them all
        first_five = set(re.findall(r"(C\d+)(?=:)", ref.detail))
        assert first_five and first_five <= set(mine.failing)
        assert set(mine.failing) >= {"C3", "C20", "C21"}


def test_a_room_of_two_cells_is_validated_on_its_union_through_the_group_checks():
    # the living room is an L: one cell 6 x 4.5 plus one 2 x 1.5 below its east end, in a house
    # whose hall is shortened to leave room for it
    cells = {"LIVING__c0": _rect(0, 0, 6, 4.5), "LIVING__c1": _rect(4, 4.5, 6, 6.0),
             "KITCHEN": _rect(6, 0, 10, 4.5), "HALL": _rect(0, 4.5, 4, 6.0),
             "BED1": _rect(0, 6.0, 4, 10), "BED2": _rect(4, 6.0, 8, 10), "BATH": _rect(8, 6.0, 10, 10),
             "PASS": _rect(6, 4.5, 10, 6.0)}
    zone_of = {c: c.split("__")[0] for c in cells}
    roles = dict(_ROLES, PASS=R.HALL)
    intents = {z: frozen.zone_intent(z, r) for z, r in roles.items()}
    out = realize("t", Layout(cells, (_rect(0, 0, 10, 10),), zone_of, {"LIVING": ("LIVING__c0", "LIVING__c1")},
                              roles, _ACCESS + [("LIVING", "PASS")], _WET), intents)
    assert out.code in (None, "VALIDATION_FAILED") and out.n_checks > 28        # the GROUP-C2/C3/C20 ran
    assert all(":" not in c for c in out.failing)                                # zone suffix stripped


# --------------------------------------------------------------------------- AC-6 / AC-7

def test_nothing_outside_the_harness_directory_imports_it():
    here = REPO / "backend" / "app"
    own = here / "ai_harness" / "representation_ceiling"
    offenders = [str(p.relative_to(REPO)) for p in here.rglob("*.py")
                 if own not in p.parents and "representation_ceiling" in p.read_text()]
    assert offenders == []


def test_the_harness_modifies_no_validator_or_production_module():
    # it only imports them; it defines no check and rebinds no name in them
    for p in (Path(__file__).resolve().parents[2] / "app" / "ai_harness" / "representation_ceiling").glob("*.py"):
        text = p.read_text()
        assert not re.search(r"^\s*(validation|rectilinear_realizer|doors|windows|furniture)\.\w+\s*=", text, re.M), p.name
        assert "monkeypatch" not in text and "setattr(" not in text, p.name


def test_the_committed_results_are_consistent():
    path = REPORT_DIR / "data" / "R1-results.json"
    if not path.exists():
        pytest.skip("the experiment has not been run yet")
    data = json.loads(path.read_text())
    plans = data["plans"]
    assert len(plans) == 19 and "synthetic-spine-01" not in plans
    for arm in (frozen.ARM_1, frozen.ARM_2, frozen.ARM_2R):
        assert data["aggregate"][arm]["carried"] == sum(1 for p in plans.values() if p["arms"][arm]["carried"])
    for p in plans.values():
        for a in p["arms"].values():
            assert a["carried"] or a["failing"], "a refusal must name its failing check"
    word, _ = frozen.verdict(data["arm1_carried"], data["arm2_carried"],
                             data["aggregate"][frozen.ARM_2]["plans_failing_check"])
    assert data["verdict"] == word
