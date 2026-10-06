"""#142L — render a realized plan record from `quality_142l.baseline` as a readable architectural
floor plan, and render A/B pair sheets for the pairwise comparison and the independent judge.

Deliberately NEUTRAL: a rendered plan carries the brief, the rooms, their areas and the openings, and
nothing that could leak which plan production preferred — no candidate index, no heuristic score, no
metric values. The judge sheets label the two plans only "Plan A" / "Plan B" (the caller decides which
record is which, and swaps them for the order-consistency control).
"""
from __future__ import annotations

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

#: Fill by role class — public warm, private cool, wet blue, circulation grey. Readability only.
FILL = {
    "LIVING": "#fdf1dc", "DINING": "#fdf1dc", "KITCHEN": "#fae6c8", "FAMILY_ROOM": "#fdf1dc",
    "HALL": "#eceff1", "CIRCULATION": "#eceff1", "STAIRWELL": "#e0e0e0",
    "MASTER_BEDROOM": "#e3eaf6", "BEDROOM": "#e8eef8", "STUDY": "#e8eef8", "DRESSING_ROOM": "#eef2fa",
    "BATHROOM": "#dcecf2", "TOILET": "#dcecf2", "LAUNDRY": "#e6f0ea", "STORAGE": "#efefef",
    "SAFE_ROOM": "#f6dcd8", "FLEX": "#f4f4f4",
}
WALL_COLOR = {"EXTERIOR": "#1b1b1b", "RC_SAFE_ROOM": "#b03a2e", "PARTITION": "#8a8a8a", "OPEN": "#d8d8d8"}
WALL_WIDTH = {"EXTERIOR": 3.2, "RC_SAFE_ROOM": 5.0, "PARTITION": 1.3, "OPEN": 0.6}
SIDE_SEG = {"N": lambda x, y, w, h: ([x, x + w], [y, y]), "S": lambda x, y, w, h: ([x, x + w], [y + h, y + h]),
            "W": lambda x, y, w, h: ([x, x], [y, y + h]), "E": lambda x, y, w, h: ([x + w, x + w], [y, y + h])}


def brief_text(plan: dict) -> str:
    b = plan["brief_facts"]
    return (f"{b['bedrooms']} bedroom(s), {b['wet_rooms']} wet room(s), "
            f"safe room: {'yes' if b['safe_room'] else 'no'}, open plan requested: {'yes' if b['open_plan'] else 'no'}; "
            f"footprint {b['footprint_m'][0]:.0f} x {b['footprint_m'][1]:.0f} m, built area {b['built_area_m2']:.0f} m2")


def draw_plan(plan: dict, ax, title: str) -> None:
    rooms = plan["rooms"]
    fx, fy, fw, fh = plan["footprint_m"]
    for zid, r in rooms.items():
        x, y, w, h = r["rect_m"]
        ax.add_patch(Rectangle((x, y), w, h, facecolor=FILL.get(r["role"], "#f4f4f4"), edgecolor="none"))
        label = f"{zid}\n{r['net_area_m2']:.1f} m²\n{r['net_w_m']:.1f}×{r['net_h_m']:.1f}"
        ax.text(x + w / 2, y + h / 2, label, ha="center", va="center", fontsize=6.4, linespacing=1.25)
        for side, wt in (r.get("walls") or {}).items():
            xs, ys = SIDE_SEG[side](x, y, w, h)
            ax.plot(xs, ys, color=WALL_COLOR.get(wt, "#8a8a8a"), lw=WALL_WIDTH.get(wt, 1.3),
                    solid_capstyle="butt", zorder=3)
        for win in r.get("windows", []):
            if not win.get("placeable"):
                continue
            xs, ys = SIDE_SEG[win["side"]](x, y, w, h)
            cx, cy = sum(xs) / 2, sum(ys) / 2
            horiz = abs(xs[0] - xs[1]) > abs(ys[0] - ys[1])
            half = win["width_m"] / 2
            ax.plot([cx - half, cx + half] if horiz else [cx, cx], [cy, cy] if horiz else [cy - half, cy + half],
                    color="#2e86c1", lw=4.0, solid_capstyle="butt", zorder=4)
    for d in plan["doors"]:
        if not d.get("placeable"):
            continue
        cx, cy = d["center_m"]
        ax.plot(cx, cy, marker="s", ms=4.2, color="#1e8449", zorder=5)
    ed = plan["entrance_door"]
    ax.plot(ed["center_m"][0], ed["center_m"][1], marker="*", ms=15, color="#1f4e9c", zorder=6)
    ax.annotate("ENTRANCE", (ed["center_m"][0], ed["center_m"][1]), textcoords="offset points",
                xytext=(0, -14), ha="center", fontsize=7, color="#1f4e9c", weight="bold")
    ax.plot([fx - 0.4, fx + fw + 0.4], [fy - 0.7, fy - 0.7], color="#1f4e9c", lw=1.1, ls="--")
    ax.text(fx + fw / 2, fy - 1.15, "STREET", ha="center", fontsize=7.5, color="#1f4e9c", weight="bold")
    ax.set_title(title, fontsize=9)
    ax.set_aspect("equal"); ax.invert_yaxis(); ax.axis("off")
    ax.set_xlim(fx - 1.0, fx + fw + 1.0); ax.set_ylim(fy + fh + 1.0, fy - 2.0)


def plan_sheet(plan: dict, out_path: str, title: str | None = None, with_identity: bool = True) -> str:
    fig, ax = plt.subplots(figsize=(7.2, 7.4))
    t = title if title is not None else (f"{plan['brief']} — candidate #{plan['candidate']}" if with_identity else "Floor plan")
    draw_plan(plan, ax, t)
    fig.text(0.5, 0.035, brief_text(plan), ha="center", fontsize=7.6, color="#333333", wrap=True)
    fig.text(0.5, 0.012, "walls: black = exterior, grey = partition, thick red = RC safe-room | blue = window | "
             "green ■ = interior door | ★ = front door", ha="center", fontsize=6.4, color="#666666")
    fig.tight_layout(rect=(0, 0.06, 1, 1)); fig.savefig(out_path, dpi=150); plt.close(fig)
    return out_path


def pair_sheet(plan_a: dict, plan_b: dict, out_path: str, *, blind: bool = True, note: str = "") -> str:
    """Side-by-side A/B sheet. With `blind` (the judge's copy) neither panel shows a candidate index."""
    fig, axes = plt.subplots(1, 2, figsize=(14.4, 7.8))
    draw_plan(plan_a, axes[0], "Plan A" if blind else f"Plan A — {plan_a['brief']} #{plan_a['candidate']}")
    draw_plan(plan_b, axes[1], "Plan B" if blind else f"Plan B — {plan_b['brief']} #{plan_b['candidate']}")
    head = f"BRIEF: {brief_text(plan_a)}"
    fig.suptitle(head + (f"\n{note}" if note else ""), fontsize=9.5)
    fig.text(0.5, 0.015, "walls: black = exterior, grey = partition, thick red = RC safe-room | blue = window | "
             "green ■ = interior door | ★ = front door | street at the bottom edge of each plan",
             ha="center", fontsize=7, color="#666666")
    fig.tight_layout(rect=(0, 0.04, 1, 0.93)); fig.savefig(out_path, dpi=140); plt.close(fig)
    return out_path


def main(pool_path: str, out_dir: str, which: str = "all") -> None:
    pool = json.load(open(pool_path))
    os.makedirs(out_dir, exist_ok=True)
    n = 0
    for bid, b in sorted(pool["briefs"].items()):
        if which not in ("all", bid):
            continue
        for plan in b["plans"]:
            plan_sheet(plan, os.path.join(out_dir, f"{bid}_c{plan['candidate']}.png"))
            n += 1
    print(f"rendered {n} plan sheets into {out_dir}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "all")
