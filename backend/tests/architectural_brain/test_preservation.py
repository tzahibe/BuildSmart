"""Verifies Issue #109 AC-3: ``measure_preservation`` reports, per ``RealizationIntent`` fact
class, what survived on the REALIZED geometry -- measured on real ``RealizedPlan``s from >= 2
different benchmark briefs. ``BRIEF_1``'s own concept-1 and ``BRIEF_3``'s own concept-5 are used
because they are the FASTEST-realizing alternatives on each brief (~4s / ~0.2s respectively --
``docs/reports/poc-architectural-brain/brief-1/comparison.md`` and .../brief-3/comparison.md's own
recorded timings), not for any other property.
"""
from __future__ import annotations

import pytest

from spikes.architectural_brain.adaptation import Rejection, adapt
from spikes.architectural_brain.brief import Brief
from spikes.architectural_brain.corpus_io import load_corpus_dir
from spikes.architectural_brain.preservation import (
    REASON_BUDGET,
    REASON_DONOR_ROOM_NOT_REALIZED,
    REASON_GUILLOTINE_IMPOSSIBLE,
    PreservationReport,
    measure_preservation,
)
from spikes.architectural_brain.realization_intent import intent_from
from spikes.architectural_brain.realize import donor_room_id_by_zone, realize_concept
from spikes.architectural_brain.retrieval import retrieve
from spikes.architectural_brain.synthesis import synthesize

from app.vertical_slice import general_pipeline as gp
from app.vertical_slice.spec import PlotSpec
from tests.architectural_brain.briefs import BRIEF_1, BRIEF_3

CORPUS_DIR = "spikes/architectural_brain/corpus"
#: Same breadth `demo.py` itself uses -- see that module's own docstring.
DEMO_K = 15
DEMO_MAX_CANDIDATES = 8

_KNOWN_REASONS = {REASON_DONOR_ROOM_NOT_REALIZED, REASON_GUILLOTINE_IMPOSSIBLE, REASON_BUDGET}

_EXPECTED_FACT_CLASSES = {
    "adjacency", "access", "exposure", "placement", "clusters",
    "wet_core_groups", "entrance_relationship", "room_proportions",
    "footprint_relationships",
}


def _realize_with_intent(brief_def, concept_index: int):
    corpus = load_corpus_dir(CORPUS_DIR)
    brief = Brief(program=brief_def.program(), stories=1)
    plot = PlotSpec(width_m=brief_def.plot_size_m[0], depth_m=brief_def.plot_size_m[1])
    refs = retrieve(brief, plot, corpus, k=DEMO_K)
    concepts = synthesize(brief, refs, max_candidates=DEMO_MAX_CANDIDATES)
    assert len(concepts) > concept_index, (
        f"{brief_def.brief_id}: only {len(concepts)} synthesized concepts, need index {concept_index}")
    concept = concepts[concept_index]
    ref_by_plan_id = {r.plan_id: r.plan_reference for r in refs}
    primary_ref = ref_by_plan_id[concept.references[0].plan_id]
    intent = intent_from(primary_ref, concept, brief)
    adapted = adapt(concept, brief, plot)
    assert not isinstance(adapted, Rejection), f"{concept.concept_id} was rejected: {adapted}"
    site = brief_def.site_constraints()
    plan = realize_concept(concept, adapted, brief, site, brief_def.plot_size_m, intent=intent)
    assert isinstance(plan, gp.RealizedPlan), f"{concept.concept_id} did not realize (got {plan!r})"
    mapping = donor_room_id_by_zone(brief, adapted)
    return intent, plan, mapping


@pytest.fixture(scope="module")
def brief_1_case():
    return _realize_with_intent(BRIEF_1, 1)


@pytest.fixture(scope="module")
def brief_3_case():
    return _realize_with_intent(BRIEF_3, 5)


def test_report_covers_every_fact_class_and_every_lost_fact_carries_a_known_reason(brief_1_case):
    intent, plan, mapping = brief_1_case
    report = measure_preservation(intent, plan, mapping)
    assert report.source_plan_id == intent.source_plan_id
    assert report.concept_id == intent.concept_id
    assert {f.fact_class for f in report.fact_classes} == _EXPECTED_FACT_CLASSES
    for f in report.fact_classes:
        assert 0 <= f.preserved <= f.total
        for lost in f.lost:
            assert lost.reason in _KNOWN_REASONS, f"{f.fact_class}: unknown reason {lost.reason!r}"
            assert lost.detail


def test_report_round_trips_through_json(brief_1_case):
    intent, plan, mapping = brief_1_case
    report = measure_preservation(intent, plan, mapping)
    assert PreservationReport.from_json(report.to_json()).to_dict() == report.to_dict()


def test_to_markdown_produces_a_preserved_and_a_lost_block(brief_1_case):
    intent, plan, mapping = brief_1_case
    report = measure_preservation(intent, plan, mapping)
    md = report.to_markdown()
    assert "PRESERVED" in md
    assert "LOST" in md


def test_measured_on_two_realized_plans_of_different_briefs(brief_1_case, brief_3_case):
    """AC-3's own wording: 'measured on at least two realized plans of different briefs'."""
    intent_1, plan_1, mapping_1 = brief_1_case
    intent_3, plan_3, mapping_3 = brief_3_case
    report_1 = measure_preservation(intent_1, plan_1, mapping_1)
    report_3 = measure_preservation(intent_3, plan_3, mapping_3)
    assert report_1.source_plan_id != report_3.source_plan_id
    assert any(f.total > 0 for f in report_1.fact_classes), "brief-1 case measured nothing at all"
    assert any(f.total > 0 for f in report_3.fact_classes), "brief-3 case measured nothing at all"


def test_a_donor_room_adaptation_dropped_is_reported_lost_not_silently_absorbed(brief_1_case):
    """A fact naming a donor room id `donor_room_id_by_zone` has no realized zone for (dropped or
    never individually resized by adaptation) must surface with DONOR_ROOM_NOT_REALIZED -- checked
    directly against a synthetic mapping missing one real donor room, so the assertion does not
    depend on this donor happening to have an unmapped room of its own."""
    intent, plan, mapping = brief_1_case
    assert intent.adjacency_edges, "this donor has no adjacency facts at all -- cannot exercise this path"
    dropped_room = intent.adjacency_edges[0].room_a
    mapping_without = {z: d for z, d in mapping.items() if d != dropped_room}

    report = measure_preservation(intent, plan, mapping_without)
    adjacency = report.fact_class("adjacency")
    affected = [e for e in intent.adjacency_edges if dropped_room in (e.room_a, e.room_b)]
    assert affected
    assert any(l.reason == REASON_DONOR_ROOM_NOT_REALIZED for l in adjacency.lost)
