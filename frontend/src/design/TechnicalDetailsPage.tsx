import type { Project, TaggedValue } from '../types'
import { ROOM_LABELS } from './roomTypes'
import './TechnicalDetailsPage.css'

interface TechnicalDetailsPageProps {
  project: Project
  onBack: () => void
}

const SOURCE_LABELS: Record<TaggedValue<unknown>['source'], string> = {
  requested: 'התבקש במפורש',
  inferred: 'הוסק מהתיאור',
  unknown: 'לא ידוע',
}

function TaggedRow({
  label,
  tagged,
  unit = '',
}: {
  label: string
  tagged: TaggedValue<unknown> | null | undefined
  unit?: string
}) {
  const display =
    tagged == null || tagged.value === null ? 'לא ידוע' : `${String(tagged.value)}${unit}`
  return (
    <div className="tech-details__row">
      <dt>{label}</dt>
      <dd>
        {display}
        {tagged != null && <span className="tech-details__source">({SOURCE_LABELS[tagged.source]})</span>}
      </dd>
    </div>
  )
}

/** User Story 4's read-only Technical Details view (FR-015): what the user entered at creation
 * (Feature 01), what was parsed from their description (Feature 02, with source tags), and the
 * generated design model (Feature 03). Rendered as an overlay on top of DesignPage (not a replacement)
 * so the sketch/chat underneath keep their state while this is open (FR-016). */
function TechnicalDetailsPage({ project, onBack }: TechnicalDetailsPageProps) {
  const floors = project.rooms ? [...new Set(project.rooms.map((room) => room.floor))].sort((a, b) => a - b) : []

  return (
    <div className="tech-details" dir="rtl">
      <div className="tech-details__header">
        <button type="button" className="tech-details__back" onClick={onBack} aria-label="חזרה לסקיצה">
          →
        </button>
        <h1>פרטים טכניים</h1>
      </div>

      <section className="tech-details__section">
        <h2>נתונים שהוזנו</h2>
        <dl>
          <div className="tech-details__row">
            <dt>עיר</dt>
            <dd>{project.city}</dd>
          </div>
          <div className="tech-details__row">
            <dt>רחוב</dt>
            <dd>{project.street}</dd>
          </div>
          <div className="tech-details__row">
            <dt>שטח מגרש</dt>
            <dd>{project.plot_area_m2} מ"ר</dd>
          </div>
          <div className="tech-details__row">
            <dt>שטח בנייה</dt>
            <dd>{project.built_area_m2} מ"ר</dd>
          </div>
          <div className="tech-details__row">
            <dt>תיאור</dt>
            <dd>{project.description}</dd>
          </div>
        </dl>
      </section>

      <section className="tech-details__section">
        <h2>דרישות שחולצו מהתיאור</h2>
        {project.requirements_parsed_at ? (
          <dl>
            <TaggedRow label="מספר קומות" tagged={project.floors} />
            <TaggedRow label="מספר חדרי שינה" tagged={project.bedrooms} />
            <TaggedRow label="ממ&quot;ד" tagged={project.safe_room} />
            <TaggedRow label="מספר חניות" tagged={project.parking_spaces} />
            {project.pool && (
              <>
                <TaggedRow label="בריכה מבוקשת" tagged={project.pool.requested} />
                <TaggedRow label="אורך בריכה" tagged={project.pool.length_m} unit=" מ'" />
                <TaggedRow label="רוחב בריכה" tagged={project.pool.width_m} unit=" מ'" />
              </>
            )}
          </dl>
        ) : (
          <p className="tech-details__empty">הדרישות עדיין לא חולצו מהתיאור</p>
        )}
      </section>

      <section className="tech-details__section">
        <h2>מודל תכנון שנוצר</h2>
        {project.rooms && project.rooms.length > 0 ? (
          <>
            <div className="tech-details__row">
              <dt>מידות המגרש (הנחת מגרש ריבועי)</dt>
              <dd>
                {project.site_width_m?.toFixed(1)} x {project.site_depth_m?.toFixed(1)} מ'
              </dd>
            </div>
            {floors.map((floor) => (
              <p key={floor} className="tech-details__floor">
                <strong>קומה {floor}:</strong>{' '}
                {project.rooms!
                  .filter((room) => room.floor === floor)
                  .map((room) => `${ROOM_LABELS[room.type] ?? room.type} (${room.area_m2.toFixed(1)} מ"ר)`)
                  .join(', ')}
              </p>
            ))}
            {project.design_notes && project.design_notes.length > 0 && (
              <ul className="tech-details__notes">
                {project.design_notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            )}
          </>
        ) : (
          <p className="tech-details__empty">מודל התכנון עדיין לא נוצר</p>
        )}
      </section>
    </div>
  )
}

export default TechnicalDetailsPage
