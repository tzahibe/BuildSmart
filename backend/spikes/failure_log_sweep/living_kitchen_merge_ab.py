"""A/B of the Architecture A spike (Issue #107) over the real 432-context corpus.

    uv run python spikes/failure_log_sweep/living_kitchen_merge_ab.py --start 0 --count 120
    uv run python spikes/failure_log_sweep/living_kitchen_merge_ab.py --start 120 --count 120
    ...
    uv run python spikes/failure_log_sweep/living_kitchen_merge_ab.py --report

OFF is today's shipped code (`room_merge.LIVING_KITCHEN_MERGE_ENABLED = False`, unconditionally
short-circuiting `plan_merge` to `None`); ON flips the flag for the same run. Reads the same
432-context corpus `tests/regression_corpus/corpus.json` already freezes (Issue #66's own trusted
snapshot), not the raw failure log — this script needs no LLM/network call either way.

CHUNKED BY DESIGN: each context takes ~2-3s through the real outline-search pipeline (both flag
states), so the full 432-context corpus is ~35-45 CPU-minutes — too long for one bounded
foreground call. `--start`/`--count` processes one slice and MERGES it into
`living_kitchen_merge_ab_result.json` beside this file (previous chunks' entries are kept,
untouched); `--report` reads that accumulated file and prints the aggregate gates, with no need
to re-solve anything. Re-running the SAME `--start`/`--count` overwrites just that slice's own
entries (idempotent).

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

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

CORPUS_PATH = Path(__file__).resolve().parents[2] / "tests" / "regression_corpus" / "corpus.json"
RESULT_PATH = Path(__file__).with_name("living_kitchen_merge_ab_result.json")


def _load_contexts(start: int = 0, count: int | None = None) -> list[tuple[str, dict]]:
    with open(CORPUS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    cases = data["cases"]
    total = len(cases)
    end = total if count is None else min(total, start + count)
    return [(case["source_key"], case["context"]) for case in cases[start:end]], total


def _room_aspect(gross_w: float, gross_h: float) -> float:
    return max(gross_w, gross_h) / max(min(gross_w, gross_h), 1e-6)


def _load_accumulated() -> dict:
    if not RESULT_PATH.exists():
        return {"off": {}, "on": {}}
    with open(RESULT_PATH, encoding="utf-8") as f:
        return json.load(f)


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
            rec = dict(status="PLANNED", sig=list(signature(res.design)),
                      rooms={r.id: [r.gross_width_m, r.gross_depth_m] for r in res.design.rooms})
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
        if i % 40 == 0:
            print(f"  flag={flag} {i}/{len(contexts)}", flush=True)
    print(f"  flag={flag} done in {time.perf_counter() - started:.0f}s", flush=True)
    return out


def cmd_chunk(start: int, count: int) -> None:
    contexts, total = _load_contexts(start, count)
    print(f"chunk: contexts[{start}:{start + len(contexts)}] of {total}")
    accumulated = _load_accumulated()
    off = run_all(contexts, False)
    on = run_all(contexts, True)
    accumulated["off"].update(off)
    accumulated["on"].update(on)
    accumulated["_source_context_count"] = total
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(accumulated, f, indent=1)
    print(f"merged {len(off)} contexts into {RESULT_PATH.name} "
          f"({len(accumulated['off'])}/{total} accumulated so far)")


def cmd_report() -> None:
    accumulated = _load_accumulated()
    off, on = accumulated["off"], accumulated["on"]
    total = accumulated.get("_source_context_count")
    print(f"accumulated: {len(off)}/{total if total else '?'} contexts")
    if total and len(off) < total:
        print(f"*** INCOMPLETE — {total - len(off)} contexts not yet run; report is over the "
              f"accumulated subset only ***")

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
    for k in crashes_off:
        print("  CRASH OFF:", k, "->", off[k]["code"])

    print(f"\nbyte-identical primary signatures (OFF==ON): {len(identical)}/{len(planned_off)}")
    print(f"primary-signature changes: {len(changed)}")
    for k in changed:
        applied_here = on[k].get("merge_applied")
        if applied_here is not True:
            print(f"  CHANGED (unexplained): {k}  merge_applied={applied_here}  "
                  f"failed_checks={on[k].get('merge_failed_checks')}")

    print(f"\nmerge candidates found (flag ON, over the OFF-planned contexts): {len(candidates)}"
          f"   applied: {len(applied)}   rejected (own checks failed): {len(rejected)}")
    for k in rejected:
        print(f"  REJECTED: {k}  failed_checks={on[k]['merge_failed_checks']}")

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
    complete = bool(total) and len(off) == total
    print(f"\nVERDICT ({'COMPLETE' if complete else 'PARTIAL'} — {len(off)}/{total or '?'}): "
          f"LOST=0 {'PASS' if verdict_lost_ok else 'FAIL'}   "
          f"crashes=0 {'PASS' if verdict_crashes_ok else 'FAIL'}   "
          f"every signature change attributable to an applied merge "
          f"{'PASS' if verdict_signature_ok else 'FAIL'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--count", type=int, default=None,
                    help="contexts[start:start+count]; omit for 'to the end' (only use this for "
                         "the full corpus if you have ~35-45 CPU-minutes free — see the module "
                         "docstring for the chunked alternative)")
    ap.add_argument("--report", action="store_true",
                    help="skip solving; print the aggregate report over whatever has already "
                         "been merged into living_kitchen_merge_ab_result.json")
    args = ap.parse_args()
    if args.report:
        cmd_report()
    else:
        cmd_chunk(args.start, args.count)


if __name__ == "__main__":
    main()
