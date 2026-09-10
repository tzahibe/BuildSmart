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

from . import scope, site_geometry
from app.vertical_slice.concept_generator import build_room_program
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

#: The setbacks now live with the site model that applies them (`site_geometry`), re-exported here
#: only so existing importers keep working. They are DEMO ASSUMPTIONS, subtracted from the
#: authoritative parcel — never used to generate one.
FRONT_SETBACK_M = site_geometry.FRONT_SETBACK_M
SIDE_SETBACK_M = site_geometry.SIDE_SETBACK_M
REAR_SETBACK_M = site_geometry.REAR_SETBACK_M


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


class SiteNote(BaseModel):
    """The site as the planner will use it, shown before Generate.

    Everything here is either what the person entered or a stated assumption derived from it — the
    buildable rectangle is the parcel MINUS the setbacks, never anything larger.
    """

    plot_width_m: float
    plot_depth_m: float
    plot_area_m2: float
    street_facing_side: str
    front_setback_m: float
    side_setback_m: float
    rear_setback_m: float
    setback_disclaimer: str
    #: Presentation-safe: 0.00 where the setbacks use up an axis, never the raw negative. Read
    #: `has_buildable_area` to tell an empty region from a small one.
    buildable_width_m: float
    buildable_depth_m: float
    buildable_area_m2: float
    has_buildable_area: bool
    footprint_width_m: float | None = None
    footprint_depth_m: float | None = None
    footprint_fits: bool | None = None


class CorridorWidthNote(BaseModel):
    value_m: float
    mode: str
    source: str


class UnsupportedRequestNote(BaseModel):
    text: str
    topic: str = "other"
    severity: str = "ambiguous"


class ScopeLimits(BaseModel):
    """What the demo can plan, straight from `app.demo.scope`."""

    bedrooms_min: int
    bedrooms_max: int
    wet_rooms_min: int
    wet_rooms_max: int
    parking_max: int
    floors: int


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
    #: The rooms the plan will ACTUALLY contain, in the person's words. Counts alone hid the gap
    #: that prompted this: a brief asking for a study came back as "3 bedrooms, 1 bathroom" and the
    #: study was nowhere — not planned, and not reported as unplanned either. A list of what will be
    #: built makes anything missing from it visible before Generate.
    planned_rooms: list[str] = Field(default_factory=list)
    #: The authoritative parcel and the assumptions applied to it. `None` before the site is known.
    site: SiteNote | None = None
    #: The counts this stage can actually plan. Sent so the review screen can REFUSE a value that
    #: generation would reject, instead of accepting it and failing after the loading screen. The
    #: numbers live in `scope`; duplicating them in the client is how the two drift apart.
    limits: ScopeLimits = Field(default_factory=lambda: _limits())


class ReviewEdit(BaseModel):
    """User corrections from the REVIEW screen. Every field optional: absent means "leave as
    parsed". A supplied value becomes authoritative."""

    bedrooms: int | None = None
    safe_room: bool | None = None
    wet_rooms: int | None = None
    open_plan: bool | None = None
    parking_spaces: int | None = None
    floors: int | None = None
    #: Demo setback assumptions, editable here precisely because they are assumptions. Supplying
    #: any of them replaces that one; the rest keep their current value.
    front_setback_m: float | None = None
    side_setback_m: float | None = None
    rear_setback_m: float | None = None


def _field(tagged, default=None, default_source: str = "inferred") -> RequirementField:
    if tagged is None or tagged.value is None:
        return RequirementField(value=default, source="unknown" if default is None else default_source)
    return RequirementField(value=tagged.value, source=str(tagged.source.value))


def _limits() -> ScopeLimits:
    return ScopeLimits(
        bedrooms_min=min(scope.SUPPORTED_BEDROOMS), bedrooms_max=max(scope.SUPPORTED_BEDROOMS),
        wet_rooms_min=min(scope.SUPPORTED_WET_ROOMS), wet_rooms_max=max(scope.SUPPORTED_WET_ROOMS),
        parking_max=scope.MAX_PARKING_SPACES, floors=scope.SUPPORTED_FLOORS,
    )


def review_of(project: Project) -> RequirementsReview:
    footprint = project.selected_footprint
    bedrooms = _field(project.bedrooms)
    safe_room = _field(project.safe_room, default=False)
    wet_rooms = _field(project.wet_rooms, default=1)
    open_plan = _field(project.open_plan, default=False)
    return RequirementsReview(
        limits=_limits(),
        planned_rooms=_planned_rooms(bedrooms.value, safe_room.value,
                                     open_plan.value, wet_rooms.value),
        site=_site_note(project),
        bedrooms=bedrooms,
        safe_room=safe_room,
        wet_rooms=wet_rooms,
        open_plan=open_plan,
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


#: Room role -> what to call it on screen. Mirrors the plan's own names so the review and the
#: drawing never disagree about what a room is called.
_ROOM_WORDS = {
    "LIVING": "סלון", "DINING": "פינת אוכל", "KITCHEN": "מטבח", "HALL": "מסדרון",
    "MASTER_BEDROOM": "חדר הורים", "BEDROOM": "חדר שינה", "SAFE_ROOM": 'ממ"ד',
    "BATHROOM": "חדר רחצה", "TOILET": "שירותים",
}


def _planned_rooms(bedrooms, safe_room, open_plan, wet_rooms) -> list[str]:
    """The room programme this brief will actually produce, named and counted.

    Takes the ALREADY-RESOLVED review values rather than the project, because `spec_for` is built
    on top of `review_of` — calling it from inside `review_of` recursed until the stack ran out.
    It still goes through the planner's own `build_room_program`, so the list cannot drift from
    what actually gets drawn.
    """
    if bedrooms is None:
        return []
    program = ProgramSpec(
        bedrooms=int(bedrooms), safe_room=bool(safe_room),
        open_plan_living=bool(open_plan), wet_rooms=int(wet_rooms or 1))
    rooms = build_room_program(ArchitecturalSpec(plot=PlotSpec(20.0, 24.0), program=program))

    counts: dict[str, int] = {}
    for room in rooms:
        word = _ROOM_WORDS.get(room.role.value, room.zone_id)
        counts[word] = counts.get(word, 0) + 1
    return [word if n == 1 else f"{word} ×{n}" for word, n in counts.items()]


def _site_note(project: Project) -> SiteNote | None:
    site = site_geometry.derive(project)
    if site is None:
        return None
    footprint = project.selected_footprint
    fit = (site_geometry.check_footprint_fits(site, footprint.width_m, footprint.depth_m)
           if footprint is not None else None)
    return SiteNote(
        plot_width_m=site.plot_width_m, plot_depth_m=site.plot_depth_m,
        plot_area_m2=site.plot_area_m2,
        street_facing_side=site.street_facing_side.value,
        front_setback_m=site.front_setback_m, side_setback_m=site.side_setback_m,
        rear_setback_m=site.rear_setback_m,
        setback_disclaimer=site_geometry.SETBACK_DISCLAIMER,
        buildable_width_m=site.presented_buildable_width_m,
        buildable_depth_m=site.presented_buildable_depth_m,
        buildable_area_m2=site.buildable_area_m2,
        has_buildable_area=site.has_buildable_area,
        footprint_width_m=footprint.width_m if footprint else None,
        footprint_depth_m=footprint.depth_m if footprint else None,
        footprint_fits=fit.fits if fit else None,
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

    site = site_geometry.derive(project)
    if site is None:  # guarded by scope.check_supported before this is ever called
        raise ValueError("spec_for requires authoritative site dimensions")

    # THE PLOT IS THE PARCEL THE PERSON ENTERED. It is no longer computed from the footprint —
    # see site_geometry's module docstring for what that used to do and why it was wrong.
    return ArchitecturalSpec(
        plot=PlotSpec(
            width_m=site.canonical_width_m,
            depth_m=site.canonical_depth_m,
            # NEAR/FAR rather than front/rear: `PlotSpec` measures its buildable origin from the
            # y=0 edge, and for a SOUTH or WEST frontage the street is at the far end. Passing the
            # near setback first keeps `site.py`'s own use of that helper correct without it
            # needing to know anything about orientation.
            front_setback_m=site.near_setback_m,
            side_setback_m=site.side_setback_m,
            rear_setback_m=site.far_setback_m,
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
