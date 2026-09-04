# Phase 0 Research: Parametric Design Model

No `NEEDS CLARIFICATION` markers remained — spec.md's Assumptions section already resolved every open
question with a documented default. This file records the concrete decisions behind those defaults.

## Decision: Merge into `Project`, same pattern as Feature 02

- **Decision**: Site dimensions, room list, omission notes, and generation timestamp become new fields on
  `Project`, via a new `ProjectRepository.set_design_model(...)` method — no separate entity/repository.
- **Rationale**: Explicitly requested, and directly continues the precedent Feature 02 already set (see
  `specs/001-project-creation/research.md`'s "`Project` absorbs Feature 02's parsed fields"): one project
  record is the single place to find everything known about it, rather than data spread across resources
  that have to be kept in sync. This feature's data has no independent lifecycle from the project either —
  same reasoning applies.
- **Alternatives considered**: A separate `DesignModel` entity (Feature 02's original, since-abandoned
  shape) — rejected for the same reasons that shape was abandoned there.

## Decision: Pure function for the generation algorithm, separate from the route

- **Decision**: `backend/app/design/generator.py` exposes a plain function (`Project -> GeneratedDesign`,
  no I/O) that `backend/app/design/router.py` calls and then persists via the repository.
- **Rationale**: The algorithm has many small edge cases (floor count, unknown fields, footprint-too-small)
  that are far cheaper to unit-test directly against the function than through `TestClient`/HTTP for every
  case. This mirrors why Feature 02 kept `RequirementParser.parse()` as a plain function returning a typed
  result rather than embedding logic in the route handler.

## Decision: Fixed placeholder room sizes and a 1D per-floor layout

- **Decision**: Kitchen 12 m², bathroom 5 m², safe room 9 m² (fixed constants); living room and bedrooms
  split whatever area remains on their floor evenly among themselves; each floor is its own coordinate
  space (footprint assumed square, rooms laid out in a single row along its width, each spanning the full
  footprint depth).
- **Rationale**: Spec.md's own Assumptions section explicitly defers exact numbers to planning as an
  implementation detail, while still requiring the *rule* to be deterministic and testable. Fixed
  constants plus even splitting are the simplest thing that satisfies FR-003 (position + size for every
  room) without inventing a real space-planning algorithm this project doesn't have inputs for (no walls,
  no door/window placement, no adjacency preferences). A 1D row layout guarantees no room overlaps and
  every room fits by construction, which a more "realistic" 2D packing heuristic would have to work harder
  to guarantee for no real benefit at this stage (there's no rendering yet to look at, per FR-011).
- **Alternatives considered**:
  - *Percentage-based room sizes (e.g. kitchen = 12% of floor area)* — rejected: fixed absolute sizes are
    easier to reason about and test exactly (a 5 m² bathroom is a bathroom regardless of how big the house
    is; a bathroom that shrinks to 2 m² on a small house is not a better answer), and match how these
    rooms actually get sized in practice (roughly fixed, not proportional to house size).
  - *2D grid/rectangle-packing layout* — rejected as unnecessary complexity for structured data with no
    renderer yet to consume the extra realism; revisit when Feature 10 (Layout Generator, per the source
    spec) actually needs it.

## Decision: Unknown `bedrooms`/`safe_room` → excluded, not defaulted, with a recorded note

- **Decision**: `design_notes: list[str]` on `Project`, populated with a human-readable sentence whenever
  `bedrooms` or `safe_room` was `unknown` at generation time (e.g. `"מספר חדרי השינה לא ידוע — לא נכללו
  חדרי שינה בפריסה."`). Empty list (not `null`) once at least one generation has happened and nothing was
  omitted.
- **Rationale**: Consistent with this entire project's running "prefer `unknown` to inventing, and never
  hide the uncertainty" instinct (see Feature 01/02's research.md for the same pattern applied to city,
  street, built area, and floors). A silent zero-bedroom layout would look complete and mislead; recording
  *why* it's incomplete keeps the system honest, matching `docs/AI_Home_Planner_SPEC.md` §30's explicit
  "do not hide uncertainty" instruction.
- **Alternatives considered**: Refusing to generate at all when `bedrooms`/`safe_room` is unknown (like
  the FR-002 "must be parsed at least once" gate) — rejected: `floors` almost always resolves (FR-011
  default from Feature 02), so refusing over `bedrooms`/`safe_room` specifically would block generation
  far more often than necessary for information that's genuinely optional to have.
