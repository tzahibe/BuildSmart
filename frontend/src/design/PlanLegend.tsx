import type { DemoDesign } from './demoDesign'
import { EXTERIOR_WALL_STYLE, WALL_STYLE } from './DemoPlan'
import './PlanLegend.css'

/** THE PLAN LEGEND — what each colour in the drawing means.
 *
 * Two rules, both inherited from the renderer it explains:
 *
 *  - The swatches are drawn from the renderer's OWN style values and CSS classes, never from a
 *    second copy of the palette. Change a wall colour in `DemoPlan` and this follows automatically.
 *  - An entry appears only when that thing is actually in THIS design. A house with no safe room
 *    shows no safe-room key, and a plan with nothing open between rooms shows no open-passage key —
 *    the legend describes the drawing in front of the user, not the renderer's full vocabulary.
 */

const SW = { w: 34, h: 12 } // swatch viewBox, in the same units the stroke widths below use

function Swatch({ children }: { children: React.ReactNode }) {
  return (
    <svg className="legend-swatch" viewBox={`0 0 ${SW.w} ${SW.h}`} aria-hidden="true">
      {children}
    </svg>
  )
}

/** A wall swatch, scaled from metres to the swatch box by the same factor for every entry so the
 * relative weights a reader sees here match the relative weights in the plan. */
const WEIGHT = 26

function WallSwatch({ style }: { style: { color: string; width: number } }) {
  return (
    <Swatch>
      <line
        x1={2} y1={SW.h / 2} x2={SW.w - 2} y2={SW.h / 2}
        stroke={style.color} strokeWidth={style.width * WEIGHT} strokeLinecap="butt"
      />
    </Swatch>
  )
}

function AreaSwatch({ className }: { className: string }) {
  return (
    <Swatch>
      <rect x={2} y={1} width={SW.w - 4} height={SW.h - 2} className={className} />
    </Swatch>
  )
}

function LegendRow({ swatch, label }: { swatch: React.ReactNode; label: string }) {
  return (
    <li className="legend-row">
      {swatch}
      <span className="legend-label">{label}</span>
    </li>
  )
}

function PlanLegend({ design }: { design: DemoDesign }) {
  const hasSafeRoom = design.walls.some((w) => w.construction === 'RC_SAFE_ROOM')
  const hasPartition = design.walls.some(
    (w) => w.construction !== 'RC_SAFE_ROOM' && w.boundary_context !== 'EXTERIOR',
  )
  const hasInteriorDoor = design.doors.some((d) => !d.is_entrance && d.kind !== 'CASED_OPENING')
  const hasCasedOpening = design.doors.some((d) => !d.is_entrance && d.kind === 'CASED_OPENING')
  const hasEntrance = design.doors.some((d) => d.is_entrance)

  const mid = SW.h / 2
  const partition = WALL_STYLE.STANDARD_PARTITION

  return (
    <div className="legend">
      <h3 className="workspace-subtitle">מקרא</h3>
      <ul className="legend-list">
        <LegendRow swatch={<WallSwatch style={EXTERIOR_WALL_STYLE} />} label="קיר חוץ" />

        {hasPartition ? (
          <LegendRow swatch={<WallSwatch style={partition} />} label="מחיצה פנימית" />
        ) : null}

        {hasSafeRoom ? (
          <LegendRow
            swatch={<WallSwatch style={WALL_STYLE.RC_SAFE_ROOM} />}
            label="קיר ממ״ד — בטון מזוין"
          />
        ) : null}

        {hasInteriorDoor ? (
          <LegendRow
            swatch={
              <Swatch>
                {/* wall, a short gap where the leaf sits, wall again — the plan draws the gap by
                    NOT drawing wall there, so the swatch does the same rather than painting white
                    over it (which is invisible against this panel). */}
                <line x1={2} y1={mid} x2={13} y2={mid}
                      stroke={partition.color} strokeWidth={partition.width * WEIGHT} />
                <line x1={21} y1={mid} x2={SW.w - 2} y2={mid}
                      stroke={partition.color} strokeWidth={partition.width * WEIGHT} />
              </Swatch>
            }
            label="פתח דלת — קיר שנקטע"
          />
        ) : null}

        {hasCasedOpening ? (
          <LegendRow
            swatch={
              <Swatch>
                {/* same interrupted wall as an ordinary door opening, but jamb ticks stand in for
                    the door symbol instead of a leaf — there is no door here at all. */}
                <line x1={2} y1={mid} x2={13} y2={mid}
                      stroke={partition.color} strokeWidth={partition.width * WEIGHT} />
                <line x1={21} y1={mid} x2={SW.w - 2} y2={mid}
                      stroke={partition.color} strokeWidth={partition.width * WEIGHT} />
                {/* the class sets its stroke-width in plan metres, invisible at swatch scale — see
                    the entrance row above for why that has to be an inline override here too. */}
                <line x1={13} y1={mid - 3} x2={13} y2={mid + 3} className="demo-door-jamb"
                      style={{ strokeWidth: 0.05 * WEIGHT }} />
                <line x1={21} y1={mid - 3} x2={21} y2={mid + 3} className="demo-door-jamb"
                      style={{ strokeWidth: 0.05 * WEIGHT }} />
              </Swatch>
            }
            label="מעבר פתוח לסלון — ללא דלת"
          />
        ) : null}

        {hasEntrance ? (
          <LegendRow
            swatch={
              <Swatch>
                <line x1={2} y1={mid} x2={SW.w - 2} y2={mid}
                      stroke={EXTERIOR_WALL_STYLE.color}
                      strokeWidth={EXTERIOR_WALL_STYLE.width * WEIGHT} />
                {/* the colour comes from the renderer's own class; the WIDTH has to be an inline
                    style, because that class also sets a stroke-width in metres and a stylesheet
                    rule beats a presentation attribute — at swatch scale that left the overlay
                    invisible and the key showed a plain black bar. */}
                <line x1={11} y1={mid} x2={23} y2={mid} className="demo-door--entrance"
                      style={{ strokeWidth: EXTERIOR_WALL_STYLE.width * WEIGHT }} />
              </Swatch>
            }
            label="דלת כניסה"
          />
        ) : null}

        {design.windows.length > 0 ? (
          <LegendRow
            swatch={
              <Swatch>
                <line x1={2} y1={mid} x2={SW.w - 2} y2={mid}
                      stroke={EXTERIOR_WALL_STYLE.color}
                      strokeWidth={EXTERIOR_WALL_STYLE.width * WEIGHT} />
                <line x1={9} y1={mid} x2={25} y2={mid} className="demo-window"
                      style={{ strokeWidth: EXTERIOR_WALL_STYLE.width * WEIGHT }} />
              </Swatch>
            }
            label="חלון"
          />
        ) : null}

        {design.open_interfaces.length > 0 ? (
          <LegendRow
            swatch={
              <Swatch>
                <line x1={2} y1={mid} x2={6} y2={mid}
                      stroke={partition.color} strokeWidth={partition.width * WEIGHT} />
                <line x1={28} y1={mid} x2={SW.w - 2} y2={mid}
                      stroke={partition.color} strokeWidth={partition.width * WEIGHT} />
              </Swatch>
            }
            label="מעבר פתוח — אין קיר כלל"
          />
        ) : null}

        {design.rooms.some((r) => r.type === 'FLEX') ? (
          <LegendRow swatch={<AreaSwatch className="demo-room-flex" />} label="שטח גמיש — לא הוקצה לחדר" />
        ) : null}

        {design.garden.length > 0 ? (
          <LegendRow swatch={<AreaSwatch className="demo-garden" />} label="גינה" />
        ) : null}

        {design.parking.length > 0 ? (
          <LegendRow swatch={<AreaSwatch className="demo-parking" />} label="חניה" />
        ) : null}

        <LegendRow swatch={<AreaSwatch className="demo-walk" />} label="שביל כניסה" />
      </ul>
    </div>
  )
}

export default PlanLegend
