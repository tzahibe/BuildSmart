"""A/B of one planner mechanism through the real service, over the 418 failure-log scenarios.

    .venv/bin/python3 spikes/failure_log_sweep/ab.py --toggle twins   # unforced-twin fallback
    .venv/bin/python3 spikes/failure_log_sweep/ab.py --toggle hub     # HUB_PRIVATE_WING parti

OFF disables the mechanism by filtering the generator's candidate list; ON is the shipped code.
Gates reported: pre-existing primary designs byte-identical; LOST == 0; gains only at >= 80 % of the
requested area; latency per scenario. Writes `gained.json` beside this file.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.demo import service as svc  # noqa: E402
from app.vertical_slice import concept_generator as cg  # noqa: E402
from spikes.failure_log_sweep.sweep import (  # noqa: E402
    StrategyRecorder, distinct_contexts, key_of, project_from_context, signature,
)

SHIPPED = cg.generate_concepts


def make_filter(toggle: str):
    def keep(c) -> bool:
        if toggle == "twins":
            return not c.rationale.endswith(cg.FREE_TWIN_RATIONALE)
        if toggle == "hub":
            return c.strategy.value != "HUB_PRIVATE_WING"
        raise ValueError(toggle)

    def filtered(spec, candidates):
        res = SHIPPED(spec, candidates)
        kept = tuple(c for c in res.candidates if keep(c))
        rej = tuple(r for r in res.rejections
                    if toggle != "hub" or r.strategy.value != "HUB_PRIVATE_WING")
        return type(res)(kept, rej, res.program)
    return filtered


def run_all(contexts, label, recorder: StrategyRecorder):
    out = {}
    started = time.perf_counter()
    for i, ctx in enumerate(contexts, start=1):
        recorder.reset()
        t = time.perf_counter()
        try:
            res = svc.generate_demo_design(project_from_context(ctx))
            rec = dict(status="PLANNED", sig=signature(res.design),
                       alts=tuple(signature(a) for a in res.alternatives),
                       area=res.design.gross_area_m2, validators=res.design.validation.passed,
                       rooms=len(res.design.rooms), code=None)
        except svc.DemoGenerationError as exc:
            rec = dict(status="REFUSED", code=exc.code + ("+outline" if "כן מתאפשר" in exc.message else ""))
        except Exception as exc:  # noqa: BLE001
            rec = dict(status="CRASH", code=f"{type(exc).__name__}: {exc}")
        rec["seconds"] = time.perf_counter() - t
        rec["strategy"] = recorder.chosen_strategy
        rec["twin"] = recorder.chosen_is_twin
        rec["candidates"] = list(recorder.candidate_strategies)
        rec["rejections"] = list(recorder.rejections)
        out[key_of(ctx)] = rec
        if i % 100 == 0:
            print(f"  {label} {i}/{len(contexts)}", flush=True)
    print(f"  {label} done in {time.perf_counter() - started:.0f}s", flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--toggle", choices=("twins", "hub"), required=True)
    args = ap.parse_args()
    contexts = distinct_contexts()
    by_key = {key_of(c): c for c in contexts}
    print(f"scenarios: {len(contexts)}   toggle: {args.toggle}")

    recorder = StrategyRecorder()
    cg.generate_concepts = make_filter(args.toggle)
    recorder.install()
    off = run_all(contexts, "OFF", recorder)
    recorder.remove()
    cg.generate_concepts = SHIPPED
    recorder.install()
    on = run_all(contexts, "ON ", recorder)
    recorder.remove()

    pre = [k for k, v in off.items() if v["status"] == "PLANNED"]
    identical = sum(1 for k in pre if on[k]["status"] == "PLANNED" and on[k]["sig"] == off[k]["sig"])
    identical_alts = sum(1 for k in pre if on[k]["status"] == "PLANNED"
                         and on[k]["sig"] == off[k]["sig"] and on[k]["alts"] == off[k]["alts"])
    lost = [k for k in pre if on[k]["status"] != "PLANNED"]
    gained = [k for k, v in on.items() if v["status"] == "PLANNED" and off[k]["status"] != "PLANNED"]

    print(f"\nplanned OFF={len(pre)}  ON={sum(1 for v in on.values() if v['status']=='PLANNED')}")
    print(f"pre-existing PRIMARY designs byte-identical: {identical}/{len(pre)}   (primary + alternatives: {identical_alts}/{len(pre)})")
    print(f"LOST: {len(lost)}   GAINED: {len(gained)}   crashes OFF={sum(v['status']=='CRASH' for v in off.values())} ON={sum(v['status']=='CRASH' for v in on.values())}")
    for k in lost:
        print("  LOST:", by_key[k], "->", on[k]["code"])

    counted = 0
    if gained:
        print(f"\n{'footprint':>12} {'bd/wet/safe':>11} {'asked':>7} {'built':>7} {'%':>5}  validators  strategy")
        for k in sorted(gained):
            c, v = by_key[k], on[k]
            pct = 100 * v["area"] / c["built_area_m2"]
            ok = pct >= 80 and v["validators"]
            counted += ok
            print(f"{c['footprint_width_m']}x{c['footprint_depth_m']:<8} {c['bedrooms']}/{c['wet_rooms']}/{'Y' if c['safe_room'] else 'N':<7} "
                  f"{c['built_area_m2']:7.1f} {v['area']:7.1f} {pct:4.0f}%  {'pass' if v['validators'] else 'FAIL':10s} "
                  f"{v['strategy']}{' (twin)' if v['twin'] else ''}{'' if ok else '   <-- not counted'}")
        print(f"counted as gains (>=80% of ask, validators pass): {counted}/{len(gained)}")

    print("\nrefusal codes:")
    cb = Counter(v["code"] for v in off.values() if v["status"] == "REFUSED")
    ca = Counter(v["code"] for v in on.values() if v["status"] == "REFUSED")
    for code in sorted(set(cb) | set(ca)):
        print(f"  {code:52s} OFF={cb.get(code,0):4d}  ON={ca.get(code,0):4d}")

    print("\nstrategy of delivered plans (ON):", dict(Counter(v["strategy"] for v in on.values() if v["status"] == "PLANNED")))
    if args.toggle == "hub":
        had_hub = [k for k, v in on.items() if "HUB_PRIVATE_WING" in v["candidates"]]
        won = [k for k in had_hub if on[k]["status"] == "PLANNED" and on[k]["strategy"] == "HUB_PRIVATE_WING"]
        other = [k for k in had_hub if on[k]["status"] == "PLANNED" and on[k]["strategy"] != "HUB_PRIVATE_WING"]
        print(f"hub candidate present: {len(had_hub)}   hub delivered: {len(won)}   other parti won: {len(other)}")
        hub_rej = Counter(r for v in on.values() for s, r in v["rejections"] if s == "HUB_PRIVATE_WING")
        print("hub rejections by reason:", dict(hub_rej))

    def lat(keys, label):
        if not keys:
            return
        d = sorted((on[k]["seconds"] - off[k]["seconds"], k) for k in keys)
        print(f"latency {label} (n={len(keys)}): median OFF {statistics.median(off[k]['seconds'] for k in keys):.2f}s "
              f"-> ON {statistics.median(on[k]['seconds'] for k in keys):.2f}s   worst regression {d[-1][0]:+.2f}s")
    lat(pre, "already planned")
    lat([k for k in off if k not in set(pre)], "not planned before")
    print(f"total OFF {sum(v['seconds'] for v in off.values()):.0f}s   ON {sum(v['seconds'] for v in on.values()):.0f}s")

    with open(Path(__file__).with_name("gained.json"), "w") as f:
        json.dump([by_key[k] for k in sorted(gained)], f, indent=1)


if __name__ == "__main__":
    main()
