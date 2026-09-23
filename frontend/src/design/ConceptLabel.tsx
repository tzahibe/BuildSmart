import type { DemoConcept } from './demoDesign'
import './ConceptLabel.css'

/** One plan's concept, beside its title (Issue #78, Concept Engine v2 4/5, AC-5).
 *
 * Renders nothing when `concept` is absent — the backend only attaches `DemoDesign.concept` when
 * `CONCEPT_ENGINE_V2_ENABLED` is on, so a flag-off payload (or one from before this field existed)
 * shows exactly what it showed before this Issue. The rationale sentence is a `title` attribute
 * (a hover), never a second line, so the plan title's own layout is unaffected either way.
 */
function ConceptLabel({ concept }: { concept?: DemoConcept | null }) {
  if (!concept) {
    return null
  }
  return (
    <span className="concept-label" title={concept.rationale} data-testid="concept-label">
      {concept.label}
    </span>
  )
}

export default ConceptLabel
