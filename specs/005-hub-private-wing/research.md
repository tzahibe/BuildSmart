# Research: Hub-Organised Private Wing

Every decision below was resolved by reading the current code (paths and line references are to the
tree at commit `2e19d89`) or by a measurement already made, not by assumption. Where the spec left a
question open (§9), the answer is recorded here and the spec's number stands.

## R1 — The hub's zone id is `HALL`; only its template is new

**Decision**: the hub `ProgramRoom` is `ProgramRoom("HALL", ProgramRole.HALL, ZoneGroup.CIRCULATION,
HUB_TEMPLATE)` — the variant's HALL room with its template swapped for the hub's. No new
`ProgramRole`; `_roles_of` and `geometry_core/model.py` are untouched.

**Rationale**: the literal id `"HALL"` is load-bearing in five places that must not change:
`Concept(fixture, "HALL", Side.N, …)` in `_concept_from`/`_front_band_concept`;
`_contains_hall` (the twin keeps every cut on the root→`HALL` path forced);
`_build_access(hall_ids=["HALL"], hall_for=…)`; the corridor measurement `realized_corridor_width_m_of`
(`demo/service.py:223`) and `demo/contract.py:297`, which select circulation by roles `HALL`/`CIRCULATION`;
and the Hebrew label map (`requirements_view.py:219`, `contract.py:24`). A second circulation id
(`HALL_MAIN`/`HALL_SPUR` already appear in the label map) is the v2 "entrance lobby + room lobby"
design, not v1.

**Alternatives considered**: a new id `ROOM_LOBBY` — rejected for v1 because C14 and the twin logic
would need to learn it, which is Geometry-adjacent churn for no user-visible gain.

## R2 — Where the strategy plugs in, and what "tried before the spine partis" actually means

**Decision**: `generate_concepts` calls `_hub_concept(spec, variant, primary.rect)` for each variant
right after `_front_band_concept`, appending its candidate to `accepted` (and its rejection to
`rejections` when `variant is rooms`). Nothing else in the loop changes.

**Rationale**: `accepted` is then sorted by `(|used_area − target|, used_area, strategy.value)`
(`concept_generator.py`, end of `generate_concepts`) whenever the brief has a target area — which every
demo brief does. So the order candidates are TRIED in is area-proximity first; insertion order only
breaks exact ties, and within a tie `"HUB_PRIVATE_WING"` sorts after `"FRONT_PUBLIC_BAND"` and before
`"SPINE_*"`. The spec's Q5 phrasing "before the spine partis" is therefore satisfied for equal-area
ties and otherwise decided by which proportion lands nearest the ask. This is documented, not changed:
altering the sort would reorder existing plans and break the byte-identical gate.

**Consequence for the twin**: the twins are appended after the sort for every accepted candidate, so
a hub tree whose forced positions the solver refuses falls through to its unforced twin exactly like
the other partis — no hub-specific code.

## R3 — Tree shape (v1: public band in front, hub wing behind)

**Decision**:

```
Split(H, band_tree,                                   # public zones across the front (existing helper)
      Split(H, hub_band, foot_band, D_hub),           # the wing
      D_band)
hub_band  = Split(V, Leaf(flank_west), Split(V, Leaf("HALL"), Leaf(flank_east), W_hub), W_west)
foot_band = _forced_v_chain([r1, r2, (r3)], widths)   # 2–3 rooms; an ensuite shares its master's slot
```

`band_tree` is the existing `_forced_v_chain(public, public_widths)`; the first public zone must span
the hub's x-range (see R6).

**Rationale**: the root→`HALL` path is `root(H) → wing(H) → hub_band(V) → inner(V)`; `_contains_hall`
keeps exactly those four cuts forced in the twin, so the hub's rectangle — width `W_hub`, depth
`D_hub` — is never moved by the solver, while the foot band's internal widths and the band's internal
widths are released. That is the same contract the corridor already has in the existing partis.

**Alternatives considered**: a head band of wet rooms above the hub (as most references have) — in
this regime it would sit between the public band and the hub and sever the hub's cased opening; it
belongs to the side-by-side regime (v2). Two foot bands — rooms in the second would not touch the hub
and would have no door; rejected for v1.

## R4 — Door and opening geometry: 1.10 m, measured in the solver's own units

**Decision**: a foot-band room is eligible for a hub door only if its x-range overlaps the hub's by
≥ `INTERIOR_DOOR_WIDTH_M + 2·DOOR_MARGIN_M = 0.9 + 0.2 = 1.10 m` (`doors.py:24-26`, applied at
`doors.py:118` as `shared_u >= width_u + 2*margin_u`). Flank rooms share the hub's full depth
(`D_hub ≥ 2.8`) and always qualify. The public zone above the hub must overlap it by ≥ 1.10 m for the
`CASED_OPENING` (same rule, same placer).

**Rationale**: `DesiredAccessEdge.min_clear_m = 0.9` (`model.py:300`) is intent; the placer's 1.10 is
what decides, and C13 then reports "shares X m of wall but no placeable opening was generated". The
allocator rejects rather than shrinks when an overlap is short (spec FR-4).

**Consequence**: with `W_hub ∈ [2.4, 3.6]`, at most two foot-band rooms can each overlap ≥ 1.10 m
(three only at `W_hub ≥ 3.3` with narrow wet rooms). Realistic hub degree in v1 is **4–5**: two
flanks, two or three below, plus the cased opening above, which is a public connection and not
counted in FR-5's 4–7.

## R5 — Interior rooms and daylight

**Decision**: wet rooms and the laundry may be interior; habitable rooms may not.

**Rationale**: an interior wet room gets `ventilation_status = MECHANICAL_VENTILATION_REQUIRED`
(`windows.py:55,101,113`), a descriptive label that no check refuses. C8 requires a placeable window
for every zone whose roles intersect `DAYLIGHT_ROLES` (`validation.py:251`). In the v1 tree every
flank room touches the wing's side, every foot-band room touches its bottom — all on the envelope — so
C8 is satisfied by construction and the allocator does not need to reason about it. The 5 C8 losses
seen when ALL cuts were released came from the front band's rear split moving; the hub tree keeps that
band/wing cut forced (R3), so the same failure cannot occur here.

## R6 — The cased opening to the public zone needs no `_build_access` change

**Decision**: call `_build_access(rooms, ["HALL"], public_ids, open_plan, hall_for,
hall_borders_only_first_public=True)` exactly as `_front_band_concept` does.

**Rationale**: that flag makes `_build_access` declare `HALL → public_ids[0]` as `CASED_OPENING` and
chain the remaining public zones with doors (`concept_generator.py`, `_build_access` body); with
`open_plan` it declares the public group `OPEN_CONNECTION` and still opens the hall onto the first
zone. So the only geometric obligation is R4's ≥ 1.10 m overlap between `public_ids[0]` and the hub,
which `_plan_hub_wing` guarantees by sizing the first public zone to span the hub's x-range — the same
rule `_plan_front_band` already applies ("the first public zone must span the hall's x-range").
`OPEN_CONNECTION` is not used for the hub: `engine.py:376-386` requires the shared edge to equal the
full side of both rectangles, impossible for a hub flanked by rooms.

## R7 — FLEX is refused

**Decision**: `_hub_concept` returns `ConceptRejection(INSUFFICIENT_WING_AREA, …)` when any room's role
is `FLEX`, with the same rationale text `_front_band_concept` uses.

**Rationale**: FLEX exists to absorb surplus the spine partis have no mechanism for; the front band
absorbs surplus through its own elasticity and refuses FLEX for double counting
(`concept_generator.py`, `_front_band_concept`). The hub parti shares the front band's public
treatment and therefore the same argument. Over-capacity briefs (197 of the 418 scenarios) are an area
problem that the capacity refusal now explains; the hub is not for them.

## R8 — Eligibility and v1 capacity

**Decision**: offer the hub only when `program.bedrooms ≥ 3`; reject with `ACCESS_DEGREE_EXCEEDED` when
the rooms that need a hub door exceed what two flanks plus the foot band can seat under R4.

**Rationale (measured)**: of the 25 concept-stage generic refusals, 15 have ≥ 3 bedrooms and 14 of
those are ≥ 8.2 m wide — the regime this tree needs. References with two bedrooms use a small lobby,
not a hub. Rooms needing a hub door = bedrooms (master counts once; its ensuite is entered from it) +
safe room + shared wet rooms; a 3BR + safe + 2-wet brief needs 5 and fits (flank, flank, foot ×3 at
`W_hub ≥ 3.3`); 4BR + safe + 3-wet needs 7 and does not — it falls through to the spine partis, which
is the correct v1 behaviour and is what the fall-through ordering guarantees.

## R9 — Sizing follows the existing pattern

**Decision**: areas from `scale_program(rooms, Σ target areas)` as the front band does ("modest",
sized from the programme rather than the whole footprint so the bedrooms are not inflated); `D_hub` =
max(flank rooms' `min_short_side + inset`, hub template `min_short_side + inset`, area quotient);
foot-band depth from `_row_depths` semantics (area quotient floored by the band's largest
`min_short_side + inset`); widths within the foot band from `_row_widths` (minimums first, surplus by
area); `W_hub` searched over `{2.4, 2.7, 3.0, 3.3, 3.6}` nearest the hub template's target first;
footprint proportions from `_proportions` as every parti does. Band depth = whatever the wing does not
need, capped by the binding public room's `max_area_m2` exactly as `_plan_front_band` does.

**Bound**: 5 hub widths × ≤ 14 proportions × ≤ 7 depths per proportion — the same order as the front
band's `split_options` loop. Deterministic: no randomness, fixed iteration orders.

## R10 — Measurement harness becomes part of the repo

**Decision**: promote `sweep.py`, the toggle A/B and `quality_metrics.py` from the session scratch
directory into `backend/spikes/failure_log_sweep/` as a task, parameterised by a toggle callable so the
hub A/B (enabled vs disabled) and any future parti use one script.

**Rationale**: every gate in spec §6 is a number those scripts produce; a gate that can only be run
from one person's scratch directory is not a gate.
