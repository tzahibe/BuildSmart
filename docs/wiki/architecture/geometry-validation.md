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
- `app/vertical_slice/quality_metrics.py` (M1–M6, Issue #17), `app/demo/contract.py`'s
  `QualityOut.metrics`, `tests/regression_corpus/{quality_baseline.json,test_quality_baseline.py,
  freeze_quality_baseline.py}` — see the dedicated section below.

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

## Architectural-quality metrics (M1–M6) and the corpus baseline

Issue #17 (2026-09-17). Hard validation (above) enforces the structural basics — no overlap, no
dead space, dimension/aspect/area maxima, reachability, declared access, bathroom access — but says
nothing about architectural QUALITY: room proportions, wet-room adjacency, circulation share,
public-zone contiguity. Six metrics, M1–M6, measure that on realized geometry:

- **M1** habitable-room aspect (long/short), median and worst, by room type.
- **M2** share of habitable rooms touching the exterior envelope.
- **M3** circulation (hall) share of total room area.
- **M4** doors opening onto the hall, and the hall's own long/short aspect.
- **M5** share of wet rooms (bathroom/toilet) sharing an interior wall with another wet room,
  the kitchen, or the laundry.
- **M6** whether the public zone (living/dining/kitchen) is one contiguous open-plan group.

**Authoritative implementation**: `app/vertical_slice/quality_metrics.py` —
`measure_design(design) -> QualityMetrics` for one plan, `summarize(designs) -> dict` for a
corpus-level report (medians/shares/by-type breakdowns). Side-effect-free, no planner/validation
coupling — read-only off a realized `app.demo.contract.DemoDesign`.
`spikes/failure_log_sweep/quality_metrics.py` is now just the corpus driver and printed report
around this module (previously it computed M1–M6 itself).

**Per-plan reporting**: `app.demo.contract.QualityOut.metrics` (a `QualityMetricsOut`) carries
M1–M6 for that one plan on every delivered `DemoDesign`, plus `dead_space_m2` (always `0.0` —
validation C2 already gates every delivered plan to zero residual interior area) and
`wasted_circulation_share` (the share of M3's circulation area sitting in a hall past the compact
threshold below — the portion of circulation that reads as a spine rather than a lobby, and so is
plausibly recoverable). Computed once, in `contract.to_demo_design`, from the same flattened
walls/open-interfaces/doors that function already builds.

**Corpus regression signal**: `tests/regression_corpus/test_quality_baseline.py` (REGRESSION tier,
`tests/conftest.py`'s shared TEST_MODE gating) recomputes `summarize()` over the 404 PLANNED cases
of the frozen 432-context corpus (`corpus.json`) and compares four load-bearing stats against a
committed baseline, `tests/regression_corpus/quality_baseline.json` — produced by the re-runnable
`tests/regression_corpus/freeze_quality_baseline.py`. Tolerances (percentage points for a share,
aspect-ratio units for M4; a metric moving in the IMPROVING direction never regresses):

| Metric | Tolerance |
|---|---|
| M3 circulation-share median | 2 pp |
| M4 hall aspect median | 0.2 |
| M5 wet-adjacency share | 2 pp |
| M6 public-contiguity share | 2 pp |

This is a **no-regression bar, not a new absolute one** — it passes unchanged on today's main and
exists only to catch a FUTURE planner/template change quietly making one of these four worse.

**CI cost (Issue #17 repair, 2026-09-18)**: gate-4 (`agent-regression.yml`) already replays the
whole corpus twice — merge-base and head, via `spikes/failure_log_sweep/corpus_snapshot.py` — to
check outcome/signature invariants; the test above replaying it a THIRD time, sequentially, in one
pytest process blew the 120-minute CI budget. `corpus_snapshot.py` now also records each PLANNED
context's `measure_design` output under `"metrics"` (plus two raw counts,
`m5_wet_adjacent_count`/`m5_wet_total_count`, folded into that same dict — not part of
`QualityMetrics`/`QualityOut`, only the snapshot's own copy, needed because M5's per-plan RATIO
alone cannot be pooled back into a corpus-level share: plans have different wet-room counts, so an
unweighted mean of per-plan ratios is a different number — 11.7 pp off on this corpus, ~6x the
tolerance — from `summarize()`'s pooled adjacent/total share). When gate-4's `CORPUS_SNAPSHOT` env
var points at that snapshot, `test_quality_baseline.py` reads the stored `"metrics"` and computes
the same four stats via `quality_metrics.baseline_summary_from_metrics` WITHOUT calling
`generate_demo_design` again; without the env var (developer runs), it replays the corpus exactly
as before. M3/M6 reproduce `summarize()`'s aggregation exactly either way (both are already
per-plan values there); M4 does too on today's corpus (every plan has at most one hall room) but
would only approximate on a future corpus with multi-hall plans, the same way a naive M5 does.
`freeze_quality_baseline.py --from-snapshot SNAPSHOT.json` freezes the baseline from a snapshot
the same way, with no corpus replay.

**Measured gaps against 21 professional Israeli plans** (visual census, 2026-09-11 —
memory `architectural-quality-gaps-measured`; the same figures Issue #17's own "Current behavior"
cites): exposure (~100%, M2) and circulation share (median ~11% vs reference 8–14%, M3) are
already at reference level — NOT gaps. Three real gaps, ranked:

1. **Circulation topology**: one hall spine, long/short median 9.4, 0% compact, vs ~18/21
   reference plans having a compact "room lobby" hub (~2.5–3.5 m square, 4–7 doors) bedrooms wrap
   on up to 3 sides. The structural change spec 005 (hub parti) attempted and was rejected —
   see below.
2. **Wet-room adjacency**: 40% of bathrooms share a wall with a wet room/kitchen/laundry vs
   ~85–90% in the reference set (M5).
3. **Public rooms come out as strips**: KITCHEN median aspect 2.75, DINING 2.35, vs reference
   kitchens as an L-counter inside one open volume, not a room with its own shape (M1, public
   rooms).

## Architectural quality rubric and anti-pattern library

The measured gaps above (circulation topology, wet-room adjacency, public-room strips) are three
entries in the canonical, repo-wide quality rubric and anti-pattern library:
`docs/architecture_reference/quality_rubric.md` (sections A–O) and
`docs/architecture_reference/anti_patterns.md`. Every later geometry/circulation/interior Issue and
every reviewer should consult those files rather than re-deriving quality judgments from this page
alone.

## Known follow-ups

**PROPOSED, not scheduled — Issue #17 explicitly keeps these as write-ups, not new Issues:**

- **Public-room strip fix through the quality tier.** Gap 3 above (KITCHEN/DINING strips) is the
  same shape the room-proportion quality tier (see that Wiki page) already re-proportions bedrooms
  away from — extending that tier's row-sharing/re-proportioning logic to the public band's rooms
  is a plausible, incremental fix that does not touch the planner's topology. Not designed or
  measured yet; the quality tier's own known limits (row-sharing topology ceiling) would need
  re-checking against public-band rows specifically.
- **Private-wing lobby topology** (gap 1, the largest measured gap). Spec 005 (hub-private-wing)
  already tried this — v1 through v2.1, `specs/005-hub-private-wing/` — and was rejected on two
  hard acceptance gates (see `specs/005-hub-private-wing/RESULTS.md` and the
  `row-sharing-topology-limit-and-quality-tier` / `seam-shape-selection-investigation` memories for
  what was tried since and why it did not close the gap). Re-attempting the hub parti is
  explicitly OUT OF SCOPE for Issue #17; any future attempt should start from why v1–v2.1 failed,
  not repeat the same seat count.

Beyond these two: none currently tracked at the Wiki level from the pre-#17 state of this page.

## Evidence/history

`docs/SPATIAL_ENGINE_SPEC_V2_1.md` (the frozen domain model), `docs/GENERAL_GEOMETRY_DOMAIN_V1_REPORT.md`,
`docs/SAFE_GEOMETRY_ADAPTER_V1_REPORT.md`, `docs/REALIZED_CONNECTIVITY_INVARIANT_REPORT.md`,
`docs/GEOMETRY_DERIVED_OPEN_INTERFACES_REPORT.md`, `docs/AUTHORITATIVE_SITE_GEOMETRY_P0_REPORT.md`,
`docs/SITE_AWARE_FOOTPRINT_OPTIONS_REPORT.md`, `specs/005-hub-private-wing/spec.md` §1 (the 21
professional plans' reference values) and `RESULTS.md` (why the hub parti was rejected).

## Last verified against git

`8bd17a2` (branch `agent/17-architectural-quality-baseline-m1-m6-as`, based on `origin/main`);
the M1–M6 section above documents work landing on this branch (Issue #17), verified against this
session's own implementation and test runs, not independently re-verified beyond that.
