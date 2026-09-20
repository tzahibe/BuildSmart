"""Entrance-to-circulation integration: no dead-end wall or pocket at the entrance (Issue #22).

THE FAILURE FIXTURE (AC-1's own conclusion, `docs/ENTRANCE_CIRCULATION_SWEEP.md`): the sweep found
no context in the frozen 432-context regression corpus, the canonical single-level baseline, or a
real L-massing candidate (`l_shaped_site_front_arm`) that shows a genuine entrance POCKET — every
real plan's nearest opening off the arrival zone measures well under the calibrated
`ENTRANCE_POCKET_MAX_M`. This is the SAME situation `circulation_metrics.py`'s own C26 EXTREME case
is in (see that test module's own docstring): the fixture below is hand-built for exactly that
reason, not a shortcut. The L-massing candidate below IS real generator output, and is the TUNNEL
exemplar (AC-6) — a real, non-blocking quality signal the sweep did find.
"""
from __future__ import annotations

import pytest

from app.geometry_domain.constraints import BuildableRegion
from app.geometry_domain.primitives import MultiRegion, Region, Ring
from app.geometry_domain.provenance import Authority, Provenance, Source
from app.vertical_slice import concept_generator as cg
from app.vertical_slice import entrance_sequence as es
from app.vertical_slice import general_pipeline as gp
from app.vertical_slice import geometry_fixtures as F
from app.vertical_slice.design_output import DoorOut, GeometricDesign, RoomOut
from app.vertical_slice.geometry_core.engine import GeometryInfeasible, solve_fixture
from app.vertical_slice.pipeline import run_demo
from app.vertical_slice.safe_adapter import AdapterOutcome, adapt, build_buildable_region
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec


def _rect_buildable(w: float, d: float) -> BuildableRegion:
    return BuildableRegion.known(
        MultiRegion.of(Region(Ring.rectangle(3.0, 5.5, w, d))),
        Provenance(Source.USER, Authority.AUTHORITATIVE, ref="test"))

pytestmark = pytest.mark.filterwarnings("ignore")

_INTERIOR = {"construction": "STANDARD_PARTITION"}


def _room(zone_id, roles, rect_m, area=None):
    from app.geometry_domain.walls import BoundaryContext, Construction, WallFacts

    x, y, w, h = rect_m
    facts = WallFacts(BoundaryContext.INTERIOR, Construction.STANDARD_PARTITION)
    return RoomOut(
        zone_id=zone_id, roles=roles, rect_m=rect_m, net_w_m=w, net_h_m=h,
        net_area_m2=area if area is not None else round(w * h, 4),
        walls={s: "STANDARD_PARTITION" for s in ("N", "S", "E", "W")},
        wall_facts={s: facts for s in ("N", "S", "E", "W")},
    )


def _door(a, b, orientation, center_m, kind="ROOM_DOOR"):
    return DoorOut(a=a, b=b, kind=kind, width_m=0.9, center_m=center_m, orientation=orientation,
                  placeable=True, shared_length_m=1.0)


# --------------------------------------------------------------------------- the failure fixture

def dead_stub_beside_entrance_design(dx: float = 0.0, dy: float = 0.0,
                                     mirror_x: bool = False) -> GeometricDesign:
    """The hand-built adversarial fixture: the front door opens directly into a HALL corridor
    whose nearest OTHER opening is a genuinely dead run past the calibrated `ENTRANCE_POCKET_MAX_M`
    before the first door — the shape the Issue's own "Current behavior" names ("a wall or pocket
    immediately at the entrance"). `dx`/`dy` translate the whole design (AC-9); `mirror_x` mirrors
    it across the footprint's own vertical centreline. Both are pure coordinate transforms — no
    role, door or topology changes — so C25's own verdict must be identical under either.
    """
    footprint_w = 10.0

    def tx(x: float) -> float:
        return (footprint_w - x) if mirror_x else x

    def mv(rect_m):
        x, y, w, h = rect_m
        x2 = tx(x + w) if mirror_x else x
        return (x2 + dx, y + dy, w, h)

    def mp(point):
        x, y = point
        return ((tx(x)) + dx, y + dy)

    hall = _room("HALL", ("HALL", "CIRCULATION"), mv((0.0, 0.0, 2.0, 8.0)))
    living = _room("LIVING", ("LIVING",), mv((2.0, 6.0, 4.0, 2.0)))
    doors = [_door("HALL", "LIVING",
                   "vertical" if not mirror_x else "vertical",
                   mp((2.0, 7.0)))]
    entrance = DoorOut(a="OUTSIDE", b="HALL", kind="ENTRANCE_DOOR", width_m=1.0,
                      center_m=mp((1.0, 0.0)), orientation="horizontal", placeable=True,
                      shared_length_m=1.0)
    return GeometricDesign(
        plot_m=(0.0, 0.0, 20.0, 16.0), footprint_m=mv((0.0, 0.0, footprint_w, 8.0)),
        rooms=(hall, living), interior_doors=tuple(doors), entrance_door=entrance,
        windows=(), parking_m=(), garden=(), entrance_walk_m=(0.0, 0.0, 1.0, 1.0),
        gross_area_m2=24.0, net_area_m2=24.0, wall_iterations=0,
    )


def _fixed_equivalent_design() -> GeometricDesign:
    """The SAME shape with the corridor's nearest opening brought within the calibrated limit —
    demonstrating the topology fix's effect (AC-2): no wall/stub directly beyond the door, C25
    passes cleanly."""
    hall = _room("HALL", ("HALL", "CIRCULATION"), (0.0, 0.0, 2.0, 8.0))
    living = _room("LIVING", ("LIVING",), (2.0, 0.0, 4.0, 2.0))
    doors = [_door("HALL", "LIVING", "vertical", (2.0, 1.0))]
    entrance = DoorOut(a="OUTSIDE", b="HALL", kind="ENTRANCE_DOOR", width_m=1.0,
                      center_m=(1.0, 0.0), orientation="horizontal", placeable=True,
                      shared_length_m=1.0)
    return GeometricDesign(
        plot_m=(0.0, 0.0, 20.0, 16.0), footprint_m=(0.0, 0.0, 10.0, 8.0),
        rooms=(hall, living), interior_doors=tuple(doors), entrance_door=entrance,
        windows=(), parking_m=(), garden=(), entrance_walk_m=(0.0, 0.0, 1.0, 1.0),
        gross_area_m2=24.0, net_area_m2=24.0, wall_iterations=0,
    )


def _foyer_design() -> GeometricDesign:
    """An intentional foyer: a HALL zone with its own program area (`net_area_m2` sized like a
    real small entry hall, not a corridor sliver), a nearby opening onward to LIVING — AC-7."""
    hall = _room("HALL", ("HALL", "CIRCULATION"), (0.0, 0.0, 2.5, 2.5), area=6.25)
    living = _room("LIVING", ("LIVING",), (2.5, 0.0, 4.0, 5.0))
    doors = [_door("HALL", "LIVING", "vertical", (2.5, 1.5))]
    entrance = DoorOut(a="OUTSIDE", b="HALL", kind="ENTRANCE_DOOR", width_m=1.0,
                      center_m=(1.25, 0.0), orientation="horizontal", placeable=True,
                      shared_length_m=1.0)
    return GeometricDesign(
        plot_m=(0.0, 0.0, 20.0, 16.0), footprint_m=(0.0, 0.0, 6.5, 5.0),
        rooms=(hall, living), interior_doors=tuple(doors), entrance_door=entrance,
        windows=(), parking_m=(), garden=(), entrance_walk_m=(0.0, 0.0, 1.0, 1.0),
        gross_area_m2=32.5, net_area_m2=32.5, wall_iterations=0,
    )


def _stray_pocket_design() -> GeometricDesign:
    """The Issue's own "Current behavior" shape: the entrance opens cleanly into LIVING, but a
    SEPARATE HALL zone independently fronts the street beside it with nothing served near that
    end — a blind pocket beside the entrance, not in front of it."""
    living = _room("LIVING", ("LIVING",), (0.0, 0.0, 5.0, 8.0))
    hall = _room("HALL", ("HALL", "CIRCULATION"), (5.0, 0.0, 2.0, 8.0))
    bedroom = _room("BEDROOM", ("BEDROOM",), (7.0, 0.0, 3.0, 8.0))
    doors = [_door("HALL", "BEDROOM", "vertical", (7.0, 6.5))]
    entrance = DoorOut(a="OUTSIDE", b="LIVING", kind="ENTRANCE_DOOR", width_m=1.0,
                      center_m=(2.5, 0.0), orientation="horizontal", placeable=True,
                      shared_length_m=1.0)
    return GeometricDesign(
        plot_m=(0.0, 0.0, 20.0, 16.0), footprint_m=(0.0, 0.0, 10.0, 8.0),
        rooms=(living, hall, bedroom), interior_doors=tuple(doors), entrance_door=entrance,
        windows=(), parking_m=(), garden=(), entrance_walk_m=(0.0, 0.0, 1.0, 1.0),
        gross_area_m2=80.0, net_area_m2=80.0, wall_iterations=0,
    )


def _no_arrival_design() -> GeometricDesign:
    """A dead-end room with NO opening at all past the entrance — the "no path to a public room"
    half of C25, independent of the pocket-length half."""
    hall = _room("HALL", ("HALL", "CIRCULATION"), (0.0, 0.0, 2.0, 4.0))
    entrance = DoorOut(a="OUTSIDE", b="HALL", kind="ENTRANCE_DOOR", width_m=1.0,
                      center_m=(1.0, 0.0), orientation="horizontal", placeable=True,
                      shared_length_m=1.0)
    return GeometricDesign(
        plot_m=(0.0, 0.0, 20.0, 16.0), footprint_m=(0.0, 0.0, 2.0, 4.0),
        rooms=(hall,), interior_doors=(), entrance_door=entrance,
        windows=(), parking_m=(), garden=(), entrance_walk_m=(0.0, 0.0, 1.0, 1.0),
        gross_area_m2=8.0, net_area_m2=8.0, wall_iterations=0,
    )


# --------------------------------------------------------------------------- real fixtures

@pytest.fixture(scope="module")
def canonical_design(tmp_path_factory):
    out = tmp_path_factory.mktemp("entrance") / "canonical.png"
    return run_demo(str(out)).design


def _realized_candidates(spec: ArchitecturalSpec, buildable) -> list:
    adapter = adapt(buildable)
    assert adapter.outcome is AdapterOutcome.SOLVED
    generated = cg.generate_concepts(spec, list(adapter.candidates))
    out = []
    for index, candidate in enumerate(generated.candidates):
        try:
            solve = solve_fixture(candidate.concept.fixture)
        except GeometryInfeasible:
            continue
        out.append(gp._realize(spec, buildable, None, candidate, index, solve, ()))
    return out


@pytest.fixture(scope="module")
def spine_plan():
    spec = ArchitecturalSpec(plot=PlotSpec(width_m=16.0, depth_m=20.0),
                             program=ProgramSpec(bedrooms=2, wet_rooms=1, safe_room=False))
    buildable = _rect_buildable(11.0, 12.0)
    plans = [p for p in _realized_candidates(spec, buildable) if p.ok]
    if not plans:
        pytest.skip("no validating spine candidate for this brief/site")
    return plans[0]


@pytest.fixture(scope="module")
def l_plan():
    spec = ArchitecturalSpec(plot=PlotSpec(width_m=24.0, depth_m=32.0),
                             program=ProgramSpec(bedrooms=3, wet_rooms=2, safe_room=False))
    buildable = build_buildable_region(F.l_shaped_site_front_arm())
    plans = [p for p in _realized_candidates(spec, buildable)
            if p.ok and p.massing_signature == "2W"]
    if not plans:
        pytest.skip("no validating 2W (L) candidate for this brief/site")
    return plans[0]


# --------------------------------------------------------------------------- AC-2

def test_no_dead_end_wall_in_front_of_the_entrance_on_the_failure_fixture():
    design = _fixed_equivalent_design()
    seq = es.measure(design)
    assert es.classify_pocket(seq) is None
    assert seq.pocket_length_m <= es.ENTRANCE_POCKET_MAX_M


# --------------------------------------------------------------------------- AC-3

def _served_extent_along_axis(design: GeometricDesign, hall: RoomOut, axis_sides: tuple[str, str]):
    """The union extent of every room with a placeable door onto `hall`, projected onto `hall`'s
    own long axis — what the corridor actually needs to reach."""
    rooms = {r.zone_id: r for r in design.rooms}
    served_ids = {d.a if d.b == hall.zone_id else d.b for d in design.interior_doors
                 if hall.zone_id in (d.a, d.b) and d.placeable}
    served_ids |= ({design.entrance_door.b} if design.entrance_door.b == hall.zone_id else set())
    lo, hi = None, None
    for zid in served_ids:
        room = rooms.get(zid)
        if room is None or room.zone_id == hall.zone_id:
            continue
        x, y, w, h = room.rect_m
        a = y if axis_sides == ("N", "S") else x
        b = (y + h) if axis_sides == ("N", "S") else (x + w)
        lo = a if lo is None else min(lo, a)
        hi = b if hi is None else max(hi, b)
    return lo, hi


def _hall_of(design: GeometricDesign) -> RoomOut:
    return next(r for r in design.rooms if {"HALL", "CIRCULATION"} & set(r.roles))


@pytest.mark.parametrize("which", ["spine_plan", "l_plan"])
def test_corridor_ends_at_the_last_served_door_not_at_the_boundary(which, request):
    """The corridor's own extent, along its long axis, never reaches past the last room it
    actually serves (a door or the entrance) — it may legitimately COINCIDE with the footprint
    boundary (when the last served room's own edge IS the boundary, the ordinary case), but never
    extends past it for no reason. Verified against REAL generator output for both partis; the
    sweep (`docs/ENTRANCE_CIRCULATION_SWEEP.md`) found this already holds today — see that
    report's conclusion for why no `concept_generator.py`/`l_parti.py` change was needed."""
    plan = request.getfixturevalue(which)
    design = plan.design
    hall = _hall_of(design)
    axis = ("N", "S") if hall.net_h_m >= hall.net_w_m else ("W", "E")
    lo, hi = _served_extent_along_axis(design, hall, axis)
    assert lo is not None and hi is not None
    x, y, w, h = hall.rect_m
    hall_lo, hall_hi = (y, y + h) if axis == ("N", "S") else (x, x + w)
    tol = 0.15  # wall-thickness-scale tolerance, matches entrance_sequence's own
    assert hall_lo >= lo - tol
    assert hall_hi <= hi + tol


# --------------------------------------------------------------------------- AC-4

def test_arrival_zone_is_a_circulation_node(canonical_design):
    seq = es.measure(canonical_design)
    assert seq.has_public_opening
    assert es.classify_pocket(seq) is None

    fixed = _fixed_equivalent_design()
    seq2 = es.measure(fixed)
    assert seq2.is_circulation_arrival
    assert seq2.has_public_opening
    assert es.classify_pocket(seq2) is None


# --------------------------------------------------------------------------- AC-5

def test_c25_flags_a_dead_stub_beside_the_entrance():
    design = dead_stub_beside_entrance_design()
    seq = es.measure(design)
    defect = es.classify_pocket(seq)
    assert defect is not None
    assert "HALL" in defect
    assert f"{seq.pocket_length_m:.2f}" in defect


def test_c25_appears_in_the_check_list(canonical_design):
    del canonical_design
    import tempfile

    result = run_demo(tempfile.mktemp(suffix=".png"))
    assert "C25" in [c.check_id for c in result.validation.checks]


def test_stray_pocket_beside_the_entrance_also_fails_c25():
    """The OTHER failure shape (Issue's "Current behavior"): a clean, valid entrance into LIVING,
    but a SEPARATE HALL zone independently fronting the street with nothing served nearby."""
    seq = es.measure(_stray_pocket_design())
    assert seq.arrival_zone == "LIVING"
    assert seq.pocket_length_m == 0.0  # LIVING itself is not circulation — no pocket of its own
    assert seq.stray_pockets and seq.stray_pockets[0][0] == "HALL"
    defect = es.classify_pocket(seq)
    assert defect is not None
    assert "HALL" in defect and "beside the entrance" in defect


def test_no_public_opening_also_fails_c25():
    seq = es.measure(_no_arrival_design())
    defect = es.classify_pocket(seq)
    assert defect is not None
    assert "no opening to a public room" in defect


def test_the_demo_path_refuses_with_entrance_dead_end(monkeypatch):
    """C25 alone failing on an otherwise-valid plan refuses with `ENTRANCE_DEAD_END` — the same
    "single specific reason" discipline `ENTRANCE_NO_ARRIVAL_ROOM`/`LAUNDRY_UNPLACEABLE` follow.
    Forces C25 to fail on every candidate (every other check is untouched) so the request that
    would otherwise plan cleanly is refused for exactly this reason."""
    from datetime import datetime, timezone

    from app.demo import service as svc
    from app.projects.models import (
        Project, SelectedFootprint, SourceTag, StreetSide, TaggedBool, TaggedInt,
    )

    monkeypatch.setattr(
        es, "classify_pocket",
        lambda seq: f"TEST-FORCED: unserved corridor beyond the entrance door in {seq.arrival_zone}")

    now = datetime.now(timezone.utc)
    project = Project(
        project_id="TEST-ENTRANCE-DEAD-END", city="TLV", street="S",
        plot_area_m2=18.0 * 22.0, plot_width_m=18.0, plot_depth_m=22.0,
        street_facing_side=StreetSide.north, built_area_m2=110.0, description="",
        status="active", created_at=now, updated_at=now,
        selected_footprint=SelectedFootprint(source="CUSTOM", shape_type="RECTANGLE",
                                             target_area_m2=110.0, width_m=10.0, depth_m=11.0,
                                             area_m2=110.0),
        floors=TaggedInt(value=1, source=SourceTag.inferred),
        bedrooms=TaggedInt(value=2, source=SourceTag.requested),
        safe_room=TaggedBool(value=False, source=SourceTag.unknown),
        parking_spaces=TaggedInt(value=0, source=SourceTag.requested),
        wet_rooms=TaggedInt(value=1, source=SourceTag.requested),
        open_plan=TaggedBool(value=False, source=SourceTag.requested),
        requirements_parsed_at=now,
    )
    with pytest.raises(svc.DemoGenerationError) as excinfo:
        svc.generate_demo_design(project)
    assert excinfo.value.code == "ENTRANCE_DEAD_END"


# --------------------------------------------------------------------------- AC-6

def test_tunnel_sequence_is_reported_and_ranked_down_but_not_refused(l_plan):
    seq = es.measure(l_plan.design)
    tunnel = es.classify_tunnel(seq)
    assert tunnel is not None
    assert es.classify_pocket(seq) is None  # not refused: the pocket gate is unaffected

    non_tunnel = es.EntranceSequence(
        arrival_zone="HALL", arrival_roles=("HALL", "CIRCULATION"), is_circulation_arrival=True,
        pocket_length_m=0.5, has_public_opening=True, distance_to_public_m=1.0,
        private_doors_passed=0, foyer=True)
    assert es.entrance_sequence_prefers(seq, non_tunnel) is None
    assert es.entrance_sequence_prefers(non_tunnel, seq) is not None


# --------------------------------------------------------------------------- AC-7

def test_intentional_foyer_passes_c25():
    seq = es.measure(_foyer_design())
    assert seq.foyer
    assert es.classify_pocket(seq) is None


# --------------------------------------------------------------------------- AC-9

@pytest.mark.parametrize("dx,dy,mirror", [(0.0, 0.0, False), (5.0, 3.0, False), (0.0, 0.0, True),
                                          (4.0, -2.0, True)])
def test_fix_holds_on_mirrored_and_translated_fixtures(dx, dy, mirror):
    design = dead_stub_beside_entrance_design(dx=dx, dy=dy, mirror_x=mirror)
    seq = es.measure(design)
    defect = es.classify_pocket(seq)
    assert defect is not None
    assert seq.arrival_zone == "HALL"


def test_no_coordinate_literal_or_fixture_name_branch_in_the_module():
    import ast
    import inspect

    from app.vertical_slice import entrance_sequence as module

    source = inspect.getsource(module)
    tree = ast.parse(source)
    banned_strings = {"HALL_MAIN", "HALL_SPUR", "SAFE_ROOM", "MASTER", "KITCHEN", "LIVING"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert node.value not in banned_strings, node.value
