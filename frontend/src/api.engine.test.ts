/** The engine preview's REQUEST contract: production sends no parameter, the Concept Engine sends
 * an explicit one, and no fallback is ever allowed to change which engine ran. */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { generateDemoDesign, generateDemoDesignStreaming } from './api'

const ok = (body: unknown) =>
  ({ ok: true, json: async () => body, body: undefined }) as unknown as Response

afterEach(() => vi.unstubAllGlobals())

describe('engine selection on the wire', () => {
  it('sends NO engine parameter for production — the request is the one that always went out', async () => {
    const urls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (url: string) => { urls.push(url); return ok({ plan: {} }) }))
    await generateDemoDesign('p1')
    await generateDemoDesign('p1', 'production')
    expect(urls).toEqual(['/projects/p1/design/demo', '/projects/p1/design/demo'])
  })

  it('sends an explicit engine for the Concept Engine preview', async () => {
    const urls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (url: string) => { urls.push(url); return ok({ plan: {} }) }))
    await generateDemoDesign('p1', 'concept_engine_v2')
    expect(urls).toEqual(['/projects/p1/design/demo?engine=concept_engine_v2'])
  })

  it('carries the engine through the stream fallback — a fallback may cost the percentage, never the engine', async () => {
    const urls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      urls.push(url)
      if (url.includes('/stream')) throw new TypeError('no stream here')
      return ok({ plan: {} })
    }))
    await generateDemoDesignStreaming('p1', () => {}, 'concept_engine_v2')
    expect(urls[0]).toBe('/projects/p1/design/demo/stream?engine=concept_engine_v2')
    expect(urls[1]).toBe('/projects/p1/design/demo?engine=concept_engine_v2')
  })

  it('carries the engine when the stream responds without a readable body', async () => {
    const urls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (url: string) => { urls.push(url); return ok({ plan: {} }) }))
    await generateDemoDesignStreaming('p1', () => {}, 'concept_engine_v2')
    expect(urls.every((u) => u.includes('engine=concept_engine_v2'))).toBe(true)
  })
})
