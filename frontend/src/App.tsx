import { useEffect, useState, type FormEvent } from 'react'
import './App.css'

interface Project {
  project_id: string
  city: string
  street: string
  plot_area_m2: number
  description: string
  status: string
  created_at: string
  updated_at: string
}

interface FormState {
  city: string
  street: string
  plot_area_m2: string
  description: string
}

interface ValidationErrorDetail {
  loc: (string | number)[]
  msg: string
}

const initialForm: FormState = { city: '', street: '', plot_area_m2: '', description: '' }

function App() {
  const [form, setForm] = useState<FormState>(initialForm)
  const [cities, setCities] = useState<string[]>([])
  const [streets, setStreets] = useState<string[]>([])
  const [project, setProject] = useState<Project | null>(null)
  const [errors, setErrors] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)

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
  // locality — this is what gates the street field open (see handleCityChange).
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

  function handleCityChange(value: string) {
    // Changing the city invalidates any previously chosen street and its suggestions.
    setForm((prev) => ({ ...prev, city: value, street: '' }))
    setStreets([])
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setErrors([])
    setProject(null)

    if (cities.length > 0 && !cities.includes(form.city)) {
      setErrors(['יש לבחור עיר / רשות מקומית מתוך הרשימה המוצעת'])
      setSubmitting(false)
      return
    }

    if (streets.length > 0 && !streets.includes(form.street)) {
      setErrors(['יש לבחור רחוב מתוך הרשימה המוצעת עבור העיר שנבחרה'])
      setSubmitting(false)
      return
    }

    try {
      const response = await fetch('/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          city: form.city,
          street: form.street,
          plot_area_m2: Number(form.plot_area_m2),
          description: form.description,
        }),
      })

      if (response.status === 201) {
        const data = (await response.json()) as Project
        setProject(data)
        setForm(initialForm)
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

  const streetFieldEnabled = streets.length > 0

  return (
    <section id="center" dir="rtl">
      <h1>AI Home Planner</h1>
      <p>פתיחת פרויקט חדש — הזן/י את פרטי הבקשה הבסיסיים</p>

      <form className="project-form" onSubmit={handleSubmit}>
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
          תיאור הבית הרצוי
          <textarea
            required
            rows={4}
            value={form.description}
            onChange={(event) => setForm({ ...form, description: event.target.value })}
          />
        </label>

        <button type="submit" className="counter" disabled={submitting}>
          {submitting ? 'שולח...' : 'צור פרויקט'}
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

      {project && (
        <div className="project-result">
          <p>הפרויקט נוצר בהצלחה</p>
          <dl>
            <dt>מזהה פרויקט</dt>
            <dd>{project.project_id}</dd>
            <dt>עיר</dt>
            <dd>{project.city}</dd>
            <dt>רחוב</dt>
            <dd>{project.street}</dd>
            <dt>סטטוס</dt>
            <dd>{project.status}</dd>
          </dl>
        </div>
      )}
    </section>
  )
}

export default App
