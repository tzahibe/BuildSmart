import "./SketchSvg.css";
import { compassOrientation, type CompassLetter } from "./compass";

/** The compass rose drawn beside a STREET-UP plan. The mapping behind it — and what the backend does
 * and does not establish — lives in `compass.ts`; this file only draws what that mapping says. Side
 * letters and the north needle appear only when the mapping defines them; otherwise the rose shows the
 * street edge at the top and the rear edge at the bottom, and nothing it cannot justify. */

const HEBREW_EDGE: Record<CompassLetter, string> = {
  N: "צפון",
  E: "מזרח",
  S: "דרום",
  W: "מערב",
};

interface CompassRoseProps {
  streetFacingSide: string | null | undefined;
  /** Centre of the rose, in the SVG's metre coordinates. */
  cx: number;
  cy: number;
  /** Size multiplier: the rose is drawn about 1 m across at 1, which suits a building-sized frame; a
   *  site-sized frame (the demo plan) passes a larger value so it stays legible. */
  scale?: number;
}

const RING_RADIUS_M = 0.34;
const LETTER_RADIUS_M = 0.52;

export function CompassRose({
  streetFacingSide,
  cx,
  cy,
  scale = 1,
}: CompassRoseProps) {
  const orientation = compassOrientation(streetFacingSide);
  if (orientation === null) return null;

  const { top, right, bottom, left, northAngleDeg } = orientation;
  const handednessKnown = northAngleDeg !== null;
  const title = handednessKnown
    ? `מצפן: הרחוב למעלה (${HEBREW_EDGE[top]})`
    : `הרחוב למעלה (${HEBREW_EDGE[top]}); כיוון הצפון בשרטוט לא נקבע`;
  return (
    <g
      className="sketch-svg-compass"
      data-testid="compass"
      data-top={top}
      data-bottom={bottom}
      data-right={right ?? undefined}
      data-left={left ?? undefined}
      data-north-angle={northAngleDeg ?? undefined}
      data-handedness={handednessKnown ? "KNOWN" : "UNDEFINED"}
      transform={`translate(${cx} ${cy})`}
    >
      <title>{title}</title>
      <g transform={`scale(${scale})`}>
        <circle r={RING_RADIUS_M} className="sketch-svg-compass-ring" />
        {handednessKnown ? (
          <path
            d="M 0 -0.23 L 0.08 0.06 L 0 -0.03 L -0.08 0.06 Z"
            className="sketch-svg-compass-needle"
            transform={`rotate(${northAngleDeg})`}
          />
        ) : null}
        <text
          x={0}
          y={-LETTER_RADIUS_M}
          className="sketch-svg-compass-letter"
          data-edge="top"
        >
          {top}
        </text>
        <text
          x={0}
          y={LETTER_RADIUS_M}
          className="sketch-svg-compass-letter"
          data-edge="bottom"
        >
          {bottom}
        </text>
        {right !== null ? (
          <text
            x={LETTER_RADIUS_M}
            y={0}
            className="sketch-svg-compass-letter"
            data-edge="right"
          >
            {right}
          </text>
        ) : null}
        {left !== null ? (
          <text
            x={-LETTER_RADIUS_M}
            y={0}
            className="sketch-svg-compass-letter"
            data-edge="left"
          >
            {left}
          </text>
        ) : null}
      </g>
    </g>
  );
}
