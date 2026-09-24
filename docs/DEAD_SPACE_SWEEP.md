# Dead-Space Sweep (Issue #43)

`scripts/dead_space_sweep.py` run over the frozen 432-context regression corpus (4 worker(s), 1781.7s) plus geometry fixtures. Read-only: measures `app.vertical_slice.dead_space.measure` on whatever `app.demo.service.generate_demo_design` already produces.

## Corpus outcome

- PLANNED: 394
- REFUSED: 38
- CRASH: 0

## Region-kind counts among PLANNED contexts

- STUB: 392
- CORNER: 1

## dead_space_m2 distribution

- min 0.00 m2, max 2.55 m2, mean 1.39 m2
- STUB lengths: min 0.75 m, max 1.50 m, mean 1.12 m — `DEAD_SPACE_STUB_HARD_LIMIT_M` is calibrated with headroom above this maximum.

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

