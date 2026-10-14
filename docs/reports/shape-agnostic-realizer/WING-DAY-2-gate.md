# The 2D wing (stacks), day-2 gate: **STOP** — the mechanism works and wins one case; the gate (≤ 15 % room deviation on ≥ 3 cases) is not met, and the remaining deviation is not something a stack can reach

Owner: "continue with the experiment you recommend" (2026-10-14). Gate set in the #197 directive comment: day 2 — mean room deviation ≤ 15 % on ≥ 3 cases, no case lost; else STOP. Branch `feature/2d-wing`, commits 954fa95 (day 1) and the one carrying this file; data `data/wing-day1-target/`, `data/wing-day2-target/`.

## 1. What a stack is, and that it works

Two rooms in one band column, sharing its width and splitting its depth (`stacks.py`): one pseudo-zone for `embed_band` and production's SELECTION screen, two members for the exact sizer (`milp_heights(stacks=)`: unit-step height binaries whose sum is the band's height; member-level contacts — a member reaches the band above only from the top of its stack; the target objective sees each member's exact area), `expand_rects`/`expand_wings` (the column is its own wing, so C22 holds). Every stacked plan realized through the unchanged validators with every contact and door (`figures/wing/F2-L-envelope-fixed__BEDROOM_WING__stack.png`: the bath over the toilet in one column of the hall's band, in the L). Day 2 added tiers (wet → public → bedroom pairs, one pair per tier, both orders), the cheap feasibility screen before the exact placement, and the time budget inside the ladder. 5 tests.

## 2. The gate, measured (six, target objective; best plan per case by room deviation, any family)

| case | best plan | room dev | circ | smallest bedroom | gross | gate |
|---|---|---|---|---|---|---|
| F1 rect | spine BEDROOM_WING (day 3) — the stacked BEDROOM_WING V is second at **10.6 %** | **6.3 %** | 13.4 % | 99 % | 81.5 % | ✓ |
| F2 L | **stack** BEDROOM_WING, bath over toilet (was band TWO_HALL 21.7 %) | **16.9 %** | 12.8 % | 74 % | 86.6 % | ✗ (close) |
| F3 wide-shallow | spine BEDROOM_WING (no stack realized: 7 500 candidates, 0 past the screen) | 31.9 % | 19.4 % | 65 % | 97.7 % | ✗ |
| F4 entry court | band PUBLIC_BAND (5 stacked plans, best 20.6 %) | 18.7 % | 17.2 % | 64 % | 85.8 % | ✗ |
| F5 garden court | band BEDROOM_WING (5 stacked plans incl. DINING over KITCHEN, best 27.2 %) | 23.6 % | 14.0 % | 79 % | 80.0 % | ✗ |

1 of 5 under 15 % (gate asked for 3). No case lost; every case's plan count grew (38 counted plans vs 20). Time: F1 408 s, F5 176 s — the exact objective per placement, ×6 stack options.

## 3. Why a stack cannot reach the rest (the per-room breakdown of the best plans)

| room | F1 | F2 | F3 | F4 | F5 |
|---|---|---|---|---|---|
| HALL | +29 % | +29 % | **+62 %** | **+46 %** | +12 % |
| LIVING | −30 % | −23 % | **−58 %** | **−50 %** | — |
| KITCHEN | −10 % | −29 % | −55 % | −49 % | — |
| DINING | — | — | −59 % | — | −50 % |
| bedrooms | ≈ 0 | −23/−26 % | — | −35 % | −21 % |
| wet rooms | ±7 % | −30 % (one) | ±40 % | — | +3 % |

Two facts, both geometric, neither about small rooms:
* **The hub hall is oversize** because it must span the width its neighbours need and take the band's full depth; the target objective penalises the overshoot but nothing in the family can make the hall shallower than its band or narrower than its contacts. A stack cannot hold the hall: a hub must touch bands above *and* below, and a stack member reaches only one of them.
* **The public rooms are undersize** because the street band is one row of full-depth rooms: a 46 m² living room at the band's 4.5 m depth wants 10 m of frontage next to a kitchen and a dining room that want theirs, inside a 14–16 m envelope. Stacking KITCHEN over DINING beside the living room was the day-2 bet; it realized only on F5 (HALL_SPINE partis) at 27–30 % — the band's depth is then set by the stack's two rooms, and the living room, still one row deep, gains little; the plans that would gain (a two-row-deep public band) fail the entrance/exposure screen or the band-depth windows before sizing (F3: 0 of 7 500 past the screen).

The lever those two facts point at is **a room that spans two bands' depth** (the living room two rows deep; the hall narrow and long across bands) — the vertical spine *is* that for the hall (F1's 6.3 % plan is the spine), and what the public band needs is the same cell-across-bands for a habitable room, not a stack. That is the general 2D wing (a room grid per band with cells spanning rows), roughly the GridWing machinery with the staircase alignment on top; it was costed at 2–3 days and the stack was its minimal first form.

## 4. Verdict

STOP, as the gate says. Kept: the stack (harness-only, tested; it is the right form for wet rooms and wins the L). Not continued: public-room and bedroom stacks (measured, no gain). Recommendation unchanged in direction, sharpened in content: the next experiment is *cells that span bands* for habitable rooms (living room two rows deep; the hall as a spine inside the band family), with the stack kept for the wet rooms — if the owner wants another time-boxed run. `scipy` remains harness-only (path C, owner).
