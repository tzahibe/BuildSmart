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


@pytest.mark.parametrize("brief_id", BRIEF_IDS)
def test_current_engine_baseline_solves_and_validates(baselines, brief_id):
    """AC-3: every fixed brief's current-engine result is recorded — solved, and passing every
    existing hard validator, so it is a real baseline rather than a refusal to compare against."""
    result = baselines[brief_id]
    assert result.design is not None, f"{brief_id}: no design ({result.outcome}) — {result.notes}"
    assert result.ok, f"{brief_id}: " + "; ".join(
        c.check_id for c in result.validation.failures()) if result.validation else result.notes


@pytest.mark.parametrize("brief_id", BRIEF_IDS)
def test_baseline_rerenders_deterministically(brief_id):
    """AC-3: the same fixed brief, run twice, produces the identical realized geometry."""
    brief = next(b for b in BENCHMARK_BRIEFS if b.brief_id == brief_id)
    first = run_general_from_site(brief.site_constraints(), plot_size_m=brief.plot_size_m,
                                  program=brief.program())
    second = run_general_from_site(brief.site_constraints(), plot_size_m=brief.plot_size_m,
                                   program=brief.program())
    assert first.design is not None and second.design is not None
    assert _layout_signature(first.design) == _layout_signature(second.design)
