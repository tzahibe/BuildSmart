# POC Architectural Brain — realization through the existing engine (Issue #96, C/3)

**The question this POC exists to answer:** did access to real architectural experience (the
Issue #94 corpus + #95's retrieve/synthesize/adapt) give BuildSmart an architectural brain that is
*visibly* better than the current hand-designed concept generator?

**Recommendation: MODIFY.**

This closes the loop: the brain's synthesized, adapted `ConceptSpec`s are compiled
(`spikes/architectural_brain/realize.py`) into a Geometry Core `Fixture` and run through the
*unchanged* `solve_fixture` + `general_pipeline._realize` chain — the same doors, windows,
furniture, validation and assembly stages every production plan goes through (AC-2, verified by
`test_demo_alternatives.py::test_poc_plans_come_from_the_unchanged_realize_chain`). The result is a
genuine, honest positive on one axis and a genuine, honest gap on another — see the checklist below
before either is taken as the whole story.

## How to read this page

Each of the 3 fixed benchmark briefs (`tests/architectural_brain/briefs.py`) gets its own section:
**A** = the current, hand-designed `concept_generator` (baseline). **B** = the brain's own realized
alternative(s) — synthesized from the corpus, adapted to the brief, compiled and validated. Full
detail (retrieved references + WHY, extracted ideas, what adaptation changed, per-plan
measurements) is in each `brief-N/references.md` / `brief-N/comparison.md`. Produced by
`spikes/architectural_brain/demo.py` (`current` / `references` / `alternative` / `comparison`
subcommands) — deterministic, re-runnable.

---

## Brief 1 — the challenging family home

4 bedrooms + SAFE_ROOM + 3 wet rooms, ~200 m², plot 17×30.5 m, street north. A plain rectangle
(one safe-adapter candidate) — the site TWO_WING needs two adjacent candidates for is not offered
here, so this brief can only ever show what SPINE looks like.

### A — current engine (`concept_generator`)

![brief-1 current](brief-1/current.svg)

Realized, `ok=True`, **circulation_class=FRONT_BAND**, in 1.6 s.

### B — brain alternatives

| | brain-A (`concept-0`) | brain-B (`concept-1`) |
|---|---|---|
| | ![brief-1 brain-A](brief-1/brain-A.svg) | ![brief-1 brain-B](brief-1/brain-B.svg) |
| realized class | SPINE | SPINE |
| `ok` | True | True |
| time | 149.9 s | 150.3 s |
| donor references | different (see `brief-1/references.md`) | different |
| adaptations | RESIZE_ROOMS only | RESIZE_ROOMS + BEDROOM_COUNT_ADJUST (+1) |

**Honest finding:** brain-A and brain-B are sourced from two DIFFERENT retrieved donor plans with
different declared patterns (`OTHER` vs `FRONT_BAND`) and different adaptation operations — but
they realize to the **identical geometry** (every measurement in `brief-1/comparison.md` matches to
the metre). Cause: `adaptation.py`'s `RESIZE_ROOMS` replaces every room's area with a **fixed
per-type constant** (`TARGET_AREA_M2`), never the donor's own proportions — so once two donors
converge on the same brief-authoritative room *types and counts*, their adapted programmes are
byte-identical inputs to `realize.py`'s deterministic compiler, which then produces the same
output. The retrieval/synthesis layer (#95) is genuinely diverse (different WHY, different
patterns cited); this realization layer (#96) currently throws that diversity away for anything
that isn't the concept's `circulation_class` label.

---

## Brief 2 — the owner's own brief

4 bedrooms (3 + master ensuite), 2 wet rooms, laundry, open plan, 130 m², plot 15×17 m. The
tightest of the 3 (documented in `briefs.BRIEF_2`'s own comment: even the production engine falls
short by 0.08–0.7 m at full plot width for this exact room mix).

### A — current engine (`concept_generator`)

![brief-2 current](brief-2/current.svg)

Realized, `ok=True`, **circulation_class=SPINE**, in 0.2 s.

### B — brain alternatives

**REFUSED — 0 realized alternatives.** Both attempted concepts (`concept-0` FRONT_BAND-labeled,
`concept-1` OTHER-labeled) refuse identically: *"no footprint size solved for the SPINE template:
depth 13.0 m: no width combination both fit and solved"* — the plot's own keep depth (13.0 m, the
hard ceiling after setbacks) is not enough for `realize.py`'s single-column, height-stacked SPINE
compiler on this room mix, even though the SAME room mix fits under the current, more sophisticated
`concept_generator` (which tries several strategies this spike's one minimal compiler does not
reimplement — `FRONT_PUBLIC_BAND`, `SPINE_SERVICE_CLUSTER`, `BRANCHED_TWO_STACK`, etc.; see
`brief-3/current.json`'s own notes for the full strategy list the production engine tries).

**Honest finding:** on the tightest of the 3 briefs, the brain is currently a regression: it
realizes nothing, where the production engine already solves the same brief. This is a genuine gap
in `realize.py`'s own minimal single-wing compiler, not a validator or corpus limitation.

---

## Brief 3 — the wide 5-bedroom home

5 bedrooms, 3 wet rooms (owner did not specify; a reasonable assumption for the size — see
`briefs.BRIEF_3`'s own comment), 200 m², plot 27×20.5 m. This brief's site is a **Z-massing** (two
notches, not one) specifically designed so the safe-geometry adapter offers TWO adjacent candidate
rectangles sharing a horizontal edge (10.5×10.0 m and 21.0×4.0 m) — the only one of the 3 briefs
where TWO_WING is geometrically reachable at all.

### A — current engine (`concept_generator`)

**REFUSED.** Every strategy the production generator tries fails on this site for this room mix;
the last and most telling note:

> `MULTI_WING_SPLIT/NO_SEAM_ALIGNMENT`: the second wing (21.0 x 4.0 m) sits north or south of the
> primary; this parti runs its hall along the seam, and a hall along the street axis is not
> authored yet.

Full failure detail (7 strategies tried, each with its own reason) in `brief-3/current.json`. This
is the current engine hitting the SAME site this POC picked precisely because its own topology
repertoire cannot solve it — an honest, deterministic refusal, not a crash (AC-3's
`test_current_engine_baseline_solves_and_validates` locks this in).

### B — brain alternative

![brief-3 brain-A](brief-3/brain-A.svg)

**REALIZED, `ok=True`, circulation_class=TWO_WING, in 0.2 s** (`concept-5`, donor plan `681`,
retrieved specifically for its `TWO_WING` pattern — see `brief-3/references.md`). Every hard
validator passes (0 failures); `_realize` unchanged. This is the POC's one clear, positive,
*visible* result: **a topology the current hand-designed generator cannot produce on this site at
all, realized end-to-end through the same unchanged engine and validators.**

Two other synthesized concepts (`concept-0` OTHER-labeled, `concept-1` FRONT_BAND-labeled) were
also attempted; both fall back to the SPINE compiler (the only template `realize.py` has for a
non-TWO_WING label) and refuse fast (0.5 s) — see "the AC-1 finding" below for why SPINE
structurally cannot solve on this particular site.

---

## Measurements table

| plan | brief | class | gross m² | net m² | M3 circulation share | M4 hall door count | M4 hall aspect (median) | M5 wet adjacency | M6 public contiguous | wet-core clusters |
|---|---|---|---|---|---|---|---|---|---|---|
| current | 1 | FRONT_BAND | 189.8 | 172.3 | 0.086 | 8 | 8.36 | 0.67 | False | 2 |
| brain-A | 1 | SPINE | 170.1 | 152.6 | 0.179 | 9 | 5.94 | 0.67 | True | 2 |
| brain-B | 1 | SPINE | 170.1 | 152.6 | 0.179 | 9 | 5.94 | 0.67 | True | 2 |
| current | 2 | SPINE | 128.7 | 117.3 | 0.141 | 6 | 9.29 | 1.00 | True | 2 |
| brain | 2 | — | — | — | (0 realized alternatives — see brief-2 section) | | | | | |
| current | 3 | — | — | — | (REFUSED — see brief-3 section) | | | | | |
| brain-A | 3 | TWO_WING | 154.4 | 140.2 | 0.221 | 9 | 3.09 | 0.67 | True | 2 |

Source data: `brief-N/comparison.md` (generated from each realized plan's own `app.demo.contract`
quality metrics — M1–M6, the SAME signals the production demo service reports; Required Behavior
4). `circulation_metrics`/`entrance_sequence` as named in the Issue's own "Current behavior" section
were not found as importable modules in this codebase snapshot (searched `app/`) — the demo instead
reports the nearest available existing signals: M3 (circulation share), M4 (hall door count/aspect
— the same shape signal a corridor-length metric would target), and the realized entrance room
(`entrance_opens_into`, per-plan in each `comparison.md`), all sourced through `app.demo.contract`
rather than invented for this POC.

---

## Failure-criteria checklist (honest, against the Issue's own Acceptance Criteria)

| # | Criterion | Status | Evidence |
|---|---|---|---|
| AC-1 | ≥ 2 realized alternatives, different `realized_circulation_class`, none SPINE-only duplicates, all `ok`, for ≥ 1 brief | **NOT MET** | See "The AC-1 finding" below. `test_demo_alternatives.py::test_one_brief_yields_two_different_verified_topologies_that_pass_every_validator` is a real, exercised `xfail(strict=True)` with the finding inline. |
| AC-2 | Every realized POC plan through the unchanged `_realize` chain; diff touches no `validation.py`/`geometry_core/`/`doors.py`/`windows.py` | **MET** | `test_poc_plans_come_from_the_unchanged_realize_chain` PASSES (genuine check-registry comparison, not mocked). Diff for this Issue touches only `spikes/architectural_brain/*`, `tests/architectural_brain/*`, `docs/reports/poc-architectural-brain/*` — confirm with `git diff --stat` against the review target list. |
| AC-3 | 3 fixed benchmark briefs, current-engine baseline recorded, deterministic re-render | **MET** | `test_benchmark_briefs.py` (6/6 passing): brief-1/2 solve+validate; brief-3's refusal is itself the recorded, deterministic baseline (its own documented engine limitation, not a crash). |
| AC-4 | This README: side-by-side SVGs for all 3 briefs, references+WHY, extracted ideas, adaptation changes, measurements table, GO/MODIFY/STOP | **MET** | This page. `references.md`/`comparison.md` per brief. |
| Goal | "≥ 2 genuinely different alternatives for one brief" (Goal section, not a numbered AC) | **PARTIALLY MET** | Brief-1's two brain alternatives differ in DONOR/rationale but realize to identical geometry (see brief-1's "honest finding" above) — genuinely different provenance, not genuinely different drawings. |

### The AC-1 finding

Investigated directly, not assumed. With `realize.py`'s current 2-compiler repertoire (SPINE:
single-column, height-stacked; TWO_WING: either a vertical-boundary height-stacked wing B, or — the
one that actually solves here — a horizontal-boundary, WIDTH-based double-loaded private column):

- **brief-1 / brief-2** (plain-rectangle sites): the safe-geometry adapter offers exactly ONE
  candidate rectangle. TWO_WING structurally needs ≥ 2 adjacent candidates (`_solve_two_wing_search`
  refuses outright below that) — geometrically unreachable here. Every realized alternative on
  these two briefs is SPINE (brief-1) or nothing (brief-2).
- **brief-3** (the Z-massing site, the only one offering 2 candidates): its own private programme
  (5 bedrooms + 3 wet rooms = 8 rooms) needs ≈ 19 m of single-column height-stacked depth — an
  invariant of the room mix, confirmed by measurement (see `realize.py`'s own module docstring and
  `_MAX_WING_DEPTH_M`). Neither candidate rectangle offers that (10.5 m and 4.0 m respectively; even
  their combined footprint is not one contiguous 19 m-deep rectangle). SPINE therefore refuses
  every trial, fast and deterministically. Only the double-loaded TWO_WING template — which trades
  WIDTH for depth by running two private-room columns side of a shared hall instead of stacking all
  8 rooms in one column — fits, because it only needs ≈ 10.5 m of depth per wing.

**The two paradigms are opposite site shapes by construction**: SPINE wants narrow-and-deep,
double-loaded TWO_WING wants wide-and-shallow, for the SAME total room area. None of the 3 FIXED
benchmark briefs (their plot dimensions are fixed by Required Behavior 2, not a free choice) has a
site that is simultaneously deep enough for a full single-column stack AND splittable into 2
candidates — every attempt to carve a second candidate out of a brief-1-sized deep rectangle either
leaves the private column too narrow (< the ≈ 8.95 m single-column SPINE already needs) or too
shallow once split by depth instead of width. Reaching AC-1 honestly would need either (a) a third,
genuinely different topology family (HUB_LOBBY/BRANCHED — explicitly out of scope for this Issue,
deferred to Concept Engine v2's own child #79), or (b) a 4th brief/site combination outside the 3
fixed ones Required Behavior 2 names. Neither was done here; flagged for the owner/Team Lead as a
decision point rather than silently declared met.

### What IS genuinely, visibly better

Brief-3: the current hand-designed generator refuses this site outright (7 strategies tried, all
failing on this exact room mix — see its own notes). The brain realizes a fully validated plan on
the SAME site through the SAME unchanged engine, in 0.2 s. That is the POC's one unambiguous,
judge-by-eye positive: **real reference-plan experience unlocked a topology (TWO_WING) that the
current concept generator's own repertoire does not reach here at all.**

### What is NOT yet better

- Brief-2: the brain currently realizes NOTHING where the production engine already solves — a
  regression on this specific brief (this spike's compiler is deliberately minimal; the production
  generator's several strategies were not reimplemented, per Required Behavior 1's "minimal spike
  compiler... where they exist" allowance).
- Brief-1: the brain's own "alternatives" are geometrically identical to each other despite
  different donor provenance — the promise of "genuinely different" (Goal section) is not delivered
  within one topology, because `RESIZE_ROOMS` collapses every donor's own proportions to one fixed
  per-type constant.
- AC-1's cross-topology diversity within one brief: not reached (see above).

## Recommendation: MODIFY

**GO** would claim the brain is unambiguously better today — it is not: brief-2 is a regression,
brief-1's "alternatives" do not actually vary, and AC-1's own bar is not met. **STOP** would throw
away brief-3's real result — a genuine, validated topology the current engine cannot produce on a
site the current engine cannot solve at all, delivered end-to-end through the unchanged engine and
every existing validator, in a fraction of a second. **MODIFY**, specifically:

1. Let `RESIZE_ROOMS` (or a new adaptation operation) carry the donor's own room-area *proportions*
   forward instead of a fixed per-type constant, so different donors produce genuinely different
   geometry within one topology (closes brief-1's gap).
2. When Concept Engine v2's own compilers (`concept_compilers.py`, child #79) land on
   `integration/concept-engine-v2`, integrate them here for HUB_LOBBY/BRANCHED — the Team Lead's own
   planned merge — which is the most direct path to AC-1 (a 3rd topology family opens real
   cross-topology diversity options this 2-compiler POC cannot reach).
3. Extend `realize.py`'s SPINE compiler with the SAME double-loaded (width-based) private-column
   trick TWO_WING already uses, as a single-wing variant — brief-2's own regression is exactly the
   "needs more depth than the plot offers" failure double-loading was built to solve for TWO_WING.

None of this is a validator, Geometry Core, doors/windows or Concept Engine v2 change — every item
above is scoped to `spikes/architectural_brain/` (`realize.py` / `adaptation.py`) plus an
integration step already planned by the Team Lead.

## Known limitations of this POC (not defects — recorded honestly)

- **Runtime**: a single SPINE realization that succeeds costs ~150 s (the compiler's own
  deterministic depth/width search, see `realize.py`'s own docstring); TWO_WING is fast when it
  solves (0.2–0.5 s) because its geometry is computed directly rather than searched. Not optimised
  for this POC, per the Team Lead's own runtime rule.
- **`circulation_metrics`/`entrance_sequence`** (named in the Issue's "Current behavior" as
  existing) were not importable modules in this codebase snapshot — see the Measurements table's
  own note for what was used instead.
- HUB_LOBBY is not compiled here at all (see `realize.py`'s module docstring for why a minimal
  spike compiler cannot produce one within a realistic house depth) — deferred to #79, per the Team
  Lead's own direction.
