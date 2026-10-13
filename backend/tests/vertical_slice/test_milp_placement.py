"""The aligned oracle as the sizer: one MILP gives heights AND boundaries that realize through the
unchanged validators with every contact and door — on a rectangle, an L and an entry court."""
import pytest

pytest.importorskip("scipy")

from app.ai_harness.shape_agnostic.milp_oracle import milp_placement  # noqa: E402
from app.vertical_slice.band_sizing import contact_requirements  # noqa: E402
from app.vertical_slice.envelope import Envelope  # noqa: E402
from app.vertical_slice.rectilinear_realizer import RealizedLayout, realize_cells  # noqa: E402
from app.vertical_slice.topology_preservation import measure_access_graph, measure_spatial_adjacency  # noqa: E402
from tests.vertical_slice.test_staircase_sizing import ENTRY_COURT, L_ENVELOPE, _two_band_programme  # noqa: E402


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
