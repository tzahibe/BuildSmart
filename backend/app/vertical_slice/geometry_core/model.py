"""Geometry Core — data model. FROZEN per Fable adversarial review verdict (GO WITH PATCHES,
2026-09-08): promoted verbatim from `backend/spikes/geometry_core/model.py` into production for
the Private House V1 first vertical slice.

Do not change this module's logic without a demonstrated integration bug — the vertical slice
is built to consume this engine as-is. The one intentional non-behavioral change from the spike
version is a rename in `engine.py` (`SpikeInfeasible` -> `GeometryInfeasible`); every proof and
regression test that validated this code in the spike still applies unchanged to this copy (see
`backend/spikes/geometry_core/README.md` and `backend/tests/vertical_slice/` for the port-fidelity
regression tests). It exists to prove — and now build on — one claim from
`PRIVATE_HOUSE_V1_ENGINE_DECISION.md` §3 + §7:

    slicing tree + shape curves + wall thickness known BEFORE dimensioning

This module also carries the three corrections the Fable review required before the spike:

  CORRECTION 1 — `ConnectionKind`
      `DesiredAccessTopology` edges distinguish DOOR / OPEN_CONNECTION / CASED_OPENING.
      An OPEN_CONNECTION must never produce a door; that is proof P8.

  CORRECTION 2 — `Mobility`
      LOOSE furniture is movable during placement but STILL participates in the final
      circulation clearance. (V2.1 wrongly said only FIXED participates.) Encoded here;
      NOT exercised by this spike — furniture placement is out of the geometry core.

  CORRECTION 3 — `OutdoorRegion.classification`
      Garden/terrace are explicit classifications, never "whatever is left over".
      A remainder region is UNCLASSIFIED_REMAINDER until something classifies it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------- geometry primitives

# All geometry is in integer grid units to keep tiling exact (no float drift).
# One unit = 5 cm — the granularity architects actually dimension walls at.
UNIT_M = 0.05


def m_to_u(metres: float) -> int:
    return int(round(metres / UNIT_M))


def u_to_m(units: int) -> float:
    return round(units * UNIT_M, 4)


@dataclass(frozen=True)
class Rect:
    """Axis-aligned rectangle in grid units. Centerline geometry unless stated otherwise."""

    x: int
    y: int
    w: int
    h: int

    @property
    def x2(self) -> int:
        return self.x + self.w

    @property
    def y2(self) -> int:
        return self.y + self.h

    def area_m2(self) -> float:
        return round(self.w * self.h * UNIT_M * UNIT_M, 4)

    def overlap_area_u(self, other: "Rect") -> int:
        dx = min(self.x2, other.x2) - max(self.x, other.x)
        dy = min(self.y2, other.y2) - max(self.y, other.y)
        return dx * dy if dx > 0 and dy > 0 else 0

    def shared_edge_len_u(self, other: "Rect") -> int:
        """Length of the touching edge, 0 if they do not touch (or overlap)."""
        if self.x2 == other.x or other.x2 == self.x:  # vertical contact
            return max(0, min(self.y2, other.y2) - max(self.y, other.y))
        if self.y2 == other.y or other.y2 == self.y:  # horizontal contact
            return max(0, min(self.x2, other.x2) - max(self.x, other.x))
        return 0


class Side(str, Enum):
    N = "N"
    S = "S"
    E = "E"
    W = "W"


# ---------------------------------------------------------------- walls

class WallType(str, Enum):
    EXTERIOR = "EXTERIOR"
    PARTITION = "PARTITION"
    RC_SAFE_ROOM = "RC_SAFE_ROOM"
    OPEN = "OPEN"  # no wall at all — two zones of one open-plan PhysicalSpace


# Thicknesses in metres. EXTERIOR / PARTITION are DOMAIN FACT for the spike's purposes.
# RC_SAFE_ROOM is REGULATION and therefore a PARAMETER — the value below is a placeholder
# and is NOT a verified legal figure (see the report §10 "no regulatory number in code").
# NOTE: every value must be an even multiple of the grid so that half-thicknesses land on
# grid units exactly. 0.25 m would give a 0.125 m inset = 2.5 units and break exact tiling.
WALL_THICKNESS_M: dict[WallType, float] = {
    WallType.EXTERIOR: 0.30,
    WallType.PARTITION: 0.10,
    WallType.RC_SAFE_ROOM: 0.30,  # PARAMETER · UNVERIFIED (regulation)
    WallType.OPEN: 0.0,
}


def half_thickness_units(thickness_m: float, *, label: str) -> int:
    """Exact half-thickness in grid units, or raise.

    TEMPORARY SAFETY GUARD, not a permanent domain limitation (Fable review §3 patch 1):
    this spike's search grid is 5 cm, so a wall thickness must currently be an exact grid
    multiple or its half-thickness cannot be represented as an integer number of units.
    `m_to_u`'s round-half-to-even previously mis-rounded e.g. 0.125 m -> 2 units instead of
    2.5 -- a silent net-area error big enough to violate a regulated minimum with no proof
    catching it beforehand. Fail fast instead of rounding. If a verified regulation value
    ever turns out non-grid-aligned, the fix is NOT to relax this check: add an exact-
    millimetre reconciliation pass after the grid search (reserve the ceiling during search,
    report the true net area from the exact value afterward) -- do not silently round here.
    """
    half_u = thickness_m / 2.0 / UNIT_M
    rounded = round(half_u)
    if abs(half_u - rounded) > 1e-9:
        raise ValueError(
            f"{label} thickness {thickness_m} m is not grid-aligned at grid={UNIT_M} m: "
            f"half-thickness {thickness_m / 2.0} m = {half_u} units, not an integer. "
            f"Refusing to silently round (see half_thickness_units docstring)."
        )
    return rounded


def inset_u(wall: WallType) -> int:
    """Half the wall thickness, in grid units — what one side loses off the centerline."""
    return half_thickness_units(WALL_THICKNESS_M[wall], label=wall.value)


# Eager check at import time: every DECLARED wall type is validated, not just the ones a
# given fixture happens to exercise through inset_u().
for _wall, _thickness_m in WALL_THICKNESS_M.items():
    half_thickness_units(_thickness_m, label=_wall.value)
del _wall, _thickness_m


# ---------------------------------------------------------------- program

class ProgramRole(str, Enum):
    ENTRANCE = "ENTRANCE"
    HALL = "HALL"
    LIVING = "LIVING"
    DINING = "DINING"
    KITCHEN = "KITCHEN"
    BEDROOM = "BEDROOM"
    MASTER_BEDROOM = "MASTER_BEDROOM"
    SAFE_ROOM = "SAFE_ROOM"
    BATHROOM = "BATHROOM"
    CIRCULATION = "CIRCULATION"
    #: Genuine unassigned interior area — the requested built area exceeds what the room programme
    #: can responsibly use, and rather than stretching a bedroom past its own cap (or refusing to
    #: plan at all), the gap is a real, visible zone. Never requested by the person; added only by
    #: `concept_generator.generate_concepts` when the numbers require it.
    FLEX = "FLEX"


@dataclass(frozen=True)
class ZoneSpec:
    """One FunctionalZone's requirement. Areas/dims are NET (clear internal), never centerline.

    `roles` is a set (V2.1 Δ03): a safe room that is also a bedroom carries both, and every
    role's rules apply. `primary_role` is what area accounting attributes it to.
    """

    zone_id: str
    roles: tuple[ProgramRole, ...]
    net_area_min_m2: float
    net_area_target_m2: float
    net_area_max_m2: float
    # Shortest permissible side, NET. Deliberately not width/depth: a room does not care which
    # axis it is on, and an axis-specific bound produces orientation artefacts.
    min_short_side_m: float
    # Report §15 A4 — proportional quality gate.
    max_aspect_ratio: float = 2.5

    @property
    def primary_role(self) -> ProgramRole:
        return self.roles[0]

    @property
    def is_safe_room(self) -> bool:
        return ProgramRole.SAFE_ROOM in self.roles


# ---------------------------------------------------------------- furniture envelope (Fable
# review §6 patch 4: a cheap feasibility SCREEN, not a placement engine)

# PRODUCT POLICY placeholders — NOT a verified furniture catalog. Purpose: catch a room that
# passes area/aspect proofs (P4/P5) but is geometrically too narrow to hold ANY plausible
# furniture set for its role (e.g. a bedroom-shaped room too shallow for a bed). Each value is
# a single conservative (width, depth) bounding envelope for that role's minimum furniture set
# plus clearance -- not a real multi-item placement result. Roles with no entry here (HALL,
# CIRCULATION, ENTRANCE) are not furnished spaces in this spike's scope and are skipped.
MIN_FURNITURE_ENVELOPE_M: dict[ProgramRole, tuple[float, float]] = {
    ProgramRole.LIVING: (3.0, 3.0),
    ProgramRole.DINING: (2.4, 2.4),
    ProgramRole.KITCHEN: (2.4, 1.8),
    ProgramRole.BEDROOM: (2.4, 2.4),
    ProgramRole.MASTER_BEDROOM: (2.8, 2.8),
    ProgramRole.SAFE_ROOM: (2.0, 1.8),
    ProgramRole.BATHROOM: (1.6, 1.6),
}


def min_furniture_envelope_m(zone: "ZoneSpec") -> tuple[float, float] | None:
    """The governing (width, depth) envelope for a zone, or None if its role(s) carry no
    furniture requirement here. A zone with multiple roles (e.g. SAFE_ROOM + BEDROOM) must
    satisfy all of them at once in the SAME room, so this takes the per-axis MAX across
    applicable roles rather than summing separate furniture sets."""
    applicable = [MIN_FURNITURE_ENVELOPE_M[r] for r in zone.roles if r in MIN_FURNITURE_ENVELOPE_M]
    if not applicable:
        return None
    return (max(e[0] for e in applicable), max(e[1] for e in applicable))


def furniture_envelope_fits(zone: "ZoneSpec", net_w_m: float, net_h_m: float) -> bool | None:
    """Can the zone's NET rectangle inscribe its governing envelope in either orientation?
    None (not False) if the role has no declared envelope -- distinct from a real failure."""
    env = min_furniture_envelope_m(zone)
    if env is None:
        return None
    ew, ed = env
    eps = 1e-6
    return (ew <= net_w_m + eps and ed <= net_h_m + eps) or (ew <= net_h_m + eps and ed <= net_w_m + eps)


# ---------------------------------------------------------------- access topology

class ConnectionKind(str, Enum):
    """CORRECTION 1. What kind of connection a desired access edge asks for."""

    DOOR = "DOOR"                      # a door leaf in a wall
    CASED_OPENING = "CASED_OPENING"    # an opening in a wall, no leaf
    OPEN_CONNECTION = "OPEN_CONNECTION"  # NO wall at all — same open-plan PhysicalSpace


@dataclass(frozen=True)
class DesiredAccessEdge:
    a: str
    b: str
    kind: ConnectionKind
    min_clear_m: float = 0.9  # required shared boundary for DOOR / CASED_OPENING


@dataclass(frozen=True)
class DesiredAccessTopology:
    """Planning INTENT, authored before geometry. Never derived from openings — that is the
    other direction (`RealizedAccessGraph`), and keeping them separate is what breaks the
    circularity the reviewer flagged."""

    edges: tuple[DesiredAccessEdge, ...]

    def of_kind(self, kind: ConnectionKind) -> list[DesiredAccessEdge]:
        return [e for e in self.edges if e.kind == kind]


# ---------------------------------------------------------------- furniture (encoded, not exercised)

class Mobility(str, Enum):
    """CORRECTION 2.

    FIXED — placed and immovable (built-in, sanitary ware, kitchen run).
    LOOSE — MAY BE MOVED while placing, but once placed it still occupies space and
            therefore STILL COUNTS toward the final circulation clearance.

    This corrects V2.1, which said only FIXED participates in `clear_width`. Not exercised
    by this spike: furniture placement is outside the geometry core.
    """

    FIXED = "FIXED"
    LOOSE = "LOOSE"


@dataclass(frozen=True)
class FurnitureItem:
    name: str
    w_m: float
    d_m: float
    mobility: Mobility
    front_clearance_m: float = 0.0
    side_clearance_m: float = 0.0

    def counts_toward_clearance(self) -> bool:
        """Both mobilities do — see CORRECTION 2."""
        return True


# ---------------------------------------------------------------- outdoor

class OutdoorClassification(str, Enum):
    """CORRECTION 3. A remainder is NOT automatically a garden."""

    GARDEN = "GARDEN"
    TERRACE = "TERRACE"
    BALCONY = "BALCONY"
    UNCLASSIFIED_REMAINDER = "UNCLASSIFIED_REMAINDER"


@dataclass(frozen=True)
class OutdoorRegion:
    region_id: str
    rects: tuple[Rect, ...]
    classification: OutdoorClassification = OutdoorClassification.UNCLASSIFIED_REMAINDER

    @property
    def is_classified(self) -> bool:
        return self.classification is not OutdoorClassification.UNCLASSIFIED_REMAINDER


# ---------------------------------------------------------------- slicing tree

class Cut(str, Enum):
    V = "V"  # vertical cut line -> children side by side (share the node's height)
    H = "H"  # horizontal cut line -> children stacked (share the node's width)


@dataclass(frozen=True)
class Leaf:
    zone_id: str


@dataclass(frozen=True)
class Split:
    cut: Cut
    first: "Node"   # V: left, H: top
    second: "Node"  # V: right, H: bottom
    # Forced cut position, in units from the node's own origin. Needed where an archetype
    # dictates a boundary — an L wing seam must align with a leaf boundary, not fall wherever
    # the dimensioner likes.
    fixed_at_u: int | None = None


Node = Leaf | Split


def leaves_of(node: Node) -> list[str]:
    if isinstance(node, Leaf):
        return [node.zone_id]
    return leaves_of(node.first) + leaves_of(node.second)


# ---------------------------------------------------------------- fixture

@dataclass(frozen=True)
class Wing:
    """One rectangular wing of the footprint, with its own slicing tree."""

    wing_id: str
    origin_x_u: int
    origin_y_u: int
    w_u: int
    h_u: int
    tree: Node
    # Declared by the footprint archetype (L-A): leaf sides that abut ANOTHER wing rather than
    # the outside world. Known before geometry, and verified against the solved geometry by
    # proof P9 — so the "wall types are structural" claim stays honest.
    seam_leaf_sides: tuple[tuple[str, "Side"], ...] = ()

    def rect(self) -> Rect:
        return Rect(self.origin_x_u, self.origin_y_u, self.w_u, self.h_u)


@dataclass(frozen=True)
class Fixture:
    name: str
    wings: tuple[Wing, ...]
    zones: tuple[ZoneSpec, ...]
    access: DesiredAccessTopology
    open_groups: tuple[tuple[str, ...], ...] = ()
    outdoor: tuple[OutdoorRegion, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Fable review §2 patch 2: a safe room's boundary must ALWAYS be a sealed RC wall,
        never an open connection -- that is a hard domain invariant, not a solver choice.
        Reject it here, at construction, with a diagnostic that names the actual conflict.
        Previously this could only be discovered indirectly, later, as a confusing P6
        'not RC on all sides: ...=OPEN' proof failure that never explained why."""
        safe_room_ids = {z.zone_id for z in self.zones if z.is_safe_room}
        for group in self.open_groups:
            conflict = safe_room_ids & set(group)
            if conflict:
                raise ValueError(
                    f"SAFE_ROOM zone(s) {sorted(conflict)} cannot be members of open_group "
                    f"{group}: a safe room's wall must always be sealed RC construction, never "
                    f"an open (wall-less) connection. Remove the safe room from this "
                    f"open_groups entry, or reconsider whether it should be a safe room."
                )

    def zone(self, zone_id: str) -> ZoneSpec:
        for z in self.zones:
            if z.zone_id == zone_id:
                return z
        raise KeyError(zone_id)

    def open_group_of(self, zone_id: str) -> tuple[str, ...] | None:
        for g in self.open_groups:
            if zone_id in g:
                return g
        return None

    def footprint_area_m2(self) -> float:
        return round(sum(w.w_u * w.h_u for w in self.wings) * UNIT_M * UNIT_M, 4)
