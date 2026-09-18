# Reference plan collection (V1)

A curated, rights-clean set of residential reference plans with structured metadata, for the
benchmark and for reviewers to compare generated plans against. This is data + policy, not code —
see `backend/tests/reference/test_reference_index.py` for the checks CI runs against it.

Scope note (V1): every entry is a **private house** (`dwelling_type: "private-house"`, matching
[`docs/wiki/decisions/private-house-v1-scope.md`](../../wiki/decisions/private-house-v1-scope.md)),
mostly single-level with a few multi-level examples, spanning the five footprint families the
product already distinguishes (`rectangle`, `wide-rectangle`, `narrow-deep`, `L`, `irregular` — see
[`docs/LAYOUT_SELECTION_UX_RESEARCH_REPORT.md`](../../LAYOUT_SELECTION_UX_RESEARCH_REPORT.md)).

## Files

| File | Purpose |
|---|---|
| `schema.json` | JSON Schema (draft 2020-12) for `index.json`. Every entry must validate against it. |
| `index.json` | The index itself: one metadata record per reference plan. |
| `<id>/` | Copied files for entry `<id>`, only where `rights` allows copying (see policy below). Most V1 entries have no such directory because their `rights` is `metadata-only`. |

## Rights policy

This collection exists to make architectural comparison possible without infringing on anyone's
rights, and — because this metadata may later inform product behavior — without ever training or
tuning on material we are not licensed to use that way. The rule is simple:

- **Copy the plan file itself only when rights are clear**: the plan was provided by its owner for
  this purpose (`rights: "owner"`), is public domain (`rights: "public-domain"`), or is under an
  open license that permits redistribution (`rights: "open-license"`, and `license` must name the
  exact license). Only then does a file go under `references/<id>/`, and the entry's `files` array
  lists it.
- **Otherwise, metadata only** (`rights: "metadata-only"`): record the descriptive fields, a
  `source_url` link and `notes` if available, but copy nothing. `files` MUST be an empty array and
  no directory `references/<id>/` may exist. This is the default whenever provenance or license is
  unclear, unverifiable, or restrictive — when in doubt, use `metadata-only`.
- **Never train on unlicensed plans.** A `metadata-only` entry's fields (dimensions, room counts,
  footprint family, notes) are analysis-safe to reference in documentation and benchmarks; the
  underlying drawing itself is not ours to copy, redistribute, or feed into any training or
  fine-tuning process.
- Every entry that does have `files` must have `rights` other than `metadata-only`, and vice versa
  — an entry whose `rights` is `metadata-only` must never have files on disk. This is a hard
  invariant, enforced by `test_no_files_for_metadata_only_entries`.

### V1 provenance note

The V1 set (`index.json`) is a scaffolding/coverage set: every entry is currently `metadata-only`,
because this collection was built with no network access and no owner-supplied plan files to copy
— see `git log` around this file for the Issue that introduced it. The entries themselves are
architecturally-grounded archetypes (footprint family × level count × room program combinations)
derived from this repository's own internal reference-plan census
(`docs/wiki/architecture/geometry-validation.md`, `specs/005-hub-private-wing/spec.md` §1), used to
exercise the schema and give the benchmark real coverage across footprint families today. Replacing
individual entries with real owner-provided, public-domain or openly-licensed plans (with a real
`source_url`/`license` and, where rights allow, copied files) is expected follow-up work and does
not require a schema change — only editing `index.json` entry by entry as in the workflow below.

## How to add an entry

1. Pick a unique, kebab-case `id` (also the name of `references/<id>/` for any files, including
   the annotation below).
2. Fill in every required field from `schema.json`: `title`, `dwelling_type`, `footprint_family`,
   `levels` (`level_count` optional), `bedrooms`, `bathrooms`, `total_area_sqm`, `rights`,
   `source_url`, `license`, `source`, `notes`, `files`, `annotation` (and `tags`/`added_date` if
   useful).
3. Decide `rights` first, honestly, per the policy above — this determines whether `files` may be
   non-empty.
4. If `rights` allows copying and you have the file(s), place them under `references/<id>/` and
   list their relative paths in `files`. If not, leave `files: []` and rely on `source_url`/`notes`.
5. Write `references/<id>/annotation.md` (this is original documentation, not a copied plan file,
   so it belongs under `references/<id>/` even for a `metadata-only` entry): a `## Why this plan
   works` section with 3-8 bullets each ending in the `docs/architecture_reference/quality_rubric.md`
   section it demonstrates (e.g. `[A]`), a `## Trade-offs` section with at least one real trade-off,
   and a `## Anti-patterns avoided` section linking into `docs/architecture_reference/anti_patterns.md`.
   Set `annotation: true` on the entry once this file exists.
6. Append the entry to the `entries` array in `index.json`.
7. Run the test suite:
   ```
   cd backend && uv run pytest -q tests/reference/test_reference_index.py
   ```
   It validates the whole index against `schema.json`, checks the minimum entry count, footprint
   family coverage, the `metadata-only` ↔ no-copied-files invariant, and that every entry has an
   annotation with rubric-tagged bullets and a trade-off.
