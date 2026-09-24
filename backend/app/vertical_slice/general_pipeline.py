"""End-to-end: general authoritative geometry -> the EXISTING vertical slice, unchanged.

    BuildableRegion -> SafeGeometryAdapter -> Geometry Core -> Doors -> Windows
                    -> Furniture -> Validation -> GeometricDesign -> Renderer

Nothing in `concept.py`, `geometry_core/`, `doors.py`, `windows.py`, `furniture.py`,
`validation.py`, `design_output.py` or `renderer.py` was changed to make this work. This module
only chooses WHERE the existing concept's footprint is placed, using a candidate the adapter
has already proven safe, and then adds the safety checks the general-geometry case needs on top
of the slice's own 12:

  * every room lies inside the authoritative buildable region (checked against the exact
    arc-aware containment, not the linearization the candidate came from);
  * no room overlaps any exclusion/obstacle constraint.

The canonical `pipeline.run_demo` is untouched and still produces the frozen baseline.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from app.geometry_domain.constraints import (
    BuildableRegion,
    ConstraintRole,
    GeometricConstraint,
    SiteConstraints,
)
from app.geometry_domain.primitives import MultiRegion

from . import circulation_metrics
from . import concept_generator as generator
from . import entrance_sequence
from . import footprint as footprint_module
from . import hub_guard
from . import l_massing_guard
from . import doors as doors_stage
from . import door_clearance
from . import relationships as relationships_stage
from . import furniture as furniture_stage
from . import site as site_stage
from . import validation as validation_stage
from . import windows as windows_stage
from .design_output import GeometricDesign, assemble
from .geometry_core.engine import GeometryInfeasible, solve_fixture
from .geometry_core.model import UNIT_M, ConnectionKind, Cut, Fixture, Leaf, Node, Rect, Split
from .renderer import render
from .safe_adapter import (
    AdapterOutcome,
    SafeGeometryResult,
    SolverGeometryCandidate,
    adapt,
    build_buildable_region,
)
from .site import EntranceWalk, SitePlan
from .spec import ArchitecturalSpec, PlotSpec, ProgramSpec, WetRoomKind


@dataclass(frozen=True)
class SafetyReport:
    """The general-geometry checks, separate from the slice's own validation."""

    rooms_inside_buildable: bool
    rooms_clear_of_exclusions: bool
    offending_rooms: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.rooms_inside_buildable and self.rooms_clear_of_exclusions


@dataclass(frozen=True)
class RunMetrics:
    """Per-scenario metrics (task section 11)."""

    concept_candidates_generated: int = 0
    candidates_rejected_pre_solver: int = 0
    solver_attempts: int = 0
    first_valid_candidate_index: int | None = None
    latency_ms: float = 0.0
    room_count: int = 0
    wing_count_offered: int = 0
    wings_used: int = 0
    unused_safe_wing_area_m2: float = 0.0
    residual_area_m2: float = 0.0
    rejection_reasons: tuple[str, ...] = ()


#: How many ALTERNATIVE plans a caller that wants them should ask for. The generator regularly
#: produces three or four genuinely different layouts for the same brief and the same land; showing
#: a few of them lets a person disagree with the engine's ranking, which is a matter of taste the
#: engine cannot settle for them.
#:
#: Asked for, never assumed: `run_general` looks for none unless a caller passes
#: `max_alternatives`, so every existing caller — the frozen baseline included — costs exactly what
#: it did before, and the one screen that shows options is the one that pays for them.
#:
#: This is the budget of the NORMAL walk. The massing representation pass below may add one plan
#: of a second massing (an L) ON TOP of it — so a pool can hold `ALTERNATIVE_PLAN_LIMIT + 1` plans
#: where two massings exist, and exactly this many where one does. It used to replace the
#: area-farthest alternative instead: measured on the deep-primary L site with a 3-bedroom
#: open-plan brief, the L displaced a 162 m2 spine plan that was the only one of its family in the
#: pool; and raising the budget to four did not help, because the walk simply fills every slot it
#: is given and the L then displaces the fourth. The SCREEN still shows three
#: (`demo/service._SHOWN_LIMIT`); this is the pool it chooses from.
ALTERNATIVE_PLAN_LIMIT = 3

#: How many candidates of an UNREPRESENTED massing family to try so that one plan of it can be
#: shown beside the rest (`_alternative_plans`). Bounded separately from the attempt limit above
#: because it only ever runs when a second massing family exists among the candidates — an L site —
#: and a one-wing brief must cost exactly what it did.
MASSING_ATTEMPT_LIMIT = 4

#: How many candidates to try while looking for those alternatives.
#:
#: THE COST IS THE SOLVER, and only the solver. Measured over a 13-candidate brief: 2142 ms in
#: `solve_fixture` against 17 ms for every stage after it (doors, windows, furniture, validation,
#: assembly) — about 165 ms per candidate, paid whether or not the candidate turns out to be
#: feasible, distinct, or valid. So there is nothing to skip cheaply: knowing what a candidate
#: draws means solving it. This limit is therefore the only lever on what a design request costs,
#: and 8 keeps the worst case near two seconds while still finding three alternatives on the
#: briefs that have them.
ALTERNATIVE_ATTEMPT_LIMIT = 8


@dataclass(frozen=True)
class RealizedPlan:
    """One concept taken all the way to a drawable, checked design.

    The chosen plan and every alternative are the same kind of object, produced by the same
    function, so an alternative can never be a plan held to a lower standard than the one the
    engine picked.
    """

    index: int
    concept: generator.ConceptCandidate
    design: GeometricDesign
    validation: validation_stage.ValidationReport
    safety: SafetyReport
    relationships: tuple = ()

    @property
    def ok(self) -> bool:
        return self.validation.ok and self.safety.ok

    @property
    def layout_signature(self) -> tuple:
        """What makes two plans the SAME DRAWING: which rooms, where, and how big.

        Different generator strategies regularly realize to IDENTICAL geometry — measured across
        nine briefs, SPINE_SERVICE_CLUSTER matched SPINE_DOUBLE_LOADED exactly in most of them.
        Offering both would be offering the same picture twice under two names.
        """
        return tuple(sorted((r.zone_id,) + tuple(round(v, 3) for v in r.rect_m)
                            for r in self.design.rooms))

    @property
    def massing_signature(self) -> str:
        """What makes two plans the SAME MASSING: how many wings the footprint is made of — one
        rectangle, or an L of two. Coarser than `family_signature` (which tells one organisation
        of a rectangle from another) and read only where a plan set is chosen for DISPLAY, so a
        valid two-wing plan is guaranteed a look beside the one-wing ones instead of sitting
        behind every re-proportioning that lands nearer the requested area. Never an input to
        which plan becomes primary — that stays the requested-area rule."""
        return massing_of(self.concept)

    @property
    def family_signature(self) -> str:
        """What makes two plans the SAME HOUSE: how the rooms are organised, dimensions aside.

        `layout_signature` answers "same drawing?"; this answers "same arrangement?" — where the
        public zone sits relative to the private wing, which rooms share a column or band, which
        wet room is entered from a bedroom. Two plans of one family differ only in proportions;
        measured over the failure log, 142 of the 178 alternatives the demo showed were the
        primary's own family re-proportioned, which is why the service (feature 006) uses this to
        decide which alternatives are worth SHOWING.

        METADATA ONLY. Nothing in this module, in `_alternative_plans` or below reads it, and it is
        never an input to which plan becomes primary — that stays the requested-area rule.
        """
        return _family_signature(self.concept.concept.fixture, self.concept.strategy)


def massing_of(candidate) -> str:
    """A concept candidate's massing family: `1W` for one rectangle, `2W` for two wings (an L)."""
    return f"{len(candidate.concept.fixture.wings)}W"


def _entrance_rank(plan: "RealizedPlan") -> int:
    """0 when the realized front door opens into HALL/CIRCULATION, 1 for LIVING, 2 otherwise.

    Used only to RANK candidates that already validate (`run_general`'s main loop): a plan this
    bad on rank 2 already fails C23 and is never `.ok`, so 2 only matters as a total-order floor.
    """
    target = plan.design.entrance_door.b
    roles = next((r.roles for r in plan.design.rooms if r.zone_id == target), ())
    if {"HALL", "CIRCULATION"} & set(roles):
        return 0
    if "LIVING" in roles:
        return 1
    return 2


#: Zone role -> the letter it takes in a family signature. Wet rooms are resolved separately: a
#: wet room with a door onto the hall is `W`, one entered from a bedroom (an ensuite) is `E`.
_FAMILY_LETTERS = {
    "HALL": "H", "LIVING": "P", "DINING": "P", "KITCHEN": "P", "FAMILY_ROOM": "P", "FLEX": "F",
    "MASTER_BEDROOM": "M", "BEDROOM": "B", "STUDY": "B", "SAFE_ROOM": "S",
}
_WET_ROLES = frozenset({"BATHROOM", "TOILET", "LAUNDRY"})


def _family_signature(fixture: Fixture, strategy) -> str:
    """The wing's slicing tree with leaves reduced to group letters, same-direction chains
    flattened, every V node mirror-normalised and every forced position dropped.

    `HUB:` prefixes a hub parti (branch 005): its tree also has a public band at the root and would
    otherwise be indistinguishable from the front-band family, which it is not.
    """
    doors: dict[str, set[str]] = {}
    for edge in fixture.access.edges:
        if edge.kind == ConnectionKind.DOOR:
            doors.setdefault(edge.a, set()).add(edge.b)
            doors.setdefault(edge.b, set()).add(edge.a)
    letters: dict[str, str] = {}
    for zone in fixture.zones:
        role = zone.primary_role.value
        if role in _WET_ROLES:
            partners = doors.get(zone.zone_id, set())
            letters[zone.zone_id] = "W" if ("HALL" in partners or not partners) else "E"
        else:
            letters[zone.zone_id] = _FAMILY_LETTERS.get(role, "?")

    def flatten(node: Node, cut: Cut) -> list[Node]:
        if isinstance(node, Split) and node.cut is cut:
            return flatten(node.first, cut) + flatten(node.second, cut)
        return [node]

    def render(node: Node) -> str:
        if isinstance(node, Leaf):
            return letters.get(node.zone_id, "?")
        kids = [render(k) for k in flatten(node, node.cut)]
        if node.cut is Cut.V:
            kids = min(kids, list(reversed(kids)))
        return f"{node.cut.value}[{','.join(kids)}]"

    prefix = "HUB:" if getattr(strategy, "value", strategy) == "HUB_PRIVATE_WING" else ""
    # One tree per wing, joined; a one-wing fixture's signature is exactly what it was.
    return prefix + "+".join(render(wing.tree) for wing in fixture.wings)


@dataclass(frozen=True)
class GeneralSliceResult:
    outcome: AdapterOutcome
    adapter: SafeGeometryResult
    design: GeometricDesign | None = None
    validation: validation_stage.ValidationReport | None = None
    safety: SafetyReport | None = None
    render_path: str | None = None
    chosen_candidate: SolverGeometryCandidate | None = None
    concept: generator.ConceptCandidate | None = None
    metrics: RunMetrics = field(default_factory=RunMetrics)
    notes: tuple[str, ...] = ()
    #: Every requested room relationship, measured on the plan that was actually built.
    relationships: tuple = ()
    #: Other plans this same brief and this same land produce, each one fully checked. Empty when
    #: the generator has nothing else to offer, which is a real and common answer.
    alternatives: tuple[RealizedPlan, ...] = ()

    @property
    def ok(self) -> bool:
        return (
            self.outcome is AdapterOutcome.SOLVED
            and self.validation is not None and self.validation.ok
            and self.safety is not None and self.safety.ok
        )


def _place_footprint(candidate: Rect, w_m: float, h_m: float) -> tuple[int, int]:
    """Centre the footprint in the candidate horizontally, flush to its street side — the same
    convention `site.place_footprint` uses, so case A reproduces the canonical layout."""
    w_u, h_u = round(w_m / UNIT_M), round(h_m / UNIT_M)
    return candidate.x + (candidate.w - w_u) // 2, candidate.y


def _entrance_x_clear_of_parking(span: tuple[int, int], parking: tuple[Rect, ...],
                                 fallback: int) -> int:
    """A point in the acceptable span whose WALK does not cross a parking bay.

    The walk runs straight from the street to the door, so a door chosen purely from the rooms can
    still put the path through a bay — which is exactly what C11 caught the moment the entrance
    stopped defaulting to the footprint's centre. Both constraints are real, so the point is chosen
    against both: scan the span at 5 cm and take the first clear position, preferring the middle so
    the walk stays central when nothing is in the way.
    """
    low, high = span
    walk_half = round(1.2 / UNIT_M) // 2

    def clear(x: int) -> bool:
        walk = Rect(x - walk_half, 0, walk_half * 2, 1)
        return not any(walk.overlap_area_u(Rect(bay.x, 0, bay.w, 1)) > 0 for bay in parking)

    middle = (low + high) // 2
    for offset in range(0, high - low + 1):
        for x in (middle + offset, middle - offset):
            if low <= x <= high and clear(x):
                return x
    return fallback


def _site_plan_for(spec: ArchitecturalSpec, footprint: Rect,
                   entrance_span: tuple[int, int] | None = None,
                   wings: tuple[Rect, ...] = ()) -> SitePlan:
    """Reuse the existing site stage's parking/entrance/garden logic with an externally chosen
    footprint placement (the one piece `place_footprint` would otherwise decide).

    `entrance_x_u` comes from `doors.resolve_entrance`, which reads the realized rooms. It used to
    default to the footprint's centre unconditionally, which put the front door wherever the middle
    of the building happened to be — see that function's docstring for what that produced.
    """
    plot = Rect(0, 0, round(spec.plot.width_m / UNIT_M), round(spec.plot.depth_m / UNIT_M))
    parking = site_stage.build_parking(spec)
    default_x = footprint.x + footprint.w // 2
    entrance_x_u = (default_x if entrance_span is None
                    else _entrance_x_clear_of_parking(entrance_span, parking, default_x))
    entrance = site_stage.build_entrance(footprint, entrance_x_u)
    garden = site_stage.classify_garden(spec, plot, footprint, parking, wings)
    return SitePlan(plot, footprint, (footprint.x, footprint.y), parking, entrance, garden,
                    wings=wings or (footprint,))


def _exclusion_geometry(site: SiteConstraints | None) -> MultiRegion:
    if site is None:
        return MultiRegion()
    from app.geometry_domain.booleans import union

    out = MultiRegion()
    for constraint in site.constraints:
        if constraint.role in (ConstraintRole.OBSTACLE, ConstraintRole.NO_BUILD_REGION):
            out = union(out, constraint.geometry) if not out.is_empty else constraint.geometry
    return out


def _check_safety(design: GeometricDesign, authoritative: MultiRegion,
                  exclusions: MultiRegion) -> SafetyReport:
    from app.geometry_domain.booleans import multiregion_to_shapely
    from shapely.geometry import box

    offenders: list[str] = []
    inside_all = True
    clear_all = True
    exclusion_geom = None if exclusions.is_empty else multiregion_to_shapely(exclusions)

    for room in design.rooms:
        x, y, w, h = room.rect_m
        # Exact arc-aware containment, sampled across the room including its corners.
        for i in range(9):
            for j in range(9):
                px = x + 1e-6 + (w - 2e-6) * i / 8
                py = y + 1e-6 + (h - 2e-6) * j / 8
                if not authoritative.contains_point((px, py)):
                    inside_all = False
                    offenders.append(room.zone_id)
                    break
            else:
                continue
            break
        if exclusion_geom is not None:
            if box(x, y, x + w, y + h).intersection(exclusion_geom).area > 1e-9:
                clear_all = False
                if room.zone_id not in offenders:
                    offenders.append(room.zone_id)

    return SafetyReport(inside_all, clear_all, tuple(dict.fromkeys(offenders)))


def _relationship_outcomes(concept_candidate, solve, relationships):
    """Measure one realized candidate. Doors are generated here because DIRECT_ACCESS and NEAR are
    defined over the REALIZED access graph, which does not exist until they are."""
    fixture = concept_candidate.concept.fixture
    doors = doors_stage.generate_interior_doors(fixture, solve.rects)
    connections = validation_stage.realized_connections(solve.rects, solve.walls, doors)
    return relationships_stage.evaluate(fixture, solve.rects, connections, relationships)


#: The stages a run genuinely passes through, in order. A progress indicator built on these is
#: reporting work that actually happened; one built on a timer is reporting nothing.
PIPELINE_STAGES = (
    ("site", "בודקים את שטח הבנייה"),
    ("concepts", "מסדרים את החדרים"),
    ("realize", "מייצרים את הגאומטריה"),
    ("openings", "מוסיפים דלתות וחלונות"),
    ("validate", "בודקים את התוכנית"),
    ("assemble", "מכינים את השרטוט"),
)


def run_general(buildable: BuildableRegion, *,
                render_path: str | None = None,
                site_constraints: SiteConstraints | None = None,
                plot_size_m: tuple[float, float] = (24.0, 28.0),
                program: ProgramSpec | None = None,
                fast_path: bool = True,
                max_alternatives: int = 0,
                on_stage: Callable[[str], None] | None = None) -> GeneralSliceResult:
    """Run one authoritative buildable region all the way through the existing slice.

    The concept now comes from the GENERATOR, not from a hard-coded fixture: the adapter's safe
    candidates and the ArchitecturalSpec go in, a small bounded set of concepts comes out, and
    they are tried in order until Geometry Core realizes one. `fast_path` stops at the first
    valid candidate (the default); set it False to measure every candidate.

    `max_alternatives` asks for OTHER plans beside the chosen one — see `_alternative_plans`. It
    defaults to none because each one costs a solver run, and a caller that will not show them
    should not pay for them.
    """
    started = time.perf_counter()

    def stage(name: str) -> None:
        """Announce a stage that is ABOUT to run. Never called for work that did not happen."""
        if on_stage is not None:
            on_stage(name)

    spec = ArchitecturalSpec(
        plot=PlotSpec(width_m=plot_size_m[0], depth_m=plot_size_m[1]),
        program=program or ProgramSpec(),
    )

    stage("site")
    adapter_result = adapt(buildable)
    if adapter_result.outcome is not AdapterOutcome.SOLVED:
        return GeneralSliceResult(adapter_result.outcome, adapter_result,
                                  notes=adapter_result.notes)

    stage("concepts")
    generated = generator.generate_concepts(spec, list(adapter_result.candidates))
    base_metrics = dict(
        concept_candidates_generated=len(generated.candidates),
        candidates_rejected_pre_solver=len(generated.rejections),
        wing_count_offered=len(adapter_result.candidates),
        room_count=len(generated.program),
        residual_area_m2=round(sum(r.area_m2 for r in adapter_result.residuals), 2),
        rejection_reasons=tuple(f"{r.strategy.value}/{r.reason.value}: {r.detail}"
                                for r in generated.rejections),
    )
    if not generated.candidates:
        return GeneralSliceResult(
            AdapterOutcome.INSUFFICIENT_RECTANGULAR_CAPACITY, adapter_result,
            metrics=RunMetrics(latency_ms=round((time.perf_counter() - started) * 1000, 1),
                               **base_metrics),
            notes=base_metrics["rejection_reasons"])

    attempts = 0
    chosen: generator.ConceptCandidate | None = None
    solve = None
    failures: list[str] = []
    relationships = spec.program.relationships
    # Room relationships are honoured by CHOOSING between candidates the generator already
    # produces, not by rebuilding how it produces them — the smallest extension compatible with the
    # current architecture. Each realized candidate is measured on its actual geometry (the same
    # function C15 uses), a candidate that breaks a HARD relationship is passed over, and among
    # those that survive the one satisfying the most PREFERENCES wins. Without relationships this
    # loop behaves exactly as before, including the fast path.
    best_score: tuple[int, int] | None = None
    best_solve = None
    # A candidate the solver realizes but validation refuses is NOT a plan, so it does not end the
    # search: the next candidate is tried, and only if none validates is the first refused one
    # returned (with its report) so the refusal path can say why. Committing to the first solved
    # candidate regardless of validation let the unforced twins turn 13 useful refusals into raw
    # C8 failures — the twin solved, was chosen, failed C8, and the forced candidates behind it
    # that would have validated were never reached.
    plan: RealizedPlan | None = None
    first_refused: RealizedPlan | None = None
    # ENTRANCE POLICY (Issue #20): among candidates that validate, one whose front door opens
    # into HALL/CIRCULATION outranks one that only reaches LIVING (`_entrance_rank`) — a candidate
    # is never PREFERRED for a worse entrance than one already found. `fast_path` still stops the
    # instant the best possible rank is reached, so a brief whose first valid candidate already has
    # a HALL/CIRCULATION entrance costs exactly what it did before this Issue.
    best_entrance_rank: int | None = None
    # ENTRANCE SEQUENCE TIEBREAK (Issue #22, hub_guard-style): a STRICT tiebreak, never a gate —
    # `entrance_sequence_prefers` only decides between candidates already equal under BOTH of the
    # existing ranking terms (the generator's own area-proximity order `generated.candidates`
    # already arrives in, and `_entrance_rank` above). A candidate is never promoted past a better
    # area-proximity or a better entrance rank for a shorter tunnel; it only breaks a genuine tie.
    best_used_area_m2: float | None = None
    best_entrance_seq: entrance_sequence.EntranceSequence | None = None
    stage("realize")
    for index, concept_candidate in enumerate(generated.candidates):
        # Tier 2 (`concept_generator.Repartition`) is strictly second: its candidates sit after
        # every normal one, and once ANY normal candidate has been chosen — by validation, or by
        # the relationship score — none of them is looked at. Without this, the relationship path
        # (which scores every candidate) would let a re-partitioned plan that satisfies one more
        # preference displace the plan the brief already had.
        if concept_candidate.repartitioned and chosen is not None:
            break
        attempts += 1
        try:
            candidate_solve = solve_fixture(concept_candidate.concept.fixture)
        except GeometryInfeasible as exc:
            failures.append(f"candidate {index} ({concept_candidate.strategy.value}): {exc}")
            continue

        if not relationships:
            candidate_plan = _realize(spec, buildable, site_constraints, concept_candidate, index,
                                      candidate_solve, relationships, on_stage=on_stage)
            if not candidate_plan.ok:
                first_refused = first_refused or candidate_plan
                failed = [c.check_id for c in candidate_plan.validation.failures()]
                failures.append(f"candidate {index} ({concept_candidate.strategy.value}) realized "
                                f"but failed validation: {', '.join(failed) or 'safety'}")
                continue
            rank = _entrance_rank(candidate_plan)
            candidate_seq = entrance_sequence.measure(candidate_plan.design)
            take = best_entrance_rank is None or rank < best_entrance_rank
            if (not take and rank == best_entrance_rank
                    and best_used_area_m2 is not None
                    and abs(concept_candidate.used_area_m2 - best_used_area_m2) < 1e-9
                    and best_entrance_seq is not None
                    and entrance_sequence.entrance_sequence_prefers(
                        best_entrance_seq, candidate_seq) is None):
                take = True
            if take:
                chosen, solve, chosen_index, plan = concept_candidate, candidate_solve, index, candidate_plan
                best_entrance_rank = rank
                best_used_area_m2 = concept_candidate.used_area_m2
                best_entrance_seq = candidate_seq
            if fast_path and best_entrance_rank == 0:
                break
            continue

        outcomes = _relationship_outcomes(concept_candidate, candidate_solve, relationships)
        broken = [o for o in outcomes if o.is_hard and not o.satisfied]
        if broken:
            failures.append(
                f"candidate {index} ({concept_candidate.strategy.value}) breaks a required "
                f"relationship: " + "; ".join(f"{o.statement} — {o.detail}" for o in broken))
            continue

        # Preferences only ever break a TIE between candidates that already satisfy every hard
        # relationship; `-index` keeps the generator's own ordering as the tiebreak, so a preference
        # can never promote a candidate the generator ranked lower on its own merits by more than
        # the preference it actually delivers.
        score = (sum(1 for o in outcomes if o.satisfied), -index)
        if best_score is None or score > best_score:
            best_score, best_solve = score, candidate_solve
            chosen, chosen_index = concept_candidate, index
        if best_score[0] == len(outcomes):
            break

    if relationships and best_solve is not None:
        # `solve` must always be the solve of the CHOSEN candidate. Assigning it inside the loop
        # left the two out of step whenever a later candidate was rejected, and the pipeline then
        # measured one fixture against another's rectangles — C2 reported thousands of unassigned
        # units. Set it once, here, from the candidate that actually won.
        solve = best_solve

    if chosen is None and first_refused is not None:
        # Every solved candidate was refused by validation: hand back the first, with its report,
        # exactly as a single refused candidate was handed back before the fall-through existed.
        chosen, chosen_index, plan = first_refused.concept, first_refused.index, first_refused
        solve = None

    if chosen is None:
        return GeneralSliceResult(
            AdapterOutcome.NO_SAFE_SOLVER_GEOMETRY, adapter_result,
            metrics=RunMetrics(solver_attempts=attempts,
                               latency_ms=round((time.perf_counter() - started) * 1000, 1),
                               **base_metrics),
            notes=tuple(failures))

    if plan is None:  # the relationships path chose on score; realize the winner here
        plan = _realize(spec, buildable, site_constraints, chosen, chosen_index, solve,
                        relationships, on_stage=on_stage)

    # 008 GUARD. When a demoted hub was passed over, the plan that won is compared with the hub
    # it displaced — both realized, both validated — and the hub stays the primary unless the
    # replacement is actually better (`hub_guard`). Without relationships only: the relationship
    # path already chose on a score of its own, and a hub kept here would bypass it.
    if not relationships and not chosen.hub_last_resort:
        chosen, chosen_index, plan = _guard_demoted_hub(
            spec, buildable, site_constraints, generated.candidates, chosen, chosen_index, plan,
            failures, on_stage=on_stage)
    # QUALITY TWIN (2026-09-16, phase 2). The plan that won is compared with ITS OWN peer
    # re-partitioned for room proportions (`concept_generator._quality_layouts`): the same
    # strategy, the same wings, the same sizing tier — both realized, both validated — and the
    # peer takes the primary's place only where its REALIZED bedroom-class shapes clear the
    # tier's acceptance rule against the primary's. Nothing else is compared: not another
    # footprint, not another parti, not the area (the peer's area IS the primary's). The base it
    # displaces is left out of the alternatives. Without relationships only, like the hub guard.
    displaced: frozenset[int] = frozenset()
    if not relationships and not chosen.quality_repartitioned:
        chosen, chosen_index, plan, displaced, twin_attempts = _prefer_quality_twin(
            spec, buildable, site_constraints, generated.candidates, chosen, chosen_index, plan,
            failures, on_stage=on_stage)
        attempts += twin_attempts
    design, validation, safety = plan.design, plan.validation, plan.safety
    path = render(design, render_path) if render_path else None

    # OTHER PLANS THE SAME BRIEF PRODUCES, when the caller asked for them. Computed here rather
    # than on demand because whether any exist is itself the answer — a screen cannot offer options
    # it has not proven are real.
    alternatives = (_alternative_plans(spec, buildable, site_constraints, generated.candidates,
                                       chosen_index, plan, relationships, max_alternatives,
                                       skip=displaced)
                    if max_alternatives > 0 else ())

    used_wings = {c.order for c in adapter_result.candidates
                  if c.order in chosen.wing_orders}
    unused = sum(c.area_m2 for c in adapter_result.candidates if c.order not in used_wings)
    metrics = RunMetrics(
        solver_attempts=attempts,
        first_valid_candidate_index=chosen_index,
        latency_ms=round((time.perf_counter() - started) * 1000, 1),
        wings_used=len(chosen.wing_orders),
        unused_safe_wing_area_m2=round(unused, 2),
        **base_metrics,
    )
    return GeneralSliceResult(
        AdapterOutcome.SOLVED, adapter_result, design, validation, safety, path,
        adapter_result.candidates[0], chosen, metrics, tuple(failures),
        # Measured on the CHOSEN plan, so the summary the person reads and the plan they see are
        # the same thing. Each alternative carries its own, for the same reason.
        relationships=plan.relationships,
        alternatives=alternatives)


def _quality_twins_of(candidates: tuple, chosen) -> list[tuple[int, object]]:
    """The chosen plan's quality peers: re-partitioned for proportions from the SAME base — same
    strategy, same wings, same sizing tier. The forced tree first, then the unforced twin: the
    base's cut regime is preferred, but a forced quality tree the solver refuses (its cuts land
    where the paired rows put them) still has its solver-cut twin."""
    wings = tuple(w.rect() for w in chosen.concept.fixture.wings)
    peers = [(i, c) for i, c in enumerate(candidates)
             if c.quality_repartitioned and c.strategy is chosen.strategy
             and tuple(w.rect() for w in c.concept.fixture.wings) == wings
             and (c.shrunk, c.over_preferred) == (chosen.shrunk, chosen.over_preferred)]
    forced = [p for p in peers if not p[1].rationale.endswith(generator.FREE_TWIN_RATIONALE)]
    twins = [p for p in peers if p[1].rationale.endswith(generator.FREE_TWIN_RATIONALE)]
    return forced + twins


def _realized_shapes(design: GeometricDesign) -> dict[str, tuple[float, float]]:
    return {r.zone_id: (r.net_w_m, r.net_h_m) for r in design.rooms}


def _prefer_quality_twin(spec: ArchitecturalSpec, buildable: BuildableRegion,
                         site_constraints: SiteConstraints | None, candidates: tuple,
                         chosen, chosen_index: int, plan: RealizedPlan, failures: list[str],
                         on_stage: Callable[[str], None] | None = None,
                         ) -> tuple[object, int, RealizedPlan, frozenset[int], int]:
    """The chosen plan, or its quality peer where that peer realizes, validates, and its realized
    bedroom-class shapes clear `concept_generator._quality_accepts` against the chosen plan's —
    the same rule the tier planned it by, now on the drawing. Returns the winner, its index, its
    plan, the indices to leave out of the alternatives (the displaced base), and the solver
    attempts spent."""
    peers = _quality_twins_of(candidates, chosen)
    if not peers:
        return chosen, chosen_index, plan, frozenset(), 0
    rooms = [z for z in chosen.concept.fixture.zones]
    templates = {z.zone_id: generator.ROOM_TEMPLATES.get(z.primary_role) for z in rooms}
    roles = {z.zone_id: z.primary_role for z in rooms}
    # ENSUITE-kind rooms are excluded here too, mirroring `concept_generator._preferred_aspects`
    # (2026-09-16, docs/WET_ROOM_STRIP_INVESTIGATION_REPORT.md §5) — same reason: an ensuite's
    # shape is its host row's, not its own, a different mechanism this change leaves untouched.
    ensuite_zones = {wr.zone_id for wr in chosen.wet_rooms if wr.kind is WetRoomKind.ENSUITE}
    preferred = {zid: t.preferred_aspect_ratio for zid, t in templates.items()
                 if t is not None and t.preferred_aspect_ratio is not None
                 and zid not in ensuite_zones}

    def aspects(design: GeometricDesign) -> dict[str, float]:
        shapes = _realized_shapes(design)
        return {zid: max(w, d) / max(min(w, d), 1e-6) for zid, (w, d) in shapes.items() if zid in preferred}

    class _Room:  # what `_quality_accepts`/`_quality_score` read: `.template`, `.role`
        def __init__(self, template, role):
            self.template = template
            self.role = role
    by_zone = {zid: _Room(templates[zid], roles[zid]) for zid in preferred}
    base = aspects(plan.design)
    attempts = 0
    for index, peer in peers:
        attempts += 1
        try:
            peer_solve = solve_fixture(peer.concept.fixture)
        except GeometryInfeasible as exc:
            failures.append(f"quality peer {index} ({peer.strategy.value}): {exc}")
            continue
        peer_plan = _realize(spec, buildable, site_constraints, peer, index, peer_solve, (),
                             on_stage=on_stage)
        if not peer_plan.ok:
            failed = [c.check_id for c in peer_plan.validation.failures()]
            failures.append(f"quality peer {index} ({peer.strategy.value}) realized but failed "
                            f"validation: {', '.join(failed) or 'safety'}")
            continue
        if generator._quality_accepts(base, aspects(peer_plan.design), by_zone):
            return peer, index, peer_plan, frozenset({chosen_index}), attempts
    return chosen, chosen_index, plan, frozenset(), attempts


def _guard_demoted_hub(spec: ArchitecturalSpec, buildable: BuildableRegion,
                       site_constraints: SiteConstraints | None,
                       candidates: tuple, chosen, chosen_index: int, plan: RealizedPlan,
                       failures: list[str],
                       on_stage: Callable[[str], None] | None = None):
    """The chosen plan, or the demoted hub it displaced when that hub is the better plan.

    Realizes the demoted hub (its forced tree first, then its twin — the first that solves and
    validates) only when one exists, so a brief without a hub pays nothing. The decision and its
    reason are written to the run's notes either way, so a kept or a demoted hub can be read off
    the diagnostics.
    """
    if not plan.ok:
        return chosen, chosen_index, plan
    # Only a hub that demotion actually DISPLACED is compared: one that would have come before
    # the winning plan in the pre-demotion order. A last-resort hub that would have trailed the
    # winner anyway was never the primary, and whether it should out-rank a poorer plan of the
    # same area is the open ranking question of specs/005 §11 — not this guard's.
    target = spec.program.target_built_area_m2
    demoted = [(index, c) for index, c in enumerate(candidates)
               if c.hub_last_resort and _would_have_preceded(c, chosen, target)]
    if not demoted:
        return chosen, chosen_index, plan
    for index, candidate in demoted:
        try:
            hub_solve = solve_fixture(candidate.concept.fixture)
        except GeometryInfeasible as exc:
            failures.append(f"hub guard: candidate {index} did not solve: {exc}")
            continue
        hub_plan = _realize(spec, buildable, site_constraints, candidate, index, hub_solve, (),
                            on_stage=on_stage)
        if not hub_plan.ok:
            failed = [c.check_id for c in hub_plan.validation.failures()]
            failures.append(f"hub guard: candidate {index} failed validation: "
                            f"{', '.join(failed) or 'safety'}")
            continue
        reason = hub_guard.hub_keeps_primary(hub_guard.proportions_of(hub_plan.design),
                                             hub_guard.proportions_of(plan.design))
        if reason is None:
            failures.append(f"hub guard: candidate {chosen_index} ({chosen.strategy.value}) "
                            f"replaces the demoted hub (candidate {index}): replacement is better")
            return chosen, chosen_index, plan
        # CIRCULATION QUALITY (Issue #36, hub_guard-style): hub_guard says the hub's bedroom/wet
        # proportions earn it the stay — but a hub whose realized circulation is not actually more
        # compact than the replacement's has not delivered the one thing a hub parti exists for
        # (specs/005). This narrows hub_guard's own decision further; it never overrides it the
        # other way — a hub is never handed the primary FOR its circulation when hub_guard already
        # said the replacement wins on proportions (`circulation_prefers`'s own docstring is why).
        circulation_reason = circulation_metrics.circulation_prefers(
            circulation_metrics.measure(hub_plan.design), hub_plan.design.gross_area_m2,
            circulation_metrics.measure(plan.design), plan.design.gross_area_m2)
        if circulation_reason is None:
            failures.append(f"circulation guard: candidate {chosen_index} ({chosen.strategy.value}) "
                            f"replaces the demoted hub (candidate {index}): its circulation is "
                            f"more compact than the hub's")
            return chosen, chosen_index, plan
        failures.append(f"hub guard: hub (candidate {index}) kept as primary over candidate "
                        f"{chosen_index} ({chosen.strategy.value}): {reason}")
        return candidate, index, hub_plan
    return chosen, chosen_index, plan


def _would_have_preceded(hub, chosen, target_m2: float | None) -> bool:
    """Whether `hub` came before `chosen` in the order `generate_concepts` had BEFORE 008 moved
    last-resort hubs to the end: without a target, insertion order (the hub is inserted last, so
    never); with one, forced trees by closeness to the target, then the twins by the same key."""
    if target_m2 is None:
        return False
    hub_is_twin = hub.rationale.endswith(generator.FREE_TWIN_RATIONALE)
    chosen_is_twin = chosen.rationale.endswith(generator.FREE_TWIN_RATIONALE)
    if hub_is_twin != chosen_is_twin:
        return chosen_is_twin  # every forced tree precedes every twin
    key = lambda c: (round(abs(c.used_area_m2 - target_m2), 4), round(c.used_area_m2, 4), c.strategy.value)
    return key(hub) < key(chosen)


def _realize(spec: ArchitecturalSpec, buildable: BuildableRegion,
             site_constraints: SiteConstraints | None,
             candidate: generator.ConceptCandidate, index: int, solve,
             relationships: tuple,
             on_stage: Callable[[str], None] | None = None) -> RealizedPlan:
    """One concept candidate -> doors, windows, furniture, validation, safety: a plan or nothing.

    Extracted so the CHOSEN plan and every alternative are produced by identical code. An
    alternative built by a second, similar-looking block would be a plan checked by a copy of the
    rules, and the copy is what eventually drifts.
    """
    def stage(name: str) -> None:
        if on_stage is not None:
            on_stage(name)

    concept = candidate.concept
    # THE FOOTPRINT IS THE FIXTURE'S WINGS — one rectangle per wing, in plot coordinates (the
    # generator positions them). `footprint` is their bounding box: the building line and the
    # frame; every stage below that cares which wall is which takes the wings.
    wings = tuple(w.rect() for w in concept.fixture.wings)
    footprint = footprint_module.bounding_box(wings)
    rects = solve.rects
    # WHERE THE FRONT DOOR GOES is read off the realized rooms, not assumed. `resolve_entrance`
    # returns the zone that genuinely fronts the street and the point on its own span; the walk is
    # then built to that point, so the path, the door and the room it opens into all agree.
    resolved = doors_stage.resolve_entrance(concept.fixture, rects, footprint, wings)
    entrance_zone_id = resolved[0] if resolved else concept.entrance_zone_id
    site_plan = _site_plan_for(spec, footprint, (resolved[1], resolved[2]) if resolved else None,
                               wings)

    stage("openings")
    interior_doors = doors_stage.generate_interior_doors(concept.fixture, rects)
    entrance_door = doors_stage.build_entrance_door(site_plan.entrance, footprint,
                                                    entrance_zone_id, wings)
    # Conflict avoidance BEFORE C28 (Issue #38): the entrance door itself never flips (there is no
    # other side of the street), but it stays IN this call so an interior door can still be flipped
    # away from a conflict WITH it.
    resolved_doors = door_clearance.resolve_swings(
        concept.fixture, rects, solve.walls, [*interior_doors, entrance_door])
    *interior_doors, entrance_door = resolved_doors
    windows = windows_stage.generate_windows(concept.fixture, rects, footprint, wings)
    furniture = furniture_stage.check_furniture_feasibility(concept.fixture, rects, solve.walls)

    stage("validate")
    validation = validation_stage.validate(
        concept.fixture, rects, solve.walls, interior_doors, entrance_door,
        windows, furniture, site_plan,
        corridor=spec.program.corridor,
        relationships=relationships,
        # The wet-room requirements of the programme THIS candidate was built from (the literal
        # brief's, or an eligible rearrangement's) — resolved, padded and defaulted, so a legacy
        # brief is held to its defaults and never skipped (C17 fails closed on absence).
        wet_rooms=candidate.wet_rooms,
        constraint=spec.safe_room_constraint,
    )
    stage("assemble")
    design = assemble(concept.fixture, rects, solve.walls, solve.wall_iterations,
                      interior_doors, entrance_door, windows, furniture, site_plan,
                      over_preferred=candidate.over_preferred, wet_rooms=candidate.wet_rooms)

    return RealizedPlan(
        index=index, concept=candidate, design=design, validation=validation,
        safety=_check_safety(design, buildable.require_known(),
                             _exclusion_geometry(site_constraints)),
        relationships=tuple(relationships_stage.evaluate(
            concept.fixture, rects,
            validation_stage.realized_connections(rects, solve.walls, interior_doors),
            relationships)) if relationships else ())


def _alternative_plans(spec: ArchitecturalSpec, buildable: BuildableRegion,
                       site_constraints: SiteConstraints | None,
                       candidates: tuple, chosen_index: int, chosen: RealizedPlan,
                       relationships: tuple, limit: int,
                       skip: frozenset[int] = frozenset()) -> tuple[RealizedPlan, ...]:
    """The other plans this brief and this land genuinely produce — never a lesser plan.

    An alternative is offered ONLY if it would have been accepted as the chosen one: every
    validation check passes and every room lies inside the buildable region. A candidate that
    fails a check is not a weaker option to be shown with a caveat, it is a plan this product
    does not draw — the same rule the chosen plan is held to in `demo/service.py`.

    Duplicates are dropped by realized geometry, not by strategy name: two strategies that produce
    the same rectangles produce the same drawing, whatever the generator called them.
    """
    found: list[RealizedPlan] = []
    seen = {chosen.layout_signature}
    # A family already realized (the chosen plan's, or an alternative's) is not tried again: the
    # demo shows one plan per family per outline (`service._select_plans`), so a second
    # re-proportioning of the same family would be realized and then dropped — and with each
    # fallback class keeping its own candidates (`concept_generator._build`), three such
    # re-proportionings of the primary's family filled the limit and a brief that had alternatives
    # showed none. Families are read off the concept's tree, before any solving.
    families = {chosen.family_signature}
    attempts = 0
    for index, candidate in enumerate(candidates):
        if len(found) >= limit or attempts >= ALTERNATIVE_ATTEMPT_LIMIT:
            break
        if index == chosen_index or index in skip:
            continue
        if _family_signature(candidate.concept.fixture, candidate.strategy) in families:
            continue
        attempts += 1
        try:
            solve = solve_fixture(candidate.concept.fixture)
        except GeometryInfeasible:
            continue
        plan = _realize(spec, buildable, site_constraints, candidate, index, solve, relationships)
        if not plan.ok or plan.layout_signature in seen:
            continue
        # ELIGIBILITY (2026-09-17): this walk takes ANY not-yet-seen family in generator order, so
        # a brief with fewer than `limit` distinct RECTANGLE families reaches an L candidate here
        # directly — before the massing-representation block below ever runs. The same gate
        # applies here for the same reason: an engine-generated non-rectangle massing earns a
        # slot, never gets one merely by being encountered first.
        if massing_of(candidate) != "1W":
            rect_plans = [p for p in ([chosen] + found) if p.massing_signature == "1W"]
            if rect_plans:
                best_rect_so_far = max(rect_plans, key=lambda p: p.concept.used_area_m2)
                if l_massing_guard.eligible_for_slot(best_rect_so_far, plan) is not None:
                    continue
        seen.add(plan.layout_signature)
        families.add(plan.family_signature)
        found.append(plan)

    # MASSING REPRESENTATION. The walk above takes candidates in the generator's order, and a
    # two-wing plan ranks by area like every other — behind the one-wing re-proportionings that
    # land nearer the request, and past the attempt cap. Measured on the five L sites: a valid L
    # existed for 17 of 25 briefs and reached the screen for one — as the primary, where nothing
    # one-wing planned. So one plan of every massing family the
    # candidates contain is guaranteed a look: for each family not yet represented, its candidates
    # are tried in the generator's order (bounded) and the first valid, distinct, ELIGIBLE one
    # joins the alternatives — in a slot of its own, beyond `limit`, so no one-wing alternative the
    # walk found is displaced (`ALTERNATIVE_PLAN_LIMIT` says why). The primary is untouched, and a
    # brief whose candidates are all one massing pays nothing here and stays within `limit`.
    #
    # ELIGIBILITY (2026-09-17, docs/L_MASSING_REPRESENTATION_QUALITY_GATE_INVESTIGATION.md): an
    # ENGINE-generated non-rectangle massing (today, only "2W" — an L) is no longer guaranteed a
    # slot merely by validating. It must clear `l_massing_guard.l_earns_representation_slot`
    # against the best "1W" plan already realized (the chosen primary, or an alternative the
    # normal walk already found) — the same hub_guard-style correctness-then-area-floor pattern
    # 008 already uses for the structurally identical "does the challenger replace the incumbent"
    # question. Measured: 14 of 16 real/fixture L's fail this gate, all on the area floor; the
    # gate reads only REALIZED metrics (area, bedroom/master/safe-room aspect, wet adjacency and
    # shape, two-sided exposure) — never `massing_signature` — so an L is never scored for being
    # an L. A brief with no realized "1W" plan to compare against (rare; a massing-only outline)
    # has nothing to gate against and the candidate is taken as before — there is no "better
    # rectangle" it could be displacing. Entrance-sequence quality is a separate, un-gated
    # follow-up (see that report's §5.1) and is untouched here.
    represented = {chosen.massing_signature} | {plan.massing_signature for plan in found}
    for massing in dict.fromkeys(massing_of(c) for c in candidates):
        if massing in represented:
            continue
        # Forced trees interleaved with their unforced twins: the generator lists every forced
        # tree before every twin (the primary must be found at today's position), but here the
        # question is only whether ANY valid plan of this massing exists within a few solves, and
        # the twin is what rescues a forced tree the solver refuses. Measured on the long-arm L
        # site: the 15 area-nearest L forced trees all failed in the solver and every twin solved,
        # so a walk in list order found nothing within the limit.
        family = [(i, c) for i, c in enumerate(candidates)
                  if i != chosen_index and i not in skip and massing_of(c) == massing]
        forced = [x for x in family if not x[1].rationale.endswith(generator.FREE_TWIN_RATIONALE)]
        twins = [x for x in family if x[1].rationale.endswith(generator.FREE_TWIN_RATIONALE)]
        interleaved = [x for pair in zip(forced, twins) for x in pair]
        interleaved += forced[len(twins):] + twins[len(forced):]
        best_rect = None
        if massing != "1W":
            rect_plans = [p for p in ([chosen] + found) if p.massing_signature == "1W"]
            if rect_plans:
                best_rect = max(rect_plans, key=lambda p: p.concept.used_area_m2)
        tries = 0
        for index, candidate in interleaved:
            if tries >= MASSING_ATTEMPT_LIMIT:
                break
            tries += 1
            try:
                solve = solve_fixture(candidate.concept.fixture)
            except GeometryInfeasible:
                continue
            plan = _realize(spec, buildable, site_constraints, candidate, index, solve, relationships)
            if not plan.ok or plan.layout_signature in seen:
                continue
            if (best_rect is not None
                    and l_massing_guard.eligible_for_slot(best_rect, plan) is not None):
                continue
            seen.add(plan.layout_signature)
            found.append(plan)
            represented.add(massing)
            break
    return tuple(found)


def run_general_from_site(site: SiteConstraints, *, render_path: str | None = None,
                          plot_size_m: tuple[float, float] = (24.0, 28.0),
                          program: ProgramSpec | None = None,
                          fast_path: bool = True,
                          max_alternatives: int = 0) -> GeneralSliceResult:
    """parcel + constraints -> buildable region -> the full run."""
    buildable = build_buildable_region(site)
    return run_general(buildable, render_path=render_path, site_constraints=site,
                       plot_size_m=plot_size_m, program=program, fast_path=fast_path,
                       max_alternatives=max_alternatives)
