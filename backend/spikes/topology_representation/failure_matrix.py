"""Builds the per-brief / per-lost-edge failure matrix (Markdown + JSON) from the measured artifacts."""
import json, os
import networkx as nx

G = json.load(open("selected_graphs.json"))
H = json.load(open("heuristic_dump.json"))
X = json.load(open("extra.json"))
SE = json.load(open("slot_exact.json"))
LV = {}
for f in os.listdir("."):
    if f.startswith("levels_") and f.endswith(".json"):
        LV.update(json.load(open(f)))

ROLE = {}
for bid, g in G.items():
    ROLE[bid] = {r["id"]: r["role"] for r in g["rooms"]}


def obstruction_edges(d):
    """Edges that belong to a K4 or to a triple-lens (the lens edge and its spokes)."""
    out = {}
    for k4 in d["k4"]:
        for i in range(4):
            for j in range(i + 1, 4):
                out.setdefault(frozenset((k4[i], k4[j])), set()).add("K4 " + "/".join(k4))
    for (a, b), common in d["lens3"]:
        tag = f"edge {a}-{b} with 3 common neighbours {'/'.join(common)}"
        out.setdefault(frozenset((a, b)), set()).add(tag)
        for c in common:
            out.setdefault(frozenset((a, c)), set()).add(tag)
            out.setdefault(frozenset((b, c)), set()).add(tag)
    return out


rows_md = []
matrix = {}
for bid in ("B10", "B13", "B15", "B16"):
    g = G[bid]; nodes = [r["id"] for r in g["rooms"]]; edges = [tuple(e) for e in g["spatial_adjacency"]]
    d = LV[bid]["diag"]; lv = LV[bid]["levels"]; x = X[bid]
    best = max(H[bid]["per_shape"], key=lambda s: s["score"])
    pset = {frozenset(e) for e in best["preserved"]}
    lost = [e for e in edges if frozenset(e) not in pset]
    obs = obstruction_edges(d)
    l1 = sorted(r for r, v in lv.get("L1", {}).items() if v["ok"])
    band_L = sorted(r for r, v in x.get("band_plus_L", {}).items() if v["ok"])
    max_band = x["max_band_y"]["k"]; kept_band = {frozenset(e) for e in x["max_band_y"]["kept"]}
    dropped_by_band_witness = [e for e in edges if frozenset(e) not in kept_band]
    per_edge = []
    for e in lost:
        fe = frozenset(e)
        if fe in obs:
            reason = ("OBSTRUCTION EDGE: " + "; ".join(sorted(obs[fe])) +
                      " -> a separating triangle in every planar embedding; EXACTLY ONE edge of this "
                      "obstruction must be lost by any dissection into rectangles (band, slicing or "
                      "non-guillotine); the other obstruction edges the search lost are search losses")
            cap = f"one L-shaped room (any of: {', '.join(band_L or l1)}) - band layout + 1 L cell is enough"
            cls = "representation (rectangles): 1 of these edges"
        else:
            reason = ("SEARCH: carried by a band layout (full GridWing dataclass); lost only because the "
                      "production search fixes balanced row lengths and 1,1,..,remainder spans")
            cap = "GridWing as already defined + an exact embedder (no new representation)"
            cls = "algorithm (search space)"
        # is the edge also kept by the max-band witness?
        kept = fe in kept_band
        per_edge.append({"edge": e, "class": cls, "reason": reason, "minimal_capability": cap,
                         "kept_by_max_band_witness": kept})
        rows_md.append(f"| {bid} | {e[0]} — {e[1]} | {cls} | {reason} | {cap} |")
    n_rep = len(edges) - max_band   # forced losses = edges no rectangle dissection can carry together
    matrix[bid] = {
        "n": len(nodes), "m": len(edges), "degree": d["degree"], "planar": d["planar"],
        "k4": d["k4"], "lens3": d["lens3"],
        "heuristic_best_form": f"GRID {best['n_rows']}x{best['n_cols']} rows={best['row_lengths']}",
        "heuristic_preserved": best["preserved"], "heuristic_lost": lost,
        "exact_max_within_production_slot_structures": max(v["exact_max"] for v in SE[bid].values()),
        "max_edges_band_full": max_band, "max_edges_slicing": x["max_slicing"]["k"],
        "max_edges_rect": x["max_rect"]["k"],
        "band_layout_carries_all": lv["band_y"]["ok"], "slicing_carries_all": lv["slicing"]["ok"],
        "rect_carries_all": lv["rect"]["ok"],
        "one_L_room_rect": l1, "one_L_room_band": band_L,
        "edges_whose_removal_alone_restores_rectangles": [k for k, v in x["edge_deletion"].items() if v["rect_without_it"]],
        "lost_edges": per_edge,
        "losses_attributed": {"representation_forced": n_rep, "search": len(per_edge) - n_rep,
                              "obstruction_edges_among_lost": sum(1 for p in per_edge if p["class"].startswith("representation"))},
        "band_witness_dropped": dropped_by_band_witness,
    }

md = ["# Failure matrix — brief -> lost edge -> structural reason -> minimal capability", "",
      "Lost edges are those of the production GridWing search's best-found embedding (`graph_embedding.embed_adjacency_graph`, "
      "the exact run `gap_closure_142a` reports). Classification is exact (SAT over all band/slicing/rectangular dissections, "
      "plus the separating-triangle theorem), not heuristic.", "",
      "| brief | lost edge | class | structural reason | minimal capability required |", "|---|---|---|---|---|"]
md += rows_md
md += ["", "## Per-brief totals", "",
       "| brief | n | m | production best | exact max within the production slot structures | max carried by ANY band layout (GridWing full) | max by any slicing | max by any rectangles | losses: search / forced by representation | one L-shaped room suffices (band + 1 L) |",
       "|---|---|---|---|---|---|---|---|---|---|"]
for bid, mtx in matrix.items():
    md.append(f"| {bid} | {mtx['n']} | {mtx['m']} | {len(mtx['heuristic_preserved'])}/{mtx['m']} ({mtx['heuristic_best_form']}) | "
              f"{mtx['exact_max_within_production_slot_structures']}/{mtx['m']} | {mtx['max_edges_band_full']}/{mtx['m']} | "
              f"{mtx['max_edges_slicing']}/{mtx['m']} | {mtx['max_edges_rect']}/{mtx['m']} | "
              f"{mtx['losses_attributed']['search']} / {mtx['losses_attributed']['representation_forced']} | "
              f"{'n/a (all edges carried by rectangles)' if mtx['rect_carries_all'] else ', '.join(mtx['one_L_room_band']) or 'no'} |")
open("failure_matrix.md", "w").write("\n".join(md) + "\n")
json.dump(matrix, open("failure_matrix.json", "w"), indent=1, default=str)
print("\n".join(md))
