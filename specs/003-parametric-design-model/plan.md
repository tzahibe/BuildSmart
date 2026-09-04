# Implementation Plan: Parametric Design Model

**Branch**: `003-parametric-design-model` | **Date**: 2026-09-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-parametric-design-model/spec.md`

## Summary

Add an endpoint that generates a deterministic room layout for a parsed project — no LLM — and merges it
directly into `Project` (same pattern as Feature 02): site dimensions (assumed square, from
`plot_area_m2`), a per-floor room list (living room/kitchen/bathroom/safe room on the ground floor,
bedrooms distributed across floors), each room with an area and a simple position/size. Unknown
`bedrooms`/`safe_room` are excluded (never guessed) with the omission recorded in a `design_notes` list.

## Technical Context

**Language/Version**: Python 3.11 (existing `backend/` package)

**Primary Dependencies**: FastAPI, Pydantic (existing) — no new dependency; this is pure arithmetic, no
external calls.

**Storage**: Merged into `Project` (`backend/app/projects/models.py`/`repository.py`), same JSON-file
mechanism as everything else — see Feature 01/02's research.md for why, unchanged here.

**Testing**: pytest, no `TestClient`/API mocking needed beyond what Features 01/02 already use — the core
logic (room generation) is pure and gets direct unit tests in addition to endpoint-level tests.

**Target Platform**: Same backend web service; no new deployment target.

**Project Type**: Backend only — no frontend UI in this slice (same "add UI later if asked" pattern as
Feature 02).

**Performance Goals**: Pure in-process arithmetic; trivially under spec.md's 10-second budget.

**Constraints**: MUST NOT call an LLM or any external service (FR-011, and the source spec's Principle D —
geometry is deterministic, not language-model reasoning). MUST NOT fabricate bedroom/safe-room counts when
unknown (FR-007/FR-008).

**Scale/Scope**: One endpoint, one new small module (`backend/app/design/`), ~4 new fields on `Project`.

## Constitution Check

`.specify/memory/constitution.md` is still the unfilled template — no project-specific gates exist (same
note as Features 01/02). No violations to justify.

## Project Structure

```text
backend/
├── app/
│   ├── main.py                    # mounts the new design router
│   ├── projects/
│   │   ├── models.py              # + Room, site_width_m/site_depth_m/rooms/design_notes/
│   │   │                          #   design_generated_at on Project
│   │   └── repository.py          # + ProjectRepository.set_design_model(...)
│   └── design/                    # new
│       ├── __init__.py
│       ├── generator.py           # pure function: Project -> (site dims, rooms, notes) — no I/O
│       └── router.py              # POST /projects/{project_id}/design
└── tests/
    └── test_design.py             # new — unit tests for generator.py + endpoint tests

frontend/                          # untouched in this feature
```

**Structure Decision**: New `backend/app/design/` module (mirrors `app/requirements/`'s shape: pure logic
+ router, no separate storage — output merges into `Project` via a new repository method, same as
`set_parsed_requirements`). The generation algorithm lives in a plain function (`generator.py`) taking a
`Project` and returning the computed fields, kept separate from the FastAPI route so it's directly
unit-testable without HTTP/TestClient overhead — appropriate since this is pure deterministic logic with
many edge cases (unknown fields, floor counts, footprint-too-small) worth testing exhaustively.

## Design decisions (implementation detail, deliberately not in spec.md)

- **Fixed room sizes**: kitchen 12 m², bathroom 5 m², safe room 9 m² (a typical Israeli מ״מד is roughly
  this size) — reasonable placeholders per spec.md's Assumptions, not a standard.
- **Remaining-area split**: on the ground floor, after subtracting kitchen/bathroom/(safe room), the
  remainder is split evenly among "occupants" of that floor — the living room (always one) plus however
  many bedrooms are also on the ground floor (only when `floors == 1`). On an upper floor, its entire
  footprint (already split evenly across floors per FR-005) is divided evenly among the bedrooms placed on
  that floor. Bedroom count is itself split evenly across upper floors when `floors > 2` (remainder to the
  lower-numbered upper floors first).
- **Positions**: each floor is treated as its own coordinate space starting at `(0, 0)` (not offset within
  the full site) — a floor's footprint is assumed square (`sqrt(area)` per side, same placeholder
  reasoning as the site itself), and rooms are laid out in a single row along that footprint's width, each
  spanning its full depth (`width_m = area_m2 / footprint_depth_m`, `x` accumulates left to right, `y =
  0`). This is a placeholder 1D layout, not real 2D space planning — good enough to be internally
  consistent and testable, not to look architecturally sensible; a real layout is Feature 10's job.
- **Footprint-too-small check (FR-012)**: if the fixed rooms required on a floor (kitchen + bathroom on
  the ground floor, or nothing fixed on an upper floor) exceed that floor's available area, generation
  fails with a clear error before computing any room, rather than producing a negative-area room.
