# Non-rectangular geometry: full-corpus (n=199) re-measurement (Issue #106)

Re-runs Issue #102's deterministic shape-measurement script
(`backend/spikes/geometry_shapes/measure_real_plan_shapes.py`) against the POC Architectural
Brain's full 199-plan real-ResPlan corpus, to firm up
`docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md` §3's directional 19-plan-sample numbers before
either candidate architecture (A/B in that report) spikes engineering time. **No product code
changed; no architecture decision made or revised** — this is measurement only, exactly Issue
#106's scope.

## How the corpus was reached

No integration branch currently carries both this ROOT's work and `integration/poc-architectural-
brain` simultaneously (the precondition named in #102 §6's "first measurable milestone"). The
corpus (`backend/spikes/architectural_brain/corpus/`, 199 `resplan_*.json` files + `ATTRIBUTION.md`,
~5.9 MB, CC BY 4.0) was read directly out of `origin/integration/poc-architectural-brain`'s git
history (`git show <ref>:<path>` per file) into a transient, **untracked**, **uncommitted**
directory outside this branch's working tree state, used only to run the two measurement commands
below, then deleted before this change was committed. The measurement script itself has **no import
dependency** on the POC branch's code (see its own module docstring) — it reads the corpus JSON
schema directly, so this worked without merging or checking out that branch's code. Per the Issue's
own "out of scope": the corpus is **not** copied into this repo's committed fixtures and is not
present anywhere in this commit; reproducing this report requires the same transient-extraction step
against `integration/poc-architectural-brain` (or a future branch where the corpus is reachable).

## Bug found and fixed (Required behavior #3)

The full-corpus run crashed (`AttributeError: 'MultiPolygon' object has no attribute 'exterior'`)
on exactly one room across the whole corpus: `resplan_3728`'s `BATHROOM_2` (5.94 m²) has a
self-intersecting ("bowtie") digitisation ring; Shapely's `buffer(0)` repair — already used for any
invalid ring — splits a bowtie into a `MultiPolygon`, which `classify_room_shape` did not handle.
The 19-plan fixture never contains a self-intersecting ring, so this path was never exercised
before. **Fix**: `_polygon_from_ring` now keeps the largest-area polygon piece when the repaired
geometry is a `MultiPolygon`/`GeometryCollection` (the standard repair for a self-intersecting ring),
so classification still runs on one simple polygon — a 4-line, purely defensive change,
`backend/spikes/geometry_shapes/measure_real_plan_shapes.py`'s `_polygon_from_ring`. **Covered by a
new unit test**: `test_classify_room_shape_self_intersecting_bowtie_ring_keeps_largest_piece`
(added to `tests/spikes/test_measure_real_plan_shapes.py`) reproduces the same failure mode with a
synthetic self-intersecting ring (two squares joined at one crossing point, so `buffer(0)` splits
into a 2-piece `MultiPolygon`) — the actual corpus room is not reachable from this repo, so this
synthetic ring is what makes the fix regression-tested in CI rather than only manually verified
against a corpus this branch cannot commit. **Verified inert on the frozen 19-plan fixture**: the
original 10/10 `tests/spikes/test_measure_real_plan_shapes.py` assertions pass unchanged before and
after the fix (no fixture room takes the new branch) — the file now has 11/11 passing with the new
test added. Both corpora
below were re-run after the fix, as required.

## Room shapes — §3.1 comparison (10 cm simplification, default 1.0 m² artefact filter)

| | 19-plan sample (n=179 rooms) | 199-plan corpus (n=1840 rooms) | delta |
|---|---|---|---|
| RECTANGLE | 75 (41.9%) | 936 (50.9%) | +9.0 pp |
| L_SHAPED | 35 (19.6%) | 317 (17.2%) | −2.4 pp |
| OTHER | 49 (27.4%) | 428 (23.3%) | −4.1 pp |
| ARTIFACT (<1 m², excluded from guillotine test) | 20 (11.2%) | 159 (8.6%) | −2.6 pp |
| DEGENERATE | 0 | 0 | — |

3-5 bedroom subset: 199/199 full-corpus plans are 3-5 bedroom (matches #102's own note that the
POC's documented corpus-level count is 162+27+10 = 199/199 in that range), so the 3-5-br-subset row
is **identical** to the all-real-rooms row above at full-corpus scale (n=1840 both ways) — no
separate table needed, unlike the 19-plan report where 17/19 plans fell in that subset.

**With the artefact filter disabled** (`--min-room-area-m2 0`, all rooms including digitisation
slivers) — full corpus only, for direct comparison with #102 §3.1's own note that its 19-plan raw
numbers are not separately tabulated there:

| | 199-plan corpus, no artefact filter (n=1840 rooms) |
|---|---|
| RECTANGLE | 938 (51.0%) |
| L_SHAPED | 317 (17.2%) |
| OTHER | 585 (31.8%) |
| ARTIFACT | 0 (0.0%) |

**Confirms or revises?** Every room-shape share moves in a consistent direction (more RECTANGLE,
less L_SHAPED/OTHER/ARTIFACT) at full-corpus scale, matching #102's own stated hypothesis that the
19-plan sample (curated for circulation-class diversity, median fill-ratio ~0.74) undercounts
footprint-regular plans relative to the full corpus (documented median ~0.82). Treating the 19-plan
counts as a binomial sample (95% Wald interval, n=179): RECTANGLE's CI is [34.7%, 49.1%] — the
full-corpus value (50.9%) sits just outside/at its edge, consistent with a real, if modest,
selection-bias effect layered on ordinary sampling noise, not sample-size noise alone. L_SHAPED
[13.8%, 25.4%], OTHER [20.9%, 33.9%], and ARTIFACT [6.6%, 15.8%] all comfortably contain their
full-corpus values — for those three shares, the 19-plan number is statistically indistinguishable
from full-corpus noise; no selection-bias claim is needed for them. **Net finding: the 19-plan
sample's directional numbers CONFIRM at full-corpus scale (rectangles are a plurality but not a
majority-by-far, L-shapes are a real ~1/6 of rooms, OTHER is a substantial minority) — the sample
was not misleading — with a small, real upward revision to the RECTANGLE share specifically,
consistent with the report's own predicted circulation-class-diversity selection bias.**

## Envelope shapes and guillotine-separability — §3.2 comparison

| | 19-plan sample (n=19) | 199-plan corpus, default filter (n=199) | 199-plan corpus, no filter (n=199) |
|---|---|---|---|
| Rectangular envelope | 0 (0.0%) | 2 (1.0%) | 2 (1.0%) |
| L-shaped envelope | 0 (0.0%) | 7 (3.5%) | 7 (3.5%) |
| Other/irregular envelope | 19 (100.0%) | 190 (95.5%) | 190 (95.5%) |
| **Guillotine-separable** | **0 (0.0%)** | **1 (0.5%)** | **0 (0.0%)** |
| Non-guillotine | 19 (100.0%) | 198 (99.5%) | 199 (100.0%) |
| UNKNOWN | 0 | 0 | 0 |

(Envelope-shape classification does not depend on the room-level artefact filter, so its column is
identical in both filter settings; only the guillotine test — which excludes artefact-area rooms —
differs.)

**Envelope shapes**: the 19-plan sample's 0/19 rectangular-or-L-envelope finding **weakens
slightly, as anticipated by #102 §3.2's own caveat**: 9/199 (4.5%) of the full corpus has a
near-rectangular or simple-L building envelope — real, but still a small minority. This is exactly
the direction #102 flagged ("the full corpus likely shows some share of near-rectangular envelopes
this 19-plan sample happens not to include, but genuinely rectangular building envelopes are not
the norm either way") — confirmed, not contradicted: 95.5% of real building envelopes are still
irregular polygons at full-corpus scale.

**Guillotine-separability — AC-2**: the 0/19 finding **holds at full-corpus scale under the
identical test** (`--min-room-area-m2 0`, no artefact filter: 0/199, 100.0% non-guillotine —
exactly 0%, now measured on n=199 instead of n=19, i.e. strengthened by sample size while
confirming the same direction). With the default 1.0 m² artefact filter enabled, exactly one small
plan (`resplan_12746`, 3 bedrooms, 8 non-artefact rooms, 7 of them plain rectangles) becomes
separable once its 2 sub-1 m² LIVING slivers are excluded — 1/199 (0.5%), not a reversal of the
finding, and itself evidence for the report's own filter-sensitivity caveat ("an unfiltered sliver
almost always defeats every candidate cut in its own plan" — here, disabling the filter restores
0/199 exactly). **Conclusion for AC-2: the headline 0% guillotine-separable finding holds and is
strengthened (same 0% result, 10× the sample), with one filter-dependent, non-artefact-excluded
edge case (0.5%) fully explained and consistent with the report's own documented caveat — not a
material weakening of the finding that architecture B (§4.B) targets.**

## Reproducing this measurement

```
# from a worktree/branch where backend/spikes/architectural_brain/corpus is reachable
cd backend
uv run python spikes/geometry_shapes/measure_real_plan_shapes.py \
    --corpus-dir <path-to-architectural_brain-corpus>
uv run python spikes/geometry_shapes/measure_real_plan_shapes.py \
    --corpus-dir <path-to-architectural_brain-corpus> --min-room-area-m2 0
uv run pytest -q tests/spikes/test_measure_real_plan_shapes.py   # frozen 19-plan numbers, unchanged
```

## What this does not change

No change to `docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md`'s own recommendation (Architecture A
first, B in parallel as research, C deferred) — that report's §6 is untouched, per Issue #106's own
scope; this report only firms up its §3 evidence. No product code (`app/`) touched. The full 199-
plan corpus is not committed anywhere in this repository.
