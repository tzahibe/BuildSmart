# Comparison -- brief-1

## Current engine baseline
REALIZED, ok=True, circulation_class=FRONT_BAND in 1.6s -> `current.svg`

## Brain alternatives

| concept | declared class | outcome | realized class | ok | time (s) |
|---|---|---|---|---|---|
| concept-0 (A) | OTHER | REALIZED | SPINE | True | 150.9 |
| concept-1 (B) | FRONT_BAND | REALIZED | SPINE | True | 3.1 |

## What adaptation changed

### concept-0
- **RESIZE_ROOMS**: total 190.7 m2 across 10 donor rooms -> total 102.0 m2 after per-type target resizing (each room type's aggregate resized to its own architectural target area, independently -- never a single scale factor applied to every room -- and each individual room's OWN share of that aggregate carries the donor's own proportion forward, so a different donor with a different internal size spread adapts to different individual room areas even at the same aggregate target)

### concept-1
- **RESIZE_ROOMS**: total 215.3 m2 across 8 donor rooms -> total 85.0 m2 after per-type target resizing (each room type's aggregate resized to its own architectural target area, independently -- never a single scale factor applied to every room -- and each individual room's OWN share of that aggregate carries the donor's own proportion forward, so a different donor with a different internal size spread adapts to different individual room areas even at the same aggregate target)
- **BEDROOM_COUNT_ADJUST**: 3 bedroom(s) -> 4 bedroom(s) (brief requires 4 bedroom(s); added 1 to match, each at its own target area)

## Refusal / rejection reasons


## RealizationIntent preservation (Issue #109 Track 3)

### PRESERVED / LOST -- concept-0 (donor 13630)

| fact class | preserved | total | ratio |
|---|---|---|---|
| adjacency | 2 | 14 | 14% |
| access | 4 | 8 | 50% |
| exposure | 3 | 3 | 100% |
| placement | 0 | 10 | 0% |
| clusters | 1 | 2 | 50% |
| wet_core_groups | 2 | 4 | 50% |
| entrance_relationship | 0 | 1 | 0% |
| room_proportions | 6 | 7 | 86% |
| footprint_relationships | 0 | 2 | 0% |

LOST facts:

- **adjacency** BATHROOM_0-LIVING_0 (realized BATH_1/LIVING do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** BATHROOM_1-BEDROOM_3 -- DONOR_ROOM_NOT_REALIZED
- **adjacency** BATHROOM_2-BEDROOM_2 -- DONOR_ROOM_NOT_REALIZED
- **adjacency** BATHROOM_2-LIVING_0 -- DONOR_ROOM_NOT_REALIZED
- **adjacency** BATHROOM_3-BEDROOM_1 -- DONOR_ROOM_NOT_REALIZED
- **adjacency** BATHROOM_3-BEDROOM_2 -- DONOR_ROOM_NOT_REALIZED
- **adjacency** BATHROOM_3-LIVING_0 -- DONOR_ROOM_NOT_REALIZED
- **adjacency** BEDROOM_0-LIVING_0 (realized BEDROOM_1/LIVING do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** BEDROOM_1-LIVING_0 (realized BEDROOM_2/LIVING do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** BEDROOM_2-LIVING_0 (realized BEDROOM_3/LIVING do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** BEDROOM_3-LIVING_0 -- DONOR_ROOM_NOT_REALIZED
- **adjacency** KITCHEN_0-LIVING_0 (realized KITCHEN/LIVING do not touch) -- GUILLOTINE_IMPOSSIBLE
- **access** BATHROOM_1-BEDROOM_3 (DOOR) -- DONOR_ROOM_NOT_REALIZED
- **access** BATHROOM_2-BEDROOM_2 (DOOR) -- DONOR_ROOM_NOT_REALIZED
- **access** BATHROOM_3-BEDROOM_1 (DOOR) -- DONOR_ROOM_NOT_REALIZED
- **access** BEDROOM_3-LIVING_0 (DOOR) -- DONOR_ROOM_NOT_REALIZED
- **placement** LIVING_0 (donor ABOVE/LEFT): realized LIVING is FRONT/LEFT -- GUILLOTINE_IMPOSSIBLE
- **placement** KITCHEN_0 (donor ABOVE/LEFT): realized KITCHEN is REAR/LEFT -- GUILLOTINE_IMPOSSIBLE
- **placement** BEDROOM_0 (donor ABOVE/RIGHT): realized BEDROOM_1 is FRONT/RIGHT -- GUILLOTINE_IMPOSSIBLE
- **placement** BEDROOM_1 (donor BELOW/RIGHT): realized BEDROOM_2 is FRONT/RIGHT -- GUILLOTINE_IMPOSSIBLE
- **placement** BEDROOM_2 (donor BELOW/RIGHT): realized BEDROOM_3 is REAR/RIGHT -- GUILLOTINE_IMPOSSIBLE
- **placement** BEDROOM_3 (donor BELOW/LEFT) -- DONOR_ROOM_NOT_REALIZED
- **placement** BATHROOM_0 (donor ABOVE/RIGHT): realized BATH_1 is FRONT/RIGHT -- GUILLOTINE_IMPOSSIBLE
- **placement** BATHROOM_1 (donor ABOVE/LEFT): realized BATH_2 is REAR/RIGHT -- GUILLOTINE_IMPOSSIBLE
- **placement** BATHROOM_2 (donor BELOW/LEFT) -- DONOR_ROOM_NOT_REALIZED
- **placement** BATHROOM_3 (donor BELOW/RIGHT) -- DONOR_ROOM_NOT_REALIZED
- **clusters** public: split across 2 disconnected groups -- GUILLOTINE_IMPOSSIBLE
- **clusters** private: BEDROOM_3 -- DONOR_ROOM_NOT_REALIZED
- **wet_core_groups** group ['BATHROOM_2']: ['BATHROOM_2'] not realized -- DONOR_ROOM_NOT_REALIZED
- **wet_core_groups** group ['BATHROOM_3']: ['BATHROOM_3'] not realized -- DONOR_ROOM_NOT_REALIZED
- **entrance_relationship** donor entrance -> TO_LIVING, realized entrance -> TO_HALL -- GUILLOTINE_IMPOSSIBLE
- **room_proportions** BEDROOM_2/BEDROOM_3: donor share=0.849, realized share=1.000 -- BUDGET
- **footprint_relationships** aspect_ratio: donor=1.826, realized=2.123 -- GUILLOTINE_IMPOSSIBLE
- **footprint_relationships** fill_ratio: donor=0.733, realized=1.000 -- GUILLOTINE_IMPOSSIBLE

### PRESERVED / LOST -- concept-1 (donor 1996)

| fact class | preserved | total | ratio |
|---|---|---|---|
| adjacency | 2 | 12 | 17% |
| access | 3 | 4 | 75% |
| exposure | 0 | 0 | n/a |
| placement | 0 | 8 | 0% |
| clusters | 1 | 2 | 50% |
| wet_core_groups | 0 | 2 | 0% |
| entrance_relationship | 0 | 1 | 0% |
| room_proportions | 6 | 7 | 86% |
| footprint_relationships | 1 | 2 | 50% |

LOST facts:

- **adjacency** BATHROOM_0-BATHROOM_1 (realized BATH_1/BATH_2 do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** BATHROOM_0-BEDROOM_2 (realized BATH_1/BEDROOM_3 do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** BATHROOM_0-LIVING_0 (realized BATH_1/LIVING do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** BATHROOM_1-BEDROOM_2 (realized BATH_2/BEDROOM_3 do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** BATHROOM_2-BEDROOM_0 -- DONOR_ROOM_NOT_REALIZED
- **adjacency** BATHROOM_2-BEDROOM_1 -- DONOR_ROOM_NOT_REALIZED
- **adjacency** BEDROOM_0-LIVING_0 (realized BEDROOM_1/LIVING do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** BEDROOM_1-LIVING_0 (realized BEDROOM_2/LIVING do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** BEDROOM_2-LIVING_0 (realized BEDROOM_3/LIVING do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** KITCHEN_0-LIVING_0 (realized KITCHEN/LIVING do not touch) -- GUILLOTINE_IMPOSSIBLE
- **access** BATHROOM_2-BEDROOM_1 (DOOR) -- DONOR_ROOM_NOT_REALIZED
- **placement** LIVING_0 (donor FRONT/RIGHT): realized LIVING is FRONT/LEFT -- GUILLOTINE_IMPOSSIBLE
- **placement** KITCHEN_0 (donor FRONT/LEFT): realized KITCHEN is REAR/LEFT -- GUILLOTINE_IMPOSSIBLE
- **placement** BEDROOM_0 (donor REAR/RIGHT): realized BEDROOM_1 is FRONT/RIGHT -- GUILLOTINE_IMPOSSIBLE
- **placement** BEDROOM_1 (donor REAR/RIGHT): realized BEDROOM_2 is FRONT/RIGHT -- GUILLOTINE_IMPOSSIBLE
- **placement** BEDROOM_2 (donor REAR/LEFT): realized BEDROOM_3 is REAR/RIGHT -- GUILLOTINE_IMPOSSIBLE
- **placement** BATHROOM_0 (donor REAR/LEFT): realized BATH_1 is FRONT/RIGHT -- GUILLOTINE_IMPOSSIBLE
- **placement** BATHROOM_1 (donor REAR/LEFT): realized BATH_2 is REAR/RIGHT -- GUILLOTINE_IMPOSSIBLE
- **placement** BATHROOM_2 (donor REAR/RIGHT) -- DONOR_ROOM_NOT_REALIZED
- **clusters** public: split across 2 disconnected groups -- GUILLOTINE_IMPOSSIBLE
- **wet_core_groups** group ['BATHROOM_0', 'BATHROOM_1']: realized zones ['BATH_1', 'BATH_2'] span different wet-core clusters -- GUILLOTINE_IMPOSSIBLE
- **wet_core_groups** group ['BATHROOM_2']: ['BATHROOM_2'] not realized -- DONOR_ROOM_NOT_REALIZED
- **entrance_relationship** donor entrance -> TO_LIVING, realized entrance -> TO_HALL -- GUILLOTINE_IMPOSSIBLE
- **room_proportions** BEDROOM_0/BEDROOM_1: donor share=0.771, realized share=1.000 -- BUDGET
- **footprint_relationships** fill_ratio: donor=0.736, realized=1.000 -- GUILLOTINE_IMPOSSIBLE

## Layout collapse (identical realized geometry from different donors)

- concept-0, concept-1 realized to BYTE-IDENTICAL geometry. Root cause (measured, see `tests/architectural_brain/test_realization_intent.py::test_two_donors_for_one_brief_realize_to_different_layouts`, xfail-documented): `realize.py`'s own compiler selects each private column's WIDTH from `ROOM_TEMPLATES`' [min, max] area bound only -- identical for both donors, since it comes from the brief's own authoritative room counts (the owner's explicit requirement), never from the donor plan. Only within THAT already-fixed width does `RealizationIntent.room_proportions`' donor-specific TARGET area get a say (`geometry_core.engine.assign`'s closest-to-target picker) -- here both donors' own proportional targets fall below the width-driven minimum feasible height, so both saturate at the same minimum regardless of their different donors.

## Measurements table (realized-and-ok plans, plus the current baseline)

| plan | class | gross_area_m2 | net_area_m2 | m3_circulation_share | m4_hall_door_count | m4_hall_aspect_median | m5_wet_adjacency_ratio | m6_public_zone_contiguous | wet_core_cluster_count | entrance_opens_into |
|---|---|---|---|---|---|---|---|---|---|---|
| current | FRONT_BAND | 189.8 | 172.31 | 0.08630136986301369 | 8 | 8.357142857142858 | 0.6666666666666666 | False | 2 | LIVING |
| brain-A (concept-0) | SPINE | 170.05 | 152.55 | 0.1787709497206704 | 9 | 5.9375 | 0.6666666666666666 | True | 2 | HALL_1 |
| brain-B (concept-1) | SPINE | 170.05 | 152.55 | 0.1787709497206704 | 9 | 5.9375 | 0.6666666666666666 | True | 2 | HALL_1 |
