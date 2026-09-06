"""Structural candidate-generation strategies (SPATIAL_V2_1 Phase 2) -- transformations that can
produce a genuinely different RELATIVE room arrangement, not merely a translated copy of one
already in the pool. Every transform is a pure, generic geometric operation (reflection, dimension
transpose, position exchange) -- none reference a room type by name beyond generic hard-constraint
bookkeeping (min_width_m lookup), and none are tuned to any specific scenario. Every candidate this
module produces is re-validated through the SAME `_layout_satisfies_hard_requirements` Spatial V1
already uses before being returned -- a transform that would violate a hard constraint is simply
dropped, never forced through.
"""
from app.architect.models import ArchitecturalSpec
from app.geometry.models import BuildingFootprintSpec, RoomInstance
from app.geometry.solver import _layout_satisfies_hard_requirements, _overlaps

_DEFAULT_MIN_WIDTH_M = 1.5  # same fallback app.geometry.solver._DEFAULT_MIN_WIDTH_M uses


def _bbox(instances: list[RoomInstance]) -> tuple[float, float, float, float]:
    return (
        min(r.x for r in instances), max(r.x + r.width for r in instances),
        min(r.y for r in instances), max(r.y + r.height for r in instances),
    )


def _validated(candidate: list[RoomInstance], spec: ArchitecturalSpec, footprint: BuildingFootprintSpec):
    if _layout_satisfies_hard_requirements(spec, footprint, candidate):
        return candidate
    return None


# --- A/B/C: reflections -----------------------------------------------------------------------


def reflection_variants(
    solution: list[RoomInstance], spec: ArchitecturalSpec, footprint: BuildingFootprintSpec
) -> list[list[RoomInstance]]:
    """Mirrors the arrangement within its OWN bounding box (not the footprint's) along the
    horizontal axis, vertical axis, and both -- each is a genuinely different relative arrangement
    whenever the layout isn't already symmetric, since which room ends up on which side of which
    neighbor changes. Bounding-box extent is unchanged by a mirror, so footprint containment is
    preserved; only overlap/relationship/zone/entry-edge hard requirements need re-checking."""
    if not solution:
        return []
    min_x, max_x, min_y, max_y = _bbox(solution)

    def mirror_x(r: RoomInstance) -> RoomInstance:
        return r.model_copy(update={"x": round(min_x + max_x - (r.x + r.width), 6)})

    def mirror_y(r: RoomInstance) -> RoomInstance:
        return r.model_copy(update={"y": round(min_y + max_y - (r.y + r.height), 6)})

    horizontal = [mirror_x(r) for r in solution]
    vertical = [mirror_y(r) for r in solution]
    both = [mirror_y(mirror_x(r)) for r in solution]

    variants = []
    for candidate in (horizontal, vertical, both):
        validated = _validated(candidate, spec, footprint)
        if validated is not None:
            variants.append(validated)
    return variants


# --- F: orientation (width/height) swap --------------------------------------------------------


def orientation_swap_variants(
    solution: list[RoomInstance], spec: ArchitecturalSpec, footprint: BuildingFootprintSpec,
    program_by_instance_id: dict,
) -> list[list[RoomInstance]]:
    """For each room, tries swapping width<->height in place (same x, y) -- reshapes that single
    room's footprint (potentially changing which neighbor it touches) without moving anyone else.
    Skipped if the swapped dimensions would fall below THIS room INSTANCE's own min_width_m (the
    same hard bound app.geometry.solver._candidate_shapes already enforces when generating shapes
    in the first place) or would immediately overlap another room / exceed the footprint.

    `program_by_instance_id` (keyed by room.id, e.g. "BEDROOM_2", not room.type) is required, not
    a `{room_type: item}` dict -- ROOM_INSTANCE_SIZE_FIDELITY: two same-type instances can come
    from different ProgramItems with different bounds/targets, and a type-keyed lookup would
    silently apply the wrong instance's constraint here."""
    variants = []
    for i, room in enumerate(solution):
        if abs(room.width - room.height) < 1e-6:
            continue  # square room -- swapping is a no-op, not a new candidate
        item = program_by_instance_id.get(room.id)
        min_width = (item.min_width_m if item is not None else None) or _DEFAULT_MIN_WIDTH_M
        new_width, new_height = room.height, room.width
        if new_width + 1e-9 < min_width or new_height + 1e-9 < min_width:
            continue
        if room.x + new_width > footprint.width_m + 1e-6 or room.y + new_height > footprint.depth_m + 1e-6:
            continue
        swapped_room = room.model_copy(update={"width": new_width, "height": new_height, "area_m2": room.area_m2})
        others = solution[:i] + solution[i + 1:]
        if any(_overlaps(swapped_room.x, swapped_room.y, swapped_room.width, swapped_room.height, o.x, o.y, o.width, o.height) for o in others):
            continue
        candidate = others + [swapped_room]
        validated = _validated(candidate, spec, footprint)
        if validated is not None:
            variants.append(validated)
    return variants


# --- G: cross-type room-pair position exchange --------------------------------------------------


def pair_swap_variants(
    solution: list[RoomInstance], spec: ArchitecturalSpec, footprint: BuildingFootprintSpec
) -> list[list[RoomInstance]]:
    """For every pair of DIFFERENT-type rooms whose (width, height) match EXACTLY (same orientation
    -- no reshaping needed to fit the other's slot), swaps their (x, y) positions: a genuine
    topological rearrangement (which room TYPE occupies which slot changes, so type-level
    adjacency/relationship/zone satisfaction can change too), not just a translation. Same-type
    pairs are skipped: swapping two instances of the identical type produces no architectural
    difference under this pipeline's type-level scoring, only a different room-id label -- not the
    kind of diversity this module targets."""
    variants = []
    n = len(solution)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = solution[i], solution[j]
            if a.type == b.type:
                continue
            if abs(a.width - b.width) > 1e-6 or abs(a.height - b.height) > 1e-6:
                continue
            new_a = a.model_copy(update={"x": b.x, "y": b.y})
            new_b = b.model_copy(update={"x": a.x, "y": a.y})
            candidate = [new_a if k == i else new_b if k == j else solution[k] for k in range(n)]
            validated = _validated(candidate, spec, footprint)
            if validated is not None:
                variants.append(validated)
    return variants
