# Comparison -- brief-3

## Current engine baseline
REFUSED (outcome=INSUFFICIENT_RECTANGULAR_CAPACITY): FRONT_PUBLIC_BAND/ROOM_SHAPE_INFEASIBLE: BEDROOM_1 at 5.50 m wide in the rear west column has no depth that keeps its 2.5 aspect ratio and 2.6 m short side under its 14 m2 preferred maximum (needs 2.60 m, allowed 2.55 m); re-partitioned: BEDROOM_1 would be 5.25 x 2.70 m = 14.2 m2 in the rear west column, past its 14 m2 preferred maximum; SPINE_PUBLIC_PRIVATE/COLUMN_DEPTH_EXCEEDED: east column needs 18.06 m of depth for its rows' floors but has 10.50 m [MASTER 3.20 (shape floor, area wanted 2.39); TOILET_1+BATH_1 1.86 (shape floor, area wanted 1.75); BEDROOM_1 2.80 (shape floor, area wanted 1.96); BEDROOM_2 2.80 (shape floor, area wanted 1.96); BEDROOM_3 2.80 (shape floor, area wanted 1.96); BEDROOM_4 2.80 (shape floor, area wanted 1.96); BATH_2 1.80 (shape floor, area wanted 1.09)]; SPINE_DOUBLE_LOADED/ROOM_ABOVE_MAXIMUM_AREA: BEDROOM_1 would be 5.30 x 2.70 m = 14.3 m2 in the west column, past its 14 m2 preferred maximum; SPINE_SERVICE_CLUSTER/COLUMN_DEPTH_EXCEEDED: east column needs 17.03 m of depth for its rows' floors but has 10.50 m [BEDROOM_1 3.47 (shape floor, area wanted 3.27); BEDROOM_2 3.47 (shape floor, area wanted 3.27); BEDROOM_3 3.47 (shape floor, area wanted 3.27); BEDROOM_4 3.47 (shape floor, area wanted 3.27); TOILET_1 1.30 (shape floor, area wanted 1.12); BATH_2 1.84 (shape floor, area wanted 1.82)]; SPINE_DOUBLE_LOADED/COLUMN_DEPTH_EXCEEDED: west column needs 15.59 m of depth for its rows' floors but has 10.50 m [LIVING 3.57 (shape floor, area wanted 3.37); KITCHEN 2.60 (shape floor, area wanted 1.99); BEDROOM_1 2.80 (shape floor, area wanted 1.89); BEDROOM_2 2.80 (shape floor, area wanted 1.89); BATH_1+MASTER 3.83 (shape floor, area wanted 3.37)]; re-partitioned: west column needs 15.59 m of depth for its rows' floors but has 10.50 m [LIVING 3.57 (shape floor, area wanted 3.37); KITCHEN 2.60 (shape floor, area wanted 1.99); BEDROOM_1 2.80 (shape floor, area wanted 1.89); BEDROOM_2 2.80 (shape floor, area wanted 1.89); BATH_1+MASTER 3.83 (shape floor, area wanted 3.37)]; BRANCHED_TWO_STACK/COLUMN_DEPTH_EXCEEDED: west column needs 10.85 m of depth for its rows' floors but has 10.50 m [LIVING 4.91 (shape floor, area wanted 4.71); KITCHEN 2.85 (shape floor, area wanted 2.78); TOILET_1 1.30 (shape floor, area wanted 0.90); BATH_2 1.80 (shape floor, area wanted 1.47)]; HUB_PRIVATE_WING/ACCESS_DEGREE_EXCEEDED: 7 rooms need a door on the lobby but it seats 6 (two rooms on each flank, two in the foot band); MULTI_WING_SPLIT/NO_SEAM_ALIGNMENT: the second wing (21.0 x 4.0 m) sits north or south of the primary; this parti runs its hall along the seam, and a hall along the street axis is not authored yet

## Brain alternatives

| concept | declared class | outcome | realized class | ok | time (s) |
|---|---|---|---|---|---|
| concept-0 (-) | OTHER | REFUSED | - | - | 0.5 |
| concept-1 (-) | FRONT_BAND | REFUSED | - | - | 0.5 |
| concept-5 (A) | TWO_WING | REALIZED | TWO_WING | True | 0.2 |

## What adaptation changed

### concept-0
- **RESIZE_ROOMS**: total 190.7 m2 across 10 donor rooms -> total 102.0 m2 after per-type target resizing (each room type resized to its own architectural target area, independently -- never a single scale factor applied to every room)
- **BEDROOM_COUNT_ADJUST**: 4 bedroom(s) -> 5 bedroom(s) (brief requires 5 bedroom(s); added 1 to match, each at its own target area)

### concept-1
- **RESIZE_ROOMS**: total 215.3 m2 across 8 donor rooms -> total 85.0 m2 after per-type target resizing (each room type resized to its own architectural target area, independently -- never a single scale factor applied to every room)
- **BEDROOM_COUNT_ADJUST**: 3 bedroom(s) -> 5 bedroom(s) (brief requires 5 bedroom(s); added 2 to match, each at its own target area)

### concept-5
- **RESIZE_ROOMS**: total 143.6 m2 across 8 donor rooms -> total 85.0 m2 after per-type target resizing (each room type resized to its own architectural target area, independently -- never a single scale factor applied to every room)
- **BEDROOM_COUNT_ADJUST**: 3 bedroom(s) -> 5 bedroom(s) (brief requires 5 bedroom(s); added 2 to match, each at its own target area)

## Refusal / rejection reasons

- concept-0: REFUSED -- no footprint size solved for the SPINE template: depth 10.0 m: no width combination both fit and solved
- concept-1: REFUSED -- no footprint size solved for the SPINE template: depth 10.0 m: no width combination both fit and solved

## Measurements table (realized-and-ok plans, plus the current baseline)

| plan | class | gross_area_m2 | net_area_m2 | m3_circulation_share | m4_hall_door_count | m4_hall_aspect_median | m5_wet_adjacency_ratio | m6_public_zone_contiguous | wet_core_cluster_count | entrance_opens_into |
|---|---|---|---|---|---|---|---|---|---|---|
| brain-A (concept-5) | TWO_WING | 154.35 | 140.22 | 0.22076449627470038 | 9 | 3.085106382978723 | 0.6666666666666666 | True | 2 | HALL_A |
