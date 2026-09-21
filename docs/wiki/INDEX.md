# Project Wiki — Index

Canonical, compact "what is true now" for this repo. Git/code/tests remain the final source of
truth above even this Wiki — every page ends with what commit it was last verified against, and a
page can be wrong the moment someone merges something new (this has happened for real here; see
the Multi-Level and Laundry pages' own histories). Raw reports/specs under `docs/*.md` and
`specs/*/` hold history, rationale, and experiments — they are evidence, not current truth once a
Wiki page supersedes them. See `docs/wiki/architecture/knowledge-system.md` for the full authority
hierarchy and how RAG relates to this Wiki.

**Start here, then `docs/PROJECT_STATE.md` for the one-paragraph-per-subsystem overview, then the
specific page below for your task.**

## Architecture

- [Architectural Quality Rubric (A–O) and Anti-Pattern Library](../architecture_reference/quality_rubric.md)
  — reference document (companion: [anti_patterns.md](../architecture_reference/anti_patterns.md)),
  the canonical rubric every geometry/circulation/interior Issue and reviewer refers to
- [Knowledge System](architecture/knowledge-system.md) — IMPLEMENTED_MERGED
- [Requirements / Parsing Semantics](architecture/requirements-parsing.md) — IMPLEMENTED_MERGED
- [Geometry / Validation](architecture/geometry-validation.md) — IMPLEMENTED_MERGED
- [Autonomous Engineering Workflow (Agent Team)](architecture/agent-team-workflow.md) — LIVE (pilot passed 2026-09-17); owner-controlled governance + Telegram control plane
  - [Issue title convention](agent-team.md) — short pointer page: `[agent] #N Title`, `renumber-titles`
- [Product Roadmap (proposed, owner-maintained)](../ROADMAP.md) — PROPOSED, not a backlog

## Features

- [Concept Engine v2](features/concept-engine-v2.md) — IMPLEMENTED, flag OFF (not live product behavior)
- [Multi-Level](features/multi-level.md) — IMPLEMENTED_MERGED (backend), not wired to the product
- [L-Massing](features/l-massing.md) — IMPLEMENTED_MERGED
- [Wet Rooms](features/wet-rooms.md) — IMPLEMENTED_MERGED
- [Room Proportion / Quality Tier](features/room-proportion-quality-tier.md) — IMPLEMENTED_MERGED
- [Laundry](features/laundry.md) — INTEGRATED on `integration/laundry-into-main`, not yet on `main` (see page)
- [Review Page — Quality Panel, Room Details, Refusal Notice](features/review-page.md) — IMPLEMENTED_MERGED

## Decisions

- [Private House V1 — Scope Decision](decisions/private-house-v1-scope.md) — APPROVED

## How to keep this current

When a task changes current system behavior: update the relevant page above, update
`docs/PROJECT_STATE.md` only if a top-level subsystem status changed, link the new
implementation/report/commit, mark what it supersedes, then run `python -m app.knowledge.cli
index --changed`. Only completed/approved behavior updates a canonical page — an investigation or
in-progress report never does, no matter how confident its own wording sounds (see the Laundry
page for a real example of exactly this).
