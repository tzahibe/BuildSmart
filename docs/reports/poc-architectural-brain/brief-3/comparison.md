# Comparison -- brief-3

## Current engine baseline
REFUSED (outcome=INSUFFICIENT_RECTANGULAR_CAPACITY): FRONT_PUBLIC_BAND/ROOM_SHAPE_INFEASIBLE: BEDROOM_1 at 5.50 m wide in the rear west column has no depth that keeps its 2.5 aspect ratio and 2.6 m short side under its 14 m2 preferred maximum (needs 2.60 m, allowed 2.55 m); re-partitioned: BEDROOM_1 would be 5.25 x 2.70 m = 14.2 m2 in the rear west column, past its 14 m2 preferred maximum; SPINE_PUBLIC_PRIVATE/COLUMN_DEPTH_EXCEEDED: east column needs 18.06 m of depth for its rows' floors but has 10.50 m [MASTER 3.20 (shape floor, area wanted 2.39); TOILET_1+BATH_1 1.86 (shape floor, area wanted 1.75); BEDROOM_1 2.80 (shape floor, area wanted 1.96); BEDROOM_2 2.80 (shape floor, area wanted 1.96); BEDROOM_3 2.80 (shape floor, area wanted 1.96); BEDROOM_4 2.80 (shape floor, area wanted 1.96); BATH_2 1.80 (shape floor, area wanted 1.09)]; SPINE_DOUBLE_LOADED/ROOM_ABOVE_MAXIMUM_AREA: BEDROOM_1 would be 5.30 x 2.70 m = 14.3 m2 in the west column, past its 14 m2 preferred maximum; SPINE_SERVICE_CLUSTER/COLUMN_DEPTH_EXCEEDED: east column needs 17.03 m of depth for its rows' floors but has 10.50 m [BEDROOM_1 3.47 (shape floor, area wanted 3.27); BEDROOM_2 3.47 (shape floor, area wanted 3.27); BEDROOM_3 3.47 (shape floor, area wanted 3.27); BEDROOM_4 3.47 (shape floor, area wanted 3.27); TOILET_1 1.30 (shape floor, area wanted 1.12); BATH_2 1.84 (shape floor, area wanted 1.82)]; SPINE_DOUBLE_LOADED/COLUMN_DEPTH_EXCEEDED: west column needs 15.59 m of depth for its rows' floors but has 10.50 m [LIVING 3.57 (shape floor, area wanted 3.37); KITCHEN 2.60 (shape floor, area wanted 1.99); BEDROOM_1 2.80 (shape floor, area wanted 1.89); BEDROOM_2 2.80 (shape floor, area wanted 1.89); BATH_1+MASTER 3.83 (shape floor, area wanted 3.37)]; re-partitioned: west column needs 15.59 m of depth for its rows' floors but has 10.50 m [LIVING 3.57 (shape floor, area wanted 3.37); KITCHEN 2.60 (shape floor, area wanted 1.99); BEDROOM_1 2.80 (shape floor, area wanted 1.89); BEDROOM_2 2.80 (shape floor, area wanted 1.89); BATH_1+MASTER 3.83 (shape floor, area wanted 3.37)]; BRANCHED_TWO_STACK/COLUMN_DEPTH_EXCEEDED: west column needs 10.85 m of depth for its rows' floors but has 10.50 m [LIVING 4.91 (shape floor, area wanted 4.71); KITCHEN 2.85 (shape floor, area wanted 2.78); TOILET_1 1.30 (shape floor, area wanted 0.90); BATH_2 1.80 (shape floor, area wanted 1.47)]; HUB_PRIVATE_WING/ACCESS_DEGREE_EXCEEDED: 7 rooms need a door on the lobby but it seats 6 (two rooms on each flank, two in the foot band); MULTI_WING_SPLIT/NO_SEAM_ALIGNMENT: the second wing (21.0 x 4.0 m) sits north or south of the primary; this parti runs its hall along the seam, and a hall along the street axis is not authored yet

## Brain alternatives

| concept | declared class | outcome | realized class | ok | time (s) |
|---|---|---|---|---|---|
| concept-0 (-) | OTHER | REFUSED | - | - | 15.9 |
| concept-1 (-) | FRONT_BAND | REFUSED | - | - | 15.8 |
| concept-5 (A) | TWO_WING | REALIZED | TWO_WING | True | 0.3 |

## Compiler probes (Issue #110): HUB_LOBBY / BRANCHED, independent of retrieval

`concept_compilers.compile_hub_lobby`/`compile_branched` tried directly against this brief's own authoritative programme/site (`realize_compiled_topology`) -- never gated on whether a retrieved donor reference happened to declare that class (see `demo.py`'s own module docstring).

| class | outcome | realized class | ok | time (s) |
|---|---|---|---|---|
| BRANCHED | REFUSED | - | - | 0.2 |
| HUB_LOBBY | REFUSED | - | - | 0.2 |

## What adaptation changed

### concept-0
- **RESIZE_ROOMS**: total 190.7 m2 across 10 donor rooms -> total 102.0 m2 after per-type target resizing (each room type's aggregate resized to its own architectural target area, independently -- never a single scale factor applied to every room -- and each individual room's OWN share of that aggregate carries the donor's own proportion forward, so a different donor with a different internal size spread adapts to different individual room areas even at the same aggregate target)
- **BEDROOM_COUNT_ADJUST**: 4 bedroom(s) -> 5 bedroom(s) (brief requires 5 bedroom(s); added 1 to match, each at its own target area)

### concept-1
- **RESIZE_ROOMS**: total 215.3 m2 across 8 donor rooms -> total 85.0 m2 after per-type target resizing (each room type's aggregate resized to its own architectural target area, independently -- never a single scale factor applied to every room -- and each individual room's OWN share of that aggregate carries the donor's own proportion forward, so a different donor with a different internal size spread adapts to different individual room areas even at the same aggregate target)
- **BEDROOM_COUNT_ADJUST**: 3 bedroom(s) -> 5 bedroom(s) (brief requires 5 bedroom(s); added 2 to match, each at its own target area)

### concept-5
- **RESIZE_ROOMS**: total 143.6 m2 across 8 donor rooms -> total 85.0 m2 after per-type target resizing (each room type's aggregate resized to its own architectural target area, independently -- never a single scale factor applied to every room -- and each individual room's OWN share of that aggregate carries the donor's own proportion forward, so a different donor with a different internal size spread adapts to different individual room areas even at the same aggregate target)
- **BEDROOM_COUNT_ADJUST**: 3 bedroom(s) -> 5 bedroom(s) (brief requires 5 bedroom(s); added 2 to match, each at its own target area)

## Refusal / rejection reasons

- concept-0: REFUSED -- no footprint size solved for the SPINE template: depth 10.0 m / foyer depth 3.0 m: no width combination both fit and solved
- concept-1: REFUSED -- no footprint size solved for the SPINE template: depth 10.0 m / foyer depth 3.0 m: no width combination both fit and solved
- compiled-branched: REFUSED -- BRANCHED compiler (concept_compilers.py) declined: compile_branched supports exactly 4 bedrooms without a safe room, not 5
- compiled-hub_lobby: REFUSED -- HUB_LOBBY compiler (concept_compilers.py) declined: compile_hub_lobby supports exactly 2 bedrooms, not 5

## ATTEMPTED / REALIZED / REFUSED by circulation class (Issue #110)

| circulation class | attempted | realized (ok, concept) | refused (reason) |
|---|---|---|---|
| SPINE | yes | - | - |
  - Note: SPINE was attempted (a synthesized concept routed to it) but never REALIZED as SPINE -- its own two-hall-segment split always satisfies the merged BRANCHED classifier instead (see the BRANCHED row/note below).
| TWO_WING | yes | concept-5 | - |
| HUB_LOBBY | yes | - | compiled-hub_lobby: HUB_LOBBY compiler (concept_compilers.py) declined: compile_hub_lobby supports exactly 2 bedrooms, not 5 |
| BRANCHED | yes | - | compiled-branched: BRANCHED compiler (concept_compilers.py) declined: compile_branched supports exactly 4 bedrooms without a safe room, not 5 |

## RealizationIntent preservation (Issue #109 Track 3)

### PRESERVED / LOST -- concept-5 (donor 681)

| fact class | preserved | total | ratio |
|---|---|---|---|
| adjacency | 1 | 13 | 8% |
| access | 5 | 6 | 83% |
| exposure | 0 | 0 | n/a |
| placement | 0 | 8 | 0% |
| clusters | 0 | 2 | 0% |
| wet_core_groups | 1 | 2 | 50% |
| entrance_relationship | 0 | 1 | 0% |
| room_proportions | 2 | 7 | 29% |
| footprint_relationships | 1 | 2 | 50% |

LOST facts:

- **adjacency** BATHROOM_0-BEDROOM_1 (realized BATH_1/BEDROOM_2 do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** BATHROOM_0-BEDROOM_2 (realized BATH_1/BEDROOM_3 do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** BATHROOM_1-BATHROOM_2 -- DONOR_ROOM_NOT_REALIZED
- **adjacency** BATHROOM_1-BEDROOM_2 (realized BATH_2/BEDROOM_3 do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** BATHROOM_1-LIVING_0 (realized BATH_2/LIVING do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** BATHROOM_2-BEDROOM_2 -- DONOR_ROOM_NOT_REALIZED
- **adjacency** BATHROOM_2-LIVING_0 -- DONOR_ROOM_NOT_REALIZED
- **adjacency** BEDROOM_0-LIVING_0 (realized BEDROOM_1/LIVING do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** BEDROOM_1-BEDROOM_2 (realized BEDROOM_2/BEDROOM_3 do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** BEDROOM_1-LIVING_0 (realized BEDROOM_2/LIVING do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** BEDROOM_2-LIVING_0 (realized BEDROOM_3/LIVING do not touch) -- GUILLOTINE_IMPOSSIBLE
- **adjacency** KITCHEN_0-LIVING_0 (realized KITCHEN/LIVING do not touch) -- GUILLOTINE_IMPOSSIBLE
- **access** BATHROOM_2-LIVING_0 (DOOR) -- DONOR_ROOM_NOT_REALIZED
- **placement** LIVING_0 (donor BELOW/RIGHT): realized LIVING is FRONT/RIGHT -- GUILLOTINE_IMPOSSIBLE
- **placement** KITCHEN_0 (donor BELOW/RIGHT): realized KITCHEN is FRONT/LEFT -- GUILLOTINE_IMPOSSIBLE
- **placement** BEDROOM_0 (donor ABOVE/RIGHT): realized BEDROOM_1 is REAR/RIGHT -- GUILLOTINE_IMPOSSIBLE
- **placement** BEDROOM_1 (donor ABOVE/LEFT): realized BEDROOM_2 is REAR/RIGHT -- GUILLOTINE_IMPOSSIBLE
- **placement** BEDROOM_2 (donor ABOVE/LEFT): realized BEDROOM_3 is FRONT/RIGHT -- GUILLOTINE_IMPOSSIBLE
- **placement** BATHROOM_0 (donor ABOVE/LEFT): realized BATH_1 is REAR/RIGHT -- GUILLOTINE_IMPOSSIBLE
- **placement** BATHROOM_1 (donor BELOW/LEFT): realized BATH_2 is REAR/RIGHT -- GUILLOTINE_IMPOSSIBLE
- **placement** BATHROOM_2 (donor BELOW/LEFT) -- DONOR_ROOM_NOT_REALIZED
- **clusters** public: split across 2 disconnected groups -- GUILLOTINE_IMPOSSIBLE
- **clusters** private: split across 2 disconnected groups -- GUILLOTINE_IMPOSSIBLE
- **wet_core_groups** group ['BATHROOM_1', 'BATHROOM_2']: ['BATHROOM_2'] not realized -- DONOR_ROOM_NOT_REALIZED
- **entrance_relationship** donor entrance -> TO_LIVING, realized entrance -> TO_HALL -- GUILLOTINE_IMPOSSIBLE
- **room_proportions** BEDROOM_0/BEDROOM_1: donor share=0.691, realized share=1.043 -- BUDGET
- **room_proportions** BEDROOM_1/BEDROOM_2: donor share=0.824, realized share=1.043 -- BUDGET
- **room_proportions** BEDROOM_2/BEDROOM_3: donor share=1.486, realized share=0.913 -- BUDGET
- **room_proportions** BATHROOM_0/BATH_1: donor share=0.962, realized share=1.216 -- BUDGET
- **room_proportions** BATHROOM_1/BATH_2: donor share=1.014, realized share=0.784 -- BUDGET
- **footprint_relationships** aspect_ratio: donor=1.824, realized=1.069 -- GUILLOTINE_IMPOSSIBLE

## Measurements table (realized-and-ok plans, plus the current baseline)

| plan | class | gross_area_m2 | net_area_m2 | m3_circulation_share | m4_hall_door_count | m4_hall_aspect_median | m5_wet_adjacency_ratio | m6_public_zone_contiguous | wet_core_cluster_count | entrance_opens_into |
|---|---|---|---|---|---|---|---|---|---|---|
| brain-A (concept-5) | TWO_WING | 154.35 | 140.22 | 0.22076449627470038 | 9 | 3.085106382978723 | 0.6666666666666666 | True | 2 | HALL_A |
