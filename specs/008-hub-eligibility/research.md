# Research: Hub Eligibility by Computed Feasibility

No NEEDS CLARIFICATION items remain in the spec; the decisions below fix the design choices the
plan depends on. Evidence: specs/005-hub-private-wing/RESULTS.md §6–§7.

## R1 — Where the bound is computed

**Decision**: a pure function `hub_bound(fw, fh, rooms, hub_widths, *, grid=0.25) -> HubBound` in
`concept_generator.py`, called by `generate_concepts` once per hub candidate (after `_hub_concept`
returns one), never inside `_plan_hub_wing`.

**Rationale**: `_hub_concept` already decides the lobby widths (all five, or the one a corridor
request pins) and the outline rectangle; the bound needs exactly those inputs. Keeping it out of
`_plan_hub_wing` honours FR-005 and keeps the sizing measured in v2 byte-identical.

**Alternatives considered**: computing eligibility from the delivered plan's rectangles after
realization (too late — the pipeline commits to the first realizable candidate); a width threshold
derived from the six outlines (a tuned number; the spec forbids it and Phase 0 shows the boundary
is not a single width — 14 × 16 fails, 13 × 15 passes).

## R2 — One model, not two

**Decision**: the engine's `hub_bound` becomes the reference; `hub_topology_bound.py`'s T1 generator
is replaced by an import of it (the other topologies stay in the tool as the Phase 0 record).

**Rationale**: two hand-written models of the same tree drift. The tool's T1 already encodes the
engine's rules (1.10 m opening, 0.20 m allowance, lobby caps, entrance-centred living, ensuite beside
its master); moving that code into the engine and importing it back keeps the harness honest.

**Alternatives considered**: leave the tool's copy — rejected for drift.

## R3 — What "eligible" means, exactly

**Decision**: eligible ⇔ among T1 sizings that seat every door-needing room and reach wet adjacency
≥ 0.80, the minimum over sizings of max(bedroom-class aspects) ≤ 1.35 **and** at that sizing master
≤ 1.40. Otherwise LAST_RESORT. The numbers are §6's; they are referenced from one place
(`HUB_GATES`) so the test and the harness read the same constants.

**Rationale**: FR-002; the same quantity Phase 0 tabulated ("gated bed-class"). The safe room is
reported in the bound but not gated (§6 has no safe-room gate).

**Alternatives considered**: gating on the ungated bound (wet ignored) — rejected, it let T1 pass
14.25 × 12.35 at 1.46 with 0 % wet; gating on medians of a population — not computable per brief.

## R4 — How "last resort" is expressed

**Decision**: ordering only. After the area-proximity sort and the twin extension, candidates whose
strategy is `HUB_PRIVATE_WING` and whose eligibility is LAST_RESORT are moved to the end, keeping
their relative order (forced tree before its twin, which the stable move preserves).

**Rationale**: FR-004; no score, no bonus; the first-realizable pipeline then reaches them only when
every other candidate (forced and twin) has failed. Eligible hub candidates are not touched, so
US1's "unchanged from v2" is by construction.

**Alternatives considered**: not generating the hub at all on ineligible outlines (turns the 7
counted rescues into refusals — SC-002 forbids); a ranking score (out of scope).

## R5 — Cost

**Decision**: 0.25 m grid over lobby depth, west flank width, the west flank's stack split, foot
depth and the foot boundary, with the lobby widths `_hub_concept` would try (≤ 5). Early exits:
stop when a sizing reaches the gates (eligibility needs only existence), and skip the wet-adjacency
evaluation for foot orders that cannot cluster (ensuite not at the bath's end).

**Rationale**: Phase 0's tool did the full enumeration in ~1.5 s per outline at this grid with no
early exit and six topologies; T1 alone with existence-exit is well under 50 ms on the wide outlines
(they fail late, so the whole grid is walked — bound that case in the test).

**Alternatives considered**: caching by (fw, fh, room multiset) — unnecessary at this cost; a
coarser grid — pessimistic near the boundary (Phase 0 saw 1.46 → 1.42 from 0.5 to 0.25).

## R6 — Diagnostics

**Decision**: the candidate's `rationale` gains a suffix `"; hub eligible (bound 1.27)"` or
`"; hub last resort (bound 1.65 > 1.35 bedroom gate, wet 100 %)"`; when a brief ends with no plan,
the hub's `ConceptRejection` detail (already emitted) is unchanged — the rationale text is what the
strategy recorder and the demo notes surface.

**Rationale**: FR-006 with no new fields on `ConceptCandidate`; the harness prints rationales.
