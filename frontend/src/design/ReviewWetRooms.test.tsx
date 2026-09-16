import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import ReviewPage from './ReviewPage'
import type { RequirementsReview, WetRoomKindNote } from './demoDesign'

const field = (value: unknown) => ({ value, source: 'requested' }) as never

function reviewWith(notes: WetRoomKindNote[], problem: string | null, wetRooms = notes.length): RequirementsReview {
  return {
    limits: { bedrooms_min: 1, bedrooms_max: 6, wet_rooms_min: 1, wet_rooms_max: 3, parking_max: 2, floors: 1 },
    bedrooms: field(2),
    safe_room: field(true),
    wet_rooms: field(wetRooms),
    open_plan: field(true),
    parking_spaces: field(0),
    floors: field(1),
    built_area_m2: 176,
    footprint_width_m: 15,
    footprint_depth_m: 11.73,
    description: 'בית',
    unsupported_requests: [],
    corridor_width: null,
    room_relationships: [],
    planned_rooms: [],
    site: null,
    wet_room_kinds: notes,
    wet_room_problem: problem,
  } as unknown as RequirementsReview
}

const ENSUITE: WetRoomKindNote = {
  index: 0, kind: 'ensuite', host: 'MASTER_BEDROOM', strength: 'required',
  source_text: 'חדר הורים עם שירותים', specified: true, label: 'חדר רחצה צמוד לחדר ההורים', can_be_flexible: false,
}
const GUEST_WC: WetRoomKindNote = {
  index: 1, kind: 'guest_wc', host: null, strength: 'required',
  source_text: 'שירותי אורחים', specified: true, label: 'שירותי אורחים', can_be_flexible: false,
}
const DEFAULT_SHARED: WetRoomKindNote = {
  index: 1, kind: 'shared_bathroom', host: null, strength: 'required',
  source_text: '', specified: false, label: 'לא צוין — ברירת מחדל: חדר רחצה משותף', can_be_flexible: true,
}
const PROBLEM = 'לפי מה שנאמר על חדרי הרחצה, לחדר שינה 1 אין חדר רחצה שאפשר להגיע אליו'

/** specs/007 decision B: what each wet room IS is shown and confirmable before Generate, and a
 * configuration the backend would refuse keeps Generate blocked until the person changes it. */
describe('ReviewPage wet rooms', () => {
  it('shows one row per wet room with the backend reading and its source', () => {
    render(<ReviewPage review={reviewWith([ENSUITE, GUEST_WC], null)} onConfirm={() => {}} onBack={() => {}} />)

    expect(screen.getByLabelText('סוג חדר רחצה 1')).toHaveValue('ensuite:MASTER_BEDROOM')
    expect(screen.getByLabelText('סוג חדר רחצה 2')).toHaveValue('guest_wc')
    expect(screen.getByText(/חדר הורים עם שירותים/)).toBeInTheDocument()
  })

  it('calls a default a default, and only a shared bathroom can be flexible', () => {
    render(<ReviewPage review={reviewWith([ENSUITE, DEFAULT_SHARED], null)} onConfirm={() => {}} onBack={() => {}} />)

    expect(screen.getByText(/לא צוין — ברירת מחדל/)).toBeInTheDocument()
    expect(screen.getByLabelText('סוג חדר רחצה 2')).toHaveValue('unspecified')
    expect(screen.getByLabelText('חדר רחצה 1 גמיש')).toBeDisabled()
    expect(screen.getByLabelText('חדר רחצה 2 גמיש')).toBeEnabled()
  })

  it('keeps Generate blocked while the backend says a bedroom has no bathroom, until something changes', () => {
    const onConfirm = vi.fn()
    render(<ReviewPage review={reviewWith([ENSUITE, GUEST_WC], PROBLEM)} onConfirm={onConfirm} onBack={() => {}} />)

    expect(screen.getByRole('alert')).toHaveTextContent(/חדר שינה 1/)
    const generate = screen.getByRole('button', { name: /יצירת תוכנית/ })
    expect(generate).toBeDisabled()

    // Answering the question — making the WC a shared bathroom — re-enables the button, and the
    // rows travel with the edit for the backend to judge.
    fireEvent.change(screen.getByLabelText('סוג חדר רחצה 2'), { target: { value: 'shared_bathroom' } })
    expect(generate).toBeEnabled()
    fireEvent.click(generate)
    expect(onConfirm).toHaveBeenCalledWith(expect.objectContaining({
      wet_rooms: 2,
      wet_room_kinds: [
        { kind: 'ensuite', host: 'MASTER_BEDROOM', strength: 'required' },
        { kind: 'shared_bathroom', host: null, strength: 'required' },
      ],
    }))
  })

  it('applies the proposed answer with one click and sends those rows', () => {
    const onConfirm = vi.fn()
    const review = {
      ...reviewWith([ENSUITE, GUEST_WC], PROBLEM),
      wet_room_proposal: {
        wet_rooms: 3,
        summary: 'להוסיף חדר רחצה משותף — חדרי הרחצה יהיו: 1. חדר רחצה צמוד לחדר ההורים; 2. שירותי אורחים; 3. חדר רחצה משותף',
        wet_room_kinds: [
          { kind: 'ensuite', host: 'MASTER_BEDROOM', strength: 'required' },
          { kind: 'guest_wc', host: null, strength: 'required' },
          { kind: 'shared_bathroom', host: null, strength: 'required' },
        ],
      },
    } as RequirementsReview
    render(<ReviewPage review={review} onConfirm={onConfirm} onBack={() => {}} />)

    const generate = screen.getByRole('button', { name: /יצירת תוכנית/ })
    expect(generate).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: /להוסיף חדר רחצה משותף/ }))
    expect(screen.getByLabelText('סוג חדר רחצה 3')).toHaveValue('shared_bathroom')
    expect(generate).toBeEnabled()
    fireEvent.click(generate)
    expect(onConfirm).toHaveBeenCalledWith(expect.objectContaining({
      wet_rooms: 3,
      wet_room_kinds: [
        { kind: 'ensuite', host: 'MASTER_BEDROOM', strength: 'required' },
        { kind: 'guest_wc', host: null, strength: 'required' },
        { kind: 'shared_bathroom', host: null, strength: 'required' },
      ],
    }))
  })

  it('marks a shared bathroom flexible and sends it so', () => {
    const onConfirm = vi.fn()
    render(<ReviewPage review={reviewWith([ENSUITE, DEFAULT_SHARED], null)} onConfirm={onConfirm} onBack={() => {}} />)

    fireEvent.change(screen.getByLabelText('סוג חדר רחצה 2'), { target: { value: 'shared_bathroom' } })
    fireEvent.click(screen.getByLabelText('חדר רחצה 2 גמיש'))
    fireEvent.click(screen.getByRole('button', { name: /יצירת תוכנית/ }))
    expect(onConfirm).toHaveBeenCalledWith(expect.objectContaining({
      wet_room_kinds: [
        { kind: 'ensuite', host: 'MASTER_BEDROOM', strength: 'required' },
        { kind: 'shared_bathroom', host: null, strength: 'flexible' },
      ],
    }))
  })

  it('adds an unstated row when the count goes up and drops the last when it goes down', () => {
    render(<ReviewPage review={reviewWith([ENSUITE, GUEST_WC], null)} onConfirm={() => {}} onBack={() => {}} />)

    fireEvent.change(screen.getByLabelText('חדרי רחצה'), { target: { value: '3' } })
    expect(screen.getByLabelText('סוג חדר רחצה 3')).toHaveValue('unspecified')
    fireEvent.change(screen.getByLabelText('חדרי רחצה'), { target: { value: '1' } })
    expect(screen.queryByLabelText('סוג חדר רחצה 2')).toBeNull()
  })

  it('renders an older backend that sends no rows as today', () => {
    render(<ReviewPage review={reviewWith([], null, 2)} onConfirm={() => {}} onBack={() => {}} />)

    expect(screen.getByLabelText('סוג חדר רחצה 1')).toHaveValue('unspecified')
    expect(screen.getByRole('button', { name: /יצירת תוכנית/ })).toBeEnabled()
  })
})
