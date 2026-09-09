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
})

describe('DemoWorkspace', () => {
  it('states only validation claims the backend actually made', () => {
    const { getByText, queryByText } = render(
      <DemoWorkspace design={design()} onChangeRequirements={() => {}} />,
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
    const { getByText } = render(<DemoWorkspace design={failing} onChangeRequirements={() => {}} />)
    expect(getByText('בעיה כלשהי')).toBeTruthy()
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
    const { getByText } = render(<DemoWorkspace design={full} onChangeRequirements={() => {}} />)
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
      <DemoWorkspace design={plain} onChangeRequirements={() => {}} />,
    )
    getByText('קיר חוץ')
    // no safe room in this house, so no safe-room key — and likewise for the rest
    expect(queryByText('קיר ממ״ד — בטון מזוין')).toBeNull()
    expect(queryByText('מעבר פתוח — אין קיר כלל')).toBeNull()
    expect(queryByText('חלון')).toBeNull()
    expect(queryByText('דלת כניסה')).toBeNull()
    expect(queryByText('פתח דלת — קיר שנקטע')).toBeNull()
    expect(queryByText('גינה')).toBeNull()
    expect(queryByText('חניה')).toBeNull()
  })

  it('draws its swatches from the renderer’s own styles, so it cannot drift from the plan', () => {
    const { container } = render(<DemoWorkspace design={design()} onChangeRequirements={() => {}} />)
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

  it('says plainly when the chosen outline does not fit the land that is left', () => {
    const { getByLabelText } = render(
      <ReviewPage
        review={{ ...base, site: { ...base.site!, buildable_depth_m: 6.5, footprint_fits: false } }}
        onConfirm={() => {}} onBack={() => {}} />,
    )
    within(getByLabelText('המגרש והנחות התכנון')).getByText(/אינו נכנס בשטח שנותר לבנייה/)
  })
})
