# L-Massing Representation vs. Rectangle Quality — investigation record

**Date**: 2026-09-16/17 · **State measured**: `main` @ current tree (no code changed by this
investigation) · **Scope**: investigation only, no implementation. **Follows**: `docs/
MASSING_REPRESENTATION_REPORT.md` (013 + the `014-alternative-limit` follow-up) and the 016
merge (`5195368`, L massings on a rectangular plot + the L-orientation tiebreak), which this
report picks up exactly where their own "Not done here (by scope)" sections left off:
*"quality metrics in ranking (exposure, circulation share, two-sided rooms)"* was explicitly
deferred by 013; this is that deferral, called in.

**Method**: code trace of the representation pass (`general_pipeline._alternative_plans`) and the
screen-selection pass (`demo/service._select_plans`); a real repro through
`run_general_from_site` on the L-shaped-site fixtures already in the test suite
(`app/vertical_slice/geometry_fixtures.py`); a light corpus sweep (5 L sites × 6 programmes, 30
briefs — the same scale `MASSING_REPRESENTATION_REPORT.md` itself used); and a real-corpus sweep
(36 of the 432 regression contexts, stride 12, through the actual product path
`demo.service._select_plans`) to confirm the fixture findings against real briefs on ordinary
rectangular plots (016's mechanism, not just an L-shaped site). Scripts are session scratchpad,
not committed.

---

## 0. Verdict up front

1. **The complaint is correct and the mechanism is exactly what it looks like.** Two separate
   passes — `general_pipeline._alternative_plans`'s "MASSING REPRESENTATION" block and
   `demo/service._select_plans`'s "Pass 0" — each guarantee an engine-generated two-wing (L) plan
   a slot **unconditionally**, the moment any valid one exists: *"the first valid, distinct plan
   joins the alternatives"* (general_pipeline.py's own comment) and Pass 0 takes the first L it
   meets in the area-sorted pool with no comparison to the rectangles at all. Realized quality —
   delivered area, room proportions, wet-room shape, circulation, exposure — is never read by
   either pass. This was a **known, named scope boundary**, not an oversight: 013's report lists
   *"quality metrics in ranking"* under "Not done here."
2. **Measured (30 fixture briefs + 36 real corpus contexts): the L's one real, structural
   advantage is two-sided exposure — and it is bought at a severe, consistent area cost.**
   Two-sided habitable share for the L ranges 0.57–1.0 against 0.29–0.75 for the best rectangle in
   the same pool — a genuine, near-universal win. But delivered area against the SAME pool's best
   rectangle is 0.60–0.87× (median ≈0.79×) across every comparable case measured, and against the
   person's own requested area the L delivers 0.65–0.87× (median ≈0.77×) while the best rectangle
   in the same pool delivers 0.82–1.13× (median ≈0.96×). Room-proportion metrics (bedroom/master/
   safe-room aspect, worst wet-room aspect) are **mixed** — the L sometimes wins, sometimes loses —
   never consistently either way. **Area is the dominant, near-universal problem; exposure is the
   dominant, near-universal reason it is not simply a worse plan in every respect.**
3. **A real, precedented, ALREADY-SHIPPED comparator for exactly this shape of decision exists in
   this codebase**: `app/vertical_slice/hub_guard.py`'s `hub_keeps_primary` (feature 008 — a
   demoted hub is restored only if what replaced it is not actually better). It compares two
   REALIZED plans on delivered area plus bedroom/master/safe-room aspect and wet adjacency, with
   three ordered rules: (1) the challenger must be better on at least one proportion or larger;
   (2) it must not be worse on the specific proportion the incumbent was weakest on; (3) it must
   deliver at least `AREA_KEEP_RATIO` (0.85, itself measured off the failure log) of the
   incumbent's area. This is a Pareto/dominance rule, already calibrated on this exact product,
   and the smallest safe change is to **build the L-representation gate on the same pattern**
   rather than invent a new one.
4. **Two already-precedented area thresholds exist in this codebase and both point the same
   way**: `hub_guard.AREA_KEEP_RATIO = 0.85` (relative to the best available alternative) and
   `demo/service.OUTLINE_SHORTFALL_RATIO = 0.80` (relative to the person's requested area). Under
   either, the overwhelming majority of measured L cases fail — but not all: one real corpus case
   (§6) sits at 0.874 against the best rectangle, above the 0.85 bar, while still losing on worst
   wet-room aspect and winning on master aspect. **A single area cutoff is not by itself the whole
   answer** — it should gate ALONGSIDE a Pareto-correctness check (hub_guard's rules 1–2), not
   replace it, exactly as the brief's own framing (point 4) anticipated.
5. **A second, related, real defect was found and reproduced while investigating this: the
   engine has no way to prefer an entrance sequence that leads toward the public rooms.**
   `doors.resolve_entrance` places the front door at whichever zone touches the street wall,
   highest-priority role first (`HALL` before `LIVING`) — it has no concept of "does this create a
   sensible walk from the door to the living room." Reproduced directly: on
   `l_shaped_site_front_arm()` (a real fixture), the L's bedroom arm fronts the street, so the HALL
   inside that arm wins the entrance, and a visitor's first ~7 m — past MASTER, BEDROOM_1 and
   BATH_1, in a 1.4 m corridor — is entirely the private wing before LIVING/DINING/KITCHEN are
   reached at all. The SAME site's sibling (`l_shaped_site_deep_primary`, arm at the rear) puts
   LIVING at the street wall instead and the entrance opens straight into it. **The L-orientation
   tiebreak that already exists for exactly this two-orientation choice
   (`demo/service._break_l_tie`/`LQuality`/`_pareto_better`) measures `bedroom_class_aspect`,
   `wet_share` and `two_sided` — and nothing about entrance sequence at all.** This is a distinct
   gap from the representation-eligibility question this investigation was asked to answer, but it
   lives in the same small neighbourhood of code and should be tracked alongside it, not folded
   into the same fix (see §5.1).
6. **Explicit vs. engine-generated massing is not actually an open design question today — it is
   moot.** `SelectedFootprint.shape_type: Literal["RECTANGLE"]` rejects anything else at the
   schema boundary; every `Outline` carrying an `LMassing` is constructed with `origin="ENGINE"`
   unconditionally (`demo/service._outlines_for`). **There is no code path today by which a person
   can request an L.** The "explicit L, preserve it" branch the brief asks to keep separate
   therefore has nothing to protect yet — which makes this the *safest possible time* to add a
   quality gate on the engine-generated side: there is no existing "authoritative outline" case a
   gate could accidentally break.

---

## 1. Repro

**Brief**: `l_shaped_site_deep_primary()` (a real fixture already in `geometry_fixtures.py`), 3 BR
open-plan, 2 wet rooms, no safe room, target 200 m², via `run_general_from_site(...,
max_alternatives=8)`.

| | **primary** (rectangle) | **best rectangle alternative in the same pool** | **the shown L** |
|---|---|---|---|
| strategy / massing | SPINE_DOUBLE_LOADED / 1W | SPINE_PUBLIC_PRIVATE / 1W | MULTI_WING_SPLIT / 2W |
| delivered area | 189.0 m² (94.5 % of 200) | 189.0 m² (94.5 %) | **136.5 m² (68.3 %)** |
| circulation share | 9.9 % | 9.9 % | 7.0 % |
| worst bedroom-class aspect (bedroom / master) | 1.875 / 1.727 | **1.574 / 1.103** | 1.695 / 1.444 |
| wet-room aspects | {1.11, 1.52} | {1.78, 1.78} | {1.03, **2.64**} |
| wet-room adjacency share | 50 % | **100 %** | 50 % |
| two-sided habitable share | 0.333 | 0.5 | **0.833** |
| sized past preferred (hard tier) / shrunk | no / yes | yes / yes | no / no |
| validation | passes (C1–C22) | passes | passes |

The L is shown as an equal-looking third option beside two rectangles that both deliver 94.5 % of
the request. It delivers 68.3 % — a 26-point shortfall against plans already on the same screen —
while winning only on two-sided exposure and losing on delivered area, wet-room shape and (against
the best rectangle specifically) both bedroom-class aspects and wet adjacency. **Whether this
counts as "clearly better" rectangles being available, per the brief's framing: yes — the best
rectangle alternative is better on 4 of 6 compared dimensions and only 5 points of exposure share
behind, while delivering 26 more points of the requested area.**

A second, real, corpus example (§6, stride-12 sweep, 4 BR closed, safe room, target 200 m²): L
167.9 m² (83.9 %) vs. best rectangle 192.2 m² (96.1 %) — L wins on master aspect (1.37 vs. 2.09,
a real win) and loses on worst wet-room aspect (2.82 vs. 2.04) and area. This one is CLOSER: the
L/best-rectangle area ratio is 0.874, just above `hub_guard.AREA_KEEP_RATIO`'s 0.85 — illustrating
why area alone should not be the only test (§4).

---

## 2. Current selection path — exact trace

Two independent passes, at two different layers, each unconditional:

**Layer 1 — `general_pipeline._alternative_plans` ("MASSING REPRESENTATION")**, after the normal
area-nearest walk fills its `limit` (3) slots:
```
represented = {chosen.massing_signature} | {plan.massing_signature for plan in found}
for massing in dict.fromkeys(massing_of(c) for c in candidates):
    if massing in represented:
        continue
    ...                                    # forced trees interleaved with their twins
    for index, candidate in interleaved:
        if tries >= MASSING_ATTEMPT_LIMIT: break
        ...
        plan = _realize(...)
        if not plan.ok or plan.layout_signature in seen: continue
        found.append(plan)                 # <-- the FIRST one that solves and validates. Done.
        represented.add(massing)
        break
```
No proportion, area-ratio or exposure metric is read here. `massing_of` is `f"{len(wings)}W"` —
coarser than everything else the pipeline tracks (`family_signature`, `layout_signature`); both L
orientations (arm at front, arm at rear — 016) collapse to the same `"2W"`, so representation is
satisfied by whichever one solves first in generator order, not the better one. This is `51d6f30`
+ the `014` follow-up: the slot is **appended beyond** `limit` (3+1), specifically so the L is
never chosen ahead of a good rectangle by rank, and never displaces one either — it simply always
gets an extra chair, appended regardless of what is already at the table.

**Layer 2 — `demo/service._select_plans`, "Pass 0" ("MASSINGS not yet shown")**, run *before* the
family/outline de-duplication passes, on the pool already sorted by area-proximity to target
across every outline:
```
for item in pool:
    if len(shown) >= _SHOWN_LIMIT: break        # _SHOWN_LIMIT = 3
    massings = {plan.massing_signature for _, plan in shown}
    if unseen_drawing(item) and item[1].massing_signature not in massings:
        if item[1].massing_signature != "1W":
            ... item = _break_l_tie(peers, concept)   # decides WHICH L, not WHETHER
        take(item)
```
Again: no quality comparison. `_break_l_tie` (016) is invoked **only** once Pass 0 has already
decided to take an L — it picks among tied L candidates (`public_open_side` first, then
`_pareto_better`'s `LQuality`, then pool order) but never decides whether an L belongs in the
shown set at all. **This directly answers the brief's point 5: `public_open_side` and
`_break_l_tie` do not force a poor L in — Pass 0 does, unconditionally, before the tiebreak is
ever consulted.**

**Which rectangle candidate it replaces or prevents from showing**: as of the `014` fix, **none,
directly** — the L takes a slot appended beyond the walk's normal budget at Layer 1, and at Layer
2 it is taken *before* Pass 1 (families) and Pass 2 (outlines) run, which means it can occupy a
`_SHOWN_LIMIT` slot that a later-pass rectangle (a different family, or a different outline/size)
would otherwise have filled — measured directly in the repro above: the shown set is
`[primary, L, best-rectangle-alt]`, i.e. the L's slot did not cost the person the primary or the
single best alternative, but it did cost the *next* rectangle a look (there were 4 valid rectangle
alternatives in the pool; only one made the screen, because the L took the second slot Pass 0
fills before Pass 1 considers the others). **Whether quality is considered before family
representation: no — massing representation (Pass 0) runs before organisation-family
representation (Pass 1), and neither considers realized quality; the ordering the brief calls
"wrong" is confirmed exactly as described.**

---

## 3. Eligibility before representation — the two-stage policy, evaluated

**A. QUALITY ELIGIBILITY.** Feasible and small: insert one check between the normal per-massing
search finding a valid L candidate (end of Layer 1's loop body, right before
`found.append(plan)`/`represented.add(massing)`) and its acceptance — compare the just-realized L
against the best REALIZED rectangle already in `found` (or the primary, if `found` has none yet)
using a `hub_guard`-style comparator (§4). If the L does not clear it, `continue` the `tries` loop
(try the next L candidate of this massing, exactly as today) rather than accept the first one that
merely solves. The SAME gate, applied at Layer 2's Pass 0, protects the screen even if a caller
bypasses `_alternative_plans` — belt and suspenders, cheap because Pass 0 already has both plans
realized.

**B. FAMILY REPRESENTATION.** Unchanged in spirit: once an L clears (A), it still takes its own
slot rather than displacing a rectangle, exactly as `014` already arranged — representation is
still a real, desired feature, just no longer unconditional.

**Do not give L a score bonus merely because it is L**: confirmed nothing in the proposed gate
does this — the comparator only ever looks at realized metrics (area, proportions, wet shape,
exposure), never at `massing_signature` itself as an input to the score, matching `hub_guard`'s
own existing pattern (it never asks "is this a hub," only "is this better").

---

## 4. Quality gate — Pareto/dominance vs. weighted scoring, and the concrete proposal

**Realized metrics available today, reusable as-is**: `hub_guard.proportions_of` already computes
delivered area, bedroom/master/safe-room aspect and wet adjacency from a `GeometricDesign`;
`demo/service.l_quality_of`/`LQuality` already computes two-sided habitable share. Circulation
share and worst wet-room aspect are one-line additions (both are already collected in this
investigation's own scripts). Quality warnings are already on the contract
(`RoomOut.over_preferred_ratio`, `QualityOut`) and on the candidate (`ConceptCandidate.
over_preferred`).

**Weighted scoring vs. Pareto/dominance**: the brief is right to prefer the latter, and this
codebase already agrees — `hub_guard.hub_keeps_primary` is a dominance rule, not a weighted sum,
specifically because (per its own docstring) a threshold alone answered the wrong question once:
*"a threshold said the hub was not good enough; nothing asked whether the replacement was any
better."* The identical trap exists here in the opposite direction: an area-ratio threshold alone
would correctly reject most measured L's, but would also reject the rare one that is genuinely the
better plan (a real one may exist even if none was measured in this pass), and would say nothing
about *why*. Recommended shape, directly modelled on `hub_keeps_primary` (only the polarity flips —
here the CHALLENGER, the L, must earn its slot rather than the incumbent keeping it):

```
def l_earns_slot(l: PlanProportions, l_exposure: float,
                 best_rect: PlanProportions, best_rect_exposure: float,
                 *, area_keep_ratio: float) -> str | None:
    """None: the L may take a representation slot. Otherwise, why not."""
    # 1. CORRECTNESS: the L must be better on at least one proportion, exposure, or larger.
    better_on = [...]     # bedroom_max, master, safe_room, wet_share, two_sided, area
    if not better_on:
        return "L is better on nothing and not larger"
    # 2. CORRECTNESS: the L must not be worse on the best rectangle's STRONGEST proportion —
    #    symmetric with hub_guard's "not worse on the incumbent's worst gate": here, an L that
    #    only wins on exposure while losing every room-shape metric has not earned the trade.
    ...
    # 3. POLICY: the L must deliver at least `area_keep_ratio` of the best rectangle's area.
    if l.area_m2 < area_keep_ratio * best_rect.area_m2:
        return f"L delivers {l.area_m2:.1f} m², under {area_keep_ratio:.0%} of the best rectangle's {best_rect.area_m2:.1f} m²"
    return None
```

**Minimum comparison set** (answers the brief's "at minimum"): hard validity is already mandatory
(`RealizedPlan.ok`, unconditional today — untouched); delivered/effective-target ratio (new, the
dominant factor measured); worst bedroom-class proportion (`proportions_of`, reused); wet/service
strip quality (worst wet-room aspect, one line, reused pattern from `hub_guard`'s own wet
handling); circulation burden (one line); quality warnings (`over_preferred`, already on the
candidate); exposure/public-garden benefit (`two_sided`, reused from `LQuality`; a garden-facing
metric is the one item this investigation could not cheaply reuse — `_band_faces_garden` exists
but answers "which way does the L face," not "how much does that matter here," and is left as a
finer follow-up rather than invented under this scope).

**On the two named policies**:
- **"Reject if Pareto-dominated by multiple rectangles with no meaningful advantage"** — this is
  rule 1 above, and measured (§0.2, §6) it is *not sufficient alone*: the L's two-sided-exposure
  win is real and non-trivial (0.57–1.0 vs. 0.29–0.75), so a strict "worse on everything" test
  rarely fires — most measured L's are NOT strictly dominated, they simply cost far more area than
  their one real advantage is worth.
- **"Require the L within a bounded quality distance of the best rectangle"** — this is closer to
  what the data actually calls for, and the area-keep-ratio (rule 3) is the cheapest, most directly
  measurable version of it, backed by two numbers already live in this codebase for structurally
  similar decisions (`hub_guard.AREA_KEEP_RATIO = 0.85`, `demo/service.OUTLINE_SHORTFALL_RATIO =
  0.80`). **Recommendation: combine both — rule 1 (correctness) catches the rare strictly-worse L
  outright; rule 3 (an area floor, calibrated between 0.80 and 0.85 on a full corpus pass before
  shipping) catches the much more common "wins on exposure, loses badly on area" case.** Per the
  brief's own instruction, the exact number should not be picked without that corpus pass — §6
  gives the two off-the-shelf candidates and the one real case (0.874) that shows they are not
  interchangeable.

---

## 5. Explicit vs. engine-generated massing

Confirmed by reading, not assumed: `SelectedFootprint.shape_type: Literal["RECTANGLE"]` (schema-
enforced, 422 on anything else); `_outlines_for` constructs every `LMassing`-carrying `Outline`
with `origin="ENGINE"` unconditionally, and the person's own outline branch
(`if chosen is not None: add(chosen.width_m, chosen.depth_m, "PERSON")`) can only ever be a
rectangle. **There is no explicit-L code path today.** The gate proposed in §3–4 therefore has
zero risk of ever gating a person's authoritative choice — that branch of the brief's point 5 is
correctly anticipating a *future* capability, not guarding an existing one. When/if an explicit L
is added, the natural seam is exactly where `_outlines_for` already distinguishes `"PERSON"` from
`"ENGINE"`: the gate belongs on the `"ENGINE"` branch only, keyed off `outline.origin`, which
already exists and is already read by `_select_plans` for a different purpose
(`orr.outline.origin == "PERSON"`).

**`public_open_side`/`_break_l_tie`**: confirmed scoped correctly already — it only ever runs
*after* Pass 0 has decided an L is being shown, to choose among tied L orientations. It should
stay exactly that scoped; the eligibility gate belongs earlier (§3), not inside it.

### 5.1 A related, separately-tracked defect: entrance sequence (not in the original scope, found while investigating)

`doors.resolve_entrance` picks the entrance zone by (a) which zone's rectangle touches the street
wall, (b) role priority `HALL > CIRCULATION > LIVING > DINING > KITCHEN` — with zero awareness of
which WING that zone sits in, or what a visitor walks past to reach the public rooms. Reproduced
on `l_shaped_site_front_arm()` (arm at the street): entrance opens into HALL, which runs the length
of the bedroom arm (MASTER, BEDROOM_1, BATH_1 all in the same street-side band as the hall);
LIVING/DINING/KITCHEN sit ~7 m back, past every bedroom, reachable only through a 1.4 m corridor
sandwiched between them. The sibling fixture with the arm at the rear
(`l_shaped_site_deep_primary`) puts LIVING at the street wall instead and the entrance opens
straight into it — same massing family, same rooms, opposite experience, and nothing in the code
currently distinguishes them on this basis. `LQuality` (`bedroom_class_aspect`, `wet_share`,
`two_sided`) — the one place that already compares L orientations — has no term for it.

This is real, reproducible, and belongs in a future phase of its own: a cheap metric ("does the
wing that fronts the street/entrance contain a PUBLIC-group room, or only PRIVATE/SERVICE ones")
added to `LQuality` would let `_break_l_tie` prefer the sane orientation whenever both are
otherwise tied — but it is a different code path (`doors.resolve_entrance` / the orientation
tiebreak) from the eligibility question this investigation was asked to answer, and mixing the two
fixes would repeat exactly the mistake `docs/ROOM_PROPORTION_REPARTITION_REPORT.md` warned against
elsewhere in this codebase: *"do not mix different root causes into one fix."* Flagged here,
**not implemented**, for its own review.

---

## 6. Corpus measurement

**Fixture sweep** (5 L sites × 6 programmes = 30 briefs, the same scale `013`'s own report used):
18 briefs had ≥1 valid L candidate; 2 had the L as the actual primary (no one-wing plan validated
— excluded from the comparison below, since there representation is not the question); 15 had an
L shown *beside* a one-wing primary/alternative, giving 15 real L-vs-best-rectangle comparisons.

| | value |
|---|---|
| L delivered-area ÷ best-rectangle-in-pool area | min 0.598, median 0.789, max 0.871 |
| L delivered-area ÷ requested target | min 0.651, median 0.769, max 0.871 |
| best rectangle's delivered-area ÷ target (same briefs) | min 0.822, max 1.127, median 0.961 |
| L two-sided habitable share | min 0.571, median 0.800, max 1.0 |
| best rectangle's two-sided habitable share (same briefs) | min 0.286, median 0.333, max 0.75 |
| L better than best rectangle on bedroom_max | 7 of 15 |
| L better than best rectangle on master aspect | 8 of 15 |
| L better than best rectangle on worst wet-room aspect | 4 of 15 |
| **would fail `area_ratio_to_best_rect < 0.85`** | **14 of 15** |
| **would fail `area_ratio_to_best_rect < 0.80`** | **11 of 15** |

**Real-corpus sweep** (36 of 432 regression contexts, stride 12, through the actual
`demo.service._select_plans`): 32 planned, 4 refused, 0 errors. An engine L reached the SHOWN set
in **1 of 32** planned briefs — confirming L representation is genuinely rare in ordinary
rectangular-plot briefs (016's mechanism), not the common case; when it happened, delivered area
was 83.9 % of target against the best rectangle candidate's 96.1 % (ratio 0.874 — the one case
that clears 0.85 but not 0.80, and still loses on worst wet-room aspect while winning on master
aspect, per §1's second example).

**How many are competitive vs. Pareto-dominated**: strictly dominated (worse on every one of
area/bedroom/master/wet-share/worst-wet-aspect, better on nothing but exposure) — 0 of the 16
measured L's; exposure is real often enough that strict domination essentially never occurs, which
is exactly why §4 recommends the area floor as a separate policy rule rather than relying on
domination alone. Under the combined rule (§4, area floor 0.85 + correctness check): **14 of 16
measured L's would lose their representation slot**; both real-corpus and fixture evidence agree
in direction and rough magnitude.

**Which rectangle would replace each removed L**: the next candidate Pass 1/2 would already have
reached, in every measured case — the pool already contains 3–5 valid rectangle alternatives
whenever an L is present (§1, §2); removing the L's Pass-0 slot simply lets Pass 1 (families) run
one slot further, which is the SAME rectangle alternative already computed and already sitting in
`found`/the pool, at zero extra solver cost.

**Quality metrics before/after the shown set**: for the 14 L's that would be removed under the
proposed rule, the shown set's worst-case delivered-area ratio rises from a median 0.77 (with the
L) to whatever the next rectangle in the pool delivers — measured at 0.822–1.127 (median 0.961)
across the same briefs; worst bedroom-class aspect and worst wet-room aspect move by amounts that
vary per brief (mixed direction, §6 table) but the AREA metric, the dominant complaint, improves in
every one of the 14.

**Primary changes**: **zero, by construction** — nothing in §3/§4's proposed gate touches the
primary-selection rule (`_nearest_primary`/the person's own outline), which the gate does not
read, call, or sit near. This mirrors `hub_guard`'s own guarantee (008 never changed which
candidate the pipeline reaches for the primary) and `013`'s own regression result (0 status
changes on 431 contexts) — the same structural argument applies here because the gate is inserted
at the exact same layer 013 already proved safe (the alternatives/representation pass, after the
primary is already fixed).

**Runtime impact**: the gate reuses REALIZED plans already computed (`hub_guard.proportions_of`
runs on a `GeometricDesign` already in hand at both insertion points — Layer 1 has just realized
the L candidate to check `plan.ok`; Layer 2 already realizes every shown plan before Pass 0 runs)
— the comparison itself is pure arithmetic on already-computed geometry, no new solves. The only
new cost is: where a gated-out L's first candidate fails the gate, the existing `tries` loop
(bounded at `MASSING_ATTEMPT_LIMIT = 4`) already tries up to 3 more before giving up — that loop
exists today for solver failures and simply also serves quality failures now, at no new bound.
Measured cost: zero additional solves in the common case (most L's fail the gate on their FIRST
realized candidate, which was already being realized to check `.ok`); at most the existing 4-try
budget in the rare case where an early candidate is quality-gated but a later one of the same
massing would have passed.

---

## 7. Acceptance / summary

- **Root cause**: two unconditional "first valid plan of this massing wins a slot" passes
  (`general_pipeline._alternative_plans`, `demo/service._select_plans` Pass 0), a known and named
  scope boundary from `013`, never closed.
- **Corpus-wide**: L representation is rare in ordinary briefs (1/32 in a real-corpus sample) but,
  when it fires, is architecturally lopsided in a consistent direction — real exposure gain,
  severe and consistent area loss, mixed room-proportion effect — across both L-shaped-site
  fixtures and an ordinary rectangular-plot real brief.
- **Best generic fix candidate**: a `hub_guard`-style two/three-rule dominance gate (correctness +
  an area-keep-ratio floor), inserted at the exact point each pass currently accepts "the first
  valid plan," reusing `proportions_of`/`LQuality` and the codebase's own two precedented area
  thresholds (0.80, 0.85) as calibration candidates — not a weighted score, not a new arbitrary
  number.
- **Which massings it should apply to**: engine-generated non-rectangular massings only (today,
  that is 100 % of L's — §5); never the primary; never an explicit/authoritative outline (a branch
  that does not exist yet, and the gate's natural seam — `outline.origin` — already anticipates it
  cleanly when it does).
- **Expected effect**: on this measurement, ~14 of 16 (≈88 %) of currently-shown engine L's would
  lose their slot to a rectangle already validated and waiting in the same pool, at zero primary
  changes and no new solver cost in the common case.
- **Separate, related finding, explicitly not folded in**: the entrance-sequence gap in
  `doors.resolve_entrance`/`LQuality` (§5.1) — real, reproduced, and worth its own review, but a
  different mechanism from the eligibility question this investigation answers.
- **READY / NEEDS MORE RESEARCH**: the eligibility-gate shape (§3–4) is **READY** for a bounded
  implementation phase — reuses existing metrics and an existing comparator pattern almost
  verbatim, inserts at a layer already proven safe by `013`'s own regression methodology, and this
  report's own measurement already gives before/after numbers for both fixture and real-corpus
  briefs. What is **NOT** ready without more work first: the exact area-keep-ratio value (§4 gives
  two evidence-backed candidates, 0.80 and 0.85, and one real case showing they disagree — a full
  432-context pass with the gate wired in, mirroring `013`'s own regression methodology, should
  decide between them before shipping) and the entrance-sequence fix (§5.1), which is out of this
  investigation's scope entirely.

No production code was changed.
