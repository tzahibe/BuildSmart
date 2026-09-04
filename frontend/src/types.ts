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
}

export type ChatRole = 'user' | 'assistant'

export interface ChatMessage {
  role: ChatRole
  content: string
  created_at: string
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
