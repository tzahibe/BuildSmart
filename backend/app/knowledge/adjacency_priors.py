"""Real-plan adjacency priors (Issue #141).

STEP 1 of a 6-step Issue: this module measures, per UNORDERED pair of distinct room roles, how
often real plans put them next to each other, and writes a committed artifact. Nothing here changes
engine behaviour — see `app.vertical_slice.adjacency_priors` for the soft ranking signal (Step 5)
that later reads the artifact this module produces, behind `ADJACENCY_PRIORS_ENABLED`. This module
also carries `plan_log_likelihood`, the pure Step 2 scoring function, since it is table-shaped math
with no engine dependency and is exercised directly by `tests/knowledge/test_adjacency_priors.py`.

DATA SOURCE, honestly stated — identical constraint to Issue #140's
`app.knowledge.room_proportion_priors`: the full 17,107-plan ResPlan corpus lives only on the
unmerged branch `integration/poc-architectural-brain`, not reachable from this worktree. This module
reads the same 20-plan fixture at `tests/spikes/fixtures/geometry_shapes/plans/` (19 real ResPlan
plans, CC BY 4.0, + 1 synthetic control this scan excludes) by default, and accepts `--corpus-dir`
to point at a larger corpus once one is reachable.

ADJACENCY GROUND TRUTH: each fixture plan already carries ResPlan's own precomputed
`adjacency_edges` (room-id pairs whose boundaries touch) — this scanner reads that field directly
rather than re-deriving touching from room polygons, since ResPlan's own geometric adjacency
detection is the corpus's own definition of "next to each other" and re-deriving it would just add a
second, uncontrolled threshold on top of a real one.

ROLE REDUCTION: identical to `room_proportion_priors`'s `_SINGLE_INSTANCE_ROLES` and for the same
reason — the engine's programme models LIVING/KITCHEN/DINING/CIRCULATION/FAMILY_ROOM as ONE room per
house, but ResPlan's own room labelling may carry a second, small same-typed fragment (an entrance
nook, a sliver beside a stair). Left unreduced, these slivers touch nearly everything and would
inflate "LIVING is adjacent to X" far past what the real living room's own adjacency says. For these
roles only, this scanner keeps the SINGLE LARGEST-area instance per plan before computing role-pair
adjacency. BEDROOM/BATHROOM/TOILET/STORAGE keep every instance — a plan's SECOND bedroom being
adjacent to a bathroom is a real, distinct fact, not a labelling artefact.

SMOOTHING: `p_adjacent` uses Laplace (add-`SMOOTHING_ALPHA`) smoothing over the raw
`adjacent_count / sample_count` rate, so a pair observed 100% or 0% adjacent on a thin sample never
produces `log(0)`/`log(1)` when Step 2's score consumes it. `SMOOTHING_ALPHA = 1.0` (add-one/Laplace)
is the standard choice for a binary rate this thinly sampled.

MINIMUM SUPPORT: `MIN_SUPPORT = 3` (identical floor to `room_proportion_priors.LOW_CONFIDENCE_
SAMPLE_COUNT`, chosen for the same reason on the same 19-plan corpus — below this a rate is mostly
noise). A pair below it is still REPORTED in the artifact (flagged, never hidden — the honest state
of a thin corpus is not the scanner's own defect) but `meets_min_support=False`, and Step 2's own
scoring function (`plan_log_likelihood`) skips it entirely: it contributes to neither the numerator
nor the eligible-pair count (AC-3).

FAILS LOUDLY (this Issue's own Step 1 requirement, identical to #140's): `load_plan_role_adjacencies`
raises `EmptyCorpusError` when the corpus directory has zero plan files, when every file is excluded
(synthetic), or when the real plans yield zero usable role data. `build_priors_table` raises the same
when the scan produced plans but zero role PAIRS (fewer than two distinct roles appear together in
any single plan). The CLI (`main`) catches every `AdjacencyPriorsError` and exits non-zero.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass
from typing import Sequence

DEFAULT_CORPUS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tests", "spikes", "fixtures", "geometry_shapes", "plans",
)

#: `app/knowledge/data/` is gitignored (runtime index state) — the committed artifact lives beside
#: its own Markdown report under `docs/reports/` instead, so a fresh checkout (CI included) has it.
DEFAULT_JSON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "docs", "reports", "real-plan-priors", "adjacency.json")

_SYNTHETIC_SOURCE_DATASETS = frozenset({"SYNTHETIC"})

#: See module docstring, "ROLE REDUCTION" — identical set and rationale to
#: `room_proportion_priors._SINGLE_INSTANCE_ROLES`.
_SINGLE_INSTANCE_ROLES = frozenset({"LIVING", "KITCHEN", "DINING", "CIRCULATION", "FAMILY_ROOM"})

SMOOTHING_METHOD = "laplace"
SMOOTHING_ALPHA = 1.0

#: See module docstring, "MINIMUM SUPPORT".
MIN_SUPPORT = 3


class AdjacencyPriorsError(RuntimeError):
    """Base class for this module's own loud-failure exceptions — never caught and hidden."""


class EmptyCorpusError(AdjacencyPriorsError):
    """Raised when the scanner scanned zero usable plans, or found zero role pairs to measure."""


@dataclass(frozen=True)
class PlanRoleAdjacency:
    """One plan's role -> room-id membership (after single-instance reduction) and its own set of
    touching room-id pairs, exactly as ResPlan's `adjacency_edges` recorded them."""

    plan_id: str
    role_zone_ids: dict
    adjacency_pairs: frozenset


@dataclass(frozen=True)
class AdjacencyRow:
    role_a: str
    role_b: str
    sample_count: int          # plans where both roles are present
    adjacent_count: int        # of those, plans where >=1 instance pair actually touches
    raw_p_adjacent: float      # adjacent_count / sample_count, unsmoothed
    p_adjacent: float          # Laplace-smoothed — what Step 2 scoring reads
    lift: float                # p_adjacent / baseline_adjacency_rate
    meets_min_support: bool


@dataclass(frozen=True)
class AdjacencyPriorsTable:
    rows: tuple
    baseline_adjacency_rate: float
    smoothing_method: str
    smoothing_alpha: float
    min_support: int
    corpus_dir: str
    plans_scanned: int
    plans_excluded_synthetic: int

    def row_for(self, role_a: str, role_b: str) -> "AdjacencyRow | None":
        a, b = sorted((role_a, role_b))
        for row in self.rows:
            if row.role_a == a and row.role_b == b:
                return row
        return None


def _load_plan_file(path: str) -> dict | None:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    plan_reference = data.get("plan_reference", data)
    provenance = plan_reference.get("provenance", {})
    if provenance.get("source_dataset") in _SYNTHETIC_SOURCE_DATASETS:
        return None
    return plan_reference


def _reduce_single_instance_roles(rooms_by_role: dict) -> dict:
    reduced: dict = {}
    for role, entries in rooms_by_role.items():
        if role in _SINGLE_INSTANCE_ROLES and len(entries) > 1:
            best_id = max(entries, key=lambda e: e[1])[0]
            reduced[role] = (best_id,)
        else:
            reduced[role] = tuple(room_id for room_id, _area in entries)
    return reduced


def load_plan_role_adjacencies(corpus_dir: str = DEFAULT_CORPUS_DIR) -> tuple:
    """Every usable `PlanRoleAdjacency` in `corpus_dir`, plus (plans scanned, plans excluded
    synthetic). Raises `EmptyCorpusError` rather than returning an empty list — see module
    docstring, "FAILS LOUDLY"."""
    if not os.path.isdir(corpus_dir):
        raise EmptyCorpusError(f"corpus directory does not exist: {corpus_dir}")
    files = sorted(f for f in os.listdir(corpus_dir) if f.endswith(".json"))
    if not files:
        raise EmptyCorpusError(f"no plan files (*.json) found under {corpus_dir}")

    plans: list[PlanRoleAdjacency] = []
    scanned = 0
    excluded_synthetic = 0
    for filename in files:
        plan_reference = _load_plan_file(os.path.join(corpus_dir, filename))
        if plan_reference is None:
            excluded_synthetic += 1
            continue
        scanned += 1
        plan_id = plan_reference.get("plan_id", filename)
        rooms_by_role: dict = {}
        for room in plan_reference.get("rooms", ()):
            role = room.get("type")
            room_id = room.get("id")
            area_m2 = room.get("area_m2", 0.0)
            if not role or not room_id:
                continue
            rooms_by_role.setdefault(role, []).append((room_id, area_m2))
        if not rooms_by_role:
            continue
        role_zone_ids = _reduce_single_instance_roles(rooms_by_role)
        adjacency_pairs = frozenset(
            frozenset((edge["room_a"], edge["room_b"]))
            for edge in plan_reference.get("adjacency_edges", ())
            if edge.get("room_a") and edge.get("room_b"))
        plans.append(PlanRoleAdjacency(plan_id=plan_id, role_zone_ids=role_zone_ids,
                                       adjacency_pairs=adjacency_pairs))

    if scanned == 0:
        raise EmptyCorpusError(
            f"every file under {corpus_dir} was excluded (synthetic) — zero real plans scanned")
    if not plans:
        raise EmptyCorpusError(
            f"scanned {scanned} plan(s) under {corpus_dir} but extracted zero usable rooms "
            "(missing type/id on every room)")
    return plans, scanned, excluded_synthetic


def _pair_touches(plan: PlanRoleAdjacency, role_a: str, role_b: str) -> bool:
    ids_a = plan.role_zone_ids.get(role_a, ())
    ids_b = plan.role_zone_ids.get(role_b, ())
    return any(frozenset((a, b)) in plan.adjacency_pairs for a in ids_a for b in ids_b)


def compute_rows(plans: list) -> tuple:
    """One row per unordered pair of DISTINCT roles that co-occurred in at least one scanned plan.
    Never a fabricated row for a pair the data never produced."""
    pair_stats: dict = {}
    total_present = 0
    total_adjacent = 0
    for plan in plans:
        roles = sorted(plan.role_zone_ids)
        for i in range(len(roles)):
            for j in range(i + 1, len(roles)):
                role_a, role_b = roles[i], roles[j]
                key = (role_a, role_b)
                both, adjacent = pair_stats.get(key, (0, 0))
                touches = _pair_touches(plan, role_a, role_b)
                pair_stats[key] = (both + 1, adjacent + (1 if touches else 0))
                total_present += 1
                total_adjacent += 1 if touches else 0

    #: Pooled across every (plan, role-pair) observation actually present in the corpus — the
    #: reference rate "lift" measures each specific pair against.
    baseline = round(total_adjacent / total_present, 6) if total_present else 0.0

    rows = []
    for (role_a, role_b), (both, adjacent) in sorted(pair_stats.items()):
        raw_p = adjacent / both
        p_smoothed = (adjacent + SMOOTHING_ALPHA) / (both + 2 * SMOOTHING_ALPHA)
        lift = round(p_smoothed / baseline, 6) if baseline > 0 else 0.0
        rows.append(AdjacencyRow(
            role_a=role_a, role_b=role_b, sample_count=both, adjacent_count=adjacent,
            raw_p_adjacent=round(raw_p, 6), p_adjacent=round(p_smoothed, 6), lift=lift,
            meets_min_support=both >= MIN_SUPPORT))
    return tuple(rows), baseline


def build_priors_table(corpus_dir: str = DEFAULT_CORPUS_DIR) -> AdjacencyPriorsTable:
    plans, scanned, excluded_synthetic = load_plan_role_adjacencies(corpus_dir)
    rows, baseline = compute_rows(plans)
    if not rows:
        raise EmptyCorpusError(
            f"scanned {scanned} plan(s) under {corpus_dir} but found zero role pairs — every plan "
            "has fewer than two distinct roles")
    return AdjacencyPriorsTable(
        rows=rows, baseline_adjacency_rate=baseline, smoothing_method=SMOOTHING_METHOD,
        smoothing_alpha=SMOOTHING_ALPHA, min_support=MIN_SUPPORT, corpus_dir=corpus_dir,
        plans_scanned=scanned, plans_excluded_synthetic=excluded_synthetic)


def eligible_pairs_for_roles(roles) -> list:
    """Every unordered pair of DISTINCT roles in `roles`, sorted — the pairing rule both the
    artifact and Step 2's scoring share: a "role pair" is always two different roles."""
    ordered = sorted(set(roles))
    return [(ordered[i], ordered[j])
            for i in range(len(ordered)) for j in range(i + 1, len(ordered))]


def plan_log_likelihood(pair_outcomes: Sequence, table: AdjacencyPriorsTable) -> float | None:
    """Issue #141, Step 2 — THE score: the log-likelihood of a plan's own adjacency pattern under
    the measured real distribution, symmetric over presence AND absence, normalized by the eligible
    -pair count so a plan with more rooms earns no automatic advantage.

    `pair_outcomes` is `(role_a, role_b, adjacent)` for every unordered pair of distinct roles BOTH
    present in the plan being scored — `adjacent` is whether the plan actually realizes that pair as
    touching. A pair whose artifact row does not meet `MIN_SUPPORT` (or has no row at all)
    contributes to neither the sum nor the eligible-pair count (AC-3): "contributes nothing" means
    exactly that, not a neutral zero folded into the average.

    Returns `None` — a genuine "no evidence", never a fabricated `0.0` — when zero pairs are
    eligible (every present pair lacks a supported row, or the plan has fewer than two roles the
    table has ever seen together)."""
    contributions = []
    for role_a, role_b, adjacent in pair_outcomes:
        row = table.row_for(role_a, role_b)
        if row is None or not row.meets_min_support:
            continue
        p = row.p_adjacent
        y = 1.0 if adjacent else 0.0
        contributions.append(y * math.log(p) + (1.0 - y) * math.log(1.0 - p))
    if not contributions:
        return None
    return sum(contributions) / len(contributions)


def _repo_relpath(path: str) -> str:
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.relpath(os.path.abspath(path), start=backend_dir)


def table_to_dict(table: AdjacencyPriorsTable) -> dict:
    return {
        "corpus_dir": _repo_relpath(table.corpus_dir),
        "plans_scanned": table.plans_scanned,
        "plans_excluded_synthetic": table.plans_excluded_synthetic,
        "baseline_adjacency_rate": table.baseline_adjacency_rate,
        "smoothing_method": table.smoothing_method,
        "smoothing_alpha": table.smoothing_alpha,
        "min_support": table.min_support,
        "rows": [
            {"role_a": r.role_a, "role_b": r.role_b, "sample_count": r.sample_count,
             "adjacent_count": r.adjacent_count, "raw_p_adjacent": r.raw_p_adjacent,
             "p_adjacent": r.p_adjacent, "lift": r.lift, "meets_min_support": r.meets_min_support}
            for r in table.rows],
    }


def table_from_dict(data: dict) -> AdjacencyPriorsTable:
    rows = tuple(AdjacencyRow(**row) for row in data["rows"])
    return AdjacencyPriorsTable(
        rows=rows, baseline_adjacency_rate=data["baseline_adjacency_rate"],
        smoothing_method=data["smoothing_method"], smoothing_alpha=data["smoothing_alpha"],
        min_support=data["min_support"], corpus_dir=data["corpus_dir"],
        plans_scanned=data["plans_scanned"], plans_excluded_synthetic=data["plans_excluded_synthetic"])


def load_priors_table(path: str = DEFAULT_JSON_PATH) -> AdjacencyPriorsTable:
    if not os.path.exists(path):
        raise EmptyCorpusError(f"no committed priors table at {path} — run this module's CLI first")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not data.get("rows"):
        raise EmptyCorpusError(f"{path} carries zero rows — a stale or corrupt artifact")
    return table_from_dict(data)


def render_markdown_report(table: AdjacencyPriorsTable) -> str:
    lines = [
        "# Real-plan adjacency priors — measured artifact",
        "",
        "Issue #141, Step 1: a measured `P(adjacent | both roles present)` per unordered pair of "
        "room roles, used later ONLY as a soft ranking preference behind "
        "`ADJACENCY_PRIORS_ENABLED` — never a gate, never a validator, never a hard constraint.",
        "",
        "## Data source",
        "",
        f"`{_repo_relpath(table.corpus_dir)}` — **{table.plans_scanned} real plan(s) scanned** "
        f"({table.plans_excluded_synthetic} synthetic control plan(s) excluded).",
        "",
        "The full ResPlan corpus (17,107 real plans) lives only on the unmerged branch "
        "`integration/poc-architectural-brain`, not reachable from this worktree — the same "
        "constraint Issue #140's `room_proportion_priors.py` documented. This report measures the "
        "one real, licensed, reproducible sample committed on this branch: the 19-plan fixture at "
        "`tests/spikes/fixtures/geometry_shapes/plans/` (CC BY 4.0).",
        "",
        "## Method",
        "",
        "For every scanned plan, rooms are grouped by `type` (role). Roles the engine's own "
        "programme models as ONE room per house — LIVING, KITCHEN, DINING, CIRCULATION, "
        "FAMILY_ROOM — are reduced to their single LARGEST-area instance per plan first (same "
        "rationale, same role set, as `room_proportion_priors`'s own reduction: ResPlan sometimes "
        "labels a small entrance nook or stair sliver with the same role as the real room, and an "
        "unreduced sliver touches almost everything). Every other role keeps every instance.",
        "",
        f"Adjacency is read directly from ResPlan's own precomputed `adjacency_edges` field — this "
        "scanner does not re-derive touching from room polygons. For each unordered pair of "
        "distinct roles both present in a plan, the pair counts as adjacent in that plan if ANY "
        "room-id of the first role touches ANY room-id of the second.",
        "",
        f"**Smoothing**: `{table.smoothing_method}` (add-`{table.smoothing_alpha}`) over the raw "
        "`adjacent_count / sample_count` rate — `p_adjacent = (adjacent_count + α) / "
        "(sample_count + 2α)` — so a pair observed at 0% or 100% on a thin sample never produces "
        "`log(0)`/`log(1)` when Step 2's score consumes it.",
        "",
        f"**Minimum support**: `{table.min_support}` plans. A pair below this is still reported "
        "below (flagged, never hidden) but contributes NOTHING to Step 2's score — neither to the "
        "sum nor to the eligible-pair count.",
        "",
        f"**Baseline adjacency rate**: `{table.baseline_adjacency_rate}` — pooled across every "
        "(plan, role-pair) observation in the corpus. `lift = p_adjacent / baseline_adjacency_rate` "
        "per row.",
        "",
        "## Measured rows",
        "",
        f"{len(table.rows)} unordered role-pair row(s) observed in at least one scanned plan.",
        "",
        "| role_a | role_b | sample_count | adjacent_count | raw_p_adjacent | p_adjacent | lift | "
        "meets_min_support |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(table.rows, key=lambda r: -r.lift):
        flag = "" if r.meets_min_support else " ⚠ below min support"
        lines.append(f"| {r.role_a} | {r.role_b} | {r.sample_count} | {r.adjacent_count} | "
                     f"{r.raw_p_adjacent} | {r.p_adjacent} | {r.lift} | "
                     f"{r.meets_min_support}{flag} |")
    lines += [
        "",
        "⚠ = below minimum support — reported, never hidden. On a 19-plan corpus most pairs sit "
        "near this floor; this is the honest state of the reachable sample.",
        "",
        "Regenerate with (from `backend/`):",
        "",
        "    uv run python -m app.knowledge.adjacency_priors "
        "--write-json ../docs/reports/real-plan-priors/adjacency.json "
        "--write-report ../docs/reports/real-plan-priors/adjacency.md",
        "",
        "The scanner **fails loudly** (raises `EmptyCorpusError`, CLI exits non-zero) on zero plans "
        "scanned or an empty measurement — proven by `tests/knowledge/test_adjacency_priors.py`.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", default=DEFAULT_CORPUS_DIR)
    parser.add_argument("--write-json", default=None, help="path to write the priors JSON table")
    parser.add_argument("--write-report", default=None, help="path to write the Markdown report")
    args = parser.parse_args(argv)
    try:
        table = build_priors_table(args.corpus_dir)
    except AdjacencyPriorsError as exc:
        print(f"adjacency_priors: {exc}", file=sys.stderr)
        return 1
    print(f"scanned {table.plans_scanned} plan(s), {len(table.rows)} row(s), "
          f"baseline_adjacency_rate={table.baseline_adjacency_rate}")
    if args.write_json:
        with open(args.write_json, "w", encoding="utf-8") as f:
            json.dump(table_to_dict(table), f, indent=2)
        print(f"wrote {args.write_json}")
    if args.write_report:
        with open(args.write_report, "w", encoding="utf-8") as f:
            f.write(render_markdown_report(table))
        print(f"wrote {args.write_report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
