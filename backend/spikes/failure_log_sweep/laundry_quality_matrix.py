"""Synthetic quality matrix for a requested, PLANNED laundry room (phase 1, §7B —
docs/LAUNDRY_ROOM_OPTION_REVIEW.md). Requires `LAUNDRY_ROOM_ENABLED` patched on for this run only
(the shipped default stays off; see `laundry_gate_ab.py` for the regression side of the phase).

    .venv/bin/python3 spikes/failure_log_sweep/laundry_quality_matrix.py

For each (bedrooms x wet_rooms x footprint) cell, plans the SAME brief twice — laundry NONE and
ROOM, same target area — through the real service (`generate_demo_design`), and reports: planned/
refused for each; the laundry room's realized area/aspect/short side/access (WITH); whether any
OTHER room's area drops materially (>5%) between the two runs, the signal for "laundry crowded out
a bedroom"; and runtime. A rectangle grid (2/3/4 BR x 1-3 wet x narrow/wide/deep footprints) plus a
smaller L-parti subset, matching this repo's own L-site fixtures and their bedroom-count intent
(`geometry_fixtures.l_shaped_site*`, exercised at 3BR per `tests/vertical_slice/test_l_parti.py`).
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
from app.vertical_slice import geometry_fixtures as F  # noqa: E402
from app.vertical_slice.concept_generator import ROOM_TEMPLATES  # noqa: E402
from app.vertical_slice.general_pipeline import run_general_from_site  # noqa: E402
from app.vertical_slice.geometry_core.model import ProgramRole  # noqa: E402
from app.vertical_slice.safe_adapter import AdapterOutcome  # noqa: E402
from app.vertical_slice.spec import LaundryDemand, LaundryRequirement, ProgramSpec  # noqa: E402
from spikes.failure_log_sweep.sweep import project_from_context  # noqa: E402

cg.LAUNDRY_ROOM_ENABLED = True  # this process's measurement run ONLY — never the shipped default


class _NormalizedRoom:
    """The L-branch runs through `run_general_from_site` (design_output.py's `RoomOut`: `zone_id`,
    `net_w_m`/`net_h_m`/`net_area_m2`) while the rect branch runs through the real service
    (contract.py's `RoomOut`: `id`, `width_m`/`depth_m`/`area_m2`) — same shape, different field
    names. Normalized once here so `laundry_geometry`/`area_regressions` read one shape."""

    def __init__(self, id_: str, width_m: float, depth_m: float, area_m2: float):
        self.id, self.width_m, self.depth_m, self.area_m2 = id_, width_m, depth_m, area_m2

BEDROOMS = (2, 3, 4)
WET_ROOMS = (1, 2, 3)
#: (label, width, depth) — narrow/wide/deep variants around the same ~220-240 m2 order of
#: magnitude as `envelope.py`'s log-typical footprints, biased to the three named shapes.
RECT_FOOTPRINTS = (("narrow", 11.0, 20.0), ("wide", 20.0, 11.0), ("deep", 12.0, 24.0))
#: 3BR only, matching this repo's own L-parti fixtures/tests (`test_l_parti.py`): the L sites were
#: authored and measured at 3BR, and "where applicable" for laundry means exactly that subset.
L_SITES = (("l_front_arm", F.l_shaped_site_front_arm, (24.0, 28.0)),
          ("l_deep_primary", F.l_shaped_site_deep_primary, (24.0, 32.0)))
AREA_DROP_THRESHOLD = 0.05  # 5%: "materially worse" for another room's area


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


def _record(res_or_exc, is_result: bool) -> dict:
    if not is_result:
        exc = res_or_exc
        code = getattr(exc, "code", None) or f"{type(exc).__name__}: {exc}"
        return dict(status="REFUSED" if isinstance(exc, svc.DemoGenerationError) else "CRASH", code=code)
    res = res_or_exc
    # `DemoDesign.rooms` (app/demo/contract.py's `RoomOut`) already carries `type` as the flat
    # role string (`type=r.roles[0]` at construction) — no zones lookup needed at this layer.
    rooms_by_role: dict[str, list] = {}
    for r in res.design.rooms:
        rooms_by_role.setdefault(r.type, []).append(r)
    return dict(status="PLANNED", area=res.design.gross_area_m2,
               rooms_by_role=rooms_by_role, doors=res.design.doors,
               validators=res.design.validation.passed)


def run_pair(build) -> tuple[dict, dict]:
    """`build(laundry_requested: bool) -> Project`. Runs NONE then ROOM, each timed."""
    out = []
    for requested in (False, True):
        project = build(requested)
        t = time.perf_counter()
        try:
            res = svc.generate_demo_design(project)
            rec = _record(res, True)
        except (svc.DemoGenerationError, Exception) as exc:  # noqa: BLE001
            rec = _record(exc, False)
        rec["seconds"] = time.perf_counter() - t
        out.append(rec)
    return out[0], out[1]


def laundry_geometry(with_rec: dict) -> dict | None:
    rooms = with_rec.get("rooms_by_role", {}).get("LAUNDRY")
    if not rooms:
        return None
    r = rooms[0]
    template = ROOM_TEMPLATES[ProgramRole.LAUNDRY]
    aspect = max(r.width_m, r.depth_m) / min(r.width_m, r.depth_m)
    short = min(r.width_m, r.depth_m)
    entered = sorted({d.a if d.b == r.id else d.b
                      for d in with_rec["doors"] if r.id in (d.a, d.b)})
    return dict(area=r.area_m2, aspect=aspect, short_side=short, access=entered,
               within_template=(aspect <= template.max_aspect_ratio + 1e-6
                                and r.area_m2 <= template.hard_max + 1e-6))


def area_regressions(none_rec: dict, with_rec: dict) -> list[tuple[str, float, float]]:
    """Roles present in BOTH runs whose total area dropped by more than the threshold."""
    out = []
    a, b = none_rec.get("rooms_by_role", {}), with_rec.get("rooms_by_role", {})
    for role in set(a) & set(b):
        if role in ("LAUNDRY", "HALL", "CIRCULATION"):
            continue
        area_a = sum(r.area_m2 for r in a[role])
        area_b = sum(r.area_m2 for r in b[role])
        if area_a > 0 and (area_a - area_b) / area_a > AREA_DROP_THRESHOLD:
            out.append((role, area_a, area_b))
    return out


def main() -> None:
    rows = []
    started = time.perf_counter()

    for b in BEDROOMS:
        for w in WET_ROOMS:
            for label, fw, fd in RECT_FOOTPRINTS:
                ctx = rect_context(b, w, fw, fd)
                base = project_from_context(ctx)
                none_rec, with_rec = run_pair(lambda req: _with_laundry(base, req))
                rows.append(dict(shape="rect", label=label, bedrooms=b, wet=w,
                                 none=none_rec, withl=with_rec,
                                 laundry=laundry_geometry(with_rec) if with_rec["status"] == "PLANNED" else None,
                                 regressions=(area_regressions(none_rec, with_rec)
                                             if none_rec["status"] == "PLANNED" and with_rec["status"] == "PLANNED"
                                             else [])))
        print(f"  rect {b}BR done ({time.perf_counter() - started:.0f}s)", flush=True)

    for name, site_fn, plot in L_SITES:
        for w in (1, 2):
            def build(req, _site_fn=site_fn, _plot=plot, _w=w):
                spec_program = ProgramSpec(
                    bedrooms=3, safe_room=False, wet_rooms=_w, open_plan_living=True,
                    target_built_area_m2=round(_plot[0] * _plot[1] * 0.55, 1),
                    laundry=LaundryRequirement(demand=LaundryDemand.ROOM if req else LaundryDemand.NONE,
                                              source_text="חדר כביסה" if req else ""))
                return _site_fn, _plot, spec_program

            def run_one(req, _build=build):
                site_fn, plot, program = _build(req)
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
                            rooms_by_role.setdefault(role, []).append(
                                _NormalizedRoom(r.zone_id, r.net_w_m, r.net_h_m, r.net_area_m2))
                        rec = dict(status="PLANNED", area=res.design.gross_area_m2,
                                  rooms_by_role=rooms_by_role, doors=res.design.interior_doors,
                                  validators=res.validation.ok)
                except Exception as exc:  # noqa: BLE001
                    rec = dict(status="CRASH", code=f"{type(exc).__name__}: {exc}")
                rec["seconds"] = time.perf_counter() - t
                return rec

            none_rec, with_rec = run_one(False), run_one(True)
            rows.append(dict(shape="L", label=name, bedrooms=3, wet=w,
                             none=none_rec, withl=with_rec,
                             laundry=laundry_geometry(with_rec) if with_rec["status"] == "PLANNED" else None,
                             regressions=(area_regressions(none_rec, with_rec)
                                         if none_rec["status"] == "PLANNED" and with_rec["status"] == "PLANNED"
                                         else [])))
        print(f"  L {name} done ({time.perf_counter() - started:.0f}s)", flush=True)

    print(f"\ntotal {time.perf_counter() - started:.0f}s, {len(rows)} cells\n")

    planned_none = sum(1 for r in rows if r["none"]["status"] == "PLANNED")
    planned_with = sum(1 for r in rows if r["withl"]["status"] == "PLANNED")
    newly_refused = [r for r in rows if r["none"]["status"] == "PLANNED" and r["withl"]["status"] != "PLANNED"]
    print(f"planned: NONE={planned_none}/{len(rows)}  ROOM={planned_with}/{len(rows)}")
    print(f"newly refused BECAUSE of the laundry request: {len(newly_refused)}")
    for r in newly_refused:
        print(f"  {r['shape']} {r['label']} {r['bedrooms']}BR/{r['wet']}wet -> {r['withl']['code']}")

    with_laundry_geom = [r for r in rows if r["laundry"] is not None]
    print(f"\nlaundry room realized in {len(with_laundry_geom)}/{planned_with} planned+requested cells")
    off_template = [r for r in with_laundry_geom if not r["laundry"]["within_template"]]
    print(f"laundry rooms outside their own template bounds (should be 0 — C20 would refuse these): "
          f"{len(off_template)}")
    non_hall_access = [r for r in with_laundry_geom if r["laundry"]["access"] != ["HALL"]]
    print(f"laundry rooms NOT accessed from HALL only (should be 0): {len(non_hall_access)}")
    for r in non_hall_access:
        print(f"  {r['shape']} {r['label']} {r['bedrooms']}BR/{r['wet']}wet -> access={r['laundry']['access']}")

    print(f"\n{'shape':6} {'foot':14} {'bd':3} {'wet':4} {'area':>6} {'aspect':>7} {'short':>6}")
    for r in with_laundry_geom:
        g = r["laundry"]
        print(f"{r['shape']:6} {r['label']:14} {r['bedrooms']:3} {r['wet']:4} "
              f"{g['area']:6.2f} {g['aspect']:7.2f} {g['short_side']:6.2f}")

    with_regressions = [r for r in rows if r["regressions"]]
    print(f"\ncells where another room's area dropped >{AREA_DROP_THRESHOLD:.0%}: {len(with_regressions)}")
    for r in with_regressions:
        for role, a, b in r["regressions"]:
            print(f"  {r['shape']} {r['label']} {r['bedrooms']}BR/{r['wet']}wet: {role} {a:.1f} -> {b:.1f} m2 "
                  f"({100*(b-a)/a:+.0f}%)")

    print(f"\nruntime: NONE median {sorted(r['none']['seconds'] for r in rows)[len(rows)//2]:.2f}s  "
          f"ROOM median {sorted(r['withl']['seconds'] for r in rows)[len(rows)//2]:.2f}s")


if __name__ == "__main__":
    main()
