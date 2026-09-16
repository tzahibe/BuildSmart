"""From what the brief SAYS about bathrooms and toilets to the wet ROOMS the house gets — by rule.

The model reports words (`parser.FixtureDemand`); this module decides rooms, so that the decision can
be read, tested and argued with. The rules, in the order they run:

    R1  Named rooms first. Every bathroom named on its own is a SHARED_BATHROOM; every toilet named
        as its own room (guest WC, an additional toilet, "not a bathroom") is a GUEST_WC. Both are
        EXPLICIT: the person said "room".
    R2  One phrase, one room. A wet room attached to a bedroom with a shower or bath named for it
        is that bedroom's ENSUITE — with or without the word שירותים; the toilet inside it is a
        fixture, not a second room. An attachment that names ONLY שירותים ("חדר הורים עם שירותים")
        is NOT upgraded to a bathroom: the engine plans a toilet attached to a bedroom only as
        part of a full bathroom, and whether that is what was meant is a QUESTION
        (`ATTACHED_TOILET_ONLY`), proposed answer: an ensuite.
    R3  Absorb, then surplus. Every bathroom and ensuite already holds a toilet, so bare "שירותים"
        mentions are absorbed by them first; only the surplus becomes a GUEST_WC, and such a room
        is COUNT_DERIVED — a number made it, not the person.
    R4  Toilets with no bathroom. One bare "שירותים" and nothing else is the house's one bathroom.
        Two or more with no bathroom named ("3 חדרי שינה, 3 שירותים") is ambiguous in Hebrew
        (N bathrooms, or one bathroom and N-1 toilets) and was parsed as 1, 2 and 3 for the same
        text before this existed — so it is a QUESTION (`TOILETS_WITHOUT_BATHROOM`), with the
        absorbing reading as the proposed answer: one shared bathroom plus N-1 derived WCs. The
        proposal is also what is stored meanwhile, tagged as derived, so the record is coherent.
    R5  The count follows the rooms. `wet_rooms` is the length of the list — never a number the
        model produced. Nothing said about wet rooms at all keeps the legacy reading: count 1,
        source "inferred", no kinds, so `default_wet_room_kinds` plans it exactly as before.

Order within the list is fixed — ensuites, then WCs, then shared bathrooms — which is the order the
legacy bare-count default already used (the guest WC wants to stay near the entrance), so a brief
that reads the same either way gets the same rows in the same order.

What this never does: remove a room the person asked for, or optimise for fewer toilets. A named
WC is built; a surplus toilet is built. Only a toilet that already has a bathroom to live in stays
a fixture.

THE BACKSTOP (`extraction_mismatches`). The demand comes from a model, and a model can drop a
phrase or read one twice. Given the brief's own text, a few STRONG wet-room phrases are held
against the demand — a guest or additional WC, a bathroom word, a wet room attached to a bedroom,
an explicit "N שירותים" — and a phrase with no entry behind it, or an entry with no phrase behind
it, is a QUESTION (`EXTRACTION_MISMATCH`). The rooms stored are exactly what was extracted (the
missing room is never invented, the doubtful one never deleted); the proposal shows the likely
reading. This is a consistency check, not a second parser: it counts phrases it can name, and it
does not turn a bare "שירותים" into anything.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.projects.models import TaggedInt
from app.requirements.parser import FixtureDemand, WetRoomKindItem, WetRoomQuestion


#: The most rooms one demand entry may stand for. A model can emit any integer; a count past this
#: is not a house, and expanding it would only build a list nobody can plan. The scope envelope
#: (`demo.scope.SUPPORTED_WET_ROOMS`) refuses long before this bound matters.
MAX_COUNT = 9


def _n(count: int) -> int:
    return max(0, min(MAX_COUNT, count))


@dataclass(frozen=True)
class NormalizedWetRooms:
    wet_rooms: TaggedInt
    kinds: list[WetRoomKindItem] = field(default_factory=list)
    questions: list[WetRoomQuestion] = field(default_factory=list)


def _ensuite(host: str, source_text: str, origin: str = "explicit") -> WetRoomKindItem:
    return WetRoomKindItem(kind="ensuite", host=host, source_text=source_text, origin=origin)


def _shared(source_text: str = "", flexible: bool = False, origin: str = "explicit") -> WetRoomKindItem:
    return WetRoomKindItem(kind="shared_bathroom", strength="flexible" if flexible else "required",
                           source_text=source_text, origin=origin)


def _wc(source_text: str = "", origin: str = "explicit") -> WetRoomKindItem:
    return WetRoomKindItem(kind="guest_wc", source_text=source_text, origin=origin)


def _attached_toilet_question(host: str, source_text: str) -> str:
    room = "חדר ההורים" if host == "MASTER_BEDROOM" else "חדר השינה"
    return (f'כתבת "{source_text}". לא ברור אם הכוונה לחדר רחצה צמוד ל{room} (מקלחת ושירותים) או '
            f"לשירותים בלבד. המתכנן יודע כרגע לצרף לחדר שינה רק חדר רחצה מלא — לא נוסיף מקלחת "
            f"בלי לשאול. אם זה מה שרצית, אפשר לאשר את ההצעה; אחרת אפשר לתקן את רשימת חדרי הרחצה "
            f"או את התיאור.")


def _toilets_only_question(count: int, source_text: str) -> str:
    return (f'כתבת "{source_text}" בלי לציין חדר רחצה. לא ברור אם הכוונה ל-{count} חדרי רחצה או '
            f"לחדר רחצה אחד ועוד {count - 1} שירותים נפרדים. ההצעה: חדר רחצה אחד ועוד {count - 1} "
            f"שירותים — אפשר לאשר או לתקן את הרשימה.")


def normalize_wet_rooms(demand: FixtureDemand, description: str = "") -> NormalizedWetRooms:
    """R1–R5 over one brief's demand; with `description`, the backstop too. Pure: the same demand
    and text always give the same rooms and the same questions."""
    ensuites: list[WetRoomKindItem] = []
    wcs: list[WetRoomKindItem] = []
    shared: list[WetRoomKindItem] = []
    questions: list[WetRoomQuestion] = []

    # R1 — rooms the person named as rooms.
    for bath in demand.bathrooms:
        shared.extend(_shared(bath.source_text, bath.flexible) for _ in range(_n(bath.count)))
    for wc in demand.separate_wcs:
        wcs.extend(_wc(wc.source_text) for _ in range(_n(wc.count)))

    # R2 — attachments: a bath makes an ensuite; a toilet alone makes a question.
    pending_ensuites: list[WetRoomKindItem] = []
    for att in demand.attached:
        for _ in range(_n(att.count)):
            if att.fixtures == "bath":
                ensuites.append(_ensuite(att.host, att.source_text))
            else:
                pending_ensuites.append(_ensuite(att.host, att.source_text))
                questions.append(WetRoomQuestion(
                    code="ATTACHED_TOILET_ONLY",
                    text=_attached_toilet_question(att.host, att.source_text),
                    source_text=att.source_text))

    # R3 — absorb bare toilets into the bathrooms that exist; the surplus becomes derived WCs.
    # No bathroom at all means nothing absorbs: "שירותי אורחים, שירותים" keeps both toilets.
    toilets = _n(demand.toilet_mentions)
    holders = len(ensuites) + len(shared)
    surplus = max(0, toilets - holders)

    # R4 — toilets named where no bathroom is: one is the bathroom; two or more is a question.
    if toilets and not holders and not wcs and not pending_ensuites:
        shared.append(_shared(demand.toilet_source_text, origin="count_derived"))
        surplus = toilets - 1
        if toilets >= 2:
            questions.append(WetRoomQuestion(
                code="TOILETS_WITHOUT_BATHROOM",
                text=_toilets_only_question(toilets, demand.toilet_source_text),
                source_text=demand.toilet_source_text))
    wcs.extend(_wc(demand.toilet_source_text, origin="count_derived") for _ in range(surplus))

    kinds = ensuites + wcs + shared

    # A question's proposal is the FULL list that answers it. Every attached-toilet question
    # proposes every pending ensuite at once: answering one answers the reading, not one phrase.
    for question in questions:
        if question.code == "ATTACHED_TOILET_ONLY":
            question.proposal_kinds = ensuites + pending_ensuites + wcs + shared
        else:
            question.proposal_kinds = list(kinds)

    if description:
        questions.extend(extraction_mismatches(description, demand, kinds))

    # R5 — the count is the list. Nothing said at all is the legacy inferred single bathroom.
    mentioned = bool(demand.bathrooms or demand.attached or demand.separate_wcs or toilets)
    if not mentioned:
        return NormalizedWetRooms(TaggedInt(value=1, source="inferred"), [], questions)
    return NormalizedWetRooms(TaggedInt(value=len(kinds), source="requested"), kinds, questions)


# ------------------------------------------------------------------ the backstop

#: A bathroom named as a room. A definite form ("חדרי הרחצה", "שהחדרי רחצה") is a reference to
#: rooms already asked for — a relationship clause, not a request — and is excluded by the
#: lookbehind and by the article inside the construct.
_BATH_WORD = re.compile(r"(?<!ה)(?:חדרי? רחצה|חדרי? אמבטי(?:ה|ות)|מקלח(?:ת|ות)|אמבטי(?:ה|ות))")
#: A wet room attached to a bedroom by the wording.
_ATTACHED = re.compile(
    r"חדר הורים(?: גדול| קטן)? עם (?:מקלחת|שירותים|חדר רחצה|אמבטיה)"
    r"|(?:מקלחת|שירותים|חדר רחצה) בחדר ה?הורים"
    r"|אנסוויט|צמודה? לחדר ההורים|חדר רחצה צמוד"
    r"|ב(?:אחד מ)?חדרי? השינה יש(?: גם)? (?:מקלחת|שירותים)"
    r"|לכל חדר שינה חדר רחצה")
#: A toilet named as its own room: guests, the entrance, "another", "separate", "a toilet room",
#: "and not a bathroom". The definite "שירותי האורחים" is a back-reference and does not match.
_SEPARATE_WC = re.compile(
    r"שירותי אורחים|שירותים לאורחים|שירותים (?:ליד ה|ב)כניסה"
    r"|ו?עוד (?:חדר )?שירותים|שירותים נוספ(?:ים|ת)|חדר שירותים(?: נוסף)?"
    r"|שירותים נפרד(?:ים)?|שירותים ולא חדר רחצה")
#: An explicit number of toilets — "2 שירותים" — is a count the person wrote down.
_NUMBERED_TOILETS = re.compile(r"(\d+) שירותים")
#: A number written before a wet-room word: a digit, or a Hebrew number word up to five.
_NUMBER_WORDS = {"שני": 2, "שתי": 2, "שניים": 2, "שתיים": 2, "שלושה": 3, "שלוש": 3, "ארבעה": 4, "ארבע": 4,
                 "חמישה": 5, "חמש": 5}
_NUMBER_BEFORE = re.compile(r"(\d+|" + "|".join(_NUMBER_WORDS) + r")\s+$")
_TOILET_WORD = re.compile(r"שירותי(?:ם|)")


def _written_count(text: str, match: re.Match) -> int:
    """How many rooms the text writes for one wet-room word: its preceding number, else one."""
    lead = _NUMBER_BEFORE.search(text[:match.start()])
    if lead is None:
        return 1
    token = lead.group(1)
    return int(token) if token.isdigit() else _NUMBER_WORDS[token]


def _mismatch(text: str, source_text: str, proposal: list[WetRoomKindItem]) -> WetRoomQuestion:
    return WetRoomQuestion(code="EXTRACTION_MISMATCH", text=text, source_text=source_text,
                           proposal_kinds=proposal)


def extraction_mismatches(description: str, demand: FixtureDemand,
                          kinds: list[WetRoomKindItem]) -> list[WetRoomQuestion]:
    """Strong wet-room phrases in the brief against the demand the model reported — the questions
    the difference raises, in a fixed order. `kinds` is what was normalized from the demand; every
    proposal starts from it, so accepting a question keeps everything that WAS read."""
    text = " ".join(description.split())
    bath_matches = list(_BATH_WORD.finditer(text))
    bath_words = [m.group(0) for m in bath_matches]
    attached_words = _ATTACHED.findall(text)
    separate_matches = list(_SEPARATE_WC.finditer(text))
    separate_words = [m.group(0) for m in separate_matches]
    numbered = _n(max((int(n) for n in _NUMBERED_TOILETS.findall(text)), default=0))
    # The most rooms the text WRITES for each family: each word, times its number if one precedes it.
    bath_written = sum(_written_count(text, m) for m in bath_matches)
    toilet_written = sum(_written_count(text, m) for m in _TOILET_WORD.finditer(text))
    # "2 שירותים (תרשום לי שירותים ולא חדר רחצה)": the number stands before the toilet word, the
    # marker after it — an explicit "N שירותים" licenses N separate WCs too.
    separate_written = max(sum(_written_count(text, m) for m in separate_matches), numbered)

    bath_entries = len(demand.bathrooms) + sum(1 for a in demand.attached if a.fixtures == "bath")
    bath_total = (sum(_n(b.count) for b in demand.bathrooms)
                  + sum(_n(a.count) for a in demand.attached if a.fixtures == "bath"))
    separate_count = sum(_n(w.count) for w in demand.separate_wcs)
    toilets_accounted = (_n(demand.toilet_mentions) + separate_count
                         + sum(_n(a.count) for a in demand.attached if a.fixtures == "toilet_only"))
    questions: list[WetRoomQuestion] = []

    # A guest / additional / separate WC the text names, with fewer WC entries behind it.
    if len(separate_words) > separate_count:
        missing = len(separate_words) - separate_count
        phrase = ", ".join(f'"{w}"' for w in separate_words)
        questions.append(_mismatch(
            f"בתיאור כתוב {phrase}, אבל בקריאה שלנו נמצאו {separate_count} שירותים נפרדים. לא נוסיף "
            f"חדר בניחוש — אפשר לאשר את ההצעה (עם השירותים הנפרדים) או לתקן את הרשימה.",
            separate_words[0], kinds + [_wc(w) for w in separate_words[-missing:]]))

    # A bathroom word with no bathroom or ensuite behind it.
    if bath_words and bath_entries == 0:
        questions.append(_mismatch(
            f'בתיאור כתוב "{bath_words[0]}", אבל בקריאה שלנו לא נמצא חדר רחצה. לא נוסיף חדר בניחוש '
            f"— אפשר לאשר את ההצעה (עם חדר רחצה משותף) או לתקן את הרשימה.",
            bath_words[0], kinds + [_shared(bath_words[0])]))

    # A wet room attached to a bedroom by the wording, with no attached entry behind it.
    if attached_words and not demand.attached:
        host = "MASTER_BEDROOM" if "הורים" in attached_words[0] else "BEDROOM"
        questions.append(_mismatch(
            f'בתיאור כתוב "{attached_words[0]}", אבל בקריאה שלנו לא נמצא חדר רחצה צמוד לחדר שינה. '
            f"לא נוסיף חדר בניחוש — אפשר לאשר את ההצעה (חדר רחצה צמוד) או לתקן את הרשימה.",
            attached_words[0], kinds + [_ensuite(host, attached_words[0])]))

    # "N שירותים" written out, with fewer toilets accounted for anywhere in the demand.
    if numbered > toilets_accounted:
        deficit = numbered - toilets_accounted
        questions.append(_mismatch(
            f'בתיאור כתוב "{numbered} שירותים", אבל בקריאה שלנו נספרו {toilets_accounted}. לא נוסיף '
            f"חדר בניחוש — אפשר לאשר את ההצעה או לתקן את הרשימה.",
            f"{numbered} שירותים", kinds + [_wc(f"{numbered} שירותים", origin="count_derived")] * deficit))

    # More bathrooms read than the text writes — a shower counted twice, or a number nobody wrote.
    if bath_entries > len(bath_words) or bath_total > bath_written:
        questions.append(_mismatch(
            f"בקריאה שלנו נמצאו {max(bath_entries, bath_total)} חדרי רחצה, אבל בתיאור כתובים "
            f"{bath_written} — ייתכן שנספר פעמיים. אפשר לאשר את הרשימה כפי שהיא או לתקן אותה.",
            bath_words[0] if bath_words else "", list(kinds)))

    # Separate WCs read where the text never marks a toilet as its own room, or more of them
    # than the text writes.
    if demand.separate_wcs and (not separate_words or separate_count > separate_written):
        questions.append(_mismatch(
            f"בקריאה שלנו נמצאו {separate_count} שירותים נפרדים, אבל בתיאור כתובים {separate_written} "
            f"(שירותים הם חדר נפרד רק כשכתוב כך — למשל שירותי אורחים, שירותים נוספים). "
            f"אפשר לאשר את הרשימה כפי שהיא או לתקן אותה.",
            demand.separate_wcs[0].source_text, list(kinds)))

    # More bare toilets counted than the word appears or a number says.
    if _n(demand.toilet_mentions) > toilet_written:
        questions.append(_mismatch(
            f"בקריאה שלנו נספרו {_n(demand.toilet_mentions)} שירותים, אבל בתיאור כתובים {toilet_written}. "
            f"אפשר לאשר את הרשימה כפי שהיא או לתקן אותה.",
            demand.toilet_source_text, list(kinds)))

    # An attached wet room read where the text attaches nothing to a bedroom.
    if demand.attached and not attached_words:
        questions.append(_mismatch(
            f"בקריאה שלנו נמצא חדר רחצה צמוד לחדר שינה, אבל בתיאור לא כתוב שחדר רחצה צמוד לחדר "
            f"(למשל \"חדר הורים עם מקלחת\"). אפשר לאשר את הרשימה כפי שהיא או לתקן אותה.",
            demand.attached[0].source_text, list(kinds)))
    return questions
