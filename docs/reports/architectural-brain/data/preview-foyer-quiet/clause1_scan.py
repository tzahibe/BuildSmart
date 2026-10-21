"""#226 Part A, AC-1 — the gate's clause 1, tested as written.

"No shown-first plan has a strip arrival room where a usable-foyer plan OF THE SAME BRIEF passed
validators." Every plan `run_brain` keeps has already passed the validators, so the test is: for
each brief, is `distinct[0]`'s arrival a strip while some other kept plan's arrival is usable — and
if so, which key term put the strip first? Run in the product's own configuration
(`service.BRAIN_SIZER` / `BRAIN_FAMILIES`), not the report's band-only column.

usage: clause1_scan.py <tree> <out.json>"""
import json, sys, time

ROOT = sys.argv[1]; sys.path.insert(0, f"{ROOT}/backend")
OUT = sys.argv[2]
from tests.vertical_slice.test_brain import _spec_and_footprint
from app.vertical_slice.brain.proposer import programme_from_spec
from app.vertical_slice.brain import runner as br
from app.demo.service import BRAIN_FAMILIES, BRAIN_SIZER

BRIEFS = ["B02", "B06", "B08", "B09", "B11", "B16", "B19", "B20"]

# PRE216=1 restores the solve limit #216 replaced -- `max(1.0, min(10.0, remaining))` -- by setting
# the two constants `solve_time_limit` reads, so #216 can be isolated inside the branch itself
# rather than measured from a fourth tree.
import os
if os.environ.get("PRE216") == "1":
    from app.vertical_slice.brain import exact_pipeline as _xp
    _xp.SOLVE_BUDGET_FRACTION = 1.0
    _xp.MIN_SOLVE_S = 1.0
    print("PRE216: solve_time_limit(2.0) =", _xp.solve_time_limit(2.0))


def usability(realized):
    fn = getattr(br, "arrival_usability", None)
    if fn is not None:
        return fn(realized)
    from app.vertical_slice.exact.milp_oracle import FOYER_MAX_DEPTH_TO_WIDTH, FOYER_MIN_NET_M
    zone = br._arrival_zone(realized)
    room = next((r for r in realized.design.rooms if r.zone_id == zone), None) if zone else None
    if room is None:
        return 1, None
    w, h = float(room.net_w_m), float(room.net_h_m)
    return (0 if (w >= FOYER_MIN_NET_M - 1e-9 and h <= FOYER_MAX_DEPTH_TO_WIDTH * w + 1e-9) else 1), (round(w, 2), round(h, 2))


out = []
for bid in BRIEFS:
    spec, fp = _spec_and_footprint(bid); p = programme_from_spec(spec, fp)
    t = time.monotonic()
    res = br.run_brain(spec, fp, brief=bid, sizer=BRAIN_SIZER, families=BRAIN_FAMILIES)
    el = time.monotonic() - t
    plans = []
    for i, pl in enumerate(res.distinct):
        dev, circ = br.proportion_metrics(pl.realized, p.zones)
        u, dims = usability(pl.realized)
        plans.append(dict(rank=i, parti=pl.parti, sizer=pl.sizer, family=pl.family,
                          dev=round(dev, 1), circ=round(circ, 1), usable=u, net=dims,
                          key=list(pl.rank_key or ())))
    shown = plans[0] if plans else None
    usable_sibling = next((q for q in plans[1:] if q["usable"] == 0), None)
    decided = None
    if shown and shown["usable"] == 1 and usable_sibling:
        names = getattr(br, "_KEY_NAMES", ("arrival", "street", "area", "rooms", "circulation"))
        decided = next((names[i] if i < len(names) else f"key {i}")
                       for i, (x, y) in enumerate(zip(shown["key"], usable_sibling["key"])) if x != y)
    verdict = ("no plan" if not shown else
               "ok (shown arrival usable)" if shown["usable"] == 0 else
               "ok (no usable-arrival plan passed)" if not usable_sibling else
               f"VIOLATION? shown is a strip, a usable plan passed; decided by: {decided}")
    out.append(dict(brief=bid, seconds=round(el, 2), verdict=verdict, plans=plans))
    print(f"\n== {bid}  {el:5.1f} s  {verdict}")
    for q in plans:
        print(f"   #{q['rank']} {q['parti']:22s} {q['sizer']:10s} {q['family']:6s} dev {q['dev']:5.1f} "
              f"circ {q['circ']:5.1f} arrival {str(q['net']):14s} {'usable' if q['usable'] == 0 else 'STRIP '} key {q['key'][:6]}", flush=True)

json.dump(out, open(OUT, "w"), indent=1)
print("\nDONE")
