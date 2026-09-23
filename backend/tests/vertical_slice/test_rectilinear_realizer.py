"""Issue #117, Stage 1 (2/2) — THE GATE. AC-1 evidence: `realize_layout` produces, for a
hand-built layout fixture, real rectilinear polygons (an L and a U, via the notch-carve
construction) whose union equals the envelope with zero residual area and is genuinely
non-guillotine, and refuses an impossible layout with the failing constraint named.

See `app/vertical_slice/rectilinear_realizer.py`'s module docstring for the two constructions
under test (pinwheel, notch-carve) and `docs/reports/rectilinear-realizer/stage1-gate.md` for the
10-real-corpus-layout evidence (AC-2/AC-3).
"""
from __future__ import annotations

from shapely.geometry import Polygon

from app.vertical_slice.geometry_core.model import ProgramRole, Rect, u_to_m
from app.vertical_slice.rectilinear_realizer import (
    PinwheelWing,
    RealizationIntent,
    RealizedLayout,
    Refusal,
    RowWing,
    ShapeGroupIntent,
    ZoneIntent,
    realize_layout,
)
from spikes.geometry_shapes.measure_real_plan_shapes import is_guillotine_separable


def _zi(zone_id, role, target, lo, hi, min_short=1.8, max_aspect=2.5) -> ZoneIntent:
    return ZoneIntent(zone_id, role, target, lo, hi, min_short, max_aspect)


def _l_and_u_layout() -> RealizationIntent:
    """One wing, one row: an L-group and a U-group, each a `FLEX` "big" zone (Issue #102's own
    role, no furniture floor and a 500 m2 `ROOM_TEMPLATES` ceiling — see `concept_generator.
    ROOM_TEMPLATES[FLEX]`) with a small ordinary-role notch. FLEX is chosen deliberately so this
    fixture's job — proving the GEOMETRIC construction (real polygons, zero residual, genuinely
    non-guillotine, a real refusal) — is not entangled with an unrelated role's own furniture/
    hard-max tuning; AC-2/AC-3's real corpus layouts (`stage1_gate.py`) exercise real habitable
    roles instead."""
    l_group = ShapeGroupIntent(
        group_id="L_GROUP", family="L",
        big=_zi("FLEX_BIG_1", ProgramRole.FLEX, 30.0, 15.0, 60.0, 3.0, 3.0),
        notches=(_zi("FLEX_NOTCH_1", ProgramRole.FLEX, 4.0, 2.0, 8.0, 1.0, 3.0),),
        corner="NE",
    )
    u_group = ShapeGroupIntent(
        group_id="U_GROUP", family="U",
        big=_zi("FLEX_BIG_2", ProgramRole.FLEX, 24.0, 12.0, 60.0, 1.5, 4.0),
        notches=(_zi("FLEX_NOTCH_2", ProgramRole.FLEX, 3.0, 2.0, 6.0, 1.0, 3.0),),
        edge="N",
    )
    hall = _zi("HALL", ProgramRole.HALL, 8.0, 4.0, 12.0, 1.0, 4.0)
    wing = RowWing(
        wing_id="MAIN", width_m=15.0, height_m=6.5,
        slots=("HALL", "L_GROUP", "U_GROUP"),
        zones={"HALL": hall},
        groups={"L_GROUP": l_group, "U_GROUP": u_group},
    )
    return RealizationIntent(name="L_AND_U_HAND_BUILT", wings=(wing,))


def _impossible_layout() -> RealizationIntent:
    """LIVING's own target area (300 m2) cannot fit inside a 6x5 m envelope at any aspect — an
    honest, named refusal, not a silently shrunk room."""
    big = _zi("LIVING", ProgramRole.LIVING, 300.0, 250.0, 350.0, 3.0, 2.4)
    notch = _zi("STORAGE", ProgramRole.STORAGE, 3.0, 2.0, 5.0, 1.2, 3.0)
    group = ShapeGroupIntent(group_id="L_GROUP", family="L", big=big, notches=(notch,), corner="NE")
    wing = RowWing(wing_id="MAIN", width_m=6.0, height_m=5.0, slots=("L_GROUP",),
                    groups={"L_GROUP": group})
    return RealizationIntent(name="IMPOSSIBLE", wings=(wing,))


def _room_polygons_m(result: RealizedLayout) -> list[Polygon]:
    """Every DISPLAYED room's own true polygon — a notch-carve group's cells collapse into ONE
    polygon (its `MergedGeometry`), everything else is its own rectangle. Mirrors
    `test_non_guillotine_reuse_spike.py::_room_polygons_m`'s own pattern."""
    singles: dict[str, Rect] = {}
    for cell_id, zone_id in result.zone_of_cell.items():
        if cell_id == zone_id:
            singles[zone_id] = result.rects[cell_id]
    polys = []
    for zid, r in singles.items():
        x, y, w, h = u_to_m(r.x), u_to_m(r.y), u_to_m(r.w), u_to_m(r.h)
        polys.append(Polygon([(x, y), (x + w, y), (x + w, y + h), (x, y + h)]))
    for zid, geometry in result.groups.items():
        polys.append(Polygon(geometry.polygon_m))
    return polys


# --------------------------------------------------------------------------- AC-1

def test_l_and_u_layout_realizes_with_real_polygons():
    result = realize_layout(_l_and_u_layout())
    assert isinstance(result, RealizedLayout), result
    assert result.ok

    living_poly = Polygon(result.groups["FLEX_BIG_1"].polygon_m)
    kitchen_poly = Polygon(result.groups["FLEX_BIG_2"].polygon_m)
    # A genuine corner-notch L has 6 vertices; a genuine edge-notch U has 8.
    assert len(living_poly.exterior.coords) - 1 == 6, living_poly.exterior.coords[:]
    assert len(kitchen_poly.exterior.coords) - 1 == 8, kitchen_poly.exterior.coords[:]
    assert result.report.ok
    assert result.c27.passed


def test_l_and_u_layout_union_equals_envelope_with_zero_residual_area():
    result = realize_layout(_l_and_u_layout())
    assert isinstance(result, RealizedLayout), result
    footprint = result.site.footprint
    covered_u = sum(r.w * r.h for r in result.rects.values())
    assert covered_u == footprint.w * footprint.h
    c2 = next(c for c in result.report.checks if c.check_id == "C2")
    assert c2.passed, c2.detail


def test_l_and_u_layout_is_genuinely_non_guillotine():
    """Proven with the SAME recognition function the investigation/spike #108 used (imported, not
    reimplemented) against every DISPLAYED room's real polygon."""
    result = realize_layout(_l_and_u_layout())
    assert isinstance(result, RealizedLayout), result
    assert is_guillotine_separable(_room_polygons_m(result)) is False


def test_impossible_layout_is_refused_with_the_failing_constraint_named():
    result = realize_layout(_impossible_layout())
    assert isinstance(result, Refusal), result
    assert result.constraint
    assert "300" in result.detail or "LIVING" in result.detail


# --------------------------------------------------------------------------- pinwheel construction

def _pinwheel_layout() -> RealizationIntent:
    """The same 5-room windmill topology spike #108 hand-encoded for the `l-3br-corner` archetype
    (docs/reports/non-rectangular-geometry-architecture-b-spike.md) — same envelope, same roles,
    same pinwheel structure (LIVING/GALLERY/MASTER_BEDROOM/KITCHEN wrapping a surrounded HALL) —
    with target areas re-balanced so the realized GALLERY+HALL pair clears C26's circulation-ratio
    threshold (#108's own hand-picked areas realize at 34%, over the 24% limit — a real, disclosed
    finding that spike's own report names in its §4, not gated there since #108 was not a
    realizer)."""
    wing = PinwheelWing(
        wing_id="MAIN", width_m=9.4, height_m=9.8,
        n=_zi("LIVING", ProgramRole.LIVING, 29.0, 16.0, 46.0, 3.0, 2.5),
        e=_zi("GALLERY", ProgramRole.CIRCULATION, 9.0, 5.0, 30.0, 1.2, 8.0),
        s=_zi("MASTER_BEDROOM", ProgramRole.MASTER_BEDROOM, 19.3, 11.0, 20.0, 3.0, 2.5),
        w=_zi("KITCHEN", ProgramRole.KITCHEN, 24.0, 9.0, 26.0, 2.4, 3.0),
        center=_zi("HALL", ProgramRole.HALL, 6.2, 5.0, 30.0, 1.2, 8.0),
    )
    return RealizationIntent(name="PINWHEEL_HAND_BUILT", wings=(wing,))


def test_pinwheel_layout_realizes_and_is_genuinely_non_guillotine():
    result = realize_layout(_pinwheel_layout())
    assert isinstance(result, RealizedLayout), result
    assert result.ok
    assert len(result.design.rooms) == 5
    assert is_guillotine_separable(_room_polygons_m(result)) is False


def test_pinwheel_two_arms_alone_are_guillotine_a_control():
    """Control, matching the investigation's own self-check discipline: any TWO of the pinwheel's
    own rooms, taken alone, are trivially guillotine-separable (a single cut along their own shared
    boundary always exists for a pair) — proving the FULL 5-room non-guillotine result above comes
    from HALL being surrounded on every side, not from an always-False recognition test."""
    result = realize_layout(_pinwheel_layout())
    assert isinstance(result, RealizedLayout), result
    pair = {k: v for k, v in result.rects.items() if k in ("LIVING", "KITCHEN")}
    polys = []
    for zid, r in pair.items():
        x, y, w, h = u_to_m(r.x), u_to_m(r.y), u_to_m(r.w), u_to_m(r.h)
        polys.append(Polygon([(x, y), (x + w, y), (x + w, y + h), (x, y + h)]))
    assert is_guillotine_separable(polys) is True
