"""Issue #142J — the production proposal quality gate on the frozen LLM dataset (162 proposals, 20 briefs).

critic -> clean -> score -> select -> unchanged pipeline must pick an already-existing critic-clean
proposal that reaches validator PASS for at least 19 of the 20 briefs; B12 (no clean candidate) must
fail honestly with NO_VALID_PROPOSAL; a HARD-invalid candidate is never selected; the briefs once
classified as needing an L-shaped room (B02 B03 B10 B14 B15 B16) and the non-planar B19 pass because a
DIFFERENT valid proposal is chosen, with the geometry untouched; selection is deterministic across
processes and PYTHONHASHSEED values.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from app.ai_harness.topology_poc import priors as priors_mod
from app.ai_harness.topology_poc.selection_142j import DATASET, run_brief
from app.vertical_slice.proposal_selection import NoValidProposal

pytestmark = pytest.mark.skipif(not os.path.exists(DATASET), reason="frozen LLM dataset not present")

FORMER_LIMIT = ("B02", "B03", "B10", "B14", "B15", "B16")
OLD_PASSES = {"B01", "B04", "B05", "B08", "B11", "B13", "B18"}


@pytest.fixture(scope="module")
def matrix():
    d = json.load(open(DATASET))
    pri = priors_mod.load_priors()
    return {rec["brief_id"]: run_brief(rec, pri) for rec in sorted(d["records"], key=lambda r: r["brief_id"])}


def test_at_least_19_of_20_briefs_select_an_existing_clean_passing_proposal(matrix):
    passed = sorted(b for b, r in matrix.items() if r["new_result"] == "PASS")
    assert len(passed) >= 19, passed
    assert OLD_PASSES <= set(passed)


def test_selected_candidates_are_critic_clean_and_hard_invalid_ones_never_win(matrix):
    for bid, r in matrix.items():
        if r["new_result"] != "PASS":
            continue
        chosen = next(v for v in r["verdicts"] if v["rank"] == r["new_rank"])
        assert chosen["clean"] and chosen["hard"] == (), (bid, chosen)
        # the chosen one is the BEST-SCORED clean candidate (score order, ties by index), never an invalid one with a higher score
        clean_scores = [(v["score"], -v["rank"]) for v in r["verdicts"] if v["clean"]]
        assert (chosen["score"], -chosen["rank"]) == max(clean_scores), (bid, chosen, clean_scores)
        assert r["tried_before"] == [] or all(c != "PASS" for _, c in r["tried_before"])


def test_b12_is_the_honest_negative_control(matrix):
    r = matrix["B12"]
    assert r["critic_clean"] == 0 and r["new_result"] == "NO_VALID_PROPOSAL"
    assert all(v["hard"] for v in r["verdicts"])                  # every candidate carries its findings
    assert "EXPOSURE_INFEASIBLE" in r["detail"] or "ACCESS" in r["detail"] or "WET_ROOM" in r["detail"]


@pytest.mark.parametrize("bid", FORMER_LIMIT + ("B19",))
def test_former_representation_limit_briefs_pass_by_choosing_another_proposal(matrix, bid):
    r = matrix[bid]
    assert r["old"]["result"] in ("TOPOLOGY_REPRESENTATION_LIMIT", "TOPOLOGY_NON_PLANAR"), r["old"]
    assert r["new_result"] == "PASS" and r["new_rank"] != r["old"]["rank"], (bid, r["old"], r.get("new_rank"))
    assert r["access"].split("/")[0] == r["access"].split("/")[1]   # every declared door realized


def test_old_passes_keep_their_proposal_and_nothing_new_is_bizarre(matrix):
    for bid in OLD_PASSES:
        r = matrix[bid]
        assert r["new_rank"] == r["old"]["rank"], (bid, r["old"]["rank"], r["new_rank"])
    for bid, r in matrix.items():
        if r["new_result"] == "PASS":
            q = r["quality"]
            assert q["circulation_share"] <= 0.24 + 1e-9, (bid, q)       # C26's own bound, read back off the plan
            assert q["mean_net_aspect"] <= 2.2, (bid, q)                  # rooms stay room-shaped on average (C3 bounds each one)
            assert q["bands"] <= 4 and q["doors"] >= q["rooms"] - 1, (bid, q)


_DET_SCRIPT = r"""
import json, sys
from app.ai_harness.topology_poc import priors as priors_mod
from app.ai_harness.topology_poc.selection_142j import DATASET, candidates_of, brief_of
from app.ai_harness.topology_poc import critic as poc_critic
from app.vertical_slice.proposal_selection import select_proposal, ProposalSelection
d = json.load(open(DATASET)); pri = priors_mod.load_priors()
out = {}
for rec in d["records"]:
    if rec["brief_id"] not in sys.argv[1].split(","):
        continue
    tps, props = candidates_of(rec, pri); b = brief_of(rec)
    sel = select_proposal(props, score=lambda p: poc_critic.score_topology(tps[int(p.name.split('#')[1])], pri).total_score,
                          footprint_m=(b.footprint_width_m, b.footprint_depth_m))
    out[rec["brief_id"]] = ([sel.index, sel.clean_rank, {k: (r.x, r.y, r.w, r.h) for k, r in sorted(sel.pipeline.realized.rects.items())}]
                            if isinstance(sel, ProposalSelection) else sel.code)
print(json.dumps(out, sort_keys=True))
"""


def test_selection_is_deterministic_across_processes_and_hash_seeds():
    env = {**os.environ, "PYTHONPATH": os.getcwd()}
    outs = []
    for seed in ("1", "2", "random"):
        env["PYTHONHASHSEED"] = seed
        res = subprocess.run([sys.executable, "-c", _DET_SCRIPT, "B02,B19,B12"], capture_output=True, text=True, env=env, timeout=600)
        assert res.returncode == 0, res.stderr[-2000:]
        outs.append(res.stdout.strip().splitlines()[-1])
    assert outs[0] == outs[1] == outs[2]
    parsed = json.loads(outs[0])
    assert parsed["B12"] == "NO_VALID_PROPOSAL" and isinstance(parsed["B02"], list) and isinstance(parsed["B19"], list)
