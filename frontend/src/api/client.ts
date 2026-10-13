import createClient from 'openapi-fetch'
import type { paths } from '../types/api'

// Paths and request/response types come from the backend's OpenAPI contract.
export const client = createClient<paths>()

client.use({
  async onResponse({ response }) {
    if (response.ok) return response
    let message = `Request failed (${response.status}). Please try again.`
    try {
      const body: unknown = await response.clone().json()
      if (body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string') {
        message = body.detail
      }
    } catch { /* Non-JSON errors still get a readable fallback. */ }
    throw new Error(message)
  },
})

export function requireData<T>(data: T | undefined): T {
  if (data === undefined) throw new Error('The server returned an empty response. Please try again.')
  return data
}
