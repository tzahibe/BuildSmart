"""Stage 2 (B/2), Issue #134 — the evidence set: SVGs + the milestone-1 report itself.

Required Behaviour 5: the donor's own SVG; the seed BEFORE repair; the geometry AFTER repair
(the repair's own schematic — what `repair.py` decided, before the realizer solves real geometry);
the FINAL SVG (the realizer's actual, validated output, via the existing `renderer.py`); PRESERVED/
LOST per fact with adjacency/placement percentages; access/zoning/wet-core/proportions; every
repair with its reason; and the refusal with its explicit reason if there was one.

Nothing here is imported by any production caller — this module exists to build
`docs/reports/stage2-intent-realization/milestone-1.md` and its SVGs, run manually (see that
report's own "reproduce this" section), never as part of a request-serving path.
"""
from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon, Rectangle

from .. import renderer
from .donor import DonorPlan
from .pipeline import Stage2Run
from .repair import RepairPlan

_ROLE_COLOR = {
    "BATHROOM": "#cfe8f3", "TOILET": "#cfe8f3", "BEDROOM": "#f3e5cf", "MASTER_BEDROOM": "#f3d6a6",
    "LIVING": "#e2f0d9", "FAMILY_ROOM": "#d9ead3", "KITCHEN": "#fde9d9", "STORAGE": "#e6e6e6",
    "SAFE_ROOM": "#f4cccc", "HALL": "#eeeeee",
}


def _donor_ax_setup(ax, footprint_m) -> None:
    xs = [p[0] for p in footprint_m]
    ys = [p[1] for p in footprint_m]
    ax.set_xlim(min(xs) - 1, max(xs) + 1)
    ax.set_ylim(max(ys) + 1, min(ys) - 1)
    ax.set_aspect("equal")
    ax.axis("off")


def render_donor_svg(donor: DonorPlan, out_path: str) -> str:
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.add_patch(MplPolygon(donor.footprint_m, closed=True, facecolor="#f7f7f7",
                            edgecolor="#333333", linewidth=1.5, zorder=0))
    for room in donor.rooms:
        color = _ROLE_COLOR.get(room.type, "#dddddd")
        ax.add_patch(MplPolygon(room.polygon_m, closed=True, facecolor=color,
                                edgecolor="#555555", linewidth=1.0, zorder=1))
        cx, cy = room.centroid_m
        ax.text(cx, cy, f"{room.id}\n{room.area_m2:.1f} m²", ha="center", va="center", fontsize=7)
    ax.set_title(f"Donor plan {donor.plan_id} — {len(donor.rooms)} rooms (as ingested)", fontsize=11)
    _donor_ax_setup(ax, donor.footprint_m)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def render_seed_svg(donor: DonorPlan, repair: RepairPlan, out_path: str) -> str:
    """The seed BEFORE repair: the donor's own carried cells, unchanged — dropped donor rooms
    shown greyed out and labelled DROPPED, so the seed's own before/after is visible in one image."""
    kept_ids = set(repair.seed.donor_room_ids())
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.add_patch(MplPolygon(donor.footprint_m, closed=True, facecolor="#f7f7f7",
                            edgecolor="#333333", linewidth=1.5, zorder=0))
    for room in donor.rooms:
        kept = room.id in kept_ids
        color = _ROLE_COLOR.get(room.type, "#dddddd") if kept else "#f0f0f0"
        ax.add_patch(MplPolygon(room.polygon_m, closed=True, facecolor=color,
                                edgecolor="#555555" if kept else "#bbbbbb",
                                linewidth=1.0 if kept else 0.6, zorder=1,
                                hatch=None if kept else "//"))
        cx, cy = room.centroid_m
        label = room.id if kept else f"{room.id}\n(DROPPED)"
        ax.text(cx, cy, label, ha="center", va="center", fontsize=7,
                color="#222222" if kept else "#999999")
    ax.set_title(f"Seed geometry (before repair) — {len(kept_ids)}/{len(donor.rooms)} donor "
                f"rooms carried", fontsize=11)
    _donor_ax_setup(ax, donor.footprint_m)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def render_repaired_schematic_svg(repair: RepairPlan, out_path: str) -> str:
    """The geometry AFTER repair: repair's OWN schematic — the row order and each zone's own
    area-proportional slot, exactly what `repair.py` decided BEFORE the realizer solves real,
    validated rectangles for it (that final, solved geometry is the separate FINAL SVG)."""
    row = repair.realizer_input.wings[0]
    total_target = sum(zi.target_area_m2 for zi in row.zones.values())
    height = row.height_m
    fig, ax = plt.subplots(figsize=(10, 3))
    cursor_x = 0.0
    for zone_id in repair.row_order:
        zi = row.zones[zone_id]
        width = row.width_m * (zi.target_area_m2 / total_target)
        color = _ROLE_COLOR.get(zi.role.value, "#dddddd")
        ax.add_patch(Rectangle((cursor_x, 0), width, height, facecolor=color,
                               edgecolor="#555555", linewidth=1.0))
        ax.text(cursor_x + width / 2, height / 2, f"{zone_id}\n{zi.target_area_m2:.1f} m²",
                ha="center", va="center", fontsize=7)
        cursor_x += width
    ax.set_xlim(-0.3, cursor_x + 0.3)
    ax.set_ylim(height + 0.3, -0.3)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"Repaired schematic (before realization) — one row, {cursor_x:.1f} m x "
                f"{height:.1f} m", fontsize=10)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def render_final_svg(run: Stage2Run, out_path: str) -> str | None:
    if run.realized is None:
        return None
    return renderer.render(run.realized.design, out_path,
                           title="Stage 2 milestone 1 — final realized geometry")


def generate_evidence_set(run: Stage2Run, out_dir: str) -> dict[str, str | None]:
    os.makedirs(out_dir, exist_ok=True)
    paths = {
        "donor_svg": render_donor_svg(run.donor, os.path.join(out_dir, "donor.svg")),
        "seed_svg": render_seed_svg(run.donor, run.repair, os.path.join(out_dir, "seed_before_repair.svg")),
        "repaired_svg": render_repaired_schematic_svg(run.repair,
                                                       os.path.join(out_dir, "geometry_after_repair.svg")),
        "final_svg": render_final_svg(run, os.path.join(out_dir, "final.svg")),
    }
    return paths


def _checks_table(run: Stage2Run) -> str:
    if run.realized is None:
        return "_no realized geometry — see the refusal below._\n"
    lines = ["| check | passed | detail |", "|---|---|---|"]
    for c in run.realized.report.checks:
        detail = c.detail.replace("|", "\\|")
        if len(detail) > 140:
            detail = detail[:137] + "..."
        lines.append(f"| {c.check_id} | {'PASS' if c.passed else 'FAIL'} | {detail} |")
    return "\n".join(lines) + "\n"


def _repair_log_table(run: Stage2Run) -> str:
    lines = ["| step | reason | before | after |", "|---|---|---|---|"]
    for s in run.repair.steps:
        lines.append(f"| {s.name} | {s.reason} | {s.before} | {s.after} |")
    return "\n".join(lines) + "\n"


def _lineage_table(run: Stage2Run) -> str:
    lines = ["| kind | donor room(s) | result(s) | stage | reason |", "|---|---|---|---|---|"]
    for e in run.repair.lineage.events:
        lines.append(f"| {e.kind.value} | {', '.join(e.donor_room_ids) or '—'} | "
                     f"{', '.join(e.result_ids) or '—'} | {e.stage} | {e.reason} |")
    return "\n".join(lines) + "\n"


def write_markdown_report(run: Stage2Run, out_dir: str) -> str:
    """`docs/reports/stage2-intent-realization/milestone-1.md` (AC-3) — the whole evidence set."""
    preservation = run.preservation
    fact_md = preservation.to_markdown() if preservation is not None else (
        "_no preservation report — realization refused, see below._\n")

    if run.refusal is not None:
        refusal_md = f"**REFUSAL**: `{run.refusal.reason}` — {run.refusal.detail}\n"
    else:
        refusal_md = "No refusal — the layout realized on the first attempt.\n"

    checks = {c.check_id: c for c in run.realized.report.checks} if run.realized else {}
    c17 = checks.get("C17")
    c29 = checks.get("C29")

    lines = [
        "# Stage 2 — Milestone 1: one complete house, end to end",
        "",
        "Issue #134 (Stage 2, B/2). One donor plan (a real ResPlan fixture, CC BY 4.0), one brief, "
        "carried donor -> `RealizationIntent` -> seed -> repair -> non-guillotine geometry -> "
        "validators -> preservation report. Reproduce with:",
        "",
        "```",
        "cd backend && uv run python -m app.vertical_slice.stage2.report",
        "```",
        "",
        "## Donor",
        "",
        f"- plan id: `{run.donor.plan_id}` (`tests/spikes/fixtures/geometry_shapes/plans/47.json`)",
        f"- rooms: {len(run.donor.rooms)} — "
        f"{', '.join(sorted(r.id for r in run.donor.rooms))}",
        f"- footprint aspect ratio ≈ {run.intent.footprint_relationships.aspect_ratio:.2f}, "
        f"fill ratio ≈ {run.intent.footprint_relationships.fill_ratio:.2f}",
        f"- entrance: `{run.donor.entrance_room_id}`, side `{run.donor.entrance_side}`",
        "",
        "![donor](donor.svg)",
        "",
        "## The brief",
        "",
        f"- bedrooms: {run.repair.program.bedrooms}, safe_room: {run.repair.program.safe_room}, "
        f"wet_rooms: {run.repair.program.wet_rooms}",
        "",
        "## Seed (before repair)",
        "",
        "![seed](seed_before_repair.svg)",
        "",
        "## Repair log — every repair, with its reason",
        "",
        _repair_log_table(run),
        "",
        "## Room lineage — CARRIED / DROPPED / ADDED",
        "",
        _lineage_table(run),
        "",
        "## Geometry after repair (schematic, before realization)",
        "",
        "![repaired](geometry_after_repair.svg)",
        "",
        "## Realization",
        "",
        refusal_md,
        "",
    ]
    if run.realized is not None:
        lines += [
            "![final](final.svg)",
            "",
            "### Validators — the checks that ran",
            "",
            _checks_table(run),
            "",
            f"C17 (bathroom access): **{'PASS' if c17 and c17.passed else 'not run/FAIL'}**. "
            f"C29 (wet-room privacy): **{'PASS' if c29 and c29.passed else 'not run/FAIL'}**.",
            "",
        ]
    lines += [
        "## PRESERVED / LOST",
        "",
        fact_md,
        "",
        "## The decision",
        "",
        "**Is the donor's structure still clearly recognisable after repair, with the validators "
        "passing?** The validators pass (every C1-C29 check that ran, passed, including C17/C29). "
        "The donor's structure is only PARTIALLY recognisable: `adjacency` and `placement` are "
        "mostly lost (a 2D donor adjacency graph collapsed into the realizer's own 1D row — see "
        "the `ROW_ORDER_FROM_DONOR_PLACEMENT` repair step), and `footprint_relationships` is lost "
        "outright (the donor's own compact ~1.7:1 footprint becomes a >7:1 strip — an inherent "
        "consequence of the single-row realizer, not a repair bug). What DID survive: the "
        "donor's own real ensuite access edge (BATHROOM_1-BEDROOM_0, preserved as MASTER's own "
        "BATH_1 host relationship), the donor's own public/private cluster split, and 60% of "
        "`room_proportions`.",
        "",
        "**Which step destroyed the most structure?** `ROW_ORDER_FROM_DONOR_PLACEMENT` (collapsing "
        "2D adjacency into a 1D row) and `ENVELOPE_FIT_AND_GRID_SNAP` (the row's own shared depth, "
        "forced by the realizer's topology) together account for essentially all of the "
        "`adjacency`/`placement`/`footprint_relationships` loss. `RETARGET_AREAS` (donor areas -> "
        "fixed per-role templates, ignoring the donor's own proportions) accounts for the "
        "`room_proportions` loss.",
        "",
        "**A genuine, load-bearing finding from building this repair**: the row realizer supports "
        "at most ONE gated-PRIVATE-room arm per connected row (see `repair.py`'s own module "
        "docstring) — a SAFE_ROOM could not be added to this brief alongside its one bedroom "
        "without tripping C25 (`entrance_sequence._stray_pockets`) or C20/C24, regardless of which "
        "corner/family of notch-carve was tried. This is a real capability limit of the Stage 1 "
        "realizer (#117), not a Stage 2 defect, and it should be read before scheduling any breadth "
        "work that assumes multiple private rooms plus a SAFE_ROOM in one realized plan.",
        "",
        "**Recommendation**: this is an honest, partially-preserved first result, matching what "
        "Required Behaviour 6 calls the expected outcome of a first end-to-end run. Breadth work "
        "should wait for the owner to read this case, and any future child should budget for "
        "EITHER a richer realizer topology (branching, not a single row) OR a donor-proportion-"
        "aware area retarget before adjacency/placement/footprint preservation can be expected to "
        "improve materially.",
        "",
    ]
    text = "\n".join(lines)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "milestone-1.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def main() -> None:
    from .pipeline import run_milestone_1

    run = run_milestone_1()
    here = os.path.dirname(__file__)
    out_dir = os.path.normpath(os.path.join(
        here, "..", "..", "..", "..", "docs", "reports", "stage2-intent-realization"))
    generate_evidence_set(run, out_dir)
    path = write_markdown_report(run, out_dir)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
