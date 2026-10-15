# Cross-band cells (#200), day-2 gate: **STOP** — the representation and the unified sizer work and produce the most credible plans so far on the rectangle; the gate (≤ 15 % in ≥ 3 cases) is not met, and the evidence names the limit as layout *generation* against room bounds, not the cells

Owner directive 2026-10-14, item 1. Branch `feature/cross-band-cells` (commits 1fe19ba, f07be87, this one); data `data/cells-day1-target/`, `data/cells-day2-target/`, `data/cells-day2b-target/` (the measured run); figures `figures/cells/`.

## 1. What was built (and that it is one representation)

`Cell = row interval × column interval` (`cells.py`). A layout is rows of zone ids; a zone in consecutive rows spans them. The band family (every zone one row), the spine (a circulation zone over a run of rows), the stack (a row split in two sub-rows, every other zone spanning both) and a room two rows deep are all instances — the tests build each from the same class. Structural facts on the layout: rows contiguous; C22 — a spanning zone is first/last in all its rows or none; every required contact possible (sequence-neighbours in a row, or adjacent row intervals).

One exact sizer (`milp_cells.py`): each cell its own column nodes; neighbours share a node per row; every cell's net area `(w−iw)(H−ih)` exact through `w·z` products with the rows' height binaries (so area, short side and aspect are linear for plain and spanning cells alike — the big-M-per-height loops of the band oracle are gone); contacts as shared-wall length or x-overlap; the band oracle's envelope, alignment (C22) and entrance (fronting hall = three door widths) rules per row; the day-3 target objective; the inset fixed point. Each cell is its own wing, so every wall is a declared seam and C22 holds it. Parity: on 20 band candidates the band oracle and the cells oracle each find 12 feasible (the cells oracle is faster at `k=6`: 12 s vs 170 s for the 20).

Generators: `moves` (a public/circulation room extended one row at every position; a stack as a split) applied to the band family's SELECTION-passing candidates, oriented as the screen chose; `duplicated_layouts` (a zone two rows deep via `embed_band` on a top/bottom copy with its contacts partitioned, bounded). 7 tests. Harness family `cells` with the production screens (entrance, foyer at the street, exposure) and budgets.

## 2. The gate, measured (six, target objective; best plan per case by room deviation, any family)

| case | best plan | room dev | circ | smallest bedroom | gross | cells family's best | gate |
|---|---|---|---|---|---|---|---|
| F1 rect | spine BEDROOM_WING (day 3) | **6.3 %** | 13.4 | 99 % | 81.5 | **8.5 %** (kitchen two rows, V) · 8.1 % day 1 (two-row hall) | ✓ |
| F2 L | stack BEDROOM_WING (wing day 1) | **16.9 %** | 12.8 | 74 % | 86.6 | 18.7 % (hall + kitchen two rows) | ✗ |
| F3 wide-shallow | spine BEDROOM_WING | 31.9 % | 19.4 | 65 % | 97.7 | none counted | ✗ |
| F4 entry court | band PUBLIC_BAND | 18.7 % | 17.2 | 64 % | 85.8 | none counted | ✗ |
| F5 garden court | band BEDROOM_WING | 23.6 % | 14.0 | 79 % | 80.0 | 25.6 % (dining two rows; circulation 3.2 %) | ✗ |

**1 of 5 under 15 % (gate: 3). No previously solved case lost** (5/5 solved; 49 counted plans vs 20 on day 3). The cells family contributed 10 counted plans (F1 7, F2 1, F5 2); its best is the second-best plan on two cases.

Renders (`figures/cells/`): `F1…HALL_SPINE__cells.png` — living across the street with the front door, a 2.35 × 7.05 m hall two rows deep serving master, kitchen, bath and the bedrooms (8.1 %); `F1…PUBLIC_BAND__cells__kitchen-two-rows.png` — kitchen 5.7 × 4.55 two rows deep beside a 33 m² living room, hall 3.0 × 6.45, bedrooms 13.9–15.1 (8.5 %). These are the first plans of the whole study an architect would not send back on proportion.

## 3. Where it stops, by evidence (not by assumption)

Per case the cells family produced 300–700 layouts and sized 0–9. Classified on F2/F3/F4 (`cells_why.py`, `cells_bind.py`, scratch):

* **≈ 55 % of layouts fail the production screens** — entrance (no arrival room in the street row) and the foyer rule dominate, exposure third. The moves keep a room's screened row, but extending a room pushes neighbours and the duplication does not steer which rows the copies land in. This is a *generator* limitation: the enumerators do not know the screens.
* **≈ 45 % are infeasible in the sizer.** Dropping constraint groups one at a time: dropping **alignment never helps alone (0/25 on F4, 0/25 on F2)**; dropping the **room bounds** (area / short side / aspect at the *loosest* rung) makes 21/25 feasible on F4 and 9/25 on F2; dropping room bounds and contacts together 25/25 and 24/25. So the cells, the alignment rule and the envelope handling are not what refuses these layouts — **the programme's rooms do not fit the 3–4-row structure the layouts impose inside these envelopes** (F4's court leaves 11 m of depth; F2's leg is 8 m wide; F3 is 9.5 m deep), with the contacts tightening it further.
* **Runtime**: with the cheap screens and `k=6`, the cells family costs 24–230 s per case inside its 60 s/parti budget (F1 24 s, F3 232 s); the whole harness with four families runs 180–370 s per case — far from the 30 s bar, which a single product request would have to meet by sizing a bounded handful of layouts, not hundreds.

What the evidence does **not** show: that no cross-band layout exists for F2/F3/F4 under 15 %. The generators tried moves on 12 seeds and ≤ 8 duplication partitions per room; a generator that places rooms *with* the screens and the row-depth budget in mind (choose the street row first, bound the row count by the usable depth, then fill) was not built. That is the next thing to try if the owner wants the cells pursued; it is search, not representation.

## 4. Day-3 assessment, folded in (the directive's items)

* **Architectural quality**: where the sizer gets a valid layout, the plans are the most credible of the study (6–9 % deviation, bedrooms 85–99 % of target, halls 10–13 % of floor). The remaining weaknesses on those plans: strip bedrooms in a last row sized at the minimum depth (5.7 × 2.6), and a bathroom pair sized to their (generous) 12 m² targets.
* **Circulation**: 10–13 % on the cells plans (the two-row hall is the efficient hub); the F5 dining-two-rows plan reaches 3.2 % but at 25.6 % deviation — proportion and circulation trade against each other there.
* **Runtime**: above; the exact objective is seconds per placement; `k=6` and the screen-first order are the two levers that worked; a product budget needs a bounded candidate count.
* **Structural limitations, as measured**: room bounds × envelope depth for 3–4-row cross-band layouts on the L, the strip and the entry court; generator reach; not the representation.

## 5. Verdict and what is kept

STOP at the gate, as directed. Kept on the branch (harness-only, tests green, PR opened, not merged): `cells.py`, `milp_cells.py`, the harness family, 7 tests, the renders and data. Recommendation if the owner continues this line: a screen-aware generator (street row first, row count from the usable depth, rooms placed by the contact graph) over the same representation and sizer — 2 days — measured on the same six; and the preview integration (item 4) so the F1-class plans can be seen on real briefs now.
