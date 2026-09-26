"""Architectural-quality metrics M1–M6, read off a realized `app.demo.contract.DemoDesign`.

Moved out of `spikes/failure_log_sweep/quality_metrics.py` (Issue #17) — that script now imports
this module instead of computing its own copy, so the two never drift. Reference values (21
professional plans, visual census) are in `specs/005-hub-private-wing/spec.md` §1; the measured
gaps against them, and the PROPOSED follow-ups, are written up in
`docs/wiki/architecture/geometry-validation.md`.

Side-effect-free and deliberately does not import `app.demo.contract` at runtime (that module
imports `app.vertical_slice.*` and would make this a circular import) — the functions here are
duck-typed against `DemoDesign`'s shape: `.rooms` (`.id`, `.type`, `.gross_width_m`,
`.gross_depth_m`), `.walls` (`.boundary_context`, `.room_ids`), `.open_interfaces` (`.room_ids`),
`.doors` (`.a`, `.b`, `.kind`, `.is_entrance`).

Uses the GROSS rectangle deliberately, not `RoomOut`'s net `.width_m`/`.depth_m` (Issue #34's
gross/net split) — these metrics measure how the built envelope is proportioned/shared, the same
question a floor plan's own wall centerlines answer, and switching to net would move every M1/M3/M4
number by each room's own wall-inset share for no architectural reason. It also keeps this
module's numbers, and the frozen `quality_baseline.json` regression, unchanged by that Issue.

    measure_design(design)          -> QualityMetrics  # one plan's own M1–M6
    summarize(designs)              -> dict            # corpus medians/shares (the spike's report)
    baseline_summary(dict)          -> dict             # the four load-bearing stats a baseline freezes
    baseline_summary_from_metrics(list[dict]) -> dict   # same four stats, from stored per-plan metrics
    find_regressions(...)           -> list[str]        # baseline vs current, tolerance-checked
"""
from __future__ import annotations

import dataclasses
import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.demo.contract import DemoDesign

HABITABLE = ("BED", "MASTER", "LIVING", "DINING", "KITCHEN", "STUDY", "FAMILY", "SAFE")
WET = ("BATH", "TOILET", "WC")
WET_NEIGHBOURS = WET + ("KITCHEN", "LAUNDRY")
PUBLIC = ("LIVING", "DINING", "KITCHEN")
HALL = ("HALL", "CIRC")

#: A hall at or under this long/short ratio reads as a compact lobby rather than a spine
#: (`README.md`'s M4; spec 005 §1's "hall spine aspect 9.4 vs a compact lobby").
COMPACT_HALL_ASPECT_MAX = 1.5

#: Tolerance a corpus-level summary stat may move before `find_regressions` names it — percentage
#: points for a share (M3/M5/M6), aspect-ratio units for M4. A no-regression bar, not a target
#: (see the Wiki page): a change that makes a metric BETTER never regresses, by however much.
CIRCULATION_SHARE_TOLERANCE = 0.02
WET_ADJACENCY_SHARE_TOLERANCE = 0.02
PUBLIC_CONTIGUOUS_SHARE_TOLERANCE = 0.02
HALL_ASPECT_TOLERANCE = 0.2


def is_(kind, room_type: str) -> bool:
    t = room_type.upper()
    return any(k in t for k in kind)


@dataclass(frozen=True)
class QualityMetrics:
    """M1–M6 for ONE realized plan, plus the two additive facts (`dead_space_m2`,
    `wasted_circulation_share`) `QualityOut.metrics` carries. A value is `None` only when the
    plan genuinely has no room of the kind that metric measures (e.g. no wet room -> M5 `None`).
    """

    m1_habitable_aspect_median: float | None
    m1_habitable_aspect_max: float | None
    m2_habitable_on_envelope_ratio: float | None
    m3_circulation_share: float
    m4_hall_door_count: int | None
    m4_hall_aspect_median: float | None
    m5_wet_adjacency_ratio: float | None
    m6_public_zone_contiguous: bool | None
    #: Always 0 — validation C2 already gates every delivered plan on zero residual interior
    #: area. Carried as data, not re-derived, so a future change to C2 would be visible here too.
    dead_space_m2: float = 0.0
    #: Share of this plan's total area sitting in a hall whose long/short ratio is past
    #: `COMPACT_HALL_ASPECT_MAX` — the portion of M3's circulation share that reads as a spine
    #: rather than a lobby, and so is plausibly recoverable (not all circulation is "waste").
    wasted_circulation_share: float = 0.0


# --------------------------------------------------------------------------- per-design facts


def _habitable_aspects(design: "DemoDesign") -> list[tuple[str, float]]:
    return [(r.type, max(r.gross_width_m, r.gross_depth_m) / max(min(r.gross_width_m, r.gross_depth_m), 1e-6))
            for r in design.rooms if is_(HABITABLE, r.type)]


def _exterior_room_ids(design: "DemoDesign") -> set[str]:
    ext: set[str] = set()
    for w in design.walls:
        if w.boundary_context == "EXTERIOR":
            ext.update(w.room_ids)
    return ext


def _hall_room_ids(design: "DemoDesign") -> set[str]:
    return {r.id for r in design.rooms if is_(HALL, r.type)}


def _hall_stats(design: "DemoDesign") -> dict:
    # `gross_area_m2` (not `gross_width_m * gross_depth_m`) — identical for a RECTANGLE room
    # (that product IS its `gross_area_m2`, by construction), but for a merged "L" room
    # `gross_width_m`/`gross_depth_m` are the room's own AXIS-ALIGNED BOUNDING BOX, which
    # overstates a real (non-flush) L's true footprint; `gross_area_m2` is always the room's own
    # true area (Issue #118, AC-1).
    rooms = {r.id: r for r in design.rooms}
    halls = _hall_room_ids(design)
    total = sum(r.gross_area_m2 for r in design.rooms)
    circ_area = sum(r.gross_area_m2 for r in design.rooms if r.id in halls)
    aspects, wasted_area = [], 0.0
    for h in halls:
        r = rooms[h]
        a = max(r.gross_width_m, r.gross_depth_m) / max(min(r.gross_width_m, r.gross_depth_m), 1e-6)
        aspects.append(a)
        if a > COMPACT_HALL_ASPECT_MAX:
            wasted_area += r.gross_area_m2
    door_count = sum(1 for dr in design.doors if not dr.is_entrance and (dr.a in halls or dr.b in halls))
    return dict(
        circ_share=circ_area / total if total else 0.0,
        hall_aspects=aspects,
        hall_door_count=door_count,
        wasted_circulation_share=wasted_area / total if total else 0.0,
    )


def _interior_adjacency(design: "DemoDesign") -> dict[str, set[str]]:
    adj: dict[str, set[str]] = defaultdict(set)
    for w in design.walls:
        if w.boundary_context == "INTERIOR" and len(w.room_ids) >= 2:
            for rid in w.room_ids:
                adj[rid].update(x for x in w.room_ids if x != rid)
    return adj


def wet_adjacency_counts(design: "DemoDesign") -> tuple[int, int]:
    """(adjacent, total) wet rooms for this one plan — the raw components M5's ratio is built
    from, and what `summarize()` pools across every plan in the corpus for the corpus-level share.
    Public (not `_`-prefixed) because a corpus snapshot needs these RAW counts verbatim, not the
    ratio `measure_design` reports: plans have different wet-room counts, so a mean of per-plan
    ratios is not the same number as this pooled share (`baseline_summary_from_metrics`)."""
    rooms = {r.id: r for r in design.rooms}
    adj = _interior_adjacency(design)
    adjacent = total = 0
    for r in design.rooms:
        if is_(WET, r.type):
            total += 1
            adjacent += any(is_(WET_NEIGHBOURS, rooms[n].type) for n in adj[r.id] if n in rooms)
    return adjacent, total


def _open_adjacency(design: "DemoDesign") -> dict[str, set[str]]:
    open_adj: dict[str, set[str]] = defaultdict(set)
    for o in design.open_interfaces:
        for rid in o.room_ids:
            open_adj[rid].update(x for x in o.room_ids if x != rid)
    for dr in design.doors:
        if "CASED" in dr.kind.upper() or "OPEN" in dr.kind.upper():
            open_adj[dr.a].add(dr.b)
            open_adj[dr.b].add(dr.a)
    return open_adj


def _public_zone_contiguous(design: "DemoDesign") -> bool | None:
    pub = [r.id for r in design.rooms if is_(PUBLIC, r.type)]
    if len(pub) < 2:
        # A validated LIVING+KITCHEN merge (Issue #118) can leave exactly ONE public room (no
        # DINING in the plan) — that IS one contiguous public room, more so than an open-plan
        # join (there is no seam left at all), not "nothing to measure." `< 2` otherwise never
        # happens on this codebase's own room programme (LIVING and KITCHEN are always both
        # present), so this is scoped to the merge case, not a general threshold change.
        if len(pub) == 1 and any(r.id == pub[0] and getattr(r, "shape", "RECTANGLE") == "L"
                                 for r in design.rooms):
            return True
        return None
    open_adj = _open_adjacency(design)
    seen: set[str] = set()
    stack = [pub[0]]
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(x for x in open_adj[n] if x in pub)
    return all(p in seen for p in pub)


# --------------------------------------------------------------------------- public API


def measure_design(design: "DemoDesign") -> QualityMetrics:
    """M1–M6 for one realized plan (see `QualityMetrics`)."""
    aspects = [a for _, a in _habitable_aspects(design)]
    ext = _exterior_room_ids(design)
    exposed = sum(1 for r in design.rooms if is_(HABITABLE, r.type) and r.id in ext)
    hab_total = len(aspects)
    hall = _hall_stats(design)
    wet_adjacent, wet_total = wet_adjacency_counts(design)
    return QualityMetrics(
        m1_habitable_aspect_median=statistics.median(aspects) if aspects else None,
        m1_habitable_aspect_max=max(aspects) if aspects else None,
        m2_habitable_on_envelope_ratio=(exposed / hab_total) if hab_total else None,
        m3_circulation_share=hall["circ_share"],
        m4_hall_door_count=hall["hall_door_count"] if hall["hall_aspects"] else None,
        m4_hall_aspect_median=statistics.median(hall["hall_aspects"]) if hall["hall_aspects"] else None,
        m5_wet_adjacency_ratio=(wet_adjacent / wet_total) if wet_total else None,
        m6_public_zone_contiguous=_public_zone_contiguous(design),
        dead_space_m2=0.0,
        wasted_circulation_share=hall["wasted_circulation_share"],
    )


def summarize(designs: "list[DemoDesign]") -> dict:
    """Corpus medians/shares over many plans — the spike's own `measure()`, unchanged."""
    aspects, by_type = [], defaultdict(list)
    exposed = hab = 0
    circ, hub_deg, hall_asp = [], [], []
    wet_adj = wet_tot = 0
    contig = pub_plans = 0
    for d in designs:
        ext = _exterior_room_ids(d)
        for t, a in _habitable_aspects(d):
            aspects.append(a)
            by_type[t].append(a)
            hab += 1
        for r in d.rooms:
            if is_(HABITABLE, r.type):
                exposed += r.id in ext
        hall = _hall_stats(d)
        circ.append(hall["circ_share"])
        hub_deg.append(hall["hall_door_count"])
        hall_asp.extend(hall["hall_aspects"])
        wa, wt = wet_adjacency_counts(d)
        wet_adj += wa
        wet_tot += wt
        contiguous = _public_zone_contiguous(d)
        if contiguous is not None:
            pub_plans += 1
            contig += contiguous
    aspects.sort()
    return dict(
        n=len(designs),
        aspect_median=statistics.median(aspects) if aspects else None,
        aspect_p90=aspects[int(0.9 * len(aspects))] if aspects else None,
        by_type={t: (round(statistics.median(v), 2), len(v)) for t, v in sorted(by_type.items())},
        exposure=(exposed, hab),
        circ_median=statistics.median(circ) if circ else None,
        circ_max=max(circ) if circ else None,
        hall_doors_median=statistics.median(hub_deg) if hub_deg else None,
        hall_doors_range=(min(hub_deg), max(hub_deg)) if hub_deg else None,
        hall_aspect_median=statistics.median(hall_asp) if hall_asp else None,
        hall_compact_share=(sum(1 for a in hall_asp if a <= COMPACT_HALL_ASPECT_MAX), len(hall_asp)),
        wet=(wet_adj, wet_tot),
        public_contig=(contig, pub_plans),
    )


def _share(counted: tuple[int, int]) -> float | None:
    n, d = counted
    return n / d if d else None


def baseline_summary(summary: dict) -> dict:
    """The four load-bearing corpus stats a baseline freezes and the regression test checks —
    M3 median, M4 hall aspect median, M5 share, M6 share. Everything else `summarize()` reports
    (M1, M2, per-type breakdowns) is diagnostic, not gated — see the Wiki page for why."""
    return {
        "n": summary["n"],
        "m3_circulation_share_median": summary["circ_median"],
        "m4_hall_aspect_median": summary["hall_aspect_median"],
        "m5_wet_adjacency_share": _share(summary["wet"]),
        "m6_public_contiguous_share": _share(summary["public_contig"]),
    }


def baseline_summary_from_metrics(metrics: "list[dict]") -> dict:
    """The same four load-bearing stats `baseline_summary(summarize(designs))` computes, read
    directly off each plan's own already-computed `measure_design` output (e.g. `dict`s read back
    from a CI corpus snapshot's per-context `"metrics"`) instead of the raw `DemoDesign` list —
    replaying the whole corpus a third time in one process is what CI's 120-minute budget does not
    fit (Issue #17 repair). Each `metrics` dict is `dataclasses.asdict(QualityMetrics)`, PLUS the
    two raw `wet_adjacency_counts` fields `corpus_snapshot.py` folds into that same dict
    (`m5_wet_adjacent_count`, `m5_wet_total_count` — not part of `QualityMetrics`/`QualityOut`,
    only the snapshot's own copy) — M5's per-plan RATIO alone cannot be re-pooled into a corpus
    share: plans have different wet-room counts, so an unweighted mean of per-plan ratios is a
    different number from `summarize()`'s pooled adjacent/total share (measured gap on this
    corpus: 11.7pp, ~6x the 2pp tolerance — this is not a rounding nicety).

    M3 (median of each plan's own share) and M6 (share of plans with a contiguous public zone)
    reproduce `summarize()`'s own aggregation exactly off `measure_design`'s fields alone — both
    are already per-plan values there too. So does M4 (median hall aspect) on any corpus where
    every plan has at most one hall room, true of every plan in this codebase's corpus today (a
    single circulation hub) — verified byte-identical against `quality_baseline.json`; a future
    plan type introducing multiple halls would make M4 approximate the same way a naive M5 is.
    """
    rows = [m if isinstance(m, dict) else dataclasses.asdict(m) for m in metrics]
    m3 = [r["m3_circulation_share"] for r in rows]
    m4 = [r["m4_hall_aspect_median"] for r in rows if r.get("m4_hall_aspect_median") is not None]
    m6 = [r["m6_public_zone_contiguous"] for r in rows if r.get("m6_public_zone_contiguous") is not None]
    wet_rows = [r for r in rows if r.get("m5_wet_total_count")]
    wet_adjacent = sum(r["m5_wet_adjacent_count"] for r in wet_rows)
    wet_total = sum(r["m5_wet_total_count"] for r in wet_rows)
    return {
        "n": len(rows),
        "m3_circulation_share_median": statistics.median(m3) if m3 else None,
        "m4_hall_aspect_median": statistics.median(m4) if m4 else None,
        "m5_wet_adjacency_share": (wet_adjacent / wet_total) if wet_total else None,
        "m6_public_contiguous_share": (sum(m6) / len(m6)) if m6 else None,
    }


#: (metric key, tolerance, direction) — "higher_is_better" regresses on a DROP past tolerance,
#: "lower_is_better" regresses on a RISE past tolerance.
_REGRESSION_CHECKS = (
    ("m3_circulation_share_median", CIRCULATION_SHARE_TOLERANCE, "lower_is_better"),
    ("m4_hall_aspect_median", HALL_ASPECT_TOLERANCE, "lower_is_better"),
    ("m5_wet_adjacency_share", WET_ADJACENCY_SHARE_TOLERANCE, "higher_is_better"),
    ("m6_public_contiguous_share", PUBLIC_CONTIGUOUS_SHARE_TOLERANCE, "higher_is_better"),
)


def find_regressions(baseline: dict, current: dict) -> list[str]:
    """Which of the four `baseline_summary()` keys moved the wrong way by more than its
    tolerance. Empty when nothing regressed — including when a metric is missing from either
    side (nothing to compare, so nothing is claimed)."""
    regressions = []
    for key, tolerance, direction in _REGRESSION_CHECKS:
        b, c = baseline.get(key), current.get(key)
        if b is None or c is None:
            continue
        delta = c - b
        regressed = delta > tolerance if direction == "lower_is_better" else delta < -tolerance
        if regressed:
            regressions.append(key)
    return regressions
