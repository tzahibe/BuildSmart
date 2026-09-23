"""Two guards that must hold for the whole general-geometry migration.

1. THE FROZEN NUMERIC BASELINE (task §0). Not "the tests still pass" — the exact numbers. Any
   refactor that moves one of these has changed behaviour and must do so deliberately.
2. RENDERER DECOUPLING (task §9). Enforced by reading the module source, not by convention,
   because the renderer must never need to know which engine produced a design.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from app.geometry_domain.walls import BoundaryContext, Construction
from app.vertical_slice.pipeline import run_demo

#: The canonical First Vertical Slice result. Frozen.
BASELINE_GROSS_M2 = 170.4
BASELINE_NET_M2 = 153.83
BASELINE_WALL_ITERATIONS = 2
BASELINE_ROOM_COUNT = 11
BASELINE_INTERIOR_DOORS = 7
#: Deliberately moved from 7: ROOM_AREA_CAPS_AND_WET_ROOM_WINDOW_REPORT added a best-effort,
#: non-required window attempt for wet rooms (BATHROOM) on top of the pre-existing
#: DAYLIGHT_ROLES set — this baseline's 2 bathrooms both land on a real exterior wall.
BASELINE_WINDOWS = 9
BASELINE_CHECK_COUNT = 27  # C13 realized connectivity; C16 the entrance's own realization; C17 bathroom access; C18 parking clear of the house; C19 required rooms touch an exterior wall; C20 template aspect; C21 template maximum area; C23 entrance opens into an allowed arrival room; C24 access topology obeys the door rules; C25 (Issue #22) no dead-space pocket at the entrance — additive; C26 no extreme dedicated circulation; C28 doors usable; C29 (Issue #37) wet-room privacy — additive, runs on every plan with wet rooms; C31 (Issue #41) public-zone composition — additive; C33 (Issue #45) the wall semantic model — additive, runs on every plan
#: Between Phase 1 of the room-size work (hard maxima at the template values, 2026-09-15) and the
#: two-level model the frozen slice failed C21: its hand-authored 5.7 m rooms column realizes two
#: bedrooms at 15.40 m2 against the 14 m2 maximum. Under the two-level model 14 is the PREFERRED
#: maximum and the gate is the HARD one (18), so the slice validates in full again — with the
#: two bedrooms reported above preferred by the demo contract, not refused.
FROZEN_SLICE_FAILS_C21: list[str] = []


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    out = tmp_path_factory.mktemp("baseline") / "house.png"
    return run_demo(str(out))


def test_canonical_numeric_baseline_is_unchanged(result):
    d = result.design
    assert d.gross_area_m2 == pytest.approx(BASELINE_GROSS_M2)
    assert d.net_area_m2 == pytest.approx(BASELINE_NET_M2)
    assert d.wall_iterations == BASELINE_WALL_ITERATIONS


def test_canonical_element_counts_are_unchanged(result):
    d = result.design
    assert len(d.rooms) == BASELINE_ROOM_COUNT
    assert len(d.interior_doors) == BASELINE_INTERIOR_DOORS
    assert len(d.windows) == BASELINE_WINDOWS
    assert len(result.validation.checks) == BASELINE_CHECK_COUNT
    assert [c.check_id for c in result.validation.failures()] == FROZEN_SLICE_FAILS_C21


def test_every_room_area_is_unchanged(result):
    """Per-room, not just the total — a compensating pair of errors would pass a total check."""
    expected = {
        "LIVING": 21.82, "DINING": 20.25, "KITCHEN": 20.48,
        "HALL_MAIN": 4.95, "HALL_SPUR": 14.84,
        "MASTER": 12.03, "BATH_1": 5.53,
        "BEDROOM_1": 15.40, "SAFE_ROOM": 12.96, "BEDROOM_2": 15.40, "BATH_2": 10.18,
    }
    actual = {r.zone_id: r.net_area_m2 for r in result.design.rooms}
    assert actual.keys() == expected.keys()
    for zone_id, area in expected.items():
        assert actual[zone_id] == pytest.approx(area, abs=0.01), zone_id


# ------------------------------------------------------------------ orthogonal wall facts

def test_safe_room_exterior_wall_reports_both_facts_in_the_contract(result):
    """End-to-end version of the defect: the design output must be able to say EXTERIOR *and*
    RC_SAFE_ROOM about the same wall."""
    safe_room = next(r for r in result.design.rooms if r.zone_id == "SAFE_ROOM")
    east = safe_room.wall_facts["E"]
    assert east.boundary_context is BoundaryContext.EXTERIOR
    assert east.construction is Construction.RC_SAFE_ROOM
    assert east.can_take_a_window
    # The raw solver value still reports only the precedence winner — which is why the
    # orthogonal facts had to be recovered rather than read off it.
    assert safe_room.walls["E"] == "RC_SAFE_ROOM"


def test_safe_room_interior_walls_are_distinguishable_from_its_exterior_one(result):
    safe_room = next(r for r in result.design.rooms if r.zone_id == "SAFE_ROOM")
    assert safe_room.wall_facts["W"].boundary_context is BoundaryContext.INTERIOR
    assert safe_room.wall_facts["W"].construction is Construction.RC_SAFE_ROOM
    assert not safe_room.wall_facts["W"].can_take_a_window


def test_open_plan_boundaries_report_no_construction(result):
    living = next(r for r in result.design.rooms if r.zone_id == "LIVING")
    assert living.wall_facts["S"].construction is Construction.NONE


# ------------------------------------------------------------------ contract is in metres

def test_contract_carries_no_grid_units(result):
    """Every geometric quantity leaving the pipeline is in metres, which is what allows the
    renderer to be engine-agnostic."""
    d = result.design
    assert d.footprint_m == pytest.approx((4.0, 5.5, 12.0, 14.2))
    for door in d.interior_doors:
        assert all(isinstance(v, float) for v in door.center_m)
    for window in d.windows:
        assert all(isinstance(v, float) for v in window.center_m)
    for garden in d.garden:
        assert all(len(r) == 4 for r in garden.rects_m)


# ------------------------------------------------------------------ decoupling

def test_renderer_imports_nothing_from_the_solver_engine():
    source = pathlib.Path("app/vertical_slice/renderer.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    offenders = [m for m in imported if "geometry_core" in m]
    assert not offenders, f"renderer must not import solver internals, found: {offenders}"


def test_geometry_domain_does_not_depend_on_the_solver_or_the_slice():
    """The dependency direction is the architecture: the domain layer must stay ignorant of any
    engine, so the rectangular core remains one realization engine behind an adapter."""
    offenders: list[str] = []
    for path in pathlib.Path("app/geometry_domain").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            for name in names:
                if "geometry_core" in name or "vertical_slice" in name:
                    offenders.append(f"{path.name}: {name}")
    assert not offenders, f"geometry_domain must not import engine code, found: {offenders}"
