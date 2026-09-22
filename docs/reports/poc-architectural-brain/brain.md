# POC Architectural Brain — retrieval, synthesis, adaptation (Issue #95)

Given a `Brief` (`spikes/architectural_brain/brief.py`: `app.vertical_slice.spec.ProgramSpec` plus
a few POC-only architectural preferences) + a `PlotSpec` site, this package retrieves real
reference plans from the Issue #94 corpus, synthesizes 2-3 candidate `ConceptSpec`s that each
combine patterns from several references, and adapts a candidate to the brief with named
semantic/topological operations. Code: `backend/spikes/architectural_brain/{brief,corpus_io,
retrieval,synthesis,adaptation}.py`. Tests: `backend/tests/architectural_brain/test_{retrieval,
synthesis,adaptation,architect_hints}.py`. See `dataset.md` for the corpus/`PlanReference`/
`ArchitecturalPattern` this all reads, and `architect-model.md` for the separate hint
investigation.

## `Brief` (`brief.py`)

`program: app.vertical_slice.spec.ProgramSpec` is reused, not duplicated — the same hard-
requirements contract the live vertical slice already validates against (bedrooms, safe_room,
wet_rooms, wet_room_kinds, `relationships`, `target_built_area_m2`). `stories`,
`circulation_preference`, `outline_preference`, `zoning_preference`, `exposure_requirement` are
this POC's own additions: non-binding SCORING preferences retrieval reads, with no equivalent on
`ProgramSpec`/`HouseConcept`. `site: app.vertical_slice.spec.PlotSpec` is passed separately to
`retrieve`/`adapt`.

## `retrieve(brief, site, corpus, k=8)` (`retrieval.py`)

Nine deterministic terms, weighted, summed — never text embeddings:

| Term | Weight | What it measures |
|---|---|---|
| `built_area` | 0.15 | closeness of `target_built_area_m2 / stories` to the plan's `footprint_area_m2` |
| `room_count_types` | 0.20 | normalised L1 closeness of {BEDROOM, WET, KITCHEN, LIVING, SAFE_ROOM} counts |
| `footprint_aspect_shape` | 0.10 | bbox-aspect closeness (site buildable region vs plan footprint) + outline_preference match (TWO_WING vs RECTANGULAR) when stated |
| `adjacency` | 0.10 | share of `ProgramSpec.relationships` realized on the plan's `adjacency_edges`/`access_edges` |
| `public_private_org` | 0.10 | exact match of `zoning_preference` against `ArchitecturalPattern.zoning` |
| `circulation_class` | 0.15 | exact match of `circulation_preference` against `ArchitecturalPattern.circulation_class` |
| `floors` | 0.05 | flat penalty for `stories > 1` (the whole corpus is single-storey — see `dataset.md`) |
| `wet_room_requirements` | 0.10 | 60% wet-room count closeness + 40% ensuite-share match against `wet_room_kinds` |
| `exterior_exposure` | 0.05 | plan's `exposure_pattern` against `exposure_requirement`, when both are measurable |

Weights sum to 1.0 (`WEIGHTS` in `retrieval.py`, asserted at import time). A term whose brief-side
input is unstated contributes a fixed **neutral 0.5**, not a dropped/renormalised weight — every
candidate gets identical credit on that term, so an unstated preference cannot discriminate
between plans (equivalently: not scoring on it), without needing to change the total's meaning
between briefs that do and don't state a preference.

**Why this isn't "ordered by area alone"**: `footprint_aspect_shape` + `circulation_class` combine
to 0.25 of the total — more than `built_area`'s 0.15 — so a brief stating an outline/circulation
preference can and does out-rank same-area plans that don't match it. `test_retrieval.py` proves
this two ways: two benchmark briefs sharing `target_built_area_m2=140` retrieve different top-3s
(`test_same_area_different_programme_retrieves_a_different_top_three`), and an L-outline brief's
actual top-3 differs from what a pure area-distance ranking of the same corpus would produce
(`test_area_only_ranking_would_disagree_with_actual_ranking`).

Every `RetrievedReference` carries all nine `TermScore`s (weight, raw score, weighted
contribution, a numeric `detail` string) and a `why` built from its top-3 contributing terms —
never a bare number. Results are sorted by `(-total_score, plan_id)` — deterministic, ties broken
by plan id — and `retrieve` is a pure function of its inputs (no randomness, no caching that could
drift between calls).

**Known limitation**: `adjacency`'s `NEAR` and `ADJACENT` `RoomRelation`s are both approximated by
physical touching (`PlanReference.adjacency_edges`) — the corpus has no independent notion of
"near but not touching," so this is a coarser check than `app.vertical_slice.relationships
.resolve_reference`'s own `NEAR` semantics. Documented, not hidden.

## `synthesize(brief, references)` (`synthesis.py`)

For candidate `i` (best-first over the retrieved references): `primary = references[i]` supplies
`circulation_class`/`zoning`/`wet_core_strategy` (the three fields `topologically_distinct`
compares); `secondary = references[i+1 mod n]` (a DIFFERENT plan) supplies
`entrance_relationship`/`bedroom_grouping_share`. A candidate is kept only if its
`(circulation_class, zoning, wet_core_strategy)` triple hasn't already appeared — so the returned
list is pairwise topologically distinct by construction. Stops at 3 candidates or once every
reference has been tried as a primary.

Every candidate's `bedrooms`/`safe_room`/`wet_rooms`/`wet_room_kinds`/`stories` are copied straight
from `brief.program` — NEVER derived from a reference — so every authoritative requirement is
present on every candidate regardless of which references contributed patterns.
`ConceptSpec.baseline_rooms` carries the primary donor's own `Room`s (areas/types), the starting
point `adaptation.py` works from; nothing in `ConceptSpec` is a copied room LIST from one
reference, since the 5 pattern-level fields above are combined from >= 2 references while the room
areas themselves are only a starting point adaptation is required to change (see below).

`topologically_distinct(a, b)` is the same rule `app.vertical_slice.concept_spec
.topologically_distinct` uses: unequal on any of `(circulation_class, zoning, wet_core_strategy)`.

## `adapt(concept, brief, site)` (`adaptation.py`)

Three semantic operations (`Adaptation{kind, before, after, reason}`), applied to
`concept.baseline_rooms`:

- **`RESIZE_ROOMS`** (always): each room's area is replaced by a **fixed per-TYPE target**
  (`TARGET_AREA_M2`), never a single scale factor applied to every room. Because each donor room's
  own area differs from its type's fixed target by a different relative amount, the before/after
  ratio necessarily differs per room type — this is the concrete, testable meaning of "changes
  room-area ratios non-uniformly, no global scaling" (`room_area_ratios`, asserted in
  `test_adaptation.py`).
- **`BEDROOM_COUNT_ADJUST`** (when the donor's bedroom count != `brief.program.bedrooms`): adds
  (at the fixed bedroom target area) or removes bedroom-type rooms to match.
- **`WET_ZONE_ADJUST`** (when the brief needs an ensuite but the donor's `wet_core_strategy` is
  `CLUSTERED`, i.e. all wet rooms in one block with no bedroom relationship): relabels the
  strategy to `MIXED`.

**Rejection** (`Rejection{concept_id, reason}`, never a crash, never a silently-wrong plan):

- the site's buildable area (`PlotSpec.buildable_size_m()`) is below the summed MINIMUM area of
  every authoritative room the brief requires (`MIN_AREA_M2`) — generalises "no place for the
  SAFE_ROOM" to one measurable check covering every authoritative room type.
- the brief requires an ensuite but the donor's `wet_core_strategy` is `UNKNOWN` (zero measured
  wet rooms on the donor plan at all — no placement evidence exists to adapt an ensuite
  relationship from) — "wet core unreachable".

Both rejection rules are exercised by hand-built synthetic cases in `test_adaptation.py`
(`test_rejects_when_the_site_has_no_room_for_the_brief_authoritative_rooms`,
`test_rejects_when_the_wet_core_is_unreachable_for_an_ensuite_request`).

## Scope note

This package is realization-adjacent, not a realization: `AdaptedRoom` carries only `(id,
room_type, area_m2)`, never a polygon/wall/door — actually placing an adapted concept's rooms on
the site's buildable region is Issue #95's sibling POC agent C's job (out of scope here, per the
Issue's "Out of scope" list).
