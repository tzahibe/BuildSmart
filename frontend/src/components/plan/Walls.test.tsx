import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { Walls, wallStyle, WALL_CLASS_STYLE, WALL_STYLE, EXTERIOR_WALL_STYLE } from './Walls'
import type { DemoWallSegment } from '../../design/demoDesign'

/** AC-3 (Issue #45): the renderer draws wall thickness/colour from the contract's own semantic
 * `wall_class`, not a frontend guess — a snapshot pins the actual drawn geometry per class, and a
 * second fixture proves a pre-Issue segment (no `wall_class`/`thickness_m`) still falls back to
 * the legacy `construction`/`boundary_context` styling unchanged. */

const CLASSED_WALLS: DemoWallSegment[] = [
  {
    id: 'wall-0', orientation: 'horizontal', coord: 5.5, start: 3, end: 8,
    construction: 'STANDARD_PARTITION', boundary_context: 'EXTERIOR', room_ids: ['LIVING'],
    wall_class: 'EXTERIOR', thickness_m: 0.3,
  },
  {
    id: 'wall-1', orientation: 'vertical', coord: 8, start: 5.5, end: 11.5,
    construction: 'RC_SAFE_ROOM', boundary_context: 'INTERIOR', room_ids: ['SAFE_ROOM', 'HALL'],
    wall_class: 'PROTECTED', thickness_m: 0.3,
  },
  {
    id: 'wall-2', orientation: 'vertical', coord: 6, start: 5.5, end: 9,
    construction: 'STANDARD_PARTITION', boundary_context: 'INTERIOR', room_ids: ['BATH_1', 'MASTER'],
    wall_class: 'WET_SERVICE', thickness_m: 0.1,
  },
  {
    id: 'wall-3', orientation: 'vertical', coord: 9, start: 5.5, end: 9,
    construction: 'STANDARD_PARTITION', boundary_context: 'INTERIOR', room_ids: ['HALL', 'BEDROOM'],
    wall_class: 'INTERIOR', thickness_m: 0.1,
  },
]

describe('wallStyle', () => {
  it('reads colour and REAL thickness_m from wall_class when present', () => {
    for (const wall of CLASSED_WALLS) {
      const style = wallStyle(wall)
      expect(style.color).toBe(WALL_CLASS_STYLE[wall.wall_class!].color)
      expect(style.width).toBe(wall.thickness_m)
    }
  })

  it('falls back to construction/boundary_context for a pre-Issue segment with no wall_class', () => {
    const legacyExterior: DemoWallSegment = {
      orientation: 'horizontal', coord: 5.5, start: 3, end: 8,
      construction: 'STANDARD_PARTITION', boundary_context: 'EXTERIOR', room_ids: ['LIVING'],
    }
    expect(wallStyle(legacyExterior)).toEqual(EXTERIOR_WALL_STYLE)

    const legacyProtected: DemoWallSegment = {
      orientation: 'vertical', coord: 8, start: 5.5, end: 11.5,
      construction: 'RC_SAFE_ROOM', boundary_context: 'INTERIOR', room_ids: ['SAFE_ROOM'],
    }
    expect(wallStyle(legacyProtected)).toEqual(WALL_STYLE.RC_SAFE_ROOM)

    const legacyPartition: DemoWallSegment = {
      orientation: 'vertical', coord: 6, start: 5.5, end: 9,
      construction: 'STANDARD_PARTITION', boundary_context: 'INTERIOR', room_ids: ['A', 'B'],
    }
    expect(wallStyle(legacyPartition)).toEqual(WALL_STYLE.STANDARD_PARTITION)
  })
})

describe('Walls', () => {
  it('draws one line per segment, positioned and weighted by class (snapshot)', () => {
    const { container } = render(
      <svg>
        <Walls walls={CLASSED_WALLS} />
      </svg>,
    )
    expect(container.innerHTML).toMatchSnapshot()
  })

  it('draws every wall class at a visibly different width or colour', () => {
    const { container } = render(
      <svg>
        <Walls walls={CLASSED_WALLS} />
      </svg>,
    )
    const lines = Array.from(container.querySelectorAll('line'))
    expect(lines).toHaveLength(CLASSED_WALLS.length)
    const styles = lines.map((l) => `${l.getAttribute('stroke')}:${l.getAttribute('stroke-width')}`)
    expect(new Set(styles).size).toBe(CLASSED_WALLS.length)
  })
})
