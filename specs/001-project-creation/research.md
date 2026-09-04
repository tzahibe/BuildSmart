# Phase 0 Research: Project Creation (Basic Intake)

No open `NEEDS CLARIFICATION` items remained from `spec.md` or the Technical Context (all were resolved
with documented assumptions/defaults). This file records the concrete decisions made while turning those
defaults into a technical approach.

## Decision: JSON-file storage behind a repository interface

- **Decision**: Store `Project` records in a single JSON file on disk (`backend/app/data/projects.json`),
  accessed only through a `ProjectRepository` abstract interface (`get`, `create`, `update`). The file is
  read/written as a whole on each operation (one small JSON object keyed by `project_id`); no database.
- **Rationale**: The spec's own guidance (`docs/AI_Home_Planner_SPEC.md` §30) says to implement the
  smallest working version and to keep providers replaceable. A file is enough to let data survive a
  server restart during manual/local testing, with no new infrastructure (no DB process, no migrations).
  Hiding it behind the repository interface means the storage mechanism is an implementation detail the
  rest of the app never sees.
- **Note — this is explicitly temporary**: Once more features need real persistence (concurrent writers,
  querying, larger volume — e.g. once document ingestion/RAG or multi-project listing arrive), this JSON
  file implementation should be replaced with a `PostgresProjectRepository` (per the long-term stack in
  §25 of the source spec), implementing the same `ProjectRepository` interface. Because the API/router
  layer only depends on the interface, that swap will not require any changes outside `repository.py`.
- **Alternatives considered**:
  - *In-memory dict*: rejected for this iteration — data would be lost on every server restart, which
    makes manual end-to-end testing (quickstart.md) more annoying than necessary.
  - *PostgreSQL now*: rejected — adds infrastructure (DB, migrations, Docker) with no feature-level
    benefit yet; premature for a single intake endpoint. Planned as the follow-up (see note above).
  - *SQLite file*: rejected for now — marginally more capable than a plain JSON file but adds a schema/
    migration story for one table; a plain JSON file is simpler and sufficient until the Postgres swap.

## Decision: FastAPI `APIRouter` module under `app/projects/`

- **Decision**: New `backend/app/projects/` package with `models.py` (Pydantic schemas), `repository.py`
  (storage interface + in-memory implementation), and `router.py` (the 3 endpoints), mounted into the
  existing `backend/app/main.py`.
- **Rationale**: Matches the existing single-package `backend/app` layout already in the repo; avoids
  introducing the larger `apps/`/`packages/` monorepo structure suggested for the full product before
  there's a second feature to justify it.
- **Alternatives considered**: Full `apps/api` + `packages/domain` restructuring per §26 of the source
  spec — rejected for now as premature; revisit once several backend features exist and the current flat
  layout starts to strain.

## Decision: pytest + FastAPI `TestClient` for tests

- **Decision**: Add `pytest` and `httpx` (peer dependency of `TestClient`) as dev dependencies; write
  request-level tests against the 3 endpoints rather than unit-testing the repository in isolation only.
- **Rationale**: `TestClient` exercises the real FastAPI app (routing, validation, status codes) with no
  extra infrastructure, which is the fastest way to cover the acceptance scenarios in `spec.md` end-to-end.
- **Alternatives considered**: Testing the repository directly with plain unit tests only — kept as a
  secondary, cheap addition, but request-level tests are primary since they validate the actual contract.

## Decision: `project_id` generation via `uuid4`

- **Decision**: Use Python's standard `uuid.uuid4()`, stored/returned as a string.
- **Rationale**: No requirement for sequential or human-readable ids; UUIDs avoid collision handling and
  need no external counter/sequence (relevant later if storage becomes distributed).
- **Alternatives considered**: Auto-incrementing integer — rejected, implies a single authoritative
  sequence which conflicts with the "storage is swappable" decision above.

## Decision (2026-09-03, added on request, SUPERSEDED same day — see next decision): City list as suggestion only

> **Superseded**: a same-day follow-up request explicitly asked for `city` to be restricted to the list.
> Kept here for the record of what was tried and why; the decision now in force is the one below it.

- **Decision**: `GET /localities` serves a static Python-embedded list (`backend/app/localities/data.py`)
  compiled from Hebrew Wikipedia's category listings for cities, local councils, and regional councils
  (~229 entries). The `city` field on `Project` is validated only for non-emptiness — it is never checked
  against this list.
- **Rationale**: The list is real, sourced data (not invented), but Wikipedia's categorization can lag
  official status changes and the fetch used here did not confirm it matches the current official ~259
  authorities. Whitelisting `city` against a dataset known to be possibly incomplete would risk rejecting
  genuine addresses — worse than the UX cost of an unconstrained free-text field. This mirrors the source
  spec's own "don't invent, mark UNKNOWN rather than ALLOWED" instinct, applied the other way: prefer
  under-constraining a convenience feature over over-constraining real user input.
- **Alternatives considered**:
  - *Strict whitelist*: rejected for the reason above.
  - *Live official API (e.g. data.gov.il)*: would be more authoritative and complete, but adds a network
    dependency and latency to every project creation if used for validation, and a separate caching story
    if used only for autocomplete; out of scope for this feature. Worth revisiting if `city` ever needs to
    drive real regulatory lookups (Feature 03/04 in the source spec) rather than just autocomplete.

## Decision (2026-09-03, follow-up request — currently in force): City must be selected from the list

- **Decision**: `city` on `ProjectCreate`/`ProjectUpdate` is now validated against `ISRAELI_LOCALITIES`
  (`backend/app/localities/data.py`) — any value not an exact match is rejected with `422`. The frontend
  mirrors this: `App.tsx` checks the typed value against the fetched list client-side before submitting,
  so an unrecognized city is caught instantly rather than round-tripping to the server (falling back to
  server-side rejection if the `/localities` fetch itself failed, rather than blocking all submissions).
- **Rationale**: Explicitly requested, superseding the suggestion-only decision above. The trade-off noted
  there still holds — a genuine locality missing from the ~229-entry list cannot currently be entered —
  but the user chose guaranteed-clean, consistent city values over that edge case. If this becomes a real
  problem, the fix is expanding/refreshing `ISRAELI_LOCALITIES` (or switching to a live official source),
  not relaxing the validation.
- **Alternatives considered**: Reverting to suggestion-only — rejected, contradicts the explicit request.
- **Superseded by the next decision**: the ~229-entry Wikipedia list (`ISRAELI_LOCALITIES`) referenced
  above was itself replaced the same day — see below.

## Decision (2026-09-03, follow-up request — currently in force): Switch city+street source to an official government dataset, as a static snapshot

- **Decision**: Requested feature — street suggestions scoped to the chosen city, gated so the street
  field only opens after a valid city is picked. This needs a real per-city street list, which the
  previous Wikipedia-sourced city-only list can't provide. Replaced `backend/app/localities/data.py`'s
  static `ISRAELI_LOCALITIES` list with a loader over `backend/app/localities/streets_by_city.json` — a
  snapshot of data.gov.il's official "רשימת רחובות בישראל" dataset (Israel Population and Immigration
  Authority, resource `bf185c7f-1a4e-4662-88c5-fa118a244bda`), fetched 2026-09-03 via `datastore_search`,
  filtered to `street_name_status == "official"`: **1,314 cities/settlements, 63,575 streets**. `city`
  validation now checks against this dataset's `KNOWN_CITIES` instead of the old list. New endpoint `GET
  /localities/{city}/streets` serves the per-city street list (404 for an unrecognized city).
- **Rationale**:
  - *Official source over a wiki scrape*: this is a government address registry, not a
    community-maintained encyclopedia category — a genuine quality upgrade, and it directly fixes the
    earlier "~229 entries, not necessarily complete/official" caveat (1,314 entries here, from the
    authority that actually assigns them).
  - *One dataset for both city and street*: sourcing both from the same registry guarantees every city
    `GET /localities` returns has a matching (possibly non-empty-only, never missing) entry at `GET
    /localities/{city}/streets` — no cross-source name-spelling mismatches (this was checked: the old
    Wikipedia list spelled Tel Aviv `"תל אביב-יפו"`, the official registry spells it `"תל אביב - יפו"` —
    exactly the kind of inconsistency a single source avoids).
  - *Static snapshot, not a live call*: `ensure` fetching per-request (or even per-startup) would make
    `POST /projects` validation and the test suite depend on data.gov.il being reachable, and would slow
    every cold start fetching/paginating ~63k rows. A committed JSON snapshot (1.15MB) keeps validation
    and tests fast, offline, and deterministic — consistent with keeping `pytest` hermetic. The cost is
    staleness: the source updates weekly and this snapshot won't reflect that automatically.
- **Alternatives considered**:
  - *Live query per request*: rejected — latency + a hard external dependency on every project write,
    and breaks test hermeticity (confirmed: an early version of `get_cities()` that called the API lazily
    made `pytest` require network access).
  - *Keep the Wikipedia list for `city`, add a separate street source*: rejected — reintroduces exactly
    the name-mismatch risk above (Tel Aviv, and likely others), for no benefit once a better single source
    covers both.
  - *Enforce `street` against its city's list the same way `city` is enforced*: not done — not requested;
    `street` is still just required-non-empty. Worth revisiting for consistency with the `city` decision
    above if asked.
- **Refreshing the snapshot**: page `datastore_search` for the resource id above with
  `filters={"street_name_status": "official"}` (paginate via `offset`, ~32k rows/page), group records by
  `city_name` into sorted, deduplicated `street_name` lists, and overwrite `streets_by_city.json`.

## Decision (2026-09-03, follow-up request — currently in force): `street` must also be selected from the list

- **Decision**: `ProjectCreate` gained a `model_validator(mode="after")` checking `street in
  CITY_STREETS.get(city, [])`, rejecting any street not exactly matching an entry for the *submitted*
  city (so a real street from a different city is rejected too — the previous decision's "one dataset for
  both" design is what makes this cheap: no separate lookup or reconciliation needed). `ProjectUpdate`
  gets the same check, but **only when both `city` and `street` are provided in the same update payload**.
  `App.tsx` mirrors the check client-side (`streets.includes(form.street)`) before submitting, and now
  strips the `Value error, ` prefix and skips showing a `loc` of `"body"` (FastAPI's location for a
  whole-model validator, not a specific field) when rendering errors.
- **Rationale**: Explicitly requested, directly following the same pattern already applied to `city`
  (suggestion → whitelist). Straightforward given the previous decision: because `city` and `street` come
  from the same registry snapshot, "is `street` valid for `city`" is a pure local dict lookup, no new data
  or network access needed.
- **Known gap at the time this was written — now closed by T013**: `ProjectUpdate`'s cross-field check
  can't run when only one of `city`/`street` is provided, because the schema has no access to the
  project's *currently stored* values. Concretely: updating only `street` wouldn't re-check it against the
  existing stored `city`, and updating only `city` wouldn't re-check the existing stored `street` against
  the new city's list — either could leave a project's stored city+street inconsistent with each other
  after an update. This is exactly what `PATCH /projects/{project_id}` (T013,
  `backend/app/projects/routes/base_routes.py`) now does at the router level: it loads the existing
  project, computes the merged `city`/`street` pair (existing values overlaid with whatever the update
  provides), and rejects with `422` before calling `repository.update` if that merged pair isn't a real
  match in `CITY_STREETS` — the way a database-level check constraint would. Covered by
  `test_update_project_street_only_not_matching_existing_city_is_rejected` and
  `test_update_project_city_only_invalidating_existing_street_is_rejected` in `test_projects.py`.
- **Alternatives considered**:
  - *Validate `ProjectUpdate.street` against `city="anywhere"` (i.e., street just needs to exist for *some*
    city)*: rejected — weaker than what was asked ("must be selected from the list" for the relevant
    city), and would let a street silently jump to the wrong city on a partial update.
  - *Require `city` and `street` together on every update (reject a street-only or city-only PATCH)*:
    a real option for closing the gap above cleanly, but changes `PATCH`'s contract before it's even
    built; left for the T013 implementation to decide, not bundled into this change.

## Decision (2026-09-03, well after initial ship, per follow-up request): Add required `built_area_m2`, strictly less than `plot_area_m2`

- **Context**: it was pointed out that a project could be created with a fully valid `plot_area_m2` but a
  `description` carrying no real information at all (e.g. random characters) — since `description`'s
  *content* was never validated, only its non-emptiness (FR-009). Such a project would have had no
  reliable numeric planning data beyond the plot size.
- **Decision**: add `built_area_m2` (the desired built house size) as a required field on `ProjectCreate`/
  `Project`, `> 0`, and — via a `model_validator` — strictly smaller than `plot_area_m2`. Same
  merged-pair-on-PATCH pattern as `city`/`street` (see decision above): `ProjectUpdate` only cross-checks
  when both fields are supplied together; the `PATCH` route re-checks the merged pair (existing values
  overlaid with the update) before saving.
- **Rationale — deterministic structured data over validating free text**: the alternative (have `POST
  /projects` call an LLM to judge whether `description` is "meaningful") was considered and rejected — it
  would add cost/latency/a new failure mode to every project creation just to make a fuzzy, disputable
  judgment ("is this text meaningful?" has no crisp answer), and doesn't actually guarantee anything
  useful even if the description *is* judged "meaningful" (an LLM's idea of meaningful prose doesn't
  imply usable planning numbers). Requiring a real, validated `built_area_m2` number directly guarantees
  the one thing that actually matters downstream — real size/footprint data — regardless of what
  `description` says. This is the same "prefer deterministic domain logic over LLM judgment for facts"
  instinct that runs through this whole project (`docs/AI_Home_Planner_SPEC.md`'s central principle).
  `description`'s semantic quality remains intentionally unvalidated; this was a conscious choice to solve
  the actual risk (no usable data) rather than to chase "does the text sound meaningful," which is a much
  harder and less well-defined problem.
- **Relationship to Feature 02's `target_built_area_m2` — now resolved, see decision below**: Feature 02
  (`specs/002-requirement-parser/`) originally had its own `target_built_area_m2`, extracted from
  `description` by the LLM parser. That created exactly the unreconciled-duplicate-source problem this
  note originally flagged. It was resolved the same day, not left open: see "Decision: `Project` absorbs
  Feature 02's parsed fields" below.
- **Alternatives considered**:
  - *LLM-based "is this description meaningful?" gate on `POST /projects`*: rejected per the rationale
    above.
  - *Minimum character-length heuristic for `description`*: rejected — easy to defeat with meaningless
    padding (e.g. `"aaaaaaaaaaaaaaaaaaaaaaa"`), and doesn't address the actual downstream problem (missing
    usable planning numbers) the way a validated `built_area_m2` does directly.
  - *Reconcile `built_area_m2` with Feature 02's `target_built_area_m2`*: superseded — see next decision.

## Decision (2026-09-03, later the same day, per follow-up request): `Project` absorbs Feature 02's parsed fields

- **Context**: per explicit request — "`Project` should contain everything needed to eventually produce a
  sketch, with most of it filled in by the LLM from the user's description" — Feature 02's separate
  `StructuredRequirements` entity (its own JSON file, its own repository, a dedicated `GET
  /projects/{id}/requirements`) was merged directly into `Project`.
- **Decision**: `Project` gained `floors`, `bedrooms`, `safe_room`, `parking_spaces`, `pool` (each a
  tagged field, `null` until first parsed) and `requirements_parsed_at`. `ProjectRepository` gained a
  `set_parsed_requirements(...)` method (loads, merges these fields in, saves — parallel to `update()` but
  intentionally separate, since these come from the parser, not from `ProjectUpdate`/user input, and don't
  touch `updated_at`). Feature 02's own `GET /projects/{project_id}/requirements` was removed entirely —
  `GET /projects/{project_id}` (this feature) already returns everything now, so a second endpoint for the
  same data would just be a duplicate to keep in sync. `POST /projects/{project_id}/requirements` (still
  Feature 02, unchanged in location) now returns the updated `Project` instead of a separate resource.
  Feature 02's own `target_built_area_m2` was dropped in the same change — see this file's earlier note
  and Feature 02's research.md for why re-deriving built area from free text was redundant once
  `built_area_m2` existed here as the validated, structured source of truth.
- **Rationale**: this directly resolves the duplicate-source-of-truth risk noted above (two different
  numbers both claiming to be "the built area"), and matches the real relationship between the two
  features — Feature 02 doesn't own a separate concept, it *completes* a `Project` that Feature 01 already
  created, filling in the fields a structured form is a poor fit for (natural-language preferences like
  "עם ממ"ד" or "בריכה 8 על 4") while the fields with a good structured/validated form (areas, city, street)
  stay exactly where they were. One entity, one place to look for "everything about this project."
- **What stays unchanged**: `RequirementParser`/`OpenAIRequirementParser` (Feature 02) are untouched by
  this move — they still just take a description string and return a tagged extraction; only *where the
  result is stored* changed. The FR-011 floors-default-to-1 behavior, the `requested`/`inferred`/`unknown`
  tagging, and the "no fabricated unknowns" guarantee all carry over exactly as before.
- **Alternatives considered**:
  - *Keep `StructuredRequirements` separate, add a cross-check between `target_built_area_m2` and
    `built_area_m2`*: rejected in favor of removing the duplicate field entirely — a cross-check still
    leaves two numbers a client has to reconcile; removing one is simpler and was explicitly requested
    scope ("`Project` should contain everything").
  - *Keep the separate `GET /projects/{id}/requirements` endpoint as a thin alias returning the same
    `Project`*: rejected as pointless — two URLs for one representation of one resource, with no
    behavioral difference, is just a maintenance burden.
