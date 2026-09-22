"""``retrieve(brief, site, corpus, k=8) -> list[RetrievedReference]``: a deterministic WEIGHTED
score over architectural terms — never text embeddings, never a single dominant term.

Nine terms, each a pure function of ``(brief, site, entry)`` returning a score in [0, 1], combined
by a fixed weight (documented in ``docs/reports/poc-architectural-brain/brain.md`` alongside this
module). A term whose brief-side input is unstated (e.g. no ``outline_preference``, no
``zoning_preference``) contributes a fixed NEUTRAL score of 0.5 rather than being dropped from the
sum — every candidate gets the same neutral credit on that term, so it does not discriminate
between candidates (equivalent to not scoring on it) without needing to renormalise the remaining
weights. This keeps the total always exactly 1.0 and the per-term contributions always comparable
across different briefs.

WEIGHTS (sum to 1.0) — chosen so no single term can dominate the ranking by itself, and so that a
brief stating an outline/circulation preference (``footprint_aspect_shape`` + ``circulation_class``
= 0.25 combined) can out-rank a same-area, different-programme plan on ``built_area`` (0.15) alone:

    built_area              0.15
    room_count_types        0.20
    footprint_aspect_shape  0.10
    adjacency               0.10
    public_private_org      0.10
    circulation_class       0.15
    floors                  0.05
    wet_room_requirements   0.10
    exterior_exposure       0.05

Every ``RetrievedReference`` carries the per-term ``TermScore`` (weight, raw score, weighted
contribution, and a short numeric detail) plus a one-paragraph WHY built from its top-contributing
terms — never a black-box number.
"""
from __future__ import annotations

from dataclasses import dataclass

from spikes.architectural_brain.brief import Brief
from spikes.architectural_brain.corpus_io import CorpusEntry
from spikes.architectural_brain.patterns import ArchitecturalPattern
from spikes.architectural_brain.plan_reference import PlanReference

from app.vertical_slice.spec import PlotSpec, RoomRelation

NEUTRAL = 0.5

WEIGHTS: dict[str, float] = {
    "built_area": 0.15,
    "room_count_types": 0.20,
    "footprint_aspect_shape": 0.10,
    "adjacency": 0.10,
    "public_private_org": 0.10,
    "circulation_class": 0.15,
    "floors": 0.05,
    "wet_room_requirements": 0.10,
    "exterior_exposure": 0.05,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


@dataclass(frozen=True)
class TermScore:
    term: str
    weight: float
    score: float
    contribution: float
    detail: str


@dataclass(frozen=True)
class RetrievedReference:
    plan_id: str
    total_score: float
    term_scores: tuple[TermScore, ...]
    why: str
    plan_reference: PlanReference
    pattern: ArchitecturalPattern


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _bbox_extent(points: tuple) -> tuple[float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (max(xs) - min(xs), max(ys) - min(ys))


def _bbox_aspect(w: float, h: float) -> float:
    lo, hi = sorted((abs(w), abs(h)))
    return hi / lo if lo > 1e-6 else float("inf")


def _relative_closeness(a: float, b: float) -> float:
    """1.0 when equal, decaying toward 0.0 as the relative gap grows -- used for every "how close
    are these two numbers" term below."""
    denom = max(a, b)
    if denom <= 1e-9:
        return 1.0
    return _clip01(1.0 - abs(a - b) / denom)


def _score_built_area(brief: Brief, entry: CorpusEntry) -> TermScore:
    target = brief.program.target_built_area_m2
    if target is None:
        return TermScore("built_area", WEIGHTS["built_area"], NEUTRAL,
                          WEIGHTS["built_area"] * NEUTRAL, "no target_built_area_m2 stated")
    per_floor_target = target / max(brief.stories, 1)
    ref_area = entry.plan_reference.derived.footprint_area_m2
    score = _relative_closeness(per_floor_target, ref_area)
    detail = f"brief {per_floor_target:.1f} m2/floor vs plan {ref_area:.1f} m2"
    return TermScore("built_area", WEIGHTS["built_area"], score,
                      WEIGHTS["built_area"] * score, detail)


def _score_room_count_types(brief: Brief, entry: CorpusEntry) -> TermScore:
    counts = entry.plan_reference.derived.room_type_counts
    ref_wet = counts.get("BATHROOM", 0) + counts.get("TOILET", 0)
    brief_counts = {
        "BEDROOM": brief.program.bedrooms,
        "WET": brief.program.wet_rooms,
        "KITCHEN": 1,
        "LIVING": 1,
        "SAFE_ROOM": 1 if brief.program.safe_room else 0,
    }
    ref_counts = {
        "BEDROOM": counts.get("BEDROOM", 0),
        "WET": ref_wet,
        "KITCHEN": counts.get("KITCHEN", 0),
        "LIVING": counts.get("LIVING", 0),
        "SAFE_ROOM": counts.get("SAFE_ROOM", 0),
    }
    diff_sum = sum(abs(brief_counts[t] - ref_counts[t]) for t in brief_counts)
    max_sum = sum(max(brief_counts[t], ref_counts[t]) for t in brief_counts)
    score = 1.0 if max_sum == 0 else _clip01(1.0 - diff_sum / max_sum)
    detail = f"brief {brief_counts} vs plan {ref_counts}"
    return TermScore("room_count_types", WEIGHTS["room_count_types"], score,
                      WEIGHTS["room_count_types"] * score, detail)


def _score_footprint_aspect_shape(brief: Brief, site: PlotSpec, entry: CorpusEntry) -> TermScore:
    site_w, site_h = site.buildable_size_m()
    site_aspect = _bbox_aspect(site_w, site_h)
    ref_w, ref_h = _bbox_extent(entry.plan_reference.footprint)
    ref_aspect = _bbox_aspect(ref_w, ref_h)
    aspect_sim = _relative_closeness(site_aspect, ref_aspect)

    if brief.outline_preference is None:
        score = aspect_sim
        detail = f"aspect similarity only (no outline_preference): site {site_aspect:.2f} vs plan {ref_aspect:.2f}"
    else:
        is_two_wing = entry.pattern.circulation_class == "TWO_WING"
        wants_two_wing = brief.outline_preference == "TWO_WING"
        outline_match = 1.0 if is_two_wing == wants_two_wing else 0.0
        score = 0.5 * aspect_sim + 0.5 * outline_match
        detail = (f"outline_preference={brief.outline_preference}, plan circulation_class="
                  f"{entry.pattern.circulation_class} (match={outline_match}), aspect_sim={aspect_sim:.2f}")
    return TermScore("footprint_aspect_shape", WEIGHTS["footprint_aspect_shape"], score,
                      WEIGHTS["footprint_aspect_shape"] * score, detail)


_RELATION_KINDS_AS_TOUCHING = {RoomRelation.ADJACENT, RoomRelation.DIRECT_ACCESS, RoomRelation.NEAR}


def _score_adjacency(brief: Brief, entry: CorpusEntry) -> TermScore:
    relationships = brief.program.relationships
    if not relationships:
        return TermScore("adjacency", WEIGHTS["adjacency"], NEUTRAL,
                          WEIGHTS["adjacency"] * NEUTRAL, "no relationships stated")

    ref = entry.plan_reference
    touching_pairs = {frozenset((e.room_a, e.room_b)) for e in ref.adjacency_edges}
    door_pairs = {frozenset((e.room_a, e.room_b)) for e in ref.access_edges if e.kind == "DOOR"}
    rooms_by_type: dict[str, list[str]] = {}
    for room in ref.rooms:
        rooms_by_type.setdefault(room.type, []).append(room.id)

    satisfied = 0
    for rel in relationships:
        a_ids = rooms_by_type.get(rel.source_role.upper(), [])
        b_ids = rooms_by_type.get(rel.target_role.upper(), [])
        any_pair_touching = any(frozenset((a, b)) in touching_pairs for a in a_ids for b in b_ids)
        any_pair_door = any(frozenset((a, b)) in door_pairs for a in a_ids for b in b_ids)
        if rel.relation == RoomRelation.NOT_ADJACENT:
            ok = not any_pair_touching if (a_ids and b_ids) else True
        elif rel.relation == RoomRelation.DIRECT_ACCESS:
            ok = any_pair_door
        else:  # ADJACENT, NEAR -- approximated by physical touching (see docs/brain.md)
            ok = any_pair_touching
        satisfied += 1 if ok else 0

    score = satisfied / len(relationships)
    detail = f"{satisfied}/{len(relationships)} requested relationships realized on this plan"
    return TermScore("adjacency", WEIGHTS["adjacency"], score,
                      WEIGHTS["adjacency"] * score, detail)


def _score_public_private_org(brief: Brief, entry: CorpusEntry) -> TermScore:
    if brief.zoning_preference is None:
        return TermScore("public_private_org", WEIGHTS["public_private_org"], NEUTRAL,
                          WEIGHTS["public_private_org"] * NEUTRAL, "no zoning_preference stated")
    score = 1.0 if entry.pattern.zoning == brief.zoning_preference else 0.0
    detail = f"brief wants {brief.zoning_preference}, plan is {entry.pattern.zoning}"
    return TermScore("public_private_org", WEIGHTS["public_private_org"], score,
                      WEIGHTS["public_private_org"] * score, detail)


def _score_circulation_class(brief: Brief, entry: CorpusEntry) -> TermScore:
    if brief.circulation_preference is None:
        return TermScore("circulation_class", WEIGHTS["circulation_class"], NEUTRAL,
                          WEIGHTS["circulation_class"] * NEUTRAL, "no circulation_preference stated")
    score = 1.0 if entry.pattern.circulation_class == brief.circulation_preference else 0.0
    detail = f"brief wants {brief.circulation_preference}, plan is {entry.pattern.circulation_class}"
    return TermScore("circulation_class", WEIGHTS["circulation_class"], score,
                      WEIGHTS["circulation_class"] * score, detail)


def _score_floors(brief: Brief, entry: CorpusEntry) -> TermScore:
    # The ResPlan corpus (and every derived PlanReference) is single-storey by construction --
    # see docs/reports/poc-architectural-brain/dataset.md's typology gap -- so a multi-storey
    # brief cannot be matched on floor count by any corpus plan. A flat, documented penalty
    # (never a hard filter: retrieval never refuses to return references for this reason).
    score = 1.0 if brief.stories <= 1 else 0.3
    detail = f"brief.stories={brief.stories}, corpus is single-storey only"
    return TermScore("floors", WEIGHTS["floors"], score, WEIGHTS["floors"] * score, detail)


def _score_wet_room_requirements(brief: Brief, entry: CorpusEntry) -> TermScore:
    counts = entry.plan_reference.derived.room_type_counts
    ref_wet = counts.get("BATHROOM", 0) + counts.get("TOILET", 0)
    count_sim = _relative_closeness(float(brief.program.wet_rooms), float(ref_wet))

    kinds = brief.program.wet_room_kinds
    ensuite_requested = any(k.kind.value == "ensuite" for k in kinds)
    non_ensuite_requested = any(k.kind.value in ("shared_bathroom", "guest_wc") for k in kinds)
    ensuite_share = entry.pattern.relationships.get("wet_bedrooms_public")

    if not kinds or ensuite_share is None:
        kind_score = NEUTRAL
        kind_detail = "no wet_room_kinds stated or plan's ensuite share is unmeasurable"
    elif ensuite_requested and not non_ensuite_requested:
        kind_score = ensuite_share
        kind_detail = f"brief wants ensuite(s), plan ensuite share={ensuite_share:.2f}"
    elif non_ensuite_requested and not ensuite_requested:
        kind_score = 1.0 - ensuite_share
        kind_detail = f"brief wants shared wet room(s), plan ensuite share={ensuite_share:.2f}"
    else:
        kind_score = NEUTRAL
        kind_detail = "brief mixes ensuite and shared wet-room kinds"

    score = 0.6 * count_sim + 0.4 * kind_score
    detail = f"count_sim={count_sim:.2f} ({brief.program.wet_rooms} vs {ref_wet}); {kind_detail}"
    return TermScore("wet_room_requirements", WEIGHTS["wet_room_requirements"], score,
                      WEIGHTS["wet_room_requirements"] * score, detail)


def _score_exterior_exposure(brief: Brief, entry: CorpusEntry) -> TermScore:
    if brief.exposure_requirement is None or entry.pattern.exposure_pattern is None:
        detail = ("no exposure_requirement stated" if brief.exposure_requirement is None
                  else "plan's exposure_pattern is UNKNOWN (no window geometry)")
        return TermScore("exterior_exposure", WEIGHTS["exterior_exposure"], NEUTRAL,
                          WEIGHTS["exterior_exposure"] * NEUTRAL, detail)
    ref_exposure = entry.pattern.exposure_pattern
    score = 1.0 if ref_exposure >= brief.exposure_requirement else _clip01(
        ref_exposure / brief.exposure_requirement)
    detail = f"brief wants >= {brief.exposure_requirement:.2f} exposed, plan measures {ref_exposure:.2f}"
    return TermScore("exterior_exposure", WEIGHTS["exterior_exposure"], score,
                      WEIGHTS["exterior_exposure"] * score, detail)


def _score_entry(brief: Brief, site: PlotSpec, entry: CorpusEntry) -> tuple[float, tuple[TermScore, ...]]:
    terms = (
        _score_built_area(brief, entry),
        _score_room_count_types(brief, entry),
        _score_footprint_aspect_shape(brief, site, entry),
        _score_adjacency(brief, entry),
        _score_public_private_org(brief, entry),
        _score_circulation_class(brief, entry),
        _score_floors(brief, entry),
        _score_wet_room_requirements(brief, entry),
        _score_exterior_exposure(brief, entry),
    )
    total = sum(t.contribution for t in terms)
    return total, terms


def _why(entry: CorpusEntry, total: float, terms: tuple[TermScore, ...]) -> str:
    top = sorted(terms, key=lambda t: t.contribution, reverse=True)[:3]
    reasons = "; ".join(f"{t.term} ({t.detail})" for t in top)
    return (f"Plan {entry.plan_reference.plan_id} scored {total:.3f} overall; strongest factors: "
           f"{reasons}.")


def retrieve(brief: Brief, site: PlotSpec, corpus: list[CorpusEntry], k: int = 8) -> list[RetrievedReference]:
    """Top-``k`` ``CorpusEntry``s by the weighted term score above, deterministic (ties broken by
    ``plan_id``). Never text embeddings; every result carries its per-term contributions and WHY."""
    scored = []
    for entry in corpus:
        total, terms = _score_entry(brief, site, entry)
        scored.append((entry, total, terms))
    scored.sort(key=lambda item: (-item[1], item[0].plan_reference.plan_id))
    top = scored[:k]
    return [
        RetrievedReference(
            plan_id=entry.plan_reference.plan_id,
            total_score=total,
            term_scores=terms,
            why=_why(entry, total, terms),
            plan_reference=entry.plan_reference,
            pattern=entry.pattern,
        )
        for entry, total, terms in top
    ]
