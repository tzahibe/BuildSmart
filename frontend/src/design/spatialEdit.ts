import type { Project, Room } from '../types'
import type { GeometricDesign } from './geometricDesign'

/** Mirrors `backend/app/geometry/spatial_edit_types.py`'s `Direction` — NOT redefined semantics, just
 * the same four literal labels the backend's `direction_delta` already owns. The frontend never maps
 * a direction to a coordinate delta itself; see `applySpatialEdit` in `../api.ts`, which only ever
 * sends this label to the backend and renders back whatever `GeometricDesign` it returns. */
export type Direction = 'NORTH' | 'SOUTH' | 'EAST' | 'WEST'

/** Request body for `POST /projects/{project_id}/design/spatial-edit` — field names match
 * `backend/app/design/router.py`'s `SpatialEditRequest` exactly (`room_id`/`direction`/`distance_m`). */
export interface SpatialEditRequest {
  room_id: string
  direction: Direction
  distance_m?: number
}

/** Folds a spatial-edit endpoint's response (a bare `GeometricDesign` — see the router's
 * `response_model=GeometricDesign`) into a full `Project`, the shape every other mutation in this
 * app (`updateProject`, chat proposals) already returns and `onProjectUpdated` already expects — so
 * the rest of the app (floor tabs' room list, TechnicalDetailsPage, etc.) never has to special-case a
 * project whose `rooms`/`site_width_m`/`site_depth_m` disagree with its `geometric_design`. Pure
 * reshaping of fields the backend already computed — no coordinate math, no direction semantics. */
export function mergeGeometricDesignIntoProject(project: Project, design: GeometricDesign): Project {
  const rooms: Room[] = design.rooms.map((room) => ({
    type: room.type,
    floor: room.floor,
    area_m2: room.area_m2,
    x: room.x,
    y: room.y,
    width_m: room.width_m,
    depth_m: room.depth_m,
    source: room.source,
  }))

  return {
    ...project,
    geometric_design: design,
    rooms,
    site_width_m: design.footprint.width_m,
    site_depth_m: design.footprint.depth_m,
  }
}
