import type { DemoLayoutObject } from '../../design/demoDesign'

/** Engine-placed semantic layout objects (Issue #39) — drawn AS-IS, one rectangle per object,
 * labelled with its own `kind`. This component decides nothing architectural: it never invents a
 * decorative object, never guesses a position, never draws an item the backend did not place —
 * the same boundary `DoorSymbol` already holds for doors. An object whose placement failed is
 * simply absent from `design.layout` (`RoomLayout.unplaceable`, backend-only diagnostic data) —
 * never drawn as a guess. */

function kindClass(kind: string): string {
  return `demo-layout-object--${kind.toLowerCase().replace(/_/g, '-')}`
}

export function InteriorLayout({ objects }: { objects: DemoLayoutObject[] }) {
  return (
    <g className="demo-layout">
      {objects.map((obj, i) => (
        <g key={`layout-${obj.room_id}-${obj.kind}-${i}`} className={`demo-layout-object ${kindClass(obj.kind)}`}>
          <rect x={obj.x} y={obj.y} width={obj.width_m} height={obj.depth_m} className="demo-layout-object-rect" />
          <text
            x={obj.x + obj.width_m / 2}
            y={obj.y + obj.depth_m / 2}
            className="demo-layout-object-label"
          >
            {obj.kind}
          </text>
        </g>
      ))}
    </g>
  )
}

export default InteriorLayout
