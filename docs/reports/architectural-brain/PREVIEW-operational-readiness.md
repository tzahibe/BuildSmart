# `?engine=brain` — operational readiness of the internal preview (#214, ROOT #211 §4)

Branch `feature/brain-ops-readiness`, stacked on `feature/brain-preview-gate` (PR #224, #212's
gate), so everything below describes the **real** flag rather than a proposed one.

**What this report is not.** The latency, CPU, memory, concurrency and failure-isolation
measurements are **#226's**, which runs alone on an idle machine. Two measurements on this machine
have already been corrupted by contention, so nothing here was timed: every wall-clock-triggered
path was *constructed* (a deadline already in the past, a hand-built result carrying the budget
warning) instead of raced for. Where a risk is a measured one, the register below says
**deferred → #226** and gives no number.

The operator-facing procedure is `docs/runbooks/brain-preview.md`. This file is the evidence.

---

## 1. Every typed failure and fallback, constructed

`backend/tests/vertical_slice/test_brain_fallbacks.py` — **26 passed**. Each row was built in a
test, not read off the source. "Caller" is what comes back on the wire; "logged" is what the server
writes down **with this branch's observability in place** (§2 says what it was before).

| # | typed outcome | where it is decided | how it is triggered | what the CALLER sees | what is LOGGED | does the plan name its maker? |
|---|---|---|---|---|---|---|
| 1 | `EXACT_SIZER_UNAVAILABLE` / stage `SIZING` | `exact_pipeline.run_exact_pipeline`, the solver import | `scipy` absent from the environment | **200 OK** with plans. Every plan's notes: `sized by the production sizer (band layout)` **and** `exact sizer fell back to production: EXACT_SIZER_UNAVAILABLE: scipy is not installed (…)` | `engine=brain … plan_sizer=production plan_family=band exact_refusal=EXACT_SIZER_UNAVAILABLE solves=0` | yes — production / band |
| 2 | `EXACT_SIZER_UNKNOWN` / `SIZING` | `run_exact_pipeline`, after the loop | every MILP solve returns `UNKNOWN` (its time limit) and nothing was realized | 200 OK, production-sized plans, the code in the notes | same line, `exact_refusal=EXACT_SIZER_UNKNOWN`, `solves` > 0 | yes |
| 3 | `NO_EXACT_PLAN` / `SIZING` | ditto | the request budget was gone before a solve could run (`candidates_tried` 0) | 200 OK, production-sized, plus the warning `request budget reached after N s; later candidates and families were not sized` | `exact_refusal=NO_EXACT_PLAN budget_expired=true` | yes |
| 4 | `NO_EXACT_PLAN` / `REALIZATION` | ditto | placements realized, none kept (a validator or preservation refused each); the histogram names the constraint | 200 OK, production-sized | `exact_refusal=NO_EXACT_PLAN`, `solves` > 0 | yes |
| 5 | `TOPOLOGY_NON_PLANAR` / `EMBEDDING` | `band_embedding.representation_precheck`, **passed through verbatim** | a non-planar required-contact graph | 200 OK, production-sized, the embedder's own code and sentence in the notes | `exact_refusal=TOPOLOGY_NON_PLANAR` | yes |
| 6 | `TOPOLOGY_REPRESENTATION_LIMIT` / `EMBEDDING` | ditto | a K4 (four mutually touching rooms) or a triple-lens | as above | as above | yes |
| 7 | `BAND_UNSAT` / `EMBEDDING` | `band_embedding.embed_band`, search complete | no band layout carries every required pair | as above | as above | yes |
| 8 | `EMBEDDING_SEARCH_EXHAUSTED` / `EMBEDDING` | ditto, search bound hit | the node limit stopped the search — **not** a proof of impossibility | as above | as above | yes |
| 9 | `INVALID_INPUT` / `EMBEDDING` | ditto | a self-adjacency, an edge naming an unknown room, or no rooms | as above | as above | yes |
| 10 | the production-sizer **fallback** itself | `runner._one`, `fallback=True` | any of rows 1–9 | 200 OK — the preview **never loses a parti production can plan** | the row's own `exact_refusal` | yes, and the note says what it fell back *from* |
| 11 | the exact refusal **as a plan** (stage `UNAVAILABLE` / the diagnosis' own stage) | `runner._one`, `fallback=False` | rows 1–9 inside `_improve_exactly`, which already holds production's plan | nothing directly — production's plan is kept | as above | n/a (the plan did not realize) |
| 12 | the exact plan **does not count** | `runner._improve_exactly` | the exact plan's area verdict is unacceptable, or preservation is not n/n | 200 OK, production's plan, note: `exact sizer's spine plan did not count (area\|preservation); production kept` | `plan_sizer=production`, the declined attempt's `solves` still counted | yes |
| 13 | the exact plan **ranks below** production's | ditto | its preference key is worse | 200 OK, production's plan, note naming **both** keys in words (`arrival ok, street ok, area in tolerance, rooms N %, circulation N %`) | as above | yes |
| 14 | the exact plan **wins** | ditto | it counts and its key is no worse | 200 OK, note: `exact sizer improved on production's plan` or `… planned what production could not (…)` | `plan_sizer=exact plan_family=band\|spine\|stack\|cells` | yes |
| 15 | stage `CRITIC` | `runner._one`, **before any placement** | a parti with a HARD critic finding (e.g. `NO_ENTRANCE_ACCESS`) | that parti is simply absent from the offered plans | counted in `partis` but not `plans`; `solves=0` for it | n/a |
| 16 | the **production** sizer also refuses | `runner._one`, after the widening ladder | `_pipeline` returns a diagnosis for every rung | → row 17 | the parti's code and stage in `BRAIN_NO_PLAN`'s detail | n/a |
| 17 | `BRAIN_NO_PLAN` | `demo/service.py::_brain_result` | `res.distinct` is empty — no parti produced a distinct, counting plan | **422** `{code: BRAIN_NO_PLAN, message: <Hebrew, names no cause>, detail: "exact sizer: <CODE> \| <parti> [<stage>]: <reason>; …"}` | `failure_log` REFUSAL with the full brief context **and `engine: brain`**, plus a **WARNING** preview line carrying `code=BRAIN_NO_PLAN` | n/a |
| 18 | `unknown engine '<value>'` | `demo/router._resolve_engine` (#212) | the flag is off, or the token is missing/wrong | **422**, byte-identical to a genuinely unknown engine name | nothing engine-specific — deliberately, so the log is not an oracle either | n/a |
| 19 | an unhandled exception | `app/main.py`'s handler | a defect | 500 with the generic Hebrew sentence | `failure_log` CRASH with the traceback **and `engine: brain`** (new: it was indistinguishable from a production crash) | n/a |

Two neighbours of the same seam, for completeness — they are `?engine=e1_rear_band`'s, not the
brain's, and are gated by the same check: `E1_REAR_BAND_UNAVAILABLE` (the adapter did not solve)
and `E1_REAR_BAND_NOT_PLANNABLE` (no rear-band candidate realized), both 422.

### Paths that could not be constructed

None. Every row above was built in a test. Two are worth naming because the *trigger* was replaced
rather than reproduced:

- **Rows 2 and 3's real-world trigger is the clock.** Row 2 is constructed by making every solve
  answer `UNKNOWN`; row 3 by a deadline already in the past. A *race* to a genuine mid-request
  budget expiry is a timing measurement and belongs to #226. The plumbing that carries the fact out
  (`_exact_counters`) is tested on both result shapes with no clock involved.
- **Row 1 is simulated in the suite** (the solver import blocked through `sys.modules`) **and
  proven for real** in §3, in a virtualenv that genuinely has no scipy.

---

## 2. Observability: the gap, and what was done about it

### What a brain request emitted before this branch

| question an operator asks | answerable before? |
|---|---|
| did a brain request happen at all? | **no** — nothing is written on success |
| which engine served it? | only by inference from a *refusal* code; a CRASH said nothing |
| which sizer and family made the plan that was shown? | **no** — it was in the response notes, i.e. on the caller's screen, and nowhere else |
| did the request budget expire? | **no** — a sentence in the response notes only |
| how many solves ran? | **no** — the pipeline built the tallies and `runner` discarded them |
| which typed refusal came back? | **no** on success; and on `BRAIN_NO_PLAN` the detail was built from each parti's *production* reason, so a request with **no solver at all** was recorded as "could not plan" with the real cause nowhere |

The last row is the sharp end. §3 below returns **200 OK** with eight plans from a server that has
no MILP solver installed — architecturally, production's plans under the brain's name. From every
log the server kept, that was indistinguishable from a healthy preview.

### The change (smallest additive)

`backend/app/observability/preview_log.py` — **one line per brain request**, on both paths:

```
engine=brain sizer=exact families=band,spine,stack,cells plan_sizer=exact plan_family=spine \
  budget_expired=false solves=14 plans=3 partis=8 seconds=24.1
engine=brain sizer=exact families=band,spine plan_sizer=production plan_family=band \
  exact_refusal=EXACT_SIZER_UNAVAILABLE budget_expired=false solves=0 plans=3 partis=8 seconds=1.9
engine=brain sizer=exact families=band exact_refusal=NO_EXACT_PLAN solves=6 partis=8 \
  seconds=12.4 code=BRAIN_NO_PLAN
```

- A **logger** (`buildsmart.preview`), not a file. `failure_log` keeps a JSON file because a failure
  is a question to ask later; a per-request health signal is read live, which is what the process's
  stdout already is — *provided something is listening*, which it was not until **#233** gave the
  `buildsmart` namespace a handler (`app/observability/log_output.py`). Everything shown above was
  emitted by this branch and arrived nowhere — and writing successes into `failures.json` would corrupt
  `failure_log.summary()`, whose counts mean "people who did not get a drawing".
- A request that produced **no plan** logs at **WARNING**; a served one at INFO. One line is one
  request, so a `grep -c` is a rate.
- The counters are **not a new measurement**. `PipelineSuccess.selection["histogram"]` and
  `PipelineDiagnosis.stage_histogram` already held the SIZING tallies and the caller threw them
  away. `_exact_counters` reads them; `BrainPlan` carries `solves` / `budget_expired` /
  `exact_refusal`; `_carry` moves them onto the plan that was **kept**, so a declined exact attempt
  is not under-reported; `BrainResult` sums them. No geometry, no ranking, no note ordering changes.
- `BRAIN_NO_PLAN`'s `detail` now **leads with the exact sizer's own code**.
- `_failure_context` gains `engine`, known only in the request frame, so a crash on a preview path
  is no longer indistinguishable in `failures.json` from one in production.

### No secret is logged, on any path (AC-4)

`backend/tests/demo/test_brain_preview_gate.py` — **42 → 49 passed**, extended because this
branch is what created new places a secret *could* leak into:

- an authorized request on the wire: the token is in neither the captured log records (every
  logger, DEBUG) nor the failure log's entries, while `engine=brain` **is** recorded;
- four unauthorized shapes — no token, a wrong one, a truncated one, a wrong-case one — none of
  them, nor the near-miss value presented, reaches any log;
- a **structural** pin, over the AST with docstrings excluded, that `preview_log`, `service` and
  `failure_log` never even name `BRAIN_PREVIEW_TOKEN` in executed code, that `brain_request` has no
  token-shaped parameter, and that `preview_log.FIELDS` — the fixed list a line is built from —
  contains no such field;
- `preview_gate`, the one module that *reads* the secret, still contains no `logging`, `print(`,
  `open(`, `failure_log` or `preview_log`. It cannot write anything down.

### What was deliberately NOT built

A metrics endpoint, a counter store, request IDs, and per-family latency histograms. All of them
are the right thing for a *product* feature and none is the smallest change that answers "is the
preview healthy?" for an internal preview whose duration is measured in days. The one line is
greppable, is 12 fields, and adds no new file, port, dependency or configuration.

---

## 3. SciPy / HiGHS as a deployment dependency

### Where it must be installed

`backend/pyproject.toml`, `[project].dependencies` — **`scipy>=1.11,<2`**, a *main* dependency, not
an extra, declared by #203 ("already in the lock transitively; declared so `uv sync` cannot drop
it"). `backend/uv.lock` pins **1.17.1** for Python < 3.12 and **1.18.1** for ≥ 3.12, 122 wheel
entries. **HiGHS needs no separate install**: `scipy.optimize.milp` bundles it inside the scipy
wheel, confirmed here (`from scipy.optimize import milp` → ok, scipy 1.17.1).

Consequence for an image or a host: a plain `uv sync` (or `uv sync --frozen`) installs it. The
absence scenarios are a `--no-deps` install, a hand-written subset of requirements, or an
environment created **before** #203 declared it and never re-synced.

### What actually happens when it is absent — observed, not inferred

A scratch virtualenv was built with the application's main dependencies **except scipy**
(`fastapi`, `uvicorn[standard]`, `openai`, `python-dotenv`, `httpx`, `matplotlib`, `shapely`, and
the dev group), confirmed with `import scipy` → `ModuleNotFoundError`, then the real path was run
in it on brief **B08** (3 bedrooms, 1 wet room, open plan, 132 m², 11 × 12 m footprint):

```
scipy absent: No module named 'scipy'
1. milp_oracle ImportError: No module named 'scipy'
2. run_exact_pipeline -> PipelineDiagnosis code='EXACT_SIZER_UNAVAILABLE' stage='SIZING'
                         detail="scipy is not installed (No module named 'scipy')"
3. run_brain: 8 plans, 8 accepted, 8 distinct, 1.921s
   TWO_HALL:          sizer=production family=band stage=REALIZED
     notes=['exact sizer fell back to production: EXACT_SIZER_UNAVAILABLE: scipy is not installed …']
   PUBLIC_BAND+FOYER: sizer=production family=band stage=REALIZED   (same note)
   HALL_SPINE+FOYER:  sizer=production family=band stage=REALIZED   (same note)
   sizers: ['production']
4. HTTP status=200
   primary family: brain:TWO_HALL
   note: requested graph preserved — contacts 8/8, doors 8/8; 3 bands
   note: sized by the production sizer (band layout)
   note: exact sizer fell back to production: EXACT_SIZER_UNAVAILABLE: scipy is not installed …
```

**The result is a 200, not an error.** The typed fallback works exactly as designed: the preview
loses no parti, the graph is preserved 8/8 and 8/8, and the plan says in writing which sizer made
it. The `?engine=brain` **families** — spine, stack and cells — are, however, entirely unreachable:
they exist only in the exact pipeline. So the honest description of a scipy-less preview is **"the
brain's concepts, production's geometry"**, which is a materially weaker thing to judge
architecturally than what the preview is for, and nothing in the interface shouts about it.

This is the one path where #214's observability earns its keep: the request is logged with
`plan_sizer=production exact_refusal=EXACT_SIZER_UNAVAILABLE solves=0`. One `grep` separates "the
exact sizer is slow" from "the exact sizer is not installed".

### Lockfile and image implications

1. **`uv sync` must not be run with `--no-install-project --no-deps` or a hand-rolled requirements
   subset** for a host that serves the preview. There is no runtime check for the solver at
   startup — the first *request* discovers it, degrades, and returns 200.
2. **`uv.lock` must be committed in step with `pyproject.toml`.** It is, today.
3. scipy's wheel is large (tens of MB) and platform-specific. Any future image build has to install
   it for the image's own platform; a lockfile is honoured per-platform by `uv`, so this is a
   non-issue for `uv sync` and would be one for a copied `site-packages`.
4. The **same** absence disables the shape-agnostic realizer's exact sizer everywhere else it is
   used, not only in the preview. It is a process-level fact.

---

## 4. The live environment today (AC-5) — reported, **unchanged**

Investigated read-only. **Nothing live was changed: no deploy, no restart, no environment variable,
no credential, no configuration.**

| finding | evidence |
|---|---|
| **There is no deployment target.** No `Dockerfile`, no `docker-compose*`, no `fly.toml`, `Procfile`, `render.yaml`, systemd unit or deploy workflow anywhere in the repository. The four CI workflows (`agent-ci`, `agent-contract`, `agent-regression`, `agent-snapshot`) contain no deploy step. | repository-wide search |
| The only running environment is a **local development server**: `uvicorn app.main:app --reload --port 8000`, from the owner's IDE checkout `/Users/mymacbook/projects/sddproject`, **up since 2026-09-25 14:26** (pid 79460). | `ps` |
| **scipy IS present in that environment**: **1.17.1** in its virtualenv, satisfying `scipy>=1.11,<2`, installed 2026-09-06 — before that process started. HiGHS is bundled. | `…/.venv/bin/python -c "import scipy"` |
| **…but that environment cannot serve the preview at all today.** Its checkout is at `55d1048` (its local `main`, behind `origin/main` `5b155d1`) and contains **neither `app/vertical_slice/brain/` nor `app/demo/preview_gate.py`**. `?engine=brain` there is an unknown engine. | `git log -1`, file listing |
| Therefore **enabling the preview is not only a flag.** It needs the brain (already in `origin/main` since #206) *and* PR #224's gate merged, *and* that checkout updated. Both merges are the owner's gate. | #211's boundaries |
| **A pre-#224 server is the one that is open.** On `55d1048`'s successor commits — any main that has the brain but not #224 — `?engine=brain` *is* the authorization, with no flag and no token. That is exactly the defect #212 closed, and it is the state of `origin/main` right now. | PR #224 is open |
| Whether `BRAIN_PREVIEW_*` is set in that checkout's `.env` was **not** verified: reading a live `.env` was refused by this session's credential policy and was not retried. It is moot while the gate module is absent — nothing reads those names. | stated as a gap |

---

## 5. The emergency-disable mechanics, as actually observed

> **Superseded as a procedure by #231, kept as the measurement.** Everything in this section was
> observed and is still true of the two `.env` levers. What it concludes — that in step 4's shape
> the only disable is stopping the process — is no longer the situation: #231 added a kill switch
> inside `preview_gate` (`touch backend/DISABLE_BRAIN_PREVIEW`) that closes the preview on the next
> request in the same process, beating an exported `BRAIN_PREVIEW_ENABLED`, and fails closed on any
> ambiguity. See `PREVIEW-killswitch-proof.md` and `docs/runbooks/brain-preview.md` §3. Read this
> section for *why* the environment alone could not do it.

#212's promise is that unsetting either half **closes the preview on the next request, with no
redeploy and no restart**, because `preview_gate` reads `os.environ` per request and caches no
decision. That is true of the decision. It is **not** the whole operational story, and the
difference is the single most important thing in the runbook, so it was measured rather than
reasoned about.

A probe mirroring `app/main.py`'s first three lines exactly (`load_dotenv()` at import, before
anything else) and exposing the **real** `preview_gate.enabled()` / `authorized()` was run under
`uvicorn --reload`, as the README documents the app being run:

| step | observed |
|---|---|
| 1. `.env` holds `BRAIN_PREVIEW_ENABLED=1` + a token; request carries the header | `pid=11864 enabled=true authorized=true` |
| 2. **blank both lines in `.env`**, wait, request again | `pid=11864 enabled=true authorized=true` — **STILL OPEN** |
| 3. `touch` any `.py` file (the reloader respawns the worker), request again | `pid=12014 enabled=false authorized=false` — **closed** |
| 4. repeat with the variables **exported in the shell that started uvicorn**, then remove them from `.env` and force a reload | `pid` changes 12066 → 12073, `enabled=true authorized=true` — **STILL OPEN** |

What this means, stated plainly:

- A process's `os.environ` **cannot be changed from outside the process**. Editing `.env`, or
  exporting a variable in another shell, changes nothing for a request already being served by a
  running worker (step 2).
- `load_dotenv()` runs once per process, at import, and **does not override** variables already in
  the environment. So the `.env` route only works when the variable is *only* in `.env` (step 3),
  and is inert when it was exported into the parent (step 4).
- The genuinely restart-free lever on a `--reload` server is therefore **blank the `.env` line and
  touch a `.py` file**: the reloader respawns the worker, which re-reads `.env`. That is a worker
  respawn, not a service restart — no redeploy, no port drop, in-flight requests finish.
- On a server **not** running `--reload`, and in step 4's shape, the only disable **was** stopping
  the process. #211 forbids a restart without owner approval, which is what made this a GO blocker
  rather than a documentation defect — and what #231 closed: the kill switch needs neither the
  environment's cooperation nor a respawn, so the runbook's first lever is now a file, and the two
  `.env` levers below it are for revoking a leaked secret and for tidying up.

All three levers are in `docs/runbooks/brain-preview.md` §3, in that order.

---

## 6. Risk register

Severity is **operational**, for an internal preview on a non-public host: **HIGH** = can expose
unfinished work or mislead a judgment; **MEDIUM** = degrades the preview or wastes the owner's
session; **LOW** = annoyance or an already-mitigated edge.

| # | risk | sev | why | mitigation / state |
|---|---|---|---|---|
| R1 | **The preview silently serves production's geometry.** scipy absent, or every solve refusing, returns 200 with plans whose only tell is a sentence on the caller's screen. An owner judges "the brain" and is looking at the band sizer. | **HIGH** | observed in §3: 8/8 partis, 200 OK | **detection closed by #233, not by this branch.** This branch emitted the right record — `exact_refusal=` and `plan_sizer=` in every request line, §2 — and **delivered it nowhere**: the application had no logging configuration, so under `uvicorn app.main:app` the `INFO` record reached the root logger, found no handler and was dropped. #231 measured 0 lines on a running server; the `caplog` tests here passed because `caplog` installs the root handler a deployment did not have. So between #214 and #233 this risk was **open** and recorded as closed, which is worse than open. #233 added the handler and proved the line in a server's own output (`PREVIEW-logging-proof.md`), and verification step 3 of the runbook now finds something when an operator looks. Still not closed on the *interface* side — the response reads as a brain plan. |
| R2 | **The preview is enabled on a pre-#224 server**, where `?engine=brain` alone is the authorization. | **HIGH** → **largely CLOSED** | it was `origin/main`'s exact state when this was written (§4); **#224 has since merged**, so `main` now carries the gate | #224 must merge **before** the preview is used anywhere reachable. Named as a precondition in the runbook's enable section, and the single owner gate. |
| R3 | **The emergency disable does not work the way it reads.** An operator unsets the variable, serves the next request, and the preview is still open (§5 steps 2 and 4). | **HIGH** → **CLOSED by #231** | observed | **Closed, not documented around.** #231 added a kill switch inside `preview_gate`: `touch backend/DISABLE_BRAIN_PREVIEW` closes the preview on the next request, same process, beating an exported `BRAIN_PREVIEW_ENABLED` — measured on a running server in `PREVIEW-killswitch-proof.md`. It fails closed on any ambiguity. The runbook's §3 now leads with it; §5 below records what was observed BEFORE that fix and is kept as the measurement it was. |
| R4 | **The token leaks** (a shell history, a `curl` in a shared terminal, a screenshot). The secret is shared, not per-user, and there is no audit trail. | **HIGH** | #212's own stated limits | blank `BRAIN_PREVIEW_TOKEN` (the leaked-secret lever, §5) and reissue. No log line can contain it (AC-4, §2). Per-user identity and an audit trail were deliberately out of #212's scope. |
| R5 | **An unfinished layout family reaches the owner.** | **LOW** | mitigated at the source | `preview_gate.ALLOWED_FAMILIES` is an allow-list configuration can only *narrow*; #208's `generator` is in `GATE_FAILED_FAMILIES` and no environment variable can add it. Pinned by four tests. |
| R6 | **A refusal becomes an oracle** — a prober learns a hidden engine exists. | **LOW** | mitigated at the source | identical 422, identical work before the answer, `hmac.compare_digest`; the preview line does not record *refused* gate decisions, so the log is not an oracle either. |
| R7 | **`BRAIN_NO_PLAN` in the field with no actionable cause.** | **MEDIUM** | the detail was built from production's reasons only | **closed by this branch**: the detail leads with the exact sizer's typed code, the failure-log entry carries `engine: brain` and the whole brief, and the request logs at WARNING. The WARNING was the one preview line that **did** reach a server's output before #233 — through `logging.lastResort`, as a bare message with no level and no logger name (#233's proof); it is labelled now. Per-code actions are in the runbook. |
| R8 | **The preview's 30 s budget is spent on a brief it cannot plan**, so the owner's session is slow and the plans are production's anyway. | **MEDIUM** | `budget_expired` and `solves` now say so | the fields exist in this branch (`budget_expired`, `solves`); they are on the **INFO** line, so an operator could not see them until #233 delivered it. **Detection closed by #233.** The *size* of the problem — how often, how long — is a measurement: **deferred → #226**. A narrower `BRAIN_PREVIEW_FAMILIES` (e.g. `band`) is the lever that needs no code change. |
| R9 | **Latency.** A brain request is a 30 s wall-clock budget by design, against production's sub-second path. | **MEDIUM** | by design | **measured by #226, still open.** Brain **31.6 s median / 48.9 s max**; production 1.38 s / 13.7 s. And the 30 s is not a request timeout — it bounds only `_improve_exactly`, so `budget_s=0.2` still cost 23.0 s on B11 and 34.8 s on B16. Bounding the whole request is **#247**. #246 did not change this and does not claim to: its scratch-server runs cost 26.7–32.7 s per brain request on a 3-bedroom brief. |
| R10 | **CPU and memory.** Each MILP solve is a HiGHS run in-process. | **MEDIUM** | measured | **no longer in-process (#246).** #226: 168–213 MB against production's 113–118 MB, and 1.00–1.07 cores for 30–49 s. #246 measured the *control* server reaching **206 % CPU with one** brain request, **335 %** with two and **498 %** with four — so on that host the solver releases the GIL and the demand is for several cores, not one. Both readings are reported in `PREVIEW-isolation-proof.md` §4 and the discrepancy is **not diagnosed**; the un-diagnosed direction is the one that makes isolation more necessary. The demand now lands in a **child process at +10 niceness**, so the OS scheduler resolves it in production's favour. Memory was never the risk. |
| R11 | **Concurrency.** Two brain requests on one worker share the cores; the budget is per request, not per process, so N concurrent requests are N × 30 s of CPU demand. There is no concurrency limit anywhere on the path. | **MEDIUM** → **CLOSED by #246** | measured | **closed at the source, not documented around.** `preview_isolation.admitted()` admits **one** preview request at a time, enforced server-side in the gate path; `BRAIN_PREVIEW_MAX_CONCURRENCY` is 1 by default and **1 at most** (configuration may narrow the preview, never widen it — #226 measured N=2 and N=4 as harmful and no N above 1 as safe). A second simultaneous request is **refused**, not queued: `PREVIEW_BUSY`, HTTP 503, `Retry-After`, measured at **2.5–9 ms** on a real server. Queueing was rejected because a 49 s wait before the work starts is itself a bad answer and no client would still be listening. Reachable only after authorization, so it is not a new oracle. The primitive is a `threading.Lock` and not an `asyncio.Semaphore`, which would have bounded nothing: the route handlers are sync and run on a worker thread with no event loop. 36 tests. |
| R12 | **Failure isolation** — whether a brain request can degrade a concurrent production request. | **HIGH** → **CLOSED by #246** | measured both ways | **It could, and it no longer can.** #226: production 1.65 s median quiet → 5.89 s beside two brain requests → 9.29 s beside four, 16.87 s worst, recovering to 1.63 s. #246 repeated the protocol on two scratch servers, one at a time, with a `git archive` control at its own base commit sharing the same virtual environment. **Control**: median 0.329 → 0.650 s (**×1.98**), worst 0.365 → 2.801 s (**×7.67**), and ×6.04 on the worst case from a **single** brain request. **Branch**: median **0.337–0.338 s at N=1, 2 and 4** against 0.333–0.347 s quiet, worst 0.378–0.383 s against a quiet worst of 0.386 s — the spread under load is smaller than the baseline's own. The N=1 row isolates the process shape from the limit. The preview also got faster and searched more (1120 solves in 26.0 s against the control's best 810 in 30.0 s) and returned the same plan in every phase. `PREVIEW-isolation-proof.md`. |
| R13 | **A long-lived `--reload` dev server serves the preview.** It has no process supervision, no log rotation and no restart-on-crash; the live one has been up 24 days. | **MEDIUM** | §4 | out of #214's scope to change. Stated so the GO/NO-GO decision is taken knowing the host is a development server, not a deployment. |
| R14 | **`failures.json` is a single rewritten-whole JSON array capped at 2000 entries**, oldest dropped. A burst of preview refusals can evict genuine production failures. | **LOW** | `failure_log` by design | the preview's own signal is now the logger, not that file, so a preview burst adds *refusals* only, not successes. Watch `failure_log.summary()` if a preview session is long. |
| R15 | **No preview request has a request id**, so a slow request in the log cannot be tied to the plan the owner was looking at. | **LOW** | — | accepted. `brief` (the project id) is already in `run_brain`'s result and the failure context; adding an id is a product-shaped change, not a preview one. |

### Explicitly deferred to #226 — and what came back

#226 answered all four (§ R9–R12 above) and its answer to the fourth was the reason the readiness
report recommends **NO-GO as it stands**. **#246 closed R11 and R12**; **R9 is #247's** and **R10 is
now a property of a child process rather than of the server**. The one thing #226 measured that is
*not* closed anywhere yet is the request's own bound — see R9.

A fifth question nobody had deferred, and #246 raised: **a liveness probe that answers in 26 ms
while a user waits 17 s suppresses the alarm it exists to raise.** `/health` now carries
`preview.in_flight`, `preview.limit`, `preview.slots_free` and `preview.oldest_running_s` —
observed reading `6.009` six seconds into a real request on a running server. It deliberately still
answers **200**, because a probe that went red here would tell a supervisor to restart the process
serving production, and that is recorded as an **accepted risk** with its reason in
`PREVIEW-isolation-proof.md` §6: nothing raises an alarm automatically, and an operator who wants
one must threshold `oldest_running_s`.

## 7. Evidence index

| artifact | what it proves |
|---|---|
| `backend/tests/vertical_slice/test_brain_fallbacks.py` | §1, 26 passed |
| `backend/tests/demo/test_brain_preview_gate.py` | §2's AC-4 and the per-request line on the wire, 49 passed (42 before); **53 after #233**, which re-makes the secret's absence against a real stream |
| `docs/reports/architectural-brain/PREVIEW-logging-proof.md` | **#233**: the four operational signals at the process level, before and after. R1's detection, actually closed |
| `docs/reports/architectural-brain/PREVIEW-isolation-proof.md` | **#246**: that a preview request can no longer slow production down. #226's protocol repeated with a same-session control at this branch's base commit — R11 and R12, closed by measurement rather than by diagram |
| `backend/tests/demo/test_brain_preview_concurrency.py` | **#246**: the limit of 1, its ceiling, the typed refusal, the child process, and that an unauthorized caller can never see the busy refusal — 36 passed |
| `backend/app/observability/preview_log.py` | §2's change |
| `docs/runbooks/brain-preview.md` | the operator's procedure |
| §3's transcript | the scipy-absent path, in a virtualenv that genuinely lacks it |
| §5's table | the disable mechanics, under a real `uvicorn --reload` |

Suites run on this branch, verbatim:

- `tests/vertical_slice/test_brain_fallbacks.py` — **26 passed** (50 s).
- `tests/demo/test_brain_preview_gate.py` — **49 passed** (5.5 s); 42 on PR #224.
- `tests/demo/ tests/test_engine_preview.py tests/test_demo_p0.py tests/vertical_slice/test_brain.py
  tests/vertical_slice/test_brain_fallbacks.py tests/knowledge/test_capability_wiring_table.py -n 4`
  — **249 passed, 1 xfailed** (2:14).
- Fast suite, `WALLCLOCK_BUDGETS=off … -n 4` — **2521 passed, 883 skipped, 10 xfailed, 0 failed**
  (6:42). PR #224 reported 2484 passed with 4 failures in `tests/test_local_gateway.py` on a
  missing `torch`; those four pass here because the environment was built with
  `uv sync --group dev --extra local-model`, which is the difference, not a change in this branch.
  2488 + 26 + 7 = 2521 exactly.
- **The corpus snapshot suite was deliberately NOT run**: #209 measured it at 55 minutes and #212
  proved the gate cannot affect it, since `corpus_snapshot.py` calls `generate_demo_design(project)`
  with no engine keyword and so never reaches the router. Nothing in this branch is reachable from
  it either: `preview_log` is called only from `_brain_result`, and `_failure_context`'s new field
  is set only in the two demo routes. `agent-regression.yml`'s base-vs-head comparison on the PR is
  the authoritative check.
