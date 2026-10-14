"""The aligned oracle as the sizer: one MILP gives heights AND boundaries that realize through the
unchanged validators with every contact and door — on a rectangle, an L and an entry court."""
import pytest

pytest.importorskip("scipy")

from app.ai_harness.shape_agnostic.milp_oracle import milp_placement
from app.vertical_slice.band_sizing import contact_requirements
from app.vertical_slice.envelope import Envelope
from app.vertical_slice.rectilinear_realizer import RealizedLayout, realize_cells
from app.vertical_slice.topology_preservation import (
    measure_access_graph,
    measure_spatial_adjacency,
)
from tests.vertical_slice.test_staircase_sizing import (
    ENTRY_COURT,
    L_ENVELOPE,
    _two_band_programme,
)


@pytest.mark.parametrize("envelope", [Envelope.rectangle(10, 9), L_ENVELOPE, ENTRY_COURT])
def test_the_aligned_oracle_placement_realizes_with_every_contact_and_door(envelope):
    zones, bands, required, access = _two_band_programme()
    union = sorted({tuple(sorted(e)) for e in required} | {tuple(sorted(e)) for e in access})
    o = milp_placement(bands, zones, required, envelope,
                       min_contact_u=contact_requirements(zones, union, access))
    assert o.status == "FEASIBLE", o.detail
    s = o.as_sizing()
    for w in s.band_rects(bands):
        assert envelope.contains_rect_u(w), w
    out = realize_cells("oracle", s.rects(bands), zones, s.band_rects(bands), access)
    assert isinstance(out, RealizedLayout), getattr(out, "detail", out)
    assert out.ok
    sp = measure_spatial_adjacency(out.rects, frozenset(frozenset(e) for e in required))
    ac = measure_access_graph(out.fixture.access.edges, access)
    assert sp.preserved == sp.requested and ac.preserved == ac.requested


def test_a_step_from_the_oracle_lands_on_a_cell_boundary_of_the_band_above():
    zones, bands, required, access = _two_band_programme()
    union = sorted({tuple(sorted(e)) for e in required} | {tuple(sorted(e)) for e in access})
    o = milp_placement(bands, zones, required, L_ENVELOPE,
                       min_contact_u=contact_requirements(zones, union, access))
    above, below = o.band_x_u[0], o.band_x_u[1]
    for endpoint in (below[0], below[-1]):
        inside = above[0] < endpoint < above[-1]
        assert not inside or endpoint in above, (endpoint, above)


def test_the_target_objective_lands_rooms_on_their_targets_where_the_area_objective_grows_them():
    """A1 (#197, path B day 3): with exact per-room net areas in the objective, each room tracks
    the programme's target instead of its band maximum, and the hall stops being the sink."""
    from app.vertical_slice.rectilinear_realizer import RealizedLayout, realize_cells
    zones, bands, required, access = _two_band_programme()
    union = sorted({tuple(sorted(e)) for e in required} | {tuple(sorted(e)) for e in access})
    contacts = contact_requirements(zones, union, access)
    nets = {}
    for objective in ("area", "target"):
        o = milp_placement(bands, zones, required, L_ENVELOPE, min_contact_u=contacts, objective=objective)
        assert o.status == "FEASIBLE", (objective, o.detail)
        s = o.as_sizing()
        out = realize_cells(objective, s.rects(bands), zones, s.band_rects(bands), access)
        assert isinstance(out, RealizedLayout), getattr(out, "detail", out)
        nets[objective] = {r.zone_id: r.net_area_m2 for r in out.design.rooms}
    dev = {obj: sum(abs(n - zones[z].target_area_m2) / zones[z].target_area_m2 for z, n in ns.items()) / len(ns)
           for obj, ns in nets.items()}
    assert dev["target"] < dev["area"], (dev, nets)
    assert dev["target"] < 0.05, nets["target"]
