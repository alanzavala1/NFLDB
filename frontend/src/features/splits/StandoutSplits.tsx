import Card from '../../components/Card'
import type { selectStandouts } from './standouts'

export function StandoutSplits({ notable, entityLabel, isCareer, season }: {
  notable: ReturnType<typeof selectStandouts>; entityLabel: string; isCareer: boolean; season: number
}) {
  if (!notable || notable.items.length === 0) return null
  return (<Card title={`Where ${entityLabel} stands out`} className="mb-6" headerClassName="[&>div:first-child]:whitespace-normal">
    <div className="border-t border-surface-line p-4">
      <p className="text-xs text-ink-dim leading-relaxed mb-3">Biggest swings in {notable.met.label} vs {isCareer ? 'career' : season} average of {notable.met.fmt(notable.base)}.</p>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
        {notable.items.map((it, i) => {
          const good = notable.met.higherIsBetter ? it.delta > 0 : it.delta < 0
          return (
            <div key={i} className="bg-surface-card border border-surface-line rounded-xl px-3 py-2.5" style={{ boxShadow: `inset 0 2px 0 0 ${good ? 'rgba(16,185,129,0.7)' : 'rgba(244,63,94,0.7)'}` }}>
              <div className="text-xs font-semibold text-ink truncate flex items-center gap-1">{it.label}</div>
              <div className="text-[10px] text-ink-dim uppercase tracking-wide mb-1.5">{it.kind}</div>
              <div className="text-lg font-bold text-ink tabular-nums leading-none">{notable.met.fmt(it.v)}</div>
              <div className={`text-[11px] font-semibold tabular-nums mt-1 ${good ? 'text-data-win' : 'text-data-loss'}`}>
                {it.delta >= 0 ? '+' : '−'}{notable.met.fmt(Math.abs(it.delta))}<span className="text-ink-dim font-normal"> · {it.vol} {notable.unit}</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  </Card>)
}
