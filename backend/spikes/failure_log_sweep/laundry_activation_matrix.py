"""Explicit laundry activation matrix (2026-09-16, §5B —
docs/LAUNDRY_ROOM_ACTIVATION_REPORT.md). Requires `LAUNDRY_ROOM_ENABLED` patched on for this run
only (the shipped default stays off until this measurement is clean and the flag is flipped as
its own, separate commit).

    .venv/bin/python3 spikes/failure_log_sweep/laundry_activation_matrix.py

Extends phase-1's `laundry_quality_matrix.py` (same 31-cell matrix: 2/3/4 BR x 1-3 wet x
narrow/wide/deep rectangle footprints, plus a 3BR x {1,2} wet L-parti subset) to measure the
service-first allocation policy (`concept_generator._laundry_deficit_targets`) and the disclosure
notice (`contract.quality_of`'s `laundry_notice`) this activation adds:

- laundry realized area/aspect
- source room(s) of the redistributed area, INCLUDING circulation (phase-1's own matrix excluded
  HALL/CIRCULATION from "regressions" — this one does not, since §1 explicitly asks for a
  circulation delta)
- bathroom/WC area delta specifically (the policy's own first-choice source)
- bedroom/master area AND ASPECT delta (phase-1 only tracked area)
- delivered/effective target vs the baseline (no-laundry) run
- hard-limit failures (a realized room past its template's hard maximum — should be 0 everywhere,
  proving §4's "not cause any other room to fall below hard limits" the other direction too)
- notice frequency and content (`laundry_notice` — new this phase)
- runtime
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.demo import service as svc  # noqa: E402
from app.demo import site_geometry  # noqa: E402
from app.demo.contract import quality_of  # noqa: E402
from app.projects.models import TaggedBool  # noqa: E402
from app.vertical_slice import concept_generator as cg  # noqa: E402
from app.vertical_slice import geometry_fixtures as F  # noqa: E402
from app.vertical_slice.concept_generator import ROOM_TEMPLATES  # noqa: E402
from app.vertical_slice.general_pipeline import run_general_from_site  # noqa: E402
from app.vertical_slice.geometry_core.model import ProgramRole  # noqa: E402
from app.vertical_slice.safe_adapter import AdapterOutcome  # noqa: E402
from app.vertical_slice.spec import LaundryDemand, LaundryRequirement, ProgramSpec  # noqa: E402
from spikes.failure_log_sweep.sweep import project_from_context  # noqa: E402

cg.LAUNDRY_ROOM_ENABLED = True  # this process's measurement run ONLY — never the shipped default

BEDROOMS = (2, 3, 4)
WET_ROOMS = (1, 2, 3)
RECT_FOOTPRINTS = (("narrow", 11.0, 20.0), ("wide", 20.0, 11.0), ("deep", 12.0, 24.0))
L_SITES = (("l_front_arm", F.l_shaped_site_front_arm, (24.0, 28.0)),
          ("l_deep_primary", F.l_shaped_site_deep_primary, (24.0, 32.0)))
AREA_DROP_THRESHOLD = 0.05


def rect_context(bedrooms: int, wet: int, fw: float, fd: float) -> dict:
    return dict(
        plot_width_m=fw + 2 * site_geometry.SIDE_SETBACK_M + 2.0,
        plot_depth_m=fd + site_geometry.FRONT_SETBACK_M + site_geometry.REAR_SETBACK_M + 2.0,
        street_facing_side="NORTH", built_area_m2=round(fw * fd, 2),
        footprint_width_m=fw, footprint_depth_m=fd,
        bedrooms=bedrooms, wet_rooms=wet, safe_room=False, open_plan=True,
    )


def _with_laundry(project, requested: bool):
    return project.model_copy(update={
        "laundry_requested": TaggedBool(value=requested, source="requested" if requested else "inferred"),
        "laundry_source_text": "חדר כביסה" if requested else "",
    })


class _R:
    """One room, normalized to (zone_id, width_m, depth_m, area_m2) regardless of which of the
    two result shapes (`svc.generate_demo_design`'s contract RoomOut, or `run_general_from_site`'s
    design_output RoomOut) produced it."""

    def __init__(self, zone_id, width_m, depth_m, area_m2):
        self.zone_id, self.width_m, self.depth_m, self.area_m2 = zone_id, width_m, depth_m, area_m2

    @property
    def aspect(self):
        return max(self.width_m, self.depth_m) / min(self.width_m, self.depth_m)


def _record_rect(res_or_exc, is_result: bool) -> dict:
    if not is_result:
        exc = res_or_exc
        code = getattr(exc, "code", None) or f"{type(exc).__name__}: {exc}"
        return dict(status="REFUSED" if isinstance(exc, svc.DemoGenerationError) else "CRASH", code=code)
    res = res_or_exc
    rooms_by_role: dict[str, list] = {}
    for r in res.design.rooms:
        rooms_by_role.setdefault(r.type, []).append(_R(r.id, r.width_m, r.depth_m, r.area_m2))
    doors = res.design.doors
    entered = {}
    for role, rs in rooms_by_role.items():
        if role == "LAUNDRY":
            r = rs[0]
            entered[role] = sorted({d.a if d.b == r.zone_id else d.b for d in doors if r.zone_id in (d.a, d.b)})
    return dict(status="PLANNED", area=res.design.gross_area_m2, rooms_by_role=rooms_by_role,
               laundry_access=entered.get("LAUNDRY"), validators=res.design.validation.passed,
               notice=res.design.quality.laundry_notice if res.design.quality else None)


def run_pair_rect(build) -> tuple[dict, dict]:
    out = []
    for requested in (False, True):
        project = build(requested)
        t = time.perf_counter()
        try:
            res = svc.generate_demo_design(project)
            rec = _record_rect(res, True)
        except (svc.DemoGenerationError, Exception) as exc:  # noqa: BLE001
            rec = _record_rect(exc, False)
        rec["seconds"] = time.perf_counter() - t
        out.append(rec)
    return out[0], out[1]


def run_one_L(site_fn, plot, program) -> dict:
    t = time.perf_counter()
    try:
        res = run_general_from_site(site_fn(), plot_size_m=plot, program=program)
        if res.outcome is not AdapterOutcome.SOLVED:
            rec = dict(status="REFUSED", code=str(res.notes))
        else:
            zones = {z.zone_id: z for z in res.concept.concept.fixture.zones}
            rooms_by_role: dict[str, list] = {}
            for r in res.design.rooms:
                role = zones[r.zone_id].primary_role.value if r.zone_id in zones else r.roles[0]
                rooms_by_role.setdefault(role, []).append(_R(r.zone_id, r.net_w_m, r.net_h_m, r.net_area_m2))
            doors = res.design.interior_doors
            entered = None
            if "LAUNDRY" in rooms_by_role:
                r = rooms_by_role["LAUNDRY"][0]
                entered = sorted({d.a if d.b == r.zone_id else d.b for d in doors if r.zone_id in (d.a, d.b)})
            rec = dict(status="PLANNED", area=res.design.gross_area_m2, rooms_by_role=rooms_by_role,
                      laundry_access=entered, validators=res.validation.ok,
                      notice=quality_of(res.design).laundry_notice)
    except Exception as exc:  # noqa: BLE001
        rec = dict(status="CRASH", code=f"{type(exc).__name__}: {exc}")
    rec["seconds"] = time.perf_counter() - t
    return rec


def laundry_geometry(with_rec: dict) -> dict | None:
    rooms = with_rec.get("rooms_by_role", {}).get("LAUNDRY")
    if not rooms:
        return None
    r = rooms[0]
    template = ROOM_TEMPLATES[ProgramRole.LAUNDRY]
    return dict(area=r.area_m2, aspect=r.aspect, short_side=min(r.width_m, r.depth_m),
               access=with_rec.get("laundry_access"),
               within_template=(r.aspect <= template.max_aspect_ratio + 1e-6
                                and r.area_m2 <= template.hard_max + 1e-6))


def deltas(none_rec: dict, with_rec: dict) -> dict[str, dict]:
    """Every role present in both runs: area before/after, aspect before/after (area-weighted mean
    aspect when a role has more than one room), and whether it counts as a "regression" (>5%
    area drop). LAUNDRY excluded (that is the requested room, not a "source"); everything else,
    circulation included, is in scope this time."""
    a, b = none_rec.get("rooms_by_role", {}), with_rec.get("rooms_by_role", {})
    out = {}
    for role in set(a) & set(b):
        if role == "LAUNDRY":
            continue
        area_a, area_b = sum(r.area_m2 for r in a[role]), sum(r.area_m2 for r in b[role])
        aspect_a = sum(r.aspect * r.area_m2 for r in a[role]) / area_a if area_a else 0.0
        aspect_b = sum(r.aspect * r.area_m2 for r in b[role]) / area_b if area_b else 0.0
        out[role] = dict(area_before=area_a, area_after=area_b, aspect_before=aspect_a, aspect_after=aspect_b,
                         regression=area_a > 0 and (area_a - area_b) / area_a > AREA_DROP_THRESHOLD)
    return out


def hard_limit_violations(with_rec: dict) -> list[str]:
    if with_rec["status"] != "PLANNED":
        return []
    bad = []
    for role, rooms in with_rec["rooms_by_role"].items():
        t = ROOM_TEMPLATES.get(ProgramRole(role)) if role in ProgramRole.__members__ else None
        if t is None:
            continue
        for r in rooms:
            if r.area_m2 > t.hard_max + 0.05:
                bad.append(f"{role} {r.area_m2:.2f} > hard max {t.hard_max:.2f}")
    return bad


def main() -> None:
    rows = []
    started = time.perf_counter()

    for b in BEDROOMS:
        for w in WET_ROOMS:
            for label, fw, fd in RECT_FOOTPRINTS:
                ctx = rect_context(b, w, fw, fd)
                base = project_from_context(ctx)
                none_rec, with_rec = run_pair_rect(lambda req: _with_laundry(base, req))
                rows.append(dict(shape="rect", label=label, bedrooms=b, wet=w, none=none_rec, withl=with_rec,
                                 laundry=laundry_geometry(with_rec) if with_rec["status"] == "PLANNED" else None,
                                 deltas=(deltas(none_rec, with_rec)
                                        if none_rec["status"] == "PLANNED" and with_rec["status"] == "PLANNED"
                                        else {}),
                                 hard_violations=hard_limit_violations(with_rec)))
        print(f"  rect {b}BR done ({time.perf_counter() - started:.0f}s)", flush=True)

    for name, site_fn, plot in L_SITES:
        for w in (1, 2):
            def program_for(req, _w=w, _plot=plot):
                return ProgramSpec(bedrooms=3, safe_room=False, wet_rooms=_w, open_plan_living=True,
                                   target_built_area_m2=round(_plot[0] * _plot[1] * 0.55, 1),
                                   laundry=LaundryRequirement(
                                       demand=LaundryDemand.ROOM if req else LaundryDemand.NONE,
                                       source_text="חדר כביסה" if req else ""))
            none_rec = run_one_L(site_fn, plot, program_for(False))
            with_rec = run_one_L(site_fn, plot, program_for(True))
            rows.append(dict(shape="L", label=name, bedrooms=3, wet=w, none=none_rec, withl=with_rec,
                             laundry=laundry_geometry(with_rec) if with_rec["status"] == "PLANNED" else None,
                             deltas=(deltas(none_rec, with_rec)
                                    if none_rec["status"] == "PLANNED" and with_rec["status"] == "PLANNED"
                                    else {}),
                             hard_violations=hard_limit_violations(with_rec)))
        print(f"  L {name} done ({time.perf_counter() - started:.0f}s)", flush=True)

    print(f"\ntotal {time.perf_counter() - started:.0f}s, {len(rows)} cells\n")

    planned_none = sum(1 for r in rows if r["none"]["status"] == "PLANNED")
    planned_with = sum(1 for r in rows if r["withl"]["status"] == "PLANNED")
    newly_refused = [r for r in rows if r["none"]["status"] == "PLANNED" and r["withl"]["status"] != "PLANNED"]
    print(f"planned: NONE={planned_none}/{len(rows)}  ROOM={planned_with}/{len(rows)}")
    print(f"newly refused BECAUSE of the laundry request: {len(newly_refused)}")
    for r in newly_refused:
        print(f"  {r['shape']} {r['label']} {r['bedrooms']}BR/{r['wet']}wet -> {r['withl']['code']}")

    with_geom = [r for r in rows if r["laundry"] is not None]
    print(f"\nlaundry realized in {len(with_geom)}/{planned_with} planned+requested cells")
    off_template = [r for r in with_geom if not r["laundry"]["within_template"]]
    non_hall = [r for r in with_geom if r["laundry"]["access"] != ["HALL"]]
    print(f"outside template bounds (should be 0): {len(off_template)}")
    print(f"not HALL-only access (should be 0): {len(non_hall)}")

    all_hard_violations = [r for r in rows if r["hard_violations"]]
    print(f"\nhard-limit violations (should be 0): {len(all_hard_violations)}")
    for r in all_hard_violations:
        print(f"  {r['shape']} {r['label']} {r['bedrooms']}BR/{r['wet']}wet: {r['hard_violations']}")

    print(f"\n{'shape':6} {'foot':14} {'bd':3} {'wet':4} {'laundry m2':>10} {'aspect':>7}")
    for r in with_geom:
        g = r["laundry"]
        print(f"{r['shape']:6} {r['label']:14} {r['bedrooms']:3} {r['wet']:4} {g['area']:10.2f} {g['aspect']:7.2f}")

    print("\n=== source of redistributed area, by role (aggregated) ===")
    by_role_delta: dict[str, list[float]] = {}
    regressed_cells = 0
    for r in rows:
        if not r["deltas"]:
            continue
        if any(d["regression"] for d in r["deltas"].values()):
            regressed_cells += 1
        for role, d in r["deltas"].items():
            by_role_delta.setdefault(role, []).append(d["area_before"] - d["area_after"])
    for role, diffs in sorted(by_role_delta.items(), key=lambda kv: -sum(kv[1])):
        group = ("wet/service" if role in ("BATHROOM", "TOILET") else
                "circulation" if role in ("HALL", "CIRCULATION") else
                "private" if role in ("MASTER_BEDROOM", "BEDROOM", "SAFE_ROOM") else "public")
        print(f"  {role:16s} ({group:12s}) total {sum(diffs):+7.1f} m2 over {len(diffs)} cells, "
              f"median {sorted(diffs)[len(diffs)//2]:+6.2f} m2")
    print(f"cells with >{AREA_DROP_THRESHOLD:.0%} regression somewhere: {regressed_cells}/"
          f"{sum(1 for r in rows if r['deltas'])}")

    print("\n=== bedroom/master aspect delta (where regressed) ===")
    for r in rows:
        for role in ("BEDROOM", "MASTER_BEDROOM"):
            d = r["deltas"].get(role)
            if d and d["regression"]:
                print(f"  {r['shape']} {r['label']} {r['bedrooms']}BR/{r['wet']}wet: {role} "
                      f"area {d['area_before']:.1f}->{d['area_after']:.1f}  "
                      f"aspect {d['aspect_before']:.2f}->{d['aspect_after']:.2f}")

    print("\n=== circulation (HALL) delta ===")
    for r in rows:
        d = r["deltas"].get("HALL")
        if d:
            pct = 100 * (d["area_before"] - d["area_after"]) / d["area_before"] if d["area_before"] else 0
            print(f"  {r['shape']} {r['label']} {r['bedrooms']}BR/{r['wet']}wet: "
                  f"{d['area_before']:.2f} -> {d['area_after']:.2f} m2 ({pct:+.0f}%)")

    with_notice = [r for r in rows if r["withl"].get("notice")]
    print(f"\n=== disclosure notice ===\nfired in {len(with_notice)}/{planned_with} planned+requested cells")
    for r in with_notice:
        print(f"  {r['shape']} {r['label']} {r['bedrooms']}BR/{r['wet']}wet: {r['withl']['notice']}")
    silent_regressions = [r for r in rows if r["deltas"] and any(d["regression"] for d in r["deltas"].values())
                          and not r["withl"].get("notice")]
    print(f"cells with a >{AREA_DROP_THRESHOLD:.0%} regression but NO notice: {len(silent_regressions)}")
    for r in silent_regressions:
        print(f"  {r['shape']} {r['label']} {r['bedrooms']}BR/{r['wet']}wet")

    print(f"\nruntime: NONE median {sorted(r['none']['seconds'] for r in rows)[len(rows)//2]:.2f}s  "
          f"ROOM median {sorted(r['withl']['seconds'] for r in rows)[len(rows)//2]:.2f}s")


if __name__ == "__main__":
    main()
