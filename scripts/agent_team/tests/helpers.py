"""Builders shared by the orchestration tests."""
from __future__ import annotations

from agent_team.issue_contract import IssueContract, parse_contract
from agent_team.state_store import StateStore
from agent_team.tests.conftest import VALID_BODY

KNOWN_LOCKS = ("planner-core", "geometry-core", "validator-core", "requirements-parser",
               "knowledge-index", "frontend-review", "database-schema", "ci-infra", "docs")


def make_contract(number: int, *, title: str = "[agent] Sample task", risk: str = "LOW",
                  resource: str = "LIGHT", domains: str = "knowledge", deps: str = "none",
                  locks: str = "docs (shared)") -> IssueContract:
    body = (VALID_BODY
            .replace("knowledge, backend", domains)
            .replace("\nLOW\n", f"\n{risk}\n")
            .replace("\nLIGHT\n", f"\n{resource}\n")
            .replace("### Dependencies\n\nnone", f"### Dependencies\n\n{deps}")
            .replace("docs (shared)", locks))
    return parse_contract(number, title, body, known_locks=KNOWN_LOCKS)


def track(store: StateStore, c: IssueContract, state: str = "QUEUED"):
    return store.track(c.number, title=c.title, risk=c.risk, resource_class=c.resource_class,
                       domains=list(c.domains), dependencies=list(c.dependencies), contract=c.to_dict(), state=state)
