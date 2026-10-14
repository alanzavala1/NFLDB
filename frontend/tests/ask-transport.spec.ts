import { test, expect } from '@playwright/test'

// Controlled stream replies verify the moved client without calling a model.
test('Ask sends conversation history and renders the final streamed answer', async ({ page }) => {
  const requests: { question: string; history: { role: string; content: string }[] }[] = []
  await page.route(url => url.pathname.startsWith('/api/'), route => {
    expect(new URL(route.request().url()).pathname).toBe('/api/ask/stream')
    expect(route.request().method()).toBe('POST')
    requests.push(route.request().postDataJSON())
    const answer = requests.length === 1 ? 'Josh Allen threw 29 touchdowns.' : 'That was the 2023 season.'
    return route.fulfill({
      contentType: 'text/event-stream',
      body: `data: ${JSON.stringify({ type: 'done', answer, data: [], tools_used: [] })}\n\n`,
    })
  })
  await page.goto('/ask')
  const input = page.getByPlaceholder('Ask about any player, team or season since 1999…')
  await input.fill('  How did Josh Allen do?  ')
  await page.getByRole('button', { name: 'Send', exact: true }).click()
  await expect(page.getByText('Josh Allen threw 29 touchdowns.', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '+ New chat', exact: true })).toBeEnabled()
  await input.fill('Which season?')
  await page.getByRole('button', { name: 'Send', exact: true }).click()
  await expect(page.getByText('That was the 2023 season.', { exact: true })).toBeVisible()
  expect(requests).toEqual([
    { question: 'How did Josh Allen do?', history: [] },
    { question: 'Which season?', history: [
      { role: 'user', content: 'How did Josh Allen do?' },
      { role: 'assistant', content: 'Josh Allen threw 29 touchdowns.' },
    ] },
  ])
})

test('Ask displays a pre-stream rejection and permits another question', async ({ page }) => {
  await page.route(url => url.pathname.startsWith('/api/'), route => {
    expect(new URL(route.request().url()).pathname).toBe('/api/ask/stream')
    return route.fulfill({ status: 429, json: { detail: 'The assistant is busy. Please try later.' } })
  })
  await page.goto('/ask')
  const input = page.getByPlaceholder('Ask about any player, team or season since 1999…')
  await input.fill('Who led in rushing?')
  await page.getByRole('button', { name: 'Send', exact: true }).click()
  await expect(page.getByText('The assistant is busy. Please try later.', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '+ New chat', exact: true })).toBeEnabled()
  await input.fill('Who led in passing?')
  await expect(page.getByRole('button', { name: 'Send', exact: true })).toBeEnabled()
})
