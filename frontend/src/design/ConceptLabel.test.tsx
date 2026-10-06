import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import ConceptLabel from './ConceptLabel'
import type { DemoConcept } from './demoDesign'

/** AC-5: the ReviewPage renders the concept label for each plan. `ConceptLabel` is the one place
 * that reads `DemoDesign.concept`, so these tests exercise it directly. */

const fixtureConcept: DemoConcept = {
  circulation_class: 'HUB_LOBBY',
  label: 'מבואת חדרים',
  rationale: 'החדרים נפתחים סביב מבואה קומפקטית.',
}

describe('ConceptLabel', () => {
  it('renders the label and carries the rationale as a hover title', () => {
    render(<ConceptLabel concept={fixtureConcept} />)

    const label = screen.getByTestId('concept-label')
    expect(label).toHaveTextContent('מבואת חדרים')
    expect(label).toHaveAttribute('title', 'החדרים נפתחים סביב מבואה קומפקטית.')
  })

  it('renders nothing when the backend attached no concept (flag off)', () => {
    render(<ConceptLabel concept={null} />)

    expect(screen.queryByTestId('concept-label')).not.toBeInTheDocument()
  })

  it('renders nothing when concept is undefined (a payload predating this field)', () => {
    render(<ConceptLabel />)

    expect(screen.queryByTestId('concept-label')).not.toBeInTheDocument()
  })
})
