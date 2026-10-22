# Engine Preview Gate (`?engine=`)

Status: IMPLEMENTED (Issue #212, ROOT #211; the kill switch #231) — the preview ships **DEFAULT OFF**

## Current behavior

`POST /projects/{id}/design/demo` and `.../design/demo/stream` accept `?engine=` to generate the
SAME brief through a development engine instead of the production path, so engine progress is
visually inspectable in the existing UI. Two of those engines are gated.

| `?engine=` | who may ask | what it runs |
| --- | --- | --- |
| absent / `production` | anyone | production. The default; the gate costs it nothing. |
| `concept_engine_v2` | anyone | a per-request override of `general_pipeline.CONCEPT_ENGINE_V2_ENABLED`, which stays globally `False`. Not gated: it was never an unauthorized path to unfinished geometry. |
| `brain` | **flag + token** | the Architectural Brain (#197) — `service._brain_result`. |
| `e1_rear_band` | **flag + token** | E1's garden-facing public band (`service._rear_band_selection`). |

Before #212, `?engine=brain` **was** the authorization: any caller who typed the parameter reached
the brain, and nothing could be turned off without a new deployment. Now a gated request must
satisfy both halves of `app/demo/preview_gate.py`, and **both are read from the environment on
every request**:

| variable | default | meaning |
| --- | --- | --- |
| `BRAIN_PREVIEW_ENABLED` | unset = **OFF** | `1`, `true`, `yes` or `on` (any case, surrounding space ignored) opens the preview. Anything else — unset, empty, `0`, `false`, a typo — is OFF, because the dangerous direction of a misread flag is the one that opens it. |
| `BRAIN_PREVIEW_TOKEN` | unset = **nobody** | the shared secret. An unset or empty value authorizes nobody, so a deployment that forgets it is closed rather than open. |
| `BRAIN_PREVIEW_FAMILIES` | the measured four | comma-separated; may only NARROW the layout families (see below). |
| `BRAIN_PREVIEW_SIZER` | `exact` | the brain's sizer. |
| `BRAIN_PREVIEW_KILL_FILE` | unset | an **additional** path whose existence closes the preview. `preview_gate.DEFAULT_KILL_FILE` (`backend/DISABLE_BRAIN_PREVIEW`) is checked whatever this says, so configuration can add a kill location and can never move or remove the built-in one. |

The secret is presented in the **`X-Brain-Preview-Token`** request header and compared with
`hmac.compare_digest`. It is never logged, never echoed in a response, and no value is committed to
this repository — `.env.example` carries the name with an empty value only.

### The kill switch, and why reading the environment per request was not enough (#231)

`preview_gate.killed()`, consulted by `enabled()` and therefore by the single `authorized()` call
`_resolve_engine` already makes: **the existence of `backend/DISABLE_BRAIN_PREVIEW` closes the
preview**, resolved per request, overriding every other signal.

#212 read both halves of the gate per request, and PR #224 concluded from that that blanking either
variable closes the preview on the next request. #214 measured the claim against a running server
and it is **false** in the configuration that matters:

| what was done | what happened |
| --- | --- |
| blanked both lines in `.env`, waited | preview **open**, same pid — a worker does not re-read `.env`, and a process's `os.environ` cannot be changed from outside the process |
| `touch app/main.py` | closed — but only because `--reload` respawns the worker |
| the variables **exported** in the starting shell, removed from `.env`, reload forced | preview **open**: `load_dotenv()` does not override, and a respawned worker inherits its parent's environment |

In the third case the only disable was stopping the process — an owner action under ROOT #211 and
the opposite of "immediately, without a new deployment". A file is the one signal an operator can
change from **outside** the process, that needs no cooperation from the environment that enabled the
preview, and that the next request sees.

- **Resolved per request, never cached.** Create the file and the next request refuses; remove it
  and the next request is served (if the flag and token are still set — removing it grants nothing).
- **It beats an exported, truthy `BRAIN_PREVIEW_ENABLED`.** Proven on a running server, same pid
  throughout: `docs/reports/architectural-brain/PREVIEW-killswitch-proof.md`.
- **It fails closed.** `os.lstat`, not an existence helper: `Path.exists()` swallows every `OSError`
  and answers "keep serving" for a permission error or a broken mount. Exactly one outcome means
  not killed — `FileNotFoundError`. A permission error, an unusable path, a `TypeError`, a
  `KeyboardInterrupt` mid-check: **disabled**. A gate that cannot decide refuses.
- **The path is derived from the module's own location**, not from the working directory, so the
  path the runbook names is the path the running process checks however it was started.
- **It adds no refusal, no status and no message of its own**, and the `lstat` runs for every
  `?engine=` value because `authorized()` is still consulted first and unconditionally — so a
  killed preview is byte-identical to one that does not exist, and there is no new timing oracle.
- **The gate stays write-free.** Its only contact with the outside world is one read; nothing in
  `preview_gate` creates, writes, moves or deletes a path, so the gate cannot be what re-opens the
  preview either.

### Why the environment and not a module constant

`CONCEPT_ENGINE_V2_ENABLED`, `RECTILINEAR_REALIZER_ENABLED` and `LIVING_KITCHEN_MERGE_ENABLED` are
module-level constants, and flipping one of those needs a new deployment — which cannot satisfy
ROOT #211's "instantly disablable". The repository's existing convention for configuration that
must change without a deployment is `app/architect/config.py`'s `*_from_env()` functions, read at
call time, and `preview_gate` follows it rather than inventing a third mechanism. Nothing is
enabled because a module was imported; `preview_gate` contains no committed `True`.

### Refusal codes

| status | body | when |
| --- | --- | --- |
| 422 | `unknown engine '<value>'; expected 'production' or 'concept_engine_v2'` | the flag is OFF, the token is missing, or the token is wrong — **and also** when the engine name genuinely does not exist. The two are deliberately indistinguishable. |
| 422 | `unknown engine '<value>'; expected 'production', 'concept_engine_v2', 'brain' or 'e1_rear_band'` | an AUTHORIZED caller asked for a name that does not exist. Authorization is not a bypass of validation. |
| 422 | `{"code": "BRAIN_NO_PLAN", ...}` | authorized, reached the brain, the brain could not plan the brief. |
| 422 | `{"code": "E1_REAR_BAND_UNAVAILABLE"/"E1_REAR_BAND_NOT_PLANNABLE", ...}` | authorized, reached E1's preview, likewise. |

The first message lists **only** the engines the caller may ask for. Naming the previews
unconditionally would make the error text itself the disclosure the gate exists to prevent, which
is also why `e1_rear_band` is gated by the same check as the brain rather than left open: an
ungated second preview in that list would announce that a hidden one exists.
`preview_gate.authorized` is consulted first and unconditionally for every `?engine=` value, so the
work done — and therefore the time taken — is the same whatever was asked for. Neither the message
nor the timing is an oracle.

### The layout families are configuration, not a constant

`BRAIN_SIZER`/`BRAIN_FAMILIES` used to be module constants in `app/demo/service.py`, which made
"enable a family" a one-word edit to a line of production source. They are now
`preview_gate.sizer()`/`families()`. `BRAIN_PREVIEW_FAMILIES` is filtered through
`preview_gate.ALLOWED_FAMILIES` = `band`, `spine`, `stack`, `cells` (the layouts measured on the
frozen six), so configuration can only narrow the preview: a name outside that set is dropped
rather than honoured, and an empty or entirely-unrecognised list falls back to the default rather
than silently sizing nothing. **#208's `generator` family took a day-2 gate verdict of STOP and is
not in the allow-list** (`preview_gate.GATE_FAILED_FAMILIES` says so by name), so no environment
variable can show an owner a plan it made. Widening the set is a code change with a review.

### One preview request at a time, in a process of its own (#246)

A gated preview is not only *authorized* at the gate, it is *admitted*. `preview_isolation.plan_set`
is the one seam either endpoint runs an engine through, and a gated engine there takes one of
`preview_gate.max_concurrency()` slots — **1 by default and 1 at most** — and runs in a **child
process** (`python -m app.demo.preview_isolation`) at +10 niceness. Production and Concept Engine v2
run where they always ran, in this process, with no admission check and no child.

**Why.** #226 measured production's own latency going 1.65 s quiet → 5.89 s beside two brain
requests → 9.29 s beside four, worst case 16.87 s, recovering fully afterwards. #246 repeated that
protocol with a same-session control: the unchanged code moved production's median ×1.98 and its
worst case ×7.67, and a *single* brain request moved the worst case ×6.04. With the limit and the
child process production measures **0.337–0.338 s at 0, 2 and 4 requested brain requests** against a
0.333–0.347 s quiet baseline (`PREVIEW-isolation-proof.md`).

Four properties worth knowing:

- **The primitive is a `threading.Lock` around a counter, not an `asyncio.Semaphore`**, which would
  have bounded nothing: the route handlers are plain `def`, so Starlette runs them on a worker
  thread with no event loop, and the streaming endpoint does the work on its own bare thread. Making
  the handler `async def` to await a semaphore would have put a 30-second solver on the event loop
  thread.
- **A second simultaneous request is refused, not queued** — `PREVIEW_BUSY`, HTTP 503,
  `Retry-After`, measured at 2.5–9 ms. A brain request costs 31.6 s median, so queueing would make
  the second caller wait up to 49 s before their own work started.
- **Admission is checked after authorization**, so only an authorized caller can ever see
  `PREVIEW_BUSY`; with the only slot taken an unauthorized `?engine=brain` still gets the one 422
  that names no hidden engine. The new code is not a new oracle.
- **The child is not given `BRAIN_PREVIEW_TOKEN`** — the authorization decision was taken in the
  parent's request frame and is finished — but it does inherit the rest of the configuration and it
  calls `log_output.configure()` itself, so #233's one line per request still reaches the server's
  own output from inside the child.

`BRAIN_PREVIEW_MAX_CONCURRENCY` has the same asymmetry as `BRAIN_PREVIEW_FAMILIES`: it may narrow
the preview and can never widen it. `0` and a negative value are the default too, because closing
the preview is the kill switch's job and two ways to turn it off is one way too many.

## Operating it

**To enable** (owner action; the preview ships off and the owner turns it on):

1. Generate a secret that is not reused anywhere else, e.g. `python -c "import secrets;
   print(secrets.token_urlsafe(32))"`.
2. Set `BRAIN_PREVIEW_TOKEN=<secret>` and `BRAIN_PREVIEW_ENABLED=1` in the server's environment.
   Set the token **first**: with the flag on and no token, the preview is closed, which is the safe
   ordering either way.
3. Call it: `curl -X POST ".../projects/<id>/design/demo?engine=brain" -H "X-Brain-Preview-Token:
   <secret>"`. The frontend's engine switch does not send the header, so the preview is reachable
   from a tool that can set one, not from the UI as it stands (deliberately out of #212's scope).

**To emergency-disable**, in this order:

1. **`touch backend/DISABLE_BRAIN_PREVIEW`** — the kill switch. Closes the preview on the NEXT
   request with no redeploy, no restart and no variable unset, and it is the only lever that works
   when the variables were exported in the starting shell. Use this first, always. `rm` re-opens.
2. **unset or blank `BRAIN_PREVIEW_TOKEN`** — additionally, if the secret leaked: the kill switch
   closes the door, it does not change the lock.
3. **unset or blank `BRAIN_PREVIEW_ENABLED`** — the tidy close once the incident is over.

Levers 2 and 3 are read per request, but only reach the process if the variables live in `.env`
**and** the worker re-reads it; lever 1 depends on neither. Nothing caches any of the three
decisions, and the next `?engine=brain` becomes the ordinary unknown-engine 422. There is no third
state and no grace period. The runbook is `docs/runbooks/brain-preview.md` §3.

## Authoritative implementation

- `app/demo/preview_gate.py` — `enabled()`, `authorized()`, `killed()`, `kill_file_paths()`,
  `DEFAULT_KILL_FILE`, `sizer()`, `families()`, the environment-variable names,
  `ALLOWED_FAMILIES`, `GATE_FAILED_FAMILIES`.
- `app/demo/router.py` — `_resolve_engine`/`EngineChoice` (the single resolution point for both
  endpoints), `_unknown_engine` (the one refusal), the `X-Brain-Preview-Token` header parameter.
- `app/demo/preview_isolation.py` (#246) — `plan_set` (the one seam either endpoint runs an engine
  through), `admitted()`, `occupancy()`, `PreviewBusy`, `PreviewProcessError`, `_in_this_process` /
  `_in_child_process` (deliberately the same signature), and the `__main__` guard the child runs as.
- `app/demo/service.py` — `_brain_result` reads `preview_gate.sizer()`/`families()`.
- `app/main.py` — `/health` reports `preview_isolation.occupancy()`.
- `backend/.env.example` — the variable names, with no values.

## Tests

- `backend/tests/demo/test_brain_preview_killswitch.py` — #231's AC-1..AC-4 and AC-7: the file
  beats every truthy spelling of an exported flag, both gated engines and both routes, removal
  re-enables with no restart, nothing is cached, a real `PermissionError` and any other exception
  refuse, configuration cannot move the built-in path, the refusal is identical to both the
  unknown-engine and the flag-off refusal, and the kill check is counted on every engine name.
- `backend/tests/demo/test_brain_preview_gate.py` — AC-1..AC-5 and AC-7 on the wire: OFF by
  default, only an explicit true opens it, the identical refusal, both endpoints gated, nothing
  request-shaped standing in for the header, a runtime flip between two requests in one process,
  production and `concept_engine_v2` untouched, and `generator` absent from what `run_brain` is
  handed even when the environment asks for it.
- `backend/tests/demo/test_brain_preview_concurrency.py` — #246: two concurrent requests admit
  exactly one (two real threads, two real children), the ceiling cannot be raised, the slot is
  released on success/refusal/crash/watchdog, the refusal is typed and reaches the failure log, an
  unauthorized caller can never see it, production never leaves this process, the child is not given
  the token, and the real `python -m app.demo.preview_isolation` answers the protocol end to end.
- `backend/tests/test_engine_preview.py` — the pre-existing per-request-override invariants, still
  green: the global Concept Engine v2 flag is never written.

## What this does NOT do

No deployment, no live configuration, no change to the default engine, and no frontend engine
switch for the gated previews. There is no per-user identity and no audit trail of who used the
preview: one shared secret, held by the owner, for an internal preview — not an authentication
system. The app has no auth seam to reuse (no FastAPI dependency, no middleware, no `auth`/`deps`
module, nothing reading an `Authorization` header on an inbound request), which is why this is a
shared secret rather than an integration; if one is ever introduced, this is the one call site to
move.
