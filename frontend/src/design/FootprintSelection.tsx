import { useEffect, useMemo, useState, type KeyboardEvent } from 'react'
import {
  customFootprint,
  FOOTPRINT_SHAPE_LABELS,
  footprintAreaToleranceM2,
  generateFootprintOptions,
  isFootprintAreaValid,
  isFootprintStillValid,
  type BuildingFootprint,
} from './footprint'
import './FootprintSelection.css'

interface FootprintSelectionProps {
  /** TARGET BUILT AREA (Project.built_area_m2) — never re-derived here, always passed down from the
   * one place it was actually entered (App.tsx's form). */
  targetAreaM2: number
  /** The SELECTED BUILDING FOOTPRINT — owned by App.tsx (see this task's requirement that the
   * choice "must not exist only as temporary visual state"), not local to this component. `null`
   * means no valid selection yet (nothing chosen, or a stale one App.tsx already cleared). */
  value: BuildingFootprint | null
  onChange: (footprint: BuildingFootprint | null) => void
  onConfirm: () => void
  onBack: () => void
  submitting?: boolean
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
        {footprint.width_m.toFixed(2)} × {footprint.depth_m.toFixed(2)} מ&apos;
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
  targetAreaM2,
  selected,
  initialWidthText,
  initialDepthText,
  onSelect,
}: {
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
  const valid = area !== null && isFootprintAreaValid(area, targetAreaM2)
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
          {width.toFixed(2)} × {depth.toFixed(2)} מ&apos; → {area.toFixed(2)} מ&quot;ר
          {valid ? (
            ' — תואם לשטח היעד'
          ) : (
            <> — שטח היעד {targetAreaM2.toFixed(2)} מ&quot;ר (הפרש {Math.abs(area - targetAreaM2).toFixed(2)} מ&quot;ר, מעבר לסטייה המותרת {tolerance.toFixed(2)} מ&quot;ר)</>
          )}
        </p>
      )}
    </div>
  )
}

/** The FOOTPRINT SELECTION step — shown once the target built area is known (App.tsx's 'footprint'
 * view), before any architectural plan generation runs. Presents several PRESET rectangular options
 * (all preserving the same target built area, at genuinely different aspect ratios) plus a CUSTOM
 * option for the user's own exact width/depth. Selection is single (radiogroup semantics) and is
 * reported to the caller as a full `BuildingFootprint`, never as bare numbers. */
function FootprintSelection({ targetAreaM2, value, onChange, onConfirm, onBack, submitting = false }: FootprintSelectionProps) {
  const options = useMemo(() => generateFootprintOptions(targetAreaM2), [targetAreaM2])

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
    <section className="footprint-selection" dir="rtl">
      <header className="page-header">
        <span className="eyebrow">BuildSmart</span>
        <h1>בחר/י את צורת המבנה</h1>
        <p>
          שטח בנייה יעד: {targetAreaM2.toFixed(2)} מ&quot;ר. כל אפשרות שומרת בקירוב על אותו שטח בנייה — הצורה הסופית
          עדיין לא נקבעה על ידי המערכת.
        </p>
      </header>

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
          targetAreaM2={targetAreaM2}
          selected={selectedIsCustom}
          initialWidthText={selectedIsCustom && value ? String(value.width_m) : ''}
          initialDepthText={selectedIsCustom && value ? String(value.depth_m) : ''}
          onSelect={onChange}
        />
      </div>

      <div className="footprint-actions">
        <button type="button" className="footprint-back" onClick={onBack} disabled={submitting}>
          ‹ חזרה לעריכת שטח הבנייה
        </button>
        <button type="button" className="submit-button" disabled={value === null || submitting} onClick={onConfirm}>
          {submitting ? 'יוצר פרויקט...' : 'המשך ליצירת התכנון'}
        </button>
      </div>
    </section>
  )
}

export default FootprintSelection
