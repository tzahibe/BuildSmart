import { fireEvent, render, screen, within } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import FootprintSelection from './FootprintSelection'
import { generateFootprintOptions, type BuildingFootprint } from './footprint'

/** A thin controlled-component harness — App.tsx owns `footprint` state the same way; these tests
 * exercise FootprintSelection exactly as it's actually used, not with a bare `onChange` spy that
 * would never let the component read back its own committed selection. */
function Harness({ targetAreaM2, onConfirm }: { targetAreaM2: number; onConfirm?: () => void }) {
  const [value, setValue] = useState<BuildingFootprint | null>(null)
  return (
    <FootprintSelection
      targetAreaM2={targetAreaM2}
      value={value}
      onChange={setValue}
      onConfirm={onConfirm ?? (() => {})}
      onBack={() => {}}
    />
  )
}

/** Exposes a live-editable target area WITHOUT clearing the selection itself (App.tsx clears it
 * directly too, but this harness deliberately does NOT, so these tests prove FootprintSelection's
 * OWN defensive re-check — not App.tsx's separate belt-and-suspenders clear — is what invalidates a
 * stale selection when the target area changes underneath it). */
function ReareaHarness() {
  const [area, setArea] = useState(120)
  const [value, setValue] = useState<BuildingFootprint | null>(null)
  return (
    <div>
      <button type="button" onClick={() => setArea(240)}>
        change-area
      </button>
      <FootprintSelection targetAreaM2={area} value={value} onChange={setValue} onConfirm={() => {}} onBack={() => {}} />
    </div>
  )
}

describe('FootprintSelection', () => {
  it('shows one card per preset option, each with distinct dimensions/area, once the target area is known', () => {
    render(<Harness targetAreaM2={120} />)
    const options = generateFootprintOptions(120)
    for (const option of options) {
      expect(screen.getByText(`${option.width_m.toFixed(2)} × ${option.depth_m.toFixed(2)} מ'`)).toBeInTheDocument()
    }
    // the CUSTOM card is present too
    expect(screen.getByTestId('footprint-card-custom')).toBeInTheDocument()
  })

  it('"continue" is disabled until a valid option is selected', () => {
    render(<Harness targetAreaM2={120} />)
    expect(screen.getByRole('button', { name: 'המשך ליצירת התכנון' })).toBeDisabled()
  })

  it('selecting a preset card stores that exact footprint and enables continue', () => {
    render(<Harness targetAreaM2={120} />)
    const options = generateFootprintOptions(120)
    const target = options.find((option) => option.shape_type === 'WIDE')!

    fireEvent.click(screen.getByText('רחב'))

    expect(screen.getByRole('button', { name: 'המשך ליצירת התכנון' })).toBeEnabled()
    // the WIDE card is now visually the selected one (radio semantics)
    const wideCard = screen.getByText('רחב').closest('[role="radio"]')
    expect(wideCard).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByText(`${target.width_m.toFixed(2)} × ${target.depth_m.toFixed(2)} מ'`)).toBeInTheDocument()
  })

  it('selecting a different preset deselects the previous one (single selection only)', () => {
    render(<Harness targetAreaM2={120} />)
    fireEvent.click(screen.getByText('רחב'))
    fireEvent.click(screen.getByText('צר ומוארך'))

    const wideCard = screen.getByText('רחב').closest('[role="radio"]')
    const narrowCard = screen.getByText('צר ומוארך').closest('[role="radio"]')
    expect(wideCard).toHaveAttribute('aria-checked', 'false')
    expect(narrowCard).toHaveAttribute('aria-checked', 'true')
  })

  it('CUSTOM: entering dimensions that match the target area (within tolerance) enables continue and shows live feedback', () => {
    render(<Harness targetAreaM2={200} />)

    fireEvent.change(screen.getByTestId('footprint-custom-width'), { target: { value: '10' } })
    fireEvent.change(screen.getByTestId('footprint-custom-depth'), { target: { value: '20' } })

    const customCard = within(screen.getByTestId('footprint-card-custom'))
    expect(customCard.getByText(/200\.00 מ"ר/)).toBeInTheDocument()
    expect(customCard.getByText(/תואם לשטח היעד/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'המשך ליצירת התכנון' })).toBeEnabled()
  })

  it('CUSTOM: dimensions off the target area beyond tolerance stay invalid and block continue (task\'s own worked example: 9x20 vs 200)', () => {
    render(<Harness targetAreaM2={200} />)

    fireEvent.change(screen.getByTestId('footprint-custom-width'), { target: { value: '9' } })
    fireEvent.change(screen.getByTestId('footprint-custom-depth'), { target: { value: '20' } })

    const customCard = within(screen.getByTestId('footprint-card-custom'))
    expect(customCard.getByText(/180\.00 מ"ר/)).toBeInTheDocument()
    expect(customCard.queryByText(/תואם לשטח היעד/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'המשך ליצירת התכנון' })).toBeDisabled()
  })

  it('CUSTOM: does not silently modify what the user typed — the exact entered numbers are echoed back', () => {
    render(<Harness targetAreaM2={200} />)

    fireEvent.change(screen.getByTestId('footprint-custom-width'), { target: { value: '10' } })
    fireEvent.change(screen.getByTestId('footprint-custom-depth'), { target: { value: '20' } })

    expect(screen.getByTestId('footprint-custom-width')).toHaveValue(10)
    expect(screen.getByTestId('footprint-custom-depth')).toHaveValue(20)
  })

  it('selecting CUSTOM does not clobber an existing valid PRESET selection while merely typing an incomplete entry', () => {
    render(<Harness targetAreaM2={120} />)
    fireEvent.click(screen.getByText('רחב'))
    expect(screen.getByRole('button', { name: 'המשך ליצירת התכנון' })).toBeEnabled()

    fireEvent.change(screen.getByTestId('footprint-custom-width'), { target: { value: '3' } })

    // still enabled — the WIDE preset is still the active, valid selection
    expect(screen.getByRole('button', { name: 'המשך ליצירת התכנון' })).toBeEnabled()
    const wideCard = screen.getByText('רחב').closest('[role="radio"]')
    expect(wideCard).toHaveAttribute('aria-checked', 'true')
  })

  it('changing the target area recalculates option dimensions', () => {
    render(<ReareaHarness />)
    const before120 = generateFootprintOptions(120).find((option) => option.shape_type === 'COMPACT')!
    expect(screen.getByText(`${before120.width_m.toFixed(2)} × ${before120.depth_m.toFixed(2)} מ'`)).toBeInTheDocument()

    fireEvent.click(screen.getByText('change-area'))

    const after240 = generateFootprintOptions(240).find((option) => option.shape_type === 'COMPACT')!
    expect(screen.getByText(`${after240.width_m.toFixed(2)} × ${after240.depth_m.toFixed(2)} מ'`)).toBeInTheDocument()
    expect(screen.queryByText(`${before120.width_m.toFixed(2)} × ${before120.depth_m.toFixed(2)} מ'`)).not.toBeInTheDocument()
  })

  it('a stale selection (made before the target area changed) is invalidated and cannot be submitted', () => {
    render(<ReareaHarness />)
    fireEvent.click(screen.getByText('רחב'))
    expect(screen.getByRole('button', { name: 'המשך ליצירת התכנון' })).toBeEnabled()

    fireEvent.click(screen.getByText('change-area'))

    // the stale selection was cleared — continue is disabled again until a fresh choice is made
    expect(screen.getByRole('button', { name: 'המשך ליצירת התכנון' })).toBeDisabled()
    const wideCard = screen.getByText('רחב').closest('[role="radio"]')
    expect(wideCard).toHaveAttribute('aria-checked', 'false')
  })

  it('a stale CUSTOM selection is also invalidated when the target area changes', () => {
    render(<ReareaHarness />)
    fireEvent.change(screen.getByTestId('footprint-custom-width'), { target: { value: '10' } })
    fireEvent.change(screen.getByTestId('footprint-custom-depth'), { target: { value: '12' } }) // 120 m2, valid for area=120
    expect(screen.getByRole('button', { name: 'המשך ליצירת התכנון' })).toBeEnabled()

    fireEvent.click(screen.getByText('change-area')) // area becomes 240 -> 10x12=120 no longer valid

    expect(screen.getByRole('button', { name: 'המשך ליצירת התכנון' })).toBeDisabled()
  })

  it('calls onConfirm only when clicked with a valid selection', () => {
    const onConfirm = vi.fn()
    render(<Harness targetAreaM2={120} onConfirm={onConfirm} />)
    fireEvent.click(screen.getByText('קומפקטי'))
    fireEvent.click(screen.getByRole('button', { name: 'המשך ליצירת התכנון' }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })
})
