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

## SAFE_ROOM/MAMAD becomes a typed constraint (Issue #35)

`spec_for` (`app/demo/requirements_view.py`) maps `review.safe_room.value` (the resolved reading of
the parser's `safe_room: TaggedBool` — corrected on the review screen if the person changed it, not
the raw LLM tag) onto `ProgramSpec.safe_room: bool`, unchanged by this Issue. What's new is one more
step, in `ArchitecturalSpec.safe_room_constraint`: that resolved bool is turned into a single
`TypedConstraint(kind=SAFE_ROOM, source=USER|NONE, authoritative, min_area_m2)` — `USER` whenever
the person's own words asked for the room (however the parser tagged its own confidence, this
codebase has no path that derives a safe room from anything else), `NONE`/not-authoritative for a
brief that never requested one. See Geometry/Validation's "Typed constraints and the SAFE_ROOM/MAMAD
refusal" section for how that constraint is then checked, not merely carried, through concept
generation, geometry realization and the validator. `ConstraintSource.COMPLIANCE` exists in
`app/vertical_slice/constraints.py` for a future legal-applicability rule but is not produced by any
parsing or spec-building code today — whether the law requires a safe room for a given brief stays
explicitly out of this Issue's scope.

## Current constraints/invariants

- `OpenAIRequirementParser` is the only LLM call in the live product request path — any test or
  evaluation of this step against a local/production model belongs in
  `backend/tests/ai_harness/`, never product code (see the Knowledge System page).
- `public_open_side` must never be treated as an LLM-extraction concern in tests or docs — it is
  a structured field, confirmed by reading both `parser.py`'s schema and `requirements_view.py`.

## Supersedes

N/A — no prior version of this parsing layer is tracked as superseded in this Wiki round.

## Latency: reasoning effort (Issue #89)

`OpenAIRequirementParser` calls `chat.completions.parse(..., reasoning_effort=...)` — gpt-5-nano is
a reasoning model, and by default spends its reasoning budget even on this simple structured
extraction. The owner's own brief (Abu Snan, 15×17 m, 130 m²) measured `POST
/projects/{id}/requirements` at 64.5 s with no `reasoning_effort` set, against 0.9 s for the whole
design generation that follows it — measured 2026-09-21. `reasoning_effort` defaults to `"minimal"`
(constructor param, overridable via the `REQUIREMENTS_REASONING_EFFORT` env var; allowed values
`minimal`/`low`/`medium`/`high`; an unrecognised value raises at construction, never silently sent
to the API). The model, system prompt, `response_format` and `normalize_extraction` are unchanged
by this — only the reasoning-effort request parameter moved. Measurement method:
`backend/scripts/measure_parser_latency.py` parses a fixed set of 6 real Hebrew briefs (including
the Abu Snan one above) against the real API N times per brief and prints p50/p95 wall time per
brief plus the extraction JSON, for comparing efforts with a real `OPENAI_API_KEY` (CI never runs
this script — it makes real API calls). Before/after numbers from that script belong here once
measured by the lead/owner; not yet recorded at time of writing.

## Known follow-ups

- Record the lead/owner's before/after `measure_parser_latency.py` numbers (minimal vs. no
  `reasoning_effort` override) in the section above once measured.

## Evidence/history

`specs/002-requirement-parser/` (the original spec), `docs/UNSUPPORTED_REQUEST_CLASSIFICATION_REPORT.md`,
`backend/tests/wet_room_corpus/corpus.json` (61 hand-labelled real briefs — the golden reference
for what correct extraction looks like).

## Last verified against git

`1d648c3` (main HEAD). specs/002 and the classification report both confirmed present in `main`'s
history via `git log --oneline main`; not independently re-verified line-by-line this round
(confidence: medium, consistent with `doc_status.json`).

The SAFE_ROOM/MAMAD typed-constraint section documents Issue #35, landed on branch
`agent/35-safe-room-mamad-requirement-preservation` (based on `4aade91`), verified against this
session's own implementation and test runs.
