"""#142L step 10 — the PRIVATE-ROOM prompt clarification, measured on a small controlled sample.

#142K's finding: of the 62 proposals the production critic still rejected under the corrected prompt,
57 shared one cause — a bedroom or safe room entered directly from the living room — and its
`UNREACHABLE_ROOM` twin was a consequence of that same illegal door.

Is the rule unambiguously supported by existing policy? Yes, and it is already ENFORCED:
`access_rules.ALLOWED_ENTERED_FROM` maps every role in `PRIVATE_ROLES` (BEDROOM, MASTER_BEDROOM,
SAFE_ROOM, STUDY, DRESSING_ROOM) to `CIRCULATION_ROLES` — hall or circulation, and nothing else.
Validator C24 (`check_access_topology`) and the production proposal critic both fail closed on it. The
prompt simply never told the model a rule the system already applies, so the clarification adds no new
policy; it states one.

The added sentence, verbatim:
    "PRIVATE ROOMS: a bedroom, master bedroom, safe room, study or dressing room is entered ONLY from a
     hall or circulation space — never from the living room, the kitchen, the dining room, or another
     bedroom."

This module regenerates a SMALL deterministic sample of briefs with the amended prompt and compares
the critic findings against #142K's own first batch for exactly those briefs. It is kept separate from
the quality-ranking conclusions, as the task requires.

Usage: PYTHONPATH=backend python -m app.ai_harness.quality_142l.prompt_experiment <out_dir> [n_briefs]
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.ai_harness.topology_poc import briefs as briefs_mod
from app.ai_harness.topology_poc import context as context_mod
from app.ai_harness.topology_poc import critic as poc_critic
from app.ai_harness.topology_poc import gap_closure_142a as gc
from app.ai_harness.topology_poc import priors as priors_mod
from app.ai_harness.topology_poc import prompt as prompt_mod
from app.ai_harness.topology_poc import schema
from app.ai_harness.topology_poc.proposal_critic import from_topology_proposal
from app.ai_harness.topology_poc.regen_142k import N_PROPOSALS, _call, _client, proposals_of
from app.vertical_slice.band_pipeline import PipelineSuccess, run_band_pipeline
from app.vertical_slice.proposal_critic import criticize
from app.vertical_slice.proposal_selection import pipeline_input

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ANALYSIS_142K = os.path.join(os.path.dirname(_BACKEND), "docs", "reports", "142k-corrected-proposer",
                             "data", "analysis_142k.json")
SENTENCE = ("PRIVATE ROOMS: a bedroom, master bedroom, safe room, study or dressing room is entered ONLY "
            "from a hall or circulation space — never from the living room, the kitchen, the dining "
            "room, or another bedroom.")


def worst_briefs(n: int) -> list:
    """The n briefs whose #142K first batch carried the most ILLEGAL_ACCESS_PAIR findings — the
    failure mode this sentence targets. Deterministic, ties by brief id."""
    a = json.load(open(ANALYSIS_142K))
    rows = []
    for b in a["per_brief"]:
        c = sum(1 for r in b["first"]["rows"] for code in r["hard"] if code == "ILLEGAL_ACCESS_PAIR")
        rows.append((-c, b["brief"]))
    return [bid for _c, bid in sorted(rows)[:n]]


def baseline_142k(bids: list) -> dict:
    a = json.load(open(ANALYSIS_142K))
    out = {}
    for b in a["per_brief"]:
        if b["brief"] not in bids:
            continue
        f = b["first"]
        out[b["brief"]] = {
            "candidates": f["candidates"], "clean": f["clean"], "hard_invalid": f["hard_invalid"],
            "clean_pass": len(f["clean_pass"]),
            "hard_codes": dict(Counter(c for r in f["rows"] for c in r["hard"])),
            "illegal_pair_proposals": sum(1 for r in f["rows"] if "ILLEGAL_ACCESS_PAIR" in r["hard"]),
        }
    return out


def run(out_dir: str, n_briefs: int = 6) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    pri = priors_mod.load_priors()
    ctx = context_mod.build_prompt_context(pri)
    all_briefs = {b.brief_id: b for b in briefs_mod.select_briefs()}
    bids = worst_briefs(n_briefs)
    base = baseline_142k(bids)
    client = _client()
    sys_prompt, _ = prompt_mod.build_prompt(ctx, all_briefs[bids[0]], n_proposals=N_PROPOSALS)
    assert SENTENCE.split(" — ")[0] in sys_prompt, "the amended prompt is not in place"

    def one(bid):
        brief = all_briefs[bid]
        sp, up = prompt_mod.build_prompt(ctx, brief, n_proposals=N_PROPOSALS)
        att = _call(client, sp, up)
        raws = proposals_of(att["parsed_json"])
        kinds = briefs_mod.brief_wet_room_kinds(brief)
        fp = (brief.footprint_width_m, brief.footprint_depth_m)
        rows, rejected = [], 0
        for i, raw in enumerate(raws):
            try:
                tp = schema.proposal_from_dict(raw)
            except schema.SchemaViolationError:
                rejected += 1
                continue
            zones = {rid: gc.room_area_intent(rid, role) for rid, role in tp.role_by_id.items()}
            p = from_topology_proposal(f"{bid}#{i}", tp, zones, kinds)
            rep = criticize(p)
            row = {"index": i, "clean": rep.clean, "hard": list(rep.hard_codes),
                   "warn": sorted({f.code for f in rep.findings if f.severity == "WARN"}),
                   "score": round(poc_critic.score_topology(tp, pri).total_score, 4), "production": None}
            if rep.clean:
                res = run_band_pipeline(pipeline_input(p, rep, fp))
                row["production"] = "PASS" if isinstance(res, PipelineSuccess) else res.code
            rows.append(row)
        return bid, {"attempt": {k: att[k] for k in ("model", "parameters", "usage", "cost_usd", "seconds",
                                                     "response_id", "timestamp", "raw_sha256")},
                     "candidates": len(rows), "schema_rejected": rejected,
                     "clean": sum(1 for r in rows if r["clean"]),
                     "hard_invalid": sum(1 for r in rows if not r["clean"]),
                     "clean_pass": sum(1 for r in rows if r["production"] == "PASS"),
                     "hard_codes": dict(Counter(c for r in rows for c in r["hard"])),
                     "illegal_pair_proposals": sum(1 for r in rows if "ILLEGAL_ACCESS_PAIR" in r["hard"]),
                     "rows": rows}

    after = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        for fut in as_completed([ex.submit(one, b) for b in bids]):
            bid, res = fut.result()
            after[bid] = res
            print(f"{bid}: clean {res['clean']}/{res['candidates']} (was {base[bid]['clean']}/{base[bid]['candidates']}) "
                  f"| illegal-pair proposals {res['illegal_pair_proposals']} (was {base[bid]['illegal_pair_proposals']}) "
                  f"| clean&PASS {res['clean_pass']} (was {base[bid]['clean_pass']}) | ${res['attempt']['cost_usd']}", flush=True)

    def agg(d, key):
        return sum(v[key] for v in d.values())
    codes_b, codes_a = Counter(), Counter()
    for v in base.values():
        codes_b.update(v["hard_codes"])
    for v in after.values():
        codes_a.update(v["hard_codes"])
    out = {
        "added_sentence": SENTENCE,
        "policy_basis": "access_rules.ALLOWED_ENTERED_FROM maps every PRIVATE_ROLES role to "
                        "CIRCULATION_ROLES only; validator C24 and the production proposal critic already "
                        "fail closed on it. The sentence states an existing rule, it does not add one.",
        "system_prompt_sha256": hashlib.sha256(sys_prompt.encode()).hexdigest(),
        "briefs": bids, "selection_rule": "the briefs with the most ILLEGAL_ACCESS_PAIR findings in the "
                                          "#142K first batch (deterministic, ties by brief id)",
        "before_142k": base, "after": after,
        "totals": {
            "before": {"candidates": agg(base, "candidates"), "clean": agg(base, "clean"),
                       "clean_pass": agg(base, "clean_pass"),
                       "illegal_pair_proposals": agg(base, "illegal_pair_proposals"),
                       "hard_codes": dict(codes_b)},
            "after": {"candidates": agg(after, "candidates"), "clean": agg(after, "clean"),
                      "clean_pass": agg(after, "clean_pass"),
                      "illegal_pair_proposals": agg(after, "illegal_pair_proposals"),
                      "hard_codes": dict(codes_a),
                      "cost_usd": round(sum(v["attempt"]["cost_usd"] for v in after.values()), 4)},
        },
        "new_failure_modes": sorted(set(codes_a) - set(codes_b)),
    }
    json.dump(out, open(os.path.join(out_dir, "prompt_experiment.json"), "w"), indent=1, default=str)
    print(json.dumps(out["totals"], indent=1))
    print("codes appearing only AFTER the change (new failure modes):", out["new_failure_modes"])
    return out


if __name__ == "__main__":
    run(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 6)
