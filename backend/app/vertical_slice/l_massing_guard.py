"""The L-massing representation guard: an engine-generated L earns its shown slot only against
the best rectangle already available — it is never given one merely for being a different shape.

docs/L_MASSING_REPRESENTATION_QUALITY_GATE_INVESTIGATION.md measured this directly: an engine L's
one real, near-universal advantage is two-sided exposure, bought at a severe, consistent area
cost (median ~0.79x the best rectangle in the same pool; 14 of 16 measured cases fell under
`hub_guard.AREA_KEEP_RATIO`). Room-proportion effects are genuinely mixed — sometimes the L wins,
sometimes it loses — never consistently either way, and the L is essentially never strictly
worse on every proportion (exposure keeps that from happening), which is why an area floor is a
SEPARATE policy rule here, not folded into a pure dominance check.

This module is deliberately the same SHAPE as `hub_guard.py` (feature 008's demotion guard) —
reusing `PlanProportions`/`proportions_of` for the metrics they already cover, and the same
two-rule pattern (a correctness check, then a policy floor) rather than a new weighted score. It
does not touch `hub_guard.py` itself: the L-vs-rectangle decision needs two extra realized
metrics (two-sided exposure, worst wet-room aspect) `PlanProportions` does not carry, and adding
them as parameters here keeps `hub_guard.py`'s own dataclass and its 008 tests completely
untouched.
"""
from __future__ import annotations

from dataclasses import dataclass

from .design_output import GeometricDesign
from .geometry_core.model import ProgramRole
from .hub_guard import AREA_KEEP_RATIO, PlanProportions, proportions_of
from app.geometry_domain.walls import BoundaryContext

#: Same tolerance as `hub_guard._ASPECT_EPS` — the 5 cm grid moves an aspect by ~0.02.
_ASPECT_EPS = 0.02
#: Same idea for a share (0.0-1.0) metric: two plans within 2 percentage points of two-sided
#: exposure are the same number for this purpose.
_SHARE_EPS = 0.02

_WET_ROLES = (ProgramRole.BATHROOM, ProgramRole.TOILET)
_HABITABLE_ROLES = frozenset({"LIVING", "DINING", "KITCHEN", "BEDROOM", "MASTER_BEDROOM",
                              "SAFE_ROOM"})


@dataclass(frozen=True)
class ExposureProportions:
    """The two realized measures `PlanProportions` does not carry, needed for this comparison
    specifically: worst wet-room aspect (the strip-quality metric) and two-sided habitable share
    (the L's one real, structural advantage). Kept apart from `PlanProportions` rather than added
    to it — see the module docstring."""

    worst_wet_aspect: float | None
    two_sided_share: float | None


def exposure_of(design: GeometricDesign) -> ExposureProportions:
    wet_aspects = []
    for r in design.rooms:
        if any(role in r.roles for role in _WET_ROLES):
            wet_aspects.append(max(r.net_w_m, r.net_h_m) / max(min(r.net_w_m, r.net_h_m), 1e-6))
    habitable = [r for r in design.rooms if set(r.roles) & _HABITABLE_ROLES]
    two_sided = (sum(1 for r in habitable
                     if sum(1 for f in r.wall_facts.values()
                            if f.boundary_context is BoundaryContext.EXTERIOR) >= 2)
                 / len(habitable)) if habitable else None
    return ExposureProportions(max(wet_aspects) if wet_aspects else None, two_sided)


def l_earns_representation_slot(rect: PlanProportions, rect_x: ExposureProportions,
                                l: PlanProportions, l_x: ExposureProportions,
                                *, area_keep_ratio: float = AREA_KEEP_RATIO) -> str | None:
    """`None`: the L may take the non-rectangle representation slot. Otherwise, why not.

    Two rules, mirroring `hub_guard.hub_keeps_primary`'s pattern (a correctness check, then a
    policy floor) rather than a weighted score — no `hub_keeps_primary`-style rule 2 ("not worse
    on the incumbent's own worst gate") has a clean analogue here: a rectangle is not demoted for
    missing a bound the way a hub is, so there is no single protected gate to name. What that
    rule protects against — winning on a weak dimension while losing badly elsewhere — is already
    covered here by the area floor doing the actual work (§ measured: rule 1 essentially always
    passes, because two-sided exposure is real often enough that the L is almost never STRICTLY
    worse on everything; rule 2, the area floor, is what actually gates).

    1. CORRECTNESS — the L must be better on at least one compared proportion (bedroom/master/
       safe-room aspect, wet adjacency, worst wet-room aspect, two-sided exposure) or deliver more
       area. An L better on nothing and not larger has no claim on a slot.
    2. POLICY — the L must deliver at least `area_keep_ratio` of the best rectangle's area
       (reusing `hub_guard.AREA_KEEP_RATIO` by default — the same, already-calibrated threshold
       008 uses for the structurally analogous "does the challenger replace the incumbent"
       decision, not a new number).

    No score or bonus is given merely for being an L: every comparison reads REALIZED metrics off
    both plans and nothing here reads massing/strategy at all.
    """
    better_on, worse_on = [], []
    for name, r_val, l_val in (
        ("bedroom_max", rect.bedroom_max, l.bedroom_max),
        ("master", rect.master, l.master),
        ("safe_room", rect.safe_room, l.safe_room),
        ("worst_wet_aspect", rect_x.worst_wet_aspect, l_x.worst_wet_aspect),
    ):
        if r_val is None or l_val is None:
            continue
        if l_val < r_val - _ASPECT_EPS:
            better_on.append(name)
        elif l_val > r_val + _ASPECT_EPS:
            worse_on.append(name)
    if rect_x.two_sided_share is not None and l_x.two_sided_share is not None:
        if l_x.two_sided_share > rect_x.two_sided_share + _SHARE_EPS:
            better_on.append("two_sided_share")
        elif l_x.two_sided_share < rect_x.two_sided_share - _SHARE_EPS:
            worse_on.append("two_sided_share")
    if l.wet_total and l.wet_share > rect.wet_share + 1e-9:
        better_on.append("wet_adjacency")
    elif l.wet_total and l.wet_share < rect.wet_share - 1e-9:
        worse_on.append("wet_adjacency")
    if l.area_m2 > rect.area_m2 + 0.05:
        better_on.append("area")
    if not better_on:
        return ("L is better on no measured proportion and not larger "
                f"({l.area_m2:.1f} vs {rect.area_m2:.1f} m2)")
    if l.area_m2 < area_keep_ratio * rect.area_m2:
        return (f"L delivers {l.area_m2:.1f} m2, under {area_keep_ratio:.0%} of the best "
                f"rectangle's {rect.area_m2:.1f} m2")
    return None


def eligible_for_slot(rect_plan, l_plan) -> str | None:
    """`l_earns_representation_slot`, reading the two REALIZED plans' `.design` directly — the
    one seam both call sites (`general_pipeline._alternative_plans`,
    `demo.service._select_plans`) use, so a test can stand in for it without building full
    geometry (see `demo.service._l_massing_eligible`, the analogous existing seam
    `_l_quality_of_plan` already set the precedent for)."""
    return l_earns_representation_slot(
        proportions_of(rect_plan.design), exposure_of(rect_plan.design),
        proportions_of(l_plan.design), exposure_of(l_plan.design))
