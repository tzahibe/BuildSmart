"""Concept Engine v2 (4/5) — Issue #78: the flag-on stage wired into `run_general`.

AC-3 and AC-6 are proved against a REAL, frozen regression-corpus context (not a synthetic
fixture): a request whose shown plan set, flag ON, genuinely contains two circulation classes —
found via `spikes/failure_log_sweep/concept_diversity_v2.py` (context index 1 of `tests/
regression_corpus/corpus.json`'s PLANNED cases, `project_id` below). Hard-coded here rather than
read back from the corpus file, so this test does not depend on the corpus's own ordering.

A `_ClassRecorder` (the same instrumentation `spikes/failure_log_sweep/concept_diversity.py`'s own
`_ClassRecorder` uses for the Issue #75 baseline) matches every `DemoDesign` the demo service hands
back to the `RealizedPlan` `general_pipeline._realize` built it from, by room-rectangle signature —
so "the label matches the realized class" and "shown plans are pairwise distinct" are checked
against the SAME realized geometry the pipeline itself classified, never against the label's own
claim.
"""
from __future__ import annotations

import pytest

from app.demo import service as svc
from app.vertical_slice import general_pipeline as gp
from app.vertical_slice.concept_spec import CirculationClass, concept_spec_of, topologically_distinct
from spikes.failure_log_sweep.sweep import project_from_context

#: A single-bedroom, 2-wet-room, safe-room brief on an 11x12 footprint within an 18x22.5 plot —
#: `project_id` "47f81017-..." in the frozen corpus. Flag ON, its shown set contains a SPINE
#: primary and a FRONT_BAND alternative.
_MULTI_CLASS_CONTEXT = {
    "project_id": "47f81017-3d75-4783-8958-6790a5791ffc",
    "plot_width_m": 18.0, "plot_depth_m": 22.5, "street_facing_side": "NORTH",
    "built_area_m2": 132.0, "footprint_width_m": 11.0, "footprint_depth_m": 12.0,
    "bedrooms": 1, "wet_rooms": 2, "safe_room": True, "open_plan": False,
}


def _layout_signature_of_rooms(rooms) -> tuple:
    return tuple(sorted((zid, round(x, 3), round(y, 3), round(w, 3), round(h, 3))
                        for zid, x, y, w, h in rooms))


def _demo_design_rooms(design) -> tuple:
    return tuple((r.id, r.x, r.y, r.width_m, r.depth_m) for r in design.rooms)


def _realized_plan_rooms(design) -> tuple:
    return tuple((r.zone_id, *r.rect_m) for r in design.rooms)


class _ClassRecorder:
    """Records every `RealizedPlan` `_realize` builds, keyed by its own layout signature, so a
    `DemoDesign` the demo service later hands back can be matched to the `RealizedPlan` it was
    realized from — mirrors `concept_diversity.py`'s `_ClassRecorder` (Issue #75)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch):
        self._orig = gp._realize
        self.by_signature: dict[tuple, object] = {}
        monkeypatch.setattr(gp, "_realize", self._realize)

    def _realize(self, *args, **kwargs):
        plan = self._orig(*args, **kwargs)
        sig = _layout_signature_of_rooms(_realized_plan_rooms(plan.design))
        self.by_signature[sig] = plan
        return plan

    def plan_for(self, design) -> object | None:
        sig = _layout_signature_of_rooms(_demo_design_rooms(design))
        return self.by_signature.get(sig)


@pytest.fixture
def flag_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gp, "CONCEPT_ENGINE_V2_ENABLED", True)


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _ClassRecorder:
    return _ClassRecorder(monkeypatch)


def _shown_designs(flag_on, recorder):
    project = project_from_context(_MULTI_CLASS_CONTEXT)
    result = svc.generate_demo_design(project)
    return [result.design, *result.alternatives]


def test_multi_class_context_actually_shows_two_classes(flag_on, recorder):
    """Guards the fixture context itself: if the corpus/pipeline ever changes so this context no
    longer demonstrates diversity, the two tests below would otherwise pass vacuously."""
    shown = _shown_designs(flag_on, recorder)
    classes = {recorder.plan_for(d).circulation_class for d in shown if recorder.plan_for(d)}
    assert len(classes) >= 2, f"expected >=2 circulation classes, got {classes}"


def test_every_shown_plan_label_matches_its_realized_class(flag_on, recorder):
    """AC-3: every shown plan's `concept` label names the SAME class `general_pipeline._realize`
    computed for it (`concept_spec.realized_circulation_class`, read off the realized geometry)."""
    shown = _shown_designs(flag_on, recorder)
    labelled = [d for d in shown if d.concept is not None]
    assert labelled, "expected at least one shown plan to carry a concept label"
    for design in labelled:
        plan = recorder.plan_for(design)
        assert plan is not None, "labelled plan not found in the realized-plan recorder"
        assert plan.circulation_class is not None
        assert design.concept.circulation_class == plan.circulation_class.value


def test_shown_plans_are_pairwise_topologically_distinct(flag_on, recorder):
    """AC-6: no two shown plans are mirror images or re-proportionings of the same concept family
    — `concept_spec.topologically_distinct` holds for every pair of shown plans."""
    shown = _shown_designs(flag_on, recorder)
    specs = []
    for design in shown:
        plan = recorder.plan_for(design)
        assert plan is not None
        specs.append(concept_spec_of(plan.concept))
    assert len(specs) >= 2
    for i in range(len(specs)):
        for j in range(i + 1, len(specs)):
            assert topologically_distinct(specs[i], specs[j]), (
                f"shown plans {i} and {j} are not topologically distinct: {specs[i]} vs {specs[j]}")


def test_concept_label_covers_every_circulation_class():
    """`concept_engine_v2.concept_label` never raises for a class `realized_circulation_class` can
    return — every `CirculationClass` value has a Hebrew label and rationale."""
    from app.vertical_slice.concept_engine_v2 import concept_label

    for circulation_class in CirculationClass:
        label = concept_label(circulation_class)
        assert label.label
        assert label.rationale
