import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import ReviewPage from './ReviewPage'
import type { RequirementsReview } from './demoDesign'

const field = (value: unknown) => ({ value, source: 'requested' }) as never

function reviewWith(limits: RequirementsReview['limits'], bedrooms: number): RequirementsReview {
  return {
    limits,
    bedrooms: field(bedrooms),
    safe_room: field(false),
    wet_rooms: field(2),
    open_plan: field(true),
    parking_spaces: field(1),
    floors: field(1),
    built_area_m2: 150,
    footprint_width_m: 13,
    footprint_depth_m: 11.5,
    description: 'בית',
    unsupported_requests: [],
    corridor_width: null,
    room_relationships: [],
    planned_rooms: [],
    site: null,
  } as unknown as RequirementsReview
}

const LIMITS = { bedrooms_min: 2, bedrooms_max: 5, wet_rooms_min: 1, wet_rooms_max: 3, parking_max: 2, floors: 1 }

/** The review screen is the LAST place an unsupported count can still be corrected cheaply.
 * These tests hold it there rather than letting generation refuse it after the loading screen. */
describe('ReviewPage scope limits', () => {
  it('bounds the bedroom input by what the backend says it can plan', () => {
    render(<ReviewPage review={reviewWith(LIMITS, 3)} onConfirm={() => {}} onBack={() => {}} />)

    const input = screen.getByLabelText('חדרי שינה')
    expect(input).toHaveAttribute('min', '2')
    expect(input).toHaveAttribute('max', '5')
  })

  it('refuses to generate a count generation would reject, and says why here', () => {
    const onConfirm = vi.fn()
    render(<ReviewPage review={reviewWith(LIMITS, 1)} onConfirm={onConfirm} onBack={() => {}} />)

    expect(screen.getByRole('alert')).toHaveTextContent(/2 עד 5 חדרי שינה/)
    const generate = screen.getByRole('button', { name: /יצירת תוכנית/ })
    expect(generate).toBeDisabled()
    fireEvent.click(generate)
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('generates normally for a count inside the envelope', () => {
    const onConfirm = vi.fn()
    render(<ReviewPage review={reviewWith(LIMITS, 4)} onConfirm={onConfirm} onBack={() => {}} />)

    expect(screen.queryByRole('alert')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /יצירת תוכנית/ }))
    expect(onConfirm).toHaveBeenCalledWith(expect.objectContaining({ bedrooms: 4 }))
  })

  it('falls back to its own bounds when an older backend sends no limits', () => {
    render(<ReviewPage review={reviewWith(undefined, 3)} onConfirm={() => {}} onBack={() => {}} />)

    expect(screen.getByLabelText('חדרי שינה')).toHaveAttribute('max', '6')
    expect(screen.queryByRole('alert')).toBeNull()
  })
})


/** The storey count is a requirement like the others and is shown with its provenance. Until the
 * engine plans a second level, a count above the backend's limit is refused HERE, where it can be
 * corrected — not after the loading screen. */
describe('ReviewPage storey count', () => {
  function reviewWithFloors(floors: number, source = 'requested'): RequirementsReview {
    const review = reviewWith(LIMITS, 3)
    return { ...review, floors: { value: floors, source } as never }
  }

  it('shows the storey count the parser read, with its provenance, bounded by the backend limit', () => {
    render(<ReviewPage review={reviewWithFloors(1, 'inferred')} onConfirm={() => {}} onBack={() => {}} />)
    const input = screen.getByLabelText('קומות')
    expect(input).toHaveValue(1)
    expect(input).toHaveAttribute('min', '1')
    expect(input).toHaveAttribute('max', '1')
    expect(screen.getByText('קומות').parentElement).toHaveTextContent('הנחנו')
  })

  it('refuses to generate a two-storey house while only one storey is supported, and says so here', () => {
    const onConfirm = vi.fn()
    render(<ReviewPage review={reviewWithFloors(2)} onConfirm={onConfirm} onBack={() => {}} />)

    expect(screen.getByRole('alert')).toHaveTextContent(/בקומה אחת בלבד/)
    const generate = screen.getByRole('button', { name: /יצירת תוכנית/ })
    expect(generate).toBeDisabled()
    fireEvent.click(generate)
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('sends the storey count with the other corrections', () => {
    const onConfirm = vi.fn()
    render(<ReviewPage review={reviewWithFloors(1)} onConfirm={onConfirm} onBack={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: /יצירת תוכנית/ }))
    expect(onConfirm).toHaveBeenCalledWith(expect.objectContaining({ floors: 1 }))
  })
})

