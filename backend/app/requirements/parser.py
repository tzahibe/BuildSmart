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
  Do not count those here — report them under `other_requests` (see the room-type rule there).
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

Special rule for `wet_rooms` (bathrooms / shower rooms / toilet rooms):
- Count every bathroom or shower room the person asks for, including an en-suite attached to a \
bedroom. A separate guest toilet counts as one.
- If the text does not mention bathrooms at all, output {"value": 1, "source": "inferred"} — a house \
with no stated bathroom count is assumed to have one.
- If the text states a count, output it with source "requested".
- ONE ROOM CONTAINING BOTH a shower and a toilet is ONE wet room: "חדר הורים עם מקלחת ושירותים" adds
  one, not two. Separate rooms are separate: a שירותי אורחים in addition to that master en-suite
  makes two.
- An en-suite described as part of a bedroom still counts, and the count is the TOTAL for the house.

`wet_room_kinds` — WHAT EACH WET ROOM IS, in the order the text names them (one item per wet room,
never more than `wet_rooms`; fewer is fine — the rest are unstated):
- "ensuite" with host "MASTER_BEDROOM": a bathroom/shower belonging to the master bedroom — "חדר הורים עם מקלחת", "חדר הורים עם שירותים", "אנסוויט", "חדר רחצה צמוד לחדר ההורים".
- "ensuite" with host "BEDROOM": a bathroom belonging to a child's/secondary bedroom — "חדר רחצה לחדר הילדים", "לכל חדר שינה חדר רחצה צמוד" (one item PER such bedroom).
- "guest_wc": שירותי אורחים / שירותים לאורחים / שירותים ליד הכניסה — a WC, not a full bathroom.
- "shared_bathroom": a bathroom or shower room named without belonging to any bedroom — "חדר רחצה", "מקלחת", "חדר אמבטיה".
- "unspecified": the text only COUNTS ("3 חדרי רחצה") and says nothing about a room's kind. Use it for every counted room the text does not describe. When in doubt, "unspecified" — never guess a kind.
- `strength` is "flexible" ONLY when the person says the room's placement does not matter or may be attached to a bedroom ("לא משנה איפה", "יכול להיות צמוד לחדר", "גמיש"); otherwise "required".
- `source_text` quotes the person's own words for that one room.
- `host` is null for every kind but "ensuite".

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
  bedrooms, a safe room and bathrooms, so any OTHER room the person asks for must be reported here
  with topic "room_type": חדר עבודה, חדר כביסה, מחסן, חדר משחקים, ספרייה, מרתף, יחידת דיור, סטודיו,
  a walk-in closet, a garage as a room. This is the most commonly dropped kind of request and the
  one people notice first, so never let a named room go unreported. Also: dimensions for a space
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
- Do NOT list anything already covered by the structured fields above: a bathroom count, a bedroom
  count, a safe room, parking, a pool, floors, whether the kitchen is open, a NUMERIC corridor
  width, or a room RELATIONSHIP between two resolvable rooms. Those are extracted, not unsupported.
  A corridor mentioned WITHOUT a number still belongs here — there is nothing to plan from.
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
    """What the brief said about one wet room (specs/007). `kind`/`host`/`strength` are the plain
    strings `vertical_slice.spec.WetRoomKind` / `WetRoomStrength` accept; a value the vocabulary does
    not know is a clarification at generation time, never a silent default."""

    kind: Literal["shared_bathroom", "ensuite", "guest_wc", "unspecified"] = "unspecified"
    host: Literal["MASTER_BEDROOM", "BEDROOM"] | None = None
    strength: Literal["required", "flexible"] = "required"
    source_text: str = ""


class RequirementExtraction(BaseModel):
    floors: TaggedInt
    bedrooms: TaggedInt
    safe_room: TaggedBool
    parking_spaces: TaggedInt
    pool: PoolField
    # Added for the demo path: `ProgramSpec` needs both, and neither was extracted before.
    # Defaulted to "unknown" so extractions constructed before these fields existed still validate;
    # the live prompt above always fills them.
    wet_rooms: TaggedInt = Field(default_factory=lambda: TaggedInt(value=None, source="unknown"))
    open_plan: TaggedBool = Field(default_factory=lambda: TaggedBool(value=None, source="unknown"))
    #: Requirements found in the brief that no structured field can carry. Defaulted so extractions
    #: built before this field existed still validate.
    other_requests: list[UnsupportedRequest] = Field(default_factory=list)
    #: Defaulted so extractions built before this field existed still validate.
    room_relationships: list[RoomRelationship] = Field(default_factory=list)
    #: What the brief said about each wet room, in order (specs/007). Empty for extractions made
    #: before the field existed — every wet room unspecified, the programme a bare count gives.
    wet_room_kinds: list[WetRoomKindItem] = Field(default_factory=list)
    corridor_width: CorridorWidth = Field(
        default_factory=lambda: CorridorWidth(value_m=None, source=SourceTag.unknown))


class RequirementParser(ABC):
    @abstractmethod
    def parse(self, description: str) -> RequirementExtraction: ...


class OpenAIRequirementParser(RequirementParser):
    """Extracts RequirementExtraction via OpenAI's gpt-5-nano (cheapest current model, confirmed via
    platform.openai.com/docs/pricing) using structured outputs. See
    specs/002-requirement-parser/research.md for the model choice and the accepted trade-off: adherence
    to the "never guess" instructions above is the model's instruction-following, not a hard guarantee.
    """

    def __init__(self, model: str = "gpt-5-nano") -> None:
        self._model = model
        # Deliberately does not require OPENAI_API_KEY at construction — only when parse() is actually
        # called — so importing this module (e.g. via app.main during tests) never needs the key set.
        self._client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    def parse(self, description: str) -> RequirementExtraction:
        response = self._client.chat.completions.parse(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": description},
            ],
            response_format=RequirementExtraction,
        )
        parsed = response.choices[0].message.parsed
        assert parsed is not None
        return parsed
