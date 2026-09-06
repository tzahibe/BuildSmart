import type { ChatMutationResponse, Conversation, Project, ProjectCreatePayload, ProjectUpdateRequest } from './types'

/** The backend's `/design` failure codes (see backend/app/architect/errors.py and
 * backend/app/design/pipeline.py) — a caller switches on `code`, never on the raw message text, since
 * the backend's `message` is meant for logs/debugging, not necessarily the exact wording to show a
 * user. `UNKNOWN` covers a response the backend never actually sends (network failure, an
 * unrecognized code, a non-JSON body) — treated as a safe generic fallback, not a real backend code. */
export type DesignErrorCode =
  | 'DESIGN_UNSATISFIABLE'
  | 'MULTI_FLOOR_NOT_SUPPORTED'
  | 'AUTHORITATIVE_AREA_EXCEEDS_BUDGET'
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
  AUTHORITATIVE_AREA_EXCEEDS_BUDGET:
    'שטח הבנייה קטן מכדי לכלול את הדרישות המחייבות (כמו ממ"ד). נסה/י להגדיל את שטח הבנייה.',
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

/** Thrown by `updateProject` — either a plain validation message (e.g. an invalid street/area pair,
 * 422 with a bare string `detail`) or, when the update triggered a design regeneration that then
 * failed, the SAME structured `DesignErrorCode` `generateDesign` would throw (see PATCH
 * /projects/{id}'s handling in backend/app/projects/routes/base_routes.py — it reuses
 * app/design/errors_http.py, the same mapping /design uses). `code` is only set in that second case. */
export class ProjectUpdateError extends PipelineStepError {
  code?: DesignErrorCode

  constructor(message: string, code?: DesignErrorCode) {
    super(message)
    this.code = code
  }
}

/** The single project-mutation call — see backend/app/projects/update.py's module docstring. Settings
 * and a future Chat Agent both call this with the same `ProjectUpdateRequest` shape; the caller always
 * re-fetches/replaces its local `Project` from the response rather than merging the diff itself, so the
 * frontend never maintains a second, competing copy of project state (see SettingsPage.tsx). */
export async function updateProject(projectId: string, request: ProjectUpdateRequest): Promise<Project> {
  const response = await fetch(`/projects/${projectId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!response.ok) {
    let body: unknown = null
    try {
      body = await response.json()
    } catch {
      throw new ProjectUpdateError('לא ניתן היה לעדכן את הפרויקט')
    }
    const detail = (body as { detail?: unknown } | null)?.detail
    if (detail !== null && typeof detail === 'object' && 'error' in detail) {
      const code = designErrorCodeFrom(detail)
      throw new ProjectUpdateError(DESIGN_ERROR_MESSAGES[code], code)
    }
    const message = typeof detail === 'string' ? detail : 'לא ניתן היה לעדכן את הפרויקט'
    throw new ProjectUpdateError(message)
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

/** Thrown by confirmProposal/cancelProposal — `stale: true` specifically means the backend rejected it
 * with 409 PROPOSAL_STALE (see backend/app/chat/router.py's `_load_pending_or_409`): a newer proposal
 * has since superseded this one, or it was already confirmed/canceled. ChatPanel uses this to show a
 * distinct "this is no longer the current proposal" message rather than a generic failure. */
export class ProposalError extends ChatError {
  stale: boolean

  constructor(message: string, stale: boolean) {
    super(message)
    this.stale = stale
  }
}

async function postProposalAction(projectId: string, proposalId: string, action: 'confirm' | 'cancel'): Promise<ChatMutationResponse> {
  const response = await fetch(`/projects/${projectId}/chat/proposals/${proposalId}/${action}`, { method: 'POST' })
  if (!response.ok) {
    if (response.status === 409) {
      throw new ProposalError('ההצעה הזו כבר אינה בתוקף — יתכן שהיא בוטלה או הוחלפה בהצעה חדשה יותר', true)
    }
    throw new ProposalError('לא ניתן היה לעדכן את ההצעה', false)
  }
  return (await response.json()) as ChatMutationResponse
}

/** Confirms a pending proposal — the chat-side counterpart to `updateProject`. Same contract: the
 * caller replaces its Project with `response.project` wholesale (never merges), so Chat and Settings
 * can never disagree about what the project currently looks like. */
export function confirmProposal(projectId: string, proposalId: string): Promise<ChatMutationResponse> {
  return postProposalAction(projectId, proposalId, 'confirm')
}

export function cancelProposal(projectId: string, proposalId: string): Promise<ChatMutationResponse> {
  return postProposalAction(projectId, proposalId, 'cancel')
}
