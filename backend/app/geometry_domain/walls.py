"""Orthogonal wall facts.

Fixes the domain-model defect the First Vertical Slice actually hit (report §8, task §7).

The solver's `geometry_core.model.WallType` resolves four competing facts into ONE enum by
precedence (`OPEN > RC_SAFE_ROOM > EXTERIOR > PARTITION`). That is correct for what the solver
needs it for — deciding a wall's THICKNESS — and Geometry Core is frozen, so it is untouched.
But it is lossy: a ממ"ד wall that is also on the building envelope resolves to RC_SAFE_ROOM and
the EXTERIOR fact is destroyed. Window placement, which looked for EXTERIOR, then silently found
no eligible side for the safe room and produced a safe room with no window.

Here the two facts are kept orthogonal, because they answer different questions and come from
different places:

    boundary_context  — GEOMETRIC. Is this segment on the building envelope?
                        Derived from geometry, never from construction type.
    construction      — PROGRAM/REGULATION. RC because it is a ממ"ד; structural because it
                        carries load. Independent of where the wall sits.

`opening_policy` is DERIVED, never stored: it is a function of (context, construction), and
storing it would let it disagree with its own inputs.

Deliberately NOT modelled yet: thermal, acoustic, fire, U-value, finish. Adding them now would
create fields nothing validates.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BoundaryContext(str, Enum):
    """Where the wall sits. A geometric fact."""

    EXTERIOR = "EXTERIOR"
    INTERIOR = "INTERIOR"
    #: Shared with a neighbouring property. Reserved; unused by the current single-house scope.
    PARTY = "PARTY"


class Construction(str, Enum):
    """What the wall is made of. A program/regulation fact."""

    #: No wall at all — two zones of one open-plan space.
    NONE = "NONE"
    STANDARD_PARTITION = "STANDARD_PARTITION"
    RC_SAFE_ROOM = "RC_SAFE_ROOM"
    STRUCTURAL = "STRUCTURAL"


class OpeningPolicy(str, Enum):
    FREE = "FREE"                      # ordinary doors/windows permitted
    RESTRICTED = "RESTRICTED"          # openings permitted but specified (e.g. blast-rated)
    NONE_PERMITTED = "NONE_PERMITTED"  # no opening may be cut


@dataclass(frozen=True)
class WallFacts:
    """Two independent facts, plus a derived policy. Never collapsed into one value."""

    boundary_context: BoundaryContext
    construction: Construction

    @property
    def opening_policy(self) -> OpeningPolicy:
        if self.construction is Construction.NONE:
            # An open-plan boundary is not a wall; there is nothing to cut an opening into.
            return OpeningPolicy.NONE_PERMITTED
        if self.construction is Construction.RC_SAFE_ROOM:
            # This is the case the vertical slice got wrong: an exterior ממ"ד wall CAN take an
            # opening (a blast-rated window), an interior one is far more constrained. The
            # distinction is only expressible because the two facts stayed separate.
            return (
                OpeningPolicy.RESTRICTED
                if self.boundary_context is BoundaryContext.EXTERIOR
                else OpeningPolicy.NONE_PERMITTED
            )
        return OpeningPolicy.FREE

    @property
    def is_on_envelope(self) -> bool:
        return self.boundary_context is BoundaryContext.EXTERIOR

    @property
    def can_take_a_window(self) -> bool:
        """Exterior exposure AND a construction that permits an opening — two facts, both
        required, neither derivable from the other."""
        return self.is_on_envelope and self.opening_policy is not OpeningPolicy.NONE_PERMITTED
