import { expect } from '@playwright/test'
import { test } from './fixtures/scores'
import { mockSplits } from './fixtures/splits'
import { playerProfile } from './fixtures/playerProfile'

for (const width of [320, 390, 1280]) {
  test(`search results remain visible outside the controls and accept keyboard selection at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 })
    await mockSplits(page)
    await page.route(url => url.pathname === '/api/search', route => route.fulfill({ json: Array.from({ length: 5 }, (_, i) => ({
      type: 'player', id: `result-${i}`, name: `Search quarterback ${i}`, position: 'QB', team: 'BUF', headshot_url: null,
    })) }))
    await page.goto('/splits')
    const search = page.getByRole('textbox', { name: 'Add player', exact: true })
    await search.fill('quarterback')
    const lastResult = page.getByRole('button', { name: /^Search quarterback 4/ })
    await expect(lastResult).toBeVisible()
    expect(await lastResult.evaluate(element => {
      const box = element.getBoundingClientRect()
      const hit = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2)
      return hit !== null && element.contains(hit)
    })).toBe(true)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await search.press('Tab')
    await expect(page.getByRole('button', { name: /^Search quarterback 0/ })).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('button', { name: 'Remove Search quarterback 0', exact: true })).toBeVisible()
    await expect(page).toHaveURL(/p=result-0/)
    await expect(search).toHaveValue('')
  })
}

test('phone tables retain row labels while scrolling and sorting works by keyboard', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockSplits(page)
  await page.goto('/splits?p=test-player&season=2023')
  const down = page.getByRole('button', { name: /^By Down / }).locator('..')
  const firstLabel = down.getByRole('cell', { name: '1st Down', exact: true })
  await expect(firstLabel).toBeVisible()
  const scroller = down.getByRole('region')
  await scroller.evaluate(element => { element.scrollLeft = element.scrollWidth })
  const labelBox = await firstLabel.boundingBox()
  const scrollBox = await scroller.boundingBox()
  expect(labelBox).not.toBeNull()
  expect(scrollBox).not.toBeNull()
  expect(Math.abs(labelBox!.x - scrollBox!.x)).toBeLessThan(2)
  const yards = down.getByRole('button', { name: 'YDS', exact: true })
  await yards.focus()
  await page.keyboard.press('Enter')
  await expect(down.getByRole('columnheader', { name: /^YDS/ })).toHaveAttribute('aria-sort', 'descending')
  await page.keyboard.press('Enter')
  await expect(down.getByRole('row').nth(1)).toContainText('3rd Down')
  await expect(down.getByRole('columnheader', { name: /^YDS/ })).toHaveAttribute('aria-sort', 'ascending')
})

test('six long player names fit on a narrow phone and keep usable removal controls', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 844 })
  await mockSplits(page)
  await page.route(url => /^\/api\/players\/[^/]+$/.test(url.pathname), route => route.fulfill({ json: {
    ...playerProfile, player_name: 'A very long quarterback comparison name',
  } }))
  await page.goto('/splits?p=one,two,three,four,five,six&season=2023')
  const removals = page.getByRole('button', { name: /^Remove A very long/ })
  await expect(removals).toHaveCount(6)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  for (const button of await removals.all()) {
    const box = await button.boundingBox()
    expect(box!.width).toBeGreaterThanOrEqual(40)
    expect(box!.x + box!.width).toBeLessThanOrEqual(320)
  }
  await removals.first().click()
  await expect(removals).toHaveCount(5)
})
