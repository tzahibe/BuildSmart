"""Where a brain request's wall clock actually goes, per stage (#247 AC-1).

Nothing here changes product code: every number is taken by wrapping a callable the request
already makes, so the measured request is the product's own request. Run as

    PYTHONPATH=backend python -m app.ai_harness.request_bound.stages <out.json> [BRIEF ...]

`BUDGET_S` is what the request asks for; the point of the measurement is that the stages below
`_improve_exactly` do not read it.
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter

BUDGET_S = float(__import__("os").environ.get("BUDGET_S", "30"))


def _project_for(b):
    from tests.vertical_slice.test_hub_guard import _project
    return _project(dict(bedrooms=b.bedrooms, wet_rooms=b.wet_rooms, safe_room=b.safe_room,
                         open_plan=b.open_plan, built_area_m2=b.built_area_m2,
                         footprint_width_m=b.footprint_width_m,
                         footprint_depth_m=b.footprint_depth_m,
                         plot_width_m=b.footprint_width_m + 8,
                         plot_depth_m=b.footprint_depth_m + 8))


class Probe:
    """Wall-clock totals and call counts, keyed by stage name."""

    def __init__(self) -> None:
        self.secs: Counter = Counter()
        self.calls: Counter = Counter()
        self.worst: dict[str, float] = {}

    def wrap(self, module, name: str, key: str):
        original = getattr(module, name)

        def timed(*a, **kw):
            t = time.monotonic()
            try:
                return original(*a, **kw)
            finally:
                d = time.monotonic() - t
                self.secs[key] += d
                self.calls[key] += 1
                self.worst[key] = max(self.worst.get(key, 0.0), d)

        setattr(module, name, timed)
        return original

    def rows(self) -> dict:
        return {k: {"seconds": round(self.secs[k], 3), "calls": self.calls[k],
                    "worst_call_s": round(self.worst.get(k, 0.0), 3)}
                for k in sorted(self.secs, key=lambda x: -self.secs[x])}


def measure(bid: str, *, budget_s: float = BUDGET_S) -> dict:
    from app.ai_harness.topology_poc import briefs as briefs_mod
    from app.demo import service as svc
    from app.vertical_slice import band_pipeline as bp
    from app.vertical_slice.brain import exact_pipeline as ep
    from app.vertical_slice.brain import runner as rn

    b = {x.brief_id: x for x in briefs_mod.select_briefs()}[bid]
    project = _project_for(b)
    probe = Probe()

    # the two halves of the request, from the outside in
    probe.wrap(svc, "_plan_outlines_until_one_plans", "production prefix: outlines")
    probe.wrap(svc, "_select_plans", "production prefix: selection")
    probe.wrap(svc, "_brain_result", "brain total (run_brain + payload)")
    probe.wrap(svc, "to_demo_design", "payload: to_demo_design")
    probe.wrap(svc, "_plan_outlines", "production prefix: _plan_outlines") \
        if hasattr(svc, "_plan_outlines") else None
    # inside run_brain
    probe.wrap(rn, "_one", "run_brain: _one (a parti, either sizer)")
    probe.wrap(rn, "_improve_exactly", "run_brain: _improve_exactly (BOUNDED today)")
    probe.wrap(rn, "_rank", "run_brain: _rank")
    probe.wrap(rn, "programme_from_spec", "run_brain: programme_from_spec")
    # the production sizer the brain's stage 1 and its fallback both use
    probe.wrap(rn, "run_band_pipeline", "production sizer: run_band_pipeline")
    probe.wrap(bp, "solve_band_layout", "  band LP: solve_band_layout")
    probe.wrap(bp, "realize_layout", "  realize_layout + validators")
    probe.wrap(bp, "embed_band", "  embed_band")
    # the exact sizer
    probe.wrap(rn, "run_exact_pipeline", "exact sizer: run_exact_pipeline") \
        if hasattr(rn, "run_exact_pipeline") else None
    probe.wrap(ep, "run_exact_pipeline", "exact sizer: run_exact_pipeline")

    # `run_brain`'s own signature default binds at DEFINITION time, so setting the module constant
    # changes nothing — the first version of this harness did exactly that and silently measured
    # the 30 s default while reporting 0.2 s. The budget is set where the product sets it.
    #
    # In an UNCHANGED control tree, which predates `service.BRAIN_BUDGET_S`, the product sets it
    # nowhere: `_brain_result` takes `run_brain`'s default. There the budget is injected into the
    # call instead, so the control and the branch are asked for the same number and the before/
    # after comparison is of the code, not of two different questions.
    prev = getattr(svc, "BRAIN_BUDGET_S", None)
    if prev is not None:
        svc.BRAIN_BUDGET_S = budget_s
    else:
        inner = svc.run_brain
        svc.run_brain = lambda *a, **kw: inner(*a, **{**kw, "budget_s": budget_s})
    out: dict = {"brief": bid, "asked_budget_s": budget_s, "requested_m2": b.built_area_m2,
                 "bedrooms": b.bedrooms, "wet_rooms": b.wet_rooms}
    t0 = time.monotonic()
    try:
        res = svc.generate_demo_design(project, brain=True)
        out["plans"] = 1 + len(res.alternatives)
        out["primary"] = res.design.family
        out["notes"] = list(res.design.validation.warnings or ())
    except svc.DemoGenerationError as exc:
        out["refused"] = exc.code
        out["detail"] = exc.detail[:200]
    except Exception as exc:                        # a harness crash must not look like a refusal
        out["crashed"] = f"{type(exc).__name__}: {exc}"[:300]
    finally:
        if prev is not None:
            svc.BRAIN_BUDGET_S = prev
        else:
            svc.run_brain = inner
    out["request_s"] = round(time.monotonic() - t0, 3)
    out["overshoot_s"] = round(out["request_s"] - budget_s, 3)
    out["stages"] = probe.rows()
    return out


def main(argv: list[str]) -> None:
    path = argv[0]
    briefs = argv[1:] or ["B08", "B20", "B02", "B11", "B16", "B19", "B06", "B09"]
    rows = []
    for bid in briefs:
        rows.append(measure(bid))
        r = rows[-1]
        print(f"{bid}: request {r['request_s']:.2f} s for an asked {r['asked_budget_s']:.1f} s "
              f"(overshoot {r['overshoot_s']:+.2f} s) plans={r.get('plans', r.get('refused'))}",
              flush=True)
    with open(path, "w") as fh:
        json.dump(rows, fh, indent=2)


if __name__ == "__main__":
    main(sys.argv[1:])
