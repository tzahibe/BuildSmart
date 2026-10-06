"""#142N — render the cycles so the plans behind the numbers can be inspected.

A cycle sheet puts the three plans of one measured cycle side by side, each panel labelled with the
circulation values that carry the edge into it, and the arrow that closes the loop spelled out
underneath. Drawing is `quality_142l.render.draw_plan` — the same renderer #142L used, unchanged.

    PYTHONPATH=backend python -m app.ai_harness.circulation_142n.renders <pool.json> <analysis.json> <out_dir>
"""
from __future__ import annotations

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from app.ai_harness.quality_142l.render import brief_text, draw_plan

from .relation import plans_of


def cycle_sheet(plans: list[dict], edges: dict, out_path: str, note: str) -> str:
    """Three plans of one cycle, left to right, with the edge that beats each predecessor."""
    fig, axes = plt.subplots(1, 3, figsize=(20.4, 7.6))
    keys = [f"{p['brief']}#{p['candidate']}" for p in plans]
    for ax, p, k in zip(axes, plans, keys):
        c = p["production_quality"]["circulation"]
        title = (f"{k}   ratio {c['ratio']:.3f} · longest {c['longest_segment_m']:.2f} m · "
                 f"dead ends {c['dead_end_count']} · plan {p['gross_area_m2']:.1f} m²")
        draw_plan(p, ax, title)
    arrows = "    ".join(f"{a} ≻ {b} (by {', '.join(v) or 'nothing'})"
                         for (a, b), v in edges.items())
    fig.suptitle(f"BRIEF: {brief_text(plans[0])}\n{note}\n{arrows}", fontsize=10)
    fig.text(0.5, 0.015, "walls: black = exterior, grey = partition, thick red = RC safe-room | blue = window | "
             "green = interior door | star = front door | street at the bottom edge",
             ha="center", fontsize=7.5, color="#666666")
    fig.tight_layout(rect=(0, 0.04, 1, 0.88))
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path


def main(pool_path: str, analysis_path: str, out_dir: str) -> list[str]:
    pool = json.load(open(pool_path))
    analysis = json.load(open(analysis_path))
    os.makedirs(out_dir, exist_ok=True)
    made = []
    for ds in ("historical", "corrected"):
        by_key = {p.key: p.record for v in plans_of(pool, ds).values() for p in v}
        d = analysis["datasets"][ds]

        cyc = d["f0"]["smallest_cycle"]
        if cyc:
            edges = {tuple(k.split("->")): v for k, v in cyc["causes_per_edge"].items()}
            made.append(cycle_sheet(
                [by_key[k] for k in cyc["cycle"]], edges,
                os.path.join(out_dir, f"{ds}-smallest-cycle.png"),
                "SMALLEST MEASURED CYCLE under production's circulation_prefers — each plan is "
                "preferred over the one on its left, and the last is preferred over the first."))

        na = d["cycles_without_the_area_disjunct"]["smallest"]
        if na:
            edges = {tuple(k.split("->")): v for k, v in na["better_on"].items()}
            made.append(cycle_sheet(
                [by_key[k] for k in na["cycle"]], edges,
                os.path.join(out_dir, f"{ds}-cycle-without-area.png"),
                "A CYCLE THAT SURVIVES WITHOUT THE `area` DISJUNCT — the three circulation "
                "measures alone, each plan better than its left neighbour on a different one."))
    print("\n".join(made))
    return made


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
