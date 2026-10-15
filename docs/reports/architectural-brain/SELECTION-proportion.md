# Proportion-aware selection (#197, owner item 2, 2026-10-14): old vs new ranking on the same candidate pool

**Question (owner):** are better plans selected without reducing feasibility or violating the architectural priorities, with hard constraints never traded?

**What changed (`brain/runner.py`):** `_proportion_preference` = `_entrance_preference` with two keys inserted BELOW its three hard-priority keys (the parti's arrival room, the street elevation, the area tolerance) and ABOVE its ornament keys (garden elevation, closest area, worst wet-room proportion): the mean relative deviation of the habitable rooms from their targets, then circulation's share of the net floor. `SELECTION = "proportion"` makes it the brain's default; `"entrance"` restores the previous key. Hard constraints are not in play: the pipeline only offers candidates the validators accepted (`test_a_preference_never_accepts_a_candidate_the_validators_rejected`).

**Method:** the 8 real briefs through `run_brain`; the preference handed to `run_band_pipeline` was wrapped to record every accepted candidate — the pool — while the pipeline kept selecting the old way; both keys were then applied to the identical pool (`selection_eval.py`, scratch).

**Result:** 44 (brief, parti) pools, 198 accepted candidates. The pick changes in **16 of 44** pools. The three hard-priority keys are identical old vs new in **all 44** (lexicographic: they cannot differ). Feasibility is unchanged by construction (same pool, same validators).

| | room deviation | circulation | gross m² |
|---|---|---|---|
| all 44 pools, old → new | 16.5 → 15.4 % | 14.1 → 14.0 % | 162.4 → 161.4 |
| the 16 changed pools | 17.0 → **13.9 %** | 12.8 → 12.5 % | 163.5 → 160.9 |

Per changed pool:

| brief | parti | pool | old dev / circ / gross | new dev / circ / gross | arrival |
|---|---|---|---|---|---|
| B08 | HALL_SPINE | 7 | 12.7 / 8.2 / 123.2 | **8.7** / 8.3 / 122.1 | LIVING |
| B08 | BEDROOM_WING | 9 | 9.3 / 10.8 / 123.6 | **8.7** / 8.3 / 122.1 | LIVING |
| B20 | PUBLIC_BAND | 7 | 24.4 / 13.5 / 132.2 | **15.3** / 12.9 / 133.2 | LIVING |
| B02 | HALL_SPINE+FOYER | 7 | 14.0 / 13.3 / 149.9 | **11.2** / 12.8 / 155.0 | ENTRY |
| B02 | HALL_SPINE | 12 | 13.4 / 11.6 / 156.4 | **7.4** / 10.3 / 153.1 | HALL |
| B11 | HALL_SPINE+FOYER | 2 | 29.4 / 19.9 / 174.4 | **28.4** / 19.4 / 170.4 | ENTRY |
| B11 | PUBLIC_BAND | 5 | 40.7 / 16.8 / 183.3 | **35.2** / 20.0 / 165.6 | LIVING |
| B11 | BEDROOM_WING | 2 | 19.7 / 12.5 / 197.4 | **18.8** / 12.5 / 197.4 | LIVING |
| B19 | BEDROOM_WING | 2 | 27.9 / 13.8 / 171.7 | **19.9** / 12.8 / 182.3 | LIVING |
| B06 | HALL_SPINE+FOYER | 4 | 12.9 / 14.2 / 172.2 | **11.1** / 14.4 / 167.1 | ENTRY |
| B06 | HALL_SPINE | 4 | 11.1 / 10.2 / 166.3 | **10.1** / 10.5 / 160.0 | LIVING |
| B06 | PUBLIC_BAND+FOYER | 12 | 13.0 / 14.7 / 173.2 | **9.9** / 14.2 / 169.0 | ENTRY |
| B06 | PUBLIC_BAND | 12 | 9.9 / 11.5 / 167.7 | **8.7** / 11.5 / 167.0 | LIVING |
| B06 | BEDROOM_WING | 7 | 13.3 / 11.5 / 169.5 | **9.5** / 9.0 / 160.0 | LIVING |
| B09 | HALL_SPINE | 3 | 11.2 / 11.3 / 178.0 | **10.5** / 11.5 / 174.0 | LIVING |
| B09 | PUBLIC_BAND | 8 | 9.3 / 11.3 / 177.3 | **8.4** / 11.4 / 176.0 | LIVING |

**Read honestly:** every changed pick lowers the room deviation (that is what the key orders by); circulation moves ±1 point either way; gross area drops a little (−2.6 m² on the changed pools) because a plan nearer its room targets is sometimes the smaller one — the area tolerance key above it keeps that inside the brief's tolerance. One pick (B11 PUBLIC_BAND) trades 3.2 points of circulation and 18 m² of gross for 5.5 points of deviation; that is the order the key states (rooms before hall), not an accident, and the area key above both is what bounds it.

**Not covered:** the frozen six's pools (harness, different sizer); the proportion metric is the one the six were measured by, so the two agree in kind. The brain is reachable only through `?engine=brain` (preview); production's own `select_primary` is untouched.
