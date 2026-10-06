"""The ARRIVAL POLICY — which room a front door may open into, as a strict ranking (Issue #142O).

ONE source, like `wet_room_policy.py` is for wet-room entry. The rule was previously private to
`general_pipeline._entrance_rank`, so the band/proposal selection path could not reach it without
copying it; a second copy is exactly how two selection paths start disagreeing about what a good
entrance is. It does NOT live in `entrance_sequence.py`: that module measures the entrance sequence
and is deliberately barred from branching on a role name (its own
`test_no_coordinate_literal_or_fixture_name_branch_in_the_module` enforces it), whereas naming
LIVING is the whole content of this policy.

    arrival_rank(design) -> int     0 hall/circulation, 1 living, 2 anything else

Reads REALIZED geometry only — the entrance door's target zone and that room's already resolved
`.roles` — never a zone_id, a fixture name or a coordinate, so a brief's own naming is never a
signal. Pure and deterministic.
"""
from __future__ import annotations

from .design_output import GeometricDesign

#: A room carrying either role is circulation — mirrors `circulation_metrics._CIRCULATION_ROLES`.
_CIRCULATION_ROLES = ("HALL", "CIRCULATION")
#: The one public room a front door may open into without the plan being wrong. It is WORSE than
#: arriving in a hall (no buffer between the street and the living room), which is why it ranks
#: second rather than being either forbidden or equal.
_PUBLIC_FALLBACK_ROLE = "LIVING"

#: The front door opens into a hall or circulation space — the preferred arrival.
ARRIVAL_RANK_CIRCULATION = 0
#: The front door opens straight into the living room — allowed, but second.
ARRIVAL_RANK_LIVING = 1
#: Anything else. A plan this bad on arrival already fails C23 and never validates, so this exists
#: as a total-order floor rather than as a ranking a real candidate reaches.
ARRIVAL_RANK_OTHER = 2


def arrival_rank(design: GeometricDesign) -> int:
    """`ARRIVAL_RANK_*` for the room this design's realized front door opens into."""
    target = design.entrance_door.b
    roles = next((r.roles for r in design.rooms if r.zone_id == target), ())
    if set(_CIRCULATION_ROLES) & set(roles):
        return ARRIVAL_RANK_CIRCULATION
    if _PUBLIC_FALLBACK_ROLE in roles:
        return ARRIVAL_RANK_LIVING
    return ARRIVAL_RANK_OTHER


__all__ = ["ARRIVAL_RANK_CIRCULATION", "ARRIVAL_RANK_LIVING", "ARRIVAL_RANK_OTHER", "arrival_rank"]
