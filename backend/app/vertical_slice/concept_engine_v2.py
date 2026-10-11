"""Concept Engine v2 (4/5): the stage wired behind `general_pipeline.CONCEPT_ENGINE_V2_ENABLED`
(Issue #78).

S1-S3 of the bounded per-brief search, over data this run already has:

    S1  `concept_patterns.patterns_for(brief, outline)` — the 2-3 concept patterns worth trying
        (Issue #77), best first, keyed on the CHOSEN plan's own realized footprint.
    S2  each pattern's class is COMPILED by filtering the candidates the EXISTING generator
        already built for this run (`concept_generator.generate_concepts`'s own output — the same
        pool `general_pipeline._alternative_plans` draws from, never a new generator path) down to
        those whose own declared `circulation_class` matches the pattern's; when that leaves
        nothing (a class the generator's own strategies cannot produce at all — HUB_LOBBY,
        BRANCHED), `concept_compilers.compile_hub_lobby`/`compile_branched` (Issue #79) are tried
        instead, on the SAME outline `chosen_plan` was fit to. The first that REALIZES through the
        existing `_realize` pipeline (doors/windows/furniture/validation, unchanged) and validates
        is SCORED (`concept_score.concept_score`, Issue #76) and VERIFIED
        (`concept_spec.verify_class`) — a mismatch is dropped, never re-labelled.
    S3  when the bounded adaptation ladder (`concept_score.adapt`) names a target concept, a
        SIBLING candidate already sitting in that same filtered list — never a new solve of
        geometry the generator didn't already produce — that already matches the adapted spec is
        realized too, and the better-scoring `.ok` plan of the two wins the class.

One verified plan per REALIZED circulation class — the class `concept_label` attaches to it must
equal (`concept_spec.realized_circulation_class`, AC-3) — replaces `general_pipeline.
_alternative_plans`'s ordinary walk in `run_general` when the flag is on; the primary is never
touched (`chosen_plan` is read, never re-realized), and the massing-representation slot rule stays
`general_pipeline`'s own (`_massing_representation_plans`, called separately by `run_general`).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING

from . import concept_compilers
from .concept_patterns import patterns_for
from .concept_score import ConceptScore, adapt, better, concept_score
from .concept_spec import CirculationClass, ConceptSpec, concept_spec_of, verify_class
from .geometry_core.engine import GeometryInfeasible

if TYPE_CHECKING:
    from .general_pipeline import RealizedPlan
    from .spec import ArchitecturalSpec

#: How many candidates this module realizes per brief before giving up on whatever pattern
#: classes remain unfilled — the ONLY cost this stage adds on top of the existing pipeline
#: (`patterns_for`/`concept_score`/`adapt` are all pure, pre-solve or read-only functions over
#: data the run already produced). Calibrated like `general_pipeline.ALTERNATIVE_ATTEMPT_LIMIT`
#: (8): up to 3 pattern classes, each costing at most one realization for the pattern's own best
#: candidate plus one more for the sibling `adapt` names, with headroom for a class whose first
#: couple of candidates fail to validate. See `tests/test_concept_engine_v2_budget.py` for the
#: measured wallclock this buys.
CONCEPT_ENGINE_V2_MAX_REALIZATIONS = 10

#: Per pattern/class, how many of the filtered candidates (generator order) are tried before that
#: class contributes nothing — bounded independently of the brief-wide budget so one stubborn
#: class can never spend the whole budget alone and starve the patterns after it.
_PER_CLASS_ATTEMPT_LIMIT = 3

Realize = Callable[[int, object], "RealizedPlan"]


@dataclass(frozen=True)
class ConceptLabel:
    """One plan's concept, in the person's own language (Issue #78 AC-3/AC-5) — a label and a
    one-sentence Hebrew rationale for the circulation class the plan REALIZED to."""

    circulation_class: CirculationClass
    label: str
    rationale: str


#: `CirculationClass` -> (label, one-sentence rationale), both Hebrew — the same vocabulary
#: `concept_patterns.py`'s own citations already use (e.g. "מבואת חדרים" for a room lobby).
#: Covers every value the enum declares (`concept_spec.CirculationClass`'s own docstring: BRANCHED
#: and RING are not produced by any builder today) so a label is never missing for a class this
#: module could in principle be asked to name.
_LABELS: dict[CirculationClass, tuple[str, str]] = {
    CirculationClass.SPINE: (
        "מסדרון מרכזי",
        "החדרים מסודרים משני צדי מסדרון אחד המחבר ביניהם.",
    ),
    CirculationClass.FRONT_BAND: (
        "רצועה ציבורית קדמית",
        "החללים הציבוריים יוצרים רצועה רציפה לאורך חזית הבית, והחדרים הפרטיים נמצאים מאחוריה.",
    ),
    CirculationClass.HUB_LOBBY: (
        "מבואת חדרים",
        "החדרים נפתחים סביב מבואה קומפקטית.",
    ),
    CirculationClass.TWO_WING: (
        "שני אגפים",
        "הבית מתפצל לשני אגפים הנפגשים בפינה משותפת.",
    ),
    CirculationClass.BRANCHED: (
        "פריסה מסועפת",
        "מסדרון ראשי מתפצל למספר זרועות המובילות לאזורי הבית השונים.",
    ),
    CirculationClass.RING: (
        "טבעת סביב חצר",
        "החדרים עוטפים חצר פנימית במעגל רציף.",
    ),
}


def concept_label(circulation_class: CirculationClass) -> ConceptLabel:
    """The `ConceptLabel` for `circulation_class` — every value `CirculationClass` declares has
    one, so this never raises for a class `concept_spec.realized_circulation_class` can return."""
    label, rationale = _LABELS[circulation_class]
    return ConceptLabel(circulation_class, label, rationale)


def brief_and_outline_of(spec: "ArchitecturalSpec", chosen_plan: "RealizedPlan"):
    """The duck-typed `concept_patterns.Brief`/`Outline` `patterns_for` reads — built entirely
    from data this run already has: the programme's own counts, and the CHOSEN plan's own realized
    footprint (the same figure `reference_benchmark.classify_footprint_family` reads off a
    `DemoDesign`, one layer down) — never a new input, and never the primary's geometry itself."""
    brief = SimpleNamespace(bedrooms=spec.program.bedrooms, wet_rooms=spec.program.wet_rooms,
                            levels="single")
    _, _, w_m, h_m = chosen_plan.design.footprint_m
    is_l = len(chosen_plan.concept.concept.fixture.wings) > 1
    outline = SimpleNamespace(width_m=w_m, depth_m=h_m, shape=("L" if is_l else "RECTANGLE"))
    return brief, outline


def _sibling(candidates_for_class: list[tuple[int, object]], target: ConceptSpec,
            skip_index: int) -> tuple[int, object] | None:
    """The first OTHER candidate in `candidates_for_class` whose own `ConceptSpec` already
    matches `target` (same class, zoning and wet-core strategy) — never a new solve, the same
    "sibling" rule `spikes/failure_log_sweep/concept_adaptation_report.py` measures offline."""
    for index, candidate in candidates_for_class:
        if index == skip_index:
            continue
        here = concept_spec_of(candidate)
        if ((here.circulation_class, here.zoning, here.wet_core_strategy)
                == (target.circulation_class, target.zoning, target.wet_core_strategy)):
            return index, candidate
    return None


def _best_for_class(realize: Realize, candidates_for_class: list[tuple[int, object]],
                    budget: list[int]) -> "RealizedPlan | None":
    """The best verified plan `candidates_for_class` (already filtered to one pattern's declared
    class, generator order) produces within `budget[0]` remaining realizations — S2/S3 above."""
    best: "RealizedPlan | None" = None
    best_score: ConceptScore | None = None
    tried = 0
    for index, candidate in candidates_for_class:
        if tried >= _PER_CLASS_ATTEMPT_LIMIT or budget[0] <= 0:
            break
        tried += 1
        budget[0] -= 1
        try:
            plan = realize(index, candidate)
        except GeometryInfeasible:
            continue
        if not plan.ok:
            continue
        if verify_class(candidate, plan) is not None:
            # Issue #79, AC-1: a candidate whose declared `circulation_class` disagrees with what
            # it actually realized to is dropped here, never re-labelled and never scored — the
            # compilers this Issue adds (`concept_compilers.compile_hub_lobby`/`compile_branched`)
            # are the first callers where a genuine mismatch is expected in the ordinary course of
            # search (a witness-sized hub that still realizes as a plain SPINE hall, say).
            continue
        score = concept_score(plan)
        if best_score is None or better(score, best_score) is score:
            best, best_score = plan, score
        if budget[0] > 0:
            target = adapt(concept_spec_of(candidate), plan, score, attempt=0)
            sibling = _sibling(candidates_for_class, target, index) if target is not None else None
            if sibling is not None:
                budget[0] -= 1
                s_index, s_candidate = sibling
                try:
                    s_plan = realize(s_index, s_candidate)
                except GeometryInfeasible:
                    s_plan = None
                if s_plan is not None and s_plan.ok and verify_class(s_candidate, s_plan) is None:
                    s_score = concept_score(s_plan)
                    if best_score is None or better(s_score, best_score) is s_score:
                        best, best_score = s_plan, s_score
        if best is not None:
            break  # this class already has a verified plan; spend the rest of the budget elsewhere
    return best


def _outline_rect_of(candidates: tuple):
    """The one wing every one of `candidates` was fit to, as a `Rect` — what
    `concept_compilers.compile_hub_lobby`/`compile_branched` need to place their own tree in
    (Issue #79). `None` when `candidates` is empty (nothing to derive it from)."""
    if not candidates:
        return None
    return candidates[0].concept.fixture.wings[0].rect()


def _compiled_candidates_for(circulation_class: CirculationClass, spec: "ArchitecturalSpec",
                             outline_rect) -> list:
    """Generator-level pattern compilers (Issue #79) — tried ONLY when the generator's OWN
    candidates for this outline carry nothing of `circulation_class` at all, so a brief that
    already has a real one is never displaced by a compiled stand-in. `[]` for every class the
    generator already builds itself (SPINE/FRONT_BAND/TWO_WING): `concept_compilers.compile`
    would only re-derive what `candidates` already has, at the cost of a second generator call."""
    if outline_rect is None:
        return []
    if circulation_class is CirculationClass.HUB_LOBBY:
        return concept_compilers.compile_hub_lobby(spec, outline_rect)
    if circulation_class is CirculationClass.BRANCHED:
        return concept_compilers.compile_branched(spec, outline_rect)
    return []


def plans_per_class(spec: "ArchitecturalSpec", realize: Realize, candidates: tuple,
                    chosen_index: int, chosen_plan: "RealizedPlan", *,
                    skip: frozenset[int] = frozenset()) -> tuple["RealizedPlan", ...]:
    """One best verified plan per circulation class `patterns_for` names for this brief/outline.

    `realize(index, candidate) -> RealizedPlan` is a thin wrapper the caller
    (`general_pipeline.run_general`) supplies over its own `_realize`, so this module never
    imports the solver stages or repeats their argument list, and never re-realizes `chosen_plan`
    itself. `chosen_plan`'s own realized class is never re-offered here — an alternative exists to
    be a genuinely different organisation from the primary the person already sees, and excluding
    it also guarantees every returned plan is `concept_spec.topologically_distinct` from the
    primary (a different `circulation_class` alone decides that comparison).
    """
    brief, outline = brief_and_outline_of(spec, chosen_plan)
    patterns = patterns_for(brief, outline)
    # `patterns_for` orders what is worth trying FIRST (S1) — it is explicitly documented as a
    # PRIOR, "not a feasibility gate" (`concept_patterns.py`'s own module docstring), so a class the
    # generator's EXISTING builders already produced for this exact outline is never left untried
    # merely because the architectural-reference table does not name it for this footprint family:
    # every other class `candidates` actually carries follows the named patterns, same compile step.
    ordered_classes = list(dict.fromkeys(p.circulation_class for p in patterns))
    for candidate in candidates:
        if candidate.circulation_class not in ordered_classes:
            ordered_classes.append(candidate.circulation_class)
    seen_signatures = {chosen_plan.layout_signature}
    seen_classes = {chosen_plan.circulation_class}
    outline_rect = chosen_plan.concept.concept.fixture.wings[0].rect()
    budget = [CONCEPT_ENGINE_V2_MAX_REALIZATIONS]
    found: list["RealizedPlan"] = []
    for circulation_class in ordered_classes:
        if budget[0] <= 0:
            break
        if circulation_class in seen_classes:
            continue
        candidates_for_class = [(i, c) for i, c in enumerate(candidates)
                                if i != chosen_index and i not in skip
                                and c.circulation_class == circulation_class]
        if not candidates_for_class:
            compiled = _compiled_candidates_for(circulation_class, spec, outline_rect)
            candidates_for_class = [(-(j + 1), c) for j, c in enumerate(compiled)]
        if not candidates_for_class:
            continue
        plan = _best_for_class(realize, candidates_for_class, budget)
        if plan is None or plan.circulation_class is None:
            continue
        if plan.layout_signature in seen_signatures or plan.circulation_class in seen_classes:
            continue
        seen_signatures.add(plan.layout_signature)
        seen_classes.add(plan.circulation_class)
        found.append(plan)
    return tuple(found)


@dataclass(frozen=True)
class OutlineCandidates:
    """One OTHER outline the service surveyed (Issue #79, AC-5): its own concept candidates
    (`general_pipeline.GeneralSliceResult.candidates` — the SAME pool that outline's own
    `run_general` call already built, never a second generator call) and a `realize` wrapper
    closed over THAT outline's own `buildable`/`spec`. `demo.service` builds these from
    `OutlineResult`s that are not the one already searched by `plans_per_class` above."""

    candidates: tuple
    realize: Realize


def plans_per_class_cross_outline(
        spec: "ArchitecturalSpec", chosen_plan: "RealizedPlan",
        already_found: tuple["RealizedPlan", ...],
        outlines: list[tuple[object, OutlineCandidates]],
) -> tuple[tuple[object, "RealizedPlan"], ...]:
    """Extends `plans_per_class`'s result across OTHER surveyed outlines (`demo.service
    ._plan_outlines`), when the PRIMARY outline's own candidates (already searched by
    `plans_per_class`, `already_found`) left a pattern class unfilled.

    Never touches the primary outline's own candidates, `chosen_plan` or `already_found` — those
    are `plans_per_class`'s own result. Only classes STILL missing from them are searched, in
    `outlines` order, over each `OutlineCandidates.candidates` in turn until one verifies; the
    first outline whose own candidates offer a class wins it (never every outline compared for the
    same class — cost stays bounded exactly like `plans_per_class`'s own per-class budget).
    `outlines` items carry an opaque caller key (`demo.service`'s own `OutlineResult`) so the
    caller can attribute each returned plan to the outline it came from without this module
    knowing anything about `demo.service`'s own types. Additive: the primary selection rule and
    the flag-off path are untouched, and this function is never called from `run_general`'s own
    single-outline path — only from the flag-on service-level orchestration, and only when more
    than one outline was actually surveyed.
    """
    brief, outline = brief_and_outline_of(spec, chosen_plan)
    patterns = patterns_for(brief, outline)
    ordered_classes = list(dict.fromkeys(p.circulation_class for p in patterns))
    for _key, oc in outlines:
        for candidate in oc.candidates:
            if candidate.circulation_class not in ordered_classes:
                ordered_classes.append(candidate.circulation_class)

    seen_classes = {chosen_plan.circulation_class, *(p.circulation_class for p in already_found)}
    seen_signatures = {chosen_plan.layout_signature, *(p.layout_signature for p in already_found)}
    budget = [CONCEPT_ENGINE_V2_MAX_REALIZATIONS]
    found: list[tuple[object, "RealizedPlan"]] = []
    for circulation_class in ordered_classes:
        if budget[0] <= 0:
            break
        if circulation_class in seen_classes:
            continue
        for key, oc in outlines:
            candidates_for_class = [(i, c) for i, c in enumerate(oc.candidates)
                                    if c.circulation_class == circulation_class]
            if not candidates_for_class:
                compiled = _compiled_candidates_for(
                    circulation_class, spec, _outline_rect_of(oc.candidates))
                candidates_for_class = [(-(j + 1), c) for j, c in enumerate(compiled)]
            if not candidates_for_class:
                continue
            plan = _best_for_class(oc.realize, candidates_for_class, budget)
            if plan is None or plan.circulation_class is None:
                continue
            if plan.layout_signature in seen_signatures or plan.circulation_class in seen_classes:
                continue
            seen_signatures.add(plan.layout_signature)
            seen_classes.add(plan.circulation_class)
            found.append((key, plan))
            break
    return tuple(found)
