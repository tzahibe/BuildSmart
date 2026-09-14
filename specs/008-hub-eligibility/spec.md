# Feature Specification: Hub Eligibility by Computed Feasibility

**Feature Branch**: `008-hub-eligibility`

**Created**: 2026-09-14

**Status**: Draft — from Hub v3 Phase 0 (specs/005-hub-private-wing/RESULTS.md §7)

**Input**: "Offer the hub parti as the primary plan only where the lobby wing can meet the §6 quality gates on that outline — a feasibility computed from the outline and the brief, not a tuned width threshold — and keep it as a last resort elsewhere, so no rescued plan turns back into a refusal."

**Baseline**: branch `007-wet-room-semantics` at `30e2312` (hub v2 + the interim shared-bathroom guard). On the 426-scenario failure log: 107 plans, 19 of them hub primaries, 10 hub-only rescues (7 at ≥ 80 % of the ask); hub population bedroom 1.57 / master 1.61 / wet 79 % against gates 1.35 / 1.40 / 80 %.

## What Phase 0 established *(the evidence this spec is built on)*

1. The v2 hub tree (T1) is the only three-band tree that seats the five doors a 3-bedroom + safe-room + 2-wet brief needs on the lobby **and** clusters the wet rooms; every non-stacked or hybrid tree loses a seat by construction, side-by-side loses bedroom exposure.
2. T1's stack fixes the lobby band at ≥ 4.6 m; on outlines ≥ 14 m wide the bedroom-class rooms cannot all get under the gate by any sizing (14.25 × 12.35 → 1.65, 18 × 12 → 2.38, 14 × 16 → 1.42), while narrow-deep outlines pass (13 × 15 → 1.32, 12 × 18 → 1.27, 10 × 20 → 1.27).
3. With three wet rooms T1 tops out at 67 % wet adjacency on every outline.
4. Sizing (v2.1) only moves the strip from one room to another; the miss is topological.

So the hub should be *selected* by whether it can be good, and the wide-shallow outlines belong to the front-band / spine partis, whose bedrooms already sit at 1.31.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A hub plan is delivered only where it can be a good hub (Priority: P1)

A person asks for 3 bedrooms, a safe room and 2 wet rooms on a 12 × 18 m outline and gets the room-lobby plan; the same brief on 18 × 12 m gets the front-band plan with near-square bedrooms instead of a lobby wing with 2.4-aspect strips.

**Why this priority**: the hub was built as a quality feature; delivering it where it is measurably worse than the plan it displaces defeats the purpose and is what §6 currently shows (9 of 19 hub primaries are wide-shallow).

**Independent Test**: run the harness on the 426 scenarios; every hub primary that remains passes the bedroom/master/wet gates as a population; the displaced wide-shallow primaries revert to non-hub plans that already existed (hub OFF baseline).

**Acceptance Scenarios**:

1. **Given** a brief and outline for which the computed bound passes, **When** concepts are generated, **Then** the hub candidates are ordered exactly as today (area-proximity sort) and the delivered plan is unchanged from v2.
2. **Given** a brief and outline for which the bound fails, **When** another parti can plan it, **Then** that parti's plan is delivered, byte-identical to the hub-OFF plan.

---

### User Story 2 - A rescued plan never becomes a refusal (Priority: P1)

The 14.25 × 12.35 m, 3-bedroom + safe-room brief planned only through the hub; with the hub demoted it must still get that plan — as the last resort, after every other parti has been tried — rather than the generic refusal it had before feature 005.

**Why this priority**: 7 counted gains (≥ 80 % of the ask) are wide-shallow outlines the bound fails; a policy that refuses them is a measured regression.

**Independent Test**: harness LOST = 0 and plans 107 → 107; the 10 hub-only rescues are still delivered with `HUB_PRIVATE_WING` as the strategy.

**Acceptance Scenarios**:

1. **Given** an outline the bound fails, **When** no other candidate realizes, **Then** the hub candidate (and its unforced twin, in that order) is tried and delivered.
2. **Given** an outline the bound fails, **When** the hub is delivered as the last resort, **Then** the rationale says so and carries the bound's figure.

---

### User Story 3 - The decision is explainable (Priority: P2)

A developer reading a plan's rationale or a refusal's diagnostics sees "hub demoted on this outline: best reachable bedroom-class aspect 1.65 (gate 1.35), wet adjacency 100 %" — the same numbers the harness prints.

**Independent Test**: unit test on `generate_concepts` output for a wide and a narrow outline.

**Acceptance Scenarios**:

1. **Given** a demoted hub candidate, **When** its rationale is read, **Then** it names the failing gate and the bound value.

---

### Edge Cases

- Three wet rooms: the bound never reaches the wet gate (67 %), so the hub is always last resort for those briefs — this follows from the computation, no special case.
- A requested corridor width: the bound is computed with the requested lobby width only (as `_hub_concept` already restricts it).
- FLEX briefs: the hub is not offered at all (unchanged).
- The unforced twin of a demoted hub is demoted with it (twins keep their forced tree's order rule: all forced trees first, then all twins; among last-resort candidates, forced before twin).
- An outline exactly at the gate (bound = 1.35): passes — the gate is `≤`.
- The bound's model must be no more permissive than `_plan_hub_wing` on the same outline where it matters: a bound that passes but a plan that the engine cannot realize simply falls back as today; a bound that fails where the engine would have made a good plan is the risk to measure (SC-005).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The concept stage MUST compute, for a hub candidate's outline and brief, the best reachable bedroom-class aspect among T1 sizings that satisfy access (≥ 1.10 m lobby edge per door-needing room) and the wet-adjacency gate — the same rectangles and rules as `hub_topology_bound.py`, restricted to the widths `_hub_concept` would use.
- **FR-002**: A hub candidate is **eligible** when that bound is ≤ the §6 bedroom gate (1.35) with master ≤ 1.40 and wet adjacency ≥ 80 % reachable. No new numbers: the gates are §6's.
- **FR-003**: Eligible hub candidates MUST be ordered exactly as today (inserted last, then the area-proximity sort, twins after all forced trees).
- **FR-004**: Ineligible hub candidates (forced tree, then its twin) MUST be appended after every other candidate, including the other partis' twins, so they are realized only when nothing else does.
- **FR-005**: Non-hub candidates, `ROOM_TEMPLATES`, `HUB_TEMPLATE`, `_plan_hub_wing` and Geometry Core MUST be untouched.
- **FR-006**: The candidate's rationale (and the rejection diagnostics when nothing plans) MUST carry the bound value, the failing gate and the eligibility decision.
- **FR-007**: The computation MUST be deterministic and bounded: a 0.25 m grid over the wing's decisions on one outline, ≤ 50 ms per brief in the sweep's median.

### Key Entities

- **HubBound**: for (outline width, depth, brief rooms, lobby widths) → best gated bedroom-class aspect, master aspect, safe-room aspect, seats seated/required, best wet adjacency.
- **HubEligibility**: ELIGIBLE | LAST_RESORT with the HubBound that decided it.

## Success Criteria *(mandatory)*

Measured with `spikes/failure_log_sweep/` on the 426 scenarios against the `30e2312` baseline, in frozen worktrees.

- **SC-001**: Non-hub primary plans byte-identical: 88/88 of the hub-OFF plans unchanged.
- **SC-002**: LOST = 0; plans 107 → 107; the 10 hub-only rescues still delivered.
- **SC-003**: The remaining hub primaries, as a population, pass all eight §6 gates — bedroom ≤ 1.35, master ≤ 1.40, wet ≥ 80 %, lobby ≤ 1.5 in 100 %, doors 4–7, exposure 100 %, circulation ≤ 14 %.
- **SC-004**: Each displaced wide-shallow primary reverts to its hub-OFF plan; on those plans the bedroom median is ≤ 1.35 (the non-hub population's 1.31).
- **SC-005**: No outline where v2 delivered a hub plan passing all three gates loses it (the bound is not over-strict).
- **SC-006**: Sweep time within +5 % of the baseline; 0 new test failures beyond the 4 the baseline carries.

## Assumptions

- The bound's T1 model (front band with the living centred on the entrance; stacked west flank; three-room foot band) is the tree `_plan_hub_wing` builds; the engine's own sizing is a point in the bound's search space, so the bound is never stricter than the engine on feasibility, only on quality.
- "Last resort" is expressed by candidate order alone — no new ranking score, no hub bonus.

## Out of scope

- New hub topologies (closed by Phase 0), sizing changes (closed by v2.1), the side-by-side regime, wet-room kinds (feature 007), presenting last-resort plans differently in the UI.
