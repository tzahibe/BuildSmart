# Realized-Connectivity Invariant — Implementation Report

```
REALIZED_CONNECTIVITY_INVARIANT = READY
NEXT_STEP                       = IMPLEMENT_GEOMETRY_DERIVED_OPEN_INTERFACES
```

**628 passed, 11 xfailed (strict).** Geometry Core untouched. The concept generator was not
modified, no geometry was repaired, and no fixture-specific exception was added.

**The invariant immediately exposed two live defects in the generated plans.** Per your
instruction to fail loudly and not repair in this task, they are pinned as strict `xfail`, not
fixed. Details in §5.

---

## 1. The exact invariant added

```
A declared access edge is treated as realized ONLY if the built geometry contains a
traversable connection supporting it. The realized plan — walls, openings and generated
doors — is the source of truth for physical accessibility.
```

Implemented as `validation.realized_connections()`, which accepts exactly two forms of
physical evidence and nothing else:

| Evidence | Accepted when |
|---|---|
| A generated door / cased opening | `placeable` **and** `shared_length_m > 0` |
| A wall-less join | The zones share a boundary **and both facing sides** are `WallType.OPEN` |

An unplaceable door is explicitly *not* evidence — a hole that does not fit carries no traffic.

## 2. C5: rewired, not supplemented

**C5 now uses realized connectivity directly.** It previously built its graph from
`fixture.access.edges` (the declared topology) and could therefore call a room reachable while a
solid wall stood in the way. It now traverses only `realized_connections()`, and the entrance
edge is admitted only if `entrance_door.placeable`.

A **new C13** supplements it with the desired-vs-realized comparison. The two are different
questions and both are needed:

- **C5** — *is every room physically reachable?* (a graph property of the built plan)
- **C13** — *did every declared edge actually get built?* (intent vs. reality)

C13 is the one that names the physical reason; C5 is the one that catches a room being sealed
even if no single edge looks wrong.

## 3. Behaviour for a missing DOOR

A declared `DOOR`/`CASED_OPENING` whose zones share no interface produces no door — silently,
before this change. Now:

```
C13  FAIL  A-C (DOOR): the zones share no physical interface, so no connection could be built
C5   FAIL  C
```

If the zones *do* touch but no placeable opening was generated, C13 reports that distinctly:
`shares 0.40 m of wall but no placeable opening was generated`.

## 4. Behaviour for a blocked OPEN connection

A declared `OPEN_CONNECTION` between non-sibling leaves leaves a real wall, and
`generate_openings` deliberately skips `OPEN_CONNECTION`, so nothing is cut either. Now:

```
C13  FAIL  A-C (OPEN_CONNECTION): blocked by a PARTITION wall over their 3.00 m shared
           boundary — declared open, physically walled
```

## 5. Regressions — and two real defects the invariant caught

**The canonical vertical slice passes 13/13.** Its open groups are whole subtrees, so it was
genuinely correct all along: gross 170.4 m², net 153.83 m², 2 iterations, unchanged.

**The generated concepts do not**, and the failures are real, not artefacts:

**Defect 1 — the "open-plan" LDK is three sealed rooms.** In `SPINE_DOUBLE_LOADED` the west
column holds public *and* private rooms, so `{LIVING, DINING, KITCHEN}` is not a whole subtree,
`_mark_open_interfaces` never marks it, and every LDK boundary stays `PARTITION` — with no doors
between them either, because `OPEN_CONNECTION` deliberately generates none. The renderer drew
thin grey partition lines that read as intentional.

**Defect 2 — `HALL–MASTER` is declared but no door exists.** In the **west** column a shared row
places `row[0]` on the left (away from the corridor) and `row[1]` against it — so the ensuite
takes the corridor frontage and the bedroom is buried behind it. `MASTER` and `BATH_1` are
physically sealed. The member order must depend on which side of the hall the column sits, and
currently does not.

Both were invisible before: C5 read the declared graph, C6 only checks that a door does *not*
exist where it shouldn't, and C7 only inspects doors that were generated.

**Pinned, not repaired** (`strict=True`, so they flip loudly when fixed):

| Pinned | Count |
|---|---|
| `test_each_programme_runs_end_to_end_on_a_rectangle` — 3BR, 3BR+SR, 3BR+SR+3wet | 3 |
| `test_each_geometry_runs_end_to_end` — L, curved, obstacle, disconnected | 4 |
| `test_all_slice_checks_still_pass` — 4 general-pipeline cases | 4 |

Alongside each, a companion test asserts what is **not** broken:
`test_only_the_connectivity_checks_fail` and
`test_each_geometry_still_produces_a_geometrically_valid_design` both assert the failure set is
`⊆ {C5, C13}` — geometry, areas, safe room, doors, windows, furniture and site checks all still
pass, and every room is still inside the legal buildable region.

2BR and 2BR+safe room are unaffected: they use partis whose open groups *are* whole subtrees.

## 6. Files changed

| File | Change |
|---|---|
| `app/vertical_slice/validation.py` | `RealizedConnection`, `realized_connections()`, C5 rewired, C13 added |
| `tests/vertical_slice/test_realized_connectivity.py` | **new** — 9 tests |
| `tests/vertical_slice/test_concept_generator.py` | 3 pins + 2 companion tests |
| `tests/vertical_slice/test_general_pipeline.py` | 4 pins + 1 companion test |
| `tests/vertical_slice/test_baseline_and_decoupling.py` | check count 12 → 13 |
| `tests/vertical_slice/test_pipeline.py` | check ids C1–C12 → C1–C13 |

Not touched: `geometry_core/`, `safe_adapter.py`, `concept_generator.py`, `doors.py`,
`windows.py`, `design_output.py`, `renderer.py`.

## 7. Tests

- `test_declared_door_between_non_adjacent_zones_fails_validation` — the required A/B/C case
- `test_c5_no_longer_reports_a_sealed_room_as_reachable` — the exact hole, closed
- `test_declared_open_connection_blocked_by_a_partition_fails_validation` — the required blocked-OPEN case
- Two **controls** proving the invariant rejects false claims and not valid plans: the same
  plans pass once the declared edge matches the geometry, and a genuine whole-subtree open group
  is accepted with no door
- `test_an_unplaceable_door_is_not_a_realized_connection`
- `test_declared_topology_is_preserved_as_intent` — `DesiredAccessTopology` is untouched
- `test_validation_reports_the_failure_and_does_not_repair_it`

---

## Verdict

```
REALIZED_CONNECTIVITY_INVARIANT = READY
NEXT_STEP                       = IMPLEMENT_GEOMETRY_DERIVED_OPEN_INTERFACES
```

The invariant holds, the canonical baseline is unchanged, and the guard is installed **before**
the representation change — which is exactly what it was for: option B now cannot introduce a
silent connectivity failure while fixing one.

One thing worth your decision before that step: **defect 2 (the buried master bedroom) is not
fixed by option B.** It is an ordering bug in the concept generator, independent of open
interfaces, and it needs its own small fix. Option B will clear defect 1 and the L/T corridor
work; defect 2 will still be pinned unless it is included.

Stopping for review.
