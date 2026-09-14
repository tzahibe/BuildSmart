"""The hub demotion guard: a demoted hub is replaced only by a plan that is actually better.

Feature 008 moves a hub whose bound misses the §6 gates to the END of the candidate list, and the
first-realizable pipeline then delivers whatever candidate is next by area. Measured on the
current main (specs/008 review, 2026-09-14), that replaced eleven hub primaries: five with a plan of
the same area and far better bedrooms — the intended effect — but one with a plan worse on every
proportion the hub was demoted for, and four with a plan a quarter to a third SMALLER than the
house the hub delivered. A threshold said the hub was not good enough; nothing asked whether the
replacement was any better.

This module asks. It compares two REALIZED, validated plans on the same outline — the plan that
won and the demoted hub — on the proportions the bound judges (bedroom, master, safe-room aspect,
wet adjacency) and on delivered area. The hub stays primary when the replacement is not better on
any of those, or when it delivers less than `AREA_KEEP_RATIO` of the hub's area. Nothing here
touches the bound, its gates, candidate topology or the validators: a plan that failed validation
never reaches this comparison, and a hub the guard keeps is the same plan the pipeline would have
delivered before 008.
"""
from __future__ import annotations

from dataclasses import dataclass

from .design_output import GeometricDesign
from .geometry_core.model import ProgramRole

#: Policy: a replacement that delivers less than this share of the demoted hub's gross area is not
#: an improvement, whatever its proportions. Chosen from the measured cases: the four narrow-deep
#: outlines lost 15–29 % (77–87 % of the ask → 54–74 %); the five wide outlines lost 1–2 %.
AREA_KEEP_RATIO = 0.85

#: Below this, two aspects are the same number — the 5 cm grid moves a 3.5 m room's aspect by ~0.02.
_ASPECT_EPS = 0.02

_WET_ROLES = (ProgramRole.BATHROOM, ProgramRole.TOILET)
_WET_NEIGHBOUR_ROLES = _WET_ROLES + (ProgramRole.KITCHEN,)


@dataclass(frozen=True)
class PlanProportions:
    """What the guard compares — the same quantities the §6 gates and the 008 bound speak of."""

    area_m2: float
    bedroom_max: float | None       # worst secondary bedroom long/short
    master: float | None
    safe_room: float | None
    wet_adjacent: int               # wet rooms touching another wet room or the kitchen
    wet_total: int

    @property
    def wet_share(self) -> float:
        return self.wet_adjacent / self.wet_total if self.wet_total else 1.0


def _aspect(rect: tuple[float, float, float, float]) -> float:
    _, _, w, h = rect
    return max(w, h) / max(min(w, h), 1e-6)


def _touching(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x_overlap = min(ax + aw, bx + bw) - max(ax, bx)
    y_overlap = min(ay + ah, by + bh) - max(ay, by)
    return (abs(x_overlap) < 1e-6 and y_overlap > 0.5) or (abs(y_overlap) < 1e-6 and x_overlap > 0.5)


def proportions_of(design: GeometricDesign) -> PlanProportions:
    rooms = list(design.rooms)
    beds = [_aspect(r.rect_m) for r in rooms if ProgramRole.BEDROOM in r.roles]
    master = [_aspect(r.rect_m) for r in rooms if ProgramRole.MASTER_BEDROOM in r.roles]
    safe = [_aspect(r.rect_m) for r in rooms if ProgramRole.SAFE_ROOM in r.roles]
    wet = [r for r in rooms if any(role in r.roles for role in _WET_ROLES)]
    neighbours = [r for r in rooms if any(role in r.roles for role in _WET_NEIGHBOUR_ROLES)]
    adjacent = sum(
        1 for w in wet
        if any(n is not w and _touching(w.rect_m, n.rect_m) for n in neighbours))
    return PlanProportions(
        area_m2=design.gross_area_m2,
        bedroom_max=max(beds) if beds else None,
        master=master[0] if master else None,
        safe_room=safe[0] if safe else None,
        wet_adjacent=adjacent, wet_total=len(wet))


def hub_keeps_primary(hub: PlanProportions, replacement: PlanProportions,
                      *, area_keep_ratio: float = AREA_KEEP_RATIO) -> str | None:
    """Why the demoted hub stays the primary, or `None` when the replacement is the better plan.

    Two rules, in the order they were decided:

    1. CORRECTNESS — the replacement must be better on at least one of the proportions the hub was
       demoted for (lower bedroom / master / safe-room aspect, higher wet adjacency) or deliver
       more area. A replacement that is worse or equal on all of them has no claim on the primary.
    2. POLICY — a replacement that delivers less than `area_keep_ratio` of the hub's area is not an
       improvement: better-proportioned rooms in a house a quarter smaller than the one the person
       asked for is not what "better" means here.

    Compares realized numbers only; a metric absent from either plan (no safe room, no secondary
    bedroom) is not compared.
    """
    better_on = []
    for name in ("bedroom_max", "master", "safe_room"):
        h, r = getattr(hub, name), getattr(replacement, name)
        if h is not None and r is not None and r < h - _ASPECT_EPS:
            better_on.append(name)
    if replacement.wet_total and replacement.wet_share > hub.wet_share + 1e-9:
        better_on.append("wet_adjacency")
    if replacement.area_m2 > hub.area_m2 + 0.05:
        better_on.append("area")
    if not better_on:
        return ("replacement is better on no proportion the hub was demoted for and not larger "
                f"({replacement.area_m2:.1f} vs {hub.area_m2:.1f} m²)")
    if replacement.area_m2 < area_keep_ratio * hub.area_m2:
        return (f"replacement delivers {replacement.area_m2:.1f} m², under "
                f"{area_keep_ratio:.0%} of the hub's {hub.area_m2:.1f} m²")
    return None
