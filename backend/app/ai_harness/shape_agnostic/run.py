"""Gate 2 harness — the six frozen cases through ONE code path (ADR-001 §5, #197).

    PYTHONPATH=backend python -m app.ai_harness.shape_agnostic.run <out_dir> [case_id ...]

Per case, the same sequence with no per-case branch anywhere:

    brief + envelope  ->  programme (the brain's own `programme_from_spec`, Stage 3 banding)
                      ->  partis (the brain's own `DeterministicProposer`)
                      ->  representation pre-check (K4 / triple-lens: refused before any geometry)
                      ->  `embed_band` (UNCHANGED; which rooms share a band, in what order)
                      ->  `solve_staircase_layout` inside the envelope polygon (formulation A)
                      ->  `realize_cells` (walls, doors, entrance, windows, UNCHANGED validators)
                      ->  `topology_preservation` + the Stage 3 area verdict

Everything is recorded: status per stage, runtime, the typed refusal when there is one, and a
DemoDesign JSON for every realized plan so the product's own `DemoPlan` draws it. Failures are
reported as what they are; nothing is retried with a relaxed constraint.
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter

from app.demo.contract import to_demo_design
from app.demo.service import spec_for
from app.vertical_slice.band_embedding import (BandEmbedding, BandEmbeddingRefusal, embed_band,
                                               find_k4, find_triple_lens)
from app.vertical_slice.band_pipeline import hard_rejections, orient, placement_flags
from app.vertical_slice.band_sizing import contact_requirements
from app.vertical_slice.brain.area import assess_area
from app.vertical_slice.brain.proposer import DeterministicProposer, _hall_intent, programme_from_spec
from app.vertical_slice.brain.runner import AREA_BAND_LADDER, _arrival_zone, _rebanded
from app.vertical_slice.envelope import Envelope
from app.vertical_slice.rectilinear_realizer import RealizedLayout, realize_cells
from app.vertical_slice.staircase_sizing import solve_staircase_layout
from app.vertical_slice.topology_preservation import measure_access_graph, measure_spatial_adjacency

CASES_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "docs", "reports",
                          "shape-agnostic-realizer", "cases", "frozen-six.json")
MAX_CANDIDATES = 150         # embedder candidates examined per parti; the selection + oracle screens are cheap
MAX_SIZINGS = 12             # candidates actually sized per parti (both orientations count)

try:                         # the MILP oracle (formulation B) where scipy exists — research tooling:
    from app.ai_harness.shape_agnostic.milp_oracle import milp_heights, milp_placement
except ImportError:          # pragma: no cover
    milp_heights = milp_placement = None


def _project_for(case: dict):
    from tests.vertical_slice.test_hub_guard import _project
    env = Envelope(tuple(tuple(v) for v in case["envelope"]))
    bw, bd = env.width_u * 0.05, env.depth_u * 0.05
    prog = case["programme"]
    return _project(dict(bedrooms=prog["bedrooms"], wet_rooms=prog["wet_rooms"],
                         safe_room=prog["safe_room"], open_plan=prog.get("open_plan", False),
                         built_area_m2=case["footprint"]["gross_m2"],
                         footprint_width_m=round(bw, 2), footprint_depth_m=round(bd, 2),
                         plot_width_m=round(bw + 8, 2), plot_depth_m=round(bd + 8, 2))), env


def _adjacency(pairs) -> dict[str, set[str]]:
    adj: dict[str, set[str]] = {}
    for a, b in pairs:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    return adj


def _extra(case: dict, kind: str, zones: dict) -> list[tuple[str, str]]:
    """The case's own extra contacts/doors, by ROLE name, mapped onto this programme's zone ids —
    the first zone of each role. Written in the frozen spec before any code; a role the programme
    does not carry is reported, never silently dropped."""
    by_role: dict[str, str] = {}
    for zid, zi in zones.items():
        by_role.setdefault(zi.role.name, zid)
    out = []
    for a, b in case.get(kind, []):
        if a not in by_role or b not in by_role:
            raise InvalidCase(f"{kind} names a role this programme does not carry: {a}-{b} "
                              f"(programme roles: {sorted(by_role)})")
        out.append((by_role[a], by_role[b]))
    return out


class InvalidCase(Exception):
    """The frozen spec asks for something the brief's own programme cannot express. Reported as
    such — never silently dropped, which is how a K4 once collapsed into a triangle and 'solved'."""


def _transposed_envelope(env: Envelope) -> Envelope:
    return Envelope(tuple((y, x) for x, y in env.vertices_m))


def _transpose_rects(rects: dict) -> dict:
    from app.vertical_slice.geometry_core.model import Rect
    return {z: Rect(r.y, r.x, r.h, r.w) for z, r in rects.items()}


def run_case(case: dict, out_dir: str) -> dict:
    t0 = time.monotonic()
    rec: dict = {"id": case["id"], "expected": case["expected"], "stages": Counter(), "plans": [],
                 "refusals": []}
    project, env = _project_for(case)
    spec = spec_for(project)
    # The programme is scaled to the floor that EXISTS — the envelope polygon's area — not to its
    # bounding box: on F2 the box is 224 m² and the L is 182 m², and rooms scaled to the box can
    # never fit the L. `programme_from_spec` takes a rectangle, so pass the equivalent one.
    W = env.width_u * 0.05
    p = programme_from_spec(spec, (W, env.area_m2 / W))
    requested = case["footprint"]["gross_m2"]
    proposals = DeterministicProposer().propose(p)
    rec["partis"] = [x.name for x in proposals]
    os.makedirs(os.path.join(out_dir, "designs"), exist_ok=True)
    # the same algorithm in both orientations: bands along the street, and bands across it (the
    # envelope transposed, the result transposed back). Neither names a shape.
    orientations = (("H", env), ("V", _transposed_envelope(env)))

    for prop in proposals:
        zones = {z: p.zones[z] for z in prop.rooms if z in p.zones}
        for z in prop.rooms:
            if z not in zones:
                zones[z] = _hall_intent(z, target=7.0)
        try:
            spatial = list(prop.spatial) + _extra(case, "contacts_extra", zones)
            access = [(a, b) for a, b in prop.access if a != "ENTRANCE"] + _extra(case, "access_extra", zones)
        except InvalidCase as exc:
            rec["stages"]["INVALID_CASE"] += 1
            rec["refusals"].append({"parti": prop.name, "stage": "CASE", "code": "INVALID_CASE",
                                    "detail": str(exc)[:200]})
            continue
        union = sorted({tuple(sorted(e)) for e in spatial} | {tuple(sorted(e)) for e in access})

        # 1. representation: refused before any geometry, in milliseconds
        adj = _adjacency(union)
        k4, lens = find_k4(adj), find_triple_lens(adj)
        if k4 or lens:
            rec["stages"]["REPRESENTATION"] += 1
            rec["refusals"].append({"parti": prop.name, "stage": "REPRESENTATION",
                                    "code": "TOPOLOGY_REPRESENTATION_LIMIT",
                                    "detail": f"K4 {k4}" if k4 else f"triple-lens {lens}"})
            continue

        # 2. embedding (unchanged)
        emb = embed_band(zones, union, max_candidates=MAX_CANDIDATES)
        if isinstance(emb, BandEmbeddingRefusal):
            rec["stages"]["EMBEDDING"] += 1
            rec["refusals"].append({"parti": prop.name, "stage": "EMBEDDING", "code": emb.code,
                                    "detail": emb.detail[:200]})
            continue
        contacts = contact_requirements(zones, union, access)

        # 3. sizing inside the envelope, then realization; both orientations; the Stage 3 ladder
        sized = 0
        best = None
        reasons: Counter = Counter()
        screened = 0
        for cand in emb.candidates:
          # the production pipeline's own SELECTION step, reused: an allowed arrival room must be
          # able to front the street in some orientation, every door pair must touch legally,
          # REQUIRED exposure rooms must lie on the envelope, every room must be reachable. A
          # candidate failing these is never sized (it was: F4 spent 13 of 20 oracle-feasible
          # sizings on layouts with no entrance-eligible room in the street band).
          flags = placement_flags(cand, zones, p.resolved_wet, tuple(access))
          rejected = hard_rejections(flags)
          if rejected:
              for k in rejected:
                  reasons[f"SELECTION_{k}"] += 1
              continue
          oriented, _flipped = orient(cand, flags)
          for orient_tag, env_o in orientations:
            for bands in (oriented.bands,):
                if sized >= MAX_SIZINGS:
                    break
                seed = None
                if milp_heights is not None:
                    # 15 ms: does ANY height vector satisfy every constraint at the loosest band
                    # rung? If not, no rung can, and the exact sizer is not asked.
                    screened += 1
                    o = milp_heights(bands, _rebanded(zones, p, None), union, env_o,
                                     min_contact_u=contacts, k=16)
                    reasons[f"ORACLE_{o.status}"] += 1
                    if o.status != "FEASIBLE":
                        continue
                    seed = o.heights_u
                sized += 1
                for rung in AREA_BAND_LADDER:
                    zr = _rebanded(zones, p, rung) if rung != AREA_BAND_LADDER[0] else zones
                    if milp_placement is not None:
                        # the aligned oracle IS the sizer: heights and boundaries from one exact
                        # MILP, insets to a fixed point, no search left to fail
                        sz = milp_placement(bands, zr, union, env_o, min_contact_u=contacts).as_sizing()
                    else:
                        sz = solve_staircase_layout(bands, zr, union, env_o, min_contact_u=contacts,
                                                    node_limit=800, seed=seed)
                    if sz.status != "FEASIBLE":
                        reasons[sz.status] += 1
                        if sz.status == "BAND_GAP":
                            break                      # structural: no band width fixes a split envelope
                        continue                       # INFEASIBLE / ALIGNMENT_UNSAT / UNKNOWN: a wider band may
                    cell_rects, wing_rects = sz.rects(bands), sz.band_rects(bands)
                    if orient_tag == "V":
                        cell_rects = _transpose_rects(cell_rects)
                        wing_rects = tuple(_transpose_rects(dict(enumerate(wing_rects))).values())
                    out = realize_cells(f"{case['id']}:{prop.name}", cell_rects, zr,
                                        wing_rects, access, wet_rooms=p.resolved_wet)
                    if not isinstance(out, RealizedLayout):
                        reasons[out.constraint] += 1
                        break
                    sp = measure_spatial_adjacency(out.rects, frozenset(frozenset(e) for e in spatial))
                    ac = measure_access_graph(out.fixture.access.edges, access)
                    gross = float(out.design.gross_area_m2)
                    net = float(out.design.net_area_m2 or 0.0)
                    verdict = assess_area(requested, gross, net, p.capacity_m2)
                    full = sp.preserved == sp.requested and ac.preserved == ac.requested
                    plan = {"parti": prop.name, "bands": len(bands), "rung": rung, "orientation": orient_tag,
                            "contacts": f"{sp.preserved}/{sp.requested}",
                            "doors": f"{ac.preserved}/{ac.requested}",
                            "lost_doors": sorted(str(e) for e in ac.lost),
                            "arrival": _arrival_zone(out),
                            "gross_m2": round(gross, 1), "net_m2": round(net, 1),
                            "area": verdict.code, "gross_pct": verdict.gross_pct,
                            "wings": [(round(w.x * .05, 2), round(w.y * .05, 2), round(w.w * .05, 2),
                                       round(w.h * .05, 2)) for w in wing_rects],
                            "non_rectangular": len({(w.x, w.w) for w in sz.band_rects(bands)}) > 1,
                            "validators": len(out.report.checks),
                            "counts": bool(full and verdict.acceptable)}
                    rec["plans"].append(plan)
                    if plan["counts"] and best is None:
                        best = (plan, out)
                    break                                 # this candidate is sized; next candidate
            if best is not None:
                break
          if best is not None:
              break
        rec["stages"]["SIZED_CANDIDATES"] += sized
        rec["stages"]["SCREENED"] += screened
        for k, v in reasons.items():
            rec["stages"][k] += v
        if best is not None:
            plan, out = best
            design = to_demo_design(out.design, out.report, family=f"spike:{prop.name}",
                                    notes=[f"{case['id']} — {prop.name}; {plan['area']} {plan['gross_pct']}%"])
            path = os.path.join(out_dir, "designs", f"{case['id']}__{prop.name}.json")
            with open(path, "w") as fh:
                json.dump(design.model_dump(mode="json"), fh)
            plan["render"] = os.path.basename(path)

    rec["seconds"] = round(time.monotonic() - t0, 1)
    counted = [x for x in rec["plans"] if x["counts"]]
    rec["solved"] = bool(counted)
    rec["distinct_footprints"] = len({tuple(x["wings"]) for x in counted})
    rec["stages"] = dict(rec["stages"])
    return rec


def main(argv: list[str]) -> None:
    out_dir = argv[0] if argv else "shape_agnostic_out"
    os.makedirs(out_dir, exist_ok=True)
    spec = json.load(open(os.path.normpath(CASES_PATH)))
    wanted = set(argv[1:])
    results = []
    for case in spec["cases"]:
        if wanted and case["id"] not in wanted:
            continue
        rec = run_case(case, out_dir)
        results.append(rec)
        counted = [x for x in rec["plans"] if x["counts"]]
        print(f"{rec['id']:24} solved={rec['solved']!s:5} plans={len(counted)}/{len(rec['plans'])} "
              f"distinct_footprints={rec['distinct_footprints']} {rec['seconds']:6.1f}s "
              f"stages={rec['stages']}", flush=True)
    with open(os.path.join(out_dir, "results.json"), "w") as fh:
        json.dump(results, fh, indent=2, default=str)


if __name__ == "__main__":
    main(sys.argv[1:])
