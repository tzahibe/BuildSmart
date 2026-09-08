"""Stage 2 — Concept / DesiredAccessTopology.

Turns an `ArchitecturalSpec` into exactly ONE `geometry_core.model.Fixture` (one candidate,
no scoring, no diversity — per the vertical-slice scope). This is where the slicing tree,
zone program, and desired access edges are authored, using ONLY the frozen Geometry Core's own
types (`Cut`/`Leaf`/`Split`/`Wing`/`Fixture`/`ZoneSpec`/`DesiredAccessTopology`) — no new domain
concepts are introduced here, matching "no new domain-model research".

The tree reuses the exact patterns the geometry-core spike proved, scaled to this program:
  - LIVING/DINING/KITCHEN stacked front-to-back as one open group (proven by F3/F4).
  - A two-segment HALL (HALL_MAIN/HALL_SPUR) as one open circulation group, so it reaches
    every private room without being a single spanning strip (proven by F4 — this is the
    direct, deliberate reuse of the branching-hall pattern the review's L1 finding required).
  - MASTER + ensuite BATH_1 as a suite reachable from HALL_MAIN; BEDROOM_1/SAFE_ROOM/
    BEDROOM_2/BATH_2 stacked as a full-width chain reachable from HALL_SPUR (proven by F4's
    "both touch hall_spur" stacking trick).
  - SAFE_ROOM is a standalone room here (not dual-role with a bedroom), sized to the
    regulation-placeholder minimum only — simpler than F3's dual-role case and avoids
    re-triggering the furniture-envelope tightness the review's patch 4 found there.

Every split is a forced cut (`fixed_m`), so the resulting geometry is fully deterministic and
was hand-verified against the engine before being committed here (see
`backend/tests/vertical_slice/test_concept.py`).
"""
from __future__ import annotations

from dataclasses import dataclass

from .geometry_core.model import (
    ConnectionKind,
    Cut,
    DesiredAccessEdge,
    DesiredAccessTopology,
    Fixture,
    Leaf,
    ProgramRole,
    Side,
    Split,
    Wing,
    ZoneSpec,
    m_to_u,
)
from .spec import ArchitecturalSpec


def _z(zid: str, roles: tuple[ProgramRole, ...], lo: float, target: float, hi: float,
       short: float, aspect: float = 2.5) -> ZoneSpec:
    return ZoneSpec(zid, roles, lo, target, hi, short, aspect)


def _v(a, b, fixed_m: float) -> Split:
    return Split(Cut.V, a, b, m_to_u(fixed_m))


def _h(a, b, fixed_m: float | None) -> Split:
    return Split(Cut.H, a, b, m_to_u(fixed_m) if fixed_m is not None else None)


L = Leaf

# Footprint size this concept is authored for (m). `site.py` places this rectangle inside the
# plot's buildable envelope; it does not resize it — resizing the concept to fit an arbitrary
# plot is future work (see README "known limitations"), not attempted here.
FOOTPRINT_WIDTH_M = 12.0
FOOTPRINT_DEPTH_M = 14.2  # 3.8 (master suite) + 10.4 (back chain) — 10.4 clears back_chain's
# measured 10.3 m minimum feasible depth for BEDROOM_1/SAFE_ROOM/BEDROOM_2/BATH_2 stacked; 14.0
# undershot it by 0.1 m and made the concept infeasible (caught by running it, not by hand-math).

# Street-facing side of the wing, in the wing's OWN (0,0)-origin coordinate frame. y=0 is the
# street edge — `site.py` places the wing so this side ends up on the building line.
STREET_SIDE = Side.N

ENTRANCE_ZONE_ID = "HALL_MAIN"


@dataclass(frozen=True)
class Concept:
    fixture: Fixture
    entrance_zone_id: str
    street_side: Side
    footprint_width_m: float
    footprint_depth_m: float


def build_concept(spec: ArchitecturalSpec) -> Concept:
    if not (spec.program.bedrooms == 3 and spec.program.safe_room and spec.program.wet_rooms == 2):
        raise NotImplementedError(
            "This vertical slice's concept is hand-authored for exactly 3 bedrooms + 1 safe "
            "room + 2 wet rooms (the frozen demo scenario) — a general concept generator for "
            "arbitrary programs is out of scope (see README 'known limitations')."
        )

    zones = (
        _z("LIVING", (ProgramRole.LIVING,), 18, 21, 27, 3.0),
        _z("DINING", (ProgramRole.DINING,), 16, 19, 24, 2.8, aspect=3.0),
        _z("KITCHEN", (ProgramRole.KITCHEN,), 16, 19, 24, 2.8, aspect=3.0),
        _z("HALL_MAIN", (ProgramRole.HALL, ProgramRole.CIRCULATION), 4, 5.5, 8, 1.2, aspect=8.0),
        _z("HALL_SPUR", (ProgramRole.HALL, ProgramRole.CIRCULATION), 10, 13.5, 18, 1.2, aspect=8.0),
        _z("MASTER", (ProgramRole.MASTER_BEDROOM,), 12, 14.5, 19, 3.0),
        _z("BATH_1", (ProgramRole.BATHROOM,), 4, 5.5, 8, 1.6, aspect=3.0),
        _z("BEDROOM_1", (ProgramRole.BEDROOM,), 12, 14.5, 19, 2.8),
        _z("SAFE_ROOM", (ProgramRole.SAFE_ROOM,), 9.0, 10.5, 13.5, 2.4),
        _z("BEDROOM_2", (ProgramRole.BEDROOM,), 12, 14.5, 19, 2.8),
        _z("BATH_2", (ProgramRole.BATHROOM,), 6, 8, 11, 1.6, aspect=3.0),
    )

    ldk_block = _h(
        L("LIVING"),
        _h(L("DINING"), L("KITCHEN"), fixed_m=4.5),
        fixed_m=5.0,
    )
    # MUST equal rooms_col's own split below (3.45) — hall_col and rooms_col are separate
    # subtrees, so nothing else forces them to align. A mismatch here doesn't raise
    # GeometryInfeasible (both sides still tile); it silently gives HALL_MAIN a sliver of
    # undeclared, doorless contact with BEDROOM_1 instead of a clean 1:1 border with MASTER
    # only — caught by re-deriving neighbours from the solved rects, not by a proof failing.
    HALL_ROOMS_SPLIT_M = 3.45
    hall_col = _h(L("HALL_MAIN"), L("HALL_SPUR"), fixed_m=HALL_ROOMS_SPLIT_M)
    master_suite = _v(L("MASTER"), L("BATH_1"), fixed_m=3.8)
    # These three internal splits are deliberately UNFORCED: nothing outside back_chain needs
    # to align with them (unlike hall_col/rooms_col's shared split below), so the proven
    # target-ratio heuristic in `assign()` is left to pick a value it has already verified is
    # feasible — hand-forcing all four depths here previously produced two infeasible values
    # in a row (SAFE_ROOM's all-RC 0.30 m inset, then BEDROOM_2's own min-short-side floor),
    # both caught only by running the solver, not by hand arithmetic.
    back_chain = _h(
        L("BEDROOM_1"),
        _h(L("SAFE_ROOM"), _h(L("BEDROOM_2"), L("BATH_2"), fixed_m=None), fixed_m=None),
        fixed_m=None,
    )
    # 3.45, not 3.8: at the 5.7 m width this column is forced to, back_chain's own aspect-ratio
    # bound needs >=10.55 m of depth (measured, not assumed) — 3.8 left it only 10.4/10.2 and
    # was infeasible. master_suite is still comfortably feasible at 3.45 m (its floor is 3.4 m).
    rooms_col = _h(master_suite, back_chain, fixed_m=HALL_ROOMS_SPLIT_M)
    rest = _v(hall_col, rooms_col, fixed_m=1.6)
    tree = _v(ldk_block, rest, fixed_m=4.7)  # ldk_block width 4.7; rest width 7.3 = 1.6 (hall) + 5.7 (rooms)

    wing = Wing("W", 0, 0, m_to_u(FOOTPRINT_WIDTH_M), m_to_u(FOOTPRINT_DEPTH_M), tree)

    access = DesiredAccessTopology((
        DesiredAccessEdge("HALL_MAIN", "LIVING", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL_MAIN", "MASTER", ConnectionKind.DOOR),
        DesiredAccessEdge("MASTER", "BATH_1", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL_SPUR", "BEDROOM_1", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL_SPUR", "SAFE_ROOM", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL_SPUR", "BEDROOM_2", ConnectionKind.DOOR),
        DesiredAccessEdge("HALL_SPUR", "BATH_2", ConnectionKind.DOOR),
        DesiredAccessEdge("LIVING", "DINING", ConnectionKind.OPEN_CONNECTION),
        DesiredAccessEdge("DINING", "KITCHEN", ConnectionKind.OPEN_CONNECTION),
        DesiredAccessEdge("HALL_MAIN", "HALL_SPUR", ConnectionKind.OPEN_CONNECTION),
    ))

    fixture = Fixture(
        "V1_DEMO_HOUSE", (wing,), zones, access,
        open_groups=(("LIVING", "DINING", "KITCHEN"), ("HALL_MAIN", "HALL_SPUR")),
    )
    return Concept(fixture, ENTRANCE_ZONE_ID, STREET_SIDE, FOOTPRINT_WIDTH_M, FOOTPRINT_DEPTH_M)
