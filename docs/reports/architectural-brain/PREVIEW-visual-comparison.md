# `?engine=brain` with the exact sizer — the visual comparison on real briefs (owner item 4, 2026-10-15)

Branch `feature/brain-preview-exact`. Eight real briefs (the brain's own corpus), four plans each, all drawn by the product's `DemoPlan` through the same payload: **production** (the guillotine engine's primary), **brain · production sizer** (the brain as it was: partis → critic → `band_pipeline`'s sizer), **brain · exact, band** (the MILP placement with the target objective), **brain · exact, all families** (+ spine, stack, cross-band cells). The brain plan shown per configuration is its best by room deviation. Figures: `figures/preview-compare/<brief>__<config>.png` (32); data `data/preview-compare/metrics.json`.

**Metrics per cell:** room deviation from target % / circulation share of net % / smallest bedroom as % of target · gross m² · seconds for the whole request; the brain cells name the family and the sizer that actually made the plan (a parti the exact path could not size within its budget falls back to production, typed, and says so).

| brief | production | brain · production sizer | brain · exact, band | brain · exact, all families |
|---|---|---|---|---|
| B08 | 3.9 / 12.7 / 95 · 130 · 0.3 s | 8.7 / 8.3 / 90 · 122 · 1.7 s | **1.4** / 8.2 / 100 · 127 · 28 s (exact) | **1.4** / 8.2 / 100 · 127 · 30 s (exact) |
| B20 | **12.5** / 12.0 / 86 · 131 · 0.2 s | 13.3 / 13.8 / 95 · 129 · 8 s | 15.2 / 7.3 / 96 · 120 · 21 s (exact) | 15.2 / 7.3 / 96 · 120 · 31 s (exact) |
| B02 | 23.6 / 11.5 / 107 · 135 · 3.3 s | 7.4 / 10.3 / 104 · 153 · 0.6 s | **1.2** / 9.9 / 100 · 161 · 20 s (exact) | **1.2** / 9.9 / 100 · 161 · 33 s (exact) |
| B11 | 22.0 / 10.9 / 72 · 167 · 11 s | 17.9 / 12.4 / 70 · 201 · 19 s | 17.9 / 12.4 / 70 · 201 · 38 s (fell back) | **11.4** / 10.6 / 70 · 197 · 44 s (**spine**, exact) |
| B16 | **14.4** / 10.1 / 83 · 188 · 11 s | 21.4 / 13.5 / 58 · 213 · 28 s | 21.4 … (fell back) · 41 s | 21.4 … (fell back) · 43 s |
| B19 | 21.8 / 8.4 / 90 · 173 · 0.8 s | **19.9** / 12.8 / 82 · 182 · 21 s | 19.9 (fell back) · 35 s | 19.9 (fell back) · 38 s |
| B06 | 18.1 / 10.7 / 84 · 177 · 0.7 s | 8.4 / 9.7 / 85 · 167 · 2 s | **0.7** / 9.6 / 99 · 172 · 39 s (exact) | **0.7** / 9.6 / 99 · 172 · 39 s (exact) |
| B09 | 9.8 / 8.9 / 95 · 227 · 1.4 s | **8.4** / 11.4 / 85 · 176 · 6 s | 9.3 (fell back) · 41 s | 9.3 (fell back) · 41 s |
| **mean** | 15.8 / 10.7 / 89 · 3.5 s | 13.2 / 11.5 / 84 · 11 s | 10.9 / 10.6 / 86 · 33 s | **10.1** / 10.4 / 86 · 37 s |

## What the drawings show

* **Where the exact sizer runs, the rooms are on target** — B08 1.4 %, B02 1.2 %, B06 0.7 %: living 46 m², dining 30, kitchen 26, master 20, bedrooms 14, baths 12, hall 15 — against production's B02 (`B02__production.png`): a 7 m strip of living / dining / kitchen at 2.6–3.7 m depth, a 1.30 m corridor, a 14.3 m² "unallocated flexible area", and against the brain's own production-sizer plan (7.4 %). The front door opens into the hall in B02 and B06; the walk reaches it.
* **The families earn their place on one brief here**: B11's spine plan (11.4 %, hall 10.6 %) is the only configuration under 12 % on that 6-bedroom brief. On the other seven the band family's exact placement is already the best the preview finds.
* **Three briefs fell back** (B16, B19, B09 — 12–14 rooms): every exact solve within the per-parti share of the 30 s budget timed out, production sized them (typed, in the plan's notes) and the request took 38–43 s because the fallback ran after the budget. One thing follows and is in this commit: a solve's time limit now follows the remaining budget (no 10 s solve inside a 3 s share), so the request ends near its budget; the production fallback itself takes 0.1–3 s. The honest statement stands: on 12-room briefs the exact sizer needs more than 30 s / 8 partis; a product request should size the top 2–3 partis by the critic's ranking, not all eight.
* **One brief got worse** (B20: 15.2 % vs production 12.5 %): the exact path kept a 120 m² plan (gross −8 % vs production) whose rooms sit closer to targets individually but whose smaller house the deviation metric does not penalise; the area-tolerance key in the preference bounds it, and B20's production plan is itself good. Not every brief needs the brain.
* **Circulation** is 7–10 % on the exact plans (production 8–13 %); smallest bedroom 96–100 % of target on the exact plans where production gives 72–107 %.

## What this is and is not

It is the preview the owner asked to see: real briefs, side by side, drawn by the product. It is not a change to the production engine: `?engine=brain` is per request, `select_primary` and the guillotine engine are untouched, and `run_brain(sizer="production")` is byte-for-byte what it was (test). `scipy` is now a declared dependency (the assessment in `docs/reports/shape-agnostic-realizer/SCIPY-assessment.md`); without it the brain says so and sizes with production's sizer.

**Next, if the owner wants this in front of users:** rank partis before sizing and size the top three (the budget then buys 10 s each — the 12-room briefs would be sized exactly); the proportion-aware preference is already the brain's default (PR #201); the live orchestrator is not involved.

---

**Correction (2026-10-17, `PREVIEW-rank-then-size.md`).** The per-configuration plan in the table above is the one with the lowest room deviation, not the one the product shows first. Checked on the saved designs: every exact plan in the table (B08 1.4 %, B02 1.2 %, B06 0.7 %, …) puts the front door into the living room with the hall in an interior band — the defect the #197 entrance preference exists to prevent — so "the front door opens into the hall in B02 and B06" was wrong. Measured on the plan the product shows first, with the arrival in the parti's own room, the exact sizer's means are 14.8 % (band) and 13.2 % (all families) against production's 15.8 %; see the later report.
