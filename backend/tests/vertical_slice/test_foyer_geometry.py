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


# ------------------------------------------------------- the V orientation (#207): the street is the west edge
#
# `exact_pipeline` sizes every layout twice: as production orients it ("H") and on the TRANSPOSED
# envelope ("V"), transposing the rects back. In V the oracle's row 0 lands on the house's west side
# and the cells that front the street are each band's FIRST cell. #205 measured the street rules
# applied to the wrong cells there (every fronting V placement failed C25/C26/C28); `street="W"`
# tells each oracle which edge is the street. These pin, per oracle, that in the W frame the
# fronting foyer is sized to the group and holds the door after transposition — read off the
# REALIZED room, the way the preference reads it (`runner.arrival_usability`) — and what the
# N rule did to the same case.

from app.vertical_slice.brain.runner import arrival_usability
from app.vertical_slice.exact.screens import transpose_rects, transposed_envelope
from app.vertical_slice.rectilinear_realizer import RealizedLayout, realize_cells

ENV_V = transposed_envelope(ENV)          # the oracle's frame for the V orientation: 11 wide, 14 deep


def _v_programme():
    """A foyer beside the living room in the first band (a V band is a column of the house), a
    small study before the hub hall so the foyer's depth reaches the hall, and a kitchen and the
    master bedroom behind — enough habitable floor for C26's circulation share. Every contact is
    a door, so the foyer opens to the living room (C25) and every room has a way in (C24)."""
    zones = {"ENTRY": _z("ENTRY", R.CIRCULATION, 5, 3.5, 12, 1.5, 2.5),
             "LIVING": _z("LIVING", R.LIVING, 20, 16, 26, 3.0, 2.5),
             "HALL": _z("HALL", R.HALL, 6, 5, 9, 1.8, 3.0),
             "STUDY": _z("STUDY", R.STUDY, 6, 4, 8, 2.0, 2.0),
             "BED1": _z("BED1", R.BEDROOM, 12, 10, 15, 2.6, 1.8),
             "KITCHEN": _z("KITCHEN", R.KITCHEN, 12, 10, 16, 2.4, 2.5),
             "MASTER": _z("MASTER", R.MASTER_BEDROOM, 15, 13, 19, 3.0, 1.8)}
    required = [("ENTRY", "LIVING"), ("ENTRY", "HALL"), ("HALL", "STUDY"), ("HALL", "BED1"),
                ("HALL", "KITCHEN"), ("HALL", "MASTER")]
    access = list(required)
    union = sorted({tuple(sorted(e)) for e in required})
    return zones, union, access, contact_requirements(zones, union, access)


def _realized_v(name, rects, wings, zones, access):
    """What `exact_pipeline.realize` does for a V placement: transpose, then the unchanged realizer."""
    rects = transpose_rects(rects)
    wings = tuple(transpose_rects(dict(enumerate(wings))).values())
    return realize_cells(name, rects, zones, wings, access)


def _assert_v_foyer_holds_the_door(out, oracle_rect, band_start_u):
    assert isinstance(out, RealizedLayout), getattr(out, "detail", out)
    assert oracle_rect.x == band_start_u                         # first in its band: it fronts
    assert out.entrance_door.b == "ENTRY", out.entrance_door
    usable, (net_w, net_h) = arrival_usability(out)
    assert usable == 0, (net_w, net_h)
    _assert_room_not_strip(net_w, net_h)                         # frontage, depth, cap, deeper than wide
    assert out.ok, out.report


V_BANDS = (("ENTRY", "LIVING"), ("STUDY", "HALL", "BED1"), ("KITCHEN", "MASTER"))


def test_in_the_v_orientation_the_band_oracle_sizes_the_fronting_foyer_and_it_holds_the_door():
    zones, union, access, con = _v_programme()
    o = milp_placement(V_BANDS, zones, union, ENV_V, min_contact_u=con, objective="target", street="W")
    assert o.status == "FEASIBLE", o.detail
    sz = o.as_sizing()
    _assert_v_foyer_holds_the_door(_realized_v("v-band", sz.rects(V_BANDS), sz.band_rects(V_BANDS), zones, access),
                                   sz.rects(V_BANDS)["ENTRY"], o.band_x_u[0][0])
    # the N rule on the same case (what every V placement got before #207): the foyer's band
    # starts past the street line, nothing with an allowed role fronts it, no door can be placed
    old = milp_placement(V_BANDS, zones, union, ENV_V, min_contact_u=con, objective="target", street="N")
    assert old.status == "FEASIBLE", old.detail
    assert old.band_x_u[0][0] > min(x[0] for x in old.band_x_u)
    before = _realized_v("v-band-before", old.as_sizing().rects(V_BANDS), old.as_sizing().band_rects(V_BANDS), zones, access)
    assert not isinstance(before, RealizedLayout) and "fronts the street" in before.detail, before


V_SPINE = SpineLayout("HALL", ((("STUDY",), ("BED1",)),), top=(("ENTRY", "LIVING"),), bottom=(("KITCHEN", "MASTER"),))


def test_in_the_v_orientation_the_spine_oracle_sizes_the_fronting_foyer_and_it_holds_the_door():
    zones, union, access, con = _v_programme()
    o = milp_spine_placement(V_SPINE, zones, union, ENV_V, min_contact_u=con, objective="target", street="W")
    assert o.status == "FEASIBLE", o.detail
    rects, wings = spine_geometry(V_SPINE, o)
    _assert_v_foyer_holds_the_door(_realized_v("v-spine", rects, wings, zones, access), rects["ENTRY"], o.band_x_u[0][0])
    old = milp_spine_placement(V_SPINE, zones, union, ENV_V, min_contact_u=con, objective="target", street="N")
    assert old.status == "FEASIBLE", old.detail
    assert old.band_x_u[0][0] > min(x[0] for x in old.band_x_u)      # the foyer's band is off the street line
    before = _realized_v("v-spine-before", *spine_geometry(V_SPINE, old), zones, access)
    assert not isinstance(before, RealizedLayout) and "fronts the street" in before.detail, before


V_CELLS = CellLayout(V_BANDS)


def test_in_the_v_orientation_the_cells_oracle_sizes_the_fronting_foyer_and_it_holds_the_door():
    zones, union, access, con = _v_programme()
    o = cells_placement(V_CELLS, zones, union, ENV_V, min_contact_u=con, objective="target", k=12, street="W")
    assert o.status == "FEASIBLE", o.detail
    rects = cells_rects(V_CELLS, o)
    _assert_v_foyer_holds_the_door(_realized_v("v-cells", rects, tuple(rects.values()), zones, access),
                                   rects["ENTRY"], o.x_u["ENTRY"][0])
    # the N rule shaped this foyer for a NORTH street — deeper than wide in the oracle's frame —
    # which after transposition is a foyer WIDER along the street than deep: C26's shape
    old = cells_placement(V_CELLS, zones, union, ENV_V, min_contact_u=con, objective="target", k=12, street="N")
    assert old.status == "FEASIBLE", old.detail
    before = _realized_v("v-cells-before", cells_rects(V_CELLS, old), tuple(cells_rects(V_CELLS, old).values()), zones, access)
    if isinstance(before, RealizedLayout) and before.entrance_door.b == "ENTRY":
        _u, (w, h) = arrival_usability(before)
        assert w >= h, (w, h)


def test_the_oracles_refuse_an_unknown_street_side():
    zones, union, _access, con = _v_programme()
    for call in (lambda: milp_placement(V_BANDS, zones, union, ENV_V, min_contact_u=con, street="E"),
                 lambda: milp_spine_placement(V_SPINE, zones, union, ENV_V, min_contact_u=con, street="E"),
                 lambda: cells_placement(V_CELLS, zones, union, ENV_V, min_contact_u=con, street="E")):
        with pytest.raises(ValueError):
            call()
