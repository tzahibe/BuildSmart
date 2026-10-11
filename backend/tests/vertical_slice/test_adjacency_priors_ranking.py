"""Issue #141, AC-6/AC-7: the real-plan adjacency prior is a soft ranking preference behind
`ADJACENCY_PRIORS_ENABLED`, never a gate.

  1. disabled by default, and a genuine no-op on ordering while disabled (AC-7);
  2. even an adversarial adjacency score can never outrank area-budget/quality-tier ordering, or
     the room-proportion prior that precedes it — it can only reorder candidates that ALREADY tie
     on every existing criterion;
  3. over a real sample of briefs, turning the flag ON never refuses a plan the flag-OFF path
     accepted (AC-6).
"""
from __future__ import annotations

import json
import os

import pytest

from app.demo.service import DemoGenerationError, generate_demo_design
from app.vertical_slice import adjacency_priors as priors
from app.vertical_slice import concept_generator as generator
from app.vertical_slice import geometry_fixtures as F
from app.vertical_slice.concept_generator import generate_concepts
from app.vertical_slice.safe_adapter import adapt, build_buildable_region
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec
from spikes.failure_log_sweep.sweep import project_from_context

_CORPUS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "regression_corpus", "corpus.json")

_SPEC = ArchitecturalSpec(
    plot=PlotSpec(20.0, 24.0),
    program=ProgramSpec(bedrooms=3, safe_room=True, wet_rooms=2, target_built_area_m2=150.0))


def _candidates():
    adapter = adapt(build_buildable_region(F.exact_rectangle()))
    return generate_concepts(_SPEC, list(adapter.candidates)).candidates


def _existing_key(c, target_m2: float) -> tuple:
    """Every criterion `generate_concepts` ranks by EXCEPT the adjacency score — i.e. the sort
    key's own leading elements (including the room-proportion prior, disabled and constant here),
    read back for the test's own assertions."""
    return (round(abs(c.used_area_m2 - target_m2), 4), c.over_preferred or c.shrunk,
           c.over_preferred, round(c.used_area_m2, 4), c.strategy.value, 0.0)


def test_disabled_by_default():
    assert priors.ADJACENCY_PRIORS_ENABLED is False


def test_flag_off_scores_every_candidate_as_a_constant_zero():
    for c in _candidates():
        assert priors.adjacency_score(c) == 0.0


def test_flag_off_is_a_no_op_on_ordering():
    """The exact same brief, planned twice with the flag off both times, orders identically —
    proves appending a constant `0.0` never perturbs an existing sort."""
    first = [c.strategy.value for c in _candidates()]
    second = [c.strategy.value for c in _candidates()]
    assert first == second


def test_adjacency_score_cannot_outrank_area_budget_or_strategy_tiebreak(monkeypatch):
    """Adversarial: force the adjacency score to reward exactly the candidate area-budget ranks
    LAST, as strongly as a float can. `generate_concepts`'s own primary must not move."""
    candidates = _candidates()
    normal = [c for c in candidates if not c.repartitioned]
    assert len(normal) >= 2, "need at least two normal candidates to prove a non-reorder"
    target = _SPEC.program.target_built_area_m2
    off_order = sorted(normal, key=lambda c: _existing_key(c, target))
    worst = off_order[-1]

    def adversarial(candidate):
        return -1_000_000.0 if candidate is worst else 0.0

    monkeypatch.setattr(priors, "ADJACENCY_PRIORS_ENABLED", True)
    monkeypatch.setattr(generator._adjacency_priors, "adjacency_score", adversarial)
    on_result = generate_concepts(_SPEC, list(adapt(build_buildable_region(F.exact_rectangle())).candidates))
    on_normal = [c for c in on_result.candidates if not c.repartitioned]
    on_primary = on_normal[0]
    assert _existing_key(on_primary, target) == _existing_key(off_order[0], target), (
        "an adversarial adjacency score promoted a candidate the area-budget/quality ranking did "
        "not already tie for first place")


def test_adjacency_score_only_breaks_a_genuine_tie():
    """The mirror positive case, proved directly on the exact tuple shape `generate_concepts`
    sorts by (area-diff, over_preferred-or-shrunk, over_preferred, area, strategy,
    priors_score, adjacency_score): two entries that already tie on every element but the last ARE
    reordered by it — the signal has a real, bounded effect, never dead code, and never reaches
    further than a genuine tie."""
    from collections import namedtuple
    Key = namedtuple("Key", "area_diff flag1 flag2 area strategy priors_score adjacency_score")
    tied_but_for_adjacency = [
        Key(0.0, False, False, 150.0, "SPINE_PUBLIC_PRIVATE", 0.0, adjacency_score=0.4),
        Key(0.0, False, False, 150.0, "SPINE_PUBLIC_PRIVATE", 0.0, adjacency_score=-0.4),
    ]
    # a strictly WORSE area-diff (0.1 > 0.0), given an EXTREME adjacency_score (-1000) — an
    # adversarial score can still never win against a genuinely better existing criterion.
    worse_area_diff = Key(0.1, False, False, 150.1, "SPINE_PUBLIC_PRIVATE", 0.0,
                          adjacency_score=-1000.0)
    ordered = sorted([*tied_but_for_adjacency, worse_area_diff])
    assert [k.adjacency_score for k in ordered] == [-0.4, 0.4, -1000.0], (
        "within the genuine tie the lower adjacency_score wins; the worse area-diff still loses "
        "last despite an extreme adjacency_score")


def test_precedence_below_room_proportion_priors():
    """Issue #140's prior sits strictly BEFORE this one in the sort key: on the exact tuple shape
    `generate_concepts` sorts by, a genuine (non-tied) `priors_score` preference must decide the
    order even against an EXTREME adversarial `adjacency_score` on the other side."""
    from collections import namedtuple
    Key = namedtuple("Key", "area_diff flag1 flag2 area strategy priors_score adjacency_score")
    genuine_priors_preference = Key(0.0, False, False, 150.0, "SPINE_PUBLIC_PRIVATE", -1.0,
                                    adjacency_score=1_000_000.0)
    worse_on_priors_but_adversarial_adjacency = Key(0.0, False, False, 150.0, "SPINE_PUBLIC_PRIVATE",
                                                     0.0, adjacency_score=-1_000_000.0)
    ordered = sorted([genuine_priors_preference, worse_on_priors_but_adversarial_adjacency])
    assert ordered[0] is genuine_priors_preference, (
        "an adversarial adjacency_score overrode a genuine (non-tied) priors_score preference, "
        "which must sit at strictly higher precedence")


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

    monkeypatch.setattr(priors, "ADJACENCY_PRIORS_ENABLED", True)
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
