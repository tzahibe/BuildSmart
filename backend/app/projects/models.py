from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.localities.data import CITY_STREETS, KNOWN_CITIES


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


class ProjectCreate(BaseModel):
    city: str
    street: str
    plot_area_m2: float = Field(gt=0)
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


class ProjectUpdate(BaseModel):
    city: str | None = None
    street: str | None = None
    plot_area_m2: float | None = Field(default=None, gt=0)
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


class Project(BaseModel):
    project_id: str
    city: str
    street: str
    plot_area_m2: float
    description: str
    status: str
    created_at: datetime
    updated_at: datetime
