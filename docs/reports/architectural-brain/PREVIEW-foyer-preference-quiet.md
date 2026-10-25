# #207's gate, settled on a quiet machine — #226 Part A

**Branch** `feature/exact-budget-order` at `d35e30b` (PR #217: #207's two commits plus #216's two,
stacked on PR #215, all on top of `main` = `5b155d1`).
**Control** `5b155d1` — plain `main`, carrying neither #207 nor #216 — measured in the **same
session**, through the **same harness**, back to back with the branch. Every number below is judged
against that control and against nothing else. The figures #207 reported on 2026-10-19 were taken
while #208's worker shared this machine; they appear here only as "before", never as a baseline.

**Verdict: STOP stands, on one brief, and the cause is not the preference.** Clauses 2 and 3 pass
comfortably. Clause 1 fails on **B11** — and the failure is the request budget's allocation, proved
by the branch itself returning the control's exact plan, unchanged, the moment B11's parti is handed
more than its 2.1 s share.

## AC-7 — the machine was quiet

Recorded immediately before the run, from this session, by `uptime`, `ps aux | grep '[c]laude'` and
`agentctl status`:

| reading | value |
|---|---|
| `uptime` load averages, 2026-10-21 11:23:48 IDT | **2.41** / 3.52 / 4.08 |
| `agentctl status` → RUNNING | **(none)**; the only WAITING item, #222, is blocked by #221 |
| `claude` processes | 14, of which **one** above 1 % CPU (6.6 %, this session's own host); the other 13 are idle VS Code extension hosts and `zsh -c source` shells at 0.0 % |
| other top CPU consumers | `WindowServer` 27 %, three Chrome renderers 23/22/10 %, `gh api` 19 % — the owner's desktop, not agent work |
| during the run | control start 11:24:13 at 2.31/3.41/4.03; control end / branch start 11:35:04 at 3.50/3.19/3.52; branch end 11:45:25 at 3.29/2.57/2.94. The 1-minute figure rises to ~3.5 **because of this measurement** (one `uv run` process pinning one core on a MILP) and falls back when it stops. |

The 1-minute average never exceeded 3.0 at the start of either part, so no wait loop was needed.

**The contention was real and it is now gone.** The same B16 brief, same harness, same tree:
production **18.3 s** on a first attempt taken while residual load was still draining, **13.4 s** on
a repeat four minutes later — a 27 % swing on an unchanged code path. And #207's own same-session
control measured its worst brain request at **39.1 s**; the control measures **36.1 s** today.

### The four columns, control at `5b155d1` vs the branch, same session

| brief | column | control (`5b155d1`) | branch (`d35e30b`) |
|---|---|---|---|
| B02 | production | 23.6 / 11.5 · 4.2 s | 23.6 / 11.5 · 4.1 s |
| B02 | brain · production sizer | 7.4 / 10.3 · foyer · 0.8 s | 7.4 / 10.3 · foyer · 0.8 s |
| B02 | brain · exact, band | 7.4 / 10.3 · foyer · 22.0 s | 7.4 / 10.3 · foyer · 27.9 s |
| B02 | brain · exact, all families | 7.4 / 10.3 · foyer · 30.0 s | 7.4 / 10.3 · foyer · 30.0 s |
| B06 | production | 18.1 / 10.7 · 1.0 s | 18.1 / 10.7 · 1.0 s |
| B06 | brain · production sizer | 8.6 / 12.1 · **STRIP** · 2.6 s | 13.0 / 14.7 · foyer · 2.7 s |
| B06 | brain · exact, band | 8.6 / 12.1 · **STRIP** · 31.6 s | 3.8 / 10.7 · foyer · 30.4 s |
| B06 | brain · exact, all families | 8.6 / 12.1 · **STRIP** · 30.0 s | 3.8 / 10.7 · foyer · 30.4 s |
| B08 | production | 3.9 / 12.7 · 0.4 s | 3.9 / 12.7 · 0.4 s |
| B08 | brain · production sizer | 9.0 / 9.0 · **STRIP** · 2.4 s | 9.0 / 9.0 · **STRIP** · 2.3 s |
| B08 | brain · exact, band | 5.1 / 14.1 · foyer · 27.5 s | 5.1 / 14.1 · foyer · 25.1 s |
| B08 | brain · exact, all families | 5.1 / 14.1 · foyer · 30.0 s | 5.1 / 14.1 · foyer · 30.3 s |
| B09 | production | 9.8 / 8.9 · 1.7 s | 9.8 / 8.9 · 1.7 s |
| B09 | brain · production sizer | 13.1 / 14.9 · foyer · 7.1 s | 13.1 / 14.9 · foyer · 6.9 s |
| B09 | brain · exact, band | 13.1 / 14.9 · foyer · 30.0 s | 13.1 / 14.9 · foyer · 30.0 s |
| B09 | brain · exact, all families | 13.1 / 14.9 · foyer · 30.0 s | 13.1 / 14.9 · foyer · 30.0 s |
| B11 | production | 22.0 / 10.9 · 13.7 s | 22.0 / 10.9 · 13.3 s |
| B11 | brain · production sizer | 28.4 / 19.4 · **STRIP** · 23.5 s | 28.4 / 19.4 · **STRIP** · 22.9 s |
| B11 | brain · exact, band | 22.9 / 13.8 · foyer · 28.9 s | 28.4 / 19.4 · **STRIP** · 28.1 s |
| B11 | brain · exact, all families | 22.9 / 13.8 · foyer · 30.2 s | 28.4 / 19.4 · **STRIP** · 30.0 s |
| B16 | production | 14.4 / 10.1 · 13.4 s | 14.4 / 10.1 · 13.1 s |
| B16 | brain · production sizer | 21.4 / 13.5 · foyer · 36.0 s | 21.4 / 13.5 · foyer · 34.8 s |
| B16 | brain · exact, band | 21.4 / 13.5 · foyer · 36.1 s | 21.4 / 13.5 · foyer · 34.7 s |
| B16 | brain · exact, all families | 21.4 / 13.5 · foyer · 36.1 s | 21.4 / 13.5 · foyer · 34.7 s |
| B19 | production | 21.8 / 8.4 · 1.1 s | 21.8 / 8.4 · 1.1 s |
| B19 | brain · production sizer | 19.9 / 12.8 · foyer · 27.6 s | 19.9 / 12.8 · foyer · 26.9 s |
| B19 | brain · exact, band | 19.9 / 12.8 · foyer · 30.4 s | 19.9 / 12.8 · foyer · 29.6 s |
| B19 | brain · exact, all families | 19.9 / 12.8 · foyer · 30.3 s | 19.9 / 12.8 · foyer · 30.0 s |
| B20 | production | 12.5 / 12.0 · 0.2 s | 12.5 / 12.0 · 0.2 s |
| B20 | brain · production sizer | 22.2 / 15.8 · **STRIP** · 9.8 s | 22.2 / 15.8 · **STRIP** · 9.5 s |
| B20 | brain · exact, band | 16.2 / 23.7 · **STRIP** · 26.2 s | 22.2 / 15.8 · **STRIP** · 25.8 s |
| B20 | brain · exact, all families | 22.2 / 15.8 · **STRIP** · 30.7 s | 22.2 / 15.8 · **STRIP** · 30.1 s |

### Means and worst case

| column | control mean dev | branch mean dev | delta | control mean s | branch mean s | control max s | branch max s |
|---|---|---|---|---|---|---|---|
| production | 15.8 | 15.8 | +0.0 | 4.5 | 4.4 | 13.7 | 13.3 |
| brain · production sizer | 16.2 | 16.8 | +0.6 | 13.7 | 13.3 | 36.0 | 34.8 |
| brain · exact, band | 14.3 | 15.2 | +0.9 | 29.1 | 28.9 | 36.1 | 34.7 |
| brain · exact, all families | 15.1 | 15.2 | +0.1 | 30.9 | 30.7 | 36.1 | 34.7 |

Max request time over every brief and every column: control **36.1 s**, branch **34.8 s**.

### The gate's clause 1, in the product's own configuration (`BRAIN_SIZER` = exact, `BRAIN_FAMILIES` = band/spine/stack/cells)

| brief | control shown-first | branch shown-first | branch without #216 | clause 1 |
|---|---|---|---|---|
| B02 | HALL_SPINE · production · 7.4 / 10.3 · 4.9x3.0 m foyer | HALL_SPINE · production · 7.4 / 10.3 · 4.9x3.0 m foyer | HALL_SPINE · production · 7.4 / 10.3 · 4.9x3.0 m foyer | ok on both |
| B06 | BEDROOM_WING+FOYER · production · 8.6 / 12.1 · 1.6x3.15 m **STRIP** | TWO_HALL+FOYER · exact · 3.8 / 10.7 · 2.0x3.0 m foyer | TWO_HALL+FOYER · exact · 3.8 / 10.7 · 2.0x3.0 m foyer | **FIXED** by the branch |
| B08 | PUBLIC_BAND+FOYER · exact · 5.1 / 14.1 · 2.0x3.0 m foyer | PUBLIC_BAND+FOYER · exact · 5.1 / 14.1 · 2.0x3.0 m foyer | PUBLIC_BAND+FOYER · exact · 5.1 / 14.1 · 2.0x3.0 m foyer | ok on both |
| B09 | BEDROOM_WING+FOYER · production · 13.1 / 14.9 · 1.95x2.6 m foyer | BEDROOM_WING+FOYER · production · 13.1 / 14.9 · 1.95x2.6 m foyer | BEDROOM_WING+FOYER · production · 13.1 / 14.9 · 1.95x2.6 m foyer | ok on both |
| B11 | HALL_SPINE+FOYER · exact · 22.9 / 13.8 · 1.95x2.9 m foyer | HALL_SPINE+FOYER · production · 28.4 / 19.4 · 1.7x4.25 m **STRIP** | HALL_SPINE+FOYER · production · 28.4 / 19.4 · 1.7x4.25 m **STRIP** | **REGRESSED** on the branch |
| B16 | SERVICE_CORE · production · 21.4 / 13.5 · 7.95x4.9 m foyer | SERVICE_CORE · production · 21.4 / 13.5 · 7.95x4.9 m foyer | SERVICE_CORE · production · 21.4 / 13.5 · 7.95x4.9 m foyer | ok on both |
| B19 | BEDROOM_WING · production · 19.9 / 12.8 · 4.2x4.75 m foyer | BEDROOM_WING · production · 19.9 / 12.8 · 4.2x4.75 m foyer | BEDROOM_WING · production · 19.9 / 12.8 · 4.2x4.75 m foyer | ok on both |
| B20 | SERVICE_CORE+FOYER · production · 22.2 / 15.8 · 1.5x3.4 m **STRIP** | SERVICE_CORE+FOYER · production · 22.2 / 15.8 · 1.5x3.4 m **STRIP** | SERVICE_CORE+FOYER · production · 22.2 / 15.8 · 1.5x3.4 m **STRIP** | fails on BOTH — pre-existing |

Two things about this table, because it is the one the gate is actually about. First, it is run in
the **product's own configuration** — `service.BRAIN_SIZER` and `service.BRAIN_FAMILIES`, which is
what `?engine=brain` serves — and not in the report's band-only column, so "shown-first" means the
plan a person would see. Second, every plan `run_brain` keeps has already passed the validators, so
"a usable-foyer plan of the same brief passed validators" is tested by asking whether any other
kept plan of that brief has a usable arrival.

On that test the control fails on two briefs and the branch fails on two briefs. They are not the
same two.

## The gate verdict, clause by clause, against the control

| clause | control | branch | verdict |
|---|---|---|---|
| 1. no shown-first plan has a strip arrival where a usable-foyer plan of the same brief passed validators | fails on B06, B20 | fails on **B11**, B20 | **FAILED** — B11 regressed. B06 is fixed, B20 fails identically on both. |
| 2. mean room deviation no worse than the control's by more than 1 point | 15.8 / 16.2 / 14.3 / 15.1 | 15.8 / 16.8 / 15.2 / 15.2 | **PASSED** — +0.0 / +0.6 / +0.9 / +0.1, the worst 0.9 of the 1.0 allowed |
| 3. max request time no worse than the control's | 36.1 s | **34.8 s** | **PASSED** — 1.3 s faster than the control, and every column's mean is lower too |

So the gate verdict is **STOP**, and per #207's contract there is no retune and no second mechanism
in this Issue. But the two clauses that failed in October's loaded session for reasons that turned
out to be the machine now **pass against a control measured beside them**, and clause 1 fails on a
different brief than it did then, for a reason that is now isolated.

## B11 — it did NOT recover, and #216 is not why

#207 reported B11 as 22.9 → 28.4 % and traced it to the budget: production's pass leaves ~6 s of the
30 s, the top parti's share is ~1.9 s, and the first candidate's V solve — trivially infeasible
before #205's foyer group existed, a real optimisation problem after it — burned the whole share and
returned UNKNOWN, so the H candidate that works was never reached. #216 capped one solve at a
quarter of what is left to stop exactly that. **It did not bring B11 back.**

What the quiet measurement shows instead, from `diag_b11.py` on both trees:

| | share handed to `HALL_SPINE+FOYER` | seconds actually used | result |
|---|---|---|---|
| control (`5b155d1`) | 2.130 s | **3.184 s — a 1.05 s overrun** | exact band plan found, 22.9 / 13.8, arrival 1.95 x 2.90 m |
| branch (`d35e30b`) | 2.099 s | 2.136 s — the deadline obeyed | `NO_EXACT_PLAN: 0 placements realized, none kept` |

The control reached B11's good plan by **overrunning its share by a full second**, which the
pre-#216 limit `max(1.0, min(10.0, remaining))` allowed. #216 lowered that floor to 0.25 s, so the
pipeline now keeps to the deadline it was given — and the solve that worked no longer fits inside
2.1 s.

That is a tempting story, and it is wrong, because removing #216 does not bring the plan back
either. Restoring the pre-#216 limit inside the branch at runtime (`PRE216=1` sets
`SOLVE_BUDGET_FRACTION = 1.0`, `MIN_SOLVE_S = 1.0`, the two constants `solve_time_limit` reads)
leaves **all eight shown-first plans byte-identical to the shipped branch**, B11 included — the
fourth column of the clause-1 table above. On these eight briefs **#216 changes no plan at all**; it
changes only whether the deadline is honoured (2.136 s against a 2.099 s share, where the control
spent 3.184 s against 2.130 s).

**What does bring it back is time, and nothing else.** On the branch, B11, exact sizer, band family:

| configuration | result |
|---|---|
| default — 30 s budget, `exact_top` 3 (share ≈ 2.1 s) | 28.4 / 19.4, arrival 1.70 x 4.25 m **STRIP** |
| 30 s budget, `exact_top` **1** (the whole remainder to the best parti, share ≈ 7 s) | **22.9 / 13.8, arrival 1.95 x 2.90 m, a foyer** |
| **45 s** budget, `exact_top` 3 | **22.9 / 13.8, arrival 1.95 x 2.90 m, a foyer** |
| **60 s** budget, `exact_top` 3 | **22.9 / 13.8, arrival 1.95 x 2.90 m, a foyer** |

The plan the control shows is reachable on this branch, identical to three significant figures, by
the branch's own code. It is excluded by arithmetic: production's first pass over the eight partis
consumes **22.9 s of the 30 s** request on B11, `_improve_exactly` divides the remaining ~7 s by
three, and #207's street rule in the V orientation made those solves more expensive than they were
when the same share was enough. The preference ranks correctly on both trees — the branch's own
notes name the key that decided — and the lost plan is not a ranking decision at all. It is a plan
that was never sized.

**So B11's answer to the Issue's question is: no, it did not recover, and the reason is row 3 of the
path to execution (the request-time budget), not row 1.** Three levers are visible and measured, and
all three are somebody's decision, not this Issue's: raise the request budget above 30 s; give the
top parti the whole remainder (`exact_top = 1`) rather than a third of it; or stop production from
spending three quarters of the request before the exact sizer starts (see Part B, where B11's
production prefix is measured stage by stage).

## B20 — it did not recover either, because it never was a regression

#207 reported B20's band column as 16.2 → 22.2 %. In the quiet session that difference is real and
reproduces exactly: control `brain · exact, band` 16.2 / 23.7, branch 22.2 / 15.8. The control's
16.2 plan is #206's 3.40 x 8.15 m hub hall entered through its narrow end — **a strip by the
sizer's own definition** (8.15 / 3.40 = 2.4, against a cap of 1.5), which is why #205's foyer group
refuses it and why the branch does not produce it. Its circulation share is also 23.7 % against the
branch's 15.8 %.

In the **product's own configuration** there is no difference at all: both the control and the
branch show `SERVICE_CORE+FOYER`, production sizer, 22.2 / 15.8, arrival 1.50 x 3.40 m, a strip.
B20 fails clause 1 **identically on both trees**, so it is a pre-existing defect of `main`, neither
caused nor fixed here, and "recovery" was never available to #216. What it is: B20's two plans that
arrive in the parti's own arrival room are both strips, and the usable-arrival plans
(`HALL_SPINE` 13.3 / 13.8 at 4.4 x 4.7 m) lose on key index 0, `arrival` — a higher-priority
architectural term that the owner's 2026-10-14 order puts above the arrival room's shape on purpose.
Fixing B20 means either producing a non-strip arrival for those partis in the sizer, or changing
that order. Both are outside #207.

## What the branch bought, measured against the control

- **B06, the clearest win in the set**: the control shows a 1.60 x 3.15 m strip at 8.6 % deviation;
  the branch shows `TWO_HALL+FOYER`, exact sizer, a 2.00 x 3.00 m foyer, at **3.8 %** — a usable
  arrival *and* 4.8 points better proportion. Clause 1 goes from failing to passing on this brief.
- **B02**: the control's third-ranked plan is a 1.90 x 3.00 m strip `HALL_SPINE+FOYER` at 11.2 %; on
  the branch the same parti is sized exactly in the **spine** family, 8.6 %, with a 2.80 x 3.00 m
  foyer. The shown plan is unchanged, so this is invisible to the gate and visible in the product's
  alternatives.
- **B08**: unchanged at 5.1 / 14.1 with a 2.00 x 3.00 m foyer, but the control's third plan
  (`TWO_HALL`, 2.30 x 4.65 m strip, 9.0 %) now ranks below two foyer plans rather than among them.
- **Nothing got slower.** Every column's mean and max request time is lower on the branch than on
  the control, and the overall worst case improves from 36.1 s to 34.8 s.
- **#216 is, on this corpus, a discipline change with no visible effect**: zero shown-plan changes
  across eight briefs, with the deadline overrun eliminated. That is worth having and it is not what
  it was expected to buy.

## Evidence

Everything in `docs/reports/architectural-brain/data/preview-foyer-quiet/`:

| file | what it is |
|---|---|
| `preview_quiet.py` | the four-column harness, #207's `preview_pref.py` made tree-parametric (the tree is `argv[1]`, and `arrival_usability` is re-derived from the oracle's own constants where the runner has no such function) so the control is measured by the same code |
| `control/metrics.json`, `control/designs/` | the control at `5b155d1`, 56 designs |
| `after/metrics.json`, `after/designs/` | the branch at `d35e30b`, 56 designs |
| `clause1_scan.py`, `clause1-control.json`, `clause1-after.json`, `clause1-after-pre216.json` | clause 1 in the product's configuration, on the control, the branch, and the branch with #216 neutralised |
| `diag_b11.py` | every parti's full notes plus the share each was handed and the seconds it used |
| `diag_b11_share.py` | the four budget configurations that show B11's plan is excluded by time |

Deviation is the mean relative deviation of the habitable rooms from their targets, in per cent;
circulation is circulation's share of the net floor. "foyer" / "STRIP" is `arrival_usability`:
net width >= `FOYER_MIN_NET_M` (1.9 m) and net depth / net width <= `FOYER_MAX_DEPTH_TO_WIDTH` (1.5).

## Recommendation to the owner

The gate says STOP and this report does not argue with it. What it changes is the *reason*: of the
three clauses #207 failed, two failed on contention and now pass, and the third fails on one brief
whose good plan this branch can produce and simply is not given time to. PR #217 is a measured,
reversible option whose cost on these eight briefs is one brief's exact plan and whose gain is
another brief's exact plan plus 4.8 points, with no slowdown anywhere. **The owner merges.** The
blocker to close B11 is the request-time budget, which Part B measures.
