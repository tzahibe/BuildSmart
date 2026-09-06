import math
from dataclasses import dataclass

from app.projects.models import Project, Room, SourceTag

# Fixed room sizes (m²) — reasonable placeholders, not a standard; see
# specs/003-parametric-design-model/plan.md's Design decisions. A typical Israeli ממ"ד is roughly 9 m².
_KITCHEN_AREA_M2 = 12.0
_BATHROOM_AREA_M2 = 5.0
_SAFE_ROOM_AREA_M2 = 9.0

_BEDROOMS_UNKNOWN_NOTE = "מספר חדרי השינה לא ידוע — לא נכללו חדרי שינה בפריסה."
_SAFE_ROOM_UNKNOWN_NOTE = 'האם מבוקש ממ"ד לא ידוע — לא נכלל ממ"ד בפריסה.'


class FootprintTooSmallError(Exception):
    """Raised when a floor's available area can't fit its fixed-size rooms (FR-012)."""


@dataclass
class GeneratedDesign:
    site_width_m: float
    site_depth_m: float
    rooms: list[Room]
    design_notes: list[str]

    # Populated only by the new pipeline (app/design/pipeline.py), never by this module's own
    # `generate_design` below — see app/design/version.py's DesignVersion, which these four exist to
    # feed. `None`/empty here (this old generator's own construction sites never set them) simply means
    # "no version can be built from this" — app/projects/update.py checks for that.
    request_snapshot: dict | None = None
    adapter_diagnostics: list[str] | None = None
    spec_snapshot: dict | None = None
    solver_summary: dict | None = None

    # The stable UI geometry contract (see app/geometry/geometric_design.py's GeometricDesign),
    # `model_dump(mode="json")`-ed — populated only by the new pipeline, same as the four fields above.
    geometric_design: dict | None = None


def _row_layout(floor: int, floor_depth_m: float, entries: list[tuple[str, float]]) -> list[Room]:
    """Lay `entries` (room type, area_m2) out left-to-right in a single row spanning the floor's depth —
    see specs/003-parametric-design-model/research.md's 1D placeholder layout."""
    rooms: list[Room] = []
    x = 0.0
    for room_type, area_m2 in entries:
        width_m = area_m2 / floor_depth_m
        rooms.append(
            Room(
                type=room_type,
                floor=floor,
                area_m2=area_m2,
                x=x,
                y=0.0,
                width_m=width_m,
                depth_m=floor_depth_m,
            )
        )
        x += width_m
    return rooms


def generate_design(project: Project) -> GeneratedDesign:
    """Pure function — no I/O. Preconditions (parsed at least once) are checked by the router, not here;
    see specs/003-parametric-design-model/data-model.md's algorithm for the full derivation."""
    if project.floors is None or project.floors.value is None:
        raise ValueError("project must be parsed (Feature 02) before a design can be generated")

    site_width_m = site_depth_m = math.sqrt(project.plot_area_m2)

    floors = project.floors.value
    floor_area = project.built_area_m2 / floors
    floor_depth_m = math.sqrt(floor_area)

    design_notes: list[str] = []

    if project.bedrooms is not None and project.bedrooms.source != SourceTag.unknown:
        bedroom_count = project.bedrooms.value or 0
    else:
        bedroom_count = 0
        design_notes.append(_BEDROOMS_UNKNOWN_NOTE)

    safe_room_known_requested = (
        project.safe_room is not None
        and project.safe_room.source != SourceTag.unknown
        and project.safe_room.value is True
    )
    if project.safe_room is None or project.safe_room.source == SourceTag.unknown:
        design_notes.append(_SAFE_ROOM_UNKNOWN_NOTE)

    fixed_area = _KITCHEN_AREA_M2 + _BATHROOM_AREA_M2 + (_SAFE_ROOM_AREA_M2 if safe_room_known_requested else 0.0)
    if fixed_area > floor_area:
        raise FootprintTooSmallError(
            f"Ground floor's available area ({floor_area:.2f} m²) is too small to fit the required rooms "
            f"({fixed_area:.2f} m²)"
        )

    ground_floor_bedrooms = bedroom_count if floors == 1 else 0
    occupants = 1 + ground_floor_bedrooms  # living room (always) + same-floor bedrooms
    per_occupant_area = (floor_area - fixed_area) / occupants

    ground_entries: list[tuple[str, float]] = [
        ("kitchen", _KITCHEN_AREA_M2),
        ("bathroom", _BATHROOM_AREA_M2),
    ]
    if safe_room_known_requested:
        ground_entries.append(("safe_room", _SAFE_ROOM_AREA_M2))
    ground_entries.append(("living_room", per_occupant_area))
    ground_entries.extend(("bedroom", per_occupant_area) for _ in range(ground_floor_bedrooms))

    rooms = _row_layout(1, floor_depth_m, ground_entries)

    if floors > 1 and bedroom_count > 0:
        upper_floor_numbers = list(range(2, floors + 1))
        base_count, remainder = divmod(bedroom_count, len(upper_floor_numbers))
        for index, floor_num in enumerate(upper_floor_numbers):
            count = base_count + (1 if index < remainder else 0)
            if count == 0:
                continue
            per_bedroom_area = floor_area / count
            entries = [("bedroom", per_bedroom_area) for _ in range(count)]
            rooms.extend(_row_layout(floor_num, floor_depth_m, entries))

    return GeneratedDesign(
        site_width_m=site_width_m,
        site_depth_m=site_depth_m,
        rooms=rooms,
        design_notes=design_notes,
    )
