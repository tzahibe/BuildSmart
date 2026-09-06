import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

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

/** Fills and submits the initial project-requirements form exactly as a real user would — the same
 * fields/labels the real UI exposes (see e2e/spatial-edit.spec.ts's own helper for the real-backend
 * equivalent of this). Stops right after submission, at the new FOOTPRINT SELECTION step — this
 * test suite's whole point is to check what appears there and that nothing beyond it is needed to
 * exercise it, so it deliberately does not fill in city/street autocomplete lists (this app's
 * `/localities` returns `[]` in every test here, which leaves the free-text fields ungated).
 */
async function fillAndSubmitForm(builtAreaM2 = '120') {
  fireEvent.change(screen.getByLabelText('עיר / רשות מקומית'), { target: { value: 'תל אביב' } })
  fireEvent.change(screen.getByLabelText('רחוב ומספר'), { target: { value: 'הרצל 1' } })
  fireEvent.change(screen.getByLabelText('שטח מגרש (מ"ר)'), { target: { value: '400' } })
  fireEvent.change(screen.getByLabelText('שטח הבנייה (מ"ר)'), { target: { value: builtAreaM2 } })
  fireEvent.change(screen.getByLabelText('תיאור הבית הרצוי'), { target: { value: 'בית עם 3 חדרי שינה' } })
  fireEvent.click(screen.getByRole('button', { name: 'המשך לבחירת צורת המבנה' }))
  await waitFor(() => expect(screen.getByText('בחר/י את צורת המבנה')).toBeInTheDocument())
}

describe('App — project creation -> FOOTPRINT SELECTION -> plan generation', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input.toString()
        const method = init?.method ?? 'GET'

        if (url === '/localities') {
          return new Response(JSON.stringify([]), { status: 200 })
        }
        if (url === '/projects' && method === 'POST') {
          return new Response(JSON.stringify(fakeProject()), { status: 201 })
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
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('does NOT call POST /projects merely from filling out the built-area field', async () => {
    render(<App />)
    fireEvent.change(screen.getByLabelText('שטח הבנייה (מ"ר)'), { target: { value: '120' } })
    expect(projectCreatePostCalls()).toHaveLength(0)
  })

  it('shows footprint choices once the target built area is known, before any generation starts', async () => {
    render(<App />)
    await fillAndSubmitForm('120')

    // Several distinct footprint cards, each with its own name/dimensions — never a single implied
    // square. No POST /projects has happened yet at this point (still no backend call for the choice).
    expect(screen.getByText('קומפקטי')).toBeInTheDocument()
    expect(screen.getByText('מאוזן')).toBeInTheDocument()
    expect(screen.getByText('רחב')).toBeInTheDocument()
    expect(screen.getByText('צר ומוארך')).toBeInTheDocument()
    expect(screen.getByTestId('footprint-card-custom')).toBeInTheDocument()

    expect(projectCreatePostCalls()).toHaveLength(0)
  })

  it('"back" returns to the form without having created a project, and editing built area is safe', async () => {
    render(<App />)
    await fillAndSubmitForm('120')
    fireEvent.click(screen.getByText('רחב'))
    fireEvent.click(screen.getByText('‹ חזרה לעריכת שטח הבנייה'))

    expect(screen.getByLabelText('שטח הבנייה (מ"ר)')).toHaveValue(120)

    // going forward again shows freshly (re)generated options, and nothing was ever created
    fireEvent.click(screen.getByRole('button', { name: 'המשך לבחירת צורת המבנה' }))
    await waitFor(() => expect(screen.getByText('בחר/י את צורת המבנה')).toBeInTheDocument())
    expect(projectCreatePostCalls()).toHaveLength(0)
  })

  it('existing flow remains functional end to end: confirming a footprint creates the project and starts generation', async () => {
    render(<App />)
    await fillAndSubmitForm('120')
    fireEvent.click(screen.getByText('קומפקטי'))
    fireEvent.click(screen.getByRole('button', { name: 'המשך ליצירת התכנון' }))

    await waitFor(() => expect(screen.getByRole('status')).toBeInTheDocument()) // LoadingScreen

    const call = projectCreatePostCalls()[0]
    expect(call).toBeTruthy()
    const body = JSON.parse(call[1]!.body as string)
    expect(body).toEqual({
      city: 'תל אביב',
      street: 'הרצל 1',
      plot_area_m2: 400,
      built_area_m2: 120,
      description: 'בית עם 3 חדרי שינה',
    })
    // the selected footprint is NOT sent to POST /projects — no backend support exists for it yet
    // (see FOOTPRINT SELECTION task's own reported backend gap); it must not be smuggled into an
    // unrelated existing field either.
    expect(Object.keys(body)).toEqual(['city', 'street', 'plot_area_m2', 'built_area_m2', 'description'])
  })
})
