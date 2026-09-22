"""``Brief`` — the input to ``retrieval.retrieve`` / ``synthesis.synthesize`` / ``adaptation.adapt``:
a BuildSmart brief plus the architectural preferences this POC's retrieval/synthesis/adaptation
score against.

``program`` is ``app.vertical_slice.spec.ProgramSpec`` — the SAME hard-requirements contract the
live vertical slice already uses (bedrooms, safe_room, wet_rooms, wet_room_kinds, relationships,
target_built_area_m2). Reused rather than duplicated: it is what "authoritative requirements
always win" means for this POC too, and it is the concrete answer to Issue #95's requirement that
retrieval score against "adjacency requirements (``ProgramSpec.relationships``)". Nothing in this
package writes to ``app/`` — this is a read-only import of a stable contract, same direction
``app.vertical_slice.concept_spec`` itself takes on ``app.vertical_slice.spec.CirculationStyle``.

The remaining fields are this POC's own additions — preferences ``ProgramSpec``/``HouseConcept``
have no field for, needed so a benchmark brief can state an architectural preference explicitly
(e.g. "I want an L-shaped footprint") rather than have one inferred:

- ``circulation_preference`` / ``zoning_preference``: one of ``patterns.py``'s own vocabulary
  (``ArchitecturalPattern.circulation_class`` / ``.zoning``), or ``None`` for "no preference".
- ``outline_preference``: ``"RECTANGULAR"`` / ``"TWO_WING"`` (an L/two-wing footprint), or ``None``.
- ``exposure_requirement``: the minimum share (0-1) of habitable rooms the brief wants exposed to
  the exterior, or ``None`` for "not stated".

All preferences are non-binding scoring inputs for retrieval — never hard requirements. The hard
requirements live entirely on ``program`` and are what ``synthesis.py`` copies onto every
``ConceptSpec`` untouched by any reference.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.vertical_slice.spec import ProgramSpec


@dataclass(frozen=True)
class Brief:
    program: ProgramSpec
    stories: int = 1
    circulation_preference: str | None = None
    outline_preference: str | None = None
    zoning_preference: str | None = None
    exposure_requirement: float | None = None
