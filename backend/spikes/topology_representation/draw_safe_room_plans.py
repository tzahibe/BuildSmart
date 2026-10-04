"""#142G — draw the realized plans of the safe-room briefs with walls coloured by type (RC walls thick
red), doors, windows and the entrance, plus the validator verdict, as inspectable evidence.
Usage (dev venv, PYTHONPATH=backend): python draw_safe_room_plans.py <out_dir> [B04,B11,B18]"""
import json, os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from unittest import mock

from app.ai_harness.topology_poc.intent_142f import (FIXTURE, access_policy_conflicts, candidate_flags, flipped, load_brief,
                                                     solve_band_layout_doors)
from app.vertical_slice import rectilinear_realizer as rr
from app.vertical_slice.band_embedding import embed_band
from app.vertical_slice.geometry_core.engine import net_rect_m
from app.vertical_slice.geometry_core.model import Rect, Side, WallType, m_to_u
from app.vertical_slice.rectilinear_realizer import GridCell, GridWing, RealizationIntent, RealizedLayout, realize_layout

COLOR = {WallType.RC_SAFE_ROOM: "#b03a2e", WallType.EXTERIOR: "#222222", WallType.PARTITION: "#888888", WallType.OPEN: "#dddddd"}
WIDTH = {WallType.RC_SAFE_ROOM: 6, WallType.EXTERIOR: 3.5, WallType.PARTITION: 1.5, WallType.OPEN: 0.5}


def first_passing(bid, inp):
    spatial = {frozenset(e) for e in inp.required_edges}
    access = [(a, b) for a, b in inp.access_edges if a in inp.zones and b in inp.zones]
    union = sorted({tuple(sorted(e)) for e in spatial} | {tuple(sorted(e)) for e in access})
    emb = embed_band(inp.zones, union, max_candidates=150)
    fw, fd = inp.footprint_m; bw, bd = fw + 4, fd + 4
    buildable = Rect(0, 0, m_to_u(bw), m_to_u(bd))
    for i, p in enumerate(emb.candidates):
        f = candidate_flags(p, inp)
        hard = f["entrance_feasible"] and f["access_contact_ok"] and f["exposure_ok"] and f["reachable_from_entrance"] and (f["safe_room_on_envelope"] is not False)
        if not hard:
            continue
        if not f["entrance_now"] and f["entrance_flip"]:
            p = flipped(p)
        sz = solve_band_layout_doors(p.bands, inp.zones, [tuple(e) for e in spatial], access, w_max_m=bw, h_max_m=bd)
        if sz.status != "FEASIBLE":
            continue
        W, H = round(sum(sz.col_w_u) * 0.05, 2), round(sum(sz.row_h_u) * 0.05, 2)
        wing = GridWing(bid, W, H, sz.n_cols, tuple(tuple(GridCell(z, s) for z, s in r) for r in sz.rows), inp.zones)
        row_h, col_w = list(sz.row_h_u), list(sz.col_w_u)
        with mock.patch.object(rr, "_solve_grid", lambda w: (row_h, col_w)):
            res = realize_layout(RealizationIntent(name=bid, wings=(wing,), wet_rooms=inp.wet_rooms), buildable=buildable)
        if isinstance(res, RealizedLayout):
            return i, res
    return None, None


def draw(bid, res, out):
    fig, ax = plt.subplots(figsize=(9, 8))
    u = 0.05
    for zid, r in res.rects.items():
        x, y, w, h = r.x * u, r.y * u, r.w * u, r.h * u
        safe = zid.startswith("SAFE")
        ax.add_patch(Rectangle((x, y), w, h, facecolor="#f8d7d1" if safe else "#f4f4f4", edgecolor="none"))
        nw, nh, na = net_rect_m(zid, r, res.walls)
        ax.text(x + w / 2, y + h / 2, f"{zid}\n{w:.2f}x{h:.2f} gross\n{nw:.2f}x{nh:.2f} net = {na:.1f} m²", ha="center", va="center", fontsize=7)
        for s in Side:
            wt = res.walls[(zid, s)]
            if s is Side.N: xs, ys = [x, x + w], [y, y]
            elif s is Side.S: xs, ys = [x, x + w], [y + h, y + h]
            elif s is Side.W: xs, ys = [x, x], [y, y + h]
            else: xs, ys = [x + w, x + w], [y, y + h]
            ax.plot(xs, ys, color=COLOR[wt], lw=WIDTH[wt], solid_capstyle="butt", alpha=0.9 if wt is WallType.RC_SAFE_ROOM else 0.7)
    for d in res.interior_doors:
        if d.placeable:
            cx, cy = d.center_u[0] * u, d.center_u[1] * u
            ax.plot(cx, cy, marker="s", color="#2a7f62", ms=6)
            ax.text(cx, cy, f" {d.a}↔{d.b}", fontsize=5, color="#2a7f62", va="bottom")
    ed = res.entrance_door
    ax.plot(ed.center_u[0] * u, ed.center_u[1] * u, marker="*", color="#1f4e9c", ms=14)
    ax.text(ed.center_u[0] * u, ed.center_u[1] * u - 0.25, f"ENTRANCE → {ed.b}", fontsize=7, color="#1f4e9c", ha="center")
    for w in res.windows:
        if w.placeable:
            ax.plot(w.center_u[0] * u, w.center_u[1] * u, marker="_", color="#3a8fd6", ms=12, mew=3)
    c4 = next(c for c in res.report.checks if c.check_id == "C4")
    ax.set_title(f"{bid}: realized plan, validator {'PASS' if res.report.ok else 'FAIL'} — C4: {c4.detail[:70]}\n"
                 f"red thick = RC_SAFE_ROOM wall (safe room's own 4 sides + every neighbour side touching it); black = EXTERIOR; grey = PARTITION; ★ entrance; ■ doors; — windows", fontsize=8)
    ax.set_aspect("equal"); ax.invert_yaxis(); ax.set_xlabel("m"); ax.set_ylabel("m (street at the top)")
    xs = [r.x * u for r in res.rects.values()] + [(r.x + r.w) * u for r in res.rects.values()]
    ys = [r.y * u for r in res.rects.values()] + [(r.y + r.h) * u for r in res.rects.values()]
    ax.set_xlim(min(xs) - 0.5, max(xs) + 0.5); ax.set_ylim(max(ys) + 0.5, min(ys) - 0.5)
    fig.tight_layout(); fig.savefig(out, dpi=130); plt.close(fig)


def main(out_dir, briefs):
    fx = json.load(open(FIXTURE))["briefs"]
    evidence = {}
    for bid in briefs:
        inp = load_brief(bid, fx[bid])
        idx, res = first_passing(bid, inp)
        if res is None:
            print(bid, "no passing candidate"); continue
        draw(bid, res, os.path.join(out_dir, f"{bid}_safe_room_plan.png"))
        safe = [z for z in res.rects if z.startswith("SAFE")][0]
        rc_neighbours = sorted({(zid, s.value) for (zid, s), wt in res.walls.items() if wt is WallType.RC_SAFE_ROOM and zid != safe})
        doors = [f"{d.a}-{d.b}" for d in res.interior_doors if d.placeable and safe in (d.a, d.b)]
        nw, nh, na = net_rect_m(safe, res.rects[safe], res.walls)
        evidence[bid] = {"candidate": idx, "safe_room": safe, "gross_m": [round(res.rects[safe].w * 0.05, 2), round(res.rects[safe].h * 0.05, 2)],
                         "net_m": [nw, nh], "net_area_m2": na, "safe_room_sides": {s.value: res.walls[(safe, s)].value for s in Side},
                         "rc_neighbour_sides": rc_neighbours, "safe_room_doors": doors,
                         "safe_room_windows": [w.side.value for w in res.windows if w.zone_id == safe and w.placeable],
                         "exterior_sides_of_safe_room": [s.value for s in Side if res.walls[(safe, s)] is WallType.RC_SAFE_ROOM and
                                                          not any(o != safe and res.rects[safe].shared_edge_len_u(r2) > 0 and rr._side_between(res.rects[safe], r2) == s for o, r2 in res.rects.items())],
                         "validator_ok": res.report.ok, "failed_checks": [c.check_id for c in res.report.checks if not c.passed]}
        print(bid, evidence[bid])
    json.dump(evidence, open(os.path.join(out_dir, "safe_room_evidence.json"), "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2].split(",") if len(sys.argv) > 2 else ["B04", "B11", "B18"])
