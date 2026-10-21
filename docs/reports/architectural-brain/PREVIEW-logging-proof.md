# PREVIEW — the operational signals, proven at the process level

Issue **#233**, child of ROOT #211. Closes the detection half of **risk 1**, which #214 recorded as
closed and #231 found was not.

## Why a unit test could not have found this, and did not

#214 added one line per brain preview request through the `buildsmart.preview` logger and pinned it
with `caplog`. `caplog` works by installing its own handler **on the root logger**, which is exactly
the thing a deployment did not have — so the tests passed on a record that, in a running server,
reached the root logger, found no handler and was dropped. The record was genuinely emitted and
genuinely invisible.

That is the shape of defect this document exists for. Everything below is a **scratch server's own
captured output**, in the configuration the README documents
(`uv run uvicorn app.main:app`), with no `--log-config` and no `--reload`.

## The setup, identical in both phases

- host `127.0.0.1`, port **8733**, a scratch server started and stopped by the run. The development
  server on port 8000 (**pid 79460**) was never touched and never requested; the live
  `backend/.env` was never read or written — `ls backend/.env` is *No such file* in this worktree,
  so the preview's variables are **exported in the starting shell and nowhere else**.
- `BRAIN_PREVIEW_ENABLED=1`, `BRAIN_PREVIEW_TOKEN` generated for the run and never printed,
  `BRAIN_PREVIEW_FAMILIES=band` so one request costs one family rather than four.
- three seeded projects in this worktree's own `app/data/projects.json`, deleted afterwards:

  | project | brief | why |
  | --- | --- | --- |
  | `OBS233` | 3 bedrooms, 1 wet room, open plan, 132 m² on 11 × 12 m (#231's own brief) | production and the brain both plan it — the **served** request |
  | `OBS233NOPLAN` | 6 bedrooms, 3 wet rooms, safe room, 175 m² on 12.5 × 14 m | production plans it and **every parti's band layout refuses** (`EXPOSURE_INFEASIBLE`) — a real `BRAIN_NO_PLAN`, not a faked one |
  | `OBS233CRASH` | `OBS233`'s record with `bedrooms.value` set to a string | a **stored record that no longer validates**: `Project.model_validate` raises inside the route, which is the CRASH path from real corrupt data rather than an injected exception |

- four requests, in order: an authorized brain request (`OBS233`), the same URL with **no** token,
  an authorized brain request on `OBS233NOPLAN`, and a plain production request on `OBS233CRASH`.

**Nothing is faked.** `run_brain` is the real brain, the refusal is the real refusal, and the crash
is a real unhandled exception.

## BEFORE — the server's own output, verbatim

```
$ ls backend/.env
ls: .env: No such file or directory
$ lsof -ti :8733            (empty)
$ ps -o pid=,command= -p 79460
79460 /Users/mymacbook/projects/sddproject/backend/.venv/bin   <- the live server, untouched
$ export BRAIN_PREVIEW_ENABLED=1 BRAIN_PREVIEW_TOKEN=<generated, never printed> BRAIN_PREVIEW_FAMILIES=band
$ uv run uvicorn app.main:app --host 127.0.0.1 --port 8733      # no --reload, no --log-config
   server pid: 28566

   R1  authorized brain, OBS233            -> HTTP 200   a plan
   R2  the same URL, no token              -> HTTP 422   unknown engine 'brain'; expected …
   R3  authorized brain, OBS233NOPLAN      -> HTTP 422   {"code":"BRAIN_NO_PLAN", …}
   R4  production, OBS233CRASH             -> HTTP 500   {"code":"INTERNAL_ERROR", …}
   pid still: 28566

## the server's OWN output, in full
   INFO:     Started server process [28566]
   INFO:     Application startup complete.
   INFO:     Uvicorn running on http://127.0.0.1:8733 (Press CTRL+C to quit)
   INFO:     127.0.0.1 - "GET /health HTTP/1.1" 200 OK
   INFO:     127.0.0.1 - "POST /projects/OBS233/design/demo?engine=brain HTTP/1.1" 200 OK
   INFO:     127.0.0.1 - "POST /projects/OBS233/design/demo?engine=brain HTTP/1.1" 422 Unprocessable Entity
   engine=brain sizer=exact families=band exact_refusal=NO_EXACT_PLAN budget_expired=true solves=0 plans=0 partis=10 seconds=30.072 code=BRAIN_NO_PLAN
   INFO:     127.0.0.1 - "POST /projects/OBS233NOPLAN/design/demo?engine=brain HTTP/1.1" 422 Unprocessable Entity
   INFO:     127.0.0.1 - "POST /projects/OBS233CRASH/design/demo HTTP/1.1" 500 Internal Server Error
   ERROR:    Exception in ASGI application
   Traceback (most recent call last):
     …
     File ".../app/demo/router.py", line 365, in generate_demo_plan
       project = _project_or_404(project_id)
     File ".../app/projects/repository.py", line 107, in get
       return None if record is None else Project.model_validate(record)
   pydantic_core._pydantic_core.ValidationError: 2 validation errors for Project
   bedrooms.value
     Input should be a valid integer, unable to parse string as an integer …

## buildsmart.preview lines in the server's own output
   grep -c 'buildsmart.preview' server.log -> 0
   grep -c 'engine=brain sizer='  server.log -> 1        (line 9, the one above)
```

### What that says, and the thing #231 could not have seen

**The served request wrote nothing.** R1 returned 200 with a plan and produced no preview line at
all — #231's finding, reproduced.

**The no-plan request's line DID arrive** — and this is new. It is not a handler: with no handler
found anywhere on the chain, Python's `logging.lastResort` handles records of **WARNING and above**
and writes the bare message to stderr. So before #233 the output contained:

- for a **healthy** request: nothing;
- for a **failed** request: an unlabelled line with no level, no logger name and nothing marking it
  a warning or saying which subsystem produced it.

The exact inverse of the health signal #214 was asked for. #231 saw four requests that were all
either served or refused by the gate, so it saw the first half and not the second.

## AFTER — the same four requests, the same server command

```
$ uv run uvicorn app.main:app --host 127.0.0.1 --port 8733      # unchanged. No --log-config.
   server pid: 29294

   R1 -> HTTP 200    R2 -> HTTP 422    R3 -> HTTP 422    R4 -> HTTP 500     (all four unchanged)

## the server's OWN output, in full
   INFO:     Started server process [29294]
   INFO:     Application startup complete.
   INFO:     Uvicorn running on http://127.0.0.1:8733 (Press CTRL+C to quit)
   INFO:     127.0.0.1 - "GET /health HTTP/1.1" 200 OK
   INFO     buildsmart.preview engine=brain sizer=exact families=band plan_sizer=exact plan_family=band budget_expired=true solves=171 plans=8 partis=8 seconds=30.904
   INFO:     127.0.0.1 - "POST /projects/OBS233/design/demo?engine=brain HTTP/1.1" 200 OK
   INFO:     127.0.0.1 - "POST /projects/OBS233/design/demo?engine=brain HTTP/1.1" 422 Unprocessable Entity
   WARNING  buildsmart.preview engine=brain sizer=exact families=band budget_expired=false solves=0 plans=0 partis=10 seconds=30.283 code=BRAIN_NO_PLAN
   INFO:     127.0.0.1 - "POST /projects/OBS233NOPLAN/design/demo?engine=brain HTTP/1.1" 422 Unprocessable Entity
   INFO:     127.0.0.1 - "POST /projects/OBS233CRASH/design/demo HTTP/1.1" 500 Internal Server Error
   ERROR:    Exception in ASGI application
   Traceback (most recent call last):  …  ValidationError: 2 validation errors for Project

## buildsmart.preview lines in the server's own output
   grep -c 'buildsmart.preview' server.log -> 2
   7:INFO     buildsmart.preview engine=brain … plan_sizer=exact plan_family=band …
   10:WARNING  buildsmart.preview engine=brain … code=BRAIN_NO_PLAN
```

**AC-1.** The served request's line is in the server's own output, with `plan_sizer=exact
plan_family=band` — the pair the runbook's Verify step 3 tells an operator to read, and the one
fact that separates a healthy preview from one quietly serving production's geometry. It sits one
line above uvicorn's own access line for the same request, because the handler writes to the same
stderr uvicorn's `default` handler does.

**AC-2, the WARNING.** Now labelled `WARNING`, named `buildsmart.preview`, and distinguishable from
the INFO line above it. The record is the same record; only its arrival changed.

## The four signals, before and after

| signal | where the runbook says to look | reached it BEFORE | reached it AFTER |
| --- | --- | --- | --- |
| the per-request **INFO** line (`plan_sizer`, the health signal) | the server's own output (§5) | **no** — no handler, and INFO is below `lastResort` | **yes** — `INFO buildsmart.preview …` |
| the **WARNING** when no plan came back | the server's own output (§5) | **partly** — delivered by `logging.lastResort` as a bare message: no level, no logger name, nothing marking it a warning | **yes** — `WARNING buildsmart.preview …`, labelled |
| the `failure_log` **REFUSAL** | `backend/app/data/failures.json` (§5) | **yes** | yes, unchanged |
| the **CRASH** | the failure log's traceback (§5), and uvicorn's own `ERROR: Exception in ASGI application` | **yes**, both | yes, unchanged |

The failure log the four requests wrote, both phases identical:

```
entries: 3
  REFUSAL  HTTP_ERROR      | where POST /projects/OBS233/design/demo         | engine None  | traceback 0 chars
  REFUSAL  BRAIN_NO_PLAN   | where POST /projects/{id}/design/demo           | engine brain | traceback 0 chars
  CRASH    ValidationError | where POST /projects/OBS233CRASH/design/demo    | engine None  | traceback 4000 chars
```

Two things worth naming precisely rather than rounding off:

1. **The REFUSAL and CRASH paths are a file, by design**, and the runbook already says so — they
   are not records that were missing a handler, so #233 changes nothing about them. `failure_log`
   keeps a JSON file on purpose (its own docstring: a failure is a question to ask later); the
   preview's line is a logger on purpose (a health signal read live). The CRASH *also* reaches the
   server's output, as uvicorn's traceback: Starlette's `ServerErrorMiddleware` re-raises after the
   application's `Exception` handler has answered, so `uvicorn.error` logs it. That is uvicorn's
   own handler and owes nothing to this change.
2. **`engine` is absent on the two entries that never resolved an engine.** R2's refusal is raised
   by the gate itself and R4 crashes in `_project_or_404`, both before `_failure_context(engine=…)`
   is reachable. The `engine` field the runbook promises is on the entry that has one —
   `BRAIN_NO_PLAN`, `engine brain`. The runbook's 500 row says the log has "an `engine` field
   naming the preview", which holds for a crash inside generation and not for one before it; that
   sentence is narrowed in this Issue's runbook edit.

## AC-3 — the secret, with the token set

This Issue is the first time these lines are visible at all, so the claim is re-made against a real
stream rather than a captured record.

```
## the secret, in everything this run produced          (both phases)
   files containing BRAIN_PREVIEW_TOKEN (server output + all four response bodies): 0
   grep -ic in server.log: 0
```

The token was generated for the run, used only through `$BRAIN_PREVIEW_TOKEN`, and never printed.
`tests/demo/test_brain_preview_gate.py` carries the same claim as tests (**50 → 53 passed**): the
authorized line is in a real stream and the token is not, four unauthorized shapes put *nothing* in
the output at all, and one mixed run's whole output is searched once for the secret, the near-miss,
the variable's name and the header's name.

## What was configured

`backend/app/observability/log_output.py` — one `StreamHandler` to stderr, on the `buildsmart`
logger, at INFO, installed by `app/main.py` at import. There was **no logging configuration of any
kind** in this application before it, so this is the smallest one that works rather than a change
to an existing one. `buildsmart` is not a new convention: `buildsmart.preview`,
`buildsmart.design_pipeline` and `buildsmart.architect_local_gateway` are every logger the
application names for itself. The reasoning for each choice — not the root, stderr, propagation
left on, configured in the module uvicorn imports, idempotent for `--reload` — is in that module's
docstring, which is the one place it belongs.

**Nothing about what is logged changed.** `preview_log.FIELDS` and `brain_request` are untouched,
the delivered text contains the line the function returns character for character, and the two
lines above carry 10 and 9 of #214's fixed 12 — `_fields` omits the ones that do not apply to a
request, which is #214's behaviour and not a change (`exact_refusal` and `code` are absent from a
served request's line, `plan_sizer`/`plan_family`/`exact_refusal` from a no-plan one). The format adds the level (the runbook
distinguishes INFO from the no-plan WARNING, and `lastResort` could not say which) and the logger
name (three `buildsmart.*` loggers share the handler); there is no timestamp, matching uvicorn's own
default line.

### One boundary, stated

`app/knowledge/embeddings/factory.py` logs under `logging.getLogger(__name__)` → `app.knowledge.…`,
which is **outside** `buildsmart` and therefore still unconfigured. It is a CLI module, not a
request path, and no runbook tells an operator to watch it. Raising it was not asked for and is not
done here; if it is ever wanted, the one-line answer is to give that module a `buildsmart.*` name
like the other three, not to widen this handler to the root.

## Clean-up, done

- the scratch server was stopped (`kill 29294`; `lsof -ti :8733` empty afterwards) in both phases;
- the three seeded projects and the `failures.json` the requests wrote were deleted;
  `app/data/design_versions.json` verified **byte-identical** before and after, both phases (md5
  `7ec316f233cf7c7b886dae8472cda432`);
- no `DISABLE_BRAIN_PREVIEW` file was created at any point;
- the development server on port 8000 (**pid 79460**) still running, untouched, and never requested;
  the live `backend/.env` never read or written — this worktree has none.

## Suites, verbatim

| suite | result |
| --- | --- |
| `tests/test_log_output.py` (new) | **9 passed** |
| `tests/demo/test_brain_preview_gate.py` | **53 passed** (50 after #231, 49 after #214, 42 before) |
| `tests/demo` + `tests/architectural_brain` + `test_brain_fallbacks.py` + `test_engine_preview.py` + `test_demo_p0.py` + `test_log_output.py` | **277 passed, 1 skipped** (5:34) |
| fast suite, `WALLCLOCK_BUDGETS=off … -n 4` | **2557 passed, 884 skipped, 10 xfailed, 0 failed** (7:16) |

#231 reported **2545 passed, 884 skipped, 10 xfailed**. 2545 + 9 (`test_log_output.py`) + 3 (the
gate's new AC-3 tests) = **2557** exactly, and the skip count is unchanged.

**The corpus snapshot suite was deliberately not run** — the same reasoning #214 and #231 recorded:
#209 measured it at ~55 min, #212 proved the gate cannot reach it (`corpus_snapshot.py` calls
`generate_demo_design(project)` with no engine keyword), and a logging handler is reachable from it
only as output nobody asserts on. `agent-regression.yml` on the PR is the authoritative check — see
the PR's note about when CI can first run on this stack.

One observation, not a change: the fast suite rewrites this worktree's own git-ignored
`backend/app/data/design_versions.json` (`tests/test_chat.py` / `tests/test_project_update.py` use
the default path). Pre-existing suite behaviour, unrelated to this Issue, and it happened in the
branch worktree only — the owner's checkout was never touched. The **probe** left it byte-identical,
which is the claim that matters for this report's clean-up.
