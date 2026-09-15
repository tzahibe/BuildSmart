"""Cross-commit gate for ROOM AREA: every delivered room against its template's hard maximum.

    .venv/bin/python3 spikes/failure_log_sweep/room_area.py --save before.json
    ...change the code...
    .venv/bin/python3 spikes/failure_log_sweep/room_area.py --save after.json
    .venv/bin/python3 spikes/failure_log_sweep/room_area.py --compare before.json after.json

Like `snapshot.py`, but per ROOM: type, net rectangle, net area, the template maximum, and the
area `scale_program` WANTED for the zone on the delivered outline — so the comparison can say
not only planned / LOST / GAINED but how many rooms sit above their maximum, which roles the
surplus moved to, and how far each delivered plan is from the ask. Refusals keep their failed
checks so new validator codes (C20, C21) can be counted.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.demo import service as svc  # noqa: E402
from app.vertical_slice.concept_generator import (  # noqa: E402
    ASSUMED_EFFICIENCY, HUB_TEMPLATE, ROOM_TEMPLATES, ProgramRole, build_room_program, scale_program,
)
from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec  # noqa: E402
from spikes.failure_log_sweep.sweep import (  # noqa: E402
    StrategyRecorder, distinct_contexts, key_of, project_from_context, signature,
)

CIRCULATION = ("HALL", "CIRCULATION", "FLEX")


def _wanted(ctx: dict, outline, zone_ids: set[str]) -> dict[str, float]:
    """What `scale_program` asked for on this outline, per zone — the planner's own intent."""
    program = ProgramSpec(bedrooms=ctx["bedrooms"], safe_room=bool(ctx["safe_room"]),
                          open_plan_living=bool(ctx["open_plan"]), wet_rooms=ctx["wet_rooms"],
                          parking_spaces=0, target_built_area_m2=ctx["built_area_m2"])
    spec = ArchitecturalSpec(plot=PlotSpec(width_m=ctx["plot_width_m"], depth_m=ctx["plot_depth_m"]),
                             program=program)
    try:
        rooms = build_room_program(spec)
        specs = scale_program(rooms, outline.width_m * outline.depth_m * ASSUMED_EFFICIENCY)
    except Exception:  # noqa: BLE001 — a variant programme the log context cannot rebuild
        return {}
    return {z: s.net_area_target_m2 for z, s in specs.items() if z in zone_ids}


def _rooms(ctx: dict, design, strategy: str | None) -> list[dict]:
    wanted = _wanted(ctx, design.outline, {r.id for r in design.rooms}) if design.outline else {}
    out = []
    for r in design.rooms:
        role = r.type
        template = (HUB_TEMPLATE if role == "HALL" and strategy == "HUB_PRIVATE_WING"
                    else ROOM_TEMPLATES.get(ProgramRole(role)) if role in ProgramRole.__members__
                    else None)
        # `area_m2` on the contract is the NET area, which is what the templates are written against.
        out.append(dict(zone=r.id, role=role, w=r.width_m, d=r.depth_m, area=r.area_m2,
                        t_max=template.max_area_m2 if template else None,
                        wanted=wanted.get(r.id)))
    return out


def run_all():
    recorder = StrategyRecorder()
    recorder.install()
    out = {}
    contexts = distinct_contexts()
    started = time.perf_counter()
    for i, ctx in enumerate(contexts, start=1):
        recorder.reset()
        t = time.perf_counter()
        try:
            res = svc.generate_demo_design(project_from_context(ctx))
            rec = dict(status="PLANNED", sig=[list(s) for s in signature(res.design)],
                       area=res.design.gross_area_m2, asked=ctx["built_area_m2"],
                       validators=res.design.validation.passed,
                       checks_failed=[c for c, ok in res.design.validation.checks.items() if not ok],
                       strategy=recorder.chosen_strategy,
                       rooms=_rooms(ctx, res.design, recorder.chosen_strategy),
                       alternatives=[_rooms(ctx, a, None) for a in res.alternatives])
        except svc.DemoGenerationError as exc:
            rec = dict(status="REFUSED", asked=ctx["built_area_m2"],
                       code=exc.code + ("+outline" if "כן מתאפשר" in exc.message else ""))
            failed = ((getattr(exc, "diagnostics", None) or {}).get("validation") or {}).get("failed_checks") or []
            rec["checks"] = [f"{c['check']}: {c['detail']}" for c in failed]
        except Exception as exc:  # noqa: BLE001
            rec = dict(status="CRASH", asked=ctx["built_area_m2"], code=f"{type(exc).__name__}: {exc}")
        rec["seconds"] = time.perf_counter() - t
        out[key_of(ctx)] = rec
        if i % 100 == 0:
            print(f"  {i}/{len(contexts)}", flush=True)
    recorder.remove()
    print(f"  done in {time.perf_counter() - started:.0f}s", flush=True)
    return out


def _over_max(rooms: list[dict], include_circulation: bool = False) -> list[dict]:
    return [r for r in rooms if r["t_max"] is not None and r["area"] > r["t_max"] + 1e-6
            and (include_circulation or r["role"] not in CIRCULATION)]


def report_one(label: str, run: dict) -> None:
    planned = {k: v for k, v in run.items() if v["status"] == "PLANNED"}
    print(f"\n== {label}: planned {len(planned)}/{len(run)}   crashes {sum(v['status']=='CRASH' for v in run.values())}"
          f"   total {sum(v['seconds'] for v in run.values()):.0f}s   median/scenario {statistics.median(v['seconds'] for v in run.values()):.2f}s")
    over = [(k, r) for k, v in planned.items() for r in _over_max(v["rooms"])]
    over_c = [(k, r) for k, v in planned.items() for r in _over_max(v["rooms"], True)]
    print(f"   primaries with a room above template max: {len({k for k, _ in over})}   rooms above max: {len(over)}"
          f"   (incl. HALL/FLEX: {len(over_c)})")
    by_role = Counter(r["role"] for _, r in over)
    if by_role:
        print("   by role:", dict(by_role))
        worst = max(over, key=lambda kr: kr[1]["area"] / kr[1]["t_max"])[1]
        print(f"   worst: {worst['zone']} {worst['w']}x{worst['d']} = {worst['area']} m2 vs max {worst['t_max']}")
    alt_over = sum(len(_over_max(a)) for v in planned.values() for a in v["alternatives"])
    print(f"   rooms above max in ALTERNATIVES: {alt_over}")
    ratios = [v["area"] / v["asked"] for v in planned.values()]
    if ratios:
        print(f"   delivered/requested: median {statistics.median(ratios):.0%}   under 80 %: {sum(r < 0.8 for r in ratios)}")
    print("   strategies:", dict(Counter(v["strategy"] for v in planned.values())))
    codes = Counter(v.get("code") for v in run.values() if v["status"] == "REFUSED")
    print("   refusals:", dict(codes))
    checks = Counter(c.split(":")[0] for v in run.values() for c in v.get("checks", ()))
    print("   failed checks in refusals:", dict(checks))
    dev = defaultdict(list)
    for v in planned.values():
        for r in v["rooms"]:
            if r["wanted"]:
                dev[r["role"]].append(r["area"] / r["wanted"])
    print("   realized / wanted (scale_program target), median by role:",
          {role: round(statistics.median(x), 2) for role, x in sorted(dev.items())})


def compare(before: dict, after: dict) -> None:
    report_one("BEFORE", before)
    report_one("AFTER", after)
    pre = [k for k, v in before.items() if v["status"] == "PLANNED"]
    now = [k for k, v in after.items() if v["status"] == "PLANNED"]
    same = [k for k in pre if k in now and after[k]["sig"] == before[k]["sig"]]
    changed = [k for k in pre if k in now and after[k]["sig"] != before[k]["sig"]]
    lost = [k for k in pre if k not in now]
    gained = [k for k in now if k not in pre]
    print(f"\n== DELTA: planned {len(pre)} -> {len(now)}   LOST {len(lost)}   GAINED {len(gained)}"
          f"   primaries byte-identical {len(same)}/{len(pre)}   changed {len(changed)}")
    for k in lost:
        c = json.loads(k)
        print(f"   LOST  {c['footprint_width_m']}x{c['footprint_depth_m']} bd={c['bedrooms']} wet={c['wet_rooms']} "
              f"safe={c['safe_room']} open={c['open_plan']} asked {c['built_area_m2']} -> {after[k].get('code')} "
              f"{after[k].get('checks', '')}")
    for k in gained:
        c = json.loads(k); v = after[k]
        print(f"   GAINED {c['footprint_width_m']}x{c['footprint_depth_m']} bd={c['bedrooms']} wet={c['wet_rooms']} "
              f"safe={c['safe_room']} asked {c['built_area_m2']} built {v['area']:.1f} ({v['area']/c['built_area_m2']:.0%}) {v['strategy']}")
    # Where did the area go on the changed primaries? Per role, realized area after minus before.
    moved = defaultdict(float)
    for k in changed:
        b = {r["zone"]: r["area"] for r in before[k]["rooms"]}
        a = {r["zone"]: r["area"] for r in after[k]["rooms"]}
        roles = {r["zone"]: r["role"] for r in after[k]["rooms"]}
        for z in set(a) | set(b):
            moved[roles.get(z, next((r["role"] for r in before[k]["rooms"] if r["zone"] == z), z))] += a.get(z, 0) - b.get(z, 0)
    if changed:
        print("   area moved on changed primaries, net m2 by role (+ receives, - gives):",
              {r: round(x, 1) for r, x in sorted(moved.items(), key=lambda kv: -kv[1])})
        deltas = [(after[k]["area"] - before[k]["area"]) for k in changed]
        print(f"   gross area on changed primaries: median delta {statistics.median(deltas):+.1f} m2, "
              f"min {min(deltas):+.1f}, max {max(deltas):+.1f}")
    lat_pre = [(after[k]["seconds"] - before[k]["seconds"]) for k in pre if k in after]
    print(f"   latency, scenarios planned before: median before {statistics.median(before[k]['seconds'] for k in pre):.2f}s "
          f"-> after {statistics.median(after[k]['seconds'] for k in pre if k in after):.2f}s   worst {max(lat_pre):+.2f}s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save")
    ap.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"))
    args = ap.parse_args()
    if args.save:
        run = run_all()
        json.dump(run, open(args.save, "w"))
        report_one(args.save, run)
    elif args.compare:
        compare(json.load(open(args.compare[0])), json.load(open(args.compare[1])))
    else:
        ap.error("--save or --compare")


if __name__ == "__main__":
    main()
