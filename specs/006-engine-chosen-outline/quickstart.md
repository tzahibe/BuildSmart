# Quickstart: proving the engine-chosen outline end to end

All backend commands run from `backend/` with the project venv; frontend commands from `frontend/`.

## 0. Freeze the "before" (do this on `main` at `5fd9474`, before any change)

```bash
.venv/bin/python3 spikes/failure_log_sweep/snapshot.py --save /tmp/before-006.json
.venv/bin/python3 -m pytest -q --no-header -p no:warnings | tail -1     # baseline at 5fd9474: 773 passed, 6 skipped
```
Expected: `saved 424 scenarios: planned 127`.

## 1. Non-regression — the advanced path reproduces today (SC-005)

```bash
.venv/bin/python3 spikes/failure_log_sweep/snapshot.py --compare /tmp/before-006.json
```
Runs every logged context **with** its `selected_footprint` (the advanced path).
Expected: `pre-existing PRIMARY designs byte-identical: 127/127   LOST: 0`.

## 2. Main flow — the engine chooses (SC-001, SC-002, SC-003, SC-006, SC-007, SC-008)

```bash
.venv/bin/python3 spikes/failure_log_sweep/outline_ab.py
```
Runs every context twice — A: with footprint (advanced), B: without (main flow) — and prints:

| Line | Expected |
|---|---|
| `planned A=127  B=…` | B ≥ 250 |
| `B first-plan gross/requested median` | ≥ 0.95 |
| `B briefs with >=2 families shown` | ≥ 60 (of the 127 that plan in A) |
| `same family + same outline pairs shown` | 0 |
| `refusals mentioning an outline` | 0 |
| `over-capacity refusals with capacity diagnosis` | 67 / 67 |
| `latency median A / B / before` | B ≤ 4 × before |
| `plans shown failing validation` | 0 (SC-004; the script re-checks every shown plan's `validation.ok`) |

## 3. Unit and contract tests

```bash
.venv/bin/python3 -m pytest -q --no-header -p no:warnings
```
Expected: baseline count + the new tests in `tests/test_demo_outline_selection.py`
(selection invariants from [data-model.md](./data-model.md) — each invariant is one test), the
scope tests for an absent footprint, the `family_signature` invariants (forced == twin; SDL == SSC
for equal allocations; mirror-independent; hub-prefixed), and the contract tests for the additive
fields and the `plan` SSE event. Zero failures.

## 4. Frontend

```bash
npm test
```
Expected: `App.test.tsx` — form submit goes straight to loading (no footprint view); the advanced
disclosure renders `FootprintSelection` inline and, when a rectangle is confirmed there, the request
carries `selected_footprint`. `DemoPlan.test.tsx` — every plan card shows its outline label and
origin. `LoadingScreen.test.tsx` — a `plan` event renders the provisional plan with the "עוד N
מתארים בבדיקה" note, and `done` replaces it.

## 5. Manual walk-through

```bash
npm run dev            # frontend
.venv/bin/uvicorn app.main:app --reload   # backend, from backend/
```
1. Enter a plot 15 × 15 m, north street, 3 bedrooms, 2 wet rooms, safe room, 176 m². Submit.
   Expected: no outline screen; the loading screen shows "מתאר 1 מתוך 4"; a first plan appears
   before the bar completes; the final screen shows 1–3 plans, each with "12.35 × 14.25 מ׳ · 176 מ"ר ·
   מתאר אוטומטי" under its title, and no two plans that are the same house re-proportioned.
2. Open "מתקדם — קביעת מתאר ידנית", pick "צר ומוארך" (14.98 × 11.75), submit.
   Expected: the first plan shown is at exactly that outline, labelled "המתאר שהזנת"; any others
   are labelled automatic.
3. In the advanced disclosure enter 10.00 × 17.60, submit.
   Expected (this shape rarely plans): a success whose first plan is an automatic outline, with a
   note that the entered outline could not be planned — not a refusal.
4. Enter 1 bedroom, 1 wet room, 440 m² on a 22 × 22 plot. Submit.
   Expected: one refusal, the capacity diagnosis, no "try X × Y" sentence.

## 6. Latency, reported

`outline_ab.py` prints per-outline and total medians; paste them into a `RESULTS.md` in this
folder at the end, as feature 005 did. If B's median exceeds 4× before, that is a finding to report,
not to hide — research R4 names the concurrency option as the next step, deliberately not taken here.
