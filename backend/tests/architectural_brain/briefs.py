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
BRIEF_2 = BenchmarkBrief(
    brief_id="brief-2",
    title="Owner's own brief (4BR incl. master ensuite, 2 wet rooms, laundry, open plan, 130 m2)",
    plot_size_m=(15.0, 17.0),
    street_facing_side="NORTH (assumed — not specified by the owner)",
    bedrooms=4, wet_rooms=2, safe_room=False, open_plan=True, laundry=True,
    built_area_m2=130.0,
    site_factory=lambda: _rectangle_site(
        "brief-2-owner-brief", plot=(15.0, 17.0), keep=(1.0, 5.0, 13.0, 11.10)),
)

#: Brief 3 — a wide 5-bedroom home, 200 m2, plot 27x20.5 m. The wet-room count and safe-room were
#: not specified by the owner for this brief; 3 wet rooms (typical for 5 bedrooms) and no safe
#: room are this brief's own assumption. An L site (primary 13x14 m + arm 10x7 m at the front,
#: flush to the street): the only shape this slice's adapter ever offers a SECOND wing for, which
#: is what a genuinely TWO_WING alternative needs (AC-1).
BRIEF_3 = BenchmarkBrief(
    brief_id="brief-3",
    title="Wide 5-bedroom home (200 m2, wide plot — assumed 3 wet rooms, no safe room)",
    plot_size_m=(27.0, 20.5),
    street_facing_side="NORTH (assumed — not specified by the owner)",
    bedrooms=5, wet_rooms=3, safe_room=False, open_plan=False, laundry=False,
    built_area_m2=200.0,
    site_factory=lambda: _l_site(
        "brief-3-wide-5br", plot=(27.0, 20.5),
        keep=(2.0, 5.5, 23.0, 14.0), notch=(15.0, 12.5, 10.0, 7.0)),
)

BENCHMARK_BRIEFS: tuple[BenchmarkBrief, ...] = (BRIEF_1, BRIEF_2, BRIEF_3)
