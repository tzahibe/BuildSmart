"""#265 — the measurement and provenance schema (AC-1), and layer 3, canonical geometry.

The fields are **exactly #263's contract**: eleven per project (P1-P11) and six per reference value
(V1-V6). Each is annotated with its contract number so the report's table and this module cannot
drift apart.

The one design rule that matters: **there is no way to express "typical".** Every input that could
carry a convenient default is a `Measured[T]`, `Measured` has no constructor that accepts a value
without a `Provenance`, and an absent input is `None` -- which makes a formula abstain, never
estimate. The `MeasurementMethod` enum is closed and contains no member an inference could declare
itself under, so #263's `Volume / GrossArea` quotient (2.045-4.225 m on one storey) cannot enter
the schema at all.

Layers (ROOT #262 requires them separate): `RoomGeometry` is layer 3 and knows no material;
`ProductSpec` is layer 5 and knows no geometry; layer 6, pricing, does not appear -- no price, no
rate and no currency exists anywhere in this harness.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Generic, Mapping, TypeVar

from app.ai_harness.quantity_takeoff.frozen import (
    ACCURACY_BEARING,
    CALCULATION_CLASS,
    UNITS,
    CalculationClass,
    Material,
    MeasurementConvention,
    MeasurementMethod,
    Reliability,
    WEAKER_METHODS,
)

T = TypeVar("T")


# =============================================================================================
# Provenance -- #263 1.2, fields V1..V6
# =============================================================================================


@dataclass(frozen=True)
class Provenance:
    """All six of #263's per-reference-value fields. There is no partially-specified provenance:
    the constructor refuses one, because "most of a provenance" is how an unsourced number travels.
    """

    source: str
    """V1a -- the publishing body."""
    citation: str
    """V1b -- a resolvable citation: URL, DOI, drawing number, archive reference. Not "a textbook"."""
    method: MeasurementMethod
    """V2 -- how it was measured. Closed enum; the two weaker members cannot grade VERIFIED."""
    units: str
    """V3 -- explicit units. A bare number is rejected."""
    revision: str
    """V4 -- the drawing or dataset revision the value belongs to."""
    reliability: Reliability
    """V5 -- VERIFIED / STATED / DERIVED / UNVERIFIED. Only the first two may support accuracy."""
    independence: str
    """V6 -- an explicit statement that the value does NOT originate in BuildSmart, in any
    BuildSmart-derived artifact, or in a calculation of the same kind as the one under test."""

    def __post_init__(self) -> None:
        for name in ("source", "citation", "units", "revision", "independence"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"Provenance.{name} is required (#263 1.2): a reference value "
                                 f"carries all six fields or it is not a reference value")
        if self.reliability is Reliability.VERIFIED and self.method in WEAKER_METHODS:
            raise ValueError(
                f"Provenance: method {self.method.value} is one of #263's WEAKER methods (a design "
                f"dimension is an intent, not a measurement; a publisher-computed figure is their "
                f"own model's output), so it cannot grade VERIFIED"
            )

    @property
    def may_support_accuracy_claim(self) -> bool:
        """V5 alone. The project's P11 convention is the second gate; see `frozen.may_support_accuracy`."""
        return self.reliability in ACCURACY_BEARING


# =============================================================================================
# Measured -- the reason the schema cannot express "typical"
# =============================================================================================


@dataclass(frozen=True)
class Measured(Generic[T]):
    """A value that exists only together with its provenance.

    Both parameters are positional and neither has a default, so `Measured(2.5)` is a TypeError.
    There is deliberately no `Measured.typical()`, no `Measured.assumed()`, no
    `Measured.default_for()` and no module-level height, coverage or wastage constant anywhere in
    this package. An absent measurement is `None`; `None` makes the formula abstain with a reason.
    """

    value: T
    provenance: Provenance

    def __post_init__(self) -> None:
        if self.provenance is None:  # type: ignore[comparison-overlap]
            raise ValueError("Measured requires a Provenance: a promoted default is not a "
                             "provenance (#263)")
        if isinstance(self.value, (int, float)) and not isinstance(self.value, bool):
            if not math.isfinite(float(self.value)):
                raise ValueError("Measured: a non-finite measurement is not a measurement")


# =============================================================================================
# Layer 3 -- canonical geometry. Pure. Knows no material, no finish, no product.
# =============================================================================================

Point = tuple[float, float]


@dataclass(frozen=True)
class RoomGeometry:
    """A closed plan polygon and the two figures layer 4 is allowed to ask it for. Nothing in this
    class names a material; nothing in `formulas.py` touches a polygon except through it."""

    polygon: tuple[Point, ...]

    def __post_init__(self) -> None:
        pts = self._ring()
        if len(pts) < 3:
            raise ValueError("RoomGeometry: a polygon needs at least three distinct vertices")

    def _ring(self) -> tuple[Point, ...]:
        pts = tuple(tuple(float(c) for c in p) for p in self.polygon)  # type: ignore[misc]
        if len(pts) > 1 and pts[0] == pts[-1]:
            pts = pts[:-1]
        out: list[Point] = []
        for p in pts:
            if not out or p != out[-1]:
                out.append(p)  # type: ignore[arg-type]
        if len(out) > 1 and out[0] == out[-1]:
            out.pop()
        return tuple(out)

    def area_m2(self) -> float:
        """The shoelace area. This is the figure #263 measured against ResPlan's own `area_m2` and
        found identical to 0.00061299 m2 over all 179 real rooms -- which is why the harness refuses
        that field as a reference (see `selfcheck.py`)."""
        pts = self._ring()
        s = 0.0
        n = len(pts)
        for i in range(n):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % n]
            s += x1 * y2 - x2 * y1
        return abs(s) / 2.0

    def perimeter_m(self) -> float:
        pts = self._ring()
        n = len(pts)
        return sum(math.dist(pts[i], pts[(i + 1) % n]) for i in range(n))


# =============================================================================================
# The project record -- #263 1.1, fields P1..P11
# =============================================================================================


class Surface(str, Enum):
    FLOOR = "FLOOR"
    WALL = "WALL"
    CEILING = "CEILING"


class OpeningKind(str, Enum):
    DOOR = "DOOR"
    CASED_OPENING = "CASED_OPENING"
    """An archway or a doorless opening. F4 breaks at it when its width is stated."""
    WINDOW = "WINDOW"
    CEILING_OPENING = "CEILING_OPENING"
    """A skylight well or a stair void. F3 deducts it when its area is stated."""


DOOR_KINDS: frozenset[OpeningKind] = frozenset({OpeningKind.DOOR, OpeningKind.CASED_OPENING})


@dataclass(frozen=True)
class OpeningRecord:
    """P6 (door widths), P7 (window widths and sill/head) and P9 (opening areas, stated).

    Every measurement is `Measured | None`. `None` means the source did not state it, and the
    formulas abstain rather than deduce it from the others: a width and a sill/head pair would give
    an area, but an area assembled from a plan-view width and an assumed height is exactly the
    inference ROOT #262 AC-4 forbids, so `area` is never computed here.
    """

    id: str
    kind: OpeningKind
    room_ids: tuple[str, ...]
    surface: Surface = Surface.WALL
    width: Measured[float] | None = None
    """P6 / P7a."""
    sill_height: Measured[float] | None = None
    """P7b."""
    head_height: Measured[float] | None = None
    """P7c."""
    area: Measured[float] | None = None
    """P9 -- STATED BY THE SOURCE. Never derived from `width` and a height."""


@dataclass(frozen=True)
class RoomRecord:
    """One room. P1 (the plan), P4 (stated area), P5 (perimeter), P8 (wall height), P10 (finishes).

    `polygon` and `stated_area` are both optional and at least one must be present for F1/F3; both
    present is the useful case, because it is what lets the self-validation guard notice that the
    second is the first (#263's 0.00061299 m2).
    """

    id: str
    name: str = ""
    polygon: tuple[Point, ...] | None = None
    """P1 -- the plan itself, as geometry."""
    stated_area: Measured[float] | None = None
    """P4 -- per-room floor area as measured, with the method named in its provenance."""
    stated_perimeter: Measured[float] | None = None
    """P5 -- the perimeter, where the source states it rather than leaving it to the polygon."""
    wall_height: Measured[float] | None = None
    """P8 -- stated by the source. NEVER a quotient, never a regional norm, never a storey count."""
    finishes: Mapping[Surface, Measured[str]] = field(default_factory=dict)
    """P10 -- finish type / material per surface, as an input carrying provenance."""

    @property
    def geometry(self) -> RoomGeometry | None:
        return RoomGeometry(self.polygon) if self.polygon else None


@dataclass(frozen=True)
class ProductSpec:
    """Layer 5, product specifications. Knows no geometry.

    Both fields are `Measured | None`: a pack coverage is a manufacturer's published figure and a
    wastage allowance is **an input, not a guess** (this Issue says so in those words). Absent means
    the purchase quantity abstains -- the flooring AREA is unaffected, because the two are separate
    results and one missing product field must never cost the geometry.
    """

    finish_category: str
    pack_coverage_m2: Measured[float] | None = None
    wastage_fraction: Measured[float] | None = None


@dataclass(frozen=True)
class ReferenceValue:
    """A number offered as ground truth. It carries a full `Provenance` (V1-V6) or it cannot be
    constructed, and two extra declarations the self-validation guard reads."""

    material: Material
    scope: str
    """A room id, or `PROJECT` for a project-level figure."""
    value: float
    provenance: Provenance
    reference_class: CalculationClass | None = None
    """What KIND of figure this is, when the publisher says. `None` means they did not say; the
    guard then infers the class from the method (a PUBLISHER_COMPUTED figure for an area material
    is a plan-polygon area) rather than giving it the benefit of the doubt."""
    computed_from_supplied_geometry: bool = False
    """Declared: this value was computed from the very geometry supplied in this project. Refused
    outright -- it is #263 1.3 condition 4, the circular case."""

    def __post_init__(self) -> None:
        if self.provenance.units != UNITS[self.material]:
            raise ValueError(
                f"ReferenceValue({self.material.value}, {self.scope}): units "
                f"{self.provenance.units!r} != {UNITS[self.material]!r} (#263 V3). Unit errors are "
                f"the single most likely silent failure in a takeoff comparison."
            )

    @property
    def effective_class(self) -> CalculationClass | None:
        if self.reference_class is not None:
            return self.reference_class
        if self.provenance.method is MeasurementMethod.PUBLISHER_COMPUTED:
            return CALCULATION_CLASS[self.material]
        return None


PROJECT_SCOPE = "PROJECT"


@dataclass(frozen=True)
class ReferenceProject:
    """One reference project: P1-P11 plus its reference values.

    `convention` defaults to `UNSTATED` and `opening_schedule_complete` to `False`. Those are the
    only two defaults in the schema and both default to the ABSENCE of the fact, which is the safe
    direction: an unstated convention cannot support an accuracy claim and an undeclared schedule
    makes F2 abstain. Neither default ever supplies a value.
    """

    project_id: str
    publisher: str
    licence: str
    """P2 -- explicitly stated by the publisher. Empty is rejected: #263 1.3 condition 1."""
    rooms: tuple[RoomRecord, ...] = ()
    openings: tuple[OpeningRecord, ...] = ()
    scale: Measured[float] | None = None
    """P3 -- metric scale, MEASURED. The method enum has no member for an inferred scale."""
    wall_thickness: Measured[float] | None = None
    """P11a."""
    convention: MeasurementConvention = MeasurementConvention.UNSTATED
    """P11b -- internal clear / centre-line / external, or the explicit absence."""
    opening_schedule_complete: bool = False
    """Declared by the source: every opening of every room is listed. Without it F2 abstains rather
    than deduct zero, because "no openings listed" and "openings not listed" are different facts."""
    distinguishes_finishes: bool = False
    """P10 -- the source distinguishes finishes per surface, so a missing finish is a missing
    measurement rather than a field the source never had."""
    product_specs: Mapping[str, ProductSpec] = field(default_factory=dict)
    """Layer 5, keyed by finish category."""
    references: tuple[ReferenceValue, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.licence).strip():
            raise ValueError("ReferenceProject.licence is required (#263 P2 / 1.3 condition 1): a "
                             "dataset that cannot be used legally is not a dataset")
        ids = [r.id for r in self.rooms]
        if len(set(ids)) != len(ids):
            raise ValueError("ReferenceProject: duplicate room id")

    def room(self, room_id: str) -> RoomRecord | None:
        for r in self.rooms:
            if r.id == room_id:
                return r
        return None

    def openings_of(self, room_id: str) -> tuple[OpeningRecord, ...]:
        return tuple(o for o in self.openings if room_id in o.room_ids)

    def references_for(self, material: Material, scope: str) -> tuple[ReferenceValue, ...]:
        return tuple(r for r in self.references if r.material is material and r.scope == scope)
