# Engine Preview Gate (`?engine=`)

Status: IMPLEMENTED (Issue #212, ROOT #211) — the preview ships **DEFAULT OFF**

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

The secret is presented in the **`X-Brain-Preview-Token`** request header and compared with
`hmac.compare_digest`. It is never logged, never echoed in a response, and no value is committed to
this repository — `.env.example` carries the name with an empty value only.

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

**To emergency-disable**, either lever closes it on the NEXT request, with no redeploy and no
restart:

- unset or blank `BRAIN_PREVIEW_ENABLED` (the flag), **or**
- unset or blank `BRAIN_PREVIEW_TOKEN` (revoke the secret; use this if the secret leaked).

Both are read per request, nothing caches the decision, and the next `?engine=brain` becomes the
ordinary unknown-engine 422. There is no third state and no grace period.

## Authoritative implementation

- `app/demo/preview_gate.py` — `enabled()`, `authorized()`, `sizer()`, `families()`, the
  environment-variable names, `ALLOWED_FAMILIES`, `GATE_FAILED_FAMILIES`.
- `app/demo/router.py` — `_resolve_engine`/`EngineChoice` (the single resolution point for both
  endpoints), `_unknown_engine` (the one refusal), the `X-Brain-Preview-Token` header parameter.
- `app/demo/service.py` — `_brain_result` reads `preview_gate.sizer()`/`families()`.
- `backend/.env.example` — the variable names, with no values.

## Tests

- `backend/tests/demo/test_brain_preview_gate.py` — AC-1..AC-5 and AC-7 on the wire: OFF by
  default, only an explicit true opens it, the identical refusal, both endpoints gated, nothing
  request-shaped standing in for the header, a runtime flip between two requests in one process,
  production and `concept_engine_v2` untouched, and `generator` absent from what `run_brain` is
  handed even when the environment asks for it.
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
