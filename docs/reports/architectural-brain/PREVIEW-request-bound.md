# The stated budget bounds the whole request — #247

**What this settles.** #226 measured a brain request asked for `budget_s=0.2` costing **23.0 s on
B11 and 34.8 s on B16**, with the exact pipeline never entered at all on B16. The budget governed
one stage. This report establishes where the rest of the time went, bounds it, and states the real
figure the owner is being asked to approve — which is **not 30 s**.

Everything below is measured on the eight audit briefs through `generate_demo_design(project,
brain=True)`, the product's own request. The instrument is
`app/ai_harness/request_bound/stages.py`, which wraps callables the request already makes, so no
measurement path differs from the served path.

---

## 1. Where the time goes, per stage, and what was bounded (AC-1)

At the stated **30 s** default, before the change. Indented rows are inside the row above them, so
the columns do not sum.

| stage | B16 | B11 | B02 | B08 | bounded before #247? |
|---|---|---|---|---|---|
| production prefix: outline search + selection | **13.37 s** | **13.67 s** | 4.21 s | 0.41 s | **NO** — reads no clock |
| `run_brain` stage 1: production sizes every parti | **26.66 s** | **17.33 s** | 0.57 s | 1.41 s | **NO** — reads no clock |
| &nbsp;&nbsp;of which `embed_band` | **26.01 s** | **16.88 s** | 0.21 s | 0.98 s | no (bounded by candidate COUNT, not time) |
| &nbsp;&nbsp;of which `solve_band_layout` (the band LP) | 0.07 s / 438 calls | 0.11 s / 229 | 0.11 s / 386 | 0.12 s / 350 | n/a — negligible |
| &nbsp;&nbsp;of which `realize_layout` + validators | 0.03 s | 0.16 s | 0.22 s | 0.25 s | n/a — negligible |
| `run_brain` stage 2: `_improve_exactly` (exact sizer) | 0.00 s | 6.23 s | **29.49 s** | **27.78 s** | **YES** — and it honours it |
| `_rank`, `programme_from_spec` | 0.000 s | 0.000 s | 0.000 s | 0.000 s | n/a |
| payload: `to_demo_design` | 0.02 s | 0.06 s | 0.02 s | 0.05 s | n/a — negligible |
| **whole request** | **49.21 s** | **43.79 s** | **34.50 s** | **30.65 s** | |

**Three stages consumed time. Exactly one of them read the budget.**

1. **`_improve_exactly` was bounded and is well bounded.** On B02 and B08 it spent 29.5 s and 27.8 s
   of a 30 s budget and stopped — the stage was never the defect. #216's solve allowance holds.
2. **`run_brain`'s own first stage was unbounded**, and it is the stage #226 saw: 26.66 s on B16
   against an exact sizer that never started.
3. **The production prefix was unbounded**, and it is larger than anyone had attributed: **13.4 s on
   B16 and 13.7 s on B11**. A brain request pays production's whole outline search before the brain
   is entered, because the brain is handed the outline that came out of it.

### A correction to #226's attribution

#226 reported "MILP is 60–85 % where the exact sizer runs and **zero on B16**", and that the
"SELECTION screens cost 0.01–0.02 s over 360–582 calls". Both halves are confirmed. But the
conclusion drawn from them — that the unaccounted B16 time was the production *sizer* — is wrong in
its detail, and the detail is the whole lever:

> **26.01 s of B16's 26.66 s production stage is `embed_band`, the band EMBEDDING, not any sizing
> at all.** The band LP it feeds costs **0.068 s across 438 calls**. The screens are cheap exactly
> as #226 said; the enumeration in front of them is not.

`embed_band` is bounded by `max_candidates`, a count, and by nothing temporal. It is called once per
parti per widening rung — 30 times on B16 — at up to 1.65 s a call. This is recorded as the lever
for lowering the floor in §4, and it is not touched here: it is an engine change, out of scope.

---

## 2. What changed, and the one thing it refuses to do (AC-2, AC-3)

`brain/budget.py` carries the budget as an **instant**, not a duration. That is the defect in one
line: a duration re-measured inside each stage bounds each stage separately and the request not at
all. `RequestBudget.started` is taken once, at the product boundary in `_generate_demo_design`, and
every stage derives the same deadline from it.

Inside the accounting now: the production prefix (by taking `started` before it), `run_brain`'s
production stage at the parti boundary, `_one`'s widening ladder between rungs, the band pipeline's
two candidate loops, and `_improve_exactly` as before. `budget=None` — what production passes, and
what every caller passed before this — reads no clock at all.

**Nothing is cancelled in flight.** `expired()` is asked *before* a unit of work starts, never
during one. Killing a solve to make a number look right would trade a slow plan for no plan, which
is the fix this Issue was told not to reach for.

### THE FLOOR, which is the honest part

A budget may not empty a result. So the partis are sized with **no deadline at all** until one of
them produces a plan that counts, and only the partis after it are bounded; inside the pipeline the
sizing loop runs until a candidate is sizable and the realization loop until one is accepted,
whatever the clock says. A brief therefore always gets at least the first plan it would have got
before #247.

The consequence is stated rather than hidden: **a request asked for less than its floor costs its
floor.** The floor is a measured number per brief, in §3.

---

## 3. The bound, measured, and the overshoot as a number (AC-2)

Same briefs, same session, `budget_s = 0.2` — the configuration #226 used to expose the defect.

| brief | request BEFORE | request AFTER | AFTER = the floor, decomposed | plans before → after |
|---|---|---|---|---|
| B16 | 49.21 s | **27.77 s** | 13.22 s prefix + 14.54 s to the first counting plan (4 partis tried) | 2 → 1 |
| B11 | 43.79 s | **15.77 s** | 14.41 s prefix + 1.36 s to the first counting plan (1 parti) | 3 → 1 |
| B02 | 34.50 s | **6.39 s** | 6.11 s prefix + 0.28 s to the first counting plan (1 parti) | 3 → 1 |
| B08 | 30.65 s | **0.68 s** | 0.44 s prefix + 0.24 s to the first counting plan (1 parti) | 3 → 1 |

Every one of those four responses is **HTTP 200** and carries, on every plan:

> the request budget of 0.2 s ran out after 27.8 s; 6 of 10 partis were not sized, so the request
> offers fewer alternatives; the exact sizer did not run on any of the 4 ranked parti(s); every
> plan is production-sized

### The overshoot, as two numbers

A request asked for **N** seconds costs at most **N + the last unit of work already in flight**,
plus the floor when N is below it. Measured on these briefs:

| what | number | why it is this and not smaller |
|---|---|---|
| **overshoot above a budget that is above the floor** | **≤ 1.65 s** | the slowest single uninterruptible unit: one `embed_band` call (worst observed 1.653 s on B16). The band LP (0.009 s worst) and one realization + validators (0.013 s worst) are two orders of magnitude below it. |
| **the floor — the cost of the first plan, which the budget may not take away** | **0.68 s (B08) to 27.77 s (B16)**, of which the production prefix is **0.44 s to 14.41 s** | the prefix is production's own outline search, which a production request pays too; the remainder is the partis tried before one counted. |

**So the honest sentence is: a brain request costs `max(floor, stated budget) + ≤ 1.65 s`.** On the
slowest of the eight briefs that is 27.8 s before the stated budget binds at all.

---

## 4. What is given up, exactly

The Issue asked for this to be said plainly rather than buried.

**Below the floor, nothing is given up and the budget simply does not bind** — the request costs the
floor and says so. **Above the floor, what a smaller budget buys back is ALTERNATIVES, never the
primary plan.** At `budget_s=0.2` all four briefs returned 1 plan instead of 2–3. The partis after
the first are the brain's diversity, and they are what the clock takes.

What the deadline cuts inside a parti is narrower still: the **preference search**, the extra
candidates `prefer` compares in order to choose a better one among those the validators already
accepted. That is precisely the latency #197 bought knowingly ("passing it costs latency — the loop
no longer stops at the first success"), so giving it back under time pressure returns a parti to the
pre-#197 first-accepted behaviour rather than to nothing. The sizing loop is cut only past
`max_realizations` sizable candidates, which is the index past which the existing code already
records `NOT_REALIZED_BUDGET` and never realizes — that part is wasted work today and is free.

**The one path that is NOT bounded to the stated value, stated plainly.** A brief the brain cannot
plan at all never lifts the floor, so every parti is tried. That path returns `BRAIN_NO_PLAN` — the
genuine no-plan refusal — and is bounded by the proposer's parti count instead of by the clock.

**The lever that would lower the floor, and it is not this Issue's.** 26.0 s of B16's 26.7 s is
`embed_band`, bounded by a candidate count and not by time. A time-bounded embedding, or a parti
order that tries a likelier parti first, would lower the floor directly. Both are engine changes and
both are out of scope here; §1 records the measurement so the next Issue does not have to find it
again.

---

## 5. Expiry is a 200, and only a no-plan is a 422 (AC-4)

Unchanged in status, and no longer silent. `tests/vertical_slice/test_brain_fallbacks.py` drives
both outcomes through `generate_demo_design`:

| outcome | status | body |
|---|---|---|
| the budget ran out | **200** | a production-sized plan set, and a note on **every** plan naming what did not run |
| the brain has no plan | **422** | `BRAIN_NO_PLAN`, the one genuine refusal |

#226's finding was that the first outcome existed but said nothing — a request returned plans, every
one production-sized, with no indication the exact sizer had never run, while still costing 23–35 s.
`BrainResult.notes` now carries the request-level sentence and `_brain_result` attaches it to every
plan. A request that finishes inside its budget carries no such note, so the note is not a permanent
fixture of every brain response.

---

## 6. The honest latency distribution after the change (AC-5)

Three runs, **back to back in one session**, the control built by `git archive` of this branch's
base commit `75359f4` so it is the unchanged code and not a remembered number. Production is
measured in the same loop as the brain in every run, so the multiple between them cannot drift.

| run | 1-minute load before | 1-minute load after |
|---|---|---|
| control, `75359f4` | **2.52** | 3.04 |
| branch, shipped 60 s | **3.04** | 2.60 |
| branch, a stated 30 s | **2.60** | 2.94 |

Measured against my own stated threshold of 3.0, two of the three readings are below it and the
third is 3.04, i.e. 1 % above. The only processes above 1 % CPU were `WindowServer` at 25.7 % and
Chrome at 19.5 % — the owner's desktop, which is what #226 found too. `agentctl status` showed no
RUNNING agents before any run. Nothing of mine was running; the corpus replays and the test suite
had finished and drained.

### The distribution

| | production median | production max | brain median | brain max |
|---|---|---|---|---|
| **control `75359f4`** (today's code) | 1.07 s | 10.60 s | **31.19 s** | **41.31 s** |
| **branch, shipped 60 s** | 1.05 s | 10.42 s | **31.15 s** | **40.78 s** |
| **branch, a stated 30 s** | 1.04 s | 10.34 s | **30.21 s** | **30.94 s** |

Per brief, brain seconds:

| brief | control | branch 60 s | branch 30 s | plans: control → 60 s → 30 s |
|---|---|---|---|---|
| B08 | 27.26 | 27.05 | 26.85 | 3 → 3 → 3 |
| B20 | 30.45 | 30.38 | 30.06 | 3 → 3 → 3 |
| B02 | 33.57 | 33.60 | 30.15 | 3 → 3 → 3 |
| B11 | 40.47 | 40.57 | 30.31 | 3 → 3 → 3 |
| B16 | 41.31 | 40.78 | 30.94 | 2 → 2 → **1** |
| B19 | 30.95 | 30.86 | 30.11 | 2 → 2 → 2 |
| B06 | 30.86 | 30.85 | 30.27 | 3 → 3 → 3 |
| B09 | 31.44 | 31.43 | 30.30 | 3 → 3 → 3 |

**Three things this says.**

1. **At the shipped 60 s the change costs nothing and is invisible**: 31.15 s against the control's
   31.19 s median, 40.78 s against 41.31 s. That is the point — a ceiling nothing currently reaches.
2. **At a stated 30 s the bound is real and tight.** Median **30.21 s**, max **30.94 s** — a
   **0.94 s** overshoot on the worst of eight briefs, against a predicted ceiling of one
   `embed_band` call (1.65 s). Every one of the eight carries the note.
3. **#226's figures are confirmed, not contradicted.** It measured 31.6 s median / 48.9 s max; the
   same-session control here measures 31.19 s / 41.31 s. Production measured 1.38 s / 13.7 s there
   and 1.07 s / 10.60 s here. The brain is still **roughly 29x production's median**.

---

## 7. No plan was lost (AC-6)

Two independent halves, both clean.

**The corpus — production's own path, 432 scenarios.** Replayed on the branch and on a
`git archive` of `75359f4`, with 3 workers each:

```
planned before=404 after=404   refused before=28 after=28   crashes before=0 after=0
LOST=0  GAINED=0  new crashes=0  status changes=0  refusal-code changes=0
primary-signature changes=0  byte-identical primaries=404
```

`--assert-equal` reports exactly one difference across the two documents: the recorded commit
`sha`, which is `None` in an archived tree that has no git. Every scenario result is identical.
This is the expected outcome and the reason it is: production passes no budget, `budget=None` reads
no clock, and the only other production-visible change is one `time.monotonic()` call at the
request boundary.

**The brain's own plans — the eight audit briefs.** Compared as per-plan geometry signatures
(every room's rounded rectangle), because "no plan was lost" has to be a comparison of drawings and
not of counts:

| | plans lost vs the control | signature-identical briefs |
|---|---|---|
| **branch at the shipped 60 s** | **0** | **8 / 8** |
| branch at a stated 30 s | 1 (B16's second plan) | 7 / 8 |

So AC-6 holds at the shipped value, and the single loss at 30 s is the priced trade-off in §8 and
not a defect. It is also how the value was chosen: 30 s was tried first and
`test_the_brain_delivers_at_least_two_genuinely_distinct_plans[B16]` failed with
`budget_expired=True, 4 of 10 partis were not sized`.

---

## 8. What the owner is actually approving

The question #226 opened was whether "30 s" described a request. It did not, and after this change
the stated number is true — but the number that is true is **not 30 s**.

**The shipped value is 60 s, and the owner is being asked to confirm or lower it.** Both options
are now priced, which they were not before:

| stated budget | request median | request max | overshoot above the stated value | plans lost | what it means |
|---|---|---|---|---|---|
| **60 s (shipped)** | 31.15 s | 40.78 s | — the ceiling binds on no brief | **0** | a true ceiling that nothing reaches today; the honest number for "a brain request can take up to…" |
| **30 s** | 30.21 s | **30.94 s** | **+0.94 s** | **1** (B16, 2 plans → 1) | a bound that genuinely binds, for one lost alternative on the hardest of eight briefs |
| below the floor (e.g. 0.2 s) | — | — | the request costs its **floor**: 0.68 s (B08) to 27.8 s (B16) | 1–2 per brief | the budget stops describing the request and the floor does |

**30 s is a defensible choice and it was not before this change.** Before #247 a stated 30 s bought
a 41–49 s request; now it buys a 30.9 s one for one alternative on one brief. That is the decision
the owner could not previously make, and it is his.

**What must not be read into the 60 s.** It is not a promise that a request takes 60 s, and it is
not an argument that the brain is fast enough. A brain request remains **roughly 29 times
production's median**. The ceiling is honest; the engine is still slow, and §4 names the one lever
(`embed_band`) that would change that.

---

## 9. What is NOT claimed

* **No engine was made faster.** The floor is what it is because `embed_band` costs what it costs.
  This Issue made the clock honest; it did not make the brain quick.
* **Concurrency is not in scope** and is #246's: these are single-request figures, measured one
  request at a time. #246 measured a brain request no longer taking CPU from production; nothing
  here changes that and nothing here was measured alongside it.
* **No validator, sizer or ranking changed.** The budget decides only whether a unit of work
  STARTS. Every candidate that is realized is realized by the unchanged realizer, judged by the
  unchanged validators, and ranked by the unchanged preference.
* **The production prefix is accounted but not bounded.** It is inside the budget window and is
  therefore visible in every number above, and it is the largest part of the floor on three of the
  four briefs profiled. Bounding it would change what a PRODUCTION request does, which this Issue
  may not do.
