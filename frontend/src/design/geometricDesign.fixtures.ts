import type { DoorConnection, Footprint, GeometricDesign, GeometricRoom, Wall } from './geometricDesign'

/** Shared test fixtures for GeometricDesign-consuming components — deliberately small, hand-built
 * layouts (not real solver output) so each test only exercises the one geometric fact it names. */

export function footprint(overrides: Partial<Footprint> = {}): Footprint {
  return { width_m: 6, depth_m: 4, floor: 1, ...overrides }
}

export function room(overrides: Partial<GeometricRoom> & Pick<GeometricRoom, 'id' | 'type'>): GeometricRoom {
  return {
    floor: 1,
    x: 0,
    y: 0,
    width_m: 3,
    depth_m: 4,
    area_m2: 12,
    is_circulation: false,
    source: null,
    ...overrides,
  }
}

export function exteriorWalls(fp: Footprint): Wall[] {
  const { width_m: w, depth_m: d } = fp
  return [
    { id: 'EXT_N', kind: 'exterior', orientation: 'horizontal', coord: 0, start: 0, end: w, room_ids: [] },
    { id: 'EXT_S', kind: 'exterior', orientation: 'horizontal', coord: d, start: 0, end: w, room_ids: [] },
    { id: 'EXT_W', kind: 'exterior', orientation: 'vertical', coord: 0, start: 0, end: d, room_ids: [] },
    { id: 'EXT_E', kind: 'exterior', orientation: 'vertical', coord: w, start: 0, end: d, room_ids: [] },
  ]
}

export function door(overrides: Partial<DoorConnection> & Pick<DoorConnection, 'id' | 'wall_id' | 'room_ids'>): DoorConnection {
  return {
    orientation: 'vertical',
    coord: 3,
    center: 2,
    width_m: 0.9,
    provenance: 'direct_access_proxy',
    note: 'test fixture door',
    ...overrides,
  }
}

/** Two rooms (A: living_room, B: bedroom) sharing a vertical interior wall at x=3, `A` on the west
 * footprint edge, `B` on the east — with NO door between them by default. Pass `withDoor: true` to add
 * the matching `DoorConnection` for the "explicit door renders" case. */
export function twoRoomDesign(options: { withDoor?: boolean; circulation?: boolean } = {}): GeometricDesign {
  const fp = footprint()
  const rooms = [
    room({ id: 'LIVING_ROOM', type: 'living_room', x: 0, y: 0, width_m: 3, depth_m: 4, area_m2: 12 }),
    room({
      id: 'BEDROOM',
      type: options.circulation ? 'corridor' : 'bedroom',
      x: 3,
      y: 0,
      width_m: 3,
      depth_m: 4,
      area_m2: 12,
      is_circulation: Boolean(options.circulation),
    }),
  ]
  const interiorWall: Wall = {
    id: 'INT_LIVING_ROOM_BEDROOM',
    kind: 'interior',
    orientation: 'vertical',
    coord: 3,
    start: 0,
    end: 4,
    room_ids: ['LIVING_ROOM', 'BEDROOM'],
  }
  const walls = [...exteriorWalls(fp), interiorWall]
  const doors = options.withDoor
    ? [
        door({
          id: 'DOOR_LIVING_ROOM_BEDROOM',
          wall_id: interiorWall.id,
          orientation: 'vertical',
          coord: 3,
          center: 2,
          room_ids: ['LIVING_ROOM', 'BEDROOM'],
        }),
      ]
    : []

  return {
    footprint: fp,
    rooms,
    walls,
    doors,
    programmed_area_m2: rooms.reduce((sum, r) => sum + r.area_m2, 0),
    circulation_area_m2: rooms.filter((r) => r.is_circulation).reduce((sum, r) => sum + r.area_m2, 0),
  }
}
