import './Menu.css'

interface MenuProps {
  open: boolean
  onToggle: () => void
  onOpenDetails: () => void
}

/** User Story 4's menu: a toggle button revealing a dropdown that navigates to Technical Details
 * (FR-014). `open` is owned by DesignPage so it joins the same mutually-exclusive-overlay set as the
 * full-screen sketch and chat panel (spec.md's Edge Cases). */
function Menu({ open, onToggle, onOpenDetails }: MenuProps) {
  return (
    <div className="design-menu" dir="rtl">
      <button
        type="button"
        className="design-menu__toggle"
        onClick={onToggle}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="תפריט"
      >
        ☰
      </button>

      {open && (
        <div className="design-menu__dropdown" role="menu">
          <button type="button" className="design-menu__item" role="menuitem" onClick={onOpenDetails}>
            פרטים טכניים
          </button>
        </div>
      )}
    </div>
  )
}

export default Menu
