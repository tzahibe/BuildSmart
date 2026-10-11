"""Production vs the architectural brain, on the same briefs, measured not asserted (#197).

Quality is reported as a PROFILE, never a single score — a weighted total would let a win on one
axis hide a loss on another, which is exactly what #142N showed goes wrong. Every number here is
read off the realized geometry the validators already accepted.

    PYTHONPATH=backend python -m app.ai_harness.brain_eval.compare <out.json>
"""
from __future__ import annotations

import json
import sys
import time

from app.ai_harness.topology_poc import briefs as briefs_mod
from app.demo import service as svc

BRIEFS = ("B08", "B20", "B02", "B11", "B16", "B19", "B06", "B09")
PUBLIC = {"LIVING", "DINING", "KITCHEN", "FAMILY_ROOM", "LIVING_KITCHEN", "LDK"}
PRIVATE = {"BEDROOM", "MASTER_BEDROOM", "SAFE_ROOM"}
WET = {"BATHROOM", "TOILET", "GUEST_WC", "LAUNDRY"}
CIRC = {"HALL", "CIRCULATION"}
_EPS = 0.06


def _project_for(b):
    from tests.vertical_slice.test_hub_guard import _project
    return _project(dict(bedrooms=b.bedrooms, wet_rooms=b.wet_rooms, safe_room=b.safe_room,
                         open_plan=b.open_plan, built_area_m2=b.built_area_m2,
                         footprint_width_m=b.footprint_width_m,
                         footprint_depth_m=b.footprint_depth_m,
                         plot_width_m=b.footprint_width_m + 8,
                         plot_depth_m=b.footprint_depth_m + 8))


def profile(design, requested_m2: float) -> dict:
    """The architectural profile of one delivered plan."""
    fp = design.footprint
    south = fp.y + fp.depth_m
    rooms = []
    for r in design.rooms:
        rooms.append({
            "id": r.id, "type": r.type, "area": r.area_m2,
            "aspect": round(max(r.width_m, r.depth_m) / max(min(r.width_m, r.depth_m), 1e-9), 2),
            "on_garden": abs((r.y + r.gross_depth_m) - south) < _EPS,
            "on_street": abs(r.y - fp.y) < _EPS,
            "faces": sum([abs(r.y - fp.y) < _EPS,
                          abs((r.y + r.gross_depth_m) - south) < _EPS,
                          abs(r.x - fp.x) < _EPS,
                          abs((r.x + r.gross_width_m) - (fp.x + fp.width_m)) < _EPS]),
        })
    pub = [r for r in rooms if r["type"] in PUBLIC]
    wet = [r for r in rooms if r["type"] in WET]
    priv = [r for r in rooms if r["type"] in PRIVATE]
    circ = [r for r in rooms if r["type"] in CIRC]
    total = sum(r["area"] for r in rooms) or 1.0
    entrance = next((d for d in design.doors if d.is_entrance), None)
    arrival = next((z for z in ((entrance.a, entrance.b) if entrance else ())
                    if z not in ("ENTRANCE", "OUTSIDE", "")), None)
    arrival_type = next((r["type"] for r in rooms if r["id"] == arrival), None)
    windows = {}
    for w in design.windows:
        windows.setdefault(w.room_id, []).append(w.side)
    return {
        "rooms": len(rooms),
        "gross_m2": design.gross_area_m2,
        "area_fidelity_pct": round(100 * design.gross_area_m2 / requested_m2, 1),
        "public_on_garden": [r["id"] for r in pub if r["on_garden"]],
        "wet_on_garden": [r["id"] for r in wet if r["on_garden"]],
        "public_with_garden_window": sorted(
            r["id"] for r in pub if r["on_garden"] and "S" in windows.get(r["id"], [])),
        "circulation_share": round(sum(r["area"] for r in circ) / total, 4),
        "circulation_aspect": [r["aspect"] for r in circ],
        "worst_bedroom_aspect": max([r["aspect"] for r in priv], default=None),
        "rooms_no_window": sorted(r["id"] for r in rooms
                                  if r["type"] in PUBLIC | PRIVATE and not windows.get(r["id"])),
        "mean_faces": round(sum(r["faces"] for r in rooms) / max(len(rooms), 1), 2),
        "arrival": arrival_type,
        "validators": len(design.validation.checks) if hasattr(design.validation, "checks") else None,
    }


def run_brief(bid: str) -> dict:
    b = {x.brief_id: x for x in briefs_mod.select_briefs()}[bid]
    project = _project_for(b)
    out = {"brief": bid, "bedrooms": b.bedrooms, "wet_rooms": b.wet_rooms,
           "safe_room": b.safe_room, "requested_m2": b.built_area_m2}

    t0 = time.monotonic()
    prod = svc.generate_demo_design(project)
    out["production"] = {**profile(prod.design, b.built_area_m2),
                         "alternatives": len(prod.alternatives),
                         "seconds": round(time.monotonic() - t0, 2), "cost_usd": 0.0}

    t0 = time.monotonic()
    try:
        br = svc.generate_demo_design(project, brain=True)
        out["brain"] = {**profile(br.design, b.built_area_m2),
                        "alternatives": len(br.alternatives),
                        "partis": [br.design.family] + [a.family for a in br.alternatives],
                        "seconds": round(time.monotonic() - t0, 2), "cost_usd": 0.0}
        out["brain_alternatives"] = [profile(a, b.built_area_m2) for a in br.alternatives]
    except svc.DemoGenerationError as exc:
        out["brain"] = {"refused": exc.code, "detail": exc.detail[:200],
                        "seconds": round(time.monotonic() - t0, 2)}
    return out


def main(path: str) -> None:
    rows = []
    for bid in BRIEFS:
        rows.append(run_brief(bid))
        r = rows[-1]
        br = r.get("brain", {})
        print(f"{bid}: prod {r['production']['gross_m2']:.0f}m2 alts={r['production']['alternatives']} | "
              f"brain {br.get('gross_m2', '-')} alts={br.get('alternatives', '-')} "
              f"{br.get('refused', '')}", flush=True)
    with open(path, "w") as fh:
        json.dump(rows, fh, indent=2)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "brain_compare.json")
