# Comparison -- brief-2

## Current engine baseline
REALIZED, ok=True, circulation_class=SPINE in 0.2s -> `current.svg`

## Brain alternatives

| concept | declared class | outcome | realized class | ok | time (s) |
|---|---|---|---|---|---|
| concept-0 (-) | FRONT_BAND | REFUSED | - | - | 0.6 |
| concept-1 (-) | OTHER | REFUSED | - | - | 0.6 |

## What adaptation changed

### concept-0
- **RESIZE_ROOMS**: total 127.4 m2 across 8 donor rooms -> total 80.5 m2 after per-type target resizing (each room type resized to its own architectural target area, independently -- never a single scale factor applied to every room)
- **BEDROOM_COUNT_ADJUST**: 3 bedroom(s) -> 4 bedroom(s) (brief requires 4 bedroom(s); added 1 to match, each at its own target area)

### concept-1
- **RESIZE_ROOMS**: total 122.1 m2 across 7 donor rooms -> total 80.0 m2 after per-type target resizing (each room type resized to its own architectural target area, independently -- never a single scale factor applied to every room)
- **BEDROOM_COUNT_ADJUST**: 3 bedroom(s) -> 4 bedroom(s) (brief requires 4 bedroom(s); added 1 to match, each at its own target area)

## Refusal / rejection reasons

- concept-0: REFUSED -- no footprint size solved for the SPINE template: depth 13.0 m: no width combination both fit and solved
- concept-1: REFUSED -- no footprint size solved for the SPINE template: depth 13.0 m: no width combination both fit and solved

## Measurements table (realized-and-ok plans, plus the current baseline)

| plan | class | gross_area_m2 | net_area_m2 | m3_circulation_share | m4_hall_door_count | m4_hall_aspect_median | m5_wet_adjacency_ratio | m6_public_zone_contiguous | wet_core_cluster_count | entrance_opens_into |
|---|---|---|---|---|---|---|---|---|---|---|
| current | SPINE | 128.7 | 117.26 | 0.1414141414141414 | 6 | 9.285714285714286 | 1.0 | True | 2 | HALL |
