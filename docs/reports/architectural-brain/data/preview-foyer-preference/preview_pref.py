"""Owner item 4: the visual comparison on real briefs — production / brain (production sizer) /
brain (exact, band) / brain (exact, all families), side by side, with the proportion metrics."""
import json, os, sys, time
sys.path.insert(0, '/Users/mymacbook/projects/sddproject-brain/backend')
from tests.vertical_slice.test_brain import _brief, _spec_and_footprint
from tests.vertical_slice.test_hub_guard import _project
from app.demo import service as svc
from app.demo.contract import to_demo_design
from app.vertical_slice.brain.proposer import programme_from_spec
from app.vertical_slice.brain.runner import run_brain, proportion_metrics, arrival_usability
from app.vertical_slice.geometry_core.model import ProgramRole
OUT=sys.argv[1]; os.makedirs(f'{OUT}/designs', exist_ok=True)
BRIEFS=sys.argv[2:] or ["B08","B20","B02","B11","B16","B19","B06","B09"]
CONFIGS=[("brain-production",dict(sizer="production",families=("band",))),
         ("brain-exact-band",dict(sizer="exact",families=("band",))),
         ("brain-exact-all",dict(sizer="exact",families=("band","spine","stack","cells")))]
rows=[]
def project_for(bid):
    b=_brief(bid)
    return _project(dict(bedrooms=b.bedrooms, wet_rooms=b.wet_rooms, safe_room=b.safe_room, open_plan=b.open_plan,
                         built_area_m2=b.built_area_m2, footprint_width_m=b.footprint_width_m, footprint_depth_m=b.footprint_depth_m,
                         plot_width_m=b.footprint_width_m+8, plot_depth_m=b.footprint_depth_m+8))
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
    circ={ProgramRole.HALL, ProgramRole.CIRCULATION}; devs=[]; circ_net=0; total=0; beds=[]
    for r in design.rooms:
        zi=zones.get(r.id); total+=r.area_m2
        if zi is None: continue
        if zi.role in circ: circ_net+=r.area_m2; continue
        devs.append(abs(r.area_m2-zi.target_area_m2)/zi.target_area_m2)
        if zi.role in (ProgramRole.BEDROOM, ProgramRole.MASTER_BEDROOM): beds.append(r.area_m2/zi.target_area_m2)
    return (round(100*sum(devs)/len(devs),1) if devs else None, round(100*circ_net/total,1) if total else None, round(100*min(beds),1) if beds else None, len(devs))
for bid in BRIEFS:
    spec, fp = _spec_and_footprint(bid); project=project_for(bid); p=programme_from_spec(spec, fp)
    t=time.monotonic(); prod=svc.generate_demo_design(project); el=time.monotonic()-t
    d=prod.design; json.dump(d.model_dump(mode="json"), open(f"{OUT}/designs/{bid}__production.json","w"))
    dev,circ,minbed,n=dev_of_design(d, p.zones)
    rows.append(dict(brief=bid, config="production", seconds=round(el,1), gross=d.gross_area_m2, dev=dev, circ=circ, minbed=minbed, rooms_matched=n, family="guillotine", sizer="production", note="", arrival=arrival_of(d), arrival_net=arrival_dims(d)))
    print(bid, "production", round(el,1), "s dev", dev, "circ", circ, flush=True)
    for name, kw in CONFIGS:
        t=time.monotonic(); res=run_brain(spec, fp, brief=bid, **kw); el=time.monotonic()-t
        if not res.distinct:
            rows.append(dict(brief=bid, config=name, seconds=round(el,1), gross=None, dev=None, circ=None, minbed=None, rooms_matched=0, family="-", sizer=kw["sizer"], note="no plan")); print(bid, name, "no plan", flush=True); continue
        # the PRIMARY is what the product shows (distinct[0], the brain's own ranking); best-by-dev is kept for comparison with the first report
        for tag, best in (("", res.distinct[0]), ("-bydev", min(res.distinct, key=lambda pl: proportion_metrics(pl.realized, p.zones)[0]))):
            dd=to_demo_design(best.realized.design, best.realized.report, family=f"brain:{best.parti}", notes=[f"{bid} {name} {best.parti} ({best.family}, {best.sizer})"])
            json.dump(dd.model_dump(mode="json"), open(f"{OUT}/designs/{bid}__{name}{tag}.json","w"))
            dev,circ=proportion_metrics(best.realized, p.zones); _,_,minbed,n=dev_of_design(dd, p.zones)
            rows.append(dict(brief=bid, config=name+tag, seconds=round(el,1), gross=dd.gross_area_m2, dev=round(dev,1), circ=round(circ,1), minbed=minbed, rooms_matched=n, family=best.family, sizer=best.sizer, parti=best.parti, note="; ".join(best.notes)[:160], plans=len(res.distinct), arrival=arrival_of(dd), key=list(best.rank_key or ()), arrival_net=arrival_dims(dd), usable=arrival_usability(best.realized)[0], label=getattr(best.realized, "name", "")))
            print(bid, name+tag, round(el,1), "s", best.parti, best.family, best.sizer, "dev", round(dev,1), "circ", round(circ,1), "arrival", arrival_of(dd), arrival_dims(dd), "usable" if arrival_usability(best.realized)[0] == 0 else "STRIP", "plans", len(res.distinct), "key", list(best.rank_key or ()), flush=True)
json.dump(rows, open(f"{OUT}/metrics.json","w"), indent=1)
print("DONE")
