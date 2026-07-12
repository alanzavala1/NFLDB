import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import Nav from '../components/Nav'
import Card from '../components/Card'
import { askStream } from '../api'
import type { ToolCall } from '../types'

const EXAMPLES = [
  'How did Josh Allen do under pressure in 2023?',
  'Who led the NFL in rushing yards in 2022?',
  'Which players are most similar to Justin Jefferson?',
  'How is the Chiefs defense in the red zone in 2023?',
  'Has Josh Allen ever won MVP?',
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
  thead: ({ node, ...p }) => { void node; return <thead className="bg-surface-card/80 text-left text-ink-mid" {...p} /> },
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
      <div className="overflow-x-auto rounded-xl border border-surface-line">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-surface-card/80 text-left text-ink-mid">
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
    <div className="space-y-3">
      {data.map((row, i) => (
        <div key={i} className="grid gap-3 sm:grid-cols-2">
          {Object.entries(row).map(([k, v]) => (
            <div key={k} className="rounded-xl border border-surface-line bg-surface-card/40 p-3">
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
    <div className="mb-3 flex flex-wrap items-center gap-x-2 gap-y-1.5 text-xs text-ink-dim">
      <span className="text-ink-dim">Working</span>
      {names.map((n, i) => (
        <span key={i} className="inline-flex items-center gap-2">
          {i > 0 && <span className="text-ink-dim">›</span>}
          <span className="rounded-md bg-surface-raise/70 px-2 py-0.5 text-ink-mid">{TOOL_LABELS[n] ?? n}</span>
        </span>
      ))}
      <span className="h-2 w-2 animate-pulse rounded-full bg-indigo-500" />
    </div>
  )
}

export default function AskPage() {
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [answer, setAnswer] = useState('')
  const [data, setData] = useState<Record<string, unknown>[]>([])
  const [tools, setTools] = useState<ToolCall[]>([])
  const [live, setLive] = useState<string[]>([])

  async function run(q: string) {
    const query = q.trim()
    if (!query || loading) return
    setLoading(true); setError(null); setAnswer(''); setData([]); setTools([]); setLive([])
    try {
      await askStream(query, (e) => {
        if (e.type === 'tool') {
          // A tool call means any text streamed so far wasn't the final answer.
          setLive((p) => [...p, e.tool]); setAnswer('')
        } else if (e.type === 'delta') {
          setAnswer((p) => p + e.text)
        } else if (e.type === 'done') {
          setAnswer(e.answer); setData(e.data ?? []); setTools(e.tools_used ?? [])
        } else if (e.type === 'error') {
          setError(e.detail)
        }
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong.')
    } finally {
      setLoading(false)
    }
  }

  const hasOutput = loading || !!answer || tools.length > 0 || data.length > 0

  return (
    <div className="min-h-screen bg-surface-bg text-ink">
      <Nav />
      <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
        <Card title="Ask the data" className="mb-4">
        <p className="border-t border-surface-line px-4 py-3 text-sm leading-relaxed text-ink-mid">
          Ask in plain English. Answers come only from the platform's verified
          stats — every number is pulled through the same queries the rest of the
          site uses, never made up.
        </p></Card>

        <Card title="Start a conversation" className="mb-4"><form onSubmit={(e) => { e.preventDefault(); run(question) }} className="flex gap-2 border-t border-surface-line p-4">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="e.g. How did Josh Allen do under pressure in 2023?"
            maxLength={500}
            className="flex-1 rounded-xl border border-surface-line bg-surface-card px-4 py-3 text-sm text-ink placeholder:text-ink-dim transition-colors focus:border-indigo-500 focus:outline-none"
          />
          <button
            type="submit"
            disabled={loading || !question.trim()}
            className="rounded-xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-ink transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? 'Thinking…' : 'Ask'}
          </button>
        </form>

        <div className="flex flex-wrap gap-2 border-t border-surface-line p-4">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              onClick={() => { setQuestion(ex); run(ex) }}
              disabled={loading}
              className="rounded-full border border-surface-line bg-surface-card/50 px-3 py-1.5 text-xs text-ink-mid transition-colors hover:border-surface-line hover:text-ink disabled:opacity-50"
            >
              {ex}
            </button>
          ))}
        </div></Card>

        {error && (
          <div className="mt-6 rounded-xl border border-red-900/60 bg-red-950/40 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {hasOutput && !error && (
          <div className="mt-8 space-y-4">
            <Card title="Answer"><div className="border-t border-surface-line p-5">
              {loading && tools.length === 0 && <LiveTools names={live} />}
              {answer ? (
                <div className="text-[15px]">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD}>
                    {answer}
                  </ReactMarkdown>
                </div>
              ) : (
                loading && live.length === 0 && (
                  <div className="flex items-center gap-2 text-sm text-ink-dim">
                    <span className="h-2 w-2 animate-pulse rounded-full bg-indigo-500" />
                    Pulling the numbers…
                  </div>
                )
              )}
              {tools.length > 0 && <Transparency tools={tools} />}
            </div></Card>
            {data.length > 0 && <DataView data={data} />}
          </div>
        )}
      </div>
    </div>
  )
}
