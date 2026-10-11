"""#142K — regenerate the 20 frozen briefs with the CORRECTED proposer prompt (gpt-5, the production
generation settings of the #151 primary run), analyse proposal quality BEFORE selection with the
production critic, and prototype ONE bounded critic-informed regeneration for briefs whose first batch
has no critic-clean proposal. Research driver (harness); nothing here is wired into production.

    generate <dataset.json>            one gpt-5 batch per brief (8 proposals), resumable, same record
                                       schema as the frozen #151 dataset (+ prompt hash), cost recorded
    retry    <dataset.json>            for briefs with NO critic-clean proposal in batch 0: summarise the
                                       critic findings (text only, no geometry), ask for a fresh batch
                                       once, store it as attempt 1 — never more than one retry
    analyze  <dataset.json> <out_dir>  per-candidate critic/score/production records, per-brief metrics,
                                       old-vs-new comparison (old = selection_matrix of #142J), HARD
                                       finding frequencies, selected-plan quality, scoring observations

Credentials: OPENAI_API_KEY from the environment (the app's own backend/.env). Pricing constants below
reproduce the #151 dataset's recorded cost (2606 in + 9962 out tokens = $0.102877).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timezone

from app.ai_harness.topology_poc import briefs as briefs_mod
from app.ai_harness.topology_poc import context as context_mod
from app.ai_harness.topology_poc import critic as poc_critic
from app.ai_harness.topology_poc import gap_closure_142a as gc
from app.ai_harness.topology_poc import priors as priors_mod
from app.ai_harness.topology_poc import prompt as prompt_mod
from app.ai_harness.topology_poc import schema
from app.ai_harness.topology_poc.generation_dataset import _canonical_sha256
from app.ai_harness.topology_poc.proposal_critic import from_topology_proposal
from app.ai_harness.topology_poc.selection_142j import quality
from app.vertical_slice.band_pipeline import PipelineSuccess, run_band_pipeline
from app.vertical_slice.proposal_critic import criticize
from app.vertical_slice.proposal_selection import NoValidProposal, ProposalSelection, pipeline_input, select_proposal

MODEL = os.environ.get("TOPOLOGY_142K_MODEL", "gpt-5")
N_PROPOSALS = 8
PRICE_IN_PER_M = 1.25        # USD per 1M input tokens (gpt-5, as recorded in the #151 dataset)
PRICE_OUT_PER_M = 10.0       # USD per 1M output tokens
_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
OLD_MATRIX = os.path.join(os.path.dirname(_BACKEND), "docs", "reports", "142j-proposal-quality-gate", "data", "selection_matrix.json")


# ----------------------------------------------------------------------------- generation

def _client():
    import openai
    return openai.OpenAI(timeout=900.0, max_retries=2)


def _call(client, system_prompt: str, user_prompt: str) -> dict:
    """One chat-completions call in the #151 primary-run shape: json_object response format,
    temperature 1.0 (omitted if the model rejects it, and the parameters recorded say so)."""
    t0 = time.time()
    params = {"temperature": 1.0, "response_format": "json_object"}
    kwargs = dict(model=MODEL, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                  response_format={"type": "json_object"})
    try:
        resp = client.chat.completions.create(temperature=1.0, **kwargs)
    except Exception as exc:  # noqa: BLE001 — a temperature rejection is the only thing we retry without it
        if "temperature" not in str(exc):
            raise
        params = {"temperature": "model default (parameter rejected)", "response_format": "json_object"}
        resp = client.chat.completions.create(**kwargs)
    raw = resp.choices[0].message.content or ""
    usage = resp.usage.model_dump() if resp.usage is not None else {}
    cost = round(usage.get("prompt_tokens", 0) * PRICE_IN_PER_M / 1e6 + usage.get("completion_tokens", 0) * PRICE_OUT_PER_M / 1e6, 6)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {}
    return {"model": resp.model or MODEL, "parameters": params, "raw_response": raw,
            "raw_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(), "parsed_json": parsed, "usage": usage,
            "cost_usd": cost, "seconds": round(time.time() - t0, 1), "response_id": resp.id,
            "timestamp": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")}


def proposals_of(parsed) -> list:
    """The array of raw proposal dicts, whether the model returned the array itself or wrapped it in
    an object (json_object mode makes gpt-5 wrap it as {"proposals": [...]}, as in the #151 run)."""
    if isinstance(parsed, list):
        return [x for x in parsed if isinstance(x, dict)]
    if isinstance(parsed, dict):
        for key in ("proposals", "items", "data"):
            if isinstance(parsed.get(key), list):
                return [x for x in parsed[key] if isinstance(x, dict)]
        vals = [v for v in parsed.values() if isinstance(v, list)]
        if len(vals) == 1:
            return [x for x in vals[0] if isinstance(x, dict)]
    return []


def _brief_dict(b: briefs_mod.Brief) -> dict:
    return asdict(b)


def _load(path: str) -> dict:
    return json.load(open(path)) if os.path.exists(path) else None


def _save(path: str, data: dict) -> None:
    data = {k: v for k, v in data.items() if k != "dataset_sha256"}
    data["total_cost_usd"] = round(sum(a["cost_usd"] for r in data["records"] for a in r["attempts"]), 4)
    data["dataset_sha256"] = _canonical_sha256(data)
    tmp = path + ".tmp"
    json.dump(data, open(tmp, "w"), indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def generate(path: str, workers: int = 4) -> None:
    pri = priors_mod.load_priors()
    ctx = context_mod.build_prompt_context(pri)
    all_briefs = briefs_mod.select_briefs()
    system_prompt, _ = prompt_mod.build_prompt(ctx, all_briefs[0], n_proposals=N_PROPOSALS)
    data = _load(path) or {
        "experiment": "#142K — corrected proposer prompt (door needs wall, one door per wet room, kinds + hosts from the brief), first batch",
        "generated_by": "this worker, OPENAI_API_KEY from backend/.env (owner task #142K)", "model": MODEL, "n_briefs": 20,
        "n_proposals_requested_per_brief": N_PROPOSALS, "prompt_sha256": hashlib.sha256(system_prompt.encode()).hexdigest(),
        "prompt_module": "app.ai_harness.topology_poc.prompt (#142J)", "parameters": {"temperature": 1.0, "response_format": "json_object"},
        "generated_at": None, "total_cost_usd": 0.0, "records": []}
    done = {r["brief_id"] for r in data["records"]}
    todo = [b for b in all_briefs if b.brief_id not in done]
    client = _client()

    def one(b):
        sp, up = prompt_mod.build_prompt(ctx, b, n_proposals=N_PROPOSALS)
        att = _call(client, sp, up)
        att["attempt"] = 0
        return {"brief_id": b.brief_id, "brief": _brief_dict(b), "system_prompt": sp, "user_prompt": up,
                "n_proposals_requested": N_PROPOSALS, "retry_count": 0, "attempts": [att]}

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(one, b): b for b in todo}
        for fut in as_completed(futs):
            rec = fut.result()
            data["records"].append(rec)
            data["records"].sort(key=lambda r: r["brief_id"])
            data["generated_at"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
            _save(path, data)
            a = rec["attempts"][0]
            print(f"{rec['brief_id']}: {len(proposals_of(a['parsed_json']))} proposals, {a['usage'].get('completion_tokens')} out tokens, "
                  f"${a['cost_usd']}, {a['seconds']}s", flush=True)
    print("total cost $", _load(path)["total_cost_usd"])


# ----------------------------------------------------------------------------- critic / selection on a record

def _candidates(record: dict, pri, attempt_index: int):
    """(TopologyProposals, Proposals, schema-rejected count) for one attempt of a record."""
    raws = proposals_of(record["attempts"][attempt_index]["parsed_json"])
    brief = briefs_mod.Brief(**record["brief"])
    kinds = briefs_mod.brief_wet_room_kinds(brief)
    tps, props, rejected = [], [], []
    for i, raw in enumerate(raws):
        try:
            tp = schema.proposal_from_dict(raw)
        except schema.SchemaViolationError as exc:
            rejected.append((i, str(exc)[:200])); continue
        zones = {rid: gc.room_area_intent(rid, role) for rid, role in tp.role_by_id.items()}
        tps.append(tp); props.append(from_topology_proposal(f"{record['brief_id']}@{attempt_index}#{len(tps) - 1}", tp, zones, kinds))
    return tps, props, rejected


def _assess(record: dict, pri, attempt_index: int) -> dict:
    """Critic + score + production for every candidate of one attempt (the §2 metrics), plus the
    production gate's own selection (critic -> clean -> score -> select -> pipeline)."""
    brief = briefs_mod.Brief(**record["brief"])
    fp = (brief.footprint_width_m, brief.footprint_depth_m)
    tps, props, rejected = _candidates(record, pri, attempt_index)
    rows = []
    for i, (tp, p) in enumerate(zip(tps, props)):
        rep = criticize(p)
        row = {"index": i, "clean": rep.clean, "hard": rep.hard_codes, "warn": tuple(sorted({f.code for f in rep.findings if f.severity == "WARN"})),
               "findings": [{"code": f.code, "severity": f.severity, "subjects": list(f.subjects), "detail": f.detail} for f in rep.findings],
               "score": round(poc_critic.score_topology(tp, pri).total_score, 4), "production": None,
               "wet_rooms": [(w.zone_id, w.kind.value, w.host_zone, w.specified) for w in rep.wet_rooms]}
        if rep.clean:
            res = run_band_pipeline(pipeline_input(p, rep, fp))
            if isinstance(res, PipelineSuccess):
                row["production"] = {"result": "PASS", "access": res.access_preserved, "spatial": res.spatial_preserved,
                                     "candidate": res.candidate_index, "quality": quality(res, p)}
            else:
                row["production"] = {"result": res.code, "stage": res.stage, "detail": res.detail[:200]}
        rows.append(row)
    tp_by_name = {p.name: tp for tp, p in zip(tps, props)}          # names carry the RAW index; tps skips schema-rejected ones
    sel = select_proposal(props, score=lambda p: poc_critic.score_topology(tp_by_name[p.name], pri).total_score, footprint_m=fp) if props else None
    clean = [r for r in rows if r["clean"]]
    out = {"attempt": attempt_index, "generated": len(proposals_of(record["attempts"][attempt_index]["parsed_json"])),
           "schema_rejected": rejected, "candidates": len(rows), "clean": len(clean), "hard_invalid": len(rows) - len(clean),
           "clean_rate": round(len(clean) / len(rows), 3) if rows else None,
           "clean_pass": [r["index"] for r in clean if r["production"] and r["production"]["result"] == "PASS"],
           "first_clean_index": clean[0]["index"] if clean else None, "rows": rows}
    if sel is None:
        out["gate"] = {"result": "NO_CANDIDATES"}
    elif isinstance(sel, ProposalSelection):
        out["gate"] = {"result": "PASS", "index": sel.index, "clean_rank": sel.clean_rank, "score": round(sel.score, 4), "tried_before": sel.tried,
                       "access": sel.pipeline.access_preserved, "spatial": sel.pipeline.spatial_preserved, "quality": quality(sel.pipeline, props[sel.index])}
    else:
        out["gate"] = {"result": sel.code, "detail": sel.detail, **({"tried": [(i, d.code) for i, d in sel.tried]} if hasattr(sel, "tried") else {})}
    return out


# ----------------------------------------------------------------------------- bounded critic-informed retry

def feedback_text(assessment: dict) -> str:
    """Deterministic summary of the critic's HARD findings on the rejected batch — findings only,
    no geometry, no edits: the model must produce a fresh batch."""
    lines = []
    for r in assessment["rows"]:
        hard = [f for f in r["findings"] if f["severity"] == "HARD"]
        if hard:
            lines.append(f"- proposal #{r['index'] + 1}: " + " | ".join(f"{f['code']}: {f['detail']}" for f in hard[:6]))
    for i, why in assessment["schema_rejected"]:
        lines.append(f"- proposal #{i + 1}: SCHEMA_REJECTED: {why}")
    codes = Counter(c for r in assessment["rows"] for c in r["hard"])
    summary = ", ".join(f"{c} x{n}" for c, n in codes.most_common())
    return ("YOUR PREVIOUS BATCH WAS REJECTED. Every proposal violated at least one hard rule of the brief. "
            f"Findings per proposal (summary: {summary}):\n" + "\n".join(lines) +
            "\n\nGenerate a COMPLETELY NEW batch of proposals that violates none of these rules. Do not reuse the rejected "
            "proposals; design fresh topologies. Remember: a direct door requires a shared wall listed in spatial_adjacency; "
            "every wet room has exactly one door from the entrant its kind allows; every room must be reachable from "
            "ENTRANCE through legal doors; required wall contacts must be realizable by rectangular rooms.")


def retry(path: str, workers: int = 4) -> None:
    data = _load(path)
    pri = priors_mod.load_priors()
    client = _client()
    todo = []
    for rec in data["records"]:
        if len(rec["attempts"]) > 1:
            continue
        a0 = _assess(rec, pri, 0)
        if a0["clean"] == 0:
            todo.append((rec, a0))
    print("briefs with no clean proposal in batch 0:", [r["brief_id"] for r, _ in todo], flush=True)

    def one(rec, a0):
        fb = feedback_text(a0)
        att = _call(client, rec["system_prompt"], rec["user_prompt"] + "\n\n" + fb)
        att["attempt"] = 1
        att["retry_feedback"] = fb
        return rec["brief_id"], att

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for fut in as_completed([ex.submit(one, rec, a0) for rec, a0 in todo]):
            bid, att = fut.result()
            rec = next(r for r in data["records"] if r["brief_id"] == bid)
            rec["attempts"].append(att); rec["retry_count"] = 1
            _save(path, data)
            print(f"{bid}: retry batch {len(proposals_of(att['parsed_json']))} proposals, ${att['cost_usd']}, {att['seconds']}s", flush=True)


# ----------------------------------------------------------------------------- analysis

def analyze(path: str, out_dir: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    data = _load(path)
    pri = priors_mod.load_priors()
    old = {r["brief"]: r for r in json.load(open(OLD_MATRIX))} if os.path.exists(OLD_MATRIX) else {}
    per_brief = []
    for rec in sorted(data["records"], key=lambda r: r["brief_id"]):
        bid = rec["brief_id"]
        a0 = _assess(rec, pri, 0)
        row = {"brief": bid, "first": a0, "retry": None, "cost_usd": sum(a["cost_usd"] for a in rec["attempts"]),
               "seconds": sum(a["seconds"] for a in rec["attempts"]), "model": rec["attempts"][0]["model"], "parameters": rec["attempts"][0]["parameters"]}
        if len(rec["attempts"]) > 1:
            row["retry"] = _assess(rec, pri, 1)
        o = old.get(bid)
        if o:
            row["old"] = {"generated": o["generated"], "clean": o["critic_clean"], "hard_invalid": o["hard_invalid"], "clean_pass": o["clean_pass_ranks"],
                          "gate": o["new_result"], "gate_rank": o.get("new_rank"), "quality": o.get("quality"), "hard_codes": Counter(c for v in o["verdicts"] for c in v["hard"])}
        per_brief.append(row)
        g = row["first"]["gate"]
        print(f"{bid}: gen {a0['generated']} rej {len(a0['schema_rejected'])} clean {a0['clean']}/{a0['candidates']} clean&PASS {a0['clean_pass']} "
              f"first-clean #{a0['first_clean_index']} | gate {g['result']}{' #' + str(g.get('index')) if g.get('index') is not None else ''}"
              + (f" | retry: clean {row['retry']['clean']} gate {row['retry']['gate']['result']}" if row["retry"] else ""), flush=True)
    summary = {
        "model": data["model"], "prompt_sha256": data.get("prompt_sha256"), "parameters": data.get("parameters"), "total_cost_usd": data["total_cost_usd"],
        "new_first_batch": {
            "proposals": sum(r["first"]["candidates"] for r in per_brief), "schema_rejected": sum(len(r["first"]["schema_rejected"]) for r in per_brief),
            "clean": sum(r["first"]["clean"] for r in per_brief), "hard_invalid": sum(r["first"]["hard_invalid"] for r in per_brief),
            "clean_pass": sum(len(r["first"]["clean_pass"]) for r in per_brief),
            "briefs_with_clean": sum(1 for r in per_brief if r["first"]["clean"]), "briefs_with_clean_pass": sum(1 for r in per_brief if r["first"]["clean_pass"]),
            "briefs_gate_pass": sum(1 for r in per_brief if r["first"]["gate"]["result"] == "PASS"),
            "hard_codes": dict(Counter(c for r in per_brief for x in r["first"]["rows"] for c in x["hard"])),
            "warn_codes": dict(Counter(c for r in per_brief for x in r["first"]["rows"] for c in x["warn"]))},
        "old": {"proposals": sum(o["generated"] for o in old.values()), "clean": sum(o["critic_clean"] for o in old.values()),
                "hard_invalid": sum(o["hard_invalid"] for o in old.values()), "clean_pass": sum(len(o["clean_pass_ranks"]) for o in old.values()),
                "briefs_with_clean": sum(1 for o in old.values() if o["critic_clean"]), "briefs_with_clean_pass": sum(1 for o in old.values() if o["clean_pass_ranks"]),
                "briefs_gate_pass": sum(1 for o in old.values() if o["new_result"] == "PASS"),
                "hard_codes": dict(Counter(c for o in old.values() for v in o["verdicts"] for c in v["hard"]))} if old else None,
        "after_retry": {"briefs_retried": [r["brief"] for r in per_brief if r["retry"]],
                        "briefs_gate_pass": sum(1 for r in per_brief if r["first"]["gate"]["result"] == "PASS" or (r["retry"] and r["retry"]["gate"]["result"] == "PASS")),
                        "retry_clean": {r["brief"]: r["retry"]["clean"] for r in per_brief if r["retry"]},
                        "retry_gate": {r["brief"]: r["retry"]["gate"]["result"] for r in per_brief if r["retry"]}},
    }
    json.dump({"summary": summary, "per_brief": per_brief}, open(os.path.join(out_dir, "analysis_142k.json"), "w"), indent=1, default=str)
    print(json.dumps(summary, indent=1, default=str))
    return summary


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "generate":
        generate(sys.argv[2])
    elif cmd == "retry":
        retry(sys.argv[2])
    elif cmd == "analyze":
        analyze(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit(__doc__)
