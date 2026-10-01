"""20 deterministic, stratified briefs, committed by id (Issue #151, AC-3).

Selected from the FROZEN, committed 432-context regression corpus
(`backend/tests/regression_corpus/corpus.json`) — never a fresh sweep, never a random sample. Only
`expected_outcome == "PLANNED"` cases are eligible (404 of 432): a brief needs the current
generator to have actually produced a plan, since "the current generator's best topology" (Issue
requirement 5) is extracted from that solved plan (`generator_adapter.py`), not re-derived.

SELECTION METHOD: 20 explicit target strata (`_TARGET_STRATA` below) each name a desired
(bedrooms, wet_rooms, safe_room, open_plan, footprint aspect tier, house-size tier). For each
target, the single best-matching corpus case is picked by: (1) exact match on bedrooms/wet_rooms/
safe_room/open_plan where the target specifies one, (2) among ties, the case whose footprint aspect
ratio and built area are closest to the target tier's center, (3) among remaining ties, the
alphabetically-first `source_key` — fully deterministic, reproducible from the frozen corpus alone.
Every named spread (bedrooms 1-6, with/without safe room, 1-3 wet rooms, square/wide/narrow
footprints, open-plan on/off, small/medium/large) is covered by at least one of the 20.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DEFAULT_CORPUS_JSON = os.path.join(_BACKEND_DIR, "tests", "regression_corpus", "corpus.json")

SIZE_TIER_CENTERS_M2 = {"small": 90.0, "medium": 200.0, "large": 350.0}
ASPECT_TIER_CENTERS = {"narrow": 0.65, "square": 1.0, "wide": 1.6}


@dataclass(frozen=True)
class Brief:
    brief_id: str  # "B01".."B20" — the committed id
    source_key: str  # the corpus's own id for this context — traceable back to corpus.json
    project_id: str
    bedrooms: int
    wet_rooms: int
    safe_room: bool
    open_plan: bool
    built_area_m2: float
    footprint_width_m: float
    footprint_depth_m: float
    size_tier: str
    aspect_tier: str
    context: dict  # the exact context dict — reused verbatim by generator_adapter.py


#: (bedrooms, wet_rooms, safe_room, open_plan, aspect_tier, size_tier) — `None` means "no
#: preference for this field, pick on the remaining criteria". 20 rows, deliberately covering every
#: named value at least once across the set (see module docstring).
_TARGET_STRATA = (
    (1, 1, False, False, "square", "small"),
    (1, 1, False, True, "narrow", "small"),
    (2, 1, False, False, "wide", "small"),
    (2, 2, True, False, "square", "medium"),
    (2, 1, False, True, "square", "medium"),
    (3, 2, False, False, "narrow", "medium"),
    (3, 2, True, False, "wide", "medium"),
    (3, 1, False, True, "square", "small"),
    (3, 3, False, False, "square", "large"),
    (4, 2, False, False, "wide", "medium"),
    (4, 2, True, True, "narrow", "large"),
    (4, 3, False, False, "square", "large"),
    (4, 2, False, True, "wide", "large"),
    (5, 3, False, False, "narrow", "large"),
    (5, 2, True, False, "square", "large"),
    (5, 3, True, True, "wide", "large"),
    (6, 3, False, False, "square", "large"),
    (6, 3, True, False, "narrow", "large"),
    (6, 2, False, True, "wide", "large"),
    (6, 3, True, True, "square", "large"),
)


def _aspect_tier(width_m: float, depth_m: float) -> str:
    aspect = width_m / depth_m
    if aspect < 0.85:
        return "narrow"
    if aspect > 1.15:
        return "wide"
    return "square"


def _size_tier(built_area_m2: float) -> str:
    if built_area_m2 < 140.0:
        return "small"
    if built_area_m2 <= 260.0:
        return "medium"
    return "large"


def _load_planned_cases(corpus_json_path: str) -> list:
    with open(corpus_json_path, encoding="utf-8") as f:
        corpus = json.load(f)
    return [c for c in corpus["cases"] if c["expected_outcome"] == "PLANNED"]


def _match_score(case: dict, target: tuple) -> tuple:
    bedrooms, wet_rooms, safe_room, open_plan, aspect_tier, size_tier = target
    ctx = case["context"]
    exact_mismatches = (
        (ctx["bedrooms"] != bedrooms)
        + (ctx["wet_rooms"] != wet_rooms)
        + (ctx["safe_room"] != safe_room)
        + (ctx["open_plan"] != open_plan)
    )
    aspect = ctx["footprint_width_m"] / ctx["footprint_depth_m"]
    aspect_distance = abs(aspect - ASPECT_TIER_CENTERS[aspect_tier])
    size_distance = abs(ctx["built_area_m2"] - SIZE_TIER_CENTERS_M2[size_tier])
    # lower is better; tuple compares lexicographically. source_key last, for full determinism.
    return (exact_mismatches, aspect_distance, size_distance, case["source_key"])


def render_briefs_md(briefs: tuple) -> str:
    lines = [
        "# 20 stratified briefs (Issue #151, AC-3)",
        "",
        "Selected deterministically from the FROZEN, committed 432-context regression corpus "
        "(`backend/tests/regression_corpus/corpus.json`) — see `briefs.py`'s own module docstring "
        "for the selection method. Every brief below is PLANNED by the current generator (never a "
        "REFUSED context), since \"the current generator's best topology\" needs a solved plan to "
        "extract from.",
        "",
        "| brief | source_key (project_id) | bedrooms | wet_rooms | safe_room | open_plan | "
        "size_tier | aspect_tier | built_area_m2 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for b in briefs:
        lines.append(
            f"| {b.brief_id} | `{b.project_id}` | {b.bedrooms} | {b.wet_rooms} | {b.safe_room} | "
            f"{b.open_plan} | {b.size_tier} | {b.aspect_tier} | {b.built_area_m2} |")
    lines += [
        "",
        "## Coverage across the 20",
        "",
        f"- bedrooms: {sorted(set(b.bedrooms for b in briefs))}",
        f"- wet_rooms: {sorted(set(b.wet_rooms for b in briefs))}",
        f"- safe_room: {sorted(set(b.safe_room for b in briefs))}",
        f"- open_plan: {sorted(set(b.open_plan for b in briefs))}",
        f"- size_tier: {sorted(set(b.size_tier for b in briefs))}",
        f"- aspect_tier: {sorted(set(b.aspect_tier for b in briefs))}",
        "",
        "## Regenerate",
        "",
        "From `backend/`: `uv run python -m app.ai_harness.topology_poc.briefs` (deterministic — "
        "same corpus, same 20 briefs, every time).",
    ]
    return "\n".join(lines) + "\n"


def select_briefs(corpus_json_path: str = DEFAULT_CORPUS_JSON) -> tuple:
    """Deterministic — same corpus, same 20 briefs, every time. Raises `ValueError` if the corpus
    has zero PLANNED cases (never silently returns fewer than 20)."""
    cases = _load_planned_cases(corpus_json_path)
    if not cases:
        raise ValueError(f"{corpus_json_path} carries zero PLANNED cases — cannot select briefs")

    used_source_keys: set = set()
    briefs = []
    for i, target in enumerate(_TARGET_STRATA, start=1):
        candidates = [c for c in cases if c["source_key"] not in used_source_keys]
        best = min(candidates, key=lambda c: _match_score(c, target))
        used_source_keys.add(best["source_key"])
        ctx = best["context"]
        briefs.append(Brief(
            brief_id=f"B{i:02d}", source_key=best["source_key"], project_id=ctx["project_id"],
            bedrooms=ctx["bedrooms"], wet_rooms=ctx["wet_rooms"], safe_room=ctx["safe_room"],
            open_plan=ctx["open_plan"], built_area_m2=ctx["built_area_m2"],
            footprint_width_m=ctx["footprint_width_m"], footprint_depth_m=ctx["footprint_depth_m"],
            size_tier=_size_tier(ctx["built_area_m2"]),
            aspect_tier=_aspect_tier(ctx["footprint_width_m"], ctx["footprint_depth_m"]),
            context=ctx))
    return tuple(briefs)


_DEFAULT_BRIEFS_MD = os.path.join(
    os.path.dirname(_BACKEND_DIR), "docs", "reports", "llm-topology-poc", "briefs.md")


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-report", default=_DEFAULT_BRIEFS_MD)
    args = parser.parse_args(argv)
    chosen = select_briefs()
    os.makedirs(os.path.dirname(args.write_report), exist_ok=True)
    with open(args.write_report, "w", encoding="utf-8") as f:
        f.write(render_briefs_md(chosen))
    print(f"wrote {len(chosen)} briefs to {args.write_report}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
