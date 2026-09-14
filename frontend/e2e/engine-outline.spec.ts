import { expect, test, type Page } from '@playwright/test'

/** Feature 006 through the REAL application: brief + site -> the engine chooses the outline ->
 * primary + alternatives; and the advanced explicit outline, both when it plans and when it does
 * not. Needs a live backend (the parse step calls the requirements parser) — run against dev
 * servers, e.g. backend on :8006 and `vite --port 5186` proxying to it, with
 * `E2E_BASE_URL=http://localhost:5186 SMOKE_SHOTS=/tmp/shots npx playwright test e2e/engine-outline.spec.ts`.
 * Screenshots of each screen land in SMOKE_SHOTS. */

const CITY = 'מודיעין-מכבים-רעות'
const STREET = 'אגוז מכבים רעות'
const SHOT = process.env.SMOKE_SHOTS ?? '/tmp'

async function pick(page: Page, label: string, value: string) {
  const field = page.getByLabel(label)
  await field.fill(value)
  await page.getByRole('option', { name: value, exact: true }).click()
  await expect(field).toHaveValue(value)
}

async function fillBrief(page: Page) {
  await page.goto('/')
  await pick(page, 'עיר / רשות מקומית', CITY)
  await expect(page.getByLabel('רחוב ומספר')).toBeEnabled({ timeout: 10_000 })
  await pick(page, 'רחוב ומספר', STREET)
  await page.getByLabel("רוחב מגרש (מ')").fill('21')
  await page.getByLabel("עומק מגרש (מ')").fill('24.5')
  await page.getByLabel("חזית (מ')").fill('5.5')
  await page.getByLabel("אחורית (מ')").fill('4')
  await page.getByLabel("צדדים (מ')").fill('3')
  await page.getByLabel('שטח בנייה בקומה אחת (טביעת רגל) (מ"ר)').fill('176')
  await page.getByLabel('תיאור הבית הרצוי').fill('בית עם שלושה חדרי שינה, ממ"ד, שני חדרי רחצה ומטבח פתוח לסלון')
}

test('main flow: brief + site -> engine chooses the outline -> primary + diverse alternatives', async ({ page }) => {
  test.setTimeout(180_000)
  await fillBrief(page)
  await expect(page.getByText(/המערכת בוחרת את צורת הבניין בעצמה/)).toBeVisible()
  await page.screenshot({ path: `${SHOT}/01-form.png`, fullPage: true })
  await page.getByRole('button', { name: 'המשך ליצירת התכנון' }).click()
  await expect(page.getByRole('heading', { name: /בחר\/י את מתאר הבניין/ })).toHaveCount(0)
  await expect(page.getByText('זה מה שהבנתי')).toBeVisible({ timeout: 90_000 })
  await expect(page.getByText(/ייקבע אוטומטית לפי השטח המבוקש/)).toBeVisible()
  await page.screenshot({ path: `${SHOT}/02-review.png`, fullPage: true })
  await page.getByRole('button', { name: 'יצירת תוכנית' }).click()
  const outline = page.getByTestId('plan-outline')
  await expect(outline).toBeVisible({ timeout: 120_000 })
  const text = await outline.innerText()
  expect(text).toContain('מתאר אוטומטי')
  const thumbs = await page.locator('.workspace-option').count()
  console.log(`PLAN outline=${text} alternatives=${thumbs}`)
  await page.screenshot({ path: `${SHOT}/03-plan.png`, fullPage: true })
})

async function advanced(page: Page, card: string) {
  await fillBrief(page)
  await page.getByRole('button', { name: /מתקדם — קביעת מתאר ידנית/ }).click()
  await expect(page.getByText(card).first()).toBeVisible({ timeout: 15_000 })
  await page.getByText(card).first().click()
  const [request] = await Promise.all([
    page.waitForRequest((r) => r.url().endsWith('/projects') && r.method() === 'POST'),
    page.getByRole('button', { name: 'המשך ליצירת התכנון' }).click(),
  ])
  const body = request.postDataJSON()
  expect(body.selected_footprint.source).toBe('PRESET')
  await expect(page.getByText('זה מה שהבנתי')).toBeVisible({ timeout: 90_000 })
  await expect(page.getByText('מתאר הבית שנבחר')).toBeVisible()
  await page.getByRole('button', { name: 'יצירת תוכנית' }).click()
  const outline = page.getByTestId('plan-outline')
  await expect(outline).toBeVisible({ timeout: 120_000 })
  return { body, text: await outline.innerText() }
}

test('advanced: an explicit outline that plans is the plan shown, labelled as the person\'s', async ({ page }) => {
  test.setTimeout(180_000)
  const { body, text } = await advanced(page, 'קומפקטי')
  console.log(`ADVANCED(balanced) sent ${body.selected_footprint.width_m}x${body.selected_footprint.depth_m} -> ${text}`)
  expect(text).toContain('המתאר שהזנת')
  expect(text).toContain(body.selected_footprint.width_m.toFixed(2))
  await expect(page.getByRole('note')).toHaveCount(0)
  await page.screenshot({ path: `${SHOT}/05-advanced-plan.png`, fullPage: true })
})

test('advanced: an explicit outline that cannot be planned is replaced, and the screen says so', async ({ page }) => {
  test.setTimeout(180_000)
  const { body, text } = await advanced(page, 'צר ומוארך')
  console.log(`ADVANCED(narrow) sent ${body.selected_footprint.width_m}x${body.selected_footprint.depth_m} -> ${text}`)
  expect(text).toContain('מתאר אוטומטי')
  const note = page.getByRole('note')
  await expect(note).toBeVisible()
  await expect(note).toContainText(body.selected_footprint.width_m.toFixed(2))
  await page.screenshot({ path: `${SHOT}/06-advanced-replaced.png`, fullPage: true })
})
