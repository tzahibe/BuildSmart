import json
import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path

from app.projects.models import (
    PoolField,
    Project,
    ProjectCreate,
    ProjectUpdate,
    Room,
    TaggedBool,
    TaggedInt,
)


class ProjectRepository(ABC):
    @abstractmethod
    def get(self, project_id: str) -> Project | None: ...

    @abstractmethod
    def create(self, data: ProjectCreate) -> Project: ...

    @abstractmethod
    def update(self, project_id: str, data: ProjectUpdate) -> Project | None: ...

    @abstractmethod
    def replace(self, project_id: str, project: Project) -> Project:
        """Persists `project` (already fully computed by the caller) verbatim under `project_id`. The
        single lower-level primitive `app.projects.update.apply_project_update` and design-version
        rollback build on — unlike `update()`/`set_parsed_requirements()`/`set_design_model()` above,
        this doesn't itself decide what changed; callers that already have a complete, valid `Project`
        to save use this directly instead of yet another bespoke partial-field setter."""
        ...

    @abstractmethod
    def set_parsed_requirements(
        self,
        project_id: str,
        *,
        floors: TaggedInt,
        bedrooms: TaggedInt,
        safe_room: TaggedBool,
        parking_spaces: TaggedInt,
        pool: PoolField,
    ) -> Project | None: ...

    @abstractmethod
    def set_design_model(
        self,
        project_id: str,
        *,
        site_width_m: float,
        site_depth_m: float,
        rooms: list[Room],
        design_notes: list[str],
        geometric_design: dict | None = None,
    ) -> Project | None: ...


class JsonFileProjectRepository(ProjectRepository):
    """Stores projects in a single JSON file, keyed by project_id.

    This is a deliberately minimal, temporary storage mechanism (see
    specs/001-project-creation/research.md). Once real persistence needs
    arrive (concurrent writers, querying, larger volume), replace this with
    a Postgres-backed implementation of ProjectRepository — nothing outside
    this file needs to change, since callers only depend on the interface.
    """

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

    def get(self, project_id: str) -> Project | None:
        data = self._load()
        record = data.get(project_id)
        return None if record is None else Project.model_validate(record)

    def create(self, data: ProjectCreate) -> Project:
        now = datetime.now(UTC)
        project = Project(
            project_id=str(uuid.uuid4()),
            city=data.city,
            street=data.street,
            plot_area_m2=data.plot_area_m2,
            built_area_m2=data.built_area_m2,
            description=data.description,
            status="created",
            created_at=now,
            updated_at=now,
        )
        store = self._load()
        store[project.project_id] = json.loads(project.model_dump_json())
        self._save(store)
        return project

    def replace(self, project_id: str, project: Project) -> Project:
        store = self._load()
        store[project_id] = json.loads(project.model_dump_json())
        self._save(store)
        return project

    def update(self, project_id: str, data: ProjectUpdate) -> Project | None:
        store = self._load()
        record = store.get(project_id)
        if record is None:
            return None

        existing = Project.model_validate(record)
        updates = data.model_dump(exclude_unset=True)
        updated = existing.model_copy(update={**updates, "updated_at": datetime.now(UTC)})

        store[project_id] = json.loads(updated.model_dump_json())
        self._save(store)
        return updated

    def set_design_model(
        self,
        project_id: str,
        *,
        site_width_m: float,
        site_depth_m: float,
        rooms: list[Room],
        design_notes: list[str],
        geometric_design: dict | None = None,
    ) -> Project | None:
        store = self._load()
        record = store.get(project_id)
        if record is None:
            return None

        existing = Project.model_validate(record)
        updated = existing.model_copy(
            update={
                "site_width_m": site_width_m,
                "site_depth_m": site_depth_m,
                "rooms": rooms,
                "design_notes": design_notes,
                "geometric_design": geometric_design,
                "design_generated_at": datetime.now(UTC),
            }
        )

        store[project_id] = json.loads(updated.model_dump_json())
        self._save(store)
        return updated

    def set_parsed_requirements(
        self,
        project_id: str,
        *,
        floors: TaggedInt,
        bedrooms: TaggedInt,
        safe_room: TaggedBool,
        parking_spaces: TaggedInt,
        pool: PoolField,
    ) -> Project | None:
        store = self._load()
        record = store.get(project_id)
        if record is None:
            return None

        existing = Project.model_validate(record)
        updated = existing.model_copy(
            update={
                "floors": floors,
                "bedrooms": bedrooms,
                "safe_room": safe_room,
                "parking_spaces": parking_spaces,
                "pool": pool,
                "requirements_parsed_at": datetime.now(UTC),
            }
        )

        store[project_id] = json.loads(updated.model_dump_json())
        self._save(store)
        return updated
