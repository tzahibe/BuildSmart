"""SPATIAL_V2_1 evaluation suite (Phase 6). Compares V1 (GeometrySolver, unmodified), "V2 baseline"
(base pool + translation only -- the exact candidate set app.geometry.spatial_v2.candidates
produced BEFORE this task), and V2.1 (generate_tagged_candidates, this task's structural variants +
local search), on identical real pipeline inputs, for the four required scenarios."""
import json
import math
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.architect.authoritative_merge import merge_authoritative_requirements
from app.architect.gateway import MockArchitectModelGateway
from app.design.pipeline import _build_request, _derive_footprint
from app.geometry.models import BuildingFootprintSpec, SolverStatus
from app.geometry.solver import (
    GeometrySolver,
    _group_by_type,
    _layout_satisfies_hard_requirements,
    generate_valid_candidate_pool,
)
from app.geometry.spatial_v2.candidates import _translated_variants, generate_tagged_candidates
from app.geometry.spatial_v2.fingerprint import adjacency_signature, exact_geometry_signature, relative_layout_fingerprint
from app.geometry.spatial_v2.planner import plan_v2
from app.geometry.spatial_v2.scoring import score_layout
from app.projects.models import PoolField, Project, SourceTag, TaggedBool, TaggedFloat, TaggedInt

_SAMPLES_DIR = Path(__file__).parent / "spatial_v2_1_samples"

_UNKNOWN_INT = TaggedInt(value=None, source=SourceTag.unknown)
_UNKNOWN_BOOL = TaggedBool(value=None, source=SourceTag.unknown)
_UNKNOWN_POOL = PoolField(requested=_UNKNOWN_BOOL, length_m=TaggedFloat(value=None, source=SourceTag.unknown), width_m=TaggedFloat(value=None, source=SourceTag.unknown))


def _project(*, built_area_m2: float, bedrooms: int, safe_room: bool) -> Project:
    now = datetime.now(UTC)
    return Project(
        project_id="eval", city="a", street="b", plot_area_m2=built_area_m2 * 4, built_area_m2=built_area_m2,
        description="evaluation fixture", status="active", created_at=now, updated_at=now,
        floors=TaggedInt(value=1, source=SourceTag.requested), bedrooms=TaggedInt(value=bedrooms, source=SourceTag.requested),
        safe_room=TaggedBool(value=safe_room, source=SourceTag.requested), parking_spaces=_UNKNOWN_INT, pool=_UNKNOWN_POOL,
        requirements_parsed_at=now,
    )


def _real_spec_and_footprint(project: Project, footprint_override: BuildingFootprintSpec | None = None):
    site_side_m = math.sqrt(project.plot_area_m2)
    request, _budget = _build_request(project, site_side_m)
    gateway = MockArchitectModelGateway()
    spec = gateway.generate(request)
    spec = merge_authoritative_requirements(spec, request)
    footprint = footprint_override or _derive_footprint(project)
    return spec, footprint


def _reshape_footprint(footprint: BuildingFootprintSpec, aspect_ratio: float) -> BuildingFootprintSpec:
    area = footprint.width_m * footprint.depth_m
    width = math.sqrt(area * aspect_ratio)
    depth = area / width
    return BuildingFootprintSpec(width_m=width, depth_m=depth, floor=footprint.floor, available_area_m2=footprint.available_area_m2)


def _v2_baseline_candidates(spec, footprint):
    """Recreates the EXACT candidate set app.geometry.spatial_v2.candidates.generate_candidates
    produced before this task (base pool + translations only) -- for an honest before/after
    comparison without needing a second, permanently-duplicated module."""
    base_solutions = generate_valid_candidate_pool(spec, footprint)
    seen = set()
    out = []
    for solution in base_solutions:
        for variant in _translated_variants(solution, spec, footprint):
            sig = exact_geometry_signature(variant)
            if sig in seen:
                continue
            seen.add(sig)
            out.append(variant)
    return out


def _major_adjacencies(instances) -> list:
    """Sorted list of distinct room-TYPE pairs that touch somewhere in this layout."""
    return sorted(tuple(sorted(pair)) for pair in adjacency_signature(instances) if isinstance(pair, frozenset))


def _run_scenario(label: str, project: Project, footprint_override: BuildingFootprintSpec | None = None):
    spec, footprint = _real_spec_and_footprint(project, footprint_override)

    v1_result = GeometrySolver().solve(spec, footprint)
    assert v1_result.status == SolverStatus.satisfied
    v1_score = score_layout(spec, footprint, v1_result.instances)
    v1_adjacencies = _major_adjacencies(v1_result.instances)

    v2_baseline = _v2_baseline_candidates(spec, footprint)
    v2_baseline_scored = [(c, score_layout(spec, footprint, c)) for c in v2_baseline]
    v2_baseline_scored.sort(key=lambda e: e[1].total_score, reverse=True)
    v2_best_instances, v2_best_score = v2_baseline_scored[0]
    v2_unique_relative = len({relative_layout_fingerprint(c) for c in v2_baseline})

    t0 = time.monotonic()
    v21_result = plan_v2(spec, footprint)
    v21_elapsed = time.monotonic() - t0
    assert v21_result.status == SolverStatus.satisfied
    assert _layout_satisfies_hard_requirements(spec, footprint, v21_result.instances)

    v21_adjacencies = _major_adjacencies(v21_result.instances)

    report = {
        "label": label,
        "v1_score": v1_score.total_score,
        "v1_components": v1_score.components,
        "v1_major_adjacencies": v1_adjacencies,
        "v2_score": v2_best_score.total_score,
        "v2_unique_relative_layouts": v2_unique_relative,
        "v21_score": v21_result.score.total_score,
        "v21_components": v21_result.score.components,
        "v21_unique_relative_layouts": v21_result.unique_relative_layout_count,
        "v21_candidate_count": v21_result.candidate_count,
        "v21_selected_strategy": v21_result.selected_strategy,
        "v21_elapsed_s": round(v21_elapsed, 3),
        "v21_major_adjacencies": v21_adjacencies,
        "adjacencies_changed": v21_adjacencies != v1_adjacencies,
    }
    print(f"\n=== {label} ===")
    print(json.dumps(report, indent=2, default=str))

    _SAMPLES_DIR.mkdir(exist_ok=True)
    (_SAMPLES_DIR / f"{label}_report.json").write_text(json.dumps(report, indent=2, default=str))

    return report, v21_result, v1_result


def test_square_2br():
    project = _project(built_area_m2=70, bedrooms=2, safe_room=False)
    report, v21, v1 = _run_scenario("square_2BR", project)
    assert report["v21_unique_relative_layouts"] > 1
    assert report["v21_elapsed_s"] < 1.0


def test_square_3br_safe_room():
    project = _project(built_area_m2=120, bedrooms=3, safe_room=True)
    report, v21, v1 = _run_scenario("square_3BR_saferoom", project)
    assert report["v21_unique_relative_layouts"] > 1
    assert report["v21_elapsed_s"] < 1.0
    # Phase 5 acceptance: square/tight case must offer more than a translation-only choice.
    assert report["v21_selected_strategy"] not in ("base_pool", "translation") or report["v21_unique_relative_layouts"] > report["v2_unique_relative_layouts"]


def test_wide_3br_safe_room():
    project = _project(built_area_m2=120, bedrooms=3, safe_room=True)
    _, base_footprint = _real_spec_and_footprint(project)
    wide_footprint = _reshape_footprint(base_footprint, aspect_ratio=2.0)
    report, v21, v1 = _run_scenario("wide_3BR_saferoom", project, footprint_override=wide_footprint)
    assert report["v21_unique_relative_layouts"] > 1
    assert report["v21_elapsed_s"] < 1.0
    # No regression: V2.1 must not score worse than the prior V2 baseline on the case V2 already helped.
    assert report["v21_score"] >= report["v2_score"] - 1e-6


def test_zoning_pressure():
    project = _project(built_area_m2=150, bedrooms=4, safe_room=True)
    report, v21, v1 = _run_scenario("zoning_pressure_4BR_saferoom", project)
    assert report["v21_unique_relative_layouts"] > 1
    assert report["v21_elapsed_s"] < 1.0
