# Stage 2 — the shared contract (Issue #133)

**Status**: types only, pinned by tests. No realization behaviour. No wiring into the production
pipeline. Every later Stage 2 child (retrieval integration, adaptation, seeding, repair, the
realizer wiring itself) is expected to import these types rather than invent its own shape for the
same fact.

**Owning module (all six sections below)**:
`backend/app/vertical_slice/stage2/contract.py`. A later child that finds one of these types
genuinely wrong edits THIS module — never adds a second, parallel definition elsewhere.

**Why this document exists**: three pieces of prior work each invented their own representation of
the same facts and nothing bound them together —

- POC Issue #109 (`spikes/architectural_brain/realization_intent.py`, not merged to `main`) built a
  `RealizationIntent` keyed by donor room id, from a retrieved `PlanReference`.
- The same POC's `realize.py` rebuilt the donor-room correspondence ad hoc
  (`donor_room_id_by_zone(brief, adapted) -> dict[str, str]`), re-matching adapted rooms to donor
  roles positionally. A donor room the match missed was never recorded, never classified — just
  absent. Measured: 38 of 136 losses `preservation.py` reports are `DONOR_ROOM_NOT_REALIZED` for
  exactly this reason.
- Stage 1 Issue #117 (`app/vertical_slice/rectilinear_realizer.py`, on
  `integration/rectilinear-realizer`, not merged to `main`) defined its OWN `RealizationIntent` — a
  "PLACED layout" shape (wings/zones/groups) — unrelated to #109's donor-fact shape, but with the
  SAME NAME, and it excludes wet rooms and SAFE_ROOM entirely (`realize_layout` never passes
  `wet_rooms` to `validation.validate`, so C17/C29 do not run on its output).

**A note on reachability**: at the time this Issue was implemented, none of #109, #117 (Stage 1),
nor `preservation.py` were merged to `main` — they exist only in other, unmerged worktrees/branches.
This document was written by reading those worktrees directly (read-only); the type SHAPES below
transcribe what is already right in them (stated per-section), never import from them at runtime.
`backend/app/vertical_slice/stage2/contract.py` is therefore, today, the only one of these
representations that actually lives on `main`.

---

## 1. Donor room identity

**Owning module**: `stage2/contract.py` — `DonorRoomId`, `RoomLineageKind`, `RoomLineageEvent`,
`RoomLineage`, `PIPELINE_STAGES`.

The stable id of a room in the retrieved `PlanReference` (`plan_reference.Room.id`, e.g.
`"LIVING_0"`, `"BEDROOM_2"`) is a `DonorRoomId` (a `str`) — never re-minted, never a positional
role+index match, at any later stage. It travels through six named pipeline stages, in order:
`retrieval -> synthesis -> adaptation -> seeding -> repair -> realization`.

Adaptation (or any later stage) that changes the room set records it as a `RoomLineageEvent`:

| kind      | meaning                                                          | donor_room_ids | result_ids |
|-----------|-------------------------------------------------------------------|:---:|:---:|
| `CARRIED` | passes through this stage with identity unchanged (may still resize/reposition) | same as result_ids | same as donor_room_ids |
| `ADDED`   | a room with no donor counterpart is introduced                    | empty | non-empty |
| `DROPPED` | a donor room has no counterpart from here on                      | non-empty | empty |
| `MERGED`  | two or more donor rooms combine into one later entity              | ≥2 | ≥1 |
| `SPLIT`   | one donor room becomes two or more later entities                  | 1 | ≥2 |

A `RoomLineage` is the full record for one concept: every donor room id the retrieved plan carried,
plus every event any stage recorded. `RoomLineage.unaccounted_donor_ids()` is the invariant AC-2
checks — empty exactly when no donor room is silently missing (the `donor_room_id_by_zone` bug this
Issue exists to end).

## 2. Seed geometry

**Owning module**: `stage2/contract.py` — `SeedCell`, `SeedGeometry`, `DONOR_PLAN_FRAME`.

The donor's own partition, carried as data, before any repair: one `SeedCell` per (non-dropped)
donor room — `cell_id`, `donor_room_id`, `polygon_m` — plus `adjacency` (cell id pairs, copied
verbatim from the donor's own `adjacency_edges`, never re-derived), and the `frame` they are
expressed in. Today's only defined frame is `DONOR_PLAN_FRAME`
(`"DONOR_PLAN_IMAGE_FRAME_METERS"`): the donor's own unrotated, image-like coordinate system where
N/W are the smaller-coordinate sides — the same convention
`realization_intent._relative_placement_for`/`patterns._side_of_bbox_center` already use, in
meters. A `SeedGeometry` reflects the room set AFTER adaptation's add/drop decisions (a `DROPPED`
room never reaches a seed cell at all; an `ADDED` room does not get one either — it has no donor
partition slot to start from, and first appears at repair).

## 3. `RealizationIntent` content

**Owning module**: `stage2/contract.py` — `AdjacencyFact`, `AccessFact`, `ExposureFact`,
`RelativePlacement`, `Clusters`, `CirculationNode`, `EntranceRelationship`, `RoomProportion`,
`FootprintRelationships`, `RealizationIntent`.

**Adopted unchanged from POC Issue #109.** That module's own shape is already right: every field is
either a direct copy of a fact `PlanReference` states, or a deterministic, documented geometric
derivation from facts already there — never an invented value. `stage2/contract.py` reproduces the
dataclass shape field-for-field (transcribed, since #109's own branch is unmerged — see the note
above); once #109 lands, it is expected to import these types from here rather than keep its own
copy. The derivation function (`intent_from`, which needs `PlanReference`/`ConceptSpec`/`Brief` —
none on `main` yet) is deliberately NOT reproduced: that is behaviour, not vocabulary, and stays
out of this Issue's scope.

Fields carried: adjacency edges, access edges, exterior exposure, relative placement
(FRONT/REAR/LEFT/RIGHT/ABOVE/BELOW, entrance-relative), public/private clusters, circulation nodes,
wet-core groups, the entrance relationship, each room's OWN proportions (never a fixed per-type
constant), and the footprint's own proportions — every room-keyed field uses `DonorRoomId`; every
geometric fact is in the donor's own frame (`DONOR_PLAN_FRAME`, §2).

## 4. The realizer's input and refusal contract

**Owning module**: `stage2/contract.py` — `ZoneIntent`, `PinwheelWing`, `RowWing`,
`ShapeGroupIntent`, `Wing`, `RealizerInput`, `validate_realizer_input`, `RealizerRefusal`.

Stage 1 Issue #117's own `rectilinear_realizer.RealizationIntent` ("PLACED layout": wings, zones,
already-decided adjacency/placement/exposure) is a DIFFERENT thing from §3's `RealizationIntent`
(donor facts, not yet placed) — the two shared one name across two unmerged worktrees, which is the
exact confusion this section exists to end. Renamed here to **`RealizerInput`**: the exact
structure the non-guillotine realizer receives. Field shapes mirror #117's own
`ZoneIntent`/`PinwheelWing`/`RowWing`/`ShapeGroupIntent` (transcribed, not imported — same
unreachable-branch situation), plus a `wet_rooms: tuple[ResolvedWetRoom, ...]` field (§5).

**Invariants that must hold before `RealizerInput` is handed to a realizer** (checked by
`validate_realizer_input`, never silently repaired by the realizer itself):

- `wings` is non-empty.
- Every `zone_id` across every wing's zones/groups is unique.
- Every `ZoneIntent.donor_room_id` that is not `None` names a room the `RealizationIntent` it was
  built from actually has a `RoomProportion` for, OR is explicitly recorded `ADDED` in the
  `RoomLineage` (§1) this input was built from.

**Refusal contract**: a layout the realizer cannot honestly realize returns a `RealizerRefusal`
(`reason`, `detail`) — the failing constraint, named, never silently approximated. `RealizerRefusal`
enforces a non-empty `reason` at construction. It is never substituted by a result object from
another realization path: see `Stage2Result`/`ensure_stage2_result` below, the structural
enforcement AC-3 pins.

```
@dataclass(frozen=True)
class Stage2Result:
    zones: tuple[RealizedZone, ...]
    refusal: RealizerRefusal | None
    # __post_init__ enforces: exactly a success (zones set, refusal None) or a refusal
    # (zones empty, refusal set) — never both, never neither.
```

`ensure_stage2_result(candidate)` is the one checked boundary: it raises `TypeError` for anything
that is not already a genuine `Stage2Result` — a bare dict, a duck-typed object with a similar `ok`
property, `rectilinear_realizer.RealizedLayout` itself, or any guillotine-engine result — none of
them satisfy `isinstance(x, Stage2Result)`, by construction (no shared base).

## 5. Wet rooms and SAFE_ROOM

**Owning module (unchanged)**: `app/vertical_slice/wet_rooms.py` — `ResolvedWetRoom`,
`resolve_wet_rooms`. **`stage2/contract.py` only references these types, never redefines them.**

This fact already has ONE representation on `main`, and it already works:
`wet_rooms.ResolvedWetRoom`, built by `wet_rooms.resolve_wet_rooms(program)` from the brief's own
authoritative `ProgramSpec` (never from a donor/adapted concept — see that module's own I1–I4
invariants). It is already the authoritative input `validation.validate`'s `wet_rooms` parameter
reads for **C17** (bathroom access) and **C29** (wet-room privacy). SAFE_ROOM already has its own
realized-fact check, **C4**, via `ProgramRole.SAFE_ROOM` + `WallType.RC_SAFE_ROOM` +
`constraints.SAFE_ROOM_NOT_REALIZED_DETAIL` — also unchanged.

The actual gap (Required Behaviour 5) is not a missing type — it is that Stage 1's own realizer
(`rectilinear_realizer.realize_layout`) never receives a `wet_rooms` argument at all, so it can
never call `validate()` with C17/C29 able to run. `RealizerInput.wet_rooms` (§4) is the fix: the
realizer's own input carries `ResolvedWetRoom` end to end, so a later child wiring a realizer in has
nowhere else to source it from and no reason to invent a second wet-room type. SAFE_ROOM flows
through the exact same `ZoneIntent.role = ProgramRole.SAFE_ROOM` path every other room does — no
separate SAFE_ROOM type either.

## 6. Room identity end to end

**Owning module**: `stage2/contract.py` — `RepairedCell`, `RealizedZone`, `RoomIdentityChain`,
`DonorRoomTrace`, `trace_donor_room`, `verify_chain_completeness`.

The chain: **donor room → intent fact → seed cell → repaired cell → realized zone.**

| link | type | rule |
|---|---|---|
| donor room | `DonorRoomId` (§1) | the retrieved `PlanReference`'s own room id |
| intent fact | `RealizationIntent.room_proportions` entry (§3) | one per donor room, unconditionally — built from the raw retrieved plan, independent of what adaptation later does |
| seed cell | `SeedCell` (§2) | one per donor room that survives to seeding; a room `DROPPED` during adaptation never gets one |
| repaired cell | `RepairedCell` | `seed_cell_id`/`donor_room_id` both `None` only for a cell an `ADDED` event introduced; a `SPLIT` donor room's one seed cell maps to ≥2 repaired cells; a `MERGED` group's donor rooms each keep their OWN repaired cell (merging happens at the realized-zone link, mirroring #117's own `zone_of_cell` many-cells-one-zone shape) |
| realized zone | `RealizedZone` | `repaired_cell_ids` has >1 entry exactly for a `MERGED`/notch-carve group's own zone; `donor_room_ids` is empty exactly for an `ADDED` zone |

`RoomIdentityChain` bundles all five links for one concept. `trace_donor_room(chain, donor_room_id)`
walks a single donor room across every link. `verify_chain_completeness(chain)` is the invariant
AC-2 checks: every donor room must be either `fully_reachable` at every link, or have an explicit
`DROPPED`/`MERGED`/`SPLIT` event accounting for why not — never merely missing. Returns one problem
string per donor room that satisfies neither; empty means the chain is complete.

---

## What this Issue does NOT do

No realization, no repair, no placement search, no measurement of preservation, no change to any
existing validator, no generalization of #79's compilers. `STAGE2_CONTRACT_ENABLED` (in
`stage2/contract.py`) gates nothing — no existing caller imports the `stage2` package at all, so the
frozen 432-context regression corpus is unaffected by construction. The flag exists only as the
same disclosure/kill-switch precedent `RECTILINEAR_REALIZER_ENABLED`/`LAUNDRY_ROOM_ENABLED` set, for
whichever future child wires Stage 2 into the production pipeline.

## Tests

- `backend/tests/architectural_brain/test_stage2_contract.py` — AC-1 (every type group exists and
  behaves as documented) and AC-2 (the full chain, for a real retrieved plan —
  `tests/spikes/fixtures/geometry_shapes/plans/47.json`, a genuine ResPlan fixture — with an
  explicit `CARRIED`/`MERGED`/`SPLIT`/`DROPPED`/`ADDED` scenario covering every donor room).
- `backend/tests/architectural_brain/test_stage2_no_guillotine_fallback.py` — AC-3 (the refusal
  contract: a stated, non-empty reason; `Stage2Result`'s sealed success-xor-refusal invariant;
  `ensure_stage2_result` rejecting a dict, `None`, and a guillotine-shaped stand-in result).
