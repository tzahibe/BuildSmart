"""#226 Part A — the eight-brief measurement of `PREVIEW-rank-then-size.md`'s four columns, run on
ANY tree so a same-session control at `5b155d1` is measured by the same code path as the branch.

`preview_pref.py` (#207) hard-coded `/Users/mymacbook/projects/sddproject-brain/backend` on
`sys.path` and imported `arrival_usability` from the runner, which only exists from #207 onwards.
Both are parameters here: the tree to measure is `argv[1]`, and when the runner has no
`arrival_usability` the harness computes the identical predicate from the oracle's own
`FOYER_MIN_NET_M` / `FOYER_MAX_DEPTH_TO_WIDTH`, so "strip" means the same thing in every column."""
import json, os, sys, time

ROOT = os.path.abspath(sys.argv[1])
OUT = os.path.abspath(sys.argv[2])
BRIEFS = sys.argv[3:] or ["B02", "B06", "B08", "B09", "B11", "B16", "B19", "B20"]
sys.path.insert(0, f"{ROOT}/backend")
os.makedirs(f"{OUT}/designs", exist_ok=True)

from tests.vertical_slice.test_brain import _brief, _spec_and_footprint
from tests.vertical_slice.test_hub_guard import _project
from app.demo import service as svc
from app.demo.contract import to_demo_design
from app.vertical_slice.brain.proposer import programme_from_spec
from app.vertical_slice.brain import runner as brain_runner
from app.vertical_slice.brain.runner import run_brain, proportion_metrics
from app.vertical_slice.geometry_core.model import ProgramRole
from app.vertical_slice.exact.milp_oracle import FOYER_MAX_DEPTH_TO_WIDTH, FOYER_MIN_NET_M

print(f"TREE {ROOT}", flush=True)


def usability(realized):
    """#207's `arrival_usability` where it exists; the same predicate re-derived where it does not."""
    fn = getattr(brain_runner, "arrival_usability", None)
    if fn is not None:
        return fn(realized)
    zone = brain_runner._arrival_zone(realized)
    room = next((r for r in realized.design.rooms if r.zone_id == zone), None) if zone else None
    if room is None:
        return 1, None
    w, h = float(room.net_w_m), float(room.net_h_m)
    ok = w >= FOYER_MIN_NET_M - 1e-9 and h <= FOYER_MAX_DEPTH_TO_WIDTH * w + 1e-9
    return (0 if ok else 1), (round(w, 2), round(h, 2))


CONFIGS = [("brain-production", dict(sizer="production", families=("band",))),
           ("brain-exact-band", dict(sizer="exact", families=("band",))),
           ("brain-exact-all", dict(sizer="exact", families=("band", "spine", "stack", "cells")))]
rows = []


def project_for(bid):
    b = _brief(bid)
    return _project(dict(bedrooms=b.bedrooms, wet_rooms=b.wet_rooms, safe_room=b.safe_room,
                         open_plan=b.open_plan, built_area_m2=b.built_area_m2,
                         footprint_width_m=b.footprint_width_m, footprint_depth_m=b.footprint_depth_m,
                         plot_width_m=b.footprint_width_m + 8, plot_depth_m=b.footprint_depth_m + 8))


def arrival_dims(design):
    rooms = {r.id: r for r in design.rooms}
    ent = [d for d in design.doors if d.is_entrance]
    z = next((z for d in ent for z in (d.a, d.b) if z in rooms), None)
    return (rooms[z].width_m, rooms[z].depth_m) if z else None


def arrival_of(design):
    rooms = {r.id: r.type for r in design.rooms}
    ent = [d for d in design.doors if d.is_entrance]
    return next((rooms[z] for d in ent for z in (d.a, d.b) if z in rooms), None)


def dev_of_design(design, zones):
    circ = {ProgramRole.HALL, ProgramRole.CIRCULATION}
    devs = []; circ_net = 0; total = 0; beds = []
    for r in design.rooms:
        zi = zones.get(r.id); total += r.area_m2
        if zi is None:
            continue
        if zi.role in circ:
            circ_net += r.area_m2; continue
        devs.append(abs(r.area_m2 - zi.target_area_m2) / zi.target_area_m2)
        if zi.role in (ProgramRole.BEDROOM, ProgramRole.MASTER_BEDROOM):
            beds.append(r.area_m2 / zi.target_area_m2)
    return (round(100 * sum(devs) / len(devs), 1) if devs else None,
            round(100 * circ_net / total, 1) if total else None,
            round(100 * min(beds), 1) if beds else None, len(devs))


for bid in BRIEFS:
    spec, fp = _spec_and_footprint(bid); project = project_for(bid); p = programme_from_spec(spec, fp)
    t = time.monotonic(); prod = svc.generate_demo_design(project); el = time.monotonic() - t
    d = prod.design
    json.dump(d.model_dump(mode="json"), open(f"{OUT}/designs/{bid}__production.json", "w"))
    dev, circ, minbed, n = dev_of_design(d, p.zones)
    rows.append(dict(brief=bid, config="production", seconds=round(el, 1), gross=d.gross_area_m2,
                     dev=dev, circ=circ, minbed=minbed, rooms_matched=n, family="guillotine",
                     sizer="production", note="", arrival=arrival_of(d), arrival_net=arrival_dims(d)))
    print(bid, "production", round(el, 1), "s dev", dev, "circ", circ, flush=True)
    for name, kw in CONFIGS:
        t = time.monotonic(); res = run_brain(spec, fp, brief=bid, **kw); el = time.monotonic() - t
        if not res.distinct:
            rows.append(dict(brief=bid, config=name, seconds=round(el, 1), gross=None, dev=None,
                             circ=None, minbed=None, rooms_matched=0, family="-",
                             sizer=kw["sizer"], note="no plan"))
            print(bid, name, round(el, 1), "s", "no plan", flush=True); continue
        for tag, best in (("", res.distinct[0]),
                          ("-bydev", min(res.distinct, key=lambda pl: proportion_metrics(pl.realized, p.zones)[0]))):
            dd = to_demo_design(best.realized.design, best.realized.report, family=f"brain:{best.parti}",
                                notes=[f"{bid} {name} {best.parti} ({best.family}, {best.sizer})"])
            json.dump(dd.model_dump(mode="json"), open(f"{OUT}/designs/{bid}__{name}{tag}.json", "w"))
            dev, circ = proportion_metrics(best.realized, p.zones)
            _, _, minbed, n = dev_of_design(dd, p.zones)
            u, dims = usability(best.realized)
            rows.append(dict(brief=bid, config=name + tag, seconds=round(el, 1), gross=dd.gross_area_m2,
                             dev=round(dev, 1), circ=round(circ, 1), minbed=minbed, rooms_matched=n,
                             family=best.family, sizer=best.sizer, parti=best.parti,
                             note="; ".join(best.notes)[:160], plans=len(res.distinct),
                             arrival=arrival_of(dd), key=list(best.rank_key or ()),
                             arrival_net=arrival_dims(dd), usable=u, usable_net=dims,
                             label=getattr(best.realized, "name", "")))
            print(bid, name + tag, round(el, 1), "s", best.parti, best.family, best.sizer,
                  "dev", round(dev, 1), "circ", round(circ, 1), "arrival", arrival_of(dd),
                  dims, "usable" if u == 0 else "STRIP", "plans", len(res.distinct), flush=True)

json.dump(rows, open(f"{OUT}/metrics.json", "w"), indent=1)
print("DONE")
