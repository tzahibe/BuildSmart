"""#226 Part B.1 — what a request RETURNS when the wall-clock budget expires mid-solve.

`run_brain`'s `budget_s` is squeezed below what a brief needs, which is the same condition a
loaded machine produces at the default 30 s, and the result is inspected: does the request raise,
does it return production's plan, or does it return nothing at all? Run on B11 and B16 — the two
briefs whose exact solves are known to consume the whole budget.

usage: perf_budget_expiry.py <out.json>
"""
import json, os, sys, time

ROOT = "/Users/mymacbook/projects/sddproject-brain"
sys.path.insert(0, f"{ROOT}/backend")
OUT = os.path.abspath(sys.argv[1])

from tests.vertical_slice.test_brain import _brief, _spec_and_footprint
from app.vertical_slice.brain.runner import run_brain
from app.demo.service import BRAIN_FAMILIES, BRAIN_SIZER

rows = []
for bid in ("B11", "B16"):
    spec, fp = _spec_and_footprint(bid)
    for budget in (0.2, 1.0, 3.0, 10.0, 30.0):
        t = time.monotonic()
        error = None
        try:
            res = run_brain(spec, fp, brief=bid, sizer=BRAIN_SIZER, families=BRAIN_FAMILIES,
                            budget_s=budget)
            distinct = len(res.distinct)
            sizers = sorted({p.sizer for p in res.distinct})
            stages = sorted({p.stage for p in res.plans})
            notes = [n for p in res.distinct for n in p.notes if "budget" in n.lower()
                     or "time" in n.lower() or "UNKNOWN" in n or "timed out" in n.lower()][:3]
        except Exception as exc:                                    # noqa: BLE001
            distinct = sizers = stages = notes = None
            error = f"{type(exc).__name__}: {str(exc)[:160]}"
        el = time.monotonic() - t
        rows.append(dict(brief=bid, budget_s=budget, seconds=round(el, 2), distinct=distinct,
                         sizers=sizers, stages=stages, notes=notes, error=error))
        print(f"{bid} budget {budget:5.1f} s -> ran {el:6.2f} s, {distinct} distinct plans, "
              f"sizers {sizers}, stages {stages}, error {error}", flush=True)
        for n in (notes or []):
            print(f"      note: {n[:150]}", flush=True)

json.dump(rows, open(OUT, "w"), indent=1)
print("DONE")
