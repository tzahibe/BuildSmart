export interface TaggedValue<T> {
  value: T | null
  source: 'requested' | 'inferred' | 'unknown'
}

export interface PoolField {
  requested: TaggedValue<boolean>
  length_m: TaggedValue<number>
  width_m: TaggedValue<number>
}

export interface Room {
  type: string
  floor: number
  area_m2: number
  x: number
  y: number
  width_m: number
  depth_m: number
  // Where this room's presence came from — "MODEL_INFERENCE" | "USER_REQUIREMENT" | "REGULATION"
  // (see backend/app/architect/models.py's ConstraintSource). `null` for designs generated before this
  // field existed. Not surfaced in the sketch UI yet — kept for a future "why is this room here" view.
  source: string | null
}

export type PreferenceKind = 'ROOM_AREA' | 'ADJACENCY' | 'PRIVACY' | 'OTHER'
export type PreferenceSource = 'CHAT' | 'SETTINGS'
export type PreferencePriority = 'low' | 'medium' | 'high'

export interface Preference {
  preference_id: string
  kind: PreferenceKind
  target: string | null
  related_target: string | null
  value: number | string | boolean | null
  priority: PreferencePriority
  original_text: string
  source: PreferenceSource
  created_at: string
}

export interface ChangeLogEntry {
  field: string
  old_value: unknown
  new_value: unknown
  source: 'CHAT' | 'SETTINGS'
  at: string
}

export interface Project {
  project_id: string
  city: string
  street: string
  plot_area_m2: number
  built_area_m2: number
  description: string
  status: string
  created_at: string
  updated_at: string
  // Filled in by Feature 02's parser (POST /projects/{id}/requirements) — null until first parsed.
  floors: TaggedValue<number> | null
  bedrooms: TaggedValue<number> | null
  safe_room: TaggedValue<boolean> | null
  parking_spaces: TaggedValue<number> | null
  pool: PoolField | null
  requirements_parsed_at: string | null
  // Filled in by Feature 03's generator (POST /projects/{id}/design) — null until first generated.
  site_width_m: number | null
  site_depth_m: number | null
  rooms: Room[] | null
  design_notes: string[] | null
  design_generated_at: string | null
  // Which DesignVersion is currently mirrored into the flat fields above — `null` for a project never
  // updated through the new PATCH /projects/{id} operation yet (see backend/app/design/version.py).
  active_design_version_id: string | null
  preferences: Preference[]
  change_log: ChangeLogEntry[]
}

/** The single project-mutation request body — PATCH /projects/{id}. Settings sends `source:
 * "SETTINGS"`; a future Chat Agent will send `source: "CHAT"` with the exact same `diff` shape, after
 * an explicit user confirmation (see backend/app/projects/update.py's module docstring). A diff field
 * left out entirely means "leave this alone" — never send a field just to represent "no opinion". */
export interface ProjectUpdateDiff {
  city?: string
  street?: string
  plot_area_m2?: number
  built_area_m2?: number
  description?: string
  floors?: TaggedValue<number>
  bedrooms?: TaggedValue<number>
  safe_room?: TaggedValue<boolean>
  parking_spaces?: TaggedValue<number>
  pool?: PoolField
  add_preferences?: Array<{
    kind: PreferenceKind
    target?: string
    related_target?: string
    value?: number | string | boolean
    priority?: PreferencePriority
    original_text: string
  }>
  update_preferences?: Array<{ preference_id: string; priority?: PreferencePriority; original_text?: string }>
  remove_preference_ids?: string[]
}

export interface ProjectUpdateRequest {
  source: 'CHAT' | 'SETTINGS'
  diff: ProjectUpdateDiff
}

export type ChatRole = 'user' | 'assistant'

export type ProposalActionType =
  | 'UPDATE_PROJECT_FIELDS'
  | 'ADD_PREFERENCE'
  | 'UPDATE_PREFERENCE'
  | 'REMOVE_PREFERENCE'
  | 'ROLLBACK_DESIGN_VERSION'
  | 'NO_ACTION'

/** Present on an assistant message that is proposing a change and awaiting confirmation — see
 * backend/app/chat/proposals.py's ProposalSummary. The raw diff is never sent to the frontend, only
 * enough to render Confirm/Cancel and reference the exact proposal (see ChatPanel.tsx). */
export interface ProposalSummary {
  proposal_id: string
  action: ProposalActionType
  summary: string
}

export interface ChatMessage {
  role: ChatRole
  content: string
  created_at: string
  proposal: ProposalSummary | null
}

/** Response from confirming/canceling a proposal (POST .../chat/proposals/{id}/{confirm|cancel}) —
 * `project` is the FULL updated Project when a mutation actually happened (confirm), `null` for cancel.
 * The caller always replaces its whole Project with this rather than merging, same contract as
 * `updateProject` (see api.ts) — one source of truth regardless of whether Settings or Chat wrote it. */
export interface ChatMutationResponse {
  conversation: Conversation
  project: Project | null
}

export interface Conversation {
  project_id: string
  messages: ChatMessage[]
}

export interface ProjectCreatePayload {
  city: string
  street: string
  plot_area_m2: number
  built_area_m2: number
  description: string
}

export interface FormState {
  city: string
  street: string
  plot_area_m2: string
  built_area_m2: string
  description: string
}

export interface ValidationErrorDetail {
  loc: (string | number)[]
  msg: string
}
