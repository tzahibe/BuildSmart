# [agent] Reference plan collection V1: metadata schema, index, rights policy and the first curated set

### Goal

A curated, rights-clean V1 set of residential reference plans with structured metadata that the benchmark
and the reviewers can use.

### Current behavior

No reference set exists in the repository; the only external evidence is the one-off measurement of 21
professional plans recorded in the quality-gap investigations (not stored, not annotated).

### Required behavior

1. `docs/architecture_reference/references/schema.json`: the metadata schema (fields listed in the EPIC,
   plus `rights: owner|public-domain|open-license|metadata-only`, `source_url`, `license`, `files`).
2. `docs/architecture_reference/references/README.md`: the rights policy (copy only owner-provided,
   public-domain or openly licensed material; otherwise metadata + link + notes; never train on unlicensed
   plans) and how to add an entry.
3. `references/index.json` with ≥ 30 entries (target 30–50): private houses first, single-level first, a few
   multi-level, footprints rectangle / wide rectangle / narrow-deep / L / irregular; each entry validated
   against the schema; copied files only where rights allow, under `references/<id>/`.
4. A test that validates the index against the schema, the minimum count, the footprint coverage and that
   every copied file has a non-`metadata-only` rights status.

### Acceptance Criteria

- AC-1: `references/schema.json` and `references/README.md` exist and the README states the rights policy
- AC-2: `references/index.json` validates against the schema, has ≥ 30 entries and covers the five footprint families
- AC-3: no copied plan file exists for an entry whose rights are `metadata-only`

### Out of scope

Annotations (sibling), the benchmark (sibling), regulation material.

### Affected domains

knowledge

### Risk

LOW

### Resource class

MEDIUM

### Dependencies

none

### Required locks

docs (shared)

### Verification plan

- AC-1 -> file:docs/architecture_reference/references/schema.json ; grep:docs/architecture_reference/references/README.md:metadata-only
- AC-2 -> pytest:backend/tests/reference/test_reference_index.py::test_index_validates_and_has_at_least_thirty_entries ; pytest:backend/tests/reference/test_reference_index.py::test_footprint_families_are_covered
- AC-3 -> pytest:backend/tests/reference/test_reference_index.py::test_no_files_for_metadata_only_entries

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

docs/architecture_reference/references/* (new).

### Knowledge check

Consulted: EPIC 0 knowledge check; no reference data exists anywhere in the repo (grep for `reference` under docs finds only investigation reports).
