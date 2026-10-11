import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { niceScaleLengthM, ScaleBar } from './ScaleBar'

describe('niceScaleLengthM', () => {
  it.each([
    [3, 2],
    [7, 5],
    [16, 20],
    [0.6, 0.5],
    [90, 100],
  ])('picks the nearest 1-2-5 step to %s -> %s', (target, expected) => {
    expect(niceScaleLengthM(target)).toBe(expected)
  })

  it('never returns zero or negative for a degenerate frame', () => {
    expect(niceScaleLengthM(0)).toBeGreaterThan(0)
    expect(niceScaleLengthM(-5)).toBeGreaterThan(0)
  })
})

describe('ScaleBar', () => {
  it('draws a bar whose own length is a round metre step, never a field off any design', () => {
    const { container } = render(
      <svg>
        <ScaleBar x={0} y={0} frameSizeM={30} />
      </svg>,
    )
    const bar = container.querySelector('[data-testid="scale-bar"]')!
    const lengthM = Number(bar.getAttribute('data-length-m'))
    expect([1, 2, 5, 10].includes(lengthM)).toBe(true)
    const line = bar.querySelector('.demo-scale-bar-line')!
    expect(Number(line.getAttribute('x2'))).toBe(lengthM)
  })
})
