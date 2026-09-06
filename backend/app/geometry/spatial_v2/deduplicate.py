"""Diversity-aware candidate pool (SPATIAL_V2_1 Phase 4): prevents the scored pool from being
dominated by near-identical layouts, while keeping the single best-scoring representative of every
distinct family so `ArchitecturalScore` still gets to pick among genuinely different options.

Three dedup levels, in increasing strength:
  1. exact geometry duplicates      -- already removed in candidates.py (cheapest, mechanical).
  2. pure-translation duplicates    -- candidates sharing a `relative_layout_fingerprint` are the
                                        SAME relative arrangement at a different absolute position;
                                        only the best-scoring one per fingerprint is kept.
  3. mirror-equivalent families      -- REPORTED (via `mirror_family_report`), never auto-removed:
                                        a mirrored layout can be architecturally different in a way
                                        this pipeline's own scoring already partly captures
                                        (exterior_access, entry-edge access can differ after a
                                        reflection), so collapsing mirrors by default would risk
                                        discarding a real distinction, not just a redundant one.
"""
from dataclasses import dataclass

from app.geometry.models import RoomInstance
from app.geometry.spatial_v2.fingerprint import relative_layout_fingerprint
from app.geometry.spatial_v2.scoring import ArchitecturalScore


def _mirror_key(instances: list[RoomInstance]) -> frozenset:
    """A fingerprint invariant to horizontal/vertical/both-axis reflection about the layout's own
    bounding box, on top of translation-invariance -- two layouts sharing this key are mirror
    images (or translations of mirror images) of one another."""
    if not instances:
        return frozenset()
    min_x = min(r.x for r in instances)
    max_x = max(r.x + r.width for r in instances)
    min_y = min(r.y for r in instances)
    max_y = max(r.y + r.height for r in instances)

    def canonical_xy(r: RoomInstance) -> tuple[float, float]:
        # Smallest-first between a coordinate and its mirror -- makes the key identical for a
        # layout and any of its 4 reflections (id/h/v/both), independent of which one we started from.
        x0 = round(r.x - min_x, 2)
        x1 = round((min_x + max_x) - (r.x + r.width) - min_x, 2)
        y0 = round(r.y - min_y, 2)
        y1 = round((min_y + max_y) - (r.y + r.height) - min_y, 2)
        return (min(x0, x1), min(y0, y1))

    return frozenset((r.id, *canonical_xy(r), round(r.width, 2), round(r.height, 2)) for r in instances)


@dataclass(frozen=True)
class ScoredCandidate:
    instances: list[RoomInstance]
    score: ArchitecturalScore


def deduplicate_by_relative_layout(scored_candidates: list[ScoredCandidate]) -> list[ScoredCandidate]:
    """Keeps only the best-scoring candidate per `relative_layout_fingerprint` family (translation
    duplicates collapsed), in deterministic order (first-seen-best-kept, ties broken by original
    order)."""
    best_by_fingerprint: dict[frozenset, ScoredCandidate] = {}
    for candidate in scored_candidates:
        fp = relative_layout_fingerprint(candidate.instances)
        current_best = best_by_fingerprint.get(fp)
        if current_best is None or candidate.score.total_score > current_best.score.total_score:
            best_by_fingerprint[fp] = candidate
    return list(best_by_fingerprint.values())


def mirror_family_report(scored_candidates: list[ScoredCandidate]) -> dict[frozenset, list[ScoredCandidate]]:
    """Groups (already relative-layout-deduplicated) candidates by mirror-equivalence, for
    reporting only -- never used to remove candidates from the pool."""
    families: dict[frozenset, list[ScoredCandidate]] = {}
    for candidate in scored_candidates:
        key = _mirror_key(candidate.instances)
        families.setdefault(key, []).append(candidate)
    return families
