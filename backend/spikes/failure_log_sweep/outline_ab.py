"""Feature 006 A/B over the failure log: the person's outline (advanced path) vs none (main flow).

    .venv/bin/python3 spikes/failure_log_sweep/outline_ab.py --before specs/006-engine-chosen-outline/before.json

A: every logged context WITH its `selected_footprint` — the advanced path; its primaries must be
   byte-identical to the frozen `before.json` (SC-005) and nothing may be LOST.
B: the same contexts WITHOUT a footprint — the main flow; the engine plans its own outlines.

Prints one line per success criterion of specs/006-engine-chosen-outline/spec.md §4 and writes
`outline_ab.json` beside this file. Run from `backend/`.
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
from spikes.failure_log_sweep.sweep import (  # noqa: E402
    distinct_contexts, key_of, plans_shown, project_from_context, signature,
)

OUT = Path(__file__).with_name("outline_ab.json")


def run_all(contexts, *, with_footprint: bool, label: str) -> dict:
    out = {}
    started = time.perf_counter()
    for i, ctx in enumerate(contexts, 1):
        t = time.perf_counter()
        try:
            res = svc.generate_demo_design(project_from_context(ctx, with_footprint=with_footprint))
            shown = plans_shown(res)
            rec = dict(
                status="PLANNED",
                sig=[list(s) for s in signature(res.design)],
                gross=res.design.gross_area_m2,
                shown=[dict(outline=(d.outline.width_m, d.outline.depth_m, d.outline.origin),
                            family=d.family, validated=d.validation.passed,
                            sig=[list(s) for s in signature(d)]) for d in shown],
                search=res.search.model_dump() if res.search else None,
            )
        except svc.DemoGenerationError as exc:
            rec = dict(status="REFUSED", code=exc.code, message=exc.message)
        except Exception as exc:  # noqa: BLE001
            rec = dict(status="CRASH", code=f"{type(exc).__name__}: {exc}")
        rec["seconds"] = time.perf_counter() - t
        out[key_of(ctx)] = rec
        if i % 100 == 0:
            print(f"  {label} {i}/{len(contexts)}  {time.perf_counter() - started:.0f}s", flush=True)
    print(f"  {label} done in {time.perf_counter() - started:.0f}s", flush=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True, help="snapshot.py --save output at the base commit")
    ap.add_argument("--only", choices=("A", "B"), help="run one arm only (the other is read from outline_ab.json)")
    args = ap.parse_args()
    before = json.load(open(args.before))
    contexts = distinct_contexts()
    by_key = {key_of(c): c for c in contexts}
    print(f"scenarios: {len(contexts)}   before.json: {len(before)} "
          f"(planned {sum(v['status'] == 'PLANNED' for v in before.values())})")

    previous = json.load(open(OUT)) if OUT.exists() and args.only else {}
    a = previous.get("A") if args.only == "B" else run_all(contexts, with_footprint=True, label="A (advanced)")
    b = previous.get("B") if args.only == "A" else run_all(contexts, with_footprint=False, label="B (main flow)")
    json.dump({"A": a, "B": b}, open(OUT, "w"))

    pre = [k for k, v in before.items() if v["status"] == "PLANNED" and k in a]
    a_planned = [k for k, v in a.items() if v["status"] == "PLANNED"]
    b_planned = [k for k, v in b.items() if v["status"] == "PLANNED"]
    print(f"\nplanned  before={len(pre)}  A={len(a_planned)}  B={len(b_planned)}   (SC-001: B >= 250 of 424-class log)")

    # SC-005 — advanced path byte-identical
    identical = [k for k in pre if a[k]["status"] == "PLANNED" and a[k]["sig"] == before[k]["sig"]]
    lost_a = [k for k in pre if a[k]["status"] != "PLANNED"]
    print(f"SC-005 A primaries byte-identical to before: {len(identical)}/{len(pre)}   LOST in A: {len(lost_a)}")
    for k in [k for k in pre if k not in identical][:10]:
        c = by_key[k]
        print(f"   differs: {c['footprint_width_m']}x{c['footprint_depth_m']} bd{c['bedrooms']} wet{c['wet_rooms']} "
              f"safe{int(c['safe_room'])} ask {c['built_area_m2']} -> {a[k]['status']} {a[k].get('code', '')}")

    # main-flow non-regression — every brief planned before still plans in B
    lost_b = [k for k in pre if b[k]["status"] != "PLANNED"]
    print(f"main-flow non-regression: briefs PLANNED before that are NOT planned in B: {len(lost_b)}")
    for k in lost_b:
        c = by_key[k]
        print(f"   LOST in B: {c['footprint_width_m']}x{c['footprint_depth_m']} bd{c['bedrooms']} wet{c['wet_rooms']} "
              f"safe{int(c['safe_room'])} open{int(c['open_plan'])} ask {c['built_area_m2']} -> {b[k].get('code')}")

    # SC-002 — first-plan gross / requested, B, among briefs that planned before
    ratios = sorted(b[k]["gross"] / by_key[k]["built_area_m2"] for k in pre if b[k]["status"] == "PLANNED")
    if ratios:
        print(f"SC-002 B first-plan gross/requested (briefs planned before): median {statistics.median(ratios):.3f}  "
              f">=0.95: {sum(r >= 0.95 for r in ratios)}/{len(ratios)}   (target median >= 0.95)")
    ratios_all = sorted(b[k]["gross"] / by_key[k]["built_area_m2"] for k in b_planned)
    print(f"       B first-plan gross/requested (all B-planned): median {statistics.median(ratios_all):.3f}")

    # SC-003 — distinct families shown, B, among briefs that planned before
    fam2 = sum(1 for k in pre if b[k]["status"] == "PLANNED"
               and len({s["family"] for s in b[k]["shown"]}) >= 2)
    fam2_before = sum(1 for k in pre if a[k]["status"] == "PLANNED"
                      and len({s["family"] for s in a[k]["shown"]}) >= 2)
    print(f"SC-003 briefs with >=2 distinct families shown: A {fam2_before}/{len(pre)}   B {fam2}/{len(pre)}   (target B >= 60)")
    print(f"       plans shown per brief in B: {dict(sorted(Counter(len(v['shown']) for k, v in b.items() if v['status'] == 'PLANNED').items()))}")

    # SC-004 — no shown plan fails validation
    bad = sum(1 for arm in (a, b) for v in arm.values() if v["status"] == "PLANNED"
              for s in v["shown"] if not s["validated"])
    print(f"SC-004 shown plans failing validation: {bad}   (must be 0)")

    # SC-006 — same family + same outline shown twice
    dup = 0
    for arm in (a, b):
        for v in arm.values():
            if v["status"] != "PLANNED":
                continue
            seen = Counter((s["family"], tuple(s["outline"][:2])) for s in v["shown"])
            dup += sum(n - 1 for n in seen.values())
    print(f"SC-006 same-family + same-outline pairs shown: {dup}   (must be 0)")

    # SC-007 — refusals never name an outline; over-capacity carries the capacity code
    naming = [k for k, v in b.items() if v["status"] == "REFUSED" and "מתאר של" in v.get("message", "")]
    over = [k for k, v in before.items() if v.get("code", "").startswith("TARGET_AREA_EXCEEDS")]
    over_ok = sum(1 for k in over if k in b and b[k].get("code") == "TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY")
    print(f"SC-007 B refusals naming an outline: {len(naming)}   (must be 0);  over-capacity refusals keeping the "
          f"capacity diagnosis: {over_ok}/{len(over)}")
    print("       B refusal codes:", dict(Counter(v.get("code") for v in b.values() if v["status"] == "REFUSED")))
    print("       crashes: A", sum(v["status"] == "CRASH" for v in a.values()), " B", sum(v["status"] == "CRASH" for v in b.values()))

    # SC-008 — latency
    def med(arm, keys):
        vals = [arm[k]["seconds"] for k in keys if k in arm]
        return statistics.median(vals) if vals else float("nan")
    print(f"SC-008 latency median (s): A all {med(a, a):.2f}  B all {med(b, b):.2f}   "
          f"A planned-before {med(a, pre):.2f}  B planned-before {med(b, pre):.2f}   "
          f"B worst {max(v['seconds'] for v in b.values()):.2f}")
    print(f"       B outlines planned per request: {dict(sorted(Counter(len(v['search']['outlines']) for v in b.values() if v.get('search')).items()))}")
    print("       B primary outline origin:", dict(Counter(v["shown"][0]["outline"][2] for v in b.values() if v["status"] == "PLANNED")))
    print("       A primary outline origin:", dict(Counter(v["shown"][0]["outline"][2] for v in a.values() if v["status"] == "PLANNED")))


if __name__ == "__main__":
    main()
