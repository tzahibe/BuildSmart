"""The label catalogue: issue states, domains, risk and resource classes.

GitHub labels are the *visible mirror* of orchestration state; the SQLite state store is the
orchestrator's truth and reconciliation keeps the two aligned. Every state the machine can be in
has exactly one `agent:*` label so a human can read the board without the CLI.
"""
from __future__ import annotations

from dataclasses import dataclass

STATE_LABEL_PREFIX = "agent:"


@dataclass(frozen=True)
class Label:
    name: str
    color: str
    description: str


STATE_LABELS: tuple[Label, ...] = (
    Label("agent:draft", "d4c5f9", "Contract written, not yet validated/queued by the Team Lead"),
    Label("agent:queued", "0e8a16", "Validated contract waiting for the scheduler"),
    Label("agent:claimed", "1d76db", "Claimed by the orchestrator; branch/worktree being prepared"),
    Label("agent:working", "0052cc", "A worker agent is implementing it"),
    Label("agent:pr-open", "5319e7", "Pull request opened by the orchestrator"),
    Label("agent:ci", "fbca04", "Waiting for the deterministic CI gates"),
    Label("agent:review", "c2e0c6", "Deterministic gates green; independent review running"),
    Label("agent:fix-required", "e99695", "CI/review found a problem; a repair attempt is scheduled"),
    Label("agent:blocked", "b60205", "Retry budget exhausted or a decision is needed from the Team Lead"),
    Label("agent:ready-for-owner", "0e8a16", "Every gate green; waiting for the owner's merge decision (never auto-merged)"),
    Label("agent:merged", "6f42c1", "Merged to main; post-merge smoke running"),
    Label("agent:done", "2cbe4e", "Smoke green; issue closed by the orchestrator"),
)

DOMAIN_LABELS: tuple[Label, ...] = tuple(
    Label(f"domain:{d}", "bfdadc", f"Affects the {d} domain")
    for d in ("frontend", "backend", "geometry", "validator", "knowledge", "ai", "qa", "infra")
)

RISK_LABELS: tuple[Label, ...] = (
    Label("risk:low", "c2e0c6", "Docs, isolated tests, small cosmetic UI — may auto-merge"),
    Label("risk:medium", "fbca04", "Normal product feature — needs Team Lead approval"),
    Label("risk:high", "b60205", "Invariants, validator rules, schema, security — architecture review"),
)

RESOURCE_LABELS: tuple[Label, ...] = (
    Label("resource:light", "ededed", "Weight 1"),
    Label("resource:medium", "d0d0d0", "Weight 2"),
    Label("resource:heavy", "a0a0a0", "Weight 3 — needs the heavy validation pool"),
)

OWNER_APPROVED_LABEL = "owner:approved"
OWNER_LABELS: tuple[Label, ...] = (
    Label(OWNER_APPROVED_LABEL, "8b0000", "The owner approved this Issue for execution — only the owner sets this"),
)

ALL_LABELS: tuple[Label, ...] = STATE_LABELS + DOMAIN_LABELS + RISK_LABELS + RESOURCE_LABELS + OWNER_LABELS

STATE_LABEL_NAMES = tuple(l.name for l in STATE_LABELS)


def state_to_label(state: str) -> str:
    """`WORKING` -> `agent:working`, `PR_OPEN` -> `agent:pr-open`, `FIX_REQUIRED` -> `agent:fix-required`."""
    return STATE_LABEL_PREFIX + state.lower().replace("_", "-")


def label_to_state(label: str) -> str | None:
    if not label.startswith(STATE_LABEL_PREFIX):
        return None
    return label[len(STATE_LABEL_PREFIX):].upper().replace("-", "_")


def metadata_labels(domains: tuple[str, ...], risk: str, resource_class: str) -> list[str]:
    return [f"domain:{d}" for d in domains] + [f"risk:{risk.lower()}", f"resource:{resource_class.lower()}"]
