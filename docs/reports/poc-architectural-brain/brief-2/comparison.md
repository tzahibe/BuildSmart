# Comparison -- brief-2

## Current engine baseline
REALIZED, ok=True, circulation_class=SPINE in 0.2s -> `current.svg`

## Brain alternatives

| concept | declared class | outcome | realized class | ok | time (s) |
|---|---|---|---|---|---|
| concept-0 (-) | FRONT_BAND | REALIZED | SPINE | False | 17.8 |
| concept-1 (-) | OTHER | REALIZED | SPINE | False | 17.6 |

## What adaptation changed

### concept-0
- **RESIZE_ROOMS**: total 127.4 m2 across 8 donor rooms -> total 80.5 m2 after per-type target resizing (each room type's aggregate resized to its own architectural target area, independently -- never a single scale factor applied to every room -- and each individual room's OWN share of that aggregate carries the donor's own proportion forward, so a different donor with a different internal size spread adapts to different individual room areas even at the same aggregate target)
- **BEDROOM_COUNT_ADJUST**: 3 bedroom(s) -> 4 bedroom(s) (brief requires 4 bedroom(s); added 1 to match, each at its own target area)

### concept-1
- **RESIZE_ROOMS**: total 122.1 m2 across 7 donor rooms -> total 80.0 m2 after per-type target resizing (each room type's aggregate resized to its own architectural target area, independently -- never a single scale factor applied to every room -- and each individual room's OWN share of that aggregate carries the donor's own proportion forward, so a different donor with a different internal size spread adapts to different individual room areas even at the same aggregate target)
- **BEDROOM_COUNT_ADJUST**: 3 bedroom(s) -> 4 bedroom(s) (brief requires 4 bedroom(s); added 1 to match, each at its own target area)

## Refusal / rejection reasons


## Realized-but-failing-validation plans

- concept-0: REALIZED, ok=False -- failing checks: C19, C8
- concept-1: REALIZED, ok=False -- failing checks: C19, C8

## RealizationIntent preservation (Issue #109 Track 3)

### PRESERVED / LOST -- concept-0 (donor 9302)

| fact class | preserved | total | ratio |
|---|---|---|---|
| adjacency | 2 | 12 | 17% |
| access | 4 | 5 | 80% |
| exposure | 4 | 6 | 67% |
| placement | 0 | 8 | 0% |
| clusters | 0 | 2 | 0% |
| wet_core_groups | 1 | 2 | 50% |
| entrance_relationship | 0 | 1 | 0% |
| room_proportions | 6 | 6 | 100% |
| footprint_relationships | 2 | 2 | 100% |

LOST facts:

- **adjacency** BATHROOM_0-LIVING_0 (realized BATH_1/LIVING do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** BEDROOM_0-LIVING_0 (realized BEDROOM_1/LIVING do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** BEDROOM_1-LIVING_0 (realized BEDROOM_2/LIVING do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** BEDROOM_1-TOILET_0 -- DONOR_ROOM_NOT_REALIZED
- **adjacency** BEDROOM_2-LIVING_0 (realized BEDROOM_3/LIVING do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** BEDROOM_2-STORAGE_0 -- DONOR_ROOM_NOT_REALIZED
- **adjacency** KITCHEN_0-LIVING_0 (realized KITCHEN/LIVING do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** KITCHEN_0-STORAGE_0 -- DONOR_ROOM_NOT_REALIZED
- **adjacency** LIVING_0-STORAGE_0 -- DONOR_ROOM_NOT_REALIZED
- **adjacency** LIVING_0-TOILET_0 -- DONOR_ROOM_NOT_REALIZED
- **access** LIVING_0-TOILET_0 (DOOR) -- DONOR_ROOM_NOT_REALIZED
- **exposure** BATHROOM_0 (donor sides=['N']): realized BATH_1 has 0 exterior side(s) -- GUILLOTINE_IMPOSSIBLE
- **exposure** TOILET_0 (donor sides=['S']) -- DONOR_ROOM_NOT_REALIZED
- **placement** LIVING_0 (donor FRONT/ABOVE): realized LIVING is FRONT/LEFT -- GUILLOTINE_IMPOSSIBLE
- **placement** KITCHEN_0 (donor REAR/ABOVE): realized KITCHEN is REAR/LEFT -- GUILLOTINE_IMPOSSIBLE
- **placement** BEDROOM_0 (donor FRONT/ABOVE): realized BEDROOM_1 is REAR/LEFT -- GUILLOTINE_IMPOSSIBLE
- **placement** BEDROOM_1 (donor REAR/BELOW): realized BEDROOM_2 is FRONT/RIGHT -- GUILLOTINE_IMPOSSIBLE
- **placement** BEDROOM_2 (donor REAR/BELOW): realized BEDROOM_3 is REAR/RIGHT -- GUILLOTINE_IMPOSSIBLE
- **placement** BATHROOM_0 (donor FRONT/ABOVE): realized BATH_1 is REAR/LEFT -- GUILLOTINE_IMPOSSIBLE
- **placement** TOILET_0 (donor FRONT/BELOW) -- DONOR_ROOM_NOT_REALIZED
- **placement** STORAGE_0 (donor REAR/BELOW) -- DONOR_ROOM_NOT_REALIZED
- **clusters** public: split across 2 disconnected groups -- GUILLOTINE_IMPOSSIBLE
- **clusters** private: split across 2 disconnected groups -- GUILLOTINE_IMPOSSIBLE
- **wet_core_groups** group ['TOILET_0']: ['TOILET_0'] not realized -- DONOR_ROOM_NOT_REALIZED
- **entrance_relationship** donor entrance -> TO_LIVING, realized entrance -> TO_HALL -- GUILLOTINE_IMPOSSIBLE

### PRESERVED / LOST -- concept-1 (donor 518)

| fact class | preserved | total | ratio |
|---|---|---|---|
| adjacency | 2 | 9 | 22% |
| access | 5 | 5 | 100% |
| exposure | 3 | 4 | 75% |
| placement | 0 | 7 | 0% |
| clusters | 0 | 2 | 0% |
| wet_core_groups | 2 | 2 | 100% |
| entrance_relationship | 0 | 1 | 0% |
| room_proportions | 5 | 7 | 71% |
| footprint_relationships | 1 | 2 | 50% |

LOST facts:

- **adjacency** BATHROOM_0-BEDROOM_1 (realized BATH_1/BEDROOM_2 do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** BATHROOM_0-LIVING_0 (realized BATH_1/LIVING do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** BATHROOM_1-BEDROOM_1 (realized BATH_2/BEDROOM_2 do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** BEDROOM_0-LIVING_0 (realized BEDROOM_1/LIVING do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** BEDROOM_1-LIVING_0 (realized BEDROOM_2/LIVING do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** BEDROOM_2-LIVING_0 (realized BEDROOM_3/LIVING do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** KITCHEN_0-LIVING_0 (realized KITCHEN/LIVING do not touch) -- GUILLOTINE_IMPOSSIBLE
- **exposure** BATHROOM_0 (donor sides=['E']): realized BATH_1 has 0 exterior side(s) -- GUILLOTINE_IMPOSSIBLE
- **placement** LIVING_0 (donor ABOVE/LEFT): realized LIVING is FRONT/LEFT -- GUILLOTINE_IMPOSSIBLE
- **placement** KITCHEN_0 (donor ABOVE/LEFT): realized KITCHEN is REAR/LEFT -- GUILLOTINE_IMPOSSIBLE
- **placement** BEDROOM_0 (donor ABOVE/RIGHT): realized BEDROOM_1 is REAR/LEFT -- GUILLOTINE_IMPOSSIBLE
- **placement** BEDROOM_1 (donor BELOW/RIGHT): realized BEDROOM_2 is FRONT/RIGHT -- GUILLOTINE_IMPOSSIBLE
- **placement** BEDROOM_2 (donor BELOW/LEFT): realized BEDROOM_3 is REAR/RIGHT -- GUILLOTINE_IMPOSSIBLE
- **placement** BATHROOM_0 (donor BELOW/RIGHT): realized BATH_1 is REAR/LEFT -- GUILLOTINE_IMPOSSIBLE
- **placement** BATHROOM_1 (donor BELOW/RIGHT): realized BATH_2 is REAR/RIGHT -- GUILLOTINE_IMPOSSIBLE
- **clusters** public: split across 2 disconnected groups -- GUILLOTINE_IMPOSSIBLE
- **clusters** private: split across 2 disconnected groups -- GUILLOTINE_IMPOSSIBLE
- **entrance_relationship** donor entrance -> TO_LIVING, realized entrance -> TO_HALL -- GUILLOTINE_IMPOSSIBLE
- **room_proportions** BATHROOM_0/BATH_1: donor share=1.046, realized share=1.224 -- BUDGET
- **room_proportions** BATHROOM_1/BATH_2: donor share=0.954, realized share=0.776 -- BUDGET
- **footprint_relationships** fill_ratio: donor=0.798, realized=1.000 -- GUILLOTINE_IMPOSSIBLE

## Measurements table (realized-and-ok plans, plus the current baseline)

| plan | class | gross_area_m2 | net_area_m2 | m3_circulation_share | m4_hall_door_count | m4_hall_aspect_median | m5_wet_adjacency_ratio | m6_public_zone_contiguous | wet_core_cluster_count | entrance_opens_into |
|---|---|---|---|---|---|---|---|---|---|---|
| current | SPINE | 128.7 | 117.26 | 0.1414141414141414 | 6 | 9.285714285714286 | 1.0 | True | 2 | HALL |
