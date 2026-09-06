import { useEffect, useState } from 'react'
import { applySpatialEdit, SpatialEditError } from '../api'
import type { Project } from '../types'
import { roomLabel } from './roomLabel'
import './SpatialEditControls.css'
import { mergeGeometricDesignIntoProject, type Direction } from './spatialEdit'

interface SpatialEditControlsProps {
  project: Project
  // Same contract as SettingsPage's `onUpdated`/ChatPanel's `onProjectUpdated` — always the FULL
  // Project the caller should now treat as current; this component never merges partial state itself
  // (see spatialEdit.ts's `mergeGeometricDesignIntoProject`, the one place that reshapes a spatial-edit
  // response into this shape).
  onProjectUpdated: (project: Project) => void
}

const DIRECTIONS: { value: Direction; label: string; testId: string }[] = [
  { value: 'NORTH', label: '↑ צפון', testId: 'spatial-edit-direction-north' },
  { value: 'SOUTH', label: '↓ דרום', testId: 'spatial-edit-direction-south' },
  { value: 'EAST', label: '→ מזרח', testId: 'spatial-edit-direction-east' },
  { value: 'WEST', label: '← מערב', testId: 'spatial-edit-direction-west' },
]

/** Minimal real control for exercising `POST /projects/{id}/design/spatial-edit` (the Spatial V1
 * MOVE_ROOM edit) through the actual UI/API path a user would use — a room picker, a distance input,
 * and one button per `Direction`. This component sends exactly what the backend asks for
 * (`room_id`/`direction`/`distance_m`) and renders back whatever `GeometricDesign` it returns; it
 * contains NO direction-to-coordinate mapping of its own (no `if (direction === 'WEST') x -= 1`
 * anywhere here or anywhere else in the frontend) — the backend is the sole authority on whether and
 * how a room moves. A rejected edit only ever sets a local error message; `onProjectUpdated` is never
 * called for it, so the caller's `Project` (and therefore the rendered floor plan) is provably
 * untouched. */
function SpatialEditControls({ project, onProjectUpdated }: SpatialEditControlsProps) {
  const rooms = project.geometric_design?.rooms ?? []
  const [selectedRoomId, setSelectedRoomId] = useState(rooms[0]?.id ?? '')
  const [distance, setDistance] = useState('1')
  const [pending, setPending] = useState<Direction | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!rooms.some((room) => room.id === selectedRoomId)) {
      setSelectedRoomId(rooms[0]?.id ?? '')
    }
    // Only re-run when the set of available room ids actually changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rooms.map((room) => room.id).join(',')])

  if (project.geometric_design === null || rooms.length === 0) return null

  async function handleMove(direction: Direction) {
    if (!selectedRoomId) return
    setPending(direction)
    setError(null)
    try {
      const distanceValue = Number(distance)
      const updatedDesign = await applySpatialEdit(project.project_id, {
        room_id: selectedRoomId,
        direction,
        distance_m: Number.isFinite(distanceValue) && distanceValue > 0 ? distanceValue : undefined,
      })
      onProjectUpdated(mergeGeometricDesignIntoProject(project, updatedDesign))
    } catch (err) {
      setError(err instanceof SpatialEditError ? err.message : 'לא ניתן היה להזיז את החדר')
    } finally {
      setPending(null)
    }
  }

  return (
    <div className="spatial-edit-controls" dir="rtl">
      <div className="spatial-edit-controls__row">
        <label htmlFor="spatial-edit-room">חדר</label>
        <select
          id="spatial-edit-room"
          data-testid="spatial-edit-room-select"
          value={selectedRoomId}
          onChange={(event) => setSelectedRoomId(event.target.value)}
        >
          {rooms.map((room) => {
            const sameType = rooms.filter((candidate) => candidate.type === room.type)
            const indexAmongSameType = sameType.findIndex((candidate) => candidate.id === room.id)
            return (
              <option key={room.id} value={room.id}>
                {roomLabel(room.type, indexAmongSameType, sameType.length)} ({room.id})
              </option>
            )
          })}
        </select>

        <label htmlFor="spatial-edit-distance">מרחק (מ&apos;)</label>
        <input
          id="spatial-edit-distance"
          data-testid="spatial-edit-distance"
          type="number"
          min={0.1}
          step={0.1}
          value={distance}
          onChange={(event) => setDistance(event.target.value)}
        />
      </div>

      <div className="spatial-edit-controls__row">
        {DIRECTIONS.map(({ value, label, testId }) => (
          <button
            key={value}
            type="button"
            data-testid={testId}
            onClick={() => void handleMove(value)}
            disabled={pending !== null}
          >
            {pending === value ? '...' : label}
          </button>
        ))}
      </div>

      {error && (
        <p className="spatial-edit-controls__error" role="alert" data-testid="spatial-edit-error">
          {error}
        </p>
      )}
    </div>
  )
}

export default SpatialEditControls
