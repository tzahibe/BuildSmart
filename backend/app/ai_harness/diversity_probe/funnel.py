"""Stage-by-stage diversity funnel through the REAL production path, on the eight frozen briefs.

    brief -> outlines -> concept candidates -> realization -> validation -> _select_plans -> response

At every stage this counts how many STRUCTURALLY DISTINCT concepts survive, using production's own
representations wherever one exists:

    massing_signature   one wing or two (coarsest; production's own)
    family_signature    "same arrangement?" — production's own display de-duplication key
    layout_signature    "same drawing?" — production's own
    access graph        the undirected door/open-join graph over ROLES, measured here from the
                        realized design because production has no scalar for it

Nothing is modified: `demo.service`'s own functions are called and their results inspected.

    PYTHONPATH=backend python -m app.ai_harness.diversity_probe.funnel <out.json>
"""
from __future__ import annotations

import json
import os
import sys

from app.ai_harness.topology_poc import briefs as briefs_mod
from app.demo import service as svc

#: The eight Product Readiness Audit briefs (PR #179), unchanged.
BRIEFS = ("B08", "B20", "B02", "B11", "B16", "B19", "B06", "B09")

CIRC = frozenset({"HALL", "CIRCULATION"})
PRIVATE = frozenset({"BEDROOM", "MASTER_BEDROOM", "STUDY", "DRESSING_ROOM", "SAFE_ROOM"})
PUBLIC = frozenset({"LIVING", "KITCHEN", "DINING", "FAMILY_ROOM"})
WET = frozenset({"BATHROOM", "TOILET"})


def _project_for(b):
    from tests.vertical_slice.test_hub_guard import _project
    return _project(dict(bedrooms=b.bedrooms, wet_rooms=b.wet_rooms, safe_room=b.safe_room,
                         open_plan=b.open_plan, built_area_m2=b.built_area_m2,
                         footprint_width_m=b.footprint_width_m, footprint_depth_m=b.footprint_depth_m,
                         plot_width_m=b.footprint_width_m + 8, plot_depth_m=b.footprint_depth_m + 8))


def access_graph(design) -> frozenset:
    """The plan's connectivity over ROLES, which is what "a different concept" has to change.

    Roles, not zone ids, so two plans are the same concept when the same KINDS of room connect the
    same way however the engine named them. Open-plan joins count as connections, because an open
    interface is a connection a person walks through.
    """
    role = {}
    for r in design.rooms:
        role[r.zone_id] = r.roles[0] if r.roles else "?"
    edges = set()
    for d in design.interior_doors:
        if getattr(d, "placeable", True):
            edges.add(frozenset((role.get(d.a, d.a), role.get(d.b, d.b))))
    for g in (design.open_groups or ()):
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                edges.add(frozenset((role.get(g[i], g[i]), role.get(g[j], g[j]))))
    ent = design.entrance_door
    if ent is not None:
        edges.add(frozenset(("OUTSIDE", role.get(ent.b, ent.b))))
    return frozenset(edges)


def structure(design) -> dict:
    """The structural facts the investigation's taxonomy names, read off one realized design."""
    role = {r.zone_id: (r.roles[0] if r.roles else "?") for r in design.rooms}
    nbr: dict[str, set] = {}
    for d in design.interior_doors:
        if getattr(d, "placeable", True):
            nbr.setdefault(d.a, set()).add(d.b)
            nbr.setdefault(d.b, set()).add(d.a)
    for g in (design.open_groups or ()):
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                nbr.setdefault(g[i], set()).add(g[j])
                nbr.setdefault(g[j], set()).add(g[i])
    circ_ids = {z for z, r in role.items() if r in CIRC}
    privates = [z for z, r in role.items() if r in PRIVATE]
    wets = [z for z, r in role.items() if r in WET]
    ent_room = role.get(design.entrance_door.b, "?") if design.entrance_door else "?"
    return {
        "access_graph": sorted("|".join(sorted(e)) for e in access_graph(design)),
        "entrance_room_role": ent_room,
        "circulation_rooms": len(circ_ids),
        "private_off_circulation": sum(1 for z in privates if nbr.get(z, set()) & circ_ids),
        "private_total": len(privates),
        "wet_entered_from": sorted({role.get(n, n) for z in wets for n in nbr.get(z, set())}),
        "open_group_sizes": sorted(len(g) for g in (design.open_groups or ())),
        "public_roles_in_open_group": sorted({role.get(z, z) for g in (design.open_groups or ())
                                              for z in g if role.get(z) in PUBLIC}),
    }


def plan_facts(orr, plan, *, shown: bool) -> dict:
    """One realized plan's identity at every level production already has, plus its access graph."""
    return {
        "outline": orr.outline.order,
        "index": plan.index,
        "gross_area_m2": round(plan.design.gross_area_m2, 2),
        "massing_signature": plan.massing_signature,
        "family_signature": plan.family_signature,
        "layout_signature": str(plan.layout_signature),
        "shown": shown,
        **structure(plan.design),
    }


def run_brief(bid: str) -> dict:
    """The funnel for one brief, measured on the production path's own intermediate results."""
    b = {x.brief_id: x for x in briefs_mod.select_briefs()}[bid]
    project = _project_for(b)
    spec = svc.spec_for(project)
    target = spec.program.target_built_area_m2

    outlines = svc._outlines_for(project)
    results = svc._plan_outlines_until_one_plans(spec, project, outlines, target, None)
    selection = svc._select_plans(results, target, spec.concept)

    pool = [(orr, plan) for orr in results for plan in orr.plans]
    shown_ids = set()
    if selection is not None:
        shown_ids = {(orr.outline.order, plan.index)
                     for orr, plan in [(selection.primary[0], selection.primary[1])] + list(selection.alternatives)} \
            if hasattr(selection, "primary") else set()

    plans = [plan_facts(orr, plan, shown=(orr.outline.order, plan.index) in shown_ids)
             for orr, plan in pool]

    def distinct(key: str, rows) -> int:
        return len({json.dumps(r[key], sort_keys=True) for r in rows})

    shown_rows = [r for r in plans if r["shown"]]
    return {
        "brief": bid,
        "outlines_offered": len(outlines),
        "outlines_that_planned": sum(1 for orr in results if orr.plans),
        "plans_realized_and_validated": len(plans),
        "distinct_massing": distinct("massing_signature", plans),
        "distinct_family": distinct("family_signature", plans),
        "distinct_layout": distinct("layout_signature", plans),
        "distinct_access_graph": distinct("access_graph", plans),
        "shown": len(shown_rows),
        "shown_distinct_massing": distinct("massing_signature", shown_rows) if shown_rows else 0,
        "shown_distinct_family": distinct("family_signature", shown_rows) if shown_rows else 0,
        "shown_distinct_access_graph": distinct("access_graph", shown_rows) if shown_rows else 0,
        "shown_entrance_roles": sorted({r["entrance_room_role"] for r in shown_rows}),
        "plans": plans,
    }


def main(out_path: str) -> dict:
    out = {"note": "stage-by-stage structural diversity through the real production path",
           "briefs": {}}
    print(f"{'brief':5s} {'outl':>4s} {'plans':>5s} | {'massing':>7s} {'family':>6s} {'layout':>6s} {'access':>6s} "
          f"| {'shown':>5s} {'sMass':>5s} {'sFam':>4s} {'sAcc':>4s}")
    for bid in BRIEFS:
        row = run_brief(bid)
        out["briefs"][bid] = row
        print(f"{bid:5s} {row['outlines_that_planned']:>4} {row['plans_realized_and_validated']:>5} | "
              f"{row['distinct_massing']:>7} {row['distinct_family']:>6} {row['distinct_layout']:>6} "
              f"{row['distinct_access_graph']:>6} | {row['shown']:>5} {row['shown_distinct_massing']:>5} "
              f"{row['shown_distinct_family']:>4} {row['shown_distinct_access_graph']:>4}", flush=True)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(out, open(out_path, "w"), indent=1, default=str)
    return out


if __name__ == "__main__":
    main(sys.argv[1])
