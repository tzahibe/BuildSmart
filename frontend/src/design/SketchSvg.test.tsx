import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Room } from '../types'
import { twoRoomDesign } from './geometricDesign.fixtures'
import SketchSvg from './SketchSvg'

/** Two rooms sharing a long wall, in the LEGACY `Room[]` shape — long/adjacent enough that the
 * pre-existing (and still-used-for-compatibility) shared-wall-length heuristic in `LegacyFloorPlan`
 * would draw a door for them. Used to prove that heuristic is still reachable for old payloads, and
 * that it is NEVER reachable once a matching `geometricDesign` is supplied for the same floor. */
function legacyAdjacentRooms(): Room[] {
  return [
    { type: 'living_room', floor: 1, area_m2: 12, x: 0, y: 0, width_m: 3, depth_m: 4, source: null },
    { type: 'bedroom', floor: 1, area_m2: 12, x: 3, y: 0, width_m: 3, depth_m: 4, source: null },
  ]
}

describe('SketchSvg', () => {
  it('falls back to the legacy renderer when no geometricDesign is supplied (old design payload)', () => {
    const { container } = render(<SketchSvg rooms={legacyAdjacentRooms()} geometricDesign={null} />)

    // The legacy path is still reachable and still draws the rooms and their walls.
    expect(container.querySelector('.sketch-svg')).not.toBeNull()
    expect(container.querySelectorAll('.arch-door')).toHaveLength(0)
  })

  it('legacy renderer draws NO doors, because it has no authoritative door data', () => {
    // It used to infer an interior door from "shared wall long enough" and an entrance from which
    // outer edge the living room touched. Both inferences were removed in demo P0: a renderer must
    // not decide where a door is, and a legacy design carries no backend door data to draw instead.
    // Two adjacent rooms with a long shared wall, and a living room on the footprint edge — the
    // exact input that previously produced two invented doors.
    const { container } = render(<SketchSvg rooms={legacyAdjacentRooms()} geometricDesign={null} />)

    expect(container.querySelectorAll('.sketch-svg-door')).toHaveLength(0)
  })

  it('uses the authoritative ArchitecturalFloorPlan renderer once geometricDesign matches the active floor', () => {
    const design = twoRoomDesign({ withDoor: false })
    const { container } = render(<SketchSvg rooms={legacyAdjacentRooms()} geometricDesign={design} />)

    // No door in `design.doors` for these two adjacent rooms -> none rendered, even though the same
    // two rooms would have produced a legacy inferred door (see the test above).
    expect(container.querySelectorAll('.arch-door')).toHaveLength(0)
    expect(container.querySelectorAll('.sketch-svg-door')).toHaveLength(0)
    // The authoritative renderer's own wall/room markup is present.
    expect(container.querySelectorAll('.arch-wall-exterior').length).toBeGreaterThan(0)
  })

  it('still renders the authoritative door when geometricDesign supplies one', () => {
    const design = twoRoomDesign({ withDoor: true })
    const { container } = render(<SketchSvg rooms={legacyAdjacentRooms()} geometricDesign={design} />)

    expect(container.querySelectorAll('.arch-door')).toHaveLength(1)
  })

  it('renders the empty state for a project with no rooms yet, regardless of geometricDesign', () => {
    const { getByText } = render(<SketchSvg rooms={[]} geometricDesign={null} />)
    expect(getByText('אין עדיין נתוני תכנון להצגה')).toBeInTheDocument()
  })

  describe('compass', () => {
    // Neither drawing on the design page comes from the street-up demo pipeline: the legacy rooms
    // and the GeometricDesign both come from the spatial-solver / parametric pipeline, which has no
    // street and does not guarantee which edge is up. A compass there was the original bug (a
    // hardcoded "N"), and no street side can make it truthful, so none is drawn.
    it('legacy renderer draws no compass', () => {
      const { container } = render(<SketchSvg rooms={legacyAdjacentRooms()} geometricDesign={null} />)
      expect(container.querySelector('[data-testid="compass"]')).toBeNull()
      expect(container.querySelector('.sketch-svg-compass-needle')).toBeNull()
      expect(container.textContent).not.toMatch(/\bN\b/)
    })

    it('authoritative renderer draws no compass', () => {
      const { container } = render(
        <SketchSvg rooms={legacyAdjacentRooms()} geometricDesign={twoRoomDesign({ withDoor: false })} />,
      )
      expect(container.querySelector('.arch-plan')).not.toBeNull()
      expect(container.querySelector('[data-testid="compass"]')).toBeNull()
      expect(container.querySelector('.sketch-svg-compass-needle')).toBeNull()
    })
  })
})
