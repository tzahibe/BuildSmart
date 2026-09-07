import { useState, type KeyboardEvent } from 'react'
import './Autocomplete.css'

interface AutocompleteProps {
  value: string
  onChange: (value: string) => void
  options: string[]
  disabled?: boolean
  required?: boolean
  placeholder?: string
  maxSuggestions?: number
}

/** A real, custom-rendered suggestion dropdown over a free-text input — replaces the native
 * `<input list="..."> + <datalist>` combo this field used to be. That combo LOOKED like an
 * autocomplete but never forced the input's actual value to become one of the suggestions: several
 * real entries in this dataset don't match how people naturally type them (e.g. the city is stored
 * as "תל אביב - יפו", not "תל אביב"), so a user who typed the natural short form and moved on ended
 * up with a value matching nothing — the street field then silently stayed disabled forever, with no
 * indication why. Here, every suggestion is a real, clickable DOM element: clicking (or arrowing to)
 * one always sets the field's value to that EXACT option text, so "I picked a suggestion" and "the
 * value is a real match" can never drift apart. Free typing to filter is preserved — this only fixes
 * how a selection actually lands, not the ability to type at all. */
function Autocomplete({ value, onChange, options, disabled, required, placeholder, maxSuggestions = 8 }: AutocompleteProps) {
  const [open, setOpen] = useState(false)
  const [highlighted, setHighlighted] = useState(0)

  const trimmed = value.trim()
  const matches = (trimmed === '' ? options : options.filter((option) => option.includes(trimmed))).slice(0, maxSuggestions)

  function selectOption(option: string) {
    onChange(option)
    setOpen(false)
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (!open) {
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        setOpen(true)
        setHighlighted(0)
      }
      return
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setHighlighted((prev) => Math.min(prev + 1, matches.length - 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setHighlighted((prev) => Math.max(prev - 1, 0))
    } else if (event.key === 'Enter') {
      if (matches[highlighted]) {
        event.preventDefault()
        selectOption(matches[highlighted])
      }
    } else if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className="autocomplete">
      <input
        type="text"
        autoComplete="off"
        required={required}
        disabled={disabled}
        placeholder={placeholder}
        value={value}
        onChange={(event) => {
          onChange(event.target.value)
          setOpen(true)
          setHighlighted(0)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
        role="combobox"
        aria-expanded={open && matches.length > 0}
        aria-autocomplete="list"
      />
      {open && matches.length > 0 && (
        <ul className="autocomplete__list" role="listbox">
          {matches.map((option, index) => (
            <li
              key={option}
              role="option"
              aria-selected={index === highlighted}
              className={
                index === highlighted ? 'autocomplete__option autocomplete__option--highlighted' : 'autocomplete__option'
              }
              // onMouseDown (not onClick) + preventDefault: stops the input from ever blurring on
              // this click, so there is no race between "blur closes the list" and "click selects
              // from it" — the classic way this exact kind of dropdown breaks.
              onMouseDown={(event) => {
                event.preventDefault()
                selectOption(option)
              }}
              onMouseEnter={() => setHighlighted(index)}
            >
              {option}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default Autocomplete
