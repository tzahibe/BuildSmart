"""Demo API: the review contract and the authoritative generation endpoint.

Deliberately a NEW route rather than a swap of `POST /projects/{id}/design`, so the existing
solver path keeps working untouched while the demo path is built. Switching the product over is
then a one-line change, not a migration.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.projects.routes import base_routes as project_routes

from app.projects.models import SourceTag, TaggedBool, TaggedInt

from .contract import DemoDesign
from pydantic import BaseModel, Field

from app.projects.models import SetbackAssumptions, StreetSide

from app.observability import failure_log

from . import site_geometry
from .requirements_view import RequirementsReview, ReviewEdit, review_of
from .service import DemoGenerationError, generate_demo_design

router = APIRouter(prefix="/projects", tags=["demo"])


def _project_or_404(project_id: str):
    project = project_routes.repository.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/{project_id}/review", response_model=RequirementsReview)
def get_requirements_review(project_id: str) -> RequirementsReview:
    """"This is what I understood" — the correctable requirements, and where each came from."""
    return review_of(_project_or_404(project_id))


@router.put("/{project_id}/review", response_model=RequirementsReview)
def update_requirements_review(project_id: str, body: ReviewEdit) -> RequirementsReview:
    """The user corrects what we understood. Whatever they set here becomes AUTHORITATIVE — it is
    what generation reads, and a corrected value is recorded as `requested` because the person
    asked for it explicitly. Fields left absent keep their parsed value."""
    project = _project_or_404(project_id)
    if project.requirements_parsed_at is None:
        raise HTTPException(
            status_code=422,
            detail={"code": "REQUIREMENTS_NOT_PARSED",
                    "message": "עדיין לא הבנו את הדרישות.", "detail": ""})

    def _int(new, current):
        return TaggedInt(value=new, source=SourceTag.requested) if new is not None else current

    def _bool(new, current):
        return TaggedBool(value=new, source=SourceTag.requested) if new is not None else current

    # Setbacks are assumptions, so the person may correct them here like any other assumption.
    # Whatever they set is what the buildable region is derived from on the next Generate.
    current = project.setbacks
    setbacks = SetbackAssumptions(
        front_m=body.front_setback_m if body.front_setback_m is not None
        else (current.front_m if current else site_geometry.FRONT_SETBACK_M),
        side_m=body.side_setback_m if body.side_setback_m is not None
        else (current.side_m if current else site_geometry.SIDE_SETBACK_M),
        rear_m=body.rear_setback_m if body.rear_setback_m is not None
        else (current.rear_m if current else site_geometry.REAR_SETBACK_M),
    )

    updated = project_routes.repository.set_parsed_requirements(
        project_id,
        floors=_int(body.floors, project.floors),
        bedrooms=_int(body.bedrooms, project.bedrooms),
        safe_room=_bool(body.safe_room, project.safe_room),
        parking_spaces=_int(body.parking_spaces, project.parking_spaces),
        pool=project.pool,
        wet_rooms=_int(body.wet_rooms, project.wet_rooms),
        open_plan=_bool(body.open_plan, project.open_plan),
        setbacks=setbacks,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return review_of(updated)


@router.post("/{project_id}/design/demo", response_model=DemoDesign)
def generate_demo_plan(project_id: str, request: Request) -> DemoDesign:
    project = _project_or_404(project_id)
    try:
        return generate_demo_design(project).design
    except DemoGenerationError as error:
        # Recorded HERE rather than only in the generic handler, because this is the failure that
        # matters most — somebody who described a house and did not get a drawing — and only this
        # frame still has the brief, the parcel and the footprint that produced it.
        footprint = project.selected_footprint
        failure_log.refusal(
            error.code, error.message, error.detail,
            where="POST /projects/{id}/design/demo",
            context={
                "project_id": project_id,
                "description": project.description,
                "plot_width_m": project.plot_width_m,
                "plot_depth_m": project.plot_depth_m,
                "street_facing_side": (project.street_facing_side.value
                                       if project.street_facing_side else None),
                "built_area_m2": project.built_area_m2,
                "footprint_width_m": footprint.width_m if footprint else None,
                "footprint_depth_m": footprint.depth_m if footprint else None,
                "bedrooms": project.bedrooms.value if project.bedrooms else None,
                "wet_rooms": project.wet_rooms.value if project.wet_rooms else None,
                "safe_room": project.safe_room.value if project.safe_room else None,
                "open_plan": project.open_plan.value if project.open_plan else None,
            })
        # Tell the generic handler this one is already in the log WITH its context, so the same
        # failure is not counted twice — once richly here and once bare there.
        request.state.failure_recorded = True
        raise HTTPException(
            status_code=422,
            detail={"code": error.code, "message": error.message, "detail": error.detail},
        )


# --------------------------------------------------------- site-aware footprint options

class FootprintOptionsRequest(BaseModel):
    """The site as entered on the form, before any project exists."""

    plot_width_m: float = Field(gt=0)
    plot_depth_m: float = Field(gt=0)
    street_facing_side: StreetSide = StreetSide.north
    built_area_m2: float = Field(gt=0)
    front_setback_m: float | None = Field(default=None, gt=0)
    side_setback_m: float | None = Field(default=None, gt=0)
    rear_setback_m: float | None = Field(default=None, gt=0)


class FootprintOption(BaseModel):
    shape_type: str          # NARROW | COMPACT | BALANCED | WIDE — the shape that RESULTED
    width_m: float
    depth_m: float
    area_m2: float


class FootprintOptionsResponse(BaseModel):
    """Only outlines that fit, plus the numbers behind the answer either way."""

    plot_width_m: float
    plot_depth_m: float
    street_facing_side: str
    front_setback_m: float
    side_setback_m: float
    rear_setback_m: float
    setback_disclaimer: str
    #: The buildable rectangle AS IT MAY BE SHOWN. Where the setbacks use up an axis the region is
    #: empty and these are 0.00 — never the negative the raw subtraction produces, which is an
    #: intermediate and not a dimension anything can have. `has_buildable_area` is what separates
    #: "empty" from "small": 0.00 x 0.00 with the flag False means there is no region at all.
    buildable_width_m: float
    buildable_depth_m: float
    has_buildable_area: bool
    #: The buildable rectangle's area — a GEOMETRIC ceiling for one storey, not a promise about how
    #: big a house can be. The room programme can reduce it further.
    one_storey_footprint_capacity_m2: float
    requested_built_area_m2: float
    options: list[FootprintOption]
    #: Set when nothing fits, so the person is told BEFORE choosing rather than after.
    rejection: dict | None = None


@router.post("/site/footprint-options", response_model=FootprintOptionsResponse)
def footprint_options(body: FootprintOptionsRequest) -> FootprintOptionsResponse:
    """Every building outline of the REQUESTED area that fits this site — and nothing else.

    The footprint step used to build its four cards from `built_area_m2` alone, knowing nothing
    about the land. Across a 1440-scenario scan that produced 1032 `FOOTPRINT_DOES_NOT_FIT` refusals
    — 80% of all failures — every one of them a person who chose an option the system had already
    offered and could already have known was impossible. The options now come from the buildable
    rectangle, so an impossible one is never offered at all.
    """
    site = site_geometry.SiteGeometry(
        plot_width_m=body.plot_width_m, plot_depth_m=body.plot_depth_m,
        street_facing_side=body.street_facing_side,
        canonical_width_m=(body.plot_depth_m
                           if body.street_facing_side in (StreetSide.east, StreetSide.west)
                           else body.plot_width_m),
        canonical_depth_m=(body.plot_width_m
                           if body.street_facing_side in (StreetSide.east, StreetSide.west)
                           else body.plot_depth_m),
        front_setback_m=body.front_setback_m or site_geometry.FRONT_SETBACK_M,
        side_setback_m=body.side_setback_m or site_geometry.SIDE_SETBACK_M,
        rear_setback_m=body.rear_setback_m or site_geometry.REAR_SETBACK_M,
    )
    pairs = site_geometry.feasible_options(site, body.built_area_m2)
    capacity = site_geometry.one_storey_capacity_m2(site)

    rejection = None
    if not pairs and not site.has_buildable_area:
        # THE SETBACKS ATE THE PARCEL. Distinct from the capacity refusal below, which weighs a
        # requested area against a region that exists: here there is no region, the requested area
        # was never the binding constraint, and telling someone to ask for a smaller house would
        # point them at the one number that cannot help them.
        rejection = {
            "code": site_geometry.NO_BUILDABLE_AREA_CODE,
            "message": site_geometry.no_buildable_area_message(site),
        }
        failure_log.refusal(
            rejection["code"], rejection["message"],
            site_geometry.no_buildable_area_detail(site),
            where="POST /projects/site/footprint-options",
            context={"plot_width_m": body.plot_width_m, "plot_depth_m": body.plot_depth_m,
                     "street_facing_side": site.street_facing_side.value,
                     "front_setback_m": site.front_setback_m,
                     "rear_setback_m": site.rear_setback_m,
                     "side_setback_m": site.side_setback_m})
    elif not pairs:
        rejection = {
            "code": "BUILT_AREA_EXCEEDS_ONE_STOREY_CAPACITY",
            "message": (
                f"שטח הבנייה שביקשת, {body.built_area_m2:.0f} מ״ר, אינו נכנס בקומה אחת על המגרש הזה. "
                f"המגרש הוא {body.plot_width_m:.2f} × {body.plot_depth_m:.2f} מ׳, ואחרי נסיגות הדמו "
                f"נשאר שטח בנייה של {site_geometry.buildable_dimensions_he(site)} — "
                f"קיבולת מתאר גאומטרית לקומה אחת של כ-{capacity:.0f} מ״ר. "
                f"אפשר להקטין את שטח הבנייה המבוקש, או לעדכן את הנחות הנסיגה. "
                f"{site_geometry.SETBACK_DISCLAIMER}"),
        }
        failure_log.refusal(
            rejection["code"], rejection["message"],
            f"requested {body.built_area_m2} m2 vs one-storey capacity {capacity} m2",
            where="POST /projects/site/footprint-options",
            context={"plot_width_m": body.plot_width_m, "plot_depth_m": body.plot_depth_m,
                     "built_area_m2": body.built_area_m2, "capacity_m2": capacity})

    return FootprintOptionsResponse(
        plot_width_m=site.plot_width_m, plot_depth_m=site.plot_depth_m,
        street_facing_side=site.street_facing_side.value,
        front_setback_m=site.front_setback_m, side_setback_m=site.side_setback_m,
        rear_setback_m=site.rear_setback_m,
        setback_disclaimer=site_geometry.SETBACK_DISCLAIMER,
        buildable_width_m=site.presented_buildable_width_m,
        buildable_depth_m=site.presented_buildable_depth_m,
        has_buildable_area=site.has_buildable_area,
        one_storey_footprint_capacity_m2=capacity,
        requested_built_area_m2=body.built_area_m2,
        options=[FootprintOption(shape_type=site_geometry.shape_name(w, d),
                                 width_m=w, depth_m=d, area_m2=round(w * d, 2))
                 for w, d in pairs],
        rejection=rejection,
    )
