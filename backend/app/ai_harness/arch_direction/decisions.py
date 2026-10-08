"""What the production pipeline actually DECIDES, measured on the delivered plan (#186).

Three questions the earlier investigations did not answer, each measured on production's own
output through production's own entry point (`app.demo.service.generate_demo_design`):

  Q1  INDOOR/OUTDOOR. The street is the footprint's y = min edge and every other outdoor band is
      garden (`site.classify_garden`). Which rooms face the garden, and which face only the
      street? Nothing in the pipeline optimizes this, so whatever comes out is a by-product.
  Q2  EXPOSURE. How many exterior faces does each room have — the drawing-independent measure of
      whether a room sits in the building's depth or on its edge.
  Q3  OBJECTIVE COMPOSITION. In the generator's own final ordering of its candidates, which
      component of the sort key first separates each adjacent pair. The first component is
      |used_area - target|; the architectural terms sit last.

    PYTHONPATH=backend python -m app.ai_harness.arch_direction.decisions <out.json>
"""
from __future__ import annotations

import json
import sys

from app.ai_harness.topology_poc import briefs as briefs_mod
from app.demo import service as svc
from app.vertical_slice import concept_generator as generator
from app.vertical_slice.safe_adapter import adapt

BRIEFS = ("B08", "B20", "B02", "B11", "B16", "B19", "B06", "B09")

PUBLIC = {"LIVING", "DINING", "KITCHEN", "FAMILY_ROOM", "LIVING_KITCHEN", "LDK"}
PRIVATE = {"BEDROOM", "MASTER_BEDROOM", "SAFE_ROOM"}
CIRC = {"HALL", "CIRCULATION"}
WET = {"BATHROOM", "TOILET", "GUEST_WC", "LAUNDRY"}

_EPS = 0.06            # one grid unit, so a face is "on the envelope" exactly when it coincides


def _project_for(b):
    from tests.vertical_slice.test_hub_guard import _project
    return _project(dict(bedrooms=b.bedrooms, wet_rooms=b.wet_rooms, safe_room=b.safe_room,
                         open_plan=b.open_plan, built_area_m2=b.built_area_m2,
                         footprint_width_m=b.footprint_width_m,
                         footprint_depth_m=b.footprint_depth_m,
                         plot_width_m=b.footprint_width_m + 8,
                         plot_depth_m=b.footprint_depth_m + 8))


def _faces(room, fp) -> dict:
    """Which of the room's four sides lie on the building envelope, named by what is beyond."""
    x, y = room.x, room.y
    x2, y2 = x + room.gross_width_m, y + room.gross_depth_m
    return {
        "street": abs(y - fp.y) < _EPS,                              # y = min is the street
        "rear": abs(y2 - (fp.y + fp.depth_m)) < _EPS,                # the garden side
        "side_w": abs(x - fp.x) < _EPS,
        "side_e": abs(x2 - (fp.x + fp.width_m)) < _EPS,
    }


def plan_facts(design) -> dict:
    fp = design.footprint
    rows = []
    for r in design.rooms:
        f = _faces(r, fp)
        rows.append({
            "id": r.id, "type": r.type, "area_m2": r.area_m2,
            "x": r.x, "y": r.y,
            "gross_width_m": r.gross_width_m, "gross_depth_m": r.gross_depth_m,
            "aspect": round(max(r.width_m, r.depth_m) / max(min(r.width_m, r.depth_m), 1e-9), 2),
            "exterior_faces": sum(1 for v in f.values() if v),
            **f,
        })

    def group(names):
        return [r for r in rows if r["type"] in names]

    pub, priv, circ, wet = group(PUBLIC), group(PRIVATE), group(CIRC), group(WET)
    door_degree: dict[str, int] = {}
    for d in design.doors:
        for side in (d.a, d.b):
            if side:
                door_degree[side] = door_degree.get(side, 0) + 1
    circ_area = sum(r["area_m2"] for r in circ)
    total = sum(r["area_m2"] for r in rows)
    return {
        "rooms": rows,
        "room_count": len(rows),
        "footprint": [fp.width_m, fp.depth_m],
        "footprint_aspect": round(max(fp.width_m, fp.depth_m) / min(fp.width_m, fp.depth_m), 2),
        "gross_area_m2": design.gross_area_m2,
        # Q1
        "public_rooms": [r["id"] for r in pub],
        "public_facing_rear": [r["id"] for r in pub if r["rear"]],
        "public_street_only": [r["id"] for r in pub if r["street"] and not r["rear"]],
        "private_facing_rear": [r["id"] for r in priv if r["rear"]],
        "wet_on_envelope": [r["id"] for r in wet if r["exterior_faces"] > 0],
        "wet_facing_rear": [r["id"] for r in wet if r["rear"]],
        # Q2
        "rooms_one_exterior_face": [r["id"] for r in rows if r["exterior_faces"] == 1],
        "rooms_two_plus_faces": [r["id"] for r in rows if r["exterior_faces"] >= 2],
        "rooms_landlocked": [r["id"] for r in rows if r["exterior_faces"] == 0],
        "mean_exterior_faces": round(sum(r["exterior_faces"] for r in rows) / max(len(rows), 1), 2),
        # circulation
        "circulation_area_m2": round(circ_area, 2),
        "circulation_share": round(circ_area / total, 4) if total else None,
        "circulation_aspect": [r["aspect"] for r in circ],
        "door_degree": door_degree,
        "flex_area_m2": round(sum(r["area_m2"] for r in rows if r["type"] == "FLEX"), 2),
        "unassigned_present": any(r["type"] == "FLEX" for r in rows),
    }


def _sort_key_components(c, target):
    """The generator's own key, component by component (concept_generator.generate_concepts)."""
    return [
        ("area_delta", round(abs(c.used_area_m2 - target), 4)),
        ("fallback_tier", int(bool(c.over_preferred or c.shrunk))),
        ("over_preferred", int(bool(c.over_preferred))),
        ("used_area", round(c.used_area_m2, 4)),
        ("strategy", c.strategy.value),
    ]


def objective_composition(spec, project) -> dict:
    """Which key component first separates each adjacent pair in the delivered ordering."""
    buildable = svc._buildable_from(spec, project, None)
    generated = generator.generate_concepts(spec, list(adapt(buildable).candidates))
    target = spec.program.target_built_area_m2
    cands = [c for c in generated.candidates if not c.repartitioned]
    first: dict[str, int] = {}
    for a, b in zip(cands, cands[1:]):
        ka, kb = _sort_key_components(a, target), _sort_key_components(b, target)
        name = "none (tied on every component)"
        for (n, va), (_, vb) in zip(ka, kb):
            if va != vb:
                name = n
                break
        first[name] = first.get(name, 0) + 1
    return {"candidates_total": len(generated.candidates),
            "candidates_ranked": len(cands),
            "first_separating_component": first,
            "distinct_used_area_values": len({round(c.used_area_m2, 2) for c in cands}),
            "distinct_strategies": sorted({c.strategy.value for c in cands})}


def run_brief(bid: str) -> dict:
    b = {x.brief_id: x for x in briefs_mod.select_briefs()}[bid]
    project = _project_for(b)
    spec = svc.spec_for(project)
    out = {"brief": bid, "bedrooms": b.bedrooms, "wet_rooms": b.wet_rooms,
           "safe_room": b.safe_room, "open_plan": b.open_plan,
           "requested_m2": b.built_area_m2,
           "objective": objective_composition(spec, project)}
    result = svc.generate_demo_design(project)
    out["plan"] = plan_facts(result.design)
    out["alternatives"] = len(result.alternatives)
    out["alternative_plans"] = [plan_facts(d) for d in result.alternatives]
    return out


def main(path: str) -> None:
    data = []
    for bid in BRIEFS:
        try:
            data.append(run_brief(bid))
            print(f"{bid}: ok", flush=True)
        except Exception as exc:                                   # a refusal is a measurement
            data.append({"brief": bid, "error": f"{type(exc).__name__}: {exc}"})
            print(f"{bid}: {type(exc).__name__}: {exc}", flush=True)
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "arch_direction.json")
