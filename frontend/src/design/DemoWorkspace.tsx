import { useEffect, useState } from 'react'
import type { DemoOutline, DemoPlanSet } from './demoDesign'
import DemoPlan from './DemoPlan'
import PlanLegend from './PlanLegend'
import QualityPanel from '../components/review/QualityPanel'
import RoomDetails from '../components/review/RoomDetails'
import './DemoWorkspace.css'

/** THE OUTLINE A PLAN OCCUPIES, in the person's terms (feature 006). Width, depth and area come
 * from the backend's own label; the origin says whether the engine chose this rectangle or the
 * person entered it under "advanced". Different plans may sit on different outlines now, so the
 * label is what makes a same-family alternative on another outline read as a different house. */
function outlineText(outline: DemoOutline): string {
  const who = outline.origin === 'PERSON' ? 'המתאר שהזנת' : 'מתאר אוטומטי'
  if (outline.shape === 'L' && outline.wing_dims_m && outline.wing_dims_m.length === 2) {
    // Two wings: the label names both, so an L of 143 m² does not read as a 200 m² rectangle.
    const [[pw, pd], [aw, ad]] = outline.wing_dims_m
    return `בית L: ${pw.toFixed(2)} × ${pd.toFixed(2)} + ${aw.toFixed(2)} × ${ad.toFixed(2)} מ׳ · ${outline.area_m2.toFixed(0)} מ״ר · ${who}`
  }
  return `${outline.width_m.toFixed(2)} × ${outline.depth_m.toFixed(2)} מ׳ · ${outline.area_m2.toFixed(0)} מ״ר · ${who}`
}

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
function DemoWorkspace({ plans, streetFacingSide, onChangeRequirements }: {
  plans: DemoPlanSet
  /** The plot edge facing the street, from the project the plans were generated for — drawn as the
   *  compass on the large plan only; thumbnails are too small for it. */
  streetFacingSide?: string | null
  onChangeRequirements: () => void
}) {
  const all = [plans.plan, ...plans.alternatives]

  // `order[0]` is the plan on the drawing board; the rest are the thumbnails, in the order they
  // are currently sitting in. Positions, not identities — see `swapWithLargePlan`.
  const [order, setOrder] = useState<number[]>(() => all.map((_, index) => index))

  // Issue #63: which room's exposure/privacy/door facts `RoomDetails` shows, chosen from the room
  // list below. `null` — nothing selected — is the default; a fresh generation clears it, since a
  // room id from the old plan may not exist on the new one.
  const [selectedRoomId, setSelectedRoomId] = useState<string | null>(null)

  // A fresh generation replaces the whole set. Without this the old order would be applied to new
  // plans, and after a regeneration that produced fewer alternatives it would index past the end.
  useEffect(() => {
    setOrder(all.map((_, index) => index))
    setSelectedRoomId(null)
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

  // The person entered an outline and it could not be planned; what is on screen sits on an
  // outline the engine chose instead. Said once, above the drawing — never as a refusal, because a
  // house of the requested area exists; and never silently, because it is not the rectangle they
  // asked for. Read off the search summary, which is the backend's own record of what it tried.
  const personOutline = plans.search?.outlines.find((tried) => tried.origin === 'PERSON')
  const replaced = personOutline !== undefined && !personOutline.planned

  return (
    <div className="workspace">
      <main className="workspace-plan">
        {replaced ? (
          <p className="workspace-outline-note" role="note">
            המתאר שהזנת ({personOutline.width_m.toFixed(2)} × {personOutline.depth_m.toFixed(2)} מ׳)
            לא אפשר לסדר את החדרים שביקשת. התוכניות שלפניך הן באותו שטח בנייה, במתאר שהמערכת בחרה.
          </p>
        ) : null}
        <div className="workspace-plan-main">
          <DemoPlan design={design} streetFacingSide={streetFacingSide} />
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
                    {all[planIndex].outline ? (
                      <span className="workspace-option-outline">
                        {all[planIndex].outline!.width_m.toFixed(2)} × {all[planIndex].outline!.depth_m.toFixed(2)} מ׳
                      </span>
                    ) : null}
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

        {design.outline ? (
          <p className="workspace-outline" data-testid="plan-outline">
            <span className="workspace-outline-label">מתאר הבניין</span> {outlineText(design.outline)}
          </p>
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
        {/* Issue #63: hovering or clicking a room shows its exposure/privacy/door facts below —
            selection persists on click so it survives the mouse leaving the list. */}
        <ul className="workspace-rooms">
          {rooms.map((room) => (
            <li key={room.id}>
              <button
                type="button"
                className="workspace-room-select"
                aria-pressed={selectedRoomId === room.id}
                onMouseEnter={() => setSelectedRoomId(room.id)}
                onFocus={() => setSelectedRoomId(room.id)}
                onClick={() => setSelectedRoomId(room.id)}
              >
                <span>{room.name}</span>
                <span className="workspace-room-area">{room.area_m2.toFixed(1)} מ״ר</span>
              </button>
            </li>
          ))}
        </ul>

        <RoomDetails design={design} quality={design.quality} roomId={selectedRoomId} />

        <QualityPanel quality={design.quality} />

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

        {/* Room-size quality notices: not validation, not an alert — a note that some rooms came
            out well past their recommended size (the backend decides which; see DemoQuality). */}
        {design.quality && design.quality.notices.length > 0 ? (
          <ul className="workspace-quality" role="note">
            {design.quality.notices.map((notice) => (
              <li key={notice}>{notice}</li>
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
