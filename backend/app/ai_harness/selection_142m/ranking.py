"""#142M — rank REALIZED, validator-PASS plans using only preference logic that already exists in
production. Experiment code; nothing here is wired into production.

The rule this module implements is production's own, in production's own precedence. Nothing is
weighted, nothing is invented: `general_pipeline.run_general`'s candidate loop ranks validating plans by

    1. `_entrance_rank`            0 = front door into HALL/CIRCULATION, 1 = LIVING, 2 = other (strict)
    2. area proximity              production's own primary rule (`demo.service._nearest_primary`:
                                   |delivered area - requested area|), used in the loop as the
                                   equality condition for the tiebreaks below
    3. `entrance_sequence_prefers` STRICT tiebreak, only between candidates equal on 1 and 2
    4. `composition_prefers`       the lowest-precedence tiebreak, only on a tie of 1-3

and afterwards applies `circulation_prefers` (via `hub_guard`/`_guard_demoted_hub`). To those this
module appends the preference keys that production ALSO owns but has never wired to a caller, each in
its own published direction, and finally the old proposal heuristic as the last tiebreak the task asks
for:

    5. `circulation_prefers`       (see CYCLE WARNING below)
    6. `wet_privacy.candidate_privacy_key`   (worst, sum) lower better — wired today only in `_break_l_tie`
    7. `dead_space_prefers`                   lower dead space — exported, never wired
    8. `wet_core.candidate_wet_core_key`      (plumbing complexity, -shared wet wall) — never wired
    9. `master_suite.candidate_suite_key`     (worst, sum) lower better — never wired
   10. proposal heuristic score              FINAL tiebreak only (higher better)
   11. candidate index                        absolute determinism

WHY A LEXICOGRAPHIC KEY AND NOT A SCORE. Every one of production's `*_prefers` functions compares a
single scalar and returns "why not" otherwise (`entrance_sequence_prefers`: distance to the first
public room; `composition_prefers`: composition score; `dead_space_prefers`: dead-space m2). Ordering
by those scalars in that precedence reproduces the same decisions while guaranteeing a total order —
no weights, no new formula, and the same answer whichever order the candidates arrive in.

CYCLE WARNING (measured, not assumed). `circulation_prefers` is the one term that is NOT a scalar: it
prefers a candidate that is better on AT LEAST ONE of ratio, longest segment or dead ends while keeping
85% of the area. "Better on at least one of three" is not transitive and can cycle, so it cannot form
part of a total order. It is therefore applied here exactly where production applies it — after the
terms above, as a pairwise check among plans otherwise tied — and `circulation_cycles` reports whether
it actually cycles on the real pools.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.vertical_slice import circulation_metrics, dead_space, entrance_sequence
from app.vertical_slice import master_suite as suite_mod
from app.vertical_slice import public_composition, wet_core, wet_privacy
from app.vertical_slice.general_pipeline import _entrance_rank

#: The ordered terms of the chain. `basis` names the production scalar each production preference
#: function actually compares on, so the lexicographic key and the `*_prefers` call always agree.
TERMS = (
    ("entrance_rank", "general_pipeline._entrance_rank", "lower"),
    ("area_delta_m2", "demo.service._nearest_primary (|delivered - requested| area)", "lower"),
    ("distance_to_public_m", "entrance_sequence.entrance_sequence_prefers", "lower"),
    ("composition_score", "public_composition.composition_prefers", "lower"),
    ("circulation", "circulation_metrics.circulation_prefers (NOT a scalar — pairwise only)", "pairwise"),
    ("wet_privacy_key", "wet_privacy.candidate_privacy_key", "lower"),
    ("dead_space_m2", "dead_space.dead_space_prefers", "lower"),
    ("wet_core_key", "wet_core.candidate_wet_core_key", "lower"),
    ("suite_key", "master_suite.candidate_suite_key", "lower"),
    ("heuristic_score", "ai_harness.topology_poc.critic.score_topology (FINAL tiebreak only)", "higher"),
    ("candidate_index", "determinism", "lower"),
)
#: The scalar terms, in precedence order, that form the total order (circulation excluded by design).
KEY_TERMS = ("entrance_rank", "area_delta_m2", "distance_to_public_m", "composition_score",
             "wet_privacy_key", "dead_space_m2", "wet_core_key", "suite_key",
             "neg_heuristic_score", "candidate_index")


@dataclass
class PlanFacts:
    """Everything the chain needs about one realized, validated plan — every value produced by a
    production module, none computed here."""
    brief: str
    candidate: int
    heuristic_score: float
    entrance_rank: int
    area_delta_m2: float
    requested_area_m2: float
    delivered_area_m2: float
    distance_to_public_m: float
    composition_score: float
    wet_privacy_key: tuple
    dead_space_m2: float
    wet_core_key: tuple
    suite_key: tuple
    circulation: object
    circulation_area_m2: float
    entrance_seq: object
    composition: object
    dead_space: object

    @property
    def sort_key(self) -> tuple:
        return (self.entrance_rank, self.area_delta_m2, self.distance_to_public_m,
                self.composition_score, self.wet_privacy_key, self.dead_space_m2,
                self.wet_core_key, self.suite_key, -self.heuristic_score, self.candidate)

    def term(self, name: str):
        if name == "neg_heuristic_score":
            return -self.heuristic_score
        if name == "candidate_index":
            return self.candidate
        return getattr(self, name)


_BIG = float("inf")


def facts_of(realized, brief_id: str, candidate: int, heuristic_score: float,
             requested_area_m2: float, wet_rooms=()) -> PlanFacts:
    """Measure one realized plan with production's own modules only."""
    d = realized.design
    seq = entrance_sequence.measure(d)
    comp = public_composition.measure(d)
    ds = dead_space.measure(d)
    circ = circulation_metrics.measure(d)
    wp = d.wet_privacy or ()
    wc = d.wet_core
    try:
        suites = suite_mod.compute_master_suites(realized.fixture, realized.rects, realized.walls,
                                                 realized.interior_doors, tuple(wet_rooms))
    except Exception:                       # the rectilinear realizer carries no ResolvedWetRoom list
        suites = ()
    return PlanFacts(
        brief=brief_id, candidate=candidate, heuristic_score=float(heuristic_score),
        entrance_rank=_entrance_rank(realized),
        area_delta_m2=round(abs(d.gross_area_m2 - requested_area_m2), 4),
        requested_area_m2=requested_area_m2, delivered_area_m2=round(d.gross_area_m2, 3),
        distance_to_public_m=(_BIG if seq.distance_to_public_m is None else float(seq.distance_to_public_m)),
        composition_score=float(comp.composition_score),
        wet_privacy_key=tuple(wet_privacy.candidate_privacy_key(wp)) if wp else (0.0, 0.0),
        dead_space_m2=round(ds.dead_space_m2, 4),
        wet_core_key=tuple(wet_core.candidate_wet_core_key(wc)) if wc else (0, 0.0),
        suite_key=tuple(suite_mod.candidate_suite_key(suites)) if suites else (0.0, 0.0),
        circulation=circ, circulation_area_m2=round(d.gross_area_m2, 3),
        entrance_seq=seq, composition=comp, dead_space=ds)


def rank(plans: list[PlanFacts]) -> list[PlanFacts]:
    """Total order by production's precedence. Deterministic for any input order."""
    return sorted(plans, key=lambda p: p.sort_key)


def deciding_term(a: PlanFacts, b: PlanFacts) -> tuple[str, object, object]:
    """The FIRST term of the chain on which `a` and `b` differ — the answer to 'which existing
    preference caused this ordering'."""
    for name in KEY_TERMS:
        x, y = a.term(name), b.term(name)
        if x != y:
            return name, x, y
    return "none", None, None


def production_reason(a: PlanFacts, b: PlanFacts, term: str) -> str | None:
    """Production's OWN sentence for why `b` does not take the place of `a`, from the preference
    function that owns this term. `None` when the term has no `*_prefers` function."""
    if term == "distance_to_public_m":
        return entrance_sequence.entrance_sequence_prefers(a.entrance_seq, b.entrance_seq)
    if term == "composition_score":
        return public_composition.composition_prefers(a.composition, b.composition)
    if term == "dead_space_m2":
        return dead_space.dead_space_prefers(a.dead_space, b.dead_space)
    return None


def circulation_prefers_pair(a: PlanFacts, b: PlanFacts) -> str | None:
    """Production's circulation comparator, oriented as 'does b take it from a'."""
    return circulation_metrics.circulation_prefers(a.circulation, a.circulation_area_m2,
                                                  b.circulation, b.circulation_area_m2)


def circulation_cycles(plans: list[PlanFacts]) -> list[tuple]:
    """Every 3-cycle under `circulation_prefers` within this set — the measured answer to whether
    that non-scalar term could have been part of a total order. Empty means no cycle was observed."""
    beats = {(x.candidate, y.candidate): circulation_prefers_pair(x, y) is None
             for x in plans for y in plans if x.candidate != y.candidate}
    out = []
    ids = [p.candidate for p in plans]
    for i in ids:
        for j in ids:
            for k in ids:
                if len({i, j, k}) == 3 and beats.get((i, j)) and beats.get((j, k)) and beats.get((k, i)):
                    out.append((i, j, k))
    return out


__all__ = ["TERMS", "KEY_TERMS", "PlanFacts", "facts_of", "rank", "deciding_term", "production_reason",
           "circulation_prefers_pair", "circulation_cycles"]
