import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import QualityPanel from './QualityPanel'
import type { DemoQuality } from '../../design/demoDesign'

/** AC-1: the panel renders the six M-values, dead space and wasted circulation from a fixture
 * contract, and is entirely absent when the backend attached no `metrics` (a payload predating
 * Issue #17). No value here is computed — every assertion checks a number this fixture supplies. */

const fixtureQuality: DemoQuality = {
  over_preferred: false,
  signal: [],
  notices: [],
  metrics: {
    m1_habitable_aspect_median: 1.4,
    m1_habitable_aspect_max: 2.1,
    m2_habitable_on_envelope_ratio: 0.83,
    m3_circulation_share: 0.11,
    m4_hall_door_count: 4,
    m4_hall_aspect_median: 3.2,
    m5_wet_adjacency_ratio: 0.5,
    m6_public_zone_contiguous: true,
    dead_space_m2: 0,
    wasted_circulation_share: 0.02,
    corpus_median: {
      m3_circulation_share_median: 0.105,
      m4_hall_aspect_median: 9.3,
      m5_wet_adjacency_share: 0.43,
      m6_public_contiguous_share: 0.53,
    },
  },
  exposure: [],
  wet_privacy: [],
}

describe('QualityPanel', () => {
  it('renders the six M-values, dead space and wasted circulation from the contract', () => {
    render(<QualityPanel quality={fixtureQuality} />)

    expect(screen.getByText('מדדי איכות אדריכלית')).toBeInTheDocument()
    expect(screen.getByText('חציון 1.40, מקסימום 2.10')).toBeInTheDocument()
    expect(screen.getByText('83%')).toBeInTheDocument()
    expect(screen.getByText('11%')).toBeInTheDocument()
    expect(screen.getByText('יחס 3.20, 4 דלתות')).toBeInTheDocument()
    expect(screen.getByText('50%')).toBeInTheDocument()
    expect(screen.getByText('כן')).toBeInTheDocument()
    expect(screen.getByText('0.00 מ״ר')).toBeInTheDocument()
    expect(screen.getByText('2%')).toBeInTheDocument()
  })

  it('shows the corpus median beside a metric when the contract carries one', () => {
    render(<QualityPanel quality={fixtureQuality} />)

    expect(screen.getByText('חציון קורפוס: 11%')).toBeInTheDocument()
    expect(screen.getByText('חציון קורפוס: 9.30')).toBeInTheDocument()
  })

  it('omits the corpus-median line for a metric the contract does not attach one for', () => {
    const withoutCorpus: DemoQuality = {
      ...fixtureQuality,
      metrics: { ...fixtureQuality.metrics!, corpus_median: null },
    }
    render(<QualityPanel quality={withoutCorpus} />)

    expect(screen.queryByText(/חציון קורפוס/)).toBeNull()
  })

  it('renders nothing when quality.metrics is null', () => {
    const { container } = render(<QualityPanel quality={{ over_preferred: false, signal: [], notices: [], metrics: null }} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when quality itself is absent', () => {
    const { container } = render(<QualityPanel quality={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})
