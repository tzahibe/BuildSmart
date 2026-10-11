import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import RoomDetails from './RoomDetails'
import type { DemoDesign, DemoQuality } from '../../design/demoDesign'

/** AC-2: selecting a room shows its exposure and, for wet rooms, its privacy summary — all read
 * off the contract, matched to the room by id. */

const rect = { x: 0, y: 0, width_m: 1, depth_m: 1 }

const design: DemoDesign = {
  plot: rect,
  footprint: rect,
  rooms: [
    { id: 'bath-1', type: 'BATHROOM', name: 'חדר רחצה', x: 0, y: 0, width_m: 2, depth_m: 2, area_m2: 4, gross_width_m: 2.2, gross_depth_m: 2.2, gross_area_m2: 4.84, walls: {} },
    { id: 'hall-1', type: 'HALL', name: 'מסדרון', x: 0, y: 0, width_m: 2, depth_m: 2, area_m2: 4, gross_width_m: 2.2, gross_depth_m: 2.2, gross_area_m2: 4.84, walls: {} },
    { id: 'bed-1', type: 'MASTER_BEDROOM', name: 'חדר הורים', x: 0, y: 0, width_m: 3, depth_m: 3, area_m2: 9, gross_width_m: 3.2, gross_depth_m: 3.2, gross_area_m2: 10.24, walls: {} },
  ],
  walls: [],
  open_interfaces: [],
  doors: [
    { a: 'hall-1', b: 'bath-1', kind: 'SERVICE_DOOR', width_m: 0.8, x: 0, y: 0, orientation: 'horizontal', is_entrance: false },
  ],
  windows: [],
  parking: [],
  garden: [],
  entrance_walk: rect,
  gross_area_m2: 100,
  net_area_m2: 90,
  validation: { passed: true, statements: [], warnings: [], checks: {} },
  quality: undefined,
}

const quality: DemoQuality = {
  over_preferred: false,
  signal: [],
  notices: [],
  exposure: [
    { room_id: 'bath-1', exterior_sides: ['N'], window_side: 'N', window_width_m: 0.6, no_window_reason: null },
    { room_id: 'bed-1', exterior_sides: [], window_side: null, window_width_m: null, no_window_reason: 'NO_EXTERIOR_WALL' },
  ],
  wet_privacy: [
    {
      zone_id: 'bath-1', entered_from: 'hall-1', entered_from_class: 'CIRCULATION',
      door_facing: 'bed-1', direct_sight_line: false, public_exposure_score: 0.1,
      circulation_obstruction: false, adjacency_quality: true, privacy_score: 0.2,
    },
  ],
}

describe('RoomDetails', () => {
  it('renders nothing when no room is selected', () => {
    const { container } = render(<RoomDetails design={design} quality={quality} roomId={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it("shows the selected room's exposure — window side and width", () => {
    render(<RoomDetails design={design} quality={quality} roomId="bath-1" />)

    expect(screen.getByText('חדר רחצה')).toBeInTheDocument()
    expect(screen.getByText('צפון')).toBeInTheDocument()
    expect(screen.getByText('צפון · 0.60 מ׳')).toBeInTheDocument()
  })

  it('shows why a room has no window when none was placed', () => {
    render(<RoomDetails design={design} quality={quality} roomId="bed-1" />)

    expect(screen.getByText('אין קיר חיצוני לחדר זה')).toBeInTheDocument()
  })

  it('shows the wet-room privacy summary for a wet room', () => {
    render(<RoomDetails design={design} quality={quality} roomId="bath-1" />)

    expect(screen.getByText('מסדרון (מסדרון)')).toBeInTheDocument()
    expect(screen.getByText('חדר הורים')).toBeInTheDocument()
    expect(screen.getByText('0.20')).toBeInTheDocument()
  })

  it('shows the door kind and width for doors touching the room', () => {
    render(<RoomDetails design={design} quality={quality} roomId="bath-1" />)

    expect(screen.getByText('דלת שירות · 0.80 מ׳')).toBeInTheDocument()
  })
})
