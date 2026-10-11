"""#142L step 1 — the BASELINE plan pool: every critic-clean candidate of the corrected #142K dataset,
realized through the UNCHANGED production pipeline, with the validator-PASS plans' full realized
geometry preserved for the offline quality evaluator.

Experiment code (harness). Nothing here is wired into production, nothing is regenerated: the proposal
dataset is read from `docs/reports/142k-corrected-proposer/data/generation-dataset-142k.json`, so every
later step compares the SAME candidate pool.

One proposal -> at most one plan: `run_band_pipeline` tries the band layouts of that proposal in its own
order and returns the first that realizes and passes the unchanged validators. That plan is the
proposal's production outcome, and the per-brief set of such plans is the pool #142L has to rank.

Usage (dev venv): PYTHONPATH=backend python -m app.ai_harness.quality_142l.baseline <out.json> [B01,B02,...]
"""
from __future__ import annotations

import json
import os
import sys
import time

from app.ai_harness.topology_poc import briefs as briefs_mod
from app.ai_harness.topology_poc import critic as poc_critic
from app.ai_harness.topology_poc import priors as priors_mod
from app.ai_harness.topology_poc.regen_142k import _candidates
from app.vertical_slice import circulation_metrics as circ_mod
from app.vertical_slice import dead_space as dead_mod
from app.vertical_slice import entrance_sequence as entr_mod
from app.vertical_slice import hub_guard, l_massing_guard, master_suite as suite_mod
from app.vertical_slice import public_composition as pubc_mod
from app.vertical_slice.band_pipeline import PipelineSuccess, run_band_pipeline
from app.vertical_slice.geometry_core.model import Side
from app.vertical_slice.proposal_critic import criticize
from app.vertical_slice.proposal_selection import pipeline_input

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_REPO = os.path.dirname(_BACKEND)
DATASET_142K = os.path.join(_REPO, "docs", "reports", "142k-corrected-proposer", "data", "generation-dataset-142k.json")
U = 0.05            # the engine's grid unit in metres


def _m(v: int) -> float:
    return round(v * U, 3)


def plan_record(res: PipelineSuccess, p, brief: briefs_mod.Brief, score: float, index: int, report) -> dict:
    """Everything the quality evaluator may read, in METRES, from ONE realized+validated plan.
    Only production output is recorded — no derived quality number is computed here."""
    rl = res.realized
    d = rl.design
    fp = rl.site.footprint
    roles = {z: zi.role.value for z, zi in p.zones.items()}
    rooms = {}
    for r in d.rooms:
        rooms[r.zone_id] = {
            "role": roles.get(r.zone_id, r.roles[0] if r.roles else None),
            "rect_m": [round(v, 3) for v in r.rect_m],                 # x, y, w, h — y grows toward the back
            "net_w_m": round(r.net_w_m, 3), "net_h_m": round(r.net_h_m, 3), "net_area_m2": round(r.net_area_m2, 3),
            "walls": {s.value: rl.walls[(r.zone_id, s)].value for s in Side if (r.zone_id, s) in rl.walls},
            "wall_facts": {k: [v.boundary_context.value if hasattr(v.boundary_context, "value") else str(v.boundary_context),
                               v.construction.value if hasattr(v.construction, "value") else str(v.construction)]
                           for k, v in (r.wall_facts or {}).items()} if isinstance(r.wall_facts, dict) else None,
        }
    for w in d.windows:
        rooms.setdefault(w.zone_id, {}).setdefault("windows", []).append(
            {"side": w.side.value if hasattr(w.side, "value") else str(w.side), "width_m": round(w.width_m, 3),
             "placeable": bool(w.placeable)})
    for z in rooms:
        rooms[z].setdefault("windows", [])
    return {
        "brief": brief.brief_id, "candidate": index, "heuristic_score": round(score, 4),
        "brief_facts": {"bedrooms": brief.bedrooms, "wet_rooms": brief.wet_rooms, "safe_room": brief.safe_room,
                        "open_plan": brief.open_plan, "built_area_m2": brief.built_area_m2,
                        "footprint_m": [brief.footprint_width_m, brief.footprint_depth_m],
                        "size_tier": brief.size_tier, "aspect_tier": brief.aspect_tier},
        "footprint_m": [_m(fp.x), _m(fp.y), _m(fp.w), _m(fp.h)],
        "gross_area_m2": round(d.gross_area_m2, 3), "net_area_m2": round(d.net_area_m2, 3),
        "rooms": rooms,
        "doors": [{"a": x.a, "b": x.b, "kind": x.kind, "width_m": round(x.width_m, 3),
                   "center_m": [round(v, 3) for v in x.center_m], "orientation": x.orientation,
                   "placeable": bool(x.placeable), "shared_length_m": round(x.shared_length_m, 3),
                   "swings_into": x.swings_into} for x in d.interior_doors],
        "entrance_door": {"a": d.entrance_door.a, "b": d.entrance_door.b,
                          "center_m": [round(v, 3) for v in d.entrance_door.center_m],
                          "width_m": round(d.entrance_door.width_m, 3)},
        "entrance_walk_m": [round(v, 3) for v in d.entrance_walk_m] if d.entrance_walk_m else None,
        "wet_privacy": [{"zone_id": w.zone_id, "entered_from": w.entered_from,
                         "entered_from_class": w.entered_from_class.value if hasattr(w.entered_from_class, "value") else str(w.entered_from_class),
                         "door_facing": w.door_facing, "direct_sight_line": bool(w.direct_sight_line),
                         "public_exposure_score": w.public_exposure_score,
                         "circulation_obstruction": w.circulation_obstruction,
                         "adjacency_quality": bool(w.adjacency_quality),
                         "privacy_score": w.privacy_score} for w in (d.wet_privacy or ())],
        "wet_core": {"shared_wall_length_m": round(d.wet_core.shared_wall_length_m, 3),
                     "clusters": [list(c) for c in d.wet_core.clusters], "cluster_count": d.wet_core.cluster_count,
                     "kitchen_adjacent_count": d.wet_core.kitchen_adjacent_count,
                     "plumbing_complexity_index": d.wet_core.plumbing_complexity_index} if d.wet_core else None,
        "over_preferred": bool(d.over_preferred),
        "furniture_fits": {f.zone_id: bool(f.fits) for f in rl.furniture} if rl.furniture else {},
        "open_groups": [list(g) for g in (d.open_groups or ())],
        "report_ok": bool(rl.report.ok), "c27_passed": bool(rl.c27.passed),
        "checks_failed": [c.check_id for c in rl.report.checks if not c.passed],
        "checks_total": len(rl.report.checks),
        "access_preserved": res.access_preserved, "spatial_preserved": res.spatial_preserved,
        "band_rows": [[list(c) for c in row] for row in res.placement.rows],
        "n_bands": len(res.placement.rows), "n_cols": res.placement.n_cols,
        "oriented": bool(res.oriented),
        "proposal": {"spatial": sorted(tuple(sorted(e)) for e in p.spatial),
                     "access": [list(e) for e in p.access],
                     "wet_rooms": [[w.zone_id, w.kind.value, w.host_zone] for w in report.wet_rooms]},
        "production_quality": production_quality(rl),
        "soft_flags": {k: v for k, v in res.records[-1].flags.items()
                       if k in ("n_bands", "preferred_on_envelope", "preferred_total", "public_front_share", "bedrooms_bands")},
    }


def production_quality(rl) -> dict:
    """Everything the EXISTING production quality modules already measure on this realized plan.
    #142L measures with production's own definitions wherever one exists (audit finding §3), so a
    metric here is AVAILABLE rather than re-invented. `master_suite` is the one module that needs the
    solver-native geometry instead of the metres DTO, and the one with no production caller at all."""
    d = rl.design
    c = circ_mod.measure(d)
    e = entr_mod.measure(d)
    ds = dead_mod.measure(d)
    pc = pubc_mod.measure(d)
    hp = hub_guard.proportions_of(d)
    lx = l_massing_guard.exposure_of(d)
    try:
        wet = tuple(getattr(rl, "wet_rooms", ()) or ())
        suites = suite_mod.compute_master_suites(rl.fixture, rl.rects, rl.walls, rl.interior_doors, wet)
    except Exception as exc:                       # the realizer carries no ResolvedWetRoom list (known gap)
        suites, suite_err = (), f"{type(exc).__name__}: {exc}"
    else:
        suite_err = None
    return {
        "circulation": {"area_m2": round(c.area_m2, 3), "ratio": round(c.ratio, 4),
                        "longest_segment_m": c.longest_segment_m, "total_length_m": round(c.total_length_m, 3),
                        "narrowest_width_m": c.narrowest_width_m, "dead_end_count": c.dead_end_count,
                        "turn_count": c.turn_count, "duplicated_segment_count": c.duplicated_segment_count,
                        "duplicated_area_m2": round(c.duplicated_area_m2, 3),
                        "extreme": circ_mod.classify_extreme(c)},
        "entrance": {"arrival_zone": e.arrival_zone, "arrival_roles": list(e.arrival_roles),
                     "is_circulation_arrival": bool(e.is_circulation_arrival),
                     "pocket_length_m": (None if e.pocket_length_m == float("inf") else round(e.pocket_length_m, 3)),
                     "has_public_opening": bool(e.has_public_opening),
                     "distance_to_public_m": (None if e.distance_to_public_m is None else round(e.distance_to_public_m, 3)),
                     "private_doors_passed": e.private_doors_passed, "foyer": bool(e.foyer),
                     "stray_pockets": [[z, round(v, 3)] for z, v in e.stray_pockets],
                     "pocket_defect": entr_mod.classify_pocket(e), "tunnel_defect": entr_mod.classify_tunnel(e)},
        "dead_space": {"dead_space_m2": round(ds.dead_space_m2, 3), "dead_space_share": round(ds.dead_space_share, 4),
                       "regions": [{"zone_id": r.zone_id, "kind": r.kind, "area_m2": round(r.area_m2, 3),
                                    "aspect": r.aspect, "accessible": bool(r.accessible),
                                    "length_m": r.length_m} for r in ds.regions],
                       "hard": dead_mod.classify_hard(ds)},
        "public_composition": {"kitchen_dining_related": pc.kitchen_dining_related,
                               "dining_living_related": pc.dining_living_related,
                               "public_zone_coherent": pc.public_zone_coherent,
                               "entrance_reaches_public": pc.entrance_reaches_public,
                               "living_exterior_exposed": pc.living_exterior_exposed,
                               "living_has_window": pc.living_has_window,
                               "blocked_public_rooms": list(pc.blocked_public_rooms),
                               "composition_score": pc.composition_score},
        "proportions": {"area_m2": round(hp.area_m2, 3), "bedroom_max": hp.bedroom_max, "master": hp.master,
                        "safe_room": hp.safe_room, "wet_adjacent": hp.wet_adjacent, "wet_total": hp.wet_total,
                        "wet_share": hp.wet_share,
                        "worst_wet_aspect": lx.worst_wet_aspect, "two_sided_share": lx.two_sided_share},
        "master_suite": {"records": [{"bedroom_zone_id": s.bedroom_zone_id, "ensuite_zone_id": s.ensuite_zone_id,
                                      "ensuite_access": s.ensuite_access.value if hasattr(s.ensuite_access, "value") else str(s.ensuite_access),
                                      "hall_sight_line_to_bed": bool(s.hall_sight_line_to_bed),
                                      "hall_sight_line_to_ensuite_door": bool(s.hall_sight_line_to_ensuite_door),
                                      "ensuite_route_crosses_bed": bool(s.ensuite_route_crosses_bed),
                                      "wardrobe_route_crosses_bed": bool(s.wardrobe_route_crosses_bed),
                                      "suite_score": s.suite_score} for s in suites],
                         "error": suite_err},
    }


def run(out_path: str, only=None) -> dict:
    data = json.load(open(DATASET_142K))
    pri = priors_mod.load_priors()
    out = {"source_dataset": os.path.relpath(DATASET_142K, _REPO),
           "source_sha256": data.get("dataset_sha256"), "model": data.get("model"),
           "note": "every critic-clean candidate of the corrected #142K first batch, realized through the "
                   "unchanged production pipeline; validator-PASS plans carry their full realized geometry",
           "briefs": {}}
    t0 = time.time()
    for rec in sorted(data["records"], key=lambda r: r["brief_id"]):
        bid = rec["brief_id"]
        if only and bid not in only:
            continue
        brief = briefs_mod.Brief(**rec["brief"])
        fp = (brief.footprint_width_m, brief.footprint_depth_m)
        tps, props, rejected = _candidates(rec, pri, 0)
        rows, plans = [], []
        for i, (tp, p) in enumerate(zip(tps, props)):
            report = criticize(p)
            score = poc_critic.score_topology(tp, pri).total_score
            row = {"candidate": i, "clean": report.clean, "hard": list(report.hard_codes), "score": round(score, 4),
                   "realized": False, "passed": False}
            if report.clean:
                res = run_band_pipeline(pipeline_input(p, report, fp))
                if isinstance(res, PipelineSuccess):
                    row["realized"] = row["passed"] = True
                    plans.append(plan_record(res, p, brief, score, i, report))
                else:
                    row["outcome"] = res.code
                    row["realized"] = res.code in ("VALIDATION_FAILED", "SAFE_ROOM_RC_MISSING", "ACCESS_SPATIAL_MISMATCH", "EXPOSURE_INFEASIBLE")
            rows.append(row)
        clean = [r for r in rows if r["clean"]]
        passed = [r for r in rows if r["passed"]]
        heur = sorted(clean, key=lambda r: (-r["score"], r["candidate"]))
        out["briefs"][bid] = {
            "candidates": len(rows), "schema_rejected": len(rejected), "clean": len(clean),
            "realized": sum(1 for r in rows if r["realized"]), "passed": len(passed),
            "pass_candidates": [r["candidate"] for r in passed],
            "heuristic_order_clean": [r["candidate"] for r in heur],
            "heuristic_top_clean": heur[0]["candidate"] if heur else None,
            "heuristic_order_pass": [r["candidate"] for r in sorted(passed, key=lambda r: (-r["score"], r["candidate"]))],
            "rows": rows, "plans": plans}
        b = out["briefs"][bid]
        print(f"{bid}: clean {b['clean']}/{b['candidates']} realized {b['realized']} PASS {b['passed']} "
              f"{b['pass_candidates']} | heuristic top clean #{b['heuristic_top_clean']} "
              f"(PASS order {b['heuristic_order_pass']})", flush=True)
    out["seconds"] = round(time.time() - t0, 1)
    tot = out["briefs"].values()
    out["totals"] = {"candidates": sum(b["candidates"] for b in tot), "clean": sum(b["clean"] for b in tot),
                     "passed": sum(b["passed"] for b in tot),
                     "briefs_with_multiple_pass": sum(1 for b in tot if b["passed"] > 1),
                     "briefs_with_one_pass": sum(1 for b in tot if b["passed"] == 1),
                     "briefs_with_no_pass": sum(1 for b in tot if b["passed"] == 0)}
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(out, open(out_path, "w"), indent=1, default=str)
    print(json.dumps(out["totals"], indent=1))
    return out


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2].split(",") if len(sys.argv) > 2 else None)
