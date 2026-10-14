# [agent] Stage 2 (A/2): the shared contract every later child implements — donor identity, seed geometry, intent, the realizer's input, wet rooms/SAFE_ROOM, and room identity end to end

### Goal

Owner instruction 2026-09-23, under a quota limit: **before any full implementation, write ONE explicit
contract shared by every Stage 2 child**, so no two of them invent their own representation of the same
fact and the chain actually connects. This Issue writes that contract as real types plus one document, and
pins it with tests. It implements no realization behaviour of its own.

### Current behavior

The pieces exist in three different shapes and nothing binds them:
`spikes/architectural_brain/realization_intent.py` keys donor facts by a donor room id, but the mapping to a
realized zone (`realize.donor_room_id_by_zone`) is rebuilt ad hoc and loses DINING/SAFE_ROOM/TOILET
entirely — 38 of 136 measured losses are `DONOR_ROOM_NOT_REALIZED` for exactly that reason.
`rectilinear_realizer.py` (#117) consumes a PLACED layout invented by its own gate script, with no shared
type, and excludes wet rooms and SAFE_ROOM because it has no `ResolvedWetRoom` to hand C17/C29.
`preservation.py` measures facts against realized geometry through yet another correspondence.

### Required behavior

One module (`backend/app/vertical_slice/stage2/contract.py` or the equivalent package the implementer
chooses, stated in the document) plus `docs/stage2/CONTRACT.md`, defining and documenting:

1. **Donor room identity**: the stable id of a room in the retrieved `PlanReference`, and how that id
   travels through retrieval, synthesis, adaptation, seeding, repair and realization. Every later stage
   refers to a donor room by this id and nothing else. Adaptation that drops or adds a room records it
   explicitly (added / dropped / merged / split), so a fact is never silently orphaned.
2. **Seed geometry**: how the donor's own partition is carried as data before any repair — cells, their
   donor room ids, their adjacency, and the frame they are expressed in.
3. **`RealizationIntent` content**: exactly which facts, in which units, in whose coordinate frame —
   adjacency, access, exterior exposure, relative placement, public/private clusters, wet-core groups,
   entrance relationship, room proportions, footprint relationships. Where #109's existing definition is
   already right, adopt it unchanged and say so; where it is ambiguous, make it explicit.
4. **The realizer's input and refusal contract**: the exact placed-layout structure the non-guillotine
   realizer receives, its invariants (what must hold before it is called), and its REFUSAL contract — a
   refusal names its reason and is never substituted by a result from another path.
5. **Wet rooms and SAFE_ROOM**: how they are represented end to end, including everything C17/C29 need to
   run (the `ResolvedWetRoom` shape and who builds it), so the realized plan is a real house from the first
   milestone.
6. **Room identity end to end**: donor room -> intent fact -> seed cell -> repaired cell -> realized zone,
   as one traceable chain, with the rule for what happens at each transformation.

The document states, for each of the six, the ONE place the representation lives and which module may
change it. No behaviour, no flag flip, no realization: this Issue is the vocabulary the next one speaks.

### Acceptance Criteria

- AC-1: the contract module defines the donor-room identity, seed geometry, intent content, realizer input/refusal, wet-room/SAFE_ROOM and room-identity types, and `docs/stage2/CONTRACT.md` documents all six with the module that owns each
- AC-2: a test builds the full chain for one real retrieved plan — donor room id -> intent fact -> seed cell -> repaired cell placeholder -> realized zone placeholder — and asserts every donor room the brief contains is reachable at every link, with dropped/added rooms explicitly classified rather than missing
- AC-3: a test asserts the refusal contract: a refusal carries a stated reason and no result object from any other realization path can satisfy the Stage 2 result type
- AC-4: with the Stage 2 flags OFF the frozen 432-context corpus is byte-identical to the base

### Out of scope

Realization itself, repair, the placement search, any measurement of preservation, and any change to
existing validators — all of that is the next child. Generalizing #79's compilers (permanently out of scope).

### Affected domains

backend, geometry, validator, qa

### Risk

MEDIUM

### Resource class

MEDIUM

### Dependencies

none

### Required locks

geometry-core (shared), validator-core (shared), planner-core (shared)

### Verification plan

- AC-1 -> pytest:backend/tests/architectural_brain/test_stage2_contract.py
- AC-1 -> file:docs/stage2/CONTRACT.md
- AC-2 -> pytest:backend/tests/architectural_brain/test_stage2_contract.py
- AC-3 -> pytest:backend/tests/architectural_brain/test_stage2_no_guillotine_fallback.py
- AC-4 -> regression:corpus

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: 0

### Expected documentation changes

docs/stage2/CONTRACT.md (new — the shared contract), docs/wiki/architecture/geometry-validation.md (a pointer to it once Stage 2 lands).

### Knowledge check

Consulted: ROOT #127's own contract and the owner's execution order (2026-09-23); #109's
`realization_intent.py`/`preservation.py` and `docs/reports/poc-architectural-brain/preservation.md` (the fact
taxonomy and its `DONOR_ROOM_NOT_REALIZED` reason); #117's `rectilinear_realizer.py` and its gate report (the
placed-layout it consumes, and why wet rooms/SAFE_ROOM were excluded there); `validation.py` C17/C29 and the
`ResolvedWetRoom` they require; `realize.py`'s `donor_room_id_by_zone`.
