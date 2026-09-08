"""Element-level provenance.

`GENERAL_GEOMETRY_ARCHITECTURE_REPORT.md` §5: provenance must exist from day one and must
attach per geometric ELEMENT, not per object — a boundary can have three surveyed edges and one
edge a user dragged, and per-object provenance would report the whole parcel as SURVEY.

`source` and `authority` are deliberately independent axes. Publicly available GIS parcel
geometry has source=GIS and authority=INDICATIVE: knowing where a fact came from does not tell
you whether it may be relied on legally.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class Source(str, Enum):
    USER = "USER"
    SURVEY = "SURVEY"
    CAD = "CAD"
    GIS = "GIS"
    REGULATION = "REGULATION"
    INFERRED = "INFERRED"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"


class Authority(str, Enum):
    """Whether the fact may be relied on, independent of where it came from."""

    #: Legally relyable (registered survey, an authoritative plan document).
    AUTHORITATIVE = "AUTHORITATIVE"
    #: Real data, not legally relyable on its own (public GIS, a scanned plan).
    INDICATIVE = "INDICATIVE"
    #: A working assumption someone made. Never relyable.
    ASSUMED = "ASSUMED"


#: Ordered weakest-first; used by `weakest_of` to propagate pessimistically.
_AUTHORITY_ORDER = (Authority.ASSUMED, Authority.INDICATIVE, Authority.AUTHORITATIVE)


@dataclass(frozen=True)
class Provenance:
    source: Source
    authority: Authority
    #: Cadastral and planning data change; a fact without a date cannot be aged out.
    as_of: date | None = None
    #: Document id, plan number, file name, free text.
    ref: str | None = None

    @property
    def is_authoritative(self) -> bool:
        return self.authority is Authority.AUTHORITATIVE


def weakest_of(*provenances: Provenance | None) -> Authority:
    """Authority propagates pessimistically: anything derived from an ASSUMED input is ASSUMED.

    A `None` provenance counts as ASSUMED — unrecorded is not the same as trustworthy.
    """
    if not provenances:
        return Authority.ASSUMED
    worst = Authority.AUTHORITATIVE
    for p in provenances:
        level = p.authority if p is not None else Authority.ASSUMED
        if _AUTHORITY_ORDER.index(level) < _AUTHORITY_ORDER.index(worst):
            worst = level
    return worst


def assumed(ref: str | None = None) -> Provenance:
    """Convenience for test fixtures and placeholder geometry."""
    return Provenance(source=Source.USER, authority=Authority.ASSUMED, ref=ref)
