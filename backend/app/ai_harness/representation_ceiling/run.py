"""R1 (#242) — run both arms over the 19 real plans and state the verdict.

    cd backend && uv run python -m app.ai_harness.representation_ceiling.run <out_dir>

Per plan and arm: every frozen rotation is tried; the plan is CARRIED when any rotation carries; a
refused plan reports the rotation with the fewest failing checks (validators-ran before
pre-validation codes, then fewest ids, then the smallest rotation). Nothing is retried with a
relaxed constraint, and the verdict is `frozen.verdict` applied to the counts.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import frozen
from .convert import ConvertedPlan, ReprRefusal, build_layout, convert, rotate
from .realize import Outcome, realize


@dataclass
class RotationRun:
    deg: int
    outcome: Outcome
    n_cells: int = 0
    n_groups: int = 0


@dataclass
class ArmResult:
    arm: str
    carried: bool
    reported_deg: int
    failing: tuple[str, ...]                      # check ids, or the single pre-validation code
    code: str | None
    carried_degs: tuple[int, ...]
    details: dict[str, str] = field(default_factory=dict)
    n_cells: int = 0
    n_groups: int = 0
    layout_notes: list[str] = field(default_factory=list)


def _rank(r: RotationRun) -> tuple[int, int, int]:
    ran = 0 if r.outcome.code == "VALIDATION_FAILED" else 1
    n = len(r.outcome.failing) if ran == 0 else 1
    return ran, n, r.deg


def run_arm(plan_id: str, conv: ConvertedPlan | ReprRefusal, arm: str) -> ArmResult:
    if isinstance(conv, ReprRefusal):
        return ArmResult(arm, False, 0, (conv.code,), conv.code, (), {conv.code: conv.detail})
    intents = {z: frozen.zone_intent(z, role) for z, role in conv.roles.items()}
    runs: list[RotationRun] = []
    notes: dict[int, list[str]] = {}
    for deg in frozen.ROTATIONS_DEG:
        layout = build_layout(conv, rotate(conv.rooms, deg), arm)
        if isinstance(layout, ReprRefusal):
            runs.append(RotationRun(deg, Outcome(False, code=layout.code, details={layout.code: layout.detail})))
            continue
        notes[deg] = layout.notes
        runs.append(RotationRun(deg, realize(f"{plan_id}:{arm}:{deg}", layout, intents),
                                len(layout.cells), len(layout.groups)))
    carried_degs = tuple(r.deg for r in runs if r.outcome.carried)
    pick = next(r for r in runs if r.outcome.carried) if carried_degs else min(runs, key=_rank)
    failing = pick.outcome.failing if pick.outcome.code == "VALIDATION_FAILED" else (
        (pick.outcome.code,) if pick.outcome.code else ())
    return ArmResult(arm, bool(carried_degs), pick.deg, failing, pick.outcome.code, carried_degs,
                     pick.outcome.details, pick.n_cells, pick.n_groups, notes.get(pick.deg, []))


def aggregate(results: dict[str, dict[str, ArmResult]]) -> dict:
    out: dict = {}
    for arm in (frozen.ARM_1, frozen.ARM_2, frozen.ARM_2R):
        refused = [r[arm] for r in results.values() if not r[arm].carried]
        fail = Counter(c for r in refused for c in r.failing)
        sole = Counter(r.failing[0] for r in refused if len(r.failing) == 1)
        out[arm] = {
            "carried": sum(1 for r in results.values() if r[arm].carried),
            "refused": len(refused),
            "plans_failing_check": dict(sorted(fail.items(), key=lambda kv: (-kv[1], kv[0]))),
            "plans_failing_only_this_check": dict(sorted(sole.items())),
        }
    return out


def tables(conv: dict[str, ConvertedPlan | ReprRefusal], results: dict[str, dict[str, ArmResult]],
           agg: dict) -> str:
    def cell(a: ArmResult) -> str:
        if a.carried:
            return f"CARRIED (rot {', '.join(map(str, a.carried_degs))})"
        return f"refused: {', '.join(a.failing)} (rot {a.reported_deg})"

    lines = ["| plan | rooms kept / dropped | non-rect rooms | arm 1 | arm 2 | arm 2R (diagnostic) |",
             "|---|---|---|---|---|---|"]
    for pid in results:
        c = conv[pid]
        meta = ("— / —", "—") if isinstance(c, ReprRefusal) else (
            f"{len(c.rooms)} / {len(c.dropped)}", str(len(c.non_rectangular_rooms)))
        r = results[pid]
        lines.append(f"| {pid} | {meta[0]} | {meta[1]} | {cell(r[frozen.ARM_1])} | {cell(r[frozen.ARM_2])} "
                     f"| {cell(r[frozen.ARM_2R])} |")
    lines += ["", "Blocking checks — number of REFUSED plans on which the check fails "
              "(reported rotation); 'sole' = plans where it is the only failing check.", ""]
    for arm in (frozen.ARM_1, frozen.ARM_2, frozen.ARM_2R):
        a = agg[arm]
        lines.append(f"**{arm}** — carried {a['carried']}/{frozen.N_PLANS}")
        lines.append("")
        lines.append("| check | refused plans failing it | of which sole |")
        lines.append("|---|---|---|")
        for k, v in a["plans_failing_check"].items():
            lines.append(f"| {k} | {v} | {a['plans_failing_only_this_check'].get(k, 0)} |")
        lines.append("")
    return "\n".join(lines)


def main(out_dir: str) -> int:
    plans = frozen.load_real_plans()
    conv = {pid: convert(pid, ref) for pid, ref in plans.items()}
    results: dict[str, dict[str, ArmResult]] = {}
    for pid in plans:
        results[pid] = {arm: run_arm(pid, conv[pid], arm) for arm in (frozen.ARM_1, frozen.ARM_2, frozen.ARM_2R)}
        r = results[pid]
        print(pid, {arm: ("CARRIED" if r[arm].carried else ",".join(r[arm].failing)) for arm in r}, flush=True)
    agg = aggregate(results)
    c1, c2 = agg[frozen.ARM_1]["carried"], agg[frozen.ARM_2]["carried"]
    # the four STOP checks are counted per plan on arm 2, refused plans only (a carried plan fails nothing)
    word, why = frozen.verdict(c1, c2, agg[frozen.ARM_2]["plans_failing_check"])
    top = next(iter(agg[frozen.ARM_2]["plans_failing_check"].items()), None)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "verdict": word, "why": why, "arm1_carried": c1, "arm2_carried": c2, "n_plans": frozen.N_PLANS,
        "top_blocking_check_arm2": top, "aggregate": agg,
        "plans": {pid: {
            "conversion": ({"refusal": conv[pid].code, "detail": conv[pid].detail}
                           if isinstance(conv[pid], ReprRefusal) else {
                "rooms": len(conv[pid].rooms), "dropped": conv[pid].dropped, "notes": conv[pid].notes,
                "roles": {k: v.value for k, v in conv[pid].roles.items()},
                "non_rectangular_rooms": conv[pid].non_rectangular_rooms,
                "footprint_area_m2": conv[pid].footprint_area_m2,
                "resplan_footprint_area_m2": conv[pid].resplan_footprint_area_m2,
                "hole_area_m2": conv[pid].hole_area_m2, "access_edges": len(conv[pid].access)}),
            "arms": {arm: {"carried": a.carried, "carried_rotations": list(a.carried_degs),
                           "reported_rotation": a.reported_deg, "failing": list(a.failing), "code": a.code,
                           "details": a.details, "cells": a.n_cells, "groups": a.n_groups,
                           "layout_notes": a.layout_notes}
                     for arm, a in results[pid].items()}} for pid in results},
    }
    (out / "R1-results.json").write_text(json.dumps(payload, indent=1, sort_keys=True))
    md = tables(conv, results, agg)
    (out / "R1-tables.md").write_text(md + "\n")
    print(md)
    print(f"\nVERDICT: {word} — {why}")
    print(f"top blocking check (arm 2): {top}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "r1-out"))
