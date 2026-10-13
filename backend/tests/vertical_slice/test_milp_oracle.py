"""The MILP oracle (formulation B as a question about formulation A) agrees with the exact sizer
where the sizer answers, and answers where the sizer only says UNKNOWN. Research tooling under
`app/ai_harness`: it needs `scipy` (HiGHS), which is not a production dependency, so the whole
module is skipped where it is absent rather than pretending."""
import pytest

scipy = pytest.importorskip("scipy")

from app.ai_harness.shape_agnostic.milp_oracle import milp_heights  # noqa: E402
from app.vertical_slice.band_sizing import contact_requirements  # noqa: E402
from app.vertical_slice.envelope import Envelope  # noqa: E402
from app.vertical_slice.staircase_sizing import solve_staircase_layout  # noqa: E402
from tests.vertical_slice.test_staircase_sizing import L_ENVELOPE, _two_band_programme  # noqa: E402


def _setup():
    zones, bands, required, access = _two_band_programme()
    union = sorted({tuple(sorted(e)) for e in required} | {tuple(sorted(e)) for e in access})
    return zones, bands, required, contact_requirements(zones, union, access)


@pytest.mark.parametrize("envelope", [Envelope.rectangle(10, 9), L_ENVELOPE])
def test_the_oracle_and_the_sizer_agree_where_both_answer(envelope):
    zones, bands, required, mc = _setup()
    o = milp_heights(bands, zones, required, envelope, min_contact_u=mc)
    s = solve_staircase_layout(bands, zones, required, envelope, min_contact_u=mc)
    assert o.status == s.status == "FEASIBLE", (o, s.status)


def test_the_oracle_proves_a_too_small_envelope_infeasible():
    zones, bands, required, mc = _setup()
    o = milp_heights(bands, zones, required, Envelope.rectangle(5, 5), min_contact_u=mc)
    assert o.status == "INFEASIBLE"


def test_the_oracles_heights_seed_an_exact_sizing():
    """A FEASIBLE oracle answer is only heights; the exact width solver realizes them."""
    zones, bands, required, mc = _setup()
    o = milp_heights(bands, zones, required, L_ENVELOPE, min_contact_u=mc)
    assert o.status == "FEASIBLE"
    import app.vertical_slice.staircase_sizing as ss
    r = ss._solve_once(bands, zones, required, L_ENVELOPE, tol_m2=0.01, node_limit=200,
                       min_contact_u=mc, sides=None, seed=o.heights_u)
    assert r.status == "FEASIBLE", r.detail
