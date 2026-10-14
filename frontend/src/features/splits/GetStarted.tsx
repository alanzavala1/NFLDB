import Card from '../../components/Card'
import type { ComparisonMode, Example } from './types'
import { PLAYER_EXAMPLES, TEAM_EXAMPLES } from './presets'

export function GetStarted({ mode, loadExample }: { mode: ComparisonMode; loadExample: (example: Example) => unknown }) {
  return (<Card title="Get started" className="mb-6">
    <div className="border-t border-surface-line px-4 py-8 sm:px-6 sm:py-10 text-center">
      <p className="text-ink font-semibold">Compare anyone, in any situation</p>
      <p className="text-ink-dim text-sm mt-1.5 max-w-md mx-auto">Search above to add up to six {mode === 'players' ? 'players' : 'teams'} — or start from one of these:</p>
      <div className="mt-5 flex flex-wrap justify-center gap-2">
        {(mode === 'players' ? PLAYER_EXAMPLES : TEAM_EXAMPLES).map(ex => (
          <button key={ex.label} onClick={() => loadExample(ex)}
            className="rounded-full border border-surface-line bg-surface-raise/40 px-3.5 py-2 text-xs font-semibold text-ink-mid hover:border-indigo-500/60 hover:text-ink transition-colors">
            {ex.label}
          </button>
        ))}
      </div>
      <div className="mt-8 grid gap-4 sm:grid-cols-3 max-w-2xl mx-auto text-left">
        {[
          ['1', 'Add players or teams', 'up to six, side by side'],
          ['2', 'Pick a lens', 'stat category, season or career'],
          ['3', 'Drill in', 'by down, game script, opponent — to the game'],
        ].map(([n, t, s]) => (
          <div key={n} className="flex min-w-0 items-start gap-2.5 rounded-xl border border-surface-line p-3">
            <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-surface-raise text-[10px] font-bold text-ink-mid">{n}</span>
            <div>
              <div className="text-xs font-semibold text-ink">{t}</div>
              <div className="mt-0.5 text-[11px] leading-snug text-ink-dim">{s}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  </Card>)
}
