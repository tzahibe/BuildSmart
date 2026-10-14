"""How many rooms can a compact lobby actually serve?

The HUB_LOBBY parti distributes every room from one lobby. That lobby is compact by definition —
`compile_hub_lobby`'s own HALL `ZoneSpec` bounds it at 16 m2 and aspect 1.5 — and a compact
rectangle has a bounded perimeter. Each room reached from it needs a share of that perimeter at
least as wide as its own minimum short side, plus the engine's edge inset.

This computes that capacity from production's OWN numbers (`concept_generator.ROOM_TEMPLATES` and
the HALL bound), so "exactly 2 bedrooms" can be checked against geometry rather than read as an
arbitrary limitation.

    PYTHONPATH=backend python -m app.ai_harness.hub_capacity.capacity
"""
from __future__ import annotations

import math

from app.vertical_slice import concept_generator as cg
from app.vertical_slice.geometry_core.model import ProgramRole

#: `compile_hub_lobby`'s own HALL ZoneSpec — the definition of "compact lobby" this product uses.
HALL_AREA_MAX_M2 = 16.0
HALL_ASPECT_MAX = 1.5


def lobby_faces() -> tuple[float, float]:
    """The longest and shortest a compact lobby's faces can be, at its own bounds."""
    long_m = math.sqrt(HALL_AREA_MAX_M2 * HALL_ASPECT_MAX)
    return long_m, long_m / HALL_ASPECT_MAX


def edge_needed_m(role: ProgramRole) -> float:
    """The lobby edge one room of this role consumes: its own minimum short side plus the engine's
    edge inset, because a room narrower than that is not a room this engine will place."""
    return cg.ROOM_TEMPLATES[role].min_short_side_m + cg._EDGE_INSET_ALLOWANCE_M


def capacity() -> dict:
    """The parti's fan-out: the public opening and the master take one face each, the remaining
    bedroom-class rooms ring the long face, the shared wet rooms the short one."""
    long_m, short_m = lobby_faces()
    bedrooms_on_long = int(long_m // edge_needed_m(ProgramRole.BEDROOM))
    wets_on_short = int(short_m // edge_needed_m(ProgramRole.BATHROOM))
    return {
        "hall_area_max_m2": HALL_AREA_MAX_M2, "hall_aspect_max": HALL_ASPECT_MAX,
        "longest_face_m": round(long_m, 2), "shortest_face_m": round(short_m, 2),
        "edge_needed_m": {r.value: round(edge_needed_m(r), 2) for r in (
            ProgramRole.BEDROOM, ProgramRole.MASTER_BEDROOM, ProgramRole.SAFE_ROOM,
            ProgramRole.BATHROOM, ProgramRole.TOILET)},
        "bedrooms_on_the_long_face": bedrooms_on_long,
        "shared_wet_rooms_on_the_short_face": wets_on_short,
        #: the master takes the west face; the public band takes the north opening
        "total_bedrooms_servable": 1 + bedrooms_on_long,
    }


def main() -> dict:
    facts = capacity()
    print(f"compact lobby: area <= {facts['hall_area_max_m2']} m2, aspect <= {facts['hall_aspect_max']}")
    print(f"  longest face {facts['longest_face_m']} m, shortest {facts['shortest_face_m']} m")
    for role, need in facts["edge_needed_m"].items():
        print(f"  {role:16s} consumes {need} m of lobby edge")
    print(f"  => bedrooms on the long face: {facts['bedrooms_on_the_long_face']}")
    print(f"  => shared wet rooms on the short face: {facts['shared_wet_rooms_on_the_short_face']}")
    print(f"  => TOTAL BEDROOMS A COMPACT LOBBY CAN SERVE: {facts['total_bedrooms_servable']}")
    return facts


if __name__ == "__main__":
    main()
