import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import Nav from '../components/Nav'
import { askStream } from '../api'
import type { AskHistoryMessage, ToolCall } from '../types'

// Welcome-screen prompts, grouped so a first-time visitor learns the range of
// what the agent can answer by reading the grid.
const EXAMPLE_GROUPS: { label: string; examples: string[] }[] = [
  { label: 'Players', examples: ['How did Josh Allen do under pressure in 2023?', 'Which players are most similar to Justin Jefferson?'] },
  { label: 'Leaders & awards', examples: ['Who led the NFL in rushing yards in 2022?', 'Has Josh Allen ever won MVP?'] },
  { label: 'Teams', examples: ['How is the Chiefs defense in the red zone in 2023?', 'Which team had the best offense in 2024?'] },
  { label: 'Situations', examples: ['How does Derrick Henry run on 3rd and short?', 'Who is best deep passer this season?'] },
]

// Tool names → friendly labels for the "how I got this" line.
const TOOL_LABELS: Record<string, string> = {
  resolve_entity: 'looked up',
  get_player_overview: 'player overview',
  get_player_splits: 'player splits',
  get_team_splits: 'team splits',
  get_leaders: 'league leaders',
  get_standings: 'standings',
  get_comparables: 'comparable players',
  get_metadata: 'data catalog',
  report_data_gap: 'noted a data gap',
}

// Markdown styled by hand (no tailwind typography plugin in this project).
// `node` is pulled out of each component's props so it isn't spread onto the DOM
// element (React warns on unknown props); `void node` marks it intentionally
// unused.
const MD: Components = {
  p: ({ node, ...p }) => { void node; return <p className="mb-3 leading-relaxed text-ink last:mb-0" {...p} /> },
  strong: ({ node, ...p }) => { void node; return <strong className="font-semibold text-ink" {...p} /> },
  em: ({ node, ...p }) => { void node; return <em className="text-ink-mid" {...p} /> },
  ul: ({ node, ...p }) => { void node; return <ul className="mb-3 ml-5 list-disc space-y-1.5 marker:text-ink-dim last:mb-0" {...p} /> },
  ol: ({ node, ...p }) => { void node; return <ol className="mb-3 ml-5 list-decimal space-y-1.5 marker:text-ink-dim last:mb-0" {...p} /> },
  li: ({ node, ...p }) => { void node; return <li className="pl-1 leading-relaxed text-ink" {...p} /> },
  h1: ({ node, ...p }) => { void node; return <h3 className="mb-2 mt-4 text-base font-semibold text-ink first:mt-0" {...p} /> },
  h2: ({ node, ...p }) => { void node; return <h3 className="mb-2 mt-4 text-base font-semibold text-ink first:mt-0" {...p} /> },
  h3: ({ node, ...p }) => { void node; return <h4 className="mb-1.5 mt-3 text-sm font-semibold uppercase tracking-wide text-ink-mid first:mt-0" {...p} /> },
  code: ({ node, ...p }) => { void node; return <code className="rounded bg-surface-raise px-1.5 py-0.5 text-[13px] text-ink-mid" {...p} /> },
  a: ({ node, ...p }) => { void node; return <a className="text-indigo-400 underline hover:text-ink-mid" {...p} /> },
  table: ({ node, ...p }) => {
    void node
    return (
      <div className="my-3 overflow-x-auto rounded-lg border border-surface-line">
        <table className="w-full text-sm" {...p} />
      </div>
    )
  },
  thead: ({ node, ...p }) => { void node; return <thead className="bg-surface-raise/60 text-left text-ink-mid" {...p} /> },
  th: ({ node, ...p }) => { void node; return <th className="px-3 py-2 font-medium" {...p} /> },
  td: ({ node, ...p }) => { void node; return <td className="border-t border-surface-line/70 px-3 py-2 text-ink" {...p} /> },
}

function prettyKey(k: string): string {
  return k.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function isPrimitive(v: unknown): boolean {
  return v === null || typeof v !== 'object'
}

function fmt(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number') {
    return Number.isInteger(v) && Math.abs(v) >= 1000 ? v.toLocaleString() : String(v)
  }
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

// The "how I got this" line: the chain of real tool calls, minus internal ids.
function Transparency({ tools }: { tools: ToolCall[] }) {
  if (!tools.length) return null
  return (
    <div className="mt-4 flex flex-wrap items-center gap-x-2 gap-y-1.5 border-t border-surface-line pt-3 text-xs text-ink-dim">
      <span className="text-ink-dim">How I got this</span>
      {tools.map((t, i) => {
        const args = Object.entries((t.args ?? {}) as Record<string, unknown>)
          .filter(([k]) => k !== 'player_id')
          .map(([, v]) => String(v))
          .join(' · ')
        return (
          <span key={i} className="inline-flex items-center gap-2">
            {i > 0 && <span className="text-ink-dim">›</span>}
            <span className="rounded-md bg-surface-raise/70 px-2 py-0.5 text-ink-mid">
              {TOOL_LABELS[t.tool] ?? t.tool}
              {args && <span className="text-ink-dim"> · {args}</span>}
            </span>
          </span>
        )
      })}
    </div>
  )
}

// Flat list of rows → table. Single nested object (player overview) → labelled
// key/value blocks. Keeps both shapes readable.
function DataView({ data }: { data: Record<string, unknown>[] }) {
  if (!data.length) return null
  const allPrimitive = data.every((row) => Object.values(row).every(isPrimitive))

  if (allPrimitive) {
    const cols = Array.from(new Set(data.flatMap((r) => Object.keys(r))))
    return (
      <div className="mt-4 overflow-x-auto rounded-xl border border-surface-line">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-surface-raise/60 text-left text-ink-mid">
              {cols.map((c) => (
                <th key={c} className="px-3 py-2 font-medium whitespace-nowrap">{prettyKey(c)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row, i) => (
              <tr key={i} className="border-t border-surface-line/70 text-ink">
                {cols.map((c) => (
                  <td key={c} className="px-3 py-2 whitespace-nowrap">{fmt(row[c])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  return (
    <div className="mt-4 space-y-3">
      {data.map((row, i) => (
        <div key={i} className="grid gap-3 sm:grid-cols-2">
          {Object.entries(row).map(([k, v]) => (
            <div key={k} className="rounded-xl border border-surface-line bg-surface-raise/30 p-3">
              <div className="mb-1.5 text-xs font-medium uppercase tracking-wide text-ink-dim">{prettyKey(k)}</div>
              {isPrimitive(v) ? (
                <div className="text-sm text-ink">{fmt(v)}</div>
              ) : (
                <div className="space-y-1">
                  {Object.entries(v as Record<string, unknown>).map(([kk, vv]) => (
                    <div key={kk} className="flex justify-between gap-3 text-sm">
                      <span className="text-ink-dim">{prettyKey(kk)}</span>
                      <span className="font-medium text-ink">{fmt(vv)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

// The in-progress tool chain, shown live while the agent works.
function LiveTools({ names }: { names: string[] }) {
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 text-xs text-ink-dim">
      <span className="h-2 w-2 animate-pulse rounded-full bg-indigo-500" />
      <span>{names.length ? 'Running queries' : 'Reading the question'}</span>
      {names.map((n, i) => (
        <span key={i} className="inline-flex items-center gap-2">
          {i > 0 && <span className="text-ink-dim">›</span>}
          <span className="rounded-md bg-surface-raise/70 px-2 py-0.5 text-ink-mid">{TOOL_LABELS[n] ?? n}</span>
        </span>
      ))}
    </div>
  )
}

type Exchange = {
  q: string
  answer: string
  data: Record<string, unknown>[]
  tools: ToolCall[]
  live: string[]
  error: string | null
  loading: boolean
}

const MAX_HISTORY_MESSAGES = 12

function historyFrom(exchanges: Exchange[]): AskHistoryMessage[] {
  return exchanges
    .flatMap<AskHistoryMessage>((exchange) => {
      const messages: AskHistoryMessage[] = [
        { role: 'user', content: exchange.q },
      ]
      const answer = exchange.answer.trim()
      if (answer) messages.push({ role: 'assistant', content: answer })
      return messages
    })
    .slice(-MAX_HISTORY_MESSAGES)
}

function Mark({ size = 'h-7 w-7 text-[10px]' }: { size?: string }) {
  return (
    <span className={`flex shrink-0 select-none items-center justify-center rounded-full bg-indigo-600/20 font-black tracking-tight text-indigo-300 ring-1 ring-indigo-500/40 ${size}`}>
      DB
    </span>
  )
}

function Welcome({ onAsk, disabled }: { onAsk: (q: string) => void; disabled: boolean }) {
  return (
    <div className="ask-fade flex flex-col items-center px-2 pb-10 pt-14 text-center sm:pt-20">
      <Mark size="h-12 w-12 text-sm" />
      <h1 className="mt-5 text-3xl font-black tracking-tight text-ink">Ask NFLDB</h1>
      <p className="mt-3 max-w-md text-sm leading-relaxed text-ink-mid">
        Plain-English answers from 27 seasons of play-by-play. Every number is
        pulled through the site's own verified queries — never made up.
      </p>

      <div className="mt-9 grid w-full gap-2.5 text-left sm:grid-cols-2">
        {EXAMPLE_GROUPS.map((g) => (
          <div key={g.label} className="rounded-2xl bg-surface-card p-3">
            <div className="mb-2 px-1 text-[10px] font-bold uppercase tracking-[0.14em] text-ink-dim">{g.label}</div>
            <div className="space-y-1">
              {g.examples.map((ex) => (
                <button
                  key={ex}
                  onClick={() => onAsk(ex)}
                  disabled={disabled}
                  className="block w-full rounded-lg px-2.5 py-2 text-left text-[13px] leading-snug text-ink-mid transition-colors hover:bg-surface-raise hover:text-ink disabled:opacity-50"
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-9 flex max-w-lg flex-wrap items-start justify-center gap-x-6 gap-y-3 text-left">
        {[
          ['1', 'Ask in plain English', 'players, teams, leaders, awards, situations'],
          ['2', 'It runs real queries', 'watch the chain of database lookups live'],
          ['3', 'Answer with receipts', 'the data and every step shown under it'],
        ].map(([n, t, s]) => (
          <div key={n} className="flex w-44 items-start gap-2.5">
            <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-surface-raise text-[10px] font-bold text-ink-mid">{n}</span>
            <div>
              <div className="text-xs font-semibold text-ink">{t}</div>
              <div className="mt-0.5 text-[11px] leading-snug text-ink-dim">{s}</div>
            </div>
          </div>
        ))}
      </div>
      <p className="mt-6 text-[11px] text-ink-dim">Ask follow-ups — the agent carries the conversation's text context forward.</p>
    </div>
  )
}

export default function AskPage() {
  const [question, setQuestion] = useState('')
  const [exchanges, setExchanges] = useState<Exchange[]>([])
  const endRef = useRef<HTMLDivElement | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)
  const loading = exchanges.at(-1)?.loading ?? false

  const patchLast = (patch: Partial<Exchange> | ((e: Exchange) => Partial<Exchange>)) =>
    setExchanges((xs) => xs.map((e, i) => i === xs.length - 1 ? { ...e, ...(typeof patch === 'function' ? patch(e) : patch) } : e))

  async function run(q: string) {
    const query = q.trim()
    if (!query || loading) return
    const history = historyFrom(exchanges)
    setQuestion('')
    setExchanges((xs) => [...xs, { q: query, answer: '', data: [], tools: [], live: [], error: null, loading: true }])
    try {
      await askStream(query, history, (e) => {
        if (e.type === 'tool') {
          // A tool call means any text streamed so far wasn't the final answer.
          patchLast((prev) => ({ live: [...prev.live, e.tool], answer: '' }))
        } else if (e.type === 'delta') {
          patchLast((prev) => ({ answer: prev.answer + e.text }))
        } else if (e.type === 'done') {
          patchLast({ answer: e.answer, data: e.data ?? [], tools: e.tools_used ?? [] })
        } else if (e.type === 'error') {
          patchLast({ error: e.detail })
        }
      })
    } catch (e) {
      patchLast({ error: e instanceof Error ? e.message : 'Something went wrong.' })
    } finally {
      patchLast({ loading: false })
      inputRef.current?.focus()
    }
  }

  // Follow the conversation as it grows and while an answer streams in.
  const lastLen = exchanges.length ? exchanges.at(-1)!.answer.length + exchanges.at(-1)!.live.length : 0
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [exchanges.length, lastLen])

  return (
    <div className="flex min-h-screen flex-col bg-surface-bg text-ink">
      <style>{`
        @keyframes ask-in { from { opacity: 0; transform: translateY(6px) } to { opacity: 1; transform: none } }
        .ask-fade { animation: ask-in .35s ease both }
        @media (prefers-reduced-motion: reduce) { .ask-fade { animation: none } }
      `}</style>
      <Nav />
      <div className="mx-auto w-full max-w-3xl flex-1 px-4 sm:px-6">
        {exchanges.length === 0 ? (
          <Welcome onAsk={run} disabled={loading} />
        ) : (
          <div className="space-y-7 py-8">
            <div className="flex items-center gap-2.5">
              <Mark />
              <span className="text-sm font-bold text-ink">Ask NFLDB</span>
              <button
                onClick={() => { setExchanges([]); setQuestion(''); inputRef.current?.focus() }}
                disabled={loading}
                className="ml-auto rounded-full border border-surface-line px-3 py-1.5 text-xs font-semibold text-ink-mid transition-colors hover:border-indigo-500/60 hover:text-ink disabled:opacity-50"
              >
                + New chat
              </button>
            </div>
            {exchanges.map((ex, i) => (
              <div key={i} className="ask-fade space-y-4">
                <div className="flex justify-end">
                  <div className="max-w-[85%] rounded-2xl rounded-br-md bg-indigo-600 px-4 py-2.5 text-sm leading-relaxed text-white">{ex.q}</div>
                </div>
                <div className="flex items-start gap-3">
                  <Mark />
                  <div className="min-w-0 flex-1 rounded-2xl rounded-tl-md bg-surface-card px-4 py-3.5 sm:px-5">
                    {ex.error ? (
                      <div className="text-sm text-data-loss">{ex.error}</div>
                    ) : (
                      <>
                        {ex.loading && !ex.answer && <LiveTools names={ex.live} />}
                        {ex.answer && (
                          <div className="text-[15px]">
                            <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD}>
                              {ex.answer}
                            </ReactMarkdown>
                          </div>
                        )}
                        {ex.data.length > 0 && <DataView data={ex.data} />}
                        {ex.tools.length > 0 && <Transparency tools={ex.tools} />}
                      </>
                    )}
                  </div>
                </div>
              </div>
            ))}
            <div ref={endRef} />
          </div>
        )}
      </div>

      <div className="sticky bottom-0 border-t border-surface-line bg-surface-bg/90 backdrop-blur">
        <form
          onSubmit={(e) => { e.preventDefault(); run(question) }}
          className="mx-auto flex w-full max-w-3xl items-center gap-2 px-4 py-3.5 sm:px-6"
        >
          <div className="flex flex-1 items-center rounded-2xl border border-surface-line bg-surface-card transition-colors focus-within:border-indigo-500">
            <input
              ref={inputRef}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask about any player, team or season since 1999…"
              maxLength={500}
              autoFocus
              className="flex-1 bg-transparent px-4 py-3 text-sm text-ink placeholder:text-ink-dim focus:outline-none"
            />
            <button
              type="submit"
              disabled={loading || !question.trim()}
              aria-label="Send"
              className="mr-1.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-indigo-600 text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {loading
                ? <span className="h-2 w-2 animate-pulse rounded-full bg-white" />
                : <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8 13V3M3.5 7.5 8 3l4.5 4.5" /></svg>}
            </button>
          </div>
        </form>
        <p className="pb-2.5 text-center text-[10px] text-ink-dim">Answers come only from NFLDB's verified stats — nothing is made up.</p>
      </div>
    </div>
  )
}
