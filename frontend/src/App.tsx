import { useEffect, useState, type FormEvent } from 'react'
import './App.css'
import { createProject, generateDesign, parseRequirements, PipelineStepError } from './api'
import DesignPage from './design/DesignPage'
import FootprintSelection from './design/FootprintSelection'
import type { BuildingFootprint } from './design/footprint'
import LoadingScreen from './design/LoadingScreen'
import type { FormState, Project, ValidationErrorDetail } from './types'

type View = 'form' | 'footprint' | 'loading' | 'design'

const initialForm: FormState = {
  city: '',
  street: '',
  plot_area_m2: '',
  built_area_m2: '',
  description: '',
}

function App() {
  const [form, setForm] = useState<FormState>(initialForm)
  const [cities, setCities] = useState<string[]>([])
  const [streets, setStreets] = useState<string[]>([])
  const [project, setProject] = useState<Project | null>(null)
  const [errors, setErrors] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [view, setView] = useState<View>('form')
  const [pipelineError, setPipelineError] = useState<string | null>(null)
  // The SELECTED BUILDING FOOTPRINT (FOOTPRINT SELECTION step) — a real, typed choice the user makes
  // explicitly, not just which card looks highlighted (see design/footprint.ts's module docstring).
  // `null` until a valid option is chosen; cleared whenever `built_area_m2` changes (see the input's
  // onChange below) so a stale selection made against a since-changed target area can never be
  // carried forward — FootprintSelection itself defensively re-checks this too (see its own
  // docstring), but App.tsx is the actual owner of this state and clears it at the source.
  const [footprint, setFootprint] = useState<BuildingFootprint | null>(null)

  useEffect(() => {
    let cancelled = false

    fetch('/localities')
      .then((response) => (response.ok ? (response.json() as Promise<string[]>) : []))
      .then((data) => {
        if (!cancelled) setCities(data)
      })
      .catch(() => {
        /* autocomplete is a convenience — a failed fetch just leaves the list empty */
      })

    return () => {
      cancelled = true
    }
  }, [])

  // Street suggestions only load once `city` is an exact match for a known
  // localities — this is what gates the street field open (see handleCityChange).
  useEffect(() => {
    let cancelled = false

    if (!cities.includes(form.city)) return

    fetch(`/localities/${encodeURIComponent(form.city)}/streets`)
      .then((response) => (response.ok ? (response.json() as Promise<string[]>) : []))
      .then((data) => {
        if (!cancelled) setStreets(data)
      })
      .catch(() => {
        /* street autocomplete is a convenience — a failed fetch just leaves it disabled */
      })

    return () => {
      cancelled = true
    }
  }, [form.city, cities])

  // Drives User Story 1's loading screen: runs the parse (Feature 02) + design-generation (Feature 03)
  // pipeline in sequence once a project has been created, then navigates to the Design page (FR-001-004).
  //
  // Depends on `project?.project_id` (a stable primitive), NOT the whole `project` object — the object
  // reference changes on every setProject call *inside* this effect, and depending on the object itself
  // would re-trigger the effect each time, cancelling the in-flight run before generateDesign could ever
  // complete (an infinite re-parse loop that never reaches setView('design')).
  useEffect(() => {
    if (view !== 'loading' || project === null) return
    const projectId = project.project_id
    let cancelled = false

    async function runPipeline() {
      try {
        const parsed = await parseRequirements(projectId)
        if (cancelled) return
        setProject(parsed)

        const designed = await generateDesign(projectId)
        if (cancelled) return
        setProject(designed)
        setView('design')
      } catch (error) {
        if (cancelled) return
        const message =
          error instanceof PipelineStepError ? error.message : 'אירעה שגיאה בלתי צפויה בהכנת התכנון'
        setPipelineError(message)
      }
    }

    void runPipeline()

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, project?.project_id])

  function handleCityChange(value: string) {
    // Changing the city invalidates any previously chosen street and its suggestions.
    setForm((prev) => ({ ...prev, city: value, street: '' }))
    setStreets([])
  }

  // Validates the project-requirements form and, once the target built area is known, moves to the
  // FOOTPRINT SELECTION step BEFORE any backend call — `createProject` itself only happens once a
  // footprint is actually confirmed (see `handleConfirmFootprint`). This is what makes "changing the
  // built area" simply a matter of coming back here: nothing has been persisted to the backend yet at
  // this point, so there is no project to update, only the form to re-validate.
  function handleContinueToFootprint(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setErrors([])

    if (cities.length > 0 && !cities.includes(form.city)) {
      setErrors(['יש לבחור עיר / רשות מקומית מתוך הרשימה המוצעת'])
      return
    }

    if (streets.length > 0 && !streets.includes(form.street)) {
      setErrors(['יש לבחור רחוב מתוך הרשימה המוצעת עבור העיר שנבחרה'])
      return
    }

    if (Number(form.built_area_m2) >= Number(form.plot_area_m2)) {
      setErrors(['שטח הבנייה חייב להיות קטן משטח המגרש'])
      return
    }

    setView('footprint')
  }

  // Only fires with a confirmed, valid `footprint` (the "continue" button in FootprintSelection is
  // disabled otherwise) — this is where the project is actually created, exactly as `handleSubmit`
  // used to do directly from the form. NOTE (backend gap, see the task report): `footprint` itself is
  // NOT sent anywhere here — there is no backend field/endpoint for it yet (createProject's payload
  // and Project model are unchanged); the backend still derives its own square footprint from
  // `built_area_m2` alone (see backend/app/design/pipeline.py's `_derive_footprint`). This keeps the
  // choice ready to wire through once that support exists, without fabricating support that doesn't.
  async function handleConfirmFootprint() {
    if (footprint === null) return
    setSubmitting(true)
    setErrors([])

    try {
      const response = await createProject({
        city: form.city,
        street: form.street,
        plot_area_m2: Number(form.plot_area_m2),
        built_area_m2: Number(form.built_area_m2),
        description: form.description,
      })

      if (response.status === 201) {
        const data = (await response.json()) as Project
        setProject(data)
        setForm(initialForm)
        setFootprint(null)
        setPipelineError(null)
        setView('loading')
      } else if (response.status === 422) {
        const data = (await response.json()) as { detail?: ValidationErrorDetail[] }
        const messages = (data.detail ?? []).map((detail) => {
          const field = detail.loc.at(-1)
          const message = detail.msg.replace(/^Value error,\s*/, '')
          // A cross-field check (e.g. street vs. city) has no single field in `loc` —
          // FastAPI reports it as just "body", which isn't worth showing to the user.
          return field && field !== 'body' ? `${field}: ${message}` : message
        })
        setErrors(messages.length > 0 ? messages : ['הבקשה אינה תקינה'])
        setView('form')
      } else {
        setErrors(['אירעה שגיאה בלתי צפויה, נסה/י שוב'])
        setView('form')
      }
    } catch {
      setErrors(['לא ניתן להתחבר לשרת'])
      setView('form')
    } finally {
      setSubmitting(false)
    }
  }

  if (view === 'loading') {
    return <LoadingScreen error={pipelineError} />
  }

  if (view === 'design' && project) {
    return <DesignPage project={project} onProjectUpdated={setProject} />
  }

  if (view === 'footprint') {
    return (
      <section id="center" dir="rtl">
        <FootprintSelection
          targetAreaM2={Number(form.built_area_m2)}
          value={footprint}
          onChange={setFootprint}
          onConfirm={handleConfirmFootprint}
          onBack={() => setView('form')}
          submitting={submitting}
        />

        {errors.length > 0 && (
          <div className="form-errors">
            <p>לא ניתן היה ליצור את הפרויקט:</p>
            <ul>
              {errors.map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
          </div>
        )}
      </section>
    )
  }

  const streetFieldEnabled = streets.length > 0

  return (
    <section id="center" dir="rtl">
      <header className="page-header">
        <span className="eyebrow">BuildSmart</span>
        <h1>נתחיל לתכנן את הבית שלך</h1>
        <p>פתיחת פרויקט חדש — הזן/י את פרטי הבקשה הבסיסיים</p>
      </header>

      <form className="project-form" onSubmit={handleContinueToFootprint}>
        <label>
          עיר / רשות מקומית
          <input
            type="text"
            required
            list="cities-datalist"
            autoComplete="off"
            value={form.city}
            onChange={(event) => handleCityChange(event.target.value)}
          />
          <datalist id="cities-datalist">
            {cities.map((city) => (
              <option key={city} value={city} />
            ))}
          </datalist>
        </label>

        <label>
          רחוב ומספר
          <input
            type="text"
            required
            disabled={!streetFieldEnabled}
            list="streets-datalist"
            autoComplete="off"
            placeholder={streetFieldEnabled ? '' : 'יש לבחור עיר תחילה'}
            value={form.street}
            onChange={(event) => setForm({ ...form, street: event.target.value })}
          />
          <datalist id="streets-datalist">
            {streets.map((street) => (
              <option key={street} value={street} />
            ))}
          </datalist>
        </label>

        <div className="field-row">
          <label>
            שטח מגרש (מ"ר)
            <input
              type="number"
              min="0.01"
              step="any"
              required
              value={form.plot_area_m2}
              onChange={(event) => setForm({ ...form, plot_area_m2: event.target.value })}
            />
          </label>

          <label>
            שטח הבנייה (מ"ר)
            <input
              type="number"
              min="0.01"
              step="any"
              required
              value={form.built_area_m2}
              onChange={(event) => {
                setForm({ ...form, built_area_m2: event.target.value })
                // TARGET BUILT AREA changed -> any previously selected footprint was computed for a
                // now-stale area and must not be carried forward (see FootprintSelection's own
                // defensive re-check for the same rule, kept independently for the same reason).
                setFootprint(null)
              }}
            />
          </label>
        </div>

        <label>
          תיאור הבית הרצוי
          <textarea
            required
            rows={4}
            value={form.description}
            onChange={(event) => setForm({ ...form, description: event.target.value })}
          />
        </label>

        <button type="submit" className="submit-button">
          המשך לבחירת צורת המבנה
        </button>
      </form>

      {errors.length > 0 && (
        <div className="form-errors">
          <p>לא ניתן היה ליצור את הפרויקט:</p>
          <ul>
            {errors.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

export default App
