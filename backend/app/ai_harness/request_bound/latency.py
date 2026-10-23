"""The honest latency of a brain request, and proof that bounding it lost no plan (#247 AC-5/AC-6).

Deliberately runnable in an UNCHANGED control tree as well as on the branch: it reads the budget
through `getattr`, so a tree that predates `service.BRAIN_BUDGET_S` is measured at its own default
and the two runs are comparable. Production is measured in the same loop as the brain, so the
multiple between them cannot drift with the machine.

    PYTHONPATH=backend python -m app.ai_harness.request_bound.latency <out.json> [BRIEF ...]

`BUDGET_S` in the environment overrides the stated budget where the tree has one. The plan set is
recorded as a per-plan geometry signature, so "no plan was lost" is a comparison of drawings and
not of counts.
"""
from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import time


def _project_for(b):
    from tests.vertical_slice.test_hub_guard import _project
    return _project(dict(bedrooms=b.bedrooms, wet_rooms=b.wet_rooms, safe_room=b.safe_room,
                         open_plan=b.open_plan, built_area_m2=b.built_area_m2,
                         footprint_width_m=b.footprint_width_m,
                         footprint_depth_m=b.footprint_depth_m,
                         plot_width_m=b.footprint_width_m + 8,
                         plot_depth_m=b.footprint_depth_m + 8))


def _signature(design) -> list:
    """Every room's rounded rectangle — what the drawing actually is. Two plans with the same
    signature ARE the same plan, so this is what "no plan was lost" has to be decided on."""
    return sorted([r.type, round(r.x, 2), round(r.y, 2), round(r.w, 2), round(r.h, 2)]
                  for r in design.rooms)


def _load() -> str:
    try:
        return subprocess.run(["uptime"], capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception as exc:                                         # never fail a measurement on this
        return f"uptime unavailable: {exc}"


def measure(bid: str) -> dict:
    from app.ai_harness.topology_poc import briefs as briefs_mod
    from app.demo import service as svc

    b = {x.brief_id: x for x in briefs_mod.select_briefs()}[bid]
    project = _project_for(b)
    out: dict = {"brief": bid, "requested_m2": b.built_area_m2}

    t0 = time.monotonic()
    prod = svc.generate_demo_design(project)
    out["production_s"] = round(time.monotonic() - t0, 3)
    out["production_plans"] = 1 + len(prod.alternatives)

    t0 = time.monotonic()
    try:
        br = svc.generate_demo_design(project, brain=True)
        out["brain_s"] = round(time.monotonic() - t0, 3)
        out["brain_plans"] = 1 + len(br.alternatives)
        out["signatures"] = [_signature(d) for d in (br.design, *br.alternatives)]
        out["families"] = [br.design.family] + [a.family for a in br.alternatives]
        out["budget_notes"] = [n for n in (br.design.validation.warnings or ())
                               if "request budget" in n]
    except svc.DemoGenerationError as exc:
        out["brain_s"] = round(time.monotonic() - t0, 3)
        out["refused"] = exc.code
    return out


def main(argv: list[str]) -> None:
    from app.demo import service as svc

    path = argv[0]
    briefs = argv[1:] or ["B08", "B20", "B02", "B11", "B16", "B19", "B06", "B09"]
    budget = os.environ.get("BUDGET_S")
    stated = getattr(svc, "BRAIN_BUDGET_S", None)
    if budget is not None and stated is not None:
        svc.BRAIN_BUDGET_S = float(budget)
        stated = float(budget)
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                          text=True).stdout.strip() or "unknown (archived tree)"
    meta = {"load_before": _load(), "stated_budget_s": stated, "head": head,
            "budget_is_request_wide": hasattr(svc, "BRAIN_BUDGET_S")}
    print(f"stated budget {stated} · head {head}\n  load before: {meta['load_before']}", flush=True)
    rows = []
    for bid in briefs:
        rows.append(measure(bid))
        r = rows[-1]
        print(f"{bid}: production {r['production_s']:6.2f} s ({r['production_plans']} plans) · "
              f"brain {r['brain_s']:6.2f} s ({r.get('brain_plans', r.get('refused'))} plans)"
              + (f" · NOTE {len(r['budget_notes'])}" if r.get("budget_notes") else ""), flush=True)
    meta["load_after"] = _load()
    for who in ("production", "brain"):
        xs = [r[f"{who}_s"] for r in rows if f"{who}_s" in r]
        meta[who] = {"median": round(statistics.median(xs), 2), "max": round(max(xs), 2),
                     "min": round(min(xs), 2), "n": len(xs)}
    print(f"\n  production median {meta['production']['median']} s  max {meta['production']['max']} s"
          f"\n  brain      median {meta['brain']['median']} s  max {meta['brain']['max']} s"
          f"\n  load after: {meta['load_after']}", flush=True)
    with open(path, "w") as fh:
        json.dump({"meta": meta, "rows": rows}, fh, indent=2)


if __name__ == "__main__":
    main(sys.argv[1:])
