"""Geometry Core Proof Spike — the three fixtures.

  F1 RECT_SIMPLE   rectangular footprint, single wing, all-door topology
  F2 L_HOUSE       two wings meeting at a seam; access crosses the seam
  F3 OPEN_SAFEROOM open-plan public space (3 zones, no internal walls) + safe room with RC walls

Areas/dimensions are NET. Ranges are deliberately generous (~±25%) so the fixtures test the
ENGINE, not my ability to hand-fit numbers. `max_aspect_ratio` is per zone because circulation
legitimately is long and thin while a bedroom is not — a single global gate would be wrong.
"""
from __future__ import annotations

from model import (
    ConnectionKind,
    Cut,
    DesiredAccessEdge,
    DesiredAccessTopology,
    Fixture,
    Leaf,
    OutdoorClassification,
    OutdoorRegion,
    ProgramRole,
    Rect,
    Side,
    Split,
    Wing,
    ZoneSpec,
    m_to_u,
)


def _z(zid, roles, lo, target, hi, short, aspect=2.5) -> ZoneSpec:
    return ZoneSpec(zid, roles, lo, target, hi, short, aspect)


def V(a, b, fixed_m: float | None = None) -> Split:
    return Split(Cut.V, a, b, m_to_u(fixed_m) if fixed_m is not None else None)


def H(a, b, fixed_m: float | None = None) -> Split:
    return Split(Cut.H, a, b, m_to_u(fixed_m) if fixed_m is not None else None)


L = Leaf

# ---------------------------------------------------------------- F1 · rectangle

def rect_simple() -> Fixture:
    zones = (
        _z("LIVING", (ProgramRole.LIVING,), 26, 32, 42, 3.6),
        _z("KITCHEN", (ProgramRole.KITCHEN,), 10, 13, 18, 2.4, aspect=3.0),
        _z("HALL", (ProgramRole.HALL, ProgramRole.CIRCULATION), 10, 14, 20, 1.2, aspect=8.0),
        _z("BEDROOM_1", (ProgramRole.BEDROOM,), 11, 14, 18, 2.8),
        _z("BEDROOM_2", (ProgramRole.BEDROOM,), 10, 13, 17, 2.8),
        _z("BATH", (ProgramRole.BATHROOM,), 4.5, 6.5, 9.0, 1.7, aspect=3.0),
    )
    tree = V(
        H(L("LIVING"), L("KITCHEN")),
        V(L("HALL"), H(L("BEDROOM_1"), H(L("BEDROOM_2"), L("BATH")))),
    )
    wing = Wing("W", 0, 0, m_to_u(11.0), m_to_u(9.5), tree)
    access = DesiredAccessTopology((
        DesiredAccessEdge("HALL", "LIVING", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL", "KITCHEN", ConnectionKind.DOOR),
        DesiredAccessEdge("LIVING", "KITCHEN", ConnectionKind.CASED_OPENING, 1.4),
        DesiredAccessEdge("HALL", "BEDROOM_1", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL", "BEDROOM_2", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL", "BATH", ConnectionKind.DOOR),
    ))
    return Fixture("F1_RECT_SIMPLE", (wing,), zones, access)


# ---------------------------------------------------------------- F2 · L house

def l_house() -> Fixture:
    """Wing A is the tall bar; wing B is the shorter arm. The seam is wing A's HALL east side
    against wing B's west side — a FORCED cut at 8.5 m makes the seam align with a leaf
    boundary exactly, which is what stops it becoming a partly-exterior/partly-internal side."""
    zones = (
        _z("LIVING", (ProgramRole.LIVING,), 28, 34, 44, 3.6),
        _z("KITCHEN", (ProgramRole.KITCHEN,), 10, 13, 20, 2.4, aspect=3.0),
        _z("HALL", (ProgramRole.HALL, ProgramRole.CIRCULATION), 9, 12, 22, 1.2, aspect=8.0),
        _z("DINING", (ProgramRole.DINING,), 12, 20, 28, 2.6, aspect=3.0),
        _z("MASTER", (ProgramRole.MASTER_BEDROOM,), 11, 14, 19, 3.0),
        _z("BEDROOM_1", (ProgramRole.BEDROOM,), 9, 12, 16, 2.8),
        _z("BATH", (ProgramRole.BATHROOM,), 4.5, 6.0, 9.0, 1.7, aspect=3.0),
    )
    wing_a = Wing(
        "A", 0, 0, m_to_u(8.0), m_to_u(12.0),
        H(V(H(L("LIVING"), L("KITCHEN")), L("HALL")), L("DINING"), fixed_m=8.5),
        seam_leaf_sides=(("HALL", Side.E),),
    )
    wing_b = Wing(
        "B", m_to_u(8.0), 0, m_to_u(4.5), m_to_u(8.5),
        H(L("MASTER"), H(L("BEDROOM_1"), L("BATH"))),
        seam_leaf_sides=(("MASTER", Side.W), ("BEDROOM_1", Side.W), ("BATH", Side.W)),
    )
    access = DesiredAccessTopology((
        DesiredAccessEdge("HALL", "LIVING", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL", "KITCHEN", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL", "DINING", ConnectionKind.DOOR),
        DesiredAccessEdge("LIVING", "KITCHEN", ConnectionKind.CASED_OPENING, 1.4),
        DesiredAccessEdge("HALL", "MASTER", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL", "BEDROOM_1", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL", "BATH", ConnectionKind.DOOR),
    ))
    # CORRECTION 3: the L's bounding-box remainder is NOT automatically a garden. It is an
    # unclassified remainder until the site stage (not in this spike) classifies it.
    remainder = OutdoorRegion(
        "bbox_remainder",
        (Rect(m_to_u(8.0), m_to_u(8.5), m_to_u(4.5), m_to_u(3.5)),),
        OutdoorClassification.UNCLASSIFIED_REMAINDER,
    )
    return Fixture("F2_L_HOUSE", (wing_a, wing_b), zones, access, outdoor=(remainder,))


# ---------------------------------------------------------------- F3 · open plan + safe room

def open_plan_safe_room() -> Fixture:
    """LIVING+DINING+KITCHEN are ONE PhysicalSpace with three FunctionalZones: every boundary
    inside that group is wall-less, and their OPEN_CONNECTION edges must produce ZERO doors."""
    zones = (
        _z("LIVING", (ProgramRole.LIVING,), 28, 34, 46, 3.6),
        _z("DINING", (ProgramRole.DINING,), 9, 13, 20, 2.6, aspect=3.0),
        _z("KITCHEN", (ProgramRole.KITCHEN,), 9, 13, 20, 2.4, aspect=3.0),
        _z("HALL", (ProgramRole.HALL, ProgramRole.CIRCULATION), 10, 16, 24, 1.2, aspect=8.0),
        _z("MASTER", (ProgramRole.MASTER_BEDROOM,), 12, 14, 19, 3.0),
        # V2.1 Δ03: two roles, one zone. Safe-room rules AND bedroom rules both apply.
        # min_short_side raised 2.2 -> 2.4 m (Fable review §6 patch 4): P11 caught that the
        # original 2.2 m net short side, while satisfying the regulated area minimum and P5's
        # aspect gate, was too shallow to inscribe a real bed once this room also has to work
        # as a bedroom -- a genuine gap the area/aspect proofs alone could not see.
        _z("SAFE_ROOM", (ProgramRole.SAFE_ROOM, ProgramRole.BEDROOM), 9.0, 9.5, 13.0, 2.4),
        _z("BEDROOM_1", (ProgramRole.BEDROOM,), 10, 12, 17, 2.8),
        _z("BATH", (ProgramRole.BATHROOM,), 4.5, 6.0, 9.0, 1.7, aspect=3.0),
    )
    tree = V(
        H(L("LIVING"), V(L("DINING"), L("KITCHEN"))),                 # the open group
        V(L("HALL"), H(L("MASTER"), H(L("SAFE_ROOM"), H(L("BEDROOM_1"), L("BATH"))))),
    )
    wing = Wing("W", 0, 0, m_to_u(12.5), m_to_u(11.0), tree)
    access = DesiredAccessTopology((
        DesiredAccessEdge("LIVING", "DINING", ConnectionKind.OPEN_CONNECTION),
        DesiredAccessEdge("DINING", "KITCHEN", ConnectionKind.OPEN_CONNECTION),
        DesiredAccessEdge("HALL", "LIVING", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL", "MASTER", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL", "SAFE_ROOM", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL", "BEDROOM_1", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL", "BATH", ConnectionKind.DOOR),
    ))
    return Fixture(
        "F3_OPEN_SAFEROOM", (wing,), zones, access,
        open_groups=(("LIVING", "DINING", "KITCHEN"),),
    )


# ---------------------------------------------------------------- F4 · branching hall

def branching_hall() -> Fixture:
    """Fable review §4 patch 3: L1 said a hall serving 3+ rooms needs more than one hall leaf,
    and that was never actually exercised -- F1-F3 all used a single spanning-strip hall.

    HALL_MAIN and HALL_SPUR are two leaves, declared as ONE open circulation group so their
    shared boundary carries no wall (one continuous corridor), stacked in the SAME column so
    the corridor never needs to change width at the joint. LIVING and BEDROOM_1 are reachable
    only from HALL_MAIN; KITCHEN, BEDROOM_2 and BATH are reachable ONLY from HALL_SPUR (they do
    not touch HALL_MAIN at all) -- five served rooms, three of them unreachable without the
    branch. Every split is a FORCED cut (fixed_m) so the topology is exactly what is claimed,
    not left to the area-ratio heuristic.

    Honest limitation carried forward, not solved here: this proves a hall SPLIT INTO TWO
    LEAVES that together serve rooms no single leaf could reach (the actual problem L1 named).
    It does NOT prove a geometrically bent dogleg/L-shaped single corridor -- the open-marking
    mechanism (engine._mark_open_interfaces) only recognises a wall-less boundary between
    DIRECT SIBLINGS in the slicing tree, and two siblings under one Split are always aligned
    (same width for an H-cut, same height for a V-cut). A true perpendicular bend would need
    non-sibling adjacency, which this engine's open-plan mechanism cannot mark as open without
    being extended -- that extension is out of scope here (no engine changes).
    """
    zones = (
        _z("LIVING", (ProgramRole.LIVING,), 22, 28, 35, 3.6),
        _z("KITCHEN", (ProgramRole.KITCHEN,), 18, 23, 29, 2.4),
        _z("HALL_MAIN", (ProgramRole.HALL, ProgramRole.CIRCULATION), 6, 9, 12, 1.2, aspect=8.0),
        _z("HALL_SPUR", (ProgramRole.HALL, ProgramRole.CIRCULATION), 5.5, 7.5, 10, 1.2, aspect=8.0),
        _z("BEDROOM_1", (ProgramRole.BEDROOM,), 19, 24, 30, 2.8),
        _z("BEDROOM_2", (ProgramRole.BEDROOM,), 8, 10.5, 14, 2.4),
        _z("BATH", (ProgramRole.BATHROOM,), 7, 9, 12, 1.7, aspect=3.0),
    )
    left_column = H(L("LIVING"), L("KITCHEN"), fixed_m=6.0)
    hall_column = H(L("HALL_MAIN"), L("HALL_SPUR"), fixed_m=6.0)
    bottom_rooms = H(L("BEDROOM_2"), L("BATH"), fixed_m=2.6)
    rooms_column = H(L("BEDROOM_1"), bottom_rooms, fixed_m=6.0)
    right_side = V(hall_column, rooms_column, fixed_m=1.6)
    tree = V(left_column, right_side, fixed_m=5.0)
    wing = Wing("W", 0, 0, m_to_u(11.0), m_to_u(11.0), tree)
    access = DesiredAccessTopology((
        DesiredAccessEdge("LIVING", "HALL_MAIN", ConnectionKind.DOOR),
        DesiredAccessEdge("BEDROOM_1", "HALL_MAIN", ConnectionKind.DOOR),
        DesiredAccessEdge("KITCHEN", "HALL_SPUR", ConnectionKind.DOOR),
        DesiredAccessEdge("BEDROOM_2", "HALL_SPUR", ConnectionKind.DOOR),
        DesiredAccessEdge("BATH", "HALL_SPUR", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL_MAIN", "HALL_SPUR", ConnectionKind.OPEN_CONNECTION),
    ))
    return Fixture(
        "F4_BRANCHING_HALL", (wing,), zones, access,
        open_groups=(("HALL_MAIN", "HALL_SPUR"),),
    )


ALL_FIXTURES = (rect_simple, l_house, open_plan_safe_room, branching_hall)
