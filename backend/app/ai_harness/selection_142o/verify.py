"""#142O verification — run the SHIPPED `proposal_selection.select_proposal` over both #142M
datasets and check it reproduces the measured evidence.

This is deliberately not the budget harness: it calls the production entry point with its production
default and reads only what production returns, so a drift between the measurement and the shipped
behaviour shows up here.

    PYTHONPATH=backend python -m app.ai_harness.selection_142o.verify <budget.json> <out.json>
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time

from app.ai_harness.topology_poc import briefs as briefs_mod
from app.ai_harness.topology_poc import critic as poc_critic
from app.ai_harness.topology_poc import gap_closure_142a as gc
from app.ai_harness.topology_poc import priors as priors_mod
from app.ai_harness.topology_poc import schema
from app.ai_harness.topology_poc.proposal_critic import from_topology_proposal
from app.ai_harness.topology_poc.regen_142k import proposals_of
from app.vertical_slice.proposal_selection import (NoRealizableProposal, NoValidProposal,
                                                   ProposalSelection, select_proposal)

from .budget import DATASETS, _brief_of


def run_brief(record: dict, pri) -> dict:
    bid = record["brief_id"]
    brief = _brief_of(record)
    kinds = briefs_mod.brief_wet_room_kinds(brief)
    fp = (brief.footprint_width_m, brief.footprint_depth_m)
    tps, props = [], []
    for raw in proposals_of(record["attempts"][0]["parsed_json"]):
        try:
            tp = schema.proposal_from_dict(raw)
        except schema.SchemaViolationError:
            continue
        tps.append(tp)
        zones = {rid: gc.room_area_intent(rid, role) for rid, role in tp.role_by_id.items()}
        props.append(from_topology_proposal(f"{bid}#{len(tps) - 1}", tp, zones, kinds))

    t0 = time.perf_counter()
    sel = select_proposal(props, footprint_m=fp,
                          score=lambda p: poc_critic.score_topology(tps[int(p.name.split("#")[1])], pri).total_score)
    dt = time.perf_counter() - t0
    row = {"brief": bid, "candidates": len(props), "seconds": round(dt, 3)}
    if isinstance(sel, ProposalSelection):
        # what the OLD rule would have returned from the same options: best score, ties by index
        old = min(sel.options, key=lambda o: (-o.score, o.index))
        row.update({
            "result": "PASS", "winner": sel.index, "entrance_rank": sel.entrance_rank,
            "alternatives": [o.index for o in sel.alternatives],
            "pass_plans": 1 + len(sel.alternatives),
            "old_rule_winner": old.index, "old_rule_entrance_rank": old.entrance_rank,
            "winner_changed": old.index != sel.index,
            "entrance_improved": sel.entrance_rank < old.entrance_rank,
            "entrance_degraded": sel.entrance_rank > old.entrance_rank,
            "circulation_ratio": round(sel.circulation.ratio, 4),
            "alternative_circulation_ratio": [round(o.circulation.ratio, 4) for o in sel.alternatives],
        })
    else:
        row.update({"result": sel.code, "pass_plans": 0,
                    "winner": None, "alternatives": [], "winner_changed": None})
        assert isinstance(sel, (NoValidProposal, NoRealizableProposal))
    return row


def main(budget_path: str, out_path: str) -> dict:
    pri = priors_mod.load_priors()
    measured = json.load(open(budget_path))
    out = {"note": "the SHIPPED select_proposal at its production default, over both #142M datasets",
           "datasets": {}}
    ok = True
    for name, path in DATASETS.items():
        if not os.path.exists(path):
            continue
        rows = [run_brief(r, pri) for r in sorted(json.load(open(path))["records"],
                                                  key=lambda r: r["brief_id"])]
        passing = [r for r in rows if r["result"] == "PASS"]
        secs = [r["seconds"] for r in rows]
        totals = {
            "briefs": len(rows), "briefs_with_a_pass": len(passing),
            "pass_plans_total": sum(r["pass_plans"] for r in rows),
            "alternatives_total": sum(len(r["alternatives"]) for r in rows),
            "winner_changed": sum(1 for r in passing if r["winner_changed"]),
            "entrance_improved": sum(1 for r in passing if r["entrance_improved"]),
            "entrance_degraded": sum(1 for r in passing if r["entrance_degraded"]),
            "changed_briefs": [r["brief"] for r in passing if r["winner_changed"]],
            "seconds_total": round(sum(secs), 1), "seconds_p50": round(statistics.median(secs), 3),
            "seconds_worst": round(max(secs), 3),
        }
        exp = measured["datasets"][name]["by_budget"]["None"]
        agree = {
            "briefs_with_a_pass": totals["briefs_with_a_pass"] == exp["briefs_with_a_pass"],
            "pass_plans_total": totals["pass_plans_total"] == exp["pass_plans_total"],
            "alternatives_total": totals["alternatives_total"] == exp["alternatives_total"],
            "winner_changed": totals["winner_changed"] == exp["winner_changed"],
            "entrance_improved": totals["entrance_improved"] == exp["entrance_improved"],
            "entrance_degraded": totals["entrance_degraded"] == exp["entrance_degraded"] == 0,
        }
        ok = ok and all(agree.values())
        out["datasets"][name] = {"totals": totals, "measured": exp, "agrees_with_measurement": agree,
                                 "rows": rows}
        print(f"{name}: {json.dumps(totals)}")
        print(f"   agrees with the #142O measurement: {agree}", flush=True)
    out["shipped_matches_measurement"] = ok
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(out, open(out_path, "w"), indent=1, default=str)
    print(f"\nshipped behaviour matches the measurement: {ok}")
    return out


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
