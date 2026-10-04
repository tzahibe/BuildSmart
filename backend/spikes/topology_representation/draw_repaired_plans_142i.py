"""#142I — draw the production plans of the briefs that PASS only after the minimal-repair experiment
(clearly labelled as repaired), with the repairs listed in the title. Harness/spike code.
Usage: PYTHONPATH=backend:backend/tests/vertical_slice python draw_repaired_plans_142i.py <out_dir> B06,B07,B09,B12"""
import json, os, sys
from frozen_briefs import load_fixture, zones_of
from app.ai_harness.topology_poc.critic_142i import _pipeline_input
from app.ai_harness.topology_poc.proposal_critic import from_fixture
from app.ai_harness.topology_poc.proposal_repair import repair
from app.vertical_slice.band_pipeline import PipelineSuccess, run_band_pipeline
from draw_selected_plans import draw


def main(out_dir, briefs):
    fx = load_fixture()["briefs"]
    for bid in briefs:
        brief = fx[bid]
        r = repair(from_fixture(bid, brief, zones_of(brief)))
        inp = _pipeline_input(bid, r.proposal, brief["footprint_m"])
        res = run_band_pipeline(inp)
        if not isinstance(res, PipelineSuccess):
            print(bid, res.code); continue
        out = os.path.join(out_dir, f"{bid}_repaired_plan.png")
        draw(f"{bid} (REPAIRED: " + "; ".join(f"{x.rule}: {x.original} -> {x.changed}" for x in r.repairs)[:150] + ")", res, inp, out)
        print(bid, "drawn", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2].split(","))
