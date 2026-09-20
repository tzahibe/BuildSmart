import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import RefusalNotice from './RefusalNotice'

/** AC-3: a refused design shows the backend's refusal code AND its human sentence — never a
 * generic failure message that hides which check actually stopped generation. */
describe('RefusalNotice', () => {
  it("shows the backend's code and human sentence", () => {
    render(
      <RefusalNotice
        code="CORRIDOR_WIDTH_NOT_FEASIBLE"
        message="מסדרון ברוחב 1.80 מ׳ לא נכנס יחד עם החדרים שביקשת."
        detail="C19; C24"
      />,
    )

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('מסדרון ברוחב 1.80 מ׳ לא נכנס יחד עם החדרים שביקשת.')).toBeInTheDocument()
    expect(screen.getByText('קוד: CORRIDOR_WIDTH_NOT_FEASIBLE')).toBeInTheDocument()
    expect(screen.getByText('C19; C24')).toBeInTheDocument()
  })

  it('omits the detail line when the backend sent none', () => {
    render(<RefusalNotice code="LAUNDRY_UNPLACEABLE" message="לא ניתן היה למקם את חדר הכביסה." />)

    expect(screen.getByText('קוד: LAUNDRY_UNPLACEABLE')).toBeInTheDocument()
    expect(screen.queryByText('C19; C24')).toBeNull()
  })
})
