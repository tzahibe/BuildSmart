"""The single project-mutation operation — `apply_project_update()` — that BOTH the Settings UI and a
future Chat Agent must go through (see this module's own docstring on why there is deliberately no
second, chat-specific write path). Chat isn't implemented yet (explicitly out of scope this milestone);
this module's `ProjectUpdateRequest.source` already distinguishes "CHAT" from "SETTINGS" so that when a
future Chat Agent is built, it submits exactly the same typed `ProjectUpdateDiff` this operation already
accepts — after an explicit user confirmation in the chat UI, never from raw free text directly.

REQUIREMENTS VS. HARD CONSTRAINTS (see the audit's point 2): `Project`'s requirement fields (floors,
bedrooms, safe_room, parking_spaces, pool) are the ONE authoritative representation of these facts. This
module never creates a second, independently-editable copy of them as "hard constraints" — the
`RequiredRoomConstraint`s the Architect Model pipeline actually uses are DERIVED fresh from these same
fields every time `app/design/pipeline.py::_build_request` runs (already true before this module existed
— see that function). A future Regulation Engine's output would be a second INPUT into that same
derivation (requirements + regulation -> hard constraints), never a field on `Project` that competes with
`bedrooms`/`safe_room` for authority over the same fact.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from app.design.errors_http import DESIGN_PIPELINE_ERRORS
from app.design.pipeline import generate_design_via_solver
from app.design.version import DesignVersion, DesignVersionRepository
from app.projects.models import (
    ChangeLogEntry,
    PoolField,
    Project,
    TaggedBool,
    TaggedInt,
    _check_built_area_fits_plot,
    _check_street_belongs_to_city,
    _known_city,
    _non_empty,
)
from app.projects.preferences import Preference, PreferenceCreate, PreferenceUpdate
from app.projects.repository import ProjectRepository

# Fields whose change actually affects what `generate_design_via_solver` computes TODAY — see
# app/design/pipeline.py's `_build_request`/`_derive_footprint`: only these feed the Architect Model
# request or the footprint. `parking_spaces`/`pool` are genuinely inert (not yet consumed anywhere in
# the pipeline) — listing them here would trigger an expensive real-model regeneration that could not
# possibly produce a different result, which is precisely the "do not regenerate for metadata-only
# changes" the brief asked to avoid.
_REGENERATION_TRIGGERING_FIELDS = frozenset({"floors", "bedrooms", "safe_room", "plot_area_m2", "built_area_m2"})

# Fields with plausible future Regulation Engine relevance (jurisdiction) but no design-pipeline effect
# today — represented, never executed (see UpdateImpact.regulation_recheck).
_REGULATION_RELEVANT_FIELDS = frozenset({"city", "street"})


class UpdateImpact(str, Enum):
    no_regen = "NO_REGEN"
    regenerate_design = "REGENERATE_DESIGN"
    regulation_recheck = "REGULATION_RECHECK"


class ProjectNotFoundError(Exception):
    code = "PROJECT_NOT_FOUND"


class ProjectUpdateDiff(BaseModel):
    """"What to change" — a field left at its default (`None`/empty list) means "leave this alone."
    This is also exactly the request-body schema `PATCH /projects/{id}` accepts (wrapped in
    `ProjectUpdateRequest` below) — Settings and a future Chat Agent both submit this same shape, per
    the module docstring. `None` means "untouched," which is distinct from `TaggedInt`/`TaggedBool`'s
    OWN "unknown" state — a legitimate value a field can be explicitly SET to (source=unknown,
    value=None) versus not mentioned in this diff at all."""

    city: str | None = None
    street: str | None = None
    plot_area_m2: float | None = Field(default=None, gt=0)
    built_area_m2: float | None = Field(default=None, gt=0)
    description: str | None = None
    floors: TaggedInt | None = None
    bedrooms: TaggedInt | None = None
    safe_room: TaggedBool | None = None
    parking_spaces: TaggedInt | None = None
    pool: PoolField | None = None
    add_preferences: list[PreferenceCreate] = Field(default_factory=list)
    update_preferences: list[PreferenceUpdate] = Field(default_factory=list)
    remove_preference_ids: list[str] = Field(default_factory=list)


class ProjectUpdateRequest(BaseModel):
    """The actual `PATCH /projects/{id}` request body — see app/projects/routes/base_routes.py."""

    source: Literal["CHAT", "SETTINGS"]
    diff: ProjectUpdateDiff


@dataclass
class ProjectUpdateResult:
    project: Project
    impact: UpdateImpact
    design_version: DesignVersion | None = None
    design_error: Exception | None = None


def _validate_diff(existing: Project, diff: ProjectUpdateDiff) -> None:
    if diff.city is not None:
        _known_city(diff.city)
    if diff.street is not None:
        _non_empty(diff.street, "street")

    merged_city = diff.city if diff.city is not None else existing.city
    merged_street = diff.street if diff.street is not None else existing.street
    if diff.city is not None or diff.street is not None:
        _check_street_belongs_to_city(merged_city, merged_street)

    merged_plot = diff.plot_area_m2 if diff.plot_area_m2 is not None else existing.plot_area_m2
    merged_built = diff.built_area_m2 if diff.built_area_m2 is not None else existing.built_area_m2
    if diff.plot_area_m2 is not None or diff.built_area_m2 is not None:
        _check_built_area_fits_plot(merged_plot, merged_built)

    if diff.description is not None:
        _non_empty(diff.description, "description")

    known_preference_ids = {preference.preference_id for preference in existing.preferences}
    for update in diff.update_preferences:
        if update.preference_id not in known_preference_ids:
            raise ValueError(f"unknown preference_id in update_preferences: {update.preference_id!r}")
    for preference_id in diff.remove_preference_ids:
        if preference_id not in known_preference_ids:
            raise ValueError(f"unknown preference_id in remove_preference_ids: {preference_id!r}")


def _classify_impact(changed_fields: set[str]) -> UpdateImpact:
    if changed_fields & _REGENERATION_TRIGGERING_FIELDS:
        return UpdateImpact.regenerate_design
    if changed_fields & _REGULATION_RELEVANT_FIELDS:
        return UpdateImpact.regulation_recheck
    return UpdateImpact.no_regen


def _record(change_log: list[ChangeLogEntry], field_name: str, old, new, source: str, at: datetime) -> None:
    change_log.append(ChangeLogEntry(field=field_name, old_value=old, new_value=new, source=source, at=at))


def _apply_diff(existing: Project, diff: ProjectUpdateDiff, source: str, at: datetime) -> tuple[Project, set[str]]:
    updates: dict = {}
    change_log = list(existing.change_log)
    changed_fields: set[str] = set()

    for field_name in ("city", "street", "description"):
        new_value = getattr(diff, field_name)
        if new_value is not None and new_value != getattr(existing, field_name):
            _record(change_log, field_name, getattr(existing, field_name), new_value, source, at)
            updates[field_name] = new_value
            changed_fields.add(field_name)

    for field_name in ("plot_area_m2", "built_area_m2"):
        new_value = getattr(diff, field_name)
        if new_value is not None and new_value != getattr(existing, field_name):
            _record(change_log, field_name, getattr(existing, field_name), new_value, source, at)
            updates[field_name] = new_value
            changed_fields.add(field_name)

    for field_name in ("floors", "bedrooms", "safe_room", "parking_spaces", "pool"):
        new_value = getattr(diff, field_name)
        if new_value is not None and new_value != getattr(existing, field_name):
            old_value = getattr(existing, field_name)
            _record(
                change_log,
                field_name,
                old_value.model_dump(mode="json") if old_value is not None else None,
                new_value.model_dump(mode="json"),
                source,
                at,
            )
            updates[field_name] = new_value
            changed_fields.add(field_name)

    preferences = list(existing.preferences)
    for create in diff.add_preferences:
        preference = Preference(
            preference_id=str(uuid.uuid4()),
            kind=create.kind,
            target=create.target,
            related_target=create.related_target,
            value=create.value,
            priority=create.priority,
            original_text=create.original_text,
            source=source,
            created_at=at,
        )
        preferences.append(preference)
        _record(change_log, "preferences.add", None, preference.model_dump(mode="json"), source, at)
        changed_fields.add("preferences")

    for pref_update in diff.update_preferences:
        for index, preference in enumerate(preferences):
            if preference.preference_id != pref_update.preference_id:
                continue
            new_fields = pref_update.model_dump(exclude_unset=True, exclude={"preference_id"})
            updated_preference = preference.model_copy(update=new_fields)
            _record(
                change_log,
                f"preferences.update:{preference.preference_id}",
                preference.model_dump(mode="json"),
                updated_preference.model_dump(mode="json"),
                source,
                at,
            )
            preferences[index] = updated_preference
            changed_fields.add("preferences")
            break

    if diff.remove_preference_ids:
        removed_ids = set(diff.remove_preference_ids)
        for preference in preferences:
            if preference.preference_id in removed_ids:
                _record(change_log, f"preferences.remove:{preference.preference_id}", preference.model_dump(mode="json"), None, source, at)
                changed_fields.add("preferences")
        preferences = [p for p in preferences if p.preference_id not in removed_ids]

    updates["preferences"] = preferences
    updates["change_log"] = change_log
    updates["updated_at"] = at

    updated = existing.model_copy(update=updates)
    return updated, changed_fields


def apply_project_update(
    project_repository: ProjectRepository,
    design_version_repository: DesignVersionRepository,
    project_id: str,
    *,
    source: Literal["CHAT", "SETTINGS"],
    diff: ProjectUpdateDiff,
    gateway=None,
) -> ProjectUpdateResult:
    """The one operation both Settings and a future Chat Agent call — see module docstring. Always:
    1. validates the merged result,
    2. applies the diff and appends change_log entries for every field that actually changed,
    3. persists that (regardless of what happens next — a requirement correction is a real fact even if
       the resulting design turns out unsatisfiable),
    4. classifies impact and, only for REGENERATE_DESIGN, calls the UNCHANGED
       `generate_design_via_solver` and appends a new DesignVersion on success.

    A design-generation failure (`DESIGN_PIPELINE_ERRORS`) is returned via `result.design_error`, not
    raised — the caller (the HTTP route) decides how to surface it; the project-field update itself has
    already been persisted either way, matching how `/design` failing today never rolls back
    `/requirements`'s own prior results.
    """
    existing = project_repository.get(project_id)
    if existing is None:
        raise ProjectNotFoundError(project_id)

    _validate_diff(existing, diff)

    at = datetime.now(UTC)
    updated, changed_fields = _apply_diff(existing, diff, source, at)
    updated = project_repository.replace(project_id, updated)

    impact = _classify_impact(changed_fields)
    if impact != UpdateImpact.regenerate_design:
        return ProjectUpdateResult(project=updated, impact=impact)

    try:
        design = generate_design_via_solver(updated, gateway=gateway)
    except DESIGN_PIPELINE_ERRORS as error:
        return ProjectUpdateResult(project=updated, impact=impact, design_error=error)

    version = DesignVersion(
        design_version_id=str(uuid.uuid4()),
        project_id=project_id,
        created_at=at,
        supersedes_id=updated.active_design_version_id,
        request_snapshot=design.request_snapshot or {},
        adapter_diagnostics=design.adapter_diagnostics or [],
        spec_snapshot=design.spec_snapshot or {},
        solver_summary=design.solver_summary or {},
        rooms=design.rooms,
        design_notes=design.design_notes,
        geometric_design=design.geometric_design,
    )
    design_version_repository.append(version)

    final = updated.model_copy(
        update={
            "active_design_version_id": version.design_version_id,
            "site_width_m": design.site_width_m,
            "site_depth_m": design.site_depth_m,
            "rooms": design.rooms,
            "design_notes": design.design_notes,
            "geometric_design": design.geometric_design,
            "design_generated_at": at,
        }
    )
    final = project_repository.replace(project_id, final)

    return ProjectUpdateResult(project=final, impact=impact, design_version=version)


def rollback_to_design_version(
    project_repository: ProjectRepository,
    design_version_repository: DesignVersionRepository,
    project_id: str,
    design_version_id: str,
) -> Project:
    """Repoints `Project.active_design_version_id` (and mirrors the flat fields for backward
    compatibility — see app/design/version.py's module docstring) to an EXISTING version. Never calls
    the Architect Model or GeometrySolver — the version's `rooms`/`design_notes` are already-computed,
    immutable data being copied, not recomputed."""
    project = project_repository.get(project_id)
    if project is None:
        raise ProjectNotFoundError(project_id)

    version = design_version_repository.get(design_version_id)
    if version is None or version.project_id != project_id:
        raise ValueError(f"design_version_id {design_version_id!r} not found for project {project_id!r}")

    at = datetime.now(UTC)
    change_log = list(project.change_log)
    change_log.append(
        ChangeLogEntry(
            field="active_design_version_id",
            old_value=project.active_design_version_id,
            new_value=version.design_version_id,
            source="SETTINGS",
            at=at,
        )
    )

    # site_width_m/site_depth_m are derived from plot_area_m2 (see app/design/pipeline.py's
    # `_derive_footprint`), which a design-version rollback never changes — so they're left untouched
    # here; only the room layout/notes/active-pointer actually roll back.
    updated = project.model_copy(
        update={
            "active_design_version_id": version.design_version_id,
            "rooms": version.rooms,
            "design_notes": version.design_notes,
            "geometric_design": version.geometric_design,
            "design_generated_at": version.created_at,
            "change_log": change_log,
            "updated_at": at,
        }
    )
    return project_repository.replace(project_id, updated)
