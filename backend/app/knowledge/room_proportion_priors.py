"""Real-plan room-proportion priors (Issue #140).

STEP 1 of a 3-step Issue: this module ONLY measures a distribution of how real plans size rooms
and writes a committed artifact. Nothing here changes engine behaviour — see
`app.vertical_slice.room_proportion_priors` for the soft ranking signal (Step 2) that later reads
the artifact this module produces, behind `ROOM_PROPORTION_PRIORS_ENABLED`.

DATA SOURCE, HONESTLY STATED: the Issue names "the ResPlan corpus (17,107 real plans)". That full
corpus, and the POC ingest code that produced it (`spikes/architectural_brain/`), live ONLY on the
unmerged branch `integration/poc-architectural-brain` — not reachable from this worktree (same
constraint `measure_real_plan_shapes.py` documented for Issue #102, and the reason its own
follow-up child Issue, `.agent/proposals/roadmap/102-1-full-corpus-remeasurement.md`, exists). The
one real, licensed, reproducible sample committed on this branch is the 20-plan fixture at
`tests/spikes/fixtures/geometry_shapes/plans/` (19 real ResPlan plans, CC BY 4.0, + 1 synthetic
control plan this module excludes by its own `provenance.source_dataset`) — this module reads it
by default, and accepts `--corpus-dir` to point at a larger corpus once one is reachable, exactly
like `measure_real_plan_shapes.py` does. Every artifact this module writes states its own sample
size; a reader must never mistake a 19-plan measurement for the full 17,107-plan corpus.

BUCKET DEFINITIONS, justified from the data's own distribution (never invented round numbers): a
house-size bucket is the plan's own `derived.footprint_area_m2` split into thirds at the 33rd/66th
percentile of the CORPUS ACTUALLY SCANNED — recomputed every run, so a different corpus gets its
own edges rather than inheriting a value tuned for the 19-plan sample. A bedroom-count bucket is
built the same way over `derived.room_type_counts["BEDROOM"]`, except when the corpus has fewer
than 3 distinct bedroom-count values (true of the 19-plan sample: 16/19 plans are 3-bedroom) — in
that case tercile edges degenerate to a single point, so this module falls back to three named
groups instead: `LOW` (below the corpus's own median bedroom count), `TYPICAL` (equal to the
corpus's own median), `HIGH` (above it). Both fallbacks are themselves computed from the scanned
data, not hardcoded.

FAILS LOUDLY (Step 1's own requirement): `load_room_samples` raises `EmptyCorpusError` when the
corpus directory has zero plan files, or when every file is excluded (synthetic) or yields zero
usable room samples. The CLI (`main`) catches every `RoomProportionPriorsError` and exits non-zero
— a silent empty result must never look like a real answer (the Issue's own stated reason this
module exists).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from dataclasses import dataclass

DEFAULT_CORPUS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tests", "spikes", "fixtures", "geometry_shapes", "plans",
)

#: `app/knowledge/data/` is gitignored (runtime index state, see `backend/.gitignore`) — the
#: committed data artifact lives beside its own Markdown report under `docs/reports/` instead, so
#: a fresh checkout (CI included) actually has it.
DEFAULT_JSON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "docs", "reports", "real-plan-priors", "room-proportions.json")

_SYNTHETIC_SOURCE_DATASETS = frozenset({"SYNTHETIC"})

_MIN_DISTINCT_FOR_TERCILES = 3

#: Roles the engine's own programme (`concept_generator.ROOM_TEMPLATES`) models as ONE room per
#: house — LIVING, KITCHEN, DINING, the public sitting room, and the corridor. ResPlan's own room
#: labelling is coarser than that: a plan may carry a second, small "LIVING"-typed fragment (an
#: entrance nook, a sliver beside a stair) alongside the real living room — measured directly on
#: this corpus's own `47.json`: LIVING_0 = 74.7 m2 (the real room), LIVING_1 = 4.6 m2 (a nook), both
#: typed "LIVING". Aggregating every instance would blend the two into one bimodal, unusable
#: distribution (measured: median 4.6 m2 either side of a real 50-70 m2 room). For these roles only,
#: this scanner keeps the SINGLE LARGEST-area instance per plan — the one instance that actually
#: corresponds to the engine's one zone of that role. BEDROOM/BATHROOM/TOILET/STORAGE are NOT here:
#: the engine's programme also has multiple rooms of those roles, so every real instance is kept.
_SINGLE_INSTANCE_ROLES = frozenset({"LIVING", "KITCHEN", "DINING", "CIRCULATION", "FAMILY_ROOM"})


def _reduce_single_instance_roles(plan_samples: dict[str, list["RoomSample"]]) -> list["RoomSample"]:
    reduced: list[RoomSample] = []
    for role, instances in plan_samples.items():
        if role in _SINGLE_INSTANCE_ROLES and len(instances) > 1:
            reduced.append(max(instances, key=lambda s: s.area_m2))
        else:
            reduced.extend(instances)
    return reduced


class RoomProportionPriorsError(RuntimeError):
    """Base class for this module's own loud-failure exceptions — never caught and hidden."""


class EmptyCorpusError(RoomProportionPriorsError):
    """Raised when the scanner scanned zero usable plans, or extracted zero room samples."""


class EmptyBucketError(RoomProportionPriorsError):
    """Raised when a caller asks this module for a specific (role, bucket, bucket) it expected to
    have samples, and the measured table has none — never returned as a silent zero/None."""


@dataclass(frozen=True)
class RoomSample:
    plan_id: str
    role: str
    area_m2: float
    aspect: float
    footprint_area_m2: float
    bedroom_count: int


@dataclass(frozen=True)
class ProportionRow:
    role: str
    house_size_bucket: str
    bedroom_count_bucket: str
    median_area_m2: float
    p25_area_m2: float
    p75_area_m2: float
    median_aspect: float
    area_share_of_plan: float
    sample_count: int


@dataclass(frozen=True)
class BucketEdges:
    """The exact numeric cut points this scan computed, so a later reader (the runtime scorer,
    Step 2) buckets a NEW candidate the same way the artifact was built, instead of re-deriving a
    possibly-different split."""

    house_size_terciles: tuple[float, float] | None
    bedroom_count_terciles: tuple[float, float] | None
    bedroom_count_median: float


@dataclass(frozen=True)
class PriorsTable:
    rows: tuple[ProportionRow, ...]
    edges: BucketEdges
    corpus_dir: str
    plans_scanned: int
    plans_excluded_synthetic: int

    def row_for(self, role: str, house_bucket: str, bedroom_bucket: str) -> ProportionRow | None:
        for row in self.rows:
            if (row.role == role and row.house_size_bucket == house_bucket
                    and row.bedroom_count_bucket == bedroom_bucket):
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


def load_room_samples(corpus_dir: str = DEFAULT_CORPUS_DIR) -> tuple[list[RoomSample], int, int]:
    """Every usable `RoomSample` in `corpus_dir`, plus (plans scanned, plans excluded synthetic).

    Raises `EmptyCorpusError` rather than returning an empty list: a scanner that can silently
    report zero looks exactly like a real answer of zero, which is the defect this Issue exists to
    prevent (see the module docstring)."""
    if not os.path.isdir(corpus_dir):
        raise EmptyCorpusError(f"corpus directory does not exist: {corpus_dir}")
    files = sorted(f for f in os.listdir(corpus_dir) if f.endswith(".json"))
    if not files:
        raise EmptyCorpusError(f"no plan files (*.json) found under {corpus_dir}")

    samples: list[RoomSample] = []
    scanned = 0
    excluded_synthetic = 0
    for filename in files:
        plan_reference = _load_plan_file(os.path.join(corpus_dir, filename))
        if plan_reference is None:
            excluded_synthetic += 1
            continue
        scanned += 1
        derived = plan_reference.get("derived", {})
        footprint_area_m2 = derived.get("footprint_area_m2")
        bedroom_count = derived.get("room_type_counts", {}).get("BEDROOM", 0)
        plan_id = plan_reference.get("plan_id", filename)
        if not footprint_area_m2:
            continue
        plan_samples: dict[str, list[RoomSample]] = {}
        for room in plan_reference.get("rooms", ()):
            area_m2 = room.get("area_m2")
            width_m = room.get("width_m")
            depth_m = room.get("depth_m")
            role = room.get("type")
            if not (area_m2 and width_m and depth_m and role) or min(width_m, depth_m) <= 0:
                continue
            plan_samples.setdefault(role, []).append(RoomSample(
                plan_id=plan_id, role=role, area_m2=area_m2,
                aspect=max(width_m, depth_m) / min(width_m, depth_m),
                footprint_area_m2=footprint_area_m2, bedroom_count=bedroom_count))
        samples.extend(_reduce_single_instance_roles(plan_samples))

    if scanned == 0:
        raise EmptyCorpusError(
            f"every file under {corpus_dir} was excluded (synthetic) — zero real plans scanned")
    if not samples:
        raise EmptyCorpusError(
            f"scanned {scanned} plan(s) under {corpus_dir} but extracted zero usable room samples "
            "(missing area_m2/width_m/depth_m/type on every room)")
    return samples, scanned, excluded_synthetic


def _terciles(values: list[float]) -> tuple[float, float] | None:
    distinct = sorted(set(values))
    if len(distinct) < _MIN_DISTINCT_FOR_TERCILES:
        return None
    q33, q66 = statistics.quantiles(values, n=3, method="inclusive")
    return (q33, q66)


def compute_bucket_edges(samples: list[RoomSample]) -> BucketEdges:
    footprints = [s.footprint_area_m2 for s in _unique_plans(samples)]
    bedroom_counts = [float(s.bedroom_count) for s in _unique_plans(samples)]
    return BucketEdges(
        house_size_terciles=_terciles(footprints),
        bedroom_count_terciles=_terciles(bedroom_counts),
        bedroom_count_median=statistics.median(bedroom_counts))


def _unique_plans(samples: list[RoomSample]) -> list[RoomSample]:
    seen: dict[str, RoomSample] = {}
    for s in samples:
        seen.setdefault(s.plan_id, s)
    return list(seen.values())


def house_size_bucket(footprint_area_m2: float, edges: BucketEdges) -> str:
    if edges.house_size_terciles is None:
        return "ALL"
    q33, q66 = edges.house_size_terciles
    if footprint_area_m2 <= q33:
        return f"SMALL(<={q33:.0f}m2)"
    if footprint_area_m2 <= q66:
        return f"MEDIUM({q33:.0f}-{q66:.0f}m2)"
    return f"LARGE(>{q66:.0f}m2)"


def bedroom_count_bucket(bedroom_count: int, edges: BucketEdges) -> str:
    if edges.bedroom_count_terciles is not None:
        q33, q66 = edges.bedroom_count_terciles
        if bedroom_count <= q33:
            return f"LOW(<={q33:.0f}bd)"
        if bedroom_count <= q66:
            return f"MID({q33:.0f}-{q66:.0f}bd)"
        return f"HIGH(>{q66:.0f}bd)"
    median = edges.bedroom_count_median
    if bedroom_count < median:
        return f"LOW(<{median:.0f}bd)"
    if bedroom_count == median:
        return f"TYPICAL({median:.0f}bd)"
    return f"HIGH(>{median:.0f}bd)"


def compute_rows(samples: list[RoomSample], edges: BucketEdges) -> list[ProportionRow]:
    """One row per (role, house-size bucket, bedroom-count bucket) actually PRESENT in `samples` —
    never a fabricated zero-sample row for a combination the data never produced."""
    groups: dict[tuple[str, str, str], list[RoomSample]] = {}
    for s in samples:
        key = (s.role, house_size_bucket(s.footprint_area_m2, edges),
               bedroom_count_bucket(s.bedroom_count, edges))
        groups.setdefault(key, []).append(s)

    rows: list[ProportionRow] = []
    for (role, house_bucket, bedroom_bucket), group in sorted(groups.items()):
        areas = [g.area_m2 for g in group]
        aspects = [g.aspect for g in group]
        shares = [g.area_m2 / g.footprint_area_m2 for g in group]
        p25, p75 = (statistics.quantiles(areas, n=4, method="inclusive")[0],
                    statistics.quantiles(areas, n=4, method="inclusive")[2]) if len(areas) >= 2 \
            else (areas[0], areas[0])
        rows.append(ProportionRow(
            role=role, house_size_bucket=house_bucket, bedroom_count_bucket=bedroom_bucket,
            median_area_m2=round(statistics.median(areas), 3),
            p25_area_m2=round(p25, 3), p75_area_m2=round(p75, 3),
            median_aspect=round(statistics.median(aspects), 3),
            area_share_of_plan=round(statistics.median(shares), 4),
            sample_count=len(group)))
    return rows


def build_priors_table(corpus_dir: str = DEFAULT_CORPUS_DIR) -> PriorsTable:
    samples, scanned, excluded_synthetic = load_room_samples(corpus_dir)
    edges = compute_bucket_edges(samples)
    rows = compute_rows(samples, edges)
    return PriorsTable(rows=tuple(rows), edges=edges, corpus_dir=corpus_dir,
                       plans_scanned=scanned, plans_excluded_synthetic=excluded_synthetic)


#: A row this thin is reported, never hidden — the artifact flags it rather than silently
#: presenting a median computed from almost no evidence as if it were reliable.
LOW_CONFIDENCE_SAMPLE_COUNT = 3


def _repo_relpath(path: str) -> str:
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.relpath(os.path.abspath(path), start=backend_dir)


def table_to_dict(table: PriorsTable) -> dict:
    return {
        "corpus_dir": _repo_relpath(table.corpus_dir),
        "plans_scanned": table.plans_scanned,
        "plans_excluded_synthetic": table.plans_excluded_synthetic,
        "edges": {
            "house_size_terciles": list(table.edges.house_size_terciles)
                                   if table.edges.house_size_terciles else None,
            "bedroom_count_terciles": list(table.edges.bedroom_count_terciles)
                                      if table.edges.bedroom_count_terciles else None,
            "bedroom_count_median": table.edges.bedroom_count_median,
        },
        "rows": [
            {"role": r.role, "house_size_bucket": r.house_size_bucket,
             "bedroom_count_bucket": r.bedroom_count_bucket,
             "median_area_m2": r.median_area_m2, "p25_area_m2": r.p25_area_m2,
             "p75_area_m2": r.p75_area_m2, "median_aspect": r.median_aspect,
             "area_share_of_plan": r.area_share_of_plan, "sample_count": r.sample_count}
            for r in table.rows],
    }


def table_from_dict(data: dict) -> PriorsTable:
    edges = BucketEdges(
        house_size_terciles=(tuple(data["edges"]["house_size_terciles"])
                             if data["edges"]["house_size_terciles"] else None),
        bedroom_count_terciles=(tuple(data["edges"]["bedroom_count_terciles"])
                                if data["edges"]["bedroom_count_terciles"] else None),
        bedroom_count_median=data["edges"]["bedroom_count_median"])
    rows = tuple(ProportionRow(**row) for row in data["rows"])
    return PriorsTable(rows=rows, edges=edges, corpus_dir=data["corpus_dir"],
                       plans_scanned=data["plans_scanned"],
                       plans_excluded_synthetic=data["plans_excluded_synthetic"])


def load_priors_table(path: str = DEFAULT_JSON_PATH) -> PriorsTable:
    if not os.path.exists(path):
        raise EmptyCorpusError(f"no committed priors table at {path} — run this module's CLI first")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not data.get("rows"):
        raise EmptyCorpusError(f"{path} carries zero rows — a stale or corrupt artifact")
    return table_from_dict(data)


def render_markdown_report(table: PriorsTable) -> str:
    lines = [
        "# Real-plan room-proportion priors — measured artifact",
        "",
        "Issue #140, Step 1: a measured distribution of how real ResPlan plans size rooms, used "
        "later ONLY as a soft ranking preference behind `ROOM_PROPORTION_PRIORS_ENABLED` — never "
        "a hard constraint, never a change to `ROOM_TEMPLATES`.",
        "",
        "## Data source",
        "",
        f"`{_repo_relpath(table.corpus_dir)}` — **{table.plans_scanned} real plan(s) scanned** "
        f"({table.plans_excluded_synthetic} synthetic control plan(s) excluded).",
        "",
        "The Issue names the full ResPlan corpus (17,107 real plans, ingested for the POC as "
        "`PlanReference`). That corpus, and the POC ingest code that produced it "
        "(`spikes/architectural_brain/`), live only on the unmerged branch "
        "`integration/poc-architectural-brain` — not reachable from this worktree, the same "
        "constraint Issue #102's `measure_real_plan_shapes.py` documented. The one real, licensed, "
        "reproducible sample committed on this branch is the 20-plan fixture at "
        "`tests/spikes/fixtures/geometry_shapes/plans/` (19 real ResPlan plans, CC BY 4.0, + 1 "
        "synthetic control this scan excludes). This report measures that 19-plan sample. A "
        "full-corpus remeasurement is the natural next step once an integration worktree makes "
        "`spikes/architectural_brain/corpus/` reachable — see "
        "`.agent/proposals/roadmap/102-1-full-corpus-remeasurement.md` for the exact precedent.",
        "",
        "## Bucket definitions, justified from the data's own distribution",
        "",
        "**House-size bucket**: the plan's own `derived.footprint_area_m2`, split into thirds at "
        "the 33rd/66th percentile of the plans actually scanned (recomputed every run — a larger "
        "corpus gets its own edges, never a value tuned for this 19-plan sample).",
    ]
    if table.edges.house_size_terciles:
        q33, q66 = table.edges.house_size_terciles
        lines.append(f"Measured edges on this scan: {q33:.1f} m2 / {q66:.1f} m2.")
    else:
        lines.append("This scan had fewer than 3 distinct footprint values — a single `ALL` "
                     "bucket is used instead of a fabricated split.")
    lines += [
        "",
        "**Bedroom-count bucket**: the same tercile method over "
        "`derived.room_type_counts[\"BEDROOM\"]`, except when the corpus has fewer than 3 "
        "distinct bedroom counts (true here: 16/19 plans are 3-bedroom) — in that case the split "
        "degenerates to a single point, so this scan falls back to three groups relative to the "
        "corpus's OWN median bedroom count instead: `LOW` (below it), `TYPICAL` (equal to it), "
        f"`HIGH` (above it). Measured median on this scan: {table.edges.bedroom_count_median:.0f} "
        "bedroom(s).",
        "",
        "## Measured rows",
        "",
        f"{len(table.rows)} (role, house-size bucket, bedroom-count bucket) row(s) with at least "
        "one real sample. No row is fabricated for a combination the data never produced.",
        "",
        "| role | house_size_bucket | bedroom_count_bucket | median_area_m2 | p25_area_m2 | "
        "p75_area_m2 | median_aspect | area_share_of_plan | sample_count |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in table.rows:
        flag = " ⚠ low-confidence" if r.sample_count < LOW_CONFIDENCE_SAMPLE_COUNT else ""
        lines.append(f"| {r.role} | {r.house_size_bucket} | {r.bedroom_count_bucket} | "
                     f"{r.median_area_m2} | {r.p25_area_m2} | {r.p75_area_m2} | "
                     f"{r.median_aspect} | {r.area_share_of_plan} | {r.sample_count}{flag} |")
    lines += [
        "",
        f"⚠ = below {LOW_CONFIDENCE_SAMPLE_COUNT} samples — reported, never hidden. On a 19-plan "
        "corpus most rows sit near this floor; this is the honest state of the reachable sample, "
        "not a defect in the scanner (see 'Data source' above for the reachability gap this "
        "reflects).",
        "",
        "## Method",
        "",
        "`app.knowledge.room_proportion_priors.build_priors_table` reads every `*.json` file in "
        "the corpus directory as a `PlanReference` (tolerating either the bare schema or the "
        "`{\"plan_reference\": {...}}` wrapper used by the geometry-shapes fixture), excludes any "
        "plan whose `provenance.source_dataset` is `SYNTHETIC`, and for every remaining room with "
        "`area_m2`/`width_m`/`depth_m`/`type` computes `aspect = max(w,d)/min(w,d)` and "
        "`area_share = area_m2 / footprint_area_m2`. Rows aggregate by median/p25/p75 "
        "(`statistics.quantiles`, `method=\"inclusive\"`).",
        "",
        "Regenerate with (from `backend/`):",
        "",
        "    uv run python -m app.knowledge.room_proportion_priors "
        "--write-json ../docs/reports/real-plan-priors/room-proportions.json "
        "--write-report ../docs/reports/real-plan-priors/room-proportions.md",
        "",
        "The scanner **fails loudly** (raises `EmptyCorpusError`, CLI exits non-zero) on zero "
        "plans scanned or zero usable room samples extracted — proven by "
        "`tests/knowledge/test_room_proportion_priors.py`.",
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
    except RoomProportionPriorsError as exc:
        print(f"room_proportion_priors: {exc}", file=sys.stderr)
        return 1
    print(f"scanned {table.plans_scanned} plan(s), {len(table.rows)} row(s), "
          f"{sum(r.sample_count for r in table.rows)} room sample(s)")
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
