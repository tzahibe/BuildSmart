import { useState } from 'react'
import { ProjectUpdateError, updateProject } from '../api'
import type { Project, ProjectUpdateDiff, TaggedValue } from '../types'
import './SettingsPage.css'

interface SettingsPageProps {
  project: Project
  onBack: () => void
  // Always the FULL Project returned by the backend — SettingsPage never guesses at the result of its
  // own update locally; see api.ts's `updateProject` docstring on avoiding a second source of truth.
  onUpdated: (project: Project) => void
}

interface IntFieldState {
  unknown: boolean
  value: string
}

interface BoolFieldState {
  unknown: boolean
  value: boolean
}

function intFieldFromTagged(tagged: TaggedValue<number> | null): IntFieldState {
  if (tagged === null || tagged.source === 'unknown' || tagged.value === null) {
    return { unknown: true, value: '' }
  }
  return { unknown: false, value: String(tagged.value) }
}

function boolFieldFromTagged(tagged: TaggedValue<boolean> | null): BoolFieldState {
  if (tagged === null || tagged.source === 'unknown' || tagged.value === null) {
    return { unknown: true, value: false }
  }
  return { unknown: false, value: tagged.value }
}

function intFieldToDiffValue(state: IntFieldState): TaggedValue<number> {
  if (state.unknown) return { value: null, source: 'unknown' }
  return { value: Number(state.value), source: 'requested' }
}

function boolFieldToDiffValue(state: BoolFieldState): TaggedValue<boolean> {
  if (state.unknown) return { value: null, source: 'unknown' }
  return { value: state.value, source: 'requested' }
}

/** Minimal Settings UI (this milestone's "Project State foundation") — edits the existing authoritative
 * requirement fields plus preferences, entirely through the single shared PATCH /projects/{id}
 * operation (see api.ts's `updateProject`). No conversational editing here — that's future work, and
 * when it lands, it will submit the exact same diff shape after an explicit user confirmation in chat,
 * never a chat-specific write path. After a successful update, the ENTIRE returned Project replaces the
 * caller's — this component never merges its own draft state into what's shown elsewhere. */
function SettingsPage({ project, onBack, onUpdated }: SettingsPageProps) {
  const [floors, setFloors] = useState<IntFieldState>(intFieldFromTagged(project.floors))
  const [bedrooms, setBedrooms] = useState<IntFieldState>(intFieldFromTagged(project.bedrooms))
  const [safeRoom, setSafeRoom] = useState<BoolFieldState>(boolFieldFromTagged(project.safe_room))
  const [parkingSpaces, setParkingSpaces] = useState<IntFieldState>(intFieldFromTagged(project.parking_spaces))
  const [newPreferenceText, setNewPreferenceText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submitDiff(diff: ProjectUpdateDiff) {
    setSubmitting(true)
    setError(null)
    try {
      const updated = await updateProject(project.project_id, { source: 'SETTINGS', diff })
      onUpdated(updated)
    } catch (err) {
      setError(err instanceof ProjectUpdateError ? err.message : 'לא ניתן היה לעדכן את הפרויקט')
    } finally {
      setSubmitting(false)
    }
  }

  function handleSubmit() {
    void submitDiff({
      floors: intFieldToDiffValue(floors),
      bedrooms: intFieldToDiffValue(bedrooms),
      safe_room: boolFieldToDiffValue(safeRoom),
      parking_spaces: intFieldToDiffValue(parkingSpaces),
    })
  }

  function handleAddPreference() {
    const text = newPreferenceText.trim()
    if (!text) return
    void submitDiff({ add_preferences: [{ kind: 'OTHER', original_text: text }] }).then(() => setNewPreferenceText(''))
  }

  function handleRemovePreference(preferenceId: string) {
    void submitDiff({ remove_preference_ids: [preferenceId] })
  }

  return (
    <div className="settings-page" dir="rtl">
      <div className="settings-page__header">
        <button type="button" className="settings-page__back" onClick={onBack} aria-label="חזרה לסקיצה">
          →
        </button>
        <h1>הגדרות פרויקט</h1>
      </div>

      <section className="settings-page__section">
        <h2>דרישות</h2>

        <div className="settings-page__field">
          <label>מספר קומות</label>
          <div className="settings-page__field-controls">
            <input
              type="number"
              min={1}
              disabled={floors.unknown}
              value={floors.value}
              onChange={(event) => setFloors({ ...floors, value: event.target.value })}
            />
            <label className="settings-page__unknown-toggle">
              <input
                type="checkbox"
                checked={floors.unknown}
                onChange={(event) => setFloors({ unknown: event.target.checked, value: '' })}
              />
              לא ידוע
            </label>
          </div>
        </div>

        <div className="settings-page__field">
          <label>מספר חדרי שינה</label>
          <div className="settings-page__field-controls">
            <input
              type="number"
              min={0}
              disabled={bedrooms.unknown}
              value={bedrooms.value}
              onChange={(event) => setBedrooms({ ...bedrooms, value: event.target.value })}
            />
            <label className="settings-page__unknown-toggle">
              <input
                type="checkbox"
                checked={bedrooms.unknown}
                onChange={(event) => setBedrooms({ unknown: event.target.checked, value: '' })}
              />
              לא ידוע
            </label>
          </div>
        </div>

        <div className="settings-page__field">
          <label>ממ"ד</label>
          <div className="settings-page__field-controls">
            <select
              disabled={safeRoom.unknown}
              value={safeRoom.value ? 'yes' : 'no'}
              onChange={(event) => setSafeRoom({ ...safeRoom, value: event.target.value === 'yes' })}
            >
              <option value="yes">כן</option>
              <option value="no">לא</option>
            </select>
            <label className="settings-page__unknown-toggle">
              <input
                type="checkbox"
                checked={safeRoom.unknown}
                onChange={(event) => setSafeRoom({ unknown: event.target.checked, value: false })}
              />
              לא ידוע
            </label>
          </div>
        </div>

        <div className="settings-page__field">
          <label>מספר חניות</label>
          <div className="settings-page__field-controls">
            <input
              type="number"
              min={0}
              disabled={parkingSpaces.unknown}
              value={parkingSpaces.value}
              onChange={(event) => setParkingSpaces({ ...parkingSpaces, value: event.target.value })}
            />
            <label className="settings-page__unknown-toggle">
              <input
                type="checkbox"
                checked={parkingSpaces.unknown}
                onChange={(event) => setParkingSpaces({ unknown: event.target.checked, value: '' })}
              />
              לא ידוע
            </label>
          </div>
        </div>

        <button type="button" className="settings-page__save" onClick={handleSubmit} disabled={submitting}>
          {submitting ? 'שומר...' : 'שמור דרישות'}
        </button>
      </section>

      <section className="settings-page__section">
        <h2>העדפות</h2>

        {project.preferences.length === 0 ? (
          <p className="settings-page__empty">אין העדפות עדיין</p>
        ) : (
          <ul className="settings-page__preferences">
            {project.preferences.map((preference) => (
              <li key={preference.preference_id}>
                <span>{preference.original_text}</span>
                <button
                  type="button"
                  className="settings-page__remove-preference"
                  onClick={() => handleRemovePreference(preference.preference_id)}
                  disabled={submitting}
                  aria-label="הסר העדפה"
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="settings-page__add-preference">
          <textarea
            rows={2}
            placeholder="לדוגמה: אני מעדיף/ה מטבח פתוח לסלון"
            value={newPreferenceText}
            onChange={(event) => setNewPreferenceText(event.target.value)}
          />
          <button type="button" onClick={handleAddPreference} disabled={submitting || !newPreferenceText.trim()}>
            הוסף העדפה
          </button>
        </div>
      </section>

      {error && <p className="settings-page__error">{error}</p>}
    </div>
  )
}

export default SettingsPage
