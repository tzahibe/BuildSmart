# Implementation Plan: Hub-Organised Private Wing

**Branch**: `005-hub-private-wing` (work so far is on `main`; commits `2e19d89`, `d113a50`) | **Date**: 2026-09-11 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-hub-private-wing/spec.md`

## Summary

Add one new parti, `HUB_PRIVATE_WING`, to the concept generator: the public zones across the front
(the existing front-band treatment), and behind them a private wing organised around a compact
circulation cell — the "room lobby" — that bedrooms open onto from its two flanks and from the band
below it, with the wet rooms side by side in that band. It is expressed entirely in the engine's
existing slicing-tree vocabulary (`Split`/`Leaf`, `_forced_v_chain`, `ZoneSpec`, `_build_access`),
is emitted through `generate_concepts` so it inherits the forced-first / unforced-twin fallback, and
changes no existing parti, template row or Geometry Core code. It is an architectural-quality
feature: the measured targets are hub shape, hub degree, wet adjacency and room proportions, with
"every existing plan still plans" as the non-regression gate — not the rescue count.

## Technical Context

**Language/Version**: Python 3.11 (`backend/`, existing; venv at `backend/.venv`, deps via `uv`)

**Primary Dependencies**: none new. `app.vertical_slice.concept_generator` (parti generation),
`app.vertical_slice.geometry_core` (slicing-tree solver — unchanged), `app.vertical_slice.validation`
(C1–C16 — unchanged), `app.demo.service` (refusal path — unchanged).

**Storage**: N/A

**Testing**: pytest (`backend/tests`, 763 passing / 7 skipped at baseline); the 418-scenario
failure-log sweep harness used in phases 1–3 (currently session scratch scripts — see quickstart).

**Target Platform**: backend service, macOS/Linux

**Project Type**: web-service backend (engine module)

**Performance Goals**: adding the parti costs no more per scenario than the front-band parti does
today; 418-scenario sweep total may rise by at most one strategy's worth (measure, NFR-2).

**Constraints**: additive only — `ROOM_TEMPLATES` rows for existing roles, `plan_layout`,
`_plan_front_band`, `_seam_options`, `_build_access`'s rules and every Geometry Core module are
byte-identical after this feature. Deterministic, bounded search. Every hub tree goes through
`generate_concepts`, so it gets an unforced twin whose root→HALL cuts stay forced.

**Scale/Scope**: briefs with ≥ 3 bedrooms; v1 hub capacity is 4–5 rooms with a hub door (two flanks
plus two or three in the band below), so larger programmes fall through to the spine partis.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is the unfilled template — it defines no principles or gates, so
there is nothing to violate. The project's de-facto rules, recorded in its memory and honoured
throughout phases 1–3, are applied as gates instead:

| De-facto rule | How this plan satisfies it |
|---|---|
| Measure before patching the planner | Every parameter in the spec is either counted from 21 reference plans or read from the code (`doors.py`, `engine.py`, `windows.py`); acceptance is a metric script, not a judgement. |
| A "gain" is only a gain at ≥ 80 % of the requested area | Carried into §6 of the spec and into quickstart's sweep. |
| Additive changes; existing behaviour byte-identical | New strategy + new template row + new helper; the A/B gate compares full room signatures of all 111 existing primary plans. |
| Stop at the reported scope | v1 scope is regime B only (public in front); regime A, a second circulation zone, FLEX and non-rectangular envelopes are explicitly deferred. |

Post-design re-check: unchanged — Phase 1 introduced no new module, no Geometry Core change and no
template change for existing roles.

## Project Structure

### Documentation (this feature)

```text
specs/005-hub-private-wing/
├── spec.md              # feature specification (committed d113a50)
├── plan.md              # this file
├── research.md          # Phase 0: decisions taken against the actual code
├── data-model.md        # Phase 1: the hub layout entities and their invariants
├── quickstart.md        # Phase 1: how to prove the feature end to end
└── tasks.md             # /speckit-tasks output (not created here)
```

`contracts/` is intentionally absent: the feature exposes no new external interface. The demo API
payload (`DemoDesign`) is unchanged; a hub plan is just another set of rooms, walls, doors and
windows in it.

### Source Code (repository root)

```text
backend/app/vertical_slice/
├── concept_generator.py     # ALL changes land here:
│   ├── HUB_TEMPLATE              # the hub's RoomTemplate constant; ROOM_TEMPLATES rows untouched
│   ├── ConceptStrategy.HUB_PRIVATE_WING (new enum member)
│   ├── _hub_allocation(...)   # rooms -> flanks / foot band / (ensuite with master)
│   ├── _plan_hub_wing(...)    # widths, depths, ZoneSpecs — mutually consistent, like _plan_front_band
│   ├── _hub_concept(...)      # ConceptCandidate | ConceptRejection, like _front_band_concept
│   └── generate_concepts      # one added call per variant, after the front-band call
└── (everything else unchanged — geometry_core/ is not touched at all: the hub keeps role HALL)

backend/tests/vertical_slice/
└── test_concept_generator.py   # pinned tests for user stories 1–4

backend/spikes/failure_log_sweep/   # NEW: the sweep/A-B/quality scripts promoted from session scratch
├── sweep.py, free_twin_ab.py (generalised to any toggle), quality_metrics.py
```

**Structure Decision**: single existing backend module. The parti is a sibling of
`_front_band_concept` in `concept_generator.py`; no new package. The measurement harness is promoted
into `backend/spikes/` so the acceptance gates in §6 of the spec are reproducible by anyone, not only
from this session's scratch directory.

## Phase 0 — Research (see [research.md](./research.md))

Resolved against the code, not assumed: hub zone id and roles; where the strategy plugs in and how
the area-proximity sort orders it; the exact tree shape that keeps the corridor rectangle on the
root→HALL path; door overlap 1.10 m; which rooms may be interior; FLEX; regime choice for v1; hub
capacity in v1; how `_build_access` yields the CASED_OPENING to the public zone without changes.

## Phase 1 — Design

- [data-model.md](./data-model.md): `HubAllocation`, `HubPlan`, the band/flank invariants, and the
  ZoneSpec derivation.
- [quickstart.md](./quickstart.md): the exact commands that prove user stories 1–4 and the §6 gates.

## Complexity Tracking

No constitution violations to justify. One deliberate scope cut worth recording: v1 supports only the
"public band in front, hub wing behind" regime. The side-by-side regime (public column beside the
wing) needs the hub's public interface on a flank instead of its top edge and a head band for the wet
cluster; it is a second `_plan_hub_wing` mode, not a different parti, and is deferred to keep v1's
tree a single shape that can be reasoned about and tested.
