from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

from app.localities.data import CITY_STREETS, KNOWN_CITIES


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
    """One room in a generated parametric design model — see app/design/generator.py."""

    type: str
    floor: int
    area_m2: float
    x: float
    y: float
    width_m: float
    depth_m: float


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


def _check_built_area_fits_plot(plot_area_m2: float, built_area_m2: float) -> None:
    if built_area_m2 >= plot_area_m2:
        raise ValueError("built_area_m2 must be smaller than plot_area_m2")


class ProjectCreate(BaseModel):
    city: str
    street: str
    plot_area_m2: float = Field(gt=0)
    built_area_m2: float = Field(gt=0)
    description: str

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
