# #142D — Exact per-cell band sizing: stage counts (generated)

Pipeline per witness: `exact topology witness -> exact per-cell sizing (oracle) -> existing realization -> unchanged validators`. Counts are over ALL witnesses examined, never only the best one. 'sizing' = the realizer's own `_build_grid_wing` accepted the injected sizing (its area/short-side re-checks after 5 cm rounding); 'realization' = reached `validate`; 'validators' = unchanged `validate` PASS.

## PRODUCTION semantics (oracle enforces exactly `_build_grid_wing`: gross area, short side + 0.3 m)

| brief | n | m | family complete | witnesses examined | oracle FEASIBLE / INFEASIBLE / UNKNOWN | sizing pass | realization pass | validator pass | category | dominant rejections |
|---|---|---|---|---|---|---|---|---|---|---|
| B01 | 5 | 6 | yes | 68 | 48 / 20 / 0 | 46 | 34 | 12 | PASS | SIZING: AREA_INFEASIBLE (2); REALIZATION: NO_ENTRANCE (12); VALIDATORS: VALIDATION_FAILED C26+C3 (9), VALIDATION_FAILED C20+C3 (6), VALIDATION_FAILED C26 (5), VALIDATION_FAILED C26+C5 (2) |
| B04 | 8 | 9 | no | 904 | 272 / 632 / 0 | 178 | 90 | 0 | DOWNSTREAM_CONSTRAINT | SIZING: AREA_INFEASIBLE (93), SHORT_SIDE_INFEASIBLE (1); REALIZATION: NO_ENTRANCE (88); VALIDATORS: VALIDATION_FAILED C26+C3+C4 (40), VALIDATION_FAILED C3+C4 (14), VALIDATION_FAILED C3+C4+C5 (8), VALIDATION_FAILED C24+C26+C3+C4+C5 (8), VALIDATION_FAILED C25+C4 |
| B05 | 7 | 9 | no | 679 | 506 / 173 / 0 | 406 | 255 | 2 | PASS | SIZING: AREA_INFEASIBLE (100); REALIZATION: NO_ENTRANCE (151); VALIDATORS: VALIDATION_FAILED C17+C24+C3+C5 (110), VALIDATION_FAILED C26+C3 (85), VALIDATION_FAILED C20+C3 (14), VALIDATION_FAILED C24+C3+C5 (14), VALIDATION_FAILED C19+C24+C3+C5+C8 (7), VALIDATION |
| B06 | 8 | 11 | yes | 156 | 0 / 156 / 0 | 0 | 0 | 0 | BAND_GEOMETRY_LIMIT |  |
| B07 | 9 | 12 | yes | 4752 | 0 / 4752 / 0 | 0 | 0 | 0 | BAND_GEOMETRY_LIMIT |  |
| B08 | 8 | 10 | no | 694 | 238 / 456 / 0 | 159 | 66 | 10 | PASS | SIZING: AREA_INFEASIBLE (75), SHORT_SIDE_INFEASIBLE (4); REALIZATION: NO_ENTRANCE (93); VALIDATORS: VALIDATION_FAILED C3 (25), VALIDATION_FAILED C3+C5 (12), VALIDATION_FAILED C5 (6), VALIDATION_FAILED C24+C3+C5 (3), VALIDATION_FAILED C19+C20+C24+C3+C5 (3), VAL |
| B09 | 9 | 14 | yes | 180 | 4 / 176 / 0 | 4 | 2 | 0 | DOWNSTREAM_CONSTRAINT | REALIZATION: NO_ENTRANCE (2); VALIDATORS: VALIDATION_FAILED C19+C20+C3+C5+C8 (2) |
| B11 | 11 | 13 | no | 816 | 88 / 728 / 0 | 61 | 0 | 0 | DOWNSTREAM_CONSTRAINT | SIZING: AREA_INFEASIBLE (27); REALIZATION: NO_ENTRANCE (61) |
| B12 | 10 | 13 | no | 750 | 110 / 640 / 0 | 32 | 4 | 0 | DOWNSTREAM_CONSTRAINT | SIZING: AREA_INFEASIBLE (78); REALIZATION: NO_ENTRANCE (28); VALIDATORS: VALIDATION_FAILED C19+C20+C24+C3+C5 (3), VALIDATION_FAILED C1+C19+C20+C24+C3+C5 (1) |
| B13 | 10 | 12 | no | 750 | 220 / 530 / 0 | 200 | 145 | 21 | PASS | SIZING: AREA_INFEASIBLE (15), SHORT_SIDE_INFEASIBLE (5); REALIZATION: NO_ENTRANCE (55); VALIDATORS: VALIDATION_FAILED C19+C20+C3+C8 (71), VALIDATION_FAILED C20+C3 (10), VALIDATION_FAILED C19+C8 (9), VALIDATION_FAILED C5 (8), VALIDATION_FAILED C19+C3+C31+C8 (6) |
| B17 | 12 | 13 | no | 1000 | 17 / 983 / 0 | 2 | 2 | 0 | DOWNSTREAM_CONSTRAINT | SIZING: AREA_INFEASIBLE (15); VALIDATORS: VALIDATION_FAILED C24+C3+C5 (2) |
| B18 | 13 | 14 | no | 3000 | 760 / 2240 / 0 | 299 | 163 | 0 | DOWNSTREAM_CONSTRAINT | SIZING: AREA_INFEASIBLE (461); REALIZATION: NO_ENTRANCE (136); VALIDATORS: VALIDATION_FAILED C24+C3+C4+C5 (127), VALIDATION_FAILED C17+C24+C3+C4+C5 (33), VALIDATION_FAILED C19+C24+C3+C4+C5 (2), VALIDATION_FAILED C24+C4+C5 (1) |
| B20 | 10 | 11 | no | 900 | 288 / 612 / 0 | 213 | 9 | 0 | DOWNSTREAM_CONSTRAINT | SIZING: AREA_INFEASIBLE (71), SHORT_SIDE_INFEASIBLE (4); REALIZATION: NO_ENTRANCE (204); VALIDATORS: VALIDATION_FAILED C20+C24+C3+C4+C5 (7), VALIDATION_FAILED C19+C20+C3+C4+C5 (2) |

**Briefs (denominator 13):** oracle finds >= 1 feasible sizing for 11; realizer sizing accepts >= 1 for 11; realization passes for 10; **validators PASS for 4/13**.

## CORRECTED semantics counterfactual A (oracle enforces NET area/short side with the real insets, plus max aspect; the production GROSS gate left in place)

| brief | n | m | family complete | witnesses examined | oracle FEASIBLE / INFEASIBLE / UNKNOWN | sizing pass | realization pass | validator pass | category | dominant rejections |
|---|---|---|---|---|---|---|---|---|---|---|
| B01 | 5 | 6 | yes | 68 | 56 / 12 / 0 | 4 | 4 | 4 | PASS | SIZING: AREA_INFEASIBLE (48), SHORT_SIDE_INFEASIBLE (4) |
| B04 | 8 | 9 | no | 904 | 331 / 573 / 0 | 0 | 0 | 0 | REJECTED_BY_PRODUCTION_GROSS_GATE (net-feasible sizing, `_build_grid_wing` AREA_INFEASIBLE) | SIZING: AREA_INFEASIBLE (255), SHORT_SIDE_INFEASIBLE (76) |
| B05 | 7 | 9 | no | 679 | 501 / 178 / 0 | 0 | 0 | 0 | REJECTED_BY_PRODUCTION_GROSS_GATE (net-feasible sizing, `_build_grid_wing` AREA_INFEASIBLE) | SIZING: AREA_INFEASIBLE (469), SHORT_SIDE_INFEASIBLE (32) |
| B06 | 8 | 11 | yes | 156 | 0 / 156 / 0 | 0 | 0 | 0 | BAND_GEOMETRY_LIMIT |  |
| B07 | 9 | 12 | yes | 4752 | 24 / 4728 / 0 | 0 | 0 | 0 | REJECTED_BY_PRODUCTION_GROSS_GATE (net-feasible sizing, `_build_grid_wing` AREA_INFEASIBLE) | SIZING: SHORT_SIDE_INFEASIBLE (12), AREA_INFEASIBLE (12) |
| B08 | 8 | 10 | no | 694 | 277 / 417 / 0 | 6 | 6 | 0 | DOWNSTREAM_CONSTRAINT | SIZING: AREA_INFEASIBLE (193), SHORT_SIDE_INFEASIBLE (78); VALIDATORS: VALIDATION_FAILED C5 (6) |
| B09 | 9 | 14 | yes | 180 | 28 / 152 / 0 | 0 | 0 | 0 | REJECTED_BY_PRODUCTION_GROSS_GATE (net-feasible sizing, `_build_grid_wing` AREA_INFEASIBLE) | SIZING: AREA_INFEASIBLE (20), SHORT_SIDE_INFEASIBLE (8) |
| B11 | 11 | 13 | no | 816 | 80 / 736 / 0 | 0 | 0 | 0 | REJECTED_BY_PRODUCTION_GROSS_GATE (net-feasible sizing, `_build_grid_wing` AREA_INFEASIBLE) | SIZING: AREA_INFEASIBLE (61), SHORT_SIDE_INFEASIBLE (19) |
| B12 | 10 | 13 | no | 750 | 179 / 571 / 0 | 0 | 0 | 0 | REJECTED_BY_PRODUCTION_GROSS_GATE (net-feasible sizing, `_build_grid_wing` AREA_INFEASIBLE) | SIZING: AREA_INFEASIBLE (127), SHORT_SIDE_INFEASIBLE (52) |
| B13 | 10 | 12 | no | 750 | 193 / 557 / 0 | 15 | 4 | 2 | PASS | SIZING: AREA_INFEASIBLE (133), SHORT_SIDE_INFEASIBLE (45); REALIZATION: NO_ENTRANCE (11); VALIDATORS: VALIDATION_FAILED C19+C8 (2) |
| B17 | 12 | 13 | no | 1000 | 51 / 949 / 0 | 0 | 0 | 0 | REJECTED_BY_PRODUCTION_GROSS_GATE (net-feasible sizing, `_build_grid_wing` AREA_INFEASIBLE) | SIZING: SHORT_SIDE_INFEASIBLE (29), AREA_INFEASIBLE (22) |
| B20 | 10 | 11 | no | 900 | 292 / 608 / 0 | 0 | 0 | 0 | REJECTED_BY_PRODUCTION_GROSS_GATE (net-feasible sizing, `_build_grid_wing` AREA_INFEASIBLE) | SIZING: AREA_INFEASIBLE (182), SHORT_SIDE_INFEASIBLE (110) |

**Briefs (denominator 12):** oracle finds >= 1 feasible sizing for 11; realizer sizing accepts >= 1 for 3; realization passes for 3; **validators PASS for 2/12**.

## CORRECTED semantics counterfactual B (as A, with `_build_grid_wing`'s area gate made NET-consistent for the experiment only; validators unchanged)

| brief | n | m | family complete | witnesses examined | oracle FEASIBLE / INFEASIBLE / UNKNOWN | sizing pass | realization pass | validator pass | category | dominant rejections |
|---|---|---|---|---|---|---|---|---|---|---|
| B01 | 5 | 6 | yes | 68 | 56 / 12 / 0 | 56 | 34 | 18 | PASS | REALIZATION: NO_ENTRANCE (22); VALIDATORS: VALIDATION_FAILED C26 (12), VALIDATION_FAILED C26+C5 (4) |
| B04 | 8 | 9 | no | 904 | 331 / 573 / 0 | 331 | 158 | 0 | DOWNSTREAM_CONSTRAINT | REALIZATION: NO_ENTRANCE (173); VALIDATORS: VALIDATION_FAILED C26+C4 (42), VALIDATION_FAILED C26+C3+C4 (26), VALIDATION_FAILED C4 (17), VALIDATION_FAILED C4+C5 (13), VALIDATION_FAILED C19+C25+C4+C5+C8 (8), VALIDATION_FAILED C17+C24+C26+C4+C5 (7) |
| B05 | 7 | 9 | no | 679 | 501 / 178 / 0 | 501 | 297 | 18 | PASS | REALIZATION: NO_ENTRANCE (204); VALIDATORS: VALIDATION_FAILED C17+C24+C5 (130), VALIDATION_FAILED C26 (84), VALIDATION_FAILED C17+C24+C3+C5 (18), VALIDATION_FAILED C24+C5 (16), VALIDATION_FAILED C26+C3 (8), VALIDATION_FAILED C17+C19+C24+C5+C8 (7) |
| B06 | 8 | 11 | yes | 156 | 0 / 156 / 0 | 0 | 0 | 0 | BAND_GEOMETRY_LIMIT |  |
| B07 | 9 | 12 | yes | 4752 | 24 / 4728 / 0 | 24 | 6 | 0 | DOWNSTREAM_CONSTRAINT | REALIZATION: NO_ENTRANCE (18); VALIDATORS: VALIDATION_FAILED C19+C24+C3+C4+C5 (6) |
| B08 | 8 | 10 | no | 694 | 277 / 417 / 0 | 277 | 80 | 23 | PASS | REALIZATION: NO_ENTRANCE (197); VALIDATORS: VALIDATION_FAILED C5 (29), VALIDATION_FAILED C24+C5 (12), VALIDATION_FAILED C3 (5), VALIDATION_FAILED C19+C24+C5+C8 (4), VALIDATION_FAILED C19+C5+C8 (3), VALIDATION_FAILED C19+C3+C5+C8 (2) |
| B09 | 9 | 14 | yes | 180 | 28 / 152 / 0 | 28 | 4 | 0 | DOWNSTREAM_CONSTRAINT | REALIZATION: NO_ENTRANCE (24); VALIDATORS: VALIDATION_FAILED C19+C5+C8 (2), VALIDATION_FAILED C19+C3+C5+C8 (1), VALIDATION_FAILED C19+C20+C3+C5+C8 (1) |
| B11 | 11 | 13 | no | 816 | 80 / 736 / 0 | 80 | 2 | 0 | DOWNSTREAM_CONSTRAINT | REALIZATION: NO_ENTRANCE (78); VALIDATORS: VALIDATION_FAILED C24+C4+C5 (1), VALIDATION_FAILED C24+C3+C4+C5 (1) |
| B12 | 10 | 13 | no | 750 | 179 / 571 / 0 | 179 | 32 | 0 | DOWNSTREAM_CONSTRAINT | REALIZATION: NO_ENTRANCE (147); VALIDATORS: VALIDATION_FAILED C17+C19+C24+C5+C8 (16), VALIDATION_FAILED C19+C24+C3+C5+C8 (15), VALIDATION_FAILED C19+C20+C24+C3+C5 (1) |
| B13 | 10 | 12 | no | 750 | 193 / 557 / 0 | 193 | 111 | 38 | PASS | REALIZATION: NO_ENTRANCE (82); VALIDATORS: VALIDATION_FAILED C19+C8 (22), VALIDATION_FAILED C19+C3+C8 (20), VALIDATION_FAILED C5 (8), VALIDATION_FAILED C19+C31+C8 (7), VALIDATION_FAILED C19+C24+C31+C5+C8 (5), VALIDATION_FAILED C3 (3) |
| B17 | 12 | 13 | no | 1000 | 51 / 949 / 0 | 51 | 38 | 0 | DOWNSTREAM_CONSTRAINT | REALIZATION: NO_ENTRANCE (13); VALIDATORS: VALIDATION_FAILED C24+C5 (15), VALIDATION_FAILED C17+C24+C5 (9), VALIDATION_FAILED C19+C24+C3+C5+C8 (6), VALIDATION_FAILED C24+C3+C5 (6), VALIDATION_FAILED C17+C19+C24+C5+C8 (2) |
| B18 | 13 | 14 | no | 3000 | 1440 / 1560 / 0 | 1440 | 646 | 0 | DOWNSTREAM_CONSTRAINT | REALIZATION: NO_ENTRANCE (794); VALIDATORS: VALIDATION_FAILED C24+C3+C4+C5 (276), VALIDATION_FAILED C24+C4+C5 (215), VALIDATION_FAILED C17+C24+C3+C4+C5 (65), VALIDATION_FAILED C17+C24+C4+C5 (47), VALIDATION_FAILED C21+C24+C3+C4+C5 (22), VALIDATION_FAILED C20+C |
| B20 | 10 | 11 | no | 900 | 292 / 608 / 0 | 292 | 36 | 0 | DOWNSTREAM_CONSTRAINT | REALIZATION: NO_ENTRANCE (256); VALIDATORS: VALIDATION_FAILED C19+C24+C4+C5+C8 (23), VALIDATION_FAILED C19+C24+C3+C4+C5 (7), VALIDATION_FAILED C20+C21+C3+C4+C5 (4), VALIDATION_FAILED C19+C25+C4+C5+C8 (2) |

**Briefs (denominator 13):** oracle finds >= 1 feasible sizing for 12; realizer sizing accepts >= 1 for 12; realization passes for 12; **validators PASS for 4/13**.

## §9 — entrance / access / exposure properties of witnesses (production semantics; measured, not enforced)

Flags are topology-level: `entrance_ok` = a HALL/CIRCULATION/LIVING cell in the street band (row 0); `access_ok` = every room touches >= 1 room it may legally be entered from (`edge_role_pair_allowed`, wet rooms as `_filter_wet_room_access`); `exposure_ok` = every REQUIRED_EXTERIOR-role room touches the envelope. 'all three' is the counterfactual selection; its downstream pass rate is reported next to the unselected rate.

| brief | witnesses | entrance_ok | access_ok | exposure_ok | all three | sized (all / all-three) | realized (all / all-three) | validators PASS (all / all-three) | top validator failures among sized witnesses |
|---|---|---|---|---|---|---|---|---|---|
| B01 | 68 | 40 | 68 | 60 | 38 | 46 / 34 | 34 / 34 | 12 / 12 | C26+C3 (9), C20+C3 (6), C26 (5), C26+C5 (2) |
| B04 | 904 | 389 | 904 | 576 | 225 | 178 / 89 | 90 / 89 | 0 / 0 | C26+C3+C4 (40), C3+C4 (14), C3+C4+C5 (8), C24+C26+C3+C4+C5 (8) |
| B05 | 679 | 361 | 679 | 575 | 324 | 406 / 238 | 255 / 238 | 2 / 2 | C17+C24+C3+C5 (110), C26+C3 (85), C20+C3 (14), C24+C3+C5 (14) |
| B06 | 156 | 52 | 156 | 0 | 0 | 0 / 0 | 0 / 0 | 0 / 0 |  |
| B07 | 4752 | 1716 | 4752 | 0 | 0 | 0 / 0 | 0 / 0 | 0 / 0 |  |
| B08 | 694 | 165 | 694 | 315 | 126 | 159 / 59 | 66 / 59 | 10 / 10 | C3 (25), C3+C5 (12), C5 (6), C24+C3+C5 (3) |
| B09 | 180 | 76 | 180 | 0 | 0 | 4 / 0 | 2 / 0 | 0 / 0 | C19+C20+C3+C5+C8 (2) |
| B11 | 816 | 166 | 816 | 320 | 143 | 61 / 0 | 0 / 0 | 0 / 0 |  |
| B12 | 750 | 157 | 0 | 0 | 0 | 32 / 0 | 4 / 0 | 0 / 0 | C19+C20+C24+C3+C5 (3), C1+C19+C20+C24+C3+C5 (1) |
| B13 | 750 | 403 | 750 | 98 | 61 | 200 / 43 | 145 / 43 | 21 / 21 | C19+C20+C3+C8 (71), C20+C3 (10), C19+C8 (9), C5 (8) |
| B17 | 1000 | 211 | 0 | 251 | 0 | 2 / 0 | 2 / 0 | 0 / 0 | C24+C3+C5 (2) |
| B18 | 3000 | 1138 | 636 | 2591 | 181 | 299 / 32 | 163 / 32 | 0 / 0 | C24+C3+C4+C5 (127), C17+C24+C3+C4+C5 (33), C19+C24+C3+C4+C5 (2), C24+C4+C5 (1) |
| B20 | 900 | 300 | 900 | 460 | 150 | 213 / 0 | 9 / 0 | 0 / 0 | C20+C24+C3+C4+C5 (7), C19+C20+C3+C4+C5 (2) |

## First validator-passing witness per brief (production semantics)

### B01 — witness 0 (2 bands x 4 cols), envelope 10.34x7.31 m, spatial 6/6, access 4/4

| room | x | y | w | d | gross m2 |
|---|---|---|---|---|---|
| BATHROOM_1 | 2.0 | 5.95 | 3.3 | 3.35 | 11.05 |
| HALL | 5.3 | 5.95 | 2.95 | 3.35 | 9.88 |
| KITCHEN | 8.25 | 5.95 | 4.1 | 3.35 | 13.73 |
| LIVING | 6.9 | 2.0 | 5.45 | 3.95 | 21.53 |
| MASTER | 2.0 | 2.0 | 4.9 | 3.95 | 19.36 |

### B05 — witness 31 (4 bands x 3 cols), envelope 8.13x12.59 m, spatial 9/9, access 6/6

| room | x | y | w | d | gross m2 |
|---|---|---|---|---|---|
| BATHROOM_1 | 5.35 | 10.85 | 1.9 | 3.75 | 7.12 |
| BEDROOM_1 | 7.25 | 10.85 | 2.9 | 3.75 | 10.88 |
| DINING | 2.0 | 2.0 | 3.35 | 3.75 | 12.56 |
| HALL | 2.0 | 8.9 | 8.15 | 1.95 | 15.89 |
| KITCHEN | 2.0 | 5.75 | 8.15 | 3.15 | 25.67 |
| LIVING | 5.35 | 2.0 | 4.8 | 3.75 | 18.0 |
| MASTER_BEDROOM | 2.0 | 10.85 | 3.35 | 3.75 | 12.56 |

### B08 — witness 280 (2 bands x 7 cols), envelope 15.0x8.36 m, spatial 10/10, access 6/7, access lost ['LIVING-HALL']

| room | x | y | w | d | gross m2 |
|---|---|---|---|---|---|
| BATHROOM_1 | 15.0 | 2.0 | 2.0 | 4.15 | 8.3 |
| BEDROOM_1 | 9.0 | 2.0 | 3.0 | 4.15 | 12.45 |
| BEDROOM_2 | 12.0 | 2.0 | 3.0 | 4.15 | 12.45 |
| DINING | 2.0 | 6.15 | 6.95 | 4.2 | 29.19 |
| HALL | 8.95 | 6.15 | 4.65 | 4.2 | 19.53 |
| KITCHEN | 2.0 | 2.0 | 2.8 | 4.15 | 11.62 |
| LIVING | 4.8 | 2.0 | 4.2 | 4.15 | 17.43 |
| MASTER_BEDROOM | 13.6 | 6.15 | 3.4 | 4.2 | 14.28 |

### B13 — witness 7 (4 bands x 4 cols), envelope 12.96x12.99 m, spatial 12/12, access 9/9

| room | x | y | w | d | gross m2 |
|---|---|---|---|---|---|
| BATHROOM_1 | 5.75 | 11.2 | 2.4 | 3.8 | 9.12 |
| BATHROOM_2 | 8.15 | 5.8 | 3.4 | 3.4 | 11.56 |
| BEDROOM_1 | 11.55 | 5.8 | 3.4 | 3.4 | 11.56 |
| BEDROOM_2 | 11.55 | 11.2 | 3.4 | 3.8 | 12.92 |
| BEDROOM_3 | 8.15 | 11.2 | 3.4 | 3.8 | 12.92 |
| DINING | 2.0 | 5.8 | 6.15 | 3.4 | 20.91 |
| HALL | 2.0 | 9.2 | 12.95 | 2.0 | 25.9 |
| KITCHEN | 2.0 | 2.0 | 3.75 | 3.8 | 14.25 |
| LIVING | 5.75 | 2.0 | 9.2 | 3.8 | 34.96 |
| MASTER_BEDROOM | 2.0 | 11.2 | 3.75 | 3.8 | 14.25 |

