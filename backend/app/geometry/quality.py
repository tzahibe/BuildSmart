"""Geometric layout-quality metrics — computed AFTER the solver has already found a valid (all-HARD-
constraints-satisfied) layout. Nothing here can make an invalid layout valid or vice versa; this module
only measures how GOOD an already-valid layout is, which `app/geometry/solver.py` uses to rank multiple
valid candidates against each other (see `_objective_score`).

Why a grid/rasterization approach: `unused_area_m2 = footprint_area - sum(room_area)` is a real number
but a bad proxy for quality on its own — two layouts can have identical unused area while one leaves it
as a single large usable rectangle and the other scatters it into several small, useless slivers between
rooms. Since every room and the footprint itself are axis-aligned rectangles (this codebase models no
other shape anywhere), the exact union/complement of a set of rectangles is computable in closed form,
but connected-components-of-the-complement (needed for "largest contiguous unused region") is much
simpler to get right via rasterization than via exact rectilinear polygon algorithms, at a small,
bounded, documented resolution cost. `_GRID_RESOLUTION_M` trades accuracy for speed; at typical
BuildSmart footprint sizes (roughly 8-25 m per side) this stays well under 200x200 cells, fast enough to
run once per candidate layout during ranking.
"""

from dataclasses import dataclass

from app.architect.models import ArchitecturalSpec, ConstraintSeverity
from app.geometry.models import BuildingFootprintSpec, RoomInstance

# 0.2 m cells: fine enough that a standard interior door width (0.9 m) or a small bathroom (~2 m side)
# is resolved by several cells, coarse enough to keep the grid small. Not tuned to any specific example
# — a general resolution/accuracy trade-off, documented so it can be revisited if a future footprint is
# much larger or smaller than what this codebase currently generates.
_GRID_RESOLUTION_M = 0.2


@dataclass(frozen=True)
class LayoutQualityMetrics:
    programmed_area_m2: float
    footprint_area_m2: float
    utilization_ratio: float
    unused_area_m2: float
    largest_contiguous_unused_region_m2: float
    # Derived, not one of the 8 requested metrics on its own, but what makes
    # largest_contiguous_unused_region_m2 interpretable at a glance: 1.0 means ALL unused area is one
    # single usable region; a low value means it's fragmented into many small, likely-useless slivers.
    unused_region_fragmentation_ratio: float
    compactness: float
    zone_cohesion_ratio: float
    circulation_quality_ratio: float


def _rasterize(footprint: BuildingFootprintSpec, placed: list[RoomInstance]) -> tuple[list[list[bool]], int, int]:
    """`grid[row][col] = True` means that cell is covered by at least one placed room. Grid origin
    matches the footprint's own (0, 0) at (row=0, col=0)."""
    cols = max(1, round(footprint.width_m / _GRID_RESOLUTION_M))
    rows = max(1, round(footprint.depth_m / _GRID_RESOLUTION_M))
    grid = [[False] * cols for _ in range(rows)]

    for room in placed:
        col_start = max(0, int(room.x / _GRID_RESOLUTION_M))
        col_end = min(cols, round((room.x + room.width) / _GRID_RESOLUTION_M))
        row_start = max(0, int(room.y / _GRID_RESOLUTION_M))
        row_end = min(rows, round((room.y + room.height) / _GRID_RESOLUTION_M))
        for r in range(row_start, row_end):
            for c in range(col_start, col_end):
                grid[r][c] = True

    return grid, rows, cols


def _largest_connected_unused_region_m2(grid: list[list[bool]], rows: int, cols: int) -> float:
    """4-connected flood fill over unused (`False`) cells — the largest component's cell count times
    one cell's area is the largest contiguous unused region, in m²."""
    visited = [[False] * cols for _ in range(rows)]
    cell_area = _GRID_RESOLUTION_M * _GRID_RESOLUTION_M
    largest = 0

    for start_r in range(rows):
        for start_c in range(cols):
            if grid[start_r][start_c] or visited[start_r][start_c]:
                continue
            size = 0
            stack = [(start_r, start_c)]
            visited[start_r][start_c] = True
            while stack:
                r, c = stack.pop()
                size += 1
                for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                    if 0 <= nr < rows and 0 <= nc < cols and not grid[nr][nc] and not visited[nr][nc]:
                        visited[nr][nc] = True
                        stack.append((nr, nc))
            largest = max(largest, size)

    return largest * cell_area


def _compactness(placed: list[RoomInstance]) -> float:
    """Bounding-box fill ratio of the placed-room union: programmed area divided by the area of the
    smallest axis-aligned box containing every placed room. 1.0 means the rooms tile their own bounding
    box with no gaps between them; a lower value means the rooms are spread out, leaving gaps WITHIN
    their own footprint even before considering unused space elsewhere. Independent of
    `utilization_ratio` on purpose — a small, tightly-clustered program in the corner of a huge
    footprint scores high on compactness and low on utilization; that's two different facts, not one.
    """
    if not placed:
        return 0.0
    min_x = min(room.x for room in placed)
    min_y = min(room.y for room in placed)
    max_x = max(room.x + room.width for room in placed)
    max_y = max(room.y + room.height for room in placed)
    bounding_area = (max_x - min_x) * (max_y - min_y)
    if bounding_area <= 0:
        return 0.0
    programmed_area = sum(room.area_m2 for room in placed)
    return min(1.0, programmed_area / bounding_area)


def _zone_cohesion_ratio(spec: ArchitecturalSpec, by_type: dict[str, list[RoomInstance]], shared_edge_length) -> float:
    """Normalized version of solver.py's `_zone_cohesion_score`: satisfied same-zone adjacent pairs
    divided by every POSSIBLE same-zone pair, so it's a comparable 0..1 ratio across specs with
    different room counts instead of an unbounded raw count."""
    satisfied = 0
    possible = 0
    for zone in spec.zones:
        if zone.cohesion_severity != ConstraintSeverity.soft:
            continue
        instances = [instance for room_type in zone.room_types for instance in by_type.get(room_type, [])]
        for i in range(len(instances)):
            for j in range(i + 1, len(instances)):
                possible += 1
                if shared_edge_length(instances[i], instances[j]) > 1e-6:
                    satisfied += 1
    return satisfied / possible if possible > 0 else 1.0


def _circulation_quality_ratio(spec: ArchitecturalSpec, by_type: dict[str, list[RoomInstance]], shared_edge_length) -> float:
    """Normalized version of solver.py's `_circulation_reach_score`: fraction of non-entry-type room
    INSTANCES directly adjacent to some entry-room-type instance. Inherits the exact same "not real
    path-planning" caveat documented in solver.py's module docstring — this is a ratio of the same crude
    proxy, not a new, more rigorous circulation model."""
    if spec.circulation is None:
        return 1.0  # nothing to evaluate — vacuously fine, matches the hard-check's own vacuous pass
    entry_instances = by_type.get(spec.circulation.entry_room_type, [])
    if not entry_instances:
        return 0.0
    reachable = 0
    total = 0
    for room_type, instances in by_type.items():
        if room_type == spec.circulation.entry_room_type:
            continue
        for instance in instances:
            total += 1
            if any(shared_edge_length(instance, entry) > 1e-6 for entry in entry_instances):
                reachable += 1
    return reachable / total if total > 0 else 1.0


def compute_quality_metrics(
    spec: ArchitecturalSpec,
    footprint: BuildingFootprintSpec,
    placed: list[RoomInstance],
    by_type: dict[str, list[RoomInstance]],
    shared_edge_length,
) -> LayoutQualityMetrics:
    footprint_area_m2 = footprint.width_m * footprint.depth_m
    programmed_area_m2 = sum(room.area_m2 for room in placed)
    unused_area_m2 = max(0.0, footprint_area_m2 - programmed_area_m2)
    utilization_ratio = programmed_area_m2 / footprint_area_m2 if footprint_area_m2 > 0 else 0.0

    grid, rows, cols = _rasterize(footprint, placed)
    largest_unused_m2 = _largest_connected_unused_region_m2(grid, rows, cols)
    fragmentation_ratio = (largest_unused_m2 / unused_area_m2) if unused_area_m2 > 1e-9 else 1.0

    return LayoutQualityMetrics(
        programmed_area_m2=round(programmed_area_m2, 3),
        footprint_area_m2=round(footprint_area_m2, 3),
        utilization_ratio=round(utilization_ratio, 4),
        unused_area_m2=round(unused_area_m2, 3),
        largest_contiguous_unused_region_m2=round(largest_unused_m2, 3),
        unused_region_fragmentation_ratio=round(min(1.0, fragmentation_ratio), 4),
        compactness=round(_compactness(placed), 4),
        zone_cohesion_ratio=round(_zone_cohesion_ratio(spec, by_type, shared_edge_length), 4),
        circulation_quality_ratio=round(_circulation_quality_ratio(spec, by_type, shared_edge_length), 4),
    )
