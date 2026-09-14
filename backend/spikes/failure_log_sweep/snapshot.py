"""Cross-commit gate: snapshot every scenario's primary design signature, or compare to one.

    .venv/bin/python3 spikes/failure_log_sweep/snapshot.py --save before.json
    ...change the code...
    .venv/bin/python3 spikes/failure_log_sweep/snapshot.py --compare before.json

`ab.py` compares a mechanism ON vs OFF inside one process; this compares two commits.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.demo import service as svc  # noqa: E402
from spikes.failure_log_sweep.sweep import distinct_contexts, key_of, project_from_context, signature  # noqa: E402


def run_all():
    out = {}
    for ctx in distinct_contexts():
        try:
            res = svc.generate_demo_design(project_from_context(ctx))
            out[key_of(ctx)] = {"status": "PLANNED", "sig": [list(s) for s in signature(res.design)],
                                "area": res.design.gross_area_m2}
        except svc.DemoGenerationError as exc:
            out[key_of(ctx)] = {"status": "REFUSED",
                                "code": exc.code + ("+outline" if "כן מתאפשר" in exc.message else "")}
        except Exception as exc:  # noqa: BLE001
            out[key_of(ctx)] = {"status": "CRASH", "code": f"{type(exc).__name__}: {exc}"}
    return out


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--save"); g.add_argument("--compare")
    args = ap.parse_args()
    now = run_all()
    if args.save:
        json.dump(now, open(args.save, "w"))
        print(f"saved {len(now)} scenarios: planned {sum(v['status']=='PLANNED' for v in now.values())}")
        return
    before = json.load(open(args.compare))
    pre = [k for k, v in before.items() if v["status"] == "PLANNED"]
    same = sum(1 for k in pre if now.get(k, {}).get("status") == "PLANNED" and now[k]["sig"] == before[k]["sig"])
    lost = [k for k in pre if now.get(k, {}).get("status") != "PLANNED"]
    gained = [k for k, v in now.items() if v["status"] == "PLANNED" and before.get(k, {}).get("status") != "PLANNED"]
    print(f"planned before={len(pre)}  now={sum(v['status']=='PLANNED' for v in now.values())}")
    print(f"pre-existing PRIMARY designs byte-identical: {same}/{len(pre)}   LOST: {len(lost)}   GAINED: {len(gained)}")
    for k in gained:
        c = json.loads(k); print(f"  GAINED {c['footprint_width_m']}x{c['footprint_depth_m']} bd={c['bedrooms']} wet={c['wet_rooms']} safe={c['safe_room']} asked {c['built_area_m2']} built {now[k]['area']:.1f} ({100*now[k]['area']/c['built_area_m2']:.0f}%)")
    for k in lost:
        print("  LOST", json.loads(k), "->", now.get(k))
    cb = Counter(v.get("code") for v in before.values() if v["status"] == "REFUSED")
    ca = Counter(v.get("code") for v in now.values() if v["status"] == "REFUSED")
    print("refusal codes:")
    for code in sorted(set(cb) | set(ca), key=str):
        print(f"  {str(code):52s} before={cb.get(code,0):4d}  now={ca.get(code,0):4d}")


if __name__ == "__main__":
    main()
