# Private House V1 — Scope Decision

Status: APPROVED (decision), no code — this is a scope freeze, not a capability

## Current behavior

Scope for the private-house V1 engine is frozen on `SPATIAL_ENGINE_SPEC_V2_1.md`'s domain model.
No redesign of that domain model without a new decision doc superseding this one.

## Authoritative implementation

N/A — a decision, not a capability. Enforced by review convention, not code.

## Current constraints/invariants

Any change that would require redesigning the domain model itself (as opposed to building new
capability on top of it, e.g. Multi-Level, L-Massing) needs a new decision doc before
implementation starts.

## Supersedes

N/A.

## Known follow-ups

None — this is a standing constraint, not a task.

## Evidence/history

`docs/PRIVATE_HOUSE_V1_ENGINE_DECISION.md`, `docs/SPATIAL_ENGINE_SPEC_V2_1.md` (the frozen
domain model this decision points at).

## Last verified against git

`1d648c3` (main HEAD).
