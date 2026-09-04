# Phase 1 Data Model: Design Viewer & Assistant Chat

Two parts: (1) a new `Conversation` entity for chat (this feature's own data), and (2) the already-designed
`Project` fields from Feature 03 that this feature reads to render the sketch — no changes to those.

## New entity: `Conversation` (`backend/app/chat/models.py`)

Per spec.md's Key Entities: one conversation per project, an ordered sequence of messages, stored
separately from `Project` (research.md §7).

### `ChatMessage`

| Field | Type | Notes |
|---|---|---|
| `role` | `"user"` \| `"assistant"` | Who sent it. No `"system"` messages are ever stored — the grounding prompt (research.md §3) is built fresh per request, not persisted as a message |
| `content` | string | Non-empty (validated on the request side — see `ChatMessageCreate` below) |
| `created_at` | datetime (UTC) | Set server-side when the message is appended, never client-supplied |

### `Conversation`

| Field | Type | Notes |
|---|---|---|
| `project_id` | string | Matches `Project.project_id` |
| `messages` | list of `ChatMessage` | Chronological order, oldest first. Empty list, not absent/null, when a project has no chat yet — simpler for the frontend than a nullable-vs-empty distinction, and there's no "never generated" state to distinguish here the way Feature 03 has (a project simply has no messages until the first one is sent) |

### Request shape

`ChatMessageCreate`: `{ "content": string }` — the only thing a client supplies; everything else
(`role: "user"`, `created_at`, the resulting assistant reply) is server-determined.

## Persistence shape (`backend/app/data/conversations.json`)

Mirrors `backend/app/data/projects.json`'s shape (a single JSON object keyed by id):

```json
{
  "<project_id>": [
    { "role": "user", "content": "אפשר להוסיף עוד חדר שינה?", "created_at": "2026-09-03T12:05:00Z" },
    { "role": "assistant", "content": "כרגע יש 3 חדרי שינה לפי התיאור שסיפקת...", "created_at": "2026-09-03T12:05:03Z" }
  ]
}
```

A missing key means "no conversation yet for this project" (`ConversationRepository.get` returns an empty
`Conversation`, not `None`/404 — see contracts/chat-api.md).

## Reused, unchanged: Feature 03's `Project` fields

This feature's Design page reads `site_width_m`, `site_depth_m`, `rooms` (each a `Room`: `type`, `floor`,
`area_m2`, `x`, `y`, `width_m`, `depth_m`), `design_notes`, and `design_generated_at` exactly as defined in
`specs/003-parametric-design-model/data-model.md` — no new fields, no changes. The sketch is a pure
presentation of that data (plan.md's Design decisions, "Sketch rendering").

## Repository interface (`backend/app/chat/repository.py`)

```python
class ConversationRepository(ABC):
    def get(self, project_id: str) -> Conversation: ...            # empty Conversation if none stored yet
    def append_messages(self, project_id: str, *, new_messages: list[ChatMessage]) -> Conversation: ...
```

`append_messages` takes both the new user message and the assistant's reply in one call (not two separate
appends) so a single request either persists the full exchange or none of it — no state where a user
message is saved but the assistant's reply generation then fails and is lost mid-way with no record of what
happened to it (see contracts/chat-api.md's error case).

`JsonFileConversationRepository` mirrors `JsonFileProjectRepository`'s whole-file load/mutate/save pattern
(`backend/app/projects/repository.py`) — no concurrent-writer handling, same accepted, already-documented
trade-off as the rest of this project's storage (`specs/001-project-creation/research.md`).
