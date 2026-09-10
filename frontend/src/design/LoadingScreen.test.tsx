import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import LoadingScreen from './LoadingScreen'
import { generateDemoDesignStreaming } from '../api'

/** The percentage exists to report work that genuinely happened. These tests hold that line: a
 * number is shown when the backend reported a stage, and no number is shown when it did not. */
describe('LoadingScreen progress indicator', () => {
  it('shows the percentage and the stage the backend reported', () => {
    render(<LoadingScreen progress={{ step: 4, total: 6, label: 'מוסיפים דלתות וחלונות', percent: 67 }} />)

    expect(screen.getByText('67%')).toBeInTheDocument()
    expect(screen.getByText('4/6')).toBeInTheDocument()
    expect(screen.getByText('מוסיפים דלתות וחלונות')).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '67')
  })

  it('shows NO percentage until a stage is reported', () => {
    render(<LoadingScreen />)

    expect(screen.queryByRole('progressbar')).toBeNull()
    expect(screen.queryByText(/%/)).toBeNull()
    expect(screen.getByText('בונים את הבית שלך...')).toBeInTheDocument()
  })

  it('shows the error instead of a percentage when generation failed', () => {
    render(<LoadingScreen error="נפילה" progress={{ step: 3, total: 6, label: 'x', percent: 50 }} />)

    expect(screen.getByText('נפילה')).toBeInTheDocument()
    expect(screen.queryByRole('progressbar')).toBeNull()
  })
})

function sseStream(frames: string[]): Response {
  const encoder = new TextEncoder()
  let i = 0
  return {
    ok: true,
    body: {
      getReader: () => ({
        read: async () =>
          i < frames.length
            ? { done: false, value: encoder.encode(frames[i++]) }
            : { done: true, value: undefined },
      }),
    },
  } as unknown as Response
}

describe('generateDemoDesignStreaming', () => {
  it('reports every stage as it arrives and resolves the plan', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseStream([
      'event: progress\ndata: {"step":1,"total":6,"label":"א","percent":17}\n\n',
      'event: progress\ndata: {"step":2,"total":6,"label":"ב","percent":33}\n\n',
      'event: done\ndata: {"plan":{"id":"p"},"alternatives":[]}\n\n',
    ])))
    const seen: number[] = []

    const plan = await generateDemoDesignStreaming('pid', (p) => seen.push(p.percent))

    expect(seen).toEqual([17, 33])
    expect((plan as unknown as { plan: { id: string } }).plan.id).toBe('p')
  })

  it('handles a frame split across two chunks', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseStream([
      'event: progress\ndata: {"step":1,"tot',
      'al":6,"label":"א","percent":17}\n\nevent: done\ndata: {"plan":{},"alternatives":[]}\n\n',
    ])))
    const seen: number[] = []

    await generateDemoDesignStreaming('pid', (p) => seen.push(p.percent))

    expect(seen).toEqual([17])
  })

  it('raises the backend refusal as a DemoPipelineError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseStream([
      'event: progress\ndata: {"step":1,"total":6,"label":"א","percent":17}\n\n',
      'event: error\ndata: {"code":"PLAN_NOT_REALIZABLE","message":"לא ניתן","detail":"why"}\n\n',
    ])))

    await expect(generateDemoDesignStreaming('pid', () => {})).rejects.toMatchObject({
      code: 'PLAN_NOT_REALIZABLE',
      message: 'לא ניתן',
      detail: 'why',
    })
  })

  it('falls back to the plain endpoint when the stream is unusable, and still returns a plan', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 404, json: async () => ({}) } as unknown as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ plan: { id: 'fallback' }, alternatives: [] }) } as unknown as Response)
    vi.stubGlobal('fetch', fetchMock)

    const plan = await generateDemoDesignStreaming('pid', () => {})

    expect(fetchMock.mock.calls[0][0]).toBe('/projects/pid/design/demo/stream')
    expect(fetchMock.mock.calls[1][0]).toBe('/projects/pid/design/demo')
    expect((plan as unknown as { plan: { id: string } }).plan.id).toBe('fallback')
  })

  it('does not resolve an empty plan when the connection drops mid-generation', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseStream([
      'event: progress\ndata: {"step":2,"total":6,"label":"ב","percent":33}\n\n',
    ])))

    await expect(generateDemoDesignStreaming('pid', () => {})).rejects.toMatchObject({
      code: 'STREAM_INCOMPLETE',
    })
  })
})
