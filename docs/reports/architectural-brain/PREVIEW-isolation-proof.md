# `?engine=brain` — failure isolation, proven by measurement (#246, ROOT #211)

**The question.** #226 measured that a brain preview request degrades concurrent production
traffic. That measurement is the reason the readiness report says **NO-GO as it stands**, and this
issue is the GO blocker. The claim to be proven here is narrow and falsifiable:

> With a server-side concurrency limit of 1 and the preview served by a process that cannot take
> CPU from the process serving production, production's own latency at 0, 2 and 4 concurrent brain
> requests stays within noise of its quiet baseline.

**The answer: yes, and the margin is not a judgement call.** Production's median is **0.337–0.338 s
at every level of brain load**, against a quiet baseline of **0.347 s before** and **0.333 s
after**. The worst case under four requested brain requests (**0.379 s**) is *lower* than the worst
case with no brain load at all (**0.386 s**). In the same-session control, taken back to back with
the same protocol against the same brief on the same machine, the same load moved the median from
**0.329 s to 0.650 s** and the worst case from **0.365 s to 2.801 s**.

Nothing in the engine, the sizer, the validators or the ranking was changed. The plan the preview
returned is the same plan in every phase of both runs: `brain:PUBLIC_BAND+FOYER`.

---

## 1. The protocol, and why it is #226's

#226's protocol, repeated: **production's own latency, measured while N brain preview requests run
concurrently**, at N = 0, 1, 2, 4 and then 0 again — the recovery phase, which is what separates
contention from a leak.

* **Both servers are scratch servers**, plain `uvicorn`, **no `--reload`**, bound to `127.0.0.1`,
  on unused ports (branch **8751**, control **8752**). `BRAIN_PREVIEW_ENABLED` and
  `BRAIN_PREVIEW_TOKEN` were **exported in the starting shell and nowhere else** — neither tree has
  a `.env` at all — which is #231's harder configuration and the one where a mistake would show.
* **One at a time.** The control server was stopped and its port confirmed released before the
  branch server was started, so the two readings never competed.
* **The brief** is the gate suite's own: 3 bedrooms, 1 wet room, open plan, 132 m² on an 11.0 ×
  12.0 m footprint in a 19 × 20 m plot. A real brain request on it costs 26–33 s and 400–1100 MILP
  solves, so it is not a toy.
* **A production request** is `POST /projects/MEASURE/design/demo` with no `?engine=` at all — the
  traffic being protected, on the same server, through the same route.
* **Production requests are issued sequentially for the whole window** in which any brain request
  is still in flight, so every sample is a request that both started and finished beside the load.
* **A brain request** is the same URL with `?engine=brain` and the token header, one per thread.

The control is **a separate source tree at the branch's base commit `54f2b5b`**, extracted with
`git archive` (which touches no repository state), run with the branch's own virtual environment so
that the dependency set is identical and only the source differs. It has no
`app/demo/preview_isolation.py` at all, and its `/health` answers `{"status":"ok"}` with no
`preview` key — so the control is demonstrably the unchanged code.

### Load readings, as recorded

| | at the start | at the end |
|---|---|---|
| control run | `19:07 … load averages: 2.40 4.18 4.50` | `19:09 … 4.82 4.51 4.59` |
| branch run | `19:10 … load averages: 3.41 4.13 4.44` | `19:12 … 3.34 3.99 4.35` |

`agentctl status` reported **RUNNING (none)** and **WAITING (none)** immediately before both runs.
The only other load on the machine was a desktop session (Chrome and `WindowServer`, together
under one core) on a ten-core host.

**Stated rather than glossed:** the branch run began at a 1-minute load of **3.41**, above the
3.00 threshold this work set for itself, because the control run's own load was still decaying when
it started. Waiting for 3.00 would have broken "back to back in the same session", which is the
property that makes the two readings comparable at all. The branch therefore ran in the **more**
loaded half of the window, which makes its flatness a conservative result and not a flattered one.
Both runs sit inside the same decaying window and neither is a quiet-machine best case.

---

## 2. The control: the unchanged code, same session

| requested brain requests | production median | production worst | production best | samples | brain requests |
|---|---|---|---|---|---|
| 0 | **0.329 s** | 0.365 s | 0.324 s | 8 | — |
| 1 | 0.395 s | **2.206 s** | 0.337 s | 56 | 1 × 200 in 30.7 s |
| 2 | 0.494 s | 1.832 s | 0.352 s | 48 | 2 × 200 in 31.3 s |
| 4 | **0.650 s** | **2.801 s** | 0.400 s | 31 | 4 × 200 in 32.1–32.7 s |
| 0 again | 0.352 s | 0.411 s | 0.348 s | 8 | — |

**×1.98 on the median and ×7.67 on the worst case**, with a full recovery once the load stopped.
Every production request still returned 200; the damage is entirely in the clock.

The ratios are smaller than #226's ×3.6–×5.6, and the reason is the brief: a production request on
this one costs **0.33 s** against the 1.65 s of #226's. A cheaper baseline has less room to be
multiplied. The direction, the shape and the recovery are #226's exactly, and **one brain request
was already enough to take production's worst case from 0.365 s to 2.206 s** — ×6.0, with a single
preview request on the machine.

**The contention damaged the preview as well as production**, which #226 saw too and is worth
restating with numbers. Solves completed inside the same wall-clock budget, from the server's own
`buildsmart.preview` lines:

| control phase | solves per brain request |
|---|---|
| N=1 | 810 |
| N=2 | 786, 804 |
| N=4 | **392, 408, 415, 415** |

At four concurrent requests each one completed **roughly half** the search it completed alone. That
is the mechanism behind #226's finding that contention changes the plan the product shows: the
preview is a wall-clock-budgeted search, so less CPU is literally less searching.

---

## 3. The branch: a limit of 1, and a child process

| requested brain requests | production median | production worst | production best | samples | brain requests |
|---|---|---|---|---|---|
| 0 | 0.347 s | 0.386 s | 0.327 s | 8 | — |
| 1 | **0.337 s** | 0.378 s | 0.335 s | 68 | 1 × 200 in 26.7 s |
| 2 | **0.338 s** | 0.383 s | 0.334 s | 68 | 1 × 200 in 26.9 s · **1 × 503 in 6 ms** |
| 4 | **0.338 s** | **0.379 s** | 0.335 s | 68 | 1 × 200 in 26.8 s · **3 × 503 in 8–9 ms** |
| 0 again | 0.333 s | 0.334 s | 0.331 s | 8 | — |

**Production does not move.** The median varies by 1 ms across N=1, 2 and 4 and sits between the
two quiet baselines (0.347 s before, 0.333 s after). The worst case under load, 0.378–0.383 s, is
inside the quiet run's own worst case of 0.386 s. There is no degradation left to measure: the
spread under four requested brain requests is smaller than the spread of the baseline itself.

### Side by side

| | control | branch |
|---|---|---|
| production median, quiet | 0.329 s | 0.347 s |
| production median, 2 brain requests | 0.494 s (**×1.50**) | 0.338 s (**×0.97**) |
| production median, 4 brain requests | 0.650 s (**×1.98**) | 0.338 s (**×0.97**) |
| production worst, quiet | 0.365 s | 0.386 s |
| production worst, 1 brain request | 2.206 s (**×6.04**) | 0.378 s (**×0.98**) |
| production worst, 4 brain requests | 2.801 s (**×7.67**) | 0.379 s (**×0.98**) |
| solves per brain request, 4 requested | 392–415 | 1120 (the one admitted) |
| brain wall clock | 30.7–32.7 s | 26.7–26.9 s |

The **N=1 row is the one that isolates the process shape from the limit**, because at N=1 the limit
refuses nothing and both trees run exactly one brain request. Control ×6.04 on the worst case,
branch ×0.98. The separate process is doing that work on its own; the limit is what stops N=2 and
N=4 from being four of them.

The preview got **faster and searched more**: 1120 solves in 26.0 s against the control's best of
810 in 30.0 s. A child with its own interpreter, competing with production through the OS scheduler
rather than through the interpreter lock, gets more done — and the plan it returned is the same one
the control returned on every phase, `brain:PUBLIC_BAND+FOYER`.

---

## 4. The mechanism, refined — one of #226's statements does not survive this measurement

#226 reported that `scipy.optimize.milp` **holds the GIL**, that brain requests therefore
**serialize**, and that the server process sat at **107.3 % CPU with one** brain request and
**100.2 % with four** — one core, saturated. That reading implies the preview can never use more
than one core.

**This measurement does not reproduce that.** In the control, the server process's CPU went
**94.6 % quiet → 206.0 % with one brain request → 335.0 % with two → 498.0 % with four**, and the
four brain requests finished in **32.1–32.7 s** rather than serializing into the ~123 s that one
saturated core would require.

So on this host the solver stack **does** release the interpreter lock and does use more than one
core — the contention that damaged production was for **cores**, not only for the GIL. This is
reported as a correction to the mechanism, not to the conclusion: #226's **measured effect on
production** reproduced in the control with the same direction, the same shape and the same full
recovery, and that effect is what matters for the decision. The difference in the diagnosis makes
the fix *more* necessary rather than less, because a preview that can take two to five cores is a
preview that an in-process semaphore could never have contained.

Why the two readings differ is **not established here** and is listed as unverified in §8. A
plausible cause is a threaded BLAS or HiGHS build whose thread count depends on the environment the
process was started in, which would differ between #226's shell and this one. Nothing in this
issue's scope turns on it.

**Why a process, in one line, given the above:** the child is `nice`d +10, so the remaining
competition is resolved by the OS scheduler in production's favour — which is a thing an operating
system is good at and an interpreter lock cannot do at all.

---

## 5. The same thing at the process level, on a running server

A brain request in flight, the server's own output and `ps`, with no test harness anywhere:

```
--- health mid-request ---
{"status":"ok","preview":{"in_flight":1,"limit":1,"slots_free":0,"oldest_running_s":6.009}}

--- processes ---
  PID  PPID  %CPU  NI  COMMAND
35711     1   0.0   5  …/.venv/bin/python …/uvicorn app.main:app --port 8751
36529 35711 112.4  15  …/.venv/bin/python -m app.demo.preview_isolation

--- a second request, concurrently ---
{"detail":{"code":"PREVIEW_BUSY",
           "message":"התצוגה המוקדמת של המוח האדריכלי תפוסה כרגע בבקשה אחרת. נסו שוב בעוד דקה.",
           "detail":"preview concurrency limit 1 reached: 1 in flight, oldest running 6.1s"}}
second=503 0.002499

--- an unauthorized request, the same moment ---
{"detail":"unknown engine 'brain'; expected 'production' or 'concept_engine_v2'"}
unauth=422

first=200 26.731827

--- health after ---
{"status":"ok","preview":{"in_flight":0,"limit":1,"slots_free":1,"oldest_running_s":0.0}}
```

Six facts in one transcript:

1. **The work is in another process.** pid 36529, parent 35711, running `-m
   app.demo.preview_isolation`.
2. **The server process is idle while the preview works** — 0.0 % against the child's 112.4 %.
3. **The child is 10 nicer than its parent** (`NI` 15 against 5; the parent inherited 5 from the
   shell, and +10 is the delta the code sets). Production wins any contest for a core.
4. **A second simultaneous request is refused in 2.5 ms**, typed, with the limit and the age of the
   request it is behind in the detail. Not a 30-second wait, which would itself have been a bad
   answer.
5. **The refusal is not a new oracle.** At the same moment, with the only slot taken, an
   unauthorized `?engine=brain` got the one 422 that names no hidden engine — byte-identical to
   `?engine=banana`. Admission is checked after `preview_gate.authorized`, so an unauthorized
   prober cannot learn that a preview exists, let alone that it is busy.
6. **#233's health line survives the process boundary.** Three brain requests were served across
   the measurement and three `buildsmart.preview` lines appear in the *parent's* output, written by
   children whose stderr is inherited and which call `log_output.configure()` themselves:

   ```
   INFO  buildsmart.preview engine=brain sizer=exact families=band,spine,stack,cells \
     plan_sizer=exact plan_family=band budget_expired=true solves=1119 plans=8 partis=8 seconds=26.18
   ```

   This was the single most likely silent regression in the change — a logger in a fresh process
   starts out in exactly the no-handler state #233 was created to fix — and it is proven not to
   have happened rather than assumed.

---

## 6. Liveness: the smallest honest signal, and what was deliberately not done

#226's worst finding is not in the latency table. While four brain requests ran and real requests
took up to 16.87 s, **`/docs` answered in 26 ms median over 315 samples**. The event loop was never
what was blocked, so every probe stayed green. A probe that cannot see the harm does not merely
fail to help — it **suppresses the alarm it exists to raise**.

**What was implemented** (small, additive): `/health` now carries `preview` —
`in_flight`, the enforced `limit`, `slots_free`, and **`oldest_running_s`**. The last one is the
point: a count cannot tell a request that started a moment ago from one that has been running for
five minutes, and the transcript in §5 shows it reading `6.009` six seconds into a real request and
`0.0` after. An alert rule finally has a number.

**What was deliberately NOT done, and is recorded here as an accepted risk.** `/health` still
returns **200** with `"status": "ok"` while the preview is busy. It would have been easy to fail
the probe instead, and it would have been wrong:

* A failing liveness probe hands a supervisor an instruction to **restart the process serving
  production** — destroying the traffic the probe exists to protect.
* After this change the condition being reported no longer degrades production at all (§3). A probe
  that failed on it would be raising an alarm about something measured to be harmless, which is how
  probes get ignored.
* The dishonesty #226 found was not that the probe *passed*; it was that **nothing in the response
  mentioned the preview at all**, so no amount of reading it could reveal the problem. The fix for
  that is disclosure, and disclosure is what was added.

**Accepted risk, stated plainly:** `/health` will not go red for a user who is waiting. An operator
or an alert rule has to read `preview.oldest_running_s` and threshold it. Nothing in this branch
raises that alarm automatically, and a preview request legitimately takes 26–33 s, so what the
threshold should be is a question for #247 — which is the issue that makes the request's own bound
true — and not for this one.

---

## 7. What is proven, against the acceptance criteria

| AC | claim | where |
|---|---|---|
| AC-1 | a second concurrent brain request is bounded by the limit, default 1 | `tests/demo/test_brain_preview_concurrency.py` (36 tests); §5 item 4 on a real server |
| AC-2 | the limit cannot exceed the measurement, and the path is typed | `2`, `4`, `8`, `1000` and `" 4 "` all resolve to 1 (`preview_gate.MAX_CONCURRENCY_CEILING`); `PREVIEW_BUSY` + 503 + `Retry-After` |
| AC-3 | production stays within noise of its quiet baseline at 0, 2 and 4 | §3: medians 0.347 / 0.338 / 0.338 against 0.333–0.347 quiet; control §2 for the same protocol without the change |
| AC-4 | the liveness signal reflects real waiting, or its absence is an accepted risk with a reason | §6: `oldest_running_s` implemented; the 200 status recorded as an accepted risk |
| AC-5 | no engine, sizer or validator change | the diff touches `app/demo/` and `app/main.py` only; the plan returned is identical in every phase of both runs |
| AC-6 | the risk register and runbook carry the figures and the limit | `PREVIEW-operational-readiness.md` §6 (R9–R12), `docs/runbooks/brain-preview.md` §1 and §5 |

---

## 8. Not verified, and not claimed

1. **Why #226 measured one saturated core and this measured two to five** (§4). Both readings are
   reported; the cause is not established. The conclusion does not depend on it, and the
   un-diagnosed direction is the one that makes isolation more necessary.
2. **`#226`'s plan-change effect was not reproduced**, so it is not claimed to be fixed by
   measurement. This brief returned `brain:PUBLIC_BAND+FOYER` in every phase of both runs,
   including the contended control phases. What *is* true is structural: two brain requests can no
   longer run at once, so the condition that produced #226's B08 divergence cannot arise. The
   solve-count collapse in §2 (810 → ~400) is the same mechanism measured on a brief where it did
   not change the outcome.
3. **One brain request still uses more than one core** — 112.4 % in §5, up to 230.8 % of the
   server-plus-child total. Production was unaffected on a ten-core host with the child at +10
   niceness. **On a host with few cores this has not been measured**, and nothing here promises it.
4. **`seconds=26.0` with `budget_expired=true`** appears on the branch's lines where the control's
   read `seconds=30.0`, against a `REQUEST_BUDGET_S` of 30.0. Reported as observed. The request
   budget is #247's subject and was not touched.
5. **Latency figures are from one brief on one host, one run each.** The quiet baselines were taken
   twice per run and agree to 14 ms; the loaded phases were not repeated.
6. **The corpus regression was not run** (see the suite-numbers commit for which suites were).

---

## 9. Everything this measurement started, and that it is gone

* **The live server (pid 79460, port 8000) was never touched.** Confirmed still running at
  **0.0 % CPU**, up 27 days, from its own checkout `/Users/mymacbook/projects/sddproject/backend` —
  a different tree from the one this work used. Its `backend/.env` was never read or written.
* **Two scratch servers**, ports **8751** and **8752**, both stopped; both ports confirmed released
  with `lsof`.
* **No `app.demo.preview_isolation` child process left**, confirmed with `ps`.
* **The control source tree was removed.** It was a `git archive` extraction, so no worktree, no
  branch and no repository state was created or changed anywhere.
* No deploy, no restart, no live configuration, no spend, no `agentctl notify`, no merge.
