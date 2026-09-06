import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'
import '@testing-library/jest-dom/vitest'

// `test.globals` is off (explicit imports everywhere else in this project) — `@testing-library/react`'s
// automatic per-test `cleanup()` only self-registers when it finds a global `afterEach`, so without
// this it silently never runs and DOM nodes leak across tests within the same file.
afterEach(() => {
  cleanup()
})
