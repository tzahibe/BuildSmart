# Feature Specification: Hub-Organised Private Wing

**Feature Branch**: `005-hub-private-wing`

**Created**: 2026-09-11

**Status**: v1 implemented and measured 2026-09-11 — **not accepted** (2 of 8 quality gates failed; see [RESULTS.md](./RESULTS.md) §3). Spec stands for v2 with the scope note in §11.

**Input**: Stage-0 measurement of the engine's 85 delivered plans against a visual census of 21 professional Israeli house plans (see `memory: architectural-quality-gaps-measured`). The one structural gap: the engine organises the private wing as a straight hall spine (hall long/short median 9.4, compact hubs 0%); the references organise it around a compact room lobby (~18/21 plans, 0 straight double-loaded corridors). This spec defines that hub as a new parti, in the engine's own representation, with the parameters the references measured.

---

## 1. What the references show *(the evidence this spec is built on)*

| Property | Reference census (21 plans) | Engine today (85 plans) |
|---|---|---|
| Private-wing circulation | Compact "room lobby" (מבואת חדרים) or TV room, ~2.5–3.5 m square, in **~18/21**; ring around a patio in 2; straight double-loaded corridor in **0** | One hall spine, full footprint depth, long/short **9.4** |
| Doors opening onto it | **4–7**, median ~5 | 7 (all on one strip) |
| Rooms around it | Wrap it on **up to 3 sides**; 4th side faces the public zone / entrance lobby | Stacked in one column beside it |
| Bedroom proportions | ~1.0–1.35 | 1.26 (fine) |
| Public rooms | Kitchen is an L-counter inside one open volume | KITCHEN aspect 2.75, DINING 2.35 (strips) |
| Wet rooms | Back-to-back pair in **~20/21**; ~85–90 % adjacent to wet/kitchen/laundry; typically **at the head of the hub** | 40 % |
| Habitable rooms on the envelope | ~100 % | 100 % (not a gap) |
| Circulation share | ~8–14 % (estimate) | 11 % (not a gap) |
| Safe room | Labelled "bedroom / security room" in every plan that has one — it **is one of the bedrooms** | An extra room beyond the bedroom count |

Continuous reference figures (proportions, share) are visual estimates; the discrete ones (counts of hubs, doors, adjacencies, labels) are counted.

---

## 2. User Scenarios & Testing *(mandatory)*

### User Story 1 — A brief with 3+ bedrooms gets a hub-organised private wing (Priority: P1)

A person asks for a house with several bedrooms and wet rooms. The private wing that comes back is organised the way an architect would draw it: a compact lobby that the bedrooms open onto from around it, not a long corridor with rooms in a line.

**Why this priority**: it is the single largest measured gap between the engine and professional plans, and it is the change that gives near-square rooms, clustered wet rooms and short circulation *as consequences* rather than as separate fixes.

**Independent Test**: generate plans for the 85 scenarios that plan today plus the 46 that still fail with no diagnosis; measure with the Stage-0 metric script; the acceptance metrics in §6 must hold.

**Acceptance Scenarios**:

1. **Given** a brief with ≥3 bedrooms, **When** a plan is produced by the hub parti, **Then** the private wing contains a circulation zone with long/short ≤ 1.5, short side ≥ 2.4 m, area 6–12 m², onto which **every** private and service room (except an ensuite, which opens from its bedroom) has a realised door.
2. **Given** the same brief, **Then** the hub has between 4 and 7 realised doors, and at most one of them leads to the public zone.
3. **Given** the same brief, **Then** every habitable room still touches the building envelope (no regression on the 100 % exposure the engine already achieves).
4. **Given** the same brief, **Then** the plan passes every existing validation check (C5 reachability, C13 realised connectivity, C14 corridor width, C15 relationships) unchanged — the hub is validated by the checks that exist, not exempted from them.

### User Story 2 — Wet rooms cluster at the head of the hub (Priority: P2)

**Acceptance Scenarios**:

1. **Given** a brief with ≥2 shared wet rooms, **Then** they occupy the hub's head band side by side, sharing an interior wall with each other, and each has a door onto the hub.
2. **Given** a brief with one shared wet room and a laundry, **Then** the two share the head band.

### User Story 3 — Master suite is one block (Priority: P2)

**Acceptance Scenarios**:

1. **Given** a brief with a master bedroom and ≥2 wet rooms, **Then** the ensuite shares the master's band, is entered from the master, and the master's door opens onto the hub (existing `entered_from` semantics, unchanged).

### User Story 4 — Nothing that plans today stops planning (Priority: P1)

**Acceptance Scenarios**:

1. **Given** the 418 failure-log scenarios, **When** the hub parti is added, **Then** every scenario that produced a plan before still produces one, and the refusal codes of the rest are unchanged or improved. The hub parti is an **additional** strategy; the existing partis are not modified.
2. **Given** a scenario the hub parti cannot serve, **Then** it rejects with one of the existing precise reason codes (`COLUMN_DEPTH_EXCEEDED`, `ROW_WIDTH_EXCEEDED`, …), carrying `shortfall_m`, so `_nearest_miss` ranks it like any other attempt.

---

## 3. Representation *(how the hub is expressed in the engine that exists)*

The engine lays rooms out as a **slicing tree** (`Split(Cut.H|Cut.V, …)` / `Leaf`) inside a rectangular `Wing`, with forced cut positions in metres (`_forced_chain`, `_forced_v_chain`), a programme-derived access graph (`_build_access`) and open groups whose members must be sibling leaves. A hub layout is expressible in exactly these terms, with no new geometric primitive:

```
              W_left     W_hub      W_right
           ┌──────────┬──────────┬──────────┐
  D_head   │  BATH    │  WC / LAUNDRY / BEDROOM …   │   head band  (V-split)
           ├──────────┼──────────┼──────────┤
  D_hub    │ BEDROOM  │   HUB    │ BEDROOM  │   hub band   (V-split; hub is the middle leaf)
           ├──────────┴──────────┴──────────┤
  D_foot   │  ENSUITE | MASTER   │ SAFE/BED │   foot band  (V-split)
           └──────────┴──────────┴──────────┘
                      ↕ public interface on one side of the hub band
```

- **Tree**: `Split(H, head_band, Split(H, hub_band, foot_band))`, each band a `_forced_v_chain`. This is the same "rows of a column" structure the engine already builds, with two differences: bands span the **wing's full width**, and the middle band's centre leaf is circulation.
- **Doors** exist where a room's x-range **overlaps the hub's x-range by at least the door clearance** (head and foot bands) or where the room shares the hub's full side (left/right rooms). The tree does not have to be re-shaped for doors; the allocation (§4) has to guarantee the overlaps.
- **Access graph**: a new circulation zone id `ROOM_LOBBY` (roles `HALL, CIRCULATION`) with `hall_for[room] = "ROOM_LOBBY"` for every private/service room; `_build_access` already takes `hall_for` per room and already handles `len(hall_ids) > 1` by chaining halls, so `hall_ids = ["HALL", "ROOM_LOBBY"]` where an entrance lobby exists, or `["ROOM_LOBBY"]` alone in v1 (hub opens directly onto the public zone through a cased opening — as in ~half the references).
- **Exposure by construction**: head band rooms touch the top edge, foot band rooms the bottom, left/right rooms the sides. Only the hub is interior. Interior *wet* rooms are permitted (references have them, mechanically ventilated) — see open question Q2.

### Why this and not "two rooms per row"

Sharing a row saves only the floor term of a column's depth (measured: closes 19 % of the remaining failures). The hub changes the **topology**: the wing's depth is three bands (~2.4 + ~3.4 + ~3.8 ≈ 9.6 m) regardless of bedroom count, because rooms are added **around** the hub — across the bands' widths — not stacked. That is what the references do, and it is why their 5–6-bedroom houses are no deeper than their 3-bedroom ones.

---

## 4. Requirements

### Functional

- **FR-1** A new `ConceptStrategy.HUB_PRIVATE_WING` is offered by `_allocations` / `generate_concepts` **in addition to** the existing partis. Existing partis are byte-identical.
- **FR-2** A hub `RoomTemplate` — `HUB_TEMPLATE` in `concept_generator.py` — of `min_short_side_m = 2.4`, `min_area_m2 = 6.0`, `target_area_m2 = 8.5`, `max_area_m2 = 12.0`, `max_aspect_ratio = 1.5`, `elasticity = 0.1` (circulation tier — never outranks a bedroom for surplus, per the existing ranking comment at the top of `ROOM_TEMPLATES`). The hub's `ProgramRoom` keeps `zone_id = "HALL"` and `role = ProgramRole.HALL` and carries this template instead of `ROOM_TEMPLATES[HALL]`; no new `ProgramRole` is added, so Geometry Core's `model.py` is untouched and every consumer keyed on the HALL role (C14, the twin's root→HALL rule, labels) works unchanged. The figures are reference-derived working values, flagged PRODUCT POLICY like every template row.
- **FR-3** Allocation places rooms into the three bands under these rules, in priority order:
  1. Shared wet rooms and laundry → head band, adjacent to each other (wet cluster).
  2. Master (+ ensuite in its band, entered from it) → foot band.
  3. Safe room → foot or hub band, never head band (RC envelope on the perimeter; reached from circulation, never through a bedroom — existing rule).
  4. Remaining bedrooms → hub band sides first (they come out `D_hub` deep and ≥2.6 wide → near-square), then head/foot bands.
  5. The public interface takes one **side** of the hub band (replacing a side bedroom) when the public zone is beside the wing; or the hub's **foot edge** when the wing sits behind a front public band (`FRONT_PUBLIC_BAND` already produces that geometry).
- **FR-4** Every room assigned to the head or foot band must have x-overlap with the hub ≥ `DOOR_SHARED_EDGE_MIN_M` (see Q1). Allocation orders rooms within a band so the ones needing the hub sit over it; a band member that cannot reach the hub is a **rejection**, not a room without a door.
- **FR-5** Hub degree is bounded: `4 ≤ doors ≤ 7`. Above 7 the parti rejects (`ACCESS_DEGREE_EXCEEDED` — the reason already exists).
- **FR-6** Sizing follows the existing pattern: `scale_program` for areas; band depths chosen directly (`_row_depths` semantics — area quotient floored by min short side), with the hub band's depth ≥ the deeper of the two side rooms' `min_short_side`; widths within a band from `_row_widths` (minimums first, surplus by area).
- **FR-7** Search variables, nearest-target-first and bounded like `_proportions` / `_seam_options`: footprint proportion (existing), hub width `W_hub ∈ {2.4 … 3.6}` at 0.3 m, band depths, and which side carries the public interface. Runtime budget: the parti may cost no more than the front-band parti does today per scenario (measure; see §7).
- **FR-8** Rejections carry the precise reason code and `shortfall_m` where measurable, exactly as the existing partis do after feature 004's refusal work.
- **FR-9** No change to `ROOM_TEMPLATES` rows that exist today. No change to `plan_layout`, `_plan_front_band`, `_seam_options`.

### Non-functional

- **NFR-1** Deterministic: same inputs → same plan.
- **NFR-2** Added latency on the happy path ≤ the cost of one additional strategy, measured on the 418-scenario sweep.

---

## 5. Reference-derived parameters *(numbers to build to)*

| Parameter | Value | Source |
|---|---|---|
| Hub short side | 2.4–3.6 m | census: ~2.5–3.5 m |
| Hub aspect | ≤ 1.5 | census: near-square; engine hall today 9.4 |
| Hub area | 6–12 m² | derived |
| Doors on hub | 4–7 | census median ~5 |
| `DOOR_SHARED_EDGE_MIN_M` | **1.10 m** = `INTERIOR_DOOR_WIDTH_M` 0.9 + 2 × `DOOR_MARGIN_M` 0.1 (`doors.py:24-26`; `placeable = shared_u >= width_u + 2*margin_u`, `doors.py:118`). `DesiredAccessEdge.min_clear_m` (0.9) is the declared intent; the placer's 1.1 m is what actually decides. Build to **1.1**. | Q1 — answered |
| Head band depth | max(wet min short side + inset, 2.2) ≈ 2.2–2.6 m | BATHROOM 1.6 / TOILET 1.1 templates |
| Hub band depth | ≥ 2.8 m (bedroom 2.6 + inset); target 3.4 | near-square bedrooms |
| Foot band depth | 3.5–4.2 m | MASTER template 3.0 min; census |
| Minimum wing width | `2.6 + 2.4 + 2.6 + 3 × 0.2 ≈ 8.2 m` | derived: side bedroom + hub + side bedroom |
| Rooms around a hub | 6–8 (1 + 1 + 2–3 + 2–3) | derived from overlaps at W_hub 3.0–3.6 |

The minimum wing width means: with the public zone **beside** the wing, the footprint must be ≥ ~12.5 m wide; with the public zone **in front** (front band), ≥ ~8.2 m. Both regimes are common in the failure log (widths 9–24 m).

---

## 6. Acceptance metrics *(measured with the Stage-0 script, not eyeballed)*

Run the Stage-0 metrics over every plan the hub parti produces, and over the whole 418-scenario sweep:

| Metric | Gate |
|---|---|
| Hub long/short | ≤ 1.5 in 100 % of hub plans |
| Doors on hub | 4–7 in 100 % |
| Wet-room adjacency | ≥ 80 % (engine today 40 %, reference ~85–90 %) |
| Bedroom aspect median | ≤ 1.35; master ≤ 1.40 (engine today 1.57) |
| Habitable rooms on envelope | 100 % (no regression) |
| Circulation share | ≤ 14 % (no regression; hub replaces the spine, does not add to it) |
| Scenarios that planned before | 111/111 still plan, primary design byte-identical (baseline after the unforced-twin change) |
| Newly planning scenarios | reported with built-area-vs-ask, per `planner-gains-must-be-quality-checked`; a "gain" under 80 % of the requested area is a regression |
| Test suite | 763 passed, 0 failed |

---

## 7. Verification plan

1. **Baseline** (exists): `scratchpad/phase2.json`, `final_sweep.py`, `quality_metrics.py`, `regression_ab.py` — re-run all four after implementation.
2. **Per-parti A/B**: hub parti enabled vs disabled (monkeypatch), 418 scenarios, diff of outcome tuples — the same discipline as phases 1–2.
3. **Latency**: sweep time with and without the parti; NFR-2.
4. **Pinned tests**: one test per user story above, each verified to fail with the parti disabled.

---

## 8. Out of scope *(explicitly deferred)*

- Non-rectangular envelopes (L/T/cross wings driven by daylight) — feature 006.
- Public zone as one open volume with an L-counter kitchen — feature 007.
- Separate entrance lobby + room lobby as two circulation zones (v2 of this feature; v1 opens the hub onto the public zone directly).
- Safe room counted as one of the bedrooms — a programme/product decision, to be measured on its own; it interacts with capacity and is not part of the geometry change.
- Ring circulation around a patio (2/21 references).
- Any change to existing partis, templates or the seam search.

---

## 9. Open questions — resolved from the code (2026-09-11)

- **Q1 — Door shared-edge minimum: 1.1 m.** `doors.py:118` places a door only when `shared_u >= INTERIOR_DOOR_WIDTH_M (0.9) + 2 × DOOR_MARGIN_M (0.1)`. `DesiredAccessEdge.min_clear_m = 0.9` (`model.py:300`) is intent only. **Consequence for §4/§5**: a head or foot band room needs ≥ 1.1 m of x-overlap with the hub; two doors on one hub edge therefore need `W_hub ≥ 2.2` plus the rooms' own widths — with `W_hub` 3.0–3.6 that is at most **two** rooms per head/foot edge, so hub degree is realistically 4–6 and FR-5's ceiling of 7 is reached only with a full-side room on each flank plus two above and two below. The allocator (FR-4) must reject, not shrink, when an overlap falls under 1.1 m; C13 will otherwise report "shares X m of wall but no placeable opening was generated".
- **Q2 — Interior wet rooms: permitted.** A wet room with no exterior wall gets `ventilation_status = MECHANICAL_VENTILATION_REQUIRED` (`windows.py:55,101,113`), a descriptive, non-regulatory label; no validation check or refusal keys on it. **Consequence**: wet rooms may sit in the hub band if the allocator needs it, but FR-3.1 keeps them in the head band by preference so they stay on the envelope (matches the references and keeps the label rare).
- **Q3 — FLEX: refuse, exactly as the front band does.** FLEX is `ZoneGroup.PUBLIC` and is injected as its own row (`concept_generator.py:1560-1573`) only when the target exceeds programme capacity. The hub parti organises the **private** wing; FLEX never belongs in it, and the public side of a hub plan is the existing public treatment. v1 refuses with `INSUFFICIENT_WING_AREA` and the same rationale string the front band uses, so over-capacity briefs keep going to the spine partis. **Consequence**: the hub parti will not touch the 197 over-capacity refusals — which is correct; those are an area problem the capacity message now explains.
- **Q4 — Hub ↔ public: `CASED_OPENING`.** It needs the same 1.1 m of shared wall as a door and nothing else. `OPEN_CONNECTION` is far stricter: `engine.py:376-386` requires the shared edge to equal the **full side of both rectangles**, which a hub flanked by rooms can never satisfy against a public zone. So v1 declares `HUB → LIVING` (or `HUB → HALL` where an entrance lobby exists) as `CASED_OPENING`, the kind the living room's own entrance already uses; the hub is **not** added to the public open group.
- **Q5 — Which briefs get the hub: measured on the refusals that remain generic after feature 004.** Of the 46 generic refusals, **25 fail at the concept stage** (no parti tiles them — the hub's territory) and **21 fail downstream**. The downstream group turned out to be the visible tip of a much larger population — 171 of the 256 concept-stage successes never became designs, 170 of them on "no split … at forced position" — with a single cause: forced cut positions computed from a flat wall allowance that Geometry Core, netting by actual per-side walls, cannot honour. That is addressed separately by appending every candidate's **unforced twin** after all forced trees (`_unforced` / `_free_twin` in `concept_generator.py`; cuts on the root→HALL path stay forced so the corridor's rectangle remains authoritative). **Measured baseline after that change, through the real service over the 418 scenarios: 85 → 111 plans; all 85 primary designs byte-identical; 26 new plans of which 17 deliver ≥ 80 % of the requested area (median 88 %) and count as gains; 0 lost.** The raw pipeline figure (219 solved without the service's capacity/outline logic) is an upper bound, not the baseline. The hub parti gets the same fallback for free: `generate_concepts` appends twins for every accepted candidate, so a hub tree with forced positions the solver refuses falls through to its unforced twin like any other. Acceptance in §6 therefore reads "111/111 still plan", not 85. Of the 25: bedrooms 1→7, 2→3, 3→6, 4→5, 5→1, 6→3. **Hub candidates (≥ 3 bedrooms): 15**, of which 14 are ≥ 8.2 m wide (front-band regime) and 3 are ≥ 12.5 m (side-by-side regime); one is 7.0 m wide, below the hub's minimum wing width. The 1-bedroom cluster (7, all `wet_rooms = 2`) is the brief family the research agent found plans **nowhere** at any area — that is a programme-construction defect to investigate separately, not a topology problem.
  **Rule adopted for v1**: offer the hub parti only for briefs with **≥ 3 bedrooms**; try it **before** the spine partis for those briefs so a hub plan is preferred when both exist; the sweep decides whether that ordering costs any scenario its plan (User Story 4). **Honest expectation**: the hub's rescue ceiling among today's generic refusals is ~14 scenarios; its main value is the quality of the 85 plans that already exist (hub aspect 9.4 → ≤ 1.5, wet adjacency 40 % → ≥ 80 %, master aspect 1.57 → ≤ 1.40), not the success rate.

---

## 11. v1 outcome and v2 scope (2026-09-11)

v1 — the "public band in front, lobby wing behind" tree with four lobby seats — was implemented
additively (existing plans 112/112 byte-identical, 0 lost, +0.02 s) and measured. It is safe but
not accepted: on the failure log it produces a hub candidate in 6/420 briefs and a realized hub
plan in 2, because ≥ 3-bedroom briefs there carry a safe room and 2–3 wet rooms (5–7 lobby doors
against 4 seats; 124 `ACCESS_DEGREE_EXCEEDED`); and on those 2 plans wet adjacency is 0 % and the
master's aspect 1.59, both by construction of the foot band (RESULTS.md §3). The lobby itself met
its targets (aspect 1.1, 5 doors, exposure 100 %, circulation 7 %, bedrooms 1.21).

v2 scope, in order: (a) two-room flanks (bedroom over bathroom at lobby depth ≈ 4.4 m; re-derive
`HUB_TEMPLATE.max_area_m2` from the census, since a near-square 3.0 × 4.4 lobby is 13 m²);
(b) the side-by-side regime with a head band for the wet cluster; (c) only then the ordering
question of when a hub plan should out-rank an area-closer spine plan.

**v2 (a) outcome, 2026-09-13 (branch `005-hub-v2`, RESULTS.md §5):** hub candidates 6 → 43,
delivered as the primary plan 0 → 17, +10 plans (7 counted), 0 lost, +5 % sweep time,
771 tests. On the 17 hub plans: lobby 1.4 / 100 %, 6 doors, exposure 100 %, circulation 8 %,
**wet adjacency 83 %** (v1: 0 %) — six of eight targets; bedroom 1.42 and master 1.50 miss
narrowly while beating the plans they replaced (1.50 / 1.60). Not merged: two targets short, and
7 production primaries now change to hub plans through the area-proximity sort, which makes (c) a
decision rather than a deferral. v2.1 lever for the two misses: a shape-aware share of surplus
width in `_plan_hub_wing` (flanks and foot), measured with the harness, not tuned.

## 10. Success definition

The hub parti is done when a 4-bedroom, 2-wet-room, safe-room brief on a 13 × 14 m footprint — which today plans as a 9.4-aspect spine with strip-shaped public rooms and 40 % wet adjacency — comes back with a 3 × 3.4 m room lobby, five doors on it, two wet rooms side by side at its head, a master suite at its foot, near-square bedrooms on its flanks, every habitable room on the envelope, all validation checks passing, and no scenario that planned before planning worse.
