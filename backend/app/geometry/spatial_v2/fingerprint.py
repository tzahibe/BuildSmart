"""Canonical fingerprints for telling genuinely different room arrangements apart from mere
translations of the same relative layout (SPATIAL_V2_1 Phase 1).

`relative_layout_fingerprint` normalizes a candidate by translating it so its own bounding box
starts at (0, 0) -- two candidates that are pure translations of each other (same rooms, same
relative positions, shifted by a constant (dx, dy)) collapse to the IDENTICAL fingerprint. Any
candidate whose rooms are arranged differently relative to each other produces a different one.
Room IDENTITY (room.id) is part of the key, not just type, so this also distinguishes "which
specific room instance ended up where" -- a same-type instance swap (e.g. BEDROOM_1 <-> BEDROOM_2)
IS a different fingerprint under this definition, even though it may score identically (V2's
scoring reads by TYPE, not by instance id) -- `adjacency_signature` below is the type-level view
that a same-type swap does NOT change, used to separate "the room ID layout differs" from "the
architecturally meaningful structure differs".
"""
from app.geometry.models import RoomInstance
from app.geometry.solver import _group_by_type, _shared_edge_length

_COORD_PRECISION = 2  # cm-level rounding -- collapses float noise, not architectural distinctions


def relative_layout_fingerprint(instances: list[RoomInstance]) -> frozenset:
    if not instances:
        return frozenset()
    min_x = min(r.x for r in instances)
    min_y = min(r.y for r in instances)
    return frozenset(
        (
            r.id,
            round(r.x - min_x, _COORD_PRECISION),
            round(r.y - min_y, _COORD_PRECISION),
            round(r.width, _COORD_PRECISION),
            round(r.height, _COORD_PRECISION),
        )
        for r in instances
    )


def adjacency_signature(instances: list[RoomInstance]) -> frozenset:
    """Type-level (not instance-level) touching-pairs signature -- the architecturally meaningful
    structure V2's scoring actually reads (`_relationship_satisfied`/`_zone_cohesion_score`/etc. all
    operate on `by_type`). Two candidates with the same adjacency_signature satisfy the exact same
    type-level relationships/zoning, even if they differ in relative_layout_fingerprint (e.g. a
    same-type room swap)."""
    pairs = set()
    for i in range(len(instances)):
        for j in range(i + 1, len(instances)):
            a, b = instances[i], instances[j]
            if _shared_edge_length(a, b) > 1e-6:
                pairs.add(frozenset((a.type, b.type)) if a.type != b.type else (a.type, "self"))
    return frozenset(pairs)


def exact_geometry_signature(instances: list[RoomInstance]) -> tuple:
    """Absolute-position signature (NOT translation-normalized) -- distinguishes two candidates
    that are literal duplicates (same room, same x/y/width/height) from ones that only share a
    relative arrangement after normalization. Used for the cheapest, first-pass dedup stage."""
    return tuple(
        sorted((r.id, round(r.x, _COORD_PRECISION), round(r.y, _COORD_PRECISION), round(r.width, _COORD_PRECISION), round(r.height, _COORD_PRECISION)) for r in instances)
    )


def is_pure_translation(a: list[RoomInstance], b: list[RoomInstance]) -> bool:
    """True if `b` is `a` shifted by one constant (dx, dy) -- i.e. same relative_layout_fingerprint.
    A convenience wrapper naming the exact check Phase 1/8 ask to prove."""
    return relative_layout_fingerprint(a) == relative_layout_fingerprint(b)
