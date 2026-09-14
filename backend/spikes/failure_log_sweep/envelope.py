"""The demo envelope, measured: which (bedrooms, wet rooms, safe room, footprint) cells the engine
plans through the real service, and whether every plan passes C17.

    .venv/bin/python3 spikes/failure_log_sweep/envelope.py            # prints, writes ENVELOPE.md

The 216-cell grid of docs/WET_ROOM_SEMANTICS_PROPOSAL.md §8: bedrooms 1-6 x wet rooms 1-3 x safe
room x six log-typical footprints, target area = footprint area, open plan, no parking, a parcel
that holds the footprint with the default setbacks. Every cell is inside `scope.check_supported`,
so the engine, not the guard, is what gets measured. The numbers in `app/demo/scope.py` are
rewritten from this file's output (spec 007, decision D) — never from memory.
"""
from __future__ import annotations

import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.demo import service as svc  # noqa: E402
from app.demo import site_geometry  # noqa: E402
from spikes.failure_log_sweep.sweep import project_from_context  # noqa: E402

BEDROOMS = (1, 2, 3, 4, 5, 6)
WET_ROOMS = (1, 2, 3)
SAFE = (False, True)
FOOTPRINTS = ((11.0, 12.0), (12.5, 14.5), (12.0, 18.0), (14.0, 16.0), (18.0, 12.0), (16.0, 18.0))
OUT = Path(__file__).with_name("ENVELOPE.md")


def context(bedrooms: int, wet: int, safe: bool, fw: float, fd: float) -> dict:
    return dict(
        plot_width_m=fw + 2 * site_geometry.SIDE_SETBACK_M + 2.0,
        plot_depth_m=fd + site_geometry.FRONT_SETBACK_M + site_geometry.REAR_SETBACK_M + 2.0,
        street_facing_side="NORTH", built_area_m2=round(fw * fd, 2),
        footprint_width_m=fw, footprint_depth_m=fd,
        bedrooms=bedrooms, wet_rooms=wet, safe_room=safe, open_plan=True,
    )


def run_cell(ctx: dict) -> dict:
    t = time.perf_counter()
    try:
        res = svc.generate_demo_design(project_from_context(ctx))
        checks = res.design.validation.checks
        rec = dict(status="PLANNED", area=res.design.gross_area_m2,
                   c17=checks.get("C17"), passed=res.design.validation.passed)
    except svc.DemoGenerationError as exc:
        rec = dict(status="REFUSED", code=exc.code)
    except Exception as exc:  # noqa: BLE001
        rec = dict(status="CRASH", code=f"{type(exc).__name__}: {exc}")
    rec["seconds"] = time.perf_counter() - t
    return rec


def main() -> None:
    cells: dict[tuple, dict] = {}
    started = time.perf_counter()
    for b in BEDROOMS:
        for w in WET_ROOMS:
            for s in SAFE:
                for fw, fd in FOOTPRINTS:
                    cells[(b, w, s, fw, fd)] = run_cell(context(b, w, s, fw, fd))
        print(f"  {b}BR done ({time.perf_counter() - started:.0f}s)", file=sys.stderr)

    lines = [f"# Demo envelope — measured {date.today().isoformat()}", "",
             f"{len(cells)} cells: bedrooms {BEDROOMS[0]}-{BEDROOMS[-1]} x wet rooms "
             f"{WET_ROOMS[0]}-{WET_ROOMS[-1]} x safe room x footprints "
             + ", ".join(f"{fw:g}x{fd:g}" for fw, fd in FOOTPRINTS)
             + " m (target area = footprint area, open plan, no parking, default setbacks), "
             "through `generate_demo_design`. Produced by `envelope.py`; the numbers in "
             "`app/demo/scope.py` are copied from here.", ""]

    planned = [k for k, r in cells.items() if r["status"] == "PLANNED"]
    c17_fail = [k for k in planned if cells[k]["c17"] is not True]
    crashes = [k for k, r in cells.items() if r["status"] == "CRASH"]
    lines += [f"planned {len(planned)}/{len(cells)}; C17 failures among plans: {len(c17_fail)}; "
              f"crashes: {len(crashes)}; total {time.perf_counter() - started:.0f}s", ""]

    per_cells = len(WET_ROOMS) * len(SAFE) * len(FOOTPRINTS)
    lines += ["## By bedrooms", "", f"| bedrooms | planned / {per_cells} | share |", "|---|---|---|"]
    for b in BEDROOMS:
        n = sum(1 for k in planned if k[0] == b)
        lines.append(f"| {b} | {n} | {100 * n / per_cells:.0f} % |")

    lines += ["", "## By bedrooms x wet rooms (of 12 cells each)", "",
              "| bedrooms | " + " | ".join(f"wet {w}" for w in WET_ROOMS) + " |",
              "|---|" + "---|" * len(WET_ROOMS)]
    for b in BEDROOMS:
        lines.append(f"| {b} | " + " | ".join(
            str(sum(1 for k in planned if k[0] == b and k[1] == w)) for w in WET_ROOMS) + " |")

    lines += ["", "## Smallest planning footprint of the six, by programme", "",
              "`—` = none of the six footprints plans it.", "",
              "| bedrooms | wet | no safe room | safe room |", "|---|---|---|---|"]
    smallest: dict[tuple, tuple | None] = {}
    for b in BEDROOMS:
        for w in WET_ROOMS:
            row = []
            for s in SAFE:
                fits = sorted((fw * fd, fw, fd) for (bb, ww, ss, fw, fd) in planned
                              if (bb, ww, ss) == (b, w, s))
                smallest[(b, w, s)] = fits[0] if fits else None
                row.append(f"{fits[0][1]:g}x{fits[0][2]:g} ({fits[0][0]:.0f} m²)" if fits else "—")
            lines.append(f"| {b} | {w} | {row[0]} | {row[1]} |")

    lines += ["", "## Every cell", "", "| bedrooms | wet | safe | footprint | result | gross m² | C17 | s |",
              "|---|---|---|---|---|---|---|---|"]
    for (b, w, s, fw, fd), r in cells.items():
        if r["status"] == "PLANNED":
            result, area, c17 = "planned", f"{r['area']:.1f}", "pass" if r["c17"] else "FAIL"
        else:
            result, area, c17 = r["code"], "", ""
        lines.append(f"| {b} | {w} | {'Y' if s else 'N'} | {fw:g}x{fd:g} | {result} | {area} | {c17} "
                     f"| {r['seconds']:.1f} |")

    refusals: dict[str, int] = defaultdict(int)
    for r in cells.values():
        if r["status"] != "PLANNED":
            refusals[r["code"]] += 1
    lines += ["", "## Refusal codes", ""] + [f"- {code}: {n}" for code, n in sorted(refusals.items())]

    text = "\n".join(lines) + "\n"
    OUT.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
