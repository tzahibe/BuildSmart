# The preview cannot degrade production — the limit, the process, and the measurement (#246, ROOT #211)

**Verdict.** A brain request in the same process as production degrades it ×4 to ×4.3 on the median
and ×15 at worst (reproduced here, same protocol as #226). Served from **a second process**, production
stays at **1.63–1.64 s median and 1.76 s worst at 0, 2 and 4 concurrent brain requests, against 1.63 s /
1.66 s quiet** — inside the noise of its own quiet baseline. The server now also refuses a second
simultaneous brain request with a typed **429** in 18–19 ms instead of letting it run. Nothing in the
engine, the sizer, the validators or the ranking was touched.

| | what | where |
|---|---|---|
| limit | one gated preview request per process, typed 429, `Retry-After` | `backend/app/demo/preview_limit.py`, `backend/app/demo/router.py` |
| tests | 26, on the wire | `backend/tests/demo/test_brain_preview_concurrency.py` |
| process shape | a second process with the flag; production's process has it OFF | `docs/runbooks/brain-preview.md` §7 |
| harness | real uvicorn processes, real HTTP, #226's briefs and protocol | `backend/scripts/preview_isolation_proof.py` |
| raw results | `data/preview-isolation-{single,two,enforced}.json` | this directory |

---

## 1. The limit (AC-1, AC-2)

`BRAIN_PREVIEW_MAX_CONCURRENCY` — default **1**, read per request, clamped to
`MEASURED_MAX_CONCURRENCY = 1`. A larger value is clamped and logged; an empty, non-numeric or `< 1`
value is the default. The ceiling is a constant in code citing #226 B.3/B.4: at two concurrent
requests production's median is ×3.6 and its worst ×6.7, so no measured value above 1 is acceptable.
Raising it is a code change that cites a new measurement, the same rule `ALLOWED_FAMILIES` follows —
not an environment variable someone sets at 2 a.m.

**Refuse, not wait.** A brain request takes 31.6 s median and 48.9 s at worst (#226 B.1). A caller
queued behind another would wait 30–90 s — itself a bad answer — while holding a threadpool thread
and a connection, and a reverse proxy's own timeout would cut it with the work still running. A
refusal is instant, costs nothing and tells the truth: the preview is single-user. It is typed:
HTTP **429**, `code: BRAIN_PREVIEW_BUSY`, `Retry-After: 30`. Measured: **18–19 ms**, three times,
beside a request that was still running (`data/preview-isolation-enforced.json`).

The refusal reaches only an authorized caller: `_resolve_engine` runs first, so an unauthorized
probe still gets the byte-identical unknown-engine 422 and cannot learn from the limit that a
preview exists. Production and `concept_engine_v2` never take a slot and never queue behind one.
The streaming route takes its slot in the request frame (so the refusal is a 429 on the request, not
an error event in a started stream) and the *worker thread* releases it when the work is over, so a
client that disconnects mid-solve does not free a slot the solver is still using.

The count is per **process**, which is the right unit — the contention is for one process's GIL —
and is also why the preview must run **one worker** (`--workers N` would be N independent counters).

---

## 2. The process shape (AC-3)

**Chosen: a second `uvicorn` process running the same application, with `BRAIN_PREVIEW_ENABLED`
unset in the process that serves production.** Production's process then cannot run the brain at all:
`?engine=brain` there is the ordinary unknown-engine 422 (measured: 7–9 ms, byte-identical to
`?engine=banana`). The brain runs in a process of its own, with its own GIL and its own limit.

Why not the alternatives:

| shape | verdict |
|---|---|
| **second uvicorn** | no code in the request path beyond what exists; the isolation is the operating system's, and it is the shape the gate already supports (the flag is per process). **Chosen.** |
| worker pool / `ProcessPoolExecutor` inside one app | adds IPC, pickling of the project and a pool lifecycle to the request path, and production's process still supervises and shares a cgroup with the work. More code, same isolation as a second process. |
| subprocess per request | pays interpreter and scipy import (seconds) on every request, adds a launch path to the product, and still needs the limit. |
| `--workers N` on one uvicorn | the workers are processes, but a worker serves whichever request arrives: a brain request lands on a worker that is also serving production traffic. No isolation, N counters. |

**What this needs from the host.** A brain request holds one core for 30–49 s (#226 B.2), so the
host needs at least one core more than production alone uses. The measurement below was taken on 10
cores. On a one-core host a second process would not help; pin or cgroup it.

### The measurement

Protocol: #226's `perf_load.py` B.4 — production (`POST /projects/B09/design/demo`, no `engine`, the
path real traffic takes) measured quiet, then **while** N brain requests are in flight, then quiet
again as a drift check. Brain requests take #226's briefs in order (B11, B16, B19, B09, B02, B06, B08,
B20). Production is sampled back to back; only requests that **started after** the load did count as
under load, and requests still running when the load ended are kept (dropping them could only flatter
the result). Real uvicorn processes on loopback, real HTTP, the real app and the real HiGHS. The
harness runs three shapes from scratch:

* `single` — **the control**: one process serves both, the limit lifted to 4 *by the harness only*
  (`preview_limit.MEASURED_MAX_CONCURRENCY` patched inside the server process; no environment
  variable can do this). It is #226's condition. If it did not reproduce the degradation the other
  rows would prove nothing.
* `two` — the shipped process shape, with the preview process's limit **also lifted to 4** by the
  harness, so the rows for 2 and 4 are the **worst case** of the isolation, not the shipped
  configuration.
* `enforced` — the shipped configuration: two processes, limit 1, four requests offered at once.

Production latency (seconds; median / worst; n requests):

| concurrent brain requests | `single` (control) | `two` (second process) | `enforced` (limit 1, 4 offered) |
|---|---|---|---|
| 0 | 1.636 / 1.796 (10) | 1.628 / 1.632 (10) | 1.637 / 1.674 (10) |
| 2 | **6.838 / 26.078** (15) | **1.630 / 1.759** (57) | — |
| 4 | **7.084 / 26.619** (13) | **1.640 / 1.754** (80) | **1.634 / 1.707** (29) |
| 0 again | 1.654 / 1.701 (10) | 1.631 / 1.661 (10) | 1.631 / 1.667 (10) |

* **The control reproduces #226**: quiet 1.64 s (#226: 1.65 s), ×4.2 / ×4.3 on the median beside
  two / four brain requests (#226: ×3.6 / ×5.6), worst 26 s (#226: 17 s), and it recovers (1.65 s).
* **The second process removes it**: the median beside four brain requests is 1.640 s against a quiet
  1.628–1.631 s (+0.6 %); the worst is 1.754 s against a quiet worst of 1.661 s (+5.6 %, +0.09 s). The
  difference between the median under load and the quiet median is 0.002–0.012 s; the quiet phases
  themselves differ by 0.003 s. That is noise.
* **The limit does its job in the shipped configuration**: of four requests offered at once, one ran
  (47.8 s, 200) and three were refused in 18, 19 and 19 ms with `BRAIN_PREVIEW_BUSY`; production was
  1.634 s median throughout.
* **Brain requests still serialize inside their own process** (second-process rows, limit lifted:
  two requests took 61 s and 93 s; four took 51, 101, 101 and 132 s — against 48 s alone). So the
  limit remains right for the preview's *own* users and for the plan it shows (#226: B08 alone ships
  `PUBLIC_BAND+FOYER`, beside three others `TWO_HALL`): the second process protects production, the
  limit protects the preview from itself.

### Conditions, stated

* **The machine was not idle in the strict sense.** 10 cores, 1-minute load average 2.0–4.0 before and
  3.3–3.8 after each run (other work was active on the host; recorded in each JSON). The same-session
  control is the answer to that: it measured the same quiet baseline as #226's idle run (1.64 s vs
  1.65 s) and the same degradation (×4.2–×4.3 vs ×3.6–×5.6), so the contention that was present is
  not what moved the result. The second-process rows, run in the same conditions, did not move.
* The brain briefs and the production brief are #226's. Single run per shape; the noise figure above
  comes from the quiet phases inside each run, not from repeats.
* `two` lifts the limit through the harness only; `enforced` is the product as shipped.

Reproduce, from `backend/` (each takes 3–5 minutes, alone on the machine):

```
uv run python scripts/preview_isolation_proof.py single   --out ../docs/reports/architectural-brain/data/preview-isolation-single.json
uv run python scripts/preview_isolation_proof.py two      --out ../docs/reports/architectural-brain/data/preview-isolation-two.json
uv run python scripts/preview_isolation_proof.py enforced --out ../docs/reports/architectural-brain/data/preview-isolation-enforced.json
```

---

## 3. A liveness signal that fails when users are waiting (AC-4)

**Not shipped, and the reason is a measurement.** `/health` is a liveness probe that stays green while
a person waits: beside four brain requests in one process production took 7.1 s median and 26.6 s at
worst, and `/health` answered 200 every time (0.4 s median, 1.1 s worst). #226 saw the same on
`/docs` (26 ms). Three in-process probes were built and measured against exactly that condition,
each on the harness's `single` shape; none separates "users are waiting" from "users are not":

| probe design | quiet (production's own request running) | beside 2 / 4 brain requests | production's median meanwhile |
|---|---|---|---|
| time for a worker thread to start 1 ms of pure-Python work, red above 0.5 s | median 0.151 s | median 0.198 / 0.245 s; 2 of 81 samples red at 4 | 1.6 → 4.6 → 6.6 s |
| 20 ms of CPU work, wall-clock ÷ CPU time, red above ×3 (hop included) | ×7.2, **already red** at quiet | ×7.1 / ×6.9 | 1.6 → 7.0 → 7.0 s |
| 100 ms of CPU work timed inside the thread, wall ÷ CPU, red above ×3 | ×2.0 (worst 2.5) | median ×1.8 / ×2.0; worst 4.4 / 5.5, red in 8/65 and 10/88 | 1.7 → 8.1 → 8.0 s |

(These came from the console output of three harness iterations, not from retained files; the code
was removed, because a probe that does not move is the defect this section is about.) The mechanism
explains it: a thread that needs the GIL gets it back within milliseconds, it just gets a *share* of
it, and a request that needs 1.6 s of CPU takes four to five times longer under that share — an effect
that accumulates over a whole request and that no short, synthetic piece of work sees. Shipping a probe
that is green here would repeat the fault the Issue names: it would suppress the alarm.

**The accepted risk, and what covers it.**

1. In the shipped shape the question stops being asked of the production process: it carries no
   preview work, so its existing `/health` is honest about production (production was 1.63 s at 4
   concurrent brain requests, §2). The preview process's own waiting is **bounded** by the limit and
   **never queued**.
2. The signal that users are being turned away is already in the product: every refusal is a
   `BRAIN_PREVIEW_BUSY` 429 in the preview process's failure log and logger. A non-zero count means
   somebody asked for the preview while it was busy.
3. The only honest signal of real waiting is a **black-box** one from outside the process: time a
   canned production request (`POST /projects/<known project>/design/demo`, B09 in this report) on a
   schedule and alert above ×2 its quiet latency (1.63 s quiet, noise ±0.1 s → alert above ~3.3 s).
   That is the measurement this report used and it moved by ×4 in the control. It is an operator
   instruction in the runbook (§7.4), not code, because the right place for it is the host's monitor,
   and a request that runs production's engine every N seconds is a cost the owner should choose.

**Residual risk.** A deployment that runs the preview in production's process (flag ON there) gets no
latency alarm from anything in this repository. The runbook forbids that shape and the limit still
bounds it to one brain request, which the control shows is ×4 on the median, so it is not a safe
shape — only a bounded one.

---

## 4. Limits of this work

* **`failures.json` has two writers in the two-process shape.** It is a rewritten-whole JSON array
  guarded by a `threading.Lock`, which does not span processes, and `failure_log.set_path` is not
  reachable from the environment. A simultaneous production and preview refusal can lose one entry.
  Not changed here (out of scope, and R14 already names the file); the preview's own signal is the
  logger.
* **The projects store is a JSON file read per call.** Both processes read the same file; the demo
  route only reads it, so this is safe for the preview. A process that *writes* projects while the
  other reads is the existing single-writer assumption, unchanged.
* **Host CPU**: needs a free core (§2). Not testable in CI.
* **The request-bound defect** (the 30 s budget is not a request timeout) is #247 and is untouched.
* **No engine change**: `git diff` for this Issue touches `backend/app/demo/{preview_limit,router}.py`,
  one test file, one script, and documents. The 432-context regression is unaffected by construction
  (the limit applies only to `?engine=brain|e1_rear_band`), and was run (see the Issue's report).
