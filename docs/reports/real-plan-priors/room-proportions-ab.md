# Real-plan room-proportion priors — A/B report (Issue #140, Step 3)

`ROOM_PROPORTION_PRIORS_ENABLED = False` (shipped default, "OFF") vs
`ROOM_PROPORTION_PRIORS_ENABLED = True` ("ON"), over the frozen, committed **432-context**
regression corpus (`backend/tests/regression_corpus/corpus.json`), via
`backend/spikes/failure_log_sweep/room_proportion_priors_ab.py` (sharded 4-way, 8 workers each
side — see that script's own header for the exact commands run).

## Headline result

| metric | OFF | ON |
|---|---|---|
| planned | 404 | 404 |
| refused | 28 | 28 |
| crashes | 0 | 0 |
| validity / refusal rate | 93.5% / 6.5% | 93.5% / 6.5% |
| byte-identical primaries (vs the other column) | — | **404/404 (100%)** |
| M1 — habitable aspect median (`app.vertical_slice.quality_metrics`) | 1.6744 | 1.6744 |
| room-area fidelity, median (this Issue's own metric, see "Method" below) | 2.742 | 2.742 |
| refusal codes | `TARGET_AREA_EXCEEDS_CURRENT_PROGRAM_CAPACITY`=14, `PLAN_NOT_REALIZABLE`=13, `WET_ROOMS_UNSUPPORTED`=1 | identical |
| LOST | — | 0 |
| GAINED | — | 0 |
| new crashes | — | 0 |
| status changes | — | 0 |
| refusal-code changes | — | 0 |
| **primary_signature_changes** | — | **0** |

## `primary_signature_changes`: 0 — what moved, and why nothing did

**Nothing moved.** Every one of the 404 contexts that plan produces the exact same primary
drawing (`layout_signature`-equivalent — room type, position and rectangle) with the flag ON as
with it OFF; every one of the 28 refusals keeps the same refusal code.

This is the EXPECTED result given how the signal is wired (`app/vertical_slice/concept_generator.py`,
`generate_concepts`'s own sort calls): `priors_score(c)` is appended as the LAST element of every
sort key, strictly after area-budget proximity, `over_preferred`/`shrunk` and the `strategy.value`
determinism tiebreak — see `app/vertical_slice/room_proportion_priors.py`'s module docstring. It
can only ever reorder two candidates that ALREADY tie on every one of those existing criteria.
Measured directly (`backend/tests/vertical_slice/test_room_proportion_priors_ranking.py`,
`test_priors_score_only_breaks_a_genuine_tie`): a genuine tie of that kind is rare in this
generator's own candidate sets — different strategies overwhelmingly realize to distinct
`used_area_m2` values for a given brief, so the FIRST-ranked ("primary") candidate essentially
never has a same-ranked peer for the priors score to choose between. Across this real 432-brief
corpus, that rarity turned out to be **total**: not one brief produced the exact tie the signal
needs to have any visible effect.

This is not evidence the mechanism is dead code — `test_priors_score_only_breaks_a_genuine_tie`
and `test_priors_score_cannot_outrank_area_budget_or_strategy_tiebreak`
(`test_room_proportion_priors_ranking.py`) prove the mechanism does reorder a constructed genuine
tie, and does not reorder anything else, directly on the tuple shape `generate_concepts` sorts by.
It is evidence that, on the 19-real-plan measurement this Issue could reach (see
`room-proportions.md`'s "Data source"), the resulting priors table is not yet DIFFERENT enough
from what the existing area-budget/quality-tier signals already deliver to change a single
delivered plan. A full 17,107-plan ResPlan measurement (once
`integration/poc-architectural-brain`'s corpus is reachable — see
`.agent/proposals/roadmap/102-1-full-corpus-remeasurement.md` for the precedent) would sharpen the
table's medians/spreads and could change this; re-running this exact script against that table is
the natural next step, not a rewrite of the mechanism.

## Method

`room_proportion_priors_ab.py` replays every context through
`app.demo.service.generate_demo_design`, once per flag value (the SAME frozen
`tests/regression_corpus/corpus.json` contexts `test_frozen_regression_corpus.py` itself replays),
recording for each: `status` (PLANNED/REFUSED/CRASH), the primary's `signature()`
(`spikes.failure_log_sweep.sweep.signature` — room type/position/rectangle, the same signature the
existing `ab.py`/`corpus_snapshot.py` scripts use for "byte-identical primary"), `m1_habitable_aspect_median`
(`app.vertical_slice.quality_metrics.measure_design` — unchanged by this Issue, read only, not
recomputed), and **room-area fidelity**: for the delivered plan's own rooms, the mean of
`|room.area_m2 - row.median_area_m2| / max(row.p75_area_m2 - row.p25_area_m2, 1e-3)` over every
room that has a matching Step-1 artifact row for its (role, house-size bucket, bedroom-count
bucket) — the exact normalisation `priors_score` (Step 2) uses, applied here to the REALIZED plan
rather than a pre-solve target, since a full A/B can afford one realized plan per context. Lower is
closer to the measured real distribution; a context whose plan has no matching row for any of its
rooms contributes no value (never a fabricated 0). The reported figure is the MEDIAN of this
per-plan value across all 404 planned contexts, on each side.

`compare()` reuses the exact LOST/GAINED/status-change/refusal-code-change/primary-signature-change
definitions `spikes/failure_log_sweep/corpus_snapshot.py`'s own `compare()` uses (the frozen-corpus
CI gate's own comparator), so these numbers are directly comparable to any other flag/toggle A/B in
this repo.

## Reproduce

From `backend/`:

    uv run python spikes/failure_log_sweep/room_proportion_priors_ab.py --save-off off.json --workers 8
    uv run python spikes/failure_log_sweep/room_proportion_priors_ab.py --save-on  on.json  --workers 8
    uv run python spikes/failure_log_sweep/room_proportion_priors_ab.py --compare off.json on.json --report report.json

(run sharded — `--shard I/4` for `I` in `0..3`, then `--merge-off`/`--merge-on` — to fit each half
inside a bounded wall-clock budget; every number above was produced that way).
