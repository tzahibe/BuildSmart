# Path B, day-2 gate: **GO** — the spine family solves F1/F3/F4, and a harness defect (one door declared twice) was what refused F2 and F4 in *both* families; with it fixed, the frozen six stand at 5/5 feasible cases solved, every case under 30 s

Owner directive (#197, 2026-10-13): path B — a 2D wing per band / vertical spine — three days, same frozen six, gate at day 2 ("F2 or F4 solved → continue, else STOP").
Branch `feature/architectural-brain`, worktree commit below. Everything here runs through the UNCHANGED validators, doors, windows and area verdicts; no validator, policy or room bound was weakened; nothing names a shape.

## 0. The correction first

Frozen-six **v1.1** (declared on day 4 of the spike) added `access_extra: [[KITCHEN, LIVING]]` to F2 and F4. Every brain parti already carries `LIVING–KITCHEN`. The harness concatenated the two orderings into the access list, `realize_cells` generated **two doors on the same wall**, and C28 ("door swing envelopes overlap") refused every sized candidate of F2 and F4 — in the band family *and* in the spine family. The refusal was typed and visible (`VALIDATION_FAILED` counts in the stage tallies) but I attributed it to the band family's exposure/entrance limit without reading the validator text. That attribution in `GATE-3-verdict.md` ("F2/F4 … blocked by exposure/entrance in the band family") is therefore **partly wrong**: the selection screen *did* reject most candidates on exposure/entrance, but the ones that survived were killed by the duplicate door, not by the family.

Fix (`run.py`): one door per unordered pair — a case extra that repeats a parti pair the other way round is the same door. The six cases are unchanged (v1.1); only the harness's reading of them is corrected. After the fix the band family alone solves F2 (TWO_HALL, 4 bands, 11/11 contacts, 11/11 doors, 81.8 %) and F4 (3 plans).

Lesson recorded in memory: *a validator refusal on a sized candidate must be read before it is attributed to a family.*

## 1. What path B built (all under `backend/app/ai_harness/shape_agnostic/`, harness-only; `scipy` stays undeclared)

| piece | what it is | the rule it honours (none new) |
|---|---|---|
| `spine.py` — `SpineLayout` | a run of bands (the **section**) in which one circulation cell spans every band between shared column nodes `xa, xb`; each section band = left part \| spine \| right part; plain full-width bands may sit above (street) and below (back) | — |
| `embed_spine` | reuses `embed_band` per side **component** (rows stacked, one block per component) and per plain group; a spine neighbour is innermost on its side or in the plain band touching the section's end | contact graph |
| C22 fact | an occupied left and right side run the **same number of bands** (the spine's wall is one type per side) | C22 / one-wall-type-per-side |
| entrance fact | a spine that fronts the street is the arrival room (HALL outranks LIVING) and must be **three door widths** wide; otherwise the street band holds an arrival room; a **foyer** (CIRCULATION off the spine) must front the street | `doors.resolve_entrance`, `ENTRANCE_ZONE_PRIORITY` |
| `milp_oracle.py` — `_spine_once` | the aligned MILP with shared nodes; alignment of a band edge that *is* `xa`/`xb` holds by identity (this was the "INFEASIBLE with alignment" of day 1); the spine's net area / short side / aspect are **exact** through McCormick products `p = w·z` (no height windows); `_skip` is a diagnostic hook naming constraint groups | C3, C20, door widths |
| `milp_spine_placement` | the inset fixed point; an exact-inset INFEASIBLE is returned as such, never replaced by the loose estimate | C3 |
| `spine_intents` | the spine's intent declared as a corridor: `max_aspect_ratio = 6.0`, every other bound the programme's | — |
| `spine_geometry` | cell rects + wings (one per plain band, per left part, per right part, and the spine) → `realize_cells`, unchanged | — |
| `run.py` — `_spine_family`, `_spine_selection` | production's SELECTION questions asked of a spine layout before sizing: entrance feasible (both orientations), every REQUIRED-exposure room and the safe room on the envelope, foyer at the street; both orientations, the Stage 3 ladder, budgets | `placement_flags` |

Tests: `tests/vertical_slice/test_spine_embedding.py` (8), `test_milp_spine.py` (8, `importorskip("scipy")`) — realization with every contact and door on a rectangle, an L and an entry court; the section/wing invariants; the exact-inset refusal policy; the walk at the door (below). Whole `tests/vertical_slice`: 1221 passed, 1 skipped, 9 xfailed.

**A production defect found on the way and fixed in both realizers** (`rectilinear_realizer.py`): `_build_site` placed the entrance walk at the footprint's centre and neither `realize_cells` nor `realize_layout` replaced it with the walk to the door `resolve_entrance` chose — the drawing showed the path landing on a bathroom while the door was in the living room. The site now carries the resolved walk (`dataclasses.replace(site, entrance=entrance)`), so the payload, the renderer and C18/C11 see the real walk.

## 2. The frozen six, final run (`data/spine-day2/`, both families, main-venv interpreter)

| case | expected | solved | by | best plan | contacts / doors | gross | s |
|---|---|---|---|---|---|---|---|
| F1 rect | FEASIBLE | **yes** | band 8 + **spine 3** | spine HALL_SPINE+FOYER, section rows 1–5, arrival ENTRY | 9/9 · 9/9 | 71.9 % | 17.9 |
| F2 L | FEASIBLE | **yes** | band (TWO_HALL, 4 bands) | arrival LIVING | 11/11 · 11/11 | 81.8 % | 29.0 |
| F3 wide-shallow | FEASIBLE | **yes** | **spine** BEDROOM_WING + band SERVICE_CORE | spine: arrival LIVING | 16/16 · 12/12 | **103.7 %** | 28.1 |
| F4 entry court | FEASIBLE | **yes** | band 3 + **spine 1** | band PUBLIC_BAND+FOYER arrival ENTRY; spine BEDROOM_WING | 15/15 · 11/11 | 76.8–86.2 % | 27.8 |
| F5 garden court | FEASIBLE | **yes** | band 3 | PUBLIC_BAND / BEDROOM_WING / TWO_HALL+FOYER | 10/10 · 8–10 | 66–80 % | 10.3 |
| F6 K4 | UNSAT | refused | representation | — | — | — | 0.0 |

Day-2 gate: **F4 solved by the spine → GO.** Gate 3's own bar — ≥5/6 usable, ≤30 s/case — is now met numerically (5/5 feasible solved, max 29.0 s). Quality is a separate question (§4).

Renders (`figures/spine-day2/`): `F2-L-envelope-fixed__TWO_HALL__band.png` (an L-house: public band at the street, the second hall in the leg), `F4-entry-court-notch__BEDROOM_WING__spine.png` and `F4…__PUBLIC_BAND+FOYER__band.png` (front door in the court, into the foyer), `F3-wide-shallow-free__BEDROOM_WING__spine.png` (central corridor, bedroom wing south, public rooms north, safe room on the envelope), `F1-rect-control__HALL_SPINE+FOYER__spine.png`.

## 3. Where the spine stops, precisely

* **F2 (the L) is not solved by the spine** — 0 feasible of 1 236 sizings. Diagnosis by constraint group (`_skip`): dropping the *room* bounds makes the layouts feasible; dropping alignment, contacts, envelope or the spine's own bounds does not. In the 8 m leg, "room | corridor | room" does not fit the programme's rooms (bedroom ≥ 11.7 m² at ≥ 2.6 m ⇒ ≈ 4.5 m wide; 4.5 + 1.8 + 4.5 > 8), and a *single-loaded* corridor in the leg is exactly what C22's one-wall-type-per-side fact forbids for one spine cell (its east wall would be partition in the wide part, exterior in the leg). The band family's TWO_HALL parti gets the L because its second hall *is* a separate cell in the leg. The shape-agnostic generalisation is a **two-section spine** (HALL spine in one run of bands, HALL_B spine in the next, each with uniform sides) — the brain already proposes TWO_HALL; not built (day 3 candidate, ~1 day).
* **F5 (garden court)** — 0 feasible of 568: the court splits the depth and the spine needs a contiguous run of bands beside it; the band family's BAND_GAP handling solves it. A spine beside a court is the same two-section idea.
* **V orientation** — the embedding's entrance rule assumes the street at the top; across the street the fronting cells are the outer-left ones and `x == min x` is not guaranteed, so 11 F1 sizings were refused `NO_ENTRANCE` after being sized. Correct, just wasteful.
* **Time** — the first integration spent ~10 min/case inside `embed_spine` (4⁹ side assignments × `embed_band` over large plain groups). Capping plain bands at two components per side brought it to 1–2 s/parti; the budgets (`SPINE_MAX_LAYOUTS = 40`, `SPINE_BUDGET_S = 90`) were never hit in the final run.

## 4. Quality, honestly

Same picture as Gate 3: valid, not yet credible. Bedrooms sit at their minima (9.1–10.4 m²), the spine corridor is the elastic filler again (F3: 11.5 × 2.6 = 29.9 m²; F4: 10.25 × 2.75 = 28.2 m²) because the area objective excludes circulation and the hall's band is the only thing bounding it; gross area 66–86 % except F3. The spine fixes *topology* (a hub that reaches the street, interior rooms with an exterior wall, the foyer at the door); it does not yet fix *proportion*. That is the A1 item (heights in the objective, circulation minimised explicitly) — not done on day 2.

## 5. Day 3 (within the three days)

1. A1: the objective — maximise room area with heights in it and minimise the spine's area explicitly; measure on the same six.
2. Two-section spine (F2/F5-class envelopes) if the owner wants the spine itself, not the band family, to carry the L; otherwise leave it: the six are solved.
3. Report, then STOP at the time-box.

Knowledge preflight: index unchanged (no new docs since the Gate-3 run); canonical pages: `docs/wiki/features/*` for the realizer; RAG not used; verified against code: `doors.resolve_entrance`, `exposure_policy.REQUIRED_EXTERIOR_ROLES`, `validation.py` C22/C28/C18, `rectilinear_realizer._build_site`.
