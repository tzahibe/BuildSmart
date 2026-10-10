"""E1 — production vs REAR_PUBLIC_BAND, measured on the eight frozen audit briefs.

Both sides are realized by the UNCHANGED pipeline (`general_pipeline._realize`) and judged by the
UNCHANGED validators. The rear-band candidates are driven explicitly
(`generate_concepts(public_orientation=GARDEN)`) rather than left to the ranking, because E1 is
forbidden from changing production ranking — the experiment must therefore realize its own
candidate and report what it is worth, not hope the area sort picks it.

    PYTHONPATH=backend python -m app.ai_harness.e1_orientation.measure <out.json>
"""
from __future__ import annotations

import json
import sys

from app.ai_harness.topology_poc import briefs as briefs_mod
from app.demo import service as svc
from app.vertical_slice import concept_generator as generator
from app.vertical_slice import general_pipeline as gp
from app.vertical_slice.concept_spec import PublicOrientation
from app.vertical_slice.geometry_core.engine import GeometryInfeasible, solve_fixture
from app.vertical_slice.safe_adapter import adapt

BRIEFS = ("B08", "B20", "B02", "B11", "B16", "B19", "B06", "B09")

PUBLIC = {"LIVING", "DINING", "KITCHEN", "FAMILY_ROOM", "LIVING_KITCHEN", "LDK"}
PRIVATE = {"BEDROOM", "MASTER_BEDROOM", "SAFE_ROOM"}
WET = {"BATHROOM", "TOILET", "GUEST_WC", "LAUNDRY"}
CIRC = {"HALL", "CIRCULATION"}

_EPS = 0.06
#: How many rear-band candidates to realize per brief before giving up. The same bounded shape
#: `concept_engine_v2.CONCEPT_ENGINE_V2_MAX_REALIZATIONS` uses, for the same reason.
_MAX_REALIZATIONS = 8


def _project_for(b):
    from tests.vertical_slice.test_hub_guard import _project
    return _project(dict(bedrooms=b.bedrooms, wet_rooms=b.wet_rooms, safe_room=b.safe_room,
                         open_plan=b.open_plan, built_area_m2=b.built_area_m2,
                         footprint_width_m=b.footprint_width_m,
                         footprint_depth_m=b.footprint_depth_m,
                         plot_width_m=b.footprint_width_m + 8,
                         plot_depth_m=b.footprint_depth_m + 8))


# ------------------------------------------------------------------ architectural measurements

def _frontage(rect, fp, side: str) -> float:
    """Metres of a room's own wall that lie ON the named elevation — zero when it does not reach
    it. A room TOUCHING the garden edge is not the same fact as a room with frontage on it, and
    the owner's instruction is explicit that touching proves nothing on its own."""
    x, y, w, h = rect
    if side == "rear":
        return w if abs((y + h) - (fp.y + fp.depth_m)) < _EPS else 0.0
    if side == "street":
        return w if abs(y - fp.y) < _EPS else 0.0
    return 0.0


def plan_facts(design) -> dict:
    fp = design.footprint
    rows = []
    for r in design.rooms:
        rect = (r.x, r.y, r.gross_width_m, r.gross_depth_m)
        rows.append({
            "id": r.id, "type": r.type, "area_m2": r.area_m2,
            "x": r.x, "y": r.y,
            "gross_width_m": r.gross_width_m, "gross_depth_m": r.gross_depth_m,
            "aspect": round(max(r.width_m, r.depth_m) / max(min(r.width_m, r.depth_m), 1e-9), 2),
            "garden_frontage_m": round(_frontage(rect, fp, "rear"), 2),
            "street_frontage_m": round(_frontage(rect, fp, "street"), 2),
            "exterior_faces": sum([
                abs(r.y - fp.y) < _EPS,
                abs((r.y + r.gross_depth_m) - (fp.y + fp.depth_m)) < _EPS,
                abs(r.x - fp.x) < _EPS,
                abs((r.x + r.gross_width_m) - (fp.x + fp.width_m)) < _EPS]),
            # A room can only take a window where its own wall says so — the engine's own fact,
            # not a geometric guess.
            "windowable_sides": sorted(k for k, v in r.walls.items()
                                       if v.get("can_take_a_window")),
        })

    def group(names):
        return [r for r in rows if r["type"] in names]

    pub, priv, wet, circ = group(PUBLIC), group(PRIVATE), group(WET), group(CIRC)
    entrance = next((d for d in design.doors if d.is_entrance), None)
    windows_by_room: dict[str, int] = {}
    window_sides: dict[str, list[str]] = {}
    for w in design.windows:
        windows_by_room[w.room_id] = windows_by_room.get(w.room_id, 0) + 1
        window_sides.setdefault(w.room_id, []).append(w.side)
    total = sum(r["area_m2"] for r in rows)
    return {
        "rooms": rows,
        "room_count": len(rows),
        "room_ids": sorted(r["id"] for r in rows),
        "footprint": [fp.width_m, fp.depth_m],
        "gross_area_m2": design.gross_area_m2,
        "public_garden_frontage_m": round(sum(r["garden_frontage_m"] for r in pub), 2),
        "wet_garden_frontage_m": round(sum(r["garden_frontage_m"] for r in wet), 2),
        "private_garden_frontage_m": round(sum(r["garden_frontage_m"] for r in priv), 2),
        "public_street_frontage_m": round(sum(r["street_frontage_m"] for r in pub), 2),
        "garden_frontage_total_m": round(sum(r["garden_frontage_m"] for r in rows), 2),
        "public_rooms_on_garden": [r["id"] for r in pub if r["garden_frontage_m"] > 0],
        "wet_rooms_on_garden": [r["id"] for r in wet if r["garden_frontage_m"] > 0],
        # A usable garden connection needs a wall that can actually hold an opening.
        "public_garden_windowable": [r["id"] for r in pub
                                     if r["garden_frontage_m"] > 0 and "S" in r["windowable_sides"]],
        # The entrance door names the OUTSIDE on one end and the arrival room on the other; which
        # end varies, so take whichever is a real zone.
        "entrance_room": next((z for z in ((entrance.a, entrance.b) if entrance else ())
                               if z not in ("ENTRANCE", "OUTSIDE", "")), None),
        "circulation_area_m2": round(sum(r["area_m2"] for r in circ), 2),
        "circulation_share": round(sum(r["area_m2"] for r in circ) / total, 4) if total else None,
        "circulation_aspect": [r["aspect"] for r in circ],
        "windows_per_room": windows_by_room,
        "window_sides": {k: sorted(v) for k, v in window_sides.items()},
        # THE REAL TEST of an indoor/outdoor relationship: a public room with a window ON the
        # garden elevation. Frontage alone is a wall; this is an opening.
        "public_rooms_with_garden_window": sorted(
            r["id"] for r in pub
            if r["garden_frontage_m"] > 0 and "S" in window_sides.get(r["id"], [])),
        "public_garden_window_count": sum(
            1 for r in pub for side in window_sides.get(r["id"], [])
            if side == "S" and r["garden_frontage_m"] > 0),
        "rooms_without_window": sorted(r["id"] for r in rows
                                       if r["type"] in PUBLIC | PRIVATE
                                       and windows_by_room.get(r["id"], 0) == 0),
        "worst_bedroom_aspect": max([r["aspect"] for r in priv], default=None),
    }


def _validation_facts(plan) -> dict:
    report = plan.validation
    failures = [c.check_id for c in report.failures()]
    return {"ok": bool(plan.ok), "checks": len(report.checks),
            "failed": failures,
            "safety_inside": bool(plan.safety.rooms_inside_buildable),
            "safety_clear": bool(plan.safety.rooms_clear_of_exclusions)}


def run_brief(bid: str) -> dict:
    b = {x.brief_id: x for x in briefs_mod.select_briefs()}[bid]
    project = _project_for(b)
    spec = svc.spec_for(project)
    out: dict = {"brief": bid, "bedrooms": b.bedrooms, "wet_rooms": b.wet_rooms,
                 "safe_room": b.safe_room, "open_plan": b.open_plan,
                 "requested_m2": b.built_area_m2}

    # ---- production, through the product's own entry point, untouched
    production = svc.generate_demo_design(project)
    out["production"] = plan_facts(production.design)
    out["production"]["alternatives"] = len(production.alternatives)

    # ---- E1, on the SAME outline the production primary was fit to
    outline = production.design.outline
    o = next((x for x in svc._outlines_for(project)
              if outline is not None and abs(x.width_m - outline.width_m) < 1e-6
              and abs(x.depth_m - outline.depth_m) < 1e-6), None)
    project_e1 = svc._with_outline(project, o) if o is not None else project
    buildable = svc._buildable_from(spec, project_e1, o)
    adapted = adapt(buildable)
    generated = generator.generate_concepts(spec, list(adapted.candidates),
                                            public_orientation=PublicOrientation.GARDEN)
    rear = [(i, c) for i, c in enumerate(generated.candidates)
            if c.strategy is generator.ConceptStrategy.REAR_PUBLIC_BAND]
    out["rear_candidates_generated"] = len(rear)
    out["rear_rejections"] = [f"{r.strategy.value}/{r.reason.value}: {r.detail}"
                              for r in generated.rejections
                              if r.strategy is generator.ConceptStrategy.REAR_PUBLIC_BAND]
    attempts = []
    winner = None
    for index, candidate in rear[:_MAX_REALIZATIONS]:
        try:
            solve = solve_fixture(candidate.concept.fixture)
        except GeometryInfeasible as exc:
            attempts.append({"index": index, "rationale": candidate.rationale,
                             "outcome": f"solver refused: {exc}"})
            continue
        plan = gp._realize(spec, buildable, None, candidate, index, solve, ())
        facts = _validation_facts(plan)
        attempts.append({"index": index, "rationale": candidate.rationale, **facts})
        if plan.ok and winner is None:
            winner = plan
    out["rear_attempts"] = attempts
    if winner is not None:
        from app.demo.contract import to_demo_design
        demo = to_demo_design(winner.design, winner.validation,
                              corridor=spec.program.corridor,
                              relationships=winner.relationships,
                              family=winner.family_signature,
                              constraint=spec.safe_room_constraint)
        out["e1"] = plan_facts(demo)
        out["e1"]["validation"] = _validation_facts(winner)
        out["e1"]["circulation_class"] = getattr(winner.circulation_class, "value", None)
    else:
        out["e1"] = None
    return out


def main(path: str) -> None:
    rows = []
    for bid in BRIEFS:
        try:
            rows.append(run_brief(bid))
            r = rows[-1]
            got = "PASS" if r["e1"] else "no valid rear band"
            print(f"{bid}: {r['rear_candidates_generated']} rear candidates -> {got}", flush=True)
        except Exception as exc:
            rows.append({"brief": bid, "error": f"{type(exc).__name__}: {exc}"})
            print(f"{bid}: {type(exc).__name__}: {exc}", flush=True)
    with open(path, "w") as fh:
        json.dump(rows, fh, indent=2)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "e1.json")
