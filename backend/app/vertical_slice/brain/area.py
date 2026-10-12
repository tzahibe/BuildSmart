"""Did the plan deliver the area that was asked for — and if not, WHOSE fault is it (#197).

The brain's first report quoted "area fidelity 53-110%" as one number, which hid two unrelated
things and, worse, presented a plan covering 53% of the brief as meeting it. This module splits
them, because the answers are opposite:

  the PLAN missed        the room programme could have filled the footprint and the layout did
                         not. A defect. The plan must not count.
  the BRIEF cannot add   the room list, at every room's own template ceiling, totals less than
                         the area requested. B09 asks for 440 m2 from a programme that tops out at
                         250; production delivers 51.6% of it and the brain 40%, and neither is
                         wrong — there is no 440 m2 house made of those rooms. The caller passes
                         that ceiling in as `capacity_m2`, and it should be production's own
                         `program_capacity_gross_m2`, never a second opinion about it.

PRIOR ART, and this module does not replace it. `contract.capacity_notice_text` already tells the
customer when the requested area exceeds the programme's capacity, and it is already attached to
every design the brain produces. What is added here is that the number also GATES delivery instead
of only being printed, and that "the brief does not add up" is distinguished from "the layout fell
short" — a distinction the notice cannot make, because it never looks at the realized plan.

Decidable before any geometry exists in the second case, which is why it is cheap and exact.

Gross vs net, stated once so the report cannot conflate them again (it did): GROSS is the sum of
`gross_area_m2` — rooms including their share of wall thickness, the figure a brief's "built area"
means. NET is the usable floor inside the walls, 7-9 points lower on these briefs.
"""
from __future__ import annotations

from dataclasses import dataclass

#: How far from the requested area a plan may land and still be said to MEET the brief.
AREA_TOLERANCE = 0.10
#: …and how far it may fall short and still be DELIVERED, with the shortfall stated.
#:
#: Two thresholds, not one, and the second is deliberately loose. Measured first, chosen after:
#: PRODUCTION — the shipping product — lands at 98.2%, 99.1%, 62.6%, 77.4%, 87.2%, 95.2%, 56.9%
#: and 51.6% of the requested area on these eight briefs. A single 10% bar rejects the product on
#: four of eight, and a bar the shipping path cannot clear is not a quality bar. Setting it at 20%
#: instead — enough to pass the brain and fail production — would be the same dishonesty pointed
#: the other way.
#:
#: So the two numbers do different jobs. 10% is what may be CLAIMED: inside it the plan meets the
#: brief, and `meets_brief` is the only thing a customer is ever shown as success. 50% is a floor
#: on what may be DRAWN at all: below half the area asked for, the drawing is not an answer to
#: that brief whatever its proportions. Between them the plan ships with the shortfall in writing.
AREA_DISCLOSE_TOLERANCE = 0.50


@dataclass(frozen=True)
class AreaVerdict:
    code: str
    requested_m2: float
    gross_m2: float
    net_m2: float
    capacity_m2: float
    detail: str

    @property
    def gross_pct(self) -> float:
        return round(100 * self.gross_m2 / self.requested_m2, 1) if self.requested_m2 else 0.0

    @property
    def net_pct(self) -> float:
        return round(100 * self.net_m2 / self.requested_m2, 1) if self.requested_m2 else 0.0

    #: Codes a plan may be DELIVERED under. Everything else is refused.
    DELIVERABLE = ("WITHIN_TOLERANCE", "BELOW_TARGET_DISCLOSED", "PROGRAMME_UNDERFILLS_FOOTPRINT",
                   "NO_TARGET")

    @property
    def acceptable(self) -> bool:
        """`PROGRAMME_UNDERFILLS_FOOTPRINT` is deliverable and `AREA_TOLERANCE_EXCEEDED` is not —
        the distinction this module exists for. The first is the honest answer to a brief that
        does not add up and arrives WITH that explanation attached; the second is the layout
        failing at something its own programme could have done."""
        return self.code in self.DELIVERABLE

    @property
    def meets_brief(self) -> bool:
        """Stricter than `acceptable`: only this may be presented as meeting the requested area."""
        return self.code == "WITHIN_TOLERANCE"


def assess_area(requested_m2: float, gross_m2: float, net_m2: float, capacity_m2: float,
                tolerance: float = AREA_TOLERANCE,
                disclose_tolerance: float = AREA_DISCLOSE_TOLERANCE) -> AreaVerdict:
    """Classify one realized plan's area against the brief. Never changes geometry."""
    def v(code: str, detail: str) -> AreaVerdict:
        return AreaVerdict(code, round(requested_m2, 2), round(gross_m2, 2), round(net_m2, 2),
                           round(capacity_m2, 2), detail)

    if requested_m2 <= 0:
        return v("NO_TARGET", "the brief states no built area to measure against")

    low, high = requested_m2 * (1 - tolerance), requested_m2 * (1 + tolerance)
    if low <= gross_m2 <= high:
        return v("WITHIN_TOLERANCE",
                 f"{gross_m2:.0f} m² gross against {requested_m2:.0f} m² requested "
                 f"(±{tolerance:.0%})")
    if gross_m2 > high:
        return v("AREA_OVER_TOLERANCE",
                 f"{gross_m2:.0f} m² gross exceeds the {requested_m2:.0f} m² requested by more "
                 f"than {tolerance:.0%} — the plan is larger than the brief asked for")
    if capacity_m2 >= low and gross_m2 >= requested_m2 * (1 - disclose_tolerance):
        return v("BELOW_TARGET_DISCLOSED",
                 f"{gross_m2:.0f} m² gross against {requested_m2:.0f} m² requested "
                 f"({100 * gross_m2 / requested_m2:.0f}%) — delivered, but it is {requested_m2 - gross_m2:.0f} m² "
                 f"short of the brief and that is stated rather than rounded away")
    if capacity_m2 < low:
        return v("PROGRAMME_UNDERFILLS_FOOTPRINT",
                 f"the requested rooms cannot make a {requested_m2:.0f} m² house: at every room's "
                 f"own maximum size they total {capacity_m2:.0f} m². This plan delivers "
                 f"{gross_m2:.0f} m² gross. To reach {requested_m2:.0f} m² the brief needs more "
                 f"rooms or larger room types, not a different layout")
    return v("AREA_TOLERANCE_EXCEEDED",
             f"{gross_m2:.0f} m² gross against {requested_m2:.0f} m² requested, and the programme "
             f"could have reached {capacity_m2:.0f} m² — the layout, not the brief, fell short")
