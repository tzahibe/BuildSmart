"""Tier A of the pyramid: behavior tested with real application code, zero LLM calls. These are
deliberately not new coverage of wet_room_normalizer (tests/wet_room_corpus already covers that
thoroughly) — they exist to demonstrate the pyramid's point directly: don't reach for an LLM where
deterministic code already answers the question.
"""

from types import SimpleNamespace

from app.demo.requirements_view import _public_open_side_of
from app.requirements.parser import FixtureDemand, NamedBathroom
from app.requirements.wet_room_normalizer import normalize_wet_rooms
from app.vertical_slice.spec import PublicOpenSide


def test_wet_room_count_is_deterministic_not_llm_dependent():
    demand = FixtureDemand(bathrooms=[NamedBathroom(count=2, source_text="2 חדרי רחצה")])
    result = normalize_wet_rooms(demand)
    assert result.wet_rooms.value == 2


def test_public_open_side_resolves_from_a_structured_field_not_llm_extraction():
    """public_open_side is set from Project.public_open_side (a structured UI/API field) — it is
    NOT among app.requirements.parser.RequirementExtraction's fields, so no LLM ever extracts it.
    Confirmed by reading both modules; see golden/semantic_cases.json's `_note` for why this topic
    is intentionally absent from the LLM golden set."""
    review = SimpleNamespace(public_open_side=SimpleNamespace(value="garden"))
    assert _public_open_side_of(review) is PublicOpenSide.GARDEN


def test_public_open_side_falls_back_to_engine_on_invalid_value():
    review = SimpleNamespace(public_open_side=SimpleNamespace(value="not-a-real-value"))
    assert _public_open_side_of(review) is PublicOpenSide.ENGINE
