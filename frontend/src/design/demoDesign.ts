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

/** `x`/`y` is the room's GROSS rectangle's corner — the centerline allocation the walls (drawn
 * from this same rectangle) actually run along. `width_m`/`depth_m`/`area_m2` are the NET
 * (usable, wall-inset) triple: `width_m * depth_m === area_m2` always (backend check C27).
 * `gross_width_m`/`gross_depth_m`/`gross_area_m2` are the drawing rectangle at `x`,`y` — see
 * `docs/wiki/architecture/geometry-validation.md` ("Realized dimensions: gross vs net"). */
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
  gross_width_m: number
  gross_depth_m: number
  gross_area_m2: number
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
  /** The room the leaf opens into, and the hinged jamb — both decided by the engine. The drawing
   *  renders the door symbol from these; it never decides a swing itself. */
  swings_into?: string
  hinge_x?: number
  hinge_y?: number
  /** The open leaf's own direction in degrees (`doors.py::Door.swing_deg`: 0=+x, 90=+y, 180=-x,
   *  270=-y) — `DoorSymbol` places the leaf from this alone, never from a room lookup. */
  swing_deg?: number
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

/** One engine-placed semantic layout object (Issue #39) — mirrors `app.demo.contract.
 * LayoutObjectOut` exactly. `clearance_*` always contains the object's own footprint (`x`/`y`/
 * `width_m`/`depth_m`): a footprint plus its required use clearance, never a disjoint zone. The
 * renderer draws these as-is — never inventing a decorative object of its own. */
export interface DemoLayoutObject {
  kind: string
  room_id: string
  x: number
  y: number
  width_m: number
  depth_m: number
  rotation_deg: number
  clearance_x: number
  clearance_y: number
  clearance_width_m: number
  clearance_depth_m: number
}

export interface DemoValidation {
  passed: boolean
  /** Product language, e.g. "כל החדרים נגישים פיזית מהכניסה". Never raw check codes. */
  statements: string[]
  warnings: string[]
  checks: Record<string, boolean>
}

/** M1–M6 for one plan — mirrors `app.demo.contract.QualityMetricsOut` (Issue #17). `null` only
 * when the plan genuinely has no room of the kind that metric measures. */
export interface DemoQualityMetrics {
  m1_habitable_aspect_median: number | null
  m1_habitable_aspect_max: number | null
  m2_habitable_on_envelope_ratio: number | null
  m3_circulation_share: number
  m4_hall_door_count: number | null
  m4_hall_aspect_median: number | null
  m5_wet_adjacency_ratio: number | null
  m6_public_zone_contiguous: boolean | null
  dead_space_m2: number
  wasted_circulation_share: number
  /** Corpus-level medians for context beside this plan's own M3/M4/M5/M6 (the same four stats
   *  `tests/regression_corpus/quality_baseline.json` freezes). Optional and absent from today's
   *  payload — shown only when a future backend attaches one; never computed here. */
  corpus_median?: {
    m3_circulation_share_median?: number | null
    m4_hall_aspect_median?: number | null
    m5_wet_adjacency_share?: number | null
    m6_public_contiguous_share?: number | null
  } | null
}

/** One room's exposure standing — mirrors `app.demo.contract.ExposureOut` (Issue #19). Which
 * sides sit on the envelope, and either the window that was placed or why none was. */
export interface DemoExposure {
  room_id: string
  exterior_sides: string[]
  window_side: string | null
  window_width_m: number | null
  no_window_reason: 'NO_EXTERIOR_WALL' | 'EXTERIOR_WALL_TOO_SHORT' | 'WINDOW_NOT_REQUIRED' | string | null
}

/** One wet room's privacy standing — mirrors `app.demo.contract.WetPrivacyOut` (Issue #37).
 * Display data only; the one hard rule it backs (C29) lives on the backend. */
export interface DemoWetPrivacy {
  zone_id: string
  entered_from: string | null
  entered_from_class: string
  door_facing: string | null
  direct_sight_line: boolean
  public_exposure_score: number
  circulation_obstruction: boolean
  adjacency_quality: boolean
  privacy_score: number
}

/**
 * Room-size quality, kept apart from validation: the preferred maximum is a soft target, the hard
 * one is the gate (C21). Every room above preferred is on its room as `over_preferred_ratio`;
 * `signal` is the middle tier (ranking/diagnostics, not shown); `notices` is the only user-facing
 * text — one aggregated sentence per plan for rooms far past preferred. Never in `warnings`.
 */
export interface DemoQuality {
  over_preferred: boolean
  signal: { room_id: string; ratio: number }[]
  notices: string[]
  /** Issue #21 — a room realized materially below its own template target in a plan with an
   *  explicitly requested LAUNDRY room. Never a validation failure, never a refusal. */
  laundry_notice?: string | null
  /** M1–M6 for this plan (Issue #17). Absent only for a payload built before this field existed. */
  metrics?: DemoQualityMetrics | null
  /** One entry per room (Issue #19). Absent/empty for a payload built before this field existed. */
  exposure?: DemoExposure[]
  /** One entry per wet room (Issue #37). Empty for a plan with no wet rooms. */
  wet_privacy?: DemoWetPrivacy[]
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

/** Who chose the rectangle a plan occupies (feature 006): the engine's own outline search, or the
 * person, under "advanced". */
export type OutlineOrigin = 'ENGINE' | 'PERSON'

/** The person-facing label of a plan's outline — width, depth, area — and its origin. A rectangle,
 * or an L of two wings whose bounding box `width_m x depth_m` is (`wing_dims_m` lists the primary's
 * and the arm's width and depth). Absent `shape` means a rectangle (a payload that predates it). */
export interface DemoOutline {
  width_m: number
  depth_m: number
  area_m2: number
  origin: OutlineOrigin
  shape?: 'RECTANGLE' | 'L'
  wing_dims_m?: [number, number][]
}

/** One outline the engine planned for this request, whether or not it produced a plan. */
export interface OutlineTried {
  width_m: number
  depth_m: number
  origin: OutlineOrigin
  shape?: 'RECTANGLE' | 'L'
  planned: boolean
  plans_found: number
  latency_ms: number
}

/** What the outline search did — every outline tried and what it cost. */
export interface SearchSummary {
  outlines: OutlineTried[]
  total_latency_ms: number
}

/** One plan's concept, in the person's own language (Issue #78, Concept Engine v2 4/5) — mirrors
 *  `backend/app/demo/contract.py`'s `ConceptOut`. `circulation_class` is the same class
 *  `concept_spec.realized_circulation_class` computed for this exact plan; `label`/`rationale` are
 *  already-formatted Hebrew text, never parsed or re-derived by the renderer. */
export interface DemoConcept {
  circulation_class: string
  label: string
  rationale: string
}

export interface DemoDesign {
  plot: DemoRect
  /** The building's bounding box — the footprint itself for a one-wing house. */
  footprint: DemoRect
  rooms: DemoRoom[]
  walls: DemoWallSegment[]
  open_interfaces: DemoOpenInterface[]
  doors: DemoDoor[]
  windows: DemoWindow[]
  /** Engine-placed semantic layout objects (Issue #39). Absent/empty for a payload that predates
   *  the field, or a plan with no role this Issue furnishes. */
  layout?: DemoLayoutObject[]
  parking: DemoRect[]
  garden: DemoRect[]
  entrance_walk: DemoRect
  gross_area_m2: number
  net_area_m2: number
  corridor?: DemoCorridor | null
  relationships?: DemoRelationship[]
  validation: DemoValidation
  /** Feature 006. Absent only for a design that did not come through the demo service. */
  outline?: DemoOutline | null
  /** Feature 006. Opaque family signature — never parsed or shown. */
  family?: string | null
  /** Room-size quality tiers. Absent only for a payload that predates it. */
  quality?: DemoQuality | null
  /** The footprint as its wings, one rectangle each. One entry — equal to `footprint` — for every
   *  house the engine plans today; absent for a payload that predates the field. */
  footprints?: DemoRect[]
  /** Issue #78. Absent unless the backend's `CONCEPT_ENGINE_V2_ENABLED` labelled this plan. */
  concept?: DemoConcept | null
}

/** The rectangles a design is made of: its wings, or the one footprint when the payload has no
 *  wing list. The single place the fallback is decided. */
export function footprintsOf(design: DemoDesign): DemoRect[] {
  return design.footprints && design.footprints.length > 0 ? design.footprints : [design.footprint]
}

/** What the design request answers with: a plan, and the other plans that were also possible.
 *
 * `alternatives` are not runners-up. Each one passed exactly the same checks `plan` did, so the
 * person is choosing between plans, not between a plan and some lesser drawings. Empty is a real
 * and common answer — for many briefs the engine produces only one distinct layout. */
/** THE BUILDING — multi-level Phase 0. Mirrors `backend/app/demo/contract.py`'s `DemoBuilding`.
 *
 * A list of levels, each carrying a `DemoDesign` exactly as the single-storey demo produces it:
 * `levels[0].design` is the same payload as `DemoPlanSet.plan`. A two-storey building, when the
 * engine can plan one, is the same shape with two levels and one core — never a new payload. Every
 * level name and check statement is supplied by the backend; nothing here maps an index to a word. */
export interface DemoLevelEntry {
  kind: 'STREET_DOOR' | 'STAIR_ARRIVAL'
  zone_id: string
  core_id?: string | null
}

export interface DemoLevel {
  level_id: string
  index: number
  kind: 'GROUND' | 'UPPER'
  /** Display name from the backend ("קומת קרקע", "קומה א׳"). */
  name: string
  elevation_m: number
  floor_to_floor_m: number
  entry: DemoLevelEntry
  design: DemoDesign
}

/** A stair — real area on both levels it connects. Empty on a one-storey house. */
export interface DemoCore {
  core_id: string
  kind: 'STAIR'
  archetype: 'STRAIGHT' | 'L_SHAPED' | 'U_HALF_LANDING'
  lower_level_id: string
  upper_level_id: string
  zone_id: string
  footprint: DemoRect
  entry_edge: string
  arrival_edge: string
  direction: string
}

export interface DemoMassing {
  plot: DemoRect
  /** One BOUNDING BOX per level, index-aligned with `levels`. */
  level_outlines: DemoRect[]
  /** The rectangles each level is made of — one per wing — index-aligned with `levels`. Only the
   *  ground level's touch the site. */
  level_regions?: DemoRect[][]
  ground_coverage: number
  retreat_m2: number
}

/** The between-level checks (V-codes), in product language. Only checks that ran appear. */
export interface DemoBuildingValidation {
  passed: boolean
  statements: string[]
  warnings: string[]
  checks: Record<string, boolean>
}

export interface DemoBuilding {
  story_count: number
  levels: DemoLevel[]
  cores: DemoCore[]
  massing: DemoMassing
  total_gross_area_m2: number
  total_net_area_m2: number
  validation: DemoBuildingValidation
}

export interface DemoPlanSet {
  plan: DemoDesign
  alternatives: DemoDesign[]
  /** Feature 006: the outlines tried and their cost. */
  search?: SearchSummary | null
  /** Multi-level Phase 0: `plan` as the ground level of a building. Absent for a payload that
   *  predates it; `building.levels[0].design` equals `plan` when present. */
  building?: DemoBuilding | null
}

/** "This is what I understood" — mirrors `RequirementsReview`. */
export interface ReviewField {
  value: number | boolean | string | null
  source: 'requested' | 'inferred' | 'unknown'
}

/** Which side the living rooms open to. A preference: it orders otherwise-tied plans (the two
 * orientations of an L), it never refuses one. `engine` — the engine decides. */
export type PublicOpenSide = 'street' | 'garden' | 'engine'
export const PUBLIC_OPEN_SIDES: PublicOpenSide[] = ['engine', 'street', 'garden']

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
/** What the demo can plan, as the BACKEND reports it (app/demo/scope.py). Optional so a response
 * from an older backend still parses; the screen then falls back to its own bounds. */
export interface ScopeLimits {
  bedrooms_min: number
  bedrooms_max: number
  wet_rooms_min: number
  wet_rooms_max: number
  parking_max: number
  floors: number
}

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

/** One wet room as the plan will build it (specs/007). `specified` tells a stated kind from a
 * default; the label already says which. */
export interface WetRoomKindNote {
  index: number
  kind: 'shared_bathroom' | 'ensuite' | 'guest_wc' | string
  host: 'MASTER_BEDROOM' | 'BEDROOM' | null
  strength: 'required' | 'flexible' | string
  source_text: string
  specified: boolean
  label: string
  can_be_flexible: boolean
  /** "explicit" — the brief named this room; "count_derived" — a number did (a surplus toilet). */
  origin?: 'explicit' | 'count_derived' | string
}

export interface WetRoomKindEdit {
  kind: 'shared_bathroom' | 'ensuite' | 'guest_wc' | 'unspecified'
  host: 'MASTER_BEDROOM' | 'BEDROOM' | null
  strength: 'required' | 'flexible'
}

export interface RequirementsReview {
  limits?: ScopeLimits
  bedrooms: ReviewField
  safe_room: ReviewField
  wet_rooms: ReviewField
  open_plan: ReviewField
  parking_spaces: ReviewField
  floors: ReviewField
  /** Absent from a backend older than the field; the page reads that as `engine`. */
  public_open_side?: ReviewField
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
  /** One row per wet room, as it will be built. */
  wet_room_kinds?: WetRoomKindNote[]
  /** Why the wet rooms as stored cannot be planned — the refusal generation would give. Null when
   * they can. Generate stays blocked while this is set. */
  wet_room_problem?: string | null
  /** The answer the backend offers to `wet_room_problem`, as rows for the editor. Null when none. */
  wet_room_proposal?: WetRoomProposalNote | null
}

export interface WetRoomProposalNote {
  wet_rooms: number
  wet_room_kinds: WetRoomKindEdit[]
  summary: string
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
  public_open_side?: PublicOpenSide
  /** The wet rooms' kinds, one per room, replacing the stored list whole. */
  wet_room_kinds?: WetRoomKindEdit[]
}
