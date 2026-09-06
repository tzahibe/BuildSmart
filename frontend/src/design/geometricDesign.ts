/** The stable UI geometry contract — mirrors `backend/app/geometry/geometric_design.py`'s
 * `GeometricDesign` (and its `Wall`/`DoorConnection`/`GeometricRoom`/`Footprint`) field for field. This
 * is the ONLY shape `ArchitecturalFloorPlan.tsx` is allowed to read architecture (walls/doors/
 * circulation) from — see that file's module docstring for the renderer boundary this exists to
 * enforce.
 *
 * Every field here is something the backend already computed from a solved layout; nothing in this
 * file (or anything that consumes it) may invent geometry that isn't present on the object — see
 * `frontend/src/design/SketchSvg.tsx`'s legacy fallback path for the (isolated, backward-compatible)
 * alternative used for designs generated before this contract existed. */

export type WallKind = 'exterior' | 'interior'
export type Orientation = 'horizontal' | 'vertical'

export interface Wall {
  id: string
  kind: WallKind
  orientation: Orientation
  /** Fixed coordinate: `x` for a vertical wall, `y` for a horizontal one. */
  coord: number
  /** Span along the other axis: `x` range for horizontal, `y` range for vertical. */
  start: number
  end: number
  room_ids: string[]
}

export interface DoorConnection {
  id: string
  wall_id: string
  orientation: Orientation
  coord: number
  /** Midpoint of the opening along the wall's span (same axis as the wall's `start`/`end`). */
  center: number
  width_m: number
  room_ids: [string, string]
  provenance: string
  note: string
}

export interface GeometricRoom {
  id: string
  type: string
  floor: number
  x: number
  y: number
  width_m: number
  depth_m: number
  area_m2: number
  is_circulation: boolean
  source: string | null
}

export interface Footprint {
  width_m: number
  depth_m: number
  floor: number
}

export interface GeometricDesign {
  footprint: Footprint
  rooms: GeometricRoom[]
  walls: Wall[]
  doors: DoorConnection[]
  programmed_area_m2: number
  circulation_area_m2: number
}
