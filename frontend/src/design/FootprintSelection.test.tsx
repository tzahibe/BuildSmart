import { fireEvent, render, screen, within } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import FootprintSelection from './FootprintSelection'
import {
  generateFootprintOptions,
  type BuildingFootprint,
  type FootprintOptionsResponse,
} from './footprint'

/** A site whose buildable rectangle comfortably holds every option, so these tests exercise the
 * selection behaviour rather than the fit rule (which has its own tests, backend and front). The
 * options themselves now come from the backend, so the harness supplies them as it would arrive. */
function siteFor(targetAreaM2: number, buildable = { width_m: 40, depth_m: 40 }): FootprintOptionsResponse {
  return {
    plot_width_m: buildable.width_m + 6, plot_depth_m: buildable.depth_m + 9.5,
    street_facing_side: 'NORTH',
    front_setback_m: 5.5, side_setback_m: 3, rear_setback_m: 4,
    setback_disclaimer: 'הנחות תכנון לדמו — אינן מידע תכנוני או רגולטורי מאומת.',
    buildable_width_m: buildable.width_m, buildable_depth_m: buildable.depth_m,
    has_buildable_area: true,
    one_storey_footprint_capacity_m2: buildable.width_m * buildable.depth_m,
    requested_built_area_m2: targetAreaM2,
    options: generateFootprintOptions(targetAreaM2).map((option) => ({
      shape_type: option.shape_type,
      width_m: option.width_m,
      depth_m: option.depth_m,
      area_m2: option.area_m2,
    })),
    rejection: null,
  }
}

/** A thin controlled-component harness — App.tsx owns `footprint` state the same way; these tests
 * exercise FootprintSelection exactly as it's actually used, not with a bare `onChange` spy that
 * would never let the component read back its own committed selection. */
function Harness({ targetAreaM2, onConfirm }: { targetAreaM2: number; onConfirm?: () => void }) {
  const [value, setValue] = useState<BuildingFootprint | null>(null)
  return (
    <FootprintSelection
      site={siteFor(targetAreaM2)}
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
      <FootprintSelection site={siteFor(area)} targetAreaM2={area} value={value} onChange={setValue} onConfirm={() => {}} onBack={() => {}} />
    </div>
  )
}

describe('FootprintSelection', () => {
  it('shows one card per preset option, each with distinct dimensions/area, once the target area is known', () => {
    render(<Harness targetAreaM2={120} />)
    const options = generateFootprintOptions(120)
    for (const option of options) {
      const pair = screen.getByText(`${option.width_m.toFixed(2)} × ${option.depth_m.toFixed(2)}`)
      expect(pair).toHaveAttribute('dir', 'ltr')      // read left-to-right inside the RTL page
      expect(pair.parentElement).toHaveTextContent(
        `${option.width_m.toFixed(2)} × ${option.depth_m.toFixed(2)} מ'`)
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
    expect(screen.getByText(`${target.width_m.toFixed(2)} × ${target.depth_m.toFixed(2)}`)
      .parentElement).toHaveTextContent(`${target.width_m.toFixed(2)} × ${target.depth_m.toFixed(2)} מ'`)
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
    const pair = (option: { width_m: number; depth_m: number }) =>
      `${option.width_m.toFixed(2)} × ${option.depth_m.toFixed(2)}`
    expect(screen.getByText(pair(before120))).toBeInTheDocument()

    fireEvent.click(screen.getByText('change-area'))

    const after240 = generateFootprintOptions(240).find((option) => option.shape_type === 'COMPACT')!
    expect(screen.getByText(pair(after240))).toBeInTheDocument()
    expect(screen.queryByText(pair(before120))).not.toBeInTheDocument()
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

  // ------------------------------------------------------------------ a site with nothing to build on
  //
  // 200 x 3 m is a real thing for someone to type. The raw subtraction 3 - 5.5 - 4 is -6.5, and the
  // screen used to present that as the derived buildable area — a negative length, beside a refusal
  // about the requested house being too big for a parcel that has no buildable region at all.

  /** What the backend returns for that parcel: the region is EMPTY, and says so. */
  function noBuildableAreaSite(): FootprintOptionsResponse {
    return {
      plot_width_m: 200, plot_depth_m: 3,
      street_facing_side: 'NORTH',
      front_setback_m: 5.5, side_setback_m: 3, rear_setback_m: 4,
      setback_disclaimer: 'הנחות תכנון לדמו — אינן מידע תכנוני או רגולטורי מאומת.',
      buildable_width_m: 194, buildable_depth_m: 0,
      has_buildable_area: false,
      one_storey_footprint_capacity_m2: 0,
      requested_built_area_m2: 250,
      options: [],
      rejection: {
        code: 'NO_BUILDABLE_AREA',
        message: 'אין אזור בנייה: סך הנסיגות הקדמית והאחורית הוא 9.50 מ׳, גדול מעומק המגרש 3.00 מ׳.',
      },
    }
  }

  function renderSite(site: FootprintOptionsResponse) {
    return render(
      <FootprintSelection
        site={site}
        targetAreaM2={site.requested_built_area_m2}
        value={null}
        onChange={() => {}}
        onConfirm={() => {}}
        onBack={() => {}}
      />,
    )
  }

  it('states that there is no buildable area instead of showing a negative dimension', () => {
    renderSite(noBuildableAreaSite())

    expect(screen.getByRole('alert')).toHaveTextContent('אין אזור בנייה על המגרש הזה')
    // the derived region is named in words, because an empty rectangle has no size to state
    expect(screen.getByText('אזור בנייה שנגזר').parentElement).toHaveTextContent('אין אזור בנייה')
    // the backend's own explanation of the CAUSE is what the person reads
    expect(screen.getByText(/סך הנסיגות הקדמית והאחורית הוא 9.50 מ׳/)).toBeInTheDocument()
    // ...and not the capacity advice, which points at the one number that cannot help here
    expect(screen.queryByText(/אפשר להקטין את שטח הבנייה המבוקש/)).not.toBeInTheDocument()
    // the entered plot is echoed back exactly as entered
    expect(screen.getByText('מידות המגרש').parentElement).toHaveTextContent('200.00 × 3.00')
  })

  it('never renders a negative number anywhere on such a site', () => {
    const { container } = renderSite(noBuildableAreaSite())
    fireEvent.change(screen.getByTestId('footprint-custom-width'), { target: { value: '200' } })
    fireEvent.change(screen.getByTestId('footprint-custom-depth'), { target: { value: '3' } })

    expect(container.textContent).not.toMatch(/(?<![0-9A-Za-z\u0590-\u05FF])-\s*\d/)
    const custom = within(screen.getByTestId('footprint-card-custom'))
    expect(custom.getByText(/אין אזור בנייה על המגרש הזה אחרי הנסיגות/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'המשך ליצירת התכנון' })).toBeDisabled()
  })

  // ------------------------------------------------------------- reading order in an RTL page
  //
  // The numbers were never wrong; the reading order was. In an RTL paragraph the "×" between two
  // numbers resolves to right-to-left and the bidi algorithm reverses the run, so "200.00 × 3.00"
  // is DISPLAYED as "3.00 × 200.00" and the reader sees a plot they never entered. Every pair has
  // to sit in an LTR island for the order on screen to be the order in the markup.

  /** An element's own text — what it holds directly, not what its children add. */
  function ownText(el: Element): string {
    return Array.from(el.childNodes)
      .filter((node) => node.nodeType === Node.TEXT_NODE)
      .map((node) => node.textContent)
      .join('')
      .trim()
  }

  /** Every element that itself holds a "W × D" pair. */
  function pairHosts(root: HTMLElement): HTMLElement[] {
    return Array.from(root.querySelectorAll<HTMLElement>('*'))
      .filter((el) => /\d\s*×\s*\d/.test(ownText(el)))
  }

  it('every width × depth pair on the screen is isolated left-to-right', () => {
    const { container } = render(<Harness targetAreaM2={200} />)
    fireEvent.change(screen.getByTestId('footprint-custom-width'), { target: { value: '10' } })
    fireEvent.change(screen.getByTestId('footprint-custom-depth'), { target: { value: '20' } })

    const hosts = pairHosts(container)
    expect(hosts.length).toBeGreaterThan(0)          // preset cards + the custom feedback line
    for (const host of hosts) {
      expect(host.closest('[dir]')).toHaveAttribute('dir', 'ltr')
    }
  })

  it('a pair reads width first — the width the person entered, not the depth', () => {
    const { container } = renderSite(noBuildableAreaSite())
    const texts = pairHosts(container).map(ownText)
    expect(texts).toContain('200.00 × 3.00')         // the plot, width first
    expect(texts).not.toContain('3.00 × 200.00')
  })

  it('the custom feedback echoes the entered pair in the order it was typed', () => {
    const { container } = render(<Harness targetAreaM2={200} />)
    fireEvent.change(screen.getByTestId('footprint-custom-width'), { target: { value: '10' } })
    fireEvent.change(screen.getByTestId('footprint-custom-depth'), { target: { value: '20' } })

    const feedback = pairHosts(screen.getByTestId('footprint-card-custom')).map(ownText)
    expect(feedback).toContain('10.00 × 20.00')      // as typed: width, then depth
    expect(feedback).not.toContain('20.00 × 10.00')
    expect(container.querySelectorAll('[dir="ltr"]').length).toBeGreaterThan(0)
  })
})
