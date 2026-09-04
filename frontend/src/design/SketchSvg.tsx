import { useEffect, useState } from 'react'
import type { Room } from '../types'
import './SketchSvg.css'

interface SketchSvgProps {
  rooms: Room[]
}

const ROOM_LABELS: Record<string, string> = {
  kitchen: 'מטבח',
  bathroom: 'חדר רחצה',
  safe_room: 'ממ"ד',
  living_room: 'סלון',
  bedroom: 'חדר שינה',
}

// Real-world-ish constants (meters) purely for how the drawing reads — walls, door swings, and
// dimension-line offsets. These are drafting conventions, not measured data: the underlying room
// geometry (position/size) still comes entirely from backend/app/design/generator.py; nothing here
// invents or adjusts a room's actual size or position.
const DOOR_WIDTH_M = 0.9
const TOP_PAD_M = 1.5
const RIGHT_PAD_M = 1.35
const SIDE_PAD_M = 0.5

function roomLabel(room: Room, indexAmongSameType: number, countOfSameType: number): string {
  const base = ROOM_LABELS[room.type] ?? room.type
  return countOfSameType > 1 ? `${base} ${indexAmongSameType + 1}` : base
}

/** A short architectural-style door symbol: a leaf line from the hinge to its open position, plus the
 * quarter-circle arc showing the swept path back to the opening's other side. Standard floor-plan
 * drafting convention — see e.g. any architectural graphic-standards reference for "door swing". */
function doorSymbolPath(hinge: [number, number], leafTip: [number, number], otherSide: [number, number]) {
  return `M ${hinge[0]} ${hinge[1]} L ${leafTip[0]} ${leafTip[1]} A ${DOOR_WIDTH_M} ${DOOR_WIDTH_M} 0 0 1 ${otherSide[0]} ${otherSide[1]}`
}

/** Pure presentational component: renders a floor's `Room[]` (already-computed x/y/width_m/depth_m, in
 * meters — see backend/app/design/generator.py) as an architectural-style floor plan sketch — exterior/
 * interior wall lines, door openings, dimension callouts, a north marker, and pale per-room tints with
 * type + size labels. The `viewBox` is in meters and scales via CSS (width/height: 100%), so it stays
 * responsive with no resize listener needed.
 *
 * This is a drafting/rendering pass only: the rooms' actual positions and sizes are exactly what the
 * backend generated (still a single-row-per-floor layout, per specs/003's documented placeholder
 * algorithm) — nothing here changes the underlying geometry. */
function SketchSvg({ rooms }: SketchSvgProps) {
  const floors = [...new Set(rooms.map((room) => room.floor))].sort((a, b) => a - b)
  const [activeFloor, setActiveFloor] = useState<number>(floors[0] ?? 1)

  useEffect(() => {
    if (floors.length > 0 && !floors.includes(activeFloor)) {
      setActiveFloor(floors[0])
    }
    // Only re-run when the set of available floors actually changes (e.g. after regeneration).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [floors.join(',')])

  if (rooms.length === 0) {
    return <p className="sketch-svg-empty">אין עדיין נתוני תכנון להצגה</p>
  }

  const floorRooms = rooms.filter((room) => room.floor === activeFloor).sort((a, b) => a.x - b.x)
  const maxX = Math.max(...floorRooms.map((room) => room.x + room.width_m), 0)
  const maxDepth = Math.max(...floorRooms.map((room) => room.depth_m), 0)
  const viewBox = `${-SIDE_PAD_M} ${-TOP_PAD_M} ${maxX + SIDE_PAD_M + RIGHT_PAD_M} ${maxDepth + TOP_PAD_M + SIDE_PAD_M}`

  // The ground floor's living room gets a stylized front entry (opening toward the garden backdrop);
  // this is a drafting convention for legibility, not a claim about the real entry's location.
  const groundFloor = floors[0]
  const livingRoom =
    activeFloor === groundFloor ? floorRooms.find((room) => room.type === 'living_room') : undefined

  let exteriorWallPath: string
  let exteriorDoorPath: string | null = null
  if (livingRoom) {
    const half = Math.min(DOOR_WIDTH_M / 2, livingRoom.width_m / 2 - 0.1)
    const centerX = livingRoom.x + livingRoom.width_m / 2
    const gapStart = centerX - half
    const gapEnd = centerX + half
    exteriorWallPath =
      `M 0 0 L ${maxX} 0 L ${maxX} ${maxDepth} L ${gapEnd} ${maxDepth} ` +
      `M ${gapStart} ${maxDepth} L 0 ${maxDepth} L 0 0`
    exteriorDoorPath = doorSymbolPath(
      [gapStart, maxDepth],
      [gapStart, maxDepth - DOOR_WIDTH_M],
      [gapEnd, maxDepth],
    )
  } else {
    exteriorWallPath = `M 0 0 L ${maxX} 0 L ${maxX} ${maxDepth} L 0 ${maxDepth} Z`
  }

  const partitionXs: number[] = []
  for (let i = 0; i < floorRooms.length - 1; i++) {
    partitionXs.push(floorRooms[i].x + floorRooms[i].width_m)
  }
  const partitionDoorHalf = Math.min(DOOR_WIDTH_M / 2, maxDepth / 2 - 0.1)
  const partitionGapCenterY = maxDepth / 2

  const typeCounts = new Map<string, number>()
  for (const room of floorRooms) {
    typeCounts.set(room.type, (typeCounts.get(room.type) ?? 0) + 1)
  }
  const typeSeen = new Map<string, number>()

  return (
    <div className="sketch-svg-wrapper">
      {floors.length > 1 && (
        <div className="sketch-svg-floor-tabs" role="tablist" aria-label="בחירת קומה">
          {floors.map((floor) => (
            <button
              key={floor}
              type="button"
              role="tab"
              aria-selected={floor === activeFloor}
              className={
                floor === activeFloor
                  ? 'sketch-svg-floor-tab sketch-svg-floor-tab--active'
                  : 'sketch-svg-floor-tab'
              }
              onClick={() => setActiveFloor(floor)}
            >
              קומה {floor}
            </button>
          ))}
        </div>
      )}

      <svg
        className="sketch-svg"
        viewBox={viewBox}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={`שרטוט סקיצה של קומה ${activeFloor}`}
      >
        <defs>
          <pattern id="sketch-grid" width={1} height={1} patternUnits="userSpaceOnUse">
            <path d="M 1 0 L 0 0 0 1" fill="none" className="sketch-svg-grid-line" />
          </pattern>
        </defs>

        <rect
          x={-SIDE_PAD_M}
          y={-TOP_PAD_M}
          width={maxX + SIDE_PAD_M + RIGHT_PAD_M}
          height={maxDepth + TOP_PAD_M + SIDE_PAD_M}
          className="sketch-svg-base"
        />
        <rect
          x={-SIDE_PAD_M}
          y={-TOP_PAD_M}
          width={maxX + SIDE_PAD_M + RIGHT_PAD_M}
          height={maxDepth + TOP_PAD_M + SIDE_PAD_M}
          fill="url(#sketch-grid)"
        />

        {floorRooms.map((room, index) => {
          const seen = typeSeen.get(room.type) ?? 0
          typeSeen.set(room.type, seen + 1)
          const cx = room.x + room.width_m / 2
          const cy = room.y + room.depth_m / 2
          const narrow = room.width_m < room.depth_m * 0.55
          const fontSize = Math.max(0.15, Math.min(0.32, Math.min(room.width_m, room.depth_m) * 0.24))

          return (
            <g key={`${room.type}-${index}`}>
              <rect
                className={`sketch-svg-room sketch-svg-room--${room.type}`}
                x={room.x}
                y={room.y}
                width={room.width_m}
                height={room.depth_m}
              />
              {/* A room wide enough for two lines gets type + dimensions; a sliver too narrow for
                  that (< 0.9m — a direct symptom of the generator's single-row layout, not something
                  styling alone can fix) gets just its type name, to avoid the two lines overlapping
                  the next room over. */}
              {room.width_m >= 0.9 ? (
                <text
                  className="sketch-svg-room-label"
                  x={cx}
                  y={cy}
                  style={{ fontSize }}
                  transform={narrow ? `rotate(-90 ${cx} ${cy})` : undefined}
                >
                  <tspan x={cx} dy="-0.2em">
                    {roomLabel(room, seen, typeCounts.get(room.type) ?? 1)}
                  </tspan>
                  <tspan
                    x={cx}
                    dy="1.3em"
                    className="sketch-svg-room-dims"
                    style={{ fontSize: fontSize * 0.62 }}
                  >
                    {room.width_m.toFixed(1)}×{room.depth_m.toFixed(1)} מ&apos; · {room.area_m2.toFixed(1)}{' '}
                    מ&quot;ר
                  </tspan>
                </text>
              ) : (
                <text
                  className="sketch-svg-room-label"
                  x={cx}
                  y={cy}
                  style={{ fontSize: Math.min(fontSize, 0.22) }}
                  transform={`rotate(-90 ${cx} ${cy})`}
                >
                  {roomLabel(room, seen, typeCounts.get(room.type) ?? 1)}
                </text>
              )}
            </g>
          )
        })}

        {partitionXs.map((x, index) => (
          <g key={index}>
            <path
              d={
                `M ${x} 0 L ${x} ${partitionGapCenterY - partitionDoorHalf} ` +
                `M ${x} ${partitionGapCenterY + partitionDoorHalf} L ${x} ${maxDepth}`
              }
              className="sketch-svg-wall-interior"
            />
            <path
              d={doorSymbolPath(
                [x, partitionGapCenterY - partitionDoorHalf],
                [x + DOOR_WIDTH_M, partitionGapCenterY - partitionDoorHalf],
                [x, partitionGapCenterY + partitionDoorHalf],
              )}
              className="sketch-svg-door"
            />
          </g>
        ))}

        <path d={exteriorWallPath} className="sketch-svg-wall-exterior" />
        {exteriorDoorPath && <path d={exteriorDoorPath} className="sketch-svg-door" />}

        <g>
          <line x1={0} y1={-0.55} x2={maxX} y2={-0.55} className="sketch-svg-dim-line" />
          <line x1={0} y1={0} x2={0} y2={-0.55} className="sketch-svg-dim-ext" />
          <line x1={maxX} y1={0} x2={maxX} y2={-0.55} className="sketch-svg-dim-ext" />
          <text x={maxX / 2} y={-0.75} className="sketch-svg-dim-text" style={{ fontSize: 0.26 }}>
            {maxX.toFixed(1)} מ&apos;
          </text>
        </g>

        <g>
          <line
            x1={maxX + 0.55}
            y1={0}
            x2={maxX + 0.55}
            y2={maxDepth}
            className="sketch-svg-dim-line"
          />
          <line x1={maxX} y1={0} x2={maxX + 0.55} y2={0} className="sketch-svg-dim-ext" />
          <line x1={maxX} y1={maxDepth} x2={maxX + 0.55} y2={maxDepth} className="sketch-svg-dim-ext" />
          <text
            x={maxX + 0.8}
            y={maxDepth / 2}
            className="sketch-svg-dim-text"
            style={{ fontSize: 0.26 }}
            transform={`rotate(-90 ${maxX + 0.8} ${maxDepth / 2})`}
          >
            {maxDepth.toFixed(1)} מ&apos;
          </text>
        </g>

        <g transform={`translate(${maxX + RIGHT_PAD_M - 0.5} ${-TOP_PAD_M + 0.6})`}>
          <circle r={0.5} className="sketch-svg-compass-ring" />
          <path d="M 0 -0.32 L 0.12 0.08 L 0 -0.05 L -0.12 0.08 Z" className="sketch-svg-compass-needle" />
          <text y={0.35} className="sketch-svg-compass-label" style={{ fontSize: 0.22 }}>
            N
          </text>
        </g>
      </svg>
    </div>
  )
}

export default SketchSvg
