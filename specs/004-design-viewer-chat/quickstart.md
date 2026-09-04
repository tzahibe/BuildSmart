# Quickstart: Design Viewer & Assistant Chat

Validates this feature end-to-end, per spec.md's acceptance scenarios. Covers both the completed Feature 03
backend (prerequisite) and this feature's own chat endpoints and frontend flow.

## Prerequisites

- Python 3.11+, `backend/.venv` set up (`uv sync --group dev` from `backend/`).
- Node 20+, `frontend/node_modules` installed (`npm install` from `frontend/`).
- `backend/.env` with a valid `OPENAI_API_KEY` — needed for requirement parsing (Feature 02) and the chat
  assistant (this feature); design generation itself makes no external calls.

## Run the backend

```bash
cd backend
.venv/bin/uvicorn app.main:app --reload --port 8000
```

## Run the frontend

```bash
cd frontend
npm run dev
```

## Run the backend tests

```bash
cd backend
.venv/bin/pytest
```

Expected: all tests pass, including `tests/test_design.py` (completed Feature 03) and `tests/test_chat.py`
(this feature).

## Manual validation — backend (chat API)

1. **Create and parse a project** (setup, reuses Features 01 & 02):

   ```bash
   curl -s -X POST http://127.0.0.1:8000/projects \
     -H "Content-Type: application/json" \
     -d '{"city": "מודיעין-מכבים-רעות", "street": "אגוז מכבים רעות", "plot_area_m2": 500, "built_area_m2": 150, "description": "בית עם 3 חדרי שינה, ממ\"ד"}'
   # note the project_id, then:
   curl -s -X POST http://127.0.0.1:8000/projects/<project_id>/requirements
   curl -s -X POST http://127.0.0.1:8000/projects/<project_id>/design
   ```

2. **Empty conversation before any message** (User Story 3 precondition):

   ```bash
   curl -s http://127.0.0.1:8000/projects/<project_id>/chat
   ```

   Expected: `200`, `{"project_id": "...", "messages": []}`.

3. **Send a message and get a reply** (User Story 3, Scenario 1):

   ```bash
   curl -s -X POST http://127.0.0.1:8000/projects/<project_id>/chat/messages \
     -H "Content-Type: application/json" \
     -d '{"content": "כמה חדרי שינה יש בתכנון הנוכחי?"}'
   ```

   Expected: `200`, `messages` now has 2 entries (`role: "user"` then `role: "assistant"`), and the
   assistant's reply references the project's actual parsed bedroom count.

4. **Conversation persists across requests** (User Story 3, Scenario 2):

   ```bash
   curl -s http://127.0.0.1:8000/projects/<project_id>/chat
   ```

   Expected: `200`, same 2 messages from step 3, in order.

5. **Nonexistent project**:

   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/projects/00000000-0000-0000-0000-000000000000/chat
   ```

   Expected: `404`.

6. **Empty message rejected**:

   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8000/projects/<project_id>/chat/messages \
     -H "Content-Type: application/json" -d '{"content": "   "}'
   ```

   Expected: `422`.

## Manual validation — frontend (full user flow)

With both servers running, open the frontend (`http://localhost:5173` by default):

1. **Create a project** using the existing form (Feature 01). On submit, confirm a **full-screen loading
   animation of a house being progressively built** plays — not a blank screen, not a generic spinner
   (User Story 1, Scenario 1 / FR-001/FR-002).
2. Confirm the app **automatically navigates** to the Design page once parsing + design generation finish,
   with no button to click (User Story 1, Scenario 2 / FR-003).
3. On the Design page, confirm the **sketch appears inside a bounded card** over a house-and-garden
   backdrop (User Story 2 setup / FR-005/FR-006).
4. **Click the sketch card** — confirm it expands to fill the entire screen (User Story 2, Scenario 1 /
   FR-007).
5. **Click the X** in the full-screen view — confirm it returns to the card view on the Design page
   (User Story 2, Scenario 2 / FR-008).
6. Resize the browser window (or use device emulation for a phone width) with the sketch full-screen open —
   confirm it stays legible and correctly laid out (User Story 2, Scenario 3 / FR-009).
7. In the **chat panel**, send a message — confirm a reply appears without leaving the page (User Story 3,
   Scenario 1 / FR-010). Reload the page — confirm the same conversation is still there and you can keep
   chatting (User Story 3, Scenario 2 / FR-011/FR-012).
8. Open the **menu** and select **Technical Details** — confirm it shows the fields entered at creation and
   the system-derived data (parsed requirements, generated design model) (User Story 4, Scenario 1 /
   FR-014/FR-015). Navigate back — confirm the sketch and chat are exactly as left (User Story 4,
   Scenario 2 / FR-016).
9. Narrow the browser to a common phone width (e.g. ~360px) and repeat steps 3-8 — confirm nothing is cut
   off or overlapping (FR-009 / SC-005).

## Interactive exploration

With the backend running, open `http://127.0.0.1:8000/docs` for the auto-generated Swagger UI (includes
the design and chat endpoints alongside Features 01/02's).
