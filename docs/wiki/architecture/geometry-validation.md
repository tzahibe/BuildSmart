# Geometry / Validation

Status: IMPLEMENTED_MERGED

## Current behavior

`app/geometry_domain/` provides Shapely-backed booleans/offsetting, primitives, transforms, walls,
and linearization — used instead of hand-rolled polygon math because robust boolean geometry is
exactly where hand-rolled code fails silently. `app/geometry/spatial_v2/` holds the frozen
domain-model foundation (`SPATIAL_ENGINE_SPEC_V2_1.md`). Realized-plan validation runs a family of
lettered checks (referenced throughout other Wiki pages as e.g. C17, C20, C21, C22) that hold a
drawing to hard limits (aspect ratio, area maxima, seam/access correctness) regardless of which
planner path produced the candidate — a quality-tier or repartition candidate is never exempt from
them (see Room Proportion / Quality Tier). Building-level checks (the "V" family, e.g. V2, V7) are
kept separate from per-level "C" checks for multi-level buildings.

Open interfaces (doors/openings between rooms) are derived from the realized geometry itself
(`GEOMETRY_DERIVED_OPEN_INTERFACES_REPORT.md`, 636 tests) rather than declared separately —
superseding an earlier declared-interface architecture.

## Authoritative implementation

- `app/geometry_domain/{booleans,primitives,transforms,walls,linearize,constraints,provenance,
  units}.py`.
- `app/geometry/spatial_v2/` (the frozen domain model).
- `app/vertical_slice/validation.py`, `building_validation.py` (the C/V check families).
- `docs/GEOMETRY_DERIVED_OPEN_INTERFACES_REPORT.md` (derived-interfaces architecture, 636 tests).

## Current constraints/invariants

- Hard limits (max aspect ratio, area maxima) are enforced identically regardless of which planner
  mechanism produced a candidate — quality-tier/repartition candidates get no exemption.
- Per-level "C" validation and building-level "V" validation are kept separate for multi-level
  buildings (see Multi-Level).
- Open interfaces are derived from realized geometry, never declared as a separate, potentially
  inconsistent source of truth.

## Supersedes

`docs/BRANCHED_CIRCULATION_ARCHITECTURE_REPORT.md` (superseded once open-interface derivation
landed); `docs/GENERAL_GEOMETRY_ARCHITECTURE_REPORT.md` (research-only, superseded by
`GENERAL_GEOMETRY_DOMAIN_V1_REPORT.md`); `docs/SPATIAL_ENGINE_RESEARCH.md` and
`docs/SPATIAL_ENGINE_SPEC_V2.md` (both explicitly superseded by `SPATIAL_ENGINE_SPEC_V2_1.md`).

## Known follow-ups

None currently tracked at the Wiki level beyond what individual feature pages (Multi-Level, Room
Proportion) already list.

## Evidence/history

`docs/SPATIAL_ENGINE_SPEC_V2_1.md` (the frozen domain model), `docs/GENERAL_GEOMETRY_DOMAIN_V1_REPORT.md`,
`docs/SAFE_GEOMETRY_ADAPTER_V1_REPORT.md`, `docs/REALIZED_CONNECTIVITY_INVARIANT_REPORT.md`,
`docs/GEOMETRY_DERIVED_OPEN_INTERFACES_REPORT.md`, `docs/AUTHORITATIVE_SITE_GEOMETRY_P0_REPORT.md`,
`docs/SITE_AWARE_FOOTPRINT_OPTIONS_REPORT.md`.

## Last verified against git

`1d648c3` (main HEAD). Presence in `main`'s history confirmed via `git log --oneline main`; not
independently re-verified line-by-line this round (confidence: medium, consistent with
`doc_status.json`).
