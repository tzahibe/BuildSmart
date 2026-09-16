"""Phase 0 + Phase 1 gate: the labelled corpus of 61 distinct wet-room briefs (`corpus.json`).

Each brief carries the `FixtureDemand` the parser should extract and the rooms the normalizer must
make of it, both hand-labelled on 2026-09-15 against the rule the product adopted: a toilet is a
fixture every bathroom already holds, only the surplus becomes a room, and a toilet attached to a
bedroom on its own is a question, not an invented shower. `stored` is what the old count-based
parser actually stored for the same text — the "before" this replaces.

The corpus is frozen data: change it only when the rule changes, and say so in the label.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.requirements.parser import FixtureDemand
from app.requirements.wet_room_normalizer import normalize_wet_rooms
from app.vertical_slice.spec import (
    ENSUITE_HOST_MASTER,
    ProgramSpec,
    WetRoomKind,
    WetRoomOrigin,
    WetRoomRequirement,
)
from app.vertical_slice.wet_rooms import resolve_wet_rooms

CORPUS = json.loads((Path(__file__).parent / "corpus.json").read_text(encoding="utf-8"))["briefs"]


def _ids():
    return [f"{b['idx']:02d}-{b['class']}" for b in CORPUS]


@pytest.mark.parametrize("brief", CORPUS, ids=_ids())
def test_the_normalizer_makes_the_labelled_rooms_of_the_labelled_demand(brief):
    got = normalize_wet_rooms(FixtureDemand.model_validate(brief["demand"]))
    expected = brief["expected"]
    assert [[k.kind, k.host, k.origin] for k in got.kinds] == expected["kinds"], brief["text"]
    assert got.wet_rooms.value == expected["wet_rooms"] == len(got.kinds)
    assert [q.code for q in got.questions] == expected["questions"]


def test_the_corpus_is_the_measured_one():
    """61 distinct texts over 95 stored records; 90 of them carry a count the old parser gave."""
    assert len(CORPUS) == 61
    records = [s for b in CORPUS for s in b["stored"]]
    assert len(records) == 95
    assert sum(s["wet_rooms"] is not None for s in records) == 90


def test_before_the_old_parser_counted_every_toilet_as_a_room_in_most_bath_plus_toilet_briefs():
    """The number this work exists to change, kept as a fact about the 'before'. Briefs naming a
    bathroom AND bare toilets (classes P2/P3): the stored count equalled bathrooms + toilets —
    every fixture a room — in 16 of 29 records."""
    naive = total = 0
    for brief in CORPUS:
        if brief["class"] not in ("P2", "P3"):
            continue
        labels = brief["labels"]
        for stored in brief["stored"]:
            if stored["wet_rooms"] is None:
                continue
            total += 1
            naive += stored["wet_rooms"] == labels["bathrooms"] + labels["toilet_mentions"]
    assert (naive, total) == (16, 29)


def test_after_no_labelled_brief_gets_a_room_for_a_toilet_a_bathroom_already_holds():
    for brief in CORPUS:
        labels = brief["labels"]
        got = normalize_wet_rooms(FixtureDemand.model_validate(brief["demand"]))
        holders = sum(k.kind in ("shared_bathroom", "ensuite") for k in got.kinds)
        derived_wcs = sum(k.kind == "guest_wc" and k.origin == "count_derived" for k in got.kinds)
        if labels["bathrooms"]:
            assert derived_wcs == max(0, labels["toilet_mentions"] - holders), brief["text"]


# ------------------------------------------------------------------ the four canonical briefs

def _kinds(program: ProgramSpec):
    return [(r.zone_id, r.kind.value, r.origin.value) for r in resolve_wet_rooms(program)]


def test_one_bathroom_is_one_shared_bathroom_and_no_wc():
    got = normalize_wet_rooms(FixtureDemand(bathrooms=[{"source_text": "חדר רחצה"}]))
    assert [k.kind for k in got.kinds] == ["shared_bathroom"] and got.wet_rooms.value == 1


def test_one_bathroom_plus_guest_wc_is_a_bathroom_and_a_separate_wc():
    got = normalize_wet_rooms(FixtureDemand(bathrooms=[{"source_text": "חדר רחצה"}],
                                            separate_wcs=[{"source_text": "שירותי אורחים"}]))
    assert [(k.kind, k.origin) for k in got.kinds] == [("guest_wc", "explicit"), ("shared_bathroom", "explicit")]


def test_one_bathroom_plus_two_toilets_is_a_bathroom_with_a_toilet_and_one_derived_wc():
    got = normalize_wet_rooms(FixtureDemand(bathrooms=[{"source_text": "מקלחת"}], toilet_mentions=2,
                                            toilet_source_text="2 שירותים"))
    assert [(k.kind, k.origin) for k in got.kinds] == [("guest_wc", "count_derived"), ("shared_bathroom", "explicit")]
    assert got.wet_rooms.value == 2 and not got.questions


def test_two_bathrooms_plus_guest_wc_keeps_both_bathrooms_and_the_wc():
    got = normalize_wet_rooms(FixtureDemand(bathrooms=[{"source_text": "2 חדרי רחצה", "count": 2}],
                                            separate_wcs=[{"source_text": "שירותי אורחים"}]))
    assert [k.kind for k in got.kinds] == ["guest_wc", "shared_bathroom", "shared_bathroom"]


def test_the_engine_builds_exactly_those_rooms_from_the_normalized_kinds():
    program = ProgramSpec(bedrooms=3, wet_rooms=2, wet_room_kinds=(
        WetRoomRequirement(WetRoomKind.GUEST_WC, origin=WetRoomOrigin.COUNT_DERIVED),
        WetRoomRequirement(WetRoomKind.SHARED_BATHROOM)))
    assert _kinds(program) == [("TOILET_1", "guest_wc", "count_derived"), ("BATH_1", "shared_bathroom", "explicit")]


def test_the_legacy_bare_count_default_is_untouched():
    """Nothing said about wet rooms keeps the inferred count of 1 and no kinds, and a bare count
    of 3 still plans as the ensuite + WC + shared bathroom it always did — every padded room is
    COUNT_DERIVED because the count made it."""
    got = normalize_wet_rooms(FixtureDemand())
    assert (got.wet_rooms.value, got.wet_rooms.source.value, got.kinds) == (1, "inferred", [])
    assert _kinds(ProgramSpec(bedrooms=3, wet_rooms=3)) == [
        ("BATH_1", "ensuite", "count_derived"), ("TOILET_1", "guest_wc", "count_derived"),
        ("BATH_2", "shared_bathroom", "count_derived")]


def test_toilets_only_one_is_the_bathroom_two_or_more_is_a_question_with_the_absorbing_reading():
    one = normalize_wet_rooms(FixtureDemand(toilet_mentions=1, toilet_source_text="שירותים"))
    assert [(k.kind, k.origin) for k in one.kinds] == [("shared_bathroom", "count_derived")] and not one.questions
    three = normalize_wet_rooms(FixtureDemand(toilet_mentions=3, toilet_source_text="3 שירותים"))
    assert [k.kind for k in three.kinds] == ["guest_wc", "guest_wc", "shared_bathroom"]
    assert [q.code for q in three.questions] == ["TOILETS_WITHOUT_BATHROOM"]
    assert [k.kind for k in three.questions[0].proposal_kinds] == ["guest_wc", "guest_wc", "shared_bathroom"]


def test_a_bedroom_with_only_a_toilet_named_is_a_question_whose_proposal_is_an_ensuite():
    got = normalize_wet_rooms(FixtureDemand(
        attached=[{"host": ENSUITE_HOST_MASTER, "fixtures": "toilet_only", "source_text": "חדר הורים עם שירותים"}],
        separate_wcs=[{"source_text": "שירותי אורחים"}]))
    # No shower is invented: the only room stored is the one the person named as a room.
    assert [k.kind for k in got.kinds] == ["guest_wc"] and got.wet_rooms.value == 1
    (question,) = got.questions
    assert question.code == "ATTACHED_TOILET_ONLY" and "חדר הורים עם שירותים" in question.text
    assert [(k.kind, k.host) for k in question.proposal_kinds] == [("ensuite", ENSUITE_HOST_MASTER), ("guest_wc", None)]


def test_a_bedroom_with_a_shower_named_is_an_ensuite_and_its_toilet_is_a_fixture():
    got = normalize_wet_rooms(FixtureDemand(
        attached=[{"host": ENSUITE_HOST_MASTER, "fixtures": "bath", "source_text": "חדר הורים עם מקלחת ושירותים"}]))
    assert [(k.kind, k.host, k.origin) for k in got.kinds] == [("ensuite", ENSUITE_HOST_MASTER, "explicit")]
    assert not got.questions


def test_an_additional_toilet_named_as_a_room_is_built_even_when_a_bathroom_could_hold_it():
    """Not optimising for fewer toilets: 'ועוד שירותים' is a separate WC the person asked for."""
    got = normalize_wet_rooms(FixtureDemand(
        attached=[{"host": ENSUITE_HOST_MASTER, "fixtures": "bath", "source_text": "חדר הורים עם מקלחת ושירותים"}],
        separate_wcs=[{"source_text": "ועוד שירותים"}]))
    assert [(k.kind, k.origin) for k in got.kinds] == [("ensuite", "explicit"), ("guest_wc", "explicit")]


def test_the_same_demand_always_gives_the_same_rooms():
    demand = FixtureDemand(bathrooms=[{"source_text": "מקלחת"}], toilet_mentions=2, toilet_source_text="2 שירותים")
    first = normalize_wet_rooms(demand)
    assert all(normalize_wet_rooms(demand) == first for _ in range(5))
