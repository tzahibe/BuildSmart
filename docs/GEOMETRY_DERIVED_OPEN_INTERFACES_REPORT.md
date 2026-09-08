# Shared-Row Ordering Fix + Geometry-Derived Open Interfaces

```
STATUS = DONE
```

**636 passed, 0 failed, 0 xfail.** Both defects the realized-connectivity invariant exposed are
fixed, all 11 strict pins were removed because they flipped to XPASS, and the canonical baseline
is numerically unchanged.

**A Geometry Core change was necessary.** Details and justification in §3.

---

## 1. Shared-row ordering fix

`_orient_row(row, corridor_on_east)` in `concept_generator.py`. A V-split places `row[0]` west
and `row[1]` east, so the corridor-facing slot depends on which side of the hall the column sits
on. The rule is stated generally, not per fixture:

> The member entered from **circulation** takes the corridor-facing slot; the member entered
> from its neighbour (an ensuite) takes the far one.

Applied at one place per column, before widths, specs or the tree are built, so every downstream
consumer sees the same order. The east column keeps the old behaviour (bedroom first, adjacent
to the hall on its west); the west column is now reversed.

**HALL–MASTER result:** the door is generated, `MASTER` and `BATH_1` are reachable, and both C5
and C13 pass. Visible in the render: `MASTER` sits against the hall, `BATH_1` behind it.

```
doors: HALL-LIVING, HALL-MASTER, HALL-BEDROOM_1, HALL-BEDROOM_2,
       HALL-SAFE_ROOM, MASTER-BATH_1, HALL-BATH_2
```

## 2. Geometry-derived open interfaces

`derive_wall_types` gained an `open_neighbours` parameter, injected exactly the way
`safe_room_neighbours` already was, and `solve_fixture`'s existing bounded re-solve loop now
discovers both. Structural marking (`_mark_open_interfaces`) is unchanged and still runs first;
geometric discovery only adds interfaces it could not express.

**The precondition is enforced, not assumed.** `_discover_open_interfaces` requires the shared
boundary to cover the **full side of both zones**. A wall side carries exactly one type, so a
partial overlap would have to be part open and part solid — the same part-exterior/part-seam
problem an L-wing seam has. Partial contact is skipped and the pair stays walled, rather than
approximated.

Safe rooms are skipped defensively as well, on top of the existing constructor guard.

**LDK physical openness result** — declared open, now actually open:

```
LIVING  {'N': 'EXTERIOR', 'S': 'OPEN',  'E': 'PARTITION', 'W': 'EXTERIOR'}
DINING  {'N': 'OPEN',     'S': 'OPEN',  'E': 'PARTITION', 'W': 'EXTERIOR'}
KITCHEN {'N': 'OPEN',     'S': 'PARTITION', 'E': 'PARTITION', 'W': 'EXTERIOR'}
```

No `PARTITION` remains anywhere an `OPEN_CONNECTION` was declared. The render shows one
continuous LIVING/DINING/KITCHEN volume with no internal lines.

## 3. Geometry Core change — necessary, and why

Option B cannot be done outside the engine. Wall type is decided in `derive_wall_types`, before
any dimension exists, and the whole engine reads insets from that map — so injecting open
interfaces after the fact would leave every net area, shape curve and validated figure computed
against walls that are no longer there.

What changed in `geometry_core/engine.py` (~80 lines):

| Element | Change |
|---|---|
| `derive_wall_types` | new optional `open_neighbours` parameter, applied before the precedence loop |
| `_side_facing` | **new** — which side of A faces B |
| `_discover_open_interfaces` | **new** — full-side open interfaces the tree could not express |
| `solve_wing` | new optional `extra_open` parameter, passed through |
| `solve_fixture` | the existing re-solve loop now discovers open interfaces alongside safe-room adjacency |

**Unchanged:** shape curves (`leaf_shapes`, `_combine`), assignment (`assign`), exact tiling,
`_mark_open_interfaces`, `WallType`, and the grid. No algorithm was replaced; one derivation
gained a second, geometric source.

**Disclosure:** `app/vertical_slice/geometry_core/` now intentionally diverges from the frozen
spike copy at `spikes/geometry_core/` (380 → 470 lines). The spike remains the historical proof
artifact for the original claim and still passes its own 34 tests; production has evolved past
it. They are no longer expected to be identical.

## 4. Tests

**636 passed.** New/changed:

- `test_open_plan_ldk_is_physically_open_not_merely_declared` — parametrized over all four
  geometries, asserts the actual `OPEN` wall values plus C13
- `test_declared_topology_is_physically_realized` — C13 green on all four general-pipeline cases
- All 11 strict `xfail` pins **removed** (they XPASSed, which is how they were designed to
  report a fix)
- `test_known_unrealized_programmes_fail_on_c13_specifically` deleted — its premise is gone
- The 9 realized-connectivity tests from the previous step are untouched and still pass,
  including the A/B/C and blocked-OPEN cases and both controls

## 5. Regressions

**None.** Canonical: gross **170.4 m²**, net **153.83 m²**, **2** iterations, **13/13** —
identical.

| Scenario | Strategy | Gross | Iters | Checks |
|---|---|---|---|---|
| 2BR | FRONT_PUBLIC_BAND | 104.5 | 1 | 13/13 |
| 2BR + safe room | SPINE_PUBLIC_PRIVATE | 128.8 | 2 | 13/13 |
| 3BR | SPINE_DOUBLE_LOADED | 152.6 | 2 | 13/13 |
| 3BR + safe room | SPINE_DOUBLE_LOADED | 154.8 | 2 | 13/13 |
| 3BR + safe room + 3 wet | SPINE_DOUBLE_LOADED | 149.9 | 2 | 13/13 |
| L-shape | SPINE_DOUBLE_LOADED | 149.9 | 2 | 13/13 |
| curved façade | SPINE_DOUBLE_LOADED | 149.9 | 2 | 13/13 |
| obstacle | SPINE_DOUBLE_LOADED | 149.9 | 2 | 13/13 |
| disconnected | SPINE_DOUBLE_LOADED | 150.4 | 2 | 13/13 |

One behaviour change worth naming: programmes without a safe room now take **2** wall
iterations instead of 1, because open-interface discovery needs the second pass. That is the
same cost the safe room already paid, it is bounded by the existing `max_wall_iterations`, and
it does not affect the canonical (already 2).

## 6. Files changed

| File | Change |
|---|---|
| `app/vertical_slice/geometry_core/engine.py` | option B (§3) |
| `app/vertical_slice/concept_generator.py` | `_orient_row` + applied per column |
| `tests/vertical_slice/test_concept_generator.py` | pins removed, LDK openness test added |
| `tests/vertical_slice/test_general_pipeline.py` | pins removed, C13 test added |

Not touched: `safe_adapter.py`, `geometry_domain/`, `doors.py`, `windows.py`, `validation.py`,
`design_output.py`, `renderer.py`, `concept.py` (the frozen canonical fixture).

## 7. Out of scope, as instructed

No work on 4BR, multi-wing, or further spatial research. 4BR remains rejected and is still
pinned by `test_four_bedroom_programme_still_does_not_complete_end_to_end`.

Worth noting for whenever you pick it up: **the constraint that blocked branched circulation is
now gone.** A hall may now be several leaves joined by real geometric open interfaces across
different subtrees, provided each joint is full-side. That is the capability the L/T corridor and
the multi-wing seam both needed.

Stopping for review.
