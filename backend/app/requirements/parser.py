import os
from abc import ABC, abstractmethod
from enum import Enum
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, Field

from app.projects.models import PoolField, SourceTag, TaggedBool, TaggedInt

_SYSTEM_PROMPT = """\
You extract structured home-building requirements from a free-text Hebrew (or mixed-language) \
description written by a person describing the house they want to build.

The built area (square meters) is already known from a separate, structured field the user filled in \
directly — do NOT extract or report a built area from this text; it is not part of your output.

For every field, decide a `source`:
- "requested": the person explicitly stated this value in the text.
- "inferred": reasonably implied by the text but not stated outright.
- "unknown": there is no reasonable basis in the text to determine this value.

Never guess or invent a value. When source is "unknown", `value` MUST be null. Only use "requested" when \
the exact value is explicit in the text.

Special rule for `floors`:
- If the text does not state a floor count at all, output {"value": 1, "source": "inferred"} — a house \
with no stated floor count is assumed to be a single story.
- If the text states conflicting floor counts (e.g. "2 floors" in one sentence and "3 floors" in \
another), output {"value": null, "source": "unknown"} instead — a conflict is not the same as \
"unstated", so do NOT apply the single-story default in that case.
- If the text clearly states one floor count, output that value with source "requested".

Special rule for `bedrooms` (sleeping rooms):
- Count EVERY sleeping room, the master bedroom included. "2 חדרי ילדים וחדר הורים" is 3 bedrooms,
  not 2 — the master is a bedroom. "3 חדרי שינה ובנוסף חדר הורים" is 4.
- A room named for who sleeps in it is a bedroom: חדר ילדים, חדר הורים, חדר שינה, חדר אורחים
  (when described as a room to sleep in).
- A room named for what is DONE in it is not: חדר עבודה, חדר משחקים, חדר כביסה, מחסן, ספרייה.
  Do not count those here. Most go under `other_requests` (see the room-type rule there); a named
  laundry room is the one exception — it has its own field, `laundry` below.
- THE BARE WORD "חדרים" IS THE MOST COMMON WAY PEOPLE SAY THIS, and it has two meanings. Decide by
  whether the public rooms are named separately in the same sentence:
  * The sentence ALSO names סלון / מטבח / פינת אוכל separately — then the plain "N חדרים" are N
    SLEEPING rooms, and any חדר הורים named beside them ADDS to that count.
    "בית עם 4 חדרים, חדר הורים, מטבח וסלון" is 5 bedrooms, source "requested". It is NOT 1.
    Dropping the "4 חדרים" and counting only the חדר הורים is the single worst error you can make
    here — the person asked for five sleeping rooms and would be told their house is unsupported.
  * The sentence says only "דירת/בית N חדרים" with NO other room named — that is the Israeli
    real-estate convention where the count INCLUDES the living room, so bedrooms = N - 1, and the
    source is "inferred" (it is a convention, not something the person said).
- If the text does not state any sleeping rooms at all, output {"value": null, "source": "unknown"}.
  Never assume a bedroom count.

`wet_room_demand` — WHAT THE TEXT SAYS ABOUT BATHROOMS AND TOILETS. You do NOT count rooms here
and you do NOT decide what becomes a room: you sort the WORDS into four lists, and the system turns
them into rooms with fixed rules. In everyday Hebrew "שירותים" can mean a room; here it is a
FIXTURE until the text itself says otherwise — every bathroom contains one, so a bare "שירותים" is
NOT reported as a room. Follow this procedure for every wet-room word, and report every one:

STEP 1 — every מקלחת / חדר רחצה / אמבטיה / חדר אמבטיה that is NOT attached to a bedroom goes in
`bathrooms`. NEVER drop one: "מקלחת" in a comma list ("2 שירותים, מקלחת, סלון") is a bathroom
entry with count 1. A numeral or number word gives `count` ("2 מקלחות" -> 2; "שני חדרי רחצה" -> 2;
"שלושה חדרי רחצה" -> 3). `flexible` is true ONLY when the person says its placement does not
matter or it may be attached to a bedroom ("לא משנה איפה", "יכול להיות צמוד לחדר", "גמיש").

STEP 2 — a wet room ATTACHED TO A BEDROOM by the wording ("חדר הורים עם ...", "... בחדר הורים",
"צמוד לחדר ההורים", "אנסוויט", "באחד מחדרי השינה יש ...", "לכל חדר שינה ...") goes in `attached`.
`host` is "MASTER_BEDROOM" for the parents' room and "BEDROOM" for a child's / secondary bedroom
(count one per such bedroom). `fixtures` is "bath" when a shower, bath or חדר רחצה is named for it
— with or without שירותים: "חדר הורים עם מקלחת", "חדר הורים עם מקלחת ושירותים", "מקלחת בחדר הורים"
— and "toilet_only" when the ONLY thing named for it is שירותים: "חדר הורים עם שירותים". NEVER
upgrade toilet_only to bath: the word שירותים alone does not say there is a shower. ONE PHRASE IS
ONE ENTRY: "חדר הורים עם מקלחת ושירותים" is one attached entry, fixtures "bath", and its שירותים is
NOT counted anywhere else.

STEP 3 — a toilet goes in `separate_wcs` ONLY when the text itself marks it as its own room, with
one of these markers: אורחים ("שירותי אורחים", "שירותים לאורחים"), a location by the entrance
("שירותים ליד הכניסה", "שירותים בכניסה"), נפרד / נפרדים, נוסף / נוספים / ועוד ("ועוד שירותים",
"ועוד חדר שירותים", "שירותים נוספים"), the word חדר ("חדר שירותים"), or an explicit "not a
bathroom" ("תרשום לי שירותים ולא חדר רחצה"). A remark in parentheses or right after a number
applies to that number: "2 שירותים (תרשום לי שירותים ולא חדר רחצה)" is separate_wcs count 2, not
a toilet mention. A numeral gives `count`.

STEP 4 — EVERY OTHER שירותים — a bare "שירותים", "2 שירותים", "3 שירותים" in a list, with no
marker from step 3 and not attached to a bedroom — is a FIXTURE MENTION: add its numeral to
`toilet_mentions` (no numeral = 1) and quote the words in `toilet_source_text`. This is the rule
people get wrong: "3 חדרי שינה, 2 שירותים, מקלחת" is bathrooms=[מקלחת x1], separate_wcs=[],
toilet_mentions=2 — NOT separate_wcs=[2 שירותים]. Whether those toilets become rooms is the
system's decision, not yours.

Worked examples (what the four lists contain):
- "3 חדרי שינה, 2 שירותים, מקלחת, סלון ומטבח" -> bathrooms: [מקלחת, count 1]; attached: [];
  separate_wcs: []; toilet_mentions: 2 ("2 שירותים").
- "חדר רחצה אחד, סלון ומטבח" -> bathrooms: [חדר רחצה אחד, count 1]; everything else empty; toilet_mentions 0.
- "חדר הורים עם מקלחת ושירותים, ועוד שירותים" -> attached: [MASTER_BEDROOM, bath, "חדר הורים עם
  מקלחת ושירותים"]; separate_wcs: [ועוד שירותים, count 1]; toilet_mentions 0.
- "חדר הורים עם שירותים, שירותי אורחים" -> attached: [MASTER_BEDROOM, toilet_only, "חדר הורים עם
  שירותים"]; separate_wcs: [שירותי אורחים, count 1]; toilet_mentions 0.
- "3 חדרי שינה, 3 שירותים, ממ״ד" -> bathrooms: []; separate_wcs: []; toilet_mentions: 3.
- "2 שירותים (תרשום לי שירותים ולא חדר רחצה), מקלחת" -> bathrooms: [מקלחת, 1]; separate_wcs:
  [2 שירותים ... ולא חדר רחצה, count 2]; toilet_mentions 0.
- "חדר הורים עם מקלחת קטנה, מקלחת" -> attached: [MASTER_BEDROOM, bath]; bathrooms: [מקלחת, 1].

If the text says nothing about bathrooms or toilets at all, leave every list empty and
`toilet_mentions` 0 — do not invent a bathroom; the system assumes one. `source_text` quotes the
person's own words for that one entry.

Special rule for `open_plan` (is the kitchen open to the living/dining area?):
- READ NEGATION CAREFULLY. This is the field most easily got wrong.
- Only output {"value": true, "source": "requested"} when the text positively asks for an open, \
connected or shared kitchen/living/dining space ("מטבח פתוח", "מטבח פתוח לסלון", "חלל פתוח").
- If the text asks for a CLOSED or SEPARATE kitchen, or explicitly denies an open one \
("מטבח סגור", "מטבח נפרד", "לא מטבח פתוח", "בלי מטבח פתוח"), output \
{"value": false, "source": "requested"}. A sentence containing the words "מטבח" and "פתוח" is NOT \
automatically an open-plan request — check whether it is being negated.
- If the text says nothing either way, output {"value": false, "source": "inferred"} — do not assume \
an open plan that was never asked for.

`laundry` — WHETHER THE TEXT ASKS FOR A LAUNDRY ROOM OF ITS OWN:
- `requested` is {"value": true, "source": "requested"} ONLY when the text names a SEPARATE ROOM \
for laundry: חדר כביסה, חדר שירות לכביסה, מקום/חדר נפרד למכונת כביסה. Quote the exact phrase in \
`source_text`.
- NEVER infer a room from an appliance mention alone. Mentioning a washing machine or dryer, or a \
laundry corner INSIDE another room, is NOT a room request: "מכונת כביסה במטבח", "יש לי מייבש", \
"פינת כביסה במרפסת" (a corner OF the balcony, not its own room) all stay {"value": false, \
"source": "inferred"} with empty `source_text`. Only a NAMED ROOM counts, exactly as for every \
other room in `other_requests` below (חדר עבודה, מחסן, …) — a laundry room is the one such room \
with its own field instead of going there.
- If the text says nothing about laundry at all, output {"value": false, "source": "inferred"} and \
empty `source_text` — never guess, and never default to "requested".
- When it is genuinely unclear whether the phrase names a room or just an appliance, default to \
false/"inferred" — the same fail-toward-nothing rule as every other field above.

Special rule for `pool`:
- If the text never mentions a pool, `pool.requested` is "unknown" (not false), and `length_m`/`width_m` \
are "unknown" too.
- If the text says a pool is wanted but gives no dimensions, `pool.requested` is {"value": true, \
"source": "requested"}, but `length_m`/`width_m` stay "unknown" — do not invent dimensions.
- If the text gives dimensions, only report them when they are given for the pool specifically.

Special rule for `corridor_width` (the hall / מסדרון / פרוזדור):
- Only report a width when the text gives a NUMBER for the corridor specifically. A corridor
  mentioned without a measurement ("מסדרון רחב", "מסדרון מרווח") is NOT a corridor width — leave
  `value_m` null with source "unknown", and report the phrase under `other_requests` instead.
- `value_m` is in METRES. Convert centimetres ("160 ס\"מ" -> 1.6). Never invent a number.
- `mode` records how it was worded, and the difference matters — do not flatten it:
  - "minimum" for a floor: לפחות, לא פחות מ, מינימום, at least, no less than.
    "המסדרון חייב להיות לפחות 1.6 מטר" is a MINIMUM of 1.6, NOT exactly 1.6.
  - "exact" for a stated width with no floor/ceiling wording: "מסדרון ברוחב 1.8 מטר",
    "אני רוצה מסדרון של 2 מטר".
  - "preference" when the width is wished for rather than required: עדיף, רצוי, אשמח, אם אפשר —
    "אני מעדיף מסדרון של 2 מטר".
- A corridor width reported here must NOT also appear in `other_requests`; it is supported now.

`room_relationships` — HOW ROOMS SHOULD SIT RELATIVE TO EACH OTHER:
- Extract every request about two rooms' relationship. Both rooms must resolve to one of these
  tokens, and to nothing else: MASTER_BEDROOM, BEDROOM (a child's/secondary bedroom),
  SAFE_ROOM (ממ"ד), KITCHEN, LIVING, DINING, BATHROOM, ENSUITE (a bathroom belonging to the master
  bedroom), GUEST_BATHROOM (שירותי אורחים), ENTRANCE (הכניסה).
- `relation` is one of, and these are NOT interchangeable:
  - "adjacent"      — צמוד, נושק, קיר משותף. A shared wall.
  - "direct_access" — ONLY when the wording asks to pass between them: "כניסה מ...", "דלת בין...",
    "יציאה ישירה ל...". "צמוד" alone is NOT direct access.
  - "near"          — קרוב, ליד, בסמוך, לא רחוק. Do NOT upgrade this to "adjacent".
  - "not_adjacent"  — לא צמוד, לא ליד, רחוק מ, שלא יהיה ליד.
- `strength` is "hard_requirement" when worded as binding (חייב, חובה, נדרש, אסור, לא רוצה,
  must, has to) and "preference" when wished for (עדיף, רצוי, אשמח, כדאי, אם אפשר).
  "אני רוצה ש..." is a hard requirement; "אני מעדיף ש..." is a preference.
- `source_text` quotes the person's own words for that one relationship.
- AMBIGUOUS REFERENCES: if a room cannot be resolved to exactly one token — "החדר הגדול",
  "החדר של יוסי", a room this system has no concept of — do NOT guess and do NOT drop it. Set
  `ambiguous` true, leave the unresolved side's token empty, and still quote `source_text`. It is
  reported back for the person to clarify.
- A relationship reported here must NOT also appear in `other_requests`.

`other_requests` — REQUIREMENTS THIS SYSTEM CANNOT YET EXPRESS:
- The fields above are the ONLY requirements the planner can act on. A description often carries
  more: A ROOM THIS SYSTEM CANNOT PLAN — the planner knows only living, dining, kitchen, corridor,
  bedrooms, a safe room, bathrooms and (see `laundry` above) a laundry room, so any OTHER room the
  person asks for must be reported here with topic "room_type": חדר עבודה, מחסן, חדר משחקים, ספרייה,
  מרתף, יחידת דיור, סטודיו, a walk-in closet, a garage as a room. This is the most commonly dropped
  kind of request and the one people notice first, so never let a named room go unreported. Also: dimensions for a space
  OTHER than the corridor ("a 4 m ceiling"), orientation
  ("living room facing south"), style, materials, budget, accessibility, a garden layout, a
  basement, a balcony, storage.
- List each such requirement as one entry, quoting the person's OWN words in `text` (a short phrase,
  not the whole sentence, and never a translation). These are shown back to them as things we
  understood but will not plan, so accuracy of quoting matters more than completeness of coverage.
- `severity` says how binding the wording is. This decides whether a plan may be produced at all,
  so judge the WORDING, never how important the request sounds to you:
  - "hard_requirement" — stated as mandatory or as a limit. Hebrew cues: חייב, חובה, נדרש, אסור,
    בשום אופן, לפחות, לא פחות מ, לכל היותר, מינימום, מקסימום; English: must, has to, required,
    at least, no less than, minimum. A specific number given as a bound is a hard requirement even
    without one of those words ("מסדרון ברוחב 1.8 מטר לפחות").
  - "preference" — stated as a wish or a leaning. Hebrew cues: עדיף, רצוי, אשמח, כדאי, נחמד,
    אם אפשר, במידת האפשר; English: prefer, ideally, would like, nice to have.
  - "ambiguous" — the wording does not settle it: a bare noun phrase or a plain statement with no
    modality at all ("מסדרון רחב", "חדרי רחצה לא צמודים"). When in doubt choose "ambiguous". Do NOT
    guess a severity to be helpful — an ambiguous request stops generation and asks the person,
    which is the correct outcome when we genuinely cannot tell.
- `topic` is a short lowercase English slug for grouping — e.g. "room_adjacency", "corridor_width",
  "orientation", "ceiling_height", "storage", "style", "budget", "outdoor", "accessibility". Use
  "other" when nothing fits.
- Do NOT list anything already covered by the structured fields above: bathrooms and toilets, a bedroom
  count, a safe room, parking, a pool, floors, whether the kitchen is open, a NUMERIC corridor
  width, a NAMED laundry room, or a room RELATIONSHIP between two resolvable rooms. Those are
  extracted, not unsupported. A corridor mentioned WITHOUT a number still belongs here — there is
  nothing to plan from, and so does a laundry APPLIANCE mentioned without a room (see `laundry`).
- Do NOT invent requirements, and do NOT list mere description of the family or the plot. If the
  text asks for nothing beyond the structured fields, return an empty list.
"""


class RequestSeverity(str, Enum):
    """How binding the person's own wording was.

    This is a reading of the TEXT, not a judgement of importance: "עדיף מסדרון רחב" and
    "המסדרון חייב להיות לפחות 1.8 מטר" ask for the same thing and must be treated differently,
    because only one of them can be set aside without the person's agreement.
    """

    PREFERENCE = "preference"
    HARD_REQUIREMENT = "hard_requirement"
    AMBIGUOUS = "ambiguous"


class CorridorWidthMode(str, Enum):
    EXACT = "exact"
    MINIMUM = "minimum"
    PREFERENCE = "preference"


class CorridorWidth(BaseModel):
    """A corridor width the person asked for, in metres, with the modality of their wording.

    `mode` is not decoration: "at least 1.8 m" must never be planned as "exactly 1.8 m", and a
    preferred width may be dropped where a required one may not.
    """

    value_m: float | None = None
    mode: CorridorWidthMode = CorridorWidthMode.MINIMUM
    source: SourceTag = SourceTag.unknown


class RoomRelation(str, Enum):
    ADJACENT = "adjacent"
    DIRECT_ACCESS = "direct_access"
    NEAR = "near"
    NOT_ADJACENT = "not_adjacent"


class RoomRelationship(BaseModel):
    """One requested relationship between two rooms, in role tokens.

    `ambiguous` is how the parser declines to guess: a reference it cannot resolve to exactly one
    room kind is reported, not silently dropped and not silently resolved to whichever room seemed
    likeliest.
    """

    source_role: str = ""
    target_role: str = ""
    relation: RoomRelation = RoomRelation.NEAR
    strength: RequestSeverity = RequestSeverity.PREFERENCE
    source_text: str = ""
    ambiguous: bool = False


class LaundryRoomDemand(BaseModel):
    """Whether the text asks for a laundry room of its own (2026-09-16, phase 1 — see
    docs/LAUNDRY_ROOM_OPTION_REVIEW.md). `requested.source` follows the same convention as every
    other `TaggedBool` field: "requested" when the person named the room, "inferred" when nothing
    in the text does — never "requested" from an appliance mention alone. There is no
    "count_derived" case here the way there is for a wet room: a laundry room is never padded in
    from a number.
    """

    requested: TaggedBool = Field(default_factory=lambda: TaggedBool(value=False, source="inferred"))
    source_text: str = ""


class UnsupportedRequest(BaseModel):
    """One requirement the person asked for that the planner cannot act on.

    These exist so the system stops dropping them in silence. The review screen quotes the whole
    brief back, which made it look as though everything in it had been read — while only the
    structured fields above ever reached the planner. A request for non-adjacent bathrooms or a 5 m
    corridor went nowhere and nothing said so.
    """

    text: str        # the person's own words, quoted
    topic: str = "other"
    #: Defaults to AMBIGUOUS deliberately — fail closed. An unclassified request stops generation
    #: and asks, rather than being quietly downgraded to "just a preference" and planned around.
    severity: RequestSeverity = RequestSeverity.AMBIGUOUS


class WetRoomKindItem(BaseModel):
    """What the brief said about one wet room (specs/007). `kind`/`host`/`strength`/`origin` are the
    plain strings `vertical_slice.spec.WetRoomKind` / `WetRoomStrength` / `WetRoomOrigin` accept; a
    value the vocabulary does not know is a clarification at generation time, never a silent
    default. Produced by `wet_room_normalizer`, never by the model."""

    kind: Literal["shared_bathroom", "ensuite", "guest_wc", "unspecified"] = "unspecified"
    host: Literal["MASTER_BEDROOM", "BEDROOM"] | None = None
    strength: Literal["required", "flexible"] = "required"
    source_text: str = ""
    #: "explicit" — the person named this room; "count_derived" — a number did (a surplus toilet).
    origin: Literal["explicit", "count_derived"] = "explicit"


class NamedBathroom(BaseModel):
    """A bathroom / shower room the text names on its own (not attached to a bedroom)."""

    source_text: str = ""
    count: int = 1
    flexible: bool = False


class AttachedWetRoom(BaseModel):
    """A wet room the text attaches to a bedroom. `fixtures` is what the text NAMES for it: "bath"
    when a shower/bath is named (with or without a toilet), "toilet_only" when only שירותים is —
    the difference between an ensuite and a question (see `wet_room_normalizer`)."""

    host: Literal["MASTER_BEDROOM", "BEDROOM"] = "MASTER_BEDROOM"
    fixtures: Literal["bath", "toilet_only"] = "bath"
    source_text: str = ""
    count: int = 1


class SeparateWC(BaseModel):
    """A toilet the text names as its own room: guest WC, an additional toilet, "not a bathroom"."""

    source_text: str = ""
    count: int = 1


class FixtureDemand(BaseModel):
    """WHAT THE BRIEF SAYS about bathrooms and toilets, as words sorted into lists — never as rooms.

    This is the model's whole job on the subject. Turning it into rooms is `wet_room_normalizer`'s,
    with rules that can be read and tested: a toilet is a fixture every bathroom already holds, so
    a bare "שירותים" becomes a room only when no bathroom is left to hold it. Before this existed
    the model was asked for a room COUNT, and it counted every "שירותים" as a room in 16 of the 29
    corpus briefs that also named a bathroom (measured 2026-09-15).
    """

    bathrooms: list[NamedBathroom] = Field(default_factory=list)
    attached: list[AttachedWetRoom] = Field(default_factory=list)
    separate_wcs: list[SeparateWC] = Field(default_factory=list)
    toilet_mentions: int = 0
    toilet_source_text: str = ""


class WetRoomQuestion(BaseModel):
    """A reading of the brief the normalizer will not settle alone, with the answer it proposes.

    `proposal_kinds` is the FULL wet-room list that would answer it (the stated rooms plus the
    proposed one), before `wet_rooms.complete_with_shared_bathroom` adds whatever I4 still needs
    for the house's bedroom count — that part depends on `bedrooms`, so it is applied where the
    question is shown, not stored.
    """

    code: Literal["ATTACHED_TOILET_ONLY", "TOILETS_WITHOUT_BATHROOM", "EXTRACTION_MISMATCH"]
    text: str
    source_text: str = ""
    proposal_kinds: list[WetRoomKindItem] = Field(default_factory=list)


class BriefExtraction(BaseModel):
    """What the MODEL returns. No wet-room count and no wet-room kinds live here: the count is
    derived from the rooms the normalizer builds out of `wet_room_demand`, never produced by the
    model on its own (the parser used to ask for one, and it was the least stable number it gave —
    the same brief came back as 1, 3 and 3 on three parses)."""

    floors: TaggedInt
    bedrooms: TaggedInt
    safe_room: TaggedBool
    parking_spaces: TaggedInt
    pool: PoolField
    open_plan: TaggedBool = Field(default_factory=lambda: TaggedBool(value=None, source="unknown"))
    #: Whether a laundry room was named (2026-09-16, phase 1). Defaulted so extractions built
    #: before this field existed still validate, to "not requested" — the honest reading of a
    #: brief that never mentions this field at all.
    laundry: LaundryRoomDemand = Field(default_factory=LaundryRoomDemand)
    #: Requirements found in the brief that no structured field can carry. Defaulted so extractions
    #: built before this field existed still validate.
    other_requests: list[UnsupportedRequest] = Field(default_factory=list)
    #: Defaulted so extractions built before this field existed still validate.
    room_relationships: list[RoomRelationship] = Field(default_factory=list)
    corridor_width: CorridorWidth = Field(
        default_factory=lambda: CorridorWidth(value_m=None, source=SourceTag.unknown))
    wet_room_demand: FixtureDemand = Field(default_factory=FixtureDemand)


class RequirementExtraction(BriefExtraction):
    """The brief as the rest of the system reads it: `BriefExtraction` plus the wet rooms the
    normalizer derived from its demand. Constructed directly by tests and fakes; the live parser
    builds it through `normalize_extraction`."""

    # Defaulted to "unknown" so extractions constructed before this field existed still validate;
    # the live path always fills it from the normalizer.
    wet_rooms: TaggedInt = Field(default_factory=lambda: TaggedInt(value=None, source="unknown"))
    #: What the brief said about each wet room, in order (specs/007). Empty for extractions made
    #: before the field existed — every wet room unspecified, the programme a bare count gives.
    wet_room_kinds: list[WetRoomKindItem] = Field(default_factory=list)
    #: Readings the normalizer would not settle alone. Each blocks generation until answered.
    wet_room_questions: list[WetRoomQuestion] = Field(default_factory=list)


class RequirementParser(ABC):
    @abstractmethod
    def parse(self, description: str) -> RequirementExtraction: ...


#: Allowed values of the `reasoning_effort` request parameter (and of the
#: REQUIREMENTS_REASONING_EFFORT env override) — everything the OpenAI Chat Completions API accepts
#: for a reasoning model as of openai 3.7.0.
_REASONING_EFFORTS = ("minimal", "low", "medium", "high")


class OpenAIRequirementParser(RequirementParser):
    """Extracts RequirementExtraction via OpenAI's gpt-5-nano (cheapest current model, confirmed via
    platform.openai.com/docs/pricing) using structured outputs. See
    specs/002-requirement-parser/research.md for the model choice and the accepted trade-off: adherence
    to the "never guess" instructions above is the model's instruction-following, not a hard guarantee.

    `reasoning_effort` defaults to "minimal" (Issue #89): gpt-5-nano is a reasoning model, and this
    extraction is a simple structured read of the brief, not a task that benefits from its default
    reasoning budget — measured ~10x faster at "minimal" with the same schema/prompt. Override via
    REQUIREMENTS_REASONING_EFFORT for comparison; an unrecognised value fails fast at construction
    rather than being silently sent to the API.
    """

    def __init__(self, model: str = "gpt-5-nano", reasoning_effort: str = "minimal") -> None:
        self._model = model
        reasoning_effort = os.environ.get("REQUIREMENTS_REASONING_EFFORT", reasoning_effort)
        if reasoning_effort not in _REASONING_EFFORTS:
            raise ValueError(
                f"Unsupported REQUIREMENTS_REASONING_EFFORT {reasoning_effort!r}; "
                f"expected one of {_REASONING_EFFORTS}"
            )
        self._reasoning_effort = reasoning_effort
        # Deliberately does not require OPENAI_API_KEY at construction — only when parse() is actually
        # called — so importing this module (e.g. via app.main during tests) never needs the key set.
        self._client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    def parse(self, description: str) -> RequirementExtraction:
        return normalize_extraction(self.extract(description), description)

    def extract(self, description: str) -> BriefExtraction:
        """The model's own output, before the wet rooms are derived. Exposed for measurement."""
        response = self._client.chat.completions.parse(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": description},
            ],
            response_format=BriefExtraction,
            reasoning_effort=self._reasoning_effort,
        )
        parsed = response.choices[0].message.parsed
        assert parsed is not None
        return parsed


def normalize_extraction(brief: BriefExtraction, description: str = "") -> RequirementExtraction:
    """`BriefExtraction` -> `RequirementExtraction`: the wet rooms derived from the demand by
    `wet_room_normalizer` (R1–R5). With the brief's own text, the demand is also held against it
    (`wet_room_normalizer.extraction_mismatches`): a strong wet-room phrase the model did not
    report, or a room it reported that the text never names, is a question — never a silent
    programme with a room too few or too many."""
    from app.requirements.wet_room_normalizer import normalize_wet_rooms

    normalized = normalize_wet_rooms(brief.wet_room_demand, description)
    return RequirementExtraction(
        **brief.model_dump(),
        wet_rooms=normalized.wet_rooms,
        wet_room_kinds=normalized.kinds,
        wet_room_questions=normalized.questions,
    )
