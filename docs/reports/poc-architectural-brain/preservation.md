# RealizationIntent preservation -- fact taxonomy and how each is measured

Issue #109 (POC Phase 2, Track 3). `backend/spikes/architectural_brain/realization_intent.py`
builds a `RealizationIntent` from the retrieved `PlanReference` (donor) + the synthesized
`ConceptSpec` -- every structural fact the donor plan carries that `ConceptSpec`/`AdaptedConcept`
themselves have no field for at all (room types/areas and the circulation label/zoning/wet-core
pattern already survive today; everything below did not). `backend/spikes/architectural_brain/
preservation.py`'s `measure_preservation(intent, plan, donor_room_id_by_zone)` then measures, for
each fact class below, how much of it actually reached the REALIZED geometry -- never crediting a
fact from the intent itself, only from `plan.design` (the realized `GeometricDesign`).

`donor_room_id_by_zone` (`realize.donor_room_id_by_zone(brief, adapted)`) is the `zone_id -> donor
room id` correspondence the SAME `brief`/`adapted` concept was compiled with -- it is how a
donor-room-keyed intent fact is translated onto a realized zone id at all. A donor room this
mapping has no entry for (dropped, or never individually resized, by `adaptation.py`) makes every
fact naming it LOST with reason `DONOR_ROOM_NOT_REALIZED` -- never silently skipped.

## Fact classes and how each is measured

| Fact class | On the donor (`RealizationIntent`) | On the realized plan (`measure_preservation`) |
|---|---|---|
| `adjacency` | `adjacency_edges`: room pairs whose donor polygons share a wall | the two realized `RoomOut.rect_m` share a positive-length edge (`_rects_touch`) |
| `access` | `access_edges`: room pairs walkable via a door on the donor | the two realized zones are connected in the realized door graph (`interior_doors` + `entrance_door`) OR share an `open_groups` entry (an `OPEN_CONNECTION` has no physical door but is still walkable) |
| `exposure` | `exterior_exposure`: which compass sides of each donor room sit on ITS OWN envelope | compares EXTERIOR-FACING SIDE **COUNT**, not compass letters -- the donor's own coordinate frame and the realized building's are unrelated, so only the count is frame-independent; preserved when the realized room's own exterior side count >= the donor's |
| `placement` | `relative_placement`: FRONT/REAR/LEFT/RIGHT/ABOVE/BELOW, computed relative to the donor's OWN entrance side and footprint centre (`_relative_placement_for`) | the SAME labelling rule, reapplied to the realized geometry (`_realized_entrance_side` + `_relative_placement_for`); preserved when every non-UNKNOWN axis label matches |
| `clusters` | `public_private_clusters`: donor room ids in `PUBLIC_TYPES`/`PRIVATE_TYPES` | the donor-mapped realized PUBLIC (resp. PRIVATE) rooms form ONE connected component under realized adjacency |
| `wet_core_groups` | connected components of donor WET_TYPES rooms under donor adjacency | every donor-mapped member of one intent group lands in the SAME realized `design.wet_core` cluster |
| `entrance_relationship` | `entrance_relationship`: donor entrance room id, classified TO_LIVING/TO_HALL/TO_KITCHEN/TO_OTHER by room TYPE (via `room_proportions`, since the fact itself only carries an id) | the realized entrance zone's own roles classified the SAME way |
| `room_proportions` | `room_proportions`: each donor room's own `area_share_of_type` (area / mean area of donor rooms of the same type) | the realized room's own area share among realized zones of the same role, within `_AREA_SHARE_TOLERANCE` (15%) |
| `footprint_relationships` | `footprint_relationships`: donor footprint `fill_ratio`/`aspect_ratio` | the realized footprint's own `fill_ratio`/`aspect_ratio` (`design.footprint_m`/`design.footprints_m`), within `_FOOTPRINT_TOLERANCE` (15%) |

## Reason taxonomy (every `LostFact.reason`)

- `DONOR_ROOM_NOT_REALIZED` -- the fact names a donor room `donor_room_id_by_zone` has no realized
  zone for (dropped by `BEDROOM_COUNT_ADJUST`, or never individually resized by adaptation at all
  -- e.g. `DINING`/`SAFE_ROOM`/`TOILET_1` have no per-instance donor match today, see `realize.py`'s
  own `_donor_room_id`).
- `GUILLOTINE_IMPOSSIBLE` -- both rooms/facts ARE realized, but `realize.py`'s own compiled
  slicing tree did not place them the way the fact asked. This POC's compiler does not actively
  search for a tree that honours adjacency/access/exposure/placement -- see "what realize.py
  actually attempts" below.
- `BUDGET` -- the realized value is clipped by `ROOM_TEMPLATES`' own `[min, max]` area bound
  (`room_proportions` only).

## What `realize.py` actually attempts today (honest scope note)

Required Behaviour 2 of Issue #109 asks the realizer to "attempt to honour" as many
adjacency/access/exposure/placement facts as the guillotine language allows. What this Issue's own
`realize.py` change actually does:

- **Room AREA sizing** IS actively driven by the intent: `_zone`/`_intent_target_area_m2` read each
  donor room's own `area_share_of_type` from `RealizationIntent.room_proportions` and use it (times
  the role's own template target) as that zone's target area, replacing the fixed per-type constant
  `adaptation.py` used alone. Measured directly (`test_two_donors_for_one_brief_realize_to_
  different_layouts`, xfail-documented): this genuinely changes each room's TARGET, but does not
  always change the REALIZED geometry -- see the root-cause note below.
- **Topology** (adjacency/access/exposure/placement) is NOT actively searched from the intent: the
  compiler still picks a FIXED template (SPINE/TWO_WING) per `circulation_class` and builds its
  hard-coded tree of ensuite/hall/entrance edges from the brief's own authoritative requirements
  (`wet_rooms.resolve_wet_rooms`), never from `intent.adjacency_edges`/`access_edges`/
  `exterior_exposure`/`relative_placement`. The `placement`/`adjacency`/`access`/`exposure`
  preservation numbers measured on brief-1/2/3 (`brief-N/comparison.md`) are therefore whatever the
  EXISTING template's own incidental structure happens to match, not a result of active honouring --
  this is exactly the "where architectural information disappears" finding the Issue's own Goal
  asks this POC to surface, not a gap this Issue's own implementation hides.

### Root cause of the persisting "brief 1 collapse" (measured)

Even with intent-driven room-area sizing, `BRIEF_1`'s own concept-0/concept-1 (two different
primary donors) still realize to byte-identical geometry. Traced into the frozen
`geometry_core.engine.assign` (explicitly out of this Issue's scope to change): the compiler's own
private-column WIDTH is selected by `_feasible_widths_u_at_height`, which reads each zone's
`[min, max]` bound ONLY -- identical for both donors, since it comes from `ROOM_TEMPLATES` (the
brief's own authoritative room counts), never from the donor. At that shared width, `leaf_shapes`'
own `min_short_side_m`/`max_aspect_ratio` bound raises a room's minimum FEASIBLE height above both
donors' own proportional target height, so `assign`'s closest-to-target picker saturates at the
same width-driven minimum for both -- never reaching either donor's own distinct target. See
`backend/tests/architectural_brain/test_realization_intent.py::
test_two_donors_for_one_brief_realize_to_different_layouts` (xfail, strict, exercised every run)
and each brief's own `comparison.md` "Layout collapse" section for the per-brief instance of this.
