# Wet-Room Strip Investigation — the shared bathroom, and the general case

**Date**: 2026-09-16 · **State measured**: `main` @ current tree (no code changed by this
investigation) · **Scope**: investigation only, no implementation, no fix applied to the shown
plan. **Follows**: `ROOM_PROPORTION_REPARTITION_REPORT.md` and
`ROOM_PROPORTION_QUALITY_TIER_REPORT.md` (bedroom-class only; this report is the wet-room
sequel those left open).

**Repro case**: the shown L-plan's shared bathroom ("חדר רחצה"), realized 4.85 × 1.85 m
(aspect 2.62), in the same private column/arm as the safe room (ממ"ד, 4.85 × 2.70) and a
secondary bedroom (חדר שינה, 4.85 × 2.95). The exact source context was not available to this
investigation (the image, not a saved fixture) — §4 reconstructs the same footprint, programme
and areas directly through the planner's own functions instead, which is methodologically
equivalent to a byte-exact replay for the questions asked here.

**Method**: code trace of every function in the decomposition path
(`app/vertical_slice/concept_generator.py`), then a fresh, targeted measurement over the real
432-context regression corpus (every 6th context, 72 briefs, 57 planned — the same sampling
`ROOM_PROPORTION_QUALITY_TIER_REPORT.md` used for its own runtime measurement), using
`ConceptCandidate.wet_rooms` (the resolved `WetRoomKind` per zone) joined against the realized
`GeometricDesign.rooms` to tag every wet room's aspect with its kind, unambiguously — cleaner
than the earlier report's role-only breakdown, and confirmed to be measuring the *same* mechanism
(the counts land within sampling noise of the earlier, larger sweep). Scripts are session
scratchpad, not committed, per that report's own convention.

---

## 0. Verdict up front

1. **Root cause**: `BATHROOM` and `TOILET` carry no `RoomTemplate.preferred_aspect_ratio` — only
   `BEDROOM`, `MASTER_BEDROOM`, `SAFE_ROOM` do (commit `be8c0ca`). The quality tier's own shape
   objective (`_preferred_aspects`) is *built to skip* any room without one. A shared bathroom or
   guest WC is therefore never poor in the planner's eyes, however it looks on the drawing — not
   refused, not repaired, not scored. This is the single, exact reason "the current bedroom-quality
   repartition does not address it."
2. **Even if it were scored, this specific room has no move available.** The one re-partition the
   planner knows (`_dependent_pairings`: a lone row takes a host bedroom's slot beside its ensuite)
   is column-local and needs a dependent (ensuite) already in the *same* column. Traced directly:
   for this arm's three rows, `_dependent_pairings` and `_pair_with_open_member` both return **zero**
   candidates, because the programme's one ensuite is already in the other column, paired with a
   different bedroom. Extending the quality tier to wet roles would still find nothing to offer
   *this* room — a second, independent limit stacked on top of the first.
3. **A real, better decomposition exists at the same footprint/areas/hard-limits, and nothing
   tries it.** Narrowing the arm from 4.85 m to 4.20 m — a move already inside the existing 9-option
   seam search window — improves all three rows at once (bathroom 2.62→~2.1, safe room ~1.9→1.56,
   bedroom ~1.64→1.31) by construction (less width, same target area, deeper by definition). Traced
   directly: the normal path picks the seam nearest the area-equalizing point regardless of shape,
   and the quality tier's own seam loop is *gated behind having a `_dependent_pairings` candidate
   first* — with none here, the seam axis is never explored for shape at all. This is the one lever
   that could fix this exact room, and it is unreachable by any code path today.
4. **Scope, corpus-wide**: every `SHARED_BATHROOM` and every `GUEST_WC` is, by construction, a lone
   full-width row — there is no code path that ever pairs one except the rare hard-refusal tier-2
   repair. Measured: shared bathrooms sit at p50 aspect **1.97** (74% over 1.6, 37% over 2.5);
   guest WCs at p50 **3.27** (88% over 1.6, 62% over **3.0** — essentially always a strip, by the
   template's own arithmetic, not a planner defect). Ensuites are a *different* mechanism (below)
   at a similar median (2.03) but a much lower tail (12% over 2.5, 0% over 3.0) — the two should
   not be fixed by the same move.
5. **Ensuite strips are a different mechanism, confirmed by construction, not just by measurement.**
   `_rows_of`/`_private_rows` always place `[bedroom, ensuite]` as one V-split row: the row's DEPTH
   is `max((area_bedroom + area_ensuite) / column_width, floor)`, driven mainly by the bedroom's
   larger area, and the ensuite gets only its area-proportional slice of the WIDTH — "stood on end."
   A lone shared bathroom has no row-mate at all: it spans the FULL column width alone, and its
   depth is its OWN area/width or floor — nothing to do with any other room. Different topology,
   different fix. The prior investigation's ensuite-sub-row lever stays a separate future phase.
6. **Smallest safe generic change (fix A) reuses 100% of existing machinery but has a real,
   bounded ceiling and does not fix this repro case.** A bigger change (fix D, generalized) is the
   only one that reaches this case, and it needs new work the codebase does not have yet (see §3).

---

## 1. Root cause — the exact decomposition path

For the shown bathroom, tracing `app/vertical_slice/concept_generator.py` in order:

1. **`build_room_program`** resolves the wet-room requirement to `WetRoomKind.SHARED_BATHROOM`
   (entered from circulation, not from a bedroom) and builds a `ProgramRoom` with
   `role=BATHROOM`, `group=SERVICE`, `template=ROOM_TEMPLATES[BATHROOM]` — `min_area=4.5,
   target=6.5, max=12.0 m², min_short_side=1.6 m, max_aspect_ratio=3.0`, **`preferred_aspect_ratio
   = None`** (the field's default; only the three bedroom-class roles override it).
2. **`_rows_of`** places this room in its own row alone: it has no `entered_from`, so it is not
   folded into any bedroom's row. The safe room and the secondary bedroom above it are lone rows
   for the same reason (neither is an ensuite).
3. **Column/seam choice** (`_column_width`, `_seam_options`, `_columns_at_seam`): the arm's net
   width (4.85 m) comes from the AREA SHARE of the whole column's rooms (safe room + bedroom +
   bathroom target areas, divided to equalize the area/depth quotient against the opposite
   column) — a footprint-level decision that has no knowledge of, or interest in, any *individual*
   row's shape. The bathroom simply inherits whatever width the other two rows' area needs settle
   the column at.
4. **`_row_depths`** sizes the bathroom's row: `depth = max(area / net_width, floor)`, where
   `floor` comes from `room_depth_band_m` — `max(min_short_side, net_width / max_aspect_ratio,
   min_area / net_width)`. At 4.85 m this is comfortably inside the template's legal band (neither
   the floor nor the area quotient exceeds the maximum) — **this is not a refusal**. `room_depth_band_m`
   returns a valid band, so nothing downstream ever sees a reason to touch this room.
5. **Tier 2** (`_repartition_rows`) triggers only when `room_depth_band_m(...) is None` — a genuine
   shape refusal. There is none here, so tier 2 never runs on this row.
6. **The quality tier** (`_quality_candidates`, `_preferred_aspects`, `_quality_shortfall`): filters
   by `room.template.preferred_aspect_ratio is not None`. `BATHROOM`'s is `None`, so this room is
   never added to the `aspects` dict scored by `_quality_shortfall`/`_quality_score` — it cannot be
   "the worst room," cannot trigger a search, and would not even be *checked* for spill if some
   other room's pairing happened to move it.
7. **Wet coupling**: the only pairing move the planner knows at all (`_dependent_pairings`) requires
   a dependent (ensuite) row *in the same column*. Traced directly for this arm's three rows:
   `_dependent_pairings(rows, index_of_bathroom)` returns **`[]`** — there is no ensuite here to pair
   into. (The programme's one ensuite belongs to a different bedroom in the other column — see §5.)

Net effect: this bathroom plans successfully, inside every limit, on the very first attempt, at a
width the column-width choice fixed for unrelated reasons — and nothing in the pipeline, gated or
ungated, was ever asked to look at its shape twice.

---

## 2. Scope of the problem (measured)

72 of the 432 real regression contexts (every 6th, the same stride
`ROOM_PROPORTION_QUALITY_TIER_REPORT.md` used), 57 planned. Every wet room tagged by its resolved
`WetRoomKind`, not just its role — this is the clean split the earlier report's role-only table
could not make directly.

| kind → role | n | p50 | p90 | max | >1.6 | >1.8 | >2.0 | >2.5 | >3.0 |
|---|---|---|---|---|---|---|---|---|---|
| SHARED_BATHROOM → BATHROOM | 57 | 1.97 | 2.97 | 3.00 | 74% | 61% | 49% | 37% | 0% |
| ENSUITE → BATHROOM | 32 | 2.03 | 2.56 | 2.85 | 69% | 59% | 50% | 12% | 0% |
| GUEST_WC → TOILET | 8 | 3.27 | 3.46 | 3.46 | 88% | 88% | 88% | 75% | 62% |
| LAUNDRY | — | — | — | — | — | — | — | — | — |

LAUNDRY is 0 by construction: `LAUNDRY_ROOM_ENABLED=False` (gated off since the 015 review; see
`docs/PROJECT_STATE.md` known limitations) — no brief can currently produce one.

**These numbers land within sampling noise of the un-split BATHROOM row in
`ROOM_PROPORTION_REPARTITION_REPORT.md`** (p50 2.14 there, n=659 on the full 432; combining
SHARED_BATHROOM+ENSUITE here gives p50 ≈2.0 on n=89) — expected, since nothing that sizes
BATHROOM/TOILET has changed since that measurement (confirmed: `be8c0ca`, the only commit to
touch this file since, adds `preferred_aspect_ratio` to the three bedroom-class roles only, plus
the quality-tier machinery gated to them — verified by reading the diff and the current
`ROOM_TEMPLATES` table). That report's own root-cause table for BATHROOM (>1.6, n=435) — pair
dependent stood on end 145, lone wide by area 145, lone wide at its 1.6 m floor 136, deep 8 — is
therefore still current and is the finer floor-vs-area attribution this report relies on rather
than re-deriving.

**Root-cause categories, per the brief's request, kept separate:**

| category | mechanism | this repro case | typical severity |
|---|---|---|---|
| lone full-width wet room | SHARED_BATHROOM/GUEST_WC, own row, column width inherited from other rows | **yes — this is it** | BATHROOM p50 1.97; GUEST_WC p50 3.27 (near its 3.0 hard cap by template arithmetic, not a planner defect — a 1.1 m short side against any real column width is inherently a strip) |
| master+ensuite combined-depth strip | ENSUITE, row-paired with its host, row depth = combined area / width | no (this plan's ensuite is elsewhere) | p50 2.03, but a much shorter tail (12% >2.5, 0% >3.0) — usually recoverable, per the earlier report's ensuite-sub-row lever |
| service-room strip (TOILET/GUEST_WC) | same lone-row mechanism as row 1, but against TOILET's much tighter template (1.6 m min area vs BATHROOM's 4.5, 1.1 m short side) | n/a here (no explicit WC in this brief) | almost always a strip; 62% already at the 3.0+ end |
| fallback/shrunk strip | any of the above, additionally deficit-shrunk or hard-tiered | 79% of primaries containing a shared bathroom are `shrunk`; 37% `over_preferred` — the mechanism is unchanged, just realized at a smaller/looser row | makes the same-mechanism strip somewhat worse, does not create a new one |

One useful cross-check: **`quality_repartitioned` (the bedroom-class fix already firing, phase 2)
is true for 30–53% of the plans containing each kind of wet room here — and the wet room's own
shape is unaffected every time.** The existing fix and this gap are provably orthogonal: a plan
can already be "fixed" for its bedrooms and still carry the exact strip in question.

---

## 3. Possible generic fixes, evaluated separately

### A. Service-room row repartition / row sharing (generalize the quality tier to wet roles)

Add `preferred_aspect_ratio` to `BATHROOM` (≈2.0, per the earlier report's knee analysis: 1.8×3.0–
3.6 m is a normal bathroom at 1.7–2.0) and `TOILET` (≈2.5, the strip/normal knee there).

- **Topology required**: none new. `_dependent_pairings`'s candidate generation is *already
  role-generic* — it takes any lone row regardless of role. Only the acceptance/scoring
  (`_preferred_aspects`, gated on `preferred_aspect_ratio is not None`) is bedroom-class-only today.
- **Access legality**: unchanged — reuses `_access_intact` exactly as tier 2 and the existing
  quality tier do.
- **Reuses tier-2/quality machinery**: essentially 100%. This is the smallest possible generic
  change in code-line terms.
- **Effect on runtime**: negligible — no new search axis, same bounded seam/pairing window.
- **Risk to existing bathroom/TOILET behavior**: real but scoped. The host slot
  `_dependent_pairings` offers is the *same single slot* be8c0ca already lets a bedroom-class room
  compete for. Adding wet roles to the objective means a wet room and a bedroom-class room can now
  compete for that one slot in the same programme, and `_quality_score`/`_quality_accepts`'s
  thresholds (`_QUALITY_MIN_GAIN=0.1`, `_QUALITY_SPILL=0.1`) are calibrated only at bedroom-class
  scale (preferred 1.5) — they would need independent recalibration for BATHROOM/TOILET's very
  different scale (preferred 2.0/2.5) before this could be trusted not to silently change which
  room wins an already-working substitution.
- **Ceiling — and why it does not fix this repro case**: bounded by the same one-ensuite-per-
  programme ceiling already documented (`docs/PROJECT_STATE.md`'s known limitations, ≈16% of lone
  rows system-wide) — narrower still than that, in practice, since the slot is already contested
  by bedroom-class rooms since `be8c0ca`. **Traced directly for this exact arm: zero candidates,
  because the programme's one ensuite is in the other column.** This fix reaches *some* lone wet
  rooms (wherever an ensuite happens to share their column and is not already taken), but not this
  one.

### B. Ensuite sub-row

Out of scope for this repro case (no ensuite here). Confirmed a genuinely separate mechanism (§0.5,
§5) — left as the prior report's own future phase, not touched by this investigation.

### C. Wet-room + neighbouring-room repartition

Tested directly: `_access_intact` on a hypothetical `[BEDROOM, BATH_SHARED]` row returns `True` at
the row-topology level, but **both rooms have `entered_from=None`** — both need the corridor, and
only one slot of a shared row can face it. The only way to legalize this pairing is to change the
bathroom's *kind* from `SHARED_BATHROOM` to that bedroom's `ENSUITE` — which is exactly what
`programme_variants` already does, but only for a wet room the person marked `FLEXIBLE`. This
repro case's bathroom is a fixed, explicit request (not flexible), so this move would silently
convert a shared/guest bathroom the person asked for into a private ensuite for one bedroom — a
real change to what was requested, not a decomposition change. Not available as a free generic
lever for a `REQUIRED` shared bathroom; already available (and already scoped correctly) for the
`FLEXIBLE` subset via the existing variant.

### D. Column-width/seam adjustment

- **What it requires**: decoupling the quality tier's seam loop from its `_dependent_pairings`
  gate, so that "re-seam alone, no row pairing" is also a valid quality move — and, because a seam
  choice moves width from ONE column to the OTHER, a new acceptance rule that checks *both*
  columns' rooms together. Today's `_quality_accepts` only ever compares one column against
  itself; nothing in the codebase currently scores a seam move's effect on the opposite column.
- **Access legality**: unaffected — no row topology changes, only widths.
- **Reuses existing machinery**: partially. The seam SEARCH (`_seam_options`, `_columns_at_seam`)
  already exists and already realizes both columns per seam candidate — the data is there. What's
  missing is new joint-column SCORING and acceptance; this is materially more than fix A.
- **Effect on runtime**: cheap in principle — no new seam candidates are generated, the existing
  9-option window is simply re-scored by shape instead of picked by nearest-to-natural-width; the
  realization cost is already paid today.
- **Demonstrated concretely for this repro case** (§4): narrowing the arm 4.85→4.20 m, same total
  column depth, same target areas, improves ALL THREE rows at once — including the bathroom
  (~2.62→~2.1). This is the only one of the four fixes that reaches this specific room.
- **Risk**: **unverified** whether the opposite column can actually absorb the freed width without
  breaking its own rows in the full plan (this investigation only checked the west arm in
  isolation — see caveat in §4). That is precisely the question the current "nearest-to-natural-
  width" seam rule exists to avoid answering per-shape; making seam choice shape-aware means
  answering it for real, which is new design work, not a small patch.

---

## 4. This plan as a repro case — alternative decompositions

The literal source context for the shown plan was not available to this investigation (rendered
from a live UI plan, not a saved fixture). Reconstructed instead, directly through the planner's
own `_row_depths`, `_dependent_pairings`, `_pair_with_open_member`, `_access_intact` — the same
method `ROOM_PROPORTION_REPARTITION_REPORT.md` used for its own replay experiments — at the same
footprint, programme and areas as closely as the printed labels allow (SAFE_ROOM 10.9 m²,
secondary BEDROOM 12.8 m², shared BATHROOM 8.1 m², arm/column net width 4.85 m, no shrinking, no
relaxed maxima):

| net width | SAFE_ROOM | BEDROOM | BATHROOM | note |
|---|---|---|---|---|
| **4.85 m (delivered)** | 4.85×2.70 (1.80) | 4.85×2.90 (1.67) | 4.85×2.30 (2.11) | reproduces the delivered kind of shape; exact figures differ slightly from the printed 1.85 m because the underlying target areas are read off the drawing, not the original request |
| 4.20 m | 4.20×2.70 (1.56) | 4.20×3.20 (1.31) | 4.20×2.00 (2.10) | legal at every row's floor and maximum; **all three rooms improve or hold**, at the same areas |
| 3.80 m and narrower | — | — | — | **refused** — the arm's rows' floors alone (2.87+3.37+2.13 ≈ 8.37 m) exceed the available 7.90 m of column depth; below ~4.2 m this programme no longer fits this arm at all |

**Existing pairing machinery, checked directly on this row set**: `_dependent_pairings` → 0
candidates; `_pair_with_open_member` → 0 candidates (no ensuite, no open-chain member in this
arm). Confirms §0.2/§3.A: even a wet-role-aware quality tier finds nothing to offer this room.

**The 4.20 m alternative is real and legal**, but two things are not established by this
investigation and should not be assumed: (1) whether the *opposite* column/the rest of this
specific footprint can absorb the 0.65 m this would take from it without breaking one of its own
rows — this was checked for the west arm alone, not the whole plan; (2) whether 4.20 m is within
whatever seam window the specific massing (this looks like an L parti, given the footprint's
notch) actually searches for this outline. Both are answerable, but require the full context this
investigation did not have.

---

## 5. Ensuite separation — verified, not assumed

The brief asked not to assume the same fix covers ensuite strips. Checked directly:

- By construction (`_private_rows`, `_rows_of`), an ENSUITE-kind bathroom is **never** a lone row —
  it is always V-split into its bedroom's row. Its depth is the ROW's depth
  (`max((area_bedroom+area_ensuite)/width, floor)`), driven mainly by the bedroom; its width is an
  area-proportional slice after both rooms' minimums are met (`_row_widths`). That is a
  fundamentally different shape mechanism from a lone SHARED_BATHROOM/GUEST_WC, which has no
  row-mate and is sized purely by its own area/width or floor.
- Measured (§2): ENSUITE aspects (p50 2.03) look similar at the median to SHARED_BATHROOM (p50
  1.97) but have a much shorter bad tail (12% over 2.5 vs 37%; 0% at the hard cap either way) —
  consistent with a bounded, recoverable defect (the prior report's ensuite-sub-row proposal) as
  opposed to the lone room's unbounded exposure to whatever width the column settles at.
- **This repro case's bathroom is a SHARED_BATHROOM, not an ensuite** — the programme's one ensuite
  belongs to a different bedroom in the other column (inferred from the image: the bedroom and
  bathroom sharing a row at matching depths on the east side, both distinct from the freestanding
  master). It belongs to category 1 (§2), not the ensuite mechanism, confirming the brief's
  suspicion that this is a different case from the one the prior investigation already covered.

**Recommendation**: keep the ensuite sub-row as its own, separate future phase, exactly as
`ROOM_PROPORTION_QUALITY_TIER_REPORT.md`'s "left for the next review" section already says. Do not
fold it into whatever comes out of this report.

---

## 6. Acceptance / summary

- **Exact root cause for the shown bathroom**: `BATHROOM` has no `preferred_aspect_ratio`, so the
  quality tier never scores it (§1.6) — *and*, independently, the one pairing move the planner
  knows has no partner available in this room's column (§1.7, confirmed by direct call). Two
  separate, stacked reasons this room was never touched, not one.
- **Corpus-wide frequency**: every SHARED_BATHROOM (p50 aspect 1.97, 74% over 1.6, 37% over 2.5)
  and every GUEST_WC (p50 3.27, 88% over 1.6, mostly against its own template's hard cap) is a lone
  full-width row, unconditionally, outside rare hard-refusal repairs. ENSUITE strips (p50 2.03) are
  common too but structurally different and much less severe in the tail.
- **Root-cause categories, kept separate**: lone full-width wet room (this repro case) / master+
  ensuite combined-depth strip (different mechanism, different future fix) / service-room (TOILET)
  strip (same mechanism as the first, worse due to the template) / fallback-shrunk variants of any
  of the above (same mechanism, deeper into deficit).
- **Best generic fix candidate**: **A (extend `preferred_aspect_ratio` to BATHROOM/TOILET, reuse
  the existing quality-tier machinery unchanged)** is the smallest, safest, highest-reuse move —
  but it has a real, bounded ceiling (the same one-ensuite-per-programme topology limit already on
  file) and **does not fix this specific repro case**, because this arm's column has no ensuite to
  pair with. **D (shape-aware, pairing-independent seam re-selection with joint two-column
  acceptance)** is the only candidate that reaches this exact room, demonstrated concretely in §4,
  but needs new scoring logic the codebase does not have (nothing today compares two columns'
  shapes against each other) and its effect on currently-valid plans is unmeasured.
- **Which roles it should apply to**: A → BATHROOM and TOILET, mirroring the bedroom-class rollout;
  not LAUNDRY (still gated off) and not ENSUITE (different mechanism, §5).
- **Expected improvement**: A reaches an unmeasured but likely small minority of lone wet-room
  strips — bounded by, and probably narrower than, the ~16% row-sharing ceiling already measured
  for bedroom-class rows, since the same single slot is now contested by two objectives. D's
  improvement is real where it applies (§4's numbers) but its reach across the corpus is unmeasured
  (would need the joint-column logic built first to measure honestly).
- **Runtime cost**: A — negligible. D — cheap in the search itself (no new candidates), but the
  joint-column scoring is new code whose cost is not yet measured.
- **Regression risk**: A — moderate (host-slot contention with the existing be8c0ca substitutions;
  needs its own threshold calibration and a full 432-context re-run before trusting it). D — higher
  and currently unquantified (would change how seams are chosen for cases that plan fine today).
- **READY / NEEDS MORE RESEARCH**:
  - **Fix A: READY** for a bounded next phase, structured exactly like `be8c0ca` (template values +
    corpus remeasurement + a tie-break rule for host-slot contention) — but should ship with an
    explicit statement of its ceiling, so it is not mistaken for a fix to cases like this one.
  - **Fix D: NEEDS MORE RESEARCH.** No existing acceptance mechanism spans two columns; a full-plan
    (not single-arm) feasibility check is required before claiming it is safe; this is real design
    work, not a small patch, even though it is the only candidate that reaches this repro case.

No production code was changed. This plan was not patched.
