"""Bounded local search (SPATIAL_V2_1 Phase 3): small deterministic perturbations around a valid
candidate, each re-validated through the same hard-feasibility check Spatial V1 already uses.
Deliberately does NOT call the public spatial-edit API (`app.geometry.spatial_edit`) -- that layer
exists for editing an already-PERSISTED, already-chosen design one room at a time; the planner
here is exploring many in-memory CANDIDATES before any design is chosen, so it works directly with
`RoomInstance` lists and the same domain primitives `structural_variants.py` and
`app.geometry.solver` already use, per this task's explicit instruction to reuse geometry
primitives directly rather than go through that API.

Bounded by construction: a fixed, small step set, a fixed cap on how many seed candidates are
perturbed, and a fixed cap on how many rooms per seed are perturbed -- never unbounded/exhaustive,
and always in a deterministic (list-order) iteration sequence.
"""
from app.architect.models import ArchitecturalSpec
from app.geometry.models import BuildingFootprintSpec, RoomInstance
from app.geometry.solver import _layout_satisfies_hard_requirements, _overlaps
from app.geometry.spatial_v2.intent import Zone, zone_by_room_type

# Bounded, deterministic perturbation steps (meters) -- generic architectural "nudge" sizes, not
# fitted to any scenario's dimensions.
_STEP_SIZES_M = (0.3, 0.6)
_STEP_DIRECTIONS = ((1, 0), (-1, 0), (0, 1), (0, -1))

MAX_ROOMS_PERTURBED_PER_SEED = 8  # every room in any of this pipeline's real programs (<=9 today)


def _single_room_perturbations(
    solution: list[RoomInstance], spec: ArchitecturalSpec, footprint: BuildingFootprintSpec
) -> list[list[RoomInstance]]:
    """Move ONE room by a small step in one of 4 directions, at one of 2 magnitudes -- 8 bounded
    perturbations per room, capped at MAX_ROOMS_PERTURBED_PER_SEED rooms."""
    results = []
    for i, room in enumerate(solution[:MAX_ROOMS_PERTURBED_PER_SEED]):
        others = solution[:i] + solution[i + 1:]
        for step in _STEP_SIZES_M:
            for ddx, ddy in _STEP_DIRECTIONS:
                dx, dy = ddx * step, ddy * step
                new_x, new_y = round(room.x + dx, 6), round(room.y + dy, 6)
                if new_x < -1e-9 or new_y < -1e-9:
                    continue
                if new_x + room.width > footprint.width_m + 1e-6 or new_y + room.height > footprint.depth_m + 1e-6:
                    continue
                moved = room.model_copy(update={"x": new_x, "y": new_y})
                if any(_overlaps(moved.x, moved.y, moved.width, moved.height, o.x, o.y, o.width, o.height) for o in others):
                    continue
                candidate = others + [moved]
                if _layout_satisfies_hard_requirements(spec, footprint, candidate):
                    results.append(candidate)
    return results


def _zone_cluster_perturbations(
    solution: list[RoomInstance], spec: ArchitecturalSpec, footprint: BuildingFootprintSpec
) -> list[list[RoomInstance]]:
    """Move an entire zone's rooms together by a small step, preserving their internal relative
    structure -- tests whether shifting a whole PRIVATE/PUBLIC/SERVICE cluster (not just one room)
    opens up a better arrangement, still fully re-validated."""
    node_types = {room.type for room in solution}
    zones = zone_by_room_type(spec.zones, node_types)
    by_zone: dict[Zone, list[int]] = {}
    for idx, room in enumerate(solution):
        by_zone.setdefault(zones.get(room.type), []).append(idx)

    results = []
    for zone, indices in by_zone.items():
        if len(indices) < 2:
            continue  # a single-room "cluster" is already covered by single-room perturbations
        others_idx = [k for k in range(len(solution)) if k not in indices]
        for step in _STEP_SIZES_M:
            for ddx, ddy in _STEP_DIRECTIONS:
                dx, dy = ddx * step, ddy * step
                moved_cluster = []
                out_of_bounds = False
                for idx in indices:
                    r = solution[idx]
                    new_x, new_y = round(r.x + dx, 6), round(r.y + dy, 6)
                    if new_x < -1e-9 or new_y < -1e-9 or new_x + r.width > footprint.width_m + 1e-6 or new_y + r.height > footprint.depth_m + 1e-6:
                        out_of_bounds = True
                        break
                    moved_cluster.append(r.model_copy(update={"x": new_x, "y": new_y}))
                if out_of_bounds:
                    continue
                # A shared (dx, dy) translation preserves every relative position within the
                # cluster exactly, so cluster-internal overlap cannot be introduced by this move --
                # only overlap against rooms OUTSIDE the cluster needs checking.
                others = [solution[k] for k in others_idx]
                if any(
                    _overlaps(m.x, m.y, m.width, m.height, o.x, o.y, o.width, o.height)
                    for m in moved_cluster for o in others
                ):
                    continue
                candidate = others + moved_cluster
                if _layout_satisfies_hard_requirements(spec, footprint, candidate):
                    results.append(candidate)
    return results


def local_search_variants(
    solution: list[RoomInstance], spec: ArchitecturalSpec, footprint: BuildingFootprintSpec
) -> list[list[RoomInstance]]:
    """All bounded local-search perturbations of one seed candidate: single-room nudges (D) and
    whole-zone-cluster shifts (E). Every returned candidate has already passed
    `_layout_satisfies_hard_requirements`."""
    return _single_room_perturbations(solution, spec, footprint) + _zone_cluster_perturbations(solution, spec, footprint)
