"""A/B of the Architecture A spike (Issue #107) over the real 432-context corpus.

    uv run python spikes/failure_log_sweep/living_kitchen_merge_ab.py

OFF is today's shipped code (`room_merge.LIVING_KITCHEN_MERGE_ENABLED = False`, unconditionally
short-circuiting `plan_merge` to `None`); ON flips the flag for the same run. Reads the same
432-context corpus `tests/regression_corpus/corpus.json` already freezes (Issue #66's own trusted
snapshot), not the raw failure log — this script needs no LLM/network call either way.

Gates reported, matching this spike's own regression budget (Issue #107 §"Regression budget"):
  * LOST == 0 (every context planned OFF must still be planned ON);
  * crashes == 0 on both sides;
  * every PRIMARY-signature change is named, with the reason (`merge.applied`) attached — so a
    reviewer can see directly that every signature change is attributable to a merge candidate
    that was found AND passed its own checks in that context's primary, not to anything else;
  * M1's kitchen/dining aspect, before (mean of the two source rooms' own gross aspect, read off
    the SAME context's OFF run) vs after (the merged room's own oriented — AABB — aspect,
    `MergeOut.oriented_aspect`), median over exactly the contexts where a merge fired.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

CORPUS_PATH = Path(__file__).resolve().parents[2] / "tests" / "regression_corpus" / "corpus.json"


def _load_contexts() -> list[tuple[str, dict]]:
    with open(CORPUS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return [(case["source_key"], case["context"]) for case in data["cases"]]


def _room_aspect(gross_w: float, gross_h: float) -> float:
    return max(gross_w, gross_h) / max(min(gross_w, gross_h), 1e-6)


def run_all(contexts, flag: bool) -> dict:
    from app.vertical_slice import room_merge
    room_merge.LIVING_KITCHEN_MERGE_ENABLED = flag
    from app.demo import service as svc
    from spikes.failure_log_sweep.sweep import project_from_context, signature

    out = {}
    started = time.perf_counter()
    for i, (key, ctx) in enumerate(contexts, start=1):
        try:
            res = svc.generate_demo_design(project_from_context(ctx))
            rec = dict(status="PLANNED", sig=signature(res.design),
                      rooms={r.id: (r.gross_width_m, r.gross_depth_m) for r in res.design.rooms})
            merge = res.design.merge
            rec["merge_applied"] = merge.applied if merge is not None else None
            if merge is not None:
                rec["merge_failed_checks"] = [c.check_id for c in merge.checks if not c.passed]
                rec["merge_oriented_aspect"] = merge.oriented_aspect
                rec["merge_living_id"] = merge.living_id
                rec["merge_kitchen_id"] = merge.kitchen_id
        except svc.DemoGenerationError as exc:
            rec = dict(status="REFUSED", code=exc.code)
        except Exception as exc:  # noqa: BLE001
            rec = dict(status="CRASH", code=f"{type(exc).__name__}: {exc}")
        out[key] = rec
        if i % 100 == 0:
            print(f"  flag={flag} {i}/{len(contexts)}", flush=True)
    print(f"  flag={flag} done in {time.perf_counter() - started:.0f}s", flush=True)
    return out


def main() -> None:
    contexts = _load_contexts()
    print(f"scenarios: {len(contexts)}")
    off = run_all(contexts, False)
    on = run_all(contexts, True)

    planned_off = [k for k, v in off.items() if v["status"] == "PLANNED"]
    lost = [k for k in planned_off if on[k]["status"] != "PLANNED"]
    identical = [k for k in planned_off if on[k]["status"] == "PLANNED" and on[k]["sig"] == off[k]["sig"]]
    changed = [k for k in planned_off if on[k]["status"] == "PLANNED" and on[k]["sig"] != off[k]["sig"]]
    crashes_off = [k for k, v in off.items() if v["status"] == "CRASH"]
    crashes_on = [k for k, v in on.items() if v["status"] == "CRASH"]
    candidates = [k for k in planned_off if on[k].get("merge_applied") is not None]
    applied = [k for k in candidates if on[k]["merge_applied"]]
    rejected = [k for k in candidates if not on[k]["merge_applied"]]

    print(f"\nplanned OFF={len(planned_off)}  ON={sum(1 for v in on.values() if v['status'] == 'PLANNED')}")
    print(f"LOST: {len(lost)}   crashes OFF={len(crashes_off)} ON={len(crashes_on)}")
    for k in lost:
        print("  LOST:", k, "->", on[k].get("code") or on[k]["status"])
    for k in crashes_on:
        print("  CRASH ON:", k, "->", on[k]["code"])

    print(f"\nbyte-identical primary signatures (OFF==ON): {len(identical)}/{len(planned_off)}")
    print(f"primary-signature changes: {len(changed)}")
    for k in changed:
        applied_here = on[k].get("merge_applied")
        print(f"  CHANGED: {k}  merge_applied={applied_here}  "
              f"failed_checks={on[k].get('merge_failed_checks')}")
        if applied_here is not True:
            print("    *** UNEXPLAINED signature change — not attributable to an applied merge ***")

    print(f"\nmerge candidates found (flag ON, over the OFF-planned contexts): {len(candidates)}"
          f"   applied: {len(applied)}   rejected (own checks failed): {len(rejected)}")
    for k in rejected:
        print(f"  REJECTED: {k}  failed_checks={on[k]['merge_failed_checks']}")

    # M1 kitchen/dining aspect, before/after, over exactly the contexts where a merge APPLIED —
    # "before" read off the SAME context's OFF run (the two source rooms, still separate there).
    before_aspects, after_aspects = [], []
    for k in applied:
        lid, kid = on[k]["merge_living_id"], on[k]["merge_kitchen_id"]
        off_rooms = off[k]["rooms"]
        if lid in off_rooms and kid in off_rooms:
            before_aspects.append(statistics.mean([_room_aspect(*off_rooms[lid]), _room_aspect(*off_rooms[kid])]))
        after_aspects.append(on[k]["merge_oriented_aspect"])

    print(f"\nM1 kitchen/dining aspect, subset where the merge fired (n={len(applied)}):")
    if before_aspects:
        print(f"  before (mean of the two source rooms' own gross aspect), median over the "
              f"subset: {statistics.median(before_aspects):.2f}")
    if after_aspects:
        print(f"  after (merged room's own oriented — AABB — aspect), median over the subset: "
              f"{statistics.median(after_aspects):.2f}")

    verdict_lost_ok = len(lost) == 0
    verdict_crashes_ok = len(crashes_off) == 0 and len(crashes_on) == 0
    verdict_signature_ok = all(on[k].get("merge_applied") is True for k in changed)
    print(f"\nVERDICT: LOST=0 {'PASS' if verdict_lost_ok else 'FAIL'}   "
          f"crashes=0 {'PASS' if verdict_crashes_ok else 'FAIL'}   "
          f"every signature change attributable to an applied merge "
          f"{'PASS' if verdict_signature_ok else 'FAIL'}")

    def _slim(rec: dict) -> dict:
        return {k: v for k, v in rec.items() if k != "rooms"}

    with open(Path(__file__).with_name("living_kitchen_merge_ab_result.json"), "w") as f:
        json.dump({"off": {k: _slim(v) for k, v in off.items()},
                  "on": {k: _slim(v) for k, v in on.items()}}, f, indent=1)


if __name__ == "__main__":
    main()
