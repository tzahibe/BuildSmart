import { useEffect, useState, type FormEvent } from 'react'
import './App.css'
import {
  createProject,
  DemoPipelineError,
  fetchFootprintOptions,
  generateDemoDesignStreaming,
  generateDesign,
  getRequirementsReview,
  parseRequirements,
  PipelineStepError,
  reportFailure,
  updateRequirementsReview,
} from './api'
import type { DemoProgress } from './api'
import Autocomplete from './Autocomplete'
import DesignPage from './design/DesignPage'
import ReviewPage from './design/ReviewPage'
import DemoWorkspace from './design/DemoWorkspace'
import type { DemoPlanSet, RequirementsReview, ReviewEdit } from './design/demoDesign'
import FootprintSelection from './design/FootprintSelection'
import {
  toSelectedFootprintPayload,
  type BuildingFootprint,
  type FootprintOptionsResponse,
} from './design/footprint'
import LoadingScreen from './design/LoadingScreen'
import type { FormState, Project, ValidationErrorDetail } from './types'

type View = 'form' | 'loading' | 'review' | 'generating' | 'plan' | 'design'

const initialForm: FormState = {
  city: '',
  street: '',
  plot_width_m: '',
  plot_depth_m: '',
  street_facing_side: 'NORTH',
  // ZERO, matching the backend default (app/demo/site_geometry.py). Any non-zero default is a
  // planning determination this project has not made — and 5.5/3/4 consumed 68% of a 300 m² plot,
  // deciding what could be built from a number nobody verified.
  front_setback_m: '0',
  side_setback_m: '0',
  rear_setback_m: '0',
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
  // DEMO PATH state. The brief is parsed, REVIEWED and corrected, and only then generated through
  // the validated pipeline (POST /design/demo). Nothing here reuses the old solver route.
  const [review, setReview] = useState<RequirementsReview | null>(null)
  const [demoPlans, setDemoPlans] = useState<DemoPlanSet | null>(null)
  const [demoError, setDemoError] = useState<{ message: string; detail: string } | null>(null)
  const [demoProgress, setDemoProgress] = useState<DemoProgress | null>(null)
  // THE OUTLINE IS THE ENGINE'S TO CHOOSE (feature 006). It used to be a screen of its own between
  // this form and generation; measured over the production log, the person's choice planned in 30 %
  // of briefs while each of the engine's own four shapes planned in 35–45 %. So the form now creates
  // the project WITHOUT an outline and the engine plans the shapes that fit. The cards survive under
  // an "advanced" disclosure for a person with a real constraint (a permit tied to a rectangle, a
  // frontage to keep); an outline chosen there is authoritative — planned first, shown first.
  //
  // `footprint` is that advanced choice — a real, typed selection, not which card looks highlighted
  // (see design/footprint.ts). `null` means "the engine chooses". Cleared whenever the built area or
  // the setbacks change, so a stale selection made against a since-changed target can never be
  // carried forward, and whenever the disclosure is closed.
  const [footprint, setFootprint] = useState<BuildingFootprint | null>(null)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  // The buildable region and the outlines that fit it, computed by the BACKEND — fetched only when
  // the advanced disclosure is opened, never for the main flow.
  const [siteOptions, setSiteOptions] = useState<FootprintOptionsResponse | null>(null)
  const [siteOptionsError, setSiteOptionsError] = useState<string | null>(null)

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

        // DEMO PATH: stop after parsing and show the user what we understood. Generation only
        // happens once they confirm — the old "parse then immediately solve" jump is gone.
        const parsedReview = await getRequirementsReview(projectId)
        if (cancelled) return
        setReview(parsedReview)
        setView('review')
      } catch (error) {
        if (cancelled) return
        const message =
          error instanceof PipelineStepError || error instanceof DemoPipelineError
            ? error.message
            : 'אירעה שגיאה בלתי צפויה בהכנת התכנון'
        reportFailure(
          error instanceof DemoPipelineError ? error.code : 'PARSE_PIPELINE_FAILED',
          message, 'parse pipeline',
          error instanceof Error ? error.stack ?? error.message : String(error),
          { projectId })
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
    // A no-op re-selection of the SAME city (e.g. the user re-clicks/re-confirms a suggestion that
    // already matches the field's current value) must not wipe the streets already loaded for it —
    // the fetch effect below only re-fires when `form.city` actually CHANGES, so clearing `streets`
    // here unconditionally would leave the street field disabled with no way to recover, even though
    // nothing about the selected city changed. Only an actual city change invalidates the previously
    // chosen street and its suggestions.
    if (value === form.city) return
    setForm((prev) => ({ ...prev, city: value, street: '' }))
    setStreets([])
  }

  /** The site inputs the advanced outline options are computed from — the same ones the project is
   *  created with. Incomplete means there is nothing honest to offer yet. */
  function siteInputs() {
    const body = {
      plot_width_m: Number(form.plot_width_m),
      plot_depth_m: Number(form.plot_depth_m),
      street_facing_side: form.street_facing_side,
      built_area_m2: Number(form.built_area_m2),
      front_setback_m: Number(form.front_setback_m),
      side_setback_m: Number(form.side_setback_m),
      rear_setback_m: Number(form.rear_setback_m),
    }
    const complete = body.plot_width_m > 0 && body.plot_depth_m > 0 && body.built_area_m2 > 0
    return { body, complete }
  }

  // Opening the advanced disclosure is what fetches the outline options — the main flow never
  // pays for them. Closing it drops any outline chosen there: closed means "the engine chooses".
  function handleToggleAdvanced() {
    if (advancedOpen) {
      setAdvancedOpen(false)
      setFootprint(null)
      return
    }
    setAdvancedOpen(true)
    void loadSiteOptions()
  }

  async function loadSiteOptions() {
    const { body, complete } = siteInputs()
    setSiteOptions(null)
    setSiteOptionsError(null)
    if (!complete) {
      setSiteOptionsError('כדי לבחור מתאר ידנית יש להזין קודם את מידות המגרש ואת שטח הבנייה.')
      return
    }
    try {
      setSiteOptions(await fetchFootprintOptions(body))
    } catch (error) {
      reportFailure('FOOTPRINT_OPTIONS_FAILED', String(error), 'footprint options')
      setSiteOptionsError('לא ניתן היה לחשב את אפשרויות המתאר עבור המגרש')
    }
  }

  /** A site input changed: any advanced outline was computed for the old site and is dropped, and
   *  the options are refetched if the disclosure is open. */
  function siteChanged(next: FormState) {
    setForm(next)
    setFootprint(null)
    setSiteOptions(null)
  }

  // Validates the brief and CREATES THE PROJECT. There is no outline step in between any more: the
  // request carries `selected_footprint: null` unless the person chose one under "advanced", and the
  // engine plans the outlines that fit (backend/app/demo/service.py, feature 006).
  async function handleSubmitBrief(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setErrors([])

    // City/street stay free-text (Autocomplete just suggests) — the typed value can still be
    // anything, so this exact-match check against the real lists is still required here.
    if (cities.length > 0 && !cities.includes(form.city)) {
      setErrors(['יש לבחור עיר / רשות מקומית מתוך הרשימה המוצעת'])
      return
    }

    if (streets.length > 0 && !streets.includes(form.street)) {
      setErrors(['יש לבחור רחוב מתוך הרשימה המוצעת עבור העיר שנבחרה'])
      return
    }

    const buildableWidth = Number(form.plot_width_m) - 2 * Number(form.side_setback_m)
    const buildableDepth =
      Number(form.plot_depth_m) - Number(form.front_setback_m) - Number(form.rear_setback_m)
    if (!(buildableWidth > 0) || !(buildableDepth > 0)) {
      setErrors([
        'הנסיגות שהוזנו אינן משאירות שטח בנייה על המגרש. אפשר לעדכן אותן או את מידות המגרש.',
      ])
      return
    }
    // Checked HERE, before any backend call. The backend recomputes and enforces this
    // independently — this only stops the person waiting on a request whose first number was
    // impossible.
    const oneStoreyCapacity = buildableWidth * buildableDepth
    if (Number(form.built_area_m2) > oneStoreyCapacity) {
      setErrors([
        `שטח בנייה של ${Number(form.built_area_m2).toFixed(2)} מ"ר אינו נכנס בקומה אחת על מגרש ` +
          `${form.plot_width_m} × ${form.plot_depth_m} מ׳. אחרי הנסיגות נשאר ` +
          `${buildableWidth.toFixed(2)} × ${buildableDepth.toFixed(2)} מ׳ — קיבולת מתאר גאומטרית ` +
          `לקומה אחת של ${oneStoreyCapacity.toFixed(2)} מ"ר. אפשר להקטין את השטח המבוקש או לעדכן ` +
          `את הנחות הנסיגה כאן.`,
      ])
      return
    }

    setSubmitting(true)
    try {
      const response = await createProject({
        city: form.city,
        street: form.street,
        // Area is DERIVED from the dimensions, never entered separately — the two could otherwise
        // contradict each other and the backend would (correctly) refuse to guess which is right.
        plot_area_m2: Number((Number(form.plot_width_m) * Number(form.plot_depth_m)).toFixed(2)),
        plot_width_m: Number(form.plot_width_m),
        plot_depth_m: Number(form.plot_depth_m),
        street_facing_side: form.street_facing_side,
        setbacks: {
          front_m: Number(form.front_setback_m),
          side_m: Number(form.side_setback_m),
          rear_m: Number(form.rear_setback_m),
        },
        built_area_m2: Number(form.built_area_m2),
        description: form.description,
        // The advanced choice, sent verbatim via `toSelectedFootprintPayload` — never recomputed
        // here from raw form numbers. `null` is the main flow: the engine chooses.
        selected_footprint: footprint === null ? null : toSelectedFootprintPayload(footprint),
      })

      if (response.status === 201) {
        const data = (await response.json()) as Project
        setProject(data)
        // The form and any advanced outline are deliberately NOT cleared here. Creating the
        // project is not the end of the flow — REVIEW's "חזרה לתיאור" comes straight back to this
        // form, and wiping it on the way out meant the user returned to an empty form and had to
        // retype everything they had just entered.
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
      } else {
        setErrors(['אירעה שגיאה בלתי צפויה, נסה/י שוב'])
      }
    } catch {
      setErrors(['לא ניתן להתחבר לשרת'])
    } finally {
      setSubmitting(false)
    }
  }

  async function handleConfirmReview(edit: ReviewEdit) {
    if (project === null) return
    setDemoError(null)
    setDemoProgress(null)
    setView('generating')
    try {
      const updated = await updateRequirementsReview(project.project_id, edit)
      setReview(updated)
      // THE WET ROOMS ARE THE BACKEND'S CALL. The edit is stored either way; if what was stored
      // still leaves a bedroom without a bathroom, generation would refuse with the same words —
      // so stay on the review screen and show them there, where they can be answered (specs/007).
      if (updated.wet_room_problem) {
        setView('review')
        return
      }
      // The percentage on the loading screen comes from these callbacks — one per pipeline stage,
      // as the backend enters it. No stream means no percentage, not a made-up one.
      setDemoPlans(await generateDemoDesignStreaming(project.project_id, setDemoProgress))
      setView('plan')
    } catch (error) {
      // Product-level failure: an unsupported request or an unrealizable brief. The message is
      // shown as-is and the requirements are left exactly as the user set them — never silently
      // adjusted to something that would have worked.
      //
      // A SERVER THAT ISN'T THERE throws a bare TypeError from `fetch` itself ("Failed to fetch"),
      // arriving here indistinguishable from a real pipeline crash unless named separately — the
      // one case where the fix is "start the server", not "read the stack trace".
      const unreachable = error instanceof TypeError
      const failure =
        error instanceof DemoPipelineError
          ? { message: error.message, detail: error.detail }
          : unreachable
            ? { message: 'לא ניתן להתחבר לשרת. יש לוודא שהשרת פועל ולנסות שוב.', detail: '' }
            : { message: 'אירעה שגיאה בלתי צפויה ביצירת התוכנית.', detail: '' }
      // The moment somebody does not get a drawing. Recorded from the UI as well as the API,
      // because a network failure or a response the client could not use never reaches the server
      // log at all — and it ends the journey just the same.
      reportFailure(
        error instanceof DemoPipelineError ? error.code : unreachable ? 'SERVER_UNREACHABLE' : 'GENERATE_FAILED',
        failure.message, 'generate', failure.detail, { projectId: project.project_id })
      setDemoError(failure)
      setView('review')
    }
  }

  if (view === 'review' && review) {
    return (
      <>
        {demoError ? (
          <div className="demo-error" role="alert">
            <strong>{demoError.message}</strong>
            {demoError.detail ? <span className="demo-error-detail">{demoError.detail}</span> : null}
          </div>
        ) : null}
        <ReviewPage review={review} onConfirm={handleConfirmReview} onBack={() => setView('form')} />
      </>
    )
  }

  if (view === 'generating') {
    return <LoadingScreen progress={demoProgress} />
  }

  if (view === 'plan' && demoPlans) {
    return (
      <DemoWorkspace
        plans={demoPlans}
        onChangeRequirements={() => {
          setDemoError(null)
          setView('review')
        }}
      />
    )
  }

  if (view === 'loading') {
    return <LoadingScreen error={pipelineError} />
  }

  if (view === 'design' && project) {
    return <DesignPage project={project} onProjectUpdated={setProject} />
  }

  // The buildable rectangle, live. A subtraction, not an algorithm — the backend stays the
  // authority (it recomputes and enforces on the options call and again on create), but the person
  // should not have to submit a form to find out their first number cannot work.
  const capacity = (() => {
    const width = Number(form.plot_width_m) - 2 * Number(form.side_setback_m)
    const depth =
      Number(form.plot_depth_m) - Number(form.front_setback_m) - Number(form.rear_setback_m)
    if (!(width > 0) || !(depth > 0)) return null
    return { width, depth, area: width * depth }
  })()
  const overCapacity =
    capacity !== null && Number(form.built_area_m2) > 0 && Number(form.built_area_m2) > capacity.area

  const streetFieldEnabled = streets.length > 0

  return (
    <section id="center" dir="rtl">
      <header className="page-header">
        <span className="eyebrow">BuildSmart</span>
        <h1>נתחיל לתכנן את הבית שלך</h1>
        <p>פתיחת פרויקט חדש — הזן/י את פרטי הבקשה הבסיסיים</p>
      </header>

      <form className="project-form" onSubmit={handleSubmitBrief}>
        <label>
          עיר / רשות מקומית
          {/* Custom autocomplete (Autocomplete.tsx), not the native <input list="..."> + <datalist>
              this used to be — a datalist only SUGGESTS matching options while the user keeps typing
              free text, it never forces the value to actually become one of them. Several real city
              names in this dataset don't match how people naturally type them (e.g. the city is
              stored as "תל אביב - יפו", not "תל אביב") — a user typing the natural short form ended
              up with a value that looked chosen but matched nothing, silently leaving the street
              field disabled forever with no indication why. Typing still filters suggestions exactly
              as before; clicking (or arrowing to) one now always sets the exact matching value. */}
          <Autocomplete required value={form.city} onChange={handleCityChange} options={cities} />
        </label>

        <label>
          רחוב ומספר
          {/* Same fix as the city field above, and for the same reason — see that field's comment. */}
          <Autocomplete
            required
            disabled={!streetFieldEnabled}
            placeholder={streetFieldEnabled ? '' : 'יש לבחור עיר תחילה'}
            value={form.street}
            onChange={(value) => setForm({ ...form, street: value })}
            options={streets}
          />
        </label>

        {/* THE SITE, as dimensions rather than an area. An area cannot say whether a house fits:
            the same 400 m² is 20×20 (fits) or 25×16 (does not), and the setbacks are edge-relative
            so the frontage matters too. The area is derived from these and shown, not entered. */}
        <div className="form-row">
          <label>
            רוחב מגרש (מ')
            <input
              type="number" min="0.01" step="any" required
              value={form.plot_width_m}
              onChange={(event) => siteChanged({ ...form, plot_width_m: event.target.value })}
            />
          </label>
          <label>
            עומק מגרש (מ')
            <input
              type="number" min="0.01" step="any" required
              value={form.plot_depth_m}
              onChange={(event) => siteChanged({ ...form, plot_depth_m: event.target.value })}
            />
          </label>
        </div>

        {Number(form.plot_width_m) > 0 && Number(form.plot_depth_m) > 0 ? (
          <p className="form-derived">
            שטח מגרש: {(Number(form.plot_width_m) * Number(form.plot_depth_m)).toFixed(2)} מ&quot;ר
          </p>
        ) : null}

        <label>
          איזו חזית פונה לרחוב
          <select
            value={form.street_facing_side}
            onChange={(event) =>
              siteChanged({ ...form, street_facing_side: event.target.value as FormState['street_facing_side'] })
            }
          >
            <option value="NORTH">צפון</option>
            <option value="SOUTH">דרום</option>
            <option value="EAST">מזרח</option>
            <option value="WEST">מערב</option>
          </select>
        </label>

        {/* THE SETBACK ASSUMPTIONS, on the screen whose numbers they decide. They used to live only
            on the review screen — two steps later — while the capacity they produce was already
            being used here to accept or refuse a built area. The refusal even told people both
            levers were "on the previous screen" when only one of them was. */}
        <fieldset className="form-setbacks">
          <legend>הנחות נסיגה לדמו</legend>
          <div className="form-row">
            {([['front_setback_m', 'חזית'], ['rear_setback_m', 'אחורית'], ['side_setback_m', 'צדדים']] as const).map(
              ([key, label]) => (
                <label key={key}>
                  {label} (מ')
                  <input
                    type="number" min="0" step="0.1" required
                    value={form[key]}
                    onChange={(event) => siteChanged({ ...form, [key]: event.target.value })}
                  />
                </label>
              ),
            )}
          </div>
          <p className="form-note">הנחות תכנון לדמו — אינן מידע תכנוני או רגולטורי מאומת.</p>
        </fieldset>

        <label>
          שטח בנייה בקומה אחת (טביעת רגל) (מ&quot;ר)
          <input
            type="number"
            min="0.01"
            step="any"
            required
            aria-describedby="one-storey-capacity"
            value={form.built_area_m2}
            // TARGET BUILT AREA changed -> any advanced outline was computed for a now-stale area
            // and must not be carried forward (FootprintSelection re-checks this independently).
            onChange={(event) => siteChanged({ ...form, built_area_m2: event.target.value })}
          />
        </label>

        {/* The capacity, right under the number it constrains — OUTSIDE the label, so it does not
            become part of the field's accessible name. Refusing only on the server meant filling
            in the whole form to learn that the first number was impossible. */}
        {capacity !== null ? (
          <p
            id="one-storey-capacity"
            className={overCapacity ? 'form-capacity form-capacity--over' : 'form-capacity'}
          >
            {overCapacity ? '⚠ ' : ''}
            קיבולת מתאר גאומטרית לקומה אחת על המגרש הזה:{' '}
            <strong>{capacity.area.toFixed(2)} מ&quot;ר</strong>{' '}
            (<span className="dim">{capacity.width.toFixed(2)} × {capacity.depth.toFixed(2)}</span> מ׳)
            {overCapacity ? ' — השטח שהוזן גדול מכך ולא ייכנס בקומה אחת.' : ''}
          </p>
        ) : null}

        <label>
          תיאור הבית הרצוי
          <textarea
            required
            rows={4}
            value={form.description}
            onChange={(event) => setForm({ ...form, description: event.target.value })}
          />
        </label>

        {/* THE OUTLINE, ADVANCED. Closed by default: the engine plans the shapes that fit and shows
            the ones that work. Open it only to fix the rectangle yourself — the same cards the old
            screen offered, and a choice made here is authoritative. */}
        <section className="form-advanced" aria-label="מתאר הבניין">
          <p className="form-advanced__note">
            כברירת מחדל המערכת בוחרת את צורת הבניין בעצמה: היא בודקת כמה מתארים באותו שטח ומציגה
            את התוכניות שמתקבלות.
          </p>
          <button
            type="button"
            className="form-advanced__toggle"
            aria-expanded={advancedOpen}
            aria-controls="advanced-outline"
            onClick={handleToggleAdvanced}
          >
            {advancedOpen ? '▾' : '▸'} מתקדם — קביעת מתאר ידנית
          </button>
          {advancedOpen ? (
            <div id="advanced-outline" className="form-advanced__body">
              {siteOptionsError ? (
                <p className="form-advanced__error" role="alert">{siteOptionsError}</p>
              ) : siteOptions === null ? (
                <p className="form-advanced__loading" role="status">בודקים את אפשרויות המתאר עבור המגרש שלך...</p>
              ) : (
                <FootprintSelection
                  inline
                  site={siteOptions}
                  targetAreaM2={Number(form.built_area_m2)}
                  value={footprint}
                  onChange={setFootprint}
                />
              )}
            </div>
          ) : null}
        </section>

        <button type="submit" className="submit-button" disabled={submitting}>
          {submitting ? 'יוצר פרויקט...' : 'המשך ליצירת התכנון'}
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
