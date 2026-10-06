"""#142J — the production proposal quality gate run over the frozen LLM dataset (162 proposals, 20
briefs): critic -> clean -> score -> select -> unchanged pipeline, versus the old flow (score -> first
access-rules-valid -> pipeline, the #142A/#142E frozen selection). Writes the 20-brief matrix and the
quality comparison the report cites.

Usage (dev venv): PYTHONPATH=backend python -m app.ai_harness.topology_poc.selection_142j <out_dir> [B01,B02,...]
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict

from app.ai_harness.topology_poc import briefs as briefs_mod
from app.ai_harness.topology_poc import critic as poc_critic
from app.ai_harness.topology_poc import gap_closure_142a as gc
from app.ai_harness.topology_poc import priors as priors_mod
from app.ai_harness.topology_poc import schema
from app.ai_harness.topology_poc.proposal_critic import from_topology_proposal
from app.vertical_slice.band_pipeline import PipelineInput, PipelineSuccess, placement_flags, run_band_pipeline
from app.vertical_slice.geometry_core.engine import net_rect_m
from app.vertical_slice.geometry_core.model import ProgramRole
from app.vertical_slice.proposal_critic import Proposal
from app.vertical_slice.proposal_selection import NoValidProposal, ProposalSelection, select_proposal

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATASET = os.path.join(os.path.dirname(_BACKEND), "docs", "reports", "llm-topology-poc", "generation-dataset.json")


def brief_of(record: dict) -> briefs_mod.Brief:
    return briefs_mod.Brief(**record["brief"])


def candidates_of(record: dict, pri) -> tuple[list, list]:
    """(TopologyProposals in the OLD score order, Proposals for the critic) — the same candidate set the
    frozen selection saw (`gap_closure_142a._scored_proposals`), so ranks are comparable."""
    scored = gc._scored_proposals(record, pri)
    brief = brief_of(record)
    kinds = briefs_mod.brief_wet_room_kinds(brief)
    tps, props = [], []
    for rank, (_score, tp) in enumerate(scored):
        zones = {rid: gc.room_area_intent(rid, role) for rid, role in tp.role_by_id.items()}
        tps.append(tp)
        props.append(from_topology_proposal(f"{record['brief_id']}#{rank}", tp, zones, kinds))
    return tps, props


def quality(res: PipelineSuccess, p: Proposal) -> dict:
    """Existing metrics only (task §12): the realized plan's circulation share, net aspects, exposure
    of PREFERRED rooms, band count, door count, validator warnings — nothing new is invented."""
    rl = res.realized
    total = sum(r.w * r.h for r in rl.rects.values())
    circ = sum(r.w * r.h for z, r in rl.rects.items() if p.roles[z] in (ProgramRole.HALL, ProgramRole.CIRCULATION))
    aspects = []
    for z, r in rl.rects.items():
        nw, nh, _ = net_rect_m(z, r, rl.walls)
        aspects.append(max(nw, nh) / max(min(nw, nh), 1e-6))
    fl = res.records[-1].flags
    return {"circulation_share": round(circ / total, 3), "mean_net_aspect": round(sum(aspects) / len(aspects), 2),
            "max_net_aspect": round(max(aspects), 2), "bands": len(res.placement.rows),
            "preferred_exposure": f"{fl.get('preferred_on_envelope')}/{fl.get('preferred_total')}",
            "public_front_share": fl.get("public_front_share"), "doors": sum(1 for d in rl.interior_doors if d.placeable),
            "rooms": len(rl.rects), "footprint_m": [round(sum(res.placement.rows and [0]) or 0, 2)]}


def run_brief(record: dict, pri) -> dict:
    bid = record["brief_id"]
    brief = brief_of(record)
    fp = (brief.footprint_width_m, brief.footprint_depth_m)
    tps, props = candidates_of(record, pri)
    # ---- OLD flow: best-scored access-rules-valid proposal, harness wet-room inference, pipeline
    old_tp = gc.best_policy_valid_proposal(record, pri)
    old_rank = next(i for i, tp in enumerate(tps) if (tp.spatial_adjacency, tp.access_graph) == (old_tp.spatial_adjacency, old_tp.access_graph))
    old_p = props[old_rank]
    old_inp = PipelineInput(bid, old_p.zones, tuple(sorted(tuple(sorted(e)) for e in old_p.spatial)), fp,
                            gc.resolve_wet_rooms(old_tp), tuple((a, b) for a, b in old_tp.access_graph if a != "ENTRANCE"))
    old_res = run_band_pipeline(old_inp)
    old = {"rank": old_rank, "result": "PASS" if isinstance(old_res, PipelineSuccess) else old_res.code,
           "score": round(poc_critic.score_topology(old_tp, pri).total_score, 4)}
    if isinstance(old_res, PipelineSuccess):
        old["quality"] = quality(old_res, old_p)
    # ---- NEW flow: critic -> clean -> score -> select -> pipeline
    t = time.perf_counter()
    sel = select_proposal(props, score=lambda p: poc_critic.score_topology(tps[int(p.name.split('#')[1])], pri).total_score, footprint_m=fp)
    dt = time.perf_counter() - t
    verdicts = [{"rank": v.index, "clean": v.eligible, "hard": v.report.hard_codes, "warn": tuple(sorted({f.code for f in v.report.findings if f.severity == "WARN"})),
                 "score": v.score, "wet_rooms": [(w.zone_id, w.kind.value, w.host_zone, w.specified) for w in v.report.wet_rooms]}
                for v in sel.verdicts]
    row = {"brief": bid, "generated": len(props), "hard_invalid": sum(1 for v in verdicts if not v["clean"]),
           "critic_clean": sum(1 for v in verdicts if v["clean"]), "old": old, "new_code": sel.code if not isinstance(sel, ProposalSelection) else "PASS",
           "seconds": round(dt, 2), "verdicts": verdicts}
    if isinstance(sel, ProposalSelection):
        row.update({"new_rank": sel.index, "new_clean_rank": sel.clean_rank, "new_score": round(sel.score, 4),
                    "tried_before": sel.tried, "new_result": "PASS", "access": sel.pipeline.access_preserved,
                    "spatial": sel.pipeline.spatial_preserved, "quality": quality(sel.pipeline, props[sel.index]),
                    "new_wet_rooms": [(w.zone_id, w.kind.value, w.host_zone, w.specified) for w in sel.verdicts[sel.index].report.wet_rooms],
                    # Issue #142O: every PASS plan reached inside the budget, so a test can check the
                    # selection rule (arrival rank, then score, then index) against the real options.
                    "new_entrance_rank": sel.entrance_rank,
                    "alternatives": [{"rank": o.index, "clean_rank": o.clean_rank,
                                      "score": round(o.score, 4), "entrance_rank": o.entrance_rank}
                                     for o in sel.alternatives]})
    elif isinstance(sel, NoValidProposal):
        row.update({"new_result": sel.code, "detail": sel.detail})
    else:
        row.update({"new_result": sel.code, "detail": sel.detail, "tried": [(i, d.code) for i, d in sel.tried]})
    # clean candidates that pass production (for the matrix): every clean one, independently
    passing = []
    for v in sel.verdicts:
        if v.eligible:
            from app.vertical_slice.proposal_selection import pipeline_input
            r = run_band_pipeline(pipeline_input(props[v.index], v.report, fp))
            if isinstance(r, PipelineSuccess):
                passing.append(v.index)
    row["clean_pass_ranks"] = passing
    return row


def main(out_dir: str, only=None) -> list:
    os.makedirs(out_dir, exist_ok=True)
    d = json.load(open(DATASET))
    pri = priors_mod.load_priors()
    rows = []
    for rec in sorted(d["records"], key=lambda r: r["brief_id"]):
        if only and rec["brief_id"] not in only:
            continue
        row = run_brief(rec, pri)
        rows.append(row)
        print(f"{row['brief']}: gen {row['generated']} hard {row['hard_invalid']} clean {row['critic_clean']} clean&PASS {row['clean_pass_ranks']} "
              f"| old rank {row['old']['rank']} -> {row['old']['result']} | new rank {row.get('new_rank')} -> {row['new_result']} "
              f"(tried {row.get('tried_before', row.get('tried'))}) {row['seconds']}s", flush=True)
    json.dump(rows, open(os.path.join(out_dir, "selection_matrix.json"), "w"), indent=1, default=str)
    n_pass = sum(1 for r in rows if r["new_result"] == "PASS")
    print(f"NEW PASS {n_pass}/{len(rows)} | OLD PASS {sum(1 for r in rows if r['old']['result'] == 'PASS')}/{len(rows)}")
    return rows


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2].split(",") if len(sys.argv) > 2 else None)
