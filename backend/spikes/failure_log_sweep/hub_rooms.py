"""Every realized hub plan's rooms with their rectangles and aspects — production winners, or with
`--hub-only` every scenario realized from its hub candidates alone. The diagnosis tool behind v2.1:
medians say WHETHER a gate fails, the rectangles say WHICH decision put the strip where.

    .venv/bin/python3 spikes/failure_log_sweep/hub_rooms.py [--hub-only]
"""
from __future__ import annotations

import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.demo import service as svc  # noqa: E402
from app.vertical_slice import concept_generator as cg  # noqa: E402
from spikes.failure_log_sweep.sweep import StrategyRecorder, distinct_contexts, project_from_context  # noqa: E402


def main():
    svc._outline_that_plans = lambda project: None  # measurement only: skip the refusal-path search
    shipped = cg.generate_concepts
    if "--hub-only" in sys.argv:
        def only(spec, candidates):
            res = shipped(spec, candidates)
            kept = tuple(c for c in res.candidates if c.strategy.value == "HUB_PRIVATE_WING")
            return type(res)(kept, res.rejections, res.program)
        cg.generate_concepts = only

    rec = StrategyRecorder()
    rec.install()
    per_type = defaultdict(list)
    by_elig = defaultdict(lambda: defaultdict(list))
    for ctx in distinct_contexts():
        rec.reset()
        try:
            res = svc.generate_demo_design(project_from_context(ctx))
        except Exception:  # noqa: BLE001
            continue
        if rec.chosen_strategy != "HUB_PRIVATE_WING":
            continue
        print(f"\n### {ctx['footprint_width_m']}x{ctx['footprint_depth_m']} bd={ctx['bedrooms']} "
              f"wet={ctx['wet_rooms']} safe={ctx['safe_room']} open={ctx['open_plan']} "
              f"asked={ctx['built_area_m2']} twin={rec.chosen_is_twin} "
              f"{'ELIGIBLE' if 'hub eligible' in rec.chosen_rationale else ('LAST_RESORT' if 'hub last resort' in rec.chosen_rationale else '')}")
        for r in sorted(res.design.rooms, key=lambda r: (r.y, r.x)):
            a = max(r.width_m, r.depth_m) / max(min(r.width_m, r.depth_m), 1e-6)
            print(f"  {r.type:16s} x={r.x:5.2f} y={r.y:5.2f}  {r.width_m:5.2f} x {r.depth_m:5.2f}  aspect {a:.2f}")
            per_type[r.type].append(a)
            by_elig["ELIGIBLE" if "hub eligible" in rec.chosen_rationale else "LAST_RESORT"][r.type].append(a)
    rec.remove()
    cg.generate_concepts = shipped
    for elig, types in sorted(by_elig.items()):
        print(f"\n=== medians by type — {elig} hub plans ===")
        for t, xs in sorted(types.items()):
            print(f"{t:16s} n={len(xs):3d} aspect median {statistics.median(xs):.2f}  "
                  f"share >1.35: {sum(1 for x in xs if x > 1.35)}/{len(xs)}")
    print("\n=== medians by type ===")
    for t, xs in sorted(per_type.items()):
        print(f"{t:16s} n={len(xs):3d} aspect median {statistics.median(xs):.2f}  "
              f"share >1.35: {sum(1 for x in xs if x > 1.35)}/{len(xs)}")


if __name__ == "__main__":
    main()
