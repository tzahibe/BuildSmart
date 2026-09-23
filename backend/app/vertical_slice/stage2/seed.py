"""Stage 2 (B/2), Issue #134 — the seed: the donor's own partition, carried as data, before repair.

`build_seed_geometry` implements Required Behaviour 1's own type (`contract.SeedGeometry`, Issue
#133 §2): one `SeedCell` per donor room that SURVIVES adaptation's CARRIED decision (a `DROPPED`
room never gets a seed cell; an `ADDED` room has no donor partition to seed FROM — see
`contract.SeedCell`'s own docstring), each cell's polygon copied verbatim from the donor room's own
polygon (not resized, not repositioned), and `adjacency` copied verbatim from `donor.adjacency_edges`
restricted to the kept rooms — never re-derived from geometry.
"""
from __future__ import annotations

from .contract import DONOR_PLAN_FRAME, SeedCell, SeedGeometry
from .donor import DonorPlan


def build_seed_geometry(donor: DonorPlan, carried_room_ids: tuple[str, ...]) -> SeedGeometry:
    kept = set(carried_room_ids)
    cells = tuple(
        SeedCell(cell_id=f"seed__{room.id}", donor_room_id=room.id, polygon_m=room.polygon_m)
        for room in donor.rooms
        if room.id in kept
    )
    adjacency = tuple(
        (a, b) for a, b in donor.adjacency_edges if a in kept and b in kept
    )
    return SeedGeometry(source_plan_id=donor.plan_id, frame=DONOR_PLAN_FRAME, cells=cells,
                         adjacency=adjacency)
