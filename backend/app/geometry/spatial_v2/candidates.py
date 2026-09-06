"""Candidate generation for Spatial V2 (Phase 5): reuses Spatial V1's own hard-feasibility search
(`app.geometry.solver.generate_valid_candidate_pool`, unmodified) rather than rewriting the
geometry engine, then safely diversifies each pooled solution's ABSOLUTE POSITION within the
footprint -- this directly targets the Phase 1 root cause: the existing objective
(`_score_candidate`) and the existing quality metrics (compactness, fragmentation, utilization) are
all translation-invariant, so a corner-anchored arrangement and the identical arrangement shifted
toward the footprint's center score IDENTICALLY on every one of those terms. Only Spatial V2's own
new `balance`/`strip_penalty` terms (scoring.py) can tell them apart -- but they can only do that if
a centered variant actually exists in the candidate pool to be scored in the first place.

Translating a whole solved arrangement by a fixed (dx, dy) preserves every RELATIVE hard constraint
(overlap, adjacency, area sum, zone connectivity) by construction -- none of those depend on
absolute position. The one hard constraint that IS position-dependent is entry-room edge access
(`_entry_room_has_allowed_edge_access` checks whether a room touches a SPECIFIC footprint edge), so
every translated variant is re-validated through the exact same
`_layout_satisfies_hard_requirements` function `solve()` itself uses before being kept -- a
translation that would break entry-edge access is simply dropped, never forced through.
"""
from app.architect.models import ArchitecturalSpec
from app.geometry.models import BuildingFootprintSpec, RoomInstance
from app.geometry.solver import _layout_satisfies_hard_requirements, generate_valid_candidate_pool

# Bounded, deterministic set of translation fractions tried per pooled solution (fraction of the
# solution's own free margin within the footprint) -- not exhaustive, not scenario-tuned: 0.0 is
# the solution's original (as-found) position, 1.0 shifts it fully into the opposite corner, 0.5
# centers it. Bounded at 5 fractions so candidate count stays small and predictable regardless of
# program size.
_TRANSLATION_FRACTIONS = (0.0, 0.25, 0.5, 0.75, 1.0)


def _translate(placed: list[RoomInstance], dx: float, dy: float) -> list[RoomInstance]:
    return [room.model_copy(update={"x": round(room.x + dx, 6), "y": round(room.y + dy, 6)}) for room in placed]


def _translated_variants(
    solution: list[RoomInstance], spec: ArchitecturalSpec, footprint: BuildingFootprintSpec
) -> list[list[RoomInstance]]:
    if not solution:
        return []
    min_x = min(room.x for room in solution)
    max_x = max(room.x + room.width for room in solution)
    min_y = min(room.y for room in solution)
    max_y = max(room.y + room.height for room in solution)

    margin_x = footprint.width_m - (max_x - min_x)
    margin_y = footprint.depth_m - (max_y - min_y)

    variants = []
    for fx in _TRANSLATION_FRACTIONS:
        for fy in _TRANSLATION_FRACTIONS:
            target_min_x = max(0.0, margin_x) * fx
            target_min_y = max(0.0, margin_y) * fy
            dx = target_min_x - min_x
            dy = target_min_y - min_y
            if abs(dx) < 1e-9 and abs(dy) < 1e-9:
                variants.append(solution)
                continue
            candidate = _translate(solution, dx, dy)
            if _layout_satisfies_hard_requirements(spec, footprint, candidate):
                variants.append(candidate)
    return variants


def generate_candidates(
    spec: ArchitecturalSpec, footprint: BuildingFootprintSpec
) -> list[list[RoomInstance]]:
    """Every hard-feasible layout Spatial V2 will score: Spatial V1's own pooled backtracking
    solutions, PLUS safe positional translations of each (deduped by rounded-coordinate signature).
    Every returned candidate has already passed `_layout_satisfies_hard_requirements` -- hard
    feasibility is fully decided before any Spatial V2 scoring runs (Phase 5's explicit
    "keep hard feasibility separate from soft quality")."""
    base_solutions = generate_valid_candidate_pool(spec, footprint)

    all_candidates: list[list[RoomInstance]] = []
    seen_signatures: set[tuple] = set()
    for solution in base_solutions:
        for variant in _translated_variants(solution, spec, footprint):
            signature = tuple(
                sorted((room.id, round(room.x, 3), round(room.y, 3)) for room in variant)
            )
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            all_candidates.append(variant)
    return all_candidates
