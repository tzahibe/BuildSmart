# Feature Specification: Design Viewer & Assistant Chat

**Feature Branch**: `004-design-viewer-chat`

**Created**: 2026-09-03

**Status**: Draft

**Input**: User description: "לאחר יצירה של פרויקט אני רוצה שהמשתמש יראה טעינה על כל המסך עם אנימציה של בית שלאט לאט נבנה. לאחר מכן הוא יעבור לעמוד הבא שאמור להיות שם סקיצה על רקע של של בית עם גינה אבל הסקיצה תהיה בריבוע שבלחיצה היא היא תפתח על כל המסך עם אפשרות לסגור בלחיצה על איקס. כמובן שהכל יהיה רספונסיבי ויהיה שם מסך שיחה עם llm באמצעות שימוש ב-AI assistant ויהיה גם תפריט שממנו הוא יוכל להגיע לפרטים הטכנים של הנתונים שהוא הזין וה-llm הזין מהמסד נתונים שלנו. וכמובן הוא יוכל להמשיך את השיחה מול המודל שלנו. כל השיחות יישמרו בקובץ json נוסף."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - From project creation to seeing the design (Priority: P1)

A person who just created a project (Feature 01) watches a full-screen loading experience — an animation of a house being built up, piece by piece — while the system works, and then lands on a Design page for that project showing a sketch of their house.

**Why this priority**: This is the connective tissue of the whole feature. Without a loading transition into a Design page, there is nowhere for the sketch, the chat, or the technical details to live, and the user has no sense that "their house" is being produced for them.

**Independent Test**: Can be fully tested by creating a project and observing that a full-screen building-house animation plays, followed by a navigation to a Design page that renders that project's sketch — without needing the chat or technical-details pieces to exist yet.

**Acceptance Scenarios**:

1. **Given** a user has just successfully created a project, **When** the system finishes preparing that project's design, **Then** a full-screen loading animation of a house being progressively built plays for the whole duration of the preparation, with no blank or frozen screen at any point.
2. **Given** the loading animation is playing, **When** the project's design becomes ready, **Then** the user is automatically taken to the Design page for that project without any extra action required.
3. **Given** a project whose design could not be prepared (e.g., the underlying generation fails), **When** the loading finishes, **Then** the user sees a clear explanatory message instead of being dropped onto a broken or empty Design page.

---

### User Story 2 - Inspect the sketch full-screen (Priority: P2)

On the Design page, the user sees a sketch of their house shown on a house-and-garden backdrop, contained inside a card. Tapping or clicking the sketch expands it to fill the whole screen for a closer look, and a visible X closes it back to the card view.

**Why this priority**: The sketch is the visual payoff of the whole pipeline (Features 01–03); letting the user actually examine it closely is the main reason to view the Design page at all. It depends on Story 1 (there has to be a Design page to put the sketch on) but not on chat or technical details.

**Independent Test**: Can be fully tested by opening a project's Design page, clicking the sketch card, confirming it fills the screen, and confirming the X closes it back to the card — independent of whether the chat or menu exist.

**Acceptance Scenarios**:

1. **Given** the Design page is showing the sketch inside its card, **When** the user clicks/taps the sketch, **Then** it expands to occupy the entire screen.
2. **Given** the sketch is shown full-screen, **When** the user clicks/taps the visible X control, **Then** it returns to the bounded card view on the Design page.
3. **Given** the sketch is shown full-screen, **When** the user changes viewport size or orientation (e.g., rotates a phone), **Then** the full-screen view stays legible and correctly laid out without needing to be reopened.

---

### User Story 3 - Continue the conversation with the assistant (Priority: P3)

On the same Design page, the user has a chat panel where they can talk to an AI assistant about their project, continuing the conversation across visits rather than starting over each time.

**Why this priority**: Valuable for refining the project after the initial sketch, but the Design page already delivers value (Stories 1–2) before any conversation happens.

**Independent Test**: Can be fully tested by sending a message in the chat panel, receiving a reply, leaving and returning to the Design page (or reloading), and confirming the prior messages are still there and new messages can still be sent.

**Acceptance Scenarios**:

1. **Given** a user is on a project's Design page, **When** they send a message in the chat panel, **Then** they receive a reply from the assistant without leaving the page.
2. **Given** a user previously exchanged messages with the assistant for a project, **When** they return to that project's Design page later (including after a reload), **Then** the full prior conversation is shown and they can keep sending new messages into it.
3. **Given** the assistant is unavailable or a request to it fails, **When** the user sends a message, **Then** the chat shows a clear error for that message while keeping the rest of the conversation history intact and lets the user retry.

---

### User Story 4 - Review the technical details behind the design (Priority: P4)

From a menu on the Design page, the user can open a Technical Details view listing the data they originally entered and the data the system produced from it (parsed requirements and the generated design model), then return to the Design page.

**Why this priority**: Supports trust and transparency, but is a secondary, read-oriented view that only matters once there's a project and a design to inspect (Stories 1–2).

**Independent Test**: Can be fully tested by opening the menu on a project's Design page, navigating to Technical Details, confirming the entered and system-derived data both appear, and navigating back to the Design page.

**Acceptance Scenarios**:

1. **Given** a user is on a project's Design page, **When** they open the menu and select Technical Details, **Then** they see the data they originally entered for the project and the data the system derived from it (parsed requirements, generated design model).
2. **Given** a user is viewing Technical Details, **When** they navigate back to the Design page, **Then** the sketch and chat conversation are exactly as they left them.

---

### Edge Cases

- What happens if a user reaches (or refreshes) the Design page for a project whose design was never generated or failed to generate? The page shows a clear "not available" state with no fabricated sketch, rather than a blank or broken card.
- What happens if a user reaches the Design page for a project created before this feature existed, with no design model yet? Same clear "not available" handling as above, not a crash.
- What happens if the user opens the full-screen sketch and then opens the chat or the menu? Full-screen sketch, chat, and menu are mutually exclusive overlays — opening one closes any other that's open, and closing it returns to the Design page underneath.
- What happens over a very long conversation? The full history stays reachable by scrolling; older messages are not deleted or hidden.
- How does the page behave on very small or very large viewports? All controls (sketch card, expand/close, chat, menu) stay usable and nothing is cut off or overlapping, from common phone widths up through desktop.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST show a full-screen loading state immediately after a project is successfully created, before the user reaches the Design page.
- **FR-002**: The loading state MUST use a progressive "house being built" animation (not a generic spinner) and MUST remain visible for the entire time the project's design is being prepared.
- **FR-003**: System MUST automatically navigate the user from the loading state to the project's Design page once the design is ready, with no manual step required.
- **FR-004**: If the project's design cannot be prepared, System MUST end the loading state with a clear, user-facing explanation rather than navigating to a broken or empty Design page.
- **FR-005**: The Design page MUST display a sketch representing the project's generated design, presented over a house-and-garden themed backdrop.
- **FR-006**: The sketch MUST initially be shown inside a bounded card, not full-screen.
- **FR-007**: Clicking/tapping the sketch card MUST expand the sketch to occupy the full screen.
- **FR-008**: The full-screen sketch view MUST include a visible close control (X) that returns the user to the card view.
- **FR-009**: The Design page and every view reachable from it (full-screen sketch, chat, technical details) MUST remain fully usable — no overlapping, cut-off, or unreachable controls — across mobile and desktop viewport sizes.
- **FR-010**: The Design page MUST provide a chat panel where the user can send messages to an AI assistant and view its replies.
- **FR-011**: The chat MUST show the project's full prior conversation (if any) when the Design page is opened, and MUST let the user continue sending new messages into that same conversation.
- **FR-012**: System MUST persist each project's full chat conversation, keyed to that project, separately from the project's own entered/derived data, so it survives navigation and reloads.
- **FR-013**: If a message to the assistant fails, System MUST show a clear error for that message without discarding the rest of the conversation, and MUST let the user retry.
- **FR-014**: The Design page MUST provide a menu offering navigation to a Technical Details view for the project.
- **FR-015**: The Technical Details view MUST display both the data the user originally entered for the project and the data the system subsequently derived or generated for it (parsed requirements and generated design model).
- **FR-016**: Navigating to Technical Details and back MUST preserve the Design page's sketch and chat conversation state exactly as they were.

### Key Entities

- **Conversation**: The ongoing chat exchange between a user and the AI assistant for one project — an ordered sequence of messages, each with who sent it, its content, and when it was sent. One conversation per project; persisted separately from the project's own record (per Feature 01) so it can be retrieved and continued later.
- No new entity is introduced for the sketch or Design page itself — they present data that already exists on the Project (Feature 01's entered fields, Feature 02's parsed requirements, Feature 03's generated design model).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After creating a project, a user sees a continuous house-building loading animation with no blank/frozen screen, then lands on that project's Design page as soon as its design is ready.
- **SC-002**: 100% of the time, a user can open the sketch to full screen and close it back with a single tap/click in each direction, on both a common mobile width and a desktop width.
- **SC-003**: A user can send a message to the assistant and receive a reply without leaving the Design page, and on returning to the project later, sees the entire prior conversation and can continue it.
- **SC-004**: A user can reach the Technical Details view from the Design page's menu in a single action, and it shows both what they entered and everything the system derived for that project.
- **SC-005**: All Design-page controls (sketch card/expand/close, chat, menu) remain fully usable with nothing cut off or overlapping across viewport widths from common phone sizes through desktop.
- **SC-006**: If a project's design fails to prepare, 100% of affected users see a clear explanatory message rather than an indefinite loading animation or a blank/broken sketch.

## Assumptions

- Creating a project automatically kicks off requirement parsing (Feature 02) and design-model generation (Feature 03) as one pipeline; the loading animation in User Story 1 represents this pipeline running end-to-end, not a fixed decorative delay.
- The "sketch" is a graphical rendering derived from the existing Feature 03 parametric design model (site dimensions, floors, rooms). This feature covers presenting that rendering, not changing how the underlying model is computed.
- The house-and-garden backdrop behind the sketch card is a static, decorative backdrop, not itself interactive or data-driven.
- The AI assistant chat is scoped to the current project: it can discuss the project and help refine its requirements, and a message that changes requirements may be re-parsed (Feature 02) and may trigger design regeneration (Feature 03). It is not a general-purpose or cross-project assistant.
- "Technical details" is scoped to data this system already owns for the project — the fields entered at creation (Feature 01), the parsed requirements with their requested/inferred/unknown tags (Feature 02), and the generated design model (Feature 03) — not external regulatory/planning data, which no feature in this system produces yet.
- Chat conversation history is kept indefinitely per project (no automatic expiry) and is viewable/continuable across sessions.
- No authentication/authorization is introduced by this feature, consistent with the rest of the system to date (single implicit user).
- "Responsive" covers common mobile and desktop browser viewport widths; a dedicated native mobile app is out of scope.
- Only the X control is required to close the full-screen sketch view; other conventional ways of closing it (e.g., a keyboard shortcut) are a nice-to-have, not a requirement.
