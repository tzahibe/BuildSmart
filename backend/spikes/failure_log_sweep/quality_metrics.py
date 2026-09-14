"""Stage-0 architectural-quality metrics on delivered geometry, optionally split by parti.

    .venv/bin/python3 spikes/failure_log_sweep/quality_metrics.py [--contexts gained.json] [--split-by-strategy]

Reference values (21 professional plans, visual census) live in specs/005-hub-private-wing/spec.md §1.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.demo import service as svc  # noqa: E402
from spikes.failure_log_sweep.sweep import StrategyRecorder, distinct_contexts, project_from_context  # noqa: E402

HABITABLE = ("BED", "MASTER", "LIVING", "DINING", "KITCHEN", "STUDY", "FAMILY", "SAFE")
WET = ("BATH", "TOILET", "WC")
WET_NEIGHBOURS = WET + ("KITCHEN", "LAUNDRY")
PUBLIC = ("LIVING", "DINING", "KITCHEN")


def is_(kind, room_type: str) -> bool:
    t = room_type.upper()
    return any(k in t for k in kind)


def measure(designs) -> dict:
    aspects, by_type = [], defaultdict(list)
    exposed = hab = 0
    circ, hub_deg, hall_asp = [], [], []
    wet_adj = wet_tot = 0
    contig = pub_plans = 0
    for d in designs:
        rooms = {r.id: r for r in d.rooms}
        halls = {r.id for r in d.rooms if is_(("HALL", "CIRC"), r.type)}
        ext = set()
        for w in d.walls:
            if w.boundary_context == "EXTERIOR":
                ext.update(w.room_ids)
        for r in d.rooms:
            if is_(HABITABLE, r.type):
                a = max(r.width_m, r.depth_m) / max(min(r.width_m, r.depth_m), 1e-6)
                aspects.append(a); by_type[r.type].append(a); hab += 1
                exposed += r.id in ext
        total = sum(r.width_m * r.depth_m for r in d.rooms)
        circ.append(sum(r.width_m * r.depth_m for r in d.rooms if r.id in halls) / total)
        hub_deg.append(sum(1 for dr in d.doors if not dr.is_entrance and (dr.a in halls or dr.b in halls)))
        for h in halls:
            r = rooms[h]
            hall_asp.append(max(r.width_m, r.depth_m) / max(min(r.width_m, r.depth_m), 1e-6))
        adj = defaultdict(set)
        for w in d.walls:
            if w.boundary_context == "INTERIOR" and len(w.room_ids) >= 2:
                for rid in w.room_ids:
                    adj[rid].update(x for x in w.room_ids if x != rid)
        for r in d.rooms:
            if is_(WET, r.type):
                wet_tot += 1
                wet_adj += any(is_(WET_NEIGHBOURS, rooms[n].type) for n in adj[r.id] if n in rooms)
        pub = [r.id for r in d.rooms if is_(PUBLIC, r.type)]
        if len(pub) >= 2:
            pub_plans += 1
            open_adj = defaultdict(set)
            for o in d.open_interfaces:
                for rid in o.room_ids:
                    open_adj[rid].update(x for x in o.room_ids if x != rid)
            for dr in d.doors:
                if "CASED" in dr.kind.upper() or "OPEN" in dr.kind.upper():
                    open_adj[dr.a].add(dr.b); open_adj[dr.b].add(dr.a)
            seen, stack = set(), [pub[0]]
            while stack:
                n = stack.pop()
                if n in seen:
                    continue
                seen.add(n); stack.extend(x for x in open_adj[n] if x in pub)
            contig += all(p in seen for p in pub)
    aspects.sort()
    return dict(
        n=len(designs),
        aspect_median=statistics.median(aspects) if aspects else None,
        aspect_p90=aspects[int(0.9 * len(aspects))] if aspects else None,
        by_type={t: (round(statistics.median(v), 2), len(v)) for t, v in sorted(by_type.items())},
        exposure=(exposed, hab),
        circ_median=statistics.median(circ) if circ else None, circ_max=max(circ) if circ else None,
        hall_doors_median=statistics.median(hub_deg) if hub_deg else None,
        hall_doors_range=(min(hub_deg), max(hub_deg)) if hub_deg else None,
        hall_aspect_median=statistics.median(hall_asp) if hall_asp else None,
        hall_compact_share=(sum(1 for a in hall_asp if a <= 1.5), len(hall_asp)),
        wet=(wet_adj, wet_tot), public_contig=(contig, pub_plans),
    )


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
