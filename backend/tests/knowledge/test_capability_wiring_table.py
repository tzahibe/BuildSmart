"""Issue #156 — keeps `docs/PROJECT_STATE.md`'s wiring table honest.

Ground truth for every row is read from `origin/main` via `git show`, not from whatever branch
happens to be checked out when this test runs — the table's whole subject is what ships on `main`
today, and this worktree may itself be a branch ahead of or behind `main` on unrelated work. If a
flag's real default drifts, or a production caller appears/disappears, the corresponding assertion
below fails — the table cannot rot silently the way `docs/wiki/INDEX.md`'s laundry entry once did.
"""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

from app.knowledge.indexer import repo_root_from_here

REPO_ROOT = Path(repo_root_from_here())
PROJECT_STATE = REPO_ROOT / "docs" / "PROJECT_STATE.md"

# Every production file under `backend/app/{vertical_slice,demo}` that could plausibly import one
# of the gated capabilities below, as last enumerated from this worktree's own `app/vertical_slice`
# + `app/demo` directories. Kept as an explicit list (not a live tree walk) because this worktree's
# own checkout may lag or lead `origin/main` by a handful of unrelated commits — every path here is
# read from `origin/main` itself via `git show`, never from local disk, so that does not matter.
_CANDIDATE_CALLER_PATHS = [
    "backend/app/demo/__init__.py",
    "backend/app/demo/contract.py",
    "backend/app/demo/requirements_view.py",
    "backend/app/demo/router.py",
    "backend/app/demo/scope.py",
    "backend/app/demo/service.py",
    "backend/app/demo/site_geometry.py",
    "backend/app/vertical_slice/__init__.py",
    "backend/app/vertical_slice/access_rules.py",
    "backend/app/vertical_slice/building.py",
    "backend/app/vertical_slice/building_coordinator.py",
    "backend/app/vertical_slice/building_validation.py",
    "backend/app/vertical_slice/circulation_metrics.py",
    "backend/app/vertical_slice/concept.py",
    "backend/app/vertical_slice/concept_compilers.py",
    "backend/app/vertical_slice/concept_engine_v2.py",
    "backend/app/vertical_slice/concept_generator.py",
    "backend/app/vertical_slice/concept_patterns.py",
    "backend/app/vertical_slice/concept_score.py",
    "backend/app/vertical_slice/concept_spec.py",
    "backend/app/vertical_slice/constraints.py",
    "backend/app/vertical_slice/design_output.py",
    "backend/app/vertical_slice/door_clearance.py",
    "backend/app/vertical_slice/doors.py",
    "backend/app/vertical_slice/entrance_sequence.py",
    "backend/app/vertical_slice/exposure_policy.py",
    "backend/app/vertical_slice/footprint.py",
    "backend/app/vertical_slice/furnishability.py",
    "backend/app/vertical_slice/furniture.py",
    "backend/app/vertical_slice/general_pipeline.py",
    "backend/app/vertical_slice/geometry_adapter.py",
    "backend/app/vertical_slice/geometry_core/__init__.py",
    "backend/app/vertical_slice/geometry_core/engine.py",
    "backend/app/vertical_slice/geometry_core/model.py",
    "backend/app/vertical_slice/geometry_fixtures.py",
    "backend/app/vertical_slice/hub_guard.py",
    "backend/app/vertical_slice/interior_layout.py",
    "backend/app/vertical_slice/l_massing_guard.py",
    "backend/app/vertical_slice/l_parti.py",
    "backend/app/vertical_slice/level_planner.py",
    "backend/app/vertical_slice/level_program.py",
    "backend/app/vertical_slice/master_suite.py",
    "backend/app/vertical_slice/pipeline.py",
    "backend/app/vertical_slice/primary_selection.py",
    "backend/app/vertical_slice/public_composition.py",
    "backend/app/vertical_slice/quality_metrics.py",
    "backend/app/vertical_slice/rectilinear_realizer.py",
    "backend/app/vertical_slice/reference_benchmark.py",
    "backend/app/vertical_slice/relationships.py",
    "backend/app/vertical_slice/renderer.py",
    "backend/app/vertical_slice/room_merge.py",
    "backend/app/vertical_slice/safe_adapter.py",
    "backend/app/vertical_slice/site.py",
    "backend/app/vertical_slice/spec.py",
    "backend/app/vertical_slice/stage2/__init__.py",
    "backend/app/vertical_slice/stage2/contract.py",
    "backend/app/vertical_slice/validation.py",
    "backend/app/vertical_slice/vertical.py",
    "backend/app/vertical_slice/walls.py",
    "backend/app/vertical_slice/wet_core.py",
    "backend/app/vertical_slice/wet_privacy.py",
    "backend/app/vertical_slice/wet_rooms.py",
    "backend/app/vertical_slice/windows.py",
]


@pytest.fixture(scope="module", autouse=True)
def _require_origin_main():
    probe = subprocess.run(["git", "rev-parse", "--verify", "origin/main"],
                            cwd=REPO_ROOT, capture_output=True, text=True)
    if probe.returncode != 0:
        pytest.skip("origin/main is not resolvable in this checkout — cannot verify the wiring "
                     "table against main (NOT_VERIFIED, not a pass)")


def _read_from_main(rel_path: str) -> str | None:
    """`None` when `rel_path` does not exist on `origin/main` — a fact (e.g. a module that only
    exists on an integration branch), not an error."""
    result = subprocess.run(["git", "show", f"origin/main:{rel_path}"],
                             cwd=REPO_ROOT, capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else None


def _flag_default_on_main(rel_path: str, flag_name: str) -> bool:
    text = _read_from_main(rel_path)
    assert text is not None, f"{rel_path} not found on origin/main"
    match = re.search(rf"^{flag_name}\s*=\s*(True|False)\b", text, re.MULTILINE)
    assert match, f"{flag_name} not found as a module-level constant in {rel_path} on origin/main"
    return match.group(1) == "True"


def _flag_present_on_main(rel_path: str, flag_name: str) -> bool:
    text = _read_from_main(rel_path)
    if text is None:
        return False
    return re.search(rf"^{flag_name}\s*=\s*(True|False)\b", text, re.MULTILINE) is not None


def _imports(rel_path: str, dotted_target: str) -> bool:
    """Whether the file at `rel_path` (read from `origin/main`) imports `dotted_target`, in any of
    the import styles this codebase actually uses (absolute, `from package import leaf`, or a
    relative `from . import leaf` / `from .leaf import x` within the same package)."""
    text = _read_from_main(rel_path)
    if text is None:
        return False
    leaf = dotted_target.rsplit(".", 1)[-1]
    package = dotted_target.rsplit(".", 1)[0]
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == dotted_target or alias.name.startswith(dotted_target + "."):
                    return True
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                if module == leaf or module.startswith(leaf + "."):
                    return True
                if not module and any(a.name == leaf for a in node.names):
                    return True
            else:
                if module == dotted_target or module.startswith(dotted_target + "."):
                    return True
                if module == package and any(a.name == leaf for a in node.names):
                    return True
    return False


def _has_production_caller(dotted_targets: list[str], own_paths: set[str]) -> bool:
    for rel_path in _CANDIDATE_CALLER_PATHS:
        if rel_path in own_paths:
            continue
        if any(_imports(rel_path, target) for target in dotted_targets):
            return True
    return False


def _dotted(rel_path: str) -> str:
    assert rel_path.startswith("backend/"), rel_path
    without_prefix = rel_path[len("backend/"):]
    without_ext = without_prefix[:-3] if without_prefix.endswith(".py") else without_prefix
    return without_ext.replace("/", ".")


def _project_state_text() -> str:
    return PROJECT_STATE.read_text(encoding="utf-8")


def _row_cells(marker: str) -> list[str]:
    for line in _project_state_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and marker in stripped:
            cells = [c.strip() for c in stripped.split("|")]
            return cells[1:-1]
    raise AssertionError(f"no wiring-table row in docs/PROJECT_STATE.md contains {marker!r}")


def _cell_bool_literal(cell: str) -> bool:
    match = re.search(r"`(True|False)`", cell)
    assert match, f"no `True`/`False` literal found in wiring-table cell: {cell!r}"
    return match.group(1) == "True"


def _cell_yes_no(cell: str) -> bool:
    stripped = cell.lstrip()
    if stripped.startswith("Yes"):
        return True
    if stripped.startswith("No"):
        return False
    raise AssertionError(f"wiring-table caller cell does not start with Yes/No: {cell!r}")


# (table row marker, flag-defining file, flag name, dotted targets checked for a caller, files
# that are the capability's own implementation and therefore excluded from the caller search)
_FLAG_ROWS = [
    (
        "Rectilinear (non-guillotine) realizer",
        "backend/app/vertical_slice/rectilinear_realizer.py",
        "RECTILINEAR_REALIZER_ENABLED",
        ["app.vertical_slice.rectilinear_realizer"],
        {"backend/app/vertical_slice/rectilinear_realizer.py"},
    ),
    (
        "LIVING+KITCHEN room merge",
        "backend/app/vertical_slice/room_merge.py",
        "LIVING_KITCHEN_MERGE_ENABLED",
        ["app.vertical_slice.room_merge"],
        {"backend/app/vertical_slice/room_merge.py"},
    ),
    (
        "Laundry room",
        "backend/app/vertical_slice/concept_generator.py",
        "LAUNDRY_ROOM_ENABLED",
        ["app.vertical_slice.concept_generator"],
        {"backend/app/vertical_slice/concept_generator.py"},
    ),
    (
        "Stage 2 contract",
        "backend/app/vertical_slice/stage2/contract.py",
        "STAGE2_CONTRACT_ENABLED",
        ["app.vertical_slice.stage2"],
        {"backend/app/vertical_slice/stage2/contract.py", "backend/app/vertical_slice/stage2/__init__.py"},
    ),
]


@pytest.mark.parametrize("marker,path,flag,dotted_targets,own_paths", _FLAG_ROWS,
                          ids=[r[0] for r in _FLAG_ROWS])
def test_flagged_capability_matches_main(marker, path, flag, dotted_targets, own_paths):
    cells = _row_cells(marker)
    recorded_default = _cell_bool_literal(cells[3])
    recorded_caller = _cell_yes_no(cells[4])

    actual_default = _flag_default_on_main(path, flag)
    assert recorded_default == actual_default, (
        f"docs/PROJECT_STATE.md records {flag} = {recorded_default} but origin/main's {path} "
        f"has {actual_default} — the wiring table has drifted from the real flag default"
    )

    actual_caller = _has_production_caller(dotted_targets, own_paths)
    assert recorded_caller == actual_caller, (
        f"docs/PROJECT_STATE.md records production-caller={recorded_caller} for {path} but a "
        f"scan of origin/main's production files found production-caller={actual_caller}"
    )


# Capabilities with no flag at all — unconditionally wired in, or unconditionally absent from the
# production path. Same drift protection on the caller answer; no flag default to check.
_UNFLAGGED_ROWS = [
    (
        "Furnishability / usability validation",
        ["app.vertical_slice.furnishability"],
        {"backend/app/vertical_slice/furnishability.py"},
        True,
    ),
    (
        "Public-zone composition validation",
        ["app.vertical_slice.public_composition"],
        {"backend/app/vertical_slice/public_composition.py"},
        True,
    ),
    (
        "Multi-level (two-storey building",
        [
            "app.vertical_slice.building_coordinator",
            "app.vertical_slice.primary_selection",
            "app.vertical_slice.level_planner",
            "app.vertical_slice.level_program",
        ],
        {
            "backend/app/vertical_slice/building_coordinator.py",
            "backend/app/vertical_slice/primary_selection.py",
            "backend/app/vertical_slice/level_planner.py",
            "backend/app/vertical_slice/level_program.py",
        },
        False,
    ),
]


@pytest.mark.parametrize("marker,dotted_targets,own_paths,expected_caller", _UNFLAGGED_ROWS,
                          ids=[r[0] for r in _UNFLAGGED_ROWS])
def test_unflagged_capability_caller_matches_main(marker, dotted_targets, own_paths, expected_caller):
    cells = _row_cells(marker)
    recorded_caller = _cell_yes_no(cells[4])
    assert recorded_caller == expected_caller, (
        f"test's own expectation for {marker!r} ({expected_caller}) disagrees with what "
        f"docs/PROJECT_STATE.md records ({recorded_caller}) — fix whichever is wrong"
    )

    actual_caller = _has_production_caller(dotted_targets, own_paths)
    assert recorded_caller == actual_caller, (
        f"docs/PROJECT_STATE.md records production-caller={recorded_caller} for {marker!r} but "
        f"a scan of origin/main's production files found production-caller={actual_caller}"
    )


def test_drawing_representation_row_matches_main():
    cells = _row_cells("Professional architectural drawing representation")
    recorded_caller = _cell_yes_no(cells[4])
    assert recorded_caller is True

    demo_plan = _read_from_main("frontend/src/design/DemoPlan.tsx")
    scale_bar = _read_from_main("frontend/src/design/ScaleBar.tsx")
    assert demo_plan is not None and scale_bar is not None, (
        "frontend/src/design/DemoPlan.tsx or ScaleBar.tsx no longer exist on origin/main"
    )
    assert "ScaleBar" in demo_plan, (
        "DemoPlan.tsx no longer references ScaleBar — the 'rendered unconditionally' claim in "
        "the wiring table needs re-checking"
    )
    assert "_ENABLED" not in demo_plan and "_ENABLED" not in scale_bar, (
        "an *_ENABLED flag appeared in the drawing-representation frontend files — the wiring "
        "table's 'none — unconditional' claim is now wrong"
    )


def test_concept_engine_v2_absence_from_main_is_still_true():
    """The one row whose defect is not gating but absence: ROOT #74's modules were integrated and
    gate-passed on `integration/concept-engine-v2` but never rolled up to `main`. This is a dated
    historical claim (as of 2026-09-29) — this test re-checks it is still true every run, so if
    Issue #153's rollup lands without this row being rewritten, it fails loudly instead of the
    table silently going stale the way it did before this Issue."""
    row = _row_cells("circulation-class alternatives")
    assert "integration branch" in " ".join(row)
    assert "#153" in " ".join(row)

    module_on_main = _read_from_main("backend/app/vertical_slice/concept_engine_v2.py")
    assert module_on_main is None, (
        "app/vertical_slice/concept_engine_v2.py now exists on origin/main — ROOT #74's rollup "
        "(#153) has landed; rewrite the Concept Engine v2 row (module/flag/caller/verdict) instead "
        "of leaving it describing an integration-branch-only module that has since shipped"
    )
    assert not _flag_present_on_main("backend/app/vertical_slice/general_pipeline.py",
                                      "CONCEPT_ENGINE_V2_ENABLED"), (
        "CONCEPT_ENGINE_V2_ENABLED now exists on origin/main's general_pipeline.py — update the "
        "wiring table, this flag is no longer integration-branch-only"
    )


def test_every_enabled_constant_on_main_has_a_row():
    """AC-1/AC-3's real teeth: every `*_ENABLED` module-level constant that exists on `main` today
    must have a row above with a matching flag name, or the table is incomplete by construction."""
    documented_flags = {flag for _, _, flag, _, _ in _FLAG_ROWS}
    found_on_main: set[str] = set()
    for rel_path in _CANDIDATE_CALLER_PATHS:
        text = _read_from_main(rel_path)
        if text is None:
            continue
        for match in re.finditer(r"^([A-Z][A-Z0-9_]*_ENABLED)\s*=\s*(?:True|False)\b", text,
                                  re.MULTILINE):
            found_on_main.add(match.group(1))
    assert found_on_main == documented_flags, (
        f"*_ENABLED constants on origin/main {found_on_main} do not match the flags documented in "
        f"docs/PROJECT_STATE.md's wiring table {documented_flags} — add/remove a row"
    )
