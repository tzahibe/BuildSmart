"""Typed spatial constraints, and the parcel / buildable-region separation.

Two rules from `GENERAL_GEOMETRY_ARCHITECTURE_REPORT.md` are structural here:

§4 — ONE constraint type with a role, not six sibling classes. All roles participate in the same
     boolean algebra over the same geometry; six classes would mean six copies of that algebra
     and six chances for them to diverge. The distinctions that DO matter are kept as roles:
     NO_BUILD_REGION shrinks the envelope, OBSTACLE punches a hole inside it — different because
     a hole is the one thing the current rectangular solver cannot represent at all.

§4/§7 — This layer knows no law. It may know `NO_BUILD_REGION = <geometry>`; it may not know
     that some regulation requires 3 m. There is deliberately no `municipality`, `zone_code` or
     `plan_id` parameter anywhere in this module — if one is ever needed here, the separation
     has leaked. Note also that coverage/FAR/height ratios are NOT representable here on
     purpose: they constrain the produced design, not the domain, and turning them into geometry
     would produce plausible, quietly incorrect plans.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .primitives import MultiRegion
from .provenance import Authority, Provenance, weakest_of


class ConstraintRole(str, Enum):
    #: The cadastral/surveyed parcel outline. A legal identity, not a permission to build.
    PARCEL_BOUNDARY = "PARCEL_BOUNDARY"
    #: A region established as buildable.
    BUILDABLE_REGION = "BUILDABLE_REGION"
    #: Subtracts from the envelope (a setback strip, an easement).
    NO_BUILD_REGION = "NO_BUILD_REGION"
    #: Sits INSIDE the envelope and must not be occupied (column, shaft). Punches a hole.
    OBSTACLE = "OBSTACLE"
    #: The geometric result of a setback rule. The rule itself lives in the regulation layer.
    SETBACK_REGION = "SETBACK_REGION"
    #: Must remain reachable/unbuilt (driveway, entrance path).
    ACCESS_REQUIRED_REGION = "ACCESS_REQUIRED_REGION"


@dataclass(frozen=True)
class GeometricConstraint:
    id: str
    role: ConstraintRole
    geometry: MultiRegion
    provenance: Provenance
    note: str | None = None

    @property
    def subtracts_from_envelope(self) -> bool:
        """NO_BUILD/SETBACK shrink the buildable region; OBSTACLE leaves it but forbids
        occupancy; ACCESS_REQUIRED constrains what may be placed, not where the envelope is."""
        return self.role in (ConstraintRole.NO_BUILD_REGION, ConstraintRole.SETBACK_REGION)


@dataclass(frozen=True)
class Parcel:
    """Survey/cadastral fact with a legal identity. NOT a statement about buildability."""

    id: str
    geometry: MultiRegion
    provenance: Provenance
    #: e.g. gush/helka. Free text here on purpose — no Israeli data integration in this layer.
    legal_ref: str | None = None


class Knowledge(str, Enum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"


class UnknownBuildableRegionError(RuntimeError):
    """Raised when something tries to plan on a buildable region we do not actually know."""


@dataclass(frozen=True)
class BuildableRegion:
    """Derived, and explicitly allowed to be UNKNOWN (report §5, task §4).

    The failure mode this type exists to prevent: lacking setback data, quietly falling back to
    the parcel boundary and producing a confident, renderable, legally impossible building. A
    missing-data path that defaults to "buildable == parcel" is worse than an error, so there is
    no constructor that can produce KNOWN geometry without geometry being supplied, and
    `require_known()` is the only way to get at it.
    """

    knowledge: Knowledge
    geometry: MultiRegion | None = None
    derived_from: tuple[str, ...] = ()
    provenance: Provenance | None = None
    unknown_reason: str | None = None

    def __post_init__(self) -> None:
        if self.knowledge is Knowledge.KNOWN and self.geometry is None:
            raise ValueError("a KNOWN BuildableRegion must carry geometry")
        if self.knowledge is Knowledge.UNKNOWN and self.geometry is not None:
            raise ValueError(
                "an UNKNOWN BuildableRegion must not carry geometry — partial knowledge must be "
                "modelled as KNOWN geometry with weaker provenance, not as UNKNOWN with a guess"
            )

    @staticmethod
    def known(geometry: MultiRegion, provenance: Provenance,
              derived_from: tuple[str, ...] = ()) -> "BuildableRegion":
        return BuildableRegion(Knowledge.KNOWN, geometry, derived_from, provenance)

    @staticmethod
    def unknown(reason: str) -> "BuildableRegion":
        return BuildableRegion(Knowledge.UNKNOWN, None, (), None, reason)

    @property
    def is_known(self) -> bool:
        return self.knowledge is Knowledge.KNOWN

    def require_known(self) -> MultiRegion:
        """The only accessor. Downstream code cannot reach the geometry without passing here,
        so 'we did not know' can never be mistaken for 'there was nothing there'."""
        if self.knowledge is Knowledge.UNKNOWN or self.geometry is None:
            raise UnknownBuildableRegionError(
                f"buildable region is UNKNOWN and must not be inferred from the parcel boundary: "
                f"{self.unknown_reason or 'no reason recorded'}"
            )
        return self.geometry


@dataclass(frozen=True)
class SiteConstraints:
    """Everything geometric known about one site. The interface between the regulation/data
    layer above and the geometry layer below."""

    parcel: Parcel
    constraints: tuple[GeometricConstraint, ...] = ()
    buildable: BuildableRegion = field(
        default_factory=lambda: BuildableRegion.unknown("not yet computed")
    )

    def by_role(self, role: ConstraintRole) -> tuple[GeometricConstraint, ...]:
        return tuple(c for c in self.constraints if c.role is role)

    def effective_authority(self) -> Authority:
        """Pessimistic propagation (report §5): a design derived from any ASSUMED input is
        ASSUMED, and may be presented as a study but never as a submission-grade output."""
        return weakest_of(
            self.parcel.provenance,
            *(c.provenance for c in self.constraints),
            *( (self.buildable.provenance,) if self.buildable.is_known else () ),
        )
