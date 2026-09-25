# Stage 0 (Issue #118, 1/2) — shipping the merged public room

The LIVING+KITCHEN merge spike #107 (`app/vertical_slice/room_merge.py`, Issue #102 §4.A) is
turned into a measured, gated product feature: `quality_metrics.py` and
`reference_benchmark.py` now read a merged room as ONE room, the 432-context corpus A/B below
decides the flag's default by a stated rule, and three before/after SVG pairs make the change
judgeable by eye.

**Issue #136 re-check note.** This branch later merged current main in (interior layout, C25,
master-suite access, wall classes) before landing on top of this report. Issue #136's own diff
touches only `app/vertical_slice/rectilinear_realizer.py` and
`spikes/geometry_shapes/stage1_gate.py` — neither is imported by any production path
(`RECTILINEAR_REALIZER_ENABLED` gates nothing today; no existing caller imports that module at
all, confirmed by a repo-wide search) — so #136's own changes cannot move this A/B's numbers, and
`room_merge.py`'s own merge-candidate gates (C6 seam-door, C1/C2/C3/C20/C27) are unrelated to C25/
entrance sequencing. A full re-run of the 432-context sweep this report is based on
(`spikes/failure_log_sweep/living_kitchen_merge_ab.py`, ~35-45 CPU-minutes) was NOT repeated in
this Issue's own session — out of #136's Verification Plan (only the frozen-corpus regression
check and the Stage 1 gate are), and a materially different cost than the rest of this Issue's
work. If the owner wants this A/B numerically re-confirmed against the fully merged base, the
sweep script above reproduces it unchanged.

## 0. Verdict up front

1. **`quality_metrics.py`/`reference_benchmark.py` now read a merged room as ONE room** (AC-1):
   own true area (`gross_area_m2`, not a bounding-box product) feeds M3/section B/section L, and a
   plan whose public zone collapses to a single merged room (no DINING) reads M6/section C as
   contiguous, not "nothing to measure." Proven by 3 new unit tests plus the corpus-level M6 move
   below.
2. **Measured over the full 432-context corpus** (AC-2): 191 merge candidates found, 168 (88%)
   applied, 23 (12%) rejected by their own checks (14 on C6 alone — a door already on the shared
   seam); **LOST 0, crashes 0, status_changes 0, refusal_code_changes 0**; 168/404 (42%)
   primary-signature changes, every one attributable to an applied merge (within the 200-change
   regression budget); no M1-M6 corpus statistic regressed — **M6 public-contiguous share actually
   IMPROVED, 52.7% → 94.3%**, exactly the bug AC-1's fix targets.
3. **The flip rule's own numbers say ON** (AC-3): every one of `decide_default`'s five conditions
   holds. `LIVING_KITCHEN_MERGE_ENABLED = True`, flipped in this same change set.
4. **Three before/after SVG pairs committed** (AC-4), §3.
5. **A real, orthogonal interaction found and fixed while flipping the flag**: two pre-existing
   tests (`test_demo_quality.py::test_every_room_width_depth_matches_its_area`, a general C27
   invariant predating merged rooms; `test_non_guillotine_reuse_spike.py`, Issue #108's own spike
   fixture) either assumed every room's `width_m × depth_m == area_m2` (false, by design, for a
   merged "L" room — its own `RoomOut` docstring already says so) or happened to contain a
   CLOSED_ADJACENT LIVING/KITCHEN pair unrelated to this Issue's own scope. Fixed narrowly: the
   dimension-product test now skips `shape == "L"` rooms (keeping the net-never-exceeds-gross
   check); the reuse-spike fixture's own tests disable the merge flag for themselves, since its own
   claim ("the existing pipeline accepts this fixture with ZERO code changes") predates and is
   orthogonal to Issue #118. Full fast suite: **1517 passed, 0 failed, 478 skipped, 9 xfailed**
   with the flag ON.

## 1. What changed (AC-1)

`spikes/failure_log_sweep/living_kitchen_merge_ab.py` (Issue #107's own spike sweep) already
proved the merge itself sound (191 candidates over the 432-context corpus, 168 applied, 23
rejected by their own checks, LOST 0, crashes 0). What this stage adds is the QUALITY REPORTING
side — the merged room must read as one room everywhere a plan's quality is measured, not as its
two now-nonexistent source rectangles:

- **`app/vertical_slice/quality_metrics.py`**:
  - `_hall_stats`'s plan-total-area denominator (M3's circulation share, and the compact-hall
    "wasted circulation" share) now sums each room's own `gross_area_m2` instead of
    `gross_width_m * gross_depth_m`. Identical for every ordinary RECTANGLE room (that product IS
    its `gross_area_m2`, by construction in `contract.py`) — but a merged "L" room's
    `gross_width_m`/`gross_depth_m` are only its bounding box (`RoomOut`'s own documented
    convention), which overstates a real, non-flush L's true footprint. Before this fix, a merged
    room's inflated bbox area silently understated M3's circulation share.
  - `_public_zone_contiguous` (M6): a validated merge can leave a plan's public zone at exactly
    ONE room (no DINING) — previously `< 2 rooms` read as "nothing to measure" (`None`); now a
    lone room that IS a merge (`shape == "L"`) reads as trivially contiguous (`True`) — more true
    than an ordinary open-plan join, since there is no seam left between the two former rooms at
    all.
  - M1 (habitable aspect) needed no code change: `demo.rooms` already carries the MERGED room
    (contract.py replaces the two source `RoomOut`s with one before `quality_metrics.measure_design`
    ever runs), so M1's per-type breakdown already reads ONE `"LIVING_KITCHEN"` entry at the
    union's own bounding-box aspect — never the two source rooms' own (possibly much worse)
    standalone aspects. §3 below measures this quantitatively via a fixture where the KITCHEN arm
    alone would have read as a strip.
- **`app/vertical_slice/reference_benchmark.py`**:
  - Section B (circulation) and section L (area consistency) switched from
    `gross_width_m * gross_depth_m` to `gross_area_m2` for the same reason as M3 above — section
    L in particular exists to measure "net vs. gross by wall thickness," and a merged room's bbox
    product is not that; it is a shape artefact of the L, not a wall-thickness fact.
  - Section C (zoning/public-composition): the same "one merged room passed by DINING's absence"
    fix as M6, so a plan whose public zone is a single merged room reads `public_contiguous: True`
    (one contiguous public room), not `n/a`.

**Unit tests** (AC-1's verification target,
`backend/tests/vertical_slice/test_living_kitchen_merge_spike.py`, 3 new tests added to the
existing 8):

- `test_m1_aspect_reads_the_merged_rooms_own_shape_not_a_strip_arm_penalty` — a fixture where the
  KITCHEN arm alone (gross 4.0 × 1.5 m, aspect 2.67 — a strip on its own) merges with LIVING; the
  merged room's own aspect (its bounding box) is measured directly, proven strictly better
  (`< 2.67`) than the arm's own standalone reading, and proven to be the ONLY entry under its type
  (no leftover `"LIVING"`/`"KITCHEN"` entries).
- `test_m3_circulation_share_uses_the_merged_rooms_own_true_area_not_its_bounding_box` — the same
  fixture's bbox is proven strictly larger than its true union area (a genuine, non-flush L); M3's
  circulation share is proven to match the TRUE-area computation and to differ from the
  bbox-inflated one.
- `test_public_zone_and_zoning_section_count_the_merged_room_as_one_contiguous_public_room` — with
  no DINING room in the fixture, both M6 and reference_benchmark's section C are proven `True`
  (not `None`/n/a).

All 11 tests in the file pass; the pre-existing 8 (candidate detection, the redesigned checks,
the contract-layer payload transform) are unchanged.

## 2. The flip rule (AC-3)

Stated once, applied mechanically, and unit-tested directly
(`app/vertical_slice/room_merge.decide_default`,
`backend/tests/vertical_slice/test_rectilinear_realizer_flags.py`, 8 tests): the flag defaults
**ON** only when, over the full 432-context corpus, EVERY one of the following holds —

1. **LOST == 0** — every context that planned with the flag off still plans with it on.
2. **crashes == 0** — on both sides.
3. **status_changes == 0** — no context's PLANNED/REFUSED/CRASH class flips either way (a GAIN
   is generically an allowed corpus-regression outcome elsewhere in this codebase, but this
   feature should never produce one — the merge only ever recombines two already-realized,
   already-validated rooms inside a plan that already reached `to_demo_design`, so a genuine
   status change would mean something is wrong).
4. **refusal_code_changes == 0** — a context REFUSED on both sides keeps the same refusal code.
5. **No M1-M6 corpus statistic regresses beyond its existing tolerance**
   (`quality_metrics.find_regressions`, the SAME tolerance-checked comparison
   `tests/regression_corpus/test_quality_baseline.py` already gates on: M3 2pp, M4 0.2, M5 2pp,
   M6 2pp — M1/M2 are diagnostic, not gated, matching that test's own convention).

Otherwise the flag stays OFF, and the failing condition(s) are named — never a partial flip, never
a silent guess. `decide_default` is the single source of truth both this report's own generator
script (`scripts/stage0_merge_ab.py`) and the flag's own test call, so the report's numbers and
the shipped constant can never silently disagree.

## 3. Before/after SVG pairs (AC-4)

Three committed pairs, `docs/reports/rectilinear-realizer/svg/context-{097,116,214}-{before,after}.svg`
— rendered directly off the real solved geometry (`generate_demo_design`, flag off vs. on) by
`scripts/stage0_merge_ab.py --svgs`, chosen as the three most-oriented (least square bounding-box)
applied merges in the corpus. Each "before" pair shows the two source rooms (`סלון`/`מטבח` —
LIVING/KITCHEN) as separate rectangles with a partition wall between them; each "after" pair shows
the same plan with one polygon room (`סלון ומטבח`), the shared wall gone entirely. Honestly: all
three of THESE particular contexts happen to be flush merges (a 4-point rectangle, not a
6-plus-point L) — the Issue's own scope explicitly allows this ("an L, or a rectangle if they
happen to align flush" — a real corpus effect, not a shortcut: LIVING/KITCHEN pairs from a
guillotine tree are often the same height or width as each other, per spike #107's own report). A
genuine non-flush L (more than 4 vertices) is proven directly by
`test_merged_room_passes_validation_and_renders_as_polygon` and the new
`test_m3_circulation_share_uses_the_merged_rooms_own_true_area_not_its_bounding_box` fixture in
`test_living_kitchen_merge_spike.py`, both asserted on a hand-built partial-edge pair.

## 4. 432-context corpus A/B (AC-2, AC-3)

Method: `scripts/stage0_merge_ab.py` (new, committed — extends spike #107's own
`spikes/failure_log_sweep/living_kitchen_merge_ab.py` with status/refusal-code-change tracking
and the M1-M6 corpus deltas), run in chunks against `tests/regression_corpus/corpus.json` (the
frozen 432-context corpus), `--report` printing the aggregate below. Full run, 2026-09-23,
`uv run python scripts/stage0_merge_ab.py --start N --count M` in five chunks covering
`[0:432)`, then `--report`:

```
accumulated: 432/432 contexts

planned OFF=404  ON=404
LOST: 0   crashes OFF=0 ON=0

status_changes (any context whose PLANNED/REFUSED/CRASH class differs OFF vs ON): 0
refusal_code_changes (both sides REFUSED, code differs): 0

byte-identical primary signatures (OFF==ON): 236/404
primary-signature changes: 168

merge candidates found (flag ON, over the OFF-planned contexts): 191   applied: 168   rejected (own checks failed): 23
  rejected on C6: 14
  rejected on C3: 4
  rejected on C20+C6: 3
  rejected on C20: 2

M1-M6 corpus deltas, flag OFF -> ON (before/after, over all PLANNED contexts):
  M1 habitable aspect (median of per-plan medians): 1.674 -> 1.593  (diagnostic, not gated)
  M2 habitable-on-envelope (mean of per-plan ratios): 1.000 -> 1.000  (diagnostic, not gated)
  M3 circulation-share median: 0.1085 -> 0.1085  (tolerance 0.02)
  M4 hall aspect median: 9.500 -> 9.500  (tolerance 0.2)
  M5 wet-adjacency share: 0.4344 -> 0.4344  (tolerance 0.02)
  M6 public-contiguous share: 0.5272 -> 0.9431  (tolerance 0.02)
  M1-M6 regressions beyond tolerance: NONE

merged room's own oriented (AABB) aspect over the 168 applied contexts: median 1.18

FLIP RULE (COMPLETE — 432/432): flag defaults ON — LOST=0, crashes=0, status_changes=0, refusal_code_changes=0, no M1-M6 regression beyond tolerance
```

**Reading it**: the candidates-found/applied/rejected split (191/168/23) and rejection reasons
(14×C6, 4×C3, 3×C6+C20, 2×C20) exactly match spike #107's own prior measurement of this same
corpus (Issue's own "Current behavior" text) — this stage changed nothing about WHICH merges fire,
only how a merged room is measured once it does. The 168 primary-signature changes are the 168
applied merges themselves (a room disappearing from the list, one polygon room appearing instead)
— matching count, not a coincidence. **M6 moving from 52.7% to 94.3%** is the single largest
number in this report: it is the corpus-level confirmation that AC-1's fix works — every plan
whose public zone became one merged room (with no DINING alongside it) now correctly reads as
contiguous instead of "nothing to measure," on top of the plans that were already open-plan-joined
before this stage. M1's median aspect improving (1.674 → 1.593) is the same "no strip penalty"
effect the unit test proves directly, now visible at corpus scale. M3/M4/M5 are unchanged to 4
decimal places — expected: M3/M4 only involve HALL rooms (a merge never touches one), and M5 only
counts wet rooms (also untouched).

## 5. Out of scope, deliberately untouched

Per the Issue's own scope: the Stage 1 realizer, merging anything but an adjacent LIVING+KITCHEN
pair, changing any validator/threshold/hard limit. `quality.exposure`/`quality.wet_privacy`/
`quality.signal`/`quality.notices` still refer to the two source room ids individually (computed
off the raw pre-merge solver output, before `_apply_room_merge` runs) even when a merge applies —
a known, disclosed inconsistency inherited from spike #107's own report, not addressed here (AC-1
scopes this stage to `quality_metrics.py`/`reference_benchmark.py` specifically). The frontend
room label (`demoRoomLabel.ts`) printing a merged room's bounding-box `width_m × depth_m` beside
its true polygon `area_m2` is the same pre-existing, disclosed cosmetic gap.
