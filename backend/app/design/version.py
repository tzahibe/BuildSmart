"""DesignVersion: an immutable snapshot of one successful design generation — enough to reproduce/
explain it later (what was asked, what the model actually said, what the authoritative merge changed,
what the solver decided) without re-running anything. Introduced so `app/projects/update.py` can create
a NEW version on every design-affecting change instead of overwriting `Project`'s design fields in
place (the previous behavior — see `app/design/pipeline.py`'s `set_design_model` call, still used to
mirror the ACTIVE version into `Project`'s flat fields for backward compatibility, but no longer the
only record of a generation).

Versions are never mutated once created — "rollback" (see `app/projects/update.py`) only repoints
`Project.active_design_version_id` to an existing version's id; it never edits a version or calls the
model/solver again.
"""

import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from app.projects.models import Room


class DesignVersion(BaseModel):
    design_version_id: str
    project_id: str
    created_at: datetime
    supersedes_id: str | None = None

    # The ArchitectModelRequest actually sent (model_dump(mode="json")) — lets a later reader see exactly
    # what budget/constraints the model was given, including the area-budget reservation.
    request_snapshot: dict

    # Populated only when the gateway used exposes diagnostics (today: LocalArchitectModelGateway via
    # its `last_diagnostics` attribute) — empty for mock/remote, which don't produce any.
    adapter_diagnostics: list[str] = Field(default_factory=list)

    # The ArchitecturalSpec AFTER app.architect.authoritative_merge.merge_authoritative_requirements —
    # i.e. what actually went into the Geometry Solver, safe_room/etc. already injected.
    spec_snapshot: dict

    # GeometrySolverResult, dumped: status, checked constraints, scores, unsatisfiable_reason.
    solver_summary: dict

    rooms: list[Room]
    design_notes: list[str] = Field(default_factory=list)


class DesignVersionRepository(ABC):
    @abstractmethod
    def get(self, design_version_id: str) -> DesignVersion | None: ...

    @abstractmethod
    def list_for_project(self, project_id: str) -> list[DesignVersion]: ...

    @abstractmethod
    def append(self, version: DesignVersion) -> DesignVersion: ...


class JsonFileDesignVersionRepository(DesignVersionRepository):
    """Same deliberately minimal JSON-file storage convention as JsonFileProjectRepository/
    JsonFileConversationRepository — keyed by project_id, each value an append-only list of version
    dicts in creation order."""

    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path

    def _load(self) -> dict[str, list[dict]]:
        if not self._file_path.exists():
            return {}
        with self._file_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data: dict[str, list[dict]]) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        with self._file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    def get(self, design_version_id: str) -> DesignVersion | None:
        data = self._load()
        for versions in data.values():
            for record in versions:
                if record.get("design_version_id") == design_version_id:
                    return DesignVersion.model_validate(record)
        return None

    def list_for_project(self, project_id: str) -> list[DesignVersion]:
        data = self._load()
        return [DesignVersion.model_validate(record) for record in data.get(project_id, [])]

    def append(self, version: DesignVersion) -> DesignVersion:
        data = self._load()
        records = data.get(version.project_id, [])
        records.append(json.loads(version.model_dump_json()))
        data[version.project_id] = records
        self._save(data)
        return version
