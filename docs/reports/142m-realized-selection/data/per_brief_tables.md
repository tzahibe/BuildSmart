# #142M — per-brief matrices

Old = today's gate (highest-scoring clean candidate that passes). New = V1, production's own
preference precedence. Alternatives are classified against the chosen winner.

## historical dataset (`docs/reports/llm-topology-poc/generation-dataset.json`)

| brief | clean | realized | PASS | old | new | changed | deciding term | alt D/V/M | s |
|---|---:|---:|---:|---:|---:|---|---|---|---:|
| B01 | 3 | 3 | 3 | #1 | #1 | no | none | 0/0/2 | 0.293 |
| B02 | 6 | 6 | 6 | #5 | #7 | **yes** | distance_to_public_m | 0/0/5 | 0.46 |
| B03 | 2 | 2 | 2 | #4 | #4 | no | none | 0/0/1 | 0.237 |
| B04 | 3 | 3 | 3 | #1 | #6 | **yes** | area_delta_m2 | 2/0/0 | 1.825 |
| B05 | 3 | 3 | 3 | #4 | #7 | **yes** | entrance_rank | 2/0/0 | 0.721 |
| B06 | 5 | 5 | 5 | #3 | #6 | **yes** | area_delta_m2 | 3/1/0 | 1.767 |
| B07 | 4 | 4 | 4 | #4 | #1 | **yes** | area_delta_m2 | 0/3/0 | 2.435 |
| B08 | 2 | 2 | 2 | #3 | #1 | **yes** | entrance_rank | 1/0/0 | 1.066 |
| B09 | 4 | 4 | 4 | #1 | #6 | **yes** | area_delta_m2 | 3/0/0 | 3.148 |
| B10 | 1 | 1 | 1 | #8 | #8 | no | none | 0/0/0 | 1.397 |
| B11 | 5 | 5 | 4 | #2 | #5 | **yes** | area_delta_m2 | 3/0/0 | 4.73 |
| B12 | 0 | 0 | 0 | — | — | — | — | 0/0/0 | 3.454 |
| B13 | 5 | 5 | 3 | #2 | #2 | no | none | 2/0/0 | 4.028 |
| B14 | 3 | 3 | 3 | #1 | #7 | **yes** | area_delta_m2 | 2/0/0 | 3.507 |
| B15 | 1 | 1 | 1 | #7 | #7 | no | none | 0/0/0 | 2.027 |
| B16 | 2 | 2 | 1 | #3 | #3 | no | none | 0/0/0 | 6.791 |
| B17 | 4 | 4 | 3 | #4 | #3 | **yes** | area_delta_m2 | 2/0/0 | 6.93 |
| B18 | 3 | 3 | 1 | #7 | #7 | no | none | 0/0/0 | 12.568 |
| B19 | 2 | 2 | 1 | #7 | #7 | no | none | 0/0/0 | 6.512 |
| B20 | 1 | 1 | 1 | #1 | #1 | no | none | 0/0/0 | 1.911 |

**Totals** — clean 59, realized 59, PASS 51, briefs with a PASS 19/20, winner changed 10/20, circulation 3-cycles 84.

## corrected dataset (`docs/reports/142k-corrected-proposer/data/generation-dataset-142k.json`)

| brief | clean | realized | PASS | old | new | changed | deciding term | alt D/V/M | s |
|---|---:|---:|---:|---:|---:|---|---|---|---:|
| B01 | 6 | 6 | 6 | #0 | #2 | **yes** | entrance_rank | 5/0/0 | 0.575 |
| B02 | 5 | 5 | 5 | #2 | #3 | **yes** | entrance_rank | 2/0/2 | 0.828 |
| B03 | 4 | 4 | 4 | #5 | #5 | no | none | 0/0/3 | 0.895 |
| B04 | 4 | 4 | 4 | #7 | #7 | no | none | 0/3/0 | 1.398 |
| B05 | 6 | 6 | 5 | #1 | #4 | **yes** | entrance_rank | 3/0/1 | 1.175 |
| B06 | 6 | 6 | 6 | #1 | #4 | **yes** | area_delta_m2 | 4/0/1 | 1.589 |
| B07 | 2 | 2 | 2 | #0 | #0 | no | none | 1/0/0 | 1.241 |
| B08 | 6 | 6 | 6 | #6 | #1 | **yes** | area_delta_m2 | 4/1/0 | 1.441 |
| B09 | 6 | 6 | 6 | #3 | #5 | **yes** | area_delta_m2 | 3/2/0 | 1.785 |
| B10 | 5 | 5 | 5 | #3 | #2 | **yes** | area_delta_m2 | 2/2/0 | 1.934 |
| B11 | 5 | 5 | 5 | #4 | #1 | **yes** | area_delta_m2 | 1/3/0 | 4.301 |
| B12 | 4 | 4 | 3 | #6 | #6 | no | none | 2/0/0 | 3.978 |
| B13 | 6 | 6 | 5 | #3 | #2 | **yes** | area_delta_m2 | 3/1/0 | 3.409 |
| B14 | 6 | 6 | 3 | #4 | #4 | no | none | 0/1/1 | 5.059 |
| B15 | 4 | 4 | 3 | #6 | #5 | **yes** | area_delta_m2 | 2/0/0 | 4.043 |
| B16 | 5 | 5 | 2 | #5 | #6 | **yes** | area_delta_m2 | 1/0/0 | 9.704 |
| B17 | 4 | 4 | 2 | #7 | #0 | **yes** | area_delta_m2 | 1/0/0 | 8.57 |
| B18 | 4 | 4 | 3 | #0 | #7 | **yes** | area_delta_m2 | 2/0/0 | 6.968 |
| B19 | 7 | 7 | 3 | #0 | #0 | no | none | 1/1/0 | 10.7 |
| B20 | 5 | 5 | 3 | #7 | #6 | **yes** | entrance_rank | 2/0/0 | 9.979 |

**Totals** — clean 100, realized 100, PASS 81, briefs with a PASS 20/20, winner changed 14/20, circulation 3-cycles 267.

