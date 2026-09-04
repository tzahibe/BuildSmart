# API Contract: Chat

Base path: `/projects/{project_id}/chat` (mounted on the existing FastAPI app in `backend/app/main.py`,
nested under a project from Feature 01, same shape-of-response pattern as Features 02/03).

Design generation itself is unchanged from Feature 03's own contract — see
`specs/003-parametric-design-model/contracts/design-api.md` for `POST /projects/{project_id}/design`; this
document only covers the new chat endpoints.

## GET /projects/{project_id}/chat

Fetch the full stored conversation for a project (User Story 3, Scenario 2).

**Responses**:

- `200 OK` → `Conversation`:

  ```json
  {
    "project_id": "uuid-string",
    "messages": [
      { "role": "user", "content": "אפשר להוסיף עוד חדר שינה?", "created_at": "2026-09-03T12:05:00Z" },
      { "role": "assistant", "content": "כרגע יש 3 חדרי שינה לפי התיאור שסיפקת...", "created_at": "2026-09-03T12:05:03Z" }
    ]
  }
  ```

  `messages` is `[]` (not an error) when nothing has been sent yet for this project.

- `404 Not Found` → `{"detail": "Project not found"}` when `project_id` does not exist.

## POST /projects/{project_id}/chat/messages

Send a user message and receive the assistant's reply, both persisted (User Story 3, Scenario 1).

**Request body**: `ChatMessageCreate`:

```json
{ "content": "אפשר להוסיף עוד חדר שינה?" }
```

- `content` MUST be non-empty (after trimming whitespace) — `422` otherwise, same convention as
  `ProjectCreate.description` in Feature 01.

**Responses**:

- `200 OK` → the full updated `Conversation` (same shape as `GET`, above), including the just-sent user
  message and the assistant's reply as its final two entries.
- `404 Not Found` → `{"detail": "Project not found"}` when `project_id` does not exist.
- `422 Unprocessable Entity` → validation error when `content` is empty/whitespace-only.
- `502 Bad Gateway` → `{"detail": "Assistant is unavailable, please try again"}` when the underlying LLM
  call fails. On this path, **nothing is persisted** — the user's message is not saved without a reply
  (data-model.md's `append_messages` atomicity note) — so the client's own optimistic UI (if any) for that
  message should be rolled back, and the user can simply resend (User Story 3, Scenario 3 / FR-013).

### What the assistant is grounded in

Not part of the wire contract (no client-supplied field), but observable in reply quality: each call
builds a system prompt from the project's current `city`/`street`/`plot_area_m2`/`built_area_m2`/
`description`, its parsed requirements (`floors`/`bedrooms`/`safe_room`/`parking_spaces`/`pool`, with their
`source` tags) if present, and a short summary of the generated design model (site dimensions, room count
per floor) if present — see research.md §3. The assistant does not call any tool and cannot itself change
`Project` (plan.md's Design decisions).
