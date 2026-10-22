# Runbook — the Architectural Brain internal preview (`?engine=brain`)

For an operator who has read none of the work behind this. It assumes you can reach the server's
host, edit its `backend/.env`, and read the process's output. It assumes nothing else.

**What the preview is.** A per-request override that answers the *same* brief through the
Architectural Brain instead of the production engine, so its plans can be judged in the real UI.
It changes no default. Production is untouched whether the preview is on or off.

**Who may turn it on.** The owner. This runbook is the procedure, not the authorization. Merging,
deploying and restarting are all owner decisions (ROOT #211).

---

## 0. Before you enable anything — two preconditions

1. **The server's code must contain the gate.** Check:

   ```bash
   ls backend/app/demo/preview_gate.py
   ```

   If that file is **missing**, this server is from before PR #224 and **`?engine=brain` is itself
   the authorization on it** — anyone who can reach the port can request brain plans, and there is
   no flag to turn it off. Do not use the preview on such a server. Merge #224 first.

2. **The solver must be installed.** Check, in the server's own environment:

   ```bash
   cd backend && uv run python -c "from scipy.optimize import milp; import scipy; print(scipy.__version__)"
   ```

   Expect a version in `>=1.11,<2`. If this raises `ModuleNotFoundError`, the preview will still
   answer **200 with plans** — but they will be the *production* sizer's geometry under the brain's
   concepts, which is not what the preview is for. Fix it with `cd backend && uv sync` before
   showing anyone the result. See step 3 of "Verify".

---

## 1. Enable

Two environment variables. **Both** are required; either one missing means closed.

| variable | set it to |
|---|---|
| `BRAIN_PREVIEW_TOKEN` | a fresh secret — `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `BRAIN_PREVIEW_ENABLED` | `1` |

Optional, and only ever *narrowing*:

| variable | default | notes |
|---|---|---|
| `BRAIN_PREVIEW_FAMILIES` | `band,spine,stack,cells` | comma-separated. A name outside the allow-list is **dropped**, not honoured. Narrow to `band` to make the preview cheaper. |
| `BRAIN_PREVIEW_SIZER` | `exact` | `production` turns the brain's own sizer off while keeping its concepts. |

**Put them in `backend/.env`, not in your shell.** This matters, and it is the one thing in this
runbook that is easy to get wrong: a variable exported in the shell that started the server
**cannot be removed without stopping the process**, which makes the emergency disable in §3
unavailable to you. A variable that lives only in `.env` can be removed without a restart.

```bash
cd backend
cat >> .env <<'EOF'
BRAIN_PREVIEW_TOKEN=<the secret you just generated>
BRAIN_PREVIEW_ENABLED=1
EOF
```

Then make the server pick them up:

- **If it is running `uvicorn --reload`** (the documented way to run it): `touch` any `.py` file
  under `backend/app/` — `touch app/main.py` — and the reloader respawns the worker, which re-reads
  `.env`. No restart, no redeploy, in-flight requests finish.
- **If it is not running `--reload`**: the process must be restarted. That is an **owner decision**
  under ROOT #211. Stop here and ask.

`.env` is git-ignored. **Never commit the token.** `backend/.env.example` lists the four names with
empty values and is the file that belongs in git.

---

## 2. Verify, in three steps

The frontend's engine switch **cannot** send the header, so the preview is reachable from a tool
that can set one — not from the UI. That is deliberate.

**Step 1 — an authorized request is served.**

```bash
curl -si -X POST "http://HOST:8000/projects/PROJECT_ID/design/demo?engine=brain" \
  -H "X-Brain-Preview-Token: $BRAIN_PREVIEW_TOKEN" | head -1
```

Expect `HTTP/1.1 200 OK`. A `422` with `unknown engine 'brain'` means the preview is **closed** —
go back to §1 and check that the worker really re-read `.env` (the `pid` in the server's output
should have changed).

**Step 2 — an UNauthorized request is refused, and says nothing.**

```bash
curl -s -X POST "http://HOST:8000/projects/PROJECT_ID/design/demo?engine=brain" | head -c 200
```

Expect `unknown engine 'brain'; expected 'production' or 'concept_engine_v2'` — the *same* refusal
as `?engine=banana`. If the message *names* `'brain'` as an expected value, the gate is not doing
its job: close the preview and report it.

**Step 3 — the plan was made by the sizer you think it was.** This is the step people skip, and it
is the one that catches a preview that is quietly serving production's geometry.

```bash
# in the server's output
grep "engine=brain" <the server's log> | tail -5
```

A healthy line:

```
engine=brain sizer=exact families=band,spine,stack,cells plan_sizer=exact plan_family=spine \
  budget_expired=false solves=14 plans=3 partis=8 seconds=24.1
```

**`plan_sizer=exact` is the health signal.** `plan_sizer=production` with an `exact_refusal=…`
field means the brain's *concepts* are being shown with the *production* sizer's geometry — see §5
for what each refusal code means. The same facts are also on every plan in the response, as a note
reading `sized by the production sizer (band layout)`.

---

## 3. EMERGENCY DISABLE — the fastest path, no deployment

**Lever A — close the preview** (use this by default):

```bash
cd backend
# blank the line; do not just delete it, so the next person sees that it exists
sed -i '' 's/^BRAIN_PREVIEW_ENABLED=.*/BRAIN_PREVIEW_ENABLED=/' .env
touch app/main.py          # --reload respawns the worker, which re-reads .env
```

**Lever B — revoke the secret** (use this instead if the token may have leaked):

```bash
sed -i '' 's/^BRAIN_PREVIEW_TOKEN=.*/BRAIN_PREVIEW_TOKEN=/' .env
touch app/main.py
```

An unset or empty token authorizes **nobody**, so lever B also closes the preview — and it
invalidates the leaked secret, which lever A does not. Either way the very next request gets the
ordinary unknown-engine 422. Nothing caches the decision; there is no third state and no grace
period.

Confirm:

```bash
curl -s -X POST ".../design/demo?engine=brain" -H "X-Brain-Preview-Token: $OLD" | head -c 120
# expect: unknown engine 'brain'; expected 'production' or 'concept_engine_v2'
```

### Read this before you need it

- **Editing `.env` alone is not enough.** A running worker does not re-read it. Measured: blanking
  both lines and waiting left the preview fully open on the same pid. The `touch` is what closes
  it, because it makes the reloader start a worker that re-reads `.env`.
- **If the variables were exported in the shell that started the server, neither lever works.**
  Measured: removing them from `.env` and forcing a reload left the preview open, because
  `load_dotenv()` does not override what the process already has, and a respawned worker inherits
  the parent's environment. The only disable is then **stopping the process** — an owner decision
  under ROOT #211. This is why §1 says to put the variables in `.env`.
- **The absolute fallback, if you cannot wait for an owner:** the preview cannot serve a request a
  request cannot reach. Blocking the port, or stopping the process, are the only levers that do not
  depend on how the variables were set. Both are owner decisions. Say which one you need and why.

---

## 4. Rollback

In increasing order of cost. Stop at the first one that fixes your problem.

| # | action | what it costs | when |
|---|---|---|---|
| 1 | **Close the preview** (§3). | nothing. Production is unaffected — it never reads these variables. | anything wrong with the preview |
| 2 | **Narrow it.** `BRAIN_PREVIEW_FAMILIES=band`, then `touch app/main.py`. | the cross-band families are not shown | the preview is too slow, or a non-band family produces bad plans |
| 3 | **Turn the brain's own sizer off.** `BRAIN_PREVIEW_SIZER=production`, then `touch`. | the brain's concepts stay, its geometry does not | the exact sizer is refusing or misbehaving and you still want the concepts |
| 4 | **Revert the code.** Revert PR #224 and the brain's preview seam. | a merge and a deploy — **owner decision** | a defect in the gate itself, or in `_resolve_engine` |

There is nothing to roll *back* in production: the preview adds a per-request branch and a module
that production never calls. No default moved, no validator changed, no stored data differs.
Closing the preview is a complete rollback of its behaviour.

---

## 5. What to watch, and what to do about each failure

One line is written per brain request, to the logger `buildsmart.preview`, in the server's own
output. Served requests are **INFO**; a request that produced **no plan** is **WARNING**.

```
engine=brain sizer=exact families=… plan_sizer=… plan_family=… [exact_refusal=…] \
  budget_expired=… solves=N plans=N partis=N seconds=N [code=…]
```

| field | watch for |
|---|---|
| `plan_sizer` | anything other than `exact` while `sizer=exact` — the preview has degraded |
| `exact_refusal` | **any** value; the table below says what each means |
| `budget_expired` | `true` repeatedly — the brief is too big for the budget |
| `solves` | `0` together with `exact_refusal` — no solve ran at all |
| `code` | present at all; the request returned no plan |
| `plans` | `1` where you expect several — the partis are converging on one geometry |

Refusals also land in the product's failure log (`backend/app/data/failures.json`, summary via
`failure_log.summary()`), now with an `engine` field, so a preview refusal can be told apart from a
production one.

### The typed failures, and the action for each

| what you see | what it means | what to do |
|---|---|---|
| `exact_refusal=EXACT_SIZER_UNAVAILABLE`, `solves=0` | **scipy is not installed** in the server's environment. The brief is fine. Every plan shown is the production sizer's geometry. | `cd backend && uv sync`, then `touch app/main.py`. Re-run Verify step 3. Treat any architectural judgment made while this was showing as void. |
| `exact_refusal=EXACT_SIZER_UNKNOWN`, `solves` > 0 | every MILP solve hit its time limit. The solver is installed and the brief is too hard for the budget — usually a 12-room-plus brief. | Not a defect. Narrow `BRAIN_PREVIEW_FAMILIES` to `band`, or judge this brief from production's plans. If it happens on *every* brief, the host is overloaded — see #226's measurements. |
| `exact_refusal=NO_EXACT_PLAN` + `budget_expired=true` | the budget ran out before a solve could finish. | as above. |
| `exact_refusal=NO_EXACT_PLAN`, `budget_expired=false`, `solves` > 0 | placements were found and **none survived the validators or graph preservation**. A geometric result, not an operational one. | Nothing to do operationally. Worth reporting with the brief — it is the engine's own limit and the plan's notes name the constraint. |
| `exact_refusal=TOPOLOGY_NON_PLANAR` or `TOPOLOGY_REPRESENTATION_LIMIT` | the parti's required adjacencies **cannot** be drawn with rectangles at all (a K4, or three rooms each touching the same two). A proof, not a timeout. | Nothing to do. Expected on some briefs. |
| `exact_refusal=BAND_UNSAT` | no band layout carries every required contact; the search was complete. | Nothing to do. |
| `exact_refusal=EMBEDDING_SEARCH_EXHAUSTED` | the embedder's node bound stopped the search. **Not** a proof of impossibility. | Nothing to do operationally; report the brief if its plans look impoverished. |
| `exact_refusal=INVALID_INPUT` | a malformed parti (an edge naming a room that is not in the programme, a self-adjacency). | **Report it** — this is a defect in the proposer, not a configuration problem. |
| `code=BRAIN_NO_PLAN` + HTTP **422** | no parti produced a plan at all. The response's `detail` leads with the exact sizer's code and then names each parti, its stage and its reason. The failure log has the whole brief. | Read the first code in `detail`: if it is `EXACT_SIZER_UNAVAILABLE`, see row 1 — the real cause is the environment. Otherwise it is a brief the brain cannot plan; production's own engine is unaffected and can still serve it (just omit `?engine=brain`). |
| HTTP **422** `unknown engine 'brain'` when you expected 200 | the preview is **closed**: the flag is off, or the token is missing/wrong/stale. Indistinguishable, on purpose, from an engine that does not exist. | Re-do §1. Check the `pid` changed after the `touch`. |
| HTTP **500** | a defect. The failure log has the traceback and an `engine` field naming the preview. | Close the preview (§3) and report with the failure-log entry. |
| a slow request | the preview's budget is **30 s of wall clock by design**, against production's sub-second path. | Not a defect by itself. Latency, CPU and concurrency are measured in Issue #226 and #246 (§7) — do not draw conclusions from a stopwatch on a busy host. |
| HTTP **429** `code=BRAIN_PREVIEW_BUSY`, `Retry-After: 30` | another preview request is running **in this process**. The limit is one, by measurement (§7). The refusal is instant and nothing was started. | Wait the `Retry-After` and retry. Not a defect. If it is refused when **nobody** is using the preview, a worker thread died holding the slot — restart the preview process. Do **not** try to raise the limit (§7). |

### Never do these

- **Never log, paste or echo `BRAIN_PREVIEW_TOKEN`**, including a wrong one someone tried. No code
  path writes it down and no diagnostic needs it.
- **Never commit `.env`.**
- **Never widen `BRAIN_PREVIEW_FAMILIES`** hoping to add a family. It is an allow-list; names
  outside it are dropped. `generator` in particular took a gate verdict of STOP and no environment
  variable can show it to anyone.
- **Never switch the default engine** to reach the brain. The preview is per request, on purpose.

---

## 7. Concurrency and the process shape — the preview must not slow production (#246)

**Measured, not argued** (`docs/reports/architectural-brain/PREVIEW-isolation-proof.md`, #226's
protocol, real processes over HTTP). Production's median latency, quiet 1.64 s:

| brain requests at once | same process as production | preview in a **second process** |
|---|---|---|
| 2 | **6.84 s** median, 26.1 s worst (×4.2 / ×15) | 1.63 s median, 1.76 s worst |
| 4 | **7.08 s** median, 26.6 s worst (×4.3 / ×15) | 1.64 s median, 1.75 s worst |

The cause is the GIL: HiGHS holds it, so brain requests serialize (four took 51–145 s each) and take
production's CPU with them. The event loop is *not* blocked, so `/health` stays green while a person
waits 26 s (§7.4).

### 7.1 The limit — enforced in the server, one request at a time

| | |
|---|---|
| `BRAIN_PREVIEW_MAX_CONCURRENCY` | optional, default **1**, read on every request |
| ceiling | **1**, a constant in `backend/app/demo/preview_limit.py` (`MEASURED_MAX_CONCURRENCY`). A bigger value is **clamped to 1 and logged**; empty, non-numeric or `< 1` means 1. |
| scope | `?engine=brain` and `?engine=e1_rear_band`. Production and `concept_engine_v2` never take a slot. |
| a second request | **refused, not queued**: HTTP 429, `code=BRAIN_PREVIEW_BUSY`, `Retry-After: 30`, in about 20 ms. A request queued behind a 30–49 s brain request would itself be a 30–90 s wait. |
| who sees it | only an **authorized** caller. An unauthorized one still gets the unknown-engine 422. |

**Do not try to raise it.** There is no supported value above 1: two concurrent requests were
measured at ×3.6–×4.2 on production's median. Raising the ceiling is a code change that must cite a
new measurement.

### 7.2 The process shape — two processes, the flag in only one of them

Run the preview as **a second `uvicorn` on its own port, one worker**, and keep
`BRAIN_PREVIEW_ENABLED` / `BRAIN_PREVIEW_TOKEN` out of the process that serves production:

```bash
# production — as today. No BRAIN_PREVIEW_* anywhere in its environment.
uvicorn app.main:app --port 8000

# preview — its own process, its own port, ONE worker (the limit is per process)
BRAIN_PREVIEW_ENABLED=1 BRAIN_PREVIEW_TOKEN=<secret> uvicorn app.main:app --port 8001 --workers 1
```

* Send `?engine=brain` requests to **8001**. Production's process refuses them as an unknown engine
  (measured: 7–9 ms, byte-identical to `?engine=banana`), so a request that lands on the wrong port is
  harmless.
* Never pass `--workers N` (N > 1) to the preview: the limit is per process, so N workers are N
  independent counters, and a brain request would land on a worker that is also serving traffic.
* The host needs a **free core** for the preview (a brain request holds one for 30–49 s). On a
  one-core host a second process does not help.
* The §1 note about putting the variables in `backend/.env` applies to the preview process only; in
  this shape the §3 emergency levers act on port 8001, and **closing the preview never touches
  production**.
* The two processes read the same projects file and write the same `failures.json`. The failure log
  has a thread lock, not a process lock, so a simultaneous production and preview refusal can lose one
  entry. The preview's own logger is the signal that does not.

### 7.3 Confirm the shape

1. `curl -s -X POST "http://HOST:8000/projects/ID/design/demo?engine=brain" -H "X-Brain-Preview-Token: $T"`
   against the **production** port must be the unknown-engine 422. A 200 means the flag is set in
   production's process — fix it before anything else.
2. Two brain requests at once against **8001**: one runs, the other gets `429 BRAIN_PREVIEW_BUSY`.
3. Production's latency while a brain request runs on 8001 should be its quiet latency. To measure it
   properly, alone on the machine: `cd backend && uv run python scripts/preview_isolation_proof.py
   enforced --out /tmp/isolation.json`.

### 7.4 Watching for real waiting — a liveness probe that is honest

`/health` and `/docs` answer in milliseconds while production requests take 26 s: they prove the event
loop turns, not that anyone is being served. Three in-process probes were tried and none separated the
two states (proof report §3), so **none is shipped**. What is honest:

* **Black-box**: from outside the server, time a canned production request on a schedule —
  `POST /projects/<a stored project>/design/demo` with no `engine` (1.63 s quiet on the measured
  host, ±0.1 s) — and alert above about twice its quiet latency. This is the only signal that moved in
  every measurement. Calibrate the threshold on your host; the number above is not portable.
* **Turned-away users**: every refusal is a `BRAIN_PREVIEW_BUSY` 429 in the preview process's log.
* In the two-process shape production's process carries no preview work, so `/health` on port 8000 is
  honest about production again. If the flag is ever set there, **there is no alarm** — treat it as an
  incident.

---

## 8. Reference

| | |
|---|---|
| the gate | `backend/app/demo/preview_gate.py` |
| the one call site | `backend/app/demo/router.py::_resolve_engine` |
| the brain | `backend/app/vertical_slice/brain/` (`runner.py`, `exact_pipeline.py`) |
| the preview's log line | `backend/app/observability/preview_log.py` |
| the failure log | `backend/app/observability/failure_log.py` |
| design of the gate | `docs/wiki/architecture/engine-preview-gate.md` |
| the concurrency limit | `backend/app/demo/preview_limit.py` |
| the isolation measurement and its harness | `docs/reports/architectural-brain/PREVIEW-isolation-proof.md`, `backend/scripts/preview_isolation_proof.py` |
| the evidence behind this runbook | `docs/reports/architectural-brain/PREVIEW-operational-readiness.md` |
| the variables, with empty values | `backend/.env.example` |
