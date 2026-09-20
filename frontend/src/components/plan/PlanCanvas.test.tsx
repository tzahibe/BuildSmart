import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import DemoPlan from '../../design/DemoPlan'
import type { DemoDesign } from '../../design/demoDesign'

/** AC-4 (Issue #63): the plan canvas itself must stay byte-for-byte unchanged while the
 * QualityPanel/RoomDetails/RefusalNotice work is added around it. There is no separate
 * `PlanCanvas` component in this codebase — the plan drawing IS `DemoPlan`
 * (`frontend/src/design/DemoPlan.tsx`), exercised through `DemoWorkspace`; this test exists at
 * this path only to satisfy this Issue's own verification target. `DemoPlan` is not touched by
 * the Issue #63 work at all — this snapshot exists to prove it and to catch a future regression.
 * The full behavioral regression suite for the plan drawing (walls/doors/windows/compass/legend)
 * already exists, untouched, at `frontend/src/design/DemoPlan.test.tsx` (55 tests). */

const design: DemoDesign = {
  plot: { x: 0, y: 0, width_m: 12, depth_m: 10 },
  footprint: { x: 1, y: 1, width_m: 10, depth_m: 8 },
  rooms: [
    {
      id: 'living-1', type: 'LIVING', name: 'סלון', x: 1, y: 1, width_m: 5, depth_m: 4, area_m2: 20,
      walls: {},
    },
    {
      id: 'bed-1', type: 'BEDROOM', name: 'חדר שינה', x: 6, y: 1, width_m: 5, depth_m: 4, area_m2: 20,
      walls: {},
    },
  ],
  walls: [
    { orientation: 'vertical', coord: 6, start: 1, end: 5, construction: 'STANDARD_PARTITION', boundary_context: 'INTERIOR', room_ids: ['living-1', 'bed-1'] },
  ],
  open_interfaces: [],
  doors: [
    {
      a: 'living-1', b: 'bed-1', kind: 'ROOM_DOOR', width_m: 0.9, x: 6, y: 3,
      orientation: 'vertical', is_entrance: false, swings_into: 'bed-1', hinge_x: 6, hinge_y: 3.9,
      swing_deg: 0,
    },
  ],
  windows: [{ room_id: 'living-1', side: 'S', width_m: 1.5, x: 3, y: 9 }],
  parking: [{ x: 1, y: 9.2, width_m: 2.5, depth_m: 5 }],
  garden: [{ x: 0, y: 9, width_m: 12, depth_m: 1 }],
  entrance_walk: { x: 4, y: 9, width_m: 1.5, depth_m: 1 },
  gross_area_m2: 40,
  net_area_m2: 40,
  validation: { passed: true, statements: [], warnings: [], checks: {} },
}

describe('PlanCanvas (DemoPlan)', () => {
  it('renders the same SVG for the same design — a snapshot guard while quality UI is added around it', () => {
    const { container } = render(<DemoPlan design={design} streetFacingSide="NORTH" />)
    expect(container.querySelector('svg')?.outerHTML).toMatchSnapshot()
  })
})
