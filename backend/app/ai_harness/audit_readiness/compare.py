"""Product Readiness Audit — the product path vs the #142 path, on the same eight briefs.

PRODUCT PATH (what a user actually gets today):
    Project -> demo.service.generate_demo_design -> general_pipeline.run_general
            -> DemoDesign (the contract `DemoPlan` renders)

#142 PATH (validated, merged, and reachable from no product endpoint):
    brief proposals -> proposal_selection.select_proposal -> band_pipeline
                    -> RealizedLayout -> demo.contract.to_demo_design -> DemoDesign

Both are reduced to the SAME `DemoDesign` contract, so every comparison below is like-for-like and
the conversion itself answers "what would be required to feed a #142 plan into the product renderer".

Evidence only. Nothing here is wired into production and no production file is modified.

    PYTHONPATH=backend python -m app.ai_harness.audit_readiness.compare <out.json>
"""
from __future__ import annotations

import json
import os
import sys
import time

from app.ai_harness.topology_poc import briefs as briefs_mod
from app.ai_harness.topology_poc import critic as poc_critic
from app.ai_harness.topology_poc import gap_closure_142a as gc
from app.ai_harness.topology_poc import priors as priors_mod
from app.ai_harness.topology_poc import schema
from app.ai_harness.topology_poc.proposal_critic import from_topology_proposal
from app.ai_harness.topology_poc.regen_142k import proposals_of
from app.demo import service as svc
from app.demo.contract import to_demo_design
from app.vertical_slice import arrival_policy, circulation_metrics, dead_space, entrance_sequence
from app.vertical_slice.proposal_selection import ProposalSelection, select_proposal

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_REPO = os.path.dirname(_BACKEND)
DATASET = os.path.join(_REPO, "docs", "reports", "142k-corrected-proposer", "data",
                       "generation-dataset-142k.json")

#: The eight audited briefs and why each was chosen (report §1).
BRIEFS = {
    "B08": "smallest house (132 m2, 11x12), 3 bed, open plan, most retained alternatives",
    "B20": "small + SAFE_ROOM + wet-heavy (3 wet in 132 m2); #142O changed its winner",
    "B02": "simplest programme (1 bed/1 wet) in a narrow 12x18 envelope; #142O changed its winner",
    "B11": "dense programme (4 bed/2 wet) + SAFE_ROOM in the same narrow envelope",
    "B16": "WIDE envelope (18x12), 5 bed/3 wet + SAFE_ROOM",
    "B19": "most bedrooms (6) in a medium square envelope; historically the non-planar brief",
    "B06": "long narrow deep envelope (13x24), NOT open plan",
    "B09": "largest house (440 m2, 20x22), 3 bed/3 wet, NOT open plan",
}

PRIVATE_ROLES = frozenset({"BEDROOM", "MASTER_BEDROOM", "STUDY", "DRESSING_ROOM", "SAFE_ROOM"})
WET_ROLES = frozenset({"BATHROOM", "TOILET"})
CIRC_ROLES = frozenset({"HALL", "CIRCULATION"})
PUBLIC_ROLES = frozenset({"LIVING", "KITCHEN", "DINING", "FAMILY_ROOM"})


def _project_for(b):
    from tests.vertical_slice.test_hub_guard import _project
    return _project(dict(bedrooms=b.bedrooms, wet_rooms=b.wet_rooms, safe_room=b.safe_room,
                         open_plan=b.open_plan, built_area_m2=b.built_area_m2,
                         footprint_width_m=b.footprint_width_m, footprint_depth_m=b.footprint_depth_m,
                         plot_width_m=b.footprint_width_m + 8, plot_depth_m=b.footprint_depth_m + 8))


def measure_design(design, brief, *, source: str, seconds: float, extra=None) -> dict:
    """Every quantity the audit records, read off the realized `design_output.GeometricDesign`
    with production's own measurement modules. Nothing is re-invented."""
    rooms = list(design.rooms)
    roles = {r.zone_id: (r.roles[0] if r.roles else "") for r in rooms}
    circ = circulation_metrics.measure(design)
    seq = entrance_sequence.measure(design)
    ds = dead_space.measure(design)

    nbrs: dict[str, set] = {}
    for d in design.interior_doors:
        if getattr(d, "placeable", True):
            nbrs.setdefault(d.a, set()).add(d.b)
            nbrs.setdefault(d.b, set()).add(d.a)
    for g in (design.open_groups or ()):
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                nbrs.setdefault(g[i], set()).add(g[j])
                nbrs.setdefault(g[j], set()).add(g[i])
    circ_ids = {z for z, r in roles.items() if r in CIRC_ROLES}
    privates = [z for z, r in roles.items() if r in PRIVATE_ROLES]
    wets = [z for z, r in roles.items() if r in WET_ROLES]
    priv_not_circ = [z for z in privates if not (nbrs.get(z, set()) & circ_ids)]
    wet_entered = {z: sorted(roles.get(n, n) for n in nbrs.get(z, set())) for z in wets}

    windows = [w for w in design.windows if getattr(w, "placeable", False)]
    windowed = {w.zone_id for w in windows}
    fp_area = None
    aspects = [round(max(r.net_w_m, r.net_h_m) / max(0.01, min(r.net_w_m, r.net_h_m)), 2) for r in rooms]
    out = {
        "source": source, "seconds": round(seconds, 3),
        "validator_ok": bool(design is not None),
        "rooms": len(rooms),
        "roles": sorted(roles.values()),
        "bedrooms": sum(1 for r in roles.values() if r in ("BEDROOM", "MASTER_BEDROOM")),
        "wet_rooms": len(wets), "safe_room": any(r == "SAFE_ROOM" for r in roles.values()),
        "gross_area_m2": round(design.gross_area_m2, 2), "net_area_m2": round(design.net_area_m2, 2),
        "target_area_m2": brief.built_area_m2,
        "area_fidelity_pct": round(100 * design.gross_area_m2 / brief.built_area_m2, 1),
        "worst_room_aspect": max(aspects) if aspects else None,
        "rooms_over_aspect_2_2": sum(1 for a in aspects if a > 2.2),
        "doors": len(design.interior_doors),
        "open_group_joins": sum(len(g) * (len(g) - 1) // 2 for g in (design.open_groups or ())),
        "entrance_room_role": roles.get(design.entrance_door.b, "?"),
        "arrival_rank": arrival_policy.arrival_rank(design),
        "distance_to_public_m": seq.distance_to_public_m,
        "private_doors_passed": seq.private_doors_passed,
        "circulation_ratio": round(circ.ratio, 4),
        "circulation_area_m2": circ.area_m2,
        "circulation_dead_ends": circ.dead_end_count,
        "circulation_longest_m": circ.longest_segment_m,
        "circulation_extreme": circulation_metrics.classify_extreme(circ),
        "private_rooms": len(privates),
        "private_not_off_circulation": len(priv_not_circ),
        "private_not_off_circulation_ids": sorted(priv_not_circ),
        "wet_entered_from": wet_entered,
        "wet_off_public_only": sum(1 for z, ns in wet_entered.items()
                                   if ns and not (set(ns) & CIRC_ROLES)),
        "windows_placed": len(windows),
        "rooms_without_a_window": sorted(z for z, r in roles.items()
                                         if z not in windowed and r not in CIRC_ROLES),
        "dead_space_m2": round(ds.dead_space_m2, 2),
        "dead_space_share": round(ds.dead_space_share, 4),
        "dead_space_hard": dead_space.classify_hard(ds),
    }
    if extra:
        out.update(extra)
    return out


def visual_completeness(dd: dict) -> dict:
    """What the product renderer would actually have to draw, from a DemoDesign dict."""
    doors = dd["doors"]
    return {
        "demo_rooms": len(dd["rooms"]), "demo_walls": len(dd["walls"]), "demo_doors": len(doors),
        "doors_with_swing_deg": sum(1 for d in doors if d.get("swing_deg") is not None),
        "doors_with_hinge": sum(1 for d in doors if d.get("hinge_x") is not None),
        "demo_windows": len(dd["windows"]), "demo_layout_objects": len(dd["layout"]),
        "demo_open_interfaces": len(dd["open_interfaces"]),
        "demo_garden": len(dd["garden"]), "demo_parking": len(dd["parking"]),
        "has_outline": bool(dd["outline"]), "has_family": bool(dd["family"]),
        "has_concept": bool(dd["concept"]), "has_plot": bool(dd["plot"]),
    }


def run_brief(bid: str, pri) -> dict:
    b = {x.brief_id: x for x in briefs_mod.select_briefs()}[bid]
    row = {"brief": bid, "why_chosen": BRIEFS[bid],
           "brief_facts": {"bedrooms": b.bedrooms, "wet_rooms": b.wet_rooms, "safe_room": b.safe_room,
                           "open_plan": b.open_plan, "built_area_m2": b.built_area_m2,
                           "footprint_m": [b.footprint_width_m, b.footprint_depth_m]}}

    # ---- PRODUCT PATH: the product contract (what DemoPlan renders) AND the realized design
    # underneath it (so both paths are measured by the SAME production modules).
    t0 = time.perf_counter()
    try:
        project = _project_for(b)
        res = svc.generate_demo_design(project)
        dt = time.perf_counter() - t0
        dd = res.design.model_dump()
        gs = svc._plan(svc.spec_for(project), project)
        prod = {"ok": True, "seconds": round(dt, 3), "alternatives": len(res.alternatives),
                "visual": visual_completeness(dd), "demo_design": dd,
                "validation_ok": bool(getattr(gs, "ok", False)),
                "failed_checks": sorted({c.check_id for c in gs.validation.checks if not c.passed})
                                 if getattr(gs, "validation", None) else []}
        if getattr(gs, "design", None) is not None:
            prod["winner_measure"] = measure_design(gs.design, b, source="product-winner", seconds=dt)
        alts = list(getattr(gs, "alternatives", ()) or ())
        if alts:
            alt = alts[0]
            ad = getattr(alt, "design", alt)
            prod["alt_measure"] = measure_design(ad, b, source="product-alt", seconds=0.0)
            try:
                prod["alt_demo_design"] = to_demo_design(ad, gs.validation).model_dump()
                prod["alt_visual"] = visual_completeness(prod["alt_demo_design"])
            except Exception as exc:
                prod["alt_demo_design_error"] = f"{type(exc).__name__}: {exc}"
        row["product"] = prod
    except Exception as exc:
        import traceback
        row["product"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                          "trace": traceback.format_exc()[-800:]}

    # ---- #142 PATH
    rec = next((r for r in json.load(open(DATASET))["records"] if r["brief_id"] == bid), None)
    brief = briefs_mod.Brief(**rec["brief"])
    kinds = briefs_mod.brief_wet_room_kinds(brief)
    tps, props = [], []
    for raw in proposals_of(rec["attempts"][0]["parsed_json"]):
        try:
            tp = schema.proposal_from_dict(raw)
        except schema.SchemaViolationError:
            continue
        tps.append(tp)
        zones = {rid: gc.room_area_intent(rid, rr) for rid, rr in tp.role_by_id.items()}
        props.append(from_topology_proposal(f"{bid}#{len(tps) - 1}", tp, zones, kinds))
    t0 = time.perf_counter()
    sel = select_proposal(props, footprint_m=(brief.footprint_width_m, brief.footprint_depth_m),
                          score=lambda p: poc_critic.score_topology(tps[int(p.name.split("#")[1])], pri).total_score)
    dt = time.perf_counter() - t0
    if isinstance(sel, ProposalSelection):
        winner_dd = to_demo_design(sel.pipeline.realized.design, sel.pipeline.realized.report).model_dump()
        row["v142"] = {
            "ok": True, "seconds": round(dt, 3), "winner_candidate": sel.index,
            "entrance_rank": sel.entrance_rank, "alternatives": len(sel.alternatives),
            "winner_measure": measure_design(sel.pipeline.realized.design, brief, source="142-winner",
                                             seconds=dt),
            "winner_visual": visual_completeness(winner_dd),
            "winner_demo_design": winner_dd,
        }
        if sel.alternatives:
            alt = sel.alternatives[0]
            alt_dd = to_demo_design(alt.pipeline.realized.design, alt.pipeline.realized.report).model_dump()
            row["v142"]["alt_candidate"] = alt.index
            row["v142"]["alt_measure"] = measure_design(alt.pipeline.realized.design, brief,
                                                        source="142-alt", seconds=0.0)
            row["v142"]["alt_visual"] = visual_completeness(alt_dd)
            row["v142"]["alt_demo_design"] = alt_dd
    else:
        row["v142"] = {"ok": False, "code": sel.code, "seconds": round(dt, 3)}
    return row


def main(out_path: str) -> dict:
    pri = priors_mod.load_priors()
    out = {"note": "Product Readiness Audit evidence: the real product path vs the #142 path on the "
                   "same eight briefs, both reduced to the DemoDesign contract the product renders.",
           "briefs": BRIEFS, "rows": []}
    for bid in BRIEFS:
        row = run_brief(bid, pri)
        out["rows"].append(row)
        p, v = row.get("product", {}), row.get("v142", {})
        print(f"{bid}: product ok={p.get('ok')} {p.get('seconds')}s alts={p.get('alternatives')} | "
              f"#142 ok={v.get('ok')} {v.get('seconds')}s alts={v.get('alternatives')} "
              f"rank={v.get('entrance_rank')}", flush=True)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(out, open(out_path, "w"), indent=1, default=str)
    return out


if __name__ == "__main__":
    main(sys.argv[1])
