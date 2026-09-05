import type { Conversation, Project, ProjectCreatePayload } from './types'

/** The backend's `/design` failure codes (see backend/app/architect/errors.py and
 * backend/app/design/pipeline.py) — a caller switches on `code`, never on the raw message text, since
 * the backend's `message` is meant for logs/debugging, not necessarily the exact wording to show a
 * user. `UNKNOWN` covers a response the backend never actually sends (network failure, an
 * unrecognized code, a non-JSON body) — treated as a safe generic fallback, not a real backend code. */
export type DesignErrorCode =
  | 'DESIGN_UNSATISFIABLE'
  | 'MULTI_FLOOR_NOT_SUPPORTED'
  | 'ARCHITECT_MODEL_UNAVAILABLE'
  | 'ARCHITECT_MODEL_TIMEOUT'
  | 'ARCHITECT_MODEL_INVALID_OUTPUT'
  | 'UNKNOWN'

/** Thrown by parseRequirements/generateDesign when the pipeline step fails — carries a user-facing
 * Hebrew message so the loading screen can show it directly (see design/LoadingScreen.tsx). */
export class PipelineStepError extends Error {}

/** `generateDesign`'s richer failure: preserves which of the backend's distinct `/design` failure
 * codes actually occurred (see `DesignErrorCode`) instead of collapsing every failure into one
 * generic string — `code` lets a caller (or a future UI) branch on the specific situation; `message`
 * is already the matching user-facing Hebrew text from `DESIGN_ERROR_MESSAGES` below. */
export class DesignGenerationError extends PipelineStepError {
  code: DesignErrorCode

  constructor(code: DesignErrorCode, message: string) {
    super(message)
    this.code = code
  }
}

const DESIGN_ERROR_MESSAGES: Record<DesignErrorCode, string> = {
  DESIGN_UNSATISFIABLE:
    'לא ניתן היה למצוא פריסה שעומדת בכל הדרישות עבור השטח שהוזן. נסה/י לשנות את שטח הבנייה או את הדרישות ולנסות שוב.',
  MULTI_FLOOR_NOT_SUPPORTED: 'תכנון בתים מרובי קומות עדיין אינו נתמך. נסה/י פרויקט עם קומה אחת.',
  ARCHITECT_MODEL_UNAVAILABLE: 'שירות התכנון אינו זמין כרגע. נסה/י שוב בעוד מספר דקות.',
  ARCHITECT_MODEL_TIMEOUT: 'יצירת התכנון לקחה יותר מדי זמן. נסה/י שוב.',
  ARCHITECT_MODEL_INVALID_OUTPUT: 'אירעה תקלה ביצירת התכנון. נסה/י שוב.',
  UNKNOWN: 'לא ניתן היה ליצור סקיצה עבור הפרויקט',
}

function designErrorCodeFrom(detail: unknown): DesignErrorCode {
  if (
    detail !== null &&
    typeof detail === 'object' &&
    'error' in detail &&
    typeof (detail as { error: unknown }).error === 'string' &&
    (detail as { error: string }).error in DESIGN_ERROR_MESSAGES
  ) {
    return (detail as { error: DesignErrorCode }).error
  }
  return 'UNKNOWN'
}

/** Thrown by sendChatMessage when the request fails — carries a user-facing Hebrew message so
 * ChatPanel can show a per-message retry state without losing the rest of the conversation
 * (contracts/chat-api.md: nothing is persisted server-side on failure either). */
export class ChatError extends Error {}

/** Raw `POST /projects` call — status-code handling (201/422/other) stays in App.tsx, which already has
 * the field-level Hebrew error-message logic for this specific endpoint. */
export function createProject(payload: ProjectCreatePayload): Promise<Response> {
  return fetch('/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function parseRequirements(projectId: string): Promise<Project> {
  const response = await fetch(`/projects/${projectId}/requirements`, { method: 'POST' })
  if (!response.ok) {
    throw new PipelineStepError('לא ניתן היה לנתח את דרישות הפרויקט')
  }
  return (await response.json()) as Project
}

export async function generateDesign(projectId: string): Promise<Project> {
  const response = await fetch(`/projects/${projectId}/design`, { method: 'POST' })
  if (!response.ok) {
    // The backend always sends `{"detail": {"error": <code>, "message": ...}}` for the failure codes
    // DESIGN_ERROR_MESSAGES knows about (see backend/app/design/router.py) — but stay defensive: a
    // non-JSON body, a plain-string `detail` (still used for a couple of unrelated 404/422 cases), or
    // an unrecognized code all fall back to UNKNOWN rather than throwing while handling the error.
    let code: DesignErrorCode = 'UNKNOWN'
    try {
      const body: unknown = await response.json()
      if (body !== null && typeof body === 'object' && 'detail' in body) {
        code = designErrorCodeFrom((body as { detail: unknown }).detail)
      }
    } catch {
      // response wasn't JSON at all — keep UNKNOWN
    }
    throw new DesignGenerationError(code, DESIGN_ERROR_MESSAGES[code])
  }
  return (await response.json()) as Project
}

export async function getChat(projectId: string): Promise<Conversation> {
  const response = await fetch(`/projects/${projectId}/chat`)
  if (!response.ok) {
    throw new ChatError('לא ניתן היה לטעון את השיחה')
  }
  return (await response.json()) as Conversation
}

export async function sendChatMessage(projectId: string, content: string): Promise<Conversation> {
  const response = await fetch(`/projects/${projectId}/chat/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
  if (!response.ok) {
    const message =
      response.status === 502
        ? 'העוזר אינו זמין כרגע, נסה/י שוב'
        : 'לא ניתן היה לשלוח את ההודעה'
    throw new ChatError(message)
  }
  return (await response.json()) as Conversation
}
