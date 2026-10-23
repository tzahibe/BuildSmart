# The preview's performance, measured alone on the machine — #226 Part B (ROOT #211 §4)

**Where this should have gone.** The Issue asks for this to be appended to
`docs/reports/architectural-brain/PREVIEW-operational-readiness.md`. That file is not on this
branch — it lives on `feature/brain-ops-readiness` and `feature/preview-killswitch` (#214's and the
kill-switch chain's work) and is reachable from four commits, none of them an ancestor of
`feature/exact-budget-order`. Cherry-picking it here to append to it would put #214's deterministic
half on a branch that has no business carrying it, so this is a separate file, as the contract
allows. **Whoever rolls the two up should merge this file into that one; nothing here duplicates
#214's deterministic half, and nothing here contradicts it.**

**Measured on** `feature/exact-budget-order` at `d35e30b` (PR #217 = #207 + #216 on `main`
`5b155d1`), the branch Part A judged — stated per the contract. Part A's control at `5b155d1` shows
`production` identical on both trees (mean deviation 15.8, max 13.7 s vs 13.3 s), so none of the
production figures below depend on the branch.

**Machine**: Apple M1 Pro, **10 cores**, 32 GB. `hw.ncpu` 10, `hw.physicalcpu` 10.

> **Corrected and settled by #247** (`PREVIEW-request-bound.md`), 2026-10-23. Answer 1's finding —
> that the 30 s budget bounds only the exact-sizer phase — was right and is now fixed: the stated
> budget bounds the whole request, including the production prefix. Two numbers below are
> superseded. **Answer 1's attribution of B16's unaccounted time is wrong in its detail**: 26.0 s of
> B16's 26.7 s production stage is `embed_band`, the band EMBEDDING, not any sizing — the band LP it
> feeds costs 0.068 s across 438 calls. And "the 30 s budget overruns itself by 16 % on B16" below
> understates it: the production prefix is a further 13.4 s that this report did not attribute to
> the request at all. The `31.6 s median / 48.9 s max` figures stand and #247 re-measured them
> against a same-session control.

## The four answers, first

1. **Latency**: a brain request is **31.6 s median, 48.9 s max** against production's
   **1.38 s median, 13.7 s max** — and **the 30 s budget is not a request timeout**. It bounds only
   the exact-sizer phase. Squeezing it to **0.2 s** leaves B11 taking **23.0 s** and B16 **34.8 s**,
   because `run_brain`'s first stage sizes all eight partis with no deadline at all. #213's 32.4 s /
   50.0 s were very nearly right: the figure is structural, not contention.
2. **CPU and memory**: a brain request peaks at **168–213 MB** RSS against production's
   **113–118 MB**, and burns **1.00–1.07 cores** for 30–49 s. HiGHS is effectively single-threaded
   here; it adds at most 7 % CPU beyond wall time.
3. **Concurrency**: brain requests **do not run in parallel — they serialize**. On ten cores, N=1 is
   43.5 s and N=2's slowest is 85.1 s. Four concurrent brain requests keep the server process at
   **100.2 % CPU, one core**. The per-request 30 s budget does not hold under load (N=8 median
   94 s). **Safe limit: one concurrent brain request, enforced server-side.**
4. **Failure isolation — yes, a brain request degrades production traffic.** Production goes from
   **1.65 s median / 1.71 s max** quiet to **5.89 s / 11.51 s** beside two brain requests and
   **9.29 s / 16.87 s** beside four: **x3.6 to x5.6 on the median, up to x9.9 on the worst case.**
   The asyncio event loop is **not** blocked — a trivial route still answers in 26 ms while four
   brain requests run — so **a liveness probe stays green while real users wait 17 seconds.** The
   damage is the GIL, not the loop.

## AC-7 — the machine was idle for this part too

| reading | value |
|---|---|
| `uptime` load averages, 2026-10-21 12:10:04 IDT | 3.19 / 2.76 / 2.75 |
| **above the 3.0 threshold, so this part waited** | re-checked at 12:10:17: **2.94** / 2.58 / 2.57, settled on the first re-check of a bounded 20-attempt loop. What the 3.19 was: Chrome 20.6 %, this session's own `claude` host 12.3 %, `WindowServer` 11.8 %, Activity Monitor 9.4 % — the owner's desktop, no agent work. |
| `agentctl status` → RUNNING | **(none)** |
| `claude` processes | 14, of which 2 above 1 % CPU: this session's host at 9.4 % and its own `zsh` at 4.2 % |
| the live server, pid 79460 | present, `0.0 %` CPU, `etime` 25 days — idle throughout, and never touched |
| load before the concurrency run, 12:31 | 2.25 / 2.58 / 2.69 |
| load after everything, 12:46 | 2.17 / 2.48 / 2.57 |

The drift check proves the quiet: production measured **1.65 s** median before the load runs and
**1.63 s** median after them, a 0.98x ratio. Nothing in this report's "quiet" column is contaminated.

### B.1 — where a `?engine=brain` request's seconds go (quiet machine, one request at a time)

| brief | brain total | production prefix | brain: production sizing | embedding | screens | MILP solves | MILP calls | realization | payload | MILP share of total |
|---|---|---|---|---|---|---|---|---|---|---|
| B02 | **34.44 s** | 4.21 s | 0.53 s | 0.18 s | 0.01 s | 29.01 s | 259 | 0.08 s | 0.05 s | 84 % |
| B06 | **31.18 s** | 0.99 s | 1.59 s | 0.50 s | 0.01 s | 26.37 s | 81 | 0.05 s | 0.08 s | 85 % |
| B08 | **30.53 s** | 0.44 s | 1.45 s | 0.46 s | 0.02 s | 20.87 s | 807 | 0.14 s | 0.05 s | 68 % |
| B09 | **31.87 s** | 1.64 s | 5.00 s | 0.74 s | 0.01 s | 21.64 s | 37 | -- s | 0.08 s | 68 % |
| B11 | **43.76 s** | 13.74 s | 17.04 s | 1.17 s | 0.02 s | 4.39 s | 74 | -- s | 0.06 s | 10 % |
| B16 | **48.92 s** | 13.36 s | 26.43 s | -- s | -- s | 0.00 s | -- | -- s | 0.02 s | 0 % |
| B19 | **31.31 s** | 1.12 s | 20.24 s | 1.25 s | 0.02 s | 0.12 s | 5 | -- s | 0.02 s | 0 % |
| B20 | **30.31 s** | 0.22 s | 7.52 s | 1.22 s | 0.02 s | 18.22 s | 618 | 0.04 s | 0.04 s | 60 % |

| | median | max | min |
|---|---|---|---|
| brain request | **31.6 s** | **48.9 s** | 30.3 s |
| production request | **1.38 s** | **13.7 s** | 0.22 s |

### B.2 — CPU and memory, one request in a fresh process

| engine | brief | seconds | peak RSS | RSS the request itself added | CPU seconds | CPU / wall |
|---|---|---|---|---|---|---|
| production | B02 | 4.09 s | **116.9 MB** | 12.6 MB | 4.08 s | 0.997 |
| brain | B02 | 34.21 s | **212.6 MB** | 107.8 MB | 36.61 s | 1.07 |
| production | B08 | 0.43 s | **113.3 MB** | 8.0 MB | 0.43 s | 1.0 |
| brain | B08 | 30.7 s | **177.7 MB** | 73.0 MB | 32.91 s | 1.1 |
| production | B11 | 13.48 s | **117.5 MB** | 12.1 MB | 13.43 s | 0.996 |
| brain | B11 | 43.65 s | **184.1 MB** | 78.5 MB | 43.97 s | 1.0 |
| production | B16 | 13.14 s | **118.0 MB** | 12.1 MB | 13.12 s | 0.998 |
| brain | B16 | 48.49 s | **168.0 MB** | 62.7 MB | 48.34 s | 0.997 |

### B.3 — N simultaneous brain requests (10-core Apple M1 Pro, 32 GB)

| N | wall for the batch | per-request min / median / max | HTTP codes | server RSS before -> peak |
|---|---|---|---|---|
| 1 | 43.48 s | 43.48 / 43.48 / **43.48** s | [200] | 241.5 -> 246.1 MB |
| 2 | 85.11 s | 67.8 / 76.5 / **85.11** s | [200] | 246.1 -> 259.5 MB |
| 4 | 122.81 s | 55.7 / 91.5 / **122.8** s | [200] | 259.5 -> 266.0 MB |
| 8 | 146.79 s | 72.95 / 94.1 / **146.79** s | [200] | 265.6 -> 272.5 MB |

### B.4 — production latency with and without concurrent brain load

| condition | production median | production max | n | vs quiet |
|---|---|---|---|---|
| quiet, before | **1.65 s** | 1.71 s | 6 | baseline |
| 2 concurrent brain requests | **5.89 s** | **11.51 s** | 17 | median x3.6, max x6.7 |
| 4 concurrent brain requests | **9.29 s** | **16.87 s** | 16 | median x5.6, max x9.9 |
| quiet, after (drift check) | 1.63 s | 1.69 s | 6 | x0.98 |

| trivial route (answered on the event loop) | quiet median | quiet max | under 4 brain requests: median | max | n |
|---|---|---|---|---|---|
| `/docs` | 0.000 s | 0.007 s | **0.026 s** | 0.105 s | 315 |
| `/openapi.json` | 0.002 s | 0.212 s | **0.032 s** | 0.157 s | 315 |

| B08 `?engine=brain` | seconds | server CPU median | server CPU max | primary plan |
|---|---|---|---|---|
| alone | 30.77 s | **107.3 %** | 128.1 % | `brain:PUBLIC_BAND+FOYER`, 131.45 m2 |
| beside 3 other brain requests | 53.64 s | **100.2 %** | 110.3 % | `brain:TWO_HALL`, 129.92 m2 |

## B.1 read out

**A brain request is a production request plus the brain.** `_brain_result` needs
`selection.primary`'s outline, so `?engine=brain` runs the entire production pipeline first and only
then calls `run_brain`. That prefix is free on most briefs (0.22–1.64 s) and is **13.7 s on B11 and
13.4 s on B16** — a third of those requests' total before the brain has started.

**The stage that dominates depends on the brief, and it is never the one people expect.**

- **MILP solving is 60–85 % of the request** where the exact sizer gets to run (B02 29.0 s of
  34.4 s; B06 26.4 s; B08 20.9 s over 807 solves; B20 18.2 s over 618).
- **The brain's own production-sizer stage is the whole request** where it does not: B16 spends
  **26.4 s in `run_band_pipeline`** over 30 calls and reaches **zero MILP solves** — the exact
  pipeline is never entered, which is exactly why B16 has never had an exact plan in any report.
  B19 spends 20.2 s the same way; B11 spends 17.0 s and gets only 4.4 s of solving.
- **Everything else is noise.** Band embedding is 0.18–1.25 s. The production SELECTION screens are
  **0.01–0.02 s across 360–582 calls** — a rounding error, not a stage. Realization is 0.04–0.14 s.
  Payload assembly, which includes the renderer and #180's label work, is **0.02–0.08 s**.

So the "30 s budget" buys MILP time on half the corpus and buys nothing at all on the other half,
where the brain's own first pass has already spent it. **Any attempt to make the preview faster
should start at `run_brain`'s stage 1, not at the solver.**

### What a request returns when the budget expires mid-solve

Measured by squeezing `budget_s` from 30 s down to 0.2 s on the two briefs whose solves consume the
whole budget (`perf_budget_expiry.py`):

| brief | `budget_s` | the request actually ran | distinct plans | sizers | raised |
|---|---|---|---|---|---|
| B11 | 0.2 / 1 / 3 / 10 s | **23.0 / 22.8 / 22.9 / 22.8 s** | 6 | production | no |
| B11 | 30 s | 30.1 s | 6 | production | no |
| B16 | 0.2 / 1 / 3 / 10 s | **34.8 / 34.9 / 34.8 / 34.7 s** | 2 | production | no |
| B16 | 30 s | 34.8 s | 2 | production | no |

Two facts, both structural:

1. **`budget_s` does not bound the request.** `run_brain` sizes every parti with the production
   sizer before it looks at the clock; only `_improve_exactly` respects `deadline`. A 0.2 s budget
   still costs 23 s on B11 and 35 s on B16, and the **30 s budget overruns itself by 16 % on B16
   (34.8 s) even when honoured.** There is no request timeout on the preview path at all.
   *(FIXED by #247. One deadline, taken at the request's start, is read by every stage that spends
   time; a 0.2 s budget now costs 0.68 s on B08 and 27.8 s on B16, and what remains is the floor —
   the cost of the first plan, which a budget may not take away. The two numbers this item does not
   account for are the 13.4 s production prefix and the fact that 26.0 s of the 26.7 s production
   stage is `embed_band`. See `PREVIEW-request-bound.md` §1 and §3.)*
2. **Expiry degrades silently but audibly.** The request returns **HTTP 200 with a complete plan
   set**, sized by the production sizer, and the plan's notes say
   `exact sizer fell back to production: ...` with the reason. It never raises. The only refusal is
   `BRAIN_NO_PLAN` — **HTTP 422** with code, message and detail — and that happens only when no
   parti can be planned at all, which none of the eight briefs does. So a user never sees an error
   from the budget; they see a worse plan, with a note, in the same number of seconds.

## B.3 read out — the serialization, and why concurrency is not a capacity question

N=2 is not 43 s, it is **85 s** — twice N=1, on a machine with ten cores and 32 GB. The server
process's own CPU figure settles it: **107.3 % median with one brain request, 100.2 % median with
four.** Four concurrent requests on a ten-core machine use one core. `scipy.optimize.milp` holds
the GIL for the duration of each HiGHS call, so the anyio threadpool that Starlette runs the
synchronous endpoint in buys no parallelism whatsoever.

**Memory is therefore not the risk.** Server RSS went 241.5 MB → 272.5 MB across N=1 to N=8 — a
31 MB spread, because the requests queue instead of coexisting. Anyone sizing this on memory will
size it wrong.

**And the 30 s budget does not hold per request under load.** N=8 ran 73–147 s per request, median
94 s. Nothing returned an error — all `[200]` at every N — so the queue is invisible to the caller
except as latency.

**The worst consequence is not the clock, it is the plan.** The budget is wall-clock, so a
contended request sizes fewer candidates inside the same 30 s and ships something else. Same brief,
same server, same code, measured in this session:

- **B08 alone**: 30.8 s, primary `brain:PUBLIC_BAND+FOYER`, 131.45 m2 — the 5.1 % exact plan.
- **B08 beside three other brain requests**: 53.6 s, primary **`brain:TWO_HALL`**, 129.92 m2 — a
  different parti.

Two viewers comparing the preview at the same moment are not looking at the same engine. This is
the same effect that corrupted #207's and #212's measurements, now reproduced deliberately at the
HTTP boundary.

## B.4 read out — the event loop is innocent, the GIL is not

The demo endpoint is a plain `def`, so Starlette hands it to the anyio threadpool and the loop
stays free. Measured rather than assumed: with four brain requests in flight, `/docs` answers in
**26 ms median / 105 ms max** over 315 samples, and `/openapi.json` in 32 ms / 157 ms. Quiet, those
are 0–2 ms. So the loop is slowed by a factor of ten and remains, in absolute terms, instant.

Real work is not. Production's own `POST /design/demo` goes **1.65 s → 5.89 s median / 11.51 s max**
beside two brain requests and **9.29 s / 16.87 s** beside four, and returns to 1.63 s the moment the
load stops. The pipeline is Python, the solver holds the GIL, and production queues behind it.

**The operational trap this creates is worth stating on its own.** Health checks, readiness probes
and uptime monitors hit cheap routes. Those stay green at 26 ms while a person who asked for a house
waits 17 s. **No existing monitor would notice this.** The signal to watch is p95 on
`POST /projects/{id}/design/demo` with `engine` absent, segmented from requests where it is present.

## Risks, each with a severity and a mitigation

| # | risk | severity | evidence | mitigation |
|---|---|---|---|---|
| R1 | **A preview request degrades production traffic for everyone.** Two concurrent brain requests take production's median from 1.65 s to 5.89 s; four take its worst case to 16.9 s. | **HIGH** | B.4 | Serve the preview from **its own process** (a separate uvicorn worker or container) so the GIL it monopolises is not production's. If that is not available before the preview opens, a server-side semaphore of **1** on the brain path, returning 429 when held, caps the damage at one request's worth. Neither change touches the engine. |
| R2 | **Nothing bounds concurrent preview requests** — #214's structural finding, confirmed here at the HTTP boundary: every N returned 200, nothing queued visibly, nothing refused. | **HIGH** | B.3 | The same semaphore as R1. It is the single highest-value change in this report, and it is a few lines in `demo/router.py` next to `_brain_requested`. |
| R3 | **There is no request timeout.** `budget_s` bounds only the exact phase; a 0.2 s budget still costs 23–35 s, and under N=8 a request ran 147 s. A reverse proxy's own 60 s timeout would cut the connection with the work still running. | **HIGH** | B.1, B.3 | Give `run_brain`'s stage 1 the same `deadline` `_improve_exactly` already has, so the budget means the request; and set an explicit server-side timeout that returns 422 with a code rather than being cut off mid-solve. |
| R4 | **Contention changes which plan the product shows**, so two people comparing the preview at the same time may see different engines. B08 alone gives `PUBLIC_BAND+FOYER`, B08 beside three others gives `TWO_HALL`. | **HIGH** for a preview whose entire purpose is judging architectural quality | B.3 | The R1/R2 semaphore makes this impossible by construction. Until then, the preview's payload should carry the seconds it had and the number of candidates it sized, so a judgment can be discarded when it was made under load. |
| R5 | **A brain request is 20x a production request's latency and ~1.7x its memory**, and it burns a full core for 30–49 s. | MEDIUM | B.1, B.2 | Accept it for an internal preview; it is the cost of an exact sizer. Do not accept it on a shared process (R1). |
| R6 | **The brain's own production-sizer stage, not the solver, is the whole cost on half the corpus** (B16 26.4 s, B19 20.2 s, B11 17.0 s), and on B16 it consumes the budget before a single MILP solve runs. | MEDIUM — it is a quality ceiling, not an outage | B.1 | This is Part A's B11 blocker and the same lever: bound stage 1, or cache its result across the exact phase, so the budget reaches the solver. Owner's call, measured here. |
| R7 | **HiGHS's stderr is not captured.** `HighsMipSolverData::transformNewIntegerFeasibleSolution tmpSolver.run();` is printed straight to the process's stderr, thousands of lines per run. | LOW | every run log in `data/` | Silence it at the `scipy.optimize.milp` call or filter it in the log pipeline before the preview is deployed anywhere that collects logs. |
| R8 | The preview's authorization is still the query parameter alone — `_brain_requested(engine)` is `engine == "brain"`, with no flag and no authorization check. | **HIGH**, but it is **#212's**, recorded here only because this measurement walked the same path | `demo/router.py` | #212 / the kill-switch chain. Not touched here. |

## What this does NOT measure

- **MILP failure and fallback paths beyond the budget**, logging and observability, the SciPy/HiGHS
  deployment dependency, and the runbook are ROOT #211 §4's other halves and are #214's, not this
  Issue's.
- **Concurrency above N=8**, and concurrency of *mixed* briefs chosen adversarially. N=8 already
  shows the shape; the serialization means more N adds queue, not risk.
- **A multi-worker uvicorn.** Everything here is `--workers 1`, which is what makes the GIL finding
  clean. R1's mitigation is precisely to stop that being the deployment.
- **Any figure from another session.** Nothing in this report is compared against one.

## Evidence and how to re-run it

All in `docs/reports/architectural-brain/data/preview-performance-quiet/`:

| file | what it does |
|---|---|
| `perf_stages.py`, `stages.json` | B.1 — the stage breakdown, by wrapping the module attribute each caller actually looks up (the three oracles are imported *inside* `run_exact_pipeline`, so the source modules are what get wrapped). Nothing in the engine is modified. |
| `perf_one_request.py`, `onereq.log` | B.2 — one request per fresh process, because `ru_maxrss` is a high-water mark for the process's whole life |
| `perf_budget_expiry.py`, `budget_expiry.json` | B.1 — what a request returns when the budget expires |
| `scratch_app.py` | the scratch server: the real `app.main:app` with `_project_or_404` reading an in-memory dict of the eight briefs, so the measurement never writes `app/data/projects.json` and never goes near the live server |
| `perf_load.py`, `load.json` | B.3 and B.4 — N=1/2/4/8 and the production probes |
| `perf_mechanism.py`, `mechanism.json` | the GIL, from the server's own CPU percentage, and the plan that changes under load |
| `perf_eventloop.py`, `eventloop.json` | whether the asyncio loop is blocked |

Re-run with `cd backend && uv sync --group dev --extra local-model`,
`export OPENAI_API_KEY=not-a-real-key-ci-only`, and for the two load harnesses a scratch server:
`PYTHONPATH=<that data dir> uv run uvicorn scratch_app:app --host 127.0.0.1 --port 8731 --workers 1`.
The scratch server used for this report was stopped and its port released; port 8000 and pid 79460,
the live server, were never touched.
