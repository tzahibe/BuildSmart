# Architectural Anti-Pattern Library

Status: reference document, companion to `quality_rubric.md`. Each entry names a specific,
recognizable failure mode a reviewer (human or LLM) should be able to spot on a realized plan, with
the rubric section it violates and how it is (or would be) caught. `Detection:` names an existing
check/metric where one exists, or `proposed: Issue N` / `proposed: no Issue yet` where it doesn't.
"Example" cites a corpus context id or a specific investigation where the pattern was actually
measured, not a hypothetical.

## 1. Strip-shaped public room

**Description**: a KITCHEN or DINING room realizes as a long, narrow rectangle (aspect notably
above ~2.0) rather than a room that reads as its own volume, even though it legally satisfies its
area and aspect-ceiling requirements.

**Why it is bad**: a strip public room can't hold an L-counter or a dining table set the way a
person would actually use the space; it reads as leftover area shaped to fit rather than a
purpose-designed room.

**Detection:** M1 (habitable aspect by room type, `quality_metrics.py`) measured on the current
corpus: KITCHEN median aspect 2.75, DINING median aspect 2.35
(`docs/wiki/architecture/geometry-validation.md`). No dedicated pass/fail gate exists yet — the fix
(extending the room-proportion quality tier to the public band) is PROPOSED, not implemented
(same page's Known follow-ups).

**Example**: the M1 corpus measurement above (aggregate, not a single context id — see
`docs/wiki/architecture/geometry-validation.md`'s "Measured gaps" section).

**Violates**: rubric section G (Public-Zone Contiguity & Open-Plan Coherence), also A (Room
Proportion & Aspect Ratio).

## 2. Hall spine without a compact hub

**Description**: circulation realizes as one long, narrow hall (long/short aspect far above the
compact threshold) rather than a compact lobby that rooms cluster around.

**Why it is bad**: a spine hall wastes area on pure transit space and produces a house that feels
like a line of rooms off a corridor rather than an organized set of zones.

**Detection:** M4 (hall long/short aspect, `COMPACT_HALL_ASPECT_MAX = 1.5`,
`quality_metrics.py`). Measured: median 9.4, 0% compact on the current corpus vs. ~18/21 reference
plans having a compact hub (`docs/wiki/architecture/geometry-validation.md`). The structural fix
(hub parti, spec 005) was attempted and rejected on two hard acceptance gates
(`specs/005-hub-private-wing/RESULTS.md`); no accepted fix exists yet.

**Example**: `specs/005-hub-private-wing/spec.md` §1 (21-plan census); rejection detail in
`specs/005-hub-private-wing/RESULTS.md`.

**Violates**: rubric section D (Circulation Efficiency & Compactness), also E (Circulation Topology
& Access Sequence).

## 3. Isolated wet room

**Description**: a bathroom or toilet has no interior wall shared with another wet room, the
kitchen, or the laundry — it sits plumbing-isolated from every other fixture-bearing room.

**Why it is bad**: isolated wet rooms mean longer, more expensive plumbing runs and is a pattern
professional plans consistently avoid.

**Detection:** M5 (wet-room adjacency share, `quality_metrics.py`). Measured: 40% on the current
corpus vs. ~85–90% on the 21-plan reference set — the largest measured gap after hall-spine
topology (`docs/wiki/architecture/geometry-validation.md`). The wet-room quality-tier extension
(commit `f2092af`) improves proportion, not adjacency; the adjacency gap itself has no accepted fix
(`wet-room-strip-root-cause` memory: fix A "READY but doesn't fix the repro case", fix D "NEEDS MORE
RESEARCH").

**Example**: `docs/WET_ROOM_STRIP_INVESTIGATION_REPORT.md` (the general-case investigation).

**Violates**: rubric section F (Wet-Room Adjacency & Plumbing Efficiency).

## 4. Room-in-a-room

**Description**: a room's only access is a doorway carved through a corner of another room rather
than a real doorway off shared circulation — the room is legally distinct (no overlap, no residual
area) but functions as a nested pocket inside its neighbour.

**Why it is bad**: a room reached only through another private room has no independent access and
forces every visit to pass through — and announce itself in — the room it's nested in.

**Detection:** proposed: no Issue yet. C1/C2 (`validation.py`) already guarantee no geometric
overlap and no residual area, but neither check judges whether a room's *access* is independent
rather than incidental; C13 confirms declared access is realized, not that the access point reads
as a real doorway rather than a corner cut-through.

**Example**: none isolated in the current corpus census; the pattern is named from the general
principle behind C1/C2's own scope note (`validation.py` — those checks are explicitly geometric,
not access-quality, gates).

**Violates**: rubric section K (Dead Space & Structural Validity), also I (Doors & Access
Topology).

## 5. Door-fixture clash

**Description**: a door's swing arc, once fixtures are considered, crosses the space a fixture
(toilet, sink, tub) needs for clearance — most likely in a small wet room sized right at its
template's minimum band.

**Why it is bad**: a door that can't fully open without hitting a fixture is not a usable room,
regardless of how correct its declared area and access are.

**Detection:** proposed: no Issue yet (ROADMAP P1 "Kitchen / Bathroom fixture-aware planning").
Rooms are planned as typed rectangles with no fixture geometry today, so no check can evaluate a
door-fixture clash directly; the guest-WC size band
(`specs/009-guest-wc-placement/spec.md` decision D, aspect ≤ 2.2, short side 0.9–1.2 m) is the
closest existing proxy — a room narrower than that band is at elevated risk of this clash once a
door is placed.

**Example**: none measured yet (no fixture geometry exists to measure against); flagged as a risk
in the guest-WC spec's own size-band rationale.

**Violates**: rubric section N (Fixture & Clearance Awareness), also I (Doors & Access Topology).

## 6. Bedroom-to-bedroom access

**Description**: the only way to reach one bedroom is by walking through another bedroom.

**Why it is bad**: it eliminates privacy for the room being passed through and is a pattern no
professional residential plan uses as a routine solution.

**Detection:** proposed: no Issue yet (ROADMAP P0 "Doors + Access Topology"). C13 confirms declared
access is realized but does not evaluate whether the access route is itself acceptable; no check
today specifically flags a private room whose only route passes through another private room.

**Example**: none isolated as a named corpus case; named directly from the ROADMAP P0 item's own
description ("בלי bedroom-to-bedroom כפתרון רגיל", `docs/ROADMAP.md`).

**Violates**: rubric section I (Doors & Access Topology), also J (Adjacency & Privacy Zoning).

## 7. Entrance dead-end

**Description**: the front door opens directly onto a blank wall, or into a "pocket" of leftover
space beside the entrance with no functional role — rather than into a hall, foyer, or public zone
that leads somewhere.

**Why it is bad**: it produces a bad first impression and a genuinely wasted piece of area right at
the highest-traffic point of the plan.

**Detection:** proposed: Issue #22 ("Entrance-to-Circulation Integration / no entrance dead-end
walls", depends on #20, `docs/ROADMAP.md`). `is_entrance` (`app.demo.contract`) and C5
(reachability) confirm a door exists and the house is reachable from it, not that the space
directly ahead of it is functional.

**Example**: none isolated as a measured corpus case yet; the pattern is the explicit subject of
Issue #22's own problem statement.

**Violates**: rubric section H (Entrance & Arrival Sequence), also E (Circulation Topology & Access
Sequence).

## 8. Silent area shrinking

**Description**: a room's realized area comes in meaningfully below what the user asked for, with
no warning or disclosure anywhere in the review flow — the plan just quietly delivers less than
requested.

**Why it is bad**: the user explicitly asked for a size; silently not honoring it breaks trust in
every other number the plan reports, even when the plan is otherwise structurally valid.

**Detection:** proposed: no Issue yet (ROADMAP P0 "Exact Area / Room Area Fidelity"). One concrete
historical instance is already fixed by construction rather than detected after the fact: the
guest-WC spec's own §1 measurement found a realized `TOILET` area (7.8 m²) that *exceeded* its
template's `max_area_m2` ceiling via headroom scaling — the inverse direction of this anti-pattern,
fixed by the spec's size-band design (decision D) rather than caught by a shrinkage check, because
no such check exists yet.

**Example**: `specs/009-guest-wc-placement/spec.md` §1 (the headroom-scaling-past-ceiling
measurement — the adjacent, currently-fixed-by-construction case).

**Violates**: rubric section B (Area Fidelity).

## 9. Windowless habitable room

**Description**: a bedroom, living room, or kitchen has an exterior-adjacent wall (so it passes
M2) but no window drawn on it — exposure without an actual opening.

**Why it is bad**: an exterior wall with no window delivers none of the daylight/ventilation a
habitable room needs; M2 alone can't tell the difference between this and a genuinely lit room.

**Detection:** proposed: no Issue yet (ROADMAP P0 "Windows + Exterior Exposure"). M2
(`quality_metrics.py`) confirms envelope contact only; no check yet confirms a window actually
exists on that wall.

**Example**: none isolated as a measured corpus case — windows are not yet modeled as distinct
geometric objects the corpus census could count.

**Violates**: rubric section C (Exterior Exposure & Daylight).

## 10. Unconditional L-massing slot

**Description**: an L-shaped footprint takes a representation slot in the offered candidates simply
because it is a valid L, regardless of whether the resulting plan is actually better than the next
rectangle alternative.

**Why it is bad**: showing a worse plan just because its footprint shape is more visually
interesting misleads the user about what their best option actually is.

**Detection:** now fixed — `l_massing_guard.py` (commit `9ae6893`) gates L-slot eligibility on
realized quality (`worst_wet_aspect`, `two_sided_share`); measured effect: 14/16 previously-
unconditional L slots lost their slot after the gate, 0 primary changes
(`docs/wiki/features/l-massing.md`). Kept here because the anti-pattern is exactly what the gate
exists to prevent, and because the gate explicitly does not cover entrance-sequence quality for an
L that does earn its slot (a deliberately deferred, separate follow-up).

**Example**: `docs/L_MASSING_REPRESENTATION_QUALITY_GATE_INVESTIGATION.md` (the pre-fix
measurement); `docs/L_MASSING_REPRESENTATION_QUALITY_GATE_IMPLEMENTATION.md` (the fix, commit
`9ae6893`).

**Violates**: rubric section L (Massing & Footprint Shape Quality).

## 11. Chained circulation

**Description**: instead of a distinct hall or hub, a sequence of rooms is strung together such
that reaching a room at the end of the chain means passing through every room before it — the
"chain" itself functions as the only circulation.

**Why it is bad**: it collapses privacy and flexibility (every room in the chain is a mandatory
through-route) and is explicitly called out as a planning-quality failure the owner wants closed
("בלי פתרונות שרשרת גרועים", ROADMAP P0 planning-quality item).

**Detection:** proposed: no Issue yet (ROADMAP P0, the general planning-quality item, not yet
split into its own Issue). C5 confirms every room is reachable at all; it does not distinguish a
genuine hall-served plan from a chain where reachability only holds by passing through other
private rooms.

**Example**: none isolated as a measured corpus case; named directly from the ROADMAP P0 item's own
wording.

**Violates**: rubric section E (Circulation Topology & Access Sequence), also I (Doors & Access
Topology).

## 12. Cross-level stair misalignment

**Description**: on a multi-level building, the stair/vertical core lands in a position on one
level that does not correspond to a sensible position on the other — e.g. it opens into a hallway
on the ground floor but lands inside a room's footprint-adjacent corner upstairs.

**Why it is bad**: a structurally-required vertical core that isn't coherently seated on both
levels either fails outright or forces an awkward compromise on whichever level it's misaligned on.

**Detection:** V-checks (`building_validation.py`, V1–V5/V7/V8) enforce the structural minimum
today via the shared, pinned `VerticalCore`. The topology bound itself was measured directly: only
one stair-seat approach was found to work on both levels across the investigated briefs (27/36
hand-built, 0/76 independently generated — `multi-level-phase1-core-band-seat` memory); whether the
implementation fully closed this gap is an explicit, not-yet-independently-reverified open item on
the Multi-Level Wiki page's Known follow-ups.

**Example**: `docs/MULTI_LEVEL_PHASE_1_INVESTIGATION_REPORT.md` (the stair-seat measurement).

**Violates**: rubric section M (Multi-Level Vertical Coherence).

## 13. Underspecified laundry room

**Description**: a room typed LAUNDRY exists in the plan without a door, without machine-clearance
area, or without an exterior window — the room satisfies its area template without satisfying what
makes a laundry room usable.

**Why it is bad**: a laundry room the owner explicitly wants defined as "a closed room you can
enter, with a door, usable space for the machine, and a mandatory exterior window" fails that
definition silently if only its area is checked (ROADMAP P0 "Laundry Room semantics").

**Detection:** LAUNDRY is IMPLEMENTED_MERGED and gated on (`LAUNDRY_ROOM_ENABLED=True`,
`docs/wiki/features/laundry.md`) with service-first area allocation; `LAUNDRY` is explicitly
excluded from the room-proportion quality tier's aspect target
(`docs/wiki/features/wet-rooms.md`) and has no dedicated door/window/clearance check of its own
yet — the ROADMAP item ("לבדוק שה-generator וה-validator באמת מבטיחים את זה") is explicitly still
open.

**Example**: `docs/LAUNDRY_ROOM_ACTIVATION_REPORT.md` (the shipped feature and its own noted open
question: whether area-budget crowding under it is fully resolved).

**Violates**: rubric section N (Fixture & Clearance Awareness), also F (Wet-Room Adjacency &
Plumbing Efficiency — LAUNDRY is one of M5's wet-neighbour kinds).

## 14. Site-blind footprint

**Description**: a plan's footprint and orientation are chosen as if the site were an abstract
rectangle, ignoring the parcel's actual setbacks, buildable polygon, or orientation constraints.

**Why it is bad**: a plan that fits perfectly inside an assumed rectangle but not inside the real
buildable region isn't actually buildable — it's a drawing, not a plan.

**Detection:** partially covered — `app/geometry_domain` and the site-geometry primitives
(`docs/AUTHORITATIVE_SITE_GEOMETRY_P0_REPORT.md`, `docs/SITE_AWARE_FOOTPRINT_OPTIONS_REPORT.md`)
already constrain outline search to a buildable polygon where site data is supplied; the remaining
gap — treating this as the default rather than an abstract-rectangle fallback, and orientation/
solar reasoning specifically — is proposed: no Issue yet (ROADMAP P0 "Buildable Region / Site
Constraints", P2 "North / Orientation / Solar reasoning").

**Example**: `docs/SITE_AWARE_FOOTPRINT_OPTIONS_REPORT.md` (the buildable-polygon primitives this
partially covers).

**Violates**: rubric section O (Site & Orientation Fit).
