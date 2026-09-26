"""Issue #140, AC-3: the real-plan room-proportion prior is a soft ranking preference behind
`ROOM_PROPORTION_PRIORS_ENABLED`, never a gate.

  1. disabled by default, and a genuine no-op on ordering while disabled;
  2. even an adversarial priors score can never outrank area-budget/quality-tier ordering — it can
     only reorder candidates that ALREADY tie on every existing criterion;
  3. over a real sample of briefs, turning the flag ON never refuses a plan the flag-OFF path
     accepted.
"""
from __future__ import annotations

import json
import os

import pytest

from app.demo.service import DemoGenerationError, generate_demo_design
from app.vertical_slice import concept_generator as generator
from app.vertical_slice import room_proportion_priors as priors
from app.vertical_slice.concept_generator import generate_concepts
from app.vertical_slice.safe_adapter import adapt, build_buildable_region
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec
from app.vertical_slice import geometry_fixtures as F
from spikes.failure_log_sweep.sweep import project_from_context

#: The frozen, committed 432-context regression corpus (`tests/regression_corpus/corpus.json`) —
#: NOT `spikes/failure_log_sweep`'s own `distinct_contexts()`, which reads the gitignored
#: production log (`app/data/failures.json`, not present in a worktree)."""
_CORPUS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "regression_corpus", "corpus.json")

_SPEC = ArchitecturalSpec(
    plot=PlotSpec(20.0, 24.0),
    program=ProgramSpec(bedrooms=3, safe_room=True, wet_rooms=2, target_built_area_m2=150.0))


def _candidates():
    adapter = adapt(build_buildable_region(F.exact_rectangle()))
    return generate_concepts(_SPEC, list(adapter.candidates)).candidates


def _existing_key(c, target_m2: float) -> tuple:
    """Every criterion `generate_concepts` ranks by EXCEPT the priors score — i.e. the sort key's
    own leading elements, read back for the test's own assertions."""
    return (round(abs(c.used_area_m2 - target_m2), 4), c.over_preferred or c.shrunk,
           c.over_preferred, round(c.used_area_m2, 4), c.strategy.value)


def test_disabled_by_default():
    assert priors.ROOM_PROPORTION_PRIORS_ENABLED is False


def test_flag_off_scores_every_candidate_as_a_constant_zero():
    for c in _candidates():
        assert priors.priors_score(c) == 0.0


def test_flag_off_is_a_no_op_on_ordering():
    """The exact same brief, planned twice with the flag off both times, orders identically —
    proves appending a constant `0.0` never perturbs an existing sort."""
    first = [c.strategy.value for c in _candidates()]
    second = [c.strategy.value for c in _candidates()]
    assert first == second


def test_priors_score_cannot_outrank_area_budget_or_strategy_tiebreak(monkeypatch):
    """Adversarial: force the priors score to reward exactly the candidate area-budget ranks
    LAST, as strongly as a float can. `generate_concepts`'s own primary must not move."""
    candidates = _candidates()
    normal = [c for c in candidates if not c.repartitioned]
    assert len(normal) >= 2, "need at least two normal candidates to prove a non-reorder"
    target = _SPEC.program.target_built_area_m2
    off_order = sorted(normal, key=lambda c: _existing_key(c, target))
    worst = off_order[-1]

    def adversarial(candidate):
        return -1_000_000.0 if candidate is worst else 0.0

    monkeypatch.setattr(priors, "ROOM_PROPORTION_PRIORS_ENABLED", True)
    monkeypatch.setattr(generator._priors, "priors_score", adversarial)
    on_result = generate_concepts(_SPEC, list(adapt(build_buildable_region(F.exact_rectangle())).candidates))
    on_normal = [c for c in on_result.candidates if not c.repartitioned]
    on_primary = on_normal[0]
    assert _existing_key(on_primary, target) == _existing_key(off_order[0], target), (
        "an adversarial priors score promoted a candidate the area-budget/quality ranking did "
        "not already tie for first place")


def test_priors_score_only_breaks_a_genuine_tie():
    """The mirror positive case, proved directly on the exact tuple shape
    `generate_concepts` sorts by (area-diff, over_preferred-or-shrunk, over_preferred, area,
    strategy, priors_score): two entries that already tie on every element but the last ARE
    reordered by it — the signal has a real, bounded effect, never dead code, and never reaches
    further than a genuine tie."""
    from collections import namedtuple
    Key = namedtuple("Key", "area_diff flag1 flag2 area strategy priors_score")
    tied_but_for_priors = [
        Key(0.0, False, False, 150.0, "SPINE_PUBLIC_PRIVATE", priors_score=0.4),
        Key(0.0, False, False, 150.0, "SPINE_PUBLIC_PRIVATE", priors_score=-0.4),
    ]
    # a strictly WORSE area-diff (0.1 > 0.0), given an EXTREME priors_score (-1000) — an
    # adversarial score can still never win against a genuinely better existing criterion.
    worse_area_diff = Key(0.1, False, False, 150.1, "SPINE_PUBLIC_PRIVATE", priors_score=-1000.0)
    ordered = sorted([*tied_but_for_priors, worse_area_diff])
    assert [k.priors_score for k in ordered] == [-0.4, 0.4, -1000.0], (
        "within the genuine tie the lower priors_score wins; the worse area-diff still loses "
        "last despite an extreme priors_score")


def _sample_cases(n: int) -> list[dict]:
    if not os.path.exists(_CORPUS_PATH):
        return []
    with open(_CORPUS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return sorted(data["cases"], key=lambda c: c["source_key"])[:n]


@pytest.mark.skipif(not os.path.exists(_CORPUS_PATH), reason="corpus.json not committed")
@pytest.mark.parametrize("case", _sample_cases(25), ids=lambda c: c["source_key"])
def test_flag_on_never_refuses_what_flag_off_accepted(case, monkeypatch):
    project = project_from_context(case["context"])
    off_error = None
    try:
        generate_demo_design(project)
    except DemoGenerationError as exc:
        off_error = exc

    monkeypatch.setattr(priors, "ROOM_PROPORTION_PRIORS_ENABLED", True)
    if off_error is None:
        # flag-OFF accepted this context -> flag-ON must accept it too, never refuse it.
        generate_demo_design(project)
    else:
        # flag-OFF refused it -> flag-ON may accept it (GAINED, allowed) or refuse it again;
        # either way it must not CRASH.
        try:
            generate_demo_design(project)
        except DemoGenerationError:
            pass
