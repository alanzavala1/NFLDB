import type { AskHistoryMessage, AskRequest, ToolCall } from '../types'

const BASE = '/api'

// ── /ask streaming (Server-Sent Events) ─────────────────────────────────────
// Mirrors the backend events from run_ask_stream: a `tool` event per tool call,
// `delta` events for answer tokens, a final `done`, or an `error`.
export type AskEvent =
  | { type: 'tool'; tool: string }
  | { type: 'delta'; text: string }
  | { type: 'done'; answer: string; data: Record<string, unknown>[]; tools_used: ToolCall[] }
  | { type: 'error'; detail: string }

export async function askStream(
  question: string,
  history: AskHistoryMessage[],
  onEvent: (e: AskEvent) => void,
): Promise<void> {
  const res = await fetch(`${BASE}/ask/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, history } satisfies AskRequest),
  })
  if (!res.ok || !res.body) {
    // Pre-stream rejection (rate limit, bad input) comes back as normal JSON.
    let detail = `${res.status} ${res.statusText}`
    try { const j = await res.json(); if (j?.detail) detail = j.detail } catch { /* ignore */ }
    throw new Error(detail)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const frames = buf.split('\n\n')
    buf = frames.pop() ?? '' // keep the trailing partial frame
    for (const frame of frames) {
      const line = frame.split('\n').find((l) => l.startsWith('data:'))
      if (!line) continue
      try { onEvent(JSON.parse(line.slice(5).trim()) as AskEvent) } catch { /* ignore malformed frame */ }
    }
  }
}
