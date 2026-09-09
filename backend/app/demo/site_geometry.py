"""Authoritative site geometry: the parcel comes first, and everything else is subtracted from it.

THE DIRECTION THIS MODULE EXISTS TO FIX
---------------------------------------
`spec_for` used to build the plot FROM the building:

    plot_width  = footprint.width + 2 * SIDE_SETBACK
    plot_depth  = footprint.depth + FRONT_SETBACK + REAR_SETBACK

which is the honest relationship run backwards. With `+`, the site grows to whatever the building
needs and the parcel can never be the binding constraint — a person who entered a 300 m² plot had
their house laid out on a synthesised 517 m². The direction here is the only correct one:

    SITE (authoritative)  −  setbacks  →  BUILDABLE REGION  →  the footprint must FIT INSIDE it

Land is only ever removed. Nothing in this module can produce a rectangle larger than the parcel it
was given, and `derive` has no access to the footprint at all — the fit check is a separate step
that reads the derived region rather than influencing it.

SCOPE (P0)
----------
Rectangular parcels only, with one of the four cardinal edges facing the street. No polygons, no
corner lots, no angled frontage, no GIS, no regulation lookup. Anything outside that is refused by
`check_supported`, never approximated.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.projects.models import Project, StreetSide

#: DEMO PLANNING ASSUMPTIONS — not verified planning or legal figures, and not presented as such.
#: They are applied by SUBTRACTION from the authoritative site; they never generate one.
FRONT_SETBACK_M = 5.5
SIDE_SETBACK_M = 3.0
REAR_SETBACK_M = 4.0

#: Shown with the numbers wherever they appear, so nobody mistakes them for a planning determination.
SETBACK_DISCLAIMER = "הנחות תכנון לדמו — אינן מידע תכנוני או רגולטורי מאומת."

#: Appended to every feasibility refusal, in both languages. The point is the SCOPE of the claim:
#: what failed is this brief against THIS parcel and THESE assumptions. Nothing here says the house
#: cannot be designed — change the plot, the setbacks or the programme and the answer changes.
NOT_FEASIBLE_PHRASE = "not feasible under the current site geometry and setback assumptions"
NOT_FEASIBLE_HE = (
    "לא ניתן לביצוע עם גאומטריית המגרש והנחות הנסיגה הנוכחיות. "
    "אין בכך קביעה שהתכנון בלתי אפשרי — שינוי מידות המגרש, הנסיגות או התוכנית עשוי לפתור זאת.")


@dataclass(frozen=True)
class SiteGeometry:
    """The parcel as the planner sees it, in the engine's canonical frame.

    The engine assumes the street lies along the y=0 edge (the site stage puts parking and the
    entrance walk in the front band there). A parcel whose street edge is EAST or WEST is therefore
    presented to the engine with its dimensions swapped — `canonical_width_m` is always the
    street-parallel dimension. `plot_width_m`/`plot_depth_m` keep the numbers the person actually
    entered, so the review screen can show those rather than the rotated ones.
    """

    plot_width_m: float
    plot_depth_m: float
    street_facing_side: StreetSide
    canonical_width_m: float
    canonical_depth_m: float
    front_setback_m: float = FRONT_SETBACK_M
    side_setback_m: float = SIDE_SETBACK_M
    rear_setback_m: float = REAR_SETBACK_M

    @property
    def plot_area_m2(self) -> float:
        return round(self.plot_width_m * self.plot_depth_m, 2)

    @property
    def buildable_width_m(self) -> float:
        return round(self.canonical_width_m - 2 * self.side_setback_m, 2)

    @property
    def buildable_depth_m(self) -> float:
        return round(self.canonical_depth_m - self.front_setback_m - self.rear_setback_m, 2)

    @property
    def has_buildable_area(self) -> bool:
        return self.buildable_width_m > 0 and self.buildable_depth_m > 0

    @property
    def buildable_area_m2(self) -> float:
        return round(max(self.buildable_width_m, 0.0) * max(self.buildable_depth_m, 0.0), 2)

    @property
    def near_setback_m(self) -> float:
        """The setback on the canonical y=0 edge — the street edge for NORTH/EAST frontage."""
        return (self.front_setback_m
                if self.street_facing_side in (StreetSide.north, StreetSide.east)
                else self.rear_setback_m)

    @property
    def far_setback_m(self) -> float:
        return (self.rear_setback_m
                if self.street_facing_side in (StreetSide.north, StreetSide.east)
                else self.front_setback_m)

    def buildable_origin_m(self) -> tuple[float, float]:
        """Where the buildable rectangle starts inside the canonical plot.

        For a NORTH or EAST frontage the street edge is the canonical y=0 one, so the front setback
        is the offset. For SOUTH and WEST the parcel is presented flipped, and the offset is the
        REAR setback instead — the buildable rectangle is the same size either way, but it sits at
        the other end, which is what puts the parking and the entrance on the correct side.
        """
        return (self.side_setback_m, self.near_setback_m)


def derive(project: Project) -> SiteGeometry | None:
    """The authoritative site, or `None` when the project does not carry one.

    Deliberately takes no footprint argument: this function CANNOT be influenced by the building.
    """
    if (project.plot_width_m is None or project.plot_depth_m is None
            or project.street_facing_side is None):
        return None

    width, depth = float(project.plot_width_m), float(project.plot_depth_m)
    # A street on an EAST or WEST edge means the street-perpendicular dimension is the plot's
    # WIDTH, so the two swap before the setbacks are applied. This is the whole of P0's
    # orientation support, and it changes the answer materially — a 25 x 16 parcel yields a
    # 19.0 x 6.5 buildable rectangle fronting north, and 10.0 x 15.5 fronting east.
    if project.street_facing_side in (StreetSide.east, StreetSide.west):
        canonical_w, canonical_d = depth, width
    else:
        canonical_w, canonical_d = width, depth

    # The project's OWN assumptions when it has them, the demo defaults otherwise. Either way they
    # are assumptions, and either way they are only ever subtracted.
    setbacks = project.setbacks
    return SiteGeometry(
        plot_width_m=width, plot_depth_m=depth,
        street_facing_side=project.street_facing_side,
        canonical_width_m=canonical_w, canonical_depth_m=canonical_d,
        front_setback_m=setbacks.front_m if setbacks else FRONT_SETBACK_M,
        side_setback_m=setbacks.side_m if setbacks else SIDE_SETBACK_M,
        rear_setback_m=setbacks.rear_m if setbacks else REAR_SETBACK_M,
    )


@dataclass(frozen=True)
class FitResult:
    fits: bool
    detail: str


def check_footprint_fits(site: SiteGeometry, width_m: float, depth_m: float) -> FitResult:
    """Does the chosen building outline fit inside the derived buildable rectangle?

    Compared in the canonical frame, because that is the frame the setbacks were applied in. The
    footprint is NOT rotated to make it fit: a person choosing a wide outline on a deep narrow plot
    has chosen something that does not go there, and silently turning it 90° would be a different
    house from the one they picked.
    """
    if not site.has_buildable_area:
        return FitResult(False, (
            f"after the demo setbacks the plot leaves no buildable area at all "
            f"({site.buildable_width_m:.2f} x {site.buildable_depth_m:.2f} m)"))
    if width_m <= site.buildable_width_m + 1e-9 and depth_m <= site.buildable_depth_m + 1e-9:
        return FitResult(True, (
            f"{width_m:.2f} x {depth_m:.2f} m fits inside "
            f"{site.buildable_width_m:.2f} x {site.buildable_depth_m:.2f} m"))

    short = []
    if width_m > site.buildable_width_m + 1e-9:
        short.append(f"{width_m - site.buildable_width_m:.2f} m too wide")
    if depth_m > site.buildable_depth_m + 1e-9:
        short.append(f"{depth_m - site.buildable_depth_m:.2f} m too deep")
    return FitResult(False, (
        f"footprint {width_m:.2f} x {depth_m:.2f} m vs buildable "
        f"{site.buildable_width_m:.2f} x {site.buildable_depth_m:.2f} m — " + " and ".join(short)))


# --------------------------------------------------------------------------- footprint options

#: How many outlines to offer. Four is what the UI has always shown; the point of the range search
#: below is that all four are now guaranteed to fit rather than four fixed proportions of which
#: most usually cannot.
OPTION_COUNT = 4

#: Aspect ratio (width / depth) -> name. Derived from the SHAPE that actually results, not from a
#: fixed catalogue, because on a constrained site the offered proportions are whatever fits.
_SHAPE_BANDS = (
    (0.90, "NARROW"),
    (1.15, "COMPACT"),
    (1.55, "BALANCED"),
    (float("inf"), "WIDE"),
)


def shape_name(width_m: float, depth_m: float) -> str:
    ratio = width_m / max(depth_m, 1e-9)
    for upper, name in _SHAPE_BANDS:
        if ratio < upper:
            return name
    return "WIDE"


def one_storey_capacity_m2(site: SiteGeometry) -> float:
    """The largest single-storey footprint the site can GEOMETRICALLY hold.

    This is the buildable rectangle's area and nothing more. It is a geometric ceiling, NOT a
    promise about how big a house can be: the room programme, minimum room dimensions, corridor
    width and the validation checks can all reduce it further. Naming it "maximum house area" would
    be a claim this number cannot support.
    """
    return site.buildable_area_m2


def feasible_width_range_m(site: SiteGeometry, area_m2: float) -> tuple[float, float] | None:
    """The widths at which a footprint of EXACTLY `area_m2` fits inside the buildable rectangle.

    A footprint of a fixed area is a curve, `depth = area / width`. Requiring `width <= BW` and
    `depth <= BD` turns it into an interval: `width` from `area / BD` up to `BW`. `None` when the
    interval is empty — that is precisely the case where the requested area does not fit in one
    storey at all, and no proportion can rescue it.

    The area is never reduced to make the interval non-empty. That would be silently giving the
    person a smaller house than they asked for.
    """
    if not site.has_buildable_area or area_m2 <= 0:
        return None
    low = area_m2 / site.buildable_depth_m
    high = site.buildable_width_m
    if low > high + 1e-9:
        return None
    return (low, min(high, max(low, high)))


def feasible_options(site: SiteGeometry, area_m2: float,
                     count: int = OPTION_COUNT) -> list[tuple[float, float]]:
    """Up to `count` (width, depth) outlines of the requested area, all of which FIT.

    Spread evenly across the feasible width interval so the offered set still spans genuinely
    different proportions where the site allows it, and collapses to one option where it does not.
    Widths are snapped to the 5 cm grid and then re-checked, because snapping can push an endpoint
    a few millimetres outside the interval.
    """
    interval = feasible_width_range_m(site, area_m2)
    if interval is None:
        return []
    low, high = interval

    raw = [low] if high - low < 0.05 else [
        low + (high - low) * i / (count - 1) for i in range(count)]

    out: list[tuple[float, float]] = []
    for width in raw:
        w = round(width / 0.05) * 0.05
        w = min(max(w, low), high)          # snapping must not leave the feasible interval
        w = round(w, 2)
        d = round(area_m2 / w, 2)
        if w > site.buildable_width_m + 1e-9 or d > site.buildable_depth_m + 1e-9:
            continue
        if any(abs(w - existing_w) < 0.05 for existing_w, _ in out):
            continue
        out.append((w, d))
    return out
