"""Stage 3 — Site + parking + entrance facade.

Placement sequencing follows `PRIVATE_HOUSE_V1_ENGINE_DECISION.md`'s site ordering: parking is
decided ALONGSIDE footprint placement (both driven by the plot + setbacks), not after the
house is already drawn — parking lives entirely in the street-side band (`front_band_m`), so
it never competes with the footprint for buildable area, and the footprint is simply centered
in the remaining buildable envelope. Garden is an EXPLICIT classification of the plot's leftover
area (Correction 3 / geometry_core.model.OutdoorClassification), never an implicit remainder.

THE BAND IS NOT THE SETBACK. It used to be: bays were drawn at y=0 and the house at the front
setback, and "the bays are in front of the house" held only because the default setback (5.5 m)
happened to be deeper than a bay (5.0 m). When the default setback became 0 — a planning
determination this project does not make — the house moved to the street line and the bays were
drawn UNDER it, invisible on every plan. `front_band_m` is the depth the house must actually
leave, whichever of the two numbers is larger, and validation C18 refuses a plan where a bay and
the house overlap so that this can never again fail silently.

Everything here operates in the SAME grid-unit `Rect` type Geometry Core uses, in one shared
plot-absolute coordinate frame (y=0 at the street edge) — the wing's own solved rects (which
Geometry Core produces in a local 0,0-origin frame) are translated into this frame by
`place_footprint`, not recomputed.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import footprint as footprint_module
from .geometry_core.model import (
    OutdoorClassification,
    OutdoorRegion,
    Rect,
    m_to_u,
    u_to_m,
)
from .spec import ArchitecturalSpec

PARKING_BAY_WIDTH_M = 2.5
PARKING_BAY_DEPTH_M = 5.0   # PARAMETER · UNVERIFIED — plausible standard bay, not a sourced code value
PARKING_GAP_M = 0.3
ENTRANCE_SETBACK_FROM_SIDE_M = 1.0  # keep the front door off the very corner of the facade
#: The pedestrian walk's own width, shared by `build_entrance` and `entrance_x_clear_of_parking`
#: so the path that is DRAWN and the path that is kept off a bay are the same path.
_WALK_WIDTH_M = 1.2


@dataclass(frozen=True)
class EntranceWalk:
    """A straight pedestrian path from the street edge to the entrance door point."""
    door_point_u: tuple[int, int]
    path_rect: Rect  # a thin corridor from the street to the door, used for the connectivity check


#: WHAT THE DRAWING SAYS WHEN THE PARCEL IS NOT THERE (Issue #223). A plot rectangle drawn around
#: a house that nobody entered a parcel for is the most visible untruth a sheet can carry: it looks
#: exactly like a surveyed boundary. The product itself never gets here — `demo.scope.check_supported`
#: refuses a project with no authoritative parcel before anything is planned — so this is the
#: sentence for a caller that realizes geometry WITHOUT a parcel (a harness, a frozen case): the
#: rectangle is named a drawing margin, out loud, rather than passed off as the client's land.
NO_PARCEL_NOTICE = (
    "לא הוזן מגרש עבור התכנון הזה, ולכן המלבן שמסביב לבית הוא שולי שרטוט בלבד ואינו גבול מגרש. "
    "גם הגינה והחניה אינן מוצגות — אין מגרש שמהם לגזור אותן.")


@dataclass(frozen=True)
class SiteFrame:
    """THE PERSON'S OWN PARCEL, carried into a realizer (Issue #223).

    `site.build_site_plan` and `general_pipeline._site_plan_for` already build the production
    site from the brief's `ArchitecturalSpec` — the parcel the person entered, the setbacks that
    were applied to it, their parking count. The shape-agnostic realizer
    (`rectilinear_realizer._build_site`) had no way to be told any of it and so SYNTHESISED a plot
    from the footprint plus a 2 m skirt, with no parking and a garden that was only the crook of an
    L. This is the one value that closes the gap: the same four numbers, in grid units, in the one
    coordinate frame everything else already uses (y=0 at the street edge).

    `front_band_u` is `front_band_m` already resolved — the depth the house must leave at the
    street, which is the front setback or one parking bay, whichever is deeper. It is passed
    resolved rather than as a setback so this type never has to know about parking geometry.
    """

    plot: Rect
    front_band_u: int
    side_setback_u: int
    rear_setback_u: int
    parking: tuple[Rect, ...] = ()
    #: what the brief asked for, so a plan can disclose bays it could not draw
    parking_spaces_requested: int = 0

    def buildable_u(self) -> tuple[int, int]:
        """The land left for the building: the parcel minus the side setbacks, minus the street
        band and the rear setback. The SAME subtraction `spec.PlotSpec.buildable_size_m` and
        `buildable_size_with_parking_m` make, in units."""
        return (self.plot.w - 2 * self.side_setback_u,
                self.plot.h - self.front_band_u - self.rear_setback_u)

    def place(self, w_u: int, h_u: int) -> tuple[int, int]:
        """Where a `w_u` x `h_u` footprint sits in the parcel: centred across the buildable
        width, flush to the street-side band — `place_footprint`'s own convention, so a plan
        realized through this frame stands exactly where production would stand it."""
        buildable_w, _ = self.buildable_u()
        return (self.side_setback_u + max(0, (buildable_w - w_u) // 2), self.front_band_u)

    def overflow_m(self, w_u: int, h_u: int) -> tuple[float, float]:
        """How far a footprint of this size runs past the buildable envelope, in metres — (0, 0)
        when it fits. Disclosed on the plan rather than silently clamped away."""
        buildable_w, buildable_h = self.buildable_u()
        return (round(u_to_m(max(0, w_u - buildable_w)), 2),
                round(u_to_m(max(0, h_u - buildable_h)), 2))


@dataclass(frozen=True)
class SitePlan:
    plot: Rect
    #: The building's BOUNDING BOX. For a one-wing house this is the footprint itself; for a
    #: multi-wing one it is the rectangle the wings span — what the building line, the frame and
    #: the entrance walk are measured against. `wings` is the footprint proper.
    footprint: Rect
    footprint_offset_u: tuple[int, int]
    parking: tuple[Rect, ...]
    entrance: EntranceWalk
    garden: tuple[OutdoorRegion, ...]
    #: The footprint as the wings that make it up (`footprint.py`). Defaults to the one rectangle
    #: `footprint` names, so every existing constructor call describes the same site.
    wings: tuple[Rect, ...] = ()
    #: Something about THIS site the person must read before the drawing (Issue #223) — a plot
    #: that is a drawing margin rather than their parcel, a footprint that runs past the buildable
    #: envelope, parking the brief asked for that this site could not seat. `None` — the default,
    #: and what every site built from a real `ArchitecturalSpec` carries — means the drawing shows
    #: the parcel, the setbacks and the parking the brief actually gave.
    notice: str | None = None

    def __post_init__(self) -> None:
        if not self.wings:
            object.__setattr__(self, "wings", (self.footprint,))


def front_band_m(spec: ArchitecturalSpec) -> float:
    """Depth of the street-side band the house must leave free, measured from y=0.

    The front setback when there is no parking; otherwise the deeper of the setback and one
    parking bay, because the bays stand perpendicular to the street in that band and a house
    placed closer than a bay is deep would sit on top of them. The setback is a planning
    assumption the person can lower to 0; the bay depth is what a car needs, and lowering the
    setback does not shrink the car.
    """
    if spec.program.parking_spaces <= 0:
        return spec.plot.front_setback_m
    return max(spec.plot.front_setback_m, PARKING_BAY_DEPTH_M)


def buildable_size_with_parking_m(spec: ArchitecturalSpec) -> tuple[float, float]:
    """The buildable envelope once the parking band is taken out of the plot's depth."""
    buildable_w_m, _ = spec.plot.buildable_size_m()
    return buildable_w_m, spec.plot.depth_m - front_band_m(spec) - spec.plot.rear_setback_m


def place_footprint(spec: ArchitecturalSpec, footprint_w_m: float, footprint_h_m: float) -> tuple[int, int]:
    """Center the footprint in the plot's buildable envelope, flush to the street-side band.
    Returns the (x_u, y_u) offset to add to every wing-local rect to place it in plot-absolute
    coordinates."""
    origin_x_m, _ = spec.plot.buildable_origin_m()
    origin_y_m = front_band_m(spec)
    buildable_w_m, buildable_h_m = buildable_size_with_parking_m(spec)
    if footprint_w_m > buildable_w_m + 1e-6 or footprint_h_m > buildable_h_m + 1e-6:
        raise ValueError(
            f"footprint {footprint_w_m}x{footprint_h_m} m does not fit the buildable envelope "
            f"{buildable_w_m:.2f}x{buildable_h_m:.2f} m (plot {spec.plot.width_m}x{spec.plot.depth_m} "
            f"m minus setbacks and the {front_band_m(spec):.2f} m street-side band for parking) — "
            f"enlarge the plot or shrink the concept footprint."
        )
    offset_x_m = origin_x_m + (buildable_w_m - footprint_w_m) / 2.0
    offset_y_m = origin_y_m  # flush to the front building line; remaining depth slack goes to the rear garden
    return m_to_u(offset_x_m), m_to_u(offset_y_m)


def translate_rects(rects: dict[str, Rect], offset_u: tuple[int, int]) -> dict[str, Rect]:
    ox, oy = offset_u
    return {zid: Rect(r.x + ox, r.y + oy, r.w, r.h) for zid, r in rects.items()}


def build_parking(spec: ArchitecturalSpec) -> tuple[Rect, ...]:
    """`spec.program.parking_spaces` bays, side by side, flush against the street edge (y=0)
    within the front setback band — so "parking connected to street" holds by construction,
    and is still checked explicitly in `validation.py`, not just assumed."""
    bays = []
    bay_w_u, bay_d_u = m_to_u(PARKING_BAY_WIDTH_M), m_to_u(PARKING_BAY_DEPTH_M)
    gap_u = m_to_u(PARKING_GAP_M)
    x_u = m_to_u(spec.plot.side_setback_m)
    for _ in range(spec.program.parking_spaces):
        bays.append(Rect(x_u, 0, bay_w_u, bay_d_u))
        x_u += bay_w_u + gap_u
    return tuple(bays)


def build_entrance(footprint: Rect, entrance_x_u: int) -> EntranceWalk:
    """A door point centered on the given x within the footprint's street-facing (N, y=min)
    edge, plus a thin walk rect from the street to that point."""
    door_point = (entrance_x_u, footprint.y)
    walk_width_u = m_to_u(_WALK_WIDTH_M)
    path = Rect(entrance_x_u - walk_width_u // 2, 0, walk_width_u, footprint.y)
    return EntranceWalk(door_point, path)


def classify_garden(spec: ArchitecturalSpec | None, plot: Rect, footprint: Rect,
                     parking: tuple[Rect, ...],
                     wings: tuple[Rect, ...] = ()) -> tuple[OutdoorRegion, ...]:
    """The plot's leftover area, EXPLICITLY classified GARDEN (Correction 3) — not because it
    is unclaimed, but because a deliberate site-planning decision was made that all leftover
    plot area in this vertical slice is garden (no driveway/terrace carve-outs beyond parking
    are in this scope). Represented as up to 3 non-overlapping bands (front-of-house strip
    beside parking, side yards, rear yard) rather than one bounding-box remainder, since a
    single rectangle would overlap the footprint.

    `footprint` is the building's bounding box; `wings` the rectangles that make it up. The bands
    are drawn around the box exactly as before; whatever the box holds that no wing covers — the
    crook of an L — is appended as garden too, so the plot is still accounted for to the last
    cell. Classifying that crook as a terrace or an entry court is a site decision for the parti
    that produces it; until then it is garden, said explicitly, never "left over".

    `spec` is accepted and read by nothing here — the bands are a function of the plot, the
    footprint, the wings and the bays alone. It stays in the signature because every existing
    caller passes it positionally; `None` is the honest value for a caller that has the parcel
    (as a `SiteFrame`) but not the whole spec.
    """
    regions = []
    # Rear yard: full plot width, from the footprint's south edge to the plot's south edge.
    if plot.y2 > footprint.y2:
        regions.append(Rect(plot.x, footprint.y2, plot.w, plot.y2 - footprint.y2))
    # Side yards: from the footprint's north edge (building line) to its south edge, left/right
    # of the footprint, so they don't overlap the front setback's parking band.
    if footprint.x > plot.x:
        regions.append(Rect(plot.x, footprint.y, footprint.x - plot.x, footprint.h))
    if plot.x2 > footprint.x2:
        regions.append(Rect(footprint.x2, footprint.y, plot.x2 - footprint.x2, footprint.h))
    # Front strip: the setback band not occupied by parking (front-left of the parking row, if any).
    last_parking_x2 = max((p.x2 for p in parking), default=plot.x)
    if footprint.x2 > last_parking_x2 and footprint.y > 0:
        # occupies from the end of the parking row to the footprint's east edge, within the setback
        front_w = footprint.x2 - last_parking_x2
        if front_w > 0:
            regions.append(Rect(last_parking_x2, 0, front_w, footprint.y))
    # The crook: inside the bounding box, outside every wing. Empty for one wing.
    regions.extend(footprint_module.remainder_within_bbox(wings or (footprint,)))

    return tuple(
        OutdoorRegion(f"garden_{i}", (r,), OutdoorClassification.GARDEN)
        for i, r in enumerate(regions) if r.w > 0 and r.h > 0
    )


def build_site_plan(spec: ArchitecturalSpec, footprint_w_m: float, footprint_h_m: float,
                     entrance_local_x_u: int) -> SitePlan:
    plot = Rect(0, 0, m_to_u(spec.plot.width_m), m_to_u(spec.plot.depth_m))
    offset_u = place_footprint(spec, footprint_w_m, footprint_h_m)
    footprint = Rect(offset_u[0], offset_u[1], m_to_u(footprint_w_m), m_to_u(footprint_h_m))
    parking = build_parking(spec)
    entrance = build_entrance(footprint, offset_u[0] + entrance_local_x_u)
    garden = classify_garden(spec, plot, footprint, parking)
    return SitePlan(plot, footprint, offset_u, parking, entrance, garden)



def entrance_x_clear_of_parking(span: tuple[int, int], parking: tuple[Rect, ...],
                                fallback: int) -> int:
    """A point in the acceptable span whose WALK does not cross a parking bay.

    The walk runs straight from the street to the door, so a door chosen purely from the rooms can
    still put the path through a bay — which is exactly what C11 caught the moment the entrance
    stopped defaulting to the footprint's centre. Both constraints are real, so the point is chosen
    against both: scan the span at 5 cm and take the first clear position, preferring the middle so
    the walk stays central when nothing is in the way.

    With no bays the middle is always clear, so this returns the midpoint — byte-identical to the
    `(low + high) // 2` every caller used before it existed.
    """
    low, high = span
    walk_half = m_to_u(_WALK_WIDTH_M) // 2

    def clear(x: int) -> bool:
        walk = Rect(x - walk_half, 0, walk_half * 2, 1)
        return not any(walk.overlap_area_u(Rect(bay.x, 0, bay.w, 1)) > 0 for bay in parking)

    middle = (low + high) // 2
    for offset in range(0, high - low + 1):
        for x in (middle + offset, middle - offset):
            if low <= x <= high and clear(x):
                return x
    return fallback


def site_frame_for(spec: ArchitecturalSpec) -> SiteFrame:
    """The brief's own parcel as a `SiteFrame` (Issue #223) — the ONE place the spec's plot,
    setbacks and parking count become the frame a realizer can carry. Nothing is derived from the
    building: the same reason `demo.site_geometry.derive` takes no footprint argument."""
    return SiteFrame(
        plot=Rect(0, 0, m_to_u(spec.plot.width_m), m_to_u(spec.plot.depth_m)),
        front_band_u=m_to_u(front_band_m(spec)),
        side_setback_u=m_to_u(spec.plot.side_setback_m),
        rear_setback_u=m_to_u(spec.plot.rear_setback_m),
        parking=build_parking(spec),
        parking_spaces_requested=spec.program.parking_spaces,
    )
