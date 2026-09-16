"""The extraction backstop (`wet_room_normalizer.extraction_mismatches`): a strong wet-room phrase
in the brief with no demand behind it — or a demand with no phrase behind it — is a question, not
a silent programme. Cases are the four remaining live misses of the 2026-09-16 corpus run, plus
the four phrase families the check must cover. Nothing here invents a room: the stored rooms are
always exactly what was extracted, and the proposal is where the likely reading lives."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.requirements.parser import FixtureDemand, normalize_extraction
from app.requirements.wet_room_normalizer import normalize_wet_rooms
from tests.test_wet_room_questions import _brief

CORPUS = {b["idx"]: b for b in json.loads(
    (Path(__file__).parent / "wet_room_corpus" / "corpus.json").read_text(encoding="utf-8"))["briefs"]}

MASTER_BATH = {"host": "MASTER_BEDROOM", "fixtures": "bath", "source_text": "חדר הורים עם מקלחת"}


def _run(text: str, demand: FixtureDemand):
    got = normalize_wet_rooms(demand, text)
    return ([(k.kind, k.origin) for k in got.kinds],
            [q for q in got.questions if q.code == "EXTRACTION_MISMATCH"])


# ------------------------------------------------------------------ the four live misses

def test_a_dropped_additional_toilet_is_a_question_and_the_proposal_adds_it():
    """Live miss [30]: 'ועוד שירותים' was filed as a bare mention and absorbed into the ensuite —
    the person's extra toilet vanished without a word."""
    text = "בית עם 3 חדרי שינה, חדר הורים עם מקלחת ושירותים, ועוד שירותים ו2 חניות"
    rooms, questions = _run(text, FixtureDemand(
        attached=[{"host": "MASTER_BEDROOM", "fixtures": "bath", "source_text": "חדר הורים עם מקלחת ושירותים"}],
        toilet_mentions=1, toilet_source_text="ועוד שירותים"))
    assert rooms == [("ensuite", "explicit")]                      # what was extracted, untouched
    (question,) = questions
    assert "ועוד שירותים" in question.text
    assert [(k.kind, k.origin) for k in question.proposal_kinds] == [("ensuite", "explicit"), ("guest_wc", "explicit")]


def test_two_toilets_read_as_separate_rooms_with_no_separateness_in_the_text_is_a_question():
    """Live miss [46]: '2 שירותים' with no marker became two explicit WCs."""
    text = "בית עם 3 חדרי שינה, חדר הורים עם מקלחת, מרפסת, 2 שירותים סלון ומטבח"
    rooms, questions = _run(text, FixtureDemand(attached=[MASTER_BATH],
                                                separate_wcs=[{"source_text": "2 שירותים", "count": 2}]))
    assert rooms == [("ensuite", "explicit"), ("guest_wc", "explicit"), ("guest_wc", "explicit")]
    (question,) = questions
    assert "שירותים נפרדים" in question.text
    # The doubtful rooms are not deleted: the proposal is the list as read, for the person to keep or fix.
    assert [k.kind for k in question.proposal_kinds] == ["ensuite", "guest_wc", "guest_wc"]


@pytest.mark.parametrize("text", [
    "4 חדרי שינה, חדר הורים עם מקלחת, שירותי אורחים סלון ומטבח",                    # live miss [53]
    "בית עם 3 חדרי שינה, חדר הורים עם מקלחת, שירותי אורחים, סלון ומטבח, ועוד חדר שירותים",  # [52]
])
def test_the_masters_shower_listed_again_as_a_standalone_bathroom_is_a_question(text):
    separate = [{"source_text": "שירותי אורחים"}] + (
        [{"source_text": "ועוד חדר שירותים"}] if "ועוד" in text else [])
    rooms, questions = _run(text, FixtureDemand(
        bathrooms=[{"source_text": "מקלחת"}], attached=[MASTER_BATH], separate_wcs=separate))
    assert ("shared_bathroom", "explicit") in rooms                # kept as extracted
    (question,) = questions
    assert "נספר פעמיים" in question.text


def test_a_missed_bare_toilet_mention_beside_a_bathroom_is_not_a_question():
    """Live misses [31]/[45]: 'מקלחת שירותים' lost its toilet mention. Harmless — absorbed either
    way — and the check must not turn a bare שירותים into anything."""
    text = "בית עם 3 חדרי שינה, חדר הורים, מקלחת שירותים סלון ומטבח"
    rooms, questions = _run(text, FixtureDemand(bathrooms=[{"source_text": "מקלחת"}]))
    assert rooms == [("shared_bathroom", "explicit")] and questions == []


# ------------------------------------------------------------------ the phrase families

def test_a_guest_wc_in_the_text_with_no_separate_wc_extracted_is_a_question():
    rooms, questions = _run("3 חדרי שינה, חדר רחצה, שירותי אורחים, סלון ומטבח",
                            FixtureDemand(bathrooms=[{"source_text": "חדר רחצה"}]))
    assert rooms == [("shared_bathroom", "explicit")]
    (question,) = questions
    assert "שירותי אורחים" in question.text
    assert [k.kind for k in question.proposal_kinds] == ["shared_bathroom", "guest_wc"]


def test_a_bathroom_word_with_no_bathroom_extracted_is_a_question_even_on_an_empty_extraction():
    rooms, questions = _run("3 חדרי שינה, מקלחת, סלון ומטבח", FixtureDemand())
    assert rooms == []
    (question,) = questions
    assert "מקלחת" in question.text and [k.kind for k in question.proposal_kinds] == ["shared_bathroom"]
    # ...and the legacy inferred count is what the record keeps meanwhile: nothing invented.
    extraction = normalize_extraction(_brief(demand=FixtureDemand()), "3 חדרי שינה, מקלחת, סלון ומטבח")
    assert (extraction.wet_rooms.value, extraction.wet_rooms.source.value, extraction.wet_room_kinds) == (1, "inferred", [])
    assert [q.code for q in extraction.wet_room_questions] == ["EXTRACTION_MISMATCH"]


def test_attached_wording_with_no_attached_entry_is_a_question_proposing_the_ensuite():
    rooms, questions = _run("3 חדרי שינה, חדר הורים עם מקלחת, שירותי אורחים",
                            FixtureDemand(bathrooms=[{"source_text": "מקלחת"}], separate_wcs=[{"source_text": "שירותי אורחים"}]))
    assert rooms == [("guest_wc", "explicit"), ("shared_bathroom", "explicit")]
    (question,) = questions
    assert "חדר הורים עם מקלחת" in question.text
    assert [(k.kind, k.host) for k in question.proposal_kinds] == [
        ("guest_wc", None), ("shared_bathroom", None), ("ensuite", "MASTER_BEDROOM")]


def test_an_explicit_number_of_toilets_with_fewer_accounted_for_is_a_question():
    rooms, questions = _run("3 חדרי שינה, 2 שירותים, מקלחת, סלון ומטבח",
                            FixtureDemand(bathrooms=[{"source_text": "מקלחת"}]))
    assert rooms == [("shared_bathroom", "explicit")]
    (question,) = questions
    assert "2 שירותים" in question.text
    assert [(k.kind, k.origin) for k in question.proposal_kinds] == [
        ("shared_bathroom", "explicit"), ("guest_wc", "count_derived"), ("guest_wc", "count_derived")]


def test_a_single_bare_toilet_word_is_never_a_question():
    """No heuristic conversion of "שירותים": with nothing else to hold it against, an empty
    extraction of 'חדר הורים, שירותים' passes, and the legacy single bathroom is the right room."""
    rooms, questions = _run("בית עם 3 חדרים חדר הורים, שירותים סלון ומטבח", FixtureDemand())
    assert rooms == [] and questions == []


def test_a_back_reference_to_the_bathrooms_is_not_a_request():
    """'שהחדרי רחצה לא יהיו צמודים' refers to rooms already counted; 'חדרי הרחצה' likewise."""
    text = "2 חדרי שינה, 3 שירותים, ממ״ד, מטבח וסלון שהחדרי רחצה לא יהיו חדרים צמודים"
    _, questions = _run(text, FixtureDemand(toilet_mentions=3, toilet_source_text="3 שירותים"))
    assert questions == []
    text = "3 חדרי שינה, 2 חדרי רחצה, סלון. אני מעדיף שחדרי הרחצה לא יהיו צמודים"
    _, questions = _run(text, FixtureDemand(bathrooms=[{"source_text": "2 חדרי רחצה", "count": 2}]))
    assert questions == []


def test_the_labelled_corpus_raises_no_mismatch_and_an_empty_extraction_never_passes_a_wet_word_brief_silently():
    for brief in CORPUS.values():
        got = normalize_wet_rooms(FixtureDemand.model_validate(brief["demand"]), brief["text"])
        assert [q.code for q in got.questions] == brief["expected"]["questions"], brief["idx"]
    silent = [idx for idx, b in CORPUS.items()
              if not normalize_wet_rooms(FixtureDemand(), b["text"]).questions]
    # The one brief an empty extraction passes is a single bare "שירותים" and nothing else — the
    # word this check must not convert; the legacy path gives it the one bathroom it means.
    assert silent == [42]


def test_without_the_brief_text_the_check_does_not_run():
    got = normalize_wet_rooms(FixtureDemand())
    assert got.questions == []


def test_a_count_the_text_never_wrote_is_a_question():
    """Live repeatability run, brief [03] call 1: nine bathrooms for one 'מקלחת'. Entries matched
    words, so the earlier check passed it; counts are held against the numbers the text writes."""
    text = "בית עם 4 חדרים, חדר הורים, 2 שירותים, מקלחת מטבח וסלון"
    rooms, questions = _run(text, FixtureDemand(bathrooms=[{"source_text": "מקלחת", "count": 9}],
                                                toilet_mentions=2, toilet_source_text="2 שירותים"))
    assert len(rooms) == 9                                          # stored as read, not trimmed
    (question,) = questions
    assert "נספר פעמיים" in question.text
    # ...while a number the text DOES write is not questioned: "2 מקלחות", "שני חדרי רחצה", "3 שירותים".
    for text, demand in [
        ("3 חדרי שינה, 2 מקלחות", FixtureDemand(bathrooms=[{"source_text": "2 מקלחות", "count": 2}])),
        ("שני חדרי רחצה, סלון", FixtureDemand(bathrooms=[{"source_text": "שני חדרי רחצה", "count": 2}])),
        ("3 חדרי שינה, 3 שירותים", FixtureDemand(toilet_mentions=3, toilet_source_text="3 שירותים")),
        ("2 שירותים, מקלחת, סלון ושירותים", FixtureDemand(bathrooms=[{"source_text": "מקלחת"}], toilet_mentions=3)),
    ]:
        assert _run(text, demand)[1] == [], text


def test_more_separate_wcs_than_the_text_writes_is_a_question():
    _, questions = _run("חדר רחצה, שירותי אורחים", FixtureDemand(
        bathrooms=[{"source_text": "חדר רחצה"}], separate_wcs=[{"source_text": "שירותי אורחים", "count": 3}]))
    assert len(questions) == 1 and "שירותים נפרדים" in questions[0].text


def test_more_bare_toilets_than_the_word_appears_is_a_question():
    _, questions = _run("3 חדרי שינה, שירותים, מקלחת", FixtureDemand(
        bathrooms=[{"source_text": "מקלחת"}], toilet_mentions=4, toilet_source_text="שירותים"))
    assert len(questions) == 1 and "נספרו 4 שירותים" in questions[0].text


def test_an_absurd_count_from_the_model_is_clamped_not_expanded():
    """A model can emit any integer. The normalizer bounds every count (`MAX_COUNT`) instead of
    materializing a billion rooms — the scope envelope refuses long before the bound matters."""
    from app.requirements.wet_room_normalizer import MAX_COUNT
    got = normalize_wet_rooms(FixtureDemand(
        bathrooms=[{"source_text": "מקלחת", "count": 10**9}], toilet_mentions=10**9, toilet_source_text="שירותים"),
        "3 חדרי שינה, 999999999 שירותים, מקלחת")
    # Nine bathrooms (clamped), the clamped toilets all absorbed by them — and a question, since
    # the text wrote one bathroom and no such number of toilets.
    assert [k.kind for k in got.kinds] == ["shared_bathroom"] * MAX_COUNT
    assert [q.code for q in got.questions] == ["EXTRACTION_MISMATCH"]
