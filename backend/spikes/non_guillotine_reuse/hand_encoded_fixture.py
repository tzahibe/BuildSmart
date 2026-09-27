"""Hand-encoded, genuinely non-guillotine room layout — Issue #108 (Architecture B reuse spike,
Issue #102's report §4.B). See docs/reports/non-rectangular-geometry-architecture-b-spike.md.

Archetype chosen: `l-3br-corner` (docs/architecture_reference/references/index.json, `footprint_
family: "L"`) — "3-bedroom L-shape, corner plot... two-wing L on a corner plot; bedrooms in their
own arm, entry court formed by the L." That entry is `rights: metadata-only` with `files: []`: by
the collection's own schema (Issue #30) it carries no per-room geometry at all (confirmed in
docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md §3.3 — "UNKNOWN by design, not by omission"). This
module hand-authors a layout consistent with the archetype's own description, not copied from any
source file.

THE LAYOUT, not solver-generated:
`app.vertical_slice.geometry_core.engine.solve_fixture` is never called anywhere in this module —
every `Rect` below is authored by hand. The 5-room core (LIVING/KITCHEN/HALL/MASTER_BEDROOM/
GALLERY) is the textbook minimal non-guillotine rectangular dissection — a "pinwheel"/"windmill"
tiling, five rectangles exactly covering a rectangle with no straight full-span cut avoiding all
five rooms' interiors (see `test_non_guillotine_reuse_spike.py::test_fixture_layout_is_genuinely_
non_guillotine`, which proves this with the SAME `is_guillotine_separable` recognition function
`measure_real_plan_shapes.py` uses). A 4-room bedroom arm (BED2/BED3/BATH1/BATH2) is attached as a
second wing, exactly tiling its own rectangle, forming an L envelope whose crook is the archetype's
"entry court formed by the L".

Coordinates are hand-picked, not computed: every boundary is a multiple of 0.05 m (`UNIT_M`, the
Geometry Core's own grid), every net dimension (after wall insets) was checked by hand against the
REAL `ROOM_TEMPLATES` table (`app.vertical_slice.concept_generator`) before being committed here,
and the wing/room tiling was verified to have zero gap and zero overlap (also asserted by the test
file, independent of the guillotine test).
"""
from __future__ import annotations

from app.vertical_slice.footprint import remainder_within_bbox
from app.vertical_slice.geometry_core.engine import WallMap
from app.vertical_slice.geometry_core.model import (
    ConnectionKind,
    DesiredAccessEdge,
    DesiredAccessTopology,
    Fixture,
    Leaf,
    OutdoorClassification,
    OutdoorRegion,
    ProgramRole,
    Rect,
    Side,
    WallType,
    Wing,
    ZoneSpec,
    m_to_u,
)
from app.vertical_slice.site import EntranceWalk, SitePlan, build_entrance
from app.vertical_slice.spec import WetRoomKind, WetRoomStrength
from app.vertical_slice.wet_rooms import ResolvedWetRoom

#: Front/side setbacks applied only so the entrance walk and plot are non-degenerate — not part
#: of the reuse question this spike asks. (metres)
OFFSET_X_M = 2.0
OFFSET_Y_M = 3.0
PLOT_MARGIN_SIDE_M = 2.0
PLOT_MARGIN_REAR_M = 2.0

#: Room rectangles, LOCAL to the footprint's own (0, 0) origin — (x, y, w, h) in metres.
#: y = 0 is the street-facing edge (`site.py`'s own convention: "y=0 at the street edge").
#:
#: The five WING_MAIN rooms form the pinwheel/windmill: LIVING (bottom band), KITCHEN (left
#: band), MASTER_BEDROOM (top band), GALLERY (right band), HALL (the surrounded centre) — see the
#: module docstring. The four WING_BED rooms are a simple attached 2x2 grid (BED2/BED3 one
#: column, BATH1/BATH2 the other), which on its own would be guillotine-separable — the whole
#: fixture is non-guillotine only because it CONTAINS the pinwheel, which the AC-1 test proves
#: directly (not merely inferred from this comment).
ROOM_RECTS_LOCAL_M: dict[str, tuple[float, float, float, float]] = {
    "LIVING":         (0.0, 0.0, 5.6, 3.4),
    "KITCHEN":        (0.0, 3.4, 3.6, 6.4),
    "HALL":           (3.6, 3.4, 2.0, 3.1),
    "MASTER_BEDROOM": (3.6, 6.5, 5.8, 3.3),
    "GALLERY":        (5.6, 0.0, 3.8, 6.5),
    "BED2":           (9.4, 0.0, 3.2, 3.25),
    "BED3":           (9.4, 3.25, 3.2, 3.25),
    "BATH1":          (12.6, 0.0, 2.8, 3.25),
    "BATH2":          (12.6, 3.25, 2.8, 3.25),
}

ROOM_ROLES: dict[str, tuple[ProgramRole, ...]] = {
    "LIVING": (ProgramRole.LIVING,),
    "KITCHEN": (ProgramRole.KITCHEN,),
    "HALL": (ProgramRole.HALL,),
    "MASTER_BEDROOM": (ProgramRole.MASTER_BEDROOM,),
    #: The pinwheel's 4th arm: a circulation gallery, not a public room — this is what lets the
    #: bedroom wing (physically reachable only across this room's seam wall) be entered from
    #: circulation rather than from a public room, per `access_rules.ALLOWED_ENTERED_FROM`.
    "GALLERY": (ProgramRole.CIRCULATION,),
    "BED2": (ProgramRole.BEDROOM,),
    "BED3": (ProgramRole.BEDROOM,),
    "BATH1": (ProgramRole.BATHROOM,),
    "BATH2": (ProgramRole.BATHROOM,),
}

#: Net-area ZoneSpec bounds — copied from `ROOM_TEMPLATES` (`concept_generator.py`) for every role
#: that has an entry there; GALLERY (CIRCULATION) copies HALL's row, the same way the production
#: hub carries HALL's template today.  (min, target, max, min_short_side, max_aspect_ratio)
ZONE_SPEC_BOUNDS: dict[str, tuple[float, float, float, float, float]] = {
    "LIVING": (16.0, 22.0, 46.0, 3.0, 2.5),
    "KITCHEN": (9.0, 13.0, 26.0, 2.4, 3.0),
    "HALL": (5.0, 11.0, 30.0, 1.2, 8.0),
    "MASTER_BEDROOM": (11.0, 14.0, 20.0, 3.0, 2.5),
    "GALLERY": (5.0, 11.0, 30.0, 1.2, 8.0),
    "BED2": (9.0, 10.5, 14.0, 2.6, 2.5),
    "BED3": (9.0, 10.5, 14.0, 2.6, 2.5),
    "BATH1": (4.5, 6.5, 12.0, 1.6, 3.0),
    "BATH2": (4.5, 6.5, 12.0, 1.6, 3.0),
}

#: (wing_id, origin_local_m, size_m) — WING_MAIN is the pinwheel's bounding box, WING_BED the
#: bedroom arm's. Local to the same (0, 0) origin as ROOM_RECTS_LOCAL_M.
WING_RECTS_LOCAL_M: dict[str, tuple[float, float, float, float]] = {
    "WING_MAIN": (0.0, 0.0, 9.4, 9.8),
    "WING_BED": (9.4, 0.0, 6.0, 6.5),
}

WING_ZONES: dict[str, tuple[str, ...]] = {
    "WING_MAIN": ("LIVING", "KITCHEN", "HALL", "MASTER_BEDROOM", "GALLERY"),
    "WING_BED": ("BED2", "BED3", "BATH1", "BATH2"),
}

#: Declared wing-seam sides (C22) — the ONE boundary where WING_BED abuts WING_MAIN: GALLERY's E
#: side (full height of WING_BED) meets BED2's and BED3's W sides.
SEAM_LEAF_SIDES: dict[str, tuple[tuple[str, Side], ...]] = {
    "WING_MAIN": (("GALLERY", Side.E),),
    "WING_BED": (("BED2", Side.W), ("BED3", Side.W)),
}

#: (a, b, kind) — every edge is a plain DOOR; see the spike report for why (this fixture
#: deliberately avoids `open_groups`/`WallType.OPEN`, orthogonal to the reuse question).
ACCESS_EDGES: tuple[tuple[str, str, ConnectionKind], ...] = (
    ("LIVING", "HALL", ConnectionKind.DOOR),
    ("HALL", "KITCHEN", ConnectionKind.DOOR),
    ("HALL", "MASTER_BEDROOM", ConnectionKind.DOOR),
    ("LIVING", "GALLERY", ConnectionKind.DOOR),
    ("GALLERY", "BED2", ConnectionKind.DOOR),
    ("GALLERY", "BED3", ConnectionKind.DOOR),
    ("BED2", "BATH1", ConnectionKind.DOOR),
    ("BED3", "BATH2", ConnectionKind.DOOR),
)

#: Entrance door position, LOCAL x — the midpoint of GALLERY's street-facing frontage. Not
#: LIVING's: `doors.ENTRANCE_ZONE_PRIORITY` ranks CIRCULATION above LIVING, and GALLERY (role
#: CIRCULATION) also fronts the street here, so `doors.resolve_entrance` picks GALLERY. This
#: constant is set to match that real, unchanged `doors.py` policy — not the other way around.
ENTRANCE_LOCAL_X_M = 7.5


def room_rects_m() -> dict[str, tuple[float, float, float, float]]:
    """Room rectangles in ABSOLUTE metres (after the front/side setback offset)."""
    return {
        zone_id: (x + OFFSET_X_M, y + OFFSET_Y_M, w, h)
        for zone_id, (x, y, w, h) in ROOM_RECTS_LOCAL_M.items()
    }


def build_rects() -> dict[str, Rect]:
    """The hand-encoded `dict[str, Rect]` this whole spike is about — grid units, absolute."""
    return {
        zone_id: Rect(m_to_u(x), m_to_u(y), m_to_u(w), m_to_u(h))
        for zone_id, (x, y, w, h) in room_rects_m().items()
    }


def build_wing_rects() -> dict[str, Rect]:
    return {
        wing_id: Rect(m_to_u(x + OFFSET_X_M), m_to_u(y + OFFSET_Y_M), m_to_u(w), m_to_u(h))
        for wing_id, (x, y, w, h) in WING_RECTS_LOCAL_M.items()
    }


def _side_between(a: Rect, b: Rect) -> Side | None:
    if a.x2 == b.x:
        return Side.E
    if b.x2 == a.x:
        return Side.W
    if a.y2 == b.y:
        return Side.S
    if b.y2 == a.y:
        return Side.N
    return None


def build_walls(rects: dict[str, Rect]) -> WallMap:
    """PARTITION where another room's rect touches this side, EXTERIOR otherwise — derived
    purely from rectangle adjacency (the same geometric fact `assign()` would have encoded, had
    a slicing tree produced this layout). No RC_SAFE_ROOM/OPEN in this fixture."""
    walls: WallMap = {}
    for zone_id, rect in rects.items():
        touching_sides = {
            _side_between(rect, other)
            for other_id, other in rects.items()
            if other_id != zone_id and rect.shared_edge_len_u(other) > 0
        }
        for side in Side:
            walls[(zone_id, side)] = WallType.PARTITION if side in touching_sides else WallType.EXTERIOR
    return walls


def build_fixture() -> Fixture:
    wing_rects_local = {
        wing_id: (m_to_u(x), m_to_u(y), m_to_u(w), m_to_u(h))
        for wing_id, (x, y, w, h) in WING_RECTS_LOCAL_M.items()
    }
    wings = tuple(
        Wing(
            wing_id=wing_id,
            origin_x_u=ox + m_to_u(OFFSET_X_M),
            origin_y_u=oy + m_to_u(OFFSET_Y_M),
            w_u=w,
            h_u=h,
            # The tree's SHAPE is never used — `solve_fixture`/`assign()` are never called on this
            # fixture — but `Wing.tree` is a non-optional field, and `leaves_of(wing.tree)` (used
            # by C22's wing-of-zone membership map, `validation.py::_seam_defects`) must return
            # the CORRECT zone-id set for this wing. A left-leaning `Leaf` chain does that without
            # asserting a cut order that was never used to produce these rects.
            tree=_leaf_chain(WING_ZONES[wing_id]),
            seam_leaf_sides=SEAM_LEAF_SIDES[wing_id],
        )
        for wing_id, (ox, oy, w, h) in wing_rects_local.items()
    )
    zones = tuple(
        ZoneSpec(
            zone_id=zone_id,
            roles=ROOM_ROLES[zone_id],
            net_area_min_m2=ZONE_SPEC_BOUNDS[zone_id][0],
            net_area_target_m2=ZONE_SPEC_BOUNDS[zone_id][1],
            net_area_max_m2=ZONE_SPEC_BOUNDS[zone_id][2],
            min_short_side_m=ZONE_SPEC_BOUNDS[zone_id][3],
            max_aspect_ratio=ZONE_SPEC_BOUNDS[zone_id][4],
        )
        for zone_id in ROOM_RECTS_LOCAL_M
    )
    access = DesiredAccessTopology(tuple(
        DesiredAccessEdge(a, b, kind) for a, b, kind in ACCESS_EDGES
    ))
    return Fixture("L_3BR_CORNER_HAND_ENCODED", wings, zones, access)


def _leaf_chain(zone_ids: tuple[str, ...]):
    from app.vertical_slice.geometry_core.model import Cut, Split
    node = Leaf(zone_ids[-1])
    for zone_id in reversed(zone_ids[:-1]):
        node = Split(Cut.V, Leaf(zone_id), node, None)
    return node


def build_wet_rooms() -> tuple[ResolvedWetRoom, ...]:
    """BATH1/BATH2 as this fixture's own `DesiredAccessTopology` actually built them: each an
    ensuite entered only from its own bedroom (BED2/BED3 respectively) — matching `ACCESS_EDGES`
    above, not the production resolver's `BATH_n` naming (which would not match this fixture's
    own zone ids)."""
    return (
        ResolvedWetRoom("BATH1", WetRoomKind.ENSUITE, "BED2", WetRoomStrength.REQUIRED, True),
        ResolvedWetRoom("BATH2", WetRoomKind.ENSUITE, "BED3", WetRoomStrength.REQUIRED, True),
    )


def build_site_plan(wing_rects: dict[str, Rect]) -> SitePlan:
    footprint = Rect(
        m_to_u(OFFSET_X_M), m_to_u(OFFSET_Y_M),
        m_to_u(WING_RECTS_LOCAL_M["WING_MAIN"][2] + WING_RECTS_LOCAL_M["WING_BED"][2]),
        m_to_u(WING_RECTS_LOCAL_M["WING_MAIN"][3]),
    )
    plot = Rect(
        0, 0,
        footprint.x2 + m_to_u(PLOT_MARGIN_SIDE_M),
        footprint.y2 + m_to_u(PLOT_MARGIN_REAR_M),
    )
    wings = (wing_rects["WING_MAIN"], wing_rects["WING_BED"])
    entrance_x_u = m_to_u(OFFSET_X_M + ENTRANCE_LOCAL_X_M)
    entrance = build_entrance(footprint, entrance_x_u)
    crook = [r for r in remainder_within_bbox(wings) if r.w > 0 and r.h > 0]
    garden = tuple(
        OutdoorRegion(f"garden_{i}", (r,), OutdoorClassification.GARDEN)
        for i, r in enumerate(crook)
    )
    return SitePlan(
        plot=plot, footprint=footprint, footprint_offset_u=(0, 0), parking=(),
        entrance=entrance, garden=garden, wings=wings,
    )
