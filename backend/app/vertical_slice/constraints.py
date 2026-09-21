"""Typed constraints that must survive the whole pipeline, never silently dropped.

Issue #35. SAFE_ROOM/MAMAD is the first (and, today, only) kind. Before this module, "is there a
safe room" was a single `bool` (`ProgramSpec.safe_room`) read independently by
`concept_generator.py`, `validation.py`'s C4, `renderer.py` and the hub/L-massing guards — nothing
carried WHY the room exists (a person asked for it vs. an assumption this codebase does not make)
and nothing PROVED it was still there at each later stage. A fallback ladder, a candidate swap, or
an alternative selection could in principle drop the room before C4 ever saw the design, and C4's
own loop (`for z in fixture.zones: if not z.is_safe_room: continue`) would simply find nothing to
check and report "safe room compliant" — a false pass, not a caught defect.

`TypedConstraint` is derived ONCE, from the requirement itself (see `derive_safe_room_constraint`),
and is then CHECKED — not merely carried — after concept generation, after geometry realization,
and in the validator (C4, extended below). `assert_realized` is the one place that decision is
made: an authoritative constraint not found present raises `SafeRoomDropped` rather than letting
the pipeline continue toward delivering a plan without it. `app.demo.service` turns that exception
(or an equivalent C4 failure) into a refusal with code `SAFE_ROOM_DROPPED`.

Compliance applicability (WHETHER the law requires a safe room for a given brief) is explicitly
out of scope for #35 — see the Issue's "Out of scope". `ConstraintSource.COMPLIANCE` exists so a
future decision has somewhere to put that answer; nothing in this codebase derives it today, and
`derive_safe_room_constraint` never invents a requirement the brief did not carry.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConstraintKind(str, Enum):
    SAFE_ROOM = "SAFE_ROOM"


class ConstraintSource(str, Enum):
    """WHERE an authoritative constraint's requirement came from.

    USER: the brief itself asked for it (however the parser tagged its own confidence —
    "requested" or "inferred" — this codebase has no path that derives a safe room from anything
    OTHER than the person's own words, so both collapse to USER here).
    COMPLIANCE: reserved for a future legal-applicability rule. Not produced anywhere today.
    NONE: the brief carries no such requirement. A `NONE`-source constraint is never
    `authoritative`, and nothing downstream may treat it as a reason to add the room.
    """

    USER = "USER"
    COMPLIANCE = "COMPLIANCE"
    NONE = "NONE"


#: The regulated net-area minimum a safe room is sized to — mirrors
#: `concept_generator.ROOM_TEMPLATES[ProgramRole.SAFE_ROOM].min_area_m2`. PARAMETER · UNVERIFIED,
#: like that template row's own comment: not sourced from a specific regulation number. Kept as
#: its own constant (not imported from `concept_generator`) to avoid a cycle — that module imports
#: this one's `assert_realized`.
SAFE_ROOM_MIN_AREA_M2 = 9.0


@dataclass(frozen=True)
class TypedConstraint:
    kind: ConstraintKind
    source: ConstraintSource
    #: A plan that does not realize this constraint must be refused, never delivered with a
    #: warning. Always `False` for `ConstraintSource.NONE`.
    authoritative: bool
    min_area_m2: float | None = None


#: The constraint for a brief that carries no safe-room requirement at all.
NO_SAFE_ROOM_CONSTRAINT = TypedConstraint(ConstraintKind.SAFE_ROOM, ConstraintSource.NONE, False)


def derive_safe_room_constraint(requested: bool) -> TypedConstraint:
    """The one place a SAFE_ROOM `TypedConstraint` is derived.

    `requested` is already the resolved reading of the brief (the parser's `TaggedBool.value`,
    or the review screen's correction of it) — this function does not itself read Hebrew text or
    decide "requested" vs "inferred"; it turns that resolved bool into the typed constraint every
    later stage checks against. `False`/`None` -> `NO_SAFE_ROOM_CONSTRAINT`: never invented.
    """
    if not requested:
        return NO_SAFE_ROOM_CONSTRAINT
    return TypedConstraint(ConstraintKind.SAFE_ROOM, ConstraintSource.USER, True,
                           SAFE_ROOM_MIN_AREA_M2)


#: The `ValidationReport` C4 detail (and the marker `app.demo.service` looks for) when an
#: authoritative constraint has no realized room. Shared so the two files cannot drift on the
#: exact wording.
SAFE_ROOM_NOT_REALIZED_DETAIL = "authoritative SAFE_ROOM constraint has no realized zone"


class SafeRoomDropped(Exception):
    """An authoritative SAFE_ROOM constraint was not realized at `stage`.

    Raised by `assert_realized`. `app.demo.service.generate_demo_design` catches this (from the
    concept stage) and turns it into a `DemoGenerationError` with code `SAFE_ROOM_DROPPED` —
    refused, never delivered without the room. A drop caught later, inside the validator itself,
    is instead reported as a normal C4 failure (see `validation.validate`) and escalated to the
    same refusal code by `app.demo.service._finish`, alongside this codebase's other
    check-specific diagnoses (C14 -> CORRIDOR_WIDTH_NOT_FEASIBLE, C15 -> ROOM_RELATIONSHIP_NOT_FEASIBLE).
    """

    def __init__(self, stage: str, detail: str = "") -> None:
        self.stage = stage
        self.detail = detail
        message = f"SAFE_ROOM_DROPPED at {stage}"
        if detail:
            message = f"{message}: {detail}"
        super().__init__(message)


def assert_realized(constraint: TypedConstraint, present: bool, *, stage: str,
                    detail: str = "") -> None:
    """Fail closed: an authoritative constraint not found `present` at `stage` raises
    `SafeRoomDropped` instead of letting the pipeline continue toward a plan without it."""
    if constraint.authoritative and not present:
        raise SafeRoomDropped(stage, detail)
