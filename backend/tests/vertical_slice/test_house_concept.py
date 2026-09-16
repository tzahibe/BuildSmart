"""`HouseConcept` — how a house is organised, beside `ProgramSpec` (what it contains).

Two properties are held here. The DEFAULT concept is exactly the house the demo has always
planned, so every existing two-field `ArchitecturalSpec(plot, program)` builds the same spec.
And a concept can never carry a dimension or repeat a requirement: it is program allocation
and search ordering, nothing else — which is what keeps "the person chooses plans, not
footprints" true when a concept is chosen before generation.
"""
from __future__ import annotations

from dataclasses import fields

import pytest

from app.vertical_slice.spec import (
    ArchitecturalSpec,
    BedroomGrouping,
    CirculationStyle,
    ConceptSource,
    HouseConcept,
    LevelAreaPreference,
    LevelRef,
    PlotSpec,
    ProgramSpec,
    PublicOpenSide,
    PublicPrivateStrategy,
    demo_spec,
)


def test_the_default_concept_is_the_engine_deciding_one_storey():
    concept = HouseConcept()
    assert concept.stories == 1
    assert concept.is_single_storey
    assert concept.public_private_strategy is PublicPrivateStrategy.ENGINE
    assert concept.master_level is LevelRef.ENGINE
    assert concept.entrance_level is LevelRef.GROUND
    assert concept.bedroom_grouping is BedroomGrouping.ENGINE
    assert concept.circulation_style is CirculationStyle.ENGINE
    assert concept.public_open_side is PublicOpenSide.ENGINE
    assert concept.source is ConceptSource.ENGINE
    assert concept.level_area_preferences == ()
    assert concept.hard_fields == frozenset()


def test_every_existing_spec_constructor_gets_the_default_concept():
    """The two-field constructor is what every caller uses; it must build what it always did."""
    spec = ArchitecturalSpec(plot=PlotSpec(20.0, 24.0), program=ProgramSpec())
    assert spec.concept == HouseConcept()
    assert demo_spec().concept == HouseConcept()


def test_a_concept_names_no_dimension():
    """No footprint, no ratio, no stair size. The one number is the storey count — a PROGRAM
    fact (how many level programs exist), not a geometric one. Area preferences are the only
    other numeric field and are preferences by type."""
    numeric = {f.name for f in fields(HouseConcept)
               if f.type in ("int", "float", int, float)}
    assert numeric == {"stories"}


def test_a_concept_does_not_repeat_a_requirement():
    """`open_plan`, bedrooms, wet rooms, corridor, relationships live on `ProgramSpec`. A second
    home for any of them would be a second source of truth for the same fact."""
    concept_fields = {f.name for f in fields(HouseConcept)}
    program_fields = {f.name for f in fields(ProgramSpec)}
    assert not (concept_fields & program_fields)
    assert "open_plan" not in concept_fields and "open_plan_living" not in concept_fields


def test_stories_is_always_binding_and_other_fields_only_when_named():
    concept = HouseConcept(stories=2,
                           public_private_strategy=PublicPrivateStrategy.MASTER_SUITE_BELOW,
                           master_level=LevelRef.GROUND,
                           hard_fields=frozenset({"master_level"}))
    assert concept.is_binding("stories")
    assert concept.is_binding("master_level")
    assert not concept.is_binding("public_private_strategy")
    assert not concept.is_binding("circulation_style")


def test_a_single_storey_concept_refuses_two_storey_fields():
    """A stale two-storey field must not survive a switch back to one storey and be read later."""
    with pytest.raises(ValueError, match="stories > 1"):
        HouseConcept(stories=1, public_private_strategy=PublicPrivateStrategy.MASTER_SUITE_BELOW)
    with pytest.raises(ValueError, match="second storey"):
        HouseConcept(stories=1, master_level=LevelRef.UPPER)
    # GROUND is trivially true on one storey and is allowed.
    HouseConcept(stories=1, master_level=LevelRef.GROUND)


def test_stories_below_one_and_a_non_ground_entrance_are_refused():
    with pytest.raises(ValueError, match="at least 1"):
        HouseConcept(stories=0)
    with pytest.raises(ValueError, match="entrance_level"):
        HouseConcept(stories=2, entrance_level=LevelRef.UPPER)


def test_level_area_preferences_must_name_a_level_the_house_has():
    HouseConcept(stories=2, level_area_preferences=(LevelAreaPreference(0, 120.0),
                                                    LevelAreaPreference(1, 80.0)))
    with pytest.raises(ValueError, match="names level 2"):
        HouseConcept(stories=2, level_area_preferences=(LevelAreaPreference(2, 80.0),))
    with pytest.raises(ValueError, match="positive"):
        HouseConcept(stories=2, level_area_preferences=(LevelAreaPreference(1, 0.0),))


def test_only_bindable_fields_may_be_made_hard():
    with pytest.raises(ValueError, match="cannot be bound"):
        HouseConcept(hard_fields=frozenset({"family"}))
    with pytest.raises(ValueError, match="cannot be bound"):
        HouseConcept(hard_fields=frozenset({"stories"}))  # always bound; listing it is a mistake
    HouseConcept(stories=2, hard_fields=frozenset({"public_open_side", "circulation_style"}))


def test_total_built_area_is_the_target_the_person_entered():
    """One number has been doing four jobs; this is the name for the TOTAL. Same field today."""
    program = ProgramSpec(target_built_area_m2=200.0)
    assert program.total_built_area_m2 == 200.0
    assert ProgramSpec().total_built_area_m2 is None
