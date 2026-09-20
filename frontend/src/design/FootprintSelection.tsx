import { useEffect, useMemo, useState, type KeyboardEvent } from 'react'
import {
  customFootprint,
  fitsBuildable,
  footprintFromOption,
  type FootprintOptionsResponse,
  FOOTPRINT_SHAPE_LABELS,
  footprintAreaToleranceM2,
  isFootprintAreaValid,
  isFootprintStillValid,
  NO_BUILDABLE_AREA_CODE,
  type BuildingFootprint,
} from './footprint'
import { Dim } from './Dim'
import './FootprintSelection.css'

interface FootprintSelectionProps {
  /** Site-aware options computed by the BACKEND. Every entry is already proven to fit the buildable
   *  region, so the screen cannot offer an impossible outline — the defect this replaced. */
  site: FootprintOptionsResponse | null
  /** TARGET BUILT AREA (Project.built_area_m2) — never re-derived here, always passed down from the
   * one place it was actually entered (App.tsx's form). */
  targetAreaM2: number
  /** The SELECTED BUILDING FOOTPRINT — owned by App.tsx (see this task's requirement that the
   * choice "must not exist only as temporary visual state"), not local to this component. `null`
   * means no valid selection yet (nothing chosen, or a stale one App.tsx already cleared). */
  value: BuildingFootprint | null
  onChange: (footprint: BuildingFootprint | null) => void
  /** Present only when this is a screen of its own. Under the advanced disclosure (feature 006)
   *  the form's own submit button continues, so there is nothing to confirm here. */
  onConfirm?: () => void
  onBack?: () => void
  submitting?: boolean
  /** INLINE — rendered inside the brief form's advanced disclosure rather than as a step of its
   *  own: no page title, no continue/back buttons; the cards and the site facts only. */
  inline?: boolean
}

const VIEW_W = 132
const VIEW_H = 92
const MAX_RECT_W = 108
const MAX_RECT_H = 68

/** Fits a `widthM` x `depthM` rectangle inside the fixed preview viewBox, preserving its true aspect
 * ratio — this is what makes every card's outline visually distinct (a wide option really does look
 * wider on screen), not a cosmetic approximation. */
function fitPreviewRect(widthM: number, depthM: number) {
  if (!Number.isFinite(widthM) || !Number.isFinite(depthM) || widthM <= 0 || depthM <= 0) return null
  const scale = Math.min(MAX_RECT_W / widthM, MAX_RECT_H / depthM)
  const w = widthM * scale
  const h = depthM * scale
  return { x: (VIEW_W - w) / 2, y: (VIEW_H - h) / 2, w, h }
}

function FootprintPreview({ widthM, depthM, placeholder }: { widthM: number; depthM: number; placeholder?: boolean }) {
  const rect = fitPreviewRect(widthM, depthM)
  return (
    <svg className="footprint-card__preview" viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} aria-hidden="true">
      {rect ? (
        <rect x={rect.x} y={rect.y} width={rect.w} height={rect.h} rx="2" className="footprint-card__rect" />
      ) : (
        <rect
          x={(VIEW_W - MAX_RECT_W) / 2}
          y={(VIEW_H - MAX_RECT_H) / 2}
          width={MAX_RECT_W}
          height={MAX_RECT_H}
          rx="2"
          className={placeholder ? 'footprint-card__rect footprint-card__rect--placeholder' : 'footprint-card__rect'}
          strokeDasharray={placeholder ? '5 5' : undefined}
        />
      )}
    </svg>
  )
}

function PresetCard({
  footprint,
  selected,
  onSelect,
}: {
  footprint: BuildingFootprint
  selected: boolean
  onSelect: () => void
}) {
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      onSelect()
    }
  }

  return (
    <div
      className={selected ? 'footprint-card footprint-card--selected' : 'footprint-card'}
      role="radio"
      aria-checked={selected}
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={onKeyDown}
    >
      <FootprintPreview widthM={footprint.width_m} depthM={footprint.depth_m} />
      <p className="footprint-card__name">{FOOTPRINT_SHAPE_LABELS[footprint.shape_type]}</p>
      <p className="footprint-card__dims">
        <Dim a={footprint.width_m} b={footprint.depth_m} /> מ&apos;
      </p>
      <p className="footprint-card__area">{footprint.area_m2.toFixed(2)} מ&quot;ר</p>
    </div>
  )
}

function parsePositive(text: string): number | null {
  const value = Number(text)
  return text.trim() !== '' && Number.isFinite(value) && value > 0 ? value : null
}

function CustomCard({
  buildable,
  targetAreaM2,
  selected,
  initialWidthText,
  initialDepthText,
  onSelect,
}: {
  buildable: { width_m: number; depth_m: number; has_area: boolean } | null
  targetAreaM2: number
  selected: boolean
  initialWidthText: string
  initialDepthText: string
  onSelect: (footprint: BuildingFootprint | null) => void
}) {
  const [widthText, setWidthText] = useState(initialWidthText)
  const [depthText, setDepthText] = useState(initialDepthText)

  const width = parsePositive(widthText)
  const depth = parsePositive(depthText)
  const area = width !== null && depth !== null ? width * depth : null
  // Valid means BOTH: the right area, and an outline that actually goes on the land. The backend
  // enforces the second independently (see projects/routes/base_routes.py) — this only stops the
  // person submitting something it will refuse.
  const fits = width !== null && depth !== null && buildable !== null
    ? buildable.has_area && fitsBuildable(width, depth, buildable.width_m, buildable.depth_m)
    : buildable === null
  const valid = area !== null && isFootprintAreaValid(area, targetAreaM2) && fits
  const hasBothValues = width !== null && depth !== null
  const tolerance = footprintAreaToleranceM2(targetAreaM2)

  // Reports the CUSTOM footprint upward the moment it becomes valid, and clears the selection the
  // moment it stops being valid — never a footprint whose area doesn't actually match what the user
  // typed (see the module docstring's "do not silently modify the user's entered dimensions"). Only
  // clears when CUSTOM was already the active selection (`selected`): typing into these fields while
  // a PRESET card is selected must never silently wipe out that unrelated, valid selection.
  useEffect(() => {
    if (width !== null && depth !== null && valid) {
      onSelect(customFootprint(targetAreaM2, width, depth))
    } else if (selected) {
      onSelect(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [widthText, depthText, targetAreaM2])

  return (
    <div
      className={selected ? 'footprint-card footprint-card--custom footprint-card--selected' : 'footprint-card footprint-card--custom'}
      data-testid="footprint-card-custom"
    >
      <FootprintPreview widthM={width ?? 0} depthM={depth ?? 0} placeholder={!hasBothValues} />
      <p className="footprint-card__name">{FOOTPRINT_SHAPE_LABELS.RECTANGLE}</p>
      {/* Names WHOSE dimensions these two fields are. Without it they read "רוחב"/"עומק" — the exact
          wording of the plot fields two screens back — and get re-entered as the plot's numbers. */}
      <p className="footprint-card__custom-caption">מידות הבניין</p>

      <div className="footprint-card__custom-inputs">
        <label>
          רוחב (מ&apos;)
          <input
            type="number"
            min="0.01"
            step="any"
            inputMode="decimal"
            value={widthText}
            onChange={(event) => setWidthText(event.target.value)}
            data-testid="footprint-custom-width"
          />
        </label>
        <label>
          עומק (מ&apos;)
          <input
            type="number"
            min="0.01"
            step="any"
            inputMode="decimal"
            value={depthText}
            onChange={(event) => setDepthText(event.target.value)}
            data-testid="footprint-custom-depth"
          />
        </label>
      </div>

      {hasBothValues && area !== null && (
        <p className={valid ? 'footprint-card__custom-feedback' : 'footprint-card__custom-feedback footprint-card__custom-feedback--invalid'}>
          <Dim a={width} b={depth} /> מ&apos; → {area.toFixed(2)} מ&quot;ר
          {valid ? (
            ' — תואם לשטח היעד ונכנס בשטח הבנייה'
          ) : !fits && buildable && !buildable.has_area ? (
            <> — אין אזור בנייה על המגרש הזה אחרי הנסיגות</>
          ) : !fits && buildable ? (
            <> — אינו נכנס בשטח הבנייה (<Dim a={buildable.width_m} b={buildable.depth_m} /> מ׳)</>
          ) : (
            <> — שטח היעד {targetAreaM2.toFixed(2)} מ&quot;ר (הפרש {Math.abs(area - targetAreaM2).toFixed(2)} מ&quot;ר, מעבר לסטייה המותרת {tolerance.toFixed(2)} מ&quot;ר)</>
          )}
        </p>
      )}
    </div>
  )
}

/** THE OUTLINE CARDS. Since feature 006 this is no longer a step of the main flow: the engine plans
 * its own outlines (measured: the person's choice planned in 30 % of briefs, each of the engine's
 * shapes in 35–45 %). It lives under the form's "advanced" disclosure (`inline`) for a person with a
 * real constraint — a permit tied to a rectangle, a frontage to keep — and an outline chosen here is
 * authoritative: it is planned first and, if it plans, shown first. Presents several PRESET rectangular options
 * (all preserving the same target built area, at genuinely different aspect ratios) plus a CUSTOM
 * option for the user's own exact width/depth. Selection is single (radiogroup semantics) and is
 * reported to the caller as a full `BuildingFootprint`, never as bare numbers.
 *
 * WHAT THIS STEP IS, AND WHAT IT IS NOT. It selects AUTHORITATIVE PHYSICAL INPUT: the building's
 * outline on the plot, which becomes the buildable rectangle the planner must fit the house inside
 * (backend/app/demo/requirements_view.py's `spec_for` -> `_buildable_from`). It is NOT a choice of
 * internal layout. The layout strategy, corridor organization, zoning and room arrangement are
 * INTERNAL PLANNING DECISIONS: `concept_generator.ConceptStrategy` is picked by the generator from
 * the approved requirements plus this outline, and is never an input the user supplies or sees.
 * The preset names (COMPACT/BALANCED/WIDE/NARROW) are outline PROPORTIONS, not layout styles —
 * hence the explicit note in the header, which exists to keep the two from being read as one. */
function FootprintSelection({ site, targetAreaM2, value, onChange, onConfirm, onBack, submitting = false, inline = false }: FootprintSelectionProps) {
  const options = useMemo(
    () => (site?.options ?? []).map((option) => footprintFromOption(option, targetAreaM2)),
    [site, targetAreaM2],
  )

  // Defensive invalidation: if `targetAreaM2` changes while a selection exists (App.tsx already
  // clears its own state when the built-area field itself changes, but this guards the component's
  // OWN contract independent of that) and the current selection no longer preserves the area within
  // tolerance, drop it rather than silently keep a stale footprint selectable/submittable.
  useEffect(() => {
    if (value !== null && !isFootprintStillValid(value, targetAreaM2)) {
      onChange(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetAreaM2])

  const selectedIsCustom = value?.source === 'CUSTOM'

  return (
    <section className={inline ? 'footprint-selection footprint-selection--inline' : 'footprint-selection'} dir="rtl">
      <header className={inline ? 'footprint-selection__inline-header' : 'page-header'}>
        {inline ? null : (
          <>
            <span className="eyebrow">BuildSmart</span>
            <h1>בחר/י את מתאר הבניין</h1>
          </>
        )}
        {/* The single most common confusion at this step: the four cards below rarely share the
            plot's own width/depth ratio, and nothing said why. The building is its OWN outline,
            smaller than the plot (a 200 m² building on a 300 m² plot leaves a garden) and free to
            take any proportion that preserves its target area — it is not the plot resized. */}
        {site && !site.rejection ? (
          <p className="footprint-selection__plot-note">
            המגרש שלך: <Dim a={site.plot_width_m} b={site.plot_depth_m} /> מ&apos; ({site.one_storey_footprint_capacity_m2.toFixed(0)} מ&quot;ר קיבולת בנייה). הבניין המבוקש — {targetAreaM2.toFixed(0)} מ&quot;ר — קטן מהמגרש, ולכן יכול לקבל כל יחס רוחב-עומק שמשמר את שטחו; הוא אינו חייב להתאים ליחס המידות של המגרש עצמו. ארבע ההצעות למטה הן ארבע צורות שונות לאותו שטח בניין.
          </p>
        ) : (
          <p>
            שטח בנייה יעד: {targetAreaM2.toFixed(2)} מ&quot;ר. זהו המתאר הפיזי של הבניין על המגרש — הגבול החיצוני
            בלבד. כל אפשרות שומרת בקירוב על אותו שטח בנייה ונבדלת רק ביחס המידות שלה.
          </p>
        )}
        <p className="footprint-selection__scope-note">
          החלוקה הפנימית — סידור החדרים, המסדרון והאזורים — נקבעת אוטומטית על ידי המערכת מתוך הדרישות שאישרת,
          ואינה נבחרת כאן.
        </p>
      </header>

      {/* NOTHING FITS. Said here, before any choosing, rather than as a refusal after a choice the
          system itself offered. The two actions are the two the system actually implements — a
          second storey is not among them. */}
      {site?.rejection ? (
        <section className="footprint-blocked" role="alert">
          <h2>
            {site.rejection.code === NO_BUILDABLE_AREA_CODE
              ? 'אין אזור בנייה על המגרש הזה'
              : 'שטח הבנייה המבוקש אינו נכנס בקומה אחת על המגרש הזה'}
          </h2>
          <dl>
            <div><dt>שטח בנייה מבוקש</dt><dd>{site.requested_built_area_m2.toFixed(2)} מ״ר</dd></div>
            <div><dt>מידות המגרש</dt><dd><Dim a={site.plot_width_m} b={site.plot_depth_m} /> מ׳</dd></div>
            <div>
              <dt>אזור בנייה שנגזר</dt>
              {/* An axis the setbacks used up leaves no rectangle to state the size of. The region
                  is EMPTY, and it is said in words — a negative length is not a dimension. */}
              <dd>{site.has_buildable_area
                ? <><Dim a={site.buildable_width_m} b={site.buildable_depth_m} /> מ׳</>
                : 'אין אזור בנייה'}</dd>
            </div>
            <div>
              <dt>קיבולת מתאר גאומטרית לקומה אחת</dt>
              <dd>{site.one_storey_footprint_capacity_m2.toFixed(2)} מ״ר</dd>
            </div>
          </dl>
          {/* The NO-BUILDABLE-AREA refusal states its own cause and its own two remedies, so it is
              shown as the backend wrote it. The capacity refusal's numbers are already in the list
              above and its remedies below, and repeating its sentence here would only duplicate
              them. */}
          {site.rejection.code === NO_BUILDABLE_AREA_CODE ? (
            <p className="footprint-blocked__note">{site.rejection.message}</p>
          ) : (
            <>
              <p className="footprint-blocked__note">
                זו קיבולת גאומטרית בלבד — תוכנית החדרים, מידות מינימום ורוחב המסדרון עשויים להקטין
                אותה עוד. {site.setback_disclaimer}
              </p>
              <p className="footprint-blocked__actions">
                אפשר להקטין את שטח הבנייה המבוקש, או לעדכן את הנחות הנסיגה — שתי האפשרויות זמינות
                במסך הקודם.
              </p>
            </>
          )}
        </section>
      ) : null}

      <div className="footprint-grid" role="radiogroup" aria-label="בחירת צורת מבנה">
        {options.map((option) => (
          <PresetCard
            key={option.id}
            footprint={option}
            selected={value?.id === option.id}
            onSelect={() => onChange(option)}
          />
        ))}
        <CustomCard
          buildable={site ? { width_m: site.buildable_width_m, depth_m: site.buildable_depth_m,
                              has_area: site.has_buildable_area } : null}
          targetAreaM2={targetAreaM2}
          selected={selectedIsCustom}
          initialWidthText={selectedIsCustom && value ? String(value.width_m) : ''}
          initialDepthText={selectedIsCustom && value ? String(value.depth_m) : ''}
          onSelect={onChange}
        />
      </div>

      {inline ? null : (
        <div className="footprint-actions">
          <button type="button" className="footprint-back" onClick={onBack} disabled={submitting}>
            ‹ חזרה לעריכת שטח הבנייה
          </button>
          <button type="button" className="submit-button" disabled={value === null || submitting} onClick={onConfirm}>
            {submitting ? 'יוצר פרויקט...' : 'המשך ליצירת התכנון'}
          </button>
        </div>
      )}
    </section>
  )
}

export default FootprintSelection
