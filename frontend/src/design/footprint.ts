/** BUILDING FOOTPRINT SELECTION — the user's chosen building outline, decided explicitly BEFORE
 * architectural plan generation ever runs (see App.tsx's 'footprint' view, inserted between project
 * creation and the parse+design pipeline).
 *
 * Kept deliberately distinct from three other, easily-confused quantities (never call this "plot
 * size", never derive it from the plot):
 *   - PLOT: `Project.plot_area_m2` — the parcel itself.
 *   - BUILDABLE ENVELOPE: setbacks/coverage-ratio-derived buildable region within the plot — not
 *     modeled anywhere in this codebase yet (see backend/app/architect/models.py's own docstring on
 *     `SiteSpec`) — deliberately left unknown here too, never silently assumed.
 *   - TARGET BUILT AREA: `Project.built_area_m2` — the room-program area BUDGET the user requested.
 *   - SELECTED BUILDING FOOTPRINT (this module): the actual outline shape/dimensions chosen for that
 *     budget — today the backend derives this itself, always as a square (see
 *     backend/app/design/pipeline.py's `_derive_footprint`); nothing here is sent to the backend yet
 *     (see App.tsx's own note on that gap).
 */

export type FootprintSource = 'PRESET' | 'CUSTOM'

/** `RECTANGLE` is the CUSTOM source's own shape type (a user-dimensioned rectangle, not one of the
 * four named presets) — kept distinct from the preset labels so a future non-rectangular custom
 * shape (a polygon) would get its own value here rather than overloading `RECTANGLE`. */
export type FootprintShapeType = 'COMPACT' | 'BALANCED' | 'WIDE' | 'NARROW' | 'RECTANGLE'

export interface FootprintPoint {
  x: number
  y: number
}

/** A rectangle is still represented as a closed polygon in V1 — never just `{width, depth}` — so an
 * L-shape or custom polygon later is a variant of this SAME contract, not a new one that would break
 * every caller of this type. `width_m`/`depth_m` are (and, for any future non-rectangular shape,
 * would remain) the polygon's bounding box. */
export interface BuildingFootprint {
  id: string
  source: FootprintSource
  shape_type: FootprintShapeType
  target_area_m2: number
  width_m: number
  depth_m: number
  area_m2: number
  polygon: FootprintPoint[]
}

const PRESET_ASPECT_RATIOS = {
  COMPACT: 1.0,
  BALANCED: 1.35,
  WIDE: 1.8,
  NARROW: 1 / 1.8,
} as const

export const PRESET_SHAPE_TYPES = Object.keys(PRESET_ASPECT_RATIOS) as Array<keyof typeof PRESET_ASPECT_RATIOS>

export const FOOTPRINT_SHAPE_LABELS: Record<FootprintShapeType, string> = {
  COMPACT: 'קומפקטי',
  BALANCED: 'מאוזן',
  WIDE: 'רחב',
  NARROW: 'צר ומוארך',
  RECTANGLE: 'מותאם אישית',
}

function round2(value: number): number {
  return Math.round(value * 100) / 100
}

function rectanglePolygon(widthM: number, depthM: number): FootprintPoint[] {
  return [
    { x: 0, y: 0 },
    { x: widthM, y: 0 },
    { x: widthM, y: depthM },
    { x: 0, y: depthM },
  ]
}

/** Explicit, small ROUNDING tolerance (never a magic per-scenario number) for "is this footprint's
 * actual area still close enough to the requested target built area" — relative (0.5% of the target)
 * so it scales sensibly from a tiny extension to a large house, with a small absolute floor so a
 * very small target area isn't held to an unreasonably strict bound. Used both to validate a CUSTOM
 * entry and, in tests, to confirm every generated PRESET option preserves the requested area. */
export function footprintAreaToleranceM2(targetAreaM2: number): number {
  return Math.max(0.05, targetAreaM2 * 0.005)
}

export function isFootprintAreaValid(areaM2: number, targetAreaM2: number): boolean {
  return Math.abs(areaM2 - targetAreaM2) <= footprintAreaToleranceM2(targetAreaM2)
}

/** One PRESET footprint option for `targetAreaM2` — built from ONLY that area and a fixed aspect
 * ratio, never a hard-coded example dimension (e.g. "10x20"). `depth` is computed from the
 * UNROUNDED width (`width = sqrt(area * ratio)`, `depth = area / width`), so the true area is
 * exactly `targetAreaM2` before display/storage rounding — rounding both dimensions to 2 decimals
 * (this project's existing area/dimension rounding convention — see e.g.
 * backend/app/geometry/solver.py's `round(width * height, 2)`) only ever introduces a sub-percent
 * discrepancy, well inside `footprintAreaToleranceM2`. */
function presetFootprint(shapeType: keyof typeof PRESET_ASPECT_RATIOS, targetAreaM2: number): BuildingFootprint {
  const ratio = PRESET_ASPECT_RATIOS[shapeType]
  const rawWidth = Math.sqrt(targetAreaM2 * ratio)
  const rawDepth = targetAreaM2 / rawWidth
  const width = round2(rawWidth)
  const depth = round2(rawDepth)
  return {
    id: `preset-${shapeType.toLowerCase()}`,
    source: 'PRESET',
    shape_type: shapeType,
    target_area_m2: round2(targetAreaM2),
    width_m: width,
    depth_m: depth,
    area_m2: round2(width * depth),
    polygon: rectanglePolygon(width, depth),
  }
}

/** Every PRESET footprint option for a given target built area — regenerated fresh any time the
 * caller's target area changes (App.tsx keys a `useMemo` on it); never cached across areas. */
export function generateFootprintOptions(targetAreaM2: number): BuildingFootprint[] {
  return PRESET_SHAPE_TYPES.map((shapeType) => presetFootprint(shapeType, targetAreaM2))
}

/** Builds the CUSTOM footprint from the user's own, UNMODIFIED width/depth — never normalized
 * toward the target area, and never rounded (a preset's dimensions are computed by this module, so
 * rounding them is this module's own choice; a custom entry is the user's own number and must
 * survive exactly as entered downstream). Only `area_m2` (a derived DISPLAY quantity, not the
 * dimensions themselves) is rounded, purely for cosmetic consistency with the preset options. */
export function customFootprint(targetAreaM2: number, widthM: number, depthM: number): BuildingFootprint {
  return {
    id: 'custom',
    source: 'CUSTOM',
    shape_type: 'RECTANGLE',
    target_area_m2: round2(targetAreaM2),
    width_m: widthM,
    depth_m: depthM,
    area_m2: round2(widthM * depthM),
    polygon: rectanglePolygon(widthM, depthM),
  }
}

/** True if `footprint` is still a valid choice for `targetAreaM2` — used to invalidate a stale
 * selection made against a since-changed target area (see App.tsx: the built-area field clears any
 * existing selection directly, but a footprint passed in from elsewhere is defensively re-checked
 * here too, e.g. by FootprintSelection itself). Re-validates the AREA rule, not just a matching
 * `target_area_m2` field, so a CUSTOM footprint that happens to still satisfy a new target area is
 * not needlessly discarded. */
export function isFootprintStillValid(footprint: BuildingFootprint, targetAreaM2: number): boolean {
  return isFootprintAreaValid(footprint.area_m2, targetAreaM2)
}
