import type { GeometricDesign } from './design/geometricDesign'
import type { FootprintOptionsResponse } from './design/footprint'
import type { DemoDesign, RequirementsReview, ReviewEdit } from './design/demoDesign'
import type { SpatialEditRequest } from './design/spatialEdit'
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
/** Reports a failure the UI showed the user, so it lands in the same log as the backend's own.
 *
 * A backend-only log misses the half of the problem the person experiences: a request that never
 * arrived, a response the UI could not use, a crash in the browser. Those end the journey just as
 * completely as a 500 does. Fire-and-forget on purpose — a failing failure report must never
 * become a second error in front of the user.
 */
export function reportFailure(code: string, message: string, where: string,
                              detail = '', context: Record<string, unknown> = {}): void {
  try {
    void fetch('/failures', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, message, detail, where, context }),
    }).catch(() => {})
  } catch {
    /* never let logging surface to the user */
  }
}

/** Site-aware footprint options, computed by the BACKEND from the buildable region.
 *
 * The options used to be generated in the browser from `built_area_m2` alone, which knew nothing
 * about the land — across a 1440-scenario scan that produced 1032 refusals, 80% of all failures,
 * every one of them somebody choosing an option the system itself had offered. They now come from
 * the same module that enforces the fit rule, so an impossible outline is never on screen.
 */
export async function fetchFootprintOptions(body: {
  plot_width_m: number
  plot_depth_m: number
  street_facing_side: string
  built_area_m2: number
  front_setback_m?: number
  side_setback_m?: number
  rear_setback_m?: number
}): Promise<FootprintOptionsResponse> {
  const response = await fetch('/projects/site/footprint-options', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new PipelineStepError('לא ניתן היה לחשב את אפשרויות המתאר עבור המגרש')
  }
  return (await response.json()) as FootprintOptionsResponse
}

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

/** The backend's `POST /design/spatial-edit` rejection reasons (see
 * backend/app/geometry/spatial_edit_types.py's `RejectReason` and
 * backend/app/design/errors_http.py's `raise_spatial_edit_rejection_as_http`) — same
 * `{"error", "message"}` detail shape and same defensive-fallback convention as `DesignErrorCode`
 * above, kept as its own type rather than merged into it since these are a distinct endpoint's
 * failure modes, not the design-generation pipeline's. */
export type SpatialEditErrorCode = 'ROOM_NOT_FOUND' | 'OUT_OF_BOUNDS' | 'OVERLAP' | 'CONSTRAINT_VIOLATION' | 'UNKNOWN'

export class SpatialEditError extends Error {
  code: SpatialEditErrorCode

  constructor(code: SpatialEditErrorCode, message: string) {
    super(message)
    this.code = code
  }
}

const SPATIAL_EDIT_ERROR_MESSAGES: Record<SpatialEditErrorCode, string> = {
  ROOM_NOT_FOUND: 'החדר המבוקש לא נמצא בתכנון הנוכחי.',
  OUT_OF_BOUNDS: 'ההזזה תוציא את החדר מגבולות המבנה.',
  OVERLAP: 'ההזזה תגרום לחפיפה עם חדר אחר.',
  CONSTRAINT_VIOLATION: 'ההזזה תפגע בדרישת סמיכות מחייבת בין חדרים.',
  UNKNOWN: 'לא ניתן היה להזיז את החדר.',
}

function spatialEditErrorCodeFrom(detail: unknown): SpatialEditErrorCode {
  if (
    detail !== null &&
    typeof detail === 'object' &&
    'error' in detail &&
    typeof (detail as { error: unknown }).error === 'string' &&
    (detail as { error: string }).error in SPATIAL_EDIT_ERROR_MESSAGES
  ) {
    return (detail as { error: SpatialEditErrorCode }).error
  }
  return 'UNKNOWN'
}

/** Applies one bounded spatial edit (currently always MOVE_ROOM) to a project's CURRENT
 * GeometricDesign — see backend/app/design/router.py's `apply_spatial_edit_to_project_design`. The
 * backend is the sole authority on whether/how a room moves; this function only forwards `request`
 * verbatim and returns whatever `GeometricDesign` comes back (or throws `SpatialEditError` for a
 * REJECTED edit) — see design/spatialEdit.ts's `mergeGeometricDesignIntoProject` for folding a
 * successful result back into the caller's `Project`. */
export async function applySpatialEdit(projectId: string, request: SpatialEditRequest): Promise<GeometricDesign> {
  const response = await fetch(`/projects/${projectId}/design/spatial-edit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!response.ok) {
    let code: SpatialEditErrorCode = 'UNKNOWN'
    try {
      const body: unknown = await response.json()
      if (body !== null && typeof body === 'object' && 'detail' in body) {
        code = spatialEditErrorCodeFrom((body as { detail: unknown }).detail)
      }
    } catch {
      // response wasn't JSON at all — keep UNKNOWN
    }
    throw new SpatialEditError(code, SPATIAL_EDIT_ERROR_MESSAGES[code])
  }
  return (await response.json()) as GeometricDesign
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


/** A product-level failure from the demo pipeline: an unsupported request, or a brief the
 * validated pipeline could not realize. `message` is written for a person and is safe to show
 * as-is; `detail` carries the measured reason for support. */
export class DemoPipelineError extends Error {
  code: string
  detail: string

  constructor(code: string, message: string, detail: string) {
    super(message)
    this.code = code
    this.detail = detail
  }
}

async function demoErrorFrom(response: Response): Promise<DemoPipelineError> {
  let code = 'UNKNOWN'
  let message = 'אירעה שגיאה בעת יצירת התוכנית.'
  let detail = ''
  try {
    const body = await response.json()
    const payload = body?.detail
    if (payload && typeof payload === 'object') {
      code = payload.code ?? code
      message = payload.message ?? message
      detail = payload.detail ?? ''
    }
  } catch {
    /* keep the defaults */
  }
  return new DemoPipelineError(code, message, detail)
}

export async function getRequirementsReview(projectId: string): Promise<RequirementsReview> {
  const response = await fetch(`/projects/${projectId}/review`)
  if (!response.ok) throw await demoErrorFrom(response)
  return response.json()
}

export async function updateRequirementsReview(projectId: string, edit: ReviewEdit): Promise<RequirementsReview> {
  const response = await fetch(`/projects/${projectId}/review`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(edit),
  })
  if (!response.ok) throw await demoErrorFrom(response)
  return response.json()
}

export async function generateDemoDesign(projectId: string): Promise<DemoDesign> {
  const response = await fetch(`/projects/${projectId}/design/demo`, { method: 'POST' })
  if (!response.ok) throw await demoErrorFrom(response)
  return response.json()
}
