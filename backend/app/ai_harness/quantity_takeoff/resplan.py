"""#265 — the AC-5 demonstration: the repository's own 19 real plans, offered as a reference, and
refused.

#263 measured that across all 179 real rooms of the 19 ResPlan plans the stated `area_m2` equals
the shoelace area of the room's own polygon to 0.00061299 m2. So offering that field as the
reference for flooring area or ceiling paintable area would compare a polygon's area with the same
polygon's area and report an **identity as an accuracy**. The Issue asks for the harness to be
fed exactly this and to decline.

Two arms, because a guard that only reads declarations is a guard that trusts them:

  * **as_graded** -- the plans described honestly. ResPlan publishes the area; its own paper
    documents no methodology for validating the pixel-to-metre scale, so P3 is absent; there is no
    stated convention, no height, no finish and no door width. Grade `DERIVED`, method
    `PUBLISHER_COMPUTED`. R1 alone refuses it.
  * **optimistic** -- the same number offered in the strongest form an advocate could claim for it:
    grade `STATED`, method `DESIGN_DRAWING_DIMENSION`, a full V6 independence statement, a declared
    `INTERNAL_CLEAR` convention and a stated scale. **R1 raises nothing. R2 must refuse it anyway**,
    on the residual alone. That arm is the real test of the guard.

What this module deliberately does NOT do: read a door width off a door polygon. ResPlan lists the
doors but states no width, and a width measured off the supplied geometry is precisely the kind of
figure this harness refuses to treat as an input measurement. So the doors are carried with
`width=None` and F4 abstains -- which is the honest answer and is itself part of the result.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.ai_harness.quantity_takeoff.frozen import (
    Material,
    MeasurementConvention,
    MeasurementMethod,
    Reliability,
)
from app.ai_harness.quantity_takeoff.schema import (
    Measured,
    OpeningKind,
    OpeningRecord,
    Provenance,
    ReferenceProject,
    ReferenceValue,
    RoomRecord,
    Surface,
)

PLANS_DIR = (Path(__file__).resolve().parents[3] / "tests" / "spikes" / "fixtures"
             / "geometry_shapes" / "plans")

SYNTHETIC_FIXTURES = frozenset({"synthetic-spine-01"})
REAL_SOURCE_DATASET = "ResPlan"
EXPECTED_REAL_PLANS = 19
EXPECTED_REAL_ROOMS = 179

CITATION = "ResPlan, Abouagour & Garyfallidis 2025, arXiv 2508.14006"
LICENCE = "CC BY 4.0"

AS_GRADED = "as_graded"
OPTIMISTIC = "optimistic"
ARMS = (AS_GRADED, OPTIMISTIC)


def load_real_plans() -> dict[str, dict]:
    """The 19 real plans, keyed by file stem. The synthetic fixture is excluded by NAME and,
    independently, by its PROVENANCE; the two must agree and exactly 19 must remain. Lifted from
    #242's R1, which established the pattern for the same fixture directory."""
    out: dict[str, dict] = {}
    seen_synthetic: set[str] = set()
    for path in sorted(PLANS_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        ref = data["plan_reference"]
        source = ref["provenance"]["source_dataset"]
        by_name = path.stem in SYNTHETIC_FIXTURES
        by_source = source != REAL_SOURCE_DATASET
        if by_name != by_source:
            raise ValueError(f"{path.name}: name says synthetic={by_name}, provenance says {source!r}")
        if by_name:
            seen_synthetic.add(path.stem)
            continue
        out[path.stem] = ref
    if seen_synthetic != set(SYNTHETIC_FIXTURES):
        raise ValueError(f"synthetic fixture(s) not found: {sorted(SYNTHETIC_FIXTURES - seen_synthetic)}")
    if len(out) != EXPECTED_REAL_PLANS:
        raise ValueError(f"expected {EXPECTED_REAL_PLANS} real plans, found {len(out)}")
    return out


def _provenance(arm: str, units: str) -> Provenance:
    if arm == AS_GRADED:
        return Provenance(
            source="ResPlan (Abouagour & Garyfallidis)",
            citation=CITATION,
            method=MeasurementMethod.PUBLISHER_COMPUTED,
            units=units,
            revision="arXiv v1, 2025",
            reliability=Reliability.DERIVED,
            independence=("published by ResPlan, outside this repository; the publisher computed it "
                          "from their own vectorised geometry and no independent measurement "
                          "exists"),
        )
    return Provenance(
        source="ResPlan (Abouagour & Garyfallidis)",
        citation=CITATION,
        method=MeasurementMethod.DESIGN_DRAWING_DIMENSION,
        units=units,
        revision="arXiv v1, 2025",
        reliability=Reliability.STATED,
        independence=("published by a third party before this work began; it originates in no "
                      "artifact of this repository and in no calculation performed here"),
    )


def _width_of_thin_polygon(poly: list) -> float:
    """The long side of a door's thin rectangle. Used ONLY to report, in the results, how large the
    deduction would have been -- never offered as a P6 input, because a width read off the supplied
    geometry is not a stated measurement."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return max(max(xs) - min(xs), max(ys) - min(ys))


def as_reference_project(plan_id: str, ref: dict, arm: str) -> ReferenceProject:
    """One ResPlan plan, dressed as a reference project with its own `area_m2` offered as the
    reference for the two area materials."""
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}")
    area_prov = _provenance(arm, "m2")

    rooms = tuple(
        RoomRecord(
            id=r["id"],
            name=r["type"],
            polygon=tuple((float(x), float(y)) for x, y in r["polygon"]),
            stated_area=Measured(float(r["area_m2"]), area_prov),
            # P5 is left to the polygon; ResPlan states no perimeter.
            # P8 wall height: ABSENT. 0 of 20 fixtures carry one (#263) and a quotient is forbidden.
            # P10 finishes: ABSENT. 0 of 20 fixtures carry a material, finish or paint field.
        )
        for r in ref["rooms"]
    )

    openings: list[OpeningRecord] = []
    for d in ref.get("doors", []):
        openings.append(OpeningRecord(
            id=d["id"],
            kind=OpeningKind.DOOR,
            room_ids=tuple(d.get("room_ids", ())),
            surface=Surface.WALL,
            # P6 width: ABSENT ON PURPOSE. ResPlan states none, and reading it off the door polygon
            # would be a figure computed from the supplied geometry.
        ))
    for w in ref.get("windows", []):
        rid = w.get("room_id")
        openings.append(OpeningRecord(
            id=w["id"],
            kind=OpeningKind.WINDOW,
            room_ids=(rid,) if rid else (),
            surface=Surface.WALL,
        ))

    references: list[ReferenceValue] = []
    for r in ref["rooms"]:
        for material in (Material.FLOORING_AREA, Material.CEILING_PAINT_AREA):
            references.append(ReferenceValue(
                material=material,
                scope=r["id"],
                value=float(r["area_m2"]),
                provenance=area_prov,
                # The optimistic arm declares nothing about the class, exactly as an advocate would
                # not: R1 then has only the method to go on, and in that arm the method is clean.
            ))

    scale = None
    thickness = None
    convention = MeasurementConvention.UNSTATED
    if arm == OPTIMISTIC:
        d = ref.get("derived", {})
        if "scale_m_per_px" in d:
            scale = Measured(float(d["scale_m_per_px"]), _provenance(arm, "m"))
        if "wall_thickness_m" in d:
            thickness = Measured(float(d["wall_thickness_m"]), _provenance(arm, "m"))
        convention = MeasurementConvention.INTERNAL_CLEAR

    return ReferenceProject(
        project_id=f"resplan-{plan_id}",
        publisher="ResPlan",
        licence=LICENCE,
        rooms=rooms,
        openings=tuple(openings),
        scale=scale,
        wall_thickness=thickness,
        convention=convention,
        opening_schedule_complete=False,
        distinguishes_finishes=False,
        references=tuple(references),
    )


def projects(arm: str) -> list[ReferenceProject]:
    plans = load_real_plans()
    return [as_reference_project(pid, ref, arm) for pid, ref in sorted(plans.items())]
