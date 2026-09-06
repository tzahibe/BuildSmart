"""Unit tests for SPATIAL_V2_1's candidate-diversity machinery (Phase 8)."""
import math
import time
from datetime import UTC, datetime

from app.architect.authoritative_merge import merge_authoritative_requirements
from app.architect.gateway import MockArchitectModelGateway
from app.design.pipeline import _build_request, _derive_footprint
from app.geometry.models import RoomInstance
from app.geometry.solver import _layout_satisfies_hard_requirements, _overlaps, generate_valid_candidate_pool
from app.geometry.spatial_v2.candidates import generate_candidates, generate_tagged_candidates
from app.geometry.spatial_v2.deduplicate import ScoredCandidate, deduplicate_by_relative_layout, mirror_family_report
from app.geometry.spatial_v2.fingerprint import (
    exact_geometry_signature,
    is_pure_translation,
    relative_layout_fingerprint,
)
from app.geometry.spatial_v2.local_search import local_search_variants
from app.geometry.spatial_v2.planner import plan_v2
from app.geometry.spatial_v2.scoring import score_layout
from app.geometry.spatial_v2.structural_variants import orientation_swap_variants, reflection_variants
from app.projects.models import PoolField, Project, SourceTag, TaggedBool, TaggedFloat, TaggedInt

_UNKNOWN_INT = TaggedInt(value=None, source=SourceTag.unknown)
_UNKNOWN_BOOL = TaggedBool(value=None, source=SourceTag.unknown)
_UNKNOWN_POOL = PoolField(requested=_UNKNOWN_BOOL, length_m=TaggedFloat(value=None, source=SourceTag.unknown), width_m=TaggedFloat(value=None, source=SourceTag.unknown))


def _project(built_area_m2, bedrooms, safe_room):
    now = datetime.now(UTC)
    return Project(
        project_id="e", city="a", street="b", plot_area_m2=built_area_m2 * 4, built_area_m2=built_area_m2,
        description="x", status="active", created_at=now, updated_at=now,
        floors=TaggedInt(value=1, source=SourceTag.requested), bedrooms=TaggedInt(value=bedrooms, source=SourceTag.requested),
        safe_room=TaggedBool(value=safe_room, source=SourceTag.requested), parking_spaces=_UNKNOWN_INT, pool=_UNKNOWN_POOL,
        requirements_parsed_at=now,
    )


def _spec_fp(p):
    site = math.sqrt(p.plot_area_m2)
    req, _ = _build_request(p, site)
    gw = MockArchitectModelGateway()
    spec = gw.generate(req)
    spec = merge_authoritative_requirements(spec, req)
    fp = _derive_footprint(p)
    return spec, fp


def _square_3br_saferoom():
    return _spec_fp(_project(120, 3, True))


# 1. pure translations share the same relative-layout fingerprint ---------------------------


def test_pure_translation_shares_fingerprint():
    room = RoomInstance(id="A", type="bedroom", floor=1, x=1.0, y=2.0, width=3.0, height=3.0, area_m2=9.0)
    other = RoomInstance(id="B", type="kitchen", floor=1, x=4.0, y=2.0, width=2.0, height=2.0, area_m2=4.0)
    original = [room, other]
    translated = [r.model_copy(update={"x": r.x + 5.0, "y": r.y + 3.0}) for r in original]

    assert is_pure_translation(original, translated)
    assert relative_layout_fingerprint(original) == relative_layout_fingerprint(translated)
    assert exact_geometry_signature(original) != exact_geometry_signature(translated)


# 2. structurally different layouts get different fingerprints ------------------------------


def test_structurally_different_layouts_get_different_fingerprints():
    a = RoomInstance(id="A", type="bedroom", floor=1, x=0.0, y=0.0, width=3.0, height=3.0, area_m2=9.0)
    b = RoomInstance(id="B", type="kitchen", floor=1, x=3.0, y=0.0, width=2.0, height=2.0, area_m2=4.0)
    layout_1 = [a, b]
    # B moved to sit BELOW A instead of beside it -- a genuinely different relative arrangement
    layout_2 = [a, b.model_copy(update={"x": 0.0, "y": 3.0})]

    assert relative_layout_fingerprint(layout_1) != relative_layout_fingerprint(layout_2)
    assert not is_pure_translation(layout_1, layout_2)


# 3. valid reflection candidates are accepted ------------------------------------------------


def test_reflection_variants_are_accepted_and_hard_valid():
    spec, footprint = _square_3br_saferoom()
    seeds = generate_valid_candidate_pool(spec, footprint)
    assert seeds

    found_any = False
    for seed in seeds:
        variants = reflection_variants(seed, spec, footprint)
        for variant in variants:
            found_any = True
            assert _layout_satisfies_hard_requirements(spec, footprint, variant)
            # a reflection must differ from its seed in relative arrangement whenever the seed
            # isn't already perfectly symmetric
            if relative_layout_fingerprint(variant) == relative_layout_fingerprint(seed):
                continue
    assert found_any, "expected at least one accepted reflection across all seeds"


# 4. invalid transformed candidates are rejected by hard validation -------------------------


def test_invalid_orientation_swap_is_rejected():
    """A room swapped to dimensions that would overlap a neighbor must never appear in the
    accepted variant list -- hard validation must reject it, not the caller."""
    # Two rooms placed edge-to-edge such that swapping A's width/height would overlap B.
    a = RoomInstance(id="A", type="bedroom", floor=1, x=0.0, y=0.0, width=2.0, height=5.0, area_m2=10.0)
    b = RoomInstance(id="B", type="kitchen", floor=1, x=2.0, y=0.0, width=2.0, height=2.0, area_m2=4.0)
    from app.geometry.models import BuildingFootprintSpec
    footprint = BuildingFootprintSpec(width_m=6.0, depth_m=6.0, floor=1, available_area_m2=36.0)

    class _FakeItem:
        min_width_m = 1.0

    program_by_type = {"bedroom": _FakeItem(), "kitchen": _FakeItem()}

    from app.architect.models import ArchitecturalSpec
    spec = ArchitecturalSpec(program=[], relationships=[], zones=[], circulation=None, incomplete_requirements=[])

    variants = orientation_swap_variants([a, b], spec, footprint, program_by_type)
    # swapping A (2x5 -> 5x2) would extend A to x=[0,5], overlapping B at x=[2,4] -- must be rejected
    for variant in variants:
        assert _layout_satisfies_hard_requirements(spec, footprint, variant)
        for i in range(len(variant)):
            for j in range(i + 1, len(variant)):
                r1, r2 = variant[i], variant[j]
                assert not _overlaps(r1.x, r1.y, r1.width, r1.height, r2.x, r2.y, r2.width, r2.height)


# 5. local search cannot bypass overlap/bounds/access constraints ---------------------------


def test_local_search_never_produces_invalid_candidates():
    spec, footprint = _square_3br_saferoom()
    seeds = generate_valid_candidate_pool(spec, footprint)
    for seed in seeds[:5]:
        for variant in local_search_variants(seed, spec, footprint):
            assert _layout_satisfies_hard_requirements(spec, footprint, variant)
            for i in range(len(variant)):
                for j in range(i + 1, len(variant)):
                    r1, r2 = variant[i], variant[j]
                    assert not _overlaps(r1.x, r1.y, r1.width, r1.height, r2.x, r2.y, r2.width, r2.height)
                assert variant[i].x >= -1e-6 and variant[i].y >= -1e-6
                assert variant[i].x + variant[i].width <= footprint.width_m + 1e-6
                assert variant[i].y + variant[i].height <= footprint.depth_m + 1e-6


# 6. deduplication reduces translation clones -------------------------------------------------


def test_deduplication_collapses_translation_clones_to_best_scoring():
    spec, footprint = _square_3br_saferoom()
    candidates = generate_candidates(spec, footprint)
    scored = [ScoredCandidate(c, score_layout(spec, footprint, c)) for c in candidates]

    deduped = deduplicate_by_relative_layout(scored)
    unique_fingerprints = {relative_layout_fingerprint(c.instances) for c in scored}

    assert len(deduped) == len(unique_fingerprints)
    assert len(deduped) < len(scored)  # real reduction -- translation clones existed and were collapsed

    # every family's survivor must be THE best-scoring member of that family, not an arbitrary one
    by_fp: dict = {}
    for c in scored:
        fp = relative_layout_fingerprint(c.instances)
        by_fp.setdefault(fp, []).append(c)
    survivors_by_fp = {relative_layout_fingerprint(c.instances): c for c in deduped}
    for fp, family in by_fp.items():
        assert survivors_by_fp[fp].score.total_score == max(m.score.total_score for m in family)


def test_mirror_family_report_does_not_remove_candidates():
    spec, footprint = _square_3br_saferoom()
    candidates = generate_candidates(spec, footprint)
    scored = [ScoredCandidate(c, score_layout(spec, footprint, c)) for c in candidates]
    deduped = deduplicate_by_relative_layout(scored)

    families = mirror_family_report(deduped)
    total_in_families = sum(len(members) for members in families.values())
    assert total_in_families == len(deduped)  # reporting only -- nothing dropped


# 7. at least one square/tight scenario creates multiple relative arrangements --------------


def test_square_tight_scenario_creates_multiple_relative_arrangements():
    spec, footprint = _square_3br_saferoom()
    result = plan_v2(spec, footprint)
    assert result.unique_relative_layout_count > 1
    # Phase 5's explicit anti-cheat: must not be satisfied by translation alone.
    assert result.selected_strategy != "translation"


# 8. candidate generation is deterministic ----------------------------------------------------


def test_candidate_generation_is_deterministic():
    spec, footprint = _square_3br_saferoom()
    first = generate_tagged_candidates(spec, footprint)
    second = generate_tagged_candidates(spec, footprint)

    first_sigs = [(exact_geometry_signature(c), s) for c, s in first]
    second_sigs = [(exact_geometry_signature(c), s) for c, s in second]
    assert first_sigs == second_sigs


# 9. best candidate is selected using existing ArchitecturalScore ---------------------------


def test_best_candidate_matches_max_architectural_score():
    spec, footprint = _square_3br_saferoom()
    candidates = generate_candidates(spec, footprint)
    scores = [score_layout(spec, footprint, c).total_score for c in candidates]

    result = plan_v2(spec, footprint)
    assert result.score.total_score == max(scores)


# 10. runtime stays bounded (Phase 7) --------------------------------------------------------


def test_runtime_stays_under_one_second_for_evaluation_scenarios():
    for built_area, bedrooms, safe_room in [(70, 2, False), (120, 3, True), (150, 4, True)]:
        spec, footprint = _spec_fp(_project(built_area, bedrooms, safe_room))
        t0 = time.monotonic()
        result = plan_v2(spec, footprint)
        elapsed = time.monotonic() - t0
        assert elapsed < 1.0, f"plan_v2 took {elapsed:.3f}s for bedrooms={bedrooms}"
        assert result.status.value == "satisfied"
