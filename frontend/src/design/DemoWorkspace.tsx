import { useEffect, useState } from 'react'
import type { DemoPlanSet } from './demoDesign'
import DemoPlan from './DemoPlan'
import PlanLegend from './PlanLegend'
import './DemoWorkspace.css'

/** The plans in the order the backend produced them: the engine's own choice first.
 *
 * A plan's LABEL is bound to this original position, not to where it currently sits on screen, so
 * "אפשרות 2" keeps meaning the same drawing after the person has swapped things around. */
function labelFor(index: number): string {
  return index === 0 ? 'הבחירה של המנוע' : `אפשרות ${index + 1}`
}

/** SCREEN D — the plan workspace. The drawing dominates; information sits beside it, never on top.
 *
 * The side panel states only what the backend actually validated. `design.validation.statements`
 * is already product language produced from the passing checks — this component never invents a
 * claim, and never shows a raw check code.
 *
 * ALTERNATIVES. The engine ranks its candidates, but the ranking cannot settle taste: several
 * layouts pass every check and a person may simply prefer one of the others. The ones the backend
 * proved are shown small beside the drawing, and picking one SWAPS it with the large plan — the
 * drawing that was large takes the slot of the one that replaced it, so the set on screen stays
 * the same set and nothing is lost by looking. Everything beside the drawing (areas, rooms,
 * legend, checks) is read off the plan CURRENTLY shown, so the panel always describes what the
 * person is looking at. */
function DemoWorkspace({ plans, onChangeRequirements }: {
  plans: DemoPlanSet
  onChangeRequirements: () => void
}) {
  const all = [plans.plan, ...plans.alternatives]

  // `order[0]` is the plan on the drawing board; the rest are the thumbnails, in the order they
  // are currently sitting in. Positions, not identities — see `swapWithLargePlan`.
  const [order, setOrder] = useState<number[]>(() => all.map((_, index) => index))

  // A fresh generation replaces the whole set. Without this the old order would be applied to new
  // plans, and after a regeneration that produced fewer alternatives it would index past the end.
  useEffect(() => {
    setOrder(all.map((_, index) => index))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plans])

  /** The clicked thumbnail becomes the large plan, and the large one takes the slot it left. */
  function swapWithLargePlan(slot: number) {
    setOrder((current) => {
      const next = [...current]
      ;[next[0], next[slot]] = [next[slot], next[0]]
      return next
    })
  }

  // The fallback covers the one render between a new `plans` arriving and the effect above
  // resetting `order`: for that frame the stale order may point past the end of the new set.
  const design = all[order[0]] ?? plans.plan
  const rooms = [...design.rooms].sort((a, b) => b.area_m2 - a.area_m2)

  return (
    <div className="workspace">
      <main className="workspace-plan">
        <div className="workspace-plan-main">
          <DemoPlan design={design} />
        </div>

        {order.length > 1 ? (
          <div className="workspace-options">
            <h2 className="workspace-options-title">
              אפשרויות נוספות שעברו את אותן בדיקות — לחיצה מציגה בגדול
            </h2>
            <ul className="workspace-options-strip">
              {order.slice(1).map((planIndex, position) => (
                <li key={planIndex}>
                  <button
                    type="button"
                    className="workspace-option"
                    onClick={() => swapWithLargePlan(position + 1)}
                    aria-label={`הצג בגדול: ${labelFor(planIndex)}`}
                    data-testid={`plan-option-${planIndex}`}
                  >
                    <DemoPlan design={all[planIndex]} />
                    <span className="workspace-option-label">{labelFor(planIndex)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </main>

      <aside className="workspace-side" aria-label="פרטי התוכנית">
        <h2 className="workspace-title">התוכנית שלך</h2>
        {order.length > 1 ? (
          <p className="workspace-shown" data-testid="plan-shown">{labelFor(order[0])}</p>
        ) : null}

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

        <PlanLegend design={design} />

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
