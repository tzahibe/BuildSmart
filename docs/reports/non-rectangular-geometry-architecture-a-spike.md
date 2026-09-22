# Non-rectangular geometry — Architecture A LIVING+KITCHEN merge spike (Issue #107)

**2-week spike, ROOT #102 child 2/3 (per `docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md` §4.A,
§6).** Implements the ONE merge case §4.A itself scoped: an adjacent LIVING leaf and KITCHEN leaf
whose relationship reads CLOSED_ADJACENT merge into one L-shaped room, by opening their shared
seam — generalising `app.demo.contract._open_corridor_to_public`'s own precedent (hall<->LDK, a
wall opened at segment level, the solver untouched) from "remove a wall" to "two rooms become one
room with a non-rectangular boundary." Flagged off by default
(`app.vertical_slice.room_merge.LIVING_KITCHEN_MERGE_ENABLED = False`); this is a spike, not a
product rollout — the Issue's own scope.

## 1. What was built

- **`app/vertical_slice/room_merge.py`** (new module, sibling to `contract.py` per the Issue's own
  "implementer's choice" language): `find_merge_candidate` (the CLOSED_ADJACENT test, reimplemented
  from the Issue's own description of the POC's `patterns.py::_public_composition` rule — that
  branch is not a dependency of this one), `compute_geometry` (the union polygon, via `shapely`),
  `validate_merged_room` (the redesigned/polygon-variant checks), `plan_merge` (orchestrates the
  three, returns `None` when the flag is off or no candidate exists).
- **`app/demo/contract.py`** (additive): `RoomOut` gains `shape: Literal["RECTANGLE","L"]` (mirrors
  `OutlineOut.shape`'s own precedent) and `polygon_m: list[tuple[float,float]] | None`; `DemoDesign`
  gains `merge: MergeOut | None` (which candidate was found, whether it was applied, and every
  check's own pass/fail + detail — a rejected candidate is a real, reportable outcome, not silently
  dropped). `_apply_room_merge` is the payload transform: the two source rooms collapse into one,
  the wall segment(s) strictly between them are DROPPED (not converted to an `OpenInterface` — the
  seam is now interior to one room, not a boundary between two), any door between them is dropped,
  and every remaining wall/open-interface/door naming one of the two source ids is remapped onto
  the merged id.
- **Frontend** (`DemoPlan.tsx`, `demoDesign.ts`, `DemoPlan.css`, additive): a merged room's own
  `polygon_m` is drawn as a real SVG `<polygon>` (a faint fill, `.demo-room-merged`) alongside the
  wall lines `design.walls` already draws correctly once the shared segment is removed; the room
  label centres on the polygon's own AREA CENTROID (shoelace formula) rather than the bounding-box
  centre, which can land in the L's own crook.
- **Tests**: `backend/tests/vertical_slice/test_living_kitchen_merge_spike.py` — 8 tests, direct
  unit proof of `room_merge.py`'s own logic and `contract._apply_room_merge`'s own payload
  transform (same style as `test_laundry_room.py`'s
  `test_laundry_notice_uses_the_fixed_template_target_not_a_second_solve`: a hand-built fixture,
  not a full pipeline solve — what is under test is the merge module's own logic, not whether a
  real brief happens to produce this pair, which the corpus sweep below measures separately).
- **`spikes/failure_log_sweep/living_kitchen_merge_ab.py`** — the 432-context corpus A/B this
  report's §3 reads from.

## 2. The CLOSED_ADJACENT test (AC-1)

Ported from the Issue's own description of `patterns.py::_public_composition`, without that
branch as a dependency: a LIVING leaf and a KITCHEN leaf are a merge candidate when, in the
realized `dict[str, Rect]` (read here off `design_output.GeometricDesign.rooms`):

1. their rectangles share a positive-length boundary (adjacent) — `find_merge_candidate` computes
   this directly off `rect_m`, the same `_side_between`/shared-edge-length primitives
   `validation.py`/`contract.py` already use elsewhere;
2. they are NOT members of the same declared open-plan group (`Fixture.open_groups`) — an open
   pair already reads as one space (OPEN), not CLOSED_ADJACENT, so there is nothing to merge;
3. the wall between them is an ordinary `STANDARD_PARTITION` — an RC wall or anything unusual is
   left untouched.

The FIRST such pair is used; this spike does not rank candidates (the Issue's own "one case only"
scope).

## 3. The redesigned/polygon-variant checks (AC-1, AC-4's kill criterion)

`validate_merged_room` re-derives exactly the checks the Issue named, scoped to the merged room
ONLY — every other room in the plan keeps its existing rectangle-only checks, computed by
`validation.validate()` exactly as before this spike, untouched.

| Check | Treatment for the merged room | Why |
|---|---|---|
| C1 — no overlap | **Recomputed**, real polygon-intersection (`shapely`) against every other room | new geometry (the union), so proven rather than assumed |
| C2 — no residual/no double-counted area | **Recomputed**, union area == exact sum of the two source rectangles | a real coverage proof for the merged pair specifically |
| C3 — areas/dimensions valid | **Recomputed**: combined `RoomTemplate` min/max (no single template covers a merged pair) + each source rectangle's own short side | no template exists for "LIVING+KITCHEN"; the short-side check is inherited-in-spirit (the merge never shrinks either rectangle) but recomputed directly |
| C6 — no artificial door in open-plan | **Recomputed**: no door remains exactly between the two source ids | a genuinely new fact about the opened seam |
| C7 — doors placeable | **Inherited** from the plan's own C7 | the merge touches no OTHER door |
| C8 — daylight/window exposure | **Inherited** from the plan's own C8 | the merge touches no exterior wall |
| C9 — furniture-envelope feasibility | **Inherited** from the plan's own C9 | restricted, as the investigation report itself proposes, to the case where a rectangular inscribed sub-area is already known — each source room's own already-proven fit, untouched by a union that only ever ADDS area |
| C14 — corridor width | **Not applicable** | neither LIVING nor KITCHEN is a circulation zone |
| C16 — entrance on the room it names | **Inherited** when the entrance targets a source room, else not applicable | the merge touches no exterior wall |
| C19 — required rooms touch an exterior wall | **Inherited** from the plan's own C19 | the merge touches no exterior wall |
| C20 — template aspect ratio | **Recomputed**: the union polygon's own axis-aligned-bounding-box long/short ratio vs the more permissive of the two source templates | genuinely new — no single template's aspect ceiling applies to a merged pair; see the AABB note below |
| C26 — no extreme circulation | **Not applicable** | neither merged room is circulation |
| C27 — displayed dims consistent | **Recomputed**, REDESIGNED formula: area is the union polygon's OWN area, never a bounding-box width x depth product | the check's own test asserts BOTH that the reported area matches the polygon and that the naive bbox formula would have overstated it — proving the redesign is necessary, not merely different |

**A real shapely bug found while measuring the corpus**: `Polygon.minimum_rotated_rectangle`
(GEOS `oriented_envelope`) divides by zero on a purely axis-aligned/orthogonal polygon — confirmed
directly against this environment's shapely (2.1.2), on both a flush-rectangle union AND a
genuine, non-degenerate L union. Every room this spike ever merges is axis-aligned by construction
(the solver never produces anything else), so C20's "oriented long/short" generalisation uses the
polygon's own AXIS-ALIGNED bounding box directly instead of a rotated search — a documented
simplification (a rotated search has nothing to gain over the AABB for a shape that is already
axis-aligned in the first place), not a shortcut around a real geometric question, and a real
regression guard for the shapely bug is in the test file
(`test_flush_merge_is_a_rectangle_not_a_degenerate_polygon`).

**AC-1 evidence**: `test_merged_room_passes_validation_and_renders_as_polygon` builds a hand-crafted
LIVING(5x5)+KITCHEN(4x3, partial-edge adjacency) pair, a third unrelated room, and a plan-level
`ValidationReport` with C7/C8/C9/C16/C19 already passing (as a real solved plan reaching
`to_demo_design` always has). It asserts all 13 checks above pass, the union polygon has more than
4 vertices (a genuine L, not an accidental flush rectangle), the bounding box is strictly larger
than the true polygon area (proving C27's redesign is actually needed), and that
`contract._apply_room_merge` produces exactly ONE `RoomOut` with `shape="L"` and a populated
`polygon_m`, with the two source rooms gone and every wall/door correctly remapped.

## 4. 432-context corpus measurement (AC-2, AC-3)

`spikes/failure_log_sweep/living_kitchen_merge_ab.py`, run against
`tests/regression_corpus/corpus.json` (the same trusted 432-context snapshot Issue #66 froze).

<!-- FILL-IN: exact numbers from the AB sweep run, 2026-09-23 -->

- **AC-2 (flag OFF)**: `room_merge.LIVING_KITCHEN_MERGE_ENABLED` defaults to `False`; `plan_merge`
  returns `None` unconditionally in that state before touching any geometry — the flag-off path is
  provably untouched by inspection (the very first line of `plan_merge`), and the sweep's own OFF
  pass is what today's baseline already is. **PASS.**
- **AC-3 (flag ON)**: LOST=`<FILL>`, `<FILL>` primary-signature changes, every one attributable to
  a merge candidate that was found AND passed its own checks (`merge.applied=True`) in that
  context's own primary — named per-context in the sweep's own console output (reproduce with the
  command in §6). `<FILL>` candidates found across the corpus, `<FILL>` applied, `<FILL>` rejected
  (found but failed one of their own checks — the plan is then drawn exactly as it would be with
  the flag off, per `MergeOut.applied=False`).

## 5. M1 kitchen/dining aspect, and the kill criterion (AC-4)

Over the `<FILL>` contexts where a merge actually APPLIED: kitchen/dining aspect median
**before** (mean of the two source rooms' own gross long/short ratio, read off the SAME context's
flag-OFF run) was `<FILL>`; **after** (the merged room's own oriented — axis-aligned-bounding-box —
aspect) was `<FILL>`.

**The investigation report's own kill criterion, answered directly**:

> if the merge candidate never validates a merged room's C9 furniture inscription across a
> representative footprint sweep, or moves M1's kitchen median aspect by less than the reference
> gap it targets (2.75 -> reference L-counter shape), the generalisation to more room-pairs is not
> worth pursuing.

- **C9 across a representative footprint sweep**: <FILL — PASS/FAIL and why, once the corpus
  numbers are in>.
- **M1 aspect move vs the 2.75 reference gap**: <FILL>.
- **Verdict**: <FILL — PROVEN / KILLED, and the one-sentence reason>.

## 6. Reproducing this spike

```
cd backend
uv run pytest -q tests/vertical_slice/test_living_kitchen_merge_spike.py -v
uv run python spikes/failure_log_sweep/living_kitchen_merge_ab.py
```

## 7. Out of scope, deliberately untouched

Per the Issue's own scope: any room-pair merge other than LIVING+KITCHEN, turning the flag on by
default, any change to the solver (`geometry_core/`), Architecture B or C. `contract.RoomOut.walls`
(per-side wall facts) is left empty (`{}`) for a merged room — that field's per-N/S/E/W semantics
do not generalise to an L's six-plus-sided boundary, and nothing reads it downstream (the
authoritative wall geometry for every room, merged or not, already lives in
`DemoDesign.walls`/`open_interfaces`). Net area for the merged room is the plain sum of the two
source rooms' own net areas — it does not reclaim the sliver of wall thickness the opened seam
frees, a conservative, documented simplification (the same direction `_open_corridor_to_public`'s
own C14 conservatism already takes). `quality.exposure`/`quality.wet_privacy` still list the two
source room ids individually (built off the raw pre-merge solver output) even when a merge
applies — a known, disclosed inconsistency with `DemoDesign.rooms`, not fixed in this spike.
