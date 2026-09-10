import type { DemoProgress } from '../api'
import './LoadingScreen.css'

interface LoadingScreenProps {
  /** When set, the build animation freezes and this message is shown instead (FR-004) — the loading
   * state never silently navigates to a broken/empty Design page. */
  error?: string | null
  /** The stage generation is actually in, streamed from the backend. Absent while the pipeline
   * reports nothing measurable (the parse step, or an older backend without the stream) — and then
   * an indeterminate bar is shown instead of a percentage, because a number invented from elapsed
   * time would be a progress indicator that indicates nothing. */
  progress?: DemoProgress | null
  /** Caption shown while `progress` is absent (no streamed stage to report yet, or none applies to
   * this step at all — e.g. the footprint-options fetch, which has no pipeline stages of its own).
   * Ignored once `progress` arrives, since `progress.label` then takes over. */
  caption?: string
}

/** Full-screen "house being built" loading state shown while the parse+design pipeline
 * (App.tsx's runPipeline) is in flight. The house animation loops indefinitely — its duration has no
 * relation to how long the pipeline takes (FR-002); the percentage beneath it does. */
function LoadingScreen({ error = null, progress = null, caption = 'בונים את הבית שלך...' }: LoadingScreenProps) {
  const percent = progress ? Math.max(0, Math.min(100, Math.round(progress.percent))) : null

  return (
    <div className="loading-screen" role="status" aria-live="polite">
      <svg
        className="loading-screen__house"
        viewBox="0 0 200 180"
        style={error ? { animationPlayState: 'paused' } : undefined}
      >
        <line x1="10" y1="160" x2="190" y2="160" className="loading-screen__ground" />

        <rect
          className="loading-screen__part loading-screen__part--foundation"
          x="40"
          y="150"
          width="120"
          height="12"
          rx="2"
          fill="#a67c52"
          style={error ? { animation: 'none', transform: 'scaleY(1)', opacity: 1 } : undefined}
        />

        <rect
          className="loading-screen__part loading-screen__part--walls"
          x="50"
          y="90"
          width="100"
          height="60"
          fill="#f2d9b1"
          stroke="#c9a876"
          strokeWidth="2"
          style={error ? { animation: 'none', transform: 'scaleY(1)', opacity: 1 } : undefined}
        />

        <polygon
          className="loading-screen__part loading-screen__part--roof"
          points="40,90 100,45 160,90"
          fill="#b1503f"
          style={error ? { animation: 'none', transform: 'scaleY(1)', opacity: 1 } : undefined}
        />

        <rect
          className="loading-screen__part loading-screen__part--door"
          x="92"
          y="120"
          width="18"
          height="30"
          rx="2"
          fill="#6b4226"
          style={error ? { animation: 'none', opacity: 1 } : undefined}
        />

        <rect
          className="loading-screen__part loading-screen__part--window"
          x="62"
          y="105"
          width="16"
          height="16"
          fill="#bfe3f5"
          stroke="#8fbcd4"
          style={error ? { animation: 'none', opacity: 1 } : undefined}
        />

        <rect
          className="loading-screen__part loading-screen__part--window-2"
          x="122"
          y="105"
          width="16"
          height="16"
          fill="#bfe3f5"
          stroke="#8fbcd4"
          style={error ? { animation: 'none', opacity: 1 } : undefined}
        />
      </svg>

      {error ? (
        <div className="loading-screen__error">
          <p>{error}</p>
          <p className="loading-screen__error-hint">רענן/י את הדף כדי לנסות שוב</p>
        </div>
      ) : (
        <div className="loading-screen__status">
          <p className="loading-screen__caption">
            {progress ? progress.label : caption}
          </p>
          {percent !== null && progress ? (
            <div
              className="loading-screen__progress"
              role="progressbar"
              aria-valuenow={percent}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="התקדמות יצירת התוכנית"
            >
              <div className="loading-screen__bar">
                <div className="loading-screen__bar-fill" style={{ width: `${percent}%` }} />
              </div>
              <div className="loading-screen__readout">
                {/* dir=ltr on the number itself: a bare percentage inside RTL text otherwise
                    renders as %72 instead of 72%. */}
                <span className="loading-screen__percent" dir="ltr">
                  {percent}%
                </span>
                <span className="loading-screen__steps" dir="ltr">
                  {progress.step}/{progress.total}
                </span>
              </div>
            </div>
          ) : (
            /* No stage reported yet, so no real percent exists to show — an indeterminate sweep
               signals "still working" without inventing a number (see the `progress` prop doc). */
            <div className="loading-screen__progress" role="progressbar" aria-label="בתהליך">
              <div className="loading-screen__bar">
                <div className="loading-screen__bar-fill loading-screen__bar-fill--indeterminate" />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default LoadingScreen
