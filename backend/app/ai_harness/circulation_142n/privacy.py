"""#142N step 3 — the architectural direction question: is LESS circulation better?

`circulation_prefers` treats a lower circulation ratio and a shorter longest segment as strictly
better. Architecturally that is only true inside bounds: a house with no dedicated circulation
reaches its bedrooms THROUGH other rooms, which is the zoning defect the corrected proposer prompt
was changed to forbid ("a bedroom ... is entered ONLY from a hall or circulation space", #142L).

Nothing new is measured here. Every quantity is read off the realized plan record that
`quality_142l.baseline.plan_record` already saves — room roles, the realized door list, and
production's own `wet_privacy` and `entrance_sequence` output.
"""
from __future__ import annotations

import itertools

from app.vertical_slice.circulation_metrics import _EPS

from .relation import Plan

CIRCULATION_ROLES = frozenset({"HALL", "CIRCULATION"})
#: Rooms whose entry route is a privacy question — the roles the corrected prompt rule names.
PRIVATE_ROLES = frozenset({"BEDROOM", "MASTER_BEDROOM", "STUDY", "DRESSING_ROOM", "SAFE_ROOM"})
#: Rooms a private room should NOT be entered through.
PUBLIC_ROLES = frozenset({"LIVING", "KITCHEN", "DINING", "FAMILY_ROOM"})


def zoning_facts(p: Plan) -> dict:
    """How this plan's circulation actually serves privacy and zoning."""
    rooms = p.record["rooms"]
    role = {z: (r.get("role") or "") for z, r in rooms.items()}
    circ = {z for z, r in role.items() if r in CIRCULATION_ROLES}
    private = [z for z, r in role.items() if r in PRIVATE_ROLES]
    doors = p.record["doors"]
    neighbours: dict[str, set[str]] = {}
    for d in doors:
        if not d.get("placeable", True):
            continue
        neighbours.setdefault(d["a"], set()).add(d["b"])
        neighbours.setdefault(d["b"], set()).add(d["a"])
    for group in p.record.get("open_groups") or ():
        for a, b in itertools.combinations(group, 2):
            neighbours.setdefault(a, set()).add(b)
            neighbours.setdefault(b, set()).add(a)
    from_circ, from_public, from_other = [], [], []
    for z in private:
        ns = neighbours.get(z, set())
        if ns & circ:
            from_circ.append(z)
        elif any(role.get(q) in PUBLIC_ROLES for q in ns):
            from_public.append(z)
        else:
            from_other.append(z)
    wet = p.record.get("wet_privacy") or []
    ent = p.record["production_quality"]["entrance"]
    return {
        "private_rooms": len(private),
        "private_from_circulation": len(from_circ),
        "private_through_public_room": len(from_public),
        "private_through_other_room": len(from_other),
        "private_not_from_circulation": len(from_public) + len(from_other),
        "private_through_public_zones": sorted(from_public),
        "wet_rooms": len(wet),
        "wet_privacy_worst": max((w["privacy_score"] for w in wet), default=None),
        "wet_privacy_sum": sum(w["privacy_score"] for w in wet) if wet else None,
        "private_doors_passed": ent["private_doors_passed"],
        "is_circulation_arrival": bool(ent["is_circulation_arrival"]),
    }


def lower_ratio_costs_zoning(plans: list[Plan]) -> dict:
    """Every within-brief ordered pair where F0 calls `y` better for having a LOWER circulation
    ratio, counted by whether `y`'s zoning is actually worse.

    `worse_zoning` is the case that matters: production's comparator prefers the plan that spends
    less on circulation, and that plan reaches MORE of its private rooms through another room.
    """
    facts = {p.key: zoning_facts(p) for p in plans}
    rows = []
    for x, y in itertools.permutations(plans, 2):
        if y.metrics.ratio >= x.metrics.ratio - _EPS:
            continue                                  # F0 does not call y better on ratio
        fx, fy = facts[x.key], facts[y.key]
        delta = fy["private_not_from_circulation"] - fx["private_not_from_circulation"]
        rows.append({
            "preferred": y.key, "over": x.key,
            "ratio": [round(x.metrics.ratio, 4), round(y.metrics.ratio, 4)],
            "private_not_from_circulation": [fx["private_not_from_circulation"],
                                             fy["private_not_from_circulation"]],
            "private_through_public_room": [fx["private_through_public_room"],
                                            fy["private_through_public_room"]],
            "wet_privacy_sum": [fx["wet_privacy_sum"], fy["wet_privacy_sum"]],
            "zoning_delta": delta,
            "verdict": "WORSE_ZONING" if delta > 0 else ("BETTER_ZONING" if delta < 0 else "SAME_ZONING"),
        })
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    worse = [r for r in rows if r["verdict"] == "WORSE_ZONING"]
    return {"pairs_where_lower_ratio_preferred": len(rows), "verdicts": counts,
            "worse_zoning_examples": worse[:8],
            "share_worse_or_equal": round(
                (counts.get("WORSE_ZONING", 0) + counts.get("SAME_ZONING", 0)) / len(rows), 3)
            if rows else None}


def ratio_vs_zoning_table(plans: list[Plan]) -> dict:
    """The pool-wide picture: mean circulation ratio grouped by how many private rooms are NOT
    entered from circulation. If spending more on circulation buys zoning, the group with zero
    such rooms has the HIGHER ratio."""
    buckets: dict[int, list[float]] = {}
    for p in plans:
        n = zoning_facts(p)["private_not_from_circulation"]
        buckets.setdefault(n, []).append(p.metrics.ratio)
    return {str(n): {"plans": len(v), "mean_ratio": round(sum(v) / len(v), 4),
                     "min_ratio": round(min(v), 4), "max_ratio": round(max(v), 4)}
            for n, v in sorted(buckets.items())}


__all__ = ["PRIVATE_ROLES", "PUBLIC_ROLES", "zoning_facts", "lower_ratio_costs_zoning",
           "ratio_vs_zoning_table"]


def branching_facts(plans: list[Plan]) -> dict:
    """Does spending MORE on circulation buy privacy? The place to look is a plan with more than
    one circulation room — a bedroom-wing spur off a main hall, which costs ratio and total length
    and exists to separate the private wing from the public one.

    Grouped by how many circulation rooms a plan has, with the circulation cost and the privacy
    that cost bought. If more circulation were simply worse, the multi-room group would show the
    higher ratio AND no privacy gain.
    """
    groups: dict[int, list[Plan]] = {}
    for p in plans:
        rooms = p.record["rooms"]
        n = sum(1 for r in rooms.values() if (r.get("role") or "") in CIRCULATION_ROLES)
        groups.setdefault(n, []).append(p)

    def mean(vals):
        vals = [v for v in vals if v is not None]
        return round(sum(vals) / len(vals), 4) if vals else None

    out = {}
    for n, ps in sorted(groups.items()):
        facts = [zoning_facts(p) for p in ps]
        out[str(n)] = {
            "plans": len(ps),
            "mean_ratio": mean([p.metrics.ratio for p in ps]),
            "mean_total_length_m": mean([p.metrics.total_length_m for p in ps]),
            "mean_narrowest_width_m": mean([p.metrics.narrowest_width_m for p in ps]),
            "mean_dead_end_count": mean([float(p.metrics.dead_end_count) for p in ps]),
            "mean_duplicated_segment_count": mean([float(p.metrics.duplicated_segment_count) for p in ps]),
            "mean_private_not_from_circulation": mean([float(f["private_not_from_circulation"]) for f in facts]),
            "mean_wet_privacy_sum": mean([f["wet_privacy_sum"] for f in facts]),
            "mean_private_doors_passed": mean([float(f["private_doors_passed"]) for f in facts]),
        }
    return out


def ratio_vs_width(plans: list[Plan]) -> dict:
    """What a lower circulation ratio actually buys back on this pool: the corridor gets narrower.

    `circulation_prefers` treats lower ratio as monotonically better and has no lower bound at all,
    while the only thing stopping a corridor from shrinking is the solver's own minimum width. The
    quartile table says whether the two move together.
    """
    rows = sorted(plans, key=lambda p: p.metrics.ratio)
    n = len(rows)
    out = {}
    for q in range(4):
        part = rows[q * n // 4:(q + 1) * n // 4]
        if not part:
            continue
        widths = [p.metrics.narrowest_width_m for p in part if p.metrics.narrowest_width_m is not None]
        out[f"Q{q + 1}"] = {
            "plans": len(part),
            "ratio_range": [round(part[0].metrics.ratio, 4), round(part[-1].metrics.ratio, 4)],
            "mean_narrowest_width_m": round(sum(widths) / len(widths), 3) if widths else None,
            "min_narrowest_width_m": round(min(widths), 3) if widths else None,
            "mean_circulation_area_m2": round(sum(p.metrics.area_m2 for p in part) / len(part), 3),
        }
    return out


__all__ += ["branching_facts", "ratio_vs_width"]


def ratio_vs_dead_ends(plans: list[Plan]) -> dict:
    """The one place this pool DOES show that more circulation is better.

    A dead end is an un-served corridor end — the corridor stops before it reaches a room. Stopping
    a corridor short is also the cheapest way to lower the circulation ratio, so the two measures
    `circulation_prefers` treats as pointing the same way ("lower ratio" and "fewer dead ends")
    pull against each other: the plan that spends MORE on circulation is the one whose corridor
    reaches both ends.
    """
    groups: dict[int, list[Plan]] = {}
    for p in plans:
        groups.setdefault(p.metrics.dead_end_count, []).append(p)
    out = {}
    for n, ps in sorted(groups.items()):
        out[str(n)] = {
            "plans": len(ps),
            "mean_ratio": round(sum(p.metrics.ratio for p in ps) / len(ps), 4),
            "mean_circulation_area_m2": round(sum(p.metrics.area_m2 for p in ps) / len(ps), 3),
            "mean_longest_segment_m": round(
                sum(p.metrics.longest_segment_m for p in ps if p.metrics.longest_segment_m is not None)
                / max(1, sum(1 for p in ps if p.metrics.longest_segment_m is not None)), 3),
        }
    return out


def within_brief_ratio_vs_dead_ends(by_brief: dict[str, list[Plan]]) -> dict:
    """The same question asked only between plans of the SAME brief, which is the only comparison a
    selection ever makes. Counts the ordered pairs where `circulation_prefers` calls `y` better for
    its lower ratio while `y` actually has MORE dead ends."""
    rows = []
    for plans in by_brief.values():
        for x in plans:
            for y in plans:
                if x is y or y.metrics.ratio >= x.metrics.ratio - _EPS:
                    continue
                if y.metrics.dead_end_count > x.metrics.dead_end_count:
                    rows.append({"preferred_for_lower_ratio": y.key, "over": x.key,
                                 "ratio": [round(x.metrics.ratio, 4), round(y.metrics.ratio, 4)],
                                 "dead_ends": [x.metrics.dead_end_count, y.metrics.dead_end_count],
                                 "circulation_area_m2": [x.metrics.area_m2, y.metrics.area_m2]})
    return {"pairs_where_lower_ratio_means_more_dead_ends": len(rows), "examples": rows[:6]}


__all__ += ["ratio_vs_dead_ends", "within_brief_ratio_vs_dead_ends"]
