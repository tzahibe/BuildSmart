import os
from abc import ABC, abstractmethod

from openai import OpenAI
from pydantic import BaseModel

from app.projects.models import PoolField, TaggedBool, TaggedInt

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

Special rule for `pool`:
- If the text never mentions a pool, `pool.requested` is "unknown" (not false), and `length_m`/`width_m` \
are "unknown" too.
- If the text says a pool is wanted but gives no dimensions, `pool.requested` is {"value": true, \
"source": "requested"}, but `length_m`/`width_m` stay "unknown" — do not invent dimensions.
- If the text gives dimensions, only report them when they are given for the pool specifically.
"""


class RequirementExtraction(BaseModel):
    floors: TaggedInt
    bedrooms: TaggedInt
    safe_room: TaggedBool
    parking_spaces: TaggedInt
    pool: PoolField


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
