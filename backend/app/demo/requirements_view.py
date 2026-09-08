"""Project (parsed requirements) <-> the demo pipeline's own ArchitecturalSpec.

Two directions, both deliberately small:

  * `review_of(project)` — the product-facing "this is what I understood" contract. It exposes
    ONLY the fields a user can meaningfully correct, each with where it came from, and never any
    internal spec detail.
  * `spec_for(project)` — the adapter into `app.vertical_slice.spec.ArchitecturalSpec`, which is
    the authoritative planning spec on the demo path.

`app.architect.models.ArchitecturalSpec` (the LLM gateway's output that feeds the old solver) is
NOT used here and is not on the demo path.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.projects.models import Project
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec

#: Setbacks used to place the selected footprint inside a plot. The footprint the user picked is
#: treated as the BUILDABLE area exactly; the setbacks only create the surrounding site the
#: parking, entrance walk and garden are laid out in. PARAMETER, not a regulation figure.
FRONT_SETBACK_M = 5.5
SIDE_SETBACK_M = 3.0
REAR_SETBACK_M = 4.0


class RequirementField(BaseModel):
    """One correctable requirement plus where it came from."""

    value: int | bool | None
    source: str  # "requested" | "inferred" | "unknown"


class RequirementsReview(BaseModel):
    """What the REVIEW screen shows and lets the user correct."""

    bedrooms: RequirementField
    safe_room: RequirementField
    wet_rooms: RequirementField
    open_plan: RequirementField
    parking_spaces: RequirementField
    floors: RequirementField
    built_area_m2: float | None = None
    footprint_width_m: float | None = None
    footprint_depth_m: float | None = None
    description: str = ""


class ReviewEdit(BaseModel):
    """User corrections from the REVIEW screen. Every field optional: absent means "leave as
    parsed". A supplied value becomes authoritative."""

    bedrooms: int | None = None
    safe_room: bool | None = None
    wet_rooms: int | None = None
    open_plan: bool | None = None
    parking_spaces: int | None = None
    floors: int | None = None


def _field(tagged, default=None, default_source: str = "inferred") -> RequirementField:
    if tagged is None or tagged.value is None:
        return RequirementField(value=default, source="unknown" if default is None else default_source)
    return RequirementField(value=tagged.value, source=str(tagged.source.value))


def review_of(project: Project) -> RequirementsReview:
    footprint = project.selected_footprint
    return RequirementsReview(
        bedrooms=_field(project.bedrooms),
        safe_room=_field(project.safe_room, default=False),
        wet_rooms=_field(project.wet_rooms, default=1),
        open_plan=_field(project.open_plan, default=False),
        parking_spaces=_field(project.parking_spaces, default=0),
        floors=_field(project.floors, default=1),
        built_area_m2=project.built_area_m2,
        footprint_width_m=footprint.width_m if footprint else None,
        footprint_depth_m=footprint.depth_m if footprint else None,
        description=project.description,
    )


def spec_for(project: Project) -> ArchitecturalSpec:
    """The authoritative planning spec, built from the (possibly user-corrected) requirements.

    The selected footprint becomes the buildable rectangle EXACTLY; the plot is that rectangle
    plus setbacks, so the site stage has somewhere to put parking, the entrance walk and garden.
    """
    review = review_of(project)
    footprint = project.selected_footprint
    if footprint is None:  # guarded by scope.check_supported before this is ever called
        raise ValueError("spec_for requires a selected rectangular footprint")

    return ArchitecturalSpec(
        plot=PlotSpec(
            width_m=footprint.width_m + 2 * SIDE_SETBACK_M,
            depth_m=footprint.depth_m + FRONT_SETBACK_M + REAR_SETBACK_M,
            front_setback_m=FRONT_SETBACK_M,
            side_setback_m=SIDE_SETBACK_M,
            rear_setback_m=REAR_SETBACK_M,
        ),
        program=ProgramSpec(
            bedrooms=int(review.bedrooms.value or 0),
            safe_room=bool(review.safe_room.value),
            open_plan_living=bool(review.open_plan.value),
            wet_rooms=int(review.wet_rooms.value or 1),
            parking_spaces=int(review.parking_spaces.value or 0),
        ),
    )
