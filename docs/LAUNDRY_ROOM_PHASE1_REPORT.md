# Laundry room — phase 1 report (demo/vertical_slice only)

**Date**: 2026-09-16 · **Branch**: `worktree-015-laundry-room-option`, off `main` @ `518e133` · **Scope**: `app.vertical_slice`/`app.demo` only, per instruction — `app.architect`/`app.geometry` untouched. Follows [docs/LAUNDRY_ROOM_OPTION_REVIEW.md](LAUNDRY_ROOM_OPTION_REVIEW.md)'s recommendation.

**State shipped**: `ProgramSpec.laundry` is a real, explicit requirement, threaded end to end from Hebrew text to the room programme — but `concept_generator.LAUNDRY_ROOM_ENABLED = False` keeps it unplanned for every real user until this report is acted on. **Nothing in this phase changes what a real user sees today.**

**Update (same day)**: §3 originally measured a 1/404 deviation from a fully general `ZoneGroup.SERVICE` row-rescue condition and left narrowing it as an open question. Directed to narrow it — `_ROW_RESCUE_ROLES` now names `(TOILET, LAUNDRY)` explicitly rather than the wider group; re-run against the same real corpus confirms this restores **0/404**. The verdict and §3 below reflect the narrowed, re-verified state.

**Correction (2026-09-16, post-review)**: this report originally called the corpus "418-context" in prose, copying the figure from `spikes/failure_log_sweep/README.md`/`ab.py`'s own historical docstrings (accurate as of THEIR measurement date). `app/data/failures.json` is a live, append-only production log — every sweep run in this phase (§3) was actually run against its state AT THAT TIME, which had already grown to **432 distinct, reproducible contexts** (750 raw log entries → 472 with every field `sweep.py`'s replay needs → 432 after de-duplication; the sweep script's own printed `scenarios: 432` line is the artifact this number is read from, not a re-run). §3's `404/432` figures were always correct; only the prose calling it "418-context" was stale. Fixed throughout below — **432 is this report's one denominator.**

---

## 0. Verdict up front

1. **The generic row-sharing solution works, and both TOILET's and BATHROOM's pre-existing behaviour are exactly unchanged.** `_ROW_RESCUE_ROLES = (ProgramRole.TOILET, ProgramRole.LAUNDRY)` — named explicitly after measurement showed the fully general `ZoneGroup.SERVICE` form also touched a lone BATHROOM in 1 of 404 real briefs. Re-verified against the same 432-context corpus after narrowing: **0/404** planned briefs changed, in either status or room signature. `hub_bound`'s own `ZoneGroup.SERVICE` use (§4) was NOT narrowed — it is inert for any laundry=NONE brief by construction, not measurement, so there was nothing there to fix.
2. **Hub topology needed no redesign.** `_hub_allocation`'s room-to-slot ranking was already role-agnostic; a laundry room fills exactly the seat a spare wet room would. Proven by a dedicated unit test, not just asserted.
3. **The room plans correctly when it plans**: 29/29 requested-and-planned cells in the synthetic matrix realised the laundry room inside its own template bounds, with HALL-only access, zero strip-shaped laundry rooms, zero ensuite-style dependents.
4. **It is not free.** Under a fixed target built area, adding the room measurably shrinks other rooms — **every one of the 29 planned-with-laundry cells** had at least one other room's area drop by more than 5%, commonly 15-35% and in a few cells 45-74% (FLEX and LIVING hit hardest). Two cells that planned without laundry were refused outright with it. This is how the deficit/area-budget machinery is SUPPOSED to behave under a fixed total — it is not a laundry-specific bug — but the magnitude is large enough that it is the central product question, not a footnote.
5. **Recommendation: KEEP GATED.** The code is correct, tested, measured to a literal zero-regression bar, and safe to merge as-is — `LAUNDRY_ROOM_ENABLED` stays `False`. Do not flip it on until the area-budget question in §4 has a product answer (does the target area grow to absorb the room, does the person get told what it costs, or is the crowding accepted as-is). BATHROOM's own eligibility for the row-sharing rescue is a live, separate question already being pursued as its own measured quality initiative (see project memory) — deliberately left there, not decided by this phase.

---

## 1. What was built

Per your 8-point spec, all in `app.vertical_slice`/`app.demo`:

- **§1 domain/requirement**: `LaundryDemand` (`NONE`/`ROOM`, `LAUNDRY_NICHE` deliberately not added) and `LaundryRequirement` (demand + `source_text`) in `spec.py`; `ProgramSpec.laundry`, default `NONE`. Parser: a new structured `laundry` field (`LaundryRoomDemand`, mirroring the existing `TaggedBool` convention) with explicit extraction rules — a named room ("חדר כביסה", "חדר שירות לכביסה") is `requested=True`; a bare appliance mention is not; removed from the `other_requests`/room_type example list since it is now a supported field. New parser-level tests (`test_requirements.py`) cover both the positive and the negative case through the full `/requirements` route.
- **§2 room programme**: `build_room_program` emits exactly one `ProgramRole.LAUNDRY` (`ZoneGroup.SERVICE`, `entered_from=None`) when `LAUNDRY_ROOM_ENABLED and program.laundry.demand is ROOM` — gated, additive, no change to any existing call.
- **§3 row-sharing generalisation**: `_rows_for_width`'s guard changed from `role is ProgramRole.TOILET` to `role in _ROW_RESCUE_ROLES` (`= (ProgramRole.TOILET, ProgramRole.LAUNDRY)`). The first cut of this used the wider, attribute-based `group is ZoneGroup.SERVICE` — the more principled form, no role named — but measurement (§3 below) found it also rescues a lone BATHROOM in 1 of 404 real briefs; narrowed to the two roles measurement actually cleared, on instruction, once that trade-off was surfaced. `_pair_with_dependent`/`_dependent_pairings` needed no change at all: they were already fully generic (confirmed by reading, and by the pre-existing `test_tier2_pairs_a_bedroom_with_the_ensuite_row...` test, which proves tier 2 already pairs bedrooms too) — the eligibility narrowing lives entirely in the one guard.
- **§4 hub**: `hub_bound`'s M5 wet-adjacency filter changed from a literal `(BATHROOM, TOILET)` tuple to `r.group is ZoneGroup.SERVICE`, computed from the actual room list already in scope — same reasoning as §3, no new tuple. `_hub_allocation` needed **zero changes**: its `rank()` function already sorts anything that isn't a bedroom or safe room into the generic "wet/service" bucket, so a laundry room fills a flank-bottom or foot-band seat exactly like a spare bathroom would. This is the one place the original review's "may need structural redesign" concern turned out not to apply — proven, not assumed (`test_hub_allocation_accepts_a_programme_with_a_laundry_room`).
- **§5 access**: nothing to write. `_build_access`'s existing rule — "circulation reaches every private and service room directly... [unless] `entered_from`" — already does exactly what was asked, because the laundry room is added with `entered_from=None`. Confirmed end to end (HALL-only access in every one of 29 realised cells).
- **§6 validation**: nothing to write. C20 (template aspect) and C21 (template hard-maximum) are already read off `ROOM_TEMPLATES[role]` generically — they cover LAUNDRY automatically. C17 (wet-room access) is explicitly scoped to `{BATHROOM, TOILET}` and was left untouched, so it correctly never looks at a laundry room — "laundry is a service room, not another bathroom" holds by construction, not by a new check. `wet_rooms.py`/`resolve_wet_rooms`/`check_wet_room_invariants` were not touched.
- **New tests**: `tests/vertical_slice/test_laundry_room.py` (15 tests: domain mapping, gate on/off, row-rescue for LAUNDRY, TOILET-unchanged re-proof, the explicit BATHROOM-exclusion proof, hub allocation, end-to-end access/shape, and a byte-identical proof for laundry=NONE at the single-scenario level) plus 3 new tests in `tests/test_requirements.py` for the parser/router path. **Full suite: 1238 passed, 9 xfailed (pre-existing, unrelated), 0 failures** — up from 1220/9/0 before this phase, i.e. every pre-existing test is still green.

## 2. Remaining unsupported partis

None found. Every parti this codebase has (spine variants, front band, hub, the L) reaches a laundry room through the same generic SERVICE-room machinery every bathroom/toilet already uses — there is no parti-specific gap to report. The only "unsupported" surface is the one you asked to leave alone: `LAUNDRY_NICHE` was not implemented, and `app.architect`/`app.geometry` was not touched.

## 3. Regression results — the real failure-log corpus

**Denominator, precisely** (`app/data/failures.json`, a live production log, as of this phase's measurement): 750 raw logged entries → 472 with every field the replay needs (278 skipped — missing a required field, never reproducible) → **432 distinct contexts** after de-duplication. Every sweep below runs all 432, and reports against that one number throughout — not the "418" figure quoted in this project's earlier, OLDER reports (`spikes/failure_log_sweep/README.md`, `ab.py`), which was accurate for the log's size when THOSE phases measured it; the log has grown with real usage since.

Method: `spikes/failure_log_sweep/laundry_gate_ab.py` (new — mirrors the existing `ab.py`'s A/B methodology). Every one of these real request contexts has `laundry` unset (the log predates this field) and the gate is off regardless, so this isolates exactly one question: **does generalising the row-rescue guard from `role is TOILET` change anything for a real, existing brief?** (`hub_bound`'s `ZoneGroup.SERVICE` use, §4, is a no-op **by construction**, not just by measurement, for any laundry=NONE brief — see the script's own docstring for the short proof, and it was never part of this A/B.)

**Round 1** (the fully general `group is ZoneGroup.SERVICE` form): 404/404 planned briefs kept their PLANNED status, but **1 changed its room signature** — `bed=1, wet=2, safe=False, open=False`, a 16×18 m footprint. Both before and after plan it and pass every validator; before leaves one BATHROOM alone in a 2.25×5.55 m row (aspect 2.47 — legal, not a strip, but elongated); after's generalised guard rescues it into the master's row instead, trading a better-shaped bathroom pair (aspect ~1.3 each) for a more elongated master bedroom (1.83 vs 1.56) and +1.5 m² of total delivered area. The same quality mechanism the 2026-09-14 WC fix already ships, now also reaching a BATHROOM for the first time — not a defect, but a genuine, measured deviation from "0 changes."

**Round 2** (directed: narrow `_ROW_RESCUE_ROLES` to `(TOILET, LAUNDRY)` by name, re-run against the same corpus):

| | OFF (pre-phase-1 TOILET-only guard) | ON (shipped, narrowed) |
|---|---|---|
| planned | 404 / 432 | 404 / 432 |
| status changed (planned/refused/crash) | — | **0 / 432** |
| planned-in-both, different room signature | — | **0 / 404** |
| total runtime | 2317 s | 2154 s (no regression) |

**Verdict: ZERO CHANGE.** Confirmed by re-running `laundry_gate_ab.py` against the shipped, narrowed code.

`test_toilet_rescue_is_unaffected_by_the_generalisation`, the new `test_a_lone_bathroom_is_deliberately_not_rescued_at_tier_one`, and the pre-existing `test_strip_rooms.py`/`test_hub_guard.py` (48 tests, unchanged) additionally confirm both TOILET's behaviour and BATHROOM's exclusion at the unit level, not just on the corpus.

## 4. Measured laundry quality — the synthetic matrix

Method: `spikes/failure_log_sweep/laundry_quality_matrix.py` (new). 2/3/4 bedrooms × 1-3 wet rooms × {narrow, wide, deep} rectangle footprints (27 cells), plus a 3BR × {1,2} wet-room L-parti subset (4 cells, matching this repo's own L fixtures' bedroom-count intent) — 31 cells, each run twice (laundry NONE vs ROOM, same target area), through the real service. `LAUNDRY_ROOM_ENABLED` patched on for this measurement process only.

**Planning rate**: NONE plans 31/31 (the baseline). ROOM plans 29/31 — two briefs already near their area capacity (3BR/3wet on a deep footprint; 4BR/3wet on a wide one) are refused outright once the laundry room is added, rather than delivering a degraded plan. That is the intended behaviour of this codebase's own "an honest refusal beats a plan at half the size" policy, not a bug.

**Shape and access, in every one of the 29 planned-with-laundry cells**:
- realised area 4.5-7.8 m² (template band 2.5-8.0), aspect 1.02-3.00 (template max 3.0 — the one cell AT 3.00 is exactly on the limit, not over it), short side 1.50-2.80 m (template floor 1.5 m — several cells sit exactly at the floor, expected, not a defect)
- **0** laundry rooms outside template bounds, **0** not accessed from HALL alone — §5/§6's guarantees hold empirically, not just in the unit tests that first proved them.

**Whether another room becomes materially worse — yes, essentially always**: **29 of 29** planned-with-laundry cells have at least one other room's area drop by more than 5% relative to the same brief without laundry. Representative range: bedrooms and bathrooms typically -10% to -25%; LIVING/DINING/KITCHEN -20% to -35% in several cells; FLEX (the deliberate surplus-absorber) took the deepest cuts, -56% to -74%, doing exactly the job its `elasticity=5.0` gives it — but even so, other real rooms absorbed a further 10-35% in the same cells. This is the deficit-distribution machinery working as designed under a FIXED target area (any new required room does this, not laundry specifically — see [[room-template-size-narrows-its-column]]), but the scale here is large enough to be the deciding product question for §5's recommendation, not a side note.

**Runtime**: median 3.68 s (NONE) → 5.12 s (ROOM) per brief — a real but modest cost, from the extra room in every layout attempt, not from anything pathological.

## 5. Recommendation

**KEEP GATED.** `LAUNDRY_ROOM_ENABLED` stays `False`; nothing here reaches a real user. The engineering is sound — generalised correctly, regression-tested against both the unit suite and the real 432-context corpus to a literal zero-change bar, hub verified rather than assumed, access/validation verified end to end. The regression question (§3) is closed. What is NOT yet decided is a product question this phase was not asked to answer:

1. **The area-budget interaction (§4) needs a decision before ENABLE is reasonable.** Options, not mine to pick: grow the effective target area when a laundry room is requested (by roughly the template's own target, ~4 m², as a starting estimate); tell the person up front what adding it will cost their other rooms; or accept the crowding as the same trade-off any other added room would cost. Shipping today would mean a person who asks for a laundry room silently gets a smaller living room or bathroom with no explanation.
2. **BATHROOM's own row-sharing eligibility** is a separate, real question this phase deliberately left alone (§3) — pursue it, if at all, through the row-sharing quality initiative already tracking it, not by re-widening this gate.

Once §4 is settled, ENABLE is a one-line flip (`LAUNDRY_ROOM_ENABLED = True`) with no further planner work expected — everything downstream (hub, access, validation, row-sharing) is already proven to hold.
