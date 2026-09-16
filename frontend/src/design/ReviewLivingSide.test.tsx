import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import ReviewPage from './ReviewPage'
import type { RequirementsReview } from './demoDesign'

const field = (value: unknown, source = 'requested') => ({ value, source }) as never

function review(publicOpenSide?: { value: unknown; source: string }): RequirementsReview {
  return {
    limits: { bedrooms_min: 2, bedrooms_max: 5, wet_rooms_min: 1, wet_rooms_max: 3, parking_max: 2, floors: 1 },
    bedrooms: field(3),
    safe_room: field(true),
    wet_rooms: field(2),
    open_plan: field(true),
    parking_spaces: field(1),
    floors: field(1),
    ...(publicOpenSide ? { public_open_side: publicOpenSide } : {}),
    built_area_m2: 200,
    footprint_width_m: null,
    footprint_depth_m: null,
    description: 'בית',
    unsupported_requests: [],
    corridor_width: null,
    room_relationships: [],
    planned_rooms: [],
    site: null,
  } as unknown as RequirementsReview
}

/** Which side the living rooms face is a PREFERENCE the person states here — the brief is not
 * parsed for it — and it is sent back with the other corrections so the engine can read it. */
describe('ReviewPage living side', () => {
  it('shows the stored preference with where it came from', () => {
    render(<ReviewPage review={review({ value: 'garden', source: 'requested' })} onConfirm={() => {}} onBack={() => {}} />)
    const select = screen.getByRole('combobox', { name: 'הסלון פונה' }) as HTMLSelectElement
    expect(select.value).toBe('garden')
    expect(select.closest('.review-row')).toHaveTextContent('ביקשת')
  })

  it('reads a backend without the field, or a value it does not know, as the engine deciding', () => {
    const { unmount } = render(<ReviewPage review={review()} onConfirm={() => {}} onBack={() => {}} />)
    expect((screen.getByRole('combobox', { name: 'הסלון פונה' }) as HTMLSelectElement).value).toBe('engine')
    unmount()
    render(<ReviewPage review={review({ value: 'courtyard', source: 'requested' })} onConfirm={() => {}} onBack={() => {}} />)
    expect((screen.getByRole('combobox', { name: 'הסלון פונה' }) as HTMLSelectElement).value).toBe('engine')
  })

  it('sends the chosen side with the other corrections', () => {
    const onConfirm = vi.fn()
    render(<ReviewPage review={review({ value: 'engine', source: 'inferred' })} onConfirm={onConfirm} onBack={() => {}} />)
    fireEvent.change(screen.getByRole('combobox', { name: 'הסלון פונה' }), { target: { value: 'street' } })
    fireEvent.click(screen.getByRole('button', { name: /יצירת תוכנית/ }))
    expect(onConfirm).toHaveBeenCalledWith(expect.objectContaining({ public_open_side: 'street' }))
  })
})
