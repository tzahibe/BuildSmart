"""Dead-space sweep (Issue #43) — calibrates `dead_space.py`'s PARAMETER constants against real
geometry before they gate anything.

Runs the frozen regression corpus (`tests/regression_corpus/corpus.json`, 432 contexts) plus the
canonical/hub/L geometry fixtures through the product path (or, for the hub, a hand-built fixture
of the same shape — see `test_circulation_metrics.py::_hub_design`'s own docstring for why) and
reports every measured region kind's own facts (`app.vertical_slice.dead_space.measure`).

    uv run python scripts/dead_space_sweep.py [--workers N] [--limit N]
                                              [--out ../docs/DEAD_SPACE_SWEEP.md]

Read-only. Run from `backend/`.
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spikes.failure_log_sweep.corpus_snapshot import CORPUS, corpus_contexts  # noqa: E402


def _run_one_raw(ctx: dict) -> dict:
    """Captures the raw `GeometricDesign` `app.demo.contract.to_demo_design` already builds
    `dead_space.measure` off (via a thin wrapper around the real function), so this sweep gets the
    full per-region breakdown (kind/length) without a second, duplicate product-path call."""
    from app.demo import contract as contract_module  # noqa: WPS433
    from app.demo import service as svc  # noqa: WPS433
    from app.vertical_slice import dead_space as ds  # noqa: WPS433
    from spikes.failure_log_sweep.sweep import key_of, project_from_context  # noqa: WPS433

    key = key_of(ctx)
    captured: dict = {}
    real_measure = ds.measure

    def _capturing_measure(design):
        result = real_measure(design)
        captured["metrics"] = result
        return result

    contract_module.dead_space.measure = _capturing_measure
    try:
        svc.generate_demo_design(project_from_context(ctx))
    except svc.DemoGenerationError as exc:
        return {"key": key, "status": "REFUSED", "code": exc.code}
    except Exception as exc:  # noqa: BLE001
        return {"key": key, "status": "CRASH", "error": f"{type(exc).__name__}: {exc}"}
    finally:
        contract_module.dead_space.measure = real_measure
    m = captured["metrics"]
    return {
        "key": key, "status": "PLANNED",
        "dead_space_m2": m.dead_space_m2, "dead_space_share": m.dead_space_share,
        "regions": [(r.kind, r.area_m2, r.length_m) for r in m.regions],
    }


def run_corpus(workers: int, limit: int | None, stride: int = 1) -> list[dict]:
    contexts = corpus_contexts(CORPUS)
    if stride > 1:
        contexts = contexts[::stride]
    if limit:
        contexts = contexts[:limit]
    if workers <= 1:
        return [_run_one_raw(c) for c in contexts]
    with mp.get_context("fork").Pool(workers) as pool:
        return pool.map(_run_one_raw, contexts, chunksize=4)


def _fixture_report() -> list[dict]:
    import tempfile

    from app.vertical_slice import dead_space as ds
    from app.vertical_slice.pipeline import run_demo

    out = []
    canonical = run_demo(tempfile.mktemp(suffix=".png")).design
    m = ds.measure(canonical)
    out.append({"name": "canonical (pipeline.run_demo, spine)", "dead_space_m2": m.dead_space_m2,
               "regions": [(r.kind, r.area_m2, r.length_m, r.detail) for r in m.regions]})

    from tests.vertical_slice.test_circulation_metrics import _hub_design, l_design  # noqa
    hub = _hub_design()
    m = ds.measure(hub)
    out.append({"name": "hub (hand-built, same shape spec 005 targets)",
               "dead_space_m2": m.dead_space_m2,
               "regions": [(r.kind, r.area_m2, r.length_m, r.detail) for r in m.regions]})
    return out


def _write_report(path: Path, corpus_results: list[dict], fixtures: list[dict],
                  workers: int, seconds: float) -> None:
    planned = [r for r in corpus_results if r["status"] == "PLANNED"]
    refused = [r for r in corpus_results if r["status"] == "REFUSED"]
    crashed = [r for r in corpus_results if r["status"] == "CRASH"]
    kind_counts = Counter()
    stub_lengths = []
    dead_space_values = [r["dead_space_m2"] for r in planned]
    for r in planned:
        for kind, area, length in r["regions"]:
            kind_counts[kind] += 1
            if kind == "STUB" and length is not None:
                stub_lengths.append(length)

    lines = [
        "# Dead-Space Sweep (Issue #43)",
        "",
        f"`scripts/dead_space_sweep.py` run over the frozen {len(corpus_results)}-context "
        f"regression corpus ({workers} worker(s), {seconds:.1f}s) plus geometry fixtures. "
        "Read-only: measures `app.vertical_slice.dead_space.measure` on whatever "
        "`app.demo.service.generate_demo_design` already produces.",
        "",
        "## Corpus outcome",
        "",
        f"- PLANNED: {len(planned)}",
        f"- REFUSED: {len(refused)}",
        f"- CRASH: {len(crashed)}",
        "",
        "## Region-kind counts among PLANNED contexts",
        "",
    ]
    for kind, count in sorted(kind_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"- {kind}: {count}")
    if not kind_counts:
        lines.append("- none — no PLANNED context has any measured dead-space region today")
    lines += ["", "## dead_space_m2 distribution", ""]
    if dead_space_values:
        lines.append(f"- min {min(dead_space_values):.2f} m2, max {max(dead_space_values):.2f} m2, "
                     f"mean {sum(dead_space_values) / len(dead_space_values):.2f} m2")
    if stub_lengths:
        lines.append(f"- STUB lengths: min {min(stub_lengths):.2f} m, max {max(stub_lengths):.2f} m, "
                     f"mean {sum(stub_lengths) / len(stub_lengths):.2f} m — "
                     "`DEAD_SPACE_STUB_HARD_LIMIT_M` is calibrated with headroom above this maximum.")
    else:
        lines.append("- no STUB region measured on any PLANNED corpus context")
    lines += ["", "## Geometry fixtures", ""]
    for f in fixtures:
        lines.append(f"### {f['name']}")
        lines.append("")
        lines.append(f"- dead_space_m2: {f['dead_space_m2']:.2f}")
        for kind, area, length, detail in f["regions"]:
            lines.append(f"  - {kind}: {area:.2f} m2"
                         + (f", {length:.2f} m" if length is not None else "") + f" — {detail}")
        if not f["regions"]:
            lines.append("  - no region measured")
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--stride", type=int, default=1)
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).resolve().parents[2] / "docs" / "DEAD_SPACE_SWEEP.md")
    args = parser.parse_args()

    t0 = time.time()
    corpus_results = run_corpus(args.workers, args.limit, args.stride)
    seconds = time.time() - t0

    fixtures = _fixture_report()
    _write_report(args.out, corpus_results, fixtures, args.workers, seconds)
    print(f"wrote {args.out} ({seconds:.1f}s, {len(corpus_results)} contexts)")


if __name__ == "__main__":
    main()
