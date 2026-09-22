import type { DemoRoom } from './demoDesign'

/** Lays out a room's label — name, realized dimensions, area — so it stays inside the rectangle.
 *
 * Presentation only. The printed dimensions are the room's own realized NET rectangle (`width_m`
 * × `depth_m`), never the template it was planned from, and the area is the backend's own
 * authoritative `area_m2`, which the backend guarantees equals that pair's product (check C27) —
 * unlike the room's GROSS box (`gross_width_m` × `gross_depth_m`) the label is actually centred
 * and fitted within.
 *
 * The default is three stacked lines. A room too shallow for three lines gets the dimensions and
 * area on one compact line; a room narrower than its label but deep enough to hold it sideways
 * is labelled rotated, the way a corridor is labelled on any plan. The type is scaled down only
 * as far as the rectangle demands, and never below `MIN_SCALE` — a label that overruns a tiny
 * room by a few centimetres beats one nobody can read. */

/** One run of a label line. `isolate` marks a `width × depth` pair that must keep its own
 *  left-to-right reading order inside the plan's RTL context — see `Dim.tsx` for why: without
 *  isolation the bidi algorithm displays "6.15 × 5.75" as "5.75 × 6.15". */
export interface LabelSegment {
  text: string
  isolate?: boolean
}

export interface LabelLine {
  segments: LabelSegment[]
  /** The line's plain text, for measuring and for tests. */
  text: string
  kind: 'name' | 'dims' | 'area' | 'compact'
  /** Font size in plan metres (SVG user units). */
  fontSize: number
  /** Vertical offset of the line's centre from the room's centre, in plan metres. */
  dy: number
}

export interface RoomLabelLayout {
  lines: LabelLine[]
  rotated: boolean
}

const NAME_FONT = 0.52
const DETAIL_FONT = 0.4
const LINE_GAP = 0.12
/** Average glyph advance as a share of the font size. Measured off Chrome's rendering of the demo
 *  plan (a 14-character dimensions line at 0.4 spans ≈2.85 m, i.e. ≈0.51 em per glyph) and padded
 *  so a different system font still fits. */
const CHAR_WIDTH_EM = 0.55
/** Clearance kept between the label and the room's walls, in plan metres. */
const SIDE_MARGIN = 0.3
const TOP_MARGIN = 0.2
/** A layout at this scale or better is "fits"; the first candidate that does is chosen. */
const GOOD_ENOUGH = 0.8
const MIN_SCALE = 0.55

export function realizedDimsSegments(room: Pick<DemoRoom, 'width_m' | 'depth_m'>): LabelSegment[] {
  return [{ text: `${room.width_m.toFixed(2)} × ${room.depth_m.toFixed(2)}`, isolate: true }, { text: ' מ׳' }]
}

export function areaSegments(room: Pick<DemoRoom, 'area_m2'>): LabelSegment[] {
  return [{ text: `${room.area_m2.toFixed(1)} מ״ר` }]
}

type Stack = { segments: LabelSegment[]; kind: LabelLine['kind']; font: number }[]

function plainText(segments: LabelSegment[]): string {
  return segments.map((s) => s.text).join('')
}

/** The scale (≤ 1) at which `stack` fits a box of `width` × `depth`. */
function fitScale(stack: Stack, width: number, depth: number): number {
  const widest = Math.max(...stack.map((l) => plainText(l.segments).length * l.font * CHAR_WIDTH_EM))
  const height = stack.reduce((sum, l) => sum + l.font, 0) + LINE_GAP * (stack.length - 1)
  return Math.min(1, (width - SIDE_MARGIN) / widest, (depth - TOP_MARGIN) / height)
}

function place(stack: Stack, scale: number): LabelLine[] {
  const gap = LINE_GAP * scale
  const fonts = stack.map((l) => l.font * scale)
  const height = fonts.reduce((sum, f) => sum + f, 0) + gap * (stack.length - 1)
  let top = -height / 2
  return stack.map((line, i) => {
    const dy = top + fonts[i] / 2
    top += fonts[i] + gap
    return { segments: line.segments, text: plainText(line.segments), kind: line.kind, fontSize: fonts[i], dy }
  })
}

export function roomLabelLayout(room: DemoRoom): RoomLabelLayout {
  const name = { segments: [{ text: room.name }], kind: 'name' as const, font: NAME_FONT }
  const dims = realizedDimsSegments(room)
  const area = areaSegments(room)
  const threeLines: Stack = [
    name,
    { segments: dims, kind: 'dims', font: DETAIL_FONT },
    { segments: area, kind: 'area', font: DETAIL_FONT },
  ]
  const twoLines: Stack = [
    name,
    { segments: [...dims, { text: ' · ' }, ...area], kind: 'compact', font: DETAIL_FONT },
  ]

  // Fits within the room's GROSS box — the rectangle actually drawn — even though the printed
  // dimensions are the smaller NET pair; a room deeper than it is wide (by its built footprint)
  // is the one sideways helps.
  const boxWidth = room.gross_width_m
  const boxDepth = room.gross_depth_m
  const orientations: boolean[] = boxDepth > boxWidth ? [false, true] : [false]
  const candidates = [threeLines, twoLines].flatMap((stack) =>
    orientations.map((rotated) => {
      const [w, d] = rotated ? [boxDepth, boxWidth] : [boxWidth, boxDepth]
      return { stack, rotated, scale: fitScale(stack, w, d) }
    }),
  )

  const chosen =
    candidates.find((c) => c.scale >= GOOD_ENOUGH) ??
    candidates.reduce((best, c) => (c.scale > best.scale ? c : best))

  return {
    rotated: chosen.rotated,
    lines: place(chosen.stack, Math.max(MIN_SCALE, chosen.scale)),
  }
}
