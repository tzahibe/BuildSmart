# #185 — BRANCHED end-to-end proof: **achieved**

One real, complete, **validator-PASS** BRANCHED plan for a frozen brief, rendered through the
product's own `DemoPlan` and visibly a different architectural idea from the production primary.

**No production file was changed.** Everything is in `backend/app/ai_harness/branched_proof/`.

---

## 1. The brief, justified before coding

**B06** — 3 bedrooms, 2 wet rooms, no safe room, not open plan, **13 × 24 m**. The deepest frozen
site; it hosts #184's measured 8.20 × 16.50 m branched envelope comfortably; its programme is inside
#185's bounded 3–4 bedroom scope; and production delivers 177.4 m² there as a baseline.

## 2. Result against every acceptance criterion

| # | criterion | result |
|---|---|---|
| 1 | all validators PASS, including C26 | **27 / 27 pass**, safety passes, `plan.ok = True`; **dead ends 0** |
| 2 | all rooms preserved | LIVING, KITCHEN, MASTER, BEDROOM_1, BEDROOM_2, BATH_1, BATH_2 all present; the programme's single `HALL` is realized as **two** circulation spaces, which is the parti |
| 3 | MASTER has legal direct access to ENSUITE | `MASTER–BATH_1` door, placeable |
| 4 | both circulation spaces joined by a real door | `HALL_A–HALL_B` door, placeable |
| 5 | within the site and room-size constraints | safety `rooms_inside_buildable` true, no offending rooms; every room inside its own template band |
| 6 | area comparable | **165.2 m²** against production's 177.4 (**93%**), and *smaller*, never oversized |
| 7 | access graph genuinely BRANCHED | `verify_class` returns `CirculationClass.BRANCHED` |
| 8 | renders through `DemoPlan`, visibly different | `figures/production-vs-branched-B06.jpg` |

## 3. The layout that worked

```
            LIVING  41.6        |     KITCHEN  23.9        public band, north
   -----------------------------------------------
     HALL_A  14.6  |  BEDROOM_1  13.9                      entry hall serving the bedrooms
             2.65 x 5.50        |  BEDROOM_2  13.9
   -----------------------------------------------
     HALL_B   9.4  |  MASTER  17.8  |  BATH_1  11.2        wing corridor serving the master suite
     BATH_2   5.6  |                                       and a wet room at its south end
```

Doors: `HALL_A–LIVING` (cased opening) · `LIVING–KITCHEN` · `HALL_A–BEDROOM_1` · `HALL_A–BEDROOM_2`
· `HALL_A–HALL_B` · `HALL_B–MASTER` · `HALL_B–BATH_2` · `MASTER–BATH_1`.

**Why this one worked where #185's first attempt did not.** Three changes, each removing a specific
conflict the previous variant hit:

1. **Both corridors in one column**, one directly above the other, so their shared wall is the full
   corridor width rather than the 0.60 m sliver that failed C7/C13.
2. **The master and its ensuite moved into the wing**, so the entry hall no longer has to be wide
   enough to carry them — which is what had pushed the plan past the bedroom size caps on a 13 m
   site — and the ensuite is entered from its host, satisfying C17.
3. **Bedrooms first, master block last** in the wing, so the master reaches the building's south
   edge and gets an exterior wall and a window (C19, C8). With the master at the top it was
   landlocked between the public band, the hall and its own ensuite.

Corridor ends: `HALL_A`'s north is the public opening and its south is the door to `HALL_B`;
`HALL_B`'s north is that same door and its south is `BATH_2`'s door. **Every end is served**, so
C26 reports zero dead ends — nothing was relabelled and `circulation_metrics` did the counting.

## 4. Architecturally different, not rearranged

| | production primary | BRANCHED |
|---|---|---|
| circulation | **one** corridor, 1.30 × 13.45 m | **two**: 2.65 × 5.50 m and 2.65 × 3.55 m, joined by a door |
| organisation | public block, bedroom strip beside one corridor | entry hall serving the bedrooms; a second corridor serving the master suite |
| public rooms | living and kitchen merged, 58.6 m² | separate living 41.6 and kitchen 23.9 |
| master | 16.8 m², off the single corridor | 17.8 m² **suite** with its own 11.2 m² bathroom at the plan's far end |
| leftover | **27.6 m² "unassigned"** | **none** |
| gross | 177.4 m² | 165.2 m² |

## 5. The envelope point, which was the last blocker

The compiler must be given a **feasible concept envelope**, not the primary's programme-capped wing
rectangle (#184's gate 4) and not an invented rectangle. With an invented 13 × 24 m rect all 27
validators passed but `safety.rooms_inside_buildable` was **false** — four rooms sat outside the
buildable region. Passing the real adapter candidate's rect (13.00 × 24.00 m at x = 4.00) placed the
plan correctly and `plan.ok` became true. Nothing about the plan changed; only where it was put.

## 6. What broader coverage would need

This is one brief and one programme shape. For coverage:

- **5–6 bedrooms** (explicitly out of scope here): the wing stack grows with the corridor's length,
  so this is tractable — unlike HUB_LOBBY, which is bounded by its own perimeter.
- **SAFE_ROOM**: it needs an exterior wall, so it would take a wing slot on the envelope edge; the
  tree already places the master that way, so the same slot rule should carry it.
- **Open-plan briefs**: the public chain already emits an open group; untested here because B06 is
  not open plan.
- **Reachability in production**: #184's gates 1, 3 and 4 remain. The compiler is still unreachable
  from the product because `_compiled_candidates_for` hands it the primary's rect. That wiring, not
  the tree, is what stands between this plan and a user seeing it.

## 7. Scope kept

No production code changed. No validator, room cap, door-width or Geometry Core change. No special
case for B06. BRANCHED enabled nowhere, production default untouched, and the house came out smaller
than the production primary rather than enlarged to pass.
