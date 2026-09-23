"""Stage 0 (Issue #118) A/B: the LIVING+KITCHEN merge (spike #107) over the full 432-context
frozen corpus, with the exact facts the flip rule needs and three before/after SVG pairs.

Extends `spikes/failure_log_sweep/living_kitchen_merge_ab.py` (Issue #107's own spike sweep,
LOST/crashes/signature-changes only) with: status-class changes (PLANNED/REFUSED/CRASH),
refusal-code changes on contexts REFUSED both sides, and the M1-M6 corpus deltas flag-off vs
flag-on (`quality_metrics.find_regressions`, the same tolerance-checked comparison the corpus
regression test already uses).

    uv run python scripts/stage0_merge_ab.py --start 0 --count 120
    uv run python scripts/stage0_merge_ab.py --start 120 --count 120
    ...
    uv run python scripts/stage0_merge_ab.py --report
    uv run python scripts/stage0_merge_ab.py --svgs

CHUNKED BY DESIGN, matching the spike script's own reasoning: ~2-5s/context/flag-state, so the
full 432-context corpus is ~35-45 CPU-minutes — too long for one bounded call. `--start`/`--count`
processes one slice and MERGES it into `stage0_merge_ab_result.json` beside this file (previous
chunks' own entries are kept); `--report` reads that accumulated file; `--svgs` picks three
applied-merge contexts and writes before/after SVG pairs into
`docs/reports/rectilinear-realizer/svg/`.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_ROOT.parent
CORPUS_PATH = _BACKEND_ROOT / "tests" / "regression_corpus" / "corpus.json"
RESULT_PATH = Path(__file__).with_name("stage0_merge_ab_result.json")
SVG_DIR = _REPO_ROOT / "docs" / "reports" / "rectilinear-realizer" / "svg"


def _load_contexts(start: int = 0, count: int | None = None) -> tuple[list[tuple[str, dict]], int]:
    with open(CORPUS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    cases = data["cases"]
    total = len(cases)
    end = total if count is None else min(total, start + count)
    return [(case["source_key"], case["context"]) for case in cases[start:end]], total


def _load_accumulated() -> dict:
    if not RESULT_PATH.exists():
        return {"off": {}, "on": {}}
    with open(RESULT_PATH, encoding="utf-8") as f:
        return json.load(f)


def _metrics_dict(design) -> dict:
    from app.vertical_slice import quality_metrics as qm
    m = dataclasses.asdict(qm.measure_design(design))
    adjacent, total = qm.wet_adjacency_counts(design)
    m["m5_wet_adjacent_count"] = adjacent
    m["m5_wet_total_count"] = total
    return m


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
                      metrics=_metrics_dict(res.design))
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


def _m1_m2_summary(rows: list[dict]) -> dict:
    """Diagnostic (not gated — `baseline_summary`'s own convention): M1/M2 read off the stored
    per-plan medians/ratios directly, not re-pooled from individual rooms (those aren't kept in
    the stored metrics dict, matching `corpus_snapshot.py`'s own precedent for M3/M4/M5/M6)."""
    m1 = [r["m1_habitable_aspect_median"] for r in rows if r.get("m1_habitable_aspect_median") is not None]
    m2 = [r["m2_habitable_on_envelope_ratio"] for r in rows if r.get("m2_habitable_on_envelope_ratio") is not None]
    return {
        "m1_habitable_aspect_median_of_medians": statistics.median(m1) if m1 else None,
        "m2_habitable_on_envelope_mean": statistics.mean(m2) if m2 else None,
    }


def cmd_report() -> None:
    from app.vertical_slice import quality_metrics as qm

    accumulated = _load_accumulated()
    off, on = accumulated["off"], accumulated["on"]
    total = accumulated.get("_source_context_count")
    lines = []

    def p(*a):
        s = " ".join(str(x) for x in a)
        print(s)
        lines.append(s)

    p(f"accumulated: {len(off)}/{total if total else '?'} contexts")
    if total and len(off) < total:
        p(f"*** INCOMPLETE — {total - len(off)} contexts not yet run; report is over the "
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

    status_changes = [k for k in off if off[k]["status"] != on[k]["status"]]
    both_refused = [k for k in off if off[k]["status"] == "REFUSED" and on[k]["status"] == "REFUSED"]
    refusal_code_changes = [k for k in both_refused if off[k]["code"] != on[k]["code"]]

    p(f"\nplanned OFF={len(planned_off)}  ON={sum(1 for v in on.values() if v['status'] == 'PLANNED')}")
    p(f"LOST: {len(lost)}   crashes OFF={len(crashes_off)} ON={len(crashes_on)}")
    for k in lost:
        p("  LOST:", k, "->", on[k].get("code") or on[k]["status"])
    for k in crashes_on:
        p("  CRASH ON:", k, "->", on[k]["code"])
    for k in crashes_off:
        p("  CRASH OFF:", k, "->", off[k]["code"])

    p(f"\nstatus_changes (any context whose PLANNED/REFUSED/CRASH class differs OFF vs ON): "
      f"{len(status_changes)}")
    for k in status_changes:
        p(f"  STATUS CHANGED: {k}  off={off[k]['status']} on={on[k]['status']}")
    p(f"refusal_code_changes (both sides REFUSED, code differs): {len(refusal_code_changes)}")
    for k in refusal_code_changes:
        p(f"  REFUSAL CODE CHANGED: {k}  off={off[k]['code']} on={on[k]['code']}")

    p(f"\nbyte-identical primary signatures (OFF==ON): {len(identical)}/{len(planned_off)}")
    p(f"primary-signature changes: {len(changed)}")
    unexplained = [k for k in changed if on[k].get("merge_applied") is not True]
    for k in unexplained:
        p(f"  CHANGED (unexplained): {k}  merge_applied={on[k].get('merge_applied')}  "
          f"failed_checks={on[k].get('merge_failed_checks')}")

    p(f"\nmerge candidates found (flag ON, over the OFF-planned contexts): {len(candidates)}"
      f"   applied: {len(applied)}   rejected (own checks failed): {len(rejected)}")
    reason_counts: dict[tuple, int] = {}
    for k in rejected:
        reason = tuple(sorted(on[k]["merge_failed_checks"]))
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    for reason, n in sorted(reason_counts.items(), key=lambda kv: -kv[1]):
        p(f"  rejected on {'+'.join(reason)}: {n}")

    # ------------------------------------------------------------------------- M1-M6 deltas
    off_rows = [off[k]["metrics"] for k in off if off[k]["status"] == "PLANNED"]
    on_rows = [on[k]["metrics"] for k in on if on[k]["status"] == "PLANNED"]
    off_baseline = qm.baseline_summary_from_metrics(off_rows)
    on_baseline = qm.baseline_summary_from_metrics(on_rows)
    off_m1m2 = _m1_m2_summary(off_rows)
    on_m1m2 = _m1_m2_summary(on_rows)
    regressions = qm.find_regressions(off_baseline, on_baseline)

    p("\nM1-M6 corpus deltas, flag OFF -> ON (before/after, over all PLANNED contexts):")
    p(f"  M1 habitable aspect (median of per-plan medians): "
      f"{off_m1m2['m1_habitable_aspect_median_of_medians']:.3f} -> "
      f"{on_m1m2['m1_habitable_aspect_median_of_medians']:.3f}  (diagnostic, not gated)")
    p(f"  M2 habitable-on-envelope (mean of per-plan ratios): "
      f"{off_m1m2['m2_habitable_on_envelope_mean']:.3f} -> "
      f"{on_m1m2['m2_habitable_on_envelope_mean']:.3f}  (diagnostic, not gated)")
    p(f"  M3 circulation-share median: {off_baseline['m3_circulation_share_median']:.4f} -> "
      f"{on_baseline['m3_circulation_share_median']:.4f}  (tolerance {qm.CIRCULATION_SHARE_TOLERANCE})")
    p(f"  M4 hall aspect median: {off_baseline['m4_hall_aspect_median']:.3f} -> "
      f"{on_baseline['m4_hall_aspect_median']:.3f}  (tolerance {qm.HALL_ASPECT_TOLERANCE})")
    p(f"  M5 wet-adjacency share: {off_baseline['m5_wet_adjacency_share']:.4f} -> "
      f"{on_baseline['m5_wet_adjacency_share']:.4f}  (tolerance {qm.WET_ADJACENCY_SHARE_TOLERANCE})")
    p(f"  M6 public-contiguous share: {off_baseline['m6_public_contiguous_share']:.4f} -> "
      f"{on_baseline['m6_public_contiguous_share']:.4f}  "
      f"(tolerance {qm.PUBLIC_CONTIGUOUS_SHARE_TOLERANCE})")
    p(f"  M1-M6 regressions beyond tolerance: {regressions or 'NONE'}")

    applied_aspects = [on[k]["merge_oriented_aspect"] for k in applied]
    if applied_aspects:
        p(f"\nmerged room's own oriented (AABB) aspect over the {len(applied)} applied contexts: "
          f"median {statistics.median(applied_aspects):.2f}")

    # ------------------------------------------------------------------------- the flip rule
    from app.vertical_slice import room_merge
    default_on, verdict = room_merge.decide_default(
        lost=len(lost), crashes=len(crashes_off) + len(crashes_on),
        status_changes=len(status_changes), refusal_code_changes=len(refusal_code_changes),
        m_regressions=regressions)
    complete = bool(total) and len(off) == total
    p(f"\nFLIP RULE ({'COMPLETE' if complete else 'PARTIAL'} — {len(off)}/{total or '?'}): {verdict}")

    with open(Path(__file__).with_name("stage0_merge_ab_report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _room_bbox_svg_elems(room, scale: float) -> str:
    x, y = room.x * scale, room.y * scale
    if room.shape == "L" and room.polygon_m:
        pts = " ".join(f"{px * scale:.1f},{py * scale:.1f}" for px, py in room.polygon_m)
        fill = "#ffe6b3"
        shape_el = f'<polygon points="{pts}" fill="{fill}" stroke="#333" stroke-width="1.5"/>'
        cx = sum(px for px, _ in room.polygon_m) / len(room.polygon_m) * scale
        cy = sum(py for _, py in room.polygon_m) / len(room.polygon_m) * scale
    else:
        w, h = room.gross_width_m * scale, room.gross_depth_m * scale
        fill = "#dbe9ff" if "HALL" not in room.type and "CIRC" not in room.type else "#eeeeee"
        shape_el = f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}" stroke="#333" stroke-width="1.5"/>'
        cx, cy = x + w / 2, y + h / 2
    label = f'<text x="{cx:.1f}" y="{cy:.1f}" font-size="11" text-anchor="middle" fill="#111">{room.name}</text>'
    return shape_el + label


def render_svg(design, title: str) -> str:
    scale = 20.0
    max_x = max((r.x + r.gross_width_m for r in design.rooms), default=10.0)
    max_y = max((r.y + r.gross_depth_m for r in design.rooms), default=10.0)
    width, height = max_x * scale + 40, max_y * scale + 60
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
             f'viewBox="0 0 {width:.0f} {height:.0f}">',
             f'<rect width="100%" height="100%" fill="white"/>',
             f'<text x="10" y="20" font-size="14" font-weight="bold">{title}</text>',
             '<g transform="translate(10,30)">']
    for room in design.rooms:
        parts.append(_room_bbox_svg_elems(room, scale))
    for wall in design.walls:
        if wall.orientation == "vertical":
            x = wall.coord * scale
            parts.append(f'<line x1="{x:.1f}" y1="{wall.start * scale:.1f}" x2="{x:.1f}" '
                         f'y2="{wall.end * scale:.1f}" stroke="#333" stroke-width="2"/>')
        else:
            y = wall.coord * scale
            parts.append(f'<line x1="{wall.start * scale:.1f}" y1="{y:.1f}" '
                         f'x2="{wall.end * scale:.1f}" y2="{y:.1f}" stroke="#333" stroke-width="2"/>')
    parts.append("</g></svg>")
    return "\n".join(parts)


def cmd_svgs(n: int) -> None:
    from app.vertical_slice import room_merge
    from app.demo import service as svc
    from spikes.failure_log_sweep.sweep import project_from_context

    accumulated = _load_accumulated()
    off, on = accumulated["off"], accumulated["on"]
    applied = [k for k, v in off.items() if v["status"] == "PLANNED"
              and on.get(k, {}).get("merge_applied") is True]
    if not applied:
        raise SystemExit("no applied-merge contexts in the accumulated result — run chunks first")

    with open(CORPUS_PATH, encoding="utf-8") as f:
        all_cases = json.load(f)["cases"]
    cases = {c["source_key"]: c["context"] for c in all_cases}
    index_of = {c["source_key"]: i for i, c in enumerate(all_cases)}

    SVG_DIR.mkdir(parents=True, exist_ok=True)
    # Prefer the most oriented (least square-like) applied merges first — those are more likely
    # to be genuine (non-flush) L's rather than a flush rectangle, so the SVG pairs are more
    # informative to look at (AC-4: "judgeable by eye").
    applied.sort(key=lambda k: on[k].get("merge_oriented_aspect", 0.0), reverse=True)
    chosen = applied[:n]
    print(f"rendering {len(chosen)} before/after pairs: contexts {[index_of[k] for k in chosen]}")
    for key in chosen:
        ctx = cases[key]
        project = project_from_context(ctx)
        room_merge.LIVING_KITCHEN_MERGE_ENABLED = False
        before = svc.generate_demo_design(project).design
        room_merge.LIVING_KITCHEN_MERGE_ENABLED = True
        after = svc.generate_demo_design(project).design
        safe = f"context-{index_of[key]:03d}"
        (SVG_DIR / f"{safe}-before.svg").write_text(
            render_svg(before, f"{key} — before (flag OFF)"), encoding="utf-8")
        (SVG_DIR / f"{safe}-after.svg").write_text(
            render_svg(after, f"{key} — after (flag ON, merge applied)"), encoding="utf-8")
        print(f"  wrote {safe}-before.svg / {safe}-after.svg")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--count", type=int, default=None)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--svgs", action="store_true")
    ap.add_argument("--svg-count", type=int, default=3)
    args = ap.parse_args()
    if args.report:
        cmd_report()
    elif args.svgs:
        cmd_svgs(args.svg_count)
    else:
        cmd_chunk(args.start, args.count)


if __name__ == "__main__":
    main()
