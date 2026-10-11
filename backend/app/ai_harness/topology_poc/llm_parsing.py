"""Robust-but-honest parsing of raw LLM text into a list of raw proposal dicts.

A local 3B model does not reliably emit clean JSON (stray prose before/after the array, an
occasional truncated tail). This module extracts the outermost JSON array by bracket balancing
(ignoring brackets inside string literals) and returns EVERY top-level element it can `json.loads`
as a dict — a malformed element is dropped and counted, never silently merged or repaired into a
different shape. Nothing here relaxes `schema.proposal_from_dict`'s own validation: this module
only gets raw text to a list of dicts; `schema.py` still decides whether each dict is a valid
proposal.
"""
from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class ParseOutcome:
    raw_dicts: tuple  # tuple[dict, ...] — successfully JSON-decoded top-level array elements
    array_found: bool
    elements_seen: int
    elements_malformed: int


def _find_outer_array(text: str) -> "str | None":
    start = text.find("[")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def parse_proposals_array(raw_text: str) -> ParseOutcome:
    array_text = _find_outer_array(raw_text)
    if array_text is None:
        return ParseOutcome(raw_dicts=(), array_found=False, elements_seen=0, elements_malformed=0)

    try:
        elements = json.loads(array_text)
    except json.JSONDecodeError:
        # try element-by-element recovery: split top-level array by scanning for `},{` boundaries
        # at depth 1 is fragile, so we deliberately do NOT attempt it — an array that does not
        # parse as a whole is honestly reported as zero usable proposals from this call, not a
        # guessed partial one.
        return ParseOutcome(raw_dicts=(), array_found=True, elements_seen=0, elements_malformed=0)

    if not isinstance(elements, list):
        return ParseOutcome(raw_dicts=(), array_found=True, elements_seen=0, elements_malformed=0)

    good = []
    malformed = 0
    for element in elements:
        if isinstance(element, dict):
            good.append(element)
        else:
            malformed += 1
    return ParseOutcome(raw_dicts=tuple(good), array_found=True,
                        elements_seen=len(elements), elements_malformed=malformed)
