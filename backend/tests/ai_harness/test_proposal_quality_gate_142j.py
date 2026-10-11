"""Issue #142J — the production proposal quality gate on the frozen LLM dataset (162 proposals, 20 briefs).

critic -> clean -> score -> select -> unchanged pipeline must pick an already-existing critic-clean
proposal that reaches validator PASS for at least 19 of the 20 briefs; B12 (no clean candidate) must
fail honestly with NO_VALID_PROPOSAL; a HARD-invalid candidate is never selected; the briefs once
classified as needing an L-shaped room (B02 B03 B10 B14 B15 B16) and the non-planar B19 pass because a
DIFFERENT valid proposal is chosen, with the geometry untouched; selection is deterministic across
processes and PYTHONHASHSEED values.

Issue #142O changed WHICH clean passing proposal wins: the gate now realizes every clean candidate
inside the same budget and orders the PASS plans by arrival rank, then the existing score, then the
candidate index. The gate's own guarantees are unchanged and still asserted here — only the
"top-scored clean candidate always wins" expectation is replaced by the rule that actually holds,
and the two briefs whose winner moves (`ENTRANCE_IMPROVED`) must move strictly toward a hall arrival.
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
#: Issue #142O: the only briefs whose winner moves, and in both the front door moves from the living
#: room (arrival rank 1) to a hall (rank 0). Measured, and asserted below to improve and never regress.
ENTRANCE_IMPROVED = {"B05", "B08"}


@pytest.fixture(scope="module")
def matrix():
    d = json.load(open(DATASET))
    pri = priors_mod.load_priors()
    return {rec["brief_id"]: run_brief(rec, pri) for rec in sorted(d["records"], key=lambda r: r["brief_id"])}


def test_at_least_19_of_20_briefs_select_an_existing_clean_passing_proposal(matrix):
    passed = sorted(b for b, r in matrix.items() if r["new_result"] == "PASS")
    assert len(passed) >= 19, passed
    assert OLD_PASSES <= set(passed)


def test_every_pass_plan_reached_inside_the_budget_is_kept_as_an_alternative(matrix):
    """Issue #142O: the gate no longer returns at the first PASS, so a brief with more than one
    clean passing candidate must offer the others instead of discarding them."""
    for bid, r in matrix.items():
        if r["new_result"] != "PASS":
            continue
        kept = {r["new_rank"]} | {a["rank"] for a in r["alternatives"]}
        assert kept == set(r["clean_pass_ranks"]), (bid, sorted(kept), r["clean_pass_ranks"])


def test_the_winner_never_arrives_worse_than_the_candidate_the_old_rule_would_have_picked(matrix):
    """The whole justification for the change: ordering by arrival rank first may only improve the
    front door, never worsen it, against the top-scored clean candidate the old gate returned."""
    for bid, r in matrix.items():
        if r["new_result"] != "PASS":
            continue
        old_rule = min([{"rank": r["new_rank"], "score": r["new_score"],
                         "entrance_rank": r["new_entrance_rank"]}] + r["alternatives"],
                       key=lambda o: (-o["score"], o["rank"]))
        assert r["new_entrance_rank"] <= old_rule["entrance_rank"], (bid, r["new_entrance_rank"], old_rule)


def test_selected_candidates_are_critic_clean_and_hard_invalid_ones_never_win(matrix):
    for bid, r in matrix.items():
        if r["new_result"] != "PASS":
            continue
        chosen = next(v for v in r["verdicts"] if v["rank"] == r["new_rank"])
        assert chosen["clean"] and chosen["hard"] == (), (bid, chosen)
        # Issue #142O's rule, against the real options: the winner is the minimum of
        # (arrival rank, -score, index) over every PASS plan, so no alternative may beat it and an
        # invalid candidate with a higher score still never wins.
        # `alternatives` reports the score rounded, so round both sides: an exact score tie must
        # fall through to the candidate index, which is the stable identity the rule ends on.
        winner_key = (r["new_entrance_rank"], -round(chosen["score"], 4), chosen["rank"])
        for alt in r["alternatives"]:
            assert winner_key < (alt["entrance_rank"], -alt["score"], alt["rank"]), (bid, chosen, alt)
        # and among the plans sharing the winner's arrival rank it is still the best-scored one
        best_rank_scores = [(-alt["score"], alt["rank"]) for alt in r["alternatives"]
                            if alt["entrance_rank"] == r["new_entrance_rank"]]
        assert all((-round(chosen["score"], 4), chosen["rank"]) < k for k in best_rank_scores), (bid, chosen)
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
        if bid in ENTRANCE_IMPROVED:
            # Issue #142O: the winner moved, and it moved for the one reason that is allowed to move
            # it — a strictly better arrival. The displaced plan is kept as an alternative.
            assert r["new_rank"] != r["old"]["rank"], (bid, r["old"]["rank"], r["new_rank"])
            assert r["new_entrance_rank"] == 0, (bid, r["new_entrance_rank"])
            assert any(a["entrance_rank"] > 0 for a in r["alternatives"]), (bid, r["alternatives"])
            continue
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
