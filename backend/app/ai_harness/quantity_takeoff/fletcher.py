"""#265 — the concrete reference fixture: Banister Fletcher & H. P. Fletcher, *Quantities*,
9th ed. 1923, Chapter XXII, "Proposed Entrance Lodge".

CC **Public Domain Mark 1.0**, read from the item's own metadata API (`licenseurl`), and public
domain by age in the US and the UK. This is a **professional quantity takeoff**: a plasterer's
dimension paper room by room, with the opening deductions written out, the skirting as its own item
in running measure, ceiling plaster and whitening, and a separate Taking Off for Painter. It is the
first artefact in this work that supplies a reference quantity for the materials under test.

**What it validates, and what it does not.** This is the distinction the report draws as sharply as
it draws A from B:

  * Fletcher is a **designed exercise taken off by a professional**, not a measured building. So a
    comparison against it tests the owner's evaluation axes **2 to 5** -- geometric calculation,
    material quantity, completeness of inputs, provenance and auditability -- and it tests the
    **conventions and deductions** better than anything else available, because they are written
    out on the page.
  * It says **NOTHING about axis 1, source measurement accuracy.** Nobody measured this lodge; it
    was never built. Axis 1 still needs a real project, and no source found anywhere supplies one.

**The transcription.** Every figure comes from `docs/reports/construction-intelligence/data/
fletcher-1923-entrance-lodge.json`, read off the PAGE IMAGES -- the OCR of a three-column
dimension paper is unusable -- with the leaf and printed page recorded per item. Each transcribed
girth was checked against the sum of its own waste column and each squaring against the product of
its own dimension pair; a reading that did not reproduce the book's printed total was not recorded.
A figure that could not be read with confidence is ABSENT, and an absent figure makes the harness
abstain. Nothing here is inferred and nothing here is computed by BuildSmart.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.ai_harness.quantity_takeoff import formulas as FO
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
        / "construction-intelligence" / "data" / "fletcher-1923-entrance-lodge.json")

#: Exact by definition (international foot, 1959). A unit conversion is not a measurement and
#: introduces no inference; the imperial figure stays the primary record in the data file.
FT_TO_M = 0.3048
FT2_TO_M2 = 0.09290304

EXPECTED_LICENCE_URL = "http://creativecommons.org/publicdomain/mark/1.0/"


def load() -> dict:
    data = json.loads(DATA.read_text())
    if data["source"]["licenseurl"] != EXPECTED_LICENCE_URL:
        raise ValueError(f"fletcher: licence is not the verified CC PD Mark 1.0: "
                         f"{data['source']['licenseurl']!r}")
    return data


def _prov(units: str, cited: str) -> Provenance:
    """V1-V6 for a figure taken off Fletcher's own dimension paper.

    V5 is **STATED**, not VERIFIED: a professional took it off, the method is documented in the
    book's own method-of-measurement chapters, and nobody has independently checked it -- which is
    exactly #263's definition. It is **not** DERIVED, because it was not computed from geometry
    this harness supplied; it predates this work by a century.
    """
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


def project(*, geometry_from_takeoff: bool = True) -> ReferenceProject:
    """The Entrance Lodge as a `ReferenceProject`.

    `geometry_from_takeoff` is the switch the AC-5 demonstration turns:

      * **True** -- the room geometry (P1/P4/P5) is taken from the SAME dimension columns the
        reference quantities were squared from. The harness must then refuse the area comparisons
        as a `GEOMETRIC_IDENTITY`, because recomputing a quantity from the dimensions it was
        squared from is arithmetic, not accuracy. This is the honest default today.
      * **False** -- the geometry is withheld, so the harness abstains instead of computing. It is
        kept so the difference between "refuses to score" and "cannot compute" stays visible.

    Taking the room polygons off the FIGURED GROUND PLAN (Plate 8, leaf 516), independently of the
    dimension columns, is what would turn the first case into a real comparison. That is step 3's
    work and it is named in the report's section 9.
    """
    data = load()
    pj = data["project"]
    rooms: list[RoomRecord] = []
    openings: list[OpeningRecord] = []
    references: list[ReferenceValue] = []

    for r in data["rooms"]:
        cited = r["cited"]
        area_ft2 = r["ceiling_area_ft2"]
        # P4: the room's net plan area, as the takeoff squared it.
        stated_area = (Measured(area_ft2 * FT2_TO_M2, _prov("m2", cited))
                       if geometry_from_takeoff else None)
        # P5: the collected girth, BUT only where the book's own note says it is the whole room.
        # The Scullery's 20'9" is the rendered length, not the perimeter, and the data file says
        # so; offering it as a perimeter would be the harness inventing a measurement.
        per = None
        if geometry_from_takeoff and not r.get("wall_girth_is_partial", False):
            per = Measured(r["wall_girth_ft"] * FT_TO_M, _prov("m", cited))
        # P8: stated by the source, in the dimension columns and in the sections. Never a quotient.
        height = Measured(r["wall_height_ft"] * FT_TO_M, _prov("m", cited))
        rooms.append(RoomRecord(id=r["id"], name=r["name"], polygon=None,
                                stated_area=stated_area, stated_perimeter=per,
                                wall_height=height))

        # P6: door widths, where the deduction line states a door-sized opening and the data file
        # records which. P9 opening AREAS are stated for every deduction line.
        for i, w_ft in enumerate(r.get("door_widths_ft", [])):
            openings.append(OpeningRecord(
                id=f"{r['id']}-DOOR-{i}", kind=OpeningKind.DOOR, room_ids=(r["id"],),
                surface=Surface.WALL,
                width=Measured(w_ft * FT_TO_M, _prov("m", cited))))
        for i, d in enumerate(r.get("wall_deductions_ft2", [])):
            openings.append(OpeningRecord(
                id=f"{r['id']}-DDT-{i}", kind=OpeningKind.WINDOW, room_ids=(r["id"],),
                surface=Surface.WALL,
                area=Measured(d["total_ft2"] * FT2_TO_M2, _prov("m2", cited))))

        # The reference quantities the takeoff BOOKED.
        references.append(ReferenceValue(
            material=Material.CEILING_PAINT_AREA, scope=r["id"],
            value=area_ft2 * FT2_TO_M2, provenance=_prov("m2", cited),
            reference_class=F.CalculationClass.PLAN_POLYGON_AREA))
        if "wall_net_ft2" in r:
            references.append(ReferenceValue(
                material=Material.WALL_PAINT_AREA, scope=r["id"],
                value=r["wall_net_ft2"] * FT2_TO_M2, provenance=_prov("m2", cited),
                reference_class=F.CalculationClass.PERIMETER_TIMES_HEIGHT))
        if "skirting_run_ft" in r:
            references.append(ReferenceValue(
                material=Material.BASEBOARD_LENGTH, scope=r["id"],
                value=r["skirting_run_ft"] * FT_TO_M, provenance=_prov("m", cited),
                reference_class=F.CalculationClass.PLAN_POLYGON_PERIMETER))

    return ReferenceProject(
        project_id="fletcher-1923-entrance-lodge",
        publisher="B. T. Batsford (Banister Fletcher & H. P. Fletcher)",
        licence="CC Public Domain Mark 1.0 (archive.org licenseurl, verified 2026-10-27)",
        rooms=tuple(rooms),
        openings=tuple(openings),
        # P3: the plates carry a drawn scale bar in feet and the plan is fully figured, so the
        # scale is READ OFF THE DRAWING rather than inferred from a pixel count.
        scale=Measured(1.0, _prov("m", "Plate 8 scale bar, leaf 516 — figured drawing, scale 1")),
        wall_thickness=Measured(min(pj["wall_thicknesses_in"]) * 0.0254,
                                _prov("m", pj["wall_thickness_cited"])),
        convention=MeasurementConvention[pj["measurement_convention"]],
        opening_schedule_complete=pj["opening_schedule_complete"],
        distinguishes_finishes=False,
        references=tuple(references),
    )


# --------------------------------------------------------------------------- the convention audit

def convention_audit() -> dict:
    """What the source's own method-of-measurement chapters say about each of the four formulas'
    contested conventions, and -- where both sides can be computed on this project -- how large the
    divergence is.

    **This is not an accuracy measurement and it is never reported as one.** A convention
    divergence is the difference between two defensible ways of booking the same work. It is
    reported because the directive asks whether a failure originates in the measurements, the
    geometry, the material assumptions or the calculation logic, and a convention divergence is
    none of those four -- it is a fifth thing, and conflating it with an error is how an
    instrument gets blamed for a disagreement about a rule.
    """
    data = load()
    out: dict = {"source": data["source"]["work"],
                 "licence": data["source"]["licence"],
                 "rules": data["stated_conventions"],
                 "measured_divergences": []}

    # F4. The one divergence this project can actually measure: our frozen convention breaks the
    # skirting at every stated door opening; the takeoff books the full collected girth and numbers
    # the breaks as stopped ends.
    for r in data["rooms"]:
        if "skirting_run_ft" not in r:
            continue
        ours_ft = r["wall_girth_ft"] - sum(r.get("door_widths_ft", []))
        theirs_ft = r["skirting_run_ft"]
        out["measured_divergences"].append({
            "formula": "F4 baseboard length",
            "scope": r["id"],
            "our_frozen_convention": "BASEBOARD_BREAKS_AT_DOOR_OPENINGS = True",
            "source_convention_as_booked": r["skirting_item"],
            "ours_m": ours_ft * FT_TO_M,
            "source_m": theirs_ft * FT_TO_M,
            "divergence_m": (ours_ft - theirs_ft) * FT_TO_M,
            "divergence_pct": 100.0 * (ours_ft - theirs_ft) / theirs_ft,
            "frozen_tolerance_pct": 100.0 * F.TOLERANCE_REL[Material.BASEBOARD_LENGTH],
            "exceeds_tolerance": abs(100.0 * (ours_ft - theirs_ft) / theirs_ft)
                                 > 100.0 * F.TOLERANCE_REL[Material.BASEBOARD_LENGTH],
            "this_is_not_an_error": ("the two figures book the same work under two conventions that "
                                     "the SAME BOOK states for two different trades; see the "
                                     "joiner's rule at p.84 and the plasterer's at p.132"),
            "labours_the_source_numbered_instead": r.get("skirting_labours"),
        })

    # F3. The source's own worked example of the cornice deduction, which our frozen convention
    # does not make. Reported from the source's example, not recomputed on this project, because
    # no cornice girth was transcribed for these rooms.
    for rule in data["stated_conventions"]:
        if rule["formula"].startswith("F3") and "divergence_in_the_sources_own_example_pct" in rule:
            out["measured_divergences"].append({
                "formula": "F3 ceiling paintable area",
                "scope": "the source's own worked example (p.128), not this project",
                "our_frozen_convention": rule["our_frozen_choice"],
                "source_convention_as_booked": rule["worked_example_in_source"],
                "divergence_pct": rule["divergence_in_the_sources_own_example_pct"],
                "frozen_tolerance_pct": 100.0 * F.TOLERANCE_REL[Material.CEILING_PAINT_AREA],
                "exceeds_tolerance": True,
                "this_is_not_an_error": ("a cornice deduction is a booking convention; no plan-view "
                                         "field in #263's contract states whether a cornice exists"),
            })
    return out


def quantities() -> dict[str, dict[Material, FO.Quantity]]:
    p = project()
    return {room.id: FO.compute_all(p, room) for room in p.rooms}
