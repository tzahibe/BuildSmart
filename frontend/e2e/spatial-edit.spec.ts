import { expect, test, type Page } from '@playwright/test'

/** End-to-end validation of the real spatial-edit flow, through the actual application UI and the
 * real backend (no mocks): fill the real project-creation form -> real parse+generate pipeline ->
 * DesignPage renders the real `GeometricDesign` -> SpatialEditControls issues a real
 * `POST /projects/{id}/design/spatial-edit` -> the returned `GeometricDesign` is read back from the
 * DOM (not merely screenshotted) to confirm the client actually re-rendered it.
 *
 * Fixture note: `CITY`/`STREET`/`BUILT_AREA_M2`/`DESCRIPTION` below drive `MockArchitectModelGateway`
 * + the real `GeometrySolver`, both fully deterministic — this exact input reliably reproduces the
 * exact 5-room layout asserted in `EXPECTED_BASELINE` (verified by generating it repeatedly via the
 * real API before writing this test). If a future change to the mock gateway or solver changes that
 * output, this test's baseline assertion will fail LOUDLY and by design — see this test's first
 * assertion — rather than silently asserting against stale coordinates.
 *
 * Per BUILDSMART's own real-data limitation: GeometrySolver's packing leaves every room in this
 * (and every other layout sampled) with zero WEST slack — moving ANY room WEST is expected to be
 * genuinely REJECTED, not a bug to work around. NORTH/EAST/SOUTH each have at least one room with
 * real slack in this exact layout, used for the APPLIED scenarios below.
 */

const CITY = 'מודיעין-מכבים-רעות'
const STREET = 'אגוז מכבים רעות'
const BUILT_AREA_M2 = 110
const DESCRIPTION = 'בית עם 2 חדרי שינה'

const EXPECTED_BASELINE: Record<string, { x: number; y: number; w: number; h: number }> = {
  LIVING_ROOM: { x: 0, y: 0, w: 4.4721, h: 4.4721 },
  BATHROOM: { x: 0, y: 4.4721, w: 2.2361, h: 2.2361 },
  BEDROOM_1: { x: 0, y: 6.7082, w: 3.4641, h: 3.4641 },
  BEDROOM_2: { x: 3.4641, y: 6.7082, w: 3.4641, h: 3.4641 },
  KITCHEN: { x: 4.4721, y: 0, w: 2.9277, h: 4.0988 },
}
const ROOM_IDS = Object.keys(EXPECTED_BASELINE)
// `toBeCloseTo` precision (decimal digits) used for round-trip / equality assertions throughout —
// matches this project's existing numeric tolerance convention (areas/dims rounded to 2 decimals).
const DECIMAL_PRECISION = 2

async function createDesignThroughRealUI(page: Page) {
  await page.goto('/')

  await page.getByLabel('עיר / רשות מקומית').fill(CITY)
  const streetInput = page.getByLabel('רחוב ומספר')
  await expect(streetInput).toBeEnabled({ timeout: 10_000 })
  await streetInput.fill(STREET)

  await page.getByLabel('שטח מגרש (מ"ר)').fill('500')
  await page.getByLabel('שטח הבנייה (מ"ר)').fill(String(BUILT_AREA_M2))
  await page.getByLabel('תיאור הבית הרצוי').fill(DESCRIPTION)

  await page.getByRole('button', { name: 'צור פרויקט' }).click()

  // Loading screen runs the real parse + generate pipeline against the real backend.
  await expect(page.locator('.sketch-svg').first()).toBeVisible({ timeout: 20_000 })
  await expect(page.getByTestId('spatial-edit-room-select')).toBeVisible()
}

function roomRect(page: Page, roomId: string) {
  return page.getByTestId(`room-rect-${roomId}`)
}

async function readRoomGeometry(page: Page, roomId: string) {
  const rect = roomRect(page, roomId)
  const [x, y, w, h] = await Promise.all([
    rect.getAttribute('x'),
    rect.getAttribute('y'),
    rect.getAttribute('width'),
    rect.getAttribute('height'),
  ])
  return { x: Number(x), y: Number(y), w: Number(w), h: Number(h) }
}

async function readAllRoomGeometry(page: Page) {
  const result: Record<string, { x: number; y: number; w: number; h: number }> = {}
  for (const id of ROOM_IDS) {
    result[id] = await readRoomGeometry(page, id)
  }
  return result
}

/** Selects the room + distance, issues the move via the real UI control, and returns the real
 * network response of `POST /design/spatial-edit` — the actual authoritative result, not an
 * assumption about what the UI did with it. */
async function issueMoveThroughUI(page: Page, roomId: string, direction: 'NORTH' | 'SOUTH' | 'EAST' | 'WEST', distanceM = 1) {
  await page.getByTestId('spatial-edit-room-select').selectOption(roomId)
  await page.getByTestId('spatial-edit-distance').fill(String(distanceM))

  const responsePromise = page.waitForResponse(
    (res) => res.url().includes('/design/spatial-edit') && res.request().method() === 'POST'
  )
  await page.getByTestId(`spatial-edit-direction-${direction.toLowerCase()}`).click()
  return responsePromise
}

test.describe('Spatial edit — real UI + real backend', () => {
  test('directional moves, round trips, rejection atomicity, and sequential edits', async ({ page }) => {
    await createDesignThroughRealUI(page)

    // --- Baseline: confirm the deterministic fixture assumption before relying on it -------------
    const before = await readAllRoomGeometry(page)
    for (const id of ROOM_IDS) {
      expect(before[id].x, `${id}.x baseline`).toBeCloseTo(EXPECTED_BASELINE[id].x, 2)
      expect(before[id].y, `${id}.y baseline`).toBeCloseTo(EXPECTED_BASELINE[id].y, 2)
      expect(before[id].w, `${id}.w baseline`).toBeCloseTo(EXPECTED_BASELINE[id].w, 2)
      expect(before[id].h, `${id}.h baseline`).toBeCloseTo(EXPECTED_BASELINE[id].h, 2)
    }

    await test.step('NORTH: BEDROOM_2 has real north slack -> APPLIED', async () => {
      const response = await issueMoveThroughUI(page, 'BEDROOM_2', 'NORTH', 1)
      expect(response.status()).toBe(200)
      const body = await response.json()
      const backendRoom = body.rooms.find((r: { id: string }) => r.id === 'BEDROOM_2')

      const after = await readRoomGeometry(page, 'BEDROOM_2')
      // NORTH => new y < old y (task's directional assertion), and no manual reload happened anywhere.
      expect(after.y).toBeLessThan(before.BEDROOM_2.y)
      expect(after.y).toBeCloseTo(before.BEDROOM_2.y - 1, 2)
      expect(after.x).toBeCloseTo(before.BEDROOM_2.x, 2)
      // width/depth unchanged by a pure translation
      expect(after.w).toBeCloseTo(before.BEDROOM_2.w, 2)
      expect(after.h).toBeCloseTo(before.BEDROOM_2.h, 2)
      // the DOM reflects EXACTLY the backend's own returned geometry, not just "some" new value
      expect(after.x).toBeCloseTo(backendRoom.x, 3)
      expect(after.y).toBeCloseTo(backendRoom.y, 3)

      // unrelated rooms did not move
      const others = await readAllRoomGeometry(page)
      for (const id of ROOM_IDS.filter((r) => r !== 'BEDROOM_2')) {
        expect(others[id], `${id} unrelated to BEDROOM_2 move`).toEqual(before[id])
      }
    })

    await test.step('round trip: SOUTH 1m returns BEDROOM_2 to its original position', async () => {
      const response = await issueMoveThroughUI(page, 'BEDROOM_2', 'SOUTH', 1)
      expect(response.status()).toBe(200)
      const after = await readRoomGeometry(page, 'BEDROOM_2')
      expect(after.x).toBeCloseTo(before.BEDROOM_2.x, DECIMAL_PRECISION)
      expect(after.y).toBeCloseTo(before.BEDROOM_2.y, DECIMAL_PRECISION)
    })

    await test.step('EAST: BATHROOM has real east slack -> APPLIED, twice sequentially', async () => {
      let response = await issueMoveThroughUI(page, 'BATHROOM', 'EAST', 1)
      expect(response.status()).toBe(200)
      let after = await readRoomGeometry(page, 'BATHROOM')
      expect(after.x).toBeGreaterThan(before.BATHROOM.x)
      expect(after.x).toBeCloseTo(before.BATHROOM.x + 1, 2)
      expect(after.y).toBeCloseTo(before.BATHROOM.y, 2)

      // Sequential accepted edit #2, building on the first — UI must still be usable/responsive.
      response = await issueMoveThroughUI(page, 'BATHROOM', 'EAST', 1)
      expect(response.status()).toBe(200)
      after = await readRoomGeometry(page, 'BATHROOM')
      expect(after.x).toBeCloseTo(before.BATHROOM.x + 2, 2)
    })

    await test.step('round trip: WEST 1m twice returns BATHROOM to its original x (EAST-then-WEST, since WEST-first has no real slack anywhere in this layout — see module docstring)', async () => {
      let response = await issueMoveThroughUI(page, 'BATHROOM', 'WEST', 1)
      expect(response.status()).toBe(200)
      response = await issueMoveThroughUI(page, 'BATHROOM', 'WEST', 1)
      expect(response.status()).toBe(200)
      const after = await readRoomGeometry(page, 'BATHROOM')
      expect(after.x).toBeCloseTo(before.BATHROOM.x, DECIMAL_PRECISION)
      expect(after.y).toBeCloseTo(before.BATHROOM.y, DECIMAL_PRECISION)
    })

    await test.step('SOUTH: KITCHEN has real south slack -> APPLIED', async () => {
      const response = await issueMoveThroughUI(page, 'KITCHEN', 'SOUTH', 1)
      expect(response.status()).toBe(200)
      const after = await readRoomGeometry(page, 'KITCHEN')
      expect(after.y).toBeGreaterThan(before.KITCHEN.y)
      expect(after.y).toBeCloseTo(before.KITCHEN.y + 1, 2)
      expect(after.x).toBeCloseTo(before.KITCHEN.x, 2)
    })

    await test.step('WEST on LIVING_ROOM (x=0, zero slack everywhere in this layout) -> honest REJECTION, no partial mutation', async () => {
      // Snapshot every room immediately before this specific move (not the test's original baseline —
      // BATHROOM/BEDROOM_2/KITCHEN already moved in earlier steps above).
      const immediatelyBefore = await readAllRoomGeometry(page)

      const response = await issueMoveThroughUI(page, 'LIVING_ROOM', 'WEST', 1)
      expect(response.status()).toBeGreaterThanOrEqual(400)

      const rejection = await response.json()
      expect(['ROOM_NOT_FOUND', 'OUT_OF_BOUNDS', 'OVERLAP', 'CONSTRAINT_VIOLATION']).toContain(rejection.detail.error)

      // Plan is provably unchanged — every room, not just the one that was targeted.
      const afterRejection = await readAllRoomGeometry(page)
      for (const id of ROOM_IDS) {
        expect(afterRejection[id], `${id} must be untouched by a rejected edit`).toEqual(immediatelyBefore[id])
      }

      // User sees an error, via the app's existing inline error convention — no new notification system.
      await expect(page.getByTestId('spatial-edit-error')).toBeVisible()
    })

    // No `page.reload()` call appears anywhere in this test — every assertion above ran against the
    // SAME page instance across 7 sequential edit attempts, proving the SVG re-renders from client
    // state alone and the UI stays usable across repeated interactions.
  })

  test('responsive smoke test: an applied move still renders correctly at tablet and mobile widths', async ({ page }) => {
    await createDesignThroughRealUI(page)

    await test.step('desktop baseline', async () => {
      await page.setViewportSize({ width: 1280, height: 900 })
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth)
      expect(scrollWidth).toBeLessThanOrEqual(1280)
    })

    const response = await issueMoveThroughUI(page, 'BATHROOM', 'EAST', 1)
    expect(response.status()).toBe(200)

    for (const [label, width, height] of [
      ['tablet', 820, 1180],
      ['mobile', 390, 844],
    ] as const) {
      await test.step(`${label} viewport: no horizontal overflow, moved room still correctly positioned`, async () => {
        await page.setViewportSize({ width, height })
        const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth)
        expect(scrollWidth, `${label} must not overflow horizontally`).toBeLessThanOrEqual(width)

        const geometry = await readRoomGeometry(page, 'BATHROOM')
        expect(geometry.x).toBeCloseTo(EXPECTED_BASELINE.BATHROOM.x + 1, 2)
      })
    }
  })
})
