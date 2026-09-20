import type { DemoDesign, DemoQuality } from '../../design/demoDesign'
import './RoomDetails.css'

/** PER-ROOM DETAILS (Issue #63) — the exposure/window fact, the wet-room privacy summary, and the
 * doors touching whichever room is currently hovered or selected. Every fact is read directly off
 * the contract's `quality.exposure` / `quality.wet_privacy` / `design.doors`, matched to the room
 * by its own id — nothing here is computed from the room's geometry. */

const SIDE_LABEL: Record<string, string> = { N: 'צפון', E: 'מזרח', S: 'דרום', W: 'מערב' }

const NO_WINDOW_REASON_LABEL: Record<string, string> = {
  NO_EXTERIOR_WALL: 'אין קיר חיצוני לחדר זה',
  EXTERIOR_WALL_TOO_SHORT: 'הקיר החיצוני קצר מכדי לקבל חלון',
  WINDOW_NOT_REQUIRED: 'לא נדרש חלון לחדר מסוג זה',
}

const ZONE_CLASS_LABEL: Record<string, string> = {
  PRIVATE: 'פרטי', CIRCULATION: 'מסדרון', PUBLIC: 'ציבורי', SERVICE: 'שירות', OTHER: 'אחר',
}

const DOOR_KIND_LABEL: Record<string, string> = {
  ROOM_DOOR: 'דלת חדר',
  SERVICE_DOOR: 'דלת שירות',
  ENTRANCE_DOOR: 'דלת כניסה',
  CASED_OPENING: 'מעבר פתוח (ללא דלת)',
}

function roomName(design: DemoDesign, roomId: string | null): string | null {
  return design.rooms.find((r) => r.id === roomId)?.name ?? null
}

function RoomDetails({ design, quality, roomId }: {
  design: DemoDesign
  quality: DemoQuality | null | undefined
  roomId: string | null
}) {
  if (roomId === null) return null
  const room = design.rooms.find((r) => r.id === roomId)
  if (!room) return null

  const exposure = quality?.exposure?.find((e) => e.room_id === roomId)
  const privacy = quality?.wet_privacy?.find((w) => w.zone_id === roomId)
  const doors = design.doors.filter((d) => d.a === roomId || d.b === roomId)

  return (
    <section className="room-details" aria-label={`פרטי ${room.name}`}>
      <h3 className="room-details-title">{room.name}</h3>

      {exposure ? (
        <dl className="room-details-facts">
          <div>
            <dt>קירות חוץ</dt>
            <dd>
              {exposure.exterior_sides.length > 0
                ? exposure.exterior_sides.map((s) => SIDE_LABEL[s] ?? s).join(', ')
                : 'אין'}
            </dd>
          </div>
          <div>
            <dt>חלון</dt>
            <dd>
              {exposure.window_side
                ? `${SIDE_LABEL[exposure.window_side] ?? exposure.window_side} · ${exposure.window_width_m?.toFixed(2)} מ׳`
                : (exposure.no_window_reason ? (NO_WINDOW_REASON_LABEL[exposure.no_window_reason] ?? exposure.no_window_reason) : 'אין')}
            </dd>
          </div>
        </dl>
      ) : null}

      {privacy ? (
        <dl className="room-details-facts">
          <div>
            <dt>נכנסים מ־</dt>
            <dd>{privacy.entered_from ? (roomName(design, privacy.entered_from) ?? privacy.entered_from) : 'לא ידוע'}
              {' '}({ZONE_CLASS_LABEL[privacy.entered_from_class] ?? privacy.entered_from_class})</dd>
          </div>
          <div>
            <dt>פונה אל</dt>
            <dd>{privacy.door_facing ? (roomName(design, privacy.door_facing) ?? privacy.door_facing) : 'אין קו ראייה ישיר'}</dd>
          </div>
          <div>
            <dt>ציון פרטיות</dt>
            <dd>{privacy.privacy_score.toFixed(2)}</dd>
          </div>
        </dl>
      ) : null}

      {doors.length > 0 ? (
        <ul className="room-details-doors">
          {doors.map((door, i) => (
            <li key={i}>
              {DOOR_KIND_LABEL[door.kind] ?? door.kind} · {door.width_m.toFixed(2)} מ׳
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}

export default RoomDetails
