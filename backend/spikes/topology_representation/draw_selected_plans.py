"""#142H — draw the plans the PRODUCTION band pipeline (`run_band_pipeline`, with selection) realizes
for the frozen briefs, walls coloured by type (RC thick red), doors with their shared-boundary length vs
the door need, windows, the entrance, and the selection funnel; plus a JSON evidence file.
Usage (dev venv, PYTHONPATH=backend:backend/tests/vertical_slice):
    python draw_selected_plans.py <out_dir> [B11,B18,...]"""
import json, os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from frozen_briefs import load_fixture, pipeline_input
from app.vertical_slice.band_pipeline import PipelineSuccess, run_band_pipeline
from app.vertical_slice.band_sizing import door_contact_u
from app.vertical_slice.geometry_core.engine import net_rect_m
from app.vertical_slice.geometry_core.model import Side, WallType

COLOR = {WallType.RC_SAFE_ROOM: "#b03a2e", WallType.EXTERIOR: "#222222", WallType.PARTITION: "#888888", WallType.OPEN: "#dddddd"}
WIDTH = {WallType.RC_SAFE_ROOM: 6, WallType.EXTERIOR: 3.5, WallType.PARTITION: 1.5, WallType.OPEN: 0.5}


def draw(bid, res, inp, out):
    rl = res.realized
    fig, ax = plt.subplots(figsize=(9.5, 8.5))
    u = 0.05
    for zid, r in rl.rects.items():
        x, y, w, h = r.x * u, r.y * u, r.w * u, r.h * u
        safe = inp.zones[zid].role.value == "SAFE_ROOM"
        ax.add_patch(Rectangle((x, y), w, h, facecolor="#f8d7d1" if safe else "#f4f4f4", edgecolor="none"))
        nw, nh, na = net_rect_m(zid, r, rl.walls)
        ax.text(x + w / 2, y + h / 2, f"{zid}\n{w:.2f}x{h:.2f} gross\n{nw:.2f}x{nh:.2f} net = {na:.1f} m²", ha="center", va="center", fontsize=7)
        for s in Side:
            wt = rl.walls[(zid, s)]
            if s is Side.N: xs, ys = [x, x + w], [y, y]
            elif s is Side.S: xs, ys = [x, x + w], [y + h, y + h]
            elif s is Side.W: xs, ys = [x, x], [y, y + h]
            else: xs, ys = [x + w, x + w], [y, y + h]
            ax.plot(xs, ys, color=COLOR[wt], lw=WIDTH[wt], solid_capstyle="butt", alpha=0.9 if wt is WallType.RC_SAFE_ROOM else 0.7)
    access = {frozenset((a, b)) for a, b in inp.access_edges}
    for d in rl.interior_doors:
        if d.placeable:
            cx, cy = d.center_u[0] * u, d.center_u[1] * u
            declared = frozenset((d.a, d.b)) in access
            ax.plot(cx, cy, marker="s", color="#2a7f62" if declared else "#9ab", ms=6)
            shared = rl.rects[d.a].shared_edge_len_u(rl.rects[d.b]) * u
            need = door_contact_u(inp.zones[d.a].role, inp.zones[d.b].role) * u
            ax.text(cx, cy, f" {d.a}↔{d.b} ({shared:.2f}≥{need:.2f})", fontsize=5, color="#2a7f62" if declared else "#9ab", va="bottom")
    ed = rl.entrance_door
    ax.plot(ed.center_u[0] * u, ed.center_u[1] * u, marker="*", color="#1f4e9c", ms=14)
    ax.text(ed.center_u[0] * u, ed.center_u[1] * u - 0.25, f"ENTRANCE → {ed.b}", fontsize=7, color="#1f4e9c", ha="center")
    for w in rl.windows:
        if w.placeable:
            ax.plot(w.center_u[0] * u, w.center_u[1] * u, marker="_", color="#3a8fd6", ms=12, mew=3)
    f = res.selection
    ax.set_title(f"{bid}: production pipeline with selection — validator {'PASS' if rl.report.ok else 'FAIL'}; "
                 f"candidate #{res.candidate_index}{' (flipped to the street)' if res.oriented else ''}; "
                 f"access {res.access_preserved}, spatial {res.spatial_preserved}\n"
                 f"funnel: {f.get('candidates')} layouts → {f.get('hard_feasible')} HARD-feasible ({f.get('oriented', 0)} flipped) → "
                 f"{f.get('sized')} door-aware sized → realized & passed on the {res.candidates_tried}th record\n"
                 f"red thick = RC_SAFE_ROOM; black = EXTERIOR; grey = PARTITION; ★ entrance; ■ door (shared m ≥ door need m); — window", fontsize=8)
    ax.set_aspect("equal"); ax.invert_yaxis(); ax.set_xlabel("m"); ax.set_ylabel("m (street at the top)")
    xs = [r.x * u for r in rl.rects.values()] + [(r.x + r.w) * u for r in rl.rects.values()]
    ys = [r.y * u for r in rl.rects.values()] + [(r.y + r.h) * u for r in rl.rects.values()]
    ax.set_xlim(min(xs) - 0.5, max(xs) + 0.5); ax.set_ylim(max(ys) + 0.5, min(ys) - 0.5)
    fig.tight_layout(); fig.savefig(out, dpi=130); plt.close(fig)


def main(out_dir, briefs):
    fx = load_fixture()["briefs"]
    evidence = {}
    for bid in briefs:
        inp = pipeline_input(bid, fx[bid])
        res = run_band_pipeline(inp)
        if not isinstance(res, PipelineSuccess):
            print(bid, res.code, res.detail[:120]); evidence[bid] = {"result": res.code, "stage": res.stage, "selection": res.selection}; continue
        draw(bid, res, inp, os.path.join(out_dir, f"{bid}_selected_plan.png"))
        rl = res.realized
        doors = {}
        for a, b in inp.access_edges:
            shared = rl.rects[a].shared_edge_len_u(rl.rects[b]) if a in rl.rects and b in rl.rects else 0
            need = door_contact_u(inp.zones[a].role, inp.zones[b].role)
            placed = any(d.placeable and {d.a, d.b} == {a, b} for d in rl.interior_doors)
            doors[f"{a}->{b}"] = {"shared_u": shared, "need_u": need, "door_placed": placed}
        safe = [z for z in rl.rects if inp.zones[z].role.value == "SAFE_ROOM"]
        evidence[bid] = {"result": "PASS", "candidate": res.candidate_index, "oriented": res.oriented, "selection": res.selection,
                         "entrance_room": rl.entrance_door.b, "street_band": [z for z, _ in res.placement.rows[0]],
                         "access": res.access_preserved, "spatial": res.spatial_preserved, "doors": doors,
                         "safe_room": ({"sides": {s.value: rl.walls[(safe[0], s)].value for s in Side},
                                        "net_area_m2": net_rect_m(safe[0], rl.rects[safe[0]], rl.walls)[2],
                                        "window": [w.side.value for w in rl.windows if w.zone_id == safe[0] and w.placeable]} if safe else None),
                         "failed_checks": [c.check_id for c in rl.report.checks if not c.passed]}
        print(bid, json.dumps(evidence[bid], default=str)[:400])
    json.dump(evidence, open(os.path.join(out_dir, "selection_evidence.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2].split(",") if len(sys.argv) > 2 else ["B01", "B04", "B05", "B08", "B11", "B13", "B18"])
