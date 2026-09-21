# Entrance-to-Circulation Sweep (Issue #22)

Phase 0 — reproduce first. `scripts/entrance_sequence_sweep.py` run over the frozen 432-context regression corpus (`8` worker(s), 431.0s) plus three geometry fixtures. Read-only: measures `app.vertical_slice.entrance_sequence.measure` on whatever `app.demo.service.generate_demo_design` already produces.

## Corpus outcome

- PLANNED: 404
- REFUSED: 28
- CRASH: 0

## Parti distribution among PLANNED contexts

- SPINE/BAND: 404

## Pocket / tunnel counts

- Contexts with an arrival-zone pocket (`pocket_length_m > 4.00 m`, the calibrated `ENTRANCE_POCKET_MAX_M`): 0
- Contexts with a STRAY pocket (a SEPARATE circulation zone beside the entrance, unserved beyond 0.60 m, the calibrated `ENTRANCE_STRAY_POCKET_MAX_M`): 0
- Contexts with an arrival zone that has no path to a public room at all: 0
- Contexts with a TUNNEL signal (reported, non-blocking, `distance_to_public_m > 4.00 m`, the calibrated `ENTRANCE_TUNNEL_MAX_M`): 342
- Measured `pocket_length_m` on the corpus: min 0.00 m, max 3.28 m, mean 1.82 m — this is why `ENTRANCE_POCKET_MAX_M` needs headroom above the corpus (see `entrance_sequence.py`'s own docstring on the constant); `ENTRANCE_STRAY_POCKET_MAX_M` needs none — 0 of 404 PLANNED contexts have a second circulation zone at all.
- Measured `distance_to_public_m` on the corpus: min 0.00 m, max 7.50 m, mean 5.18 m — the range `ENTRANCE_TUNNEL_MAX_M` is calibrated against.

## Geometry fixtures

### canonical (pipeline.run_demo, spine)

- arrival zone: `HALL_MAIN`
- pocket length: 1.88 m — passes C25
- has a public opening: True
- distance to first public opening: 3.2439
- private doors passed: 1
- foyer: True
- tunnel: no
- stray pockets: none

### L-massing (l_shaped_site_front_arm, MULTI_WING_SPLIT)

- arrival zone: `HALL`
- pocket length: 1.41 m — passes C25
- has a public opening: True
- distance to first public opening: 5.5893
- private doors passed: 3
- foyer: True
- tunnel: 5.59 m to the first public opening, passing 3 private room door(s), exceeds 4.00 m
- stray pockets: none

### hand-built: dead stub at the entrance

- arrival zone: `LIVING`
- pocket length: 0.00 m — FAILS C25 (1.50 m of unserved corridor beside the entrance in HALL exceeds 0.60 m)
- has a public opening: True
- distance to first public opening: 0
- private doors passed: 0
- foyer: False
- tunnel: no
- stray pockets: [('HALL', 1.5)]

## Conclusion — the failure fixture

No context in the frozen corpus, the canonical single-level baseline, or the L-massing candidate (`l_shaped_site_front_arm`) shows a genuine entrance POCKET or STRAY POCKET under this measurement: every real plan's nearest opening off the arrival zone is well under `ENTRANCE_POCKET_MAX_M`, and — because every real spine candidate has exactly one `HALL` leaf (`concept_generator.py`'s `_concept_from`) — no PLANNED context has a second circulation zone at all, so `ENTRANCE_STRAY_POCKET_MAX_M` (the Issue's own 0.6 m default, unchanged) has zero real contexts to conflict with. The L-massing candidate's own hall (which DOES front the street independently of a wider public band ~7 m back) opens onto a nearby door and passes C25 cleanly, with a real TUNNEL signal instead — matching the parti-change diagnosis in the Issue's own "required behavior" §3 (the tunnel is a non-blocking quality signal, not a gate). This mirrors `circulation_metrics.py`'s own C26 EXTREME case precedent (`test_circulation_metrics.py`'s docstring: "every REAL candidate this generator produces already measures comfortably inside the calibrated limits ... that is the point of C26 being additive, not a fixture this codebase can currently produce by accident").

**The failure fixture used by `test_entrance_circulation.py` is therefore a hand-built adversarial `GeometricDesign`** (`dead_stub_beside_entrance_design`, in that test module): the front door opens cleanly into LIVING (no arrival pocket), but a SEPARATE HALL zone independently fronts the street beside it with a genuinely dead 1.5 m stub before its own first door (see that fixture above) — literally AC-5's "1.5 m dead stub beside the entrance", and the shape the Issue's own "Current behavior" section names — reproduced by hand because no swept context currently produces it by accident. A second hand-built fixture in the same test module (`_stray_pocket_design`) reproduces the SAME shape at a larger, less exact scale. The L-massing candidate above is the TUNNEL exemplar instead (a real, generator-produced case).
