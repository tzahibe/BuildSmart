# Phase 0 Research: Design Viewer & Assistant Chat

## 1. Feature 03's backend doesn't exist yet — how does this feature depend on it?

**Decision**: Treat completing `backend/app/design/generator.py` + `router.py` (per
`specs/003-parametric-design-model/data-model.md` and `plan.md`'s already-documented algorithm) as an
in-scope prerequisite phase of this feature's tasks, rather than a separate invocation of the speckit
workflow against branch `003-parametric-design-model` first.

**Rationale**: `specs/003`'s spec/plan/tasks are already fully designed and unambiguous (fixed room sizes,
remaining-area split, 1D per-floor layout, footprint-too-small error) — there is no open design question
left to resolve, only implementation. Splitting it into a separate workflow run would just add process
overhead for zero additional clarity, and this feature's User Story 1 (seeing a sketch at all) is
unreachable without it.

**Alternatives considered**: Block this feature on 003 being implemented separately first — rejected, pure
overhead given 003 has nothing left to decide. Re-deriving a different/simpler design-model algorithm
inside 004 — rejected, would duplicate and diverge from 003's already-reviewed spec for no reason.

## 2. Should the chat assistant be able to change stored project requirements?

**Decision**: No, not in this slice — the assistant only reads project context and replies conversationally
(see plan.md's Design decisions). No tool-calling/function-calling wiring to the repository.

**Rationale**: spec.md's functional requirements (FR-010/FR-011) only require sending/receiving/persisting
messages; the "may trigger re-parsing" language lives in Assumptions, not a MUST. Giving an LLM direct
write access to stored requirements without an explicit user confirmation step would mean the system
silently deciding on the user's behalf — directly against the source project's Principle C ("no deciding in
place of the user," `docs/AI_Home_Planner_SPEC.md` §2) and Principle E ("MVP before multi-agent
complexity"). It's also the kind of scope expansion (agent tool-calling, re-triggering 02+03 automatically,
handling the resulting race with a user editing the form) that deserves its own feature slice with its own
acceptance criteria, not a rider on this one.

**Alternatives considered**: Function-calling with an `update_requirements` tool that appends to the
description and re-runs parse+design — rejected for this slice per above; left as a natural follow-up
feature once this conversational baseline exists.

## 3. How should the assistant be grounded (what does it know about the project)?

**Decision**: Each chat request sends a system prompt built from the project's current `Project` record
(city/street/areas/description, parsed requirements with their source tags, and the generated design model
summary if present) plus the stored conversation history, then the new user message — same
`chat.completions` pattern as `OpenAIRequirementParser`, but a plain text reply, not a structured-output
schema (a conversational reply isn't a fixed shape the way extracted requirements are).

**Rationale**: Reuses the existing OpenAI client/pattern already in the codebase (`app/requirements/
parser.py`) instead of introducing a second way of calling the LLM. Grounding in the actual stored data
(rather than just the raw description) lets the assistant reference what was actually parsed/generated,
which is the whole point of surfacing it as "our model" per the user's request.

**Alternatives considered**: A separate embeddings/RAG-backed assistant — out of scope; `docs/
AI_Home_Planner_SPEC.md`'s RAG features (05/06) are far later phases and this project has no regulatory
documents ingested yet. Sending the full conversation history unbounded forever — acceptable for now given
expected conversation lengths for a single home-planning project; revisit with truncation/summarization if
it becomes a real cost/latency problem.

## 4. Frontend structure: router library or not?

**Decision**: No router library. `App.tsx` holds a small `view: 'form' | 'loading' | 'design'` state
(plus the current `project`), and the Design page internally toggles its own overlays (full-screen sketch,
chat, menu, technical details) as local component state / a similar small union.

**Rationale**: Three top-level views with no deep-linking requirement in spec.md (nothing asks for a
shareable/bookmarkable URL per project) doesn't justify a new dependency; `frontend/package.json` currently
has zero routing dependency and this keeps that true. If a later feature needs real URLs (e.g. a project
list/dashboard, per `docs/AI_Home_Planner_SPEC.md` Feature 21's Dashboard), that's the point to introduce
one.

**Alternatives considered**: `react-router` — reasonable and not wrong, but unnecessary weight for the
current scope; deferred until an actual multi-URL need exists.

## 5. How is the sketch actually drawn?

**Decision**: Plain inline SVG, computed client-side from the `Project.rooms`/`site_width_m`/
`site_depth_m` fields already produced by Feature 03 — one `<rect>` (+ label `<text>`) per room, scaled by
a fixed meters-to-pixels factor derived from the active floor's footprint and the available card/full-screen
size (recomputed on resize for responsiveness). A floor-tab control appears only when `rooms` span more
than one floor.

**Rationale**: The data is already axis-aligned rectangles with real dimensions (`x`, `y`, `width_m`,
`depth_m` per `backend/app/projects/models.py`'s `Room`) — nothing about it needs canvas, WebGL, or a
charting library; SVG scales cleanly for the full-screen/responsive requirement (FR-009) and stays
inspectable/stylable with plain CSS.

**Alternatives considered**: `<canvas>` — more code for pixel-pushing with no benefit here since there's no
animation or huge room count to justify canvas's performance profile. A charting/diagram library — pulls in
a dependency for something a dozen lines of SVG already does.

## 6. How is the "house being built" loading animation implemented?

**Decision**: A hand-built CSS/SVG house silhouette whose parts (foundation → walls → roof → door/windows)
reveal in stages via CSS keyframe animation, looping for as long as the pipeline (parse + design generation,
per Design decision "Pipeline orchestration") is in flight.

**Rationale**: Keeps the feature asset/dependency-free (no Lottie player, no hosted image/video), matches
FR-002's "progressive house being built, not a generic spinner," and is simple enough to loop indefinitely
without a fixed duration — appropriate since the pipeline's actual duration depends on live LLM calls.

**Alternatives considered**: A Lottie/After-Effects-exported animation — higher visual polish but adds a
runtime dependency and an asset pipeline for a single animation; not justified at this project's current
scale. A static image with a spinner overlay — explicitly what FR-002 says not to do.

## 7. Where does chat history live, and what's the record shape?

**Decision**: `backend/app/data/conversations.json`, one JSON object keyed by `project_id` → list of
`{role, content, created_at}` messages, written via a `JsonFileConversationRepository` that mirrors
`JsonFileProjectRepository`'s load/mutate/save-whole-file approach (`backend/app/projects/repository.py`).

**Rationale**: Matches this project's established, explicitly-documented-as-temporary storage mechanism
(`specs/001-project-creation/research.md`) exactly — same trade-offs, same eventual swap-to-Postgres path,
and it's literally what the user asked for ("כל השיחות יישמרו בקובץ json נוסף" — all conversations saved in
an additional JSON file). A separate file (not merged into `projects.json`) keeps an unbounded, independently
growing dataset (chat) out of the record that Features 01-03 read/write as a whole document on every save.

**Alternatives considered**: Merging conversation history onto the `Project` record itself, like Features
02/03 did for their fields — rejected: those merges are small, fixed-shape fields; a chat log is unbounded
and grows differently, and every `Project` save (e.g. a `PATCH`) would otherwise rewrite the entire
conversation history for no reason.
