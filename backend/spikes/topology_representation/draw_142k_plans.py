"""#142K — draw the plan the production gate selects for each brief of the CORRECTED-prompt dataset."""
import json, os, sys
from app.ai_harness.topology_poc import priors as priors_mod, critic as poc_critic
from app.ai_harness.topology_poc.regen_142k import _candidates
from app.ai_harness.topology_poc import briefs as briefs_mod
from app.vertical_slice.proposal_selection import ProposalSelection, pipeline_input, select_proposal
from draw_selected_plans import draw

def main(path, out_dir):
    d = json.load(open(path)); pri = priors_mod.load_priors()
    for rec in sorted(d["records"], key=lambda r: r["brief_id"]):
        bid = rec["brief_id"]; tps, props, _ = _candidates(rec, pri, 0); b = briefs_mod.Brief(**rec["brief"])
        fp = (b.footprint_width_m, b.footprint_depth_m)
        sel = select_proposal(props, score=lambda p: poc_critic.score_topology(tps[int(p.name.split('#')[1])], pri).total_score, footprint_m=fp)
        if not isinstance(sel, ProposalSelection):
            print(bid, sel.code); continue
        inp = pipeline_input(sel.proposal, sel.verdicts[sel.index].report, fp)
        draw(f"{bid} — corrected prompt, gate-selected proposal #{sel.index} (clean rank {sel.clean_rank}, score {sel.score:.3f})", sel.pipeline, inp,
             os.path.join(out_dir, f"{bid}_142k_plan.png"))
        print(bid, "drawn")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
