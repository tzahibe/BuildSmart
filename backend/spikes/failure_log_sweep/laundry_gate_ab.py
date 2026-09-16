"""A/B of the laundry-phase-1 row-rescue generalisation, over the 418 failure-log scenarios.

    .venv/bin/python3 spikes/failure_log_sweep/laundry_gate_ab.py

Every scenario here has `laundry=NONE` (the log predates this field, and `LAUNDRY_ROOM_ENABLED`
is off besides) — so this answers ONE question precisely: does generalising `_rows_for_width`'s
tier-1 rescue from `role is TOILET` to `group is ZoneGroup.SERVICE`
(docs/LAUNDRY_ROOM_OPTION_REVIEW.md phase 1, §3) ever change a REAL brief's plan by newly
rescuing a lone BATHROOM row that the old, narrower guard would have left refused?

`hub_bound`'s equivalent generalisation (§4) is NOT re-tested here: it is a no-op by
CONSTRUCTION for every laundry=NONE brief, not merely by measurement — `ZoneGroup.SERVICE` is
populated by exactly two `build_room_program` call sites (the wet-room loop: BATHROOM/TOILET; the
gated LAUNDRY branch, inert here) — so with the gate off, `{r for r in rooms if r.group is
SERVICE}` and `{r for r in rooms if r.role in (BATHROOM, TOILET)}` are the same set for every
brief in this log, and the two forms of the M5 check cannot diverge. Only the row-rescue guard
compares a ROLE literal against a GROUP that a role never fully determines (BATHROOM shares
SERVICE with TOILET), which is why it is the one line that needs an empirical A/B rather than a
proof by construction.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.demo import service as svc  # noqa: E402
from app.vertical_slice import concept_generator as cg  # noqa: E402
from app.vertical_slice.geometry_core.model import ProgramRole  # noqa: E402
from spikes.failure_log_sweep.sweep import (  # noqa: E402
    distinct_contexts, key_of, project_from_context, signature,
)

SHIPPED_ROWS_FOR_WIDTH = cg._rows_for_width


def old_rows_for_width(rows, net_width, fallback=None, corridor_on_east=True):
    """Verbatim pre-phase-1 body: the guard is `role is ProgramRole.TOILET`, not the group."""
    if fallback is not None:
        return cg._repartition_rows(rows, net_width, fallback, corridor_on_east)
    for i, row in enumerate(rows):
        if (len(row) == 1 and row[0].role is ProgramRole.TOILET and not row[0].entered_from
                and cg.room_depth_band_m(row[0].template, net_width) is None):
            shared = cg._pair_with_dependent(rows, i)
            if shared is not None:
                return shared
    return rows


def run_all(contexts, label):
    out = {}
    started = time.perf_counter()
    for i, ctx in enumerate(contexts, start=1):
        t = time.perf_counter()
        try:
            res = svc.generate_demo_design(project_from_context(ctx))
            rec = dict(status="PLANNED", sig=signature(res.design),
                      area=res.design.gross_area_m2, validators=res.design.validation.passed,
                      rooms=len(res.design.rooms))
        except svc.DemoGenerationError as exc:
            rec = dict(status="REFUSED", code=exc.code)
        except Exception as exc:  # noqa: BLE001
            rec = dict(status="CRASH", code=f"{type(exc).__name__}: {exc}")
        rec["seconds"] = time.perf_counter() - t
        out[key_of(ctx)] = rec
        if i % 100 == 0:
            print(f"  {label} {i}/{len(contexts)}", flush=True)
    print(f"  {label} done in {time.perf_counter() - started:.0f}s", flush=True)
    return out


def main():
    contexts = distinct_contexts()
    by_key = {key_of(c): c for c in contexts}
    print(f"scenarios: {len(contexts)}")

    cg._rows_for_width = old_rows_for_width
    off = run_all(contexts, "OFF (TOILET-only guard, pre-phase-1)")
    cg._rows_for_width = SHIPPED_ROWS_FOR_WIDTH
    on = run_all(contexts, "ON  (ZoneGroup.SERVICE guard, shipped)")

    statuses_differ = [k for k in by_key if off[k]["status"] != on[k]["status"]]
    planned_both = [k for k in by_key if off[k]["status"] == "PLANNED" and on[k]["status"] == "PLANNED"]
    sig_differs = [k for k in planned_both if off[k]["sig"] != on[k]["sig"]]

    print(f"\nplanned OFF={sum(1 for v in off.values() if v['status']=='PLANNED')}"
          f"  ON={sum(1 for v in on.values() if v['status']=='PLANNED')}")
    print(f"status changed (PLANNED/REFUSED/CRASH): {len(statuses_differ)}/{len(by_key)}")
    print(f"planned-in-both with a DIFFERENT room signature (payload changed): "
          f"{len(sig_differs)}/{len(planned_both)}")
    for k in statuses_differ:
        print(f"  STATUS CHANGED: {by_key[k]} -> OFF={off[k]['status']}/{off[k].get('code')}  "
              f"ON={on[k]['status']}/{on[k].get('code')}")
    for k in sig_differs:
        print(f"  SIGNATURE CHANGED: {by_key[k]}")

    print(f"\ntotal OFF {sum(v['seconds'] for v in off.values()):.0f}s"
          f"   ON {sum(v['seconds'] for v in on.values()):.0f}s")
    print("\nVERDICT:", "ZERO CHANGE — the generalisation is inert on this corpus"
          if not statuses_differ and not sig_differs else "CHANGES FOUND — see above")


if __name__ == "__main__":
    main()
