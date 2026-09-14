# Demo envelope — measured 2026-09-14

216 cells: bedrooms 1-6 x wet rooms 1-3 x safe room x footprints 11x12, 12.5x14.5, 12x18, 14x16, 18x12, 16x18 m (target area = footprint area, open plan, no parking, default setbacks), through `generate_demo_design`. Produced by `envelope.py`; the numbers in `app/demo/scope.py` are copied from here.

planned 108/216; C17 failures among plans: 0; crashes: 0; total 507s

## By bedrooms

| bedrooms | planned / 36 | share |
|---|---|---|
| 1 | 5 | 14 % |
| 2 | 20 | 56 % |
| 3 | 26 | 72 % |
| 4 | 25 | 69 % |
| 5 | 14 | 39 % |
| 6 | 18 | 50 % |

## By bedrooms x wet rooms (of 12 cells each)

| bedrooms | wet 1 | wet 2 | wet 3 |
|---|---|---|---|
| 1 | 3 | 0 | 2 |
| 2 | 7 | 5 | 8 |
| 3 | 9 | 9 | 8 |
| 4 | 9 | 8 | 8 |
| 5 | 6 | 4 | 4 |
| 6 | 6 | 7 | 5 |

## Smallest planning footprint of the six, by programme

`—` = none of the six footprints plans it.

| bedrooms | wet | no safe room | safe room |
|---|---|---|---|
| 1 | 1 | 12.5x14.5 (181 m²) | 11x12 (132 m²) |
| 1 | 2 | — | — |
| 1 | 3 | — | 12.5x14.5 (181 m²) |
| 2 | 1 | 11x12 (132 m²) | 11x12 (132 m²) |
| 2 | 2 | 12.5x14.5 (181 m²) | 12.5x14.5 (181 m²) |
| 2 | 3 | 11x12 (132 m²) | 12.5x14.5 (181 m²) |
| 3 | 1 | 11x12 (132 m²) | 12x18 (216 m²) |
| 3 | 2 | 11x12 (132 m²) | 12.5x14.5 (181 m²) |
| 3 | 3 | 12.5x14.5 (181 m²) | 12.5x14.5 (181 m²) |
| 4 | 1 | 11x12 (132 m²) | 12.5x14.5 (181 m²) |
| 4 | 2 | 12.5x14.5 (181 m²) | 12.5x14.5 (181 m²) |
| 4 | 3 | 12.5x14.5 (181 m²) | 12.5x14.5 (181 m²) |
| 5 | 1 | 12.5x14.5 (181 m²) | 12x18 (216 m²) |
| 5 | 2 | 12.5x14.5 (181 m²) | — |
| 5 | 3 | 12.5x14.5 (181 m²) | — |
| 6 | 1 | 12.5x14.5 (181 m²) | 12x18 (216 m²) |
| 6 | 2 | 12.5x14.5 (181 m²) | 12x18 (216 m²) |
| 6 | 3 | 12x18 (216 m²) | 12x18 (216 m²) |

## Every cell

| bedrooms | wet | safe | footprint | result | gross m² | C17 | s |
|---|---|---|---|---|---|---|---|
| 1 | 1 | N | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.4 |
| 1 | 1 | N | 12.5x14.5 | planned | 178.8 | pass | 1.4 |
| 1 | 1 | N | 12x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.7 |
| 1 | 1 | N | 14x16 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.6 |
| 1 | 1 | N | 18x12 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.7 |
| 1 | 1 | N | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 1.5 |
| 1 | 1 | Y | 11x12 | planned | 129.6 | pass | 1.0 |
| 1 | 1 | Y | 12.5x14.5 | planned | 178.3 | pass | 1.8 |
| 1 | 1 | Y | 12x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.7 |
| 1 | 1 | Y | 14x16 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.8 |
| 1 | 1 | Y | 18x12 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.9 |
| 1 | 1 | Y | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 1.0 |
| 1 | 2 | N | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.3 |
| 1 | 2 | N | 12.5x14.5 | PLAN_NOT_REALIZABLE |  |  | 0.5 |
| 1 | 2 | N | 12x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.6 |
| 1 | 2 | N | 14x16 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.5 |
| 1 | 2 | N | 18x12 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.6 |
| 1 | 2 | N | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.8 |
| 1 | 2 | Y | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.5 |
| 1 | 2 | Y | 12.5x14.5 | PLAN_NOT_REALIZABLE |  |  | 2.1 |
| 1 | 2 | Y | 12x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.6 |
| 1 | 2 | Y | 14x16 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.7 |
| 1 | 2 | Y | 18x12 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.8 |
| 1 | 2 | Y | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.9 |
| 1 | 3 | N | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.4 |
| 1 | 3 | N | 12.5x14.5 | PLAN_NOT_REALIZABLE |  |  | 0.6 |
| 1 | 3 | N | 12x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.6 |
| 1 | 3 | N | 14x16 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.6 |
| 1 | 3 | N | 18x12 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.7 |
| 1 | 3 | N | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.8 |
| 1 | 3 | Y | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.5 |
| 1 | 3 | Y | 12.5x14.5 | planned | 168.5 | pass | 5.9 |
| 1 | 3 | Y | 12x18 | PLAN_NOT_REALIZABLE |  |  | 5.4 |
| 1 | 3 | Y | 14x16 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.7 |
| 1 | 3 | Y | 18x12 | planned | 190.8 | pass | 2.1 |
| 1 | 3 | Y | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.8 |
| 2 | 1 | N | 11x12 | planned | 129.6 | pass | 0.4 |
| 2 | 1 | N | 12.5x14.5 | planned | 178.3 | pass | 0.7 |
| 2 | 1 | N | 12x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.6 |
| 2 | 1 | N | 14x16 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.7 |
| 2 | 1 | N | 18x12 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.7 |
| 2 | 1 | N | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.8 |
| 2 | 1 | Y | 11x12 | planned | 129.6 | pass | 1.7 |
| 2 | 1 | Y | 12.5x14.5 | planned | 178.3 | pass | 2.1 |
| 2 | 1 | Y | 12x18 | planned | 165.8 | pass | 1.6 |
| 2 | 1 | Y | 14x16 | planned | 193.2 | pass | 8.5 |
| 2 | 1 | Y | 18x12 | planned | 141.6 | pass | 1.9 |
| 2 | 1 | Y | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 11.0 |
| 2 | 2 | N | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.5 |
| 2 | 2 | N | 12.5x14.5 | planned | 144.0 | pass | 2.7 |
| 2 | 2 | N | 12x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.5 |
| 2 | 2 | N | 14x16 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.6 |
| 2 | 2 | N | 18x12 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.7 |
| 2 | 2 | N | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.8 |
| 2 | 2 | Y | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.4 |
| 2 | 2 | Y | 12.5x14.5 | planned | 167.5 | pass | 5.8 |
| 2 | 2 | Y | 12x18 | planned | 214.1 | pass | 7.0 |
| 2 | 2 | Y | 14x16 | planned | 222.4 | pass | 3.2 |
| 2 | 2 | Y | 18x12 | planned | 214.8 | pass | 7.1 |
| 2 | 2 | Y | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.9 |
| 2 | 3 | N | 11x12 | planned | 130.9 | pass | 0.7 |
| 2 | 3 | N | 12.5x14.5 | planned | 157.5 | pass | 0.3 |
| 2 | 3 | N | 12x18 | planned | 214.1 | pass | 4.2 |
| 2 | 3 | N | 14x16 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.7 |
| 2 | 3 | N | 18x12 | planned | 190.8 | pass | 0.9 |
| 2 | 3 | N | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.9 |
| 2 | 3 | Y | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.3 |
| 2 | 3 | Y | 12.5x14.5 | planned | 179.8 | pass | 2.2 |
| 2 | 3 | Y | 12x18 | planned | 169.6 | pass | 2.6 |
| 2 | 3 | Y | 14x16 | planned | 222.4 | pass | 2.6 |
| 2 | 3 | Y | 18x12 | planned | 214.8 | pass | 6.3 |
| 2 | 3 | Y | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 1.8 |
| 3 | 1 | N | 11x12 | planned | 129.6 | pass | 0.4 |
| 3 | 1 | N | 12.5x14.5 | planned | 178.3 | pass | 0.7 |
| 3 | 1 | N | 12x18 | planned | 165.8 | pass | 0.6 |
| 3 | 1 | N | 14x16 | planned | 204.2 | pass | 1.9 |
| 3 | 1 | N | 18x12 | planned | 141.6 | pass | 0.6 |
| 3 | 1 | N | 16x18 | planned | 226.7 | pass | 12.4 |
| 3 | 1 | Y | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.6 |
| 3 | 1 | Y | 12.5x14.5 | PLAN_NOT_REALIZABLE |  |  | 5.5 |
| 3 | 1 | Y | 12x18 | planned | 198.0 | pass | 29.2 |
| 3 | 1 | Y | 14x16 | planned | 220.8 | pass | 3.2 |
| 3 | 1 | Y | 18x12 | planned | 199.5 | pass | 11.6 |
| 3 | 1 | Y | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 9.2 |
| 3 | 2 | N | 11x12 | planned | 129.5 | pass | 0.8 |
| 3 | 2 | N | 12.5x14.5 | planned | 179.8 | pass | 2.0 |
| 3 | 2 | N | 12x18 | planned | 149.3 | pass | 2.5 |
| 3 | 2 | N | 14x16 | planned | 222.4 | pass | 2.5 |
| 3 | 2 | N | 18x12 | planned | 190.8 | pass | 0.9 |
| 3 | 2 | N | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.8 |
| 3 | 2 | Y | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.3 |
| 3 | 2 | Y | 12.5x14.5 | planned | 179.8 | pass | 1.7 |
| 3 | 2 | Y | 12x18 | planned | 171.4 | pass | 1.0 |
| 3 | 2 | Y | 14x16 | planned | 191.1 | pass | 4.4 |
| 3 | 2 | Y | 18x12 | planned | 184.8 | pass | 1.6 |
| 3 | 2 | Y | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 6.9 |
| 3 | 3 | N | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.3 |
| 3 | 3 | N | 12.5x14.5 | planned | 179.8 | pass | 1.5 |
| 3 | 3 | N | 12x18 | planned | 184.4 | pass | 2.5 |
| 3 | 3 | N | 14x16 | planned | 222.4 | pass | 2.7 |
| 3 | 3 | N | 18x12 | planned | 184.8 | pass | 1.1 |
| 3 | 3 | N | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 5.0 |
| 3 | 3 | Y | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.3 |
| 3 | 3 | Y | 12.5x14.5 | planned | 179.8 | pass | 1.6 |
| 3 | 3 | Y | 12x18 | planned | 187.4 | pass | 1.6 |
| 3 | 3 | Y | 14x16 | planned | 192.5 | pass | 3.9 |
| 3 | 3 | Y | 18x12 | planned | 184.8 | pass | 1.5 |
| 3 | 3 | Y | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 9.6 |
| 4 | 1 | N | 11x12 | planned | 131.6 | pass | 0.6 |
| 4 | 1 | N | 12.5x14.5 | planned | 179.8 | pass | 0.7 |
| 4 | 1 | N | 12x18 | planned | 212.4 | pass | 2.3 |
| 4 | 1 | N | 14x16 | planned | 220.8 | pass | 3.0 |
| 4 | 1 | N | 18x12 | planned | 184.8 | pass | 0.8 |
| 4 | 1 | N | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 9.4 |
| 4 | 1 | Y | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.3 |
| 4 | 1 | Y | 12.5x14.5 | planned | 178.8 | pass | 4.5 |
| 4 | 1 | Y | 12x18 | planned | 216.0 | pass | 12.0 |
| 4 | 1 | Y | 14x16 | planned | 200.2 | pass | 17.0 |
| 4 | 1 | Y | 18x12 | planned | 171.6 | pass | 1.0 |
| 4 | 1 | Y | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 3.9 |
| 4 | 2 | N | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.3 |
| 4 | 2 | N | 12.5x14.5 | planned | 179.8 | pass | 0.8 |
| 4 | 2 | N | 12x18 | planned | 171.4 | pass | 1.4 |
| 4 | 2 | N | 14x16 | planned | 207.1 | pass | 4.3 |
| 4 | 2 | N | 18x12 | planned | 190.8 | pass | 1.0 |
| 4 | 2 | N | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 9.0 |
| 4 | 2 | Y | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.4 |
| 4 | 2 | Y | 12.5x14.5 | planned | 179.8 | pass | 3.3 |
| 4 | 2 | Y | 12x18 | planned | 164.2 | pass | 2.2 |
| 4 | 2 | Y | 14x16 | planned | 222.6 | pass | 17.9 |
| 4 | 2 | Y | 18x12 | planned | 190.8 | pass | 1.0 |
| 4 | 2 | Y | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 2.8 |
| 4 | 3 | N | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.3 |
| 4 | 3 | N | 12.5x14.5 | planned | 179.8 | pass | 1.0 |
| 4 | 3 | N | 12x18 | planned | 187.4 | pass | 1.0 |
| 4 | 3 | N | 14x16 | planned | 207.8 | pass | 3.1 |
| 4 | 3 | N | 18x12 | planned | 190.8 | pass | 0.8 |
| 4 | 3 | N | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 5.6 |
| 4 | 3 | Y | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.3 |
| 4 | 3 | Y | 12.5x14.5 | planned | 180.0 | pass | 2.1 |
| 4 | 3 | Y | 12x18 | planned | 202.9 | pass | 6.0 |
| 4 | 3 | Y | 14x16 | planned | 209.9 | pass | 7.6 |
| 4 | 3 | Y | 18x12 | planned | 190.8 | pass | 0.8 |
| 4 | 3 | Y | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 2.9 |
| 5 | 1 | N | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.3 |
| 5 | 1 | N | 12.5x14.5 | planned | 178.3 | pass | 0.4 |
| 5 | 1 | N | 12x18 | planned | 212.4 | pass | 0.6 |
| 5 | 1 | N | 14x16 | planned | 220.8 | pass | 2.3 |
| 5 | 1 | N | 18x12 | planned | 171.6 | pass | 0.4 |
| 5 | 1 | N | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 7.5 |
| 5 | 1 | Y | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.3 |
| 5 | 1 | Y | 12.5x14.5 | PLAN_NOT_REALIZABLE |  |  | 1.5 |
| 5 | 1 | Y | 12x18 | planned | 212.4 | pass | 1.1 |
| 5 | 1 | Y | 14x16 | planned | 221.4 | pass | 6.2 |
| 5 | 1 | Y | 18x12 | PLAN_NOT_REALIZABLE |  |  | 1.8 |
| 5 | 1 | Y | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.9 |
| 5 | 2 | N | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.3 |
| 5 | 2 | N | 12.5x14.5 | planned | 179.8 | pass | 1.6 |
| 5 | 2 | N | 12x18 | planned | 178.5 | pass | 1.9 |
| 5 | 2 | N | 14x16 | planned | 222.4 | pass | 2.0 |
| 5 | 2 | N | 18x12 | planned | 190.8 | pass | 0.4 |
| 5 | 2 | N | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 3.3 |
| 5 | 2 | Y | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.3 |
| 5 | 2 | Y | 12.5x14.5 | PLAN_NOT_REALIZABLE |  |  | 0.8 |
| 5 | 2 | Y | 12x18 | PLAN_NOT_REALIZABLE |  |  | 1.9 |
| 5 | 2 | Y | 14x16 | PLAN_NOT_REALIZABLE |  |  | 3.7 |
| 5 | 2 | Y | 18x12 | PLAN_NOT_REALIZABLE |  |  | 1.9 |
| 5 | 2 | Y | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 11.0 |
| 5 | 3 | N | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.3 |
| 5 | 3 | N | 12.5x14.5 | planned | 180.0 | pass | 1.1 |
| 5 | 3 | N | 12x18 | planned | 214.1 | pass | 2.8 |
| 5 | 3 | N | 14x16 | planned | 222.4 | pass | 1.4 |
| 5 | 3 | N | 18x12 | planned | 190.8 | pass | 0.4 |
| 5 | 3 | N | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 2.6 |
| 5 | 3 | Y | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.3 |
| 5 | 3 | Y | 12.5x14.5 | PLAN_NOT_REALIZABLE |  |  | 0.9 |
| 5 | 3 | Y | 12x18 | PLAN_NOT_REALIZABLE |  |  | 2.1 |
| 5 | 3 | Y | 14x16 | PLAN_NOT_REALIZABLE |  |  | 3.2 |
| 5 | 3 | Y | 18x12 | PLAN_NOT_REALIZABLE |  |  | 0.8 |
| 5 | 3 | Y | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.9 |
| 6 | 1 | N | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.3 |
| 6 | 1 | N | 12.5x14.5 | planned | 178.3 | pass | 0.4 |
| 6 | 1 | N | 12x18 | planned | 212.4 | pass | 0.6 |
| 6 | 1 | N | 14x16 | planned | 220.8 | pass | 1.1 |
| 6 | 1 | N | 18x12 | planned | 199.5 | pass | 1.6 |
| 6 | 1 | N | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 1.6 |
| 6 | 1 | Y | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.3 |
| 6 | 1 | Y | 12.5x14.5 | PLAN_NOT_REALIZABLE |  |  | 0.5 |
| 6 | 1 | Y | 12x18 | planned | 212.4 | pass | 1.0 |
| 6 | 1 | Y | 14x16 | planned | 220.8 | pass | 1.7 |
| 6 | 1 | Y | 18x12 | PLAN_NOT_REALIZABLE |  |  | 0.6 |
| 6 | 1 | Y | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 0.9 |
| 6 | 2 | N | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.3 |
| 6 | 2 | N | 12.5x14.5 | planned | 178.0 | pass | 0.9 |
| 6 | 2 | N | 12x18 | planned | 214.1 | pass | 2.1 |
| 6 | 2 | N | 14x16 | planned | 222.4 | pass | 0.9 |
| 6 | 2 | N | 18x12 | planned | 214.8 | pass | 1.6 |
| 6 | 2 | N | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 12.1 |
| 6 | 2 | Y | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.3 |
| 6 | 2 | Y | 12.5x14.5 | PLAN_NOT_REALIZABLE |  |  | 0.5 |
| 6 | 2 | Y | 12x18 | planned | 209.6 | pass | 2.3 |
| 6 | 2 | Y | 14x16 | planned | 222.4 | pass | 1.0 |
| 6 | 2 | Y | 18x12 | PLAN_NOT_REALIZABLE |  |  | 0.7 |
| 6 | 2 | Y | 16x18 | planned | 286.2 | pass | 3.9 |
| 6 | 3 | N | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.3 |
| 6 | 3 | N | 12.5x14.5 | PLAN_NOT_REALIZABLE |  |  | 0.5 |
| 6 | 3 | N | 12x18 | planned | 214.1 | pass | 1.9 |
| 6 | 3 | N | 14x16 | planned | 222.4 | pass | 0.6 |
| 6 | 3 | N | 18x12 | PLAN_NOT_REALIZABLE |  |  | 0.8 |
| 6 | 3 | N | 16x18 | TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY |  |  | 1.0 |
| 6 | 3 | Y | 11x12 | PLAN_NOT_REALIZABLE |  |  | 0.3 |
| 6 | 3 | Y | 12.5x14.5 | PLAN_NOT_REALIZABLE |  |  | 0.4 |
| 6 | 3 | Y | 12x18 | planned | 214.1 | pass | 2.3 |
| 6 | 3 | Y | 14x16 | planned | 222.4 | pass | 0.9 |
| 6 | 3 | Y | 18x12 | PLAN_NOT_REALIZABLE |  |  | 0.7 |
| 6 | 3 | Y | 16x18 | planned | 286.2 | pass | 1.9 |

## Refusal codes

- PLAN_NOT_REALIZABLE: 52
- TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY: 56
