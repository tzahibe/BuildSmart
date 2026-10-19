"""DRAWING-any-shape audit (#197, 2026-10-18) — build the product payload for every shape family the
brain can plan, through the REAL product path where one exists, and record where it breaks.

Parts (each writes DemoDesign JSON under <out>/designs and a record into results.json):
  A  product path: `generate_demo_design(project, brain=True)` — exactly what `?engine=brain` runs —
     primary + alternatives, for the audited briefs (BRAIN_FAMILIES = band/spine/stack/cells).
  B  per family: the same product function with `service.BRAIN_FAMILIES` narrowed to ONE family
     (band / spine / stack / cells) so the family's own plan is what the product shows first; when
     no exact plan of that family wins the brain's ranking, every parti's exact plan of that family
     is realized directly (`runner._one`, fallback=False) and converted with the same
     `to_demo_design` call `_brain_result` makes — flagged `via="_one"`.
  C  non-rectangular envelopes: the frozen F2/F4/F5 through `shape_agnostic.run.run_case`
     (the exact path over an `Envelope` polygon; `to_demo_design` is the product contract function)
     with reduced budgets, PLUS the product path on the SAME case's bounding box
     (`generate_demo_design(..., brain=True)`) — which is all `?engine=brain` can receive today.
  D  payload analysis: every JSON is checked for windows on interior walls, doors/windows without a
     host wall, rooms outside the footprint union, overlapping rooms, duplicate wall segments,
     polygon (L) rooms, footprint count, garden rects — the facts the renderer draws from.

Run from backend/:  uv run python -m app.ai_harness.drawing_audit.run <out_dir> [parts: A B C D]
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback

from app.ai_harness.topology_poc import briefs as briefs_mod
from app.demo import service as svc
from app.demo.contract import to_demo_design
from app.vertical_slice.brain import runner
from app.vertical_slice.brain.proposer import DeterministicProposer, programme_from_spec

BRIEFS_A = ("B08", "B20", "B11", "B06")
BRIEFS_B = ("B08", "B20", "B11")
FAMILIES = ("band", "spine", "stack", "cells")
FROZEN = ("F2-L-envelope-fixed", "F4-entry-court-notch", "F5-garden-court")
FAMILY_BUDGET_S = 30.0


def _project_for(b):
    from tests.vertical_slice.test_hub_guard import _project
    return _project(dict(bedrooms=b.bedrooms, wet_rooms=b.wet_rooms, safe_room=b.safe_room,
                         open_plan=b.open_plan, built_area_m2=b.built_area_m2,
                         footprint_width_m=b.footprint_width_m, footprint_depth_m=b.footprint_depth_m,
                         plot_width_m=b.footprint_width_m + 8, plot_depth_m=b.footprint_depth_m + 8))


def _dump(out_dir: str, name: str, design) -> str:
    path = os.path.join(out_dir, "designs", f"{name}.json")
    with open(path, "w") as fh:
        json.dump(design.model_dump(mode="json"), fh)
    return os.path.basename(path)


def _family_of(design) -> str:
    """The layout family a brain payload says it was sized with (`_brain_result`'s note)."""
    for w in design.validation.warnings:
        if w.startswith("sized by the "):
            return w.split("(")[-1].rstrip(")")
    return "?"


def _rec(**kw) -> dict:
    return kw


# ---------------------------------------------------------------------------- A: product path
def part_a(out_dir: str, briefs: dict) -> list[dict]:
    rows = []
    for bid in BRIEFS_A:
        project = _project_for(briefs[bid])
        t0 = time.monotonic()
        try:
            res = svc.generate_demo_design(project, brain=True)
        except svc.DemoGenerationError as exc:
            rows.append(_rec(part="A", brief=bid, outcome="REFUSED", code=exc.code, detail=exc.detail[:300],
                             seconds=round(time.monotonic() - t0, 1)))
            continue
        except Exception as exc:                      # noqa: BLE001 — the audit records, never hides
            rows.append(_rec(part="A", brief=bid, outcome="EXCEPTION", detail=traceback.format_exc()[-600:]))
            continue
        for i, d in enumerate((res.design, *res.alternatives)):
            name = f"{bid}__A-product-brain-{i}__{d.family.replace(':', '-')}__{_family_of(d)}"
            rows.append(_rec(part="A", brief=bid, outcome="PAYLOAD", index=i, family=d.family,
                             layout=_family_of(d), render=_dump(out_dir, name, d),
                             footprints=len(d.footprints), rooms=len(d.rooms),
                             polygon_rooms=[r.id for r in d.rooms if r.polygon_m],
                             seconds=round(time.monotonic() - t0, 1)))
        print(f"A {bid}: {len(res.alternatives) + 1} plans, {round(time.monotonic() - t0, 1)} s", flush=True)
    return rows


# ---------------------------------------------------------------------------- B: one family at a time
def part_b(out_dir: str, briefs: dict) -> list[dict]:
    rows = []
    for bid in BRIEFS_B:
        b = briefs[bid]
        project = _project_for(b)
        spec = svc.spec_for(project)
        for fam in FAMILIES:
            t0 = time.monotonic()
            svc.BRAIN_FAMILIES = (fam,)
            got = []
            try:
                res = svc.generate_demo_design(project, brain=True)
                for i, d in enumerate((res.design, *res.alternatives)):
                    if _family_of(d).startswith(fam):
                        got.append(d)
                        name = f"{bid}__B-{fam}-{i}__{d.family.replace(':', '-')}"
                        rows.append(_rec(part="B", brief=bid, family=fam, via="product", outcome="PAYLOAD",
                                         index=i, parti=d.family, render=_dump(out_dir, name, d),
                                         footprints=len(d.footprints), rooms=len(d.rooms),
                                         polygon_rooms=[r.id for r in d.rooms if r.polygon_m],
                                         seconds=round(time.monotonic() - t0, 1)))
            except svc.DemoGenerationError as exc:
                rows.append(_rec(part="B", brief=bid, family=fam, via="product", outcome="REFUSED",
                                 code=exc.code, detail=exc.detail[:300]))
            except Exception:                        # noqa: BLE001
                rows.append(_rec(part="B", brief=bid, family=fam, via="product", outcome="EXCEPTION",
                                 detail=traceback.format_exc()[-600:]))
            finally:
                svc.BRAIN_FAMILIES = FAMILIES
            if got:
                print(f"B {bid} {fam}: {len(got)} product plans, {round(time.monotonic() - t0, 1)} s", flush=True)
                continue
            # the family never won the ranking: realize its exact plan per parti, directly
            p = programme_from_spec(spec, (b.footprint_width_m, b.footprint_depth_m))
            proposals = DeterministicProposer().propose(p)
            share = FAMILY_BUDGET_S / max(len(proposals), 1)
            for prop in proposals:
                t1 = time.monotonic()
                try:
                    plan = runner._one(prop, p, 80, runner.MAX_REALIZATIONS_PREFERRED, sizer=runner.SIZER_EXACT,
                                       families=(fam,), deadline=time.monotonic() + share, fallback=False)
                except Exception:                    # noqa: BLE001
                    rows.append(_rec(part="B", brief=bid, family=fam, via="_one", parti=prop.name,
                                     outcome="EXCEPTION", detail=traceback.format_exc()[-600:]))
                    continue
                if plan.realized is None:
                    rows.append(_rec(part="B", brief=bid, family=fam, via="_one", parti=prop.name,
                                     outcome="NO_PLAN", stage=plan.stage, reason=plan.reason[:200],
                                     seconds=round(time.monotonic() - t1, 1)))
                    continue
                layout = plan.realized
                try:
                    d = to_demo_design(layout.design, layout.report, family=f"brain:{plan.parti}",
                                       notes=[f"{plan.parti}: {plan.rationale}",
                                              f"sized by the {plan.sizer} sizer ({plan.family} layout)", *plan.notes])
                except Exception:                    # noqa: BLE001
                    rows.append(_rec(part="B", brief=bid, family=fam, via="_one", parti=prop.name,
                                     outcome="PAYLOAD_EXCEPTION", detail=traceback.format_exc()[-600:]))
                    continue
                name = f"{bid}__B-{fam}-one__{plan.parti}"
                rows.append(_rec(part="B", brief=bid, family=fam, via="_one", parti=plan.parti, outcome="PAYLOAD",
                                 counts=plan.counts, ok=plan.ok, reason=plan.reason[:160], layout=plan.family,
                                 render=_dump(out_dir, name, d), footprints=len(d.footprints), rooms=len(d.rooms),
                                 polygon_rooms=[r.id for r in d.rooms if r.polygon_m],
                                 seconds=round(time.monotonic() - t1, 1)))
                print(f"B {bid} {fam} _one {plan.parti}: counts={plan.counts} {plan.reason[:60]}", flush=True)
    return rows


# ---------------------------------------------------------------------------- C: non-rect envelopes
def part_c(out_dir: str) -> list[dict]:
    from app.ai_harness.shape_agnostic import run as sa
    from app.vertical_slice.envelope import Envelope
    rows = []
    sa.SPINE_BUDGET_S, sa.STACK_BUDGET_S, sa.CELLS_BUDGET_S = 20.0, 20.0, 20.0
    sa.MAX_SIZINGS = 2
    spec = json.load(open(os.path.normpath(sa.CASES_PATH)))
    cases = {c["id"]: c for c in spec["cases"]}
    sub = os.path.join(out_dir, "frozen")
    os.makedirs(os.path.join(sub, "designs"), exist_ok=True)
    for cid in FROZEN:
        case = cases[cid]
        env = Envelope(tuple(tuple(v) for v in case["envelope"]))
        # C1: the exact path over the polygon (harness; `to_demo_design` is the product contract)
        t0 = time.monotonic()
        try:
            rec = sa.run_case(case, sub)
            plans = [x for x in rec["plans"] if x.get("render")]
            for x in plans:
                src = os.path.join(sub, "designs", x["render"])
                dst = os.path.join(out_dir, "designs", f"{cid}__C-polygon__{x['render']}")
                os.replace(src, dst)
                rows.append(_rec(part="C", case=cid, via="shape_agnostic.run_case", outcome="PAYLOAD",
                                 counts=x.get("counts"), family=x.get("family"), parti=x.get("parti"),
                                 render=os.path.basename(dst), seconds=round(time.monotonic() - t0, 1)))
            if not plans:
                rows.append(_rec(part="C", case=cid, via="shape_agnostic.run_case", outcome="NO_PLAN",
                                 stages=dict(rec["stages"]), refusals=rec["refusals"][:4]))
            print(f"C {cid}: {len(plans)} polygon payloads, {round(time.monotonic() - t0, 1)} s", flush=True)
        except Exception:                            # noqa: BLE001
            rows.append(_rec(part="C", case=cid, via="shape_agnostic.run_case", outcome="EXCEPTION",
                             detail=traceback.format_exc()[-800:]))
        # C2: the product path on the same case — all it can take is a rectangle (`Project.selected_footprint`
        # is width x depth; `_brain_result` hands `run_brain` `(outline.width_m, outline.depth_m)`;
        # `run_exact_pipeline` builds `Envelope.rectangle`). The bounding box is what it plans.
        t0 = time.monotonic()
        project, _ = sa._project_for(case)
        try:
            res = svc.generate_demo_design(project, brain=True)
            d = res.design
            name = f"{cid}__C-product-bbox__{d.family.replace(':', '-')}"
            rows.append(_rec(part="C", case=cid, via="product(bbox)", outcome="PAYLOAD", family=d.family,
                             layout=_family_of(d), render=_dump(out_dir, name, d), footprints=len(d.footprints),
                             bbox_m=[env.width_u * 0.05, env.depth_u * 0.05], envelope_area_m2=env.area_m2,
                             gross_m2=d.gross_area_m2, seconds=round(time.monotonic() - t0, 1)))
        except svc.DemoGenerationError as exc:
            rows.append(_rec(part="C", case=cid, via="product(bbox)", outcome="REFUSED", code=exc.code,
                             detail=exc.detail[:300]))
        except Exception:                            # noqa: BLE001
            rows.append(_rec(part="C", case=cid, via="product(bbox)", outcome="EXCEPTION",
                             detail=traceback.format_exc()[-600:]))
        print(f"C {cid} product bbox done {round(time.monotonic() - t0, 1)} s", flush=True)
    return rows


# ---------------------------------------------------------------------------- E: site context
def part_e(out_dir: str, briefs: dict) -> list[dict]:
    """The same brief with ONE parking bay, production vs brain: what the brain payload keeps of the
    person's site (plot, parking, garden, outline) and of the brief's open-plan semantics."""
    from dataclasses import replace
    from app.projects.models import TaggedInt, SourceTag
    rows = []
    b = briefs["B08"]
    project = _project_for(b)
    project = project.model_copy(update={"parking_spaces": TaggedInt(value=1, source=SourceTag.requested)}) \
        if hasattr(project, "model_copy") else replace(project, parking_spaces=TaggedInt(value=1, source=SourceTag.requested))
    for label, kw in (("production", {}), ("brain", {"brain": True})):
        t0 = time.monotonic()
        try:
            res = svc.generate_demo_design(project, **kw)
        except svc.DemoGenerationError as exc:
            rows.append(_rec(part="E", path=label, outcome="REFUSED", code=exc.code, detail=exc.detail[:300]))
            continue
        d = res.design
        name = f"B08-parking1__E-{label}__{d.family.replace(':', '-')}"
        rows.append(_rec(part="E", path=label, outcome="PAYLOAD", render=_dump(out_dir, name, d),
                         plot=d.plot.model_dump(), parking=len(d.parking), garden=len(d.garden),
                         open_interfaces=len(d.open_interfaces), footprints=len(d.footprints),
                         outline=d.outline.model_dump() if d.outline else None,
                         entrance_walk=d.entrance_walk.model_dump(), seconds=round(time.monotonic() - t0, 1)))
        print(f"E {label}: parking {len(d.parking)} garden {len(d.garden)} open {len(d.open_interfaces)}", flush=True)
    return rows


# ---------------------------------------------------------------------------- D: payload analysis
def _eps(a, b, e=1e-6):
    return abs(a - b) < e


def analyse(d: dict) -> dict:
    walls = {w.get("id"): w for w in d["walls"]}
    rooms = d["rooms"]
    fps = d.get("footprints") or [d["footprint"]]
    out: dict = {"footprints": len(fps), "rooms": len(rooms), "walls": len(d["walls"]), "doors": len(d["doors"]),
                 "windows": len(d["windows"]), "garden_rects": len(d.get("garden", [])),
                 "polygon_rooms": [r["id"] for r in rooms if r.get("polygon_m")],
                 "flex_rooms": [r["id"] for r in rooms if r["type"] == "FLEX"]}
    # windows: host wall must be EXTERIOR
    bad_w, orphan_w = [], []
    for w in d["windows"]:
        seg = walls.get(w.get("wall_id"))
        if seg is None:
            orphan_w.append(w["room_id"])
        elif seg["boundary_context"] != "EXTERIOR":
            bad_w.append((w["room_id"], w["side"]))
    out["windows_on_interior_walls"] = bad_w
    out["windows_without_wall"] = orphan_w
    out["doors_without_wall"] = [(x["a"], x["b"]) for x in d["doors"] if not x.get("wall_id")]
    # rooms inside the footprint union (grid tolerance)
    def inside(r):
        x0, y0, x1, y1 = r["x"], r["y"], r["x"] + r["gross_width_m"], r["y"] + r["gross_depth_m"]
        return any(f["x"] - 1e-6 <= x0 and f["y"] - 1e-6 <= y0 and x1 <= f["x"] + f["width_m"] + 1e-6
                   and y1 <= f["y"] + f["depth_m"] + 1e-6 for f in fps)
    out["rooms_outside_any_footprint"] = [r["id"] for r in rooms if not r.get("polygon_m") and not inside(r)]
    # overlapping rooms
    ov = []
    for i, a in enumerate(rooms):
        for b in rooms[i + 1:]:
            if a.get("polygon_m") or b.get("polygon_m"):
                continue
            if (a["x"] < b["x"] + b["gross_width_m"] - 1e-6 and b["x"] < a["x"] + a["gross_width_m"] - 1e-6
                    and a["y"] < b["y"] + b["gross_depth_m"] - 1e-6 and b["y"] < a["y"] + a["gross_depth_m"] - 1e-6):
                ov.append((a["id"], b["id"]))
    out["overlapping_rooms"] = ov
    # duplicate / overlapping collinear wall segments (drawn twice = darker seam)
    dup = 0
    segs = d["walls"]
    for i, a in enumerate(segs):
        for b in segs[i + 1:]:
            if a["orientation"] == b["orientation"] and _eps(a["coord"], b["coord"]):
                lo, hi = max(a["start"], b["start"]), min(a["end"], b["end"])
                if hi - lo > 1e-6:
                    dup += 1
    out["overlapping_wall_segments"] = dup
    # footprint union area vs rooms' gross area (uncovered floor = missing walls/rooms in the drawing)
    fp_area = sum(f["width_m"] * f["depth_m"] for f in fps)
    room_area = sum(r["gross_area_m2"] for r in rooms)
    out["footprint_area_m2"] = round(fp_area, 2)
    out["rooms_gross_area_m2"] = round(room_area, 2)
    out["uncovered_m2"] = round(fp_area - room_area, 2)
    # exterior sides of rooms that carry no window (a bedroom/living facing the garden with none)
    no_win = []
    with_win = {(w["room_id"], w["side"]) for w in d["windows"]}
    for r in rooms:
        if r["type"] in ("BEDROOM", "MASTER_BEDROOM", "LIVING", "KITCHEN", "LIVING_KITCHEN"):
            ext = [s for s, f in r["walls"].items() if f["boundary_context"] == "EXTERIOR" and f.get("can_take_a_window")]
            if ext and not any((r["id"], s) in with_win for s in ext):
                no_win.append(r["id"])
    out["habitable_rooms_without_window"] = no_win
    out["entrance_room"] = next((x["b"] if x["a"] in ("ENTRANCE", "OUTSIDE") else x["a"]
                                 for x in d["doors"] if x.get("is_entrance")), None)
    ew = d["entrance_walk"]
    ent = next((x for x in d["doors"] if x.get("is_entrance")), None)
    # the walk must end at the front door: a walk that ends in the void (entry-court notch) is a
    # drawing defect even when every validator passes
    out["walk_reaches_door"] = (ent is not None and ew["x"] - 1e-6 <= ent["x"] <= ew["x"] + ew["width_m"] + 1e-6
                                and abs(ew["y"] + ew["depth_m"] - ent["y"]) < 1e-6)
    out["validation_passed"] = d["validation"]["passed"]
    return out


def part_d(out_dir: str) -> dict:
    res = {}
    ddir = os.path.join(out_dir, "designs")
    for f in sorted(os.listdir(ddir)):
        if f.endswith(".json"):
            res[f] = analyse(json.load(open(os.path.join(ddir, f))))
    return res


def main(argv: list[str]) -> None:
    out_dir = argv[0]
    parts = set(argv[1:]) or {"A", "B", "C", "E", "D"}
    os.makedirs(os.path.join(out_dir, "designs"), exist_ok=True)
    path = os.path.join(out_dir, "results.json")
    results = json.load(open(path)) if os.path.exists(path) else {}
    briefs = {x.brief_id: x for x in briefs_mod.select_briefs()}
    for part, fn in (("A", lambda: part_a(out_dir, briefs)), ("B", lambda: part_b(out_dir, briefs)),
                     ("C", lambda: part_c(out_dir)), ("E", lambda: part_e(out_dir, briefs))):
        if part in parts:
            results[part] = fn()
            json.dump(results, open(path, "w"), indent=1, default=str)
    if "D" in parts:
        results["D"] = part_d(out_dir)
        json.dump(results, open(path, "w"), indent=1, default=str)


if __name__ == "__main__":
    main(sys.argv[1:])
