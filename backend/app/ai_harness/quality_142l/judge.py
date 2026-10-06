"""#142L step 7 — the INDEPENDENT architectural judge experiment.

An evaluation instrument, never production decision logic (task §7). A judge is shown the brief and two
rendered plans labelled only "Plan A" and "Plan B". It never sees the candidate index, the heuristic
score, any metric value, or which plan production selected — the pair sheets are rendered blind.

Consistency controls, all required before any agreement number is quoted:
  ORDER   every pair is judged twice with A and B swapped; a judge that answers "A" both times is
          position-biased, not architecturally decided.
  REPEAT  a subset is judged twice identically (same order) to measure plain run-to-run stability.
  CONFIG  two judging configurations: `visual` (the drawings alone) and `schedule` (the same drawings
          plus a plain-text room schedule), to see whether the verdict survives a change of framing.
  MODEL   a second model judges the same subset when one is reachable.

Nothing here is treated as ground truth. The report quotes judge agreement only alongside the judge's
own self-consistency, which is its ceiling.

Usage: PYTHONPATH=backend python -m app.ai_harness.quality_142l.judge <comparison.json> <pool.json> <out_dir>
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.ai_harness.quality_142l.render import brief_text, pair_sheet

PRIMARY_MODEL = os.environ.get("JUDGE_MODEL", "gpt-5")
SECOND_MODEL = os.environ.get("JUDGE_MODEL_2", "gpt-5-mini")
N_PAIRS = int(os.environ.get("JUDGE_PAIRS", "30"))
N_SECOND_CONFIG = int(os.environ.get("JUDGE_PAIRS_2", "15"))
N_REPEAT = int(os.environ.get("JUDGE_REPEATS", "10"))

CATEGORIES = ("circulation", "zoning_and_privacy", "entrance", "public_space", "bedrooms",
              "wet_rooms", "daylight_and_exposure", "room_proportion")

SYSTEM = (
    "You are an experienced residential architect reviewing two alternative floor plans for the SAME "
    "brief. Both plans are already known to be legal and buildable: every room meets its area and "
    "dimension requirements, every room is reachable, required adjacencies and doors exist, and "
    "daylight requirements are met. Do NOT re-check legality. Judge only which plan is ARCHITECTURALLY "
    "BETTER as a home to live in.\n"
    "Consider: circulation (is movement efficient, is there wasted or dead corridor); zoning and "
    "privacy (are sleeping and living separated, do you cross the living room to reach a bedroom, are "
    "bedroom or bathroom doors exposed); the entrance (does arrival happen in a sensible transition "
    "space that distributes, or straight into a room, or into a dead pocket); the public space (do "
    "kitchen, dining and living form a usable related whole, is it fragmented or strip-shaped); "
    "bedrooms (size, shape, daylight, quiet); wet rooms (sensible placement for their users, clustered "
    "or scattered); daylight and facade allocation; room proportions.\n"
    "Be decisive when one plan is genuinely better, and say EQUIVALENT when the two are different but "
    "equally good — do not invent a preference. Say CANNOT_DETERMINE only if the drawings do not let "
    "you tell.\n"
    "Street side is marked on each drawing. Reply ONLY with the JSON object described by the user."
)

SCHEMA_HINT = (
    '{"choice": "A" | "B" | "EQUIVALENT" | "CANNOT_DETERMINE", '
    '"confidence": 1-5, '
    '"categories": {' + ", ".join(f'"{c}": {{"better": "A"|"B"|"EQUAL", "why": "one short sentence"}}' for c in CATEGORIES) + '}, '
    '"decisive_reason": "the single most important reason for the overall choice", '
    '"summary": "two sentences"}'
)


def room_schedule(plan: dict) -> str:
    rows = []
    for z, r in sorted(plan["rooms"].items(), key=lambda kv: -kv[1]["net_area_m2"]):
        wins = sum(1 for w in r.get("windows", []) if w.get("placeable"))
        rows.append(f"{z} ({r['role']}): {r['net_area_m2']:.1f} m2, {r['net_w_m']:.1f}x{r['net_h_m']:.1f} m, "
                    f"{wins} window(s)")
    doors = ", ".join(f"{d['a']}-{d['b']}" for d in plan["doors"] if d.get("placeable"))
    return "Rooms: " + "; ".join(rows) + f".\nDoors: {doors}.\nFront door opens into: {plan['entrance_door']['b']}."


def _client():
    import openai
    return openai.OpenAI(timeout=600.0, max_retries=2)


def _b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def ask(client, model: str, image_path: str, brief: str, config: str, schedule_a: str = "", schedule_b: str = "") -> dict:
    user = [{"type": "text", "text":
             f"BRIEF: {brief}\n\nThe image shows two alternative floor plans for this brief: Plan A on the left, "
             f"Plan B on the right.\n"
             + (f"\nPlan A room schedule.\n{schedule_a}\n\nPlan B room schedule.\n{schedule_b}\n" if config == "schedule" else "")
             + f"\nWhich plan is architecturally better? Reply ONLY with this JSON object:\n{SCHEMA_HINT}"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_b64(image_path)}"}}]
    t0 = time.time()
    resp = client.chat.completions.create(
        model=model, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}])
    raw = resp.choices[0].message.content or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"choice": "PARSE_ERROR", "raw": raw[:400]}
    usage = resp.usage.model_dump() if resp.usage else {}
    cost = round(usage.get("prompt_tokens", 0) * 1.25e-6 + usage.get("completion_tokens", 0) * 1e-5, 6)
    return {"model": resp.model or model, "config": config, "verdict": parsed, "usage": usage,
            "cost_usd": cost, "seconds": round(time.time() - t0, 1)}


def select_pairs(comparison: dict, n: int) -> list:
    """Deterministic, representative subset: every brief contributes its most informative pair first
    (most genuinely different concept, then the most contested metric split), then the remaining
    budget goes to the globally most contested pairs. Never chosen by who the heuristic preferred."""
    by_brief: dict[str, list] = {}
    for p in comparison["pairs"]:
        by_brief.setdefault(p["brief"], []).append(p)

    def key(p):
        rank = {"DIFFERENT_CONCEPT": 0, "VARIANT": 1, "MINOR_PERMUTATION": 2}[p["concept"]]
        return (rank, abs(p["metric_wins_a"] - p["metric_wins_b"]), p["a"], p["b"])

    chosen, seen = [], set()
    for bid in sorted(by_brief):
        p = sorted(by_brief[bid], key=key)[0]
        chosen.append(p); seen.add((p["brief"], p["a"], p["b"]))
    rest = sorted((p for p in comparison["pairs"] if (p["brief"], p["a"], p["b"]) not in seen),
                  key=lambda p: (abs(p["metric_wins_a"] - p["metric_wins_b"]), p["brief"], p["a"], p["b"]))
    chosen.extend(rest[: max(0, n - len(chosen))])
    return chosen[:n]


def run(comparison_path: str, pool_path: str, out_dir: str) -> dict:
    comparison = json.load(open(comparison_path))
    pool = json.load(open(pool_path))
    plans = {(b, p["candidate"]): p for b, bb in pool["briefs"].items() for p in bb["plans"]}
    sheets = os.path.join(out_dir, "pair_sheets")
    os.makedirs(sheets, exist_ok=True)
    pairs = select_pairs(comparison, N_PAIRS)
    client = _client()

    jobs = []
    for i, p in enumerate(pairs):
        pa, pb = plans[(p["brief"], p["a"])], plans[(p["brief"], p["b"])]
        fwd = pair_sheet(pa, pb, os.path.join(sheets, f"{p['brief']}_{p['a']}_vs_{p['b']}.png"), blind=True)
        rev = pair_sheet(pb, pa, os.path.join(sheets, f"{p['brief']}_{p['b']}_vs_{p['a']}.png"), blind=True)
        bt = brief_text(pa)
        sa, sb = room_schedule(pa), room_schedule(pb)
        # ORDER control: the same pair forward and reversed, primary model + primary config
        jobs.append(dict(pair=p, order="AB", image=fwd, brief=bt, config="visual", model=PRIMARY_MODEL,
                         sa=sa, sb=sb, run="primary"))
        jobs.append(dict(pair=p, order="BA", image=rev, brief=bt, config="visual", model=PRIMARY_MODEL,
                         sa=sb, sb=sa, run="primary"))
        if i < N_SECOND_CONFIG:         # CONFIG control
            jobs.append(dict(pair=p, order="AB", image=fwd, brief=bt, config="schedule", model=PRIMARY_MODEL,
                             sa=sa, sb=sb, run="config2"))
        if i < N_REPEAT:                # REPEAT control (identical to the primary AB call)
            jobs.append(dict(pair=p, order="AB", image=fwd, brief=bt, config="visual", model=PRIMARY_MODEL,
                             sa=sa, sb=sb, run="repeat"))
        if i < N_SECOND_CONFIG and SECOND_MODEL:   # MODEL control
            jobs.append(dict(pair=p, order="AB", image=fwd, brief=bt, config="visual", model=SECOND_MODEL,
                             sa=sa, sb=sb, run="model2"))

    out = {"system_prompt": SYSTEM, "schema": SCHEMA_HINT, "categories": list(CATEGORIES),
           "primary_model": PRIMARY_MODEL, "second_model": SECOND_MODEL,
           "pairs": [{k: p[k] for k in ("brief", "a", "b", "concept", "metric_wins_a", "metric_wins_b",
                                        "class", "heuristic_pref", "pareto_dimension")} for p in pairs],
           "judgements": []}

    def one(j):
        try:
            r = ask(client, j["model"], j["image"], j["brief"], j["config"], j["sa"], j["sb"])
        except Exception as exc:                       # a model that refuses images, a transport error
            r = {"model": j["model"], "config": j["config"], "verdict": {"choice": "ERROR", "error": f"{type(exc).__name__}: {exc}"[:300]},
                 "usage": {}, "cost_usd": 0.0, "seconds": 0.0}
        return {**r, "brief": j["pair"]["brief"], "a": j["pair"]["a"], "b": j["pair"]["b"],
                "order": j["order"], "run": j["run"]}

    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(one, j) for j in jobs]
        for k, f in enumerate(as_completed(futs), 1):
            r = f.result()
            out["judgements"].append(r)
            if k % 10 == 0 or k == len(jobs):
                print(f"  {k}/{len(jobs)} judged", flush=True)
    out["judgements"].sort(key=lambda r: (r["brief"], r["a"], r["b"], r["run"], r["order"], r["model"]))
    out["total_cost_usd"] = round(sum(r["cost_usd"] for r in out["judgements"]), 4)
    os.makedirs(out_dir, exist_ok=True)
    json.dump(out, open(os.path.join(out_dir, "judgements.json"), "w"), indent=1, default=str)
    errs = sum(1 for r in out["judgements"] if r["verdict"].get("choice") in ("ERROR", "PARSE_ERROR"))
    print(f"{len(out['judgements'])} judgements, {errs} failed, ${out['total_cost_usd']}")
    return out


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2], sys.argv[3])
