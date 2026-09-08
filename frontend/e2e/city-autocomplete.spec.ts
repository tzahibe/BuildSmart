import { expect, test } from '@playwright/test'

/** Regression test for the reported bug: "dropdown city not working". Root cause (confirmed by
 * direct reproduction before this fix): the city field was a free-text `<input>` with a native
 * `<datalist>` — which only SUGGESTS matching options while typing, it never forces the field's
 * actual value to become one of them. Several real city names in this dataset don't match how
 * people naturally type them (e.g. the city is stored as "תל אביב - יפו", not "תל אביב"), so a user
 * who typed the natural short form and moved on ended up with a value matching nothing — the street
 * field then silently stayed disabled forever, and the form later rejected submission, with no clear
 * indication of what went wrong. Fixed with a custom autocomplete (Autocomplete.tsx) where every
 * suggestion is a real, clickable element that always lands the EXACT list value — typing to filter
 * is preserved, only how a selection actually lands changed.
 */

test.describe('City autocomplete — real UI', () => {
  test('typing the natural short form still surfaces and correctly selects the real (longer) city name', async ({ page }) => {
    await page.goto('/')
    const cityField = page.getByLabel('עיר / רשות מקומית')

    await cityField.fill('תל אביב')
    const suggestion = page.getByRole('option', { name: 'תל אביב - יפו', exact: true })
    await expect(suggestion).toBeVisible()

    await suggestion.click()
    await expect(cityField).toHaveValue('תל אביב - יפו')

    // street becomes selectable once a REAL city was actually chosen -- proves the fix, not just the
    // suggestion's visibility
    const streetField = page.getByLabel('רחוב ומספר')
    await expect(streetField).toBeEnabled({ timeout: 10_000 })
  })

  test('typing a partial match without clicking a suggestion is honestly rejected, never silently accepted', async ({ page }) => {
    await page.goto('/')
    await page.getByLabel('עיר / רשות מקומית').fill('תל אביב') // never clicked a suggestion
    await page.getByLabel('שטח מגרש (מ"ר)').fill('500')
    await page.getByLabel('שטח הבנייה (מ"ר)').fill('120')
    await page.getByLabel('תיאור הבית הרצוי').fill('בית עם 2 חדרי שינה')

    await page.getByRole('button', { name: 'המשך לבחירת מתאר הבניין' }).click()

    // rejected with a clear, existing error -- not a silent pass into the next step
    await expect(page.getByText('יש לבחור עיר / רשות מקומית מתוך הרשימה המוצעת')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'בחר/י את מתאר הבניין' })).not.toBeVisible()
  })

  test('a hyphenated multi-part city name (מודיעין-מכבים-רעות) is also found and selected correctly', async ({ page }) => {
    await page.goto('/')
    const cityField = page.getByLabel('עיר / רשות מקומית')

    await cityField.fill('מודיעין')
    const suggestion = page.getByRole('option', { name: 'מודיעין-מכבים-רעות', exact: true })
    await expect(suggestion).toBeVisible()
    await suggestion.click()
    await expect(cityField).toHaveValue('מודיעין-מכבים-רעות')
  })

  test('the suggestion list closes after a selection and does not obscure the rest of the form', async ({ page }) => {
    await page.goto('/')
    const cityField = page.getByLabel('עיר / רשות מקומית')
    await cityField.fill('מודיעין')
    await page.getByRole('option', { name: 'מודיעין-מכבים-רעות', exact: true }).click()

    await expect(page.getByRole('listbox')).toHaveCount(0)
  })

  test('re-confirming an already-selected city (typing the exact name, then also clicking its suggestion) does not wipe the streets it already loaded', async ({
    page,
  }) => {
    // Regression test for a second bug found while fixing the first: `handleCityChange` used to
    // unconditionally clear `streets` on every call, including a redundant call with the SAME
    // already-current city (e.g. typing the full correct name and then also clicking the shown
    // suggestion, or re-clicking a suggestion that already matches) — silently wiping the just-loaded
    // street list with no way to recover, since the fetch effect only re-fires when the city value
    // actually CHANGES. Reported live as "streets don't match the city" / the street field going
    // blank after appearing to work.
    await page.goto('/')
    const cityField = page.getByLabel('עיר / רשות מקומית')
    const streetField = page.getByLabel('רחוב ומספר')

    // Type the FULL exact city name directly (not an abbreviation), THEN also click its own
    // suggestion -- two calls with the identical final value, exactly the sequence that triggered it.
    await cityField.fill('מודיעין-מכבים-רעות')
    await page.getByRole('option', { name: 'מודיעין-מכבים-רעות', exact: true }).click()

    await expect(streetField).toBeEnabled({ timeout: 10_000 })
    await streetField.click()
    await expect(page.getByRole('option', { name: 'אגוז מכבים רעות', exact: true })).toBeVisible()
  })
})
