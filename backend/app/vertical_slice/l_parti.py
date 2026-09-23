"""The L parti — exactly two connected rectangular wings with one declared seam.

    ┌──────────────────────┐
    │   public band        │  ← LIVING · DINING · KITCHEN across the primary's free end
    ├──────────────┬───────┤──────────────┐
    │ column beside│ HALL  │ bedroom wing │  ← the hall spans EXACTLY the seam; every arm room
    │ the hall     │ (seam)│ (the arm)    │    has a door from it across the seam
    └──────────────┴───────┴──────────────┘
      primary wing (candidate 0)             arm (candidate 1)

WHAT THIS IS. The spike's F2 L-house pattern, produced by the generator instead of by hand: the
primary wing is the FRONT-BAND structure `H(band, V(column, HALL))` with the hall pinned to the
seam by forced cuts — its length IS the arm's length, so no leaf side is part-exterior and
part-seam (the spike's L2 finding) — and the arm is a second `Wing` of stacked rows whose
seam-facing sides are declared in `seam_leaf_sides`. Geometry Core solves this today unchanged
(`test_footprint_wings` runs F2 through every production stage); this module authors it from a
programme and two adjacent adapter candidates.

WHAT THIS IS NOT. Not a T (two seams), not a U or courtyard (a bent or closed corridor cannot be
one open circulation space in a slicing tree), not an arbitrary multi-wing decomposition, and not
a shape a person selects: an L is offered when the adapter finds two adjacent safe rectangles in
the buildable region, and it competes with the one-wing partis under the existing rules — nothing
ranks it up or down. An arm north or south of the primary (a hall along the street axis) and an
arm that extends past the primary's side are refused with their own reasons, not approximated.

WHAT IS REUSED, deliberately: every sizing rule of the column partis and the front band — row
pairing (`_rows_of`, `_rows_for_width`, tier-2 `Repartition`), row depths with deficit and hard
tiers (`_row_depths`), the shape-and-size rule (`room_depth_band_m`), the seam-width search
(`_seam_options`), the hall width (`_hall_width_m`), the zone specs (`_zone_spec`), the access
graph (`_build_access`, front-band form), the forced chains. The only new arithmetic is the
band's depth against the target and the wing rectangles themselves.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import Enum

from . import concept_generator as cg
from .concept import Concept
from .concept_generator import (
    ConceptCandidate,
    ConceptRejection,
    ConceptStrategy,
    PlanFailure,
    ProgramRoom,
    RejectionReason,
    ZoneGroup,
)
from .geometry_core.model import (
    Cut,
    Fixture,
    Leaf,
    Node,
    ProgramRole,
    Rect,
    Side,
    Split,
    Wing,
    ZoneSpec,
    m_to_u,
    u_to_m,
)
from .safe_adapter import SolverGeometryCandidate
from .spec import ArchitecturalSpec

STRATEGY = ConceptStrategy.MULTI_WING_SPLIT
HALL = "HALL"
#: Shorter arms tried after the candidate's full length, in metres, when the full one cannot be
#: filled within the rooms' maxima. Bounded like every other search here.
_ARM_TRIM_STEP_M = 0.5
_MAX_ARM_LENGTHS = 12


class ArmSide(str, Enum):
    """Which side of the primary the arm sits on. The seam is vertical (the hall runs N-S, like
    every hall this engine draws); an arm north or south of the primary is not this parti."""

    EAST = "E"
    WEST = "W"


class ArmEnd(str, Enum):
    """Which end of the primary the arm is flush with. The public band takes the OTHER end."""

    FRONT = "front"   # arm at the street end; band at the rear — public rooms to the garden
    REAR = "rear"     # arm at the rear; band at the street — public rooms on the front


@dataclass(frozen=True)
class SeamGeometry:
    primary: Rect      # candidate 0, trimmed so the arm is flush with one of its ends
    arm: Rect          # candidate 1, as offered
    side: ArmSide
    end: ArmEnd

    @property
    def hall_side(self) -> Side:
        """The primary's side the hall's seam wall is on."""
        return Side.E if self.side is ArmSide.EAST else Side.W

    @property
    def arm_seam_side(self) -> Side:
        """The arm rooms' side that faces the seam."""
        return Side.W if self.side is ArmSide.EAST else Side.E


def seam_geometry(primary: Rect, arm: Rect) -> SeamGeometry | ConceptRejection:
    """Where the two candidates meet, or the reason this parti cannot use them."""
    if primary.x2 == arm.x:
        side = ArmSide.EAST
    elif arm.x2 == primary.x:
        side = ArmSide.WEST
    elif primary.y2 == arm.y or arm.y2 == primary.y:
        return ConceptRejection(
            STRATEGY, RejectionReason.NO_SEAM_ALIGNMENT,
            f"the second wing ({u_to_m(arm.w):.1f} x {u_to_m(arm.h):.1f} m) sits north or south "
            f"of the primary; this parti runs its hall along the seam, and a hall along the "
            f"street axis is not authored yet", (0, 1))
    else:
        return ConceptRejection(STRATEGY, RejectionReason.NO_SEAM_ALIGNMENT,
                                "the two safe wings share no boundary", (0, 1))
    if arm.y < primary.y or arm.y2 > primary.y2:
        return ConceptRejection(
            STRATEGY, RejectionReason.NO_SEAM_ALIGNMENT,
            f"the arm (y {u_to_m(arm.y):.2f}..{u_to_m(arm.y2):.2f} m) extends past the primary's "
            f"side (y {u_to_m(primary.y):.2f}..{u_to_m(primary.y2):.2f} m); the seam would not "
            f"cover the arm's whole side", (0, 1))
    if arm.y == primary.y and arm.y2 == primary.y2:
        return ConceptRejection(
            STRATEGY, RejectionReason.NO_SEAM_ALIGNMENT,
            "the two wings span the same depth; their union is a rectangle, not an L", (0, 1))
    if arm.y == primary.y:
        return SeamGeometry(primary, arm, side, ArmEnd.FRONT)
    # Flush with the rear, or floating: a floating arm becomes rear-flush by trimming the
    # primary's rear to the arm's — a sub-rectangle of a proven-safe candidate is still safe, and
    # the public band then keeps the street.
    trimmed = Rect(primary.x, primary.y, primary.w, arm.y2 - primary.y)
    return SeamGeometry(trimmed, arm, side, ArmEnd.REAR)


# --------------------------------------------------------------------------- allocation

def _l_allocations(rooms: list[ProgramRoom], arm_len_m: float, net_arm_w_m: float,
                   open_plan: bool = True,
                   ) -> list[tuple[str, list[ProgramRoom], list[ProgramRoom], list[ProgramRoom]]]:
    """(rationale, arm rooms, column rooms, band rooms) — the bounded set this parti tries.

    The arm is the PRIVATE wing: every bedroom with its ensuite. The band is the public zone,
    whole — an open-plan group split between band and column would sit in two subtrees and be
    walled (`_mark_open_interfaces` needs siblings), so it is never split. The column beside the
    hall takes what remains, two ways: the safe room and the guest WC (the shared bathrooms stay
    with the bedrooms), or the whole wet cluster (the safe room joins the bedrooms — the census
    found it IS one of them). A column with nothing in it is not offered: the seam part would be
    hall alone.

    OVERFLOW. The arm is as long as the adapter's candidate and no longer, so a private wing that
    does not fit it is not refused outright: the arm keeps the rows that fit at their floors —
    master suite first, then the bedrooms in order — and the rest joins the column beside the
    hall, still entered from it. The rationale says so. Measured on the L fixture, a 3-bedroom
    programme needs 11.2 m of arm for its four rows and the arm has 9.5; without this the parti
    never planned a 3-bedroom house at all.
    """
    public = [r for r in rooms if r.group is ZoneGroup.PUBLIC]
    bedrooms = [r for r in rooms if r.group is ZoneGroup.PRIVATE and r.role is not ProgramRole.SAFE_ROOM]
    safe = [r for r in rooms if r.role is ProgramRole.SAFE_ROOM]
    service = [r for r in rooms if r.group is ZoneGroup.SERVICE]
    ensuites = [r for r in service if r.entered_from]
    shared = [r for r in service if not r.entered_from]
    baths = [r for r in shared if r.role is ProgramRole.BATHROOM]
    wcs = [r for r in shared if r.role is not ProgramRole.BATHROOM]

    def rows_need_m(arm: list[ProgramRoom]) -> float | None:
        """The arm's rows at their floors, end to end — None when a row cannot be shaped there
        even under the HARD maxima. Judged at the hard tier on purpose: a bedroom that is only
        oversized under its preferred maximum at this arm's width is the ladder's business
        (tier 2 pairs it with a neighbour, the hard tier admits it and marks the plan), not a
        reason to move it out of the wing before any plan is tried."""
        rows = cg._rows_of(arm)
        total = 0.0
        for row, allowance in zip(rows, cg._row_wall_allowances_m(rows, (True, True))):
            floor, failure = cg._row_depth_floor_m(row, net_arm_w_m, "bedroom wing", allowance,
                                                   hard=True)
            if failure is not None:
                return None
            total += floor
        return total

    def fits(arm: list[ProgramRoom]) -> bool:
        need = rows_need_m(arm)
        return need is not None and need <= arm_len_m + 1e-9

    def tail_overflow(arm: list[ProgramRoom]) -> tuple[list[ProgramRoom], list[ProgramRoom]]:
        """Keep rows from the front (master suite first) while they fit; the tail overflows."""
        rows = cg._rows_of(arm)
        kept: list[ProgramRoom] = []
        used = 0.0
        for index, (row, allowance) in enumerate(zip(rows, cg._row_wall_allowances_m(rows, (True, True)))):
            floor, failure = cg._row_depth_floor_m(row, net_arm_w_m, "bedroom wing", allowance,
                                                   hard=True)
            if failure is not None or used + floor > arm_len_m + 1e-9:
                return kept, [r for later in rows[index:] for r in later]
            kept.extend(row)
            used += floor
        return kept, []

    def bedroom_overflow(arm: list[ProgramRoom]) -> tuple[list[ProgramRoom], list[ProgramRoom]]:
        """Move secondary bedrooms, last first (each with its ensuite), until the rest fits. A
        bedroom beside the hall is an elastic row the column can fill its length with, where a
        bathroom alone often cannot; and a bedroom off the entrance hall is an ordinary house."""
        rest, moved = list(arm), []
        while not fits(rest):
            movable = [r for r in rest if r.role is ProgramRole.BEDROOM]
            if not movable:
                return [], moved
            last = movable[-1]
            mates = [r for r in rest if r.entered_from == last.zone_id]
            rest = [r for r in rest if r is not last and r not in mates]
            moved = [last, *mates, *moved]
        return rest, moved

    out: list[tuple[str, list[ProgramRoom], list[ProgramRoom], list[ProgramRoom]]] = []
    seen: set[tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = set()

    def offer(rationale: str, arm: list[ProgramRoom], column: list[ProgramRoom],
              band: list[ProgramRoom]) -> None:
        key = (tuple(r.zone_id for r in arm), tuple(r.zone_id for r in column),
               tuple(r.zone_id for r in band))
        if arm and column and band and key not in seen:
            seen.add(key)
            out.append((rationale, arm, column, band))

    # Where the public rooms go: the whole group in the band; and, for a CLOSED plan only, the
    # kitchen beside the hall with a door of its own and the living (and dining) in the band —
    # a narrow band can then still hold what it must. An open-plan group is never split.
    band_variants = [("", public)]
    kitchens = [r for r in public if r.role is ProgramRole.KITCHEN]
    if not open_plan and kitchens and len(public) > 1:
        band_variants.append(("; kitchen beside the hall", [r for r in public if r not in kitchens]))

    for band_note, band in band_variants:
        extra_column = [r for r in public if r not in band]
        for rationale, arm, column in (
                ("bedroom wing with its bathrooms; safe room and WC beside the hall",
                 bedrooms + ensuites + baths, safe + wcs),
                ("bedrooms and safe room in the wing; wet rooms clustered beside the hall",
                 bedrooms + ensuites + safe, baths + wcs)):
            rationale += band_note
            column = extra_column + column
            if fits(arm):
                offer(rationale, arm, column, band)
                # A column of ONE row cannot fill the hall's length: a safe room takes no surplus
                # and a lone wet room caps out well short of any arm. Offer a bedroom beside the
                # hall as well, so the column has an elastic second row — the same move the
                # overflow makes when the arm is short, made before the failure this time.
                if len(cg._rows_of(column)) < 2:
                    movable = [r for r in arm if r.role is ProgramRole.BEDROOM]
                    if movable:
                        last = movable[-1]
                        mates = [r for r in arm if r.entered_from == last.zone_id]
                        offer(f"{rationale}; {last.zone_id} beside the hall",
                              [r for r in arm if r is not last and r not in mates],
                              column + [last, *mates], band)
                continue
            kept, overflow = tail_overflow(arm)
            if kept:
                offer(f"{rationale}; {', '.join(r.zone_id for r in overflow)} beside the hall — "
                      f"the arm holds {len(cg._rows_of(kept))} rows", kept, column + overflow, band)
            kept, moved = bedroom_overflow(arm)
            if kept:
                offer(f"{rationale}; {', '.join(r.zone_id for r in moved)} beside the hall — "
                      f"the arm holds {len(cg._rows_of(kept))} rows", kept, column + moved, band)
    return out


# --------------------------------------------------------------------------- one plan

@dataclass(frozen=True)
class LPlan:
    geometry: SeamGeometry
    primary: Rect                       # the primary WING actually used (trimmed), plot units
    arm: Rect                           # the arm WING actually used, plot units
    hall_w_m: float
    column_w_m: float
    band_depth_m: float
    arm_len_m: float
    arm_rows: list[list[ProgramRoom]]
    arm_depths_m: list[float]
    column_rows: list[list[ProgramRoom]]
    column_depths_m: list[float]
    band_rows: list[list[ProgramRoom]]  # stacked: one room per row top->bottom; side by side: one row
    band_widths_m: list[float]          # side by side only
    band_depths_m: list[float]          # stacked only
    stacked_band: bool
    public_ids: list[str]               # the hall-adjacent zone FIRST, then along the open chain
    specs: dict[str, ZoneSpec]

    @property
    def used_area_m2(self) -> float:
        return round(u_to_m(self.primary.w) * u_to_m(self.primary.h)
                     + u_to_m(self.arm.w) * u_to_m(self.arm.h), 2)


def _snap(value_m: float) -> float:
    return round(value_m / 0.05) * 0.05


def _hall_width(spec: ArchitecturalSpec, rooms: list[ProgramRoom]) -> float:
    inset = cg._EDGE_INSET_ALLOWANCE_M
    return cg._hall_width_m(
        spec.program.corridor,
        max(cg.ROOM_TEMPLATES[ProgramRole.HALL].min_short_side_m + inset, cg._FRONT_BAND_HALL_M),
        cap_m=cg._FRONT_BAND_HALL_M,
        has_safe_room=any(r.role is ProgramRole.SAFE_ROOM for r in rooms))


def _band_public_order(public: list[ProgramRoom], geometry: SeamGeometry,
                       stacked: bool) -> tuple[list[ProgramRoom], list[str]]:
    """The band's rooms in GEOMETRIC order (west->east, or top->bottom when stacked), and the
    access order — hall-adjacent zone first, then along the chain.

    Side by side, the living room takes the seam end, where the hall's end opens into it (the
    front band's rule). Stacked at the street (arm at the rear), the kitchen is the row next to
    the hall and the living room fronts the street, so the front door opens into the living room
    and not the kitchen; stacked at the rear (arm at the front), the living room is next to the
    hall and the kitchen ends at the garden.
    """
    if not stacked:
        access = list(public)                                    # LIVING first
        geometric = list(reversed(public)) if geometry.side is ArmSide.EAST else list(public)
        return geometric, [r.zone_id for r in access]
    if geometry.end is ArmEnd.REAR:                              # band at the street, above the hall
        geometric = list(public)                                 # LIVING top, KITCHEN bottom
        return geometric, [r.zone_id for r in reversed(public)]  # KITCHEN is hall-adjacent
    geometric = list(public)                                     # band at the rear, below the hall
    return geometric, [r.zone_id for r in public]                # LIVING (top) is hall-adjacent


def _plan_l(spec: ArchitecturalSpec, rooms: list[ProgramRoom], geometry: SeamGeometry,
            arm_rooms: list[ProgramRoom], column_rooms: list[ProgramRoom],
            band_rooms: list[ProgramRoom], *, stacked_band: bool,
            fallback: cg.Repartition | None = None, allow_deficit: bool = False,
            allow_hard: bool = False,
            ) -> tuple[list[LPlan], PlanFailure | None]:
    """Every consistent sizing of this allocation, nearest the requested area first (bounded)."""
    inset = cg._EDGE_INSET_ALLOWANCE_M
    target = spec.program.target_built_area_m2
    modest = cg.scale_program(rooms, sum(r.template.target_area_m2 for r in rooms))
    areas = {z: s.net_area_target_m2 for z, s in modest.items()}
    hall_w = _hall_width(spec, rooms)
    P, S = geometry.primary, geometry.arm
    pw, ph, sw, sh = u_to_m(P.w), u_to_m(P.h), u_to_m(S.w), u_to_m(S.h)

    # --- the arm: rows of private rooms, the corridor across the seam ------------------------
    arm_corridor_east = geometry.side is ArmSide.WEST
    net_arm = sw - inset
    if net_arm <= 0:
        return [], PlanFailure(RejectionReason.COLUMN_WIDTH_EXCEEDED, "the arm has no net width")
    arm_rows = [cg._orient_row(r, corridor_on_east=arm_corridor_east)
                for r in cg._daylight_order(cg._rows_of(arm_rooms), north_is_envelope=True)]
    arm_rows = cg._rows_for_width(arm_rows, net_arm, fallback, arm_corridor_east, areas)
    for row in arm_rows:
        if cg._row_widths(row, net_arm) is None:
            return [], PlanFailure(
                RejectionReason.ROW_WIDTH_EXCEEDED,
                f"{' + '.join(r.zone_id for r in row)} cannot share the bedroom wing's "
                f"{net_arm:.2f} m of net width at their minimums")
    arm_need = 0.0
    for row, allowance in zip(arm_rows, cg._row_wall_allowances_m(arm_rows, (True, True))):
        floor, failure = cg._row_depth_floor_m(row, net_arm, "bedroom wing", allowance, allow_hard)
        if failure is not None:
            return [], failure
        arm_need += floor
    if arm_need > sh + 1e-9:
        return [], PlanFailure(
            RejectionReason.COLUMN_DEPTH_EXCEEDED,
            f"bedroom wing needs {arm_need:.2f} m of depth for its rows' floors but the arm is "
            f"{sh:.2f} m long", arm_need - sh)
    arm_lengths = [sh]
    length = sh
    while len(arm_lengths) < _MAX_ARM_LENGTHS and length - _ARM_TRIM_STEP_M >= arm_need - 1e-9:
        length = _snap(length - _ARM_TRIM_STEP_M)
        arm_lengths.append(length)

    # --- the column beside the hall -----------------------------------------------------------
    column_corridor_east = geometry.side is ArmSide.EAST
    column_north_exterior = geometry.end is ArmEnd.FRONT     # band at the rear -> street at the top
    column_rows0 = [cg._orient_row(r, corridor_on_east=column_corridor_east)
                    for r in cg._daylight_order(cg._rows_of(column_rooms),
                                                north_is_envelope=column_north_exterior)]
    column_min = cg._column_min_width(column_rooms)
    if column_min + hall_w > pw + 1e-9:
        return [], PlanFailure(
            RejectionReason.COLUMN_WIDTH_EXCEEDED,
            f"the column beside the hall needs {column_min:.2f} m and the hall {hall_w:.2f} m, "
            f"more than the primary wing's {pw:.2f} m")

    # --- the band ------------------------------------------------------------------------------
    band_geo, public_ids = _band_public_order(band_rooms, geometry, stacked_band)
    band_ends = (geometry.end is ArmEnd.REAR, geometry.end is ArmEnd.FRONT)  # (north, south) exterior

    found: list[LPlan] = []
    nearest: PlanFailure | None = None

    def miss(failure: PlanFailure) -> None:
        nonlocal nearest
        nearest = cg._nearest_miss(nearest, failure)

    for arm_len in arm_lengths:
        arm_depths, failure = cg._row_depths(arm_rows, areas, net_arm, arm_len, "bedroom wing",
                                             ends_exterior=(True, True),
                                             allow_deficit=allow_deficit, allow_hard=allow_hard)
        if arm_depths is None:
            miss(failure)
            continue
        failure = cg._verify_row_shapes(arm_rows, arm_depths, net_arm, "bedroom wing", allow_hard)
        if failure is not None:
            miss(failure)
            continue

        # Column widths, narrowest first: the column must FILL the hall's length, and a room's
        # depth ceiling at a width is its maximum area over that width, so the narrowest column is
        # the one most able to. The natural (area-share) width and its neighbours follow, as in
        # the spine's seam search; the band gets whatever width the column leaves it.
        natural = sum(areas[r.zone_id] for r in column_rooms) / max(arm_len, 1e-6) + inset
        options = cg._seam_options(natural, column_min, pw - hall_w,
                                   limit=None if fallback is not None and not fallback.quality
                                   else cg._MAX_SEAM_OPTIONS)
        if column_min <= pw - hall_w + 1e-9 and all(abs(column_min - w) > 1e-9 for w in options):
            options.append(_snap(column_min))
        for column_w in sorted(options):
            primary_w = _snap(column_w + hall_w)
            column_w = primary_w - hall_w
            net_column = column_w - inset
            column_rows = cg._rows_for_width(column_rows0, net_column, fallback, column_corridor_east,
                                             areas)
            bad_row = next((row for row in column_rows if cg._row_widths(row, net_column) is None), None)
            if bad_row is not None:
                miss(PlanFailure(RejectionReason.ROW_WIDTH_EXCEEDED,
                                 f"{' + '.join(r.zone_id for r in bad_row)} cannot share the "
                                 f"column's {net_column:.2f} m of net width beside the hall"))
                continue
            column_depths, failure = cg._row_depths(
                column_rows, areas, net_column, arm_len, "column beside the hall",
                ends_exterior=(column_north_exterior, not column_north_exterior),
                allow_deficit=allow_deficit, allow_hard=allow_hard)
            if column_depths is None:
                miss(failure)
                continue
            failure = cg._verify_row_shapes(column_rows, column_depths, net_column,
                                            "column beside the hall", allow_hard)
            if failure is not None:
                miss(failure)
                continue

            max_band = ph - arm_len
            if stacked_band:
                band = _stacked_band(band_geo, primary_w, max_band, areas, band_ends, target,
                                     sw, arm_len, allow_deficit, allow_hard)
            else:
                band = _side_by_side_band(band_geo, primary_w, max_band, areas, hall_w, target,
                                          sw, arm_len, allow_hard)
            if isinstance(band, PlanFailure):
                miss(band)
                continue
            band_depth, band_widths, band_depths, band_rows = band

            specs = _specs(rooms, arm_rows, arm_depths, net_arm, column_rows, column_depths,
                           net_column, band_rows, band_widths, band_depths, band_depth, primary_w,
                           hall_w, arm_len, stacked_band, allow_hard)
            failure = cg._specs_within_maxima(rooms, specs, "L wings", allow_hard)
            if failure is not None:
                miss(failure)
                continue

            found.append(LPlan(
                geometry=geometry,
                primary=_primary_rect(geometry, primary_w, band_depth, arm_len),
                arm=_arm_rect(geometry, arm_len),
                hall_w_m=hall_w, column_w_m=column_w, band_depth_m=band_depth, arm_len_m=arm_len,
                arm_rows=arm_rows, arm_depths_m=arm_depths,
                column_rows=column_rows, column_depths_m=column_depths,
                band_rows=band_rows, band_widths_m=band_widths, band_depths_m=band_depths,
                stacked_band=stacked_band, public_ids=public_ids, specs=specs))

    if not found:
        return [], nearest
    if target is not None:
        found.sort(key=lambda p: (round(abs(p.used_area_m2 - target), 4), round(p.used_area_m2, 4)))
        return found[:cg._MAX_PROPORTIONS_PER_STRATEGY], None
    return found[:1], None


def _band_target_depth(target: float | None, want: float, primary_w: float, arm_w: float,
                       arm_len: float, lo: float, hi: float) -> float | PlanFailure:
    """The band depth: what the public rooms want, or — with a request — what brings the whole
    house nearest the requested area, clamped to what the rooms can be shaped to."""
    if lo > hi + 1e-9:
        return PlanFailure(
            RejectionReason.COLUMN_DEPTH_EXCEEDED,
            f"the public band needs {lo:.2f} m of depth and may have {hi:.2f} m", lo - hi)
    depth = want
    if target is not None:
        depth = (target - arm_w * arm_len - primary_w * arm_len) / max(primary_w, 1e-6)
    return _snap(min(max(depth, lo), hi))


def _side_by_side_band(band: list[ProgramRoom], primary_w: float, max_depth: float,
                       areas: dict[str, float], hall_w: float, target: float | None,
                       arm_w: float, arm_len: float, allow_hard: bool):
    """Public rooms across the primary's width, the front band's way: widths by area share, each
    at least its minimum short side; the band's depth floored by every room's shape band and
    capped by the first room to reach its maximum."""
    inset = cg._EDGE_INSET_ALLOWANCE_M
    total = sum(areas[r.zone_id] for r in band) or 1.0
    widths = [_snap(primary_w * areas[r.zone_id] / total) for r in band[:-1]]
    widths.append(round(primary_w - sum(widths), 4))
    for room, w in zip(band, widths):
        if w - inset + 1e-6 < room.template.min_short_side_m:
            return PlanFailure(
                RejectionReason.BAND_WIDTH_BELOW_MINIMUM,
                f"{room.zone_id} would be {w:.2f} m wide in the public band, below its "
                f"{room.template.min_short_side_m} m minimum", room.template.min_short_side_m - (w - inset))
    lo, hi = 0.0, max_depth
    for room, w in zip(band, widths):
        shape = cg.room_depth_band_m(room.template, w - inset, allow_hard)
        if shape is None:
            return cg._shape_failure(room, w - inset, 0.0, "public band", allow_hard)
        lo = max(lo, shape[0] + inset)
        hi = min(hi, room.template.ceiling_m2(allow_hard) / max(w, 1e-6))   # gross, like the front band
    want = sum(areas[r.zone_id] for r in band) / max(primary_w, 1e-6) + inset
    depth = _band_target_depth(target, want, primary_w, arm_w, arm_len, lo, hi)
    if isinstance(depth, PlanFailure):
        return depth
    return depth, widths, [], [list(band)]


def _stacked_band(band: list[ProgramRoom], primary_w: float, max_depth: float,
                  areas: dict[str, float], ends_exterior: tuple[bool, bool], target: float | None,
                  arm_w: float, arm_len: float, allow_deficit: bool, allow_hard: bool):
    """Public rooms as full-width rows — one open subtree, so open-plan marking is structural."""
    inset = cg._EDGE_INSET_ALLOWANCE_M
    rows = [[r] for r in band]
    net_w = primary_w - inset
    lo = 0.0
    hi = 0.0
    for row, allowance in zip(rows, cg._row_wall_allowances_m(rows, ends_exterior)):
        floor, failure = cg._row_depth_floor_m(row, net_w, "public stack", allowance, allow_hard)
        if failure is not None:
            return failure
        wanted = max(areas[row[0].zone_id] / max(net_w, 1e-6), floor)
        lo += floor
        hi += cg._row_depth_ceiling_m(row, net_w, wanted, allow_hard)
    want = sum(areas[r.zone_id] for r in band) / max(net_w, 1e-6) + len(rows) * inset / 2
    depth = _band_target_depth(target, want, primary_w, arm_w, arm_len, lo, min(hi, max_depth))
    if isinstance(depth, PlanFailure):
        return depth
    depths, failure = cg._row_depths(rows, areas, net_w, depth, "public stack",
                                     ends_exterior=ends_exterior, allow_deficit=allow_deficit,
                                     allow_hard=allow_hard)
    if depths is None:
        return failure
    return depth, [], depths, rows


def _specs(rooms, arm_rows, arm_depths, net_arm, column_rows, column_depths, net_column,
           band_rows, band_widths, band_depths, band_depth, primary_w, hall_w, arm_len, stacked,
           allow_hard) -> dict[str, ZoneSpec]:
    """A ZoneSpec per room from the rectangle it was planned in — `_zone_spec`'s band around
    the plan, the template's aspect ratio unrelaxed — and the hall's from the seam."""
    inset = cg._EDGE_INSET_ALLOWANCE_M
    specs: dict[str, ZoneSpec] = {}
    for rows, depths, net_w in ((arm_rows, arm_depths, net_arm),
                                (column_rows, column_depths, net_column)):
        for row, depth in zip(rows, depths):
            net_d = depth - inset / 2
            widths = cg._row_widths(row, net_w, net_d) or [net_w / len(row)] * len(row)
            for room, w in zip(row, widths):
                specs[room.zone_id] = cg._zone_spec(room, w, net_d, 0.60, 1.60, allow_hard)
    if stacked:
        for row, depth in zip(band_rows, band_depths):
            specs[row[0].zone_id] = cg._zone_spec(row[0], primary_w - inset, depth - inset / 2,
                                                  0.60, 1.60, allow_hard)
    else:
        for room, w in zip(band_rows[0], band_widths):
            specs[room.zone_id] = cg._zone_spec(room, w - inset, band_depth - inset / 2,
                                                0.60, 1.60, allow_hard)
    hall_target = (hall_w - inset) * (arm_len - inset / 2)
    specs[HALL] = ZoneSpec(HALL, (ProgramRole.HALL, ProgramRole.CIRCULATION),
                           hall_target * 0.55, hall_target, hall_target * 1.75,
                           cg.ROOM_TEMPLATES[ProgramRole.HALL].min_short_side_m, 12.0)
    return specs


def _primary_rect(geometry: SeamGeometry, primary_w: float, band_depth: float,
                  arm_len: float) -> Rect:
    """The primary wing as used: trimmed from the side AWAY from the seam and, when the arm is
    at the rear, from the street (the band takes exactly the depth it needs)."""
    P, S = geometry.primary, geometry.arm
    w_u, h_u = m_to_u(primary_w), m_to_u(band_depth) + m_to_u(arm_len)
    x = P.x2 - w_u if geometry.side is ArmSide.EAST else P.x
    y = S.y2 - h_u if geometry.end is ArmEnd.REAR else S.y
    return Rect(x, y, w_u, h_u)


def _arm_rect(geometry: SeamGeometry, arm_len: float) -> Rect:
    S = geometry.arm
    h_u = m_to_u(arm_len)
    y = S.y2 - h_u if geometry.end is ArmEnd.REAR else S.y
    return Rect(S.x, y, S.w, h_u)


# --------------------------------------------------------------------------- the fixture

def _plan_shapes(plan: LPlan) -> dict[str, tuple[float, float]]:
    """Every arm and column room's planned NET (width, depth) — `cg._row_shapes` on the wing rows.
    The band's public rooms carry no preferred aspect and are not read."""
    inset = cg._EDGE_INSET_ALLOWANCE_M
    shapes = cg._row_shapes(plan.arm_rows, plan.arm_depths_m, u_to_m(plan.arm.w) - inset)
    shapes.update(cg._row_shapes(plan.column_rows, plan.column_depths_m, plan.column_w_m - inset))
    return shapes


def _quality_l_plans(spec: ArchitecturalSpec, rooms: list[ProgramRoom], geometry: SeamGeometry,
                     arm_rooms: list[ProgramRoom], column_rooms: list[ProgramRoom],
                     band_rooms: list[ProgramRoom], *, stacked_band: bool,
                     repartition: cg.Repartition, bases: list[tuple[LPlan, bool, bool]],
                     ) -> list[tuple[LPlan, bool, bool]]:
    """The quality tier for the L — `concept_generator._quality_layouts` on `_plan_l`, nothing
    L-specific: where a kept plan leaves a bedroom-class room past its preferred aspect, the same
    allocation and band form are sized again with the wing rows re-partitioned for proportions
    through the `_rows_for_width` hook `_plan_l` already uses — the base plan's own sizing tier,
    the normal nine column widths, at most `cg._MAX_QUALITY_PAIRINGS` pairings, and every plan
    held to `cg._quality_accepts` against the base with the SAME WINGS — a re-partitioned plan
    is offered at its base's footprint, never at another sizing's."""
    by_zone = {r.zone_id: r for r in rooms}
    aspects = {id(b): cg._preferred_aspects(_plan_shapes(b), rooms) for b, *_ in bases}
    poor = [(b, d, h) for b, d, h in bases if cg._quality_shortfall(aspects[id(b)], by_zone) > 1e-6]
    out: list[tuple[LPlan, bool, bool]] = []
    for allow_deficit, allow_hard in dict.fromkeys((d, h) for _, d, h in poor):
        tier_bases = [b for b, d, h in poor if (d, h) == (allow_deficit, allow_hard)]
        for rank in range(cg._MAX_QUALITY_PAIRINGS):
            options = replace(repartition, quality=True, quality_rank=rank, hard=allow_hard)
            plans, _ = _plan_l(spec, rooms, geometry, arm_rooms, column_rooms, band_rooms,
                               stacked_band=stacked_band, fallback=options,
                               allow_deficit=allow_deficit, allow_hard=allow_hard)
            if not plans or all(any(p == b for b, *_ in bases) for p in plans):
                break   # no pairing of this rank: the normal sizing came back
            for plan in plans:
                if any(plan == b for b, *_ in bases) or any(plan == o for o, *_ in out):
                    continue
                ref = next((b for b in tier_bases
                            if b.primary == plan.primary and b.arm == plan.arm), None)
                if ref is None:
                    continue
                new = cg._preferred_aspects(_plan_shapes(plan), rooms)
                if cg._quality_accepts(aspects[id(ref)], new, by_zone):
                    out.append((plan, allow_deficit, allow_hard))
    return out


def _candidate_from(spec: ArchitecturalSpec, rooms: list[ProgramRoom], plan: LPlan,
                    primary: SolverGeometryCandidate, arm: SolverGeometryCandidate,
                    rationale: str, *, repartitioned: bool, shrunk: bool,
                    over_preferred: bool, quality_repartitioned: bool = False) -> ConceptCandidate:
    inset = cg._EDGE_INSET_ALLOWANCE_M
    g = plan.geometry
    hall_w_u = m_to_u(plan.hall_w_m)
    column_w_u = m_to_u(plan.column_w_m)

    # The primary: band over/under the seam part; the hall against the seam, exactly its length.
    column_tree = cg._forced_chain(plan.column_rows, plan.column_depths_m,
                                   plan.column_w_m - inset,
                                   exterior_first=(g.side is ArmSide.EAST))
    if g.side is ArmSide.EAST:
        seam_part: Node = Split(Cut.V, column_tree, Leaf(HALL), column_w_u)
    else:
        seam_part = Split(Cut.V, Leaf(HALL), column_tree, hall_w_u)
    if plan.stacked_band:
        band_tree: Node = cg._forced_chain(plan.band_rows, plan.band_depths_m,
                                           u_to_m(plan.primary.w) - inset, exterior_first=True)
    else:
        band_tree = cg._forced_v_chain(plan.band_rows[0], plan.band_widths_m)
    if g.end is ArmEnd.REAR:
        primary_tree: Node = Split(Cut.H, band_tree, seam_part, m_to_u(plan.band_depth_m))
    else:
        primary_tree = Split(Cut.H, seam_part, band_tree, m_to_u(plan.arm_len_m))

    # The arm: rows across the seam; every row's corridor-side member is a declared seam side.
    arm_tree = cg._forced_chain(plan.arm_rows, plan.arm_depths_m, u_to_m(plan.arm.w) - inset,
                                exterior_first=(g.side is ArmSide.WEST))
    # HALL's own length is `arm_len_m` by construction (see the module docstring: "its length IS
    # the arm's length"), served on both sides of the seam — the column rows inside the primary
    # wing and the arm rows across it. Check that against the REALIZED extent of the last row on
    # each side (Issue #22), rather than assuming the shared length is always correct.
    cg._assert_corridor_extent(plan.arm_len_m, "L-parti hall",
                               plan.column_depths_m, plan.arm_depths_m)
    seam_member = (lambda row: row[0]) if g.side is ArmSide.EAST else (lambda row: row[-1])
    arm_seams = tuple((seam_member(row).zone_id, g.arm_seam_side) for row in plan.arm_rows)

    wing_a = Wing("A", plan.primary.x, plan.primary.y, plan.primary.w, plan.primary.h,
                  primary_tree, seam_leaf_sides=((HALL, g.hall_side),))
    wing_b = Wing("B", plan.arm.x, plan.arm.y, plan.arm.w, plan.arm.h, arm_tree,
                  seam_leaf_sides=arm_seams)

    # Access: the hall opens into the band's first zone and the band chains on from it (the
    # front band's form); every arm and column room has a door from the hall. A public room
    # placed in the column (a closed kitchen) is entered from the hall like any column room —
    # so it is handed to the access builder as a hall-served room, not as part of the band.
    band_ids = set(plan.public_ids)
    hall_for = {r.zone_id: HALL for r in rooms if r.zone_id not in band_ids and r.zone_id != HALL}
    band_rooms = [r for r in rooms if r.zone_id in band_ids]
    column_public = [r for r in rooms if r.group is ZoneGroup.PUBLIC and r.zone_id not in band_ids]
    served = [r for r in rooms if r.group is not ZoneGroup.PUBLIC] + column_public
    access, groups = cg._build_access(
        [*band_rooms, *[r for r in served if r.group is not ZoneGroup.PUBLIC]], [HALL],
        plan.public_ids, spec.program.open_plan_living, hall_for,
        hall_borders_only_first_public=True)
    if column_public:
        from .geometry_core.model import ConnectionKind, DesiredAccessEdge, DesiredAccessTopology
        access = DesiredAccessTopology(access.edges + tuple(
            DesiredAccessEdge(HALL, r.zone_id, ConnectionKind.DOOR) for r in column_public))
    fixture = Fixture(f"GEN_{STRATEGY.value}", (wing_a, wing_b),
                      tuple(plan.specs[r.zone_id] for r in rooms), access, open_groups=groups)

    bbox_x = min(plan.primary.x, plan.arm.x)
    bbox_x2 = max(plan.primary.x2, plan.arm.x2)
    bbox_y = min(plan.primary.y, plan.arm.y)
    bbox_y2 = max(plan.primary.y2, plan.arm.y2)
    used = plan.used_area_m2
    return ConceptCandidate(
        Concept(fixture, HALL, Side.N, u_to_m(bbox_x2 - bbox_x), u_to_m(bbox_y2 - bbox_y)),
        STRATEGY, (primary.order, arm.order),
        rationale=(f"L: {rationale}; arm {g.side.value} at the {g.end.value}, "
                   f"{u_to_m(plan.arm.w):.2f} x {plan.arm_len_m:.2f} m ({len(plan.arm_rows)} rows); "
                   f"primary {u_to_m(plan.primary.w):.2f} x {u_to_m(plan.primary.h):.2f} m: "
                   f"{'stacked' if plan.stacked_band else 'side-by-side'} public band "
                   f"{plan.band_depth_m:.2f} m | column {plan.column_w_m:.2f} m "
                   f"({len(plan.column_rows)} rows) | hall {plan.hall_w_m:.2f} m on the seam"
                   + (cg.QUALITY_RATIONALE if quality_repartitioned
                      else cg.REPARTITIONED_RATIONALE if repartitioned else "")
                   + (cg.SHRUNK_RATIONALE if shrunk else "")
                   + (cg.OVER_PREFERRED_RATIONALE if over_preferred else "")),
        used_area_m2=used,
        unused_wing_area_m2=round(primary.area_m2 + arm.area_m2 - used, 2),
        wet_rooms=cg.wet_rooms_of(rooms),
        repartitioned=repartitioned, shrunk=shrunk, over_preferred=over_preferred,
        quality_repartitioned=quality_repartitioned,
    )


# --------------------------------------------------------------------------- entry point

def l_concepts(spec: ArchitecturalSpec, rooms: list[ProgramRoom],
               primary: SolverGeometryCandidate, arm: SolverGeometryCandidate,
               ) -> tuple[list[ConceptCandidate], ConceptRejection | None]:
    """The L candidates this programme and these two adjacent wings allow, or the nearest miss.

    Same fallback ladder as `_build`: the normal attempt; tier 2 (rows re-partitioned) where a
    room's shape was refused; then rows shrunk toward their floors, then rooms allowed past
    their preferred maxima, then both. Fallback plans never displace a normal one and are
    marked as what they are.
    """
    if any(r.role is ProgramRole.FLEX for r in rooms):
        return [], ConceptRejection(
            STRATEGY, RejectionReason.INSUFFICIENT_WING_AREA,
            "the public band absorbs surplus through its own elasticity; not combined with FLEX",
            (primary.order, arm.order))
    geometry = seam_geometry(primary.rect, arm.rect)
    if isinstance(geometry, ConceptRejection):
        return [], geometry
    if len([r for r in rooms if r.group is ZoneGroup.PUBLIC]) < 1:
        return [], ConceptRejection(STRATEGY, RejectionReason.INSUFFICIENT_WING_AREA,
                                    "no public room for the band", (primary.order, arm.order))
    allocations = _l_allocations(rooms, u_to_m(geometry.arm.h),
                                 u_to_m(geometry.arm.w) - cg._EDGE_INSET_ALLOWANCE_M,
                                 open_plan=spec.program.open_plan_living)
    if not allocations:
        return [], ConceptRejection(
            STRATEGY, RejectionReason.INSUFFICIENT_WING_AREA,
            "no room for the column beside the hall: the programme has no safe room, guest WC or "
            "shared bathroom to put there", (primary.order, arm.order))

    repartition = cg._repartition_for(spec, rooms, north_is_envelope=geometry.end is ArmEnd.FRONT)
    ladder = ((None, False, False), (None, True, False), (None, False, True), (None, True, True))
    target = spec.program.target_built_area_m2
    built: list[ConceptCandidate] = []
    nearest: PlanFailure | None = None
    for rationale, arm_rooms, column_rooms, band_rooms in allocations:
        for stacked in (False, True):
            # Every sizing this allocation and band form produce, across the ladder; then the
            # nearest few to the request (a normal plan before a fallback on a tie), so the L is
            # as bounded per form as a one-wing strategy is per proportion.
            combo: list[tuple[ConceptCandidate, LPlan, bool, bool, bool]] = []
            normal_found = False
            for fallback, allow_deficit, allow_hard in ladder:
                if (allow_deficit or allow_hard) and normal_found:
                    break
                plans, failure = _plan_l(spec, rooms, geometry, arm_rooms, column_rooms, band_rooms,
                                         stacked_band=stacked, fallback=fallback,
                                         allow_deficit=allow_deficit, allow_hard=allow_hard)
                repartitioned = False
                if not plans and failure is not None and cg._shape_refused(failure):
                    plans, tier2 = _plan_l(spec, rooms, geometry, arm_rooms, column_rooms,
                                           band_rooms, stacked_band=stacked, fallback=repartition,
                                           allow_deficit=allow_deficit, allow_hard=allow_hard)
                    repartitioned = bool(plans)
                    if not plans and tier2 is not None:
                        failure = cg._nearest_miss(failure, tier2)
                if not plans:
                    if failure is not None:
                        nearest = cg._nearest_miss(nearest, failure)
                    continue
                normal_found = normal_found or not (allow_deficit or allow_hard)
                for plan in plans:
                    combo.append((_candidate_from(spec, rooms, plan, primary, arm, rationale,
                                                  repartitioned=repartitioned, shrunk=allow_deficit,
                                                  over_preferred=allow_hard),
                                  plan, repartitioned, allow_deficit, allow_hard))
            if target is not None:
                combo.sort(key=lambda item: (round(abs(item[0].used_area_m2 - target), 4),
                                             item[0].over_preferred or item[0].shrunk or item[0].repartitioned,
                                             round(item[0].used_area_m2, 4)))
            kept = combo[:cg._MAX_PROPORTIONS_PER_STRATEGY]
            built.extend(candidate for candidate, *_ in kept)
            # QUALITY TIER beside the kept plans (`_quality_l_plans`): additional candidates,
            # bounded like the kept ones, ordered last by `generate_concepts`.
            quality = [_candidate_from(spec, rooms, plan, primary, arm, rationale, repartitioned=True,
                                       shrunk=allow_deficit, over_preferred=allow_hard,
                                       quality_repartitioned=True)
                       for plan, allow_deficit, allow_hard in _quality_l_plans(
                           spec, rooms, geometry, arm_rooms, column_rooms, band_rooms,
                           stacked_band=stacked, repartition=repartition,
                           bases=[(plan, d, h) for _, plan, rep, d, h in kept if not rep])]
            if target is not None:
                quality.sort(key=lambda c: (round(abs(c.used_area_m2 - target), 4),
                                            c.over_preferred or c.shrunk, round(c.used_area_m2, 4)))
            built.extend(quality[:cg._MAX_PROPORTIONS_PER_STRATEGY])
    if built:
        return built, None
    if nearest is None:
        return [], ConceptRejection(STRATEGY, RejectionReason.INSUFFICIENT_WING_AREA,
                                    "no L sizing was attempted", (primary.order, arm.order))
    return [], ConceptRejection(STRATEGY, nearest.reason, nearest.detail, (primary.order, arm.order))
