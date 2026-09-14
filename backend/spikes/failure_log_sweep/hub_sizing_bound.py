"""Exact bound: on a footprint, the best max-aspect ANY sizing of the v2 hub tree can reach.

    .venv/bin/python3 spikes/failure_log_sweep/hub_sizing_bound.py [W D [W D ...]]

Deliberately generous — no area-driven widths, every room only at its template minimum, and all
the wing's free decisions searched exhaustively on the 0.05 m grid: lobby width (the five
`_HUB_WIDTHS_M`), lobby depth up to its net-aspect/area caps, flank split, foot-band boundary
inside its opening window, foot depth. What comes out is therefore an upper bound on what sizing
alone can deliver under the v2 topology (west flank = bedroom over a wet room, east flank = one
bedroom, foot = ensuite | master | one more room), which is the v2.1 result in one number per
footprint: on the wide-shallow footprints the four bedroom-class rooms cannot all get under ~1.6.
"""
from __future__ import annotations

import math
import sys

INSET = 0.20
OPENING = 1.10          # INTERIOR_DOOR_WIDTH_M + 2 * DOOR_MARGIN_M
HUB_WIDTHS = (2.4, 2.7, 3.0, 3.3, 3.6)
HUB_MAX_AREA, HUB_MAX_ASPECT = 16.0, 1.5
BED_MIN, MASTER_MIN, X_MIN, WET_DEPTH, BAND_MIN = 2.6, 3.0, 2.4, 1.8, 3.2


def _aspect(w: float, d: float) -> float:
    return max(w, d) / max(min(w, d), 1e-6)


def bound(fw: float, fh: float, *, both_stacked: bool = False):
    """(max aspect over the four bedroom-class wing rooms, the sizing that reaches it) and the
    same with the living room included."""
    best4 = best5 = None
    for hub_w in HUB_WIDTHS:
        floor = round((BED_MIN + INSET + WET_DEPTH + INSET) / 0.05) * 0.05
        cap = min(math.floor(((hub_w - INSET) * HUB_MAX_ASPECT + INSET / 2) / 0.05) * 0.05,
                  math.floor((HUB_MAX_AREA / (hub_w - INSET) + INSET / 2) / 0.05) * 0.05)
        hub_d = floor
        while hub_d <= cap + 1e-9:
            usable = fw - hub_w
            w = BED_MIN + INSET
            while w <= usable - (BED_MIN + INSET) + 1e-9:
                e = usable - w
                stacked_d = hub_d - WET_DEPTH - INSET - INSET / 2
                wb = _aspect(w - INSET, stacked_d)
                eb = _aspect(e - INSET, stacked_d if both_stacked else hub_d - INSET / 2)
                b = w + OPENING
                while b <= w + hub_w - OPENING + 1e-9:
                    master, x = b - (WET_DEPTH + INSET), fw - b
                    if master >= MASTER_MIN + INSET and x >= X_MIN + INSET:
                        foot = MASTER_MIN + INSET
                        while foot <= fh - hub_d - BAND_MIN + 1e-9:
                            fd = foot - INSET / 2
                            ma, xa = _aspect(master - INSET, fd), _aspect(x - INSET, fd)
                            band = fh - hub_d - foot
                            la = _aspect(fw / 2 + OPENING / 2 - INSET, band - INSET)  # entrance-centred living
                            m4 = max(wb, eb, ma, xa)
                            m5 = max(m4, la)
                            at = dict(hub=(hub_w, round(hub_d, 2)), west=w, boundary=b, foot=foot,
                                      band=round(band, 2), west_bed=round(wb, 2), east_bed=round(eb, 2),
                                      master=round(ma, 2), x=round(xa, 2), living=round(la, 2))
                            if best4 is None or m4 < best4[0]:
                                best4 = (m4, at)
                            if best5 is None or m5 < best5[0]:
                                best5 = (m5, at)
                            foot = round(foot + 0.05, 2)
                    b = round(b + 0.05, 2)
                w = round(w + 0.05, 2)
            hub_d = round(hub_d + 0.05, 2)
    return best4, best5


def main():
    args = [float(a) for a in sys.argv[1:]]
    footprints = list(zip(args[::2], args[1::2])) or [(14.25, 12.35), (18.0, 12.0), (12.0, 18.0), (10.0, 20.0)]
    for fw, fh in footprints:
        for both in (False, True):
            b4, b5 = bound(fw, fh, both_stacked=both)
            print(f"\n{fw} x {fh}   both flanks stacked: {both}")
            print(f"  four wing rooms, best reachable max aspect {b4[0]:.2f}   at {b4[1]}")
            print(f"  ...living included                       {b5[0]:.2f}   at {b5[1]}")


if __name__ == "__main__":
    main()
