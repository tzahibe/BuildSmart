"""AC-3 — Issue #96: the 3 benchmark briefs are fixed fixtures whose current-engine baseline is
recorded and re-rendered deterministically."""
from __future__ import annotations

import pytest

from app.vertical_slice.general_pipeline import run_general_from_site
from tests.architectural_brain.briefs import BENCHMARK_BRIEFS

BRIEF_IDS = [b.brief_id for b in BENCHMARK_BRIEFS]


def _layout_signature(design) -> tuple:
    return tuple(sorted((r.zone_id,) + tuple(round(v, 3) for v in r.rect_m)
                        for r in design.rooms))


@pytest.fixture(scope="module")
def baselines(tmp_path_factory):
    out = tmp_path_factory.mktemp("benchmark_baselines")
    return {
        brief.brief_id: run_general_from_site(
            brief.site_constraints(), plot_size_m=brief.plot_size_m, program=brief.program(),
            render_path=str(out / f"{brief.brief_id}.png"))
        for brief in BENCHMARK_BRIEFS
    }


#: brief-3's own Z-shaped site (see `briefs.BRIEF_3`'s own comment) is what makes a genuinely
#: TWO_WING brain-compiled alternative possible at all (AC-1) — and it is ALSO, honestly, a site
#: shape the CURRENT engine's own strategies cannot solve: every single-wing strategy needs more
#: depth than either candidate rectangle offers for this 5-bedroom/3-wet-room programme, and its
#: own `MULTI_WING_SPLIT` explicitly declines a north/south seam ("a hall along the street axis
#: is not authored yet" — an engine limitation, not a crash). AC-3 asks for the baseline
#: "recorded", not that it succeeds; a documented, deterministic REFUSAL is itself the honest
#: baseline this specific brief has, and the report says so plainly.
_EXPECTED_REFUSAL_BRIEFS = {"brief-3"}


@pytest.mark.parametrize("brief_id", BRIEF_IDS)
def test_current_engine_baseline_solves_and_validates(baselines, brief_id):
    """AC-3: every fixed brief's current-engine result is recorded — solved and passing every
    existing hard validator for brief-1/2, or (brief-3 only) a specific, deterministic refusal
    reason rather than a crash or an unexplained one."""
    result = baselines[brief_id]
    if brief_id in _EXPECTED_REFUSAL_BRIEFS:
        assert result.design is None, f"{brief_id}: expected a refusal baseline, got a design"
        assert any("MULTI_WING_SPLIT" in note and "seam" in note for note in result.notes), (
            f"{brief_id}: refusal reason changed from the documented seam limitation: {result.notes}")
        return
    assert result.design is not None, f"{brief_id}: no design ({result.outcome}) — {result.notes}"
    assert result.ok, f"{brief_id}: " + "; ".join(
        c.check_id for c in result.validation.failures()) if result.validation else result.notes


@pytest.mark.parametrize("brief_id", BRIEF_IDS)
def test_baseline_rerenders_deterministically(brief_id):
    """AC-3: the same fixed brief, run twice, produces the identical realized geometry — or,
    for brief-3's documented refusal, the identical refusal outcome both times."""
    brief = next(b for b in BENCHMARK_BRIEFS if b.brief_id == brief_id)
    first = run_general_from_site(brief.site_constraints(), plot_size_m=brief.plot_size_m,
                                  program=brief.program())
    second = run_general_from_site(brief.site_constraints(), plot_size_m=brief.plot_size_m,
                                   program=brief.program())
    if brief_id in _EXPECTED_REFUSAL_BRIEFS:
        assert first.design is None and second.design is None
        assert first.outcome == second.outcome
        return
    assert first.design is not None and second.design is not None
    assert _layout_signature(first.design) == _layout_signature(second.design)
