import { expect, test, type Page } from '@playwright/test'

/** End-to-end validation of the FOOTPRINT SELECTION step, through the real application UI —
 * inserted between "built area entered" and "plan generation starts" (see App.tsx). No project is
 * created until a footprint is actually confirmed, so most of these tests never touch the real
 * backend at all; the one exception (confirming) reuses the same real pipeline
 * e2e/spatial-edit.spec.ts already exercises.
 */

const CITY = 'מודיעין-מכבים-רעות'
const STREET = 'אגוז מכבים רעות'
const DESCRIPTION = 'בית עם 3 חדרי שינה וממ"ד'

async function fillFormOnly(page: Page, builtAreaM2: number) {
  await page.goto('/')
  await page.getByLabel('עיר / רשות מקומית').fill(CITY)
  const streetInput = page.getByLabel('רחוב ומספר')
  await expect(streetInput).toBeEnabled({ timeout: 10_000 })
  await streetInput.fill(STREET)
  await page.getByLabel('שטח מגרש (מ"ר)').fill('500')
  await page.getByLabel('שטח הבנייה (מ"ר)').fill(String(builtAreaM2))
  await page.getByLabel('תיאור הבית הרצוי').fill(DESCRIPTION)
}

async function goToFootprintStep(page: Page, builtAreaM2 = 120) {
  await fillFormOnly(page, builtAreaM2)
  await page.getByRole('button', { name: 'המשך לבחירת צורת המבנה' }).click()
  await expect(page.getByRole('heading', { name: 'בחר/י את צורת המבנה' })).toBeVisible()
}

test.describe('Footprint selection — real UI, no backend needed until confirmed', () => {
  test('choices appear only once the built area is known, with genuinely different shapes/dimensions', async ({ page }) => {
    await goToFootprintStep(page, 120)

    const continueButton = page.getByRole('button', { name: 'המשך ליצירת התכנון' })
    await expect(continueButton).toBeDisabled()

    const names = ['קומפקטי', 'מאוזן', 'רחב', 'צר ומוארך']
    const dims: string[] = []
    for (const name of names) {
      const card = page.locator('.footprint-card', { hasText: name })
      await expect(card).toBeVisible()
      const text = (await card.locator('.footprint-card__dims').innerText()).trim()
      dims.push(text)
      // every option preserves ~120 m2
      const area = Number((await card.locator('.footprint-card__area').innerText()).replace(/[^\d.]/g, ''))
      expect(Math.abs(area - 120)).toBeLessThan(1)
    }
    // no two options render the same dimensions
    expect(new Set(dims).size).toBe(dims.length)
  })

  test('selecting a preset stores it (enables continue); selecting another replaces it (single selection)', async ({ page }) => {
    await goToFootprintStep(page, 120)
    const continueButton = page.getByRole('button', { name: 'המשך ליצירת התכנון' })

    await page.locator('.footprint-card', { hasText: 'רחב' }).click()
    await expect(continueButton).toBeEnabled()
    await expect(page.locator('.footprint-card', { hasText: 'רחב' })).toHaveAttribute('aria-checked', 'true')

    await page.locator('.footprint-card', { hasText: 'צר ומוארך' }).click()
    await expect(page.locator('.footprint-card', { hasText: 'רחב' })).toHaveAttribute('aria-checked', 'false')
    await expect(page.locator('.footprint-card', { hasText: 'צר ומוארך' })).toHaveAttribute('aria-checked', 'true')
    await expect(continueButton).toBeEnabled()
  })

  test('CUSTOM: valid dimensions enable continue; invalid dimensions block it with visible live feedback', async ({ page }) => {
    await goToFootprintStep(page, 200)
    const continueButton = page.getByRole('button', { name: 'המשך ליצירת התכנון' })
    const customCard = page.getByTestId('footprint-card-custom')

    await page.getByTestId('footprint-custom-width').fill('9')
    await page.getByTestId('footprint-custom-depth').fill('20')
    await expect(customCard).toContainText('180.00')
    await expect(continueButton).toBeDisabled()

    await page.getByTestId('footprint-custom-width').fill('10')
    await expect(customCard).toContainText('200.00')
    await expect(customCard).toContainText('תואם לשטח היעד')
    await expect(continueButton).toBeEnabled()

    // the exact entered numbers are preserved, never silently changed
    await expect(page.getByTestId('footprint-custom-width')).toHaveValue('10')
    await expect(page.getByTestId('footprint-custom-depth')).toHaveValue('20')
  })

  test('changing built area after going back recalculates options and invalidates a stale selection', async ({ page }) => {
    await goToFootprintStep(page, 120)
    await page.locator('.footprint-card', { hasText: 'קומפקטי' }).click()
    const compactDimsAt120 = await page.locator('.footprint-card', { hasText: 'קומפקטי' }).locator('.footprint-card__dims').innerText()

    await page.getByRole('button', { name: '‹ חזרה לעריכת שטח הבנייה' }).click()
    await expect(page.getByLabel('שטח הבנייה (מ"ר)')).toHaveValue('120')

    await page.getByLabel('שטח הבנייה (מ"ר)').fill('240')
    await page.getByRole('button', { name: 'המשך לבחירת צורת המבנה' }).click()
    await expect(page.getByRole('heading', { name: 'בחר/י את צורת המבנה' })).toBeVisible()

    // recalculated: different dimensions for the same shape at the new area
    const compactDimsAt240 = await page.locator('.footprint-card', { hasText: 'קומפקטי' }).locator('.footprint-card__dims').innerText()
    expect(compactDimsAt240).not.toBe(compactDimsAt120)

    // stale selection cannot be submitted -- continue is disabled again until a fresh choice is made
    await expect(page.getByRole('button', { name: 'המשך ליצירת התכנון' })).toBeDisabled()
    await expect(page.locator('.footprint-card', { hasText: 'קומפקטי' })).toHaveAttribute('aria-checked', 'false')
  })

  test('responsive: footprint cards render without horizontal overflow at desktop, tablet, and mobile widths', async ({ page }) => {
    await goToFootprintStep(page, 120)

    for (const [label, width, height] of [
      ['desktop', 1280, 900],
      ['tablet', 820, 1180],
      ['mobile', 390, 844],
    ] as const) {
      await test.step(label, async () => {
        await page.setViewportSize({ width, height })
        const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth)
        expect(scrollWidth, `${label} must not overflow horizontally`).toBeLessThanOrEqual(width)
        await expect(page.locator('.footprint-card', { hasText: 'קומפקטי' })).toBeVisible()
      })
    }
  })

  test('existing project flow remains functional: confirming a footprint creates the project and reaches the real design pipeline', async ({
    page,
  }) => {
    await goToFootprintStep(page, 110)
    await page.locator('.footprint-card', { hasText: 'קומפקטי' }).click()
    await page.getByRole('button', { name: 'המשך ליצירת התכנון' }).click()

    await expect(page.locator('.sketch-svg').first()).toBeVisible({ timeout: 20_000 })
  })
})
