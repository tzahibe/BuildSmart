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

from pydantic import BaseModel, Field

from app.projects.models import Project
from app.vertical_slice.relationships import describe
from app.vertical_slice.spec import (
    ArchitecturalSpec,
    RelationStrength,
    RoomRelation,
    RoomRelationshipRequirement,
    CorridorRequirement,
    CorridorWidthMode,
    PlotSpec,
    ProgramSpec,
)

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


class RoomRelationshipNote(BaseModel):
    """One understood relationship, shown back before Generate so a misreading is catchable."""

    source_role: str
    target_role: str
    relation: str
    strength: str
    source_text: str
    ambiguous: bool = False
    #: Product wording, e.g. 'חדר ההורים צמוד לחדרי הרחצה' — built here so the UI never has to.
    statement: str = ""


class CorridorWidthNote(BaseModel):
    value_m: float
    mode: str
    source: str


class UnsupportedRequestNote(BaseModel):
    text: str
    topic: str = "other"
    severity: str = "ambiguous"


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
    #: What the brief asked for that this stage cannot plan. Shown back to the person rather than
    #: dropped — the screen quotes their whole description, so silence here reads as agreement.
    unsupported_requests: list[UnsupportedRequestNote] = Field(default_factory=list)
    #: The corridor width the brief asked for, shown back before generation. `None` when none was
    #: asked for — the planner then keeps its own derived width.
    corridor_width: CorridorWidthNote | None = None
    room_relationships: list[RoomRelationshipNote] = Field(default_factory=list)


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
        unsupported_requests=[UnsupportedRequestNote(text=r.text, topic=r.topic, severity=r.severity)
                              for r in project.unsupported_requests],
        corridor_width=(
            CorridorWidthNote(value_m=project.corridor_width.value_m,
                              mode=project.corridor_width.mode,
                              source=project.corridor_width.source.value)
            if project.corridor_width and project.corridor_width.value_m is not None else None),
        room_relationships=[
            RoomRelationshipNote(
                source_role=r.source_role, target_role=r.target_role, relation=r.relation,
                strength=r.strength, source_text=r.source_text, ambiguous=r.ambiguous,
                statement=("" if r.ambiguous else describe(RoomRelationshipRequirement(
                    source_role=r.source_role, target_role=r.target_role,
                    relation=RoomRelation(r.relation),
                    strength=RelationStrength(r.strength), source_text=r.source_text))))
            for r in project.room_relationships],
    )


def _corridor_of(project: Project) -> CorridorRequirement | None:
    """The authoritative corridor requirement, or None when the brief asked for no width.

    The parser's mode is carried through unchanged — "at least 1.6 m" stays a MINIMUM and is never
    flattened into "exactly 1.6 m".
    """
    field = project.corridor_width
    if field is None or field.value_m is None:
        return None
    try:
        mode = CorridorWidthMode(field.mode)
    except ValueError:
        mode = CorridorWidthMode.MINIMUM
    return CorridorRequirement(width_m=float(field.value_m), mode=mode)


def _relationships_of(project: Project) -> tuple[RoomRelationshipRequirement, ...]:
    """The authoritative relationships. Ambiguous ones are excluded — they never reach the planner,
    because `scope.check_supported` refuses first and asks the person which room they meant."""
    out = []
    for record in project.room_relationships:
        if record.ambiguous or not record.source_role or not record.target_role:
            continue
        try:
            relation = RoomRelation(record.relation)
            strength = RelationStrength(record.strength)
        except ValueError:
            continue
        out.append(RoomRelationshipRequirement(
            source_role=record.source_role, target_role=record.target_role,
            relation=relation, strength=strength, source_text=record.source_text))
    return tuple(out)


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
            # The TARGET BUILT AREA the person entered, carried through as a target the plan should
            # meet — not as a ceiling. The selected footprint is validated to be within 0.5% of it
            # (see projects/models.py), so the two agree by construction; the requested value is the
            # authoritative one and is never adjusted here.
            target_built_area_m2=project.built_area_m2,
            corridor=_corridor_of(project),
            relationships=_relationships_of(project),
        ),
    )
