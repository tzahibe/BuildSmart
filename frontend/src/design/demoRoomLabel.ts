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

/** A rectangle the label should avoid sitting on: a furniture symbol the engine placed, or the
 * quarter-disc a door leaf sweeps. Supplied by the caller — this module never looks a room up. */
export interface LabelObstacle {
  x: number
  y: number
  w: number
  h: number
}

export interface RoomLabelLayout {
  /** Offset of the whole block from the room's label anchor, in plan metres (see `labelOffset`). */
  dx?: number
  dy?: number
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
//: How many positions the label block is slid through along the room's free axis. Odd, so the
//: centre — the position an architect uses unless something is in the way — is always a candidate.
const PLACEMENT_STEPS = 7
//: Below this the room cannot hold the block anywhere; the label stays centred and simply overlaps,
//: which is the graceful degradation a very small room gets (never a smaller room, never no label).
const MIN_FREE_M = 0.05

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

export function roomLabelLayout(room: DemoRoom, obstacles: LabelObstacle[] = []): RoomLabelLayout {
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
  const candidates = [threeLines, twoLines].flatMap((stack, stackIndex) =>
    orientations.map((rotated) => {
      const [w, d] = rotated ? [boxDepth, boxWidth] : [boxWidth, boxDepth]
      return { stack, stackIndex, rotated, scale: fitScale(stack, w, d) }
    }),
  )

  const fits = candidates.filter((c) => c.scale >= GOOD_ENOUGH)
  const pool = fits.length > 0 ? fits : [candidates.reduce((best, c) => (c.scale > best.scale ? c : best))]

  // Among the candidates that FIT, prefer the one the drawing can actually accommodate: least area
  // covering a furniture symbol or a door's swept quarter. Ties keep the richer three-line stack
  // (lower `stackIndex`), so information is only given up when it genuinely buys clearance.
  const scored = pool.map((c) => {
    const lines = place(c.stack, Math.max(MIN_SCALE, c.scale))
    const offset = labelOffset(room, lines, c.rotated, obstacles)
    const size = blockSize(lines)
    const w = c.rotated ? size.h : size.w
    const h = c.rotated ? size.w : size.h
    const block: LabelObstacle = {
      x: room.x + boxWidth / 2 + offset.dx - w / 2,
      y: room.y + boxDepth / 2 + offset.dy - h / 2,
      w,
      h,
    }
    const cover = obstacles.reduce((sum, o) => sum + overlap(block, o), 0)
    return { ...c, lines, offset, cover }
  })
  const chosen = scored.reduce((best, c) =>
    c.cover < best.cover - 1e-9 || (Math.abs(c.cover - best.cover) <= 1e-9 && c.stackIndex < best.stackIndex)
      ? c
      : best,
  )

  return { rotated: chosen.rotated, lines: chosen.lines, dx: chosen.offset.dx, dy: chosen.offset.dy }
}

/** The label block's own size, in metres, for the layout that was chosen. Read off the placed lines
 * themselves (`fontSize` and the line's own `dy`), so the box always matches what is drawn. */
function blockSize(lines: LabelLine[]): { w: number; h: number } {
  let w = 0
  let top = Number.POSITIVE_INFINITY
  let bottom = Number.NEGATIVE_INFINITY
  for (const line of lines) {
    w = Math.max(w, line.text.length * line.fontSize * CHAR_WIDTH_EM)
    top = Math.min(top, line.dy - line.fontSize / 2)
    bottom = Math.max(bottom, line.dy + line.fontSize / 2)
  }
  return { w, h: Number.isFinite(top) ? bottom - top : 0 }
}

function overlap(a: LabelObstacle, b: LabelObstacle): number {
  const w = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)
  const h = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y)
  return w > 0 && h > 0 ? w * h : 0
}

/** Where to put the label block inside the room, as an offset from the room's own centre.
 *
 * DETERMINISTIC AND GEOMETRY-FREE. The block is slid through `PLACEMENT_STEPS` positions along the
 * room's longer free axis and the position covering the least obstacle area wins; ties go to the
 * one nearest the centre, then to the lower index. Nothing here is per-room-type, nothing is a
 * hand-tuned offset, and the ROOM IS NEVER RESIZED to make the label fit — if every position is
 * obstructed the least-bad one is used, which is exactly what a draughtsman does.
 */
export function labelOffset(room: DemoRoom, lines: LabelLine[], rotated: boolean,
                            obstacles: LabelObstacle[]): { dx: number; dy: number } {
  if (obstacles.length === 0) return { dx: 0, dy: 0 }
  const size = blockSize(lines)
  const w = rotated ? size.h : size.w
  const h = rotated ? size.w : size.h
  const boxW = room.gross_width_m
  const boxD = room.gross_depth_m
  const freeX = Math.max(0, boxW - w - 2 * SIDE_MARGIN)
  const freeY = Math.max(0, boxD - h - 2 * TOP_MARGIN)
  if (freeX <= MIN_FREE_M && freeY <= MIN_FREE_M) return { dx: 0, dy: 0 }

  // A grid over BOTH free axes: sliding only along the longer one cannot clear a bed that spans
  // the room's depth but leaves a side clear. Still a fixed, enumerable set of positions.
  const steps: number = PLACEMENT_STEPS
  const axis = (free: number) =>
    free <= MIN_FREE_M
      ? [0]
      : Array.from({ length: steps }, (_, i) => ((steps <= 1 ? 0.5 : i / (steps - 1)) - 0.5) * free)

  let best = { dx: 0, dy: 0, cover: Number.POSITIVE_INFINITY, dist: Number.POSITIVE_INFINITY }
  for (const dy of axis(freeY)) {
    for (const dx of axis(freeX)) {
      const block: LabelObstacle = {
        x: room.x + boxW / 2 + dx - w / 2,
        y: room.y + boxD / 2 + dy - h / 2,
        w,
        h,
      }
      const cover = obstacles.reduce((sum, o) => sum + overlap(block, o), 0)
      const dist = Math.hypot(dx, dy)
      if (cover < best.cover - 1e-9 || (Math.abs(cover - best.cover) <= 1e-9 && dist < best.dist - 1e-9)) {
        best = { dx, dy, cover, dist }
      }
    }
  }
  return { dx: best.dx, dy: best.dy }
}

/** The quarter-disc a door leaf sweeps, as the axis-aligned box that contains it. The hinge and the
 * swing direction are the ENGINE's own decisions (`doors.py`); nothing is guessed here. */
export function doorSwingObstacle(door: {
  hinge_x?: number; hinge_y?: number; swing_deg?: number; width_m: number
}): LabelObstacle | null {
  if (door.hinge_x === undefined || door.hinge_y === undefined || door.swing_deg === undefined) return null
  const r = door.width_m
  const rad = (door.swing_deg * Math.PI) / 180
  const dx = Math.cos(rad)
  const dy = Math.sin(rad)
  const x0 = dx >= 0 ? door.hinge_x : door.hinge_x - r
  const y0 = dy >= 0 ? door.hinge_y : door.hinge_y - r
  return { x: x0, y: y0, w: r, h: r }
}
