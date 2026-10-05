"""#142I — run the proposal critic (detection) and the separate repair experiment over the frozen suite
and the whole LLM dataset; write the measurement JSON the report cites.

Usage (dev venv): PYTHONPATH=backend:backend/tests/vertical_slice python -m app.ai_harness.topology_poc.critic_142i <out_dir>
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
from dataclasses import asdict

from app.ai_harness.topology_poc import gap_closure_142a as gc
from app.ai_harness.topology_poc import priors as priors_mod
from app.ai_harness.topology_poc import schema
from app.ai_harness.topology_poc.proposal_critic import Proposal, criticize, from_fixture, from_topology_proposal, infer_wet_rooms
from app.ai_harness.topology_poc.proposal_repair import repair
from app.vertical_slice.band_pipeline import PipelineInput, PipelineSuccess, run_band_pipeline
from app.vertical_slice.geometry_core.model import ProgramRole

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
FIXTURE = os.path.join(_BACKEND, "tests", "fixtures", "frozen_briefs_142.json")
DATASET = os.path.join(os.path.dirname(_BACKEND), "docs", "reports", "llm-topology-poc", "generation-dataset.json")


def _zones(brief: dict):
    from app.vertical_slice.rectilinear_realizer import ZoneIntent
    return {z: ZoneIntent(z, ProgramRole(v["role"]), v["target"], v["min"], v["max"], v["min_short"], v["max_aspect"])
            for z, v in brief["zones"].items()}


def _pipeline_input(name: str, p: Proposal, footprint) -> PipelineInput:
    wet = infer_wet_rooms(p)
    return PipelineInput(name, p.zones, tuple(tuple(sorted(e)) for e in sorted(p.spatial, key=sorted)),
                         tuple(footprint), tuple(wet),
                         tuple((a, b) for a, b in p.access if a != "ENTRANCE"))


def _outcome(res) -> dict:
    if isinstance(res, PipelineSuccess):
        return {"result": "PASS", "candidate": res.candidate_index, "access": res.access_preserved, "spatial": res.spatial_preserved,
                "selection": res.selection}
    return {"result": res.code, "stage": res.stage, "detail": res.detail[:240], "selection": res.selection}


def frozen_suite(out: dict) -> None:
    fx = json.load(open(FIXTURE))["briefs"]
    rows = []
    for bid in sorted(fx):
        brief = fx[bid]
        p = from_fixture(bid, brief, _zones(brief))
        rep = criticize(p)
        before = _outcome(run_band_pipeline(_pipeline_input(bid, p, brief["footprint_m"])))
        row = {"brief": bid, "expected_embedding": brief["expected_embedding"], "critic_hard": rep.hard_codes, "critic_all": rep.codes,
               "findings": [asdict(f) for f in rep.findings], "critic_seconds": rep.seconds, "production_before": before}
        if rep.hard and brief["expected_embedding"] == "BAND_REPRESENTABLE":
            r = repair(p)
            after = _outcome(run_band_pipeline(_pipeline_input(bid, r.proposal, brief["footprint_m"])))
            row["repairs"] = [asdict(x) for x in r.repairs]
            row["unrepaired"] = r.unrepaired
            row["critic_after_hard"] = r.after.hard_codes
            row["production_after_repair"] = after
        rows.append(row)
        print(bid, "critic:", rep.hard_codes, "| before:", before["result"],
              ("| repairs: %d | after: %s" % (len(row.get("repairs", [])), row.get("production_after_repair", {}).get("result"))) if "repairs" in row else "", flush=True)
    out["frozen"] = rows


def dataset(out: dict) -> None:
    d = json.load(open(DATASET))
    pri = priors_mod.load_priors()
    per_code = Counter(); n = 0; clean = 0; by_brief = {}
    for rec in d["records"]:
        bid = rec["brief_id"]
        scored = gc._scored_proposals(rec, pri)
        best = gc.best_policy_valid_proposal(rec, pri)
        fp = (rec["brief"]["footprint_width_m"], rec["brief"]["footprint_depth_m"])
        rows = []
        for rank, (score, tp) in enumerate(scored):
            zones = {rid: gc.room_area_intent(rid, role) for rid, role in tp.role_by_id.items()}
            p = from_topology_proposal(f"{bid}#{rank}", tp, zones)
            rep = criticize(p, embed_max_candidates=60)
            n += 1
            for c in rep.hard_codes:
                per_code[c] += 1
            is_frozen = (tp.spatial_adjacency, tp.access_graph) == (best.spatial_adjacency, best.access_graph)
            row = {"rank": rank, "score": round(score, 4), "policy_valid_by_access_rules": gc.is_access_policy_valid(tp),
                   "frozen_choice": is_frozen, "critic_hard": rep.hard_codes, "critic_all": rep.codes}
            if not rep.hard:
                clean += 1
                row["production"] = _outcome(run_band_pipeline(_pipeline_input(p.name, p, fp)))
            rows.append(row)
        by_brief[bid] = rows
        print(bid, "proposals", len(rows), "critic-clean", sum(1 for r in rows if not r["critic_hard"]),
              "clean&PASS", sum(1 for r in rows if r.get("production", {}).get("result") == "PASS"), flush=True)
    out["dataset"] = {"proposals": n, "critic_clean": clean, "hard_findings_per_code": dict(per_code), "by_brief": by_brief}


def main(out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    out: dict = {}
    t = time.time(); frozen_suite(out); out["frozen_seconds"] = round(time.time() - t, 1)
    json.dump(out, open(os.path.join(out_dir, "critic_frozen.json"), "w"), indent=1, default=str)
    t = time.time(); dataset(out); out["dataset_seconds"] = round(time.time() - t, 1)
    json.dump(out, open(os.path.join(out_dir, "critic_results.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main(sys.argv[1])
