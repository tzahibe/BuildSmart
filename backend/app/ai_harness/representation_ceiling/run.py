"""R1 (#242) — run both arms over the 19 real plans and state the verdict.

    cd backend && uv run python -m app.ai_harness.representation_ceiling.run <out_dir> [A|B]

Pipeline A (default) is the pre-registered one and carries the verdict; B corrects one conversion
defect (see `convert.convert`) and is reported beside it.

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

from app.vertical_slice.geometry_core.model import m_to_u

from . import frozen
from .convert import ConvertedPlan, ReprRefusal, build_layout, convert, rotate
from .oracle import partition_exists
from .realize import Outcome, realize


#: pipeline -> (doors from every `doors[].room_ids`, snapping tolerance override). A is the
#: pre-registered one and the only one that carries the verdict. B..D are post-run sensitivity
#: analyses, reported beside it and never instead of it: B corrects the door-edge defect; C and D
#: also widen the wall-face snapping (gap/span, metres) to see whether the result depends on the
#: frozen 0.30/0.60.
PIPELINES: dict[str, tuple[bool, tuple[float, float] | None]] = {
    "A": (False, None),
    "B": (True, None),
    "C": (True, (0.60, 1.20)),
    "D": (True, (0.90, 1.80)),
}


@dataclass
class RotationRun:
    deg: int
    outcome: Outcome
    n_cells: int = 0
    n_groups: int = 0
    n_thin: int = 0


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
    n_thin: int = 0                               # cells with a gross short side under 1.0 m
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
        thin = sum(1 for r in layout.cells.values() if min(r.w, r.h) < m_to_u(1.0))
        runs.append(RotationRun(deg, realize(f"{plan_id}:{arm}:{deg}", layout, intents),
                                len(layout.cells), len(layout.groups), thin))
    carried_degs = tuple(r.deg for r in runs if r.outcome.carried)
    pick = next(r for r in runs if r.outcome.carried) if carried_degs else min(runs, key=_rank)
    failing = pick.outcome.failing if pick.outcome.code == "VALIDATION_FAILED" else (
        (pick.outcome.code,) if pick.outcome.code else ())
    return ArmResult(arm, bool(carried_degs), pick.deg, failing, pick.outcome.code, carried_degs,
                     pick.outcome.details, pick.n_cells, pick.n_groups, pick.n_thin, notes.get(pick.deg, []))


def aggregate(results: dict[str, dict[str, ArmResult]]) -> dict:
    out: dict = {}
    for arm in (frozen.ARM_1, frozen.ARM_2, frozen.ARM_2R):
        refused = [r[arm] for r in results.values() if not r[arm].carried]
        fail = Counter(c for r in refused for c in r.failing)
        sole = Counter(r.failing[0] for r in refused if len(r.failing) == 1)
        # How many ROOMS/CELLS each check names across the refused plans (the ';'-separated items of
        # its detail text), and how many of those are cells of a multi-cell room (`ZONE__cN`).
        # Post-run, used only to break the tie in "plans failing the check" (see the report).
        entries: Counter = Counter()
        fragment_entries: Counter = Counter()
        plans_with_whole_room_failure = 0
        for r in refused:
            whole = False
            for chk, det in r.details.items():
                items = [e for e in det.split(";") if e.strip()]
                entries[chk] += len(items)
                fragment_entries[chk] += sum(1 for e in items if "__c" in e)
                whole = whole or any("__c" not in e for e in items)
            plans_with_whole_room_failure += whole
        out[arm] = {
            "carried": sum(1 for r in results.values() if r[arm].carried),
            "refused": len(refused),
            #: ordered by refused plans failing the check; the pre-registered tie-break (plans where it
            #: is the ONLY failing check) is 0 for every check, so ties are ordered by the number of
            #: rooms/cells the check names (post-run, disclosed in the report), then by id
            "plans_failing_check": dict(sorted(fail.items(), key=lambda kv: (-kv[1], -entries[kv[0]], kv[0]))),
            "plans_failing_only_this_check": dict(sorted(sole.items())),
            "entries_named_by_check": dict(sorted(entries.items(), key=lambda kv: (-kv[1], kv[0]))),
            "fragment_entries_named_by_check": dict(sorted(fragment_entries.items())),
            #: refused plans on which at least one check names something that is NOT a cell of a
            #: multi-cell room — plans that stay refused even if every fragment finding were forgiven
            "plans_with_a_whole_room_failure": plans_with_whole_room_failure,
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
        lines.append(f"**{arm}** — carried {a['carried']}/{frozen.N_PLANS}; refused plans that also fail on "
                     f"something that is not a cell of a multi-cell room: {a['plans_with_a_whole_room_failure']}")
        lines.append("")
        lines.append("| check | refused plans failing it | of which sole | rooms/cells it names | of which cells of a multi-cell room |")
        lines.append("|---|---|---|---|---|")
        for k, v in a["plans_failing_check"].items():
            lines.append(f"| {k} | {v} | {a['plans_failing_only_this_check'].get(k, 0)} | "
                         f"{a['entries_named_by_check'].get(k, 0)} | {a['fragment_entries_named_by_check'].get(k, 0)} |")
        lines.append("")
    lines += ["Cells per plan on the reported rotation (a cell under 1.0 m on its short side is 'thin').", "",
              "| plan | arm 1 cells | arm 2 cells / multi-cell rooms / thin | arm 2R cells / multi-cell rooms / thin |",
              "|---|---|---|---|"]
    for pid in results:
        r = results[pid]
        a1, a2, a2r = r[frozen.ARM_1], r[frozen.ARM_2], r[frozen.ARM_2R]
        lines.append(f"| {pid} | {a1.n_cells} | {a2.n_cells} / {a2.n_groups} / {a2.n_thin} "
                     f"| {a2r.n_cells} / {a2r.n_groups} / {a2r.n_thin} |")
    return "\n".join(lines)


def oracle_summary(conv: dict[str, ConvertedPlan | ReprRefusal]) -> dict:
    """Post-run, non-scored: per non-rectangular room, does ANY rectangle partition pass the
    optimistic C20/C9 test (see `oracle.py`)? Rotation-invariant, so run once on the tiling."""
    per_plan: dict[str, dict[str, bool]] = {}
    by_role: dict[str, list[int]] = {}
    for pid, c in conv.items():
        if isinstance(c, ReprRefusal):
            continue
        per_plan[pid] = {}
        for rid in c.non_rectangular_rooms:
            ok = partition_exists(c.rooms[rid], c.roles[rid])
            per_plan[pid][rid] = ok
            tally = by_role.setdefault(c.roles[rid].value, [0, 0])
            tally[0] += 1
            tally[1] += ok
    return {"rooms_by_role": {k: {"non_rectangular": v[0], "some_partition_passes": v[1]} for k, v in sorted(by_role.items())},
            "non_rectangular_total": sum(v[0] for v in by_role.values()),
            "some_partition_passes_total": sum(v[1] for v in by_role.values()),
            "per_plan": per_plan}


def main(out_dir: str, pipeline: str = "A") -> int:
    """Pipeline A is the pre-registered one (the verdict). Pipeline B is A with the one corrected
    conversion defect (doors read from every `doors[].room_ids`), reported beside it, never instead."""
    if pipeline not in PIPELINES:
        raise SystemExit(f"pipeline must be one of {sorted(PIPELINES)}")
    suffix = "" if pipeline == "A" else f"-{pipeline}"
    all_door_pairs, snap = PIPELINES[pipeline]
    plans = frozen.load_real_plans()
    conv = {pid: convert(pid, ref, all_door_pairs=all_door_pairs, snap=snap) for pid, ref in plans.items()}
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
                           "thin_cells": a.n_thin, "layout_notes": a.layout_notes}
                     for arm, a in results[pid].items()}} for pid in results},
    }
    payload["pipeline"] = pipeline
    payload["fragment_oracle"] = oracle_summary(conv)
    print("fragment oracle:", {k: v for k, v in payload["fragment_oracle"].items() if k != "per_plan"})
    (out / f"R1-results{suffix}.json").write_text(json.dumps(payload, indent=1, sort_keys=True))
    md = tables(conv, results, agg)
    (out / f"R1-tables{suffix}.md").write_text(md + "\n")
    print(md)
    print(f"\nVERDICT: {word} — {why}")
    print(f"top blocking check (arm 2): {top}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "r1-out", sys.argv[2] if len(sys.argv) > 2 else "A"))
