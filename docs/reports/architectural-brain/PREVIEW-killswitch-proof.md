# PREVIEW — the kill switch, proven against a running server

Issue **#231** AC-5, child of ROOT #211. Unit tests cannot prove this one: the defect #214 measured
is about a *process* — a running worker's `os.environ`, which nothing outside the process can
change — so the fix has to be demonstrated on a server that is actually serving.

## What is being proven, and why a unit test is not enough

PR #224 said that blanking `BRAIN_PREVIEW_ENABLED` or `BRAIN_PREVIEW_TOKEN` closes the preview on
the next request. #214 tested it and found three things:

| what was done | what happened |
| --- | --- |
| blanked **both** lines in `.env`, waited | preview **fully open**, same pid — a worker does not re-read `.env` |
| `touch app/main.py` | **closed** — but only because `--reload` respawned the worker |
| variables **exported in the starting shell**, removed from `.env`, reload forced | preview **open**. `load_dotenv()` does not override, and a respawned worker inherits its parent's environment |

In that third configuration the only disable was stopping the process: an owner action under ROOT
#211, and the opposite of "immediately, without a new deployment".

So this run is set up as the **worst case on purpose**:

- the preview's variables are **exported in the shell that starts the server** and exist nowhere
  else — `ls backend/.env` is a `No such file`, so there is no file to edit and no `.env` for a
  worker to re-read;
- the server runs with **no `--reload`**, so there is no reloader to respawn anything: one process,
  one pid, from the first request to the last;
- nothing is unset, nothing is edited, nothing is signalled, nothing is restarted. The only thing
  that happens between request 1 and request 2 is that **one empty file is created**.

## The setup

- host `127.0.0.1`, port `8731`, a **scratch** server started and stopped by this run. The
  development server on port 8000 (pid 79460) was never touched, and the live `backend/.env` was
  never read or written.
- one seeded project, `KS231` (3 bedrooms, 1 wet room, open plan, 132 m² on 11 × 12 m), in this
  worktree's own `app/data/projects.json`, deleted afterwards.
- `BRAIN_PREVIEW_FAMILIES=band` so the one served request costs one family rather than four. It
  narrows what the brain searches; it has no bearing on the gate, which is what is being measured.
- the token was generated for this run, used only through `$BRAIN_PREVIEW_TOKEN`, and never
  written down. The last command greps the whole transcript, both response bodies and the server's
  own output for it: **0 occurrences**.

## The transcript

```
# commands and output, verbatim (token redacted: it is only ever $BRAIN_PREVIEW_TOKEN)

$ ls backend/.env
ls: /Users/mymacbook/projects/sddproject-branched/backend/.env: No such file or directory
$ export BRAIN_PREVIEW_ENABLED=1; export BRAIN_PREVIEW_TOKEN=$(python -c "import secrets;print(secrets.token_urlsafe(32))"); export BRAIN_PREVIEW_FAMILIES=band
$ uv run uvicorn app.main:app --host 127.0.0.1 --port 8731        # NO --reload: one process, one pid
INFO:     Uvicorn running on http://127.0.0.1:8731 (Press CTRL+C to quit)

$ lsof -ti :8731
20563
$ ps eww $PID | tr " " "\n" | grep "^BRAIN_PREVIEW_ENABLED="   # the flag is in the running process
BRAIN_PREVIEW_ENABLED=1

## 1. the preview is open: one authorized request, served
$ curl -X POST ".../design/demo?engine=brain" -H "X-Brain-Preview-Token: $BRAIN_PREVIEW_TOKEN"
   request 1 -> HTTP 200
   body[0:110]: {"plan":{"plot":{"x":0.0,"y":0.0,"width_m":15.0,"depth_m":15.95},"footprint":{"x":2.0,"y":2.0,"width_m":11.0,"
   pid now: 20563

## 2. THE KILL SWITCH: one file, no restart, no variable touched
$ touch backend/DISABLE_BRAIN_PREVIEW
-rw-r--r--@ 1 mymacbook  staff  0 Oct 19 20:09 <repo>/backend/DISABLE_BRAIN_PREVIEW
$ ps eww $PID | tr " " "\n" | grep "^BRAIN_PREVIEW_ENABLED="   # STILL exported, STILL 1
BRAIN_PREVIEW_ENABLED=1
   request 2 (same curl) -> HTTP 422
   body[0:110]: {"detail":"unknown engine 'brain'; expected 'production' or 'concept_engine_v2'"}
   request 3 (an engine that does not exist) -> HTTP 422
   body[0:110]: {"detail":"unknown engine 'banana'; expected 'production' or 'concept_engine_v2'"}
   pid now: 20563

## 3. and it is a switch, not a latch
$ rm backend/DISABLE_BRAIN_PREVIEW
   request 4 -> HTTP 200
   body[0:110]: {"plan":{"plot":{"x":0.0,"y":0.0,"width_m":15.0,"depth_m":15.95},"footprint":{"x":2.0,"y":2.0,"width_m":11.0,"
   pid now: 20563

## the server's own output for the four requests
   INFO:     127.0.0.1:52855 - "POST /projects/KS231/design/demo?engine=brain HTTP/1.1" 200 OK
   INFO:     127.0.0.1:52860 - "POST /projects/KS231/design/demo?engine=brain HTTP/1.1" 422 Unprocessable Entity
   INFO:     127.0.0.1:52861 - "POST /projects/KS231/design/demo?engine=banana HTTP/1.1" 422 Unprocessable Entity
   INFO:     127.0.0.1:52862 - "POST /projects/KS231/design/demo?engine=brain HTTP/1.1" 200 OK

$ grep -ic "$BRAIN_PREVIEW_TOKEN" <the whole transcript, both bodies, the server log>
   0 occurrences of the secret

$ kill $PID ; lsof -ti :8731
      (empty: the probe server is stopped)
```

## What the four requests establish

| # | state of the world | answer | AC |
| --- | --- | --- | --- |
| 1 | flag exported and `1`, token exported, no kill file | **200**, a plan | the preview is genuinely open |
| 2 | *identical*, except `backend/DISABLE_BRAIN_PREVIEW` exists | **422** `unknown engine 'brain'` | **AC-1** — closed on the next request, **same pid 20563**, flag still exported and still `1` (printed from the running process's own environment with `ps eww`, between requests 1 and 2) |
| 3 | same, `?engine=banana` | **422** `unknown engine 'banana'` | **AC-4** — the killed preview's refusal differs from a genuinely unknown engine's in nothing but the name the caller itself asked for |
| 4 | kill file removed | **200**, a plan | **AC-2** — a switch, not a latch; re-opened on the next request, same pid |

**The pid is 20563 for all four**, printed after each one. No restart, no reload, no redeploy, and
no cooperation from the environment that opened the preview — which is the whole of #231's point 1,
and the thing #214 proved was impossible before this.

AC-3 (fail closed on an unreadable path, a permission error or any exception in the check) is a
unit test rather than a line here: constructing a permission error or a broken mount on a live
server means changing the host's filesystem, and the behaviour is a property of
`preview_gate.killed()`, not of the wire. `tests/demo/test_brain_preview_killswitch.py` constructs the real
`PermissionError` with a `chmod 000` directory and then pins the general claim over `OSError`,
`ValueError`, `TypeError`, `MemoryError`, `KeyboardInterrupt` and `RuntimeError`.

## One thing observed and NOT fixed here

No `buildsmart.preview` line appeared in this server's output, for the served requests or the
refused ones — the 14 lines in the log are uvicorn's own. #214's runbook §5 says one line per
brain request is written "to the logger `buildsmart.preview`, in the server's own output", and
under a plain `uvicorn app.main:app` the application's root logger has no handler, so an `INFO`
record on that logger goes nowhere. The unit tests capture it with `caplog` and it is really
emitted; what is missing is a handler in the deployed configuration. That is an observability gap
in #214's work, it is not the kill switch, and #231 does not touch it — recorded here because this
run is where it was visible.

## Clean-up, done

- the probe server was stopped (`kill 20563`; `lsof -ti :8731` empty afterwards);
- `backend/DISABLE_BRAIN_PREVIEW` removed;
- the seeded `backend/app/data/projects.json` and the `failures.json` the two refusals wrote
  removed; `app/data/design_versions.json` verified byte-identical (md5
  `7b912c31d7f343f836ba67e93909259b`) before and after;
- the development server on port 8000 (pid 79460) still running, untouched, and never requested.
