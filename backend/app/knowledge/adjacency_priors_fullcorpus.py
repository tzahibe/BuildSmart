"""Full-corpus real-plan adjacency validation (Issue #149-B).

MEASUREMENT ONLY. This module changes no ranking, generator, validator or hard constraint — it
re-measures `app.knowledge.adjacency_priors`'s Step 1 prior on the full 17,107-plan ResPlan corpus
instead of the 19-plan fixture that module's own docstring discloses as an in-sample calibration,
and keeps SPATIAL ADJACENCY and ACCESS strictly separate, per two independently reported artifacts.

DATA SOURCE: the pickle at `DEFAULT_CORPUS_PKL` — verified reachable on this machine by the Team
Lead on 2026-09-28, 17,107 plans, ~2.6s load, ~1.25GB peak RSS (ResPlan, CC BY 4.0). It is NOT part
of this repository (an external dataset path on the worker's own machine) and is not required by
CI: the artifact this module produces is committed once, and `--corpus-pkl` lets a future run point
elsewhere. `EmptyCorpusError` (AC-7) is proven by `tests/knowledge/test_adjacency_priors_fullcorpus.
py` against tiny synthetic pickles, never against the real corpus.

SCHEMA: each plan is a dict with a precomputed `networkx.Graph` at `plan["graph"]`. Every node
carries `type` — one of `living`, `kitchen`, `bedroom`, `bathroom`, `balcony` (a ROLE, mapped to the
engine's own role names below) or `front_door` (an access anchor, not a role). Every edge carries a
`type`: `adjacency` (two rooms share a boundary), `via_door` (a door bridges two rooms), `direct`
(the front door opens directly into a room) or `via_window` (a window bridges two rooms/balconies).

ADJACENCY IS NOT ACCESS (AC-4) — read literally from the corpus's own edge-type vocabulary, no
inference either direction: the SPATIAL ADJACENCY graph is built ONLY from `adjacency`-typed edges;
the ACCESS graph is built ONLY from `via_door`/`direct`-typed edges. `via_window` edges are neither
(a rare, distinct relation — 3.0% of all corpus edges per ResPlan's own published statistics) and
are reported as present but deliberately left OUT of both artifacts rather than folded into either
one. The access graph is what the corpus itself records — an undirected "a door bridges these two
rooms" / "the front door opens directly into this room" fact, never a directional entry sequence
ResPlan does not encode; this module never promotes "touches" into "is entered from".

ROLE VOCABULARY, honestly bounded by the data: ResPlan's own node taxonomy for indoor rooms is
LIVING/KITCHEN/BEDROOM/BATHROOM/BALCONY ONLY (verified by a full scan of all 17,107 plans' own graph
nodes — no other type ever appears as a graph node). MASTER, ENSUITE, DINING, CIRCULATION and
TOILET/WC are NOT distinct roles in this corpus and this module does NOT infer them (e.g. "largest
bedroom = master") — inventing a role the data does not label would be exactly the kind of
unmeasured-passed-off-as-measured this Issue exists to prevent. Every headline pair the Issue names
that needs one of these roles is reported as UNMEASURABLE, explicitly, rather than fabricated.

TRAIN/HOLDOUT (AC-2): deterministic 80/20 split by `sha256(str(plan_id)).hexdigest()` taken mod 100
against a fixed cut (`< HOLDOUT_SPLIT_PERCENT` -> HOLDOUT, else TRAIN) — independent of list/pickle
order, reproducible from the plan's own id alone. The prior (`spatial_adjacency` rows AND `access`
rows) is built from TRAIN only. The "near real" calibration (median/stdev/threshold) is measured by
scoring every HOLDOUT plan's own spatial-adjacency pattern against the TRAIN-built prior — never
in-sample.

SMOOTHING / MIN SUPPORT: identical method and parameters to `app.knowledge.adjacency_priors`
(Laplace add-`SMOOTHING_ALPHA`, `MIN_SUPPORT` plans) for direct comparability — imported from that
module rather than restated, so a future change to one is never silently forked from the other.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import statistics
import sys
from dataclasses import dataclass

from app.knowledge.adjacency_priors import (
    MIN_SUPPORT,
    SMOOTHING_ALPHA,
    SMOOTHING_METHOD,
    eligible_pairs_for_roles,
    plan_log_likelihood,
)

#: See module docstring, "DATA SOURCE".
DEFAULT_CORPUS_PKL = "/Users/mymacbook/projects/datasets/resplan/ResPlan.pkl"

DEFAULT_JSON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "docs", "reports", "real-plan-priors", "adjacency-fullcorpus.json")
DEFAULT_REPORT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "docs", "reports", "real-plan-priors", "adjacency-fullcorpus.md")

#: See module docstring, "ROLE VOCABULARY" — the only node types ResPlan's own graph ever carries
#: for an indoor room, verified by a full scan of all 17,107 plans.
_ROLE_BY_NODE_TYPE = {"living": "LIVING", "kitchen": "KITCHEN", "bedroom": "BEDROOM",
                      "bathroom": "BATHROOM", "balcony": "BALCONY"}
_FRONT_DOOR_TYPE = "front_door"

#: Headline pairs the Issue names explicitly (AC-3). A pair whose role(s) do not exist in
#: `_ROLE_BY_NODE_TYPE`'s vocabulary is UNMEASURABLE from this corpus — reported as such, never
#: inferred. `None` marks the unmeasurable side of a pair name (e.g. "ENSUITE" has no corpus role).
HEADLINE_PAIRS = (
    ("BEDROOM", "LIVING"),
    ("BEDROOM", "CIRCULATION"),      # CIRCULATION: not a corpus role -> UNMEASURABLE
    ("MASTER", "ENSUITE"),           # MASTER, ENSUITE: not corpus roles -> UNMEASURABLE
    ("MASTER", "BATHROOM"),          # MASTER: not a corpus role -> UNMEASURABLE (proxy: BEDROOM<->BATHROOM below)
    ("KITCHEN", "LIVING"),
    ("KITCHEN", "DINING"),           # DINING: not a corpus role -> UNMEASURABLE
    ("BATHROOM", "BEDROOM"),         # wet-room relationship
    ("BATHROOM", "KITCHEN"),         # wet-room relationship
    ("BATHROOM", "LIVING"),          # wet-room relationship
    ("BATHROOM", "BALCONY"),         # wet-room relationship
)

#: Split cut point: a plan is HOLDOUT when its hash falls in [0, this), else TRAIN. 20 -> 80/20.
HOLDOUT_SPLIT_PERCENT = 20


class FullCorpusAdjacencyError(RuntimeError):
    """Base class for this module's own loud-failure exceptions — never caught and hidden."""


class EmptyFullCorpusError(FullCorpusAdjacencyError):
    """Raised when the scan produced zero usable plans, or zero role pairs to measure (AC-7)."""


@dataclass(frozen=True)
class FullCorpusPlan:
    plan_id: str
    role_zone_ids: dict            # role -> tuple of node ids
    spatial_adjacency_pairs: frozenset   # frozenset of frozenset({node_a, node_b}), type=='adjacency'
    access_pairs: frozenset              # frozenset of frozenset({node_a, node_b}), type in via_door/direct
    front_door_node: str | None
    split: str                     # "TRAIN" or "HOLDOUT"


@dataclass(frozen=True)
class PairRow:
    role_a: str
    role_b: str
    sample_count: int
    positive_count: int            # adjacent_count (spatial) or access_count (access)
    raw_p: float
    p_smoothed: float
    lift: float
    meets_min_support: bool


def _split_for(plan_id: str) -> str:
    """See module docstring, "TRAIN/HOLDOUT" — deterministic, order-independent."""
    digest = hashlib.sha256(str(plan_id).encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 100
    return "HOLDOUT" if bucket < HOLDOUT_SPLIT_PERCENT else "TRAIN"


def load_full_corpus_plans(pkl_path: str = DEFAULT_CORPUS_PKL) -> tuple:
    """Returns `(plans: list[FullCorpusPlan], total_loaded: int, skipped: dict[str, int])`.

    Raises `EmptyFullCorpusError` (AC-7) when the pickle does not exist, is empty, or every plan is
    skipped — never a silent empty artifact."""
    if not os.path.exists(pkl_path):
        raise EmptyFullCorpusError(f"corpus pickle does not exist: {pkl_path}")
    with open(pkl_path, "rb") as f:
        raw = pickle.load(f)
    if not raw:
        raise EmptyFullCorpusError(f"corpus pickle at {pkl_path} contains zero plans")

    plans: list[FullCorpusPlan] = []
    skipped: dict = {}
    for entry in raw:
        try:
            plan_id = entry["id"]
            graph = entry["graph"]
        except (KeyError, TypeError):
            skipped["malformed_entry"] = skipped.get("malformed_entry", 0) + 1
            continue

        role_zone_ids: dict = {}
        front_door_node = None
        for node_id, node_data in graph.nodes(data=True):
            node_type = node_data.get("type")
            role = _ROLE_BY_NODE_TYPE.get(node_type)
            if role is not None:
                role_zone_ids.setdefault(role, []).append(node_id)
            elif node_type == _FRONT_DOOR_TYPE:
                front_door_node = node_id

        if not role_zone_ids:
            skipped["no_role_rooms"] = skipped.get("no_role_rooms", 0) + 1
            continue

        spatial_pairs = set()
        access_pairs = set()
        for u, v, edge_data in graph.edges(data=True):
            edge_type = edge_data.get("type")
            if edge_type == "adjacency":
                spatial_pairs.add(frozenset((u, v)))
            elif edge_type in ("via_door", "direct"):
                access_pairs.add(frozenset((u, v)))

        plans.append(FullCorpusPlan(
            plan_id=str(plan_id),
            role_zone_ids={role: tuple(ids) for role, ids in role_zone_ids.items()},
            spatial_adjacency_pairs=frozenset(spatial_pairs),
            access_pairs=frozenset(access_pairs),
            front_door_node=front_door_node,
            split=_split_for(plan_id)))

    total_loaded = len(raw)
    if not plans:
        raise EmptyFullCorpusError(
            f"loaded {total_loaded} plan(s) from {pkl_path} but every one was skipped: {skipped}")
    return plans, total_loaded, skipped


def _pair_positive(plan: FullCorpusPlan, role_a: str, role_b: str, pairs: frozenset) -> bool:
    ids_a = plan.role_zone_ids.get(role_a, ())
    ids_b = plan.role_zone_ids.get(role_b, ())
    return any(frozenset((a, b)) in pairs for a in ids_a for b in ids_b)


def compute_pair_rows(plans: list, pairs_attr: str) -> tuple:
    """One `PairRow` per unordered pair of distinct roles co-occurring in >=1 plan, for either
    `pairs_attr="spatial_adjacency_pairs"` or `pairs_attr="access_pairs"`. Returns `(rows, baseline)`."""
    pair_stats: dict = {}
    total_present = 0
    total_positive = 0
    for plan in plans:
        pairs = getattr(plan, pairs_attr)
        roles = sorted(plan.role_zone_ids)
        for i in range(len(roles)):
            for j in range(i + 1, len(roles)):
                role_a, role_b = roles[i], roles[j]
                key = (role_a, role_b)
                both, positive = pair_stats.get(key, (0, 0))
                is_positive = _pair_positive(plan, role_a, role_b, pairs)
                pair_stats[key] = (both + 1, positive + (1 if is_positive else 0))
                total_present += 1
                total_positive += 1 if is_positive else 0

    baseline = round(total_positive / total_present, 6) if total_present else 0.0
    rows = []
    for (role_a, role_b), (both, positive) in sorted(pair_stats.items()):
        raw_p = positive / both
        p_smoothed = (positive + SMOOTHING_ALPHA) / (both + 2 * SMOOTHING_ALPHA)
        lift = round(p_smoothed / baseline, 6) if baseline > 0 else 0.0
        rows.append(PairRow(role_a=role_a, role_b=role_b, sample_count=both, positive_count=positive,
                            raw_p=round(raw_p, 6), p_smoothed=round(p_smoothed, 6), lift=lift,
                            meets_min_support=both >= MIN_SUPPORT))
    return tuple(rows), baseline


def _front_door_direct_rates(plans: list) -> dict:
    """P(role has a `direct` edge to the front door | role present) — measured from `access_pairs`
    restricted to edges touching the plan's own `front_door_node`. Supplementary access reporting,
    not one of the headline pairs, but a real, separately-reported access fact (AC-4)."""
    present = {}
    direct = {}
    for plan in plans:
        if plan.front_door_node is None:
            continue
        for role, ids in plan.role_zone_ids.items():
            present[role] = present.get(role, 0) + 1
            has_direct = any(frozenset((rid, plan.front_door_node)) in plan.access_pairs for rid in ids)
            if has_direct:
                direct[role] = direct.get(role, 0) + 1
    return {role: {"sample_count": present[role], "direct_count": direct.get(role, 0),
                   "rate": round(direct.get(role, 0) / present[role], 6)}
            for role in sorted(present)}


def row_for(rows: tuple, role_a: str, role_b: str) -> "PairRow | None":
    a, b = sorted((role_a, role_b))
    for row in rows:
        if row.role_a == a and row.role_b == b:
            return row
    return None


class _TrainTable:
    """Duck-typed adapter so `app.knowledge.adjacency_priors.plan_log_likelihood` (generic over any
    object exposing `row_for`) can score against the full-corpus TRAIN spatial-adjacency rows
    without that module needing to know this one exists."""

    def __init__(self, rows: tuple):
        self._rows = rows

    def row_for(self, role_a: str, role_b: str):
        row = row_for(self._rows, role_a, role_b)
        if row is None:
            return None
        return _RowAdapter(row)


@dataclass(frozen=True)
class _RowAdapter:
    row: PairRow

    @property
    def p_adjacent(self):
        return self.row.p_smoothed

    @property
    def meets_min_support(self):
        return self.row.meets_min_support


def score_plan(plan: FullCorpusPlan, train_rows: tuple) -> float | None:
    """A plan's own spatial-adjacency pattern scored against the TRAIN-built rows, via the SAME
    `plan_log_likelihood` Step 2 uses — never a re-derived scoring function."""
    table = _TrainTable(train_rows)
    roles = sorted(plan.role_zone_ids)
    outcomes = [(a, b, _pair_positive(plan, a, b, plan.spatial_adjacency_pairs))
               for a, b in eligible_pairs_for_roles(roles)]
    return plan_log_likelihood(outcomes, table)


@dataclass(frozen=True)
class FullCorpusReport:
    corpus_pkl: str
    total_loaded: int
    skipped: dict
    plans_used: int
    train_count: int
    holdout_count: int
    spatial_rows: tuple
    spatial_baseline: float
    access_rows: tuple
    access_baseline: float
    front_door_direct_rates: dict
    holdout_median: float
    holdout_stdev: float
    holdout_threshold: float
    holdout_scored_count: int
    holdout_scores: tuple      # every scorable HOLDOUT plan's own score — for z-distance/percentile (AC-6)


def build_report(pkl_path: str = DEFAULT_CORPUS_PKL) -> FullCorpusReport:
    plans, total_loaded, skipped = load_full_corpus_plans(pkl_path)
    train = [p for p in plans if p.split == "TRAIN"]
    holdout = [p for p in plans if p.split == "HOLDOUT"]
    if not train:
        raise EmptyFullCorpusError("TRAIN split is empty — cannot build a prior")
    if not holdout:
        raise EmptyFullCorpusError("HOLDOUT split is empty — cannot calibrate")

    spatial_rows, spatial_baseline = compute_pair_rows(train, "spatial_adjacency_pairs")
    access_rows, access_baseline = compute_pair_rows(train, "access_pairs")
    if not spatial_rows:
        raise EmptyFullCorpusError("TRAIN split produced zero role pairs to measure")
    fd_rates = _front_door_direct_rates(train)

    holdout_scores = [s for s in (score_plan(p, spatial_rows) for p in holdout) if s is not None]
    if not holdout_scores:
        raise EmptyFullCorpusError("zero HOLDOUT plans produced a scorable adjacency pattern")
    median = statistics.median(holdout_scores)
    stdev = statistics.pstdev(holdout_scores) if len(holdout_scores) > 1 else abs(median) * 0.5

    return FullCorpusReport(
        corpus_pkl=pkl_path, total_loaded=total_loaded, skipped=skipped, plans_used=len(plans),
        train_count=len(train), holdout_count=len(holdout),
        spatial_rows=spatial_rows, spatial_baseline=spatial_baseline,
        access_rows=access_rows, access_baseline=access_baseline,
        front_door_direct_rates=fd_rates,
        holdout_median=round(median, 6), holdout_stdev=round(stdev, 6),
        holdout_threshold=round(median - stdev, 6), holdout_scored_count=len(holdout_scores),
        holdout_scores=tuple(round(s, 6) for s in holdout_scores))


def report_to_dict(report: FullCorpusReport) -> dict:
    def _rows(rows):
        return [{"role_a": r.role_a, "role_b": r.role_b, "sample_count": r.sample_count,
                 "positive_count": r.positive_count, "raw_p": r.raw_p, "p_smoothed": r.p_smoothed,
                 "lift": r.lift, "meets_min_support": r.meets_min_support} for r in rows]

    return {
        "corpus_pkl": report.corpus_pkl, "total_loaded": report.total_loaded,
        "skipped": report.skipped, "plans_used": report.plans_used,
        "train_count": report.train_count, "holdout_count": report.holdout_count,
        "split_method": "sha256(plan_id)[:8] as int mod 100 < 20 -> HOLDOUT, else TRAIN",
        "smoothing_method": SMOOTHING_METHOD, "smoothing_alpha": SMOOTHING_ALPHA,
        "min_support": MIN_SUPPORT,
        "spatial_adjacency": {"baseline_rate": report.spatial_baseline, "rows": _rows(report.spatial_rows)},
        "access": {"baseline_rate": report.access_baseline, "rows": _rows(report.access_rows)},
        "front_door_direct_access": report.front_door_direct_rates,
        "holdout_calibration": {
            "scored_count": report.holdout_scored_count, "holdout_count": report.holdout_count,
            "median": report.holdout_median, "stdev": report.holdout_stdev,
            "threshold": report.holdout_threshold, "scores": list(report.holdout_scores),
        },
    }


def _headline_row_text(rows: tuple, role_a: str, role_b: str, kind: str) -> str:
    if role_a not in _ROLE_BY_NODE_TYPE.values() or role_b not in _ROLE_BY_NODE_TYPE.values():
        return (f"| {role_a} | {role_b} | — | — | — | — | — | **UNMEASURABLE** — "
                f"{'/'.join(r for r in (role_a, role_b) if r not in _ROLE_BY_NODE_TYPE.values())} "
                "is not a distinct role in ResPlan's own node vocabulary |")
    row = row_for(rows, role_a, role_b)
    if row is None:
        return f"| {role_a} | {role_b} | 0 | 0 | — | — | — | never co-occurred in TRAIN |"
    return (f"| {row.role_a} | {row.role_b} | {row.sample_count} | {row.positive_count} | "
           f"{row.raw_p} | {row.p_smoothed} | {row.lift} | "
           f"{'meets min support' if row.meets_min_support else '⚠ below min support'} |")


def render_markdown_report(report: FullCorpusReport) -> str:
    lines = [
        "# Real-plan adjacency priors — full-corpus validation (Issue #149-B)",
        "",
        "**Measurement only.** Re-measures Issue #141's Step-1 adjacency prior on the full ResPlan "
        "corpus with an honest train/holdout split, and keeps SPATIAL ADJACENCY and ACCESS strictly "
        "separate. No ranking, generator, validator or hard constraint is changed by this report.",
        "",
        "## Corpus scan (AC-1)",
        "",
        f"Source: `{report.corpus_pkl}`. **{report.total_loaded} plans scanned** from the pickle "
        f"(exact count, never a sample — see module docstring); skipped: {report.skipped or '{}'}; "
        f"**{report.plans_used} plans used**.",
        "",
        "## Train/holdout split (AC-2)",
        "",
        "Deterministic 80/20 split by `sha256(plan_id)` mod 100 (`< 20` -> HOLDOUT, else TRAIN) — "
        "independent of pickle/list order, reproducible from each plan's own id alone.",
        "",
        f"- TRAIN: **{report.train_count}** plans — the prior below is built from TRAIN ONLY.",
        f"- HOLDOUT: **{report.holdout_count}** plans — the calibration below is measured on "
        "HOLDOUT ONLY, scored against the TRAIN-built prior. No in-sample calibration anywhere in "
        "this report.",
        "",
        "## Role vocabulary, honestly bounded by the data",
        "",
        "ResPlan's own graph node types for indoor rooms are **LIVING, KITCHEN, BEDROOM, BATHROOM, "
        "BALCONY only** (verified by a full scan of all "
        f"{report.total_loaded} plans' own graph nodes — no other type ever appears as a graph "
        "node). `MASTER`, `ENSUITE`, `DINING`, `CIRCULATION` and `TOILET`/`WC` are **not distinct "
        "roles in this corpus** and are never inferred (e.g. \"largest bedroom = master\") — every "
        "headline pair below needing one of these roles is marked **UNMEASURABLE**, not fabricated.",
        "",
        "## A. Spatial adjacency — TRAIN-built prior (AC-3)",
        "",
        f"Built ONLY from `adjacency`-typed edges (rooms that share a boundary). Smoothing: "
        f"`{SMOOTHING_METHOD}` (add-`{SMOOTHING_ALPHA}`). Minimum support: `{MIN_SUPPORT}` plans. "
        f"Baseline adjacency rate (pooled across every TRAIN (plan, role-pair) observation): "
        f"`{report.spatial_baseline}`. `lift = p_smoothed / baseline_rate`.",
        "",
        "### Headline pairs (AC-3)",
        "",
        "| role_a | role_b | sample_count | adjacent_count | raw_p | p_smoothed | lift | note |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for role_a, role_b in HEADLINE_PAIRS:
        lines.append(_headline_row_text(report.spatial_rows, role_a, role_b, "spatial"))
    lines += [
        "",
        "### Every measured spatial-adjacency row",
        "",
        "| role_a | role_b | sample_count | adjacent_count | raw_p | p_smoothed | lift | support |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(report.spatial_rows, key=lambda r: -r.lift):
        lines.append(f"| {r.role_a} | {r.role_b} | {r.sample_count} | {r.positive_count} | "
                    f"{r.raw_p} | {r.p_smoothed} | {r.lift} | "
                    f"{'yes' if r.meets_min_support else '⚠ below floor'} |")

    lines += [
        "",
        "**Key finding (AC-4)**: BATHROOM's spatial-adjacency rate to BEDROOM/KITCHEN/LIVING is "
        "essentially zero in section A (`raw_p≈0.0`) while its ACCESS rate to the same roles in "
        "section B is high (`0.91`/`0.87` to BEDROOM/LIVING) — because ResPlan labels a "
        "boundary-sharing pair EITHER `adjacency` OR `via_door`, never both: a bathroom's shared "
        "wall almost always carries a door, so it is recorded as `via_door`, not `adjacency`. "
        "Reading section A alone would wrongly conclude bathrooms rarely sit next to a bedroom; "
        "conflating A and B would wrongly conclude \"touches\" and \"entered from\" are the same "
        "fact. Neither artifact infers the other's number — this is exactly why AC-4 requires them "
        "kept apart.",
        "",
        "## B. Access graph — TRAIN-built, from via_door/direct edges only (AC-4)",
        "",
        "**ADJACENCY IS NOT ACCESS.** This section is built ONLY from `via_door`/`direct`-typed "
        "edges — never inferred from section A. `via_door` = a door bridges two rooms; `direct` = "
        "the front door opens directly into a room. This is the corpus's own undirected \"bridged "
        "by a door\" fact, not a directional entry sequence — ResPlan does not encode entry order, "
        "so none is invented here. `via_window` edges "
        "(a rare, distinct relation) are excluded from BOTH artifacts, not folded into either.",
        "",
        f"Baseline access rate (pooled across every TRAIN (plan, role-pair) observation): "
        f"`{report.access_baseline}`.",
        "",
        "### Headline pairs — access, for direct comparison against A (AC-4)",
        "",
        "| role_a | role_b | sample_count | access_count | raw_p | p_smoothed | lift | note |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for role_a, role_b in HEADLINE_PAIRS:
        lines.append(_headline_row_text(report.access_rows, role_a, role_b, "access"))
    lines += [
        "",
        "### Every measured access row",
        "",
        "| role_a | role_b | sample_count | access_count | raw_p | p_smoothed | lift | support |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(report.access_rows, key=lambda r: -r.lift):
        lines.append(f"| {r.role_a} | {r.role_b} | {r.sample_count} | {r.positive_count} | "
                    f"{r.raw_p} | {r.p_smoothed} | {r.lift} | "
                    f"{'yes' if r.meets_min_support else '⚠ below floor'} |")

    lines += [
        "",
        "### Front-door direct access, by role (supplementary access fact)",
        "",
        "P(role has a `direct` edge to the front door | role present), TRAIN only.",
        "",
        "| role | sample_count | direct_count | rate |",
        "|---|---|---|---|",
    ]
    for role, stats in report.front_door_direct_rates.items():
        lines.append(f"| {role} | {stats['sample_count']} | {stats['direct_count']} | {stats['rate']} |")

    lines += [
        "",
        "## Holdout calibration (AC-2, AC-6)",
        "",
        f"Every HOLDOUT plan's own spatial-adjacency pattern scored against the TRAIN-built prior "
        f"(section A) via `plan_log_likelihood` — the identical Step-2 scoring function, never "
        "re-derived. Scorable: "
        f"**{report.holdout_scored_count}/{report.holdout_count}** HOLDOUT plans (the rest have "
        "zero eligible pair with a supported TRAIN row).",
        "",
        f"- `real_median_score` (HOLDOUT): **{report.holdout_median}**",
        f"- `real_stdev_score` (HOLDOUT, population stdev): **{report.holdout_stdev}**",
        f"- threshold (`median - stdev`): **{report.holdout_threshold}**",
        "",
        "This calibration replaces #141's in-sample one "
        "(`real_median_score=-0.3253`, `real_stdev_score=0.1455`, measured on the same 19 plans the "
        "prior itself was built from) — see `docs/reports/real-plan-priors/"
        "adjacency-fullcorpus-diagnostic.md` for the re-run diagnostic against this threshold.",
        "",
        "## Regenerate",
        "",
        "From `backend/`:",
        "",
        "    uv run python -m app.knowledge.adjacency_priors_fullcorpus "
        "--write-json ../docs/reports/real-plan-priors/adjacency-fullcorpus.json "
        "--write-report ../docs/reports/real-plan-priors/adjacency-fullcorpus.md",
        "",
        "The scanner **fails loudly** (raises `EmptyFullCorpusError`, CLI exits non-zero) on a "
        "missing/empty pickle or zero usable plans — proven by "
        "`tests/knowledge/test_adjacency_priors_fullcorpus.py`.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-pkl", default=DEFAULT_CORPUS_PKL)
    parser.add_argument("--write-json", default=None)
    parser.add_argument("--write-report", default=None)
    args = parser.parse_args(argv)
    try:
        report = build_report(args.corpus_pkl)
    except FullCorpusAdjacencyError as exc:
        print(f"adjacency_priors_fullcorpus: {exc}", file=sys.stderr)
        return 1
    print(f"loaded {report.total_loaded} plan(s), used {report.plans_used}, "
          f"train={report.train_count} holdout={report.holdout_count}, "
          f"holdout_median={report.holdout_median} holdout_stdev={report.holdout_stdev}")
    if args.write_json:
        with open(args.write_json, "w", encoding="utf-8") as f:
            json.dump(report_to_dict(report), f, indent=2)
        print(f"wrote {args.write_json}")
    if args.write_report:
        with open(args.write_report, "w", encoding="utf-8") as f:
            f.write(render_markdown_report(report))
        print(f"wrote {args.write_report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
