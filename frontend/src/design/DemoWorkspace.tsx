import type { DemoDesign } from './demoDesign'
import DemoPlan from './DemoPlan'
import './DemoWorkspace.css'

/** SCREEN D — the plan workspace. The drawing dominates; information sits beside it, never on top.
 *
 * The side panel states only what the backend actually validated. `design.validation.statements`
 * is already product language produced from the passing checks — this component never invents a
 * claim, and never shows a raw check code. */
function DemoWorkspace({ design, onChangeRequirements }: {
  design: DemoDesign
  onChangeRequirements: () => void
}) {
  const rooms = [...design.rooms].sort((a, b) => b.area_m2 - a.area_m2)

  return (
    <div className="workspace">
      <main className="workspace-plan">
        <DemoPlan design={design} />
      </main>

      <aside className="workspace-side" aria-label="פרטי התוכנית">
        <h2 className="workspace-title">התוכנית שלך</h2>

        <dl className="workspace-areas">
          <div>
            <dt>שטח בנוי</dt>
            <dd>{design.gross_area_m2.toFixed(1)} מ״ר</dd>
          </div>
          <div>
            <dt>שטח נטו</dt>
            <dd>{design.net_area_m2.toFixed(1)} מ״ר</dd>
          </div>
        </dl>

        <h3 className="workspace-subtitle">חדרים</h3>
        <ul className="workspace-rooms">
          {rooms.map((room) => (
            <li key={room.id}>
              <span>{room.name}</span>
              <span className="workspace-room-area">{room.area_m2.toFixed(1)} מ״ר</span>
            </li>
          ))}
        </ul>

        {design.validation.statements.length > 0 ? (
          <>
            <h3 className="workspace-subtitle">בדיקות תכנון</h3>
            <ul className="workspace-checks">
              {design.validation.statements.map((statement) => (
                <li key={statement}>{statement}</li>
              ))}
            </ul>
          </>
        ) : null}

        {design.validation.warnings.length > 0 ? (
          <ul className="workspace-warnings" role="alert">
            {design.validation.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        ) : null}

        <button type="button" className="workspace-action" onClick={onChangeRequirements}>
          שינוי דרישות
        </button>
      </aside>
    </div>
  )
}

export default DemoWorkspace
