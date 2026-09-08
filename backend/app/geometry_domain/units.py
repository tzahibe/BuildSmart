"""Direction-aware quantization.

Addresses the finding in `GENERAL_GEOMETRY_ARCHITECTURE_REPORT.md` §3/§14: the solver's
`geometry_core.model.m_to_u()` is `int(round(m / UNIT_M))` — round-to-NEAREST. That is correct
for its own job (dimensioning a room the solver is free to size) and is deliberately left
untouched. It is *wrong* for quantizing a boundary, because rounding a boundary outward hands
the solver up to half a grid unit of area that does not exist, on every edge.

This module exists so that any future Safe Geometry Adapter is quantized on purpose:

  * `rounding` is KEYWORD-ONLY and has NO DEFAULT — you cannot quantize by accident.
  * The unsafe mode is spelled `Rounding.NEAREST_UNSAFE`, so it cannot be chosen quietly.
  * The intent-named helpers below are the ones call sites should normally use; they read as
    the guarantee they provide ("no overstate") rather than as a rounding mode.

Authoritative geometry is in METRES (float). Grid units belong to the solver.
"""
from __future__ import annotations

import math
from enum import Enum

# Must match geometry_core.model.UNIT_M. Duplicated deliberately rather than imported: this
# module is in the domain layer and must not depend on the solver. The equality is asserted in
# tests/vertical_slice/test_geometry_adapter.py, which is allowed to see both.
UNIT_M = 0.05

# Absorbs float representation error so an exact grid value never gets bumped a unit.
# (0.30 / 0.05 evaluates to 5.999999999999999 in IEEE-754, which would floor to 5.)
_EPS = 1e-9


class Rounding(str, Enum):
    """How to resolve a value that falls between grid units."""

    #: Toward the region interior — the result never covers space the input did not.
    INWARD = "INWARD"
    #: Away from the region interior — the result always covers at least the input.
    OUTWARD = "OUTWARD"
    #: Nearest unit. Can gain up to half a unit of nonexistent space. Dimensioning only,
    #: never boundaries. Named so it cannot be selected without noticing.
    NEAREST_UNSAFE = "NEAREST_UNSAFE"


def quantize_m(value_m: float, *, rounding: Rounding) -> int:
    """Metres -> whole grid units. `rounding` is required and keyword-only, by design.

    INWARD/OUTWARD here are expressed for a *magnitude* (a length, a clearance): INWARD
    shrinks it, OUTWARD grows it. For a coordinate, whether inward means floor or ceil depends
    on which side the interior is on — use `lower_bound_units` / `upper_bound_units` instead of
    reasoning about it at the call site.
    """
    raw = value_m / UNIT_M
    if rounding is Rounding.INWARD:
        return math.floor(raw + _EPS)
    if rounding is Rounding.OUTWARD:
        return math.ceil(raw - _EPS)
    if rounding is Rounding.NEAREST_UNSAFE:
        return int(round(raw))
    raise ValueError(f"unknown rounding mode: {rounding!r}")


def lower_bound_units(value_m: float) -> int:
    """A region's low-side coordinate (min x / min y). Rounds UP, moving the boundary inward."""
    return math.ceil(value_m / UNIT_M - _EPS)


def upper_bound_units(value_m: float) -> int:
    """A region's high-side coordinate (max x / max y). Rounds DOWN, moving the boundary inward."""
    return math.floor(value_m / UNIT_M + _EPS)


def length_units_no_overstate(value_m: float) -> int:
    """A length that must never be claimed larger than it is (available width, buildable depth)."""
    return math.floor(value_m / UNIT_M + _EPS)


def clearance_units_no_understate(value_m: float) -> int:
    """A required clearance/setback that must never be applied smaller than it is."""
    return math.ceil(value_m / UNIT_M - _EPS)


def units_to_m(units: int) -> float:
    return round(units * UNIT_M, 4)
