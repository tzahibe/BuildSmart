# Phase 0 Research: Natural Language Requirement Parser

No `NEEDS CLARIFICATION` items remained from spec.md or the Technical Context — spec.md deliberately left
the technical approach open (see its Assumptions). This file records the concrete decisions made in
turning that open question, and the rest of the Technical Context, into an approach.

## Decision (revised 2026-09-03, explicit request — supersedes the original recommendation below): OpenAI `gpt-5-nano` for extraction, not rule-based

- **Original recommendation (superseded)**: a deterministic regex/keyword extractor (see rationale kept
  below for the record — it's still a fair account of that approach's trade-offs). The user explicitly
  rejected this and asked for a cheap OpenAI model instead, called from the backend.
- **Decision now in force**: `OpenAIRequirementParser` calls OpenAI's Chat Completions API with structured
  outputs (`client.chat.completions.parse(model="gpt-5-nano", response_format=<pydantic model>, ...)`),
  passing the project's `description` and a system prompt that defines the `requested`/`inferred`/`unknown`
  semantics and explicitly instructs the model never to guess a value it should mark `unknown`. The
  response schema mirrors `StructuredRequirements`' tagged-field shape directly, so the model itself
  produces `{value, source}` per field rather than a separate post-hoc tagging step.
  - **Model choice**: `gpt-5-nano` — confirmed via OpenAI's current pricing page
    (`https://platform.openai.com/docs/pricing`, checked 2026-09-03) as their cheapest model
    ($0.05/1M input, $0.40/1M output tokens), and verified working end-to-end with a real API call during
    planning (correctly extracted `bedrooms=4, floors=2` from a short Hebrew test sentence via
    `chat.completions.parse`). More than capable for a short-paragraph structured-extraction task; no
    reason to pay for a larger model here.
  - **API key**: `OPENAI_API_KEY`, loaded from `backend/.env` (gitignored — confirmed via `git
    check-ignore`) via `python-dotenv`, read once at `app/main.py` startup before any router that needs it
    is imported. Never committed, never logged. `backend/.env.example` documents the variable name for
    other developers without the real value.
- **Honest trade-off vs. the superseded regex approach**: a regex can *structurally* never fabricate a
  value (it either matches a stated pattern or doesn't); an LLM's adherence to "never guess, mark unknown
  instead" is instruction-following, not a hard guarantee — it can still occasionally hallucinate despite
  the prompt. This is a real, accepted risk of this decision, not something to gloss over (per
  `docs/AI_Home_Planner_SPEC.md` §30: "hide uncertainty" is explicitly listed as something not to do). No
  verification/critic pass is added to catch this in this feature — spec.md's Assumptions already scope
  that out ("No confidence scoring beyond the three-way source tag... a full confidence system is a later,
  separate feature"). If hallucinated `requested`/`inferred` values turn out to be a real problem in
  practice, the fix is a verification pass (Feature 12 in the source spec) or stricter prompting/few-shot
  examples — not something this MVP attempts.
- **What's unchanged from the superseded decision**: the reasons to keep this behind a `RequirementParser`
  interface still apply, now in the other direction — a future swap to a different/cheaper/self-hosted
  model, or back to a deterministic approach for specific fields, needs no change to the router, storage,
  or API contract. `RequirementParser.parse(description: str) -> RequirementExtraction` stays the
  interface; `OpenAIRequirementParser` is the one implementation.
- **Kept for the record — rationale for the originally-recommended regex approach** (not in force):
  a regex either finds a specific stated pattern (→ `requested`) or it doesn't (→ `unknown`), which
  satisfies FR-004 structurally rather than through instructions; needs no API key, network dependency, or
  per-call cost; trivially meets the SC-001/SC-004 10-second budget; and is exhaustively unit-testable
  (fixed input → fixed expected output) in a way an LLM call, whose exact output can vary between runs, is
  not. Its accepted trade-off was under-extraction: it would only handle phrasings its patterns
  anticipated, returning `unknown` for anything more varied than that — never wrong, sometimes incomplete.
  This remains a reasonable alternative if the OpenAI dependency ever needs to be dropped (e.g. cost,
  offline requirements) — see spec.md's Assumptions, which left the technical approach open specifically
  so a swap like this stays possible.

## Decision: Per-field `{value, source}` shape, not a single flat object with a separate tag map

- **Decision**: Each extracted field is its own small object carrying both `value` (or `null`) and `source`
  (`requested`/`inferred`/`unknown`) — e.g. `{"value": 4, "source": "requested"}` — rather than one flat
  object of values plus a second parallel object mapping field names to sources.
- **Rationale**: Keeps each field's value and its provenance inseparable at the type level — a consumer
  can't accidentally read `bedrooms.value` while ignoring `bedrooms.source` without it being visually
  obvious in the code. A parallel tag map is easy to let drift out of sync (e.g., forgetting to update the
  tag when the value changes) and pushes the "did I check the source too?" burden onto every caller.
- **Alternatives considered**: Flat values object + separate `field_sources: dict[str, str]` — rejected for
  the drift/ergonomics reasons above.

## Decision: Storage — JSON file behind `RequirementsRepository`, same pattern as `ProjectRepository`

- **Decision**: `backend/app/data/requirements.json`, one entry per `project_id`, loaded/replaced via a
  `RequirementsRepository` interface + `JsonFileRequirementsRepository` implementation — structurally the
  same as Feature 01's `ProjectRepository`/`JsonFileProjectRepository`.
- **Rationale**: Consistency with the existing, already-justified decision (see
  `specs/001-project-creation/research.md`) — no new storage technology introduced for one more small
  entity. Same temporary/swappable-to-Postgres-later status applies.
- **Alternatives considered**: Storing structured requirements as a field on the `Project` record itself
  (in `projects.json`) — rejected to keep the two features' storage independent (this feature only *reads*
  project data, it doesn't need write access to the project record), and because `StructuredRequirements`
  has its own lifecycle (can be re-parsed/replaced independently of the project's own fields).

## Decision: Endpoint shape — `POST` to (re)parse, `GET` to retrieve, nested under `/projects/{project_id}`

- **Decision**: `POST /projects/{project_id}/requirements` re-parses the project's current description and
  replaces any stored result, returning it. `GET /projects/{project_id}/requirements` returns the
  previously stored result, `404` if the project doesn't exist or if it exists but has never been parsed
  (distinguished by the `detail` message).
- **Rationale**: `POST` matches "trigger a computation and store its result" better than `PUT`, which
  implies the client supplies the resource's representation (it doesn't — parsing reads the description
  server-side, per FR-007). Nesting under `/projects/{project_id}/` mirrors the 1:1, project-owned
  relationship spec.md's Key Entities describe, and reuses the existing project repository (imported from
  `app.projects.routes.base_routes`) to check the project exists and to read its `description` — no
  duplicate project-lookup logic.
- **Alternatives considered**: A custom-action-style path (`POST
  /projects/{project_id}/requirements:parse`) — rejected as unnecessary; plain `POST` to the sub-resource
  already conveys "create/replace" without extra path syntax.

## Decision: Tests use a fake `RequirementParser`, never the real OpenAI API

- **Decision**: `router.py` holds a module-level `parser: RequirementParser` instance (mirroring the
  existing `repository` module-level pattern in `app/projects/routes/base_routes.py`), defaulting to
  `OpenAIRequirementParser()`. Tests monkeypatch this to a small deterministic `FakeRequirementParser`
  (fixed input strings → fixed canned `RequirementExtraction` output) rather than calling the real API.
- **Rationale**: The exact same reasoning already applied to `GET /localities` in Feature 01 (see
  `specs/001-project-creation/research.md`'s "Live query per request" rejection) — a test suite that needs
  network access, a valid API key, and real (metered, non-free) API calls just to run isn't hermetic:
  it's slow, can fail on CI for reasons unrelated to the code under test, costs real money on every test
  run, and its assertions become non-deterministic (an LLM's exact output isn't guaranteed stable across
  calls). `OpenAIRequirementParser.__init__` deliberately does not eagerly validate or require
  `OPENAI_API_KEY` at construction (the `openai.OpenAI(api_key=...)` constructor itself makes no network
  call) — so importing `app.main` for tests never touches the network or requires the key to be set,
  even before monkeypatching.
- **Alternatives considered**: Recording/replaying real API responses (VCR-style cassettes) — more
  realistic, but adds a new testing dependency and a maintenance burden (re-recording when the prompt
  changes) disproportionate to this MVP; a hand-written fake with a handful of representative
  input/output pairs is simpler and just as effective for testing the router/storage logic, which is what
  these tests are actually responsible for (the LLM call itself was verified manually during planning —
  see the model-choice decision above).

## Decision: Essential-fields set refined twice, same day, per follow-up requests

- **Round 1**: Initial essential set (floors, target built area, bedrooms) → bedrooms dropped. Only plot
  size (already guaranteed present by Feature 01, not re-checked here), target built area, and floors are
  true blockers for starting to plan; bedrooms (and safe room, parking, pool) became optional extras the
  `message` may *suggest* but never *require*.
- **Round 2**: Floors itself should not be something the user is forced to state — an unstated floor count
  now defaults to `{value: 1, source: "inferred"}` (FR-011) instead of `unknown`. This narrows what
  `missing_essential_fields` can realistically ever contain to just `target_built_area_m2`.
- **Implementation choice for the FR-011 default — via the LLM's own extraction, not post-processing**:
  the system prompt given to `gpt-5-nano` states the exact rule ("if floor count is not stated, output
  `{value: 1, source: 'inferred'}`; if the text states conflicting floor counts, output `{value: null,
  source: 'unknown'}`"), and the model's structured-output response is trusted for the result — the
  backend does not separately post-process `floors` to force a default.
  - **Rationale**: distinguishing "never mentioned" from "mentioned but conflicting" requires actually
    understanding the text, which is exactly what's already being delegated to the model for every other
    field's `requested`/`inferred`/`unknown` decision. A mechanical post-processing rule (e.g., "if
    `floors.source == unknown`, force it to `{1, inferred}` no matter what") can't make that distinction
    without re-reading the source text itself, and would silently discard the conflict case spec.md's Edge
    Cases explicitly wants preserved as `unknown`.
  - **Accepted trade-off**: same honesty note as the model-choice decision above — this default is applied
    via instruction-following, not a structural guarantee. If the model ever fails to apply it correctly
    (e.g., defaults to 1 despite a real stated conflict, or vice versa), that's a prompting-quality problem
    to iterate on, not something this MVP adds a verification pass to catch.

## Decision (2026-09-03, later the same day, per follow-up request): merge into `Project`; drop `target_built_area_m2` and FR-010

- **Decision**: this feature's output — `floors`, `bedrooms`, `safe_room`, `parking_spaces`, `pool` — now
  merges directly into Feature 01's `Project` (via `ProjectRepository.set_parsed_requirements(...)`)
  instead of living in this feature's own `StructuredRequirements` entity/repository/`GET` endpoint, all
  of which were removed. `target_built_area_m2` was dropped from what's extracted — see rationale below.
  The full decision, including the `Project`-side changes (new fields, the new repository method, why
  `updated_at` stays untouched), is written up in
  `specs/001-project-creation/research.md`'s "`Project` absorbs Feature 02's parsed fields" — this entry
  only covers what changed on this feature's side of the boundary.
- **Rationale — why `target_built_area_m2` specifically had to go**: this feature's own "Essential fields"
  decision (above) had already identified `target_built_area_m2` as the one field realistically capable of
  triggering FR-010's "missing essential info" message (since `floors` almost always defaults per FR-011).
  Once Feature 01 gained its own required, validated `built_area_m2` (added the same day, for an unrelated
  reason — see that feature's research.md), continuing to *also* extract a built area from free text here
  would have meant two numbers claiming to represent the same fact, with no reconciliation between them —
  exactly the kind of duplicate/conflicting-source problem this whole project's evidence-first philosophy
  argues against. Removing it here, rather than adding a cross-check, was simpler and was the explicitly
  requested direction ("`Project` should contain everything").
- **Consequence — FR-010 became dead code, so it was removed, not just left unused**: FR-010's "essential
  fields missing → message" behavior existed to warn about a missing `target_built_area_m2` (`floors`
  being the field it also nominally covered, but which — per FR-011 — is essentially never actually
  missing). With `target_built_area_m2` gone entirely, there was nothing left for that check to
  meaningfully evaluate: `Project.built_area_m2` is now guaranteed present and valid at creation time
  (Feature 01, `Field(gt=0)` + the plot-area cross-check), so a `POST .../requirements` call can never
  discover it's "missing" — that would have already been rejected as a `422` back when the project was
  created. Removing FR-010 (rather than leaving it defined-but-unreachable) keeps the spec honest about
  what the system actually does.
- **What's unchanged**: `RequirementParser`/`OpenAIRequirementParser`, the `gpt-5-nano` choice, the
  `requested`/`inferred`/`unknown` tagging semantics, and the FR-011 floors default are all untouched by
  this move — only *what* gets extracted (no more built area) and *where the result is stored* (the
  project itself, not a separate entity) changed.
- **Alternatives considered**: see `specs/001-project-creation/research.md` — the alternatives evaluated
  (keeping `StructuredRequirements` separate with a cross-check; keeping a thin `GET` alias) were assessed
  from that feature's side and apply equally here, so they aren't duplicated in this file.
