"""#226 Part A — is B11's lost exact plan the share or the preference?

The control reached B11's exact band plan by OVERRUNNING its 2.13 s share by 1.05 s (the pre-#216
`max(1.0, ...)` floor). #216 made the floor 0.25 s, so the deadline is now obeyed and the solve
that worked no longer fits. If that is the whole story, then on the BRANCH the same plan must come
back as soon as the parti is handed enough time — by a longer request budget or by giving the top
parti the whole remainder. usage: diag_b11_share.py <tree>"""
import sys, time

ROOT = sys.argv[1]; sys.path.insert(0, f"{ROOT}/backend")
from tests.vertical_slice.test_brain import _spec_and_footprint
from app.vertical_slice.brain.proposer import programme_from_spec
from app.vertical_slice.brain.runner import run_brain, proportion_metrics, arrival_usability

spec, fp = _spec_and_footprint("B11")
p = programme_from_spec(spec, fp)
for label, kw in (("default 30 s, top 3", dict()),
                  ("30 s, top 1 (whole remainder to the best parti)", dict(exact_top=1)),
                  ("45 s budget, top 3", dict(budget_s=45.0)),
                  ("60 s budget, top 3", dict(budget_s=60.0))):
    t = time.monotonic(); res = run_brain(spec, fp, brief="B11", sizer="exact", families=("band",), **kw)
    el = time.monotonic() - t
    best = res.distinct[0] if res.distinct else None
    if best is None:
        print(f"{label:48s} {el:6.2f} s  NO PLAN"); continue
    dev, circ = proportion_metrics(best.realized, p.zones)
    u, dims = arrival_usability(best.realized)
    print(f"{label:48s} {el:6.2f} s  {best.parti:20s} sizer={best.sizer:10s} "
          f"dev {dev:5.1f}  circ {circ:5.1f}  arrival {dims} {'usable' if u == 0 else 'STRIP'}", flush=True)
