"""Shared fixtures. Nothing here talks to GitHub or Claude — fakes only (see tests/fakes.py)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from agent_team.config import Config, load_config

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / ".agent" / "config.yaml"


@pytest.fixture
def repo_config(tmp_path: Path) -> Config:
    """The real config file, rooted at a temp directory (state/logs/worktrees land in tmp)."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".agent").mkdir()
    shutil.copy(CONFIG_PATH, root / ".agent" / "config.yaml")
    return load_config(repo_root=root)


VALID_BODY = """### Goal

Document the agent workflow's operator commands in the backend README so a new engineer can start the orchestrator.

### Current behavior

The README does not mention scripts/agentctl at all.

### Required behavior

A short "Autonomous workflow" section in backend/README.md that lists status/run/once/dry-run.

### Acceptance Criteria

- AC-1: backend/README.md contains a section titled "Autonomous workflow"
- AC-2: the section mentions `scripts/agentctl status`
- AC-3: the fast backend test suite still passes

### Out of scope

Any change under backend/app. Any change to the orchestrator's code.

### Affected domains

knowledge, backend

### Risk

LOW

### Resource class

LIGHT

### Dependencies

none

### Required locks

docs (shared)

### Verification plan

- AC-1 -> grep:backend/README.md:Autonomous workflow
- AC-2 -> grep:backend/README.md:agentctl status
- AC-3 -> pytest:backend/tests/test_projects.py

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: none

### Expected documentation changes

backend/README.md only.
"""


@pytest.fixture
def valid_body() -> str:
    return VALID_BODY
