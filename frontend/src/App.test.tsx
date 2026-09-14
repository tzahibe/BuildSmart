import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { generateFootprintOptions } from './design/footprint'

/** All calls this test file's `fetch` mock recorded, typed loosely on purpose (vitest's own
 * `mock.calls` type is `any[][]`, and TS's overload resolution rejects a tuple-destructuring
 * predicate against that width-erased type) — narrowed back to a usable shape only where read. */
function projectCreatePostCalls(): Array<[RequestInfo | URL, RequestInit | undefined]> {
  const calls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls as Array<[RequestInfo | URL, RequestInit | undefined]>
  return calls.filter((call) => call[0] === '/projects' && call[1]?.method === 'POST')
}

/** Minimal, loosely-shaped stand-ins for the JSON bodies App.tsx reads back from `fetch` — the
 * frontend never runtime-validates these (it just casts the parsed JSON), so only the fields App.tsx
 * itself actually reads need to be present. */
function fakeProject(overrides: Record<string, unknown> = {}) {
  return {
    project_id: 'p1',
    city: 'תל אביב',
    street: 'הרצל 1',
    plot_area_m2: 400,
    built_area_m2: 120,
    description: 'תיאור',
    status: 'active',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    floors: null,
    bedrooms: null,
    safe_room: null,
    parking_spaces: null,
    pool: null,
    requirements_parsed_at: null,
    site_width_m: null,
    site_depth_m: null,
    selected_footprint: null,
    rooms: null,
    design_notes: null,
    design_generated_at: null,
    geometric_design: null,
    active_design_version_id: null,
    preferences: [],
    change_log: [],
    ...overrides,
  }
}

/** The `GET /projects/{id}/review` body — only the fields ReviewPage actually reads. */
function fakeReview(overrides: Record<string, unknown> = {}) {
  return {
    bedrooms: { value: 3, source: 'requested' },
    safe_room: { value: true, source: 'inferred' },
    wet_rooms: { value: 2, source: 'inferred' },
    open_plan: { value: true, source: 'requested' },
    parking_spaces: { value: 2, source: 'inferred' },
    floors: { value: 1, source: 'inferred' },
    built_area_m2: 120,
    footprint_width_m: 10.95,
    footprint_depth_m: 10.95,
    description: 'בית עם 3 חדרי שינה',
    ...overrides,
  }
}

/** Fills the initial project-requirements form exactly as a real user would — the same
 * fields/labels the real UI exposes. Stops BEFORE submitting so a test can open the advanced
 * disclosure first. City/street stay free-text (Autocomplete.tsx just suggests — see its own
 * docstring); typing the exact value directly (as the mock's `/localities`/`/localities/{city}/streets`
 * below are set up to match) is equivalent to clicking that same suggestion.
 */
async function fillForm(builtAreaM2 = '120') {
  fireEvent.change(screen.getByLabelText('עיר / רשות מקומית'), { target: { value: 'תל אביב' } })
  await waitFor(() => expect(screen.getByLabelText('רחוב ומספר')).toBeEnabled())
  fireEvent.change(screen.getByLabelText('רחוב ומספר'), { target: { value: 'הרצל 1' } })
  // The site is entered as DIMENSIONS now — an area cannot say whether a house fits (same area,
  // different shape, different answer) and the setbacks are edge-relative.
  // A parcel that genuinely holds these built areas in one storey: 30 - 2*3 = 24 wide,
  // 34 - 5.5 - 4 = 24.5 deep => 588 m² of geometric one-storey capacity.
  fireEvent.change(screen.getByLabelText("רוחב מגרש (מ')"), { target: { value: '30' } })
  fireEvent.change(screen.getByLabelText("עומק מגרש (מ')"), { target: { value: '34' } })
  fireEvent.change(screen.getByLabelText('שטח בנייה בקומה אחת (טביעת רגל) (מ"ר)'), { target: { value: builtAreaM2 } })
  fireEvent.change(screen.getByLabelText('תיאור הבית הרצוי'), { target: { value: 'בית עם 3 חדרי שינה' } })
}

/** Submits the form. Since feature 006 this CREATES the project and moves straight to the loading
 * screen — there is no outline step in between; the engine chooses the outline itself. */
function submitForm() {
  fireEvent.click(screen.getByRole('button', { name: 'המשך ליצירת התכנון' }))
}

/** Opens the advanced disclosure that hosts the outline cards for a person with a real constraint. */
async function openAdvancedOutline() {
  fireEvent.click(screen.getByRole('button', { name: /מתקדם — קביעת מתאר ידנית/ }))
  await waitFor(() => expect(screen.getByText('קומפקטי')).toBeInTheDocument())
}

/** The fake backend both describes run against — one definition, so a new suite cannot
 * silently exercise a different API from the existing ones. */
function stubBackend() {
  vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input.toString()
        const method = init?.method ?? 'GET'

        if (url === '/localities') {
          return new Response(JSON.stringify(['תל אביב']), { status: 200 })
        }
        if (url.includes('/localities/') && url.endsWith('/streets')) {
          return new Response(JSON.stringify(['הרצל 1']), { status: 200 })
        }
        if (url === '/projects/site/footprint-options' && method === 'POST') {
          // The options are computed by the BACKEND now, from the buildable region. The mock
          // returns the same four proportions the old client-side generator produced, on a site
          // large enough to hold them, so these tests still exercise selection rather than fit.
          const requested = JSON.parse(String(init?.body ?? '{}')).built_area_m2 as number
          return new Response(JSON.stringify({
            plot_width_m: 20, plot_depth_m: 24, street_facing_side: 'NORTH',
            front_setback_m: 5.5, side_setback_m: 3, rear_setback_m: 4,
            setback_disclaimer: 'הנחות תכנון לדמו — אינן מידע תכנוני או רגולטורי מאומת.',
            buildable_width_m: 40, buildable_depth_m: 40, has_buildable_area: true,
            one_storey_footprint_capacity_m2: 1600,
            requested_built_area_m2: requested,
            options: generateFootprintOptions(requested).map((o) => ({
              shape_type: o.shape_type, width_m: o.width_m, depth_m: o.depth_m, area_m2: o.area_m2,
            })),
            rejection: null,
          }), { status: 200 })
        }
        if (url === '/failures' && method === 'POST') {
          return new Response(JSON.stringify({ recorded: true }), { status: 201 })
        }
        if (url === '/projects' && method === 'POST') {
          return new Response(JSON.stringify(fakeProject()), { status: 201 })
        }
        if (url.endsWith('/review') && method === 'GET') {
          return new Response(JSON.stringify(fakeReview()), { status: 200 })
        }
        if (url.endsWith('/requirements') && method === 'POST') {
          return new Response(JSON.stringify(fakeProject({ requirements_parsed_at: '2026-01-01T00:00:00Z' })), { status: 200 })
        }
        if (url.endsWith('/design') && method === 'POST') {
          return new Response(JSON.stringify(fakeProject({ design_generated_at: '2026-01-01T00:00:00Z' })), { status: 200 })
        }
        throw new Error(`unexpected fetch in test: ${method} ${url}`)
      })
    )
}

describe('App — brief + site -> the engine chooses the outline -> plan generation', () => {
  beforeEach(() => {
    stubBackend()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('does NOT call POST /projects merely from filling out the built-area field', async () => {
    render(<App />)
    fireEvent.change(screen.getByLabelText('שטח בנייה בקומה אחת (טביעת רגל) (מ"ר)'), { target: { value: '120' } })
    expect(projectCreatePostCalls()).toHaveLength(0)
  })

  // FEATURE 006. The outline used to be a screen of its own between the form and generation.
  // Measured over the production log, the person's choice planned in 30 % of briefs while each of
  // the engine's own shapes planned in 35–45 % — so the engine chooses, and the screen is gone.
  it('submitting the brief creates the project WITHOUT an outline and goes straight to loading', async () => {
    render(<App />)
    await fillForm('120')
    submitForm()

    await waitFor(() => expect(screen.getByRole('status')).toBeInTheDocument()) // LoadingScreen
    expect(screen.queryByText('בחר/י את מתאר הבניין')).not.toBeInTheDocument()

    const call = projectCreatePostCalls()[0]
    expect(call).toBeTruthy()
    const body = JSON.parse(call[1]!.body as string)
    expect(body).toEqual({
      city: 'תל אביב',
      street: 'הרצל 1',
      plot_area_m2: 1020,
      plot_width_m: 30,
      plot_depth_m: 34,
      street_facing_side: 'NORTH',
      // the form's own defaults, which assert nothing until somebody enters real ones
      setbacks: { front_m: 0, side_m: 0, rear_m: 0 },
      built_area_m2: 120,
      description: 'בית עם 3 חדרי שינה',
      selected_footprint: null,
    })
  })

  it('never fetches outline options unless the advanced disclosure is opened', async () => {
    render(<App />)
    await fillForm('120')
    submitForm()
    await waitFor(() => expect(projectCreatePostCalls()).toHaveLength(1))

    const calls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls as Array<[RequestInfo | URL, RequestInit | undefined]>
    expect(calls.filter((call) => call[0] === '/projects/site/footprint-options')).toHaveLength(0)
  })

  it('the form says the engine chooses the outline, and offers the manual choice as advanced', async () => {
    render(<App />)
    expect(screen.getByText(/המערכת בוחרת את צורת הבניין בעצמה/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /מתקדם — קביעת מתאר ידנית/ })).toBeInTheDocument()
    expect(screen.queryByText('קומפקטי')).not.toBeInTheDocument()
  })

  // THE ADVANCED PATH. A person with a real constraint — a permit tied to a rectangle, a frontage to
  // keep — can still fix the outline. It is the same component the old screen used, inline.
  it('opening the advanced disclosure fetches the site options and shows the outline cards', async () => {
    render(<App />)
    await fillForm('120')
    await openAdvancedOutline()

    expect(screen.getByText('מאוזן')).toBeInTheDocument()
    expect(screen.getByText('רחב')).toBeInTheDocument()
    expect(screen.getByText('צר ומוארך')).toBeInTheDocument()
    expect(screen.getByTestId('footprint-card-custom')).toBeInTheDocument()
    expect(projectCreatePostCalls()).toHaveLength(0)
  })

  it('a chosen advanced outline is sent EXACTLY as displayed — never recomputed for the API call', async () => {
    render(<App />)
    await fillForm('150')
    await openAdvancedOutline()
    const wide = generateFootprintOptions(150).find((option) => option.shape_type === 'WIDE')!

    fireEvent.click(screen.getByText('רחב'))
    submitForm()

    await waitFor(() => expect(projectCreatePostCalls()).toHaveLength(1))
    const body = JSON.parse(projectCreatePostCalls()[0][1]!.body as string)
    expect(body.selected_footprint.source).toBe('PRESET')
    expect(body.selected_footprint.width_m).toBe(wide.width_m)
    expect(body.selected_footprint.depth_m).toBe(wide.depth_m)
    expect(body.selected_footprint.polygon).toHaveLength(4)
  })

  it('a custom advanced outline is sent with its own width and depth, not normalised to a square', async () => {
    render(<App />)
    await fillForm('200')
    await openAdvancedOutline()

    // CUSTOM 8x25 for a 200 m2 target (matches the task's own worked example)
    fireEvent.change(screen.getByTestId('footprint-custom-width'), { target: { value: '8' } })
    fireEvent.change(screen.getByTestId('footprint-custom-depth'), { target: { value: '25' } })
    submitForm()

    await waitFor(() => expect(projectCreatePostCalls()).toHaveLength(1))
    const body = JSON.parse(projectCreatePostCalls()[0][1]!.body as string)
    expect(body.selected_footprint).toEqual({
      source: 'CUSTOM',
      shape_type: 'RECTANGLE',
      target_area_m2: 200,
      width_m: 8,
      depth_m: 25,
      area_m2: 200,
      polygon: [
        { x: 0, y: 0 },
        { x: 8, y: 0 },
        { x: 8, y: 25 },
        { x: 0, y: 25 },
      ],
    })
  })

  it('closing the advanced disclosure drops the chosen outline, so the engine chooses again', async () => {
    render(<App />)
    await fillForm('120')
    await openAdvancedOutline()
    fireEvent.click(screen.getByText('רחב'))
    fireEvent.click(screen.getByRole('button', { name: /מתקדם — קביעת מתאר ידנית/ }))
    expect(screen.queryByText('רחב')).not.toBeInTheDocument()

    submitForm()
    await waitFor(() => expect(projectCreatePostCalls()).toHaveLength(1))
    const body = JSON.parse(projectCreatePostCalls()[0][1]!.body as string)
    expect(body.selected_footprint).toBeNull()
  })

  it('changing the built area drops a chosen advanced outline (it was computed for the old area)', async () => {
    render(<App />)
    await fillForm('120')
    await openAdvancedOutline()
    fireEvent.click(screen.getByText('רחב'))
    fireEvent.change(screen.getByLabelText('שטח בנייה בקומה אחת (טביעת רגל) (מ"ר)'), { target: { value: '150' } })

    submitForm()
    await waitFor(() => expect(projectCreatePostCalls()).toHaveLength(1))
    const body = JSON.parse(projectCreatePostCalls()[0][1]!.body as string)
    expect(body.selected_footprint).toBeNull()
  })

  // REGRESSION: "חזרה לתיאור" used to land on a blank form. Creating the project cleared `form`, so
  // every field the user had just typed was gone. Going back is a normal step in this flow.
  it('going back to the description from REVIEW keeps everything the user entered', async () => {
    render(<App />)
    await fillForm('120')
    submitForm()

    await waitFor(() => expect(screen.getByText('זה מה שהבנתי')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'חזרה לתיאור' }))

    await waitFor(() => expect(screen.getByLabelText('תיאור הבית הרצוי')).toBeInTheDocument())
    expect(screen.getByLabelText('תיאור הבית הרצוי')).toHaveValue('בית עם 3 חדרי שינה')
    expect(screen.getByLabelText('עיר / רשות מקומית')).toHaveValue('תל אביב')
    expect(screen.getByLabelText('רחוב ומספר')).toHaveValue('הרצל 1')
    expect(screen.getByLabelText("רוחב מגרש (מ')")).toHaveValue(30)
    expect(screen.getByLabelText("עומק מגרש (מ')")).toHaveValue(34)
    expect(screen.getByLabelText('שטח בנייה בקומה אחת (טביעת רגל) (מ"ר)')).toHaveValue(120)
  })

  // CATEGORY SEPARATION. The advanced step selects AUTHORITATIVE PHYSICAL INPUT (the building
  // outline) and nothing else: the internal layout is the planner's decision. The request must
  // carry no layout/strategy/concept field for the backend to obey.
  it('the advanced outline is a physical outline, never an internal layout', async () => {
    render(<App />)
    await fillForm('120')
    await openAdvancedOutline()
    expect(screen.getByText(/החלוקה הפנימית/)).toBeInTheDocument()

    fireEvent.click(screen.getByText('קומפקטי'))
    submitForm()
    await waitFor(() => expect(projectCreatePostCalls()).toHaveLength(1))

    const body = JSON.parse(projectCreatePostCalls()[0][1]!.body as string)
    for (const key of ['layout', 'strategy', 'concept', 'layout_strategy', 'concept_strategy']) {
      expect(body).not.toHaveProperty(key)
      expect(body.selected_footprint).not.toHaveProperty(key)
    }
    expect(body.selected_footprint.width_m).toBeGreaterThan(0)
    expect(body.selected_footprint.polygon).toHaveLength(4)
  })
})

describe('one-storey footprint semantics on the form', () => {
  beforeEach(() => {
    stubBackend()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  /** Fills only the site fields, which is all the capacity depends on. */
  /** The PRODUCT default is 0 — it asserts no planning determination. A test whose arithmetic
   *  depends on particular setbacks types them in, the same way a person would. */
  async function siteOnly(width = '15', depth = '20',
                          setbacks: [string, string, string] = ['5.5', '3', '4']) {
    render(<App />)
    fireEvent.change(screen.getByLabelText('עיר / רשות מקומית'), { target: { value: 'תל אביב' } })
    await waitFor(() => expect(screen.getByLabelText('רחוב ומספר')).toBeEnabled())
    fireEvent.change(screen.getByLabelText('רחוב ומספר'), { target: { value: 'הרצל 1' } })
    fireEvent.change(screen.getByLabelText("רוחב מגרש (מ')"), { target: { value: width } })
    fireEvent.change(screen.getByLabelText("עומק מגרש (מ')"), { target: { value: depth } })
    fireEvent.change(screen.getByLabelText("חזית (מ')"), { target: { value: setbacks[0] } })
    fireEvent.change(screen.getByLabelText("צדדים (מ')"), { target: { value: setbacks[1] } })
    fireEvent.change(screen.getByLabelText("אחורית (מ')"), { target: { value: setbacks[2] } })
  }

  const AREA_FIELD = 'שטח בנייה בקומה אחת (טביעת רגל) (מ"ר)'

  it('names the field as a one-storey footprint, not an unqualified built area', async () => {
    await siteOnly()
    // the old label promised something the demo does not plan: a total across floors
    expect(screen.queryByLabelText('שטח הבנייה (מ"ר)')).toBeNull()
    expect(screen.getByLabelText(AREA_FIELD)).toBeInTheDocument()
  })

  it('shows the geometric one-storey capacity for the entered site', async () => {
    await siteOnly('15', '20')
    // 15 - 2*3 = 9.00 wide, 20 - 5.5 - 4 = 10.50 deep -> 94.50 m²
    expect(screen.getByText(/קיבולת מתאר גאומטרית לקומה אחת/)).toBeInTheDocument()
    expect(screen.getByText('94.50 מ"ר')).toBeInTheDocument()
    expect(screen.getByText('9.00 × 10.50')).toBeInTheDocument()
  })

  it('warns while the value is being typed, not three screens later', async () => {
    await siteOnly('15', '20')
    fireEvent.change(screen.getByLabelText(AREA_FIELD), { target: { value: '250' } })
    // the exact case that was reported: 250 m² on a 15 x 20 plot
    expect(screen.getByText(/השטח שהוזן גדול מכך ולא ייכנס בקומה אחת/)).toBeInTheDocument()
  })

  it('blocks continuing and names both levers', async () => {
    await siteOnly('15', '20')
    fireEvent.change(screen.getByLabelText(AREA_FIELD), { target: { value: '250' } })
    fireEvent.change(screen.getByLabelText('תיאור הבית הרצוי'), { target: { value: 'בית' } })
    submitForm()

    expect(screen.getByText(/קיבולת מתאר גאומטרית/, { selector: 'li' })).toBeInTheDocument()
    expect(screen.getByText(/להקטין את השטח המבוקש או לעדכן את הנחות הנסיגה כאן/)).toBeInTheDocument()
    expect(projectCreatePostCalls()).toHaveLength(0)
  })

  it('the setback assumptions are on this screen, labelled, and change the capacity', async () => {
    await siteOnly('15', '20')
    expect(screen.getByText('הנחות תכנון לדמו — אינן מידע תכנוני או רגולטורי מאומת.')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText("חזית (מ')"), { target: { value: '3' } })
    fireEvent.change(screen.getByLabelText("אחורית (מ')"), { target: { value: '2' } })
    // 15 - 2*3 = 9.00 wide still, 20 - 3 - 2 = 15.00 deep now
    // 20 - 3 - 2 = 15.00 deep now
    expect(screen.getByText('9.00 × 15.00')).toBeInTheDocument()
    expect(screen.getByText('135.00 מ"ר')).toBeInTheDocument()
  })

  it('an area within capacity is accepted and carries the assumptions onward', async () => {
    await siteOnly('30', '34')
    fireEvent.change(screen.getByLabelText(AREA_FIELD), { target: { value: '140' } })
    fireEvent.change(screen.getByLabelText('תיאור הבית הרצוי'), { target: { value: 'בית' } })
    // The assumptions reach the backend on the project itself (see the flow tests above); the
    // advanced outline options are computed under the SAME assumptions the person entered.
    await openAdvancedOutline()
    const optionsCall = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.find(
      (call: unknown[]) => call[0] === '/projects/site/footprint-options',
    ) as [string, RequestInit]
    expect(JSON.parse(String(optionsCall[1].body))).toMatchObject({
      plot_width_m: 30, plot_depth_m: 34, built_area_m2: 140,
      front_setback_m: 5.5, side_setback_m: 3, rear_setback_m: 4,
    })
  })
})
