"""#142M — the realized-plan selection experiment: realize EVERY critic-clean candidate, keep the
validator-PASS plans, and rank those with production's own preference chain instead of stopping at the
first candidate the proposal-level heuristic happens to score highest.

Old selection (today's production gate, #142J `proposal_selection.select_proposal`): clean candidates
are ordered by the geometry-free proposal score and the FIRST one that realizes and validates wins.
Equivalently: the highest-scoring clean candidate that passes.

New selection (this experiment): realize all clean candidates inside a deterministic bounded budget,
keep every PASS plan, order them by `selection_142m.ranking` (production's own chain), and keep the
rest as alternatives.

Nothing in production is modified and no new score is introduced. Usage:
  PYTHONPATH=backend python -m app.ai_harness.selection_142m.experiment <out.json> [historical|corrected|both]
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time

from app.ai_harness.quality_142l.compare import concept_label, diversity
from app.ai_harness.quality_142l.metrics import evaluate
from app.ai_harness.selection_142m import ranking
from app.ai_harness.topology_poc import briefs as briefs_mod
from app.ai_harness.topology_poc import critic as poc_critic
from app.ai_harness.topology_poc import gap_closure_142a as gc
from app.ai_harness.topology_poc import priors as priors_mod
from app.ai_harness.topology_poc import schema
from app.ai_harness.topology_poc.proposal_critic import from_topology_proposal
from app.ai_harness.topology_poc.regen_142k import proposals_of
from app.ai_harness.quality_142l.baseline import plan_record
from app.vertical_slice.band_pipeline import PipelineSuccess, run_band_pipeline
from app.vertical_slice.proposal_critic import criticize
from app.vertical_slice.proposal_selection import pipeline_input

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_REPO = os.path.dirname(_BACKEND)
DATASETS = {
    "historical": os.path.join(_REPO, "docs", "reports", "llm-topology-poc", "generation-dataset.json"),
    "corrected": os.path.join(_REPO, "docs", "reports", "142k-corrected-proposer", "data",
                              "generation-dataset-142k.json"),
}
#: Deterministic bounded budget: at most this many critic-clean candidates are realized per brief.
#: The generated batches hold 8-9 proposals, so this bounds nothing today and exists so the cost is
#: stated rather than open-ended.
MAX_REALIZATIONS_PER_BRIEF = 12


def _brief_of(record: dict) -> briefs_mod.Brief:
    b = record["brief"]
    if "source_key" in b and "size_tier" in b:
        return briefs_mod.Brief(**b)
    by_id = {x.brief_id: x for x in briefs_mod.select_briefs()}
    return by_id[record["brief_id"]]


def _candidates(record: dict, pri):
    """(TopologyProposals, critic Proposals) from a record's first attempt, in dataset order."""
    raws = proposals_of(record["attempts"][0]["parsed_json"])
    brief = _brief_of(record)
    kinds = briefs_mod.brief_wet_room_kinds(brief)
    tps, props = [], []
    for raw in raws:
        try:
            tp = schema.proposal_from_dict(raw)
        except schema.SchemaViolationError:
            continue
        zones = {rid: gc.room_area_intent(rid, role) for rid, role in tp.role_by_id.items()}
        tps.append(tp)
        props.append(from_topology_proposal(f"{record['brief_id']}#{len(tps) - 1}", tp, zones, kinds))
    return tps, props


def run_brief(record: dict, pri) -> dict:
    bid = record["brief_id"]
    brief = _brief_of(record)
    fp = (brief.footprint_width_m, brief.footprint_depth_m)
    t_brief = time.perf_counter()
    tps, props = _candidates(record, pri)

    clean, realize_times = [], []
    for i, (tp, p) in enumerate(zip(tps, props)):
        rep = criticize(p)
        if rep.clean:
            clean.append((i, tp, p, rep, poc_critic.score_topology(tp, pri).total_score))

    attempted = clean[:MAX_REALIZATIONS_PER_BRIEF]
    passes, facts, plans, outcomes = [], [], {}, {}
    for i, tp, p, rep, score in attempted:
        t0 = time.perf_counter()
        res = run_band_pipeline(pipeline_input(p, rep, fp))
        dt = time.perf_counter() - t0
        realize_times.append(round(dt, 3))
        if isinstance(res, PipelineSuccess):
            passes.append(i)
            plans[i] = plan_record(res, p, brief, score, i, rep)
            facts.append(ranking.facts_of(res.realized, bid, i, score, brief.built_area_m2,
                                          wet_rooms=rep.wet_rooms))
            outcomes[i] = "PASS"
        else:
            outcomes[i] = res.code

    row = {
        "brief": bid, "candidates": len(tps), "clean": len(clean),
        "realizations_attempted": len(attempted), "pass_plans": len(passes),
        "pass_candidates": passes, "outcomes": outcomes,
        "seconds_total": round(time.perf_counter() - t_brief, 3),
        "seconds_per_realization": realize_times,
    }
    if not facts:
        row.update({"old_winner": None, "new_winner": None, "winner_changed": None,
                    "deciding_term": None, "alternatives": []})
        return row

    # OLD: the gate stops at the first PASS in heuristic order = highest-scoring clean PASS candidate
    old_winner = max(passes, key=lambda i: (dict((c[0], c[4]) for c in clean)[i], -i))
    ordered = ranking.rank(facts)
    new_winner = ordered[0].candidate
    by_cand = {f.candidate: f for f in facts}
    term, xv, yv = ranking.deciding_term(by_cand[new_winner], by_cand[old_winner]) if old_winner != new_winner else ("none", None, None)
    reason = ranking.production_reason(by_cand[new_winner], by_cand[old_winner], term) if old_winner != new_winner else None

    vecs = {i: evaluate(plans[i], pri) for i in passes}
    qdiff = {}
    if old_winner != new_winner:
        a, b = vecs[new_winner], vecs[old_winner]
        qdiff = {k: [b[k], a[k]] for k in a if abs(a[k] - b[k]) > 1e-9}

    alts = []
    for f in ordered[1:]:
        d = diversity(plans[new_winner], plans[f.candidate])
        alts.append({"candidate": f.candidate, "concept": concept_label(d),
                     "contact_jaccard_distance": d["contact_jaccard_distance"],
                     "rooms_changing_band_share": d["rooms_changing_band_share"],
                     "same_arrival_room": d["same_arrival_room"],
                     "deciding_term_vs_winner": ranking.deciding_term(ordered[0], f)[0]})

    cycles = ranking.circulation_cycles(facts)
    row.update({
        "old_winner": old_winner, "new_winner": new_winner, "winner_changed": old_winner != new_winner,
        "deciding_term": term, "deciding_values": {"new": xv, "old": yv},
        "production_reason": reason,
        "new_order": [f.candidate for f in ordered],
        "facts": {f.candidate: {t: f.term(t) for t in ranking.KEY_TERMS} for f in facts},
        "quality_vector_diff_old_to_new": qdiff,
        "alternatives": alts,
        "circulation_cycles": cycles,
        "circulation_disagrees_with_winner": [
            f.candidate for f in ordered[1:]
            if ranking.circulation_prefers_pair(ordered[0], f) is None],
    })
    return row


def run_dataset(name: str, path: str, pri) -> dict:
    data = json.load(open(path))
    rows = []
    for rec in sorted(data["records"], key=lambda r: r["brief_id"]):
        row = run_brief(rec, pri)
        rows.append(row)
        print(f"{name} {row['brief']}: clean {row['clean']}/{row['candidates']} realized "
              f"{row['realizations_attempted']} PASS {row['pass_plans']} | old #{row['old_winner']} -> "
              f"new #{row['new_winner']}"
              f"{' CHANGED by ' + str(row['deciding_term']) if row.get('winner_changed') else ' (same)'}"
              f" | {row['seconds_total']}s", flush=True)
    per = [t for r in rows for t in r["seconds_per_realization"]]
    brief_t = [r["seconds_total"] for r in rows]
    changed = [r for r in rows if r.get("winner_changed")]
    alts = [a for r in rows for a in r.get("alternatives", [])]
    return {
        "dataset": name, "path": os.path.relpath(path, _REPO), "briefs": len(rows),
        "totals": {
            "candidates": sum(r["candidates"] for r in rows), "clean": sum(r["clean"] for r in rows),
            "realizations_attempted": sum(r["realizations_attempted"] for r in rows),
            "pass_plans": sum(r["pass_plans"] for r in rows),
            "briefs_with_a_pass": sum(1 for r in rows if r["pass_plans"] > 0),
            "briefs_with_multiple_pass": sum(1 for r in rows if r["pass_plans"] > 1),
            "winner_changed": len(changed),
            "deciding_terms": {t: sum(1 for r in changed if r["deciding_term"] == t)
                               for t in sorted({r["deciding_term"] for r in changed})},
            "circulation_cycles_found": sum(len(r.get("circulation_cycles", [])) for r in rows),
            "alternatives": {k: sum(1 for a in alts if a["concept"] == k)
                             for k in ("DIFFERENT_CONCEPT", "VARIANT", "MINOR_PERMUTATION")},
        },
        "runtime": {
            "per_realization_s": {"n": len(per), "p50": round(statistics.median(per), 3) if per else None,
                                  "p95": round(sorted(per)[int(0.95 * (len(per) - 1))], 3) if per else None,
                                  "worst": round(max(per), 3) if per else None,
                                  "total": round(sum(per), 1) if per else 0.0},
            "per_brief_s": {"p50": round(statistics.median(brief_t), 3),
                            "p95": round(sorted(brief_t)[int(0.95 * (len(brief_t) - 1))], 3),
                            "worst": round(max(brief_t), 3), "total": round(sum(brief_t), 1)},
        },
        "rows": rows,
    }


def main(out_path: str, which: str = "both") -> dict:
    pri = priors_mod.load_priors()
    out = {"terms": [{"term": t, "source": s, "direction": d} for t, s, d in ranking.TERMS],
           "key_terms": list(ranking.KEY_TERMS),
           "budget": {"max_realizations_per_brief": MAX_REALIZATIONS_PER_BRIEF},
           "datasets": {}}
    for name, path in DATASETS.items():
        if which not in ("both", name) or not os.path.exists(path):
            continue
        out["datasets"][name] = run_dataset(name, path, pri)
        print(json.dumps(out["datasets"][name]["totals"], indent=1), flush=True)
        print(json.dumps(out["datasets"][name]["runtime"], indent=1), flush=True)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(out, open(out_path, "w"), indent=1, default=str)
    return out


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "both")
