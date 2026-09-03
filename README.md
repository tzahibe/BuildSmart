# sddproject

A Node.js/TypeScript boilerplate built around [Spec-Driven Development](https://github.com/github/spec-kit) (spec-kit).

## Structure

- `.specify/` — spec-kit engine: constitution, templates, and scripts that drive the SDD workflow
- `.claude/skills/` — Claude Code skills that implement each SDD step (`/speckit-*`)
- `specs/` — feature specs, plans, and tasks live here once you start a feature (created by `/speckit-specify`)
- `src/` — application source (TypeScript)

## SDD workflow

Run these as slash commands/skills in Claude Code, in order:

1. `/speckit-constitution` — establish project principles (do this first)
2. `/speckit-specify` — write the baseline specification for a feature
3. `/speckit-plan` — turn the spec into an implementation plan
4. `/speckit-tasks` — break the plan into actionable tasks
5. `/speckit-implement` — execute the tasks

Optional, for extra rigor:

- `/speckit-clarify` — de-risk ambiguous requirements before planning
- `/speckit-analyze` — check spec/plan/tasks consistency before implementing
- `/speckit-checklist` — generate quality checklists after planning

## App scaffolding

```bash
npm install
npm run dev     # run src/index.ts with live reload
npm run build    # compile to dist/
npm test         # run vitest
```