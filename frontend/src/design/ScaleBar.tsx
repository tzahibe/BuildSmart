import './DemoPlan.css'

/** A metric scale bar for the plan — a drawing CONVENTION, not an architectural fact: its own
 * length is picked purely from the frame's own size (the SVG already draws everything in real
 * metres, so no field on `DemoDesign` is needed to know what "5 m" looks like here — exactly the
 * same reasoning that lets a scale bar appear on any drawing without the drawing naming its own
 * scale). It never claims a fact about the building, so it carries none of the "never invent an
 * architectural fact" risk `DoorSymbol`/`Walls`/`InteriorLayout` are held to. */

const NICE_STEPS = [1, 2, 5, 10] as const

/** The conventional "1-2-5" scale-bar length nearest `targetM`, at whatever power of ten fits. */
export function niceScaleLengthM(targetM: number): number {
  if (!(targetM > 0)) return 1
  const magnitude = 10 ** Math.floor(Math.log10(targetM))
  const candidates = NICE_STEPS.map((step) => step * magnitude)
  return candidates.reduce((best, c) => (Math.abs(c - targetM) < Math.abs(best - targetM) ? c : best))
}

/** Roughly a sixth of the drawing's shorter side reads as a legible bar at any plan size. */
const FRAME_SHARE = 1 / 6

export function ScaleBar({ x, y, frameSizeM }: { x: number; y: number; frameSizeM: number }) {
  const lengthM = niceScaleLengthM(frameSizeM * FRAME_SHARE)
  const tick = lengthM * 0.1
  const label = lengthM >= 1 ? `${lengthM} מ׳` : `${Math.round(lengthM * 100)} ס"מ`
  return (
    <g className="demo-scale-bar" data-testid="scale-bar" data-length-m={lengthM} transform={`translate(${x} ${y})`}>
      <line x1={0} y1={0} x2={lengthM} y2={0} className="demo-scale-bar-line" />
      <line x1={0} y1={-tick} x2={0} y2={tick} className="demo-scale-bar-tick" />
      <line x1={lengthM} y1={-tick} x2={lengthM} y2={tick} className="demo-scale-bar-tick" />
      <text x={lengthM / 2} y={tick + 0.35} className="demo-scale-bar-label">{label}</text>
    </g>
  )
}

export default ScaleBar
