# Laundry room (חדר כביסה) as a user-facing option — feasibility review

**Date**: 2026-09-16 · **State reviewed**: `main` @ `518e133`, in an isolated worktree (`worktree-015-laundry-room-option`), nothing in `main` touched · **Scope**: code-level investigation only — no implementation.

**Question asked**: can a laundry room become something a person can request, and what does turning it on actually cost/break?

---

## 0. Verdict up front

1. **The system has two independent, live planning pipelines**, and they are not equally close to supporting this: `app.vertical_slice` / `app.demo` (the actively-developed engine — every recent commit and every project memory is about this one) already carries **latent scaffolding** for a laundry room; `app.architect` / `app.geometry` (the fine-tuned-model-driven production solver, mounted via `design_router`) has **none**, and is architecturally harder to extend because its room vocabulary is frozen to what an external fine-tuned model was trained to emit.
2. **In the demo/vertical_slice engine, a laundry room is modelled but unreachable.** `ProgramRole.LAUNDRY` exists with a full `RoomTemplate`, a furniture envelope, a Hebrew label, and wet-adjacency classification — but the **parser deliberately refuses it**, and `build_room_program` (the one function that turns a spec into an actual room list) never emits it. It is dead code today, not a half-built feature quietly running.
3. **Wiring it up is not just "add one field."** Two things already fixed for the WC-alone case are hardcoded to `ProgramRole.TOILET` and would **not** apply to a laundry room: the strip-room row-sharing rescue and the hub wet-adjacency bound. A naive wire-up reopens the strip-shaped-room defect this project already spent a phase fixing, and laundry is *more* exposed to it than WC was, not less (larger minimum short side).
4. **In the production model pipeline, this is a bigger and less certain effort.** There's a reusable `UTILITY → Zone.SERVICE` mapping already in the geometry solver, but whether the frozen fine-tuned model ever actually emits `UTILITY` for a Hebrew "חדר כביסה" request is an empirical unknown, not something readable from the code. The established workaround for a concept the model doesn't know (`SAFE_ROOM`) is a post-hoc injection outside the model's own output — viable, but its own separate effort.
5. **Recommendation**: scope this to the demo/vertical_slice engine only, treat it as its own reviewed phase (schema → parser → generator wiring → generalizing the row-sharing/strip fix → a measured before/after sweep), and hold off on the production model pipeline until the question below is answered. Details in §4.

---

## 1. What already exists (demo / vertical_slice engine)

| Piece | File | State |
|---|---|---|
| `ProgramRole.LAUNDRY` enum value, with a design-intent docstring ("a utility room... plumbed like a wet room, but not one a person washes in... may sit off the kitchen or a service yard") | [model.py:179-182](../backend/app/vertical_slice/geometry_core/model.py#L179-L182) | present |
| Furniture feasibility envelope, `(0.6, 1.5)` m | [model.py:255](../backend/app/vertical_slice/geometry_core/model.py#L255) | present, unverified — see §3 |
| `RoomTemplate(min=2.5, target=4.0, max=8.0, min_short_side=1.5, …, elasticity=0.10)` | [concept_generator.py:195](../backend/app/vertical_slice/concept_generator.py#L195) | present, only ever read via `ROOM_TEMPLATES[role]`, and `role` is never `LAUNDRY` at runtime |
| Hebrew display label `"חדר כביסה"` | [requirements_view.py:294](../backend/app/demo/requirements_view.py#L294), [contract.py:39](../backend/app/demo/contract.py#L39) | present |
| Counted as a **wet role** for the family-signature classifier (ensuite vs. hall-facing) | [general_pipeline.py:183](../backend/app/vertical_slice/general_pipeline.py#L183) | present, generic |
| A copy of the same `RoomTemplate` in the test fixture dict | [test_concept_generator.py:306](../backend/tests/vertical_slice/test_concept_generator.py#L306) | present, never exercised by a LAUNDRY room in any test |

This reads as reserved scaffolding — the kind of thing added when the room taxonomy was drafted, ahead of the request path that would actually use it — not as an abandoned partial feature. Nothing here is broken; it simply has no caller.

## 2. What's missing — the actual gap

**The parser refuses it, on purpose.** `app/requirements/parser.py`'s system prompt (the Hebrew-text → structured-brief extraction step) states outright:

> "the planner knows only living, dining, kitchen, corridor, bedrooms, a safe room and bathrooms, so any OTHER room the person asks for must be reported here [`other_requests`] with topic `room_type`: חדר עבודה, **חדר כביסה**, מחסן, …"

So today, a person who asks for a laundry room gets it captured as an `other_requests` entry with a severity read off their wording — and if they phrased it as a requirement (חייב, חובה, "אני צריך"), that **can block automatic plan generation entirely** per the parser's own severity rule, rather than silently dropping it. This is the actual current behavior, and it's arguably the correct fallback given nothing downstream can act on it yet — but it's the first thing to change.

**Nothing carries the request even if the parser allowed it.** `ProgramSpec` (`app/vertical_slice/spec.py:170`) has exactly four program knobs — `bedrooms`, `safe_room`, `open_plan_living`, `wet_rooms` (+ `wet_room_kinds` for per-room detail) — and no laundry field of any kind.

**`build_room_program` never emits it.** This is the single function (`concept_generator.py:455`) that turns an `ArchitecturalSpec` into the actual list of rooms the geometry engine plans against. It adds LIVING/DINING/KITCHEN, HALL, bedrooms, SAFE_ROOM, and resolved wet rooms (TOILET/BATHROOM) — never `ProgramRole.LAUNDRY`. Confirmed by search: `ROOM_TEMPLATES[ProgramRole.LAUNDRY]` has exactly one production reader (the dict definition itself) and one test-fixture copy. It is not invoked from anywhere.

## 3. What turning it on would actually touch (demo / vertical_slice engine)

Assuming the room is added as a `ZoneGroup.SERVICE` member (the natural fit, matching TOILET/BATHROOM) and placed in the same private/service stacking column:

- **Area budget.** A `target=4.0 m²` room competes for area against bedrooms and living space under the same deficit-distribution / preferred-hard-maxima ladder that now governs the private column ([[room-area-two-level-maxima]] — calibrated 2026-09-15). It needs to be folded into that ladder, not bolted on as a separate allowance, or it will quietly steal the wrong rooms' area under a tight footprint.
- **An extra row in the column.** Every SERVICE/PRIVATE room stacks one row per column; only an ensuite shares a row with its bedroom. A laundry room with no bedroom to attach to is, structurally, exactly the same kind of thing as an extra bathroom row. The one comparable measured data point in this codebase (`programme_variants`'s own docstring) puts the cost of one extra wet-room row at roughly **40 m² of footprint** before the plan's proportions work — a laundry room is smaller than a bathroom, so the true number will be lower, but it should be **measured**, not assumed, before this ships (per [[room-template-size-narrows-its-column]] — shrinking or adding one room in a column deepens every other row sharing it).
- **The strip-room defect is not generalized.** `_rows_for_width` ([concept_generator.py:1370-1390](../backend/app/vertical_slice/concept_generator.py#L1370-L1390)) rescues a lone room that would otherwise be shape-refused (a strip) by pairing it into an ensuite's row — but **only when `row[0].role is ProgramRole.TOILET`**. A lone laundry row hitting the same failure (too narrow a column for its shape floor) gets no rescue at all. This matters more than it would for a random new room type, because LAUNDRY's `min_short_side_m` is **1.5 m**, wider than TOILET's **1.1 m** — it is *more* likely to fail the shape check in a narrow column, not less. This is exactly the defect class already found and partially fixed in [[strip-rooms-root-cause-and-fix-cost]] (the fix cost 10 lost plans out of 89, WC-alone-in-a-narrow-column, "needs row-sharing" — that finding would reopen for laundry).
- **The hub wet-adjacency bound silently ignores it.** `hub_bound`'s `wet_roles = (ProgramRole.BATHROOM, ProgramRole.TOILET)` ([concept_generator.py:3614](../backend/app/vertical_slice/concept_generator.py#L3614)) drives the M5 wet-adjacency gate in the hub-eligibility measurement tool. A plan with a laundry room wouldn't have its wet-adjacency checked against it there — understating hub sizing risk specifically for laundry-containing programmes. (Consistent with [[architectural-quality-gaps-measured]] — wet adjacency is a real, already-tracked quality gap, and hub v2.1 sizing was already measured and rejected at its topology limit; adding a third wet role without extending this bound makes that measurement quietly wrong rather than loudly wrong.)
- **The furniture envelope, `(0.6, 1.5)` m, looks too small to sanity-check anything.** Every other envelope entry is a real minimum footprint for the furniture the room needs (e.g. TOILET `(1.1, 1.4)`, KITCHEN `(2.4, 1.8)`). `(0.6, 1.5)` is narrower than a standard washing-machine-and-clearance footprint and would pass almost any room as "furnishable" — worth a real value before it's load-bearing, since right now it only fails to matter because nothing reaches it.
- **Test/fixture burden.** Both `architectural_concept_samples/` and `spatial_v2_1_samples/` (currently mid-edit on `main`, per the room-proportion-repartition work) would need new laundry-requested fixtures; existing ones are unaffected only as long as the option defaults to off.

None of this is a blocker — it's the same shape of work as the WC-fixture-vs-room effort ([[toilet-fixture-vs-wc-room]]) and the room-area-maxima effort ([[room-area-two-level-maxima]]), both already done as their own reviewed phases. The point is that it is that *shape* of work, not a one-line enum wire-up.

## 4. The other pipeline: `app.architect` / `app.geometry` (production model-driven solver)

`app/design/router.py` → `app/design/pipeline.py` is a **separate, independently-mounted** pipeline (both it and the demo pipeline are wired in `main.py`). It does not import anything from `vertical_slice`, has zero references to laundry or `כביסה`, and its room vocabulary is a different enum entirely:

`ModelRoomType` ([model_schema.py:19](../backend/app/architect/model_schema.py#L19)) is documented as **"Verbatim `RoomType` enum from the fine-tuning project's `src/datasets/schema.py`"** — i.e. it is not this codebase's to extend; it's the output vocabulary of an external, already-trained model. The file's own comment explains the precedent for a concept the model can't express: SAFE_ROOM was deliberately handled **outside** the model (injected in `authoritative_merge.py` as a post-hoc "authoritative requirement") rather than by adding a value the model was never trained to emit.

Two relevant facts cut in opposite directions:
- There **is** a generic `UTILITY` room type already in `ModelRoomType`, already mapped all the way through to a `Zone.SERVICE` in the spatial solver (`"utility": Zone.SERVICE`, [intent.py:46](../backend/app/geometry/spatial_v2/intent.py#L46)) — so geometrically, a utility/laundry-labeled room is already representable with no new code.
- Whether the **deployed model actually emits `UTILITY`** when a real person's Hebrew text asks for a laundry room is unknown from reading the code — it depends on what the fine-tuning data covered, which this repository doesn't contain. That has to be checked empirically (a handful of real requests through the model) before this path can be trusted, not assumed from the enum existing.

If the model doesn't reliably produce it, the SAFE_ROOM precedent is the template to copy: detect the laundry request upstream (in the requirements parser, same as today) and inject it as an authoritative requirement in `authoritative_merge.py`, bypassing the model for this one room type. That is a real, bounded pattern — but it is its own separate implementation, sharing essentially no code with the vertical_slice/demo work in §3.

**No recent project history touches this pipeline at all.** Every commit and every stored memory about this project — massing families, multi-level, hub eligibility, the WC/toilet fixture split, room-area maxima — landed in `vertical_slice`. That's either because it's the intended target surface going forward, or because this pipeline is a separate/legacy track outside current scope — the code alone doesn't say which, and it changes whether this section is in scope at all.

## 5. Open question, and recommendation

**Open question for you**: does "an option for a laundry room" mean the demo/vertical_slice engine (matches where all current work is going), the production `design` pipeline, or both? This determines whether §4 is in scope at all, and the two are independent enough in implementation that answering this first avoids doing throwaway design work on the wrong pipeline.

**Recommendation**:
1. Scope to the demo/vertical_slice engine first. It already carries the room-type scaffolding, it's the pipeline every recent phase of this project has extended, and the production pipeline's path (§4) has a genuine empirical unknown that should be checked separately before committing to it.
2. Treat it as its own phase, in this order, each stopped for review before the next (matching how [[toilet-fixture-vs-wc-room]] and [[room-area-two-level-maxima]] were done):
   a. `ProgramSpec` field + parser prompt/schema change (stop refusing it, start extracting it) — no generation change yet, so nothing downstream is at risk.
   b. `build_room_program` wiring, behind a request flag, default off — verify it plans at all before touching quality.
   c. Generalize `_rows_for_width`'s row-sharing rescue and `hub_bound`'s `wet_roles` tuple beyond TOILET-only, since laundry inherits the same strip-room exposure at a worse minimum short side.
   d. A measured before/after sweep (matching [[architectural-quality-gaps-measured]]'s method) on a corpus of laundry-requested briefs, checking area taken from other rooms, strip-shaped laundry rows, and footprint cost per added row — before calling it done, per [[planner-gains-must-be-quality-checked]].
3. Hold §4 (the production model pipeline) until you decide it's in scope, and if it is, verify the model's actual `UTILITY` behavior empirically before designing around it.

This document is a review only — nothing in `main` or in the demo/vertical_slice engine has been changed.
