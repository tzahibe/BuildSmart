# Requirements / Parsing Semantics

Status: IMPLEMENTED_MERGED

## Current behavior

`OpenAIRequirementParser` (`app/requirements/parser.py`) is the **only** LLM in the product
path — it extracts structured fields (`floors`, `bedrooms`, `safe_room`, `parking_spaces`, `pool`,
`open_plan`, `wet_room_demand`, `other_requests`, `room_relationships`, `corridor_width`) from
free-text Hebrew/English briefs into `RequirementExtraction`/`BriefExtraction` Pydantic models.
Everything downstream of that extraction is deterministic, rule-based code — see Wet Rooms for
`wet_room_normalizer.py`'s R1–R5 rules, and Geometry/Validation for what happens after.

`public_open_side` is **not** LLM-extracted — it's a structured `Project.public_open_side` field
set directly from the UI/API (`app/demo/requirements_view.py::_public_open_side_of`). This is a
common confusion worth stating plainly: not every "requirement" comes from the LLM parse.

Unsupported hard requirements are classified (not silently dropped or silently accepted) via a
dedicated classification step, surfaced back to the person as `other_requests`/`UnsupportedRequest`
with a severity.

## Authoritative implementation

- `app/requirements/parser.py` (`OpenAIRequirementParser`, `RequirementExtraction`, `FixtureDemand`).
- `app/requirements/wet_room_normalizer.py` (deterministic downstream rules).
- `app/demo/requirements_view.py` (`_public_open_side_of`, `spec_for`, `review_of` — the
  structured-field and review-correction layer above the raw LLM extraction).
- specs/002-requirement-parser (the original feature spec; tasks fully checked/merged).
- `docs/UNSUPPORTED_REQUEST_CLASSIFICATION_REPORT.md` (classification policy).

## Current constraints/invariants

- `OpenAIRequirementParser` is the only LLM call in the live product request path — any test or
  evaluation of this step against a local/production model belongs in
  `backend/tests/ai_harness/`, never product code (see the Knowledge System page).
- `public_open_side` must never be treated as an LLM-extraction concern in tests or docs — it is
  a structured field, confirmed by reading both `parser.py`'s schema and `requirements_view.py`.

## Supersedes

N/A — no prior version of this parsing layer is tracked as superseded in this Wiki round.

## Known follow-ups

None currently tracked at the Wiki level.

## Evidence/history

`specs/002-requirement-parser/` (the original spec), `docs/UNSUPPORTED_REQUEST_CLASSIFICATION_REPORT.md`,
`backend/tests/wet_room_corpus/corpus.json` (61 hand-labelled real briefs — the golden reference
for what correct extraction looks like).

## Last verified against git

`1d648c3` (main HEAD). specs/002 and the classification report both confirmed present in `main`'s
history via `git log --oneline main`; not independently re-verified line-by-line this round
(confidence: medium, consistent with `doc_status.json`).
