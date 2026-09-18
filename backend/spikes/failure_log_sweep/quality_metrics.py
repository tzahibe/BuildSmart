"""Stage-0 architectural-quality metrics on delivered geometry, optionally split by parti.

    .venv/bin/python3 spikes/failure_log_sweep/quality_metrics.py [--contexts gained.json] [--split-by-strategy]

Reference values (21 professional plans, visual census) live in specs/005-hub-private-wing/spec.md §1.

The M1–M6 computations themselves live in `app.vertical_slice.quality_metrics` (Issue #17) — this
script is now just the corpus driver and the printed report around it.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.demo import service as svc  # noqa: E402
from app.vertical_slice.quality_metrics import summarize as measure  # noqa: E402
from spikes.failure_log_sweep.sweep import StrategyRecorder, distinct_contexts, project_from_context  # noqa: E402


def report(label: str, m: dict) -> None:
    pct = lambda a, b: f"{100*a/b:.0f}% ({a}/{b})" if b else "n/a"
    print(f"\n== {label}: {m['n']} plans ==")
    if not m["n"]:
        return
    print(f"  M1 habitable aspect median {m['aspect_median']:.2f}  p90 {m['aspect_p90']:.2f}")
    for t, (med, n) in m["by_type"].items():
        print(f"     {t:16s} median {med:.2f}  n={n}")
    print(f"  M2 habitable rooms on envelope {pct(*m['exposure'])}")
    print(f"  M3 circulation share median {100*m['circ_median']:.0f}%  max {100*m['circ_max']:.0f}%")
    print(f"  M4 doors on hall median {m['hall_doors_median']:.0f} range {m['hall_doors_range']}   "
          f"hall long/short median {m['hall_aspect_median']:.1f}   compact (<=1.5) {pct(*m['hall_compact_share'])}")
    print(f"  M5 wet adjacency {pct(*m['wet'])}")
    print(f"  M6 public zone contiguous {pct(*m['public_contig'])}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--contexts", help="JSON list of contexts to restrict to (e.g. gained.json)")
    ap.add_argument("--split-by-strategy", action="store_true")
    ap.add_argument("--hub-only", action="store_true",
                    help="realize every scenario from its HUB_PRIVATE_WING candidates only, so the "
                         "hub's own quality can be measured even where another parti wins in production")
    args = ap.parse_args()
    contexts = json.load(open(args.contexts)) if args.contexts else distinct_contexts()

    # (feature 006 retired `_outline_that_plans`; the refusal path no longer re-plans outlines)
    if args.hub_only:
        from app.vertical_slice import concept_generator as cg
        shipped = cg.generate_concepts

        def hub_only(spec, candidates):
            res = shipped(spec, candidates)
            kept = tuple(c for c in res.candidates if c.strategy.value == "HUB_PRIVATE_WING")
            return type(res)(kept, res.rejections, res.program)
        cg.generate_concepts = hub_only
    recorder = StrategyRecorder()
    recorder.install()
    designs_by_strategy = defaultdict(list)
    for ctx in contexts:
        recorder.reset()
        try:
            res = svc.generate_demo_design(project_from_context(ctx))
        except Exception:  # noqa: BLE001
            continue
        designs_by_strategy[recorder.chosen_strategy or "?"].append(res.design)
    recorder.remove()

    everything = [d for ds in designs_by_strategy.values() for d in ds]
    report("all delivered plans", measure(everything))
    if args.split_by_strategy:
        for strategy, ds in sorted(designs_by_strategy.items()):
            report(strategy, measure(ds))
        hub = designs_by_strategy.get("HUB_PRIVATE_WING", [])
        non_hub = [d for s, ds in designs_by_strategy.items() if s != "HUB_PRIVATE_WING" for d in ds]
        if hub:
            report("HUB vs NON-HUB — non-hub", measure(non_hub))


if __name__ == "__main__":
    main()
