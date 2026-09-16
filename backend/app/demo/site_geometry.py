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

from dataclasses import dataclass, replace

from app.projects.models import Project, StreetSide

#: DEMO PLANNING ASSUMPTIONS — not verified planning or legal figures, and not presented as such.
#: They are applied by SUBTRACTION from the authoritative site; they never generate one.
#:
#: DEFAULT ZERO, deliberately. Any non-zero default is a planning determination this project has not
#: made, and 5.5 / 3 / 4 consumed 68% of a 300 m² plot — a guess nobody verified was deciding what
#: could be built. Zero asserts nothing: the buildable region is the parcel until somebody enters
#: the setbacks that actually apply, and the field is right there on the form to enter them in.
FRONT_SETBACK_M = 0.0
SIDE_SETBACK_M = 0.0
REAR_SETBACK_M = 0.0

#: Shown with the numbers wherever they appear, so nobody mistakes them for a planning determination.
SETBACK_DISCLAIMER = "הנחות תכנון לדמו — אינן מידע תכנוני או רגולטורי מאומת."

#: The setbacks alone use up a whole side of the parcel, so there is no buildable rectangle at all.
#: A DISTINCT case from "the requested area does not fit": nothing about the house was even weighed,
#: and the numbers to change are the site's or the assumptions', not the programme's.
NO_BUILDABLE_AREA_CODE = "NO_BUILDABLE_AREA"

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
    def presented_buildable_width_m(self) -> float:
        """The width AS IT MAY BE SHOWN.

        The raw properties above are a subtraction, and a subtraction can go NEGATIVE: a 3.00 m deep
        plot minus 5.50 + 4.00 of setback is -6.50. That is a correct intermediate and a meaningless
        physical dimension, and it was reaching the screen as the size of the derived buildable
        area. Where an axis is used up the region is EMPTY, and empty is 0.00 — with
        `has_buildable_area` beside it to say the region is empty rather than merely small.
        """
        return max(self.buildable_width_m, 0.0)

    @property
    def presented_buildable_depth_m(self) -> float:
        return max(self.buildable_depth_m, 0.0)

    @property
    def buildable_area_m2(self) -> float:
        return round(max(self.buildable_width_m, 0.0) * max(self.buildable_depth_m, 0.0), 2)

    @property
    def near_setback_m(self) -> float:
        """The setback on the canonical y=0 edge — which is the STREET edge for every frontage.

        The engine draws every parcel with the street along y=0: the parking bays stand there, the
        entrance walk starts there, the front door sits on the footprint's y=min edge, and C10/C11
        check exactly that. Nothing rotates the drawing for a SOUTH or WEST frontage — there is no
        compass on the plan and no flip anywhere in the pipeline — so the setback at y=0 is the
        FRONT setback for all four frontages. This used to return the REAR setback for SOUTH/WEST,
        on the theory that the parcel was "presented flipped"; it was not, and the effect was a
        house placed 4.0 m from the street instead of 5.5 m with the front yard at the back, and
        (until `front_band_m`) the parking bays 1 m inside the house. The orientation support that
        IS real is the width/depth swap for EAST/WEST in `derive`.
        """
        return self.front_setback_m

    @property
    def far_setback_m(self) -> float:
        """The setback on the far edge (canonical y=max) — the rear one, for every frontage."""
        return self.rear_setback_m

    def buildable_origin_m(self) -> tuple[float, float]:
        """Where the buildable rectangle starts inside the canonical plot: one side setback in from
        the west edge, one front setback in from the street edge at y=0."""
        return (self.side_setback_m, self.near_setback_m)


def behind_parking_band(site: SiteGeometry, parking_spaces: int, bay_depth_m: float) -> SiteGeometry:
    """The same site with its street-side setback raised to one parking bay's depth.

    The bays stand perpendicular to the street in the band the house must leave free
    (`vertical_slice.site.front_band_m`), so an outline offered by the ENGINE has to fit the
    depth BEHIND that band, not merely behind the setback. Without this the engine offers — and
    plans — an outline that ends past the rear of the parcel on a plot the person's own outline
    was refused on. No parking, or a setback already deeper than a bay: the site is returned
    unchanged.
    """
    if parking_spaces <= 0 or site.near_setback_m >= bay_depth_m:
        return site
    return replace(site, front_setback_m=bay_depth_m)


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
class ConsumedAxis:
    """One parcel axis that the setbacks use up on their own, described in the person's own terms.

    The comparison happens in the CANONICAL frame, because that is the frame the setbacks are
    applied in — but an east/west frontage swaps the axes, so the canonical depth is the number the
    person entered as the plot's WIDTH. `plot_label` is resolved from the frontage for exactly that
    reason: naming the wrong field would send someone to correct a dimension that is already right.
    """

    axis: str                 #: "DEPTH" | "WIDTH", in the canonical frame
    plot_label: str           #: the field the person filled in, ready for a "גדול מ..." sentence
    plot_dimension_m: float
    setback_label: str
    setback_total_m: float

    @property
    def comparator(self) -> str:
        """Equal is not greater. A 9.50 m plot against 9.50 m of setback leaves exactly nothing."""
        return "גדול מ" if self.setback_total_m > self.plot_dimension_m else "שווה ל"


def consumed_axes(site: SiteGeometry) -> list[ConsumedAxis]:
    """Every axis with no room left in it. Empty exactly when `has_buildable_area` is True.

    Both read the same rounded buildable dimensions, so a parcel can never be refused for having no
    buildable area and then have no axis to blame for it.
    """
    axes: list[ConsumedAxis] = []
    depth_setbacks = round(site.front_setback_m + site.rear_setback_m, 2)
    width_setbacks = round(2 * site.side_setback_m, 2)
    frontage_runs_along_width = site.street_facing_side in (StreetSide.north, StreetSide.south)

    if site.buildable_depth_m <= 0:
        axes.append(ConsumedAxis(
            axis="DEPTH",
            plot_label="עומק המגרש" if frontage_runs_along_width else "רוחב המגרש",
            plot_dimension_m=site.canonical_depth_m,
            setback_label="סך הנסיגות הקדמית והאחורית",
            setback_total_m=depth_setbacks))
    if site.buildable_width_m <= 0:
        axes.append(ConsumedAxis(
            axis="WIDTH",
            plot_label="רוחב המגרש" if frontage_runs_along_width else "עומק המגרש",
            plot_dimension_m=site.canonical_width_m,
            setback_label="סך הנסיגות משני הצדדים",
            setback_total_m=width_setbacks))
    return axes


def no_buildable_area_message(site: SiteGeometry) -> str | None:
    """Why this parcel has no buildable region, or `None` when it has one.

    Says the CAUSE — these setbacks against this side of this parcel — rather than reporting the
    subtraction's negative result as though it were a dimension. It names the two numbers the person
    can actually change and, deliberately, makes no claim about the house: nothing here was measured
    against the programme, so nothing here can say the programme is impossible.
    """
    axes = consumed_axes(site)
    if not axes:
        return None
    causes = " ".join(
        f"{axis.setback_label} הוא {axis.setback_total_m:.2f} מ׳, "
        f"{axis.comparator}{axis.plot_label} {axis.plot_dimension_m:.2f} מ׳."
        for axis in axes)
    return (
        f"אין אזור בנייה: {causes} "
        f"המגרש הוא {site.plot_width_m:.2f} × {site.plot_depth_m:.2f} מ׳, ונסיגות הדמו הן "
        f"חזית {site.front_setback_m:.2f}, אחורית {site.rear_setback_m:.2f}, "
        f"צדדים {site.side_setback_m:.2f} מ׳. "
        f"אפשר לעדכן את מידות המגרש או את הנחות הנסיגה — שתי האפשרויות זמינות במסך הקודם. "
        f"אין בכך קביעה על הבית או על התוכנית עצמם: הם לא נבדקו כאן כלל. "
        f"{SETBACK_DISCLAIMER}")


def no_buildable_area_detail(site: SiteGeometry) -> str:
    """The engineering line for the log. Reports the SHORTFALL, never a negative dimension."""
    return "; ".join(
        f"canonical {axis.axis.lower()} {axis.plot_dimension_m:.2f} m vs "
        f"{axis.setback_total_m:.2f} m of setback"
        for axis in consumed_axes(site))


def buildable_dimensions_he(site: SiteGeometry) -> str:
    """A buildable rectangle for a Hebrew sentence — or the words for not having one."""
    if not site.has_buildable_area:
        return "אין אזור בנייה"
    return f"{site.buildable_width_m:.2f} × {site.buildable_depth_m:.2f} מ׳"


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
            f"({no_buildable_area_detail(site)})"))
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


#: Proportions to offer, best first. NOT an even spread across what geometry allows — that is what
#: the previous version did, and a 1440-scenario scan showed where it put people:
#:
#:     ratio 0.90-1.10   74.5% of plans succeed        ratio <0.60   16.1%
#:     ratio 1.10-1.30   52.5%                         ratio >1.60   19.0%
#:
#: and 39% of everything offered landed in those two extremes. For a 3-bedroom house with a safe
#: room, every single offer above ratio 1.3 failed — 66 of 66. The planner builds a west column |
#: hall spine | east column, and that parti needs a roughly square rectangle; an even spread across
#: a long parcel hands people outlines it cannot use.
#:
#: These four span 0.75-1.45 — real variety, all of it inside the bands that actually plan.
PREFERRED_RATIOS = (0.95, 1.15, 0.75, 1.45)


def feasible_options(site: SiteGeometry, area_m2: float,
                     count: int = OPTION_COUNT) -> list[tuple[float, float]]:
    """Up to `count` (width, depth) outlines of the requested area, all of which FIT, best first.

    Two filters, in order. GEOMETRY decides what is possible: `feasible_width_range_m` gives the
    widths at which this exact area fits inside the buildable rectangle. PLANNABILITY decides what
    is worth offering: `PREFERRED_RATIOS` picks proportions the planner can actually use, clipped to
    that interval. Where the site is generous all four come out at their preferred shapes; where it
    is tight they collapse toward whatever fits, and the caller still gets the best available rather
    than nothing.

    The area is never adjusted. An option is a different SHAPE of the requested area, never a
    smaller one.
    """
    interval = feasible_width_range_m(site, area_m2)
    if interval is None:
        return []
    low, high = interval

    def clip(width: float) -> float:
        return round(min(max(width, low), high) / 0.05) * 0.05

    wanted = [clip((area_m2 * ratio) ** 0.5) for ratio in PREFERRED_RATIOS[:count]]

    # Where the preferred shapes all clip to the same few widths — a tight site — fill the rest from
    # the interval so the person still sees the choice the geometry genuinely offers.
    if high - low >= 0.05:
        wanted += [clip(low + (high - low) * i / max(count - 1, 1)) for i in range(count)]

    out: list[tuple[float, float]] = []
    for width in wanted:
        w = round(width, 2)
        d = round(area_m2 / w, 2)
        if w > site.buildable_width_m + 1e-9 or d > site.buildable_depth_m + 1e-9:
            continue
        if any(abs(w - existing) < 0.05 for existing, _ in out):
            continue
        out.append((w, d))
        if len(out) == count:
            break
    return out


# --------------------------------------------------------- L massings on a rectangular plot

#: The arm the L parti plans a private wing in: 5 m wide — the width at which single-room rows
#: (a bedroom, a bath) sit inside their shape bands; a 6 m arm makes every lone row oversized and
#: needs row sharing (measured, `docs/L_PARTI_REPORT.md`). The parti trims the arm's LENGTH itself;
#: 9.5 m is what three private rows (master suite, two bedrooms) need at their floors.
L_ARM_WIDTH_M = 5.0
L_ARM_DEPTH_M = 9.5
#: The primary wing is offered as deep as the site allows up to this, so the public band has room
#: beyond the seam: an open-plan LDK stacked needs ~9.5 m past the arm.
L_PRIMARY_MAX_DEPTH_M = 20.0
#: The primary must be at least this wide for a band of public rooms (column beside the hall plus
#: the hall, with the living room's minimum short side).
L_PRIMARY_MIN_WIDTH_M = 6.0


@dataclass(frozen=True)
class LMassing:
    """Two wings carved from the buildable rectangle at the requested area: a primary
    `primary_w x primary_d` and an arm `arm_w x arm_d` east of it, flush with the primary's rear
    (`arm_end = "rear"`: the public band takes the street) or its street end (`"front"`: the band
    faces the garden). Not a shape a person picks — a massing the engine tries beside its
    rectangles, and shows only when a two-wing plan validates."""

    primary_w_m: float
    primary_d_m: float
    arm_w_m: float
    arm_d_m: float
    arm_end: str   # "rear" | "front"

    @property
    def bbox_w_m(self) -> float:
        return round(self.primary_w_m + self.arm_w_m, 2)

    @property
    def bbox_d_m(self) -> float:
        return self.primary_d_m

    @property
    def area_m2(self) -> float:
        return round(self.primary_w_m * self.primary_d_m + self.arm_w_m * self.arm_d_m, 2)

    def ring_points(self, x0: float, y0: float) -> list[tuple[float, float]]:
        """The L's outline, counter-clockwise, with the primary's north-west corner at (x0, y0)
        and the street at y = min. The notch is the corner the arm does not reach."""
        pw, ph, sw, sh = self.primary_w_m, self.primary_d_m, self.arm_w_m, self.arm_d_m
        if self.arm_end == "rear":      # arm along the rear part of the east side
            return [(x0, y0), (x0 + pw, y0), (x0 + pw, y0 + ph - sh), (x0 + pw + sw, y0 + ph - sh),
                    (x0 + pw + sw, y0 + ph), (x0, y0 + ph)]
        return [(x0, y0), (x0 + pw + sw, y0), (x0 + pw + sw, y0 + sh), (x0 + pw, y0 + sh),
                (x0 + pw, y0 + ph), (x0, y0 + ph)]


def _grid(value_m: float) -> float:
    return round(round(value_m / 0.05) * 0.05, 2)


def l_massings(site: SiteGeometry, area_m2: float) -> list[LMassing]:
    """The L massings of the requested area that fit the buildable rectangle — arm at the rear and
    arm at the front — or none.

    The arm is fixed (`L_ARM_WIDTH_M x L_ARM_DEPTH_M`, shortened to the site's depth); the primary
    takes the remaining area, as deep as the site allows up to `L_PRIMARY_MAX_DEPTH_M`, and must
    still be at least `L_PRIMARY_MIN_WIDTH_M` wide. One more condition is geometric, not
    architectural: the adapter decomposes the L into its largest inscribed rectangle first, so the
    primary column must be larger than the full-width strip along the arm's length — otherwise the
    adapter's primary is that strip, the "arm" sits north or south of it, and the parti refuses.
    The area is never reduced: an L that cannot hold the request is not offered.
    """
    if not site.has_buildable_area or area_m2 <= 0:
        return []
    bw, bd = site.buildable_width_m, site.buildable_depth_m
    sw = L_ARM_WIDTH_M
    if sw >= bw:
        return []
    # A smaller house gets a shorter arm (two private rows rather than three) before it gets no L
    # at all; the parti trims the arm further on its own.
    for arm_len in (L_ARM_DEPTH_M, 8.5, 7.5):
        sh = _grid(min(arm_len, bd))
        primary_area = area_m2 - sw * sh
        if primary_area <= 0:
            continue
        ph = _grid(min(bd, L_PRIMARY_MAX_DEPTH_M))
        pw = _grid(primary_area / ph)
        if pw + sw > bw + 1e-9:
            # Too wide at that depth: only a deeper primary could hold the area, and the site has
            # none — a shorter arm would only make the primary wider still.
            return []
        if pw < L_PRIMARY_MIN_WIDTH_M:
            # Too narrow for a public band: a shallower primary — never shallower than the arm plus
            # the band's own need.
            ph = _grid(max(sh + 6.5, primary_area / L_PRIMARY_MIN_WIDTH_M))
            pw = _grid(primary_area / ph)
            if ph > bd + 1e-9 or pw + sw > bw + 1e-9 or pw < L_PRIMARY_MIN_WIDTH_M - 1e-9:
                continue
        if pw * ph <= (pw + sw) * sh + 1e-9:
            continue
        return [LMassing(pw, ph, sw, sh, "rear"), LMassing(pw, ph, sw, sh, "front")]
    return []

