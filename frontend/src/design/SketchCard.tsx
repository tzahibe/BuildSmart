import { useEffect } from 'react'
import type { Room } from '../types'
import SketchSvg from './SketchSvg'
import './SketchCard.css'

interface SketchCardProps {
  rooms: Room[]
  expanded: boolean
  onExpand: () => void
  onClose: () => void
}

/** Wraps SketchSvg with the bounded-card <-> full-screen toggle (User Story 2, FR-007/FR-008). The
 * underlying SVG scales itself via `viewBox` (see SketchSvg.tsx), so there's no resize listener needed
 * here for FR-009 — the browser rescales it like any vector graphic.
 *
 * `expanded` is owned by DesignPage (not local state) so it can enforce the "full-screen sketch, chat,
 * and menu are mutually exclusive overlays" rule from spec.md's Edge Cases. */
function SketchCard({ rooms, expanded, onExpand, onClose }: SketchCardProps) {
  const hasSketch = rooms.length > 0

  useEffect(() => {
    if (!expanded) return

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [expanded, onClose])

  return (
    <>
      <div
        className={hasSketch ? 'sketch-card' : 'sketch-card sketch-card--empty'}
        onClick={() => hasSketch && onExpand()}
        role={hasSketch ? 'button' : undefined}
        tabIndex={hasSketch ? 0 : undefined}
        aria-label={hasSketch ? 'הצג את הסקיצה במסך מלא' : undefined}
        onKeyDown={(event) => {
          if (hasSketch && (event.key === 'Enter' || event.key === ' ')) {
            event.preventDefault()
            onExpand()
          }
        }}
      >
        {hasSketch ? (
          <SketchSvg rooms={rooms} />
        ) : (
          <p className="sketch-card__empty">הסקיצה עדיין לא זמינה עבור הפרויקט הזה</p>
        )}
      </div>

      {expanded && hasSketch && (
        <div className="sketch-card__fullscreen" role="dialog" aria-modal="true" aria-label="הסקיצה במסך מלא">
          <button
            type="button"
            className="sketch-card__close"
            onClick={onClose}
            aria-label="סגור תצוגת מסך מלא"
          >
            ✕
          </button>
          <div className="sketch-card__fullscreen-content">
            <SketchSvg rooms={rooms} />
          </div>
        </div>
      )}
    </>
  )
}

export default SketchCard
