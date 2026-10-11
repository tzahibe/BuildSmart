"""#142J — draw the plan the PRODUCTION quality gate selects for every brief of the frozen LLM dataset
(critic -> clean -> score -> select -> unchanged pipeline). Spike code.
Usage: PYTHONPATH=backend:backend/tests/vertical_slice python draw_gate_plans_142j.py <out_dir>"""
import json, os, sys
from app.ai_harness.topology_poc import priors as priors_mod, critic as poc_critic
from app.ai_harness.topology_poc.selection_142j import DATASET, brief_of, candidates_of
from app.vertical_slice.proposal_selection import ProposalSelection, pipeline_input, select_proposal
from draw_selected_plans import draw


def main(out_dir):
    d = json.load(open(DATASET)); pri = priors_mod.load_priors()
    for rec in sorted(d["records"], key=lambda r: r["brief_id"]):
        bid = rec["brief_id"]; tps, props = candidates_of(rec, pri); b = brief_of(rec)
        sel = select_proposal(props, score=lambda p: poc_critic.score_topology(tps[int(p.name.split('#')[1])], pri).total_score,
                              footprint_m=(b.footprint_width_m, b.footprint_depth_m))
        if not isinstance(sel, ProposalSelection):
            print(bid, sel.code); continue
        inp = pipeline_input(sel.proposal, sel.verdicts[sel.index].report, (b.footprint_width_m, b.footprint_depth_m))
        draw(f"{bid} — gate-selected proposal #{sel.index} (clean rank {sel.clean_rank}, score {sel.score:.3f})", sel.pipeline, inp,
             os.path.join(out_dir, f"{bid}_gate_plan.png"))
        print(bid, "drawn")


if __name__ == "__main__":
    main(sys.argv[1])
