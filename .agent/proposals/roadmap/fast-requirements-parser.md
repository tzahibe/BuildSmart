# [agent] Requirements parser latency: gpt-5-nano structured extraction with minimal reasoning effort — the same schema and output, ~10× faster

### Goal

The loading screen after a brief is typed is almost entirely the requirements parser's OpenAI call: measured
2026-09-21 on the owner's own brief (Abu Snan, 15×17 m, 130 m², "3 חדרי שינה, חדר הורים עם מקלחת, מקלחת
משותפת, חדר כביסה, סלון ומטבח"): `POST /projects/{id}/requirements` 64.5 s versus 0.9 s for the whole design
generation. gpt-5-nano is a reasoning model and spends its default reasoning budget on a simple structured
extraction. Owner decision (2026-09-21, "תבצע"): keep the model and the structured output exactly as they are,
and ask for minimal reasoning effort.

### Current behavior

`backend/app/requirements/parser.py::OpenAIRequirementParser.extract` calls `chat.completions.parse(model="gpt-5-nano",
messages=…, response_format=BriefExtraction)` with no `reasoning_effort`; the SDK (openai 3.7.0) accepts
`reasoning_effort` on `chat.completions.parse`. Nothing measures or records the parse latency.

### Required behavior

1. `OpenAIRequirementParser.__init__` takes `reasoning_effort: str = "minimal"` (override via the
   `REQUIREMENTS_REASONING_EFFORT` environment variable; allowed values `minimal`, `low`, `medium`, `high`)
   and `extract` passes it to `chat.completions.parse`; the model, the system prompt, `response_format` and
   `normalize_extraction` are byte-identical — the output contract does not change.
2. `backend/scripts/measure_parser_latency.py`: parses a fixed list of 6 Hebrew briefs (including the one
   above) N times and prints p50 / p95 wall time and the extraction JSON, so the lead/owner can compare
   efforts with a real key (the script needs `OPENAI_API_KEY`; CI never calls the API).
3. `docs/wiki/architecture/requirements-parsing.md`: one paragraph on the reasoning-effort setting, the
   measured before/after (the lead adds the numbers from the script; the worker records the measurement
   method), and the env override.

### Acceptance Criteria

- AC-1: with a fake OpenAI client, `OpenAIRequirementParser().extract(...)` sends `reasoning_effort="minimal"` by default and honours `REQUIREMENTS_REASONING_EFFORT=low`, while model, messages and response_format are unchanged
- AC-2: an unsupported value of `REQUIREMENTS_REASONING_EFFORT` fails fast at construction with a clear error, never silently
- AC-3: every existing requirements test still passes (the extraction schema and normalisation are untouched)
- AC-4: the latency measurement script exists and its usage is documented on the requirements-parsing Wiki page

### Out of scope

Changing the model, the prompt, the extraction schema or the wet-room normalisation; caching parses; the chat
assistant's own model calls; the local-model gateway.

### Affected domains

backend, ai, qa, knowledge

### Risk

LOW

### Resource class

LIGHT

### Dependencies

none

### Required locks

requirements-parser

### Verification plan

- AC-1 -> pytest:backend/tests/test_requirements.py::test_openai_parser_requests_minimal_reasoning_effort_by_default_and_honours_the_env_override
- AC-2 -> pytest:backend/tests/test_requirements.py::test_openai_parser_rejects_an_unknown_reasoning_effort
- AC-3 -> pytest:backend/tests/test_requirements.py
- AC-3 -> pytest:backend/tests/test_wet_room_questions.py
- AC-4 -> file:backend/scripts/measure_parser_latency.py ; grep:docs/wiki/architecture/requirements-parsing.md:reasoning_effort

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/wiki/architecture/requirements-parsing.md (reasoning effort, measurement, env override).

### Knowledge check

Consulted: `backend/app/requirements/parser.py` (`OpenAIRequirementParser.extract`: `chat.completions.parse`, gpt-5-nano,
`BriefExtraction`), `tests/test_requirements.py` (FakeRequirementParser pattern, router `parser` monkeypatch),
`docs/wiki/architecture/requirements-parsing.md`, `specs/002-requirement-parser/research.md` (model choice), the owner's
measured 64.5 s parse on the preview (2026-09-21) vs 0.9 s design generation; openai SDK 3.7.0 accepts
`reasoning_effort` on `chat.completions.parse`.
