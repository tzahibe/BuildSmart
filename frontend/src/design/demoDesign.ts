/** The demo design contract — mirrors `backend/app/demo/contract.py`'s `DemoDesign`.
 *
 * This is the ONLY shape the demo renderer reads architecture from. Nothing that consumes it may
 * invent a door, an opening, a window or an accessibility fact that is not on the object: every
 * field here was computed by the validated backend pipeline and checked by C1–C13.
 *
 * Named `DemoDesign`, not `GeometricDesign`, deliberately — `geometricDesign.ts` already mirrors
 * the OLD solver's contract and both still exist during the demo transition. */

export interface DemoRect {
  x: number
  y: number
  width_m: number
  depth_m: number
}

export interface DemoWallFacts {
  construction: 'STANDARD_PARTITION' | 'RC_SAFE_ROOM' | 'STRUCTURAL' | 'NONE'
  boundary_context: 'EXTERIOR' | 'INTERIOR' | 'PARTY'
  can_take_a_window: boolean
}

export interface DemoRoom {
  id: string
  type: string
  /** Display name, supplied by the backend so the renderer never maps roles to words itself. */
  name: string
  x: number
  y: number
  width_m: number
  depth_m: number
  area_m2: number
  walls: Record<string, DemoWallFacts>
}

export interface DemoWallSegment {
  orientation: 'horizontal' | 'vertical'
  coord: number
  start: number
  end: number
  construction: string
  boundary_context: string
  room_ids: string[]
}

/** A boundary two spaces share with NO wall. Drawn as a deliberate absence, not by omission. */
export interface DemoOpenInterface {
  orientation: 'horizontal' | 'vertical'
  coord: number
  start: number
  end: number
  room_ids: string[]
}

export interface DemoDoor {
  a: string
  b: string
  kind: string
  width_m: number
  x: number
  y: number
  orientation: 'horizontal' | 'vertical'
  is_entrance: boolean
}

export interface DemoWindow {
  room_id: string
  side: 'N' | 'S' | 'E' | 'W'
  width_m: number
  x: number
  y: number
}

export interface DemoValidation {
  passed: boolean
  /** Product language, e.g. "כל החדרים נגישים פיזית מהכניסה". Never raw check codes. */
  statements: string[]
  warnings: string[]
  checks: Record<string, boolean>
}

export interface DemoDesign {
  plot: DemoRect
  footprint: DemoRect
  rooms: DemoRoom[]
  walls: DemoWallSegment[]
  open_interfaces: DemoOpenInterface[]
  doors: DemoDoor[]
  windows: DemoWindow[]
  parking: DemoRect[]
  garden: DemoRect[]
  entrance_walk: DemoRect
  gross_area_m2: number
  net_area_m2: number
  validation: DemoValidation
}

/** "This is what I understood" — mirrors `RequirementsReview`. */
export interface ReviewField {
  value: number | boolean | null
  source: 'requested' | 'inferred' | 'unknown'
}

export interface RequirementsReview {
  bedrooms: ReviewField
  safe_room: ReviewField
  wet_rooms: ReviewField
  open_plan: ReviewField
  parking_spaces: ReviewField
  floors: ReviewField
  built_area_m2: number | null
  footprint_width_m: number | null
  footprint_depth_m: number | null
  description: string
}

export interface ReviewEdit {
  bedrooms?: number
  safe_room?: boolean
  wet_rooms?: number
  open_plan?: boolean
  parking_spaces?: number
  floors?: number
}
