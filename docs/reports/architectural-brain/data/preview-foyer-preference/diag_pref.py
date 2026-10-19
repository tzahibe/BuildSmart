"""#207 diagnosis (from #205's): every exact placement the brain realizes per brief/config, with the
street-fronting arrival-cell geometry and the validator outcome (C25/C26/C28 ...)."""
import json, os, re, sys, time
sys.path.insert(0, '/Users/mymacbook/projects/sddproject-brain/backend')
from tests.vertical_slice.test_brain import _spec_and_footprint
from app.vertical_slice.brain import exact_pipeline as ep
from app.vertical_slice.brain.runner import run_brain, arrival_usability
from app.vertical_slice.geometry_core.model import ProgramRole, u_to_m
from app.vertical_slice.rectilinear_realizer import RealizedLayout

OUT = sys.argv[1]
SKIP = sys.argv[2]            # "foyer" or "none"
BRIEFS = sys.argv[3:] or ["B08", "B20", "B02", "B11", "B16", "B19", "B06", "B09"]
CONFIGS = [("brain-production", dict(sizer="production", families=("band",))),
           ("brain-exact-band", dict(sizer="exact", families=("band",))),
           ("brain-exact-all", dict(sizer="exact", families=("band", "spine", "stack", "cells")))]
CIRC = {ProgramRole.HALL, ProgramRole.CIRCULATION}
records = []
_real = ep.realize_cells

if SKIP != "none":
    import functools
    from app.vertical_slice.exact import milp_oracle as mo, milp_cells as mc
    skip = frozenset(SKIP.split(","))
    ep_mp = functools.partial(mo.milp_placement, _skip=skip)
    ep_sp = functools.partial(mo.milp_spine_placement, _skip=skip)
    ep_cp = functools.partial(mc.cells_placement, _skip=skip)
    mo.milp_placement, mo.milp_spine_placement, mc.cells_placement = ep_mp, ep_sp, ep_cp

def logged(name, rects, intents, wings, access, wet_rooms=()):
    out = _real(name, rects, intents, wings, access, wet_rooms=wet_rooms)
    y0 = min(r.y for r in rects.values())
    front = [(z, r) for z, r in rects.items() if r.y == y0 and getattr(intents.get(z), "role", None) in CIRC]
    rec = dict(brief=CUR["brief"], config=CUR["config"], name=name, label=CUR.get("label"),
               fronting=[dict(zone=z, w=u_to_m(r.w), h=u_to_m(r.h), x=u_to_m(r.x)) for z, r in front],
               circ={z: (u_to_m(r.w), u_to_m(r.h), u_to_m(r.x), u_to_m(r.y)) for z, r in rects.items()
                     if getattr(intents.get(z), "role", None) in CIRC})
    if isinstance(out, RealizedLayout):
        ent = out.entrance_door
        rec.update(ok=True, arrival=ent.b, codes=[])
        arr = out.rects.get(ent.b)
        rec["arrival_net"] = None
        if arr is not None:
            r = [x for x in out.design.rooms if x.zone_id == ent.b]
            if r:
                rec["arrival_net"] = (round(r[0].net_w_m, 2), round(r[0].net_h_m, 2))
    else:
        rec.update(ok=False, constraint=out.constraint, detail=out.detail[:300],
                   codes=sorted(set(re.findall(r"\b(C\d+)\b", out.detail))))
    records.append(rec)
    return out

ep.realize_cells = logged
_EP = ep.ExactPlacement
class _Tagged(_EP):
    def __init__(self, *a, **k):
        super().__init__(*a, **k); CUR["label"] = self.label
ep.ExactPlacement = _Tagged
CUR = {}
rows = []
for bid in BRIEFS:
    spec, fp = _spec_and_footprint(bid)
    for cname, kw in CONFIGS:
        CUR.update(brief=bid, config=cname)
        t = time.monotonic(); res = run_brain(spec, fp, brief=bid, **kw); el = time.monotonic() - t
        first = res.distinct[0] if res.distinct else None
        row = dict(brief=bid, config=cname, seconds=round(el, 1),
                   parti=first.parti if first else None, sizer=first.sizer if first else None,
                   family=first.family if first else None, key=list(first.rank_key or ()) if first else None,
                   accepted=[dict(parti=p.parti, sizer=p.sizer, family=p.family, key=list(p.rank_key or ()),
                                  usable=arrival_usability(p.realized)[0], dims=arrival_usability(p.realized)[1],
                                  arrival=p.realized.entrance_door.b, notes=list(p.notes)) for p in res.accepted])
        rows.append(row)
        mine = [r for r in records if r["brief"] == bid and r["config"] == cname]
        fr = [r for r in mine if r["fronting"]]
        vf = [r for r in fr if (r["label"] or "").endswith("V") or " V " in (r["label"] or "") or "V rung" in (r["label"] or "")]
        row["v_fronting"] = dict(n=len(vf), ok=sum(r["ok"] for r in vf), codes={c: sum(1 for r in vf if not r["ok"] and c in r["codes"]) for c in ("C25", "C26", "C28")})
        print(bid, cname, f"{el:.1f}s", row["parti"], row["sizer"], row["family"], row["key"],
              "| accepted", [(a["parti"][:14], a["sizer"][:4], a["usable"], a["dims"]) for a in row["accepted"]],
              "| realizations", len(mine), "fronting", len(fr), "ok", sum(r["ok"] for r in fr),
              "fail", {c: sum(1 for r in fr if not r["ok"] and c in r["codes"]) for c in ("C25", "C26", "C28")},
              "| V fronting", row["v_fronting"], flush=True)
os.makedirs(OUT, exist_ok=True)
json.dump(dict(skip=SKIP, rows=rows, records=records), open(f"{OUT}/diag-{SKIP}.json", "w"), indent=1)
print("DONE")
