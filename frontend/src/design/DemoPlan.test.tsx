import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import DemoPlan from './DemoPlan'
import DemoWorkspace from './DemoWorkspace'
import type { DemoDesign } from './demoDesign'

/** The renderer boundary: DemoPlan draws exactly what the backend supplied, and nothing else. */
function design(overrides: Partial<DemoDesign> = {}): DemoDesign {
  return {
    plot: { x: 0, y: 0, width_m: 20, depth_m: 24 },
    footprint: { x: 3, y: 5.5, width_m: 12, depth_m: 14 },
    rooms: [
      {
        id: 'LIVING', type: 'LIVING', name: 'סלון',
        x: 3, y: 5.5, width_m: 5, depth_m: 6, area_m2: 27.4,
        walls: {
          N: { construction: 'STANDARD_PARTITION', boundary_context: 'EXTERIOR', can_take_a_window: true },
          S: { construction: 'NONE', boundary_context: 'INTERIOR', can_take_a_window: false },
          E: { construction: 'STANDARD_PARTITION', boundary_context: 'INTERIOR', can_take_a_window: false },
          W: { construction: 'STANDARD_PARTITION', boundary_context: 'EXTERIOR', can_take_a_window: true },
        },
      },
    ],
    walls: [
      { orientation: 'horizontal', coord: 5.5, start: 3, end: 8, construction: 'STANDARD_PARTITION', boundary_context: 'EXTERIOR', room_ids: ['LIVING'] },
      { orientation: 'vertical', coord: 8, start: 5.5, end: 11.5, construction: 'RC_SAFE_ROOM', boundary_context: 'INTERIOR', room_ids: ['SAFE_ROOM'] },
    ],
    open_interfaces: [
      { orientation: 'horizontal', coord: 11.5, start: 3, end: 8, room_ids: ['LIVING', 'DINING'] },
    ],
    doors: [
      { a: 'HALL', b: 'LIVING', kind: 'DOOR', width_m: 0.9, x: 8, y: 8, orientation: 'vertical', is_entrance: false },
      { a: 'OUTSIDE', b: 'HALL', kind: 'DOOR', width_m: 1, x: 9, y: 5.5, orientation: 'horizontal', is_entrance: true },
    ],
    windows: [{ room_id: 'LIVING', side: 'W', width_m: 1.8, x: 3, y: 8.5 }],
    parking: [{ x: 3, y: 0, width_m: 2.5, depth_m: 5 }],
    garden: [{ x: 0, y: 19.5, width_m: 20, depth_m: 4.5 }],
    entrance_walk: { x: 8.4, y: 0, width_m: 1.2, depth_m: 5.5 },
    gross_area_m2: 168,
    net_area_m2: 151.2,
    validation: {
      passed: true,
      statements: ['כל החדרים נגישים פיזית מהכניסה'],
      warnings: [],
      checks: { C5: true, C13: true },
    },
    ...overrides,
  }
}

describe('DemoPlan', () => {
  it('draws exactly the walls the backend supplied — no more, no fewer', () => {
    const { container } = render(<DemoPlan design={design()} />)
    // 2 walls + 2 doors + 1 window = 5 <line> elements. An inferred door would push this to 6.
    expect(container.querySelectorAll('line')).toHaveLength(5)
  })

  it('draws no wall where the backend reports an OPEN interface', () => {
    const withOpen = design()
    const { container } = render(<DemoPlan design={withOpen} />)
    const horizontals = Array.from(container.querySelectorAll('line')).filter(
      (line) => line.getAttribute('y1') === '11.5',
    )
    expect(horizontals).toHaveLength(0)
  })

  it('weights an RC safe-room wall differently from a partition', () => {
    const { container } = render(<DemoPlan design={design()} />)
    const strokes = Array.from(container.querySelectorAll('line')).map((l) => l.getAttribute('stroke'))
    expect(strokes).toContain('#b03a2e')
  })

  it('renders no doors at all when the backend supplies none', () => {
    const { container } = render(<DemoPlan design={design({ doors: [] })} />)
    expect(container.querySelectorAll('.demo-door')).toHaveLength(0)
  })

  it('renders no windows when the backend supplies none', () => {
    const { container } = render(<DemoPlan design={design({ windows: [] })} />)
    expect(container.querySelectorAll('.demo-window')).toHaveLength(0)
  })

  it('shows the authoritative room name and area', () => {
    const { getByText } = render(<DemoPlan design={design()} />)
    expect(getByText('סלון')).toBeTruthy()
    expect(getByText('27.4 מ״ר')).toBeTruthy()
  })
})

describe('DemoWorkspace', () => {
  it('states only validation claims the backend actually made', () => {
    const { getByText, queryByText } = render(
      <DemoWorkspace design={design()} onChangeRequirements={() => {}} />,
    )
    expect(getByText('כל החדרים נגישים פיזית מהכניסה')).toBeTruthy()
    // Raw check codes must never reach the user.
    expect(queryByText(/C13/)).toBeNull()
    expect(queryByText(/C5/)).toBeNull()
  })

  it('shows warnings when validation reported them', () => {
    const failing = design({
      validation: { passed: false, statements: [], warnings: ['בעיה כלשהי'], checks: { C13: false } },
    })
    const { getByText } = render(<DemoWorkspace design={failing} onChangeRequirements={() => {}} />)
    expect(getByText('בעיה כלשהי')).toBeTruthy()
  })
})
