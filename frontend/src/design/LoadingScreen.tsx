import './LoadingScreen.css'

interface LoadingScreenProps {
  /** When set, the build animation freezes and this message is shown instead (FR-004) — the loading
   * state never silently navigates to a broken/empty Design page. */
  error?: string | null
}

/** Full-screen "house being built" loading state shown while the parse+design pipeline
 * (App.tsx's runPipeline) is in flight. Loops indefinitely — its duration has no relation to how long
 * the pipeline actually takes (FR-002). */
function LoadingScreen({ error = null }: LoadingScreenProps) {
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
        <p className="loading-screen__caption">בונים את הבית שלך...</p>
      )}
    </div>
  )
}

export default LoadingScreen
