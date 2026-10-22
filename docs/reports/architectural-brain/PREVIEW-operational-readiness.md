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
  stdout already is — and writing successes into `failures.json` would corrupt
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
- On a server **not** running `--reload`, and in step 4's shape, the only disable is **stopping the
  process**. #211 forbids a restart without owner approval, so the runbook's first lever is the
  `.env` one and the second is an explicit owner decision.

Both steps are in `docs/runbooks/brain-preview.md`, in that order.

---

## 6. Risk register

Severity is **operational**, for an internal preview on a non-public host: **HIGH** = can expose
unfinished work or mislead a judgment; **MEDIUM** = degrades the preview or wastes the owner's
session; **LOW** = annoyance or an already-mitigated edge.

| # | risk | sev | why | mitigation / state |
|---|---|---|---|---|
| R1 | **The preview silently serves production's geometry.** scipy absent, or every solve refusing, returns 200 with plans whose only tell is a sentence on the caller's screen. An owner judges "the brain" and is looking at the band sizer. | **HIGH** | observed in §3: 8/8 partis, 200 OK | **closed by this branch** on the detection side: `exact_refusal=` and `plan_sizer=` in every request line, §2. Verification step 3 of the runbook makes the operator look. Not closed on the *interface* side — the response still reads as a brain plan. |
| R2 | **The preview is enabled on a pre-#224 server**, where `?engine=brain` alone is the authorization. | **HIGH** | `origin/main` is exactly this state today (§4) | #224 must merge **before** the preview is used anywhere reachable. Named as a precondition in the runbook's enable section, and the single owner gate. |
| R3 | **The emergency disable does not work the way it reads.** An operator unsets the variable, serves the next request, and the preview is still open (§5 steps 2 and 4). | **HIGH** | observed | the runbook gives the two levers in order, says which one is restart-free, and says plainly that an exported variable can only be closed by stopping the process — an owner decision under #211. |
| R4 | **The token leaks** (a shell history, a `curl` in a shared terminal, a screenshot). The secret is shared, not per-user, and there is no audit trail. | **HIGH** | #212's own stated limits | blank `BRAIN_PREVIEW_TOKEN` (the leaked-secret lever, §5) and reissue. No log line can contain it (AC-4, §2). Per-user identity and an audit trail were deliberately out of #212's scope. |
| R5 | **An unfinished layout family reaches the owner.** | **LOW** | mitigated at the source | `preview_gate.ALLOWED_FAMILIES` is an allow-list configuration can only *narrow*; #208's `generator` is in `GATE_FAILED_FAMILIES` and no environment variable can add it. Pinned by four tests. |
| R6 | **A refusal becomes an oracle** — a prober learns a hidden engine exists. | **LOW** | mitigated at the source | identical 422, identical work before the answer, `hmac.compare_digest`; the preview line does not record *refused* gate decisions, so the log is not an oracle either. |
| R7 | **`BRAIN_NO_PLAN` in the field with no actionable cause.** | **MEDIUM** | the detail was built from production's reasons only | **closed by this branch**: the detail leads with the exact sizer's typed code, the failure-log entry carries `engine: brain` and the whole brief, and the request logs at WARNING. Per-code actions are in the runbook. |
| R8 | **The preview's 30 s budget is spent on a brief it cannot plan**, so the owner's session is slow and the plans are production's anyway. | **MEDIUM** | `budget_expired` and `solves` now say so | detection closed by this branch. The *size* of the problem — how often, how long — is a measurement: **deferred → #226**. A narrower `BRAIN_PREVIEW_FAMILIES` (e.g. `band`) is the lever that needs no code change. |
| R9 | **Latency.** A brain request is a 30 s wall-clock budget by design, against production's sub-second path. | **MEDIUM** | by design | **deferred → #226.** Not timed here. The budget is a constant (`REQUEST_BUDGET_S`), not configuration, so shortening it is a code change. |
| R10 | **CPU and memory.** Each MILP solve is a HiGHS run in-process. | **LOW** | #226 B.2: 1.00–1.07 cores for 30–49 s, 168–213 MB RSS | measured; memory is not the risk. The core is: see R12. |
| R11 | **Concurrency.** Brain requests do not run in parallel, they serialize on the GIL (#226 B.3: N=4 slowest 122.8 s; #246: 51–145 s); the budget is per request, not per process. | **HIGH → closed** | measured (#226, #246) | **closed by #246**: a server-side limit of **one** gated request per process (`BRAIN_PREVIEW_MAX_CONCURRENCY`, default 1, clamped to the measured ceiling 1), enforced in the router before any work; a second request is a typed **429 `BRAIN_PREVIEW_BUSY`** with `Retry-After`, in about 20 ms, not a queue. Pinned by `test_brain_preview_concurrency.py` (26 tests). Runbook §7.1. |
| R12 | **Failure isolation** — a brain request degrades a concurrent production request. | **HIGH → closed by the process shape** | measured (#226 B.4; #246 `PREVIEW-isolation-proof.md` §2): in ONE process production's median goes 1.64 s → 6.84 s (2 brain requests) and 7.08 s (4), worst 26.6 s; the event loop is not blocked, so `/health` stays green | **closed by #246's process shape**, measured: the preview served by a **second process** (flag OFF in production's) leaves production at 1.63 s / 1.64 s median and 1.76 s worst with 2 / 4 brain requests running, against 1.63 s quiet. Needs a free core. Runbook §7.2. **Residual:** a deployment that sets the flag in production's process is not isolated and has no latency alarm (R16). |
| R16 | **No liveness signal reflects real waiting.** `/health` and `/docs` answer in milliseconds while a production request takes 26 s. | **MEDIUM — accepted** | three in-process probes were built and measured; none separated waiting from not waiting (`PREVIEW-isolation-proof.md` §3) | **accepted risk, stated**: no in-process probe is shipped (a green one would repeat the fault). In the two-process shape production's `/health` is honest again. The operator's alarm is a black-box timed production request plus the `BRAIN_PREVIEW_BUSY` count (runbook §7.4). |
| R13 | **A long-lived `--reload` dev server serves the preview.** It has no process supervision, no log rotation and no restart-on-crash; the live one has been up 24 days. | **MEDIUM** | §4 | out of #214's scope to change. Stated so the GO/NO-GO decision is taken knowing the host is a development server, not a deployment. |
| R14 | **`failures.json` is a single rewritten-whole JSON array capped at 2000 entries**, oldest dropped. A burst of preview refusals can evict genuine production failures. | **LOW** | `failure_log` by design | the preview's own signal is now the logger, not that file, so a preview burst adds *refusals* only, not successes. Watch `failure_log.summary()` if a preview session is long. |
| R15 | **No preview request has a request id**, so a slow request in the log cannot be tied to the plan the owner was looking at. | **LOW** | — | accepted. `brief` (the project id) is already in `run_brain`'s result and the failure context; adding an id is a product-shaped change, not a preview one. |

### Explicitly deferred to #226

R9 (latency / timeout), R10 (CPU and memory), R11 (concurrency), R12 (failure isolation), and the
*frequency* half of R8. #226 runs alone on an idle machine. **No number in §1–§5 of this report is a
timing**, and the two durations quoted (`1.921s` in §3, the `seconds=` field in §2) are
illustrations of a field's shape, not measurements of performance. **R10–R12 have since been
measured** (#226 B.2–B.4) **and closed or accepted** (#246: the limit, the process shape, the
liveness finding) — the figures are in the register above and in
`PREVIEW-isolation-proof.md`. R9 (latency) and the request-bound defect remain with #226 and #247.

---

## 7. Evidence index

| artifact | what it proves |
|---|---|
| `backend/tests/vertical_slice/test_brain_fallbacks.py` | §1, 26 passed |
| `backend/tests/demo/test_brain_preview_gate.py` | §2's AC-4 and the per-request line on the wire, 49 passed (42 before) |
| `backend/app/observability/preview_log.py` | §2's change |
| `docs/runbooks/brain-preview.md` | the operator's procedure (§7: concurrency and the process shape, #246) |
| `docs/reports/architectural-brain/PREVIEW-isolation-proof.md` | R11/R12/R16: the limit, the second process and the probe finding, measured (#246) |
| §3's transcript | the scipy-absent path, in a virtualenv that genuinely lacks it |
| §5's table | the disable mechanics, under a real `uvicorn --reload` |
