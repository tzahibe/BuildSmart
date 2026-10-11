"""Entrance-to-circulation sweep (Issue #22, phase 0 — "reproduce first").

Runs the frozen regression corpus (`tests/regression_corpus/corpus.json`, 432 contexts) and a set
of geometry fixtures (the canonical single-level baseline, an L-massing candidate, and a hand-built
adversarial fixture) through the product path, and reports each shown plan's entrance-sequence
facts (`app.vertical_slice.entrance_sequence.measure`): arrival zone, corridor pocket length beyond
the door, distance to the first public opening, private doors passed, and the foyer/tunnel flags.

    uv run python scripts/entrance_sequence_sweep.py [--workers N] [--limit N]
                                                     [--out ../docs/ENTRANCE_CIRCULATION_SWEEP.md]

Read-only: measures what `app.demo.service.generate_demo_design` already produces; changes
nothing about planning or validation. Run from `backend/`.
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


def _parti_of(design) -> str:
    shape = design.outline.shape if design.outline else "RECTANGLE"
    if shape == "L":
        return "L"
    family = design.family or ""
    if family.startswith("HUB:"):
        return "HUB"
    return "SPINE/BAND"


def _run_one(ctx: dict) -> dict:
    # Imported inside the worker so `--workers N` forks cleanly (mirrors corpus_snapshot.py).
    from app.demo import service as svc  # noqa: WPS433
    from spikes.failure_log_sweep.sweep import key_of, project_from_context  # noqa: WPS433

    key = key_of(ctx)
    try:
        result = svc.generate_demo_design(project_from_context(ctx))
    except svc.DemoGenerationError as exc:
        return {"key": key, "status": "REFUSED", "code": exc.code}
    except Exception as exc:  # noqa: BLE001 — a crash is a result, not an abort
        return {"key": key, "status": "CRASH", "error": f"{type(exc).__name__}: {exc}"}
    seq = result.design.quality.entrance_sequence
    return {
        "key": key, "status": "PLANNED", "parti": _parti_of(result.design),
        "arrival_zone": seq.arrival_zone, "arrival_roles": list(seq.arrival_roles),
        "is_circulation_arrival": seq.is_circulation_arrival,
        "pocket_length_m": seq.pocket_length_m, "has_public_opening": seq.has_public_opening,
        "distance_to_public_m": seq.distance_to_public_m,
        "private_doors_passed": seq.private_doors_passed, "foyer": seq.foyer,
        "tunnel": seq.tunnel, "stray_pockets": seq.stray_pockets,
        "context": {k: ctx[k] for k in ("bedrooms", "wet_rooms", "safe_room", "open_plan",
                                        "footprint_width_m", "footprint_depth_m")},
    }


def run_corpus(workers: int, limit: int | None) -> list[dict]:
    contexts = corpus_contexts(CORPUS)
    if limit:
        contexts = contexts[:limit]
    if workers <= 1:
        return [_run_one(c) for c in contexts]
    with mp.get_context("fork").Pool(workers) as pool:
        return pool.map(_run_one, contexts, chunksize=4)


# --------------------------------------------------------------------------- geometry fixtures

def _canonical_fixture() -> dict:
    import tempfile

    from app.vertical_slice import entrance_sequence as es
    from app.vertical_slice.pipeline import run_demo

    out = str(Path(tempfile.mkdtemp()) / "canonical.png")
    result = run_demo(out)
    seq = es.measure(result.design)
    return {
        "name": "canonical (pipeline.run_demo, spine)", "arrival_zone": seq.arrival_zone,
        "pocket_length_m": seq.pocket_length_m, "has_public_opening": seq.has_public_opening,
        "distance_to_public_m": seq.distance_to_public_m,
        "private_doors_passed": seq.private_doors_passed, "foyer": seq.foyer,
        "tunnel": es.classify_tunnel(seq), "pocket_defect": es.classify_pocket(seq),
        "stray_pockets": seq.stray_pockets,
    }


def _l_massing_fixture() -> dict | None:
    from app.vertical_slice import entrance_sequence as es
    from app.vertical_slice import concept_generator as cg
    from app.vertical_slice import general_pipeline as gp
    from app.vertical_slice import geometry_fixtures as F
    from app.vertical_slice.geometry_core.engine import GeometryInfeasible, solve_fixture
    from app.vertical_slice.safe_adapter import AdapterOutcome, adapt, build_buildable_region
    from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec

    spec = ArchitecturalSpec(plot=PlotSpec(width_m=24.0, depth_m=32.0),
                             program=ProgramSpec(bedrooms=3, wet_rooms=2, safe_room=False))
    buildable = build_buildable_region(F.l_shaped_site_front_arm())
    adapter = adapt(buildable)
    if adapter.outcome is not AdapterOutcome.SOLVED:
        return None
    generated = cg.generate_concepts(spec, list(adapter.candidates))
    for index, candidate in enumerate(generated.candidates):
        try:
            solve = solve_fixture(candidate.concept.fixture)
        except GeometryInfeasible:
            continue
        plan = gp._realize(spec, buildable, None, candidate, index, solve, ())
        if plan.ok and plan.massing_signature == "2W":
            seq = es.measure(plan.design)
            return {
                "name": "L-massing (l_shaped_site_front_arm, MULTI_WING_SPLIT)",
                "arrival_zone": seq.arrival_zone, "pocket_length_m": seq.pocket_length_m,
                "has_public_opening": seq.has_public_opening,
                "distance_to_public_m": seq.distance_to_public_m,
                "private_doors_passed": seq.private_doors_passed, "foyer": seq.foyer,
                "tunnel": es.classify_tunnel(seq), "pocket_defect": es.classify_pocket(seq),
                "stray_pockets": seq.stray_pockets,
            }
    return None


def _failure_fixture() -> dict:
    """A hand-built adversarial fixture — the front door opens cleanly into LIVING, but a SEPARATE
    HALL zone independently fronts the street beside it with a genuinely dead 1.5 m stub before
    its own first door (AC-5's literal "1.5 m dead stub beside the entrance"), well past the
    calibrated `ENTRANCE_STRAY_POCKET_MAX_M`.

    Not produced by the generator today (see the report's own conclusion): the sweep found ZERO
    real contexts with a second circulation zone at all, the same situation `circulation_metrics.py`
    's own C26 test suite documents for its EXTREME case — "every REAL candidate this generator
    produces already measures comfortably inside the calibrated limits... that is the point of C26
    being additive, not a fixture this codebase can currently produce by accident." This fixture is
    the shared basis for `test_entrance_circulation.py`.
    """
    from app.vertical_slice import entrance_sequence as es
    from tests.vertical_slice.test_entrance_circulation import dead_stub_beside_entrance_design

    design = dead_stub_beside_entrance_design()
    seq = es.measure(design)
    return {
        "name": "hand-built: dead stub at the entrance",
        "arrival_zone": seq.arrival_zone, "pocket_length_m": seq.pocket_length_m,
        "has_public_opening": seq.has_public_opening,
        "distance_to_public_m": seq.distance_to_public_m,
        "private_doors_passed": seq.private_doors_passed, "foyer": seq.foyer,
        "tunnel": es.classify_tunnel(seq), "pocket_defect": es.classify_pocket(seq),
        "stray_pockets": seq.stray_pockets,
    }


# --------------------------------------------------------------------------- report

def _write_report(path: Path, corpus_results: list[dict], fixtures: list[dict],
                  workers: int, seconds: float) -> None:
    from app.vertical_slice.entrance_sequence import (
        ENTRANCE_POCKET_MAX_M, ENTRANCE_STRAY_POCKET_MAX_M, ENTRANCE_TUNNEL_MAX_M,
    )

    planned = [r for r in corpus_results if r["status"] == "PLANNED"]
    refused = [r for r in corpus_results if r["status"] == "REFUSED"]
    crashed = [r for r in corpus_results if r["status"] == "CRASH"]
    by_parti = Counter(r["parti"] for r in planned)
    pockets = [r for r in planned if r["pocket_length_m"] is not None
              and r["pocket_length_m"] > ENTRANCE_POCKET_MAX_M + 1e-9]
    stray_pockets = [r for r in planned if r["stray_pockets"]]
    no_public = [r for r in planned if not r["has_public_opening"]]
    tunnels = [r for r in planned if r["tunnel"]]
    pocket_lengths = [r["pocket_length_m"] for r in planned if r["pocket_length_m"] is not None]
    tunnel_distances = [r["distance_to_public_m"] for r in planned
                        if r["distance_to_public_m"] is not None]

    lines = [
        "# Entrance-to-Circulation Sweep (Issue #22)",
        "",
        f"Phase 0 — reproduce first. `scripts/entrance_sequence_sweep.py` run over the frozen "
        f"{len(corpus_results)}-context regression corpus (`{workers}` worker(s), "
        f"{seconds:.1f}s) plus three geometry fixtures. Read-only: measures "
        "`app.vertical_slice.entrance_sequence.measure` on whatever "
        "`app.demo.service.generate_demo_design` already produces.",
        "",
        "## Corpus outcome",
        "",
        f"- PLANNED: {len(planned)}",
        f"- REFUSED: {len(refused)}",
        f"- CRASH: {len(crashed)}",
        "",
        "## Parti distribution among PLANNED contexts",
        "",
    ]
    for parti, count in sorted(by_parti.items(), key=lambda kv: -kv[1]):
        lines.append(f"- {parti}: {count}")
    lines += [
        "",
        "## Pocket / tunnel counts",
        "",
        f"- Contexts with an arrival-zone pocket (`pocket_length_m > "
        f"{ENTRANCE_POCKET_MAX_M:.2f} m`, the calibrated `ENTRANCE_POCKET_MAX_M`): "
        f"{len(pockets)}",
        f"- Contexts with a STRAY pocket (a SEPARATE circulation zone beside the entrance, "
        f"unserved beyond {ENTRANCE_STRAY_POCKET_MAX_M:.2f} m, the calibrated "
        f"`ENTRANCE_STRAY_POCKET_MAX_M`): {len(stray_pockets)}",
        f"- Contexts with an arrival zone that has no path to a public room at all: "
        f"{len(no_public)}",
        f"- Contexts with a TUNNEL signal (reported, non-blocking, "
        f"`distance_to_public_m > {ENTRANCE_TUNNEL_MAX_M:.2f} m`, the calibrated "
        f"`ENTRANCE_TUNNEL_MAX_M`): {len(tunnels)}",
    ]
    if pocket_lengths:
        lines.append(
            f"- Measured `pocket_length_m` on the corpus: min {min(pocket_lengths):.2f} m, "
            f"max {max(pocket_lengths):.2f} m, mean "
            f"{sum(pocket_lengths) / len(pocket_lengths):.2f} m — this is why "
            f"`ENTRANCE_POCKET_MAX_M` needs headroom above the corpus (see "
            "`entrance_sequence.py`'s own docstring on the constant); "
            f"`ENTRANCE_STRAY_POCKET_MAX_M` needs none — {len(stray_pockets)} of "
            f"{len(planned)} PLANNED contexts have a second circulation zone at all.")
    if tunnel_distances:
        lines.append(
            f"- Measured `distance_to_public_m` on the corpus: min {min(tunnel_distances):.2f} m, "
            f"max {max(tunnel_distances):.2f} m, mean "
            f"{sum(tunnel_distances) / len(tunnel_distances):.2f} m — the range "
            "`ENTRANCE_TUNNEL_MAX_M` is calibrated against.")
    lines += ["", "## Geometry fixtures", ""]
    for f in fixtures:
        if f is None:
            continue
        lines.append(f"### {f['name']}")
        lines.append("")
        lines.append(f"- arrival zone: `{f['arrival_zone']}`")
        lines.append(f"- pocket length: {f['pocket_length_m']:.2f} m"
                     f" — {'FAILS C25' if f['pocket_defect'] else 'passes C25'}"
                     + (f" ({f['pocket_defect']})" if f["pocket_defect"] else ""))
        lines.append(f"- has a public opening: {f['has_public_opening']}")
        lines.append(f"- distance to first public opening: {f['distance_to_public_m']}")
        lines.append(f"- private doors passed: {f['private_doors_passed']}")
        lines.append(f"- foyer: {f['foyer']}")
        lines.append(f"- tunnel: {f['tunnel'] or 'no'}")
        lines.append(f"- stray pockets: {list(f['stray_pockets']) or 'none'}")
        lines.append("")
    lines += [
        "## Conclusion — the failure fixture",
        "",
        "No context in the frozen corpus, the canonical single-level baseline, or the L-massing "
        "candidate (`l_shaped_site_front_arm`) shows a genuine entrance POCKET or STRAY POCKET "
        "under this measurement: every real plan's nearest opening off the arrival zone is well "
        "under `ENTRANCE_POCKET_MAX_M`, and — because every real spine candidate has exactly one "
        "`HALL` leaf (`concept_generator.py`'s `_concept_from`) — no PLANNED context has a second "
        "circulation zone at all, so `ENTRANCE_STRAY_POCKET_MAX_M` (the Issue's own 0.6 m default, "
        "unchanged) has zero real contexts to conflict with. The L-massing candidate's own hall "
        "(which DOES front the street independently of a wider public band ~7 m back) opens onto a "
        "nearby door and passes C25 cleanly, with a real TUNNEL signal instead — matching the "
        "parti-change diagnosis in the Issue's own \"required behavior\" §3 (the tunnel is a "
        "non-blocking quality signal, not a gate). This mirrors `circulation_metrics.py`'s own C26 "
        "EXTREME case precedent (`test_circulation_metrics.py`'s docstring: \"every REAL candidate "
        "this generator produces already measures comfortably inside the calibrated limits ... "
        "that is the point of C26 being additive, not a fixture this codebase can currently "
        "produce by accident\").",
        "",
        "**The failure fixture used by `test_entrance_circulation.py` is therefore a hand-built "
        "adversarial `GeometricDesign`** (`dead_stub_beside_entrance_design`, in that test module): "
        "the front door opens cleanly into LIVING (no arrival pocket), but a SEPARATE HALL zone "
        "independently fronts the street beside it with a genuinely dead 1.5 m stub before its own "
        "first door (see that fixture above) — literally AC-5's \"1.5 m dead stub beside the "
        "entrance\", and the shape the Issue's own \"Current behavior\" section names — reproduced "
        "by hand because no swept context currently produces it by accident. A second hand-built "
        "fixture in the same test module (`_stray_pocket_design`) reproduces the SAME shape at a "
        "larger, less exact scale. The L-massing candidate above is the TUNNEL exemplar instead "
        "(a real, generator-produced case).",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).resolve().parents[2] / "docs"
                        / "ENTRANCE_CIRCULATION_SWEEP.md")
    args = parser.parse_args()

    t0 = time.time()
    corpus_results = run_corpus(args.workers, args.limit)
    seconds = time.time() - t0

    fixtures = [_canonical_fixture(), _l_massing_fixture(), _failure_fixture()]
    _write_report(args.out, corpus_results, fixtures, args.workers, seconds)
    print(f"wrote {args.out} ({seconds:.1f}s, {len(corpus_results)} contexts)")


if __name__ == "__main__":
    main()
