import { describe, expect, it } from 'vitest'
import { fireEvent, render, within } from '@testing-library/react'
import DemoPlan, { planViewBox } from './DemoPlan'
import DemoWorkspace from './DemoWorkspace'
import ReviewPage from './ReviewPage'
import type { DemoDesign, RequirementsReview } from './demoDesign'

/** The renderer boundary: DemoPlan draws exactly what the backend supplied, and nothing else. */
function design(overrides: Partial<DemoDesign> = {}): DemoDesign {
  return {
    plot: { x: 0, y: 0, width_m: 20, depth_m: 24 },
    footprint: { x: 3, y: 5.5, width_m: 12, depth_m: 14 },
    rooms: [
      {
        id: 'LIVING', type: 'LIVING', name: 'סלון',
        x: 3, y: 5.5, width_m: 5, depth_m: 6, area_m2: 27.4,
        walls: {
          N: { construction: 'STANDARD_PARTITION', boundary_context: 'EXTERIOR', can_take_a_window: true },
          S: { construction: 'NONE', boundary_context: 'INTERIOR', can_take_a_window: false },
          E: { construction: 'STANDARD_PARTITION', boundary_context: 'INTERIOR', can_take_a_window: false },
          W: { construction: 'STANDARD_PARTITION', boundary_context: 'EXTERIOR', can_take_a_window: true },
        },
      },
    ],
    walls: [
      { orientation: 'horizontal', coord: 5.5, start: 3, end: 8, construction: 'STANDARD_PARTITION', boundary_context: 'EXTERIOR', room_ids: ['LIVING'] },
      { orientation: 'vertical', coord: 8, start: 5.5, end: 11.5, construction: 'RC_SAFE_ROOM', boundary_context: 'INTERIOR', room_ids: ['SAFE_ROOM'] },
    ],
    open_interfaces: [
      { orientation: 'horizontal', coord: 11.5, start: 3, end: 8, room_ids: ['LIVING', 'DINING'] },
    ],
    doors: [
      { a: 'HALL', b: 'LIVING', kind: 'DOOR', width_m: 0.9, x: 8, y: 8, orientation: 'vertical', is_entrance: false },
      { a: 'OUTSIDE', b: 'HALL', kind: 'DOOR', width_m: 1, x: 9, y: 5.5, orientation: 'horizontal', is_entrance: true },
    ],
    windows: [{ room_id: 'LIVING', side: 'W', width_m: 1.8, x: 3, y: 8.5 }],
    parking: [{ x: 3, y: 0, width_m: 2.5, depth_m: 5 }],
    garden: [{ x: 0, y: 19.5, width_m: 20, depth_m: 4.5 }],
    entrance_walk: { x: 8.4, y: 0, width_m: 1.2, depth_m: 5.5 },
    gross_area_m2: 168,
    net_area_m2: 151.2,
    validation: {
      passed: true,
      statements: ['כל החדרים נגישים פיזית מהכניסה'],
      warnings: [],
      checks: { C5: true, C13: true },
    },
    ...overrides,
  }
}

describe('DemoPlan', () => {
  it('frames the drawing on the building, not on a vast parcel', () => {
    // 400 x 200 m of land around a 19 x 10.5 m house: framing the plot draws a stamp.
    const large = design({
      plot: { x: 0, y: 0, width_m: 400, depth_m: 200 },
      footprint: { x: 190, y: 4, width_m: 19, depth_m: 10.5 },
      entrance_walk: { x: 198, y: 0, width_m: 1.2, depth_m: 4 },
      parking: [],
      garden: [{ x: 0, y: 0, width_m: 400, depth_m: 200 }],
    })
    const [, , w, h] = planViewBox(large).split(' ').map(Number)
    // The house must dominate the frame rather than be lost in it.
    expect(w).toBeLessThan(50)
    expect(h).toBeLessThan(50)
    expect(19 / w).toBeGreaterThan(0.5)
  })

  it('still shows the whole site when the plot is barely larger than the house', () => {
    const [x, y, w, h] = planViewBox(design()).split(' ').map(Number)
    expect(x).toBeLessThanOrEqual(0)
    expect(y).toBeLessThanOrEqual(0)
    expect(x + w).toBeGreaterThanOrEqual(20)
    expect(y + h).toBeGreaterThanOrEqual(24)
  })

  it('draws exactly the walls the backend supplied — no more, no fewer', () => {
    const { container } = render(<DemoPlan design={design()} />)
    // 2 walls + 2 doors + 1 window = 5 <line> elements. An inferred door would push this to 6.
    expect(container.querySelectorAll('line')).toHaveLength(5)
  })

  it('draws no wall where the backend reports an OPEN interface', () => {
    const withOpen = design()
    const { container } = render(<DemoPlan design={withOpen} />)
    const horizontals = Array.from(container.querySelectorAll('line')).filter(
      (line) => line.getAttribute('y1') === '11.5',
    )
    expect(horizontals).toHaveLength(0)
  })

  it('weights an RC safe-room wall differently from a partition', () => {
    const { container } = render(<DemoPlan design={design()} />)
    const strokes = Array.from(container.querySelectorAll('line')).map((l) => l.getAttribute('stroke'))
    expect(strokes).toContain('#b03a2e')
  })

  it('renders no doors at all when the backend supplies none', () => {
    const { container } = render(<DemoPlan design={design({ doors: [] })} />)
    expect(container.querySelectorAll('.demo-door')).toHaveLength(0)
  })

  it('renders no windows when the backend supplies none', () => {
    const { container } = render(<DemoPlan design={design({ windows: [] })} />)
    expect(container.querySelectorAll('.demo-window')).toHaveLength(0)
  })

  it('shows the authoritative room name and area', () => {
    const { getByText } = render(<DemoPlan design={design()} />)
    expect(getByText('סלון')).toBeTruthy()
    expect(getByText('27.4 מ״ר')).toBeTruthy()
  })

  it('draws a cased opening as a gap with jamb ticks, never a leaf or a swing arc', () => {
    const casedOpening = design({
      doors: [
        { a: 'HALL', b: 'LIVING', kind: 'CASED_OPENING', width_m: 0.9, x: 8, y: 8,
          orientation: 'vertical', is_entrance: false, swings_into: 'LIVING', hinge_x: 8, hinge_y: 5 },
      ],
    })
    const { container } = render(<DemoPlan design={casedOpening} />)
    expect(container.querySelectorAll('.demo-door-leaf')).toHaveLength(0)
    expect(container.querySelectorAll('.demo-door-arc')).toHaveLength(0)
    expect(container.querySelectorAll('.demo-door-jamb')).toHaveLength(2)
    expect(container.querySelectorAll('.demo-door--cased')).toHaveLength(1)
  })

  it('still draws a leaf and arc for an ordinary door with the same shape of data', () => {
    const ordinaryDoor = design({
      doors: [
        { a: 'HALL', b: 'LIVING', kind: 'DOOR', width_m: 0.9, x: 8, y: 8,
          orientation: 'vertical', is_entrance: false, swings_into: 'LIVING', hinge_x: 8, hinge_y: 5 },
      ],
    })
    const { container } = render(<DemoPlan design={ordinaryDoor} />)
    expect(container.querySelectorAll('.demo-door-leaf')).toHaveLength(1)
    expect(container.querySelectorAll('.demo-door-arc')).toHaveLength(1)
    expect(container.querySelectorAll('.demo-door-jamb')).toHaveLength(0)
  })
})

describe('DemoPlan compass', () => {
  // The demo plan is drawn STREET-UP by the backend (street, parking and entrance walk along y = 0),
  // so this is the one drawing where a compass is truthful. The letter at the top is the street side.
  it.each([
    ['NORTH', 'N', 'S', 'KNOWN'],
    ['SOUTH', 'S', 'N', 'KNOWN'],
    ['EAST', 'E', 'W', 'UNDEFINED'],
    ['WEST', 'W', 'E', 'UNDEFINED'],
  ])('street %s → top %s, bottom %s, handedness %s', (side, top, bottom, handedness) => {
    const { container } = render(<DemoPlan design={design()} streetFacingSide={side} />)
    const rose = container.querySelector('[data-testid="compass"]')!
    expect(rose).not.toBeNull()
    expect(rose.getAttribute('data-top')).toBe(top)
    expect(rose.getAttribute('data-bottom')).toBe(bottom)
    expect(rose.getAttribute('data-handedness')).toBe(handedness)
  })

  it('sits inside the drawing frame', () => {
    const { container } = render(<DemoPlan design={design()} streetFacingSide="NORTH" />)
    const [x0, y0, w] = planViewBox(design()).split(' ').map(Number)
    const transform = container.querySelector('[data-testid="compass"]')!.getAttribute('transform')!
    const [cx, cy] = transform.replace('translate(', '').replace(')', '').split(' ').map(Number)
    expect(cx).toBeLessThan(x0 + w)
    expect(cx).toBeGreaterThan(x0)
    expect(cy).toBeGreaterThan(y0)
  })

  it('draws no compass without a street side (thumbnails, or no site)', () => {
    const { container } = render(<DemoPlan design={design()} />)
    expect(container.querySelector('[data-testid="compass"]')).toBeNull()
  })
})

describe('DemoWorkspace', () => {
  it('states only validation claims the backend actually made', () => {
    const { getByText, queryByText } = render(
      <DemoWorkspace plans={{ plan: design(), alternatives: [] }} onChangeRequirements={() => {}} />,
    )
    expect(getByText('כל החדרים נגישים פיזית מהכניסה')).toBeTruthy()
    // Raw check codes must never reach the user.
    expect(queryByText(/C13/)).toBeNull()
    expect(queryByText(/C5/)).toBeNull()
  })

  it('shows warnings when validation reported them', () => {
    const failing = design({
      validation: { passed: false, statements: [], warnings: ['בעיה כלשהי'], checks: { C13: false } },
    })
    const { getByText } = render(<DemoWorkspace plans={{ plan: failing, alternatives: [] }} onChangeRequirements={() => {}} />)
    expect(getByText('בעיה כלשהי')).toBeTruthy()
  })

  // ------------------------------------------------------------------- the other plans
  //
  // Several layouts pass every check, and which one is best is taste the engine cannot settle.
  // The alternatives it proved are shown small; picking one SWAPS it with the large drawing, so
  // the set on screen stays the same set and nothing is lost by looking around.

  /** Three plans that differ in a way a test can see: the living room's area. */
  const planSet = () => ({
    plan: design({ gross_area_m2: 100 }),
    alternatives: [design({ gross_area_m2: 200 }), design({ gross_area_m2: 300 })],
  })

  it('shows the engine\'s plan large and every alternative as a thumbnail', () => {
    const { getByTestId, queryByTestId } = render(
      <DemoWorkspace plans={planSet()} onChangeRequirements={() => {}} />,
    )
    expect(getByTestId('plan-shown')).toHaveTextContent('הבחירה של המנוע')
    // the two alternatives are offered; the plan already on the board is not among them
    expect(getByTestId('plan-option-1')).toBeInTheDocument()
    expect(getByTestId('plan-option-2')).toBeInTheDocument()
    expect(queryByTestId('plan-option-0')).not.toBeInTheDocument()
  })

  it('clicking a thumbnail puts it on the board and sends the large plan to its slot', () => {
    const { getByTestId, queryByTestId, getByText } = render(
      <DemoWorkspace plans={planSet()} onChangeRequirements={() => {}} />,
    )
    expect(getByText('100.0 מ״ר')).toBeInTheDocument()      // the side panel describes plan 0

    fireEvent.click(getByTestId('plan-option-2'))

    expect(getByTestId('plan-shown')).toHaveTextContent('אפשרות 3')
    expect(getByText('300.0 מ״ר')).toBeInTheDocument()      // ...and now describes plan 2
    // a SWAP, not a removal: the engine's plan took the slot the clicked one left
    expect(getByTestId('plan-option-0')).toBeInTheDocument()
    expect(getByTestId('plan-option-1')).toBeInTheDocument()
    expect(queryByTestId('plan-option-2')).not.toBeInTheDocument()
  })

  it('a plan keeps its own name wherever it is sitting', () => {
    const { getByTestId } = render(<DemoWorkspace plans={planSet()} onChangeRequirements={() => {}} />)

    fireEvent.click(getByTestId('plan-option-2'))
    fireEvent.click(getByTestId('plan-option-1'))

    // labels follow the PLAN, not the slot — "אפשרות 3" is the same drawing it always was
    expect(getByTestId('plan-shown')).toHaveTextContent('אפשרות 2')
    expect(getByTestId('plan-option-2')).toHaveTextContent('אפשרות 3')
    expect(getByTestId('plan-option-0')).toHaveTextContent('הבחירה של המנוע')
  })

  it('offers nothing to switch to when the engine produced only one plan', () => {
    const { queryByTestId, queryByText } = render(
      <DemoWorkspace plans={{ plan: design(), alternatives: [] }} onChangeRequirements={() => {}} />,
    )
    expect(queryByTestId('plan-shown')).not.toBeInTheDocument()
    expect(queryByText(/אפשרויות נוספות/)).not.toBeInTheDocument()
    expect(queryByTestId('plan-option-1')).not.toBeInTheDocument()
  })

  it('a regenerated plan set resets the board to the engine\'s new choice', () => {
    const { getByTestId, rerender } = render(
      <DemoWorkspace plans={planSet()} onChangeRequirements={() => {}} />,
    )
    fireEvent.click(getByTestId('plan-option-2'))
    expect(getByTestId('plan-shown')).toHaveTextContent('אפשרות 3')

    // a second generation with FEWER alternatives — a stale order would index past the end
    rerender(
      <DemoWorkspace
        plans={{ plan: design({ gross_area_m2: 400 }), alternatives: [design({ gross_area_m2: 500 })] }}
        onChangeRequirements={() => {}}
      />,
    )
    expect(getByTestId('plan-shown')).toHaveTextContent('הבחירה של המנוע')
    expect(getByTestId('plan-option-1')).toBeInTheDocument()
  })
})

describe('DemoWorkspace — the outline each plan occupies (feature 006)', () => {
  const engine = design({ outline: { width_m: 12.35, depth_m: 14.25, area_m2: 175.99, origin: 'ENGINE' } })
  const person = design({ outline: { width_m: 15, depth_m: 11.75, area_m2: 176.25, origin: 'PERSON' } })

  it('states the outline under the plan on the board, and who chose it', () => {
    const { getByTestId } = render(<DemoWorkspace plans={{ plan: engine, alternatives: [] }} onChangeRequirements={() => {}} />)
    const label = getByTestId('plan-outline')
    expect(label.textContent).toContain('12.35 × 14.25')
    expect(label.textContent).toContain('176 מ״ר')
    expect(label.textContent).toContain('מתאר אוטומטי')
  })

  it('names the outline the person entered as theirs', () => {
    const { getByTestId } = render(<DemoWorkspace plans={{ plan: person, alternatives: [] }} onChangeRequirements={() => {}} />)
    expect(getByTestId('plan-outline').textContent).toContain('המתאר שהזנת')
  })

  it('labels every thumbnail with its own outline, so a different house size is visible', () => {
    const other = design({ outline: { width_m: 13.6, depth_m: 12.95, area_m2: 176.12, origin: 'ENGINE' }, gross_area_m2: 176.1 })
    const { getByTestId } = render(<DemoWorkspace plans={{ plan: engine, alternatives: [other] }} onChangeRequirements={() => {}} />)
    expect(getByTestId('plan-option-1').textContent).toContain('13.60 × 12.95')
  })

  it('says nothing about an outline when the design carries none', () => {
    const { queryByTestId } = render(<DemoWorkspace plans={{ plan: design(), alternatives: [] }} onChangeRequirements={() => {}} />)
    expect(queryByTestId('plan-outline')).toBeNull()
  })

  it('tells the person when the outline they entered could not be planned and another was used', () => {
    const { getByRole } = render(
      <DemoWorkspace
        plans={{
          plan: engine, alternatives: [],
          search: {
            outlines: [
              { width_m: 10, depth_m: 17.6, origin: 'PERSON', planned: false, plans_found: 0, latency_ms: 900 },
              { width_m: 12.35, depth_m: 14.25, origin: 'ENGINE', planned: true, plans_found: 1, latency_ms: 1200 },
            ],
            total_latency_ms: 2100,
          },
        }}
        onChangeRequirements={() => {}}
      />,
    )
    const note = getByRole('note')
    expect(note.textContent).toContain('10.00 × 17.60')
    expect(note.textContent).toContain('לא אפשר לסדר את החדרים')
  })

  it('shows no such note when the person chose nothing or their outline planned', () => {
    const { queryByRole } = render(
      <DemoWorkspace
        plans={{
          plan: person, alternatives: [],
          search: { outlines: [{ width_m: 15, depth_m: 11.75, origin: 'PERSON', planned: true, plans_found: 1, latency_ms: 1200 }], total_latency_ms: 1200 },
        }}
        onChangeRequirements={() => {}}
      />,
    )
    expect(queryByRole('note')).toBeNull()
  })
})

describe('PlanLegend', () => {
  it('names every colour the plan actually used', () => {
    const full = design({
      walls: [
        { orientation: 'horizontal', coord: 5.5, start: 3, end: 8, construction: 'STANDARD_PARTITION', boundary_context: 'EXTERIOR', room_ids: ['LIVING'] },
        { orientation: 'vertical', coord: 8, start: 5.5, end: 11.5, construction: 'RC_SAFE_ROOM', boundary_context: 'INTERIOR', room_ids: ['SAFE_ROOM'] },
        { orientation: 'vertical', coord: 6, start: 5.5, end: 9, construction: 'STANDARD_PARTITION', boundary_context: 'INTERIOR', room_ids: ['LIVING', 'HALL'] },
      ],
    })
    const { getByText } = render(<DemoWorkspace plans={{ plan: full, alternatives: [] }} onChangeRequirements={() => {}} />)
    getByText('מקרא')
    getByText('קיר חוץ')
    getByText('מחיצה פנימית')
    getByText('קיר ממ״ד — בטון מזוין')
    getByText('חלון')
    getByText('דלת כניסה')
    getByText('פתח דלת — קיר שנקטע')
    getByText('מעבר פתוח — אין קיר כלל')
    getByText('גינה')
    getByText('חניה')
  })

  it('omits a key for anything this design does not contain', () => {
    const plain = design({
      walls: [
        { orientation: 'horizontal', coord: 5.5, start: 3, end: 8, construction: 'STANDARD_PARTITION', boundary_context: 'EXTERIOR', room_ids: ['LIVING'] },
      ],
      open_interfaces: [],
      windows: [],
      parking: [],
      garden: [],
      doors: [],
    })
    const { queryByText, getByText } = render(
      <DemoWorkspace plans={{ plan: plain, alternatives: [] }} onChangeRequirements={() => {}} />,
    )
    getByText('קיר חוץ')
    // no safe room in this house, so no safe-room key — and likewise for the rest
    expect(queryByText('קיר ממ״ד — בטון מזוין')).toBeNull()
    expect(queryByText('מעבר פתוח — אין קיר כלל')).toBeNull()
    expect(queryByText('חלון')).toBeNull()
    expect(queryByText('דלת כניסה')).toBeNull()
    expect(queryByText('פתח דלת — קיר שנקטע')).toBeNull()
    expect(queryByText('מעבר פתוח לסלון — ללא דלת')).toBeNull()
    expect(queryByText('גינה')).toBeNull()
    expect(queryByText('חניה')).toBeNull()
  })

  it('shows the cased-opening key only when the design has one, distinct from an ordinary door', () => {
    const withCasedOpening = design({
      doors: [
        { a: 'HALL', b: 'LIVING', kind: 'CASED_OPENING', width_m: 0.9, x: 8, y: 8,
          orientation: 'vertical', is_entrance: false },
        { a: 'OUTSIDE', b: 'HALL', kind: 'DOOR', width_m: 1, x: 9, y: 5.5,
          orientation: 'horizontal', is_entrance: true },
      ],
    })
    const { getByText, queryByText } = render(
      <DemoWorkspace plans={{ plan: withCasedOpening, alternatives: [] }} onChangeRequirements={() => {}} />,
    )
    getByText('מעבר פתוח לסלון — ללא דלת')
    expect(queryByText('פתח דלת — קיר שנקטע')).toBeNull()
  })

  it('draws its swatches from the renderer’s own styles, so it cannot drift from the plan', () => {
    const { container } = render(<DemoWorkspace plans={{ plan: design(), alternatives: [] }} onChangeRequirements={() => {}} />)
    const swatches = container.querySelectorAll('.legend-swatch')
    expect(swatches.length).toBeGreaterThan(0)
    const strokes = Array.from(container.querySelectorAll('.legend-swatch line')).map((l) =>
      l.getAttribute('stroke'),
    )
    expect(strokes).toContain('#b03a2e') // WALL_STYLE.RC_SAFE_ROOM
    expect(strokes).toContain('#1a1a1a') // EXTERIOR_WALL_STYLE
    expect(strokes).toContain('#8b939c') // WALL_STYLE.STANDARD_PARTITION
  })
})

describe('ReviewPage — requests we cannot plan', () => {
  const review: RequirementsReview = {
    bedrooms: { value: 3, source: 'requested' },
    safe_room: { value: true, source: 'requested' },
    wet_rooms: { value: 2, source: 'requested' },
    open_plan: { value: true, source: 'requested' },
    parking_spaces: { value: 2, source: 'requested' },
    floors: { value: 1, source: 'inferred' },
    built_area_m2: 195,
    footprint_width_m: 13,
    footprint_depth_m: 15,
    description: 'בית עם 2 חדרי רחצה שלא צמודים ומסדרון ברוחב 5 מטר',
    unsupported_requests: [
      { text: '2 חדרי רחצה שלא יהיו צמודים זה לזה', topic: 'room_adjacency', severity: 'ambiguous' },
      { text: 'מסדרון ברוחב 5 מטר', topic: 'corridor_width', severity: 'hard_requirement' },
    ],
  }

  it('quotes them back in the person’s own words before generation', () => {
    const { getByLabelText, getByText } = render(
      <ReviewPage review={review} onConfirm={() => {}} onBack={() => {}} />,
    )
    getByText('צריך להכריע בבקשות האלה לפני שנתכנן')
    // scoped to the section: the same words also appear in the quoted brief above it, which is
    // exactly the overlap that made the old silence so easy to miss
    const panel = within(getByLabelText('בקשות שלא ייכללו בתכנון'))
    panel.getByText(/2 חדרי רחצה שלא יהיו צמודים זה לזה/)
    panel.getByText(/מסדרון ברוחב 5 מטר/)
    panel.getByText('יחסים בין חדרים')
    panel.getByText('רוחב מסדרון')
  })

  it('says nothing when the brief asked for nothing extra', () => {
    const { queryByText } = render(
      <ReviewPage review={{ ...review, unsupported_requests: [] }}
                  onConfirm={() => {}} onBack={() => {}} />,
    )
    expect(queryByText('מה שלא ייכלל בתכנון בשלב זה')).toBeNull()
  })

  it('grades each one by how it was worded', () => {
    const { getByLabelText } = render(
      <ReviewPage review={review} onConfirm={() => {}} onBack={() => {}} />,
    )
    const panel = within(getByLabelText('בקשות שלא ייכללו בתכנון'))
    panel.getByText('דרישה מחייבת')
    panel.getByText('לא ברור')
  })

  it('a preference alone still lets the plan be generated', () => {
    const confirmed: unknown[] = []
    const preferenceOnly: RequirementsReview = {
      ...review,
      unsupported_requests: [
        { text: 'אני מעדיף מסדרון רחב', topic: 'corridor_width', severity: 'preference' },
      ],
    }
    const { getByRole, getByText } = render(
      <ReviewPage review={preferenceOnly} onConfirm={(edit) => confirmed.push(edit)} onBack={() => {}} />,
    )
    getByText('מה שלא ייכלל בתכנון בשלב זה')
    const generate = getByRole('button', { name: 'יצירת תוכנית' })
    expect(generate).toBeEnabled()
    generate.click()
    expect(confirmed).toHaveLength(1)
  })

  it('a binding or unclear request holds generation until it is settled', () => {
    const { getByRole, getByText } = render(
      <ReviewPage review={review} onConfirm={() => {}} onBack={() => {}} />,
    )
    getByText('צריך להכריע בבקשות האלה לפני שנתכנן')
    expect(getByRole('button', { name: 'יצירת תוכנית' })).toBeDisabled()
    // and the way out is still open
    expect(getByRole('button', { name: 'חזרה לתיאור' })).toBeEnabled()
  })
})

describe('ReviewPage — the understood corridor requirement', () => {
  const base: RequirementsReview = {
    bedrooms: { value: 3, source: 'requested' },
    safe_room: { value: true, source: 'requested' },
    wet_rooms: { value: 2, source: 'requested' },
    open_plan: { value: true, source: 'requested' },
    parking_spaces: { value: 2, source: 'requested' },
    floors: { value: 1, source: 'inferred' },
    built_area_m2: 200,
    footprint_width_m: 14.14,
    footprint_depth_m: 14.14,
    description: 'המסדרון חייב להיות לפחות 1.8 מטר',
  }

  it('shows a minimum as a minimum, before Generate', () => {
    const { getByText } = render(
      <ReviewPage
        review={{ ...base, corridor_width: { value_m: 1.8, mode: 'minimum', source: 'requested' } }}
        onConfirm={() => {}} onBack={() => {}} />,
    )
    getByText(/רוחב מסדרון מינימלי/)
    getByText('1.80 מ׳')
  })

  it('does not call an exact width a minimum', () => {
    const { getByText, queryByText } = render(
      <ReviewPage
        review={{ ...base, corridor_width: { value_m: 2, mode: 'exact', source: 'requested' } }}
        onConfirm={() => {}} onBack={() => {}} />,
    )
    getByText('2.00 מ׳')
    expect(queryByText(/מינימלי/)).toBeNull()
  })

  it('says nothing when no width was asked for', () => {
    const { queryByText } = render(
      <ReviewPage review={base} onConfirm={() => {}} onBack={() => {}} />,
    )
    expect(queryByText(/רוחב מסדרון/)).toBeNull()
  })
})

describe('ReviewPage — understood room relationships', () => {
  const base: RequirementsReview = {
    bedrooms: { value: 3, source: 'requested' },
    safe_room: { value: true, source: 'requested' },
    wet_rooms: { value: 2, source: 'requested' },
    open_plan: { value: true, source: 'requested' },
    parking_spaces: { value: 2, source: 'requested' },
    floors: { value: 1, source: 'inferred' },
    built_area_m2: 200,
    footprint_width_m: 14.14,
    footprint_depth_m: 14.14,
    description: 'brief',
    room_relationships: [
      { source_role: 'MASTER_BEDROOM', target_role: 'ENSUITE', relation: 'adjacent',
        strength: 'hard_requirement', source_text: 'a', ambiguous: false,
        statement: 'חדר ההורים צמוד לחדר הרחצה של ההורים' },
      { source_role: 'SAFE_ROOM', target_role: 'BEDROOM', relation: 'near',
        strength: 'preference', source_text: 'b', ambiguous: false,
        statement: 'הממ"ד קרוב לחדרי השינה' },
    ],
  }

  it('shows each one with its strength, before Generate', () => {
    const { getByLabelText } = render(
      <ReviewPage review={base} onConfirm={() => {}} onBack={() => {}} />,
    )
    const panel = within(getByLabelText('יחסים בין חדרים'))
    panel.getByText('חדר ההורים צמוד לחדר הרחצה של ההורים')
    panel.getByText('הממ"ד קרוב לחדרי השינה')
    panel.getByText('דרישה מחייבת')
    panel.getByText('העדפה')
  })

  it('says nothing when the brief asked for no relationships', () => {
    const { queryByLabelText } = render(
      <ReviewPage review={{ ...base, room_relationships: [] }}
                  onConfirm={() => {}} onBack={() => {}} />,
    )
    expect(queryByLabelText('יחסים בין חדרים')).toBeNull()
  })
})

describe('ReviewPage — the rooms the plan will contain', () => {
  const base: RequirementsReview = {
    bedrooms: { value: 3, source: 'requested' },
    safe_room: { value: true, source: 'requested' },
    wet_rooms: { value: 2, source: 'requested' },
    open_plan: { value: true, source: 'requested' },
    parking_spaces: { value: 2, source: 'requested' },
    floors: { value: 1, source: 'inferred' },
    built_area_m2: 220,
    footprint_width_m: 17.23,
    footprint_depth_m: 12.77,
    description: '2 חדרי ילדים, חדר הורים עם מקלחת, סלון, מטבח, חדר עבודה קטן, 2 חניות',
    planned_rooms: ['סלון', 'פינת אוכל', 'מטבח', 'מסדרון', 'חדר הורים', 'חדר שינה ×2', 'ממ"ד', 'חדר רחצה ×2'],
  }

  it('names every room, so a requested room that is missing can be seen', () => {
    const { getByLabelText } = render(
      <ReviewPage review={base} onConfirm={() => {}} onBack={() => {}} />,
    )
    const panel = within(getByLabelText('חדרים שייכללו בתוכנית'))
    panel.getByText('חדר הורים')
    panel.getByText('חדר שינה ×2')
    panel.getByText('מטבח')
    // the study the brief asked for is absent from the plan, and therefore from this list
    expect(panel.queryByText(/עבודה/)).toBeNull()
  })

  it('says plainly that a room not on the list will not be built', () => {
    const { getByText } = render(
      <ReviewPage review={base} onConfirm={() => {}} onBack={() => {}} />,
    )
    getByText(/לא ייבנה/)
  })

  it('shows nothing before there is a programme to show', () => {
    const { queryByLabelText } = render(
      <ReviewPage review={{ ...base, planned_rooms: [] }} onConfirm={() => {}} onBack={() => {}} />,
    )
    expect(queryByLabelText('חדרים שייכללו בתוכנית')).toBeNull()
  })
})

describe('ReviewPage — the site and its assumptions', () => {
  const base: RequirementsReview = {
    bedrooms: { value: 3, source: 'requested' },
    safe_room: { value: true, source: 'requested' },
    wet_rooms: { value: 2, source: 'requested' },
    open_plan: { value: true, source: 'requested' },
    parking_spaces: { value: 2, source: 'requested' },
    floors: { value: 1, source: 'inferred' },
    built_area_m2: 132,
    footprint_width_m: 11,
    footprint_depth_m: 12,
    description: 'brief',
    site: {
      plot_width_m: 20, plot_depth_m: 24, plot_area_m2: 480, street_facing_side: 'NORTH',
      front_setback_m: 5.5, side_setback_m: 3, rear_setback_m: 4,
      setback_disclaimer: 'הנחות תכנון לדמו — אינן מידע תכנוני או רגולטורי מאומת.',
      buildable_width_m: 14, buildable_depth_m: 14.5, buildable_area_m2: 203,
      has_buildable_area: true,
      footprint_width_m: 11, footprint_depth_m: 12, footprint_fits: true,
    },
  }

  it('shows the plot, the frontage, the assumptions and what they leave', () => {
    const { getByLabelText } = render(
      <ReviewPage review={base} onConfirm={() => {}} onBack={() => {}} />,
    )
    const panel = within(getByLabelText('המגרש והנחות התכנון'))
    panel.getByText('20.00 × 24.00')
    panel.getByText('480.00 מ״ר')
    panel.getByText('צפון')
    panel.getByText('14.00 × 14.50')
    panel.getByText(/203\.00 מ״ר/)
    panel.getByText('הנחות תכנון לדמו — אינן מידע תכנוני או רגולטורי מאומת.')
  })

  it('lets the assumptions be corrected, and sends them with Generate', () => {
    const sent: unknown[] = []
    const { getByLabelText, getByRole } = render(
      <ReviewPage review={base} onConfirm={(edit) => sent.push(edit)} onBack={() => {}} />,
    )
    fireEvent.change(getByLabelText('נסיגה חזית'), { target: { value: '3' } })
    getByRole('button', { name: 'יצירת תוכנית' }).click()
    expect(sent).toHaveLength(1)
    expect(sent[0]).toMatchObject({ front_setback_m: 3, rear_setback_m: 4, side_setback_m: 3 })
  })

  it('says the outline will be chosen automatically when the person entered none (feature 006)', () => {
    const { getByLabelText } = render(
      <ReviewPage
        review={{ ...base, footprint_width_m: null, footprint_depth_m: null,
                  site: { ...base.site!, footprint_width_m: null, footprint_depth_m: null, footprint_fits: null } }}
        onConfirm={() => {}} onBack={() => {}} />,
    )
    within(getByLabelText('המגרש והנחות התכנון')).getByText(/ייקבע אוטומטית לפי השטח המבוקש/)
  })

  it('says plainly when the chosen outline does not fit the land that is left', () => {
    const { getByLabelText } = render(
      <ReviewPage
        review={{ ...base, site: { ...base.site!, buildable_depth_m: 6.5, footprint_fits: false } }}
        onConfirm={() => {}} onBack={() => {}} />,
    )
    within(getByLabelText('המגרש והנחות התכנון')).getByText(/אינו נכנס בשטח שנותר לבנייה/)
  })
})
