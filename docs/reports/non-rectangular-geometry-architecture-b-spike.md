# Non-rectangular geometry — Architecture B reuse spike (Issue #108)

**2-week spike, ROOT #102 child 3/3 (per `docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md` §4.B,
§6).** Answers ONE narrow question: does the EXISTING rectangle-typed pipeline (validators,
M1-M6, the demo contract, both renderers) really accept a `dict[str, Rect]` that is NOT a
slicing-tree (`solve_fixture`) output, with zero code changes, as the investigation's reuse table
(§2, §4.B) claims — before committing engineering weeks to a real non-guillotine solver. It does
not build a solver, and it does not touch product code: `app/` is unmodified by this Issue.

## 1. What was built

One hand-encoded, genuinely non-guillotine `dict[str, Rect]` for the `l-3br-corner` reference
archetype (`docs/architecture_reference/references/index.json`, `footprint_family: "L"` —
"two-wing L on a corner plot; bedrooms in their own arm, entry court formed by the L"). That entry
is `rights: metadata-only` with `files: []` — by the reference collection's own schema it carries
no per-room geometry (confirmed in the investigation report §3.3), so the layout is authored by
hand, consistent with the archetype's description, not copied from any source.

`backend/spikes/non_guillotine_reuse/hand_encoded_fixture.py` is the fixture. Nine rooms, two
wings:

- **WING_MAIN** (the pinwheel core, 5 rooms): LIVING, KITCHEN, HALL, MASTER_BEDROOM, and a
  circulation GALLERY, tiled as the textbook minimal non-guillotine rectangular dissection — the
  "pinwheel"/"windmill" partition (5 rectangles exactly covering a rectangle; the surrounded
  centre room, HALL, is what makes every full-span cut cross some room's interior).
- **WING_BED** (the bedroom arm, 4 rooms): BED2, BED3, BATH1, BATH2, an ordinary 2x2 grid — on its
  own trivially guillotine-separable (proven directly, see AC-1's control test below). The WHOLE
  9-room fixture is non-guillotine only because it CONTAINS the pinwheel core.

`app.vertical_slice.geometry_core.engine.solve_fixture`/`assign()` are never called anywhere in
this spike — every `Rect` is hand-authored, every wall type is derived from rectangle adjacency by
a small helper in the fixture module (`build_walls`, itself general-purpose, not tree-specific —
see §3), and every downstream pipeline function is called with its real, unmodified production
code.

**AC-1**: `backend/tests/vertical_slice/test_non_guillotine_reuse_spike.py::
test_fixture_layout_is_genuinely_non_guillotine` proves the layout is genuinely non-guillotine
using the exact same recognition function (`is_guillotine_separable`, imported, not
reimplemented) `measure_real_plan_shapes.py` uses for the investigation's own §3.2 finding (0/19
real plans guillotine-separable) — evaluated against every room's real polygon. A sibling test,
`test_fixture_layout_would_be_guillotine_if_the_pinwheel_core_were_removed`, proves the same
function returns `True` on the bedroom arm alone, the same self-check discipline the investigation
script uses against its own synthetic control (§3.2).

## 2. Per-module result

Every row below is a PASS/FAIL against the SAME production function, called directly, with no
mock and no reimplementation — see the named test for exact evidence. "Unchanged" means zero lines
of `app/` were touched to get this result.

| Module (Issue #102 §4.B claim) | Entry point exercised | Result | Change needed |
|---|---|---|---|
| C1 — no overlap | `validation.validate()` | **PASS, unchanged** | none |
| C3 — room areas/dims valid | `validation.validate()` | **PASS, unchanged** | none |
| C9 — furniture-envelope feasibility | `furniture.check_furniture_feasibility` + `validation.validate()` | **PASS, unchanged** | none |
| C20 — template aspect ratio | `validation.validate()` | **PASS, unchanged** | none |
| C27 — displayed dims consistent | `app.demo.contract.check_realized_dimensions` | **PASS, unchanged** | none — see note below |
| C22 — wing seams real (P9) | `validation.validate()` | **PASS, unchanged** | needs a correct `Wing.seam_leaf_sides` — a SOLVER OUTPUT obligation, not a validator change (see §3) |
| C2 — no residual interior area | `validation.validate()` | **PASS, unchanged** | none — see §3, this is a downward revision of the investigation's own classification |
| C4, C5, C6, C7, C8, C10–C13, C16–C19, C21, C23, C24, C29 (every other check `validate()` ran) | `validation.validate()` | **all PASS, unchanged** (24/25 non-C26 checks pass) | none |
| C26 — no extreme circulation | `validation.validate()` | **FAIL** — real, expected, NOT a reuse defect | see §4 |
| doors.py (`generate_interior_doors`, `resolve_entrance`, `build_entrance_door`) | called directly | **PASS, unchanged** | none |
| windows.py (`generate_windows`) | called directly | **PASS, unchanged** | none |
| M1–M6 quality metrics | `quality_metrics.measure_design`, called INSIDE `app.demo.contract.to_demo_design` | **PASS, unchanged** — all six computed a real number, no crash | none |
| Demo contract (`_wall_segments`, `to_demo_design`) | `app.demo.contract.to_demo_design` | **PASS, unchanged** | none |
| Backend renderer | `app.vertical_slice.renderer.render` | **PASS, unchanged** — produced a real SVG file | none |
| Frontend plan canvas (`DemoPlan.tsx`) | payload-shape check (no browser here — see below) | **PASS by inspection + payload round-trip** | none |

Frontend note: no browser runs in this backend worktree. `DemoPlan.tsx` was read directly — every
room, wing, door and wall is drawn independently off `room.x/y/gross_width_m/gross_depth_m` and
`design.walls[]`, never off room adjacency or wing membership — so nothing in that component reads
anything a non-guillotine layout would change. What IS mechanically verified:
`test_frontend_plan_canvas_payload_shape_is_unchanged` builds the exact `DemoDesign` JSON payload
the real API serves (`model_dump(mode="json")` + `DemoDesign.model_validate` round-trip) from this
non-guillotine design and confirms every field the component reads is present. This is
**NOT_VERIFIED at the "renders correctly in a browser" level**, only at the "the exact payload
contract holds" level.

## 3. What the spike found that the investigation's own table did not separate

Two real, load-bearing nuances the reuse claim needs, neither of which is a downstream CODE
change:

1. **`Fixture.Wing.tree: Node` is non-optional**, and `C22`'s wing-membership map
   (`validation.py::_seam_defects`, `leaves_of(wing.tree)`) reads it — but nothing else does
   (`grep`-verified: `.tree` is read only inside `geometry_core.engine` — never called here — and
   this one C22 site). This spike supplies a trivial, shape-irrelevant `Leaf` chain per wing whose
   LEAF SET is correct; that is enough. A real Architecture B solver would need to emit *some*
   tree per wing purely to satisfy this type, or `Wing.tree` needs to become optional — a
   ONE-FIELD type relaxation, not the "MUST BE REDESIGNED for a free envelope" the investigation's
   §2.1 table implies for the general case (that classification is right for a genuinely free,
   non-rectangular ENVELOPE — architecture C's problem — not for B, which keeps ordinary
   rectangular wings).
2. **`Wing.seam_leaf_sides` must be populated correctly** for C22 to mean anything (declaring
   which room sides are the seam between two wings) — a real solver's OUTPUT obligation, not a
   validator rewrite. `_seam_defects` itself (on/off-boundary checks, full-length abutment,
   wall-type-not-EXTERIOR, no-window-on-a-seam, wings-joined-by-a-realized-connection) ran
   completely unchanged and caught what it was built to catch.
3. **Wall-type derivation (PARTITION vs EXTERIOR) needs no tree at all.** This spike's
   `build_walls()` — 15 lines, general-purpose, not archetype-specific — derives every wall type
   from pure rectangle adjacency (`Rect.shared_edge_len_u`/`_side_between`, the same primitives
   `validation.py`/`doors.py` already use). A real non-guillotine solver's wall-typing step is
   exactly this algorithm, already proven correct against a non-tree input. (Not exercised:
   `RC_SAFE_ROOM`'s "strongest neighbour wins" rule and `WallType.OPEN` open-plan groups — this
   fixture has neither a safe room nor a declared open group, so that part of wall-typing is
   untested, still a small, bounded gap.)
4. **C2 ("no residual interior area") does not need a redesign**, contrary to §2.3's classification
   ("MUST BE REDESIGNED... for a general partition this becomes a real coverage proof"). C2's
   existing check is `sum(room areas) == footprint area`. For an ARBITRARY rectangle set this is
   necessary but not obviously sufficient — but combined with C1 (no pairwise overlap, which also
   ran unchanged and passed), the two together are algebraically sufficient: for any set of
   axis-aligned, non-overlapping rectangles inside a footprint of known area, area-sum equality
   IS a full coverage proof (no gap can hide once overlap is ruled out and areas sum exactly).
   No new coverage-proof code is needed for architecture B; C1+C2 already constitute one.

**Not exercised by this spike** (recorded as an honest gap, not resolved either way): C14
(corridor width along a bent/non-rectangular path) — this fixture's circulation rooms (HALL,
GALLERY) are both simple rectangles, so C14's harder "minimum inscribed width along a walking
path" case never triggered; a genuinely bent corridor is still an open question for architecture B.
RC_SAFE_ROOM wall-typing and `WallType.OPEN` open-plan groups, per point 3 above. And — most
importantly — this is ONE hand-fixed fixture, not a corpus: it says nothing about how a REAL
solver's diverse, varied rectangle-dissection outputs would move the 432-context corpus's primary
signatures (see §4).

## 4. C26 (circulation ratio) — a real failure, not a reuse defect

`validate()` ran C26 unchanged and it failed: circulation ratio 24.3% > the calibrated 24% extreme
threshold (`circulation_metrics.EXTREME_RATIO`). This is NOT a shape/reuse problem — it is this
fixture's own program design: the bedroom wing (WING_BED) is physically reachable only through the
GALLERY room (the pinwheel's 4th arm, seam-adjacent to BED2/BED3), and GALLERY was given the
CIRCULATION role so `access_rules.py`'s door table would allow it to enter the bedrooms — which
makes it large enough (23 net m²) to push the plan's total circulation share just over the
threshold. C26 is doing exactly its job: correctly catching that a real architect would give this
program a narrower corridor into the bedroom wing rather than a full room's worth of gallery. Left
as a genuine, disclosed finding rather than tuned away, because tuning it away would not be
evidence about the reuse claim — it would just be evidence this report can pick numbers that pass.

## 5. Architecture B effort estimate — REVISED DOWN, moderately

The investigation (§4.B) estimated **~8-14 engineer-weeks (~25-40 agent-days)**, with real
uncertainty attached to the validator/adjacency layer: "closer to a genuine algorithm change than
a type swap" for the 13 NEEDS POLYGON VARIANT checks (C1, C3, C4, C6-C8, C10, C14, C16, C18-C20,
C26), M1/M2/M4/M5, `wet_core.py`, and doors/windows/entrance.

This spike measured that layer directly, on a genuinely adversarial (non-guillotine, two-wing)
input, and found: **24 of the 25 checks `validate()` ran passed unchanged; doors, windows,
furniture-feasibility, `design_output.assemble`, the demo contract's `_wall_segments`, all six
M1-M6 quality metrics, the backend renderer, and the frontend payload contract all accepted the
layout with zero code changes.** The ONE genuine near-miss (C22) needs a solver OUTPUT change
(`seam_leaf_sides`), not a validator rewrite. The dominant cost driver the investigation already
correctly identified — **a fundamentally different, harder solver** (general rectangular
dissection under area/adjacency/access/exposure constraints, no guillotine guarantee, genuinely
NP-hard in general) and **the corpus-regression signature risk from broad primary-signature
churn** (§4.B: "a different partition algorithm can plausibly choose different room positions for
many/most contexts, not just merge candidates") — is **untouched by this spike**: one hand-fixed
fixture proves the DOWNSTREAM pipeline accepts non-tree geometry; it proves nothing about what a
real solver would do to hundreds of corpus contexts' primary selections.

**Revised estimate: ~6-10 engineer-weeks (~20-30 agent-days)**, down from ~8-14/~25-40 — the
reduction applies specifically to the validator/quality-metrics/contract/renderer/frontend
integration work, now measured near-zero rather than estimated with real uncertainty; the solver
and corpus-rebaselining work (still the majority of the total) is unchanged from the original
estimate, because this spike was scoped, correctly, to not touch it. **Risk stays MEDIUM-HIGH**,
for the same reason: the solver is still unbuilt and still the hard, uncertain part.

## 6. Recommendation

Architecture B's reuse claim **substantially holds** for the rectangle-typed pipeline
downstream of the solver — stronger than the investigation's own hedged language suggested. The
one honest asterisk is `Wing.tree`/`Wing.seam_leaf_sides` (§3, points 1-2), both small, additive,
solver-output-shaped requirements, not validator rewrites. **This does not change the ROOT's
existing recommendation** (`docs/NON_RECTANGULAR_GEOMETRY_INVESTIGATION.md` §6: pursue Architecture
A first, run B as parallel research) — it lowers B's estimated INTEGRATION cost once a solver
exists, without touching the solver itself, which remains the genuinely hard, unbuilt, unproven
part of B and the reason A stays the first thing to ship.

## 7. Reproducing this spike

```
cd backend
uv run pytest -q tests/vertical_slice/test_non_guillotine_reuse_spike.py -v
```

Fixture source: `backend/spikes/non_guillotine_reuse/hand_encoded_fixture.py` (not imported by
any product code — spike-only, per `pyproject.toml`'s `testpaths = ["tests"]` discipline).
