# Implementation Plan: Wet-Room Semantics

**Branch**: to be created from `005-hub-v2` after review (none created yet) | **Date**: 2026-09-14 | **Spec**: [spec.md](./spec.md)
**Status**: plan for review — no implementation

## Summary

Replace the wet-room *count* with a count **plus kinds** (`SHARED_BATHROOM` / `ENSUITE` / `GUEST_WC` /
`UNSPECIFIED`, each `REQUIRED` or `FLEXIBLE`), carried from the parser through the project, the review
screen and chat into `ProgramSpec`; derive the programme from the kinds with today's behaviour as the
`UNSPECIFIED` default; decide variant eligibility on semantics before ranking; refuse the
"nobody-can-wash" configuration before planning (decision A); and enforce the realized doors with a
new fail-closed validator C17. Land it in six independently gated phases, each proven byte-identical
on the failure-log sweep, so the feature can stop after any phase without leaving the product in a
mixed state.

## Technical Context

**Language/Version**: Python 3.11 (`backend/`, venv `backend/.venv`); TypeScript/React (`frontend/`)
**Primary modules touched**: `app/requirements/parser.py`, `app/projects/models.py` + `repository.py`,
`app/demo/requirements_view.py`, `app/demo/scope.py`, `app/chat/intent.py` + `proposal_builder.py`,
`app/vertical_slice/spec.py`, `concept_generator.py` (`build_room_program`, `programme_variants`),
`validation.py`, `general_pipeline.py` (pass kinds to `validate`), `app/demo/contract.py`
(`_STATEMENTS["C17"]`), `frontend/src/design/ReviewPage.tsx`.
**Unchanged by construction**: Geometry Core, `ROOM_TEMPLATES`, `plan_layout`, seam/row logic, the
daylight ordering, `generate_concepts` sorting, corridor rules.
**Testing**: pytest (778 passing / 6 skipped at the interim-guard baseline in an isolated worktree;
3 failing = the fixtures decision C replaces); failure-log sweep `spikes/failure_log_sweep/ab.py`;
envelope grid to be promoted from session scratch to `spikes/failure_log_sweep/envelope.py`.
**Baseline to measure against**: HEAD + interim guard (`variant_keeps_bathroom_access`) + daylight
ordering: 107 planned, 0 C8, 0 PLAN_FAILED_VALIDATION, 593 s ON arm.

## Working-tree caveat

Another session is editing `concept_generator.py` (hub-v2 hunks) and `specs/005-*` in the same
checkout. Every gate in this plan is run in an **isolated worktree** (HEAD + this feature's hunks only),
as the daylight/guard measurements were. Merging the two streams is a review-time decision, not
something this plan assumes.

## Constitution Check

- Additive vocabulary; legacy path byte-identical (spec NF-1/NF-2) — verified by sweep, not asserted.
- Refusals arrive before planning and say why in the person's terms (decision A message, review rows).
- No guessing: unstated kinds are shown as defaults, never inferred as requests.
- Fail closed: C17 fails on anything it cannot resolve; I1–I4 fail on anything not proven.

## Data model (see spec §3)

```
requirements/parser.py   WetRoomKindItem(BaseModel): kind, host, strength, source_text
                         RequirementExtraction.wet_room_kinds: list[WetRoomKindItem] = []
projects/models.py       WetRoomKindRecord(BaseModel): kind: str, host: str|None, strength: str,
                                                        source_text: str, source: SourceTag
                         Project.wet_room_kinds: list[WetRoomKindRecord] = []
                         ProjectUpdate.wet_room_kinds: list[WetRoomKindRecord] | None
vertical_slice/spec.py   WetRoomKind(Enum), WetRoomStrength(Enum), WetRoomRequirement(frozen dataclass)
                         ProgramSpec.wet_room_kinds: tuple[WetRoomRequirement, ...] = ()
demo/requirements_view   WetRoomKindNote (display), ReviewEdit.wet_room_kinds: list[WetRoomKindEdit]|None
demo/scope.py            ScopeCode.NEEDS_CLARIFICATION
concept_generator.py     ProgramRoom gains `wet_kind: WetRoomKind | None` (None for non-wet rooms)
validation.py            validate(..., wet_room_kinds=()) → C17
```

Strings, not enums, in every stored record (`RoomRelationshipRecord` precedent) so an unknown value
on disk deserialises; the *use* of an unknown value fails closed (C17 / I-checks), never the load.

## Phases

Each phase: implement → unit tests → full suite → sweep gate in the isolated worktree → stop for
review. A phase that fails its gate is not "tuned"; it is reported.

### Phase 1 — Engine vocabulary and programme derivation (no behaviour change)
- `spec.py`: `WetRoomKind`, `WetRoomStrength`, `WetRoomRequirement`, `ProgramSpec.wet_room_kinds`.
- `concept_generator.build_room_program(spec)`: resolve kinds → `ProgramRoom.wet_kind` and
  `entered_from`; `UNSPECIFIED` fill = today's algorithm in today's order (extract it into
  `_default_wet_kinds(count, has_master)` so the default is one named function, testable alone).
- Tests: snapshot equality for every `PROGRAMS` entry and for wet 1–3 × bedrooms 1–6 with empty kinds;
  explicit-kind derivation; padding.
- **Gate**: sweep `--toggle wetkinds` = no-op (107/107 identical; all counters equal). Nothing reads
  kinds yet, so this must be exactly zero-diff.

### Phase 2 — Invariants and decision A, before planning
- `scope.check_supported`: I1–I4 over the derived programme; I4 → `ScopeCode.NEEDS_CLARIFICATION`
  with a message naming the bedroom(s) without a bathroom and stating what is missing — same refusal
  shape and failure-log entry as `CLARIFICATION_REQUIRED`. **The message reports the ambiguity /
  missing access requirement; it does not choose a resolution for the person.** It may list the
  representable ways to answer (add a shared bathroom, change a kind) as options, never as a default.
- Carrier for explicit kinds: `Project.wet_room_kinds` (additive, default `[]`) and its mapping in
  `spec_for`, so the invariants have an input before Phase 5. Parser, repository signatures, review
  and chat stay in Phase 5.
- `demo/contract.py` / router: the new code is surfaced like the existing scope codes.
- Tests: each invariant; decision-A brief refuses before `run_general` is called (monkeypatch spy).
- **Gate**: sweep unchanged (the log has no explicit kinds); one new refusal code in the enum, 0 in
  the sweep.

### Phase 3 — Variant eligibility on semantics; remove the interim guard
- `programme_variants`: FR-7. `FLEXIBLE` on a `SHARED_BATHROOM`/`UNSPECIFIED`-defaulted-to-shared item
  → variant with that item as `ENSUITE(host=BEDROOM)`, if I1–I4 hold. Delete
  `variant_keeps_bathroom_access` and its tests; replace with US3 (a)/(b)/(c) tests.
- Docstrings of `programme_variants` and `generate_concepts` state the ranking contract (FR-8); test
  asserts a `REQUIRED` brief's candidate pool has no non-host bedroom→bathroom edge.
- Daylight-fix regression test stays on its `wet_rooms=4` programme; add the `FLEXIBLE` variant of the
  reported 15.00×11.73 brief as the positive case for the second-suite ordering through the real path.
- **Gate**: sweep 107/107 identical, GAINED 0, LOST 0 (no flexible brief exists in the log).

### Phase 4 — C17, fail closed
- `validation.validate(..., wet_rooms)` receives the **authoritative resolved requirements** (zone id,
  kind, host) from the programme; door-set rule per kind; unresolvable → fail with detail
  `"<zone>: kind unknown"`. **C17 compares geometry to the requirements; it never infers intent from
  geometry** — a bathroom that happens to be entered from a bedroom is a failure against a
  `SHARED_BATHROOM` requirement, not evidence of an ensuite. `general_pipeline._realize` passes `spec.program.wet_room_kinds` **after**
  `build_room_program` has padded them, so legacy programmes are fully resolved and C17 evaluates
  their defaults (never "no kinds → skip").
- `contract._STATEMENTS["C17"]`; validation summary lists it; failure-log entry names the zone.
- Tests: passes on every baseline fixture and on every plan the sweep delivers; fails on a doctored
  door set; fails on missing kind.
- **Gate**: sweep — C17 failures 0 on both arms; 107/107 identical.

### Phase 5 — Parser, storage, review, chat (decision B)
- Parser: prompt rules (spec §5), `wet_room_kinds` field, count/kind reconciliation → `ambiguous`.
- Storage: `Project.wet_room_kinds`, repository create/update, `ProjectUpdate` diff.
- `requirements_view`: `WetRoomKindNote` rows incl. "לא צוין — ברירת מחדל: …"; `ReviewEdit` per-row
  kind/host/strength; count edit re-pads/truncates; `spec_for` builds `ProgramSpec.wet_room_kinds`.
- Chat: `_UPDATABLE_FIELDS += ("wet_rooms", "wet_room_kinds")`; intent examples for "לא משנה איפה";
  proposal renders the kind change; confirm applies it through the same repository path as review.
- Frontend `ReviewPage.tsx`: rows with a kind select, host (for ENSUITE), and a "גמיש" toggle; the
  Generate button stays disabled while any row is `ambiguous`; new `ReviewLimits`-style test.
- Tests: `CANNED` briefs extended with three kind-bearing briefs; round-trips; frontend tests.
- **Gate**: sweep unchanged (legacy replay carries no kinds); demo tests green.

### Phase 6 — Envelope and fixtures (decisions C, D)
- Promote the grid to `spikes/failure_log_sweep/envelope.py`; run it; rewrite the `scope.py` comment
  and the minimum-area claims from its output; review `limits` text if it quotes areas.
- `test_demo_p0`: replace the three 13.2×10.2 m 4BR/2wet tests with (i) a refusal test on that
  footprint and (ii) supported-case fixtures for 4, 5 and 6 bedrooms on footprints the grid proves,
  each asserting C17 and per-kind reachability.
- **Gate**: full suite green with no skipped-by-convenience tests; grid output committed beside
  `BASELINE.md`.

## Test gates summary

| gate | where | pass condition |
|---|---|---|
| G-unit | pytest | all green; phase-specific tests fail when the phase's code is reverted |
| G-sweep | `ab.py --toggle wetkinds` (isolated worktree) | planned 107→107, byte-identical 107/107 (+alts), LOST 0, GAINED 0, C8 0/0, PLAN_FAILED_VALIDATION 0/0, C17 0, crashes 0, ON arm ≤ 1.05 × 593 s |
| G-daylight | `ab.py --toggle daylight` | identical to the interim-guard run |
| G-envelope | `envelope.py` | every planned cell passes C17; numbers written into `scope.py` |
| G-fixtures | `test_demo_p0` | refusal test + 4/5/6BR supported fixtures green |

## Migration / rollout

- Purely additive schema; no data rewrite; old records load as `UNSPECIFIED` (spec §7).
- **Safe backend checkpoint — after Phase 4.** With kinds always `UNSPECIFIED` the product is exactly
  the interim-guard product plus C17 and the decision-A guard. It is safe to stop here, but it is not
  a product release: nobody can yet express, review or confirm a wet-room kind.
- **Complete product release point — after Phase 5**, when the semantics can be expressed in the
  brief and in chat, and are visible and confirmable on the Review screen before generation.
- `variant_keeps_bathroom_access` removal is inside Phase 3, gated by equivalence on the sweep.
- `docs/WET_ROOM_SEMANTICS_PROPOSAL.md` is kept as the evidence record; this plan and spec are the
  contract.

## Risks

- **Parser adherence** (as with every field): the prompt can be ignored by the model. Mitigated by the
  review rows (nothing is planned unseen) and by the count/kinds reconciliation → `ambiguous`.
- **C17 on hub plans**: the hub parti's wet rooms sit in the lobby's foot band; their doors are on the
  lobby (circulation) — expected to pass, but it is the one parti whose door builder differs, so
  Phase 4's sweep must be read per strategy.
- **Concurrent hub-v2 edits** in the same file: rebase cost, not a design risk; isolated-worktree
  gating keeps the measurements honest either way.

## Complexity Tracking

None of the constitution's simplicity rules is violated: one new enum family, one new validator, no
new parti, no new solver behaviour.
