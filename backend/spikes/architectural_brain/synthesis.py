"""``synthesize(brief, references) -> list[ConceptSpec]``: 2-3 candidate ``ConceptSpec``s whose
zoning / circulation class / wet-core strategy / entrance relationship / bedroom grouping are each
taken from a DIFFERENT retrieved reference's pattern, never from one reference's full room list.

Algorithm (deterministic, no randomness): ``references`` arrives sorted best-first (as
``retrieval.retrieve`` returns it). For candidate ``i`` (``i = 0, 1, 2, ...``):

- ``primary = references[i]`` supplies ``circulation_class``, ``zoning`` and ``wet_core_strategy``
  (the three fields ``topologically_distinct`` compares — see below).
- ``secondary = references[i+1]`` (wrapping around) supplies ``entrance_relationship`` and
  ``bedroom_grouping_share`` — a DIFFERENT reference from ``primary``, so every candidate always
  cites >= 2 distinct plans, never one reference's own pattern set wholesale.

A candidate is kept only if its ``(circulation_class, zoning, wet_core_strategy)`` triple has not
already been produced by an earlier candidate (``topologically_distinct`` is exactly this triple's
inequality) -- so the returned list is pairwise topologically distinct by construction, not by a
separate filter step. Synthesis stops at 3 candidates or when every reference has been tried as a
primary, whichever comes first; ``references`` must hold at least 2 entries (retrieval always
returns 5-10, so this is never a live concern from ``retrieve``'s own output).

Every authoritative requirement of the brief -- SAFE_ROOM, bedroom count, wet-room kinds -- is
copied from ``brief.program`` directly onto every candidate, never derived from a reference: no
donor plan can add or remove one of these, whatever pattern it contributes.
"""
from __future__ import annotations

from dataclasses import dataclass

from spikes.architectural_brain.brief import Brief
from spikes.architectural_brain.plan_reference import Room
from spikes.architectural_brain.retrieval import RetrievedReference


@dataclass(frozen=True)
class ConceptReference:
    plan_id: str
    pattern_used: str
    why: str


@dataclass(frozen=True)
class ConceptSpec:
    concept_id: str
    circulation_class: str
    zoning: str
    wet_core_strategy: str
    entrance_relationship: str
    bedroom_grouping_share: float | None
    references: tuple[ConceptReference, ...]
    # Authoritative requirements -- copied from brief.program, never from a reference.
    bedrooms: int
    safe_room: bool
    wet_rooms: int
    wet_room_kinds: tuple[str, ...]
    stories: int
    # The primary donor's own rooms, before any adaptation -- adaptation.py's starting point.
    baseline_rooms: tuple[Room, ...]


def topologically_distinct(a: ConceptSpec, b: ConceptSpec) -> bool:
    """Same rule as ``app.vertical_slice.concept_spec.topologically_distinct``: two candidates
    read as the same house iff they agree on all three of circulation_class/zoning/wet_core_strategy."""
    return ((a.circulation_class, a.zoning, a.wet_core_strategy)
            != (b.circulation_class, b.zoning, b.wet_core_strategy))


def _build_candidate(brief: Brief, idx: int, primary: RetrievedReference,
                     secondary: RetrievedReference) -> ConceptSpec:
    references = (
        ConceptReference(
            plan_id=primary.plan_id, pattern_used="circulation_class",
            why=f"{primary.plan_id} was retrieved (score {primary.total_score:.3f}); its "
               f"circulation_class={primary.pattern.circulation_class} is used as this "
               f"candidate's circulation parti."),
        ConceptReference(
            plan_id=primary.plan_id, pattern_used="zoning",
            why=f"{primary.plan_id}'s zoning={primary.pattern.zoning} is used as this "
               f"candidate's public/private organisation."),
        ConceptReference(
            plan_id=primary.plan_id, pattern_used="wet_core_strategy",
            why=f"{primary.plan_id}'s wet_core_strategy={primary.pattern.wet_core_strategy} is "
               f"used as this candidate's wet-room grouping strategy."),
        ConceptReference(
            plan_id=secondary.plan_id, pattern_used="entrance_relationship",
            why=f"{secondary.plan_id} (a different retrieved reference, score "
               f"{secondary.total_score:.3f}) supplies entrance_relationship="
               f"{secondary.pattern.entrance_relationship}."),
        ConceptReference(
            plan_id=secondary.plan_id, pattern_used="bedroom_grouping",
            why=f"{secondary.plan_id} supplies bedroom_grouping="
               f"{secondary.pattern.bedroom_grouping}."),
    )
    return ConceptSpec(
        concept_id=f"concept-{idx}",
        circulation_class=primary.pattern.circulation_class,
        zoning=primary.pattern.zoning,
        wet_core_strategy=primary.pattern.wet_core_strategy,
        entrance_relationship=secondary.pattern.entrance_relationship,
        bedroom_grouping_share=secondary.pattern.bedroom_grouping,
        references=references,
        bedrooms=brief.program.bedrooms,
        safe_room=brief.program.safe_room,
        wet_rooms=brief.program.wet_rooms,
        wet_room_kinds=tuple(k.kind.value for k in brief.program.wet_room_kinds),
        stories=brief.stories,
        baseline_rooms=primary.plan_reference.rooms,
    )


def synthesize(brief: Brief, references: list[RetrievedReference], max_candidates: int = 3) -> list[ConceptSpec]:
    if len(references) < 2:
        raise ValueError("synthesize needs at least 2 references to combine patterns from "
                         f"(got {len(references)})")

    candidates: list[ConceptSpec] = []
    seen_triples: set[tuple[str, str, str]] = set()
    n = len(references)
    for i in range(n):
        primary = references[i]
        secondary = references[(i + 1) % n]
        if secondary.plan_id == primary.plan_id:
            secondary = references[(i + 2) % n]
        triple = (primary.pattern.circulation_class, primary.pattern.zoning,
                 primary.pattern.wet_core_strategy)
        if triple in seen_triples:
            continue
        seen_triples.add(triple)
        candidates.append(_build_candidate(brief, len(candidates), primary, secondary))
        if len(candidates) == max_candidates:
            break
    return candidates
