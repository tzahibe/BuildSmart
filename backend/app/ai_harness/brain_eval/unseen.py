"""Fresh briefs the brain has never been tuned on (#197). Production vs brain, same measurements.

The eight briefs in `compare.py` are the ones every decision in this work was made against, so a
result on them is not evidence that the brain generalises. These five were written afterwards and
chosen to attack what has failed before — a long thin footprint, a plan too tight for a foyer, the
most hub edges any parti has had to carry, a wide shallow plot, and a house below the foyer
threshold — not to flatter the result. Nothing here was tuned against them.

    PYTHONPATH=backend python -m app.ai_harness.brain_eval.unseen <out.json>
"""
import json, sys, time
from app.demo import service as svc
from app.demo.service import spec_for
from tests.vertical_slice.test_hub_guard import _project
from app.ai_harness.brain_eval.compare import profile

#: Chosen to attack the things that have failed before, not to flatter the result.
UNSEEN = {
    # a long thin footprint — the shape that produced production's 14 m corridors
    "U1-narrow":   dict(bedrooms=4, wet_rooms=2, safe_room=True,  built_area_m2=160.0,
                        footprint_width_m=8.0,  footprint_depth_m=20.0),
    # nearly square and tight — little room for a foyer or a band
    "U2-compact":  dict(bedrooms=3, wet_rooms=2, safe_room=False, built_area_m2=104.0,
                        footprint_width_m=10.0, footprint_depth_m=10.4),
    # six bedrooms: the most hub edges any parti has had to carry
    "U3-sixbed":   dict(bedrooms=6, wet_rooms=3, safe_room=True,  built_area_m2=238.0,
                        footprint_width_m=14.0, footprint_depth_m=17.0),
    # open plan, wide and shallow — the garden/street question at its sharpest
    "U4-wide":     dict(bedrooms=4, wet_rooms=3, safe_room=True,  open_plan=True,
                        built_area_m2=187.0, footprint_width_m=22.0, footprint_depth_m=8.5),
    # small: below the foyer threshold on purpose
    "U5-small":    dict(bedrooms=2, wet_rooms=1, safe_room=False, built_area_m2=72.0,
                        footprint_width_m=8.0,  footprint_depth_m=9.0),
}

rows = []
for bid, kw in UNSEEN.items():
    base = dict(open_plan=False, plot_width_m=kw["footprint_width_m"] + 8,
                plot_depth_m=kw["footprint_depth_m"] + 8)
    base.update(kw)
    proj = _project(base)
    req = base["built_area_m2"]
    row = {"brief": bid, "requested_m2": req, **{k: base[k] for k in
           ("bedrooms", "wet_rooms", "safe_room", "open_plan",
            "footprint_width_m", "footprint_depth_m")}}
    t0 = time.monotonic()
    try:
        row["production"] = {**profile(svc.generate_demo_design(proj).design, req),
                             "seconds": round(time.monotonic() - t0, 2)}
    except Exception as e:
        row["production"] = {"refused": type(e).__name__, "detail": str(e)[:120]}
    t0 = time.monotonic()
    try:
        br = svc.generate_demo_design(proj, brain=True)
        row["brain"] = {**profile(br.design, req), "parti": br.design.family,
                        "alternatives": len(br.alternatives),
                        "partis": [br.design.family] + [a.family for a in br.alternatives],
                        "seconds": round(time.monotonic() - t0, 2)}
        row["brain_alts"] = [{"parti": a.family, **profile(a, req)} for a in br.alternatives]
    except svc.DemoGenerationError as e:
        row["brain"] = {"refused": e.code, "detail": e.detail[:160],
                        "seconds": round(time.monotonic() - t0, 2)}
    rows.append(row)
    b = row["brain"]
    print(f"{bid:11} prod {row['production'].get('area_fidelity_pct','-')}% | "
          f"brain {b.get('area_fidelity_pct', b.get('refused','-'))} "
          f"arrive={b.get('arrival','-')} alts={b.get('alternatives','-')}", flush=True)
json.dump(rows, open(sys.argv[1], "w"), indent=2)
