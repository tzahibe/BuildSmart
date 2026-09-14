"""Hub v3 Phase 0 — bound per TOPOLOGY, with access seats and wet adjacency, not only shape.

    .venv/bin/python3 spikes/failure_log_sweep/hub_topology_bound.py [--wet 2|3] [--grid 0.5]

For each candidate hub tree and each representative outline, every free sizing decision (and every
admissible room-to-slot order) is enumerated on a coarse grid, the layout is built as rectangles,
and the SAME three facts the engine and the §6 gates care about are checked on those rectangles:

  geometry  every room at least its template minimum side (gross, incl. the 0.20 m allowance);
            lobby net aspect <= 1.5 and net area <= 16 m2; habitable rooms touch the envelope;
  access    every room that needs a lobby door shares >= 1.10 m of edge with the lobby
            (INTERIOR_DOOR_WIDTH_M + 2 * DOOR_MARGIN_M); the ensuite shares >= 1.10 m with its master;
  wet       a wet room "clusters" when it shares > 0.3 m of edge with a wet room or the kitchen (M5).

Reported per (topology, outline): the best reachable max aspect of the bedroom-class rooms among
layouts that pass geometry AND access, the master / safe-room aspects there, the wet adjacency at
that layout and the best wet adjacency reachable at all, seats seated vs required, and the
failure reason when nothing passes. Generous on purpose (rooms at minimums, coarse grid): a
topology that fails here fails in the engine; one that passes here still has to be built.

Topologies (front band L | D | K across the street side unless noted; lobby = HUB):
  T1  v2 stacked        [BED1 over BATH | HUB | BED2 (over TOILET)]   / [ENS | MASTER | SAFE]
  T3  no stacking       [BED1 | BATH | HUB | BED2]                    / [ENS | MASTER | SAFE] (+TOILET centre)
  T4  hybrid wet stack  [BED1 | BATH over ENS | HUB | BED2]           / [MASTER | SAFE] (+TOILET centre)
  T4b hybrid, 3 at foot [BED1 | BATH over ENS | HUB]                  / [BED2 | MASTER | SAFE] (+TOILET)
  T5  head-band bath    [LIV | BATH | DIN | KIT] / [BED1 | HUB | BED2]     / [ENS | MASTER | SAFE] (+TOILET)
  T2  side by side      public column | { [BATH | TOILET/–] / [BED1 | HUB | BED2] / [ENS | MASTER | SAFE] }  (control)
Foot-band orders are permuted; the ensuite must stay beside its master. Results and the reading
are in specs/005-hub-private-wing/RESULTS.md §7.
"""
from __future__ import annotations

import argparse
import itertools
import math
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

INSET = 0.20
OPENING = 1.10
HUB_WIDTHS = (3.0, 3.3, 3.6)
HUB_MAX_AREA, HUB_MAX_ASPECT, HUB_MIN = 16.0, 1.5, 2.4
MIN = dict(BED1=2.6, BED2=2.6, MASTER=3.0, SAFE=2.4, BATH=1.6, ENS=1.6, TOILET=1.1,
           LIV=3.0, DIN=2.6, KIT=2.4, HUB=2.4)
BEDROOM_CLASS = ("BED1", "BED2", "MASTER", "SAFE")
HABITABLE = BEDROOM_CLASS + ("LIV", "DIN", "KIT")
WET = ("BATH", "ENS", "TOILET")
NEEDS_LOBBY = ("BED1", "BED2", "MASTER", "SAFE", "BATH", "TOILET")
OUTLINES = ((14.25, 12.35), (18.0, 12.0), (13.0, 15.0), (12.0, 18.0), (10.0, 20.0), (14.0, 16.0))

Rect = tuple[float, float, float, float]  # x, y, w, h (gross)


def shared(a: Rect, b: Rect) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    if abs(ax + aw - bx) < 1e-6 or abs(bx + bw - ax) < 1e-6:
        return max(0.0, min(ay + ah, by + bh) - max(ay, by))
    if abs(ay + ah - by) < 1e-6 or abs(by + bh - ay) < 1e-6:
        return max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    return 0.0


def aspect(r: Rect) -> float:
    w, h = r[2] - INSET, r[3] - INSET
    return max(w, h) / max(min(w, h), 1e-6)


@dataclass
class Verdict:
    geometry: str | None      # failure reason, or None
    seated: int
    required: int
    wet_adj: float            # 0..1
    max_bedroom: float
    master: float
    safe: float


def evaluate(layout: dict[str, Rect], fw: float, fh: float, wet_rooms: tuple[str, ...]) -> Verdict:
    for name, r in layout.items():
        if r[2] < MIN[name] + INSET - 1e-6 or r[3] < MIN[name] + INSET - 1e-6:
            return Verdict(f"{name} below minimum ({r[2]:.2f} x {r[3]:.2f})", 0, 0, 0, 9, 9, 9)
    hub = layout["HUB"]
    if aspect(hub) > HUB_MAX_ASPECT + 1e-6:
        return Verdict("lobby aspect", 0, 0, 0, 9, 9, 9)
    if (hub[2] - INSET) * (hub[3] - INSET) > HUB_MAX_AREA + 1e-6:
        return Verdict("lobby area", 0, 0, 0, 9, 9, 9)
    for name in HABITABLE:
        if name not in layout:
            continue
        x, y, w, h = layout[name]
        if not (x < 1e-6 or y < 1e-6 or abs(x + w - fw) < 1e-6 or abs(y + h - fh) < 1e-6):
            return Verdict(f"{name} has no exterior wall", 0, 0, 0, 9, 9, 9)
    required = [n for n in NEEDS_LOBBY if n in layout]
    seated = sum(1 for n in required if shared(layout[n], hub) >= OPENING - 1e-6)
    if "ENS" in layout and shared(layout["ENS"], layout["MASTER"]) < OPENING - 1e-6:
        return Verdict("ensuite not beside its master", seated, len(required), 0, 9, 9, 9)
    wets = [n for n in wet_rooms if n in layout]
    adj = 0
    for n in wets:
        others = [m for m in list(wet_rooms) + ["KIT"] if m != n and m in layout]
        adj += any(shared(layout[n], layout[m]) > 0.3 for m in others)
    wet_adj = adj / len(wets) if wets else 1.0
    return Verdict(None, seated, len(required), wet_adj,
                   max(aspect(layout[n]) for n in BEDROOM_CLASS if n in layout),
                   aspect(layout["MASTER"]), aspect(layout["SAFE"]))


def grid(lo: float, hi: float, step: float):
    """`lo` itself (a room's exact minimum) and then the grid points above it, up to `hi`."""
    if lo > hi + 1e-9:
        return
    yield round(lo, 2)
    x = math.floor(lo / step + 1e-9) * step + step
    while x <= hi + 1e-9:
        yield round(x, 2)
        x += step


def hub_cap(hw: float) -> float:
    return min((hw - INSET) * HUB_MAX_ASPECT + INSET, HUB_MAX_AREA / (hw - INSET) + INSET)


def front_band(fw: float, band: float) -> dict[str, Rect]:
    """L | D | K across the street side; the living centred on the entrance (>= fw/2 + opening/2)."""
    liv = max(fw / 2 + OPENING / 2, MIN["LIV"] + INSET)
    rest = fw - liv
    if rest < MIN["DIN"] + MIN["KIT"] + 2 * INSET:  # narrow front: the closed-plan L | K programme
        return {"LIV": (0, 0, liv, band), "KIT": (liv, 0, rest, band)}
    din = rest * 14 / 27
    return {"LIV": (0, 0, liv, band), "DIN": (liv, 0, din, band), "KIT": (liv + din, 0, rest - din, band)}


def foot_orders(rooms: list[str]) -> list[list[str]]:
    """Every order of the foot band's rooms in which the ensuite stays beside its master."""
    out = []
    for p in itertools.permutations(rooms):
        if "ENS" in p and abs(p.index("ENS") - p.index("MASTER")) != 1:
            continue
        out.append(list(p))
    return out


def foot_layouts(order: list[str], x0: float, width: float, y: float, depth: float, lobby: Rect,
                 step: float):
    """Foot-band widths: door-needing rooms must reach the lobby, so the splits are searched
    inside windows around the lobby; wet rooms take their minimum width."""
    n = len(order)
    mins = [MIN[r] + INSET for r in order]
    if sum(mins) > width + 1e-9:
        return
    # split positions between consecutive rooms, on the grid
    def rec(i: int, x: float, acc: list[Rect]):
        if i == n - 1:
            w = x0 + width - x
            if w >= mins[i] - 1e-9:
                yield acc + [(x, y, w, depth)]
            return
        lo = x + mins[i]
        hi = x0 + width - sum(mins[i + 1:])
        for s in grid(lo, hi, step):
            yield from rec(i + 1, s, acc + [(x, y, s - x, depth)])
    for rects in rec(0, x0, []):
        yield dict(zip(order, rects))


def topo_T1(fw, fh, wet, step):
    """v2: [BED1 over BATH | HUB | BED2 (over TOILET)] / foot [ENS | MASTER | SAFE]."""
    foot_rooms = ["ENS", "MASTER", "SAFE"]
    for hw in HUB_WIDTHS:
        for hd in grid(MIN["BED1"] + MIN["BATH"] + 2 * INSET, hub_cap(hw), 0.25):
            for w in grid(MIN["BED1"] + INSET, fw - hw - MIN["BED2"] - INSET, step):
                e = fw - hw - w
                for d1 in grid(MIN["BED1"] + INSET, hd - MIN["BATH"] - INSET, 0.25):
                    for fd in grid(MIN["MASTER"] + INSET, fh - hd - (MIN["LIV"] + INSET), 0.25):
                        band = fh - hd - fd
                        base = front_band(fw, band)
                        base["BED1"] = (0, band, w, d1)
                        base["BATH"] = (0, band + d1, w, hd - d1)
                        base["HUB"] = (w, band, hw, hd)
                        if wet == 3:
                            base["BED2"] = (w + hw, band, e, d1)
                            base["TOILET"] = (w + hw, band + d1, e, hd - d1)
                        else:
                            base["BED2"] = (w + hw, band, e, hd)
                        for order in foot_orders(foot_rooms):
                            for foot in foot_layouts(order, 0, fw, band + hd, fd, base["HUB"], step):
                                yield {**base, **foot}


def topo_T3(fw, fh, wet, step):
    """No stacking: [BED1 | BATH | HUB | BED2] / foot [ENS | MASTER | SAFE] (+ TOILET at the foot)."""
    foot_rooms = ["ENS", "MASTER", "SAFE"] + (["TOILET"] if wet == 3 else [])
    for hw in HUB_WIDTHS:
        for hd in grid(MIN["BED1"] + INSET, hub_cap(hw), 0.25):
            for w in grid(MIN["BED1"] + INSET, fw - hw - MIN["BED2"] - MIN["BATH"] - 2 * INSET, step):
                for bw in grid(MIN["BATH"] + INSET, min(3.0, fw - hw - w - MIN["BED2"] - INSET), step):
                    e = fw - hw - w - bw
                    for fd in grid(MIN["MASTER"] + INSET, fh - hd - (MIN["LIV"] + INSET), 0.25):
                        band = fh - hd - fd
                        base = front_band(fw, band)
                        base["BED1"] = (0, band, w, hd)
                        base["BATH"] = (w, band, bw, hd)
                        base["HUB"] = (w + bw, band, hw, hd)
                        base["BED2"] = (w + bw + hw, band, e, hd)
                        for order in foot_orders(foot_rooms):
                            for foot in foot_layouts(order, 0, fw, band + hd, fd, base["HUB"], step):
                                yield {**base, **foot}


def topo_T4(fw, fh, wet, step, three_at_foot=False):
    """Hybrid: the shared bath stacked over the ENSUITE beside the lobby; the master under both.
    T4: [BED1 | BATH/ENS | HUB | BED2] / [MASTER | SAFE] (+TOILET);  T4b: no east flank, BED2 at the foot."""
    foot_rooms = ["MASTER", "SAFE"] + (["BED2"] if three_at_foot else []) + (["TOILET"] if wet == 3 else [])
    for hw in HUB_WIDTHS:
        for hd in grid(MIN["BATH"] + MIN["ENS"] + 2 * INSET, hub_cap(hw), 0.25):
            east_min = 0.0 if three_at_foot else MIN["BED2"] + INSET
            for w in grid(MIN["BED1"] + INSET, fw - hw - MIN["BATH"] - INSET - east_min, step):
                for bw in grid(MIN["BATH"] + INSET, min(3.0, fw - hw - w - east_min), step):
                    e = fw - hw - w - bw
                    if not three_at_foot and e < east_min - 1e-9:
                        continue
                    if three_at_foot and e > 1e-9:
                        continue  # the lobby reaches the east wall
                    for d1 in grid(MIN["BATH"] + INSET, hd - MIN["ENS"] - INSET, 0.25):
                        for fd in grid(MIN["MASTER"] + INSET, fh - hd - (MIN["LIV"] + INSET), 0.25):
                            band = fh - hd - fd
                            base = front_band(fw, band)
                            base["BED1"] = (0, band, w, hd)
                            base["BATH"] = (w, band, bw, d1)
                            base["ENS"] = (w, band + d1, bw, hd - d1)
                            base["HUB"] = (w + bw, band, hw, hd)
                            if not three_at_foot:
                                base["BED2"] = (w + bw + hw, band, e, hd)
                            for order in foot_orders(foot_rooms):
                                for foot in foot_layouts(order, 0, fw, band + hd, fd, base["HUB"], step):
                                    yield {**base, **foot}


def topo_T2(fw, fh, wet, step):
    """Control — public column beside the wing: [BATH | TOILET/–] / [BED1 | HUB | BED2] / foot."""
    foot_rooms = ["ENS", "MASTER", "SAFE"]
    for wp in grid(MIN["LIV"] + INSET, fw - 2 * (MIN["BED1"] + INSET) - min(HUB_WIDTHS), step):
        ww = fw - wp
        dl, dd = fh * 22 / 49, fh * 14 / 49
        pub = {"LIV": (0, 0, wp, dl), "DIN": (0, dl, wp, dd), "KIT": (0, dl + dd, wp, fh - dl - dd)}
        for hw in HUB_WIDTHS:
            for hd in grid(MIN["BED1"] + INSET, hub_cap(hw), 0.25):
                for head in grid(MIN["BATH"] + INSET, 3.0, 0.25):
                    fd = fh - hd - head
                    if fd < MIN["MASTER"] + INSET:
                        continue
                    for w in grid(MIN["BED1"] + INSET, ww - hw - MIN["BED2"] - INSET, step):
                        base = dict(pub)
                        # head band: the bath over the lobby (door on it), the rest a toilet or unused
                        base["BATH"] = (wp, 0, w + hw if wet == 2 else w + hw / 2, head)
                        if wet == 3:
                            base["TOILET"] = (wp + w + hw / 2, 0, hw / 2 + (ww - w - hw), head)
                        base["BED1"] = (wp, head, w, hd)
                        base["HUB"] = (wp + w, head, hw, hd)
                        base["BED2"] = (wp + w + hw, head, ww - w - hw, hd)
                        for order in foot_orders(foot_rooms):
                            for foot in foot_layouts(order, wp, ww, head + hd, fd, base["HUB"], step):
                                yield {**base, **foot}


def topo_T5(fw, fh, wet, step):
    """Head-band bath: the shared bath sits in the FRONT band beside the living room, over the
    lobby's head (its door on the lobby's top edge, next to the living room's cased opening), so
    the lobby band is a single unstacked row [BED1 | HUB | BED2]; foot [ENS | MASTER | SAFE]
    (+ TOILET at the foot for 3 wet). Band order [LIV | BATH | DIN | KIT]: the bath must sit over
    the lobby, so it separates the living from dining/kitchen (M6 contiguity is given up)."""
    foot_rooms = ["ENS", "MASTER", "SAFE"] + (["TOILET"] if wet == 3 else [])
    liv_w = max(fw / 2 + OPENING / 2, MIN["LIV"] + INSET)
    for hw in HUB_WIDTHS:
        for hd in grid(MIN["BED1"] + INSET, hub_cap(hw), 0.25):
            for bw in grid(MIN["BATH"] + INSET, min(2.5, hw - OPENING), step):
                for w in grid(MIN["BED1"] + INSET, fw - hw - MIN["BED2"] - INSET, step):
                    # band [LIV | BATH | DIN | KIT]: the bath [liv_w, liv_w + bw] and the living
                    # must each share an opening with the lobby's top edge [w, w + hw]
                    if liv_w - w < OPENING - 1e-9 or w + hw - liv_w < OPENING - 1e-9:
                        continue
                    e = fw - hw - w
                    for fd in grid(MIN["MASTER"] + INSET, fh - hd - (MIN["LIV"] + INSET), 0.25):
                        band = fh - hd - fd
                        rest = fw - bw - liv_w
                        if rest < MIN["DIN"] + MIN["KIT"] + 2 * INSET:
                            continue
                        din = rest * 14 / 27
                        base = {"LIV": (0, 0, liv_w, band), "BATH": (liv_w, 0, bw, band),
                                "DIN": (liv_w + bw, 0, din, band), "KIT": (liv_w + bw + din, 0, rest - din, band),
                                "BED1": (0, band, w, hd), "HUB": (w, band, hw, hd),
                                "BED2": (w + hw, band, e, hd)}
                        for order in foot_orders(foot_rooms):
                            for foot in foot_layouts(order, 0, fw, band + hd, fd, base["HUB"], step):
                                yield {**base, **foot}


def engine_t1(fw: float, fh: float, wet: int):
    """T1 through the ENGINE's own `hub_bound` (feature 008) — one model, not two; the local
    `topo_T1` generator above is kept only as the Phase 0 record."""
    from app.vertical_slice import concept_generator as cg
    from app.vertical_slice.spec import ArchitecturalSpec, PlotSpec, ProgramSpec
    spec = ArchitecturalSpec(plot=PlotSpec(20.0, 24.0), program=ProgramSpec(
        bedrooms=3, safe_room=True, wet_rooms=wet, open_plan_living=True, target_built_area_m2=180.0))
    rooms = cg.build_room_program(spec)
    rooms = [cg.ProgramRoom("HALL", cg.ProgramRole.HALL, cg.ZoneGroup.CIRCULATION, cg.HUB_TEMPLATE)
             if r.group is cg.ZoneGroup.CIRCULATION else r for r in rooms]
    b = cg.hub_bound(rooms, fw, fh, cg._HUB_WIDTHS_M)
    v = Verdict(None, b.seated_doors, b.required_doors, b.best_wet_adjacency, 9.0, 9.0, 9.0)
    g = (Verdict(None, b.seated_doors, b.required_doors, b.best_wet_adjacency, b.gated_bedroom_aspect,
                 b.gated_master_aspect, b.gated_safe_aspect) if b.gated_bedroom_aspect is not None else None)
    return v, g, b.best_wet_adjacency, None, b.evaluated


TOPOLOGIES = {
    "T1 v2 stacked": topo_T1,
    "T3 no-stack": topo_T3,
    "T4 hybrid wet stack": topo_T4,
    "T4b hybrid, BED2 at foot": lambda fw, fh, wet, step: topo_T4(fw, fh, wet, step, three_at_foot=True),
    "T5 head-band bath": topo_T5,
    "T2 side-by-side (control)": topo_T2,
}


def bound(topo, fw, fh, wet, step):
    wet_rooms = ("BATH", "ENS") + (("TOILET",) if wet == 3 else ())
    best = None          # fully feasible: (max_bedroom, -wet_adj, verdict)
    best_gated = None    # fully feasible AND wet adjacency >= 80 %: the §6-gated bound
    best_wet = 0.0       # best wet adjacency among fully feasible layouts
    most_seated = (-1, None)
    geo_fail = {}
    n = 0
    for layout in topo(fw, fh, wet, step):
        n += 1
        v = evaluate(layout, fw, fh, wet_rooms)
        if v.geometry:
            geo_fail[v.geometry.split(" (")[0]] = geo_fail.get(v.geometry.split(" (")[0], 0) + 1
            continue
        if v.seated > most_seated[0]:
            most_seated = (v.seated, v)
        if v.seated < v.required:
            continue
        best_wet = max(best_wet, v.wet_adj)
        key = (round(v.max_bedroom, 2), -v.wet_adj)
        if best is None or key < best[0]:
            best = (key, v)
        if v.wet_adj >= 0.8 - 1e-9 and (best_gated is None or key < best_gated[0]):
            best_gated = (key, v)
    if best is None:
        if most_seated[1] is not None:
            v = most_seated[1]
            reason = f"access: {v.seated}/{v.required} rooms reach the lobby"
        elif geo_fail:
            reason = "geometry: " + ", ".join(f"{k} x{c}" for k, c in sorted(geo_fail.items(), key=lambda t: -t[1])[:2])
        else:
            reason = "no layout on this grid"
        return None, None, best_wet, reason, n
    return best[1], (best_gated[1] if best_gated else None), best_wet, None, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wet", type=int, default=2, choices=(2, 3))
    ap.add_argument("--grid", type=float, default=0.5, help="width grid (depths use 0.25)")
    ap.add_argument("--only", help="run one topology (prefix match, e.g. T1) — for a finer grid")
    args = ap.parse_args()
    print(f"brief: 3 bedrooms + safe room + {args.wet} wet rooms   width grid {args.grid} m\n")
    print(f"{'topology':28s} {'outline':13s} {'bed-class':>9s} {'master':>7s} {'safe':>6s} {'seats':>7s} "
          f"{'wet max':>8s} {'gated bed':>10s} {'g.master':>8s} {'g.safe':>7s}  result")
    print("  bed-class/master/safe: best max aspect of bedroom-class rooms among layouts passing geometry + access;"
          " gated: the same among layouts that ALSO reach >= 80 % wet adjacency")
    for name, topo in TOPOLOGIES.items():
        if args.only and not name.startswith(args.only):
            continue
        for fw, fh in OUTLINES:
            if name.startswith("T1"):
                v, g, best_wet, why, n = engine_t1(fw, fh, args.wet)   # the engine's bound (008)
            else:
                v, g, best_wet, why, n = bound(topo, fw, fh, args.wet, args.grid)
            outline = f"{fw:g} x {fh:g}"
            if v is None:
                print(f"{name:28s} {outline:13s} {'—':>9s} {'—':>7s} {'—':>6s} {'—':>7s} {100*best_wet:7.0f}% {'—':>10s} {'—':>8s} {'—':>7s}  FAIL {why}")
            else:
                gs = (f"{g.max_bedroom:10.2f} {g.master:8.2f} {g.safe:7.2f}" if g else f"{'—':>10s} {'—':>8s} {'—':>7s}")
                ung = (f"{v.max_bedroom:9.2f} {v.master:7.2f} {v.safe:6.2f}" if v.max_bedroom < 9
                       else f"{'(engine)':>9s} {'':>7s} {'':>6s}")
                print(f"{name:28s} {outline:13s} {ung} "
                      f"{v.seated:3d}/{v.required:<3d} {100*best_wet:7.0f}% {gs}  {'ok' if g else 'ok, but wet gate unreachable'}")
        print()


if __name__ == "__main__":
    main()
