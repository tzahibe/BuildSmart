import { describe, expect, it } from 'vitest'
import {
  customFootprint,
  footprintAreaToleranceM2,
  generateFootprintOptions,
  isFootprintAreaValid,
  isFootprintStillValid,
  PRESET_SHAPE_TYPES,
} from './footprint'

describe('generateFootprintOptions', () => {
  it('generates one option per preset shape type, all PRESET-sourced', () => {
    const options = generateFootprintOptions(120)
    expect(options).toHaveLength(PRESET_SHAPE_TYPES.length)
    for (const option of options) {
      expect(option.source).toBe('PRESET')
    }
  })

  it.each([70, 120, 150, 320.5])('preserves the requested target area (%d m²) within tolerance for every option', (area) => {
    const options = generateFootprintOptions(area)
    for (const option of options) {
      expect(isFootprintAreaValid(option.area_m2, area)).toBe(true)
      // the actual bounding-box area (width * depth) must match too, not just the stored field
      expect(isFootprintAreaValid(option.width_m * option.depth_m, area)).toBe(true)
    }
  })

  it('produces genuinely different aspect ratios across options — not near-duplicate rectangles', () => {
    const options = generateFootprintOptions(120)
    const ratios = options.map((option) => option.width_m / option.depth_m)
    const uniqueRounded = new Set(ratios.map((ratio) => Math.round(ratio * 100)))
    expect(uniqueRounded.size).toBe(options.length)

    const compact = options.find((option) => option.shape_type === 'COMPACT')!
    const wide = options.find((option) => option.shape_type === 'WIDE')!
    const narrow = options.find((option) => option.shape_type === 'NARROW')!
    expect(wide.width_m).toBeGreaterThan(compact.width_m)
    expect(narrow.width_m).toBeLessThan(compact.width_m)
    expect(wide.width_m / wide.depth_m).toBeGreaterThan(1)
    expect(narrow.width_m / narrow.depth_m).toBeLessThan(1)
  })

  it('never hard-codes example dimensions — options scale with the requested area', () => {
    const small = generateFootprintOptions(50)
    const large = generateFootprintOptions(200)
    for (let i = 0; i < small.length; i++) {
      expect(small[i].width_m).not.toBeCloseTo(large[i].width_m, 1)
    }
  })

  it('represents every option as a closed rectangular polygon matching width/depth', () => {
    for (const option of generateFootprintOptions(90)) {
      expect(option.polygon).toEqual([
        { x: 0, y: 0 },
        { x: option.width_m, y: 0 },
        { x: option.width_m, y: option.depth_m },
        { x: 0, y: option.depth_m },
      ])
    }
  })

  it('changing the target area recalculates every option (different dimensions/ids do not persist)', () => {
    const before = generateFootprintOptions(100)
    const after = generateFootprintOptions(180)
    for (let i = 0; i < before.length; i++) {
      expect(before[i].shape_type).toBe(after[i].shape_type) // same shape catalogue
      expect(before[i].width_m).not.toBeCloseTo(after[i].width_m, 1) // but recalculated dimensions
      expect(after[i].target_area_m2).toBeCloseTo(180, 2)
    }
  })
})

describe('footprint area tolerance / validity', () => {
  it('scales the tolerance relatively, with a small absolute floor', () => {
    expect(footprintAreaToleranceM2(1)).toBeCloseTo(0.05, 5)
    expect(footprintAreaToleranceM2(1000)).toBeCloseTo(5, 5)
  })

  it('accepts a matching area and rejects one clearly outside tolerance', () => {
    expect(isFootprintAreaValid(120, 120)).toBe(true)
    expect(isFootprintAreaValid(180, 200)).toBe(false) // task's own worked example: 9x20 vs target 200
  })
})

describe('customFootprint', () => {
  it('preserves the EXACT user-entered dimensions — never normalized toward the target area', () => {
    const footprint = customFootprint(200, 10, 20)
    expect(footprint.width_m).toBe(10)
    expect(footprint.depth_m).toBe(20)
    expect(footprint.area_m2).toBeCloseTo(200, 2)
    expect(footprint.source).toBe('CUSTOM')
    expect(footprint.shape_type).toBe('RECTANGLE')
  })

  it('does not silently coerce an off-target entry back to a valid one', () => {
    // task's own worked example: 9x20 -> 180 m2, invalid against a 200 m2 target
    const footprint = customFootprint(200, 9, 20)
    expect(footprint.width_m).toBe(9)
    expect(footprint.depth_m).toBe(20)
    expect(footprint.area_m2).toBeCloseTo(180, 2)
    expect(isFootprintStillValid(footprint, 200)).toBe(false)
  })

  it('never normalizes toward sqrt(area) x sqrt(area) either', () => {
    const footprint = customFootprint(200, 10, 20)
    const naiveSquareSide = Math.sqrt(200)
    expect(footprint.width_m).not.toBeCloseTo(naiveSquareSide, 1)
  })
})

describe('isFootprintStillValid', () => {
  it('a footprint generated for one area is no longer valid once the target area changes materially', () => {
    const option = generateFootprintOptions(120)[0]
    expect(isFootprintStillValid(option, 120)).toBe(true)
    expect(isFootprintStillValid(option, 200)).toBe(false)
  })
})
