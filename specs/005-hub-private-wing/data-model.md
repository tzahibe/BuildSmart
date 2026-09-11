# Data Model: Hub-Organised Private Wing

All entities are frozen dataclasses in `backend/app/vertical_slice/concept_generator.py`, following
the existing `ColumnPlan` / `LayoutPlan` pattern. Nothing is persisted; these are intermediate planning
records that end as a `Concept` (fixture + tree + access graph) exactly like the other partis produce.

## New enum members and template row

| Entity | Change | Invariant |
|---|---|---|
| `ConceptStrategy.HUB_PRIVATE_WING` | new member | Additive; enum order of existing members unchanged (the area sort's tiebreak uses `.value`, not position). |
| `HUB_TEMPLATE` (module constant) | `RoomTemplate(6.0, 8.5, 12.0, 2.4, 1.5, elasticity=0.1)` | Circulation tier: elasticity equal to HALL's (0.1), below every bedroom. Not a `ROOM_TEMPLATES` row: the hub `ProgramRoom` is `ProgramRoom("HALL", ProgramRole.HALL, ZoneGroup.CIRCULATION, HUB_TEMPLATE)`, built by `_hub_concept` in place of the variant's HALL room. No `ProgramRole` is added; `geometry_core/` is untouched (research R1). |

## `HubAllocation`

Which room goes where. Produced by `_hub_allocation(rooms)`; pure function of the programme.

| Field | Type | Meaning | Rule (spec FR-3) |
|---|---|---|---|
| `public` | `list[ProgramRoom]` | zones across the front band | `ZoneGroup.PUBLIC`, in programme order; `public[0]` spans the hub (R6) |
| `hub` | `ProgramRoom` | the room lobby | `zone_id == "HALL"`, role `ROOM_LOBBY` |
| `flank_west`, `flank_east` | `ProgramRoom` | one room each side of the hub, full hub depth | bedrooms first (they come out near-square); safe room allowed; never a wet room when a bedroom is available |
| `foot` | `list[list[ProgramRoom]]` | 2–3 slots along the band under the hub; a slot is `[room]` or `[master, ensuite]` | master(+ensuite) first; then safe room; then wet rooms **adjacent to each other** (the wet cluster); an ensuite never occupies its own slot |
| `needs_door` | `int` | rooms that must open onto the hub | `= 2 + len(foot)`; must be `≤ 5` in v1 (R8) else `ACCESS_DEGREE_EXCEEDED` |

Validation on construction:
- every private/service room appears exactly once (flank, foot slot, or as an ensuite inside a slot);
- an ensuite (`entered_from` set) is placed in its bedroom's slot, ordered so the bedroom is the member
  that touches the hub's x-range (`_orient_row` semantics, applied along x here);
- `len(foot) ∈ {2, 3}`; the wet rooms in `foot` occupy consecutive slots.

## `HubPlan`

Mutually consistent dimensions, produced by `_plan_hub_wing(rooms, allocation, fw, fh)`; the analogue
of `_plan_front_band`'s return tuple.

| Field | Type | Meaning | Invariant |
|---|---|---|---|
| `band_depth_m` | float | depth of the public band | `≥ max(public min_short_side) + inset`; `≤` the binding public room's cap depth (same rule as `_plan_front_band`) |
| `public_widths_m` | `list[float]` | V-chain widths across the band | `public_widths[0]` covers the hub's x-range with ≥ 1.10 m overlap; each `≥ min_short_side + inset` |
| `hub_w_m` | float | hub width | `∈ {2.4, 2.7, 3.0, 3.3, 3.6}` (0.05 grid) |
| `hub_d_m` | float | hub depth = flank depth | `≥ max(flank min_short_side, hub min_short_side) + inset`; `hub_w/hub_d` and inverse `≤ 1.5` |
| `west_w_m`, `east_w_m` | float | flank widths | each `≥ flank room min_short_side + inset`; `west_w + hub_w + east_w == fw` |
| `foot_depth_m` | float | depth of the foot band | `≥ max over slots of (min_short_side + inset)`; `band + hub_d + foot == fh` |
| `foot_widths_m` | `list[float]` | V-chain widths along the foot band | `_row_widths` semantics per slot; every slot's x-overlap with the hub `≥ 1.10 m` |
| `specs` | `dict[str, ZoneSpec]` | one per zone | areas follow geometry: `target = net_w × net_d`, min `0.55×`, max `1.70×` (front-band factors); `min_short_side_m` from the template; `max_aspect_ratio = max(template, realized + 0.3)` |

Failure modes map to the existing precise reason codes with `shortfall_m` where measurable:
`COLUMN_WIDTH_EXCEEDED` (flanks + hub wider than `fw`), `COLUMN_DEPTH_EXCEEDED` (band + hub + foot
deeper than `fh`), `ROW_WIDTH_EXCEEDED` (foot slots cannot sit side by side), `BAND_WIDTH_BELOW_MINIMUM`
(a public zone too narrow), `ROOM_ABOVE_MAXIMUM_AREA` (band would inflate a public room past its cap),
`ACCESS_DEGREE_EXCEEDED` (more than 5 rooms need a hub door).

## Tree and access graph (derived, not stored)

```
Split(H, _forced_v_chain(public, public_widths),
      Split(H,
            Split(V, Leaf(flank_west), Split(V, Leaf("HALL"), Leaf(flank_east), u(hub_w)), u(west_w)),
            _forced_v_chain(foot_flat, foot_widths),      # a [master, ensuite] slot is a nested V split
            u(hub_d)),
      u(band_depth))
```

Access (`_build_access(rooms, ["HALL"], public_ids, open_plan, hall_for, hall_borders_only_first_public=True)`):
`HALL → public[0]` CASED_OPENING; public chain per existing rules; `HALL → each flank/foot room` DOOR;
`master → ensuite` DOOR. Open groups: the public group when `open_plan`; the hub is never in one.

## State transitions

None — a `HubPlan` is either produced or replaced by a `PlanFailure`, exactly like `LayoutPlan`.
