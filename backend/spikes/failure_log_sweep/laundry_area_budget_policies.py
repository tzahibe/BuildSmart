"""Laundry area-budget product decision — MEASUREMENT ONLY, no production code touched.

    .venv/bin/python3 spikes/failure_log_sweep/laundry_area_budget_policies.py

`docs/LAUNDRY_ROOM_PHASE1_REPORT.md` §4 found that a requested, planned laundry room takes its
area from the rest of the programme under the SHIPPED allocator (`concept_generator.scale_program`)
— nearly every cell that planned with laundry saw another room shrink >5%. This script investigates
WHERE that area comes from today and compares three alternative allocation policies plus a refusal
policy, entirely by monkeypatching `cg.scale_program` for the duration of one measurement run —
`app/` is never edited, `LAUNDRY_ROOM_ENABLED` is patched `True` in THIS PROCESS only, and nothing
here is wired into the shipped pipeline.

POLICIES (see the report for the full definitions and results):
  C — CURRENT/SHIPPED. `scale_program` unmodified: an initial UNIFORM proportional shrink (every
      room loses the same % of its own target) then a residue pass that pushes any leftover
      correction onto elastic rooms (FLEX heaviest, elasticity 5.0) — a hybrid, not a pure "FLEX
      first" or a pure "proportional" policy, which is exactly why the phase-1 data showed BOTH
      "FLEX absorbs the most" AND "other rooms still lose 10-35%".
  A — FLEX-FIRST. The deficit is taken from FLEX alone, down to FLEX's own floor, before any other
      room is touched at all. Only the remainder (if FLEX cannot cover it) cascades, proportionally,
      to every other room. Zero collateral damage whenever FLEX alone can absorb the gap.
  B — SERVICE-FIRST. The deficit is taken from the OTHER service/wet rooms (BATHROOM/TOILET) first,
      proportional to each one's own headroom above its floor, before PUBLIC/PRIVATE rooms are
      touched. Models "the wet/service zone absorbs its own new sibling's cost."
  D — REFUSE/CLARIFY. Not a new allocator: takes policy C's (shipped) result and reclassifies it as
      a refusal whenever any OTHER room's ALLOCATED target (not just the realized rectangle) would
      drop by more than `DEGRADATION_REFUSE_THRESHOLD` from its own no-laundry target — i.e. an
      honest refusal instead of a silently degraded plan, mirroring this codebase's own established
      "an honest refusal beats a plan at half the size" policy for area shortfalls generally.

Every policy is evaluated on the SAME `target_built_area_m2` as the no-laundry baseline — none of
them invent extra built area — and every policy floors every room at `RoomTemplate.min_area_m2`
(`floor_of`, verbatim from `scale_program`) — none of them can shrink a room below its existing
minimum.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.demo import service as svc  # noqa: E402
from app.demo import site_geometry  # noqa: E402
from app.projects.models import TaggedBool  # noqa: E402
from app.vertical_slice import concept_generator as cg  # noqa: E402
from app.vertical_slice.concept_generator import ROOM_TEMPLATES, ZoneGroup  # noqa: E402
from app.vertical_slice.geometry_core.model import ProgramRole, ZoneSpec  # noqa: E402
from app.vertical_slice.spec import LaundryDemand, LaundryRequirement, ProgramSpec  # noqa: E402
from spikes.failure_log_sweep.sweep import project_from_context  # noqa: E402

cg.LAUNDRY_ROOM_ENABLED = True  # this process's measurement run ONLY — never the shipped default

SHIPPED_SCALE_PROGRAM = cg.scale_program

#: A room's allocated target must not fall more than this fraction below its own NO-LAUNDRY target
#: before Policy D calls it a refusal. Proposed for this measurement, not a discovered constant —
#: chosen for symmetry with `OVER_PREFERRED_SIGNAL_RATIO`'s 10% granularity (the analogous
#: ABOVE-target quality bar already shipped). The report shows the full degradation distribution so
#: a different threshold can be re-read directly from the same run.
DEGRADATION_REFUSE_THRESHOLD = 0.10


# --------------------------------------------------------------------------- shared helpers


def _floor_of(room, floors: dict[str, float]) -> float:
    return max(room.template.min_area_m2, floors.get(room.zone_id, 0.0))


def _specs_from_targets(rooms, targets: dict[str, float], floors: dict[str, float]) -> dict[str, ZoneSpec]:
    """Verbatim tail of `scale_program` (the ZoneSpec construction, incl. the headroom band) —
    every policy shares this; only how `targets` was computed differs."""
    specs: dict[str, ZoneSpec] = {}
    for room in rooms:
        t = room.template
        target = targets[room.zone_id]
        roles = (room.role,) if room.role is not ProgramRole.HALL else (
            ProgramRole.HALL, ProgramRole.CIRCULATION)
        specs[room.zone_id] = ZoneSpec(
            zone_id=room.zone_id, roles=roles,
            net_area_min_m2=max(_floor_of(room, floors), target * 0.70),
            net_area_target_m2=target,
            net_area_max_m2=max(min(target * cg._expansion_headroom_mult(t.elasticity), t.max_area_m2), target),
            min_short_side_m=t.min_short_side_m, max_aspect_ratio=t.max_aspect_ratio,
        )
    return specs


def _surplus_targets(rooms, net_available_m2: float, floors: dict[str, float],
                     starts: dict[str, float]) -> dict[str, float]:
    """Verbatim shipped surplus-growth branch (`scale_program`'s `if surplus >= 0`) — every policy
    below shares this; the policies differ ONLY in how a DEFICIT is distributed, since a surplus
    scenario has nothing to "protect" a room from."""
    surplus = net_available_m2 - sum(starts.values())
    weight_total = sum(r.template.elasticity for r in rooms) or 1.0
    targets = {}
    for r in rooms:
        extra = surplus * (r.template.elasticity / weight_total)
        targets[r.zone_id] = max(starts[r.zone_id], min(starts[r.zone_id] + extra,
                                                         max(r.template.max_area_m2, starts[r.zone_id])))
    return targets


def _starts_and_base(rooms, floors: dict[str, float]) -> tuple[dict[str, float], float]:
    starts = {r.zone_id: max(r.template.target_area_m2, _floor_of(r, floors)) for r in rooms}
    return starts, sum(starts.values())


# --------------------------------------------------------------------------- policy C (shipped)

policy_c_current = SHIPPED_SCALE_PROGRAM


# --------------------------------------------------------------------------- policy A: FLEX-first


def policy_a_flex_first(rooms, net_available_m2, area_floors=None):
    floors = area_floors or {}
    starts, base = _starts_and_base(rooms, floors)
    surplus = net_available_m2 - base
    if surplus >= 0:
        return _specs_from_targets(rooms, _surplus_targets(rooms, net_available_m2, floors, starts), floors)

    deficit = -surplus
    targets = dict(starts)
    flex = next((r for r in rooms if r.role is ProgramRole.FLEX), None)
    if flex is not None:
        take = min(deficit, starts[flex.zone_id] - _floor_of(flex, floors))
        targets[flex.zone_id] = starts[flex.zone_id] - take
        deficit -= take
    if deficit > 1e-9:
        others = [r for r in rooms if flex is None or r.zone_id != flex.zone_id]
        other_base = sum(starts[r.zone_id] for r in others)
        for r in others:
            share = deficit * (starts[r.zone_id] / other_base) if other_base > 0 else 0.0
            targets[r.zone_id] = max(starts[r.zone_id] - share, _floor_of(r, floors))
    return _specs_from_targets(rooms, targets, floors)


# --------------------------------------------------------------------------- policy B: service-first


def policy_b_service_first(rooms, net_available_m2, area_floors=None):
    floors = area_floors or {}
    starts, base = _starts_and_base(rooms, floors)
    surplus = net_available_m2 - base
    if surplus >= 0:
        return _specs_from_targets(rooms, _surplus_targets(rooms, net_available_m2, floors, starts), floors)

    deficit = -surplus
    targets = dict(starts)
    service = [r for r in rooms if r.group is ZoneGroup.SERVICE and r.role is not ProgramRole.LAUNDRY]
    service_capacity = sum(starts[r.zone_id] - _floor_of(r, floors) for r in service)
    take = min(deficit, service_capacity)
    if take > 0 and service_capacity > 0:
        for r in service:
            headroom = starts[r.zone_id] - _floor_of(r, floors)
            targets[r.zone_id] = starts[r.zone_id] - take * (headroom / service_capacity)
    deficit -= take
    if deficit > 1e-9:
        others = [r for r in rooms if r not in service]
        other_base = sum(starts[r.zone_id] for r in others)
        for r in others:
            share = deficit * (starts[r.zone_id] / other_base) if other_base > 0 else 0.0
            targets[r.zone_id] = max(starts[r.zone_id] - share, _floor_of(r, floors))
    return _specs_from_targets(rooms, targets, floors)


POLICIES = {"C_current": policy_c_current, "A_flex_first": policy_a_flex_first,
           "B_service_first": policy_b_service_first}


# --------------------------------------------------------------------------- representative cases


def _footprint_tiers(bedrooms: int, wet: int) -> dict[str, float]:
    """tight = the programme's own natural (no-surplus) gross area at every room's OWN target;
    generous = +25% (still, per `program_capacity_gross_m2` below, nowhere near enough to trigger
    a FLEX zone — every room's template ALLOWS growing much further before FLEX ever appears);
    flex_present = just above `program_capacity_gross_m2` (every room already at its own PREFERRED
    maximum), the actual threshold `generate_concepts` uses to add a FLEX zone at all. Reported
    here as its own tier because Policy A ("FLEX-first") is a no-op without one — see the report.
    `LAUNDRY_ROOM_ENABLED` is on but `laundry=NONE` here on purpose — this is the baseline
    programme's OWN footprint, before the request that creates the policy question."""
    from app.vertical_slice.concept_generator import (
        build_room_program, program_capacity_gross_m2, target_gross_area_m2,
    )
    from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec
    program = ProgramSpec(bedrooms=bedrooms, safe_room=False, wet_rooms=wet, open_plan_living=True)
    rooms = build_room_program(ArchitecturalSpec(plot=PlotSpec(20.0, 24.0), program=program))
    tight = target_gross_area_m2(rooms)
    capacity = program_capacity_gross_m2(rooms)
    return {"tight": round(tight, 1), "generous": round(tight * 1.25, 1),
           "flex_present": round(capacity * 1.05, 1)}


def _context(bedrooms: int, wet: int, built_area_m2: float) -> dict:
    aspect = 0.82  # `_FOOTPRINT_ASPECT_PREF`, this codebase's own preferred width:depth ratio
    fd = (built_area_m2 / aspect) ** 0.5
    fw = built_area_m2 / fd
    return dict(
        plot_width_m=fw + 2 * site_geometry.SIDE_SETBACK_M + 2.0,
        plot_depth_m=fd + site_geometry.FRONT_SETBACK_M + site_geometry.REAR_SETBACK_M + 2.0,
        street_facing_side="NORTH", built_area_m2=round(built_area_m2, 2),
        footprint_width_m=round(fw, 2), footprint_depth_m=round(fd, 2),
        bedrooms=bedrooms, wet_rooms=wet, safe_room=False, open_plan=True,
    )


CASES = [  # (label, bedrooms, wet_rooms)
    ("2BR/1wet", 2, 1),
    ("3BR/2wet", 3, 2),
    ("4BR/2wet", 4, 2),
]


def _with_laundry(project, requested: bool):
    return project.model_copy(update={
        "laundry_requested": TaggedBool(value=requested, source="requested" if requested else "inferred"),
        "laundry_source_text": "חדר כביסה" if requested else "",
    })


def _run(project) -> dict:
    t = time.perf_counter()
    try:
        res = svc.generate_demo_design(project)
        rooms_by_role: dict[str, list] = {}
        for r in res.design.rooms:
            rooms_by_role.setdefault(r.type, []).append(r)
        rec = dict(status="PLANNED", area=res.design.gross_area_m2, rooms_by_role=rooms_by_role,
                  doors=res.design.doors, validators=res.design.validation.passed)
    except svc.DemoGenerationError as exc:
        rec = dict(status="REFUSED", code=exc.code)
    except Exception as exc:  # noqa: BLE001
        rec = dict(status="CRASH", code=f"{type(exc).__name__}: {exc}")
    rec["seconds"] = time.perf_counter() - t
    return rec


def _room_areas(rec: dict) -> dict[str, float]:
    if rec["status"] != "PLANNED":
        return {}
    return {role: sum(r.area_m2 for r in rs) for role, rs in rec["rooms_by_role"].items()}


def _laundry_geom(rec: dict) -> dict | None:
    rooms = rec.get("rooms_by_role", {}).get("LAUNDRY")
    if not rooms:
        return None
    r = rooms[0]
    aspect = max(r.width_m, r.depth_m) / min(r.width_m, r.depth_m)
    entered = sorted({d.a if d.b == r.id else d.b for d in rec["doors"] if r.id in (d.a, d.b)})
    return dict(area=r.area_m2, aspect=aspect, short_side=min(r.width_m, r.depth_m), access=entered)


def _hard_limit_violations(rec: dict) -> list[str]:
    if rec["status"] != "PLANNED":
        return []
    bad = []
    for role, rooms in rec["rooms_by_role"].items():
        t = ROOM_TEMPLATES.get(ProgramRole(role)) if role in ProgramRole._value2member_map_ else None
        if t is None:
            continue
        for r in rooms:
            if r.area_m2 > t.hard_max + 0.05:
                bad.append(f"{role} {r.area_m2:.2f} > hard max {t.hard_max:.2f}")
    return bad


# --------------------------------------------------------------------------- main


def main() -> None:
    rows = []
    started = time.perf_counter()
    for label, bedrooms, wet in CASES:
        tiers = _footprint_tiers(bedrooms, wet)
        for tag, target in tiers.items():
            ctx = _context(bedrooms, wet, target)
            base_project = project_from_context(ctx)
            baseline = _run(_with_laundry(base_project, False))
            baseline_areas = _room_areas(baseline)
            for policy_name, policy_fn in POLICIES.items():
                cg.scale_program = policy_fn
                rec = _run(_with_laundry(base_project, True))
                cg.scale_program = SHIPPED_SCALE_PROGRAM
                areas = _room_areas(rec)
                changes = {role: (baseline_areas[role], areas[role])
                          for role in set(baseline_areas) & set(areas)
                          if role not in ("LAUNDRY",) and baseline_areas[role] > 0
                          and abs(areas[role] - baseline_areas[role]) / baseline_areas[role] > 0.01}
                rows.append(dict(
                    case=label, tag=tag, target=target, policy=policy_name,
                    baseline_status=baseline["status"], status=rec["status"],
                    code=rec.get("code"), laundry=_laundry_geom(rec), changes=changes,
                    hard_violations=_hard_limit_violations(rec),
                    delivered_area=rec.get("area"), baseline_area=baseline.get("area"),
                    seconds=rec["seconds"],
                ))
        print(f"  {label} done ({time.perf_counter() - started:.0f}s)", flush=True)

    print(f"\ntotal {time.perf_counter() - started:.0f}s, {len(rows)} (case x tag x policy) cells\n")

    # ---- table 1: where does the laundry area come from (per policy, aggregated) ----
    print("=== where the laundry area comes from, by policy (aggregated over all cases) ===")
    for policy_name in POLICIES:
        prows = [r for r in rows if r["policy"] == policy_name and r["status"] == "PLANNED"]
        if not prows:
            continue
        by_role_drop: dict[str, float] = {}
        for r in prows:
            for role, (a, b) in r["changes"].items():
                by_role_drop[role] = by_role_drop.get(role, 0.0) + (a - b)
        total_drop = sum(v for v in by_role_drop.values() if v > 0)
        print(f"\n{policy_name}: total area lost across other rooms (summed over {len(prows)} planned cells): "
              f"{total_drop:.1f} m2")
        for role, drop in sorted(by_role_drop.items(), key=lambda kv: -kv[1]):
            group = ("wet/service" if role in ("BATHROOM", "TOILET") else
                    "private" if role in ("MASTER_BEDROOM", "BEDROOM", "SAFE_ROOM") else
                    "circulation" if role in ("HALL", "CIRCULATION") else
                    "FLEX/surplus" if role == "FLEX" else "public")
            print(f"    {role:16s} ({group:12s}) {drop:+7.1f} m2 total")

    # ---- table 2: per-case, per-policy summary ----
    print("\n=== per case / tag / policy ===")
    print(f"{'case':10} {'tag':9} {'policy':16} {'status':10} {'laundry m2':>10} {'aspect':>7} "
          f"{'delivered':>10} {'#rooms changed':>15} {'worst drop %':>13} {'hard viol':>10}")
    for r in rows:
        lg = r["laundry"]
        l_area = f"{lg['area']:.2f}" if lg else "-"
        l_asp = f"{lg['aspect']:.2f}" if lg else "-"
        worst = max((100 * (a - b) / a for a, b in r["changes"].values()), default=0.0)
        print(f"{r['case']:10} {r['tag']:9} {r['policy']:16} {r['status']:10} {l_area:>10} {l_asp:>7} "
              f"{r['delivered_area'] or 0:>10.1f} {len(r['changes']):>15} {worst:>12.1f}% "
              f"{len(r['hard_violations']):>10}")

    # ---- table 3: refusals and hard-limit violations ----
    refused = [r for r in rows if r["status"] != "PLANNED" and r["baseline_status"] == "PLANNED"]
    print(f"\nnewly refused/crashed (baseline planned, this policy did not): {len(refused)}")
    for r in refused:
        print(f"  {r['case']} {r['tag']} {r['policy']}: {r['status']}/{r['code']}")
    hard = [r for r in rows if r["hard_violations"]]
    print(f"\nhard-limit violations found: {len(hard)}")
    for r in hard:
        print(f"  {r['case']} {r['tag']} {r['policy']}: {r['hard_violations']}")

    # ---- table 4: Policy D (refuse/clarify) applied to Policy C's results ----
    print(f"\n=== Policy D — reclassify Policy C's results at >{DEGRADATION_REFUSE_THRESHOLD:.0%} degradation ===")
    c_rows = [r for r in rows if r["policy"] == "C_current" and r["status"] == "PLANNED"]
    d_refused = [r for r in c_rows
                if any((a - b) / a > DEGRADATION_REFUSE_THRESHOLD for a, b in r["changes"].values())]
    print(f"of {len(c_rows)} cells Policy C planned, Policy D would refuse: {len(d_refused)}")
    for r in d_refused:
        worst_role, (a, b) = max(r["changes"].items(), key=lambda kv: (kv[1][0] - kv[1][1]) / kv[1][0])
        print(f"  {r['case']} {r['tag']}: {worst_role} {a:.1f} -> {b:.1f} m2 "
              f"({100*(b-a)/a:+.0f}%) would trigger refusal")


if __name__ == "__main__":
    main()
