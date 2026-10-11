"""A/B of the real-plan room-proportion prior (Issue #140, Step 3) over the frozen, committed
432-context regression corpus (`tests/regression_corpus/corpus.json`) — flag OFF (shipped default)
vs flag ON (`ROOM_PROPORTION_PRIORS_ENABLED = True`).

    uv run python spikes/failure_log_sweep/room_proportion_priors_ab.py --save-off off.json --shard I/N --workers 8
    uv run python spikes/failure_log_sweep/room_proportion_priors_ab.py --save-on  on.json  --shard I/N --workers 8
    uv run python spikes/failure_log_sweep/room_proportion_priors_ab.py --merge-off merged_off.json off-0.json off-1.json ...
    uv run python spikes/failure_log_sweep/room_proportion_priors_ab.py --merge-on  merged_on.json  on-0.json  on-1.json ...
    uv run python spikes/failure_log_sweep/room_proportion_priors_ab.py --compare merged_off.json merged_on.json --report room-proportions-ab-report.json

Sharded the same way `corpus_snapshot.py` is (Issue #67), because the same runtime problem
applies here: this replays the whole corpus TWICE (once per flag value).

Reports: validity/refusal rate, M1 (habitable aspect median, `app.vertical_slice.quality_metrics`
— unchanged by this Issue, read only), room-area fidelity against the measured real distribution
(this Issue's own metric — the mean, over a plan's rooms that have a matching
`room_proportion_priors` row, of `|net_area_m2 - row.median_area_m2| / max(row.p75-row.p25, eps)`;
pooled median across every PLANNED context), and `primary_signature_changes` (which contexts'
`layout_signature`-equivalent changed and why).
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import multiprocessing as mp  # noqa: E402

from spikes.failure_log_sweep.corpus_snapshot import (  # noqa: E402
    CORPUS, _corpus_hash, _git_sha, _now_iso, corpus_contexts, shard_contexts,
)


def _room_fidelity(design) -> float | None:
    """This Issue's own metric, computed on the REALIZED plan — mirrors `priors_score`'s
    normalisation exactly, but reads `area_m2`/`type` off the delivered `app.demo.contract.RoomOut`
    instead of a pre-solve `ZoneSpec` target, since a full A/B can afford one realized plan per
    context. `area_m2` here is the NET (usable) area — the same definition Step 1's artifact
    measured from ResPlan's own `area_m2` field."""
    from app.knowledge.room_proportion_priors import (
        EmptyCorpusError, bedroom_count_bucket, house_size_bucket, load_priors_table,
    )
    from app.vertical_slice.room_proportion_priors import _ROLE_TO_PRIORS_ROLE

    try:
        table = load_priors_table()
    except EmptyCorpusError:
        return None
    footprint = design.gross_area_m2
    bedroom_count = sum(1 for r in design.rooms if r.type in ("BEDROOM", "MASTER_BEDROOM"))
    house_bucket = house_size_bucket(footprint, table.edges)
    bd_bucket = bedroom_count_bucket(bedroom_count, table.edges)
    deviations = []
    for room in design.rooms:
        priors_role = _ROLE_TO_PRIORS_ROLE.get(room.type, room.type)
        row = table.row_for(priors_role, house_bucket, bd_bucket)
        if row is None:
            continue
        spread = max(row.p75_area_m2 - row.p25_area_m2, 1e-3)
        deviations.append(abs(room.area_m2 - row.median_area_m2) / spread)
    return round(sum(deviations) / len(deviations), 6) if deviations else None


def _run_one(args: tuple[dict, bool]) -> tuple[str, dict]:
    ctx, flag_on = args
    from app.demo import service as svc  # noqa: E402
    from app.vertical_slice import room_proportion_priors as rpp  # noqa: E402
    from app.vertical_slice.quality_metrics import measure_design  # noqa: E402
    from spikes.failure_log_sweep.sweep import key_of, project_from_context, signature  # noqa: E402

    rpp.ROOM_PROPORTION_PRIORS_ENABLED = flag_on
    key = key_of(ctx)
    t0 = time.perf_counter()
    try:
        res = svc.generate_demo_design(project_from_context(ctx))
        out = {"status": "PLANNED", "sig": [list(s) for s in signature(res.design)],
              "area": res.design.gross_area_m2,
              "m1_habitable_aspect_median": measure_design(res.design).m1_habitable_aspect_median,
              "room_fidelity": _room_fidelity(res.design)}
    except svc.DemoGenerationError as exc:
        out = {"status": "REFUSED", "code": exc.code}
    except Exception as exc:  # noqa: BLE001 — a crash is a result, not an abort
        out = {"status": "CRASH", "code": f"{type(exc).__name__}: {exc}"}
    out["ms"] = round((time.perf_counter() - t0) * 1000, 1)
    out["context"] = {k: ctx[k] for k in ("plot_width_m", "plot_depth_m", "street_facing_side",
                                          "built_area_m2", "footprint_width_m", "footprint_depth_m",
                                          "bedrooms", "wet_rooms", "safe_room", "open_plan")}
    return key, out


def run_all(contexts: list[dict], flag_on: bool, workers: int) -> dict:
    tasks = [(c, flag_on) for c in contexts]
    if workers <= 1:
        results = [_run_one(t) for t in tasks]
    else:
        with mp.get_context("fork").Pool(workers) as pool:
            results = pool.map(_run_one, tasks, chunksize=4)
    return dict(sorted(results))


def save(path: Path, flag_on: bool, workers: int, shard: str | None) -> dict:
    contexts = shard_contexts(shard, CORPUS) if shard else corpus_contexts(CORPUS)
    t0 = time.time()
    results = run_all(contexts, flag_on, workers)
    doc = {"version": 1, "sha": _git_sha(), "corpus_hash": _corpus_hash(CORPUS), "flag_on": flag_on,
          "workers": workers, "seconds": round(time.time() - t0, 1), "written_at": _now_iso(),
          "results": results}
    if shard:
        doc["shard"] = shard
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    print(f"saved {len(contexts)} scenarios (flag_on={flag_on}, shard={shard}) in "
         f"{doc['seconds']}s ({workers} workers)")
    return doc


def merge(out_path: Path, shard_paths: list[Path]) -> dict:
    docs = [json.load(open(p, encoding="utf-8")) for p in shard_paths]
    hashes = {d["corpus_hash"] for d in docs}
    if len(hashes) != 1:
        raise SystemExit(f"shard corpus_hash mismatch: {hashes}")
    merged_results: dict = {}
    for d in docs:
        merged_results.update(d["results"])
    expected = len(corpus_contexts(CORPUS))
    if len(merged_results) != expected:
        raise SystemExit(f"merged {len(merged_results)} results, expected {expected} — a shard is "
                         "missing or a context was duplicated")
    merged = {**docs[0], "results": merged_results, "seconds": sum(d["seconds"] for d in docs)}
    merged.pop("shard", None)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(merged, f)
    print(f"merged {len(shard_paths)} shard(s) into {out_path}: {len(merged_results)} result(s)")
    return merged


def _status_counts(results: dict) -> dict:
    c = Counter(v["status"] for v in results.values())
    return {"planned": c.get("PLANNED", 0), "refused": c.get("REFUSED", 0),
           "crashes": c.get("CRASH", 0), "total": len(results)}


def _median(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 4) if xs else None


def compare(off_doc: dict, on_doc: dict) -> dict:
    off, on = off_doc["results"], on_doc["results"]
    keys = sorted(set(off) | set(on))
    lost, gained, new_crashes, status_changes, code_changes, sig_changes = [], [], [], [], [], []
    for k in keys:
        b, a = off.get(k), on.get(k)
        if b is None or a is None:
            status_changes.append({"key": k, "note": "context present on one side only"})
            continue
        row = {"key": k, "context": a["context"], "off_status": b["status"], "on_status": a["status"]}
        if b["status"] == "PLANNED" and a["status"] != "PLANNED":
            lost.append({**row, "on_code": a.get("code")})
        elif b["status"] != "PLANNED" and a["status"] == "PLANNED":
            gained.append({**row, "on_area": a.get("area")})
        elif b["status"] != a["status"]:
            status_changes.append(row)
        elif b["status"] == "REFUSED" and b.get("code") != a.get("code"):
            code_changes.append({**row, "off_code": b.get("code"), "on_code": a.get("code")})
        elif b["status"] == "PLANNED" and b["sig"] != a["sig"]:
            sig_changes.append({**row, "off_area": b.get("area"), "on_area": a.get("area")})
        if a["status"] == "CRASH" and b["status"] != "CRASH":
            new_crashes.append({**row, "error": a.get("code")})
    return {
        "off": _status_counts(off), "on": _status_counts(on),
        "lost": lost, "gained": gained, "crashes": new_crashes, "status_changes": status_changes,
        "refusal_code_changes": code_changes, "primary_signature_changes": sig_changes,
        "byte_identical_primaries": sum(
            1 for k in keys if k in off and k in on and off[k]["status"] == "PLANNED"
            and on[k]["status"] == "PLANNED" and off[k]["sig"] == on[k]["sig"]),
        "m1_habitable_aspect_median": {
            "off": _median([v.get("m1_habitable_aspect_median") for v in off.values()
                            if v["status"] == "PLANNED"]),
            "on": _median([v.get("m1_habitable_aspect_median") for v in on.values()
                           if v["status"] == "PLANNED"]),
        },
        "room_fidelity_median": {
            "off": _median([v.get("room_fidelity") for v in off.values() if v["status"] == "PLANNED"]),
            "on": _median([v.get("room_fidelity") for v in on.values() if v["status"] == "PLANNED"]),
        },
        "refusal_codes": {
            "off": dict(Counter(v.get("code") for v in off.values() if v["status"] == "REFUSED")),
            "on": dict(Counter(v.get("code") for v in on.values() if v["status"] == "REFUSED")),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--save-off", metavar="OUT.json")
    g.add_argument("--save-on", metavar="OUT.json")
    g.add_argument("--merge-off", nargs="+", metavar="FILE")
    g.add_argument("--merge-on", nargs="+", metavar="FILE")
    g.add_argument("--compare", nargs=2, metavar=("OFF.json", "ON.json"))
    ap.add_argument("--report", metavar="REPORT.json")
    ap.add_argument("--shard", metavar="I/N")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    if args.save_off:
        save(Path(args.save_off), False, args.workers, args.shard)
    elif args.save_on:
        save(Path(args.save_on), True, args.workers, args.shard)
    elif args.merge_off:
        out, *shards = args.merge_off
        merge(Path(out), [Path(p) for p in shards])
    elif args.merge_on:
        out, *shards = args.merge_on
        merge(Path(out), [Path(p) for p in shards])
    elif args.compare:
        off_doc = json.load(open(args.compare[0], encoding="utf-8"))
        on_doc = json.load(open(args.compare[1], encoding="utf-8"))
        report = compare(off_doc, on_doc)
        if args.report:
            with open(args.report, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
        print(json.dumps({k: v for k, v in report.items()
                          if k not in ("lost", "gained", "status_changes", "refusal_code_changes",
                                      "primary_signature_changes", "crashes")}, indent=2))
        print(f"LOST={len(report['lost'])} GAINED={len(report['gained'])} "
             f"primary_signature_changes={len(report['primary_signature_changes'])} "
             f"crashes={len(report['crashes'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
