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
| `BRAIN_PREVIEW_KILL_FILE` | unset | an **extra** path whose existence closes the preview. Only for a host where `backend/` is not writable; `backend/DISABLE_BRAIN_PREVIEW` works whatever this says. See §3. |

**Prefer `backend/.env` to your shell.** A variable exported in the shell that started the server
**cannot be removed without stopping the process** — a process's environment cannot be changed from
outside it — so a variable in `.env` is the one you can also *change* later. It no longer decides
whether you can **close** the preview: §3's kill switch closes it either way, and that is the lever
to reach for first. (Before #231 it did decide, and the preview could not be closed at all in the
exported case. See §3.)

```bash
cd backend
cat >> .env <<'EOF'
BRAIN_PREVIEW_TOKEN=<the secret you just generated>
BRAIN_PREVIEW_ENABLED=1
EOF
ls DISABLE_BRAIN_PREVIEW    # must be "No such file": the kill switch (§3) overrides both variables
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

## 3. EMERGENCY DISABLE — one command, no deployment

**Lever A — the kill switch. Create a file. This is the one to use.**

```bash
cd backend
touch DISABLE_BRAIN_PREVIEW
```

That is the whole procedure. The **next request** is refused, in the **same process**: no restart,
no reload, no redeploy, no variable unset, and **no cooperation from however the preview was
switched on**. It works when the variables were exported in the shell that started the server,
which is the case where nothing else does (see "Read this before you need it"). `backend/` here is
the directory that holds `.env` — the same one you were in for §1 — and the path the running server
checks is derived from its own code's location, so it is that directory whatever the server's
working directory is. To print it from the server's own environment:

```bash
cd backend && uv run python -c "from app.demo import preview_gate as g; print(g.kill_file_paths())"
```

Nothing reads the file's **contents**; its existence is the signal, so an empty file, a note to the
next person, or a directory all work. If `backend/` is read-only on this host, set
`BRAIN_PREVIEW_KILL_FILE` to a path you can write and `touch` that instead — it **adds** a
location, it does not move the built-in one, so `backend/DISABLE_BRAIN_PREVIEW` keeps working
whatever that variable says.

**If the check cannot decide, the preview is closed.** An unreadable path, a permission error, a
stale mount, a mis-set `BRAIN_PREVIEW_KILL_FILE`: every one of them refuses. You can over-apply
this lever; you cannot break it open.

**To re-open:** `rm backend/DISABLE_BRAIN_PREVIEW`. Nothing is remembered, so the next request is
served again — provided the flag and the token are still set. Deleting the file grants nothing on
its own.

**Lever B — revoke the secret** (do this *as well*, if the token may have leaked — lever A closes
the door, it does not change the lock):

```bash
sed -i '' 's/^BRAIN_PREVIEW_TOKEN=.*/BRAIN_PREVIEW_TOKEN=/' .env
touch app/main.py          # --reload respawns the worker, which re-reads .env
```

**Lever C — blank the flag** (the tidy, non-urgent close, once the incident is over):

```bash
sed -i '' 's/^BRAIN_PREVIEW_ENABLED=.*/BRAIN_PREVIEW_ENABLED=/' .env
touch app/main.py
```

Levers B and C depend on the variables living in `.env` **and** on the worker re-reading it; lever
A depends on neither. Use A first, always. Follow with B if the secret is the problem.

Confirm, whichever you used:

```bash
curl -s -X POST ".../design/demo?engine=brain" -H "X-Brain-Preview-Token: $OLD" | head -c 120
# expect: unknown engine 'brain'; expected 'production' or 'concept_engine_v2'
```

That refusal is the ordinary unknown-engine 422 — identical, byte for byte, to what
`?engine=banana` gets. A closed preview and a kill-switched preview are indistinguishable from
outside, on purpose: the refusal must not tell a prober that there is something here to come back
for.

### Read this before you need it

- **The kill switch is the only lever that does not depend on how the preview was turned on.** Use
  it first. The two `.env` levers are for tidying up and for revoking a leaked secret.
- **Editing `.env` alone is not enough.** A running worker does not re-read it. Measured (#214):
  blanking both lines and waiting left the preview fully open on the same pid. The `touch` is what
  closes it, because it makes the reloader start a worker that re-reads `.env`.
- **If the variables were exported in the shell that started the server, neither `.env` lever
  works at all.** Measured (#214): removing them from `.env` *and* forcing a reload left the
  preview **open**, because `load_dotenv()` does not override what the process already has and a
  respawned worker inherits its parent's environment. A process's `os.environ` cannot be changed
  from outside the process by anything. **Before #231 the only disable in that configuration was
  stopping the process** — an owner decision under ROOT #211, and the reason PR #224's "unset
  either variable and it closes" was wrong. The kill switch in lever A is what replaced it: it
  beats an exported, truthy `BRAIN_PREVIEW_ENABLED`, measured on a running server in
  `docs/reports/architectural-brain/PREVIEW-killswitch-proof.md` (same pid throughout).
- **If the server is not running `--reload`**, levers B and C cannot take effect at all without a
  restart. Lever A still can. This is the configuration a real deployment is most likely to be in.
- **The absolute fallback:** blocking the port or stopping the process. Both are owner decisions,
  and after #231 neither should be necessary to close the preview. Say which one you need and why.

---

## 4. Rollback

In increasing order of cost. Stop at the first one that fixes your problem.

| # | action | what it costs | when |
|---|---|---|---|
| 1 | **Close the preview** — `touch backend/DISABLE_BRAIN_PREVIEW` (§3). | nothing. Production is unaffected — it never reads these variables, and never consults the kill switch. | anything wrong with the preview |
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
| HTTP **422** `unknown engine 'brain'` when you expected 200 | the preview is **closed**: the kill switch is on, or the flag is off, or the token is missing/wrong/stale. Indistinguishable, on purpose, from an engine that does not exist. | First `ls backend/DISABLE_BRAIN_PREVIEW` — somebody closed the preview, or a crashed run left the file behind. Then re-do §1, and check the `pid` changed after the `touch`. |
| HTTP **500** | a defect. The failure log has the traceback and an `engine` field naming the preview. | Close the preview (§3) and report with the failure-log entry. |
| a slow request | the preview's budget is **30 s of wall clock by design**, against production's sub-second path. | Not a defect by itself. Latency, CPU and concurrency are measured in Issue #226, not here — do not draw conclusions from a stopwatch on a busy host. |

### Never do these

- **Never log, paste or echo `BRAIN_PREVIEW_TOKEN`**, including a wrong one someone tried. No code
  path writes it down and no diagnostic needs it.
- **Never commit `.env`.**
- **Never widen `BRAIN_PREVIEW_FAMILIES`** hoping to add a family. It is an allow-list; names
  outside it are dropped. `generator` in particular took a gate verdict of STOP and no environment
  variable can show it to anyone.
- **Never switch the default engine** to reach the brain. The preview is per request, on purpose.

---

## 6. Reference

| | |
|---|---|
| the gate | `backend/app/demo/preview_gate.py` |
| the one call site | `backend/app/demo/router.py::_resolve_engine` |
| the brain | `backend/app/vertical_slice/brain/` (`runner.py`, `exact_pipeline.py`) |
| the preview's log line | `backend/app/observability/preview_log.py` |
| the failure log | `backend/app/observability/failure_log.py` |
| design of the gate | `docs/wiki/architecture/engine-preview-gate.md` |
| the evidence behind this runbook | `docs/reports/architectural-brain/PREVIEW-operational-readiness.md` |
| the variables, with empty values | `backend/.env.example` |
| the kill switch's own evidence, on a running server | `docs/reports/architectural-brain/PREVIEW-killswitch-proof.md` |
