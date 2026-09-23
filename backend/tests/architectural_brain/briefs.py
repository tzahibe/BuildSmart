"""3 FIXED benchmark briefs for the POC Architectural Brain demo (Issue #96).

Each brief names its own authoritative `SiteConstraints` — a plain rectangle for briefs 1/2, an L
(two adjacent safe rectangles the safe-geometry adapter offers as "primary" and "arm" — the ONLY
shape a genuinely TWO_WING alternative can come from) for brief 3 — and its own `ProgramSpec`.
Both factories are pure and deterministic: calling either twice returns an equal value, which is
what "re-rendered deterministically" (AC-3) rests on.

Every safe rectangle here leaves the SAME margins `app.vertical_slice.spec.PlotSpec`'s own
defaults assume for parking/garden/entrance drawing (`front_setback_m=5.5`, `side_setback_m=3.0`,
`rear_setback_m=4.0`, see `site.py`'s `front_band_m`/`PARKING_BAY_DEPTH_M=5.0`) — not because the
general-geometry safety check requires it (it re-checks containment against whatever region is
given here), but because every other fixture in `geometry_fixtures.py` does, and drifting from it
would be an unexplained, untested combination.

`street_facing_side` is DESCRIPTIVE ONLY here: this slice draws every parcel with the street along
the region's own y=0 edge (`app.demo.site_geometry.SiteGeometry`'s own docstring — "no compass on
the plan and no flip anywhere in the pipeline"), so a brief that names a street side is recorded
for the report's own narrative, not read by anything in `run_general`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from app.geometry_domain.booleans import difference
from app.geometry_domain.constraints import (
    ConstraintRole,
    GeometricConstraint,
    Parcel,
    SiteConstraints,
)
from app.geometry_domain.primitives import MultiRegion, Region, Ring
from app.geometry_domain.provenance import Authority, Provenance, Source
from app.vertical_slice.spec import LaundryDemand, LaundryRequirement, ProgramSpec

_SURVEYED = Provenance(Source.SURVEY, Authority.AUTHORITATIVE, ref="POC benchmark brief (#96)")
_PLANNED = Provenance(Source.REGULATION, Authority.AUTHORITATIVE, ref="POC benchmark brief (#96)")

Rect = tuple[float, float, float, float]


def _frame_setback(parcel_ring: Ring, keep_ring: Ring, cid: str = "setback") -> GeometricConstraint:
    frame = difference(MultiRegion.of(Region(parcel_ring)), MultiRegion.of(Region(keep_ring)))
    return GeometricConstraint(cid, ConstraintRole.SETBACK_REGION, frame, _PLANNED,
                               note="benchmark brief building line")


def _rectangle_site(name: str, plot: tuple[float, float], keep: Rect) -> SiteConstraints:
    parcel = Ring.rectangle(0, 0, plot[0], plot[1], prefix="p")
    keep_ring = Ring.rectangle(*keep, prefix="k")
    return SiteConstraints(
        parcel=Parcel(name, MultiRegion.of(Region(parcel)), _SURVEYED),
        constraints=(_frame_setback(parcel, keep_ring),),
    )


def _l_site(name: str, plot: tuple[float, float], keep: Rect, notch: Rect) -> SiteConstraints:
    """`keep` minus the corner `notch` — the adapter then offers two adjacent safe rectangles,
    the primary and the arm, exactly as `geometry_fixtures._l_site` does for the adapter's own
    tests."""
    parcel = Ring.rectangle(0, 0, plot[0], plot[1], prefix="p")
    keep_ring = Ring.rectangle(*keep, prefix="k")
    cut = GeometricConstraint(
        "notch", ConstraintRole.NO_BUILD_REGION,
        MultiRegion.of(Region(Ring.rectangle(*notch, prefix="n"))),
        _PLANNED, note="benchmark brief L massing notch",
    )
    return SiteConstraints(
        parcel=Parcel(name, MultiRegion.of(Region(parcel)), _SURVEYED),
        constraints=(_frame_setback(parcel, keep_ring), cut),
    )


def _z_site(name: str, plot: tuple[float, float], keep: Rect, notch_a: Rect,
           notch_b: Rect) -> SiteConstraints:
    """`keep` minus TWO corner notches — an offset (Z/staggered) massing where the adapter's own
    largest-rectangle-first decomposition (`safe_adapter.adapt`, greedy: extract the biggest
    valid rectangle, then the biggest in what remains) yields two candidates that are genuinely
    NON-mergeable siblings sharing a HORIZONTAL edge, rather than `_l_site`'s vertical-edge L
    (measured — see the module's own investigation in the Issue's report: a rectangle-minus-ONE-
    corner-notch L always lets ONE piece reach FULL depth on a PARTIAL width, whatever notch is
    chosen, which is the vertical-boundary shape `_l_site` already gives; getting a horizontal
    boundary instead needs the REAR piece's own width-range to be offset from, not a subset of,
    the FRONT piece's — hence two notches, one at each of the two OTHER corners)."""
    parcel = Ring.rectangle(0, 0, plot[0], plot[1], prefix="p")
    keep_ring = Ring.rectangle(*keep, prefix="k")
    cut_a = GeometricConstraint(
        "notch_a", ConstraintRole.NO_BUILD_REGION,
        MultiRegion.of(Region(Ring.rectangle(*notch_a, prefix="na"))),
        _PLANNED, note="benchmark brief Z massing notch A",
    )
    cut_b = GeometricConstraint(
        "notch_b", ConstraintRole.NO_BUILD_REGION,
        MultiRegion.of(Region(Ring.rectangle(*notch_b, prefix="nb"))),
        _PLANNED, note="benchmark brief Z massing notch B",
    )
    return SiteConstraints(
        parcel=Parcel(name, MultiRegion.of(Region(parcel)), _SURVEYED),
        constraints=(_frame_setback(parcel, keep_ring), cut_a, cut_b),
    )


@dataclass(frozen=True)
class BenchmarkBrief:
    brief_id: str
    title: str
    plot_size_m: tuple[float, float]
    street_facing_side: str
    bedrooms: int
    wet_rooms: int
    safe_room: bool
    open_plan: bool
    laundry: bool
    built_area_m2: float
    site_factory: Callable[[], SiteConstraints]
    note: str = ""
    #: `ProgramSpec.parking_spaces` — 2 (its own default) unless a brief overrides it. Brief 2
    #: overrides to 0 (see its own comment: the plot leaves no room for a 5 m parking-bay band
    #: without contradicting the owner's stated bedroom/wet-room/laundry counts).
    parking_spaces: int = 2

    def site_constraints(self) -> SiteConstraints:
        return self.site_factory()

    def program(self) -> ProgramSpec:
        return ProgramSpec(
            bedrooms=self.bedrooms,
            safe_room=self.safe_room,
            open_plan_living=self.open_plan,
            wet_rooms=self.wet_rooms,
            laundry=LaundryRequirement(
                demand=LaundryDemand.ROOM if self.laundry else LaundryDemand.NONE,
                source_text="laundry room" if self.laundry else ""),
            target_built_area_m2=self.built_area_m2,
            parking_spaces=self.parking_spaces,
        )


#: Brief 1 — the challenging family home: 4 bedrooms + SAFE_ROOM + 3 wet rooms, ~200 m2,
#: plot 17x30.5 m, street north. A plain rectangle (single wing): SPINE/FRONT_BAND/HUB_LOBBY
#: diversity, if the generator's own candidate pool offers it, is what this brief can show.
BRIEF_1 = BenchmarkBrief(
    brief_id="brief-1",
    title="Challenging family home (4BR + SAFE_ROOM + 3 wet rooms, ~200 m2)",
    plot_size_m=(17.0, 30.5),
    street_facing_side="NORTH",
    bedrooms=4, wet_rooms=3, safe_room=True, open_plan=False, laundry=False,
    built_area_m2=200.0,
    site_factory=lambda: _rectangle_site(
        "brief-1-family-home", plot=(17.0, 30.5), keep=(2.0, 5.5, 13.0, 21.0)),
)

#: Brief 2 — the owner's own brief: 4 bedrooms (3 + master ensuite), 2 wet rooms, laundry,
#: open plan, 130 m2, plot 15x17 m. "Master ensuite" is recorded as an ambition, not a hard
#: `WetRoomRequirement` — the engine's own ensuite-pairing heuristic decides which wet room hosts
#: which bedroom, same as any ordinary brief that only counts wet rooms. Street side was not named
#: by the owner; NORTH is this brief's own assumption, same convention as brief 1.
#:
#: `parking_spaces=0`: measured (see the module's own investigation in the Issue's report) —
#: `ProgramSpec`'s own default of 2 bays reserves a fixed 5 m-deep street-side band
#: (`site.PARKING_BAY_DEPTH_M`) that this plot's own 17 m depth cannot spare on top of the
#: 12.0-12.5 m the current engine's own room templates need for this exact bedroom/wet-room/
#: laundry mix — every strategy fell short by 0.08-0.7 m even at the plot's full width. Assuming
#: on-street parking (common on a narrow 15 m urban frontage) is the one input choice, applied
#: identically to the current-engine baseline and every brain-compiled alternative, that keeps
#: the owner's own stated programme intact rather than inventing a smaller one to fit.
BRIEF_2 = BenchmarkBrief(
    brief_id="brief-2",
    title="Owner's own brief (4BR incl. master ensuite, 2 wet rooms, laundry, open plan, 130 m2)",
    plot_size_m=(15.0, 17.0),
    street_facing_side="NORTH (assumed — not specified by the owner)",
    bedrooms=4, wet_rooms=2, safe_room=False, open_plan=True, laundry=True,
    built_area_m2=130.0,
    parking_spaces=0,
    site_factory=lambda: _rectangle_site(
        "brief-2-owner-brief", plot=(15.0, 17.0), keep=(2.0, 2.0, 11.0, 13.0)),
)

#: Brief 3 — a wide 5-bedroom home, 200 m2, plot 27x20.5 m. The wet-room count and safe-room were
#: not specified by the owner for this brief; 3 wet rooms (typical for 5 bedrooms) and no safe
#: room are this brief's own assumption.
#:
#: A Z/staggered site (front band 14x4 m north, rear block 13x10.5 m south, sharing a 7 m
#: HORIZONTAL overlap) rather than `_l_site`'s vertical-edge L — measured (see the module's own
#: investigation in the Issue's report): with 5 bedrooms + 3 wet rooms (8 private rooms total),
#: a single height-stacked private column needs ~18.9 m of depth (an invariant of the room mix,
#: not of how the stack is split) — far more than ANY rectangle this plot's own 14-14.5 m usable
#: depth (after the 5.5 m front parking band) can offer on EITHER a vertical-edge L's primary
#: (14.0 m) or arm (7.0 m). Splitting the 8 rooms into two PARALLEL columns either side of a
#: central hall (a genuine double-loaded corridor, `_compile_two_wing`'s own private layout for
#: this site) needs only ~8-8.5 m of WIDTH at any height from 10.5-14 m — but that central hall
#: cannot ALSO reach the vertical boundary of an L (it would have to be adjacent to both flanking
#: columns AND to an outside edge at once, which no linear column arrangement can do). A
#: HORIZONTAL boundary resolves this: the front wing's own entrance hall reaches down and touches
#: whichever single x-range the rear wing's own central hall lands in, because both are free to
#: sit anywhere along their own wing's width — solved and verified (`test_benchmark_briefs.py`,
#: `test_demo_alternatives.py`).
BRIEF_3 = BenchmarkBrief(
    brief_id="brief-3",
    title="Wide 5-bedroom home (200 m2, wide plot — assumed 3 wet rooms, no safe room)",
    plot_size_m=(27.0, 20.5),
    street_facing_side="NORTH (assumed — not specified by the owner)",
    bedrooms=5, wet_rooms=3, safe_room=False, open_plan=False, laundry=False,
    built_area_m2=200.0,
    site_factory=lambda: _z_site(
        "brief-3-wide-5br", plot=(27.0, 20.5), keep=(2.0, 5.5, 24.0, 14.5),
        notch_a=(23.0, 5.5, 3.0, 4.0), notch_b=(2.0, 9.5, 14.0, 10.5)),
)

BENCHMARK_BRIEFS: tuple[BenchmarkBrief, ...] = (BRIEF_1, BRIEF_2, BRIEF_3)
