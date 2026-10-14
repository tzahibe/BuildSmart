"""Path B (ADR-001, #197): the spine oracle as the sizer — one exact MILP places a hub corridor
spanning several bands with plain street/back bands around it, and the placement realizes through
the UNCHANGED validators with every contact and door, on a rectangle, an L and an entry court."""
import pytest

pytest.importorskip("scipy")

from app.ai_harness.shape_agnostic.milp_oracle import milp_spine_placement, spine_geometry, spine_intents  # noqa: E402
from app.ai_harness.shape_agnostic.spine import embed_spine  # noqa: E402
from app.vertical_slice.band_sizing import contact_requirements  # noqa: E402
from app.vertical_slice.envelope import Envelope  # noqa: E402
from app.vertical_slice.rectilinear_realizer import RealizedLayout, realize_cells  # noqa: E402
from app.vertical_slice.spec import WetRoomKind, WetRoomStrength  # noqa: E402
from app.vertical_slice.topology_preservation import measure_access_graph, measure_spatial_adjacency  # noqa: E402
from app.vertical_slice.wet_rooms import ResolvedWetRoom  # noqa: E402
from tests.vertical_slice.test_spine_embedding import _hub_programme  # noqa: E402
from tests.vertical_slice.test_staircase_sizing import ENTRY_COURT, L_ENVELOPE  # noqa: E402

ACCESS = [("HALL", "LIVING"), ("LIVING", "KITCHEN"), ("HALL", "BED1"), ("HALL", "BED2"), ("HALL", "MASTER"),
          ("HALL", "BATH")]
WET = (ResolvedWetRoom("BATH", WetRoomKind.SHARED_BATHROOM, None, WetRoomStrength.REQUIRED, False),)


def _first_realized(envelope):
    zones, required = _hub_programme()
    union = sorted({tuple(sorted(e)) for e in required} | {tuple(sorted(e)) for e in ACCESS})
    contacts = contact_requirements(zones, union, ACCESS)
    tried = 0
    for layout in embed_spine(zones, union, "HALL"):
        o = milp_spine_placement(layout, zones, required, envelope, min_contact_u=contacts)
        if o.status != "FEASIBLE":
            continue
        tried += 1
        rects, wings = spine_geometry(layout, o)
        out = realize_cells("spine", rects, spine_intents(layout, zones), wings, ACCESS, wet_rooms=WET)
        if isinstance(out, RealizedLayout):
            return layout, o, rects, wings, out, required
    pytest.fail(f"no spine layout realized on {envelope.vertices_m} ({tried} oracle-feasible)")


@pytest.mark.parametrize("envelope", [Envelope.rectangle(14, 12), L_ENVELOPE, ENTRY_COURT])
def test_a_spine_placement_realizes_with_every_contact_and_door(envelope):
    layout, o, rects, wings, out, required = _first_realized(envelope)
    assert out.ok
    for w in wings:
        assert envelope.contains_rect_u(w), w
    sp = measure_spatial_adjacency(out.rects, frozenset(frozenset(e) for e in required))
    ac = measure_access_graph(out.fixture.access.edges, ACCESS)
    assert sp.preserved == sp.requested and ac.preserved == ac.requested
    assert out.entrance_door is not None


def test_the_spine_spans_its_section_and_only_its_section():
    layout, o, rects, wings, out, _ = _first_realized(Envelope.rectangle(14, 12))
    a, b = layout.section
    spine = rects["HALL"]
    assert spine.y == o.y_start_u + sum(o.heights_u[:a])
    assert spine.h == sum(o.heights_u[a:b])
    for zid, r in rects.items():
        if zid == "HALL":
            continue
        row = layout.row_of(zid)
        assert r.y == o.y_start_u + sum(o.heights_u[:row]) and r.h == o.heights_u[row], zid


def test_every_cell_lies_in_exactly_one_wing():
    _, _, rects, wings, _, _ = _first_realized(Envelope.rectangle(14, 12))
    for zid, r in rects.items():
        holders = [w for w in wings if w.x <= r.x and r.x2 <= w.x2 and w.y <= r.y and r.y2 <= w.y2]
        assert len(holders) == 1, (zid, holders)


def test_the_spine_intent_is_declared_as_a_corridor_and_nothing_else_moves():
    zones, required = _hub_programme()
    layout = embed_spine(zones, required, "HALL")[0]
    zi = spine_intents(layout, zones)
    assert zi["HALL"].max_aspect_ratio == 6.0
    assert (zi["HALL"].min_area_m2, zi["HALL"].max_area_m2, zi["HALL"].min_short_side_m) == (9, 24, 1.6)
    assert all(zi[z] is zones[z] for z in zones if z != "HALL")


def test_an_exact_inset_refusal_is_not_replaced_by_the_loose_estimate():
    """The fixed point re-solves with the real wall types; if THAT is infeasible the answer is the
    refusal — the realizer's C3 would refuse the estimate anyway."""
    zones, required = _hub_programme()
    union = sorted({tuple(sorted(e)) for e in required} | {tuple(sorted(e)) for e in ACCESS})
    contacts = contact_requirements(zones, union, ACCESS)
    statuses = set()
    for layout in embed_spine(zones, union, "HALL")[:12]:
        o = milp_spine_placement(layout, zones, required, Envelope.rectangle(14, 12), min_contact_u=contacts)
        statuses.add(o.status)
        if o.status == "FEASIBLE":
            rects, wings = spine_geometry(layout, o)
            out = realize_cells("spine", rects, spine_intents(layout, zones), wings, ACCESS, wet_rooms=WET)
            if not isinstance(out, RealizedLayout):
                assert "C3" not in out.detail, out.detail
    assert statuses


def test_the_entrance_walk_leads_to_the_resolved_door_not_the_footprint_centre():
    """`_build_site` places a placeholder walk at the footprint's centre; the realized site must
    carry the walk to the door `resolve_entrance` chose (the drawing and the payload read it)."""
    _, _, _, _, out, _ = _first_realized(Envelope.rectangle(14, 12))
    arrival = out.rects[out.entrance_door.b]
    x_door, y_door = out.site.entrance.door_point_u
    assert arrival.x <= x_door <= arrival.x2 and y_door == arrival.y, (arrival, out.site.entrance)
    walk = out.site.entrance.path_rect
    assert walk.x <= x_door <= walk.x2
