# Dead-Space Sweep (Issue #43)

`scripts/dead_space_sweep.py` run over the frozen 432-context regression corpus (8 worker(s), 471.7s) plus geometry fixtures. Read-only: measures `app.vertical_slice.dead_space.measure` on whatever `app.demo.service.generate_demo_design` already produces.

## Corpus outcome

- PLANNED: 404
- REFUSED: 28
- CRASH: 0

## Would-refuse count (STUB, if it were a hard gate)

`dead_space.classify_hard`'s STUB verdict is only ever MEASURED AND REPORTED — disclosed as a product notice (`QualityOut.dead_space_notice`), never a `validation.py` gate (a check that can never fail has no place in that chain; lead repair order, 2026-09-26/27: a real multi-level upper-level STUB tripped the old hard gate and starved `plan_buildings` of every candidate). This is the count the owner needs to decide whether it should become a hard refusal once Stage 2 changes the geometry: 27/404 PLANNED contexts would refuse if `DEAD_SPACE_STUB_HARD_LIMIT_M` (2.00 m) gated today.

## Would-be-refused count per defect kind

`dead_space.classify_hard` only ever evaluates STUB against a hard number (`DEAD_SPACE_STUB_HARD_LIMIT_M`) — SLIVER/CORNER/OVERSIZED_HALL are reported quality data (`QualityOut.metrics`) only and structurally can never produce a would-refuse verdict (see that function's own docstring), so their count is 0 by construction on every corpus, not merely measured as 0 on this one:

- STUB: 27/404 PLANNED contexts would refuse
- SLIVER: 0/404 PLANNED contexts would refuse — never evaluated by `classify_hard`
- CORNER: 0/404 PLANNED contexts would refuse — never evaluated by `classify_hard`
- OVERSIZED_HALL: 0/404 PLANNED contexts would refuse — never evaluated by `classify_hard`

## Region-kind counts among PLANNED contexts

- STUB: 404
- CORNER: 1

## dead_space_m2 distribution

- min 0.78 m2, max 3.44 m2, mean 1.55 m2
- STUB lengths: min 0.65 m, max 2.65 m, mean 1.24 m — `DEAD_SPACE_STUB_HARD_LIMIT_M` is calibrated with headroom above this maximum.

## Geometry fixtures

### canonical (pipeline.run_demo, spine)

- dead_space_m2: 1.47
  - STUB: 1.47 m2, 1.05 m — 1.05 m of HALL_SPUR past its last opening on the S end

### hub (hand-built, same shape spec 005 targets)

- dead_space_m2: 1.04
  - CORNER: 0.17 m2 — 0.17 m² notch behind the HUB-LIVING door's swing in HUB's corner
  - CORNER: 0.17 m2 — 0.17 m² notch behind the HUB-BR1 door's swing in HUB's corner
  - CORNER: 0.17 m2 — 0.17 m² notch behind the HUB-BR1 door's swing in BR1's corner
  - CORNER: 0.17 m2 — 0.17 m² notch behind the HUB-BR2 door's swing in HUB's corner
  - CORNER: 0.17 m2 — 0.17 m² notch behind the HUB-BR2 door's swing in BR2's corner
  - CORNER: 0.17 m2 — 0.17 m² notch behind the HUB-BR3 door's swing in HUB's corner

