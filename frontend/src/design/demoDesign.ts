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

/** Requested vs REALIZED corridor width — `realized_width_m` is measured off the plan. */
export interface DemoCorridor {
  requested_width_m: number | null
  requested_mode: string | null
  realized_width_m: number | null
  satisfied: boolean | null
}

/** Whether the built plan delivers each requested relationship. */
export interface DemoRelationship {
  statement: string
  satisfied: boolean
  strength: string
  source_text: string
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
  corridor?: DemoCorridor | null
  relationships?: DemoRelationship[]
  validation: DemoValidation
}

/** "This is what I understood" — mirrors `RequirementsReview`. */
export interface ReviewField {
  value: number | boolean | null
  source: 'requested' | 'inferred' | 'unknown'
}

/** A requirement the brief asked for that this stage cannot plan — the person's own words. */
export type RequestSeverity = 'preference' | 'hard_requirement' | 'ambiguous'

export interface UnsupportedRequestNote {
  text: string
  topic: string
  /** How binding the person's own wording was. Only a `preference` can be set aside and still
   *  produce a plan; the other two stop generation (see backend/app/demo/scope.py). */
  severity: RequestSeverity
}

/** The corridor width the brief asked for. `mode` decides how binding it is. */
export interface CorridorWidthNote {
  value_m: number
  mode: 'exact' | 'minimum' | 'preference'
  source: string
}

/** One understood room relationship, shown back before Generate. */
export interface RoomRelationshipNote {
  source_role: string
  target_role: string
  relation: 'adjacent' | 'direct_access' | 'near' | 'not_adjacent'
  strength: 'hard_requirement' | 'preference'
  source_text: string
  ambiguous: boolean
  /** Product wording, built by the backend — the UI never composes architectural language. */
  statement: string
}

/** The parcel and the assumptions applied to it. Everything here is either entered or derived by
 *  subtraction — the buildable rectangle is never larger than the plot. */
export interface SiteNote {
  plot_width_m: number
  plot_depth_m: number
  plot_area_m2: number
  street_facing_side: string
  front_setback_m: number
  side_setback_m: number
  rear_setback_m: number
  setback_disclaimer: string
  /** PRESENTATION-SAFE: 0 where the setbacks use up an axis, never the negative the raw
   *  subtraction produces. `has_buildable_area` separates an EMPTY region from a small one. */
  buildable_width_m: number
  buildable_depth_m: number
  buildable_area_m2: number
  has_buildable_area: boolean
  footprint_width_m: number | null
  footprint_depth_m: number | null
  footprint_fits: boolean | null
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
  unsupported_requests?: UnsupportedRequestNote[]
  corridor_width?: CorridorWidthNote | null
  room_relationships?: RoomRelationshipNote[]
  /** The rooms the plan will actually contain — what makes a missing room visible. */
  planned_rooms?: string[]
  site?: SiteNote | null
}

export interface ReviewEdit {
  front_setback_m?: number
  side_setback_m?: number
  rear_setback_m?: number
  bedrooms?: number
  safe_room?: boolean
  wet_rooms?: number
  open_plan?: boolean
  parking_spaces?: number
  floors?: number
}
