"""A `Proposal` is the ONLY thing chat ever writes on its own — a description of a change, not the
change itself. See `app/chat/router.py`: confirming a proposal calls the exact same
`apply_project_update`/`rollback_to_design_version` Settings uses, with `source="CHAT"`. There is no
other, chat-specific way to mutate a Project.

At most one proposal is ever "pending" (unconfirmed) per project — creating a new one supersedes
whatever was pending before, and `JsonFileProposalRepository` only ever stores the latest per project,
which is also what makes staleness detection trivial: confirming/canceling always names a specific
`proposal_id`, and if the stored proposal for that project doesn't have that exact id anymore (because a
newer one replaced it, or it was already consumed), the lookup simply returns nothing — there is no
separate "is this stale" check to get wrong.
"""

import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from app.chat.proposal_action import ProposalActionType
from app.projects.update import ProjectUpdateDiff


class Proposal(BaseModel):
    proposal_id: str
    project_id: str
    action: ProposalActionType
    diff: ProjectUpdateDiff | None = None
    rollback_design_version_id: str | None = None
    rollback_ordinal: int | None = None
    summary: str
    created_at: datetime
    consumed: bool = False


class ProposalSummary(BaseModel):
    """What's exposed to the frontend on a pending assistant message — never the raw diff, just enough
    to render Confirm/Cancel and reference it."""

    proposal_id: str
    action: ProposalActionType
    summary: str


class ProposalRepository(ABC):
    @abstractmethod
    def get_pending_for_project(self, project_id: str, proposal_id: str) -> Proposal | None:
        """Returns the proposal only if `proposal_id` is EXACTLY the current pending (unconsumed) one
        for this project — this is the single staleness check the whole feature relies on."""
        ...

    @abstractmethod
    def save(self, proposal: Proposal) -> Proposal:
        """Stores `proposal` as the project's current one, superseding whatever was there before."""
        ...

    @abstractmethod
    def mark_consumed(self, project_id: str, proposal_id: str) -> None: ...


class JsonFileProposalRepository(ProposalRepository):
    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path

    def _load(self) -> dict[str, dict]:
        if not self._file_path.exists():
            return {}
        with self._file_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data: dict[str, dict]) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        with self._file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    def get_pending_for_project(self, project_id: str, proposal_id: str) -> Proposal | None:
        data = self._load()
        record = data.get(project_id)
        if record is None or record.get("proposal_id") != proposal_id or record.get("consumed"):
            return None
        return Proposal.model_validate(record)

    def save(self, proposal: Proposal) -> Proposal:
        data = self._load()
        data[proposal.project_id] = json.loads(proposal.model_dump_json())
        self._save(data)
        return proposal

    def mark_consumed(self, project_id: str, proposal_id: str) -> None:
        data = self._load()
        record = data.get(project_id)
        if record is not None and record.get("proposal_id") == proposal_id:
            record["consumed"] = True
            self._save(data)
