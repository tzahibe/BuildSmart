"""The issue lifecycle as an explicit, deterministic state machine.

Every transition the orchestrator can make is listed here; `state_store.transition()` refuses
anything else. Labels mirror these states one-to-one (`labels.state_to_label`).
"""
from __future__ import annotations

QUEUED = "QUEUED"
CLAIMED = "CLAIMED"
WORKING = "WORKING"
PR_OPEN = "PR_OPEN"
CI = "CI"
REVIEW = "REVIEW"
FIX_REQUIRED = "FIX_REQUIRED"
BLOCKED = "BLOCKED"
READY = "READY"
MERGED = "MERGED"
DONE = "DONE"

STATES = (QUEUED, CLAIMED, WORKING, PR_OPEN, CI, REVIEW, FIX_REQUIRED, BLOCKED, READY, MERGED, DONE)

#: States in which an agent process may be running for the issue.
AGENT_ACTIVE_STATES = (WORKING, REVIEW)
#: States in which the issue holds its domain locks and a worktree.
RESOURCE_HOLDING_STATES = (CLAIMED, WORKING, PR_OPEN, CI, REVIEW, FIX_REQUIRED, READY, MERGED)
#: States that satisfy a dependency edge.
SATISFIES_DEPENDENCY = (DONE,)
TERMINAL_STATES = (DONE,)

TRANSITIONS: dict[str, tuple[str, ...]] = {
    QUEUED: (CLAIMED, BLOCKED),
    CLAIMED: (WORKING, PR_OPEN, QUEUED, BLOCKED),       # PR_OPEN: reconciled an existing PR
    WORKING: (PR_OPEN, QUEUED, BLOCKED),                # QUEUED: stale agent requeued
    PR_OPEN: (CI, BLOCKED),
    CI: (REVIEW, FIX_REQUIRED, BLOCKED),
    REVIEW: (READY, FIX_REQUIRED, BLOCKED, CI),         # CI: head moved -> review is stale, re-validate
    FIX_REQUIRED: (WORKING, BLOCKED),
    READY: (MERGED, CI, BLOCKED),                       # CI: base advanced -> re-validate
    MERGED: (DONE, BLOCKED),
    BLOCKED: (QUEUED, PR_OPEN, DONE),                   # lead decisions: requeue / resume PR / close
    DONE: (),
}


class IllegalTransition(RuntimeError):
    pass


def check_transition(src: str, dst: str) -> None:
    if src not in TRANSITIONS:
        raise IllegalTransition(f"unknown state {src!r}")
    if dst not in TRANSITIONS[src]:
        raise IllegalTransition(f"{src} -> {dst} is not an allowed transition")


def is_allowed(src: str, dst: str) -> bool:
    return dst in TRANSITIONS.get(src, ())
