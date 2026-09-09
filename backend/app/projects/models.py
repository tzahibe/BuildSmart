from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.localities.data import CITY_STREETS, KNOWN_CITIES
from app.projects.preferences import Preference


class SourceTag(str, Enum):
    """Where a parsed planning field's value came from — see Project.floors etc. below."""

    requested = "requested"
    inferred = "inferred"
    unknown = "unknown"


class TaggedInt(BaseModel):
    value: int | None
    source: SourceTag


class TaggedFloat(BaseModel):
    value: float | None
    source: SourceTag


class TaggedBool(BaseModel):
    value: bool | None
    source: SourceTag


class PoolField(BaseModel):
    requested: TaggedBool
    length_m: TaggedFloat
    width_m: TaggedFloat


class Room(BaseModel):
    """One room in a generated parametric design model — see app/design/generator.py.

    `source` records where this room's presence in the program came from — conventionally one of
    "MODEL_INFERENCE" / "USER_REQUIREMENT" / "REGULATION" (see app/architect/models.py's
    `ConstraintSource`; not imported directly here to keep app/projects free of a dependency on
    app/architect — this module only stores the string, app/design/pipeline.py is what sets it from the
    real `ConstraintSource`-typed value). `None` for rooms produced before this field existed (the old
    deterministic generator in app/design/generator.py never sets it either) — never backfilled/guessed.
    """

    type: str
    floor: int
    area_m2: float
    x: float
    y: float
    width_m: float
    depth_m: float
    source: str | None = None


class ChangeLogEntry(BaseModel):
    """One recorded field-level change — see app/projects/update.py, the single place that appends
    these. `old_value`/`new_value` are whatever JSON-compatible shape the field itself has (a plain
    scalar for e.g. `city`, a `TaggedInt`-shaped dict for e.g. `bedrooms`, a `Preference`-shaped dict for
    a preference add/update/remove) — kept loose on purpose rather than a per-field-type union, since
    this is a display/audit trail, not something re-parsed back into a typed value."""

    field: str
    old_value: Any = None
    new_value: Any = None
    source: Literal["CHAT", "SETTINGS"]
    at: datetime


def _non_empty(value: str, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must not be empty")
    return stripped


def _known_city(value: str) -> str:
    stripped = _non_empty(value, "city")
    if stripped not in KNOWN_CITIES:
        raise ValueError("city must be selected from the list of Israeli cities/settlements")
    return stripped


def _check_street_belongs_to_city(city: str, street: str) -> None:
    if street not in CITY_STREETS.get(city, []):
        raise ValueError("street must be selected from the list of streets for the chosen city")


class CorridorWidthField(BaseModel):
    """The corridor width the brief asked for — see requirements/parser.py's `CorridorWidth`.
    `mode` is stored as a plain string so a future mode does not invalidate stored projects."""

    value_m: float | None = None
    mode: str = "minimum"
    source: SourceTag = SourceTag.unknown


class RoomRelationshipRecord(BaseModel):
    """Storage form of a requested room relationship — role tokens, never zone ids, so the record
    stays valid whatever concept the planner later chooses."""

    source_role: str = ""
    target_role: str = ""
    relation: str = "near"
    strength: str = "preference"
    source_text: str = ""
    ambiguous: bool = False


class UnsupportedRequestRecord(BaseModel):
    """Storage form of `requirements.parser.UnsupportedRequest` — the person's own words, kept
    verbatim, plus a grouping slug."""

    text: str
    topic: str = "other"
    #: "preference" | "hard_requirement" | "ambiguous" — see requirements/parser.py's
    #: `RequestSeverity`. Stored as a plain string so a future severity does not invalidate
    #: projects already on disk. Defaults to the fail-closed value.
    severity: str = "ambiguous"


def _check_built_area_fits_plot(plot_area_m2: float, built_area_m2: float) -> None:
    if built_area_m2 >= plot_area_m2:
        raise ValueError("built_area_m2 must be smaller than plot_area_m2")


class FootprintSource(str, Enum):
    """Where a `SelectedFootprint` came from — a PRESET card (COMPACT/BALANCED/WIDE/NARROW; the
    frontend's own aspect-ratio catalog, not represented here at all, since the backend only ever
    needs to know the resulting rectangle) or a CUSTOM manual width/depth entry. Both travel through
    the exact same contract and the exact same downstream planning path — see
    app/design/pipeline.py's `_derive_footprint`."""

    preset = "PRESET"
    custom = "CUSTOM"


class FootprintPoint(BaseModel):
    x: float
    y: float


# Explicit, small ROUNDING tolerance for "is this area still close enough" — relative (0.5%) so it
# scales sensibly across small and large footprints, with a small absolute floor. Mirrors (but is
# computed independently of, per this task's own validation requirement — the backend must not
# simply trust whatever the frontend already checked) frontend/src/design/footprint.ts's own
# `footprintAreaToleranceM2`.
_FOOTPRINT_AREA_TOLERANCE_FRACTION = 0.005
_FOOTPRINT_AREA_TOLERANCE_FLOOR_M2 = 0.05


def _footprint_area_tolerance_m2(area_m2: float) -> float:
    return max(_FOOTPRINT_AREA_TOLERANCE_FLOOR_M2, area_m2 * _FOOTPRINT_AREA_TOLERANCE_FRACTION)


class SelectedFootprint(BaseModel):
    """The user's chosen BUILDING FOOTPRINT — kept deliberately distinct from the PLOT
    (`Project.plot_area_m2`) and the TARGET BUILT AREA (`Project.built_area_m2`, the room-program
    area budget this footprint was generated/entered for); see
    frontend/src/design/footprint.ts's module docstring for the full four-concept distinction this
    is the backend's own half of.

    V1 supports RECTANGLE only: `shape_type` is a `Literal`, not a free string, so an unsupported
    shape is rejected at the schema boundary (422) rather than silently accepted and mishandled by
    `_derive_footprint`/`BuildingFootprintSpec` (app/design/pipeline.py, app/geometry/models.py —
    both still rectangle-only). `polygon`, when given, is stored and returned as-is but read by
    NOTHING downstream today — carried through only so a future non-rectangular shape could extend
    this same contract instead of replacing it; its presence here is not a claim that polygon
    footprints are actually planned/solved yet.
    """

    source: FootprintSource
    shape_type: Literal["RECTANGLE"]
    target_area_m2: float = Field(gt=0)
    width_m: float = Field(gt=0)
    depth_m: float = Field(gt=0)
    area_m2: float = Field(gt=0)
    polygon: list[FootprintPoint] | None = None

    @model_validator(mode="after")
    def _area_matches_dimensions(self) -> "SelectedFootprint":
        """Rejects a malformed/tampered payload where `area_m2` doesn't actually describe
        `width_m x depth_m` — never silently repaired, never re-derived from one field or the
        other (see this task's validation requirement: reject, don't fix)."""
        actual = self.width_m * self.depth_m
        tolerance = _footprint_area_tolerance_m2(actual)
        if abs(self.area_m2 - actual) > tolerance:
            raise ValueError(
                f"selected_footprint.area_m2 ({self.area_m2}) does not match width_m * depth_m "
                f"({actual:.2f}) within tolerance ({tolerance:.3f} m²)"
            )
        return self


class ProjectCreate(BaseModel):
    city: str
    street: str
    plot_area_m2: float = Field(gt=0)
    built_area_m2: float = Field(gt=0)
    description: str
    # The user's explicit BUILDING FOOTPRINT choice (see SelectedFootprint's own docstring) — `None`
    # for a legacy caller that never went through footprint selection at all; see
    # app/design/pipeline.py's `_derive_footprint` for the resulting fallback. Optional so existing
    # callers/tests that predate this field keep working unchanged, per this task's explicit
    # "do not unnecessarily break legacy callers" requirement.
    selected_footprint: SelectedFootprint | None = None

    @field_validator("city")
    @classmethod
    def city_is_known(cls, value: str) -> str:
        return _known_city(value)

    @field_validator("street")
    @classmethod
    def street_non_empty(cls, value: str) -> str:
        return _non_empty(value, "street")

    @field_validator("description")
    @classmethod
    def description_non_empty(cls, value: str) -> str:
        return _non_empty(value, "description")

    @model_validator(mode="after")
    def street_belongs_to_city(self) -> "ProjectCreate":
        _check_street_belongs_to_city(self.city, self.street)
        return self

    @model_validator(mode="after")
    def built_area_fits_plot(self) -> "ProjectCreate":
        _check_built_area_fits_plot(self.plot_area_m2, self.built_area_m2)
        return self

    @model_validator(mode="after")
    def selected_footprint_matches_built_area(self) -> "ProjectCreate":
        """The backend's OWN check that the footprint's real area still matches `built_area_m2`
        within tolerance — never trusts that the frontend already validated this (a request can
        reach this schema from anywhere, not only the app's own UI)."""
        if self.selected_footprint is not None:
            actual = self.selected_footprint.width_m * self.selected_footprint.depth_m
            tolerance = _footprint_area_tolerance_m2(self.built_area_m2)
            if abs(actual - self.built_area_m2) > tolerance:
                raise ValueError(
                    f"selected_footprint's area ({actual:.2f} m²) does not match built_area_m2 "
                    f"({self.built_area_m2:.2f} m²) within tolerance ({tolerance:.3f} m²)"
                )
        return self


class ProjectUpdate(BaseModel):
    city: str | None = None
    street: str | None = None
    plot_area_m2: float | None = Field(default=None, gt=0)
    built_area_m2: float | None = Field(default=None, gt=0)
    description: str | None = None

    @field_validator("city")
    @classmethod
    def city_is_known(cls, value: str | None) -> str | None:
        return None if value is None else _known_city(value)

    @field_validator("street")
    @classmethod
    def street_non_empty(cls, value: str | None) -> str | None:
        return None if value is None else _non_empty(value, "street")

    @field_validator("description")
    @classmethod
    def description_non_empty(cls, value: str | None) -> str | None:
        return None if value is None else _non_empty(value, "description")

    @model_validator(mode="after")
    def street_belongs_to_city_when_both_given(self) -> "ProjectUpdate":
        # An update can change `street` without `city` (or vice versa), in which case there is no
        # way to check the pair here — the existing stored city isn't known at the schema level.
        # See specs/001-project-creation/research.md for why this is a known, accepted gap until
        # PATCH (T013) re-validates the merged city+street after applying a partial update.
        if self.city is not None and self.street is not None:
            _check_street_belongs_to_city(self.city, self.street)
        return self

    @model_validator(mode="after")
    def built_area_fits_plot_when_both_given(self) -> "ProjectUpdate":
        # Same gap/mitigation as street_belongs_to_city_when_both_given above: the route re-checks
        # the merged plot_area_m2/built_area_m2 pair against the existing stored project.
        if self.plot_area_m2 is not None and self.built_area_m2 is not None:
            _check_built_area_fits_plot(self.plot_area_m2, self.built_area_m2)
        return self


class Project(BaseModel):
    project_id: str
    city: str
    street: str
    plot_area_m2: float
    built_area_m2: float
    description: str
    status: str
    created_at: datetime
    updated_at: datetime

    # The user's explicit BUILDING FOOTPRINT choice, persisted verbatim from `ProjectCreate` — see
    # SelectedFootprint's own docstring for the PLOT / TARGET BUILT AREA / SELECTED BUILDING
    # FOOTPRINT distinction. `None` for a project created before this field existed, or by a caller
    # that never went through footprint selection — app/design/pipeline.py's `_derive_footprint`
    # falls back to the legacy derived-square footprint in that case, never fabricates a selection.
    selected_footprint: SelectedFootprint | None = None

    # Planning fields the user doesn't fill in directly — extracted from `description` by
    # Feature 02's parser (see app/requirements/). `None` means "never parsed yet"; after a parse,
    # each is present with a `source` tag (never fabricated — see specs/002-requirement-parser/).
    # `target_built_area_m2` is intentionally not one of these: `built_area_m2` above is already the
    # authoritative, validated built-area figure, so re-deriving it from free text would just create
    # a second, unreconciled source of truth for the same fact.
    floors: TaggedInt | None = None
    bedrooms: TaggedInt | None = None
    safe_room: TaggedBool | None = None
    parking_spaces: TaggedInt | None = None
    pool: PoolField | None = None
    #: Demo-path requirements. Both are extracted by the parser and both are user-correctable in
    #: the REVIEW step before generation.
    wet_rooms: TaggedInt | None = None
    open_plan: TaggedBool | None = None
    #: Requirements the brief asked for that no structured field can carry (see
    #: requirements/parser.py's `UnsupportedRequest`). Kept on the project so the REVIEW screen can
    #: show them back instead of the system dropping them silently.
    unsupported_requests: list[UnsupportedRequestRecord] = Field(default_factory=list)
    corridor_width: CorridorWidthField | None = None
    room_relationships: list[RoomRelationshipRecord] = Field(default_factory=list)
    requirements_parsed_at: datetime | None = None

    # Parametric design model — generated deterministically (no LLM) from the fields above by
    # Feature 03 (see app/design/). `None` means "never generated yet". `site_width_m`/`site_depth_m`
    # assume a square plot (a documented placeholder, not real surveyed geometry — see
    # specs/003-parametric-design-model/research.md). `design_notes` records any inputs (bedrooms/
    # safe_room) that were unknown and therefore excluded from `rooms` rather than guessed.
    site_width_m: float | None = None
    site_depth_m: float | None = None
    rooms: list[Room] | None = None
    design_notes: list[str] | None = None
    design_generated_at: datetime | None = None

    # The stable UI geometry contract (footprint/rooms/walls/doors — see
    # app/geometry/geometric_design.py's GeometricDesign) for the currently active design. Stored as a
    # plain dict, same convention as DesignVersion.solver_summary, to keep this module free of a direct
    # dependency on app/geometry (see the Room.source docstring above for the same rationale). `None`
    # for a project generated before this field existed, or never generated at all — the frontend must
    # fall back to the legacy `rooms`-only rendering path in that case, never fabricate the missing
    # walls/doors itself.
    geometric_design: dict | None = None

    # Which app/design/version.py::DesignVersion is "current" — `None` for a project created (or last
    # designed) before versioning existed; the flat fields above still hold that pre-versioning design
    # unchanged (see app/design/update.py's module docstring for the backward-compat read strategy).
    # Every NEW design generation from now on both appends a DesignVersion AND mirrors it into the flat
    # fields above, so existing frontend code that reads `project.rooms` directly keeps working.
    active_design_version_id: str | None = None

    # Soft, non-binding architectural wishes — see app/projects/preferences.py. Distinct from the
    # authoritative requirement fields above; nothing here is enforced by the solver (yet).
    preferences: list[Preference] = Field(default_factory=list)

    # Append-only audit trail of every field-level change made via app/projects/update.py, regardless of
    # whether it came from Settings or (future) Chat — the single place both write through, per that
    # module's docstring on avoiding two sources of truth.
    change_log: list[ChangeLogEntry] = Field(default_factory=list)
