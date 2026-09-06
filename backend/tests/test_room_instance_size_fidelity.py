"""ROOM_INSTANCE_SIZE_FIDELITY tests (Phases 10-11). Uses real ArchitecturalSpec/ProgramItem,
real GeometrySolver, real Spatial V2.1 planner, and the real GeometricDesign builder throughout --
no disconnected geometry-only toy types.
"""
import json
from pathlib import Path

import pytest

from app.architect.models import ArchitecturalSpec, ProgramItem
from app.geometry.geometric_design import build_geometric_design
from app.geometry.instances import expand_program_to_instances
from app.geometry.models import BuildingFootprintSpec, GeometrySolverResult, RoomInstance, SolverStatus
from app.geometry.solver import GeometrySolver, _layout_satisfies_hard_requirements, _overlaps
from app.geometry.spatial_v2.candidates import generate_candidates
from app.geometry.spatial_v2.local_search import local_search_variants
from app.geometry.spatial_v2.planner import build_geometric_design_v2, plan_v2
from app.geometry.spatial_v2.structural_variants import orientation_swap_variants, pair_swap_variants, reflection_variants

_SAMPLES_DIR = Path(__file__).parent / "spatial_v2_1_samples"


def _mixed_bedroom_spec() -> ArchitecturalSpec:
    """Living room + kitchen + bathroom + 3 differently-sized bedrooms (1 master, 2 plain bedroom
    ProgramItems each count=1) -- the exact scenario from the task's example."""
    return ArchitecturalSpec(
        program=[
            ProgramItem(room_type="living_room", count=1, target_area_m2=22.0, source="MODEL_INFERENCE"),
            ProgramItem(room_type="kitchen", count=1, target_area_m2=9.0, source="MODEL_INFERENCE"),
            ProgramItem(room_type="bathroom", count=1, target_area_m2=5.0, source="MODEL_INFERENCE"),
            ProgramItem(room_type="master_bedroom", count=1, target_area_m2=14.0, source="USER_REQUIREMENT"),
            ProgramItem(room_type="bedroom", count=1, target_area_m2=11.0, source="USER_REQUIREMENT"),
            ProgramItem(room_type="bedroom", count=1, target_area_m2=10.0, source="USER_REQUIREMENT"),
        ],
        relationships=[], zones=[], circulation=None, incomplete_requirements=[],
    )


def _footprint() -> BuildingFootprintSpec:
    return BuildingFootprintSpec(width_m=10.0, depth_m=10.0, floor=1, available_area_m2=90.0)


def _shared_bedroom_spec(shared_area: float = 10.5) -> ArchitecturalSpec:
    """The Case B / backward-compatible shape: one ProgramItem, count>1, one shared target."""
    return ArchitecturalSpec(
        program=[
            ProgramItem(room_type="living_room", count=1, target_area_m2=22.0, source="MODEL_INFERENCE"),
            ProgramItem(room_type="kitchen", count=1, target_area_m2=9.0, source="MODEL_INFERENCE"),
            ProgramItem(room_type="bathroom", count=1, target_area_m2=5.0, source="MODEL_INFERENCE"),
            ProgramItem(room_type="bedroom", count=3, target_area_m2=shared_area, source="MODEL_INFERENCE"),
        ],
        relationships=[], zones=[], circulation=None, incomplete_requirements=[],
    )


def _area_error(actual: float, target: float) -> tuple[float, float]:
    error_m2 = abs(actual - target)
    error_pct = error_m2 / target if target else 0.0
    return error_m2, error_pct


# 1. 3 bedrooms with one shared/default size still work ------------------------------------


def test_default_shared_bedroom_size_still_works():
    spec = _shared_bedroom_spec()
    footprint = _footprint()
    result = GeometrySolver().solve(spec, footprint)
    assert result.status == SolverStatus.satisfied
    bedrooms = {r.id: r for r in result.instances if r.type == "bedroom"}
    assert set(bedrooms) == {"BEDROOM_1", "BEDROOM_2", "BEDROOM_3"}
    for room in bedrooms.values():
        assert room.area_m2 == pytest.approx(10.5, abs=0.6)


# 2. 3 bedrooms with explicit different sizes retain different targets ----------------------


def test_explicit_different_bedroom_targets_are_retained_through_expansion():
    spec = _mixed_bedroom_spec()
    instances = expand_program_to_instances(spec.program)
    targets = {instance_id: item.target_area_m2 for instance_id, _room_type, item in instances}
    assert targets["MASTER_BEDROOM"] == 14.0
    assert targets["BEDROOM_1"] == 11.0
    assert targets["BEDROOM_2"] == 10.0
    # no id collision -- exactly 6 distinct instance ids for 6 program items
    assert len({instance_id for instance_id, _rt, _item in instances}) == 6


# 3. 14m2 bedroom remains larger than 10m2 bedroom (solved geometry) -------------------------


def test_14sqm_bedroom_larger_than_10sqm_bedroom():
    spec = _mixed_bedroom_spec()
    footprint = _footprint()
    result = GeometrySolver().solve(spec, footprint)
    assert result.status == SolverStatus.satisfied
    by_id = {r.id: r for r in result.instances}
    assert by_id["MASTER_BEDROOM"].area_m2 > by_id["BEDROOM_2"].area_m2


# 4. 14 > 11 > 10 requested ordering is preserved where feasible -----------------------------


def test_14_11_10_ordering_preserved_v1_and_v21():
    spec = _mixed_bedroom_spec()
    footprint = _footprint()

    v1 = GeometrySolver().solve(spec, footprint)
    assert v1.status == SolverStatus.satisfied
    by_id_v1 = {r.id: r for r in v1.instances}
    assert by_id_v1["MASTER_BEDROOM"].area_m2 > by_id_v1["BEDROOM_1"].area_m2 > by_id_v1["BEDROOM_2"].area_m2

    v21 = plan_v2(spec, footprint)
    assert v21.status == SolverStatus.satisfied
    by_id_v21 = {r.id: r for r in v21.instances}
    assert by_id_v21["MASTER_BEDROOM"].area_m2 > by_id_v21["BEDROOM_1"].area_m2 > by_id_v21["BEDROOM_2"].area_m2


# 5. explicit target area achieves configured tolerance where feasible ----------------------


def test_explicit_targets_within_tolerance():
    spec = _mixed_bedroom_spec()
    footprint = _footprint()
    result = GeometrySolver().solve(spec, footprint)
    assert result.status == SolverStatus.satisfied
    targets = {"MASTER_BEDROOM": 14.0, "BEDROOM_1": 11.0, "BEDROOM_2": 10.0}
    by_id = {r.id: r for r in result.instances}
    for room_id, target in targets.items():
        error_m2, error_pct = _area_error(by_id[room_id].area_m2, target)
        assert error_pct <= 0.10, f"{room_id}: {error_pct:.1%} exceeds 10% tolerance"


# 6. default sizing remains backward compatible ----------------------------------------------


def test_default_sizing_backward_compatible_no_duplicate_items():
    """A program with exactly one ProgramItem per type (the pre-existing, common shape) must solve
    identically to before -- this is the regression-safety condition for every change in this task."""
    spec = ArchitecturalSpec(
        program=[
            ProgramItem(room_type="living_room", count=1, target_area_m2=20.0, source="MODEL_INFERENCE"),
            ProgramItem(room_type="bedroom", count=3, target_area_m2=12.0, source="USER_REQUIREMENT"),
        ],
        relationships=[], zones=[], circulation=None, incomplete_requirements=[],
    )
    footprint = BuildingFootprintSpec(width_m=9.0, depth_m=9.0, floor=1, available_area_m2=56.0)
    result = GeometrySolver().solve(spec, footprint)
    assert result.status == SolverStatus.satisfied
    ids = {r.id for r in result.instances}
    assert ids == {"LIVING_ROOM", "BEDROOM_1", "BEDROOM_2", "BEDROOM_3"}


# 7. reasonable bedroom aspect ratios ---------------------------------------------------------


def test_bedroom_aspect_ratios_are_reasonable_not_pathological():
    spec = _mixed_bedroom_spec()
    footprint = _footprint()
    result = GeometrySolver().solve(spec, footprint)
    assert result.status == SolverStatus.satisfied
    for room in result.instances:
        if "BEDROOM" not in room.id:
            continue
        aspect = max(room.width, room.height) / min(room.width, room.height)
        assert aspect <= 2.5, f"{room.id}: pathological aspect ratio {aspect:.2f}"


# 8/9/10. no overlap, footprint bounds, required access preserved (hard constraints unchanged) --


def test_hard_constraints_unchanged_for_mixed_bedroom_spec():
    spec = _mixed_bedroom_spec()
    footprint = _footprint()
    result = GeometrySolver().solve(spec, footprint)
    assert result.status == SolverStatus.satisfied
    assert _layout_satisfies_hard_requirements(spec, footprint, result.instances)
    for i in range(len(result.instances)):
        for j in range(i + 1, len(result.instances)):
            a, b = result.instances[i], result.instances[j]
            assert not _overlaps(a.x, a.y, a.width, a.height, b.x, b.y, b.width, b.height)
        r = result.instances[i]
        assert r.x >= -1e-6 and r.y >= -1e-6
        assert r.x + r.width <= footprint.width_m + 1e-6
        assert r.y + r.height <= footprint.depth_m + 1e-6


# 11. V2.1 candidate transformations preserve room area --------------------------------------


def test_v21_candidates_preserve_each_room_instance_area():
    """No V2.1 transformation (translation, reflection, orientation swap, pair swap, local search)
    changes a room instance's OWN area -- across the entire candidate pool, `area_m2` for a given
    room id must be identical everywhere it appears (position/orientation may vary; area never
    does, since it belongs to the room instance's requirement, not its current placement)."""
    spec = _mixed_bedroom_spec()
    footprint = _footprint()

    candidates = generate_candidates(spec, footprint)
    assert candidates

    area_by_id: dict[str, float] = {}
    for candidate in candidates:
        areas_in_candidate = {r.id: r.area_m2 for r in candidate}
        assert len(areas_in_candidate) == len(candidate)  # no id collisions within one candidate
        for room_id, area in areas_in_candidate.items():
            if room_id in area_by_id:
                assert area == pytest.approx(area_by_id[room_id], abs=1e-6), (
                    f"{room_id} area changed across candidates: {area_by_id[room_id]} vs {area}"
                )
            else:
                area_by_id[room_id] = area

    # and those areas must match the mixed-bedroom spec's own explicit targets
    assert area_by_id["MASTER_BEDROOM"] == pytest.approx(14.0, abs=0.01)
    assert area_by_id["BEDROOM_1"] == pytest.approx(11.0, abs=0.01)
    assert area_by_id["BEDROOM_2"] == pytest.approx(10.0, abs=0.01)


# 12. orientation swap preserves area (width * depth unchanged) ------------------------------


def test_orientation_swap_preserves_area():
    spec = _mixed_bedroom_spec()
    footprint = _footprint()
    program_by_instance_id = {
        instance_id: item for instance_id, _rt, item in expand_program_to_instances(spec.program)
    }
    seed = GeometrySolver().solve(spec, footprint).instances
    variants = orientation_swap_variants(seed, spec, footprint, program_by_instance_id)
    seed_by_id = {r.id: r for r in seed}
    for variant in variants:
        for room in variant:
            original = seed_by_id[room.id]
            assert room.area_m2 == pytest.approx(original.area_m2, abs=1e-6)
            assert room.width * room.height == pytest.approx(original.width * original.height, abs=1e-6)


# 13. pair swapping does not swap room requirements (only different-type, matching dims swap) --


def test_pair_swap_never_changes_a_rooms_own_target_identity():
    spec = _mixed_bedroom_spec()
    footprint = _footprint()
    seed = GeometrySolver().solve(spec, footprint).instances
    variants = pair_swap_variants(seed, spec, footprint)
    seed_by_id = {r.id: r for r in seed}
    for variant in variants:
        for room in variant:
            original = seed_by_id[room.id]
            # a swap may move a room (change x, y) but must NEVER change its own id/type/area --
            # the room instance's own requirement travels with its id, never gets exchanged.
            assert room.type == original.type
            assert room.area_m2 == pytest.approx(original.area_m2, abs=1e-6)


def test_local_search_preserves_room_area():
    spec = _mixed_bedroom_spec()
    footprint = _footprint()
    seed = GeometrySolver().solve(spec, footprint).instances
    seed_by_id = {r.id: r for r in seed}
    for variant in local_search_variants(seed, spec, footprint):
        for room in variant:
            original = seed_by_id[room.id]
            assert room.area_m2 == pytest.approx(original.area_m2, abs=1e-6)
            assert room.width == pytest.approx(original.width, abs=1e-6)
            assert room.height == pytest.approx(original.height, abs=1e-6)


# 14. GeometricDesign remains compatible -------------------------------------------------------


def test_geometric_design_contract_unchanged_shape():
    spec = _mixed_bedroom_spec()
    footprint = _footprint()
    result = GeometrySolver().solve(spec, footprint)
    design = build_geometric_design(spec, footprint, result)
    assert len(design.rooms) == 6
    by_id = {r.id: r for r in design.rooms}
    assert by_id["MASTER_BEDROOM"].source == "USER_REQUIREMENT"
    assert by_id["BEDROOM_1"].source == "USER_REQUIREMENT"
    assert by_id["KITCHEN"].source == "MODEL_INFERENCE"


# --- Phase 10: real end-to-end example + sample JSON -----------------------------------------


def test_end_to_end_real_pipeline_example_and_save_sample():
    spec = _mixed_bedroom_spec()
    footprint = _footprint()

    v1 = GeometrySolver().solve(spec, footprint)
    assert v1.status == SolverStatus.satisfied
    v21 = plan_v2(spec, footprint)
    assert v21.status == SolverStatus.satisfied

    targets = {"MASTER_BEDROOM": 14.0, "BEDROOM_1": 11.0, "BEDROOM_2": 10.0}
    report = {"v1": {}, "v21": {}}
    for label, result_instances in (("v1", v1.instances), ("v21", v21.instances)):
        by_id = {r.id: r for r in result_instances}
        for room_id, room in sorted(by_id.items()):
            target = targets.get(room_id)
            row = {"actual_area_m2": room.area_m2, "width_m": room.width, "depth_m": room.height}
            if target is not None:
                error_m2, error_pct = _area_error(room.area_m2, target)
                row.update({"target_area_m2": target, "error_m2": round(error_m2, 3), "error_pct": round(error_pct, 4)})
            report[label][room_id] = row

    ordering_preserved = {
        label: by_id["MASTER_BEDROOM"].area_m2 > by_id["BEDROOM_1"].area_m2 > by_id["BEDROOM_2"].area_m2
        for label, by_id in (("v1", {r.id: r for r in v1.instances}), ("v21", {r.id: r for r in v21.instances}))
    }
    report["ordering_14_gt_11_gt_10_preserved"] = ordering_preserved
    print("\n=== ROOM_INSTANCE_SIZE_FIDELITY end-to-end report ===")
    print(json.dumps(report, indent=2, default=str))
    assert all(ordering_preserved.values())

    _SAMPLES_DIR.mkdir(exist_ok=True)
    design_v21 = build_geometric_design_v2(spec, footprint, v21)
    (_SAMPLES_DIR / "mixed_bedroom_sizes_v21_design.json").write_text(design_v21.model_dump_json(indent=2))
    (_SAMPLES_DIR / "mixed_bedroom_sizes_report.json").write_text(json.dumps(report, indent=2, default=str))


# --- Phase 8/11: interaction sanity with the previously-existing spatial-edit layer -----------
# (15/16: MOVE_ROOM / MOVE_ROOM_BY_VECTOR unchanged -- covered by the untouched
# tests/test_spatial_edit_endpoint.py, run as part of the full suite; nothing in this task
# modified app/geometry/spatial_edit*.py.)
