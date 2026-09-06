"""Contract for the Architect Model — an external service (real implementation TBD; today only
`MockArchitectModelGateway` exists) that turns a brief + site + constraints into a structured
`ArchitecturalSpec`: what rooms are needed (`program`), how they group (`zones`), how they must relate
to each other (`relationships`), and how the building is entered/circulated (`circulation`).

This module makes no assumption about how the model is trained/hosted/prompted — see
`app/architect/gateway.py`'s `ArchitectModelGateway` abstraction for the boundary.

`SiteSpec` here is plot/site geometry ONLY — informational context for the Architect Model. It is
NEVER used as the Geometry Solver's room-placement boundary; see `app/geometry/models.py`'s
`BuildingFootprintSpec` for that, which is a wholly separate type the geometry module owns and the
solver actually enforces. Nothing in this codebase derives a footprint from a site's `plot_area_m2` —
deciding how much of a site becomes buildable footprint involves setbacks/coverage-ratio/regulatory
decisions that are out of scope here and must not be shortcut.
"""

from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# Where an authoritative-side fact in an `ArchitecturalSpec` actually came from — added so a caller can
# tell a merged-in HARD requirement (e.g. a safe room the Architect Model itself never produced) apart
# from something the model inferred on its own. `None` means "not tracked" (e.g. `MockArchitectModelGateway`
# doesn't set this today). See `app/architect/authoritative_merge.py` for the only place that currently
# writes `"USER_REQUIREMENT"`/`"REGULATION"`.
ConstraintSource = Literal["MODEL_INFERENCE", "USER_REQUIREMENT", "REGULATION", "SYSTEM_POLICY"]


class SiteSpec(BaseModel):
    """The plot/site geometry — see the module docstring: informational only, not a room-placement
    boundary. Same rectangular-placeholder spirit as Feature 03's square-site assumption."""

    width_m: float = Field(gt=0)
    depth_m: float = Field(gt=0)


class ConstraintSeverity(str, Enum):
    hard = "hard"
    soft = "soft"


class ConstraintKind(str, Enum):
    required_room = "required_room"
    min_area = "min_area"
    max_area = "max_area"
    min_width = "min_width"
    adjacency = "adjacency"
    direct_access = "direct_access"
    separation = "separation"
    generic = "generic"


def _require_distinct_room_types(room_type_a: str, room_type_b: str) -> None:
    if room_type_a == room_type_b:
        raise ValueError("room_type_a and room_type_b must differ")


class RequirementState(str, Enum):
    """UNKNOWN != ZERO: whether `RequiredRoomConstraint.count` reflects a real, known answer, or the
    caller genuinely doesn't know it (e.g. the user's free-text description never mentioned a room
    type at all). These are different facts and must never be collapsed into the same number —
    `count=0` is a real, positive claim ("definitely none of this type"), which is a different
    situation from "we have no idea."""

    known = "known"
    unknown = "unknown"


class RequiredRoomConstraint(BaseModel):
    """The program must include exactly `count` instance(s) of `room_type` — but only when
    `state="known"`. `count=0` (known) is a legal, meaningful value distinct from BOTH
    `state="unknown"` AND from omitting the constraint entirely:

    - Constraint absent entirely: no opinion at all — the gateway may apply its own generic default.
    - `state="known", count=N`: exactly N instances required (N may be 0 — "definitely none").
    - `state="unknown"` (`count` omitted): the true count is genuinely not known. A gateway MUST NOT
      invent a number for this — see `MockArchitectModelGateway`, which excludes the room type from
      the program entirely and reports it via `ArchitecturalSpec.incomplete_requirements` instead of
      guessing.
    """

    kind: Literal[ConstraintKind.required_room] = ConstraintKind.required_room
    room_type: str
    state: RequirementState = RequirementState.known
    count: int | None = Field(default=None, ge=0)
    severity: ConstraintSeverity
    description: str | None = None

    @model_validator(mode="after")
    def _count_matches_state(self) -> "RequiredRoomConstraint":
        if self.state == RequirementState.known and self.count is None:
            raise ValueError("count must be provided when state='known'")
        if self.state == RequirementState.unknown and self.count is not None:
            raise ValueError("count must not be provided when state='unknown' — the count is, by definition, not known")
        return self


class MinAreaConstraint(BaseModel):
    """`room_type` must have at least `min_area_m2` — HARD when present (see `ProgramItem`)."""

    kind: Literal[ConstraintKind.min_area] = ConstraintKind.min_area
    room_type: str
    min_area_m2: float = Field(gt=0)
    severity: ConstraintSeverity
    description: str | None = None


class MaxAreaConstraint(BaseModel):
    """`room_type` must not exceed `max_area_m2` — HARD when present (see `ProgramItem`)."""

    kind: Literal[ConstraintKind.max_area] = ConstraintKind.max_area
    room_type: str
    max_area_m2: float = Field(gt=0)
    severity: ConstraintSeverity
    description: str | None = None


class MinWidthConstraint(BaseModel):
    kind: Literal[ConstraintKind.min_width] = ConstraintKind.min_width
    room_type: str
    min_width_m: float = Field(gt=0)
    severity: ConstraintSeverity
    description: str | None = None


class AdjacencyConstraint(BaseModel):
    """Two room TYPES must share a meaningful wall segment (a nonzero-length touching edge — see the
    Geometry Solver's `_shared_edge_length`). Makes NO claim about a door/opening existing between
    them. Semantically distinct from `DirectAccessConstraint` below — do not treat one as implying
    the other, in either direction."""

    kind: Literal[ConstraintKind.adjacency] = ConstraintKind.adjacency
    room_type_a: str
    room_type_b: str
    severity: ConstraintSeverity
    description: str | None = None
    source: ConstraintSource | None = None

    @model_validator(mode="after")
    def _distinct(self) -> "AdjacencyConstraint":
        _require_distinct_room_types(self.room_type_a, self.room_type_b)
        return self


class DirectAccessConstraint(BaseModel):
    """Two room TYPES must be adjacent AND have a direct connection/opening between them. Real
    door/opening geometry is not modeled yet (a future milestone) — the current Geometry Solver
    approximates "an opening could plausibly exist" as the shared wall segment being at least as long
    as a standard interior door (see the solver's `_DOOR_OPENING_MIN_M`), which is a strictly stronger
    check than plain adjacency, not the same one. A pair of rooms satisfying `AdjacencyConstraint`
    does NOT automatically satisfy this."""

    kind: Literal[ConstraintKind.direct_access] = ConstraintKind.direct_access
    room_type_a: str
    room_type_b: str
    severity: ConstraintSeverity
    description: str | None = None
    source: ConstraintSource | None = None

    @model_validator(mode="after")
    def _distinct(self) -> "DirectAccessConstraint":
        _require_distinct_room_types(self.room_type_a, self.room_type_b)
        return self


class SeparationConstraint(BaseModel):
    """Two room TYPES must be kept apart — the complement of `AdjacencyConstraint`.

    `min_distance_m` controls exactly how far apart:
    - `None` (default): the two types simply must not touch (zero-tolerance — any shared wall
      segment, however short, violates this).
    - a positive number: the minimum straight-line gap (m) between the two rectangles' nearest
      points must be at least that much — a stronger requirement than merely "not touching."
    """

    kind: Literal[ConstraintKind.separation] = ConstraintKind.separation
    room_type_a: str
    room_type_b: str
    severity: ConstraintSeverity
    min_distance_m: float | None = Field(default=None, ge=0)
    description: str | None = None
    source: ConstraintSource | None = None

    @model_validator(mode="after")
    def _distinct(self) -> "SeparationConstraint":
        _require_distinct_room_types(self.room_type_a, self.room_type_b)
        return self


class GenericConstraint(BaseModel):
    """Escape hatch for a constraint not yet modeled as its own typed class. Carried through the
    contract but NOT enforced by the current Geometry Solver — a caller must not assume a
    `GenericConstraint` was actually satisfied just because it was accepted here."""

    kind: Literal[ConstraintKind.generic] = ConstraintKind.generic
    key: str
    description: str
    severity: ConstraintSeverity
    params: dict[str, Any] = Field(default_factory=dict)


# The subset of constraint kinds that express a relationship between two room types — shared by
# `ArchitecturalSpec.relationships` and usable inside `ArchitectModelRequest`'s constraint lists.
RelationalConstraint = Annotated[
    AdjacencyConstraint | DirectAccessConstraint | SeparationConstraint,
    Field(discriminator="kind"),
]

# The full set of solver-critical constraint kinds an ArchitectModelGateway request/response may carry,
# plus the GenericConstraint escape hatch for anything not yet modeled.
ArchitectConstraint = Annotated[
    RequiredRoomConstraint
    | MinAreaConstraint
    | MaxAreaConstraint
    | MinWidthConstraint
    | AdjacencyConstraint
    | DirectAccessConstraint
    | SeparationConstraint
    | GenericConstraint,
    Field(discriminator="kind"),
]


class ArchitectModelRequest(BaseModel):
    """INPUT to `ArchitectModelGateway.generate()`.

    `target_area_m2` is optional and unused by `MockArchitectModelGateway` (which derives room sizes
    from its own fixed per-room-type constants, never from a total budget) — but real product
    validation surfaced that it is NOT optional in practice for `LocalArchitectModelGateway`/Architect
    Model V1: every training example the model saw included a total-area anchor (`brief.target_area_m2`
    and a matching `TOTAL_AREA` constraint — see `app/architect/local_gateway.py`'s `_build_model_input`),
    and without one the model has no signal for how large a house it's actually being asked for, and
    was observed producing wildly oversized rooms (e.g. a 125 m² living room for a 70 m² house) that the
    Geometry Solver then correctly rejected as unsatisfiable. Added here rather than only in
    `local_gateway.py` because it's a fact about the request BuildSmart already has
    (`project.built_area_m2`), not something specific to one gateway's wire format.
    """

    brief: str
    site: SiteSpec
    target_area_m2: float | None = Field(default=None, gt=0)
    hard_constraints: list[ArchitectConstraint] = Field(default_factory=list)
    soft_constraints: list[ArchitectConstraint] = Field(default_factory=list)

    @field_validator("hard_constraints")
    @classmethod
    def _hard_constraints_are_hard(cls, value: list) -> list:
        for constraint in value:
            if constraint.severity != ConstraintSeverity.hard:
                raise ValueError(
                    f"hard_constraints entry (kind={constraint.kind.value!r}) must have "
                    f"severity='hard', got {constraint.severity.value!r}"
                )
        return value

    @field_validator("soft_constraints")
    @classmethod
    def _soft_constraints_are_soft(cls, value: list) -> list:
        for constraint in value:
            if constraint.severity != ConstraintSeverity.soft:
                raise ValueError(
                    f"soft_constraints entry (kind={constraint.kind.value!r}) must have "
                    f"severity='soft', got {constraint.severity.value!r}"
                )
        return value


class ProgramItem(BaseModel):
    """One room type the building needs, and how many instances of it (per the type-to-instance
    mapping in `app/geometry/instances.py`).

    `target_area_m2` is an optimization PREFERENCE the Geometry Solver tries first, not a guarantee.
    `min_area_m2`/`max_area_m2` are HARD bounds when supplied — the solved room's actual area will
    never fall outside them. `target_area_m2`, when given alongside either bound, must itself already
    fall within that bound (checked below) — the contract does not silently clamp an inconsistent
    target into range.
    """

    room_type: str
    count: int = Field(ge=1)
    target_area_m2: float | None = Field(default=None, gt=0)
    min_area_m2: float | None = Field(default=None, gt=0)
    max_area_m2: float | None = Field(default=None, gt=0)
    min_width_m: float | None = Field(default=None, gt=0)
    source: ConstraintSource | None = None

    @model_validator(mode="after")
    def _area_bounds_are_consistent(self) -> "ProgramItem":
        if (
            self.min_area_m2 is not None
            and self.max_area_m2 is not None
            and self.min_area_m2 > self.max_area_m2
        ):
            raise ValueError(
                f"{self.room_type}: min_area_m2 ({self.min_area_m2}) exceeds max_area_m2 "
                f"({self.max_area_m2})"
            )
        if self.target_area_m2 is not None:
            if self.min_area_m2 is not None and self.target_area_m2 < self.min_area_m2:
                raise ValueError(
                    f"{self.room_type}: target_area_m2 ({self.target_area_m2}) is below "
                    f"min_area_m2 ({self.min_area_m2})"
                )
            if self.max_area_m2 is not None and self.target_area_m2 > self.max_area_m2:
                raise ValueError(
                    f"{self.room_type}: target_area_m2 ({self.target_area_m2}) exceeds "
                    f"max_area_m2 ({self.max_area_m2})"
                )
        return self


class Zone(BaseModel):
    """A named grouping of room types (e.g. "public"/"private"). The Geometry Solver rewards
    (`cohesion_severity="soft"`, the default) placements where a zone's rooms end up adjacent to each
    other — a soft compactness/cohesion objective, never a requirement, unless a caller explicitly
    opts a zone into `cohesion_severity="hard"`, in which case every room in the zone must form a
    single connected group (reachable from any other room in the zone via a chain of adjacencies)
    or the layout is rejected outright, the same as any other hard constraint."""

    name: str
    room_types: list[str]
    cohesion_severity: ConstraintSeverity = ConstraintSeverity.soft


class Circulation(BaseModel):
    """Minimal circulation strategy — which room type is the entry point, and whether a dedicated
    hallway is required. A later milestone can expand this into an explicit circulation graph."""

    entry_room_type: str
    requires_hallway: bool = False


class ArchitecturalSpec(BaseModel):
    """OUTPUT of `ArchitectModelGateway.generate()` — validated so a malformed/inconsistent spec is
    rejected before it ever reaches the Geometry Solver, rather than failing confusingly there.

    `incomplete_requirements` names every room TYPE that a caller flagged as
    `RequiredRoomConstraint(state="unknown")` and that the gateway therefore excluded from `program`
    rather than guessing a count for — the explicit "incomplete input" signal callers should surface
    (e.g. as a user-facing note) instead of silently treating the exclusion as "zero were wanted."

    `circulation` is `None` when no gateway/adapter has an actual basis for an entry-room claim — see
    `app/architect/adapter.py`: Architect Model V1's own `circulation` output is a list of room TYPES
    that serve as circulation space (e.g. staircases), a different concept from "which room is the
    entry," so the adapter deliberately leaves this `None` rather than inventing an entry room. The
    Geometry Solver (`app/geometry/solver.py`) only enforces an entry-room hard requirement when this
    is not `None`.
    """

    program: list[ProgramItem]
    zones: list[Zone]
    relationships: list[RelationalConstraint]
    circulation: Circulation | None = None
    incomplete_requirements: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_cross_references(self) -> "ArchitecturalSpec":
        # ROOM_INSTANCE_SIZE_FIDELITY: multiple ProgramItems of the SAME room_type are now
        # explicitly ALLOWED -- this is exactly how a program represents several differently-sized
        # instances of one type (e.g. two `bedroom` items, each count=1, at 11 m2 and 10 m2 --
        # `master_bedroom` already gets its own type for the primary case, but two ordinary bedrooms
        # of different explicit sizes have no other type to use). This was previously rejected here
        # unconditionally; it is safe now that app.geometry.instances.expand_program_to_instances
        # numbers instances GLOBALLY per type across every item (not per-item, which used to
        # collide/reset), and every downstream `{room_type: item}`-style lookup
        # (app.geometry.solver, app.design.pipeline, app.geometry.geometric_design,
        # app.geometry.spatial_v2) has been changed to key by instance id instead, so a duplicate
        # room_type no longer causes one item's target area/bounds/source to silently shadow
        # another's. A program with only one item per type (the common case, unaffected by this
        # change) behaves exactly as before.
        known = {item.room_type for item in self.program}

        for zone in self.zones:
            unknown = sorted(set(zone.room_types) - known)
            if unknown:
                raise ValueError(f"zone {zone.name!r} references unknown room type(s): {unknown}")

        for relationship in self.relationships:
            for room_type in (relationship.room_type_a, relationship.room_type_b):
                if room_type not in known:
                    raise ValueError(f"relationship references unknown room type: {room_type!r}")

        if self.circulation is not None and self.circulation.entry_room_type not in known:
            raise ValueError(
                f"circulation.entry_room_type references unknown room type: "
                f"{self.circulation.entry_room_type!r}"
            )

        return self
