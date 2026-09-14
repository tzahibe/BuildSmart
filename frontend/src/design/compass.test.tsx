import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { compassOrientation } from './compass'
import { CompassRose } from './CompassRose'

/** The drawing is street-up, so the letter at the top is the street side and the bottom is the rear.
 * For NORTH/SOUTH the plot is drawn as entered and the ring reads as a rotated north-up map. For
 * EAST/WEST the backend only swaps width and depth and never says which way the drawing is handed,
 * so the side letters and the north needle are NOT defined — the rose must not invent them. */
const EXPECTED = {
  NORTH: { top: 'N', bottom: 'S', right: 'E', left: 'W', northAngleDeg: 0 },
  SOUTH: { top: 'S', bottom: 'N', right: 'W', left: 'E', northAngleDeg: 180 },
  EAST: { top: 'E', bottom: 'W', right: null, left: null, northAngleDeg: null },
  WEST: { top: 'W', bottom: 'E', right: null, left: null, northAngleDeg: null },
} as const

describe('compassOrientation', () => {
  it.each(Object.entries(EXPECTED))('street on the %s edge', (side, expected) => {
    expect(compassOrientation(side)).toEqual(expected)
  })

  it('accepts the side in any case or with surrounding whitespace', () => {
    expect(compassOrientation(' south ')).toEqual(EXPECTED.SOUTH)
    expect(compassOrientation('East')).toEqual(EXPECTED.EAST)
  })

  it('is null when the side is missing or not a cardinal direction, so no compass is drawn', () => {
    expect(compassOrientation(undefined)).toBeNull()
    expect(compassOrientation(null)).toBeNull()
    expect(compassOrientation('')).toBeNull()
    expect(compassOrientation('NORTH_EAST')).toBeNull()
  })

  it('never claims a handedness for an east or west street', () => {
    for (const side of ['EAST', 'WEST']) {
      const o = compassOrientation(side)!
      expect(o.left).toBeNull()
      expect(o.right).toBeNull()
      expect(o.northAngleDeg).toBeNull()
    }
  })
})

describe('CompassRose', () => {
  function renderRose(side: string | null | undefined) {
    const { container } = render(
      <svg>
        <CompassRose streetFacingSide={side} cx={0} cy={0} />
      </svg>,
    )
    return container.querySelector('[data-testid="compass"]')
  }

  it.each([['NORTH', EXPECTED.NORTH], ['SOUTH', EXPECTED.SOUTH]] as const)(
    '%s street: full rose — four letters and a needle to true north',
    (side, expected) => {
      const rose = renderRose(side)!
      expect(rose).not.toBeNull()
      expect(rose.getAttribute('data-handedness')).toBe('KNOWN')
      for (const edge of ['top', 'right', 'bottom', 'left'] as const) {
        expect(rose.getAttribute(`data-${edge}`)).toBe(expected[edge])
        expect(rose.querySelector(`[data-edge="${edge}"]`)!.textContent).toBe(expected[edge])
      }
      expect(rose.querySelector('.sketch-svg-compass-needle')!.getAttribute('transform')).toBe(
        `rotate(${expected.northAngleDeg})`,
      )
    },
  )

  it.each([['EAST', EXPECTED.EAST], ['WEST', EXPECTED.WEST]] as const)(
    '%s street: partial rose — street at the top, rear at the bottom, no sides and no needle',
    (side, expected) => {
      const rose = renderRose(side)!
      expect(rose).not.toBeNull()
      expect(rose.getAttribute('data-handedness')).toBe('UNDEFINED')
      expect(rose.querySelector('[data-edge="top"]')!.textContent).toBe(expected.top)
      expect(rose.querySelector('[data-edge="bottom"]')!.textContent).toBe(expected.bottom)
      expect(rose.querySelector('[data-edge="left"]')).toBeNull()
      expect(rose.querySelector('[data-edge="right"]')).toBeNull()
      expect(rose.hasAttribute('data-left')).toBe(false)
      expect(rose.hasAttribute('data-right')).toBe(false)
      expect(rose.hasAttribute('data-north-angle')).toBe(false)
      expect(rose.querySelector('.sketch-svg-compass-needle')).toBeNull()
      expect(rose.querySelector('title')!.textContent).toContain('לא נקבע')
    },
  )

  it('draws nothing when the street side is unknown', () => {
    expect(renderRose(undefined)).toBeNull()
    expect(renderRose('diagonal')).toBeNull()
  })
})
