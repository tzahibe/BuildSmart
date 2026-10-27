"""#267 (ROOT #262) — the Entrance Lodge's geometry, taken off the FIGURED GROUND PLAN.

This module is the one thing that makes step 3's comparison real.

#265 handed the harness Fletcher's own dimension columns as **both** the geometry and the
reference, and the self-validation guard refused all three ceiling comparisons at a residual of
**exactly 0.0**. It was right to: a takeoff cannot validate a calculation that starts from the
takeoff's own dimensions. The guard is not weakened here and nothing frozen is edited. What
changes is the *input*: the room geometry now comes from **Plate 8, the Ground Plan**, read off the
page image, figure by figure, with the plate, the leaf and the pair of wall faces each figure runs
between recorded in
`docs/reports/construction-intelligence/data/plate8-ground-plan-geometry.json`.

**The one rule.** A printed figure is the only thing allowed to supply a length. A pixel
measurement on the scan decides only *which pair of drawn wall faces a printed figure runs
between*; it never supplies a value and never overrides a figure. No coordinate produced here
comes from a pixel count. Where the plate figures nothing, the room is **absent** — it carries no
polygon, no stated area and no stated perimeter, and the formulas abstain. Nothing is borrowed
from the bill.

**Two rooms of three abstain, and the heights abstain everywhere.** The Sitting Room's
west-to-east dimension is figured nowhere on the plate (the bill's 14'0" may not be borrowed), and
ROOM_324B is both unidentified on the transcribed pages and unclosable from the plate. And across
**all ten plates, both sections included, no height is figured at all** — the 8'0" the plasterer
squares his walls at lives only in his dimension columns, so F2 abstains for every room. That is
#263's height finding reproduced on a complete professional drawing set.

The provenance grade of everything in this module is **STATED / DESIGN_DRAWING_DIMENSION**, never
VERIFIED: #263 V2 calls a design dimension an intent rather than a measurement, and the schema
refuses to let it grade higher.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.ai_harness.quantity_takeoff import fletcher as FL
from app.ai_harness.quantity_takeoff import frozen as F
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

DATA = (Path(__file__).resolve().parents[3].parent / "docs" / "reports"
        / "construction-intelligence" / "data" / "plate8-ground-plan-geometry.json")

#: Exact by definition (international foot, 1959). A unit conversion is not a measurement.
FT_TO_M = FL.FT_TO_M
FT2_TO_M2 = FL.FT2_TO_M2

EXPECTED_LICENCE_URL = FL.EXPECTED_LICENCE_URL

PROJECT_ID = "fletcher-1923-entrance-lodge-PLATE8"


def load() -> dict:
    data = json.loads(DATA.read_text())
    if data["source"]["licenseurl"] != EXPECTED_LICENCE_URL:
        raise ValueError(f"plate8: licence is not the verified CC PD Mark 1.0: "
                         f"{data['source']['licenseurl']!r}")
    return data


def _plan_prov(units: str, cited: str) -> Provenance:
    """V1-V6 for a dimension **figured on Plate 8**.

    V2 is `DESIGN_DRAWING_DIMENSION` and V5 is therefore capped at `STATED`: #263 calls a design
    dimension an intent, not a measurement, and `Provenance.__post_init__` refuses to let it grade
    VERIFIED. That is the honest grade and it is why axis 1 stays unmeasured.
    """
    return Provenance(
        source="Banister Fletcher & H. P. Fletcher, Quantities, 9th ed., B. T. Batsford, 1923",
        citation=f"archive.org/details/banisterfletcherh.p.fletcher1923 — {cited}",
        method=MeasurementMethod.DESIGN_DRAWING_DIMENSION,
        units=units,
        revision="9th edition, 1923, Plate 8 (Ground Plan), leaf 516",
        reliability=Reliability.STATED,
        independence=("a dimension figured on the architect's ground plan and read from the page "
                      "image; it originates in no artifact of this repository, in no calculation "
                      "performed here, and in none of the plasterer's dimension columns, which is "
                      "the independence the comparison needs"),
    )


def _takeoff_prov(units: str, cited: str) -> Provenance:
    """V1-V6 for a quantity the 1923 plasterer actually booked. Unchanged from #265."""
    return Provenance(
        source="Banister Fletcher & H. P. Fletcher, Quantities, 9th ed., B. T. Batsford, 1923",
        citation=f"archive.org/details/banisterfletcherh.p.fletcher1923 — {cited}",
        method=MeasurementMethod.PROFESSIONAL_TAKEOFF,
        units=units,
        revision="9th edition, 1923, Chapter XXII (Proposed Entrance Lodge)",
        reliability=Reliability.STATED,
        independence=("taken off by a professional quantity surveyor in 1923 and published under "
                      "CC Public Domain Mark 1.0; it originates in no artifact of this repository "
                      "and in no calculation performed here"),
    )


def _rectangle(w_ft: float, d_ft: float) -> tuple[tuple[float, float], ...]:
    """A closed plan polygon in metres from two FIGURED imperial dimensions. The only arithmetic
    here is the exact foot-to-metre conversion."""
    w, d = w_ft * FT_TO_M, d_ft * FT_TO_M
    return ((0.0, 0.0), (w, 0.0), (w, d), (0.0, d))


def project(*, depth_reading: str = "chain") -> ReferenceProject:
    """The Entrance Lodge with its geometry taken off Plate 8.

    `depth_reading` selects which reading of the Scullery's north-to-south figure is used. The
    plate prints that dimension twice, and the two readings disagree by 16% — which is a finding,
    not a knob:

      * ``"chain"`` (the one used) — ``9'9"`` runs from the north wall's inner face to the
        Scullery/Yard partition, and the plate's second figure ``10'6"`` runs from the same
        partition to the north wall's **outer** face. The two differ by exactly the figured 9" of
        that wall and share their lower terminus, so the chain closes on printed figures alone.
      * ``"outer_to_outer"`` — the same ``9'9"`` read face-to-face across both walls, giving a
        clear of ``9'9" - 9" - 9" = 8'3"``. It fits the draughting to 1.3% but leaves the plate's
        own ``10'6"`` terminating on no drawn face.

    The second is reported as an **interpretation sensitivity** and is never aggregated. Neither
    reading reaches the frozen tolerance, which is the point.
    """
    data = load()
    pw = data["project_wide_figures"]
    scullery = next(r for r in data["rooms_derived"] if r["id"] == "SCULLERY")
    w_ft = float(scullery["clear_width_ew"]["value_ft"])
    if depth_reading == "chain":
        d_ft = float(scullery["clear_depth_ns"]["value_ft"])
        cite = (f"Plate 8, leaf 516 — {scullery['clear_width_ew']['figure_as_printed']} and "
                f"{scullery['clear_depth_ns']['figure_as_printed']}, the latter read as the chain "
                f"it closes with 10'6\"")
    elif depth_reading == "outer_to_outer":
        d_ft = float(scullery["clear_depth_ns_alternative_reading"]["value_ft"])
        cite = (f"Plate 8, leaf 516 — {scullery['clear_width_ew']['figure_as_printed']} and "
                f"9'9\" read outer face to outer face, less the two figured 9\" walls")
    else:  # pragma: no cover - a typo must not silently pick a reading
        raise ValueError(f"plate8: unknown depth_reading {depth_reading!r}")

    rooms: list[RoomRecord] = [
        # The one room Plate 8 closes. No wall height: see `heights_abstained` in the data file --
        # not one of the ten plates figures a height, both sections included.
        RoomRecord(id="SCULLERY", name="Scullery", polygon=_rectangle(w_ft, d_ft),
                   stated_area=None, stated_perimeter=None, wall_height=None),
        # Figured 10'0" one way and nothing the other. The bill squares it 14'0" x 10'0" and that
        # number is exactly what may not be borrowed.
        RoomRecord(id="SITTING_ROOM", name="Sitting Room", polygon=None,
                   stated_area=None, stated_perimeter=None, wall_height=None),
        # Unidentified on the transcribed pages, and unclosable from the plate either way.
        RoomRecord(id="ROOM_324B", name="(unnamed on the transcribed pages)", polygon=None,
                   stated_area=None, stated_perimeter=None, wall_height=None),
    ]

    # Plate 8 DRAWS three openings into the Scullery and figures the width of none of them, so
    # every one of them enters with `width=None` and `area=None`. F4 then abstains on
    # DOOR_WIDTH_NOT_STATED instead of treating a drawn doorway as solid wall, which is the whole
    # reason the record exists.
    openings: list[OpeningRecord] = []
    for i, o in enumerate(scullery["openings_visible_but_not_figured"]):
        kind = OpeningKind.WINDOW if "window" in o["what"] else OpeningKind.DOOR
        openings.append(OpeningRecord(id=f"SCULLERY-PLATE8-{i}", kind=kind,
                                      room_ids=("SCULLERY",), surface=Surface.WALL,
                                      width=None, area=None))

    # The reference quantities stay exactly what the 1923 plasterer booked, read from #265's own
    # transcription file. Nothing about them is changed here; only the geometry they are compared
    # against is now independent of them.
    takeoff = FL.load()
    references: list[ReferenceValue] = []
    for r in takeoff["rooms"]:
        cited = r["cited"]
        references.append(ReferenceValue(
            material=Material.CEILING_PAINT_AREA, scope=r["id"],
            value=r["ceiling_area_ft2"] * FT2_TO_M2, provenance=_takeoff_prov("m2", cited),
            reference_class=F.CalculationClass.PLAN_POLYGON_AREA))
        if "wall_net_ft2" in r:
            references.append(ReferenceValue(
                material=Material.WALL_PAINT_AREA, scope=r["id"],
                value=r["wall_net_ft2"] * FT2_TO_M2, provenance=_takeoff_prov("m2", cited),
                reference_class=F.CalculationClass.PERIMETER_TIMES_HEIGHT))
        if "skirting_run_ft" in r:
            references.append(ReferenceValue(
                material=Material.BASEBOARD_LENGTH, scope=r["id"],
                value=r["skirting_run_ft"] * FT_TO_M, provenance=_takeoff_prov("m", cited),
                reference_class=F.CalculationClass.PLAN_POLYGON_PERIMETER))

    return ReferenceProject(
        project_id=PROJECT_ID,
        publisher="B. T. Batsford (Banister Fletcher & H. P. Fletcher)",
        licence="CC Public Domain Mark 1.0 (archive.org licenseurl, re-verified 2026-10-27)",
        rooms=tuple(rooms),
        openings=tuple(openings),
        # P3. The plate carries a printed scale bar AND is fully figured; the figures are read
        # directly and the bar is deliberately not used, because a value scaled off a raster has
        # no member of `MeasurementMethod` to declare itself under.
        scale=Measured(1.0, _plan_prov("m", "Plate 8 is fully figured; dimensions are read from "
                                            "the printed figures, not scaled from the plate")),
        wall_thickness=Measured(
            pw["wall_thickness_internal_and_service_wing_in"]["value"] * 0.0254,
            _plan_prov("m", pw["wall_thickness_internal_and_service_wing_in"]["cited"])),
        convention=MeasurementConvention[pw["measurement_convention"]],
        # Not one opening width or opening area is figured on any plate.
        opening_schedule_complete=False,
        distinguishes_finishes=False,
        references=tuple(references),
    )


def heights_are_figured_on_no_plate() -> dict:
    """The plate-by-plate evidence for the single most consequential abstention in this project.

    It is returned as data rather than asserted in prose so the report and the test read the same
    record: ten plates, two of them sections, and not one figured height.
    """
    data = load()
    plates = data["source"]["plates_examined"]
    return {
        "plates_examined": len(plates),
        "plates_with_any_figure": [k for k, v in plates.items() if "NO figured" not in v],
        "sections_examined": [k for k, v in plates.items() if "Section" in v],
        "sections_with_any_figure": [k for k, v in plates.items()
                                     if "Section" in v and "NO figured" not in v],
        "finding": data["source"]["the_finding_about_heights"],
        "consequence": ("F2 wall paintable area abstains for every room of this project on "
                        "WALL_HEIGHT_NOT_STATED, and would abstain on "
                        "OPENING_SCHEDULE_NOT_COMPLETE as well"),
    }


def interpretation_sensitivity() -> dict:
    """What the Scullery's ceiling comparison becomes under the second reading of the plate's own
    north-to-south figure.

    **This is not a second accuracy claim and it is never aggregated.** It is reported because the
    two readings bracket the professional's quantity from opposite sides and NEITHER reaches the
    frozen tolerance — which says something about the source that one number alone would hide.
    """
    data = load()
    scullery = next(r for r in data["rooms_derived"] if r["id"] == "SCULLERY")
    takeoff = FL.load()
    ref_ft2 = next(r["ceiling_area_ft2"] for r in takeoff["rooms"] if r["id"] == "SCULLERY")
    ref = ref_ft2 * FT2_TO_M2
    out = {"material": Material.CEILING_PAINT_AREA.value, "scope": "SCULLERY",
           "reference_m2": ref,
           "reference_as_booked": "8'6\" x 7'0\" = 59.5 sq ft (p.324)",
           "tolerance_rel": F.TOLERANCE_REL[Material.CEILING_PAINT_AREA],
           "readings": []}
    w = float(scullery["clear_width_ew"]["value_ft"])
    for label, d, why in (
        ("chain (used in comparison A)", float(scullery["clear_depth_ns"]["value_ft"]),
         "9'9\" and 10'6\" share their lower terminus and differ by the figured 9\" north wall"),
        ("outer face to outer face (sensitivity only)",
         float(scullery["clear_depth_ns_alternative_reading"]["value_ft"]),
         "9'9\" read across both walls, less the two figured 9\" thicknesses"),
    ):
        computed = (w * d) * FT2_TO_M2
        out["readings"].append({
            "reading": label, "why": why,
            "clear_ft": [w, d], "computed_m2": computed,
            "absolute_error_m2": computed - ref,
            "percentage_error": F.percentage_error(Material.CEILING_PAINT_AREA, computed, ref),
            "within_frozen_tolerance": F.within_tolerance(
                Material.CEILING_PAINT_AREA, computed, ref),
        })
    out["conclusion"] = (
        "the two readings of the plate's own figure bracket the 1923 quantity from opposite sides "
        "and NEITHER is inside the frozen 2.0% tolerance, so no choice of reading rescues it: the "
        "disagreement is in the source, not in the arithmetic")
    return out
