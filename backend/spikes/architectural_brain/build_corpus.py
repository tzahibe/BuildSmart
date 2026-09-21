"""Builds the committed POC corpus: ``backend/spikes/architectural_brain/corpus/*.json``.

    RESPLAN_PKL=/path/to/ResPlan.pkl uv run python3 spikes/architectural_brain/build_corpus.py

Selection (matches ROOT #93 / Issue #94): all Villa / IndependentHouse / BuilderFloor with >= 3
bedrooms, plus Apartment with 3-5 bedrooms — the dataset is heavily Apartment-dominated
(15,854/17,107), so this filter is what makes the corpus "biased to 3-5 bedrooms" rather than
skewed to the 1-2 bedroom units that dominate raw ResPlan.

Deduplication: ResPlan has near-duplicate republished listings (README: 1,170 redundant plans in
931 clusters, geometry-based). This script cannot reproduce that exact geometric scan without the
paper's tooling, so it uses a documented, deterministic proxy fingerprint instead — see
``_dedup_key`` and ``docs/reports/poc-architectural-brain/dataset.md``.

Sampling: a fixed stride across the deduplicated candidate list (by original ResPlan ``id`` order),
not the first N — the dataset is not shuffled, and taking a stride avoids biasing the corpus toward
whatever happens to be scraped/ordered first.
"""
from __future__ import annotations

import os
import pickle
import sys
from collections import Counter

from shapely.geometry import MultiPolygon, Polygon

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from spikes.architectural_brain.patterns import derive_pattern
from spikes.architectural_brain.resplan_ingest import PlanRejected, normalise

DEFAULT_RESPLAN_PKL = "/Users/mymacbook/projects/datasets/resplan/ResPlan.pkl"
CORPUS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "corpus")
TARGET_CORPUS_SIZE = 200
MIN_CORPUS_SIZE = 100

ATTRIBUTION_TEXT = """# Attribution

This corpus is derived from **ResPlan: A Large-Scale Vector-Graph Dataset of 17,000 Residential
Floor Plans** (Abouagour & Garyfallidis, 2025, arXiv:2508.14006).

Licence: **CC BY 4.0** (data). See the original dataset's `LICENSE` file for the full grant.

Each `*.json` file in this directory is a normalised `PlanReference` derived from one ResPlan plan
(`provenance.source_plan_id` records the original ResPlan `id`) plus its `ArchitecturalPattern`.
Geometry has been rescaled to metres and re-expressed in BuildSmart's schema; no ResPlan source
images, listing text, prices, addresses or personally identifying information are included (ResPlan
itself contains none).

See `docs/reports/poc-architectural-brain/dataset.md` for the full field-by-field description.
"""


def _nparts(geom) -> int:
    if geom is None:
        return 0
    if isinstance(geom, Polygon):
        return 0 if geom.is_empty else 1
    if isinstance(geom, MultiPolygon):
        return len([g for g in geom.geoms if not g.is_empty])
    return 0


def _is_candidate(plan: dict) -> bool:
    unit_type = plan.get("unitType")
    n_bedrooms = _nparts(plan.get("bedroom"))
    if unit_type in ("Villa", "IndependentHouse", "BuilderFloor"):
        return n_bedrooms >= 3
    if unit_type == "Apartment":
        return 3 <= n_bedrooms <= 5
    return False


def _dedup_key(plan: dict) -> tuple:
    def area(key: str) -> float:
        geom = plan.get(key)
        return round(geom.area, 0) if geom is not None and not geom.is_empty else 0.0

    return (
        plan.get("unitType"),
        round(float(plan.get("net_area") or 0.0), 0),
        round(float(plan.get("area") or 0.0), 1),
        area("bedroom"), area("bathroom"), area("kitchen"), area("living"), area("storage"),
        _nparts(plan.get("bedroom")), _nparts(plan.get("bathroom")), _nparts(plan.get("door")),
    )


def _load_candidates(data: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    candidates = []
    for plan in data:
        if not _is_candidate(plan):
            continue
        key = _dedup_key(plan)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(plan)
    return candidates


def build_corpus(pkl_path: str, out_dir: str = CORPUS_DIR,
                  target: int = TARGET_CORPUS_SIZE) -> dict:
    with open(pkl_path, "rb") as f:
        data = pickle.load(f)

    candidates = _load_candidates(data)
    stride = max(1, len(candidates) // target)
    strided = candidates[::stride][:target]
    strided_ids = {id(p) for p in strided}
    remainder = [p for p in candidates if id(p) not in strided_ids]

    os.makedirs(out_dir, exist_ok=True)
    for name in os.listdir(out_dir):
        if name.endswith(".json"):
            os.remove(os.path.join(out_dir, name))

    rejects: Counter = Counter()
    class_counts: Counter = Counter()
    written = 0

    def _try_write(plan: dict) -> bool:
        nonlocal written
        try:
            ref = normalise(plan)
        except PlanRejected as e:
            rejects[e.reason.split(":")[0]] += 1
            return False
        pattern = derive_pattern(ref)
        class_counts[pattern.circulation_class] += 1
        out = {"plan_reference": ref.to_dict(), "architectural_pattern": pattern.to_dict()}
        path = os.path.join(out_dir, f"resplan_{ref.plan_id}.json")
        with open(path, "w") as f:
            import json
            json.dump(out, f, indent=2, sort_keys=True)
        written += 1
        return True

    for plan in strided:
        _try_write(plan)

    idx = 0
    while written < MIN_CORPUS_SIZE and idx < len(remainder):
        _try_write(remainder[idx])
        idx += 1

    with open(os.path.join(out_dir, "ATTRIBUTION.md"), "w") as f:
        f.write(ATTRIBUTION_TEXT)

    return {
        "candidates_seen": len(data),
        "candidates_matching_filter": len(candidates),
        "written": written,
        "rejects": dict(rejects),
        "circulation_class_counts": dict(class_counts),
    }


if __name__ == "__main__":
    pkl_path = os.environ.get("RESPLAN_PKL", DEFAULT_RESPLAN_PKL)
    summary = build_corpus(pkl_path)
    for k, v in summary.items():
        print(f"{k}: {v}")
