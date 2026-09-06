"""Tests for the single project-update operation (app/projects/update.py) — the foundation for
conversational design editing. Uses `MockArchitectModelGateway` (fast, deterministic) for any test whose
update impact is REGENERATE_DESIGN; nothing here needs the real model.
"""

from datetime import UTC, datetime

import pytest

from app.architect.gateway import MockArchitectModelGateway
from app.design.version import JsonFileDesignVersionRepository
from app.projects.models import PoolField, Project, ProjectCreate, TaggedBool, TaggedFloat, TaggedInt
from app.projects.preferences import PreferenceCreate, PreferenceUpdate
from app.projects.repository import JsonFileProjectRepository
from app.projects.update import (
    ProjectNotFoundError,
    ProjectUpdateDiff,
    UpdateImpact,
    apply_project_update,
    rollback_to_design_version,
)

_UNKNOWN_INT = TaggedInt(value=None, source="unknown")
_UNKNOWN_BOOL = TaggedBool(value=None, source="unknown")
_UNKNOWN_POOL = PoolField(
    requested=TaggedBool(value=None, source="unknown"),
    length_m=TaggedFloat(value=None, source="unknown"),
    width_m=TaggedFloat(value=None, source="unknown"),
)


@pytest.fixture
def repo(tmp_path):
    return JsonFileProjectRepository(tmp_path / "projects.json")


@pytest.fixture
def version_repo(tmp_path):
    return JsonFileDesignVersionRepository(tmp_path / "design_versions.json")


@pytest.fixture
def project(repo) -> Project:
    created = repo.create(
        ProjectCreate(
            city="מודיעין-מכבים-רעות",
            street="אגוז מכבים רעות",
            plot_area_m2=400,
            built_area_m2=100,
            description='בית עם 3 חדרי שינה, ממ"ד',
        )
    )
    repo.set_parsed_requirements(
        created.project_id,
        floors=TaggedInt(value=1, source="requested"),
        bedrooms=TaggedInt(value=3, source="requested"),
        safe_room=TaggedBool(value=False, source="requested"),
        parking_spaces=_UNKNOWN_INT,
        pool=_UNKNOWN_POOL,
    )
    return repo.get(created.project_id)


def _gateway():
    return MockArchitectModelGateway()


# --- Requirement changes: regenerate, provenance, change_log ---------------------------------------


def test_bedrooms_3_to_4_triggers_regeneration_and_new_design_version(repo, version_repo, project):
    diff = ProjectUpdateDiff(bedrooms=TaggedInt(value=4, source="requested"))

    result = apply_project_update(repo, version_repo, project.project_id, source="SETTINGS", diff=diff, gateway=_gateway())

    assert result.impact == UpdateImpact.regenerate_design
    assert result.design_error is None
    assert result.design_version is not None
    assert result.project.bedrooms.value == 4
    assert result.project.active_design_version_id == result.design_version.design_version_id
    room_types = [room.type for room in result.project.rooms]
    assert room_types.count("bedroom") == 4


def test_safe_room_false_to_true_triggers_regeneration_and_includes_safe_room(repo, version_repo, project):
    diff = ProjectUpdateDiff(safe_room=TaggedBool(value=True, source="requested"))

    result = apply_project_update(repo, version_repo, project.project_id, source="SETTINGS", diff=diff, gateway=_gateway())

    assert result.impact == UpdateImpact.regenerate_design
    assert result.design_version is not None
    assert result.project.safe_room.value is True
    assert any(room.type == "safe_room" for room in result.project.rooms)


def test_change_log_records_source_and_before_after_values(repo, version_repo, project):
    diff = ProjectUpdateDiff(bedrooms=TaggedInt(value=4, source="requested"))

    result = apply_project_update(repo, version_repo, project.project_id, source="SETTINGS", diff=diff, gateway=_gateway())

    entries = [e for e in result.project.change_log if e.field == "bedrooms"]
    assert len(entries) == 1
    assert entries[0].source == "SETTINGS"
    assert entries[0].old_value["value"] == 3
    assert entries[0].new_value["value"] == 4


def test_unknown_values_remain_unknown_unless_explicitly_changed(repo, version_repo, project):
    # parking_spaces starts unknown; updating only bedrooms must not disturb it.
    diff = ProjectUpdateDiff(bedrooms=TaggedInt(value=4, source="requested"))

    result = apply_project_update(repo, version_repo, project.project_id, source="SETTINGS", diff=diff, gateway=_gateway())

    assert result.project.parking_spaces.source == "unknown"
    assert result.project.parking_spaces.value is None
    assert not any(e.field == "parking_spaces" for e in result.project.change_log)


def test_explicitly_setting_a_field_back_to_unknown_is_recorded(repo, version_repo, project):
    diff = ProjectUpdateDiff(bedrooms=TaggedInt(value=None, source="unknown"))

    result = apply_project_update(repo, version_repo, project.project_id, source="SETTINGS", diff=diff, gateway=_gateway())

    assert result.project.bedrooms.value is None
    assert result.project.bedrooms.source == "unknown"
    entries = [e for e in result.project.change_log if e.field == "bedrooms"]
    assert len(entries) == 1
    assert entries[0].new_value["source"] == "unknown"


# --- Preferences: additive, NO_REGEN ------------------------------------------------------------


def test_preference_added_is_no_regen_and_persisted(repo, version_repo, project):
    diff = ProjectUpdateDiff(
        add_preferences=[PreferenceCreate(kind="PRIVACY", target="bedroom", original_text="I want the bedrooms private")]
    )

    result = apply_project_update(repo, version_repo, project.project_id, source="CHAT", diff=diff, gateway=_gateway())

    assert result.impact == UpdateImpact.no_regen
    assert result.design_version is None
    assert len(result.project.preferences) == 1
    pref = result.project.preferences[0]
    assert pref.kind == "PRIVACY"
    assert pref.source == "CHAT"
    assert pref.original_text == "I want the bedrooms private"


def test_preference_updated_is_no_regen(repo, version_repo, project):
    add = ProjectUpdateDiff(add_preferences=[PreferenceCreate(kind="OTHER", original_text="open kitchen")])
    created = apply_project_update(repo, version_repo, project.project_id, source="SETTINGS", diff=add, gateway=_gateway())
    preference_id = created.project.preferences[0].preference_id

    update = ProjectUpdateDiff(update_preferences=[PreferenceUpdate(preference_id=preference_id, priority="high")])
    result = apply_project_update(repo, version_repo, project.project_id, source="SETTINGS", diff=update, gateway=_gateway())

    assert result.impact == UpdateImpact.no_regen
    assert result.project.preferences[0].priority == "high"
    assert result.project.preferences[0].original_text == "open kitchen"  # untouched fields preserved


def test_preference_removed_is_no_regen(repo, version_repo, project):
    add = ProjectUpdateDiff(add_preferences=[PreferenceCreate(kind="OTHER", original_text="open kitchen")])
    created = apply_project_update(repo, version_repo, project.project_id, source="SETTINGS", diff=add, gateway=_gateway())
    preference_id = created.project.preferences[0].preference_id

    remove = ProjectUpdateDiff(remove_preference_ids=[preference_id])
    result = apply_project_update(repo, version_repo, project.project_id, source="SETTINGS", diff=remove, gateway=_gateway())

    assert result.impact == UpdateImpact.no_regen
    assert result.project.preferences == []


# --- Impact classification ------------------------------------------------------------------------


def test_metadata_only_update_does_not_regenerate(repo, version_repo, project):
    diff = ProjectUpdateDiff(description="בית מרווח ומואר")

    result = apply_project_update(repo, version_repo, project.project_id, source="SETTINGS", diff=diff, gateway=_gateway())

    assert result.impact == UpdateImpact.no_regen
    assert result.design_version is None
    assert version_repo.list_for_project(project.project_id) == []


def test_city_change_is_regulation_recheck_not_executed(repo, version_repo, project):
    diff = ProjectUpdateDiff(city="ירושלים", street="א דרג'י")

    result = apply_project_update(repo, version_repo, project.project_id, source="SETTINGS", diff=diff, gateway=_gateway())

    assert result.impact == UpdateImpact.regulation_recheck
    assert result.design_version is None  # represented only — nothing is actually invoked


def test_no_actual_change_is_no_regen_even_if_field_is_present_in_diff(repo, version_repo, project):
    diff = ProjectUpdateDiff(bedrooms=TaggedInt(value=3, source="requested"))  # same as existing

    result = apply_project_update(repo, version_repo, project.project_id, source="SETTINGS", diff=diff, gateway=_gateway())

    assert result.impact == UpdateImpact.no_regen
    assert not any(e.field == "bedrooms" for e in result.project.change_log)


# --- DesignVersion immutability + rollback ---------------------------------------------------------


def test_previous_design_version_remains_unchanged_after_a_new_one_is_created(repo, version_repo, project):
    first = apply_project_update(
        repo, version_repo, project.project_id, source="SETTINGS", diff=ProjectUpdateDiff(bedrooms=TaggedInt(value=2, source="requested")), gateway=_gateway()
    )
    first_version_id = first.design_version.design_version_id
    first_rooms_snapshot = [r.model_dump() for r in first.design_version.rooms]

    apply_project_update(
        repo, version_repo, project.project_id, source="SETTINGS", diff=ProjectUpdateDiff(bedrooms=TaggedInt(value=4, source="requested")), gateway=_gateway()
    )

    unchanged_first = version_repo.get(first_version_id)
    assert [r.model_dump() for r in unchanged_first.rooms] == first_rooms_snapshot


def test_rollback_restores_previous_version_without_model_invocation(repo, version_repo, project):
    first = apply_project_update(
        repo, version_repo, project.project_id, source="SETTINGS", diff=ProjectUpdateDiff(bedrooms=TaggedInt(value=2, source="requested")), gateway=_gateway()
    )
    first_version_id = first.design_version.design_version_id
    first_room_types = sorted(room.type for room in first.project.rooms)

    class _ExplodingGateway:
        def generate(self, request):
            raise AssertionError("rollback must never call the Architect Model")

    second = apply_project_update(
        repo, version_repo, project.project_id, source="SETTINGS", diff=ProjectUpdateDiff(bedrooms=TaggedInt(value=4, source="requested")), gateway=_gateway()
    )
    assert second.project.active_design_version_id != first_version_id

    rolled_back = rollback_to_design_version(repo, version_repo, project.project_id, first_version_id)
    # Would raise AssertionError above if the model were ever invoked, since _ExplodingGateway is never
    # even passed to rollback — proving by construction that rollback has no gateway parameter at all.

    assert rolled_back.active_design_version_id == first_version_id
    assert sorted(room.type for room in rolled_back.rooms) == first_room_types
    assert rolled_back.change_log[-1].field == "active_design_version_id"
    assert rolled_back.change_log[-1].new_value == first_version_id


def test_rollback_to_unknown_version_raises(repo, version_repo, project):
    with pytest.raises(ValueError):
        rollback_to_design_version(repo, version_repo, project.project_id, "nonexistent-id")


# --- Not found -------------------------------------------------------------------------------------


def test_update_nonexistent_project_raises(repo, version_repo):
    with pytest.raises(ProjectNotFoundError):
        apply_project_update(
            repo, version_repo, "nonexistent", source="SETTINGS", diff=ProjectUpdateDiff(description="x"), gateway=_gateway()
        )


# --- Backward compatibility: existing (pre-versioning) project data remains readable -----------------


def test_existing_project_json_without_new_fields_is_still_readable(tmp_path):
    import json

    old_shape_record = {
        "project_id": "legacy-1",
        "city": "מודיעין-מכבים-רעות",
        "street": "אגוז מכבים רעות",
        "plot_area_m2": 300.0,
        "built_area_m2": 70.0,
        "description": "בית ישן",
        "status": "created",
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
        "floors": None,
        "bedrooms": None,
        "safe_room": None,
        "parking_spaces": None,
        "pool": None,
        "requirements_parsed_at": None,
        "site_width_m": None,
        "site_depth_m": None,
        "rooms": None,
        "design_notes": None,
        "design_generated_at": None,
        # No active_design_version_id / preferences / change_log at all — genuinely pre-migration shape.
    }
    data_file = tmp_path / "projects.json"
    data_file.write_text(json.dumps({"legacy-1": old_shape_record}), encoding="utf-8")

    repo = JsonFileProjectRepository(data_file)
    project = repo.get("legacy-1")

    assert project is not None
    assert project.description == "בית ישן"
    assert project.active_design_version_id is None
    assert project.preferences == []
    assert project.change_log == []
