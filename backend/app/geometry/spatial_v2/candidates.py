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
from app.geometry.instances import expand_program_to_instances
from app.geometry.models import BuildingFootprintSpec, RoomInstance
from app.geometry.solver import _layout_satisfies_hard_requirements, generate_valid_candidate_pool
from app.geometry.spatial_v2.fingerprint import exact_geometry_signature
from app.geometry.spatial_v2.local_search import local_search_variants
from app.geometry.spatial_v2.structural_variants import orientation_swap_variants, pair_swap_variants, reflection_variants

# Bounded, deterministic set of translation fractions tried per pooled solution (fraction of the
# solution's own free margin within the footprint) -- not exhaustive, not scenario-tuned: 0.0 is
# the solution's original (as-found) position, 1.0 shifts it fully into the opposite corner, 0.5
# centers it. Bounded at 5 fractions so candidate count stays small and predictable regardless of
# program size.
_TRANSLATION_FRACTIONS = (0.0, 0.25, 0.5, 0.75, 1.0)

# SPATIAL_V2_1: explicit, named bounds on every added search dimension -- see module docstring's
# generate_candidates() for how each is used. None of these scale with program size beyond what's
# already bounded upstream (generate_valid_candidate_pool caps at _MAX_SOLUTIONS per strategy).
MAX_SEEDS_FOR_STRUCTURAL_VARIANTS = 24  # = _MAX_SOLUTIONS(8) * len(_INSTANCE_ORDER_STRATEGIES)(3)
MAX_SEEDS_FOR_LOCAL_SEARCH = 12  # local search is the most expensive stage -- kept to half the seeds


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
    """Every hard-feasible layout Spatial V2(.1) will score -- see `generate_tagged_candidates` for
    the same pool with each candidate's originating strategy attached (used for reporting)."""
    return [candidate for candidate, _strategy in generate_tagged_candidates(spec, footprint)]


def generate_tagged_candidates(
    spec: ArchitecturalSpec, footprint: BuildingFootprintSpec, base_solutions=None, hard_filter=None
) -> list[tuple[list[RoomInstance], str]]:
    """Every hard-feasible layout Spatial V2(.1) will score, combining (all bounded, all
    deterministic, all hard-validated before being returned -- Phase 5's "keep hard feasibility
    separate from soft quality"), each tagged with the strategy that produced it:

      1. "base_pool"        -- Spatial V1's own pooled backtracking solutions, unmodified.
      2. "translation"      -- safe positional translations of each (unchanged from V2 -- this is
         what already helps wide/elongated footprints; kept exactly as before so behavior doesn't
         regress).
      3. "reflection" / "orientation_swap" / "pair_swap" -- SPATIAL_V2_1 structural variants
         (structural_variants.py) -- transformations that change the RELATIVE arrangement, which
         translation alone cannot do. This is what targets square/tight layouts, where every
         pooled solution already sits in a similar relative arrangement.
      4. "local_search"     -- SPATIAL_V2_1 bounded local search around a subset of seeds
         (local_search.py) -- small single-room and whole-zone-cluster perturbations.

    Deduplicated by exact geometry signature (fingerprint.py) -- a cheap, purely mechanical dedup;
    relative-layout/adjacency-level deduplication and best-of-family selection happens in
    `deduplicate.py`, run by the planner AFTER scoring (Phase 4), not here.
    """
    # Concept-first planning (app.geometry.planning) passes its own concept-realizing pool as
    # `base_solutions` and a `hard_filter` that rejects any variant breaking a concept edge -- so
    # every V2.1 refinement move stays INSIDE the chosen architectural concept. Both default to the
    # pre-existing behavior (legacy pool, no extra filter) for every prior caller.
    if base_solutions is None:
        base_solutions = generate_valid_candidate_pool(spec, footprint)
    # ROOM_INSTANCE_SIZE_FIDELITY: keyed by instance id (e.g. "BEDROOM_2"), never by room_type --
    # a type-keyed dict would collapse multiple same-type ProgramItems (differently-sized bedrooms)
    # onto whichever happens to be last.
    program_by_instance_id = {
        instance_id: item for instance_id, _room_type, item in expand_program_to_instances(spec.program)
    }

    tagged: list[tuple[list[RoomInstance], str]] = []
    seen_signatures: set[tuple] = set()

    def _add(candidate: list[RoomInstance], strategy: str) -> None:
        if hard_filter is not None and not hard_filter(candidate):
            return
        signature = exact_geometry_signature(candidate)
        if signature in seen_signatures:
            return
        seen_signatures.add(signature)
        tagged.append((candidate, strategy))

    for solution in base_solutions:
        _add(solution, "base_pool")
        for variant in _translated_variants(solution, spec, footprint):
            _add(variant, "translation")

    structural_seeds = base_solutions[:MAX_SEEDS_FOR_STRUCTURAL_VARIANTS]
    structural_variants: list[list[RoomInstance]] = []
    for solution in structural_seeds:
        for variant in reflection_variants(solution, spec, footprint):
            _add(variant, "reflection")
            structural_variants.append(variant)
        for variant in orientation_swap_variants(solution, spec, footprint, program_by_instance_id):
            _add(variant, "orientation_swap")
            structural_variants.append(variant)
        for variant in pair_swap_variants(solution, spec, footprint):
            _add(variant, "pair_swap")
            structural_variants.append(variant)

    local_search_seeds = (base_solutions + structural_variants)[:MAX_SEEDS_FOR_LOCAL_SEARCH]
    for solution in local_search_seeds:
        for variant in local_search_variants(solution, spec, footprint):
            _add(variant, "local_search")

    return tagged
