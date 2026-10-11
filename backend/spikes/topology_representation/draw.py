"""Figures for the report: required graph, best GridWing embedding (preserved/lost), obstruction,
and the witness layout at the minimal sufficient family."""
import json, math, os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import networkx as nx

OUT = sys.argv[1] if len(sys.argv) > 1 else "fig"
os.makedirs(OUT, exist_ok=True)
G = json.load(open("selected_graphs.json"))
H = json.load(open("heuristic_dump.json"))
LV = {}
for f in os.listdir("."):
    if f.startswith("levels_") and f.endswith(".json"):
        LV.update(json.load(open(f)))

SHORT = {"MASTER_BEDROOM": "MASTER", "BATHROOM_1": "BATH1", "BATHROOM_2": "BATH2", "BATHROOM_3": "BATH3",
         "BEDROOM_1": "BED1", "BEDROOM_2": "BED2", "BEDROOM_3": "BED3", "BEDROOM_4": "BED4",
         "SAFE_ROOM": "SAFE", "KITCHEN": "KITCH", "LIVING": "LIVING", "DINING": "DINING", "HALL": "HALL",
         "MASTER": "MASTER"}
ROLE_COLOR = {"HALL": "#f2c14e", "LIVING": "#9ecae1", "DINING": "#9ecae1", "KITCHEN": "#6baed6",
              "BATH": "#c7e9c0", "BED": "#fcbba1", "MASTER": "#fb6a4a", "SAFE": "#bdbdbd"}


def color(rid):
    s = SHORT.get(rid, rid)
    for k, c in ROLE_COLOR.items():
        if s.startswith(k):
            return c
    return "#dddddd"


def lbl(rid):
    return SHORT.get(rid, rid)


def draw_graph(ax, nodes, edges, preserved=None, lost=None, highlight_nodes=(), title=""):
    g = nx.Graph(); g.add_nodes_from(nodes); g.add_edges_from(edges)
    # hub-centred layout: highest degree node in the middle
    pos = nx.kamada_kawai_layout(g)
    deg = dict(g.degree())
    nx.draw_networkx_nodes(g, pos, ax=ax, node_color=[color(v) for v in nodes], node_size=1100,
                           edgecolors=["#d62728" if v in highlight_nodes else "#333" for v in nodes],
                           linewidths=[3 if v in highlight_nodes else 1 for v in nodes])
    if preserved is None:
        nx.draw_networkx_edges(g, pos, ax=ax, width=1.6, edge_color="#444")
    else:
        pe = [tuple(e) for e in preserved]; le = [tuple(e) for e in lost]
        nx.draw_networkx_edges(g, pos, edgelist=pe, ax=ax, width=2.2, edge_color="#2ca02c")
        nx.draw_networkx_edges(g, pos, edgelist=le, ax=ax, width=2.2, edge_color="#d62728", style="dashed")
    nx.draw_networkx_labels(g, pos, {v: f"{lbl(v)}\n d={deg[v]}" for v in nodes}, ax=ax, font_size=7)
    ax.set_title(title, fontsize=9); ax.axis("off")


def draw_rects(ax, rects, edges, title="", lost=None):
    """rects: pid -> (x0,x1,y0,y1) grid units; draws room cells and marks required edges."""
    W = max(r[1] for r in rects.values()); Hh = max(r[3] for r in rects.values())
    for pid, (x0, x1, y0, y1) in rects.items():
        rid = pid.split("#")[0]
        ax.add_patch(Rectangle((x0, Hh - y1), x1 - x0, y1 - y0, facecolor=color(rid), edgecolor="#222", lw=1.2))
    # merge labels per room
    byroom = {}
    for pid, r in rects.items():
        byroom.setdefault(pid.split("#")[0], []).append(r)
    cent = {}
    for rid, rs in byroom.items():
        big = max(rs, key=lambda r: (r[1] - r[0]) * (r[3] - r[2]))
        cx, cy = (big[0] + big[1]) / 2, Hh - (big[2] + big[3]) / 2
        cent[rid] = (cx, cy)
        ax.text(cx, cy, lbl(rid) + ("\n(L)" if len(rs) > 1 else ""), ha="center", va="center", fontsize=7)
        if len(rs) > 1:  # erase the internal seam of an L room
            a, b = rs
            if a[1] == b[0] or b[1] == a[0]:
                x = a[1] if a[1] == b[0] else b[1]
                ya, yb = max(a[2], b[2]), min(a[3], b[3])
                ax.plot([x, x], [Hh - ya, Hh - yb], color=color(rid), lw=3)
            else:
                y = a[3] if a[3] == b[2] else b[3]
                xa, xb = max(a[0], b[0]), min(a[1], b[1])
                ax.plot([xa, xb], [Hh - y, Hh - y], color=color(rid), lw=3)
    lostset = {frozenset(e) for e in (lost or [])}
    for a, b in edges:
        (xa, ya), (xb, yb) = cent[a], cent[b]
        col = "#d62728" if frozenset((a, b)) in lostset else "#2ca02c"
        ax.plot([xa, xb], [ya, yb], color=col, lw=1.4, ls="--" if col == "#d62728" else "-", alpha=0.85)
    ax.set_xlim(-0.2, W + 0.2); ax.set_ylim(-0.2, Hh + 0.2); ax.set_aspect("equal"); ax.axis("off")
    ax.set_title(title, fontsize=9)


def heuristic_rects(shape):
    """The production heuristic's slot grid (every row tiles the width; last cell absorbs the rest)."""
    rects = {}
    for s_idx, (r, c0, span) in enumerate(shape["slots"]):
        rects[shape["assignment"][str(s_idx)]] = (c0, c0 + span, r, r + 1)
    return rects


for bid in ("B10", "B13", "B15", "B16"):
    g = G[bid]; nodes = [r["id"] for r in g["rooms"]]; edges = [tuple(e) for e in g["spatial_adjacency"]]
    h = H[bid]; best = max(h["per_shape"], key=lambda s: s["score"])
    preserved = [tuple(e) for e in best["preserved"]]
    pset = {frozenset(e) for e in preserved}
    lost = [e for e in edges if frozenset(e) not in pset]
    d = LV[bid]["diag"]
    hl = set()
    for k4 in d["k4"]:
        hl |= set(k4)
    for (a, b), common in d["lens3"]:
        hl |= {a, b, *common}
    lv = LV[bid]["levels"]
    # minimal family witness
    fam, rects = None, None
    for f in ("band_y", "slicing", "rect"):
        if lv.get(f, {}).get("ok") and lv[f].get("rects"):
            fam, rects = f, lv[f]["rects"]; break
    if rects is None:
        for key in ("L1", "L2"):
            for r, v in lv.get(key, {}).items():
                if v["ok"]:
                    fam, rects = f"rect + L-shaped {r}", v["rects"]; break
            if rects: break
    fig, axes = plt.subplots(1, 4, figsize=(20, 5.2))
    draw_graph(axes[0], nodes, edges, highlight_nodes=hl,
               title=f"{bid}: required spatial adjacency (n={len(nodes)}, m={len(edges)})\nred ring = rectangular-dual obstruction (K4 / edge with 3 common neighbours)")
    draw_graph(axes[1], nodes, edges, preserved=preserved, lost=lost,
               title=f"best production GridWing search result: GRID {best['n_rows']}x{best['n_cols']}\ngreen = preserved {len(preserved)}, red dashed = lost {len(lost)}")
    draw_rects(axes[2], heuristic_rects(best), edges, lost=lost,
               title=f"that GridWing slot layout (rows x cols, topology only)\nlost edges drawn red")
    if rects:
        draw_rects(axes[3], rects, edges, title=f"EXACT witness: smallest family that carries all {len(edges)} edges\n{fam}")
    else:
        axes[3].text(0.5, 0.5, "no witness found", ha="center"); axes[3].axis("off")
    fig.tight_layout()
    fig.savefig(f"{OUT}/{bid}_failure.png", dpi=130)
    plt.close(fig)
    print("wrote", bid, fam)


# ---------------------------------------------------------------- B01: pinwheel refusal vs realized band layout
try:
    B = json.load(open("b01_realized.json"))
    g = G["B01"]; nodes = [r["id"] for r in g["rooms"]]; edges = [tuple(e) for e in g["spatial_adjacency"]]
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    draw_graph(axes[0], nodes, edges, title="B01: required spatial adjacency (n=5, m=6)")
    pin = {"KITCHEN": (0, 3, 0, 1), "HALL": (3, 4, 0, 3), "MASTER": (1, 4, 3, 4), "BATHROOM_1": (0, 1, 1, 4), "LIVING": (1, 3, 1, 3)}
    draw_rects(axes[1], pin, edges, title="production choice for n=5: PINWHEEL (topology OK 6/6)\nrefused SHORT_SIDE_INFEASIBLE in all 961 envelopes")
    r0 = B["realized"][0]
    rects = {k: (v[0], v[0] + v[2], v[1], v[1] + v[3]) for k, v in r0["rects_u"].items()}
    draw_rects(axes[2], compress(rects) if False else rects, edges,
               title=f"same graph as a GridWing band layout: REALIZED + validator PASS\n{r0['envelope_m'][0]}x{r0['envelope_m'][1]} m, spatial {r0['spatial']}, access {r0['access']} ({B['n_realized']}/{B['n_layouts']} band layouts dimension)")
    fig.tight_layout(); fig.savefig(f"{OUT}/B01_pinwheel_vs_band.png", dpi=130); plt.close(fig)
    print("wrote B01")
except FileNotFoundError:
    print("no b01_realized.json")
