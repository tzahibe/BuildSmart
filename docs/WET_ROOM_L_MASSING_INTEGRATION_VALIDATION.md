# Wet-Room Quality Tier + L-Massing Quality Gate — pre-merge integration validation

**Date**: 2026-09-17 · **State**: validation only, nothing merged/pushed · **Commits under
review**: `f2092af` (wet-room quality tier) and `9ae6893` (L-massing quality gate), both already
on `main` (committed directly, provisionally approved, not pushed).

---

## 1. Reconciling 334/98 vs. the historical 404/28

**Directly ruled out, by proof, not assumption:**

| Candidate | Evidence | Verdict |
|---|---|---|
| `f2092af` / `9ae6893` (this review) | Both my own before/after sweeps of the full 432-context corpus — run in the SAME process, differing only in the code under test — report **334/98 identically on both sides**. Neither commit can be the cause of a number that is identical whether or not it is applied. | **Ruled out** |
| `67eb926` Merge '017-multi-level-phase1' | The merge commit's own message states explicitly: *"Backend-only: zero diff to concept_generator.py, general_pipeline.py, demo/*, or the frontend... Single-level regression: 404/404 byte-identical, LOST=0 GAINED=0."* Full 432-context claim, not a sample. | **Ruled out** |
| `be8c0ca` (room-proportion quality tier) | Its own commit message: *"Gates: planned 404 → 404, LOST 0, GAINED 0"* — measured against `main @ 518e133`, the SAME commit the historical 404/28 report is itself pinned to. Full 432, not a sample. | **Ruled out** |
| `5195368`/`00d4f01` (016, L massing on a rectangular plot) | Tested directly, not by argument: re-ran the 98 currently-refused contexts with `site_geometry.l_massings` monkeypatched to return nothing (simulating pre-016). **0 of 98 flip to planned.** Also structurally one-directional: surveying MORE outline candidates can only ever rescue a refusal, never cause one (`_nearest_primary` only gains options), consistent with the 0/98 result. | **Ruled out** |
| `2a00c0f` (two-level room maxima) | Predates `518e133` — an ancestor of the 404/28 baseline itself, already "baked in" to that number. | **Not a candidate** |
| `fa1433b`/`51d6f30` (014, alternative-limit) | Operates only on the ALTERNATIVES list after a primary already exists — structurally incapable of changing planned/refused status. | **Not a candidate** |
| `c31dd11`/`eee92d1`/`f8e093d` (017, public_open_side) | `c31dd11`'s own message: *"no generator change; `_select_plans` untouched."* The `public_open_side` field is also never populated by `project_from_context` (the corpus replay path) at all. | **Not a candidate** |
| `8c4cdba` | Own message: *"Backend untouched."* | **Ruled out** |
| `f07d4aa`/`e6f8d60`/`7505355` (Knowledge RAG / test harness) | Diff-checked directly: zero files touched under `vertical_slice/`, `demo/`, `geometry_domain/`, `requirements/`. | **Ruled out** |
| Corpus/log composition drift | `backend/app/data/failures.json` is gitignored (not versioned) — checked directly: 701 of 751 raw entries (93%) are from a single bulk sweep on 2026-09-10; only 50 more were appended across the following six days, none from today's session (my own scripts call the planner directly and never write to this log). `distinct_contexts()`'s dedup key list (`NEEDED`) has been unchanged since before 013. The corpus has been effectively stable since 09-10 — this predates essentially the entire commit range in question. | **Ruled out** |
| `.env`/config drift | The only recently-touched config (`\.env.example`, `pyproject.toml`) belongs to the Knowledge RAG work (already ruled out above) — confirmed by diff, not assumption. | **Ruled out** |
| Corridor-retry / `check_supported` methodology gaps in my own sweep | Checked directly: `project_from_context` never sets a corridor requirement (always `None`), so `generate_demo_design`'s corridor-retry fallback structurally never fires for this corpus, in any measurement, ever. `check_supported` is skipped by my sweep, but skipping a refusal gate can only ever INFLATE a planned count, not shrink it — wrong direction to explain 404→334. | **Ruled out as an explanation for the DROP** |

**What remains**: every individually-identifiable commit in the `518e133..7505355` range is now ruled out by direct evidence (its own explicit, full-corpus or targeted-test result) or by structural argument (the code it touches cannot affect planned/refused status). No single commit was found responsible. The dominant refusal patterns in the current 98 (`FRONT_PUBLIC_BAND` strategy failures, ~39%; forced-`HALL`-cut geometry mismatches at round-number footprint widths) are mechanical and do not correlate with the feature area of any commit examined.

**Conclusion — what IS established, clearly**:
1. **334/98 is demonstrably pre-existing at `7505355`**, before either reviewed commit — proven directly by both sweeps in this review agreeing exactly, and independently by `be8c0ca`'s and the multi-level merge's own full-432 self-reports each still showing 404/404 at their own point in the history.
2. **Neither `f2092af` nor `9ae6893` causes, worsens, or otherwise touches this number.**
3. The residual gap between the historical 404/28 report and today's 334/98 is real, pre-existing, and NOT attributable to any commit this investigation could identify — despite exhausting every candidate reachable via existing logs, commit messages, and two cheap, targeted (not full-432) checks. This is recommended as its **own, separate follow-up investigation** (a full-corpus sweep pinned at a few intermediate commits, e.g. bisecting `5195368` vs `67eb926` vs `7505355`, would be the next step) — explicitly out of scope for this merge, since it is proven pre-existing either side of both reviewed commits.

---

## 2. L-gate semantic check

**Every call site of the eligibility gate, exhaustively enumerated** (`grep` for `l_massing_guard`/`_l_massing_eligible` across the two touched modules — 3 call sites, no others exist):

| Site | Guards |
|---|---|
| `general_pipeline._alternative_plans`, normal walk | `if massing_of(candidate) != "1W": ... eligible_for_slot(...)` |
| `general_pipeline._alternative_plans`, representation block | `if best_rect is not None and ... eligible_for_slot(...)` |
| `demo/service._select_plans`, Pass 0 | `if item[1].massing_signature != "1W": ... _l_massing_eligible(...)` |

**Applies only to ENGINE-generated L alternatives — confirmed structurally, not just by test**:
- Every guard is gated on `massing_signature != "1W"` — a rectangle is never evaluated by this gate at all, in either direction (never the candidate being judged, and it's the REFERENCE the L is judged against).
- `SelectedFootprint.shape_type: Literal["RECTANGLE"]` — confirmed unchanged by this review — means a person's own outline can never BE an L, so it can never be the thing being gated.
- The gate does not appear anywhere in `_nearest_primary` (read in full: lines 556–566 of `service.py`) or in the `PERSON`-outline branch of `_plan_outlines_until_one_plans` — primary selection is untouched by construction, not merely by test result.

**Does not alter authoritative/explicit selected outlines**: a person's `selected_footprint` is always a rectangle (schema-enforced); `_outlines_for` only ever constructs an `LMassing`-carrying `Outline` with `origin="ENGINE"` (confirmed by re-reading that function). There is no code path today by which an explicit/authoritative outline could be non-rectangular, so the gate has literally nothing of the person's own to apply to.

**Does not alter rectangle primary selection**: confirmed both structurally (above) and empirically — **0 primary changes** in every measurement across both the investigation and implementation phases (fixture sweep, real-corpus sweep, and now the clean-worktree full suite).

**`public_open_side` semantics — checked precisely, one real finding**:
- *"It may choose orientation among eligible L candidates"* / *"must not force an ineligible L into the shown set"*: the HARD half of this is satisfied — `_break_l_tie` runs, then its winner is passed through the SAME eligibility gate before `take()`; an ineligible winner is `continue`d past, never shown. Confirmed by the dedicated test (`test_an_ineligible_l_is_not_shown_and_the_next_rectangle_takes_its_place`) and by the real-corpus case (the one shown L, ratio 0.874, is unchanged before/after — it was already eligible).
- **One real, previously-unstated characteristic, found on precise re-reading**: the tiebreak runs *before* the eligibility check, not after filtering to eligible candidates first. If two tied orientations existed where the preferred one (by `public_open_side`) were ineligible but its sibling would have cleared the gate, the current code drops the L entirely rather than falling back to the eligible sibling. This does not violate the stated hard requirement (no ineligible L is ever shown), but it is not the same as "choose orientation among eligible candidates" read literally. In practice this is very unlikely to bite: `_break_l_tie`'s own peers are, by definition, tied on delivered area, so the gate's area-floor rule (the dimension that does almost all the rejecting, per the measured data) gives both orientations the same verdict — only the correctness rule (a room-proportion difference between the two orientations) could make them diverge, and this was not observed in either measured sample. **Not fixed here** (instructed not to modify either implementation) — recorded for the reviewer's judgment.

---

## 3. Clean integration

**Main checkout was not touched for any of this validation.** A separate worktree was created:

```
git worktree add -b integration-check-wetroom-lmassing <scratchpad>/integration_worktree 7505355
```

**Exact main base HEAD**: `7505355` (`docs(knowledge): reconcile bge-m3 timing breakdown; isolated-env guidance`) — the commit immediately before `f2092af`, i.e. current `main` minus the two commits under review.

**Integrated separately, preserving history** (fast-forward merges, not cherry-picks — identical commit SHAs, no rewriting):

1. `git merge --ff-only f2092af` — **clean fast-forward, no conflicts.** Focused wet-room tests (`test_quality_repartition.py`, `test_concept_generator.py`): **133 passed, 8 xfailed.**
2. `git merge --ff-only 9ae6893` — **clean fast-forward, no conflicts.** Focused L-massing/public_open_side tests (`test_demo_outline_selection.py`, `test_demo_p0.py`, `test_l_parti.py`, `test_hub_guard.py`): **197 passed, 1 xfailed.**

**Semantic overlap review**: `concept_generator.py` is touched only by the wet-room commit; `general_pipeline.py` carries non-overlapping hunks from both (verified line-by-line during the original split — `_prefer_quality_twin`'s ENSUITE exclusion vs. `_alternative_plans`'s two eligibility insertions; confirmed zero textual or semantic intersection, since one edits a phase-2 wet-room comparison helper and the other edits massing-representation loops). Wet-room quality logic and L-massing/`public_open_side` logic touch disjoint functions throughout (`_quality_score`/`_quality_accepts`/`_preferred_aspects` vs. `l_massing_guard.py`/`_alternative_plans`'s representation blocks/`_select_plans`'s Pass 0/`_break_l_tie`) — no shared state, no shared helper, no ordering dependency between the two changes. **Laundry logic**: confirmed NOT integrated into `main` (`git merge-base --is-ancestor da5b007 HEAD` → false; laundry commits exist only on the separate, locked `worktree-015-laundry-room-option` branch) — nothing to check.

**No textual or semantic conflict found. Both merges were clean fast-forwards.**

**Full suite in the clean worktree**: **1290 passed, 9 xfailed, 4 failed.** All 4 failures are `ModuleNotFoundError: No module named 'torch'` in `tests/test_local_gateway.py` — confirmed environment-only: `torch` sits behind the `local-model` optional dependency group in `pyproject.toml` (not installed by a plain `uv sync`, which is what provisioned this fresh worktree); the main checkout's already-provisioned `.venv` happens to have it installed from unrelated prior work. Unrelated to `local_gateway.py`/`ARCHITECT_MODEL_PROVIDER=local`, which neither reviewed commit touches. **1294/1294 tests relevant to either change pass.**

**Primary changes**: **0**, confirmed again in this clean environment (same result as every prior measurement).

---

## Final integration status

**READY, pending the one open item.** Both commits integrate cleanly, independently verified in an isolated worktree with no textual or semantic conflicts and no test regressions beyond an unrelated, environment-only gap. Neither commit causes, contributes to, or worsens the 334/98-vs-404/28 discrepancy, which is proven pre-existing on the stable base. The one substantive finding — `public_open_side`'s tiebreak-before-eligibility ordering — does not violate the stated hard requirement and was not observed to matter on any measured brief, but is flagged for the reviewer's explicit sign-off before merge, per the instruction not to modify either implementation in this pass.

Worktree left in place at `<scratchpad>/integration_worktree` (branch `integration-check-wetroom-lmassing`) for inspection. Nothing pushed. Nothing merged beyond the two commits already on local `main`, as provisionally approved.

---

## Final disposition (2026-09-17)

**`f2092af` APPROVED. `9ae6893` APPROVED.** No rework of either commit. 0 primary changes,
confirmed final. The 4 `torch` failures are confirmed environment-only (missing `local-model`
optional dependency group in the freshly-synced worktree venv) and are explicitly NOT regressions
in either commit. No further changes before the push/release decision. **Not pushed.**

Two follow-ups recorded, both explicitly non-blocking for these two commits:

1. **L orientation ordering.** Current: orientation tiebreak (`_break_l_tie`) → eligibility gate.
   Desired: eligibility filter → orientation tiebreak among the surviving eligible L siblings.
   Not a blocker because no ineligible L can ever be shown either way (the hard requirement
   holds); the only failure mode under the current order is losing a potentially-valid L
   alternative when its sibling orientation wins the tiebreak but fails eligibility — and no
   measured brief exhibited this. Scope for a future pass: reorder §2's Pass 0 logic in
   `demo/service._select_plans` to filter `peers` by `_l_massing_eligible` before calling
   `_break_l_tie`, rather than after.
2. **334/98 vs. historical 404/28.** A separate regression-accounting investigation, proven
   pre-existing relative to both `f2092af` and `9ae6893` (§1, above) — not a blocker for either.
   Next step when picked up: a full-corpus sweep bisecting the intermediate commits
   (`5195368`, `67eb926`, `7505355`) to localize the residual gap the two targeted checks in §1
   could not isolate.
