import { useState } from 'react'
import type { Project } from '../types'
import ChatPanel from './ChatPanel'
import Menu from './Menu'
import SketchCard from './SketchCard'
import TechnicalDetailsPage from './TechnicalDetailsPage'
import './DesignPage.css'

interface DesignPageProps {
  project: Project
}

type Overlay = 'none' | 'sketch' | 'chat' | 'menu' | 'details'

/** Decorative house-and-garden backdrop — static, non-interactive (spec.md's Assumptions). Original
 * CSS/SVG shapes, no image asset (research.md §6). */
function GardenBackdrop() {
  return (
    <svg
      className="design-page__backdrop"
      viewBox="0 0 400 300"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
    >
      <circle className="design-page__sun" cx="340" cy="50" r="28" />
      <ellipse className="design-page__cloud" cx="80" cy="60" rx="34" ry="14" />
      <ellipse className="design-page__cloud" cx="150" cy="40" rx="24" ry="10" />
      <circle className="design-page__bush" cx="30" cy="270" r="22" />
      <circle className="design-page__bush" cx="60" cy="280" r="16" />
      <circle className="design-page__bush" cx="370" cy="275" r="20" />
    </svg>
  )
}

/** Design page: the generated sketch inside a bounded card over a decorative garden backdrop
 * (FR-005/FR-006), expandable to full screen with an X to close (FR-007/FR-008, via SketchCard), a
 * chat panel to talk to the assistant (FR-010-013), and a menu leading to Technical Details
 * (FR-014-016). `activeOverlay` keeps the full-screen sketch, chat, menu, and details mutually
 * exclusive, per spec.md's Edge Cases. Technical Details is rendered as an overlay *on top of* this
 * page rather than replacing it, so ChatPanel (always mounted) keeps its loaded conversation when the
 * user navigates back (FR-016). */
function DesignPage({ project }: DesignPageProps) {
  const [activeOverlay, setActiveOverlay] = useState<Overlay>('none')

  return (
    <div className="design-page" dir="rtl">
      <GardenBackdrop />
      <div className="design-page__content">
        <header className="design-page__heading">
          <h1>הסקיצה של הבית שלך</h1>
          <p>
            {project.city}, {project.street}
          </p>
        </header>

        {project.design_notes && project.design_notes.length > 0 && (
          <div className="design-page__incomplete-notice" role="status">
            <span className="design-page__incomplete-notice-icon" aria-hidden="true">
              ⚠
            </span>
            <div>
              <p className="design-page__incomplete-notice-title">
                חלק מהמידע היה חסר — לא הומצאו נתונים במקומו
              </p>
              <ul>
                {project.design_notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </div>
          </div>
        )}

        <SketchCard
          rooms={project.rooms ?? []}
          expanded={activeOverlay === 'sketch'}
          onExpand={() => setActiveOverlay('sketch')}
          onClose={() => setActiveOverlay('none')}
        />
      </div>

      <Menu
        open={activeOverlay === 'menu'}
        onToggle={() => setActiveOverlay(activeOverlay === 'menu' ? 'none' : 'menu')}
        onOpenDetails={() => setActiveOverlay('details')}
      />

      <button
        type="button"
        className="design-page__chat-toggle"
        onClick={() => setActiveOverlay('chat')}
        aria-label="פתח שיחה עם העוזר"
      >
        💬
      </button>

      <ChatPanel
        projectId={project.project_id}
        open={activeOverlay === 'chat'}
        onClose={() => setActiveOverlay('none')}
      />

      {activeOverlay === 'details' && (
        <TechnicalDetailsPage project={project} onBack={() => setActiveOverlay('none')} />
      )}
    </div>
  )
}

export default DesignPage
