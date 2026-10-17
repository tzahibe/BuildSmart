"""#205 — the front door's room is a room, not a strip: the "foyer" constraint group in the three
exact oracles (band `milp_heights`, spine `_spine_once`, cells `milp_cells`).

THE DEFECT THESE PIN. #204 measured the street-fronting exact placements: the foyers that passed
the validators were strips (B08: 1.50 x 3.05 m net — the band oracle knew nothing about the arrival
room, and the spine/cells oracles knew only that it is three door widths wide), and the ones that
failed did so on circulation geometry (C25 a 4.15 m pocket, C28 two leaves in a 1.6 m-deep foyer).
The group below holds the fronting single-row circulation cell to the swing geometry C28 measures
and to a lobby's proportion; `_skip={"foyer"}` reproduces the previous sizing exactly.
"""
import pytest

pytest.importorskip("scipy")

from app.vertical_slice.band_sizing import contact_requirements
from app.vertical_slice.envelope import Envelope
from app.vertical_slice.exact.cells import CellLayout
from app.vertical_slice.exact.milp_cells import cells_placement, cells_rects
from app.vertical_slice.exact.milp_oracle import (
    FOYER_MAX_DEPTH_TO_WIDTH,
    FOYER_MIN_NET_M,
    milp_placement,
    milp_spine_placement,
    spine_geometry,
)
from app.vertical_slice.exact.spine import SpineLayout
from app.vertical_slice.geometry_core.model import ProgramRole as R, WallType, inset_u, u_to_m
from app.vertical_slice.stage2.contract import ZoneIntent

ENV = Envelope.rectangle(14, 11)


def _z(i, role, t, lo, hi, ss=2.4, asp=2.5):
    return ZoneIntent(zone_id=i, role=role, donor_room_id=None, target_area_m2=t, min_area_m2=lo,
                      max_area_m2=hi, min_short_side_m=ss, max_aspect_ratio=asp)


def _programme(*ids):
    """A foyer parti: ENTRY (the brain's own foyer intent — CIRCULATION, 3.5–9 m², short side 1.5,
    aspect 2.5) fronting the street between the living room and the kitchen, a hub hall behind it."""
    zones = {"ENTRY": _z("ENTRY", R.CIRCULATION, 5, 3.5, 9, 1.5, 2.5),
             "LIVING": _z("LIVING", R.LIVING, 28, 22, 36, 3.0, 2.0),
             "KITCHEN": _z("KITCHEN", R.KITCHEN, 12, 10, 16, 2.4, 2.5),
             "HALL": _z("HALL", R.HALL, 10, 6, 16, 1.6, 3.0),
             "BED1": _z("BED1", R.BEDROOM, 12, 10, 15, 2.6, 1.8),
             "BED2": _z("BED2", R.BEDROOM, 12, 10, 15, 2.6, 1.8),
             "BED3": _z("BED3", R.BEDROOM, 12, 10, 15, 2.6, 1.8),
             "MASTER": _z("MASTER", R.MASTER_BEDROOM, 15, 13, 19, 3.0, 1.8),
             "BATH": _z("BATH", R.BATHROOM, 5, 4, 7, 1.6, 2.2)}
    zones = {z: zones[z] for z in ids}
    edges = [("ENTRY", "LIVING"), ("ENTRY", "KITCHEN"), ("ENTRY", "HALL"), ("HALL", "LIVING"),
             ("HALL", "BED1"), ("HALL", "BED2"), ("HALL", "BED3"), ("HALL", "MASTER"), ("HALL", "BATH")]
    required = [e for e in edges if e[0] in zones and e[1] in zones]
    access = [e for e in required if e != ("ENTRY", "LIVING")]
    union = sorted({tuple(sorted(e)) for e in required} | {tuple(sorted(e)) for e in access})
    return zones, union, contact_requirements(zones, union, access)


def _net(rect, first_in_band: bool, last_in_band: bool):
    """The cell's net width/depth as the realizer insets a street-band cell: exterior north, a
    partition south, exterior on a band end."""
    ext, part = inset_u(WallType.EXTERIOR), inset_u(WallType.PARTITION)
    iw = (ext if first_in_band else part) + (ext if last_in_band else part)
    return u_to_m(rect.w - iw), u_to_m(rect.h - ext - part)


def _assert_room_not_strip(net_w, net_h):
    assert net_w >= FOYER_MIN_NET_M - 1e-9, net_w
    assert net_h >= FOYER_MIN_NET_M - 1e-9, net_h
    assert net_h <= FOYER_MAX_DEPTH_TO_WIDTH * net_w + 1e-9, (net_w, net_h)
    assert net_h > net_w, (net_w, net_h)            # the foyer proper: its long axis is the door axis (C26)


# ----------------------------------------------------------------------- the band oracle

BANDS = (("LIVING", "ENTRY", "KITCHEN"), ("BED1", "HALL", "BED2"), ("BATH", "MASTER"))
#: the band oracle's sizing of the case BEFORE this group existed (origin/main b460a42, the same
#: solver): the foyer came out 1.60 x 3.75 m gross — a 1.5 x 3.55 m net slot entered lengthwise
BAND_BEFORE = ((75, 62, 64), ((0, 128, 160, 232), (0, 87, 150, 232), (87, 124, 232)))


def test_a_fronting_foyer_in_the_band_family_is_never_a_strip():
    zones, union, con = _programme("ENTRY", "LIVING", "KITCHEN", "HALL", "BED1", "BED2", "MASTER", "BATH")
    o = milp_placement(BANDS, zones, union, ENV, min_contact_u=con, objective="target")
    assert o.status == "FEASIBLE", o.detail
    rect = o.as_sizing().rects(BANDS)["ENTRY"]
    _assert_room_not_strip(*_net(rect, False, False))


def test_skipping_the_group_reproduces_the_previous_band_sizing_exactly():
    zones, union, con = _programme("ENTRY", "LIVING", "KITCHEN", "HALL", "BED1", "BED2", "MASTER", "BATH")
    o = milp_placement(BANDS, zones, union, ENV, min_contact_u=con, objective="target", _skip=frozenset({"foyer"}))
    assert o.status == "FEASIBLE", o.detail
    assert (o.heights_u, o.band_x_u) == BAND_BEFORE
    net_w, net_h = _net(o.as_sizing().rects(BANDS)["ENTRY"], False, False)
    assert net_w < FOYER_MIN_NET_M and net_h > FOYER_MAX_DEPTH_TO_WIDTH * net_w     # the strip, as it was


# ---------------------------------------------------------------------- the spine oracle

SPINE = SpineLayout("HALL", ((("BED1",), ("BED2",)), (("MASTER",), ("BED3",))), top=(("LIVING", "ENTRY", "KITCHEN"),))
#: before (b460a42): the same 1.5 x 3.55 m net slot — the spine oracle's entrance rule reaches
#: only the spine itself, never a foyer in the plain band above it
SPINE_BEFORE = ((75, 60, 64), ((46, 174, 206, 280), (46, 152, 196, 280), (46, 152, 196, 280)))


def test_a_fronting_foyer_beside_a_spine_section_is_never_a_strip():
    zones, union, con = _programme("ENTRY", "LIVING", "KITCHEN", "HALL", "BED1", "BED2", "BED3", "MASTER")
    o = milp_spine_placement(SPINE, zones, union, ENV, min_contact_u=con, objective="target")
    assert o.status == "FEASIBLE", o.detail
    rects, _ = spine_geometry(SPINE, o)
    _assert_room_not_strip(*_net(rects["ENTRY"], False, False))
    skipped = milp_spine_placement(SPINE, zones, union, ENV, min_contact_u=con, objective="target",
                                   _skip=frozenset({"foyer"}))
    assert skipped.status == "FEASIBLE"
    assert (skipped.heights_u, skipped.band_x_u) == SPINE_BEFORE
    net_w, net_h = _net(spine_geometry(SPINE, skipped)[0]["ENTRY"], False, False)
    assert net_w < FOYER_MIN_NET_M and net_h > FOYER_MAX_DEPTH_TO_WIDTH * net_w     # without it, a strip


# ---------------------------------------------------------------------- the cells oracle

CELLS = CellLayout((("LIVING", "ENTRY", "KITCHEN"), ("BED1", "HALL", "BED2"), ("MASTER", "HALL", "BED3")))
#: before (b460a42). The cells oracle's own entrance rule (three door widths on the street band's
#: circulation cell) already makes this foyer 2.9 m wide — so wide that with the foyer's 9 m2
#: ceiling and a living room 3.3 m deep the case is INFEASIBLE; this fixture gives the foyer 10 m2
#: and a smaller living room to have a sizing at all. What the group adds in this family is the
#: depth floor (#204's failing cells foyers were 1.6 m deep, in the V orientation), which this
#: case does not exercise; the pin shows the group costs the old sizing nothing.
CELLS_BEFORE = ((71, 54, 64), {"LIVING": (23, 147), "ENTRY": (147, 207), "KITCHEN": (207, 271), "BED1": (23, 120),
                               "HALL": (120, 174), "BED2": (174, 271), "MASTER": (23, 120), "BED3": (174, 271)})


def _cells_programme():
    zones, union, con = _programme("ENTRY", "LIVING", "KITCHEN", "HALL", "BED1", "BED2", "BED3", "MASTER")
    zones = {**zones, "LIVING": _z("LIVING", R.LIVING, 24, 20, 30, 3.0, 2.5),
             "ENTRY": _z("ENTRY", R.CIRCULATION, 5, 3.5, 10, 1.5, 2.5)}
    return zones, union, con


def test_a_fronting_foyer_in_a_cell_layout_is_never_a_strip():
    zones, union, con = _cells_programme()
    o = cells_placement(CELLS, zones, union, ENV, min_contact_u=con, objective="target", k=12)
    assert o.status == "FEASIBLE", o.detail
    _assert_room_not_strip(*_net(cells_rects(CELLS, o)["ENTRY"], False, False))
    skipped = cells_placement(CELLS, zones, union, ENV, min_contact_u=con, objective="target", k=12,
                              _skip=frozenset({"foyer"}))
    assert skipped.status == "FEASIBLE"
    assert (skipped.heights_u, skipped.x_u) == CELLS_BEFORE


def test_the_constants_are_the_door_swings_and_the_compact_hall_threshold():
    """Not invented numbers: the two leaves C28 measures (`access_rules.DOOR_WIDTH_M`) and the
    production threshold below which a hall reads as a lobby rather than a spine."""
    from app.vertical_slice.access_rules import DOOR_WIDTH_M, DoorKind
    from app.vertical_slice.concept_spec import _COMPACT_HALL_ASPECT_MAX
    assert FOYER_MIN_NET_M == DOOR_WIDTH_M[DoorKind.ENTRANCE_DOOR] + DOOR_WIDTH_M[DoorKind.ROOM_DOOR]
    assert FOYER_MAX_DEPTH_TO_WIDTH == _COMPACT_HALL_ASPECT_MAX
