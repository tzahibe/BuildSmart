# Comparison -- brief-1

## Current engine baseline
REALIZED, ok=True, circulation_class=FRONT_BAND in 1.6s -> `current.svg`

## Brain alternatives

| concept | declared class | outcome | realized class | ok | time (s) |
|---|---|---|---|---|---|
| concept-0 (A) | OTHER | REALIZED | SPINE | True | 149.9 |
| concept-1 (B) | FRONT_BAND | REALIZED | SPINE | True | 150.3 |

## What adaptation changed

### concept-0
- **RESIZE_ROOMS**: total 190.7 m2 across 10 donor rooms -> total 102.0 m2 after per-type target resizing (each room type resized to its own architectural target area, independently -- never a single scale factor applied to every room)

### concept-1
- **RESIZE_ROOMS**: total 215.3 m2 across 8 donor rooms -> total 85.0 m2 after per-type target resizing (each room type resized to its own architectural target area, independently -- never a single scale factor applied to every room)
- **BEDROOM_COUNT_ADJUST**: 3 bedroom(s) -> 4 bedroom(s) (brief requires 4 bedroom(s); added 1 to match, each at its own target area)

## Refusal / rejection reasons


## Measurements table (realized-and-ok plans, plus the current baseline)

| plan | class | gross_area_m2 | net_area_m2 | m3_circulation_share | m4_hall_door_count | m4_hall_aspect_median | m5_wet_adjacency_ratio | m6_public_zone_contiguous | wet_core_cluster_count | entrance_opens_into |
|---|---|---|---|---|---|---|---|---|---|---|
| current | FRONT_BAND | 189.8 | 172.31 | 0.08630136986301369 | 8 | 8.357142857142858 | 0.6666666666666666 | False | 2 | LIVING |
| brain-A (concept-0) | SPINE | 170.05 | 152.55 | 0.1787709497206704 | 9 | 5.9375 | 0.6666666666666666 | True | 2 | HALL_1 |
| brain-B (concept-1) | SPINE | 170.05 | 152.55 | 0.1787709497206704 | 9 | 5.9375 | 0.6666666666666666 | True | 2 | HALL_1 |
